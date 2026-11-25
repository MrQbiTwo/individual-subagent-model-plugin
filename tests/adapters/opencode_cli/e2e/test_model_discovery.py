"""Real-API integration check for the model-discovery and pair-ranking fixtures.

Unlike ``tests/unit/test_model_fixtures.py`` (fake API payloads), this module
talks to a real ``opencode serve`` and proves the fixtures describe the live
catalogue: every discovered selector exists upstream, no model is fabricated,
and the ranked pairs point at distinct real models.
"""

from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.e2e


def test_available_models_reflect_the_live_catalogue(
    opencode_server: str, available_models
) -> None:
    """Every choice must be a real, enabled chat model from GET /api/model."""
    with httpx.Client(timeout=10.0) as client:
        response = client.get(f"{opencode_server}/api/model")
    assert response.status_code == 200, response.text
    payload = response.json()
    live = payload.get("data", payload) if isinstance(payload, dict) else payload
    live_selectors = {
        f"{entry['providerID']}/{entry['modelID'] or entry['id']}"
        for entry in live
        if isinstance(entry, dict) and entry.get("providerID")
    }

    assert len(available_models) >= 2
    for choice in available_models:
        assert choice.selector == f"{choice.provider_id}/{choice.model_id}"
        assert choice.selector in live_selectors, f"fabricated model: {choice.selector}"
        assert choice.enabled is True
        assert choice.name


def test_any_two_models_are_distinct_real_choices(any_two_models) -> None:
    """The ranked pair list is capped and always contains two different models."""
    assert 1 <= len(any_two_models) <= 12
    for pair in any_two_models:
        assert pair.primary != pair.child
        assert pair.primary.selector != pair.child.selector
        assert pair.primary.provider_id
        assert pair.primary.model_id
        assert pair.child.provider_id
        assert pair.child.model_id

    # The first pair is the deterministic "best" pair used by policy tests.
    # Free models are ranked first, but a paid-only host must not fail here.
    if any(choice.is_free for pair in any_two_models for choice in (pair.primary, pair.child)):
        assert any_two_models[0].primary.is_free is True
