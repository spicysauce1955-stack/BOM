"""Once the preset leaves the design digest, the STORED preset freezes: an
unchanged fence regenerates to the same id, save_run is INSERT OR IGNORE, and the
document served for ever is the first one. A read that trusts it prices under a
preset the user changed weeks ago."""

from fastapi.testclient import TestClient

from fenceai.api.app import app, state
from tests.api.test_decision_comments import _fence  # the established fixture


def test_changing_the_preset_changes_what_the_bom_is_priced_under():
    """The policy is set through the store, not through a route: there is no
    policy endpoint. Adding one for a test's convenience would be inventing
    product surface to prove a backend property.
    """
    with TestClient(app) as client:
        pid, run_id, _ = _fence(client)
        before = client.get(f"/api/runs/{run_id}/bom").json()

        project = state.store.load_project(pid)
        project.policy = {**project.policy, "objective_preset": "honour_priority"}
        state.store.save_project(project)

        again = client.post(f"/api/projects/{pid}/generate").json()["result"]["run"]["id"]
        # the DESIGN did not move — that is digest-v3 working
        assert again == run_id
        # ...and the STORED run still carries the first generation's preset,
        # which is exactly why nothing may read it for a decision
        assert state.store.load_run(run_id).run.objective_preset == "least_cost"

        after = client.get(f"/api/runs/{run_id}/bom").json()
        # the read is nonetheless priced under the preset in force NOW
        assert after["supply"]["objective_preset"] == "honour_priority"
        assert before["supply"]["objective_preset"] == "least_cost"
        assert after["supply"]["id"] != before["supply"]["id"]


def test_the_bom_names_the_supply_run_that_produced_it():
    with TestClient(app) as client:
        _, run_id, _ = _fence(client)
        body = client.get(f"/api/runs/{run_id}/bom").json()
        s = body["supply"]
        assert s["id"].startswith("sup_")
        assert s["design_id"] == run_id
        assert s["inventory_hash"] == body["inventory_hash"]
        assert s["supply_version"]
        assert s["bom"] == body["bom"]


def test_reading_the_same_bom_twice_is_ONE_supply_run():
    """Idempotent by digest, which is why /bom can write at all: the same design
    against the same yard under the same objective is one fact, however many
    times it is read."""
    with TestClient(app) as client:
        _, run_id, _ = _fence(client)
        first = client.get(f"/api/runs/{run_id}/bom").json()["supply"]["id"]
        second = client.get(f"/api/runs/{run_id}/bom").json()["supply"]["id"]
        assert first == second
        assert len(state.store.list_supply_runs(run_id)) == 1


def test_the_spec_defect_is_gone_one_run_id_two_boms_now_have_two_names():
    """The reproduction from the spec's section 1, turned into a regression test.

    Nothing about the fence changes and GET /api/runs/{id} stays byte-identical
    — that is correct and stays correct. What was missing is that the two BOMs
    had no names, so a reader holding two printouts could not tell which
    inventory each was priced against. Now they can.
    """
    with TestClient(app) as client:
        pid, run_id, _ = _fence(client)
        before_run = client.get(f"/api/runs/{run_id}").json()
        before = client.get(f"/api/runs/{run_id}/bom").json()

        inv = client.get(f"/api/projects/{pid}/inventory").json()
        inv["items"] = [{"id": "i1", "sku": "POST-S", "kind": "full_stock", "qty": 3}]
        client.put(f"/api/projects/{pid}/inventory", json=inv)

        after = client.get(f"/api/runs/{run_id}/bom").json()
        # the DESIGN is unchanged, and still says so
        assert client.get(f"/api/runs/{run_id}").json() == before_run
        # the two supply runs are different, and each names its own yard
        assert after["supply"]["id"] != before["supply"]["id"]
        assert after["supply"]["inventory_hash"] != before["supply"]["inventory_hash"]
        assert after["supply"]["design_id"] == before["supply"]["design_id"] == run_id


def test_a_supply_run_is_retrievable_after_the_yard_moves_on():
    """The point of storing it: the row outlives the inventory state that
    produced it, which is what makes a printout checkable later."""
    with TestClient(app) as client:
        pid, run_id, _ = _fence(client)
        sup_id = client.get(f"/api/runs/{run_id}/bom").json()["supply"]["id"]
        inv = client.get(f"/api/projects/{pid}/inventory").json()
        inv["items"] = [{"id": "i1", "sku": "POST-S", "kind": "full_stock", "qty": 3}]
        client.put(f"/api/projects/{pid}/inventory", json=inv)
        stored = state.store.load_supply_run(sup_id)
        assert stored is not None and stored.design_id == run_id


def test_a_quote_names_a_supply_run_that_actually_exists():
    with TestClient(app) as client:
        _, run_id, _ = _fence(client)
        quote = client.post(f"/api/runs/{run_id}/quote", json={"label": "q1"}).json()
        assert quote["supply_id"].startswith("sup_")
        stored = state.store.load_supply_run(quote["supply_id"])
        assert stored is not None
        assert stored.design_id == run_id
        assert stored.bom.model_dump() == quote["bom"]


def test_the_quote_and_the_bom_read_agree_on_the_supply_run():
    """Same design, same yard, same objective — one supply id, whichever route
    computed it. Two ids here would mean the two paths disagree about what they
    priced, which is the whole class of defect this change removes."""
    with TestClient(app) as client:
        _, run_id, _ = _fence(client)
        from_bom = client.get(f"/api/runs/{run_id}/bom").json()["supply"]["id"]
        quote = client.post(f"/api/runs/{run_id}/quote", json={"label": "q"}).json()
        assert quote["supply_id"] == from_bom
