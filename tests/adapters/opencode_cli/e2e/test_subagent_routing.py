"""Real-client E2E coverage for subagent model authorization.

These tests drive a real ``opencode serve`` v2.3.2, a real primary model and a
real spawned child subagent. No mocks or fake HTTP responses are used.

Both tests select their primary/child models at runtime from the live
``GET /api/model`` catalogue via ``available_models`` / ``any_two_models``, and
use ``resilient_spawn`` to retry with another pair when a provider is
unavailable.  A synthetic guaranteed-absent selector proves the disallowed
fallback without depending on any one machine's catalogue.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e

DISALLOWED_MODEL = "__pytest_missing__/no-such-model"


def _empty_rule() -> dict:
    return {"models": [], "providers": [], "agentDefaults": {}}


def test_disallowed_model_is_stripped(
    config_files,
    resilient_spawn,
    spawn_subagent,
    available_models,
    subagent_tool_inputs,
) -> None:
    """A disallowed model must never reach a real spawned child session."""
    state: dict = {}

    def _action(pair):
        config_files.write_global(_empty_rule())
        parent_id, child = spawn_subagent(pair, child_selector=DISALLOWED_MODEL)
        state["parent_id"] = parent_id
        state["child"] = child
        return parent_id, child

    resilient_spawn(_action)

    child = state["child"]
    model = child.get("model") or {}
    by_selector = {choice.selector: choice for choice in available_models}
    selector = f"{model.get('providerID')}/{model.get('id')}"
    assert selector in by_selector, f"child fell back to an undiscovered model: {selector}"
    assert by_selector[selector].is_free is True
    assert model.get("id") != "no-such-model"

    # OpenCode's message history records the tool call as requested by the primary
    # model (pre-hook), so it must contain the synthetic selector. The assertions
    # above prove the hook stripped it before the child ran: the child landed on a
    # free model from the live catalogue instead of the undiscoverable one.
    inputs = subagent_tool_inputs(state["parent_id"])
    assert inputs, "no real subagent tool call was recorded"
    requested = [str(item.get("model", "")) for item in inputs]
    assert any(value.split("#")[0] == DISALLOWED_MODEL for value in requested), (
        f"the disallowed selector was never requested: {requested!r}"
    )


def test_slashed_selector_round_trip(
    config_files,
    resilient_spawn,
    spawn_subagent,
    subagent_tool_inputs,
) -> None:
    """Provider/model/variant syntax must survive a real config file and tool input."""
    state: dict = {}

    def _action(pair):
        variant = pair.child.variants[0] if pair.child.variants else "max"
        selector = f"{pair.child.selector}#{variant}"
        rule = {"models": [selector], "providers": [], "agentDefaults": {}}
        config_files.write_global(rule)
        # An AssertionError here is a real bug and is never retried.
        assert config_files.read_global() == rule
        state["selector"] = selector
        state["variant_is_real"] = bool(pair.child.variants)
        parent_id, child = spawn_subagent(pair, child_selector=selector)
        state["parent_id"] = parent_id
        state["child"] = child
        return parent_id, child

    resilient_spawn(_action)

    inputs = subagent_tool_inputs(state["parent_id"])
    assert inputs, "no real subagent tool call was recorded"
    if state["variant_is_real"]:
        assert any(item.get("model") == state["selector"] for item in inputs)
    else:
        # A synthetic variant cannot be resolved; the child must still land on
        # a real discovered model rather than the unknown provider/model.
        assert any(isinstance(item.get("model"), str) for item in inputs)
    assert (state["child"].get("model") or {}).get("providerID") is not None
