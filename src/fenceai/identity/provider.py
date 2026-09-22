"""Which identity this process runs on — decided once, at startup.

`FENCEAI_IDENTITY` has NO DEFAULT, and the refusal names both admissible
values. The precedent is `User.capacity`, which refuses a default because
"there is no safe one: the narrowest silently locks somebody out, the widest
silently lets them in, and both failures are quiet". The same argument holds one
level up, and failing at boot is strictly better than failing per request.
"""

from __future__ import annotations

import os

from fenceai.identity.dev import dev_identity_from_env
from fenceai.identity.ports import IdentityProvider

_CHOICES = ("iap", "dev")


def build_provider() -> IdentityProvider:
    choice = os.environ.get("FENCEAI_IDENTITY", "").strip().lower()
    if choice == "dev":
        return dev_identity_from_env()
    if choice == "iap":
        from fenceai.identity.iap import iap_identity_from_env
        if not os.environ.get("FENCEAI_IAP_AUDIENCE", "").strip():
            raise RuntimeError(
                "FENCEAI_IDENTITY=iap needs FENCEAI_IAP_AUDIENCE: without it "
                "`aud` goes unchecked and an assertion Google minted for "
                "another service is accepted")
        return iap_identity_from_env()
    raise RuntimeError(
        f"FENCEAI_IDENTITY must be one of {_CHOICES}, got {choice!r}. There is "
        "no default: the narrowest silently locks somebody out and the widest "
        "silently lets them in, and both failures are quiet")
