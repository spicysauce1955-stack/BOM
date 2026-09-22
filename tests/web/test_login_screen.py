"""The front door: signed out, the page is the login screen and nothing else.

These are static checks on the markup, the stylesheet and the bootstrap,
because the failure they guard against is a flash or a leak that a browser run
only sees if it happens to look at the right millisecond: a login form
flashing on a signed-in reload, or a job loaded behind the login screen.
"""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"


def _css() -> str:
    return re.sub(r"/\*.*?\*/", "", (STATIC / "style.css").read_text(), flags=re.S)


def test_the_page_starts_undecided():
    """`pending` until `/api/me` answers — neither the app nor the form shows,
    so neither can flash."""
    html = (STATIC / "index.html").read_text()
    assert re.search(r'<html[^>]*\bdata-auth="pending"', html)


def test_only_a_signed_in_page_shows_the_app_and_only_a_signed_out_one_the_form():
    """Keyed on NOT in / NOT out, so `pending` hides both. A rule written as
    `[data-auth="in"] #login-screen` instead would flash the form on every
    signed-in reload and pass every other test."""
    css = _css()
    assert re.search(
        r'html:not\(\[data-auth="in"\]\)\s+body\s*>\s*:not\(#login-screen\)\s*\{\s*display:\s*none', css)
    assert re.search(
        r'html:not\(\[data-auth="out"\]\)\s+#login-screen\s*\{\s*display:\s*none', css)


def test_the_login_screen_holds_the_form_and_the_header_does_not():
    html = (STATIC / "index.html").read_text()
    screen = html[html.index('<section id="login-screen"'):html.index("</section>")]
    for el in ('id="sign-in"', 'id="sign-in-email"',
               'id="sign-in-error"', 'id="sign-in-unreachable"'):
        assert el in screen, el
    header = html[html.index("<header>"):html.index("</header>")]
    assert 'id="sign-in"' not in header


def test_the_job_picker_and_name_box_are_gone():
    """"We don't need project selection in mid project." """
    html = (STATIC / "index.html").read_text()
    app = (STATIC / "app.js").read_text()
    for gone in ("project-select", "new-project-name"):
        assert gone not in html and gone not in app, gone


def test_no_project_is_loaded_before_somebody_signs_in():
    """The bootstrap loads projects only from `openWorkspace`, and
    `openWorkspace` runs only on `signed-in`."""
    app = re.sub(r"//[^\n]*", "", (STATIC / "app.js").read_text())
    main = app[app.index("async function main()"):]
    assert "loadProjects" not in main and "openProject" not in main
    assert "createProject" not in main
    assert re.search(r'on\("signed-in",[^\n]*openWorkspace', app)
    workspace = app[app.index("async function openWorkspace()"):app.index("function setupUndoButtons")]
    assert "loadProjects" in workspace


def test_the_frontend_is_served_revalidated_so_an_update_cannot_mix_modules():
    """No build step means the same file names every version. Cached
    heuristically, a browser paired a new `app.js` with an old `session.js`,
    the import failed, and the page stayed blank on `data-auth="pending"`."""
    from fastapi.testclient import TestClient

    from fenceai.api.app import app

    with TestClient(app) as client:
        for path in ("/", "/app.js", "/js/session.js", "/style.css"):
            r = client.get(path)
            assert r.status_code == 200, path
            assert r.headers.get("cache-control") == "no-cache", path


def test_the_front_door_asks_for_no_password():
    """There is none. A field for one would be asking for a secret the system
    cannot check and must never store."""
    html = (STATIC / "index.html").read_text()
    assert 'type="password"' not in html
    assert "sign-in-password" not in html


def test_a_refused_arrival_gets_a_screen_of_their_own():
    """Not a blank app and not the picker again. IAP let them to the door;
    this is the screen that tells them what to ask for."""
    html = (STATIC / "index.html").read_text()
    assert 'id="no-access"' in html
    assert 'data-i18n="noaccess.body"' in html
    css = _css()
    assert re.search(
        r'html:not\(\[data-auth="denied"\]\)\s+#no-access\s*\{\s*display:\s*none', css)
    assert re.search(
        r'html\[data-auth="denied"\]\s+body\s*>\s*:not\(#no-access\)\s*\{\s*display:\s*none', css)


