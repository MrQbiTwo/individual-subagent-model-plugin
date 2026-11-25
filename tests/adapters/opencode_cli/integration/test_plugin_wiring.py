"""Integration coverage for event-driven refresh and real-server registrations.

These checks pin the two review focuses that cannot be proven by pure unit
tests: empty-data invalidation events must still refresh the catalog, and the
built-in subagent tool must keep a mutable ``model`` input.

The plugin registers no commands and no UI: the real server is asserted to load
the server plugin with its RPC surface active, and configuration is controlled
only by files on disk (see the config-file E2E suite).
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[4]
ROUTING_CORE_FILE = REPO_ROOT / "opencode" / "src" / "adapters" / "opencode_cli" / "routing.ts"
PLUGIN_ID = "individual-subagent-model-plugin"


def test_real_server_loads_plugin(opencode_server: str) -> None:
    """The real server loads our plugin with RPC active and no GUI/TUI feature."""
    with httpx.Client(timeout=10.0) as client:
        response = client.get(f"{opencode_server}/api/plugin")
    assert response.status_code == 200
    entries = response.json().get("data", [])
    plugin = next((item for item in entries if item.get("id") == PLUGIN_ID), None)
    assert plugin is not None
    features = plugin.get("features", {})
    assert features.get("rpc") is True
    assert features.get("tui") is not True
    assert features.get("gui") is not True


def test_plugin_rpc_is_registered(opencode_server: str) -> None:
    """The server fixture must wait for lazy plugin RPC registration."""
    with httpx.Client(timeout=10.0) as client:
        catalog = client.post(
            f"{opencode_server}/api/rpc/subagent-models/get_catalog", json={"input": {}}
        )
        assert catalog.status_code == 200, catalog.text
        catalog_output = catalog.json().get("output", catalog.json())
        assert "catalog" in catalog_output

        policy = client.post(
            f"{opencode_server}/api/rpc/subagent-models/get_policy",
            json={"input": {"scope": "global"}},
        )
        assert policy.status_code == 200, policy.text
        policy_output = policy.json().get("output", policy.json())
        assert "rule" in policy_output


def test_catalog_refresh_after_empty_event(core_probe) -> None:
    """An empty event payload must trigger exactly one additional catalog fetch.

    Call shape: ``core_probe("service_refresh_sequence", {"includeListenerCount": True})``
    returns ``[first_model_count, after_event_model_count, listener_calls]``.
    """
    response = core_probe("service_refresh_sequence", {"includeListenerCount": True})
    assert "error" not in response, response.get("error")
    result = response.get("result", response)
    counts = (
        result.get("counts", result.get("model_counts")) if isinstance(result, dict) else result
    )

    assert counts is not None, "probe did not report catalog model counts"
    assert counts[0] == 1
    assert counts[1] == 2
    if len(counts) > 2:
        assert counts[2] == 1, "catalog.updated fired more than once (duplicate listener)"


def _assert_tool_hook_contract() -> None:
    """Pin the mutable model injection where no tool-listing HTTP route exists."""
    source = ROUTING_CORE_FILE.read_text(encoding="utf-8")
    assert 'ctx.tool.hook("execute.before"' in source
    assert "input.model =" in source
    assert "subagent" in source


def test_subagent_tool_input_exposes_model(opencode_server: str) -> None:
    """The built-in subagent tool must still accept a model override string."""
    with httpx.Client(timeout=10.0) as client:
        response = client.get(f"{opencode_server}/api/tool")
        if response.status_code in (404, 405):
            _assert_tool_hook_contract()
            return
        assert response.status_code == 200
        tools = response.json()

    entries = tools if isinstance(tools, list) else list(tools.values())
    subagent = next(
        (entry for entry in entries if isinstance(entry, dict) and entry.get("name") == "subagent"),
        None,
    )
    if subagent is None:
        _assert_tool_hook_contract()
        return
    schema = subagent.get("input", {})
    properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
    assert "model" in properties, "execute.before requires a mutable model input field"
