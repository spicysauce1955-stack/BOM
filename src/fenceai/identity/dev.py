"""Who you are on a laptop.

**This is an impersonation switch and is named as one.** No secret, no session
row, no expiry, nothing that could be mistaken for authentication — it exists
so the app keeps working with no Google, which is the same offline property
`ai/stub.py` protects. Like the stub, it must stay capped: if it ever grows a
credential it has become a second, worse implementation of the thing it stands
in for.

`provider.py` registers it only when `FENCEAI_IDENTITY=dev`, and `api/app.py`
registers `POST /api/dev/identity` on the same condition, so under `iap` the
route does not exist to be found.
"""

from __future__ import annotations

import os
from typing import Mapping

from fenceai.identity.ports import Principal

#: Named for what it is. Not `session`, which would suggest it were one.
DEV_COOKIE = "fenceai_dev_user"


class DevIdentity:
    """Cookie first, environment second.

    The env var is what a bare `uvicorn` opens as, so a developer who has set
    nothing still lands somewhere. The cookie is how ONE browser becomes
    somebody else without restarting the server — which the browser smoke needs,
    because it switches persona mid-run.
    """

    provider_id = "dev"

    def __init__(self, default_email: str = "") -> None:
        self._default = default_email

    def principal(self, headers: Mapping[str, str],
                  cookies: Mapping[str, str]) -> Principal | None:
        email = (cookies.get(DEV_COOKIE) or self._default or "").strip()
        if not email:
            return None
        # No subject. There is no Google here, and inventing one would BIND a
        # fabricated `sub` to a row — after which the real person's first
        # arrival is refused with `subject_mismatch` by a database nobody can
        # explain.
        return Principal(email=email, subject="")


def dev_identity_from_env() -> DevIdentity:
    return DevIdentity(default_email=os.environ.get("FENCEAI_DEV_USER", ""))
