"""Config parsing, serialization and file-store contracts.

Probe ops pin the JSON contract; a Node harness exercises the compiled
``projectKey`` and ``FileConfigStore`` implementation directly.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

import pytest

from conftest import skip_test

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.unit

CONFIG_MODULE = "opencode/dist/universal/domain/config.js"
STORE_MODULE = "opencode/dist/adapters/opencode_cli/config_store.js"

CONFIG_HARNESS = """
import { pathToFileURL } from "node:url";
import { resolve, join } from "node:path";
import { readdirSync } from "node:fs";

const [configPath, storePath, root] = process.argv.slice(2);
const config = await import(pathToFileURL(resolve(configPath)).href);
const storeModule = await import(pathToFileURL(resolve(storePath)).href);

const out = {};
out.version = config.CONFIG_VERSION;
out.projectKeys = {
  slash: config.projectKey("a/b"),
  traversal: config.projectKey("../../traversal_probe_9f3c"),
};
out.defaultConfig = config.defaultPluginConfig();

const store = new storeModule.FileConfigStore(root);
const ruleOne = {
  models: ["openrouter/m1"],
  providers: ["anthropic"],
  agentDefaults: { coder: "openrouter/m1#max" },
};
const ruleTwo = { models: [], providers: ["openai"], agentDefaults: {} };

out.missing = await store.read("global");
await store.write("global", ruleOne);
out.afterWrite = await store.read("global");
await store.write("global", ruleTwo);
out.afterOverwrite = await store.read("global");
await store.write("project", ruleOne, "workspace/one");
await store.write("project", ruleTwo, "second");
out.readAll = await store.readAll();

const traversalKey = "../../traversal_probe_9f3c";
await store.write("project", ruleOne, traversalKey);
out.traversalRead = await store.read("project", traversalKey);
out.traversalKeys = Object.keys((await store.readAll()).projects);
out.traversalFiles = readdirSync(join(root, "projects")).filter((name) =>
  name.includes("traversal_probe_9f3c"),
);
// A rule carrying deny fields must round-trip through disk unchanged.
const denyRule = {
  models: [], providers: [], agentDefaults: {},
  deniedModels: ["x/y"], deniedProviders: ["p"],
};
await store.write("project", denyRule, "deny-project");
out.denyStoreRoundTrip = await store.read("project", "deny-project");

out.configRoot = storeModule.resolveConfigRoot({ XDG_CONFIG_HOME: root, APPDATA: root });
process.stdout.write(JSON.stringify(out));
"""


def _probe_result(core_probe, op: str, args: dict) -> dict:
    response = core_probe(op, args)
    error = response.get("error")
    if error is not None and error.get("code") == "unknown-op":
        skip_test(f"probe op {op!r} is not registered yet")
    assert error is None, error
    return response.get("result", response)


def test_config_round_trip_via_probe(core_probe) -> None:
    config = {
        "version": 1,
        "global": {"models": ["openrouter/m1"], "providers": [], "agentDefaults": {}},
        "projects": {"a_b": {"models": [], "providers": ["anthropic"], "agentDefaults": {}}},
    }
    text = _probe_result(core_probe, "serialize_config", {"config": config})
    assert isinstance(text, str)
    assert text.endswith("\n")
    assert _probe_result(core_probe, "parse_config", {"text": text}) == config


def test_bare_rule_without_deny_fields_remains_valid(core_probe) -> None:
    """Legacy bare three-field files stay valid after the deny schema lands."""
    config = {
        "version": 1,
        "global": {"models": [], "providers": [], "agentDefaults": {}},
        "projects": {"default": {"models": [], "providers": [], "agentDefaults": {}}},
    }
    assert _probe_result(core_probe, "parse_config", {"config": config}) == config


def test_deny_fields_validate_and_round_trip(core_probe) -> None:
    config = {
        "version": 1,
        "global": {
            "models": [],
            "providers": [],
            "deniedModels": ["opencode/hy4-flash-free"],
            "deniedProviders": ["opencode-go"],
            "agentDefaults": {},
        },
        "projects": {
            "default": {
                "models": [],
                "providers": [],
                "deniedModels": ["a/1"],
                "deniedProviders": ["p1"],
                "agentDefaults": {},
            }
        },
    }
    text = _probe_result(core_probe, "serialize_config", {"config": config})
    assert _probe_result(core_probe, "parse_config", {"text": text}) == config

    invalid = {
        "version": 1,
        "global": {"models": [], "providers": [], "agentDefaults": {}, "deniedModels": [7]},
        "projects": {},
    }
    response = core_probe("parse_config", {"config": invalid})
    error = response.get("error")
    if error is not None and error.get("code") == "unknown-op":
        skip_test("probe op 'parse_config' is not registered yet")
    assert error is not None
    assert error["code"] == "invalid-config"


def test_config_v2_is_rejected_via_probe(core_probe) -> None:
    response = core_probe(
        "parse_config", {"text": json.dumps({"version": 2, "global": {}, "projects": {}})}
    )
    error = response.get("error")
    if error is not None and error.get("code") == "unknown-op":
        skip_test("probe op 'parse_config' is not registered yet")
    assert error is not None
    assert error["code"] == "invalid-config"


def test_project_key_and_defaults(run_node, tmp_path: Path) -> None:
    result = run_node(CONFIG_HARNESS, CONFIG_MODULE, STORE_MODULE, str(tmp_path))
    assert result["version"] == 1
    assert result["projectKeys"] == {
        "slash": "a_b",
        "traversal": "______traversal_probe_9f3c",
    }
    assert result["defaultConfig"] == {
        "version": 1,
        "global": {"models": [], "providers": [], "agentDefaults": {}},
        "projects": {},
    }


def test_file_store_read_write_overwrite(run_node, tmp_path: Path) -> None:
    root = tmp_path / "store_root"
    root.mkdir()
    result = run_node(CONFIG_HARNESS, CONFIG_MODULE, STORE_MODULE, str(root))

    expected_first = {
        "models": ["openrouter/m1"],
        "providers": ["anthropic"],
        "agentDefaults": {"coder": "openrouter/m1#max"},
    }
    expected_second = {"models": [], "providers": ["openai"], "agentDefaults": {}}
    assert result["missing"] == {"models": [], "providers": [], "agentDefaults": {}}
    assert result["afterWrite"] == expected_first
    assert result["afterOverwrite"] == expected_second
    assert result["denyStoreRoundTrip"] == {
        "models": [],
        "providers": [],
        "agentDefaults": {},
        "deniedModels": ["x/y"],
        "deniedProviders": ["p"],
    }
    assert result["readAll"]["version"] == 1
    assert result["readAll"]["global"] == expected_second
    assert result["readAll"]["projects"] == {
        "workspace_one": expected_first,
        "second": expected_second,
    }


def test_file_store_rejects_path_traversal(run_node, tmp_path: Path) -> None:
    root = tmp_path / "store_root"
    root.mkdir()
    result = run_node(CONFIG_HARNESS, CONFIG_MODULE, STORE_MODULE, str(root))

    assert result["traversalRead"] == result["afterWrite"]
    assert result["traversalFiles"] == ["______traversal_probe_9f3c.json"]
    for key in result["traversalKeys"]:
        assert re.fullmatch(r"[A-Za-z0-9_-]+", key), key
        assert ".." not in key
        assert "/" not in key
        assert "\\" not in key
    escaped = [path for path in tmp_path.rglob("*traversal_probe_9f3c*") if path.is_file()]
    assert escaped
    assert all(path.parent == root / "projects" for path in escaped)
    assert result["configRoot"].endswith("individual-subagent-model-plugin")
