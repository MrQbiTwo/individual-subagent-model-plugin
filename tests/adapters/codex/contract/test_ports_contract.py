"""Codex port instances and fail-closed catalog facts."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.contract, pytest.mark.codex_cli]


def test_port_instances_and_empty_free_provider_list(codex_probe) -> None:
    assert codex_probe("ports") == {
        "catalogProvider": True,
        "configStore": True,
        "freeProviders": [],
    }


def test_bundled_catalog_uses_effort_objects_and_empty_cost(codex_probe, codex_fixture) -> None:
    models = codex_probe("catalog", codex_fixture("models.json"))
    assert models == [
        {
            "id": "gpt-5.6-sol",
            "modelID": "gpt-5.6-sol",
            "providerID": "openai",
            "name": "GPT-5.6-Sol",
            "variants": [{"id": "low"}, {"id": "high"}],
            "cost": [],
            "enabled": True,
        }
    ]
    # Empty cost keeps the core's free-model check fail closed.
    assert all(model["cost"] == [] for model in models)
