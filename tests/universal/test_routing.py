"""Deny-aware routing contracts — a denied free model is never a route.

The free-model last-resort fallback must be gated by the same deny check as
explicit and parent candidates, otherwise a denied built-in would still be
selected silently for subagents.
"""

from __future__ import annotations

from typing import Any

import pytest

from conftest import skip_test

pytestmark = pytest.mark.unit

EMPTY_RULE = {"models": [], "providers": [], "agentDefaults": {}}


def _probe_result(core_probe, op: str, args: dict) -> Any:
    response = core_probe(op, args)
    error = response.get("error")
    if error is not None and error.get("code") == "unknown-op":
        skip_test(f"probe op {op!r} is not registered yet")
    assert error is None, error
    return response.get("result", response)


def _free_model(provider_id: str, model_id: str) -> dict:
    return {
        "id": model_id,
        "modelID": model_id,
        "providerID": provider_id,
        "name": model_id,
        "variants": [{"id": "high", "settings": {}}],
        "cost": [{"input": 0}],
        "enabled": True,
    }


def _catalog(core_probe, models: list[dict]) -> dict:
    return _probe_result(
        core_probe,
        "build_catalog",
        {
            "models": models,
            "providers": [
                {"id": "opencode", "name": "OpenCode"},
                {"id": "opencode-go", "name": "OpenCode Go"},
            ],
        },
    )


def _route(core_probe, catalog: dict, *, global_rule: dict | None = None) -> Any:
    return _probe_result(
        core_probe,
        "resolve_route",
        {
            "input": {"agent": "general", "description": "d", "prompt": "p"},
            "catalog": catalog,
            "global": global_rule if global_rule is not None else EMPTY_RULE,
            "project": EMPTY_RULE,
            "parentModel": {"providerID": "unlisted", "id": "none"},
        },
    )


def test_denied_free_provider_blocks_last_resort_fallback(core_probe) -> None:
    catalog = _catalog(core_probe, [_free_model("opencode", "hy4-flash-free")])
    route = _route(
        core_probe,
        catalog,
        global_rule={**EMPTY_RULE, "deniedProviders": ["opencode", "opencode-go"]},
    )
    assert route is None


def test_denied_free_model_falls_through_to_next_free_model(core_probe) -> None:
    catalog = _catalog(
        core_probe,
        [_free_model("opencode", "a-free"), _free_model("opencode", "b-free")],
    )
    route = _route(
        core_probe,
        catalog,
        global_rule={**EMPTY_RULE, "deniedModels": ["opencode/a-free"]},
    )
    assert route is not None
    assert route["selectorWithVariant"] == "opencode/b-free#high"
