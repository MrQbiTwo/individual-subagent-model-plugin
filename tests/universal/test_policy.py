"""Allowlist decision and mutation contracts.

The probe ops cover the published JSON contract. A small Node harness covers
``decideWithScopes`` and mutation purity, which the probe does not expose.
"""

from __future__ import annotations

import pytest

from conftest import skip_test

pytestmark = pytest.mark.unit

POLICY_MODULE = "opencode/dist/universal/domain/policy.js"

POLICY_HARNESS = """
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";

const mod = await import(pathToFileURL(resolve(process.argv[2])).href);
const {
  decideWithScopes, effectiveRule, applyRuleMutation, emptyRule, isAllowed, decide,
} = mod;

const descriptor = (selector, isFree, providerID) => {
  const id = selector.split("/").slice(1).join("/");
  return {
    id, modelID: id, providerID: providerID ?? selector.split("/")[0],
    providerName: "Provider", name: selector,
    variants: [{ id: "max", settings: {} }], efforts: ["max"],
    enabled: true, isFree, selector,
  };
};

const globalRule = { models: ["openrouter/m1"], providers: ["anthropic"], agentDefaults: {} };
const projectRule = { models: ["openai/gpt"], providers: ["google"], agentDefaults: {} };
const empty = emptyRule();
const out = {};

out.reasons = {
  free: decideWithScopes(descriptor("opencode/free", true), globalRule, projectRule),
  globalModel: decideWithScopes(descriptor("openrouter/m1", false), globalRule, projectRule),
  globalProvider: decideWithScopes(descriptor("anthropic/claude", false), globalRule, projectRule),
  projectModel: decideWithScopes(descriptor("openai/gpt", false), globalRule, projectRule),
  projectProvider: decideWithScopes(descriptor("google/gemini", false), globalRule, projectRule),
  denied: decideWithScopes(descriptor("meta/llama", false), globalRule, projectRule),
  precedence: decideWithScopes(
    descriptor("openrouter/m1", false), globalRule,
    { models: ["openrouter/m1"], providers: [], agentDefaults: {} },
  ),
  denyModel: decideWithScopes(
    descriptor("opencode/hy4-flash-free", true),
    { models: [], providers: [], agentDefaults: {}, deniedModels: ["opencode/hy4-flash-free"] },
    empty,
  ),
  denyProvider: decideWithScopes(
    descriptor("opencode/beam-free", true),
    empty,
    { models: [], providers: [], agentDefaults: {}, deniedProviders: ["opencode"] },
  ),
  denyBeatsAllow: decideWithScopes(
    descriptor("openrouter/m1", false),
    {
      models: ["openrouter/m1"], providers: [], agentDefaults: {},
      deniedModels: ["openrouter/m1"],
    },
    empty,
  ),
  denyInDecide: decide(
    descriptor("openrouter/m1", false),
    {
      models: ["openrouter/m1"], providers: [], agentDefaults: {},
      deniedProviders: ["openrouter"],
    },
  ),
};
out.effective = effectiveRule(
  { models: ["a/1"], providers: ["p1"], agentDefaults: { coder: "global" } },
  { models: ["a/1", "b/2"], providers: ["p2"], agentDefaults: { coder: "project" } },
);
out.effectiveDenied = effectiveRule(
  { models: [], providers: [], agentDefaults: {}, deniedModels: ["a/1"] },
  {
    models: [], providers: [], agentDefaults: {},
    deniedModels: ["a/1", "b/2"], deniedProviders: ["p"],
  },
);
out.effectivePlain = effectiveRule(globalRule, projectRule);
out.empty = empty;
out.isAllowed = isAllowed(descriptor("opencode/free", true), empty);
out.decide = decide(descriptor("openrouter/m1", false), globalRule);

const original = {
  models: ["openrouter/m1"], providers: ["anthropic"], agentDefaults: { coder: "old" },
};
const snapshot = JSON.stringify(original);
const toggled = applyRuleMutation(original, { kind: "toggle-model", selector: "openrouter/m1" });
const providerOff = applyRuleMutation(original, {
  kind: "set-provider", providerID: "anthropic", enabled: false,
});
const agentSet = applyRuleMutation(original, {
  kind: "set-agent-default", agentID: "coder", selectorWithVariant: "openrouter/m1#max",
});
const agentCleared = applyRuleMutation(original, { kind: "set-agent-default", agentID: "coder" });
out.mutations = {
  originalUnchanged: JSON.stringify(original) === snapshot,
  toggleResult: toggled,
  providerOffResult: providerOff,
  agentSetResult: agentSet,
  agentClearedResult: agentCleared,
  distinctObjects: toggled !== original && agentSet !== original,
};

process.stdout.write(JSON.stringify(out));
"""


def _probe_result(core_probe, op: str, args: dict) -> dict:
    response = core_probe(op, args)
    error = response.get("error")
    if error is not None and error.get("code") == "unknown-op":
        skip_test(f"probe op {op!r} is not registered yet")
    assert error is None, error
    return response.get("result", response)


