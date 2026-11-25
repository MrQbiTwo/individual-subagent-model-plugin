"""Real HTTP/RPC coverage for the server's read-only observability surface."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e

EMPTY_RULE = {"models": [], "providers": [], "agentDefaults": {}}


def test_get_catalog_returns_real_models(rpc_call, available_models) -> None:
    """The live catalogue must expose at least two usable chat models (research 15 §2)."""
    assert len(available_models) >= 2
    catalog = rpc_call("get_catalog")["catalog"]
    assert catalog["models"]
    for model in catalog["models"]:
        assert {"id", "modelID", "providerID", "selector", "efforts", "isFree"} <= model.keys()


def test_get_policy_returns_both_scopes(rpc_call) -> None:
    for scope in ("global", "project"):
        rule = rpc_call("get_policy", {"scope": scope})["rule"]
        assert {"models", "providers", "agentDefaults"} <= rule.keys()


def test_config_file_policy_persists_through_restart(
    rpc_call, server_handle, config_files, any_two_models
) -> None:
    """A rule written to disk survives a fresh server process."""
    config_files.reset()
    selector = any_two_models[0].primary.selector
    rule = {"models": [selector], "providers": [], "agentDefaults": {}}
    config_files.write_global(rule)
    assert rpc_call("get_policy", {"scope": "global"})["rule"] == rule

    assert server_handle.restart() == server_handle.base_url
    assert rpc_call("get_policy", {"scope": "global"})["rule"] == rule

    config_files.delete_global()
    assert rpc_call("get_policy", {"scope": "global"})["rule"] == EMPTY_RULE


def test_set_policy_round_trip_is_preserved(rpc_call, any_two_models) -> None:
    """The RPC write method remains wire-compatible; config files are the UI."""
    selector = any_two_models[0].primary.selector
    rule = {"models": [selector], "providers": [], "agentDefaults": {}}
    rpc_call("set_policy", {"scope": "global", "rule": rule})
    assert rpc_call("get_policy", {"scope": "global"})["rule"] == rule
    rpc_call("set_policy", {"scope": "global", "rule": EMPTY_RULE})
    assert rpc_call("get_policy", {"scope": "global"})["rule"] == EMPTY_RULE
