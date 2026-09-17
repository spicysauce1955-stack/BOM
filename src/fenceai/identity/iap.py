"""Google's Identity-Aware Proxy, verified rather than trusted.

`X-Goog-Authenticated-User-Email` is a header, and a header is spoofable by
anything that reaches the service directly — which includes the `*.run.app` URL
Cloud Run publishes alongside the load balancer. So the signed assertion is
verified against Google's public keys AND the deployment locks ingress to
internal-and-load-balancer. Either alone is a hole; this file is the first half.

`jwt` is imported INSIDE the methods. `pyjwt` lives in the optional `iap`
extra, and a module-level import would make `uv sync` with no extras fail to
start the app — spending the offline property CLAUDE.md states, in a file that
only a deployment ever constructs.
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable, Mapping

from fenceai.identity.ports import Principal

IAP_HEADER = "x-goog-iap-jwt-assertion"
_ISSUER = "https://cloud.google.com/iap"
_KEY_URL = "https://www.gstatic.com/iap/verify/public_key"
#: Long enough that every request is not a fetch, short enough that a rotation
#: is picked up without a redeploy.
_KEY_TTL_SECONDS = 3600
#: How much longer a fetch FAILURE is tolerated before the cached keys are
#: refused outright, on top of the TTL above. Google rotates these keys on a
#: schedule measured in days, not hours, so a key that verified a signature an
#: hour ago is overwhelmingly likely to still be one of the current ones —
#: this is a judgement call trading a longer window of stale-but-still-good
#: keys against the small risk of accepting a signature from a key Google has
#: since revoked, and it errs toward staying up through a transient gstatic
#: outage rather than refusing every request over a fetch that will very
#: likely succeed on the next attempt.
_KEY_STALE_GRACE_SECONDS = 6 * 3600
#: How often a failed refresh is retried once the cache is already stale.
#: Without this, an outage turns every single request into a blocking,
#: 5-second-timeout fetch attempt; this caps that cost without weakening the
#: grace window above, which governs correctness rather than request latency.
_KEY_RETRY_BACKOFF_SECONDS = 60


class IapIdentity:
    """Verifies the assertion and returns who Google says this is.

    `fetch_keys` is injectable for exactly one reason: a test that needed the
    real Google to run would not be run. The tests generate their own ES256 key
    pair and hand the public half in here, so the signature check under test is
    the real one and only the issuer is fabricated.
    """

    provider_id = "iap"

    def __init__(self, audience: str,
                 fetch_keys: Callable[[], dict[str, Any]] | None = None) -> None:
        if not audience:
            raise RuntimeError(
                "IapIdentity needs an audience: an unchecked `aud` accepts an "
                "assertion Google minted for somebody else's service")
        self._audience = audience
        self._fetch = fetch_keys or self._fetch_google_keys
        self._keys: dict[str, Any] | None = None
        #: `monotonic()`, not `time()`: a backwards wall-clock step (NTP
        #: correction, a laptop suspend) must never make the cache look
        #: freshER than it is — it should only ever make it look staler,
        #: which just triggers an extra fetch, never a security hole.
        self._fetched_at = 0.0
        self._last_attempt_at = 0.0

    def _fetch_google_keys(self) -> dict[str, Any]:
        import json
        import urllib.request
        with urllib.request.urlopen(_KEY_URL, timeout=5) as r:
            return json.loads(r.read())

    def _key_for(self, kid: str) -> Any:
        now = time.monotonic()
        if self._keys is None:
            # Nothing cached yet, so there is no stale copy to fall back to —
            # a failure here has to propagate. `principal()` turns it into
            # "nobody", the same answer as any other unverifiable token.
            self._keys = self._fetch()
            self._fetched_at = now
            self._last_attempt_at = now
        elif now - self._fetched_at > _KEY_TTL_SECONDS:
            # Stale. Retry, but not on every single request while an outage
            # lasts — that would turn a gstatic blip into a self-inflicted
            # 5-second latency spike on every request in the building.
            if now - self._last_attempt_at > _KEY_RETRY_BACKOFF_SECONDS:
                self._last_attempt_at = now
                try:
                    self._keys = self._fetch()
                    self._fetched_at = now
                except Exception:
                    # The keys we already have were themselves fetched from
                    # Google and have verified signatures before; they just
                    # are not provably CURRENT any more. Keep serving them —
                    # up to the grace window, past which a key Google may
                    # since have rotated away is no longer trustworthy enough
                    # to accept a signature against.
                    if now - self._fetched_at > _KEY_TTL_SECONDS + _KEY_STALE_GRACE_SECONDS:
                        raise
        return self._keys.get(kid)

    def principal(self, headers: Mapping[str, str],
                  cookies: Mapping[str, str]) -> Principal | None:
        import jwt

        token = ""
        for name, value in headers.items():
            if name.lower() == IAP_HEADER:
                token = value
                break
        if not token:
            return None
        try:
            kid = jwt.get_unverified_header(token).get("kid", "")
            key = self._key_for(kid)
            if key is None:
                return None
            claims = jwt.decode(
                token, key, algorithms=["ES256"],
                audience=self._audience, issuer=_ISSUER,
                # PyJWT only checks a claim's VALUE when the claim is
                # present — `exp` absent is not the same as `exp` expired,
                # and without `require` it verifies fine. `exp` is the one
                # whose silent absence matters most: it would turn a
                # one-hour token into one good forever. Google always sets
                # all six; requiring them costs nothing against a real
                # assertion and closes the gap against an oddly-minted one.
                options={"require": ["exp", "iat", "aud", "iss", "sub", "email"]})
        except Exception:
            # A token we cannot verify is nobody. Not an error the caller must
            # distinguish: "bad signature" and "no header" are the same answer
            # to "who is this", and telling them apart on the wire would say
            # more than a refusal should.
            return None
        email = str(claims.get("email", ""))
        subject = str(claims.get("sub", ""))
        if not email or not subject:
            return None
        return Principal(email=email, subject=subject)


def iap_identity_from_env() -> IapIdentity:
    return IapIdentity(audience=os.environ.get("FENCEAI_IAP_AUDIENCE", ""))