def _descriptor(selector: str, *, is_free: bool) -> dict:
    return {
        "id": selector.split("/", 1)[1],
        "modelID": selector.split("/", 1)[1],
        "providerID": selector.split("/", 1)[0],
        "providerName": "Provider",
        "name": selector,
        "variants": [{"id": "max", "settings": {}}],
        "efforts": ["max"],
        "enabled": True,
        "isFree": is_free,
        "selector": selector,
    }


def test_decide_reasons_from_probe(core_probe) -> None:
    rule = {"models": ["openrouter/m1"], "providers": ["anthropic"], "agentDefaults": {}}
    cases = (
        (_descriptor("opencode/free", is_free=True), (True, "free-default")),
        (_descriptor("openrouter/m1", is_free=False), (True, "global-model")),
        (_descriptor("anthropic/claude", is_free=False), (True, "global-provider")),
        (_descriptor("openai/gpt", is_free=False), (False, "not-allowlisted")),
    )
    for model, expected in cases:
        decision = _probe_result(core_probe, "decide", {"model": model, "rule": rule})
        assert (decision["allowed"], decision["reason"]) == expected


def test_apply_mutation_from_probe(core_probe) -> None:
    rule = {
        "models": ["openrouter/m1"],
        "providers": ["anthropic"],
        "agentDefaults": {},
    }
    toggled = _probe_result(
        core_probe,
        "apply_mutation",
        {"rule": rule, "mutation": {"kind": "toggle-model", "selector": "openrouter/m1"}},
    )
    assert toggled["models"] == []

    provider_off = _probe_result(
        core_probe,
        "apply_mutation",
        {
            "rule": rule,
            "mutation": {"kind": "set-provider", "providerID": "anthropic", "enabled": False},
        },
    )
    assert provider_off["providers"] == []

    agent_default = _probe_result(
        core_probe,
        "apply_mutation",
        {
            "rule": rule,
            "mutation": {
                "kind": "set-agent-default",
                "agentID": "coder",
                "selectorWithVariant": "openrouter/m1#max",
            },
        },
    )
    assert agent_default["agentDefaults"]["coder"] == "openrouter/m1#max"


def test_decide_with_scopes_reasons(run_node) -> None:
    result = run_node(POLICY_HARNESS, POLICY_MODULE)
    reasons = {
        name: (value["allowed"], value["reason"]) for name, value in result["reasons"].items()
    }
    assert reasons == {
        "free": (True, "free-default"),
        "globalModel": (True, "global-model"),
        "globalProvider": (True, "global-provider"),
        "projectModel": (True, "project-model"),
        "projectProvider": (True, "project-provider"),
        "denied": (False, "not-allowlisted"),
        "precedence": (True, "global-model"),
        "denyModel": (False, "explicitly-denied"),
        "denyProvider": (False, "explicitly-denied"),
        "denyBeatsAllow": (False, "explicitly-denied"),
        "denyInDecide": (False, "explicitly-denied"),
    }


def test_deny_fields_union_in_effective_rule(run_node) -> None:
    result = run_node(POLICY_HARNESS, POLICY_MODULE)
    assert result["effectiveDenied"]["deniedModels"] == ["a/1", "b/2"]
    assert result["effectiveDenied"]["deniedProviders"] == ["p"]
    # A rule with no deny fields must stay byte-shape compatible with the old contract.
    assert "deniedModels" not in result["effectivePlain"]
    assert "deniedProviders" not in result["effectivePlain"]


def test_deny_decision_from_probe(core_probe) -> None:
    rule = {
        "models": [],
        "providers": [],
        "agentDefaults": {},
        "deniedModels": ["opencode/free"],
    }
    decision = _probe_result(
        core_probe, "decide", {"model": _descriptor("opencode/free", is_free=True), "rule": rule}
    )
    assert decision == {"allowed": False, "reason": "explicitly-denied"}


def test_rule_helpers(run_node) -> None:
    result = run_node(POLICY_HARNESS, POLICY_MODULE)
    assert result["empty"] == {"models": [], "providers": [], "agentDefaults": {}}
    assert result["isAllowed"] is True
    assert result["decide"] == {"allowed": True, "reason": "global-model"}
    assert result["effective"] == {
        "models": ["a/1", "b/2"],
        "providers": ["p1", "p2"],
        "agentDefaults": {"coder": "project"},
    }


def test_mutation_is_pure(run_node) -> None:
    result = run_node(POLICY_HARNESS, POLICY_MODULE)
    mutations = result["mutations"]
    assert mutations["originalUnchanged"] is True
    assert mutations["distinctObjects"] is True
    assert mutations["toggleResult"]["models"] == []
    assert mutations["providerOffResult"]["providers"] == []
    assert mutations["agentSetResult"]["agentDefaults"]["coder"] == "openrouter/m1#max"
    assert "coder" not in mutations["agentClearedResult"]["agentDefaults"]
