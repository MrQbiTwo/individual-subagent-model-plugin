"""Codex subagent route resolution, including the frozen override rejection."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.contract, pytest.mark.codex_cli]


def test_inline_route_matches_exact_object(codex_probe) -> None:
    assert codex_probe("route") == {
        "ok": True,
        "route": {"providerID": "myrouter", "model": "child", "reasoningEffort": "low"},
    }


def test_provider_override_is_rejected(codex_probe, codex_fixture) -> None:
    result = codex_probe("route", codex_fixture("route.json"))
    assert result == {"ok": False, "reason": "PROVIDER_OVERRIDE_UNSUPPORTED"}
