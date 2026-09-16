"""The salesperson's home screen, the office's question back, and the drawn gate
swings — the pure halves, in node, pinned against the Python they mirror.

    js/my-jobs.js      stepToOpen, finishOffer, SALES_WORD, SALES_STATUSES
    js/desk-actions.js canSendBack, RETURNABLE
    js/notes.js        isFromOffice
    js/gate-geom.js    swingOptions, isCurrentSwing
    js/site.js         hasOptionalValue
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from fenceai.commands.desk import (
    CANCEL_JOB, COMMIT_PLAN, DESK, REOPEN_JOB, RETURN_TO_SALES, REVISE_PLAN,
    SUBMIT_JOB,
)
from fenceai.project.lifecycle import SALES_STATUS

STATIC = Path(__file__).resolve().parents[2] / "src" / "fenceai" / "web" / "static"

SCRIPT = """
import { SALES_STATUSES, SALES_WORD, finishOffer, stepToOpen } from "./js/my-jobs.js";
import {
  CANCELLABLE, COMMITTABLE, HOSTS, REVISABLE, RETURNABLE, canSendBack, deskActs,
  hostIdFor, isDeskUser,
} from "./js/desk-actions.js";
import { reopenable } from "./js/queue.js";
import { isFromOffice } from "./js/notes.js";
import { isCurrentSwing, slideOptionArrow, swingOptions, swingOptionsShownFor } from "./js/gate-geom.js";
import { SALES_EDITABLE, drawingLockedFor, runCommand } from "./js/state.js";
import { foldOpenFor, hasOptionalValue } from "./js/site.js";

const out = {};
out.sales_word = SALES_WORD;
out.sales_statuses = SALES_STATUSES;
out.open_office = stepToOpen({ office_notes: 2, sales_status: "accepted" });
out.open_needs_info = stepToOpen({ office_notes: 0, sales_status: "needs_info" });
out.open_plain = stepToOpen({ office_notes: 0, sales_status: "draft" });
out.open_none = stepToOpen(null);
out.offer = Object.fromEntries(Object.keys(SALES_WORD).map((s) => [s, finishOffer(s)]));
out.returnable = RETURNABLE;
out.committable = COMMITTABLE;
out.cancellable = CANCELLABLE;
out.revisable = REVISABLE;
out.hosts = HOSTS;
out.host_for = { plan: hostIdFor("plan"), generate: hostIdFor("generate"),
                 sale: hostIdFor("sale"), unknown: hostIdFor("nowhere") };
out.desk_user = {
  office: isDeskUser("backoffice", "backoffice"), admin: isDeskUser("all", "admin"),
  sales_view: isDeskUser("sales", "admin"), sales_account: isDeskUser("backoffice", "sales"),
};
out.acts = {
  sale: deskActs("sale", "planning", false),
  blanks: deskActs("blanks", "planning", true),
  questions: deskActs("questions", "planning", true),
  generate_with_run: deskActs("generate", "planning", true),
  generate_no_run: deskActs("generate", "planning", false),
  plan_committable: deskActs("plan", "planning", true),
  plan_already: deskActs("plan", "planned", true),
  plan_quoted: deskActs("plan", "quoted", false),
  sale_of_a_cancelled_job: deskActs("sale", "cancelled", true),
  sale_of_a_returned_job: deskActs("sale", "returned", true),
  plan_no_run: deskActs("plan", "planning", false),
  sale_of_a_finished_job: deskActs("sale", "delivered", true),
  materials: deskActs("materials", "planning", true),
};
out.reopen = { cancelled: reopenable("cancelled"), delivered: reopenable("delivered"),
               planning: reopenable("planning") };
out.send_back = {
  office_planning: canSendBack("backoffice", "backoffice", "planning"),
  admin_all_waiting: canSendBack("all", "admin", "waiting"),
  sales_view: canSendBack("sales", "admin", "planning"),
  sales_account: canSendBack("backoffice", "sales", "planning"),
  quoted: canSendBack("backoffice", "backoffice", "quoted"),
  signed_out: canSendBack("backoffice", undefined, "planning"),
};
out.office = {
  other_account: isFromOffice({ author: "user:u_yossi" }, "u_dana"),
  her_own: isFromOffice({ author: "user:u_dana" }, "u_dana"),
  system: isFromOffice({ author: "system" }, "u_dana"),
  no_creator: isFromOffice({ author: "user:u_yossi" }, ""),
};
out.options = { single: swingOptions("single"), double: swingOptions("double"),
                sliding: swingOptions("sliding"), missing: swingOptions(undefined) };
