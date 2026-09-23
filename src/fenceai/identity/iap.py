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

import logging
import os
import time
from typing import Any, Callable, Mapping

from fenceai.identity.ports import Principal

#: A total key-fetch outage otherwise reads as "everyone is nobody" — every
#: request fails closed correctly, but nothing an operator can read says WHY.
#: This is the one line that turns that silence into a diagnosable outage.
_log = logging.getLogger(__name__)

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
        #: Why the last refresh attempt failed, kept only so the refusal
        #: raised at the grace boundary can name the cause. The boundary is
        #: now checked on every call, including calls that attempted no fetch
        #: of their own (see `_key_for`), so the exception that explains the
        #: outage is no longer in scope at the point of the refusal — without
        #: this, an operator reading the ERROR line during a gstatic outage
        #: would be told the keys are too old and nothing about why they
        #: could not be replaced.
        self._last_error: Exception | None = None

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
            try:
                self._keys = self._fetch()
            except Exception:
                _log.error("IAP: initial key fetch failed; every caller will "
                           "be refused as unidentified until this recovers")
                raise
            self._fetched_at = now
            self._last_attempt_at = now
        elif now - self._fetched_at > _KEY_TTL_SECONDS:
            # TWO INDEPENDENT DECISIONS live in this branch, and conflating
            # them into one guard was a security hole. They are:
            #
            #   (a) how often a failed refresh is RE-ATTEMPTED — a latency
            #       question, answered by `_KEY_RETRY_BACKOFF_SECONDS`;
            #   (b) whether cached keys past the grace window may still be
            #       SERVED — a correctness question, answered by
            #       `_KEY_STALE_GRACE_SECONDS`.
            #
            # The grace check used to sit INSIDE the backoff branch, so it was
            # only ever evaluated on the one request per 60 seconds that
            # attempted a fetch. Every failed attempt reset
            # `_last_attempt_at`, so for the following 59 seconds this whole
            # branch was skipped and control fell through to
            # `return self._keys.get(kid)` — handing out keys Google may
            # already have retired. That was not a 60-second window that then
            # closed: it repeated for as long as the outage lasted, so a
            # multi-day gstatic outage authenticated callers against expired
            # keys for 59 of every 60 seconds, indefinitely.
            # `docs/reviews/2026-09-23-slice-2-carried-findings.md` (finding 4)
            # deferred this as "up to 60s at a time"; that reading of the
            # control flow was wrong, which is why it is fixed here.
            #
            # So: the backoff governs the FETCH only, and the grace boundary
            # below is evaluated on every call that reaches this branch.
            attempted = now - self._last_attempt_at > _KEY_RETRY_BACKOFF_SECONDS
            if attempted:
                # Stale. Retry, but not on every single request while an
                # outage lasts — that would turn a gstatic blip into a
                # self-inflicted 5-second latency spike on every request in
                # the building.
                self._last_attempt_at = now
                try:
                    self._keys = self._fetch()
                    self._fetched_at = now
                    self._last_error = None
                except Exception as exc:
                    self._last_error = exc
            if now - self._fetched_at > _KEY_TTL_SECONDS + _KEY_STALE_GRACE_SECONDS:
                # The keys we hold were themselves fetched from Google and
                # have verified signatures before; they just are not provably
                # CURRENT any more. Past the grace window a key Google may
                # since have rotated away is no longer trustworthy enough to
                # accept a signature against, so this fails closed — and it
                # does so on EVERY such call, not only on the ones that tried
                # to fetch. `principal()` turns it into "nobody".
                #
                # A fresh exception rather than re-raising `self._last_error`:
                # that object is reused across requests for the whole outage,
                # and `raise exc` appends a frame to its traceback each time,
                # so re-raising it would grow one exception's traceback for
                # every request until the outage ended.
                _log.error("IAP: cached keys are past the stale-key grace "
                           "window (last refresh failure: %s); refusing every "
                           "caller until a refresh succeeds", self._last_error)
                raise RuntimeError(
                    "IAP public keys are past the stale-key grace window"
                ) from self._last_error
            if attempted and self._last_error is not None:
                # `attempted` gates this so the log volume stays what it was
                # before the grace check moved out here: one line per failed
                # REFRESH, not one per request. Without it a six-hour grace
                # window would emit a warning for every request in the
                # building, which is how a real signal gets scrolled past.
                _log.warning("IAP: key refresh failed (%s); serving "
                             "cached keys within the grace window",
                             self._last_error)
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
        except Exception as exc:
            # Unreadable before it is even unverified. A different lever from
            # the one below, so a different line.
            _log.warning("IAP: unreadable assertion header (%s)",
                         type(exc).__name__)
            return None

        try:
            key = self._key_for(kid)
        except Exception:
            # `_key_for` has already logged this, and logged it naming the
            # RIGHT lever (the key endpoint, not the audience). Kept out of the
            # verification `try` below for exactly that reason: a gstatic
            # outage used to produce the correct ERROR followed immediately by
            # a WARNING telling the operator to go and check
            # `FENCEAI_IAP_AUDIENCE`, which is the wrong thing to go and check
            # during an outage.
            return None
        if key is None:
            return None

        try:
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
        except Exception as exc:
            # A token we cannot verify is nobody. Not an error the caller must
            # distinguish: "bad signature" and "no header" are the same answer
            # to "who is this", and telling them apart on the wire would say
            # more than a refusal should.
            #
            # The OPERATOR is a different audience from the caller, and used to
            # get nothing at all: a misconfiguration that refuses every employee
            # — a padded `FENCEAI_IAP_AUDIENCE` does exactly that, against
            # perfectly valid assertions — looked identical to nobody visiting.
            # The wire answer is unchanged; this is the line somebody on call
            # reads.
            #
            # The exception's TYPE NAME only, never `str(exc)`. PyJWT's message
            # for an unsupported `crit` header interpolates that header's value
            # verbatim, and it is read BEFORE the signature is checked — so
            # anyone who can reach this service could write arbitrary
            # multi-line text into this log, formatted to look like our own
            # logger at whatever level they chose. The type name is the
            # diagnosis anyway: `InvalidAudienceError` says more than
            # "Audience doesn't match" does.
            _log.warning("IAP: assertion rejected (%s); if this is every "
                         "caller, check FENCEAI_IAP_AUDIENCE",
                         type(exc).__name__)
            return None
        email = str(claims.get("email", ""))
        subject = str(claims.get("sub", ""))
        if not email or not subject:
            return None
        return Principal(email=email, subject=subject)


def iap_identity_from_env() -> IapIdentity:
    """`.strip()` because `build_provider` validates the STRIPPED value.

    A secret or a YAML block scalar routinely carries a trailing newline, and
    without this the app booted clean, announced `identity provider: iap`, and
    refused every correctly-signed assertion Google sent — because `aud` was
    compared against a string with a newline on the end.

    `import jwt` eagerly, for the reason `provider.py` has no default: the
    container recipe builds with `uv sync --frozen` and the `iap` extra is what
    puts PyJWT in it. Imported lazily inside `principal()`, a missing extra
    boots a healthy-looking server that 500s on every route including
    `/api/session`. A missing dependency is a deployment error, and a
    deployment error belongs at boot.
    """
    import jwt  # noqa: F401  — presence check; `principal()` imports it for use

    return IapIdentity(audience=os.environ.get("FENCEAI_IAP_AUDIENCE", "").strip())
