"""A project is a JOB somebody sold — slice 1 of the salesperson MVP.

`Project` was `id, name`, so every screen after the first read as *"project 7"*.
A salesperson does not sell a project; they sell a fence to a person at an
address on a day, and the office person receiving the layout needs to know all
three before anything else on the page means much.

**Why a typed `Job` rather than four loose fields**, following `SiteConditions`
and `fence_model`: it is stamped on the run and shown on the handover, so a typo
has to fail at the boundary rather than at rendering. And it keeps the answer to
*"is this job identified?"* in one place instead of four `if` statements spread
across the surfaces that ask.

`name` stays. It is what 59 routes, the project picker and the whole existing
suite key on; a job that also has a customer simply DISPLAYS as the customer.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fenceai.project.model import Job, Project


def test_a_project_with_nobody_named_is_still_a_valid_project():
    """Every project that exists today has no job on it, and none of them may
    break. `None` means *nobody has said yet* — the same claim `SiteConditions`
    makes about an unset dimension, and a different claim from an empty string."""
    p = Project(id="p1", name="untitled")
    assert p.job is None


def test_a_job_carries_who_bought_it_where_who_sold_it_and_when():
    job = Job(customer="דנה לוי", address="הרצל 12, תל אביב",
              sold_by="bob", sold_on="2026-09-04")
    p = Project(id="p1", name="untitled", job=job)
    assert p.job.customer == "דנה לוי"
    assert p.job.address == "הרצל 12, תל אביב"
    assert p.job.sold_by == "bob"
    assert p.job.sold_on == "2026-09-04"


def test_a_job_may_be_started_with_only_a_customer():
    """The salesperson enters this after the visit, from paper. Refusing a job
    because the address has not been typed yet would make the first field they
    fill in the one that blocks them — and completeness is reported by the
    handover sheet (slice 4), not enforced by the constructor."""
    assert Job(customer="Dana Levy").address == ""


def test_a_date_that_is_not_a_date_fails_at_the_boundary():
    """The reason this is typed at all. `sold_on` reaches the handover sheet and
    any later "when was this sold" question; a free-form string would let
    "yesterday" through and fail somewhere far away from the person who typed
    it."""
    with pytest.raises(ValidationError):
        Job(customer="Dana", sold_on="yesterday")
    with pytest.raises(ValidationError):
        Job(customer="Dana", sold_on="04/09/2026")


def test_an_empty_date_is_allowed_and_means_nobody_said():
    assert Job(customer="Dana").sold_on == ""
    assert Job(customer="Dana", sold_on="").sold_on == ""


def test_whitespace_is_stripped_so_a_padded_name_is_not_a_second_customer():
    """Two jobs for `"Dana Levy"` and `"Dana Levy "` are one customer. Stripping
    at the boundary rather than at every comparison keeps that true everywhere,
    including in the picker's sort."""
    job = Job(customer="  Dana Levy  ", address="  Herzl 12  ")
    assert job.customer == "Dana Levy"
    assert job.address == "Herzl 12"


def test_a_job_with_nothing_in_it_is_not_a_job():
    """A `Job` whose every field is blank carries no more than `None` did, and
    would make `job is not None` a lie that the handover sheet then reports as
    an identified job."""
    with pytest.raises(ValidationError):
        Job()
    with pytest.raises(ValidationError):
        Job(customer="   ")


def test_the_label_is_what_a_person_would_call_this_job():
    """What the picker shows instead of "project 7". Customer first, because
    that is how a salesperson refers to a job out loud; the address
    disambiguates two fences for the same person."""
    assert Job(customer="Dana Levy", address="Herzl 12").label() == "Dana Levy — Herzl 12"
    assert Job(customer="Dana Levy").label() == "Dana Levy"
    assert Job(address="Herzl 12").label() == "Herzl 12"


def test_the_project_falls_back_to_its_name_when_no_job_is_set():
    """So the picker has exactly one thing to call, and no surface needs to know
    whether a job exists."""
    assert Project(id="p1", name="untitled").display_name() == "untitled"
    assert Project(id="p1", name="untitled",
                   job=Job(customer="Dana Levy")).display_name() == "Dana Levy"


def test_a_job_round_trips_through_serialisation():
    """It crosses the API and the store; a field that does not survive the round
    trip is a field the office person never receives."""
    p = Project(id="p1", name="untitled",
                job=Job(customer="Dana", address="Herzl 12",
                        sold_by="bob", sold_on="2026-09-04"))
    assert Project.model_validate(p.model_dump()) == p