out.current = {
  stated: isCurrentSwing({ opens_to: "left", hinge: "end" }, { opens_to: "left", hinge: "end", slides_to: null }),
  other_post: isCurrentSwing({ opens_to: "left", hinge: "end" }, { opens_to: "left", hinge: "start", slides_to: null }),
  unstated: isCurrentSwing({}, { opens_to: "left", hinge: "start", slides_to: null }),
};
out.optional = {
  blank: hasOptionalValue({ hvhz: null, frost_depth_mm: null, jurisdiction: "", code_edition: "" }),
  hvhz_false: hasOptionalValue({ hvhz: false, frost_depth_mm: null, jurisdiction: "", code_edition: "" }),
  frost_zero: hasOptionalValue({ hvhz: null, frost_depth_mm: 0, jurisdiction: "", code_edition: "" }),
  spaces: hasOptionalValue({ hvhz: null, frost_depth_mm: null, jurisdiction: "  ", code_edition: "" }),
  code: hasOptionalValue({ hvhz: null, frost_depth_mm: null, jurisdiction: "", code_edition: "IRC 2021" }),
};
const blank = { hvhz: null, frost_depth_mm: null, jurisdiction: "", code_edition: "" };
out.fold = {
  opened_here: foldOpenFor({ projectId: "p1", open: true }, "p1", blank),
  opened_elsewhere: foldOpenFor({ projectId: "p1", open: true }, "p2", blank),
  closed_here_with_value: foldOpenFor({ projectId: "p1", open: false }, "p1", { ...blank, frost_depth_mm: 900 }),
  never_touched: foldOpenFor({ projectId: null, open: false }, "p2", blank),
};
out.sales_editable = SALES_EDITABLE;
out.locked = Object.fromEntries(Object.keys(SALES_WORD).map((s) => [s, drawingLockedFor("sales", s)]));
out.locked_other_views = [drawingLockedFor("backoffice", "planning"), drawingLockedFor("all", "waiting"),
                          drawingLockedFor("sales", undefined)];
out.capacities_ok = ["backoffice", "admin", "sales"].filter((c) => canSendBack("backoffice", c, "planning"));
out.shown = {
  gates_select: swingOptionsShownFor("gates", "select"),
  blanks_select: swingOptionsShownFor("blanks", "select"),
  gate_tool_no_road: swingOptionsShownFor(null, "gate"),
  review_select: swingOptionsShownFor("review", "select"),
  layout_draw: swingOptionsShownFor("layout", "draw"),
  sale_select: swingOptionsShownFor("sale", "select"),
};
// a gate standing beside the fence: its polyline IS the opening
out.span_slide_start = slideOptionArrow([[0, 0], [1000, 0]], 0, 1000, "start");
out.span_slide_end = slideOptionArrow([[0, 0], [1000, 0]], 0, 1000, "end");
// an in-run gate with fence beyond: the along-the-run arrow is kept
out.run_slide_end = slideOptionArrow([[0, 0], [6000, 0]], 1000, 1000, "end");