def test_the_no_access_screen_actually_renders_and_is_not_just_declared():
    """The two rules above are not enough by themselves, and this is not
    hypothetical — verified in a headless browser. The PRE-EXISTING rule
    `html:not([data-auth="in"]) body > :not(#login-screen))` (unchanged by
    this feature) has HIGHER specificity than the "hide #no-access by
    default" rule above (an extra `body >` element), and it still matches
    `#no-access` whenever `data-auth` is not `"in"` — including `"denied"`.
    Without a third rule of the SAME specificity declared AFTER it, the
    cascade's tiebreak (last declared wins a tie) never runs in `#no-access`'s
    favour, and the whole feature renders as a blank page for every denied
    user, silently, with the two assertions above still green.

    So this checks two things, not one: that the revealing rule exists, and
    that it is declared AFTER the rule it has to out-order — a text-only pin
    would still pass if somebody moved it above that rule (or above whichever
    rule around it, in the future, is fighting for the same element), and the
    regression this guards against does not throw; it just goes quiet.
    """
    css = _css()
    competitor = re.search(
        r'html:not\(\[data-auth="in"\]\)\s+body\s*>\s*:not\(#login-screen\)', css)
    assert competitor, "the rule the reveal has to out-order is gone too"
    reveal = re.search(
        r'html\[data-auth="denied"\]\s+body\s*>\s*#no-access\s*\{\s*display:\s*(?:grid|block|flex)',
        css)
    assert reveal, 'no rule sets #no-access visible under data-auth="denied"'
    assert reveal.start() > competitor.start(), (
        "the reveal rule must be declared AFTER the competing rule above — "
        "equal specificity is a tie broken by source order, so moved earlier "
        "it loses and #no-access goes back to display:none while denied")


def test_the_no_access_screen_says_which_refusal_this_is():
    """Three different refusals used to render one sentence.

    `noaccess.body` — "ask an administrator to give this address access" — is
    the cure for `no_capacity` alone. A deactivated account and an address
    bound to a different Google account both read it too, and both sent the
    person to an admin who finds a row already there. The reason line carries
    NO `data-i18n`, deliberately: the applier would overwrite it with one fixed
    key on every locale change, which is how it would silently become one
    sentence again."""
    html = (STATIC / "index.html").read_text()
    app = (STATIC / "app.js").read_text()

    reason = re.search(r'<p id="no-access-reason"([^>]*)>', html)
    assert reason, "the no-access screen has no reason line"
    assert "data-i18n" not in reason.group(1)
    assert re.search(r'<p id="no-access-advice"[^>]*data-i18n="noaccess\.body"', html)

    # The reason is the refusal code, rendered through the locale bundle.
    assert re.search(r'no-access-reason"\)\.textContent\s*=\s*\n?\s*t\(`error\.\$\{state\.authCode', app)
    # The generic advice is shown for the one refusal it actually answers.
    assert re.search(r'no-access-advice"\)\.hidden\s*=\s*\n?\s*state\.authCode\s*!==\s*"no_capacity"', app)


def test_an_unrecognised_refusal_is_still_a_refusal():
    """Written as the complement of "in" and "out" rather than as a list of the
    three codes that exist today. A fourth `resolve` status matched by neither
    branch would fall through to `out` and show the sign-in picker to somebody
    Google has already signed in — "try again" for something trying again
    cannot fix."""
    app = (STATIC / "app.js").read_text()
    assert re.search(
        r'const refused\s*=\s*!!state\.authStatus\s*&&\s*\n?\s*state\.authStatus\s*!==\s*"ok"\s*&&\s*'
        r'\n?\s*state\.authStatus\s*!==\s*"no_identity"', app), (
        "the refusal test enumerates codes again instead of complementing ok/no_identity")
