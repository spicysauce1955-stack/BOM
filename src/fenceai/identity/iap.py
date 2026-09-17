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
        self._fetched_at = 0.0

    def _fetch_google_keys(self) -> dict[str, Any]:
        import json
        import urllib.request
        with urllib.request.urlopen(_KEY_URL, timeout=5) as r:
            return json.loads(r.read())

    def _key_for(self, kid: str) -> Any:
        now = time.time()
        if self._keys is None or now - self._fetched_at > _KEY_TTL_SECONDS:
            self._keys = self._fetch()
            self._fetched_at = now
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
                audience=self._audience, issuer=_ISSUER)
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