// runCommand's three refusal shapes, with fetch stubbed
const replies = [
  () => { throw new TypeError("offline"); },
  async () => ({ ok: false, status: 409, json: async () => ({ detail: { code: "command_wrong_state", params: { status: "planning" } } }) }),
  async () => ({ ok: false, status: 404, json: async () => ({ detail: "Not Found" }) }),
  async () => ({ ok: false, status: 422, json: async () => ({ detail: [{ msg: "bad" }] }) }),
  async () => ({ ok: false, status: 500, json: async () => { throw new SyntaxError("html"); } }),
  async () => ({ ok: true, status: 200, json: async () => ({ id: "p1", status: "waiting" }) }),
];
out.command = [];
for (const reply of replies) {
  globalThis.fetch = reply;
  out.command.push(await runCommand("p1", "submit_job"));
}
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def out() -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    proc = subprocess.run([node, "--input-type=module", "-e", SCRIPT],
                          cwd=STATIC, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_the_browser_folds_job_states_exactly_as_the_server_does(out):
    """Two copies of one mapping: the list reads the server's word, the review
    panel folds the status it already has. They must never say different
    things about the same job."""
    assert out["sales_word"] == SALES_STATUS
    assert set(out["sales_statuses"]) == set(SALES_STATUS.values())


def test_a_job_the_office_wrote_on_opens_where_the_notes_are_read(out):
    """"Open them and see exactly where and what" — the review step is the map
    with the notes pinned on it and read back beside it."""
    assert out["open_office"] == "review"
    assert out["open_needs_info"] == "review"
    assert out["open_plain"] == "job"
    assert out["open_none"] == "job"


def test_only_a_job_still_in_her_hands_offers_send(out):
    """Mirrors `submit_job`'s from-states: offering it anywhere else is a
    button the server refuses."""
    sendable = {s for s, o in out["offer"].items() if o["send"]}
    assert sendable == set(SUBMIT_JOB.from_states)
    assert out["offer"]["returned"]["sendKey"] == "myjobs.send_answers"
    assert out["offer"]["drafting"]["sendKey"] == "myjobs.send"


def test_the_office_can_send_back_exactly_where_the_command_allows(out):
    assert set(out["returnable"]) == set(RETURN_TO_SALES.from_states)
    sb = out["send_back"]
    assert sb["office_planning"] and sb["admin_all_waiting"]
    assert not (sb["sales_view"] or sb["sales_account"] or sb["quoted"] or sb["signed_out"])


def test_an_office_note_is_one_written_by_another_account(out):
    o = out["office"]
    assert o["other_account"] is True
    assert o["her_own"] is False and o["system"] is False and o["no_creator"] is False


def test_every_possible_swing_is_offered_once(out):
    """Four for a single leaf (two sides × two posts), two for a double, two for
    a sliding gate — and a gate whose leaf was never stated is a single."""
    single = out["options"]["single"]
    assert len(single) == 4
    assert {(o["opens_to"], o["hinge"]) for o in single} == {
        ("left", "start"), ("left", "end"), ("right", "start"), ("right", "end")}
    assert all(o["slides_to"] is None for o in single)
    assert [(o["opens_to"], o["hinge"]) for o in out["options"]["double"]] == [
        ("left", None), ("right", None)]
    assert [o["slides_to"] for o in out["options"]["sliding"]] == ["start", "end"]
    assert out["options"]["missing"] == single


def test_the_stated_swing_is_recognised_and_nothing_else(out):
    c = out["current"]
    assert c["stated"] is True
    assert c["other_post"] is False
    assert c["unstated"] is False


def test_the_optional_site_group_opens_only_when_something_is_stated(out):
    """Blank by default — and a stated `false` or a zero depth IS stated, so it
    is never hidden behind a closed fold."""
    o = out["optional"]
    assert o["blank"] is False and o["spaces"] is False
    assert o["hvhz_false"] is True and o["frost_zero"] is True and o["code"] is True


def test_a_sent_job_is_view_only_for_her_and_editable_where_she_can_send(out):
    """The drawing is hers exactly where `submit_job` accepts the job; anywhere
    else a drag would bump the topology under a run the office generated."""
    assert set(out["sales_editable"]) == set(SUBMIT_JOB.from_states)
    assert {s for s, locked in out["locked"].items() if not locked} == set(SUBMIT_JOB.from_states)
    assert out["locked_other_views"] == [False, False, False]


def test_the_send_back_capacities_are_the_commands_own(out):
    assert set(out["capacities_ok"]) == set(DESK) & set(RETURN_TO_SALES.capacities)


def test_swing_options_show_where_gates_are_the_work_and_nowhere_else(out):
    s = out["shown"]
    assert s["gates_select"] and s["blanks_select"] and s["gate_tool_no_road"]
    assert not (s["review_select"] or s["layout_draw"] or s["sale_select"])


def test_a_sliding_option_beside_the_fence_still_points_somewhere(out):
    """The review's finding: on a `GateSpan` the two options collapsed onto the
    posts with no arrow. Each now carries on past its own edge."""
    start, end = out["span_slide_start"], out["span_slide_end"]
    assert start["from"] == [0, 0] and start["to"][0] < 0 and start["to"][1] == 0
    assert end["from"] == [1000, 0] and end["to"][0] > 1000 and end["to"][1] == 0
    assert out["run_slide_end"]["to"][0] > out["run_slide_end"]["from"][0]


def test_a_refusal_is_a_code_to_render_never_a_thrown_alert(out):
    unreachable, wrong_state, not_found, invalid, not_json, ok = out["command"]
    assert unreachable == {"ok": False, "code": "server_unreachable", "params": {}}
    assert wrong_state == {"ok": False, "code": "command_wrong_state", "params": {"status": "planning"}}
    assert not_found["code"] == "command_failed"
    assert invalid["code"] == "command_payload_invalid"
    assert not_json["code"] == "command_failed"
    assert ok == {"ok": True, "project": {"id": "p1", "status": "waiting"}}


def test_the_optional_fold_is_remembered_per_job_not_per_page(out):
    """Found by the browser smoke: opened on one job, the fold stayed open on
    the next job, which had nothing in it."""
    f = out["fold"]
    assert f["opened_here"] is True
    assert f["opened_elsewhere"] is False
    assert f["closed_here_with_value"] is True
    assert f["never_touched"] is False


def test_each_office_step_offers_its_own_act(out):
    """One panel, keyed on the step. The acts are the commands the office road's
    steps turn on, and a step with nothing of its own offers nothing rather than
    a button the server would refuse."""
    a = out["acts"]
    assert a["sale"] == ["acknowledge_sale", "return_to_sales", "cancel_job"]
    assert a["blanks"] == ["return_to_sales", "cancel_job"]
    assert a["generate_with_run"] == ["acknowledge_warnings", "cancel_job"]
    assert a["plan_committable"] == ["commit_plan", "cancel_job"]
    # nothing to act on, or nothing this step does
    assert a["questions"] == [] and a["materials"] == []
    assert a["generate_no_run"] == [] and a["plan_no_run"] == []
    # a job already planned is not committed again from here — it is taken BACK
    # to planning, which is the only way out of `planned` that does not show the
    # salesperson a rejection
    assert a["plan_already"] == ["revise_plan", "cancel_job"]
    assert a["plan_quoted"] == ["revise_plan", "cancel_job"]
    # ...and a finished job is not read, sent back or rejected: there is no work
    # left on it for an acknowledgement to be part of
    assert a["sale_of_a_finished_job"] == []
    assert a["sale_of_a_cancelled_job"] == []
    # a job handed back to her is still open — read and rejectable — but not
    # sent back again: it is already with her (`RETURNABLE`)
    assert a["sale_of_a_returned_job"] == ["acknowledge_sale", "cancel_job"]


def test_the_browser_offers_commit_exactly_where_the_command_accepts_it(out):
    assert set(out["committable"]) == set(COMMIT_PLAN.from_states)
    assert set(out["reopen"]) == {"cancelled", "delivered", "planning"}
    assert out["reopen"]["cancelled"] is True
    assert {s for s, ok in out["reopen"].items() if ok} == set(REOPEN_JOB.from_states)
    assert set(out["cancellable"]) == set(CANCEL_JOB.from_states)
    assert set(out["revisable"]) == set(REVISE_PLAN.from_states)


def test_only_an_office_account_on_an_office_view_sees_the_desk(out):
    d = out["desk_user"]
    assert d["office"] and d["admin"]
    assert not (d["sales_view"] or d["sales_account"])


def test_the_plan_step_draws_its_act_on_the_sheet_it_is_read_on(out):
    """Two hosts, one module: step 6 is read on the structure sheet and every
    other step on the canvas, where a panel in the canvas column is simply not on
    screen — which is how the commit button failed to appear at all."""
    assert out["host_for"] == {"plan": "desk-actions-plan", "generate": "desk-actions",
                               "sale": "desk-actions", "unknown": "desk-actions"}
    assert set(out["hosts"]) == set(out["host_for"].values())
