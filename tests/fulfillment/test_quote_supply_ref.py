"""A Quote was always a SupplyRun somebody decided to stand behind. It froze the
numbers without being able to name what produced them; now it can."""

from fenceai.fulfillment.fulfill import Bom
from fenceai.fulfillment.quote import Quote


def test_a_quote_carries_the_supply_run_it_froze():
    q = Quote(id="quote_1", project_id="p", run_id="run_abc",
              supply_id="sup_aaa", bom=Bom())
    assert q.supply_id == "sup_aaa"


def test_a_quote_frozen_before_supply_runs_had_names_still_reads():
    """Quotes are stored as whole JSON documents and re-read with
    model_validate_json, so a required field would make every earlier quote
    unreadable rather than merely out of date."""
    q = Quote.model_validate({"id": "quote_old", "project_id": "p",
                              "run_id": "run_abc", "bom": {}})
    assert q.supply_id == ""
