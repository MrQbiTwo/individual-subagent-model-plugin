"""Config-file-only control E2E: real files on disk drive real server behaviour.

There is no command and no ``set_policy`` call in these tests (except a one-off
project-key discovery detail). Rules are written atomically to the same
``global.json`` / ``projects/<key>.json`` paths the plugin reads, under a
worker-isolated config root. No model id is hard-coded: every selector comes
from the live catalogue.

This module lives under ``tests/adapters/opencode_cli/e2e`` because it exercises
a real OpenCode server through the CLI adapter, not the repo-level harness. It
keeps the ``e2e`` marker and the canonical direct invocation in CI. Resilient
fixtures skip (never fabricate) on a total model outage.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from conftest import fail_test

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.e2e

EMPTY_RULE: dict[str, Any] = {"models": [], "providers": [], "agentDefaults": {}}


def _descriptor(selector: str, *, is_free: bool) -> dict[str, Any]:
    provider_id, model_id = selector.split("/", 1)
    return {
        "id": model_id,
        "modelID": model_id,
        "providerID": provider_id,
        "name": model_id,
        "selector": selector,
        "isFree": is_free,
        "variants": [],
        "efforts": [],
        "enabled": True,
    }


def _rpc(base_url: str, method: str, payload: dict | None = None) -> dict:
    with httpx.Client(timeout=10.0) as client:
        response = client.post(
            f"{base_url}/api/rpc/subagent-models/{method}",
            json={"input": payload or {}},
        )
    assert response.status_code == 200, response.text
    body = response.json()
    return body.get("output", body)


def _project_key(config_files, rpc_call) -> str:  # noqa: RET503 - fail_test is NoReturn
    """Discover the workspace-derived key the live server uses for project scope.

    ``set_policy`` is part of the preserved read/write RPC contract; it is used
    here only to learn which file the server itself considers the project rule.
    The behaviour under test is still driven by direct file writes afterwards.
    """
    marker = {
        "models": ["__pytest_project_key_marker__/probe"],
        "providers": [],
        "agentDefaults": {},
    }
    rpc_call("set_policy", {"scope": "project", "rule": marker})
    try:
        projects_dir: Path = config_files.root / "projects"
        for path in sorted(projects_dir.glob("*.json")):
            if json.loads(path.read_text(encoding="utf-8")) == marker:
                return path.stem
    finally:
        config_files.reset()
    fail_test("the server did not persist its project rule under the config root")


def test_global_config_file_is_read_by_get_policy(rpc_call, config_files, any_two_models) -> None:
    """global.json is the single source for the global scope, read on demand."""
    config_files.reset()
    assert rpc_call("get_policy", {"scope": "global"})["rule"] == EMPTY_RULE

    first = {"models": [any_two_models[0].primary.selector], "providers": [], "agentDefaults": {}}
    config_files.write_global(first)
    assert rpc_call("get_policy", {"scope": "global"})["rule"] == first
    assert config_files.read_global() == first

    second = {"models": [], "providers": [any_two_models[1].child.provider_id], "agentDefaults": {}}
    config_files.write_global(second)
    assert rpc_call("get_policy", {"scope": "global"})["rule"] == second

    config_files.delete_global()
    assert rpc_call("get_policy", {"scope": "global"})["rule"] == EMPTY_RULE


def test_project_config_file_resolution_and_precedence(
    rpc_call, config_files, core_probe, any_two_models
) -> None:
    """Both scopes resolve from disk; project allowances win over global ones."""
    config_files.reset()
    key = _project_key(config_files, rpc_call)
    global_rule = {
        "models": [any_two_models[0].primary.selector],
        "providers": [],
        "agentDefaults": {},
    }
    project_rule = {
        "models": [],
        "providers": [any_two_models[1].child.provider_id],
        "agentDefaults": {},
    }
    config_files.write_global(global_rule)
    config_files.write_project(project_rule, key=key)

    assert rpc_call("get_policy", {"scope": "global"})["rule"] == global_rule
    assert rpc_call("get_policy", {"scope": "project"})["rule"] == project_rule
    assert config_files.read_project(key=key) == project_rule

    global_model = _descriptor(global_rule["models"][0], is_free=False)
    project_model = _descriptor("__pytest_project__/model", is_free=False)
    project_model["providerID"] = project_rule["providers"][0]
    project_model["selector"] = f"{project_rule['providers'][0]}/model"

    assert core_probe(
        "decide",
        {"model": global_model, "global": global_rule, "project": project_rule},
    )["result"] == {"allowed": True, "reason": "global-model"}
    assert core_probe(
        "decide",
        {"model": project_model, "global": global_rule, "project": project_rule},
    )["result"] == {"allowed": True, "reason": "project-provider"}


def test_missing_config_files_mean_empty_rule(rpc_call, config_files) -> None:
    """A missing file is an implicit empty rule for both scopes."""
    config_files.reset()
    assert not (config_files.root / "global.json").exists()
    for scope in ("global", "project"):
        assert rpc_call("get_policy", {"scope": scope})["rule"] == EMPTY_RULE


def test_denied_config_file_blocks_free_model_and_beats_allow(
    rpc_call, config_files, core_probe, available_models
) -> None:
    """deniedModels / deniedProviders on disk beat allows and the free default."""
    config_files.reset()
    free_selector = available_models[0].selector
    # A synthetic paid selector keeps the proof independent of which providers
    # happen to be connected on the machine running the suite.
    paid_provider = "__pytest_paid__"
    paid_selector = f"{paid_provider}/model"

    rule = {
        "models": [free_selector, paid_selector],
        "providers": [paid_provider],
        "deniedModels": [free_selector],
        "deniedProviders": [],
        "agentDefaults": {},
    }
    config_files.write_global(rule)
    assert rpc_call("get_policy", {"scope": "global"})["rule"] == rule
    assert config_files.read_global() == rule

    # The free model is allowed by `models` but explicitly denied: deny wins.
    assert core_probe(
        "decide",
        {"model": _descriptor(free_selector, is_free=True), "rule": config_files.read_global()},
    )["result"] == {"allowed": False, "reason": "explicitly-denied"}
    # Without the deny the same model is allowed by the free default.
    assert core_probe(
        "decide",
        {"model": _descriptor(free_selector, is_free=True), "rule": EMPTY_RULE},
    )["result"] == {"allowed": True, "reason": "free-default"}

    # A provider deny from the project file beats a global model allow too.
    project_rule = {
        "models": [],
        "providers": [],
        "deniedProviders": [paid_provider],
        "agentDefaults": {},
    }
    assert core_probe(
        "decide",
        {
            "model": _descriptor(paid_selector, is_free=False),
            "global": config_files.read_global(),
            "project": project_rule,
        },
    )["result"] == {"allowed": False, "reason": "explicitly-denied"}
    assert core_probe(
        "decide",
        {
            "model": _descriptor(paid_selector, is_free=False),
            "global": config_files.read_global(),
            "project": EMPTY_RULE,
        },
    )["result"] == {"allowed": True, "reason": "global-model"}

    config_files.reset()
    assert rpc_call("get_policy", {"scope": "global"})["rule"] == EMPTY_RULE


def test_config_file_change_redirects_subagent_model(
    config_files, resilient_spawn, spawn_subagent, available_models, subagent_tool_inputs
) -> None:
    """Rewriting global.json alone changes where a real child subagent lands.

    With only free models available an allow entry cannot change a route (free
    models are allowed by default), so the proof uses the deny fields: adding a
    deny for the requested child forces a different free model; deleting the
    file restores the original route.
    """
    by_selector = {choice.selector: choice for choice in available_models}

    def _denied(pair):
        config_files.write_global(
            {
                "models": [],
                "providers": [],
                "deniedModels": [pair.child.selector],
                "agentDefaults": {},
            }
        )
        parent_id, child = spawn_subagent(pair, child_selector=pair.child.selector)
        return parent_id, child, pair

    parent_id, child, pair = resilient_spawn(_denied)
    child_model = child.get("model") or {}
    selector = f"{child_model.get('providerID')}/{child_model.get('id')}"
    assert selector in by_selector, f"child fell back to an undiscovered model: {selector}"
    assert by_selector[selector].is_free is True
    assert selector != pair.child.selector, "denied child was still selected"
    inputs = subagent_tool_inputs(parent_id)
    assert any(str(item.get("model", "")).split("#")[0] == pair.child.selector for item in inputs)

    def _restored(pair):
        config_files.write_global(EMPTY_RULE)
        parent_id, child = spawn_subagent(pair, child_selector=pair.child.selector)
        return parent_id, child, pair

    parent_id, child, pair = resilient_spawn(_restored)
    child_model = child.get("model") or {}
    selector = f"{child_model.get('providerID')}/{child_model.get('id')}"
    assert selector == pair.child.selector, "removing the deny did not restore the route"
    inputs = subagent_tool_inputs(parent_id)
    assert any(str(item.get("model", "")).split("#")[0] == pair.child.selector for item in inputs)


def test_config_files_survive_server_restart(
    server_handle, rpc_call, config_files, any_two_models
) -> None:
    """Rules live in files, so a fresh server process reads the same values."""
    config_files.reset()
    key = _project_key(config_files, rpc_call)
    global_rule = {
        "models": [any_two_models[0].primary.selector],
        "providers": [],
        "agentDefaults": {},
    }
    project_rule = {
        "models": [any_two_models[1].child.selector],
        "providers": [],
        "agentDefaults": {},
    }
    config_files.write_global(global_rule)
    config_files.write_project(project_rule, key=key)

    assert server_handle.restart() == server_handle.base_url
    assert rpc_call("get_policy", {"scope": "global"})["rule"] == global_rule
    assert rpc_call("get_policy", {"scope": "project"})["rule"] == project_rule


def test_agent_default_from_config_file_applies_after_restart(  # noqa: PLR0913, PLR0917
    server_handle, rpc_call, config_files, resilient_spawn, spawn_subagent, any_two_models
) -> None:
    """agentDefaults need a transform replay, which a fresh server guarantees."""
    config_files.reset()
    pair = any_two_models[0]
    variant = pair.child.variants[0] if pair.child.variants else None
    selector_with_variant = f"{pair.child.selector}#{variant}" if variant else pair.child.selector
    config_files.write_global(
        {
            "models": [],
            "providers": [],
            "agentDefaults": {"general": selector_with_variant},
        }
    )

    assert server_handle.restart() == server_handle.base_url
    assert rpc_call("get_policy", {"scope": "global"})["rule"]["agentDefaults"] == {
        "general": selector_with_variant
    }

    def _action(pair):
        # resilient_spawn resets all rule files between attempts, so replay the
        # agent default for the pair actually used on this attempt.
        variant = pair.child.variants[0] if pair.child.variants else None
        selector = f"{pair.child.selector}#{variant}" if variant else pair.child.selector
        config_files.write_global(
            {"models": [], "providers": [], "agentDefaults": {"general": selector}}
        )
        parent_id, child = spawn_subagent(pair, agent="general")
        return parent_id, child, pair.child.selector

    _parent_id, child, expected = resilient_spawn(_action)
    child_model = child.get("model") or {}
    landed = f"{child_model.get('providerID')}/{child_model.get('id')}"
    assert landed == expected
