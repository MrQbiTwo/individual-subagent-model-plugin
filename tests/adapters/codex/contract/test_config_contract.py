"""Codex ``config.toml`` round-trip and misplaced-key contract."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.contract, pytest.mark.codex_cli]


def test_roundtrip_preserves_top_level_model(codex_probe, codex_fixture) -> None:
    parsed = codex_probe("toml-roundtrip", codex_fixture("config.toml"))

    assert isinstance(parsed, dict)
    # The active model and provider are top-level scalars; a rewrite must not
    # nest them into a provider table.
    assert parsed["model"] == "gpt-5.6-sol"
    assert parsed["model_provider"] == "myrouter"
    assert parsed["model_reasoning_effort"] == "high"
    assert parsed["model_catalog_json"] == "models.json"

    provider = parsed["model_providers"]["myrouter"]
    assert provider["name"] == "My Router"
    assert provider["base_url"] == "https://router.example.invalid/v1"
    assert provider["wire_api"] == "responses"
    assert provider["env_key"] == "MYROUTER_API_KEY"
    assert "model" not in provider, "model must stay a top-level scalar"

    agents = parsed["agents"]
    assert agents["default_subagent_model"] == "myrouter/child"
    assert agents["default_subagent_reasoning_effort"] == "low"


def test_misplaced_model_key_is_detected(codex_probe, codex_fixture) -> None:
    assert codex_probe("misplaced-model", codex_fixture("misplaced_model.toml")) == (
        "[model_providers.myrouter]"
    )


def test_correct_config_has_no_misplaced_model(codex_probe, codex_fixture) -> None:
    assert codex_probe("misplaced-model", codex_fixture("config.toml")) is None
