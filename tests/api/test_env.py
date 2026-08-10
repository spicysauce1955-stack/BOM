"""Tiny .env loader tests (core/env.py)."""

from __future__ import annotations

import os

from fenceai.core.env import load_dotenv


def test_loads_values_and_respects_existing_env(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comment\n"
        "FENCEAI_TEST_A=hello\n"
        'FENCEAI_TEST_B="quoted value"\n'
        "FENCEAI_TEST_C=overridden-by-real-env\n"
        "\n"
        "not a kv line\n"
    )
    monkeypatch.delenv("FENCEAI_TEST_A", raising=False)
    monkeypatch.delenv("FENCEAI_TEST_B", raising=False)
    monkeypatch.setenv("FENCEAI_TEST_C", "real-env-wins")

    applied = load_dotenv(env_file)

    assert os.environ["FENCEAI_TEST_A"] == "hello"
    assert os.environ["FENCEAI_TEST_B"] == "quoted value"
    assert os.environ["FENCEAI_TEST_C"] == "real-env-wins"  # file never overrides
    assert set(applied) == {"FENCEAI_TEST_A", "FENCEAI_TEST_B"}
    for k in ("FENCEAI_TEST_A", "FENCEAI_TEST_B"):
        monkeypatch.delenv(k)


def test_missing_file_is_a_noop(tmp_path):
    assert load_dotenv(tmp_path / "nope.env") == {}
