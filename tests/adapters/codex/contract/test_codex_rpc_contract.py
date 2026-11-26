"""Frozen Codex RPC names and offline JSONL wire parsing."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.contract, pytest.mark.codex_cli]


def test_rpc_namespace_methods_and_events(codex_probe) -> None:
    assert codex_probe("contract") == {
        "namespace": "subagent-models",
        "methods": ["get_catalog", "get_policy", "set_policy"],
        "events": ["catalog_updated", "policy_updated"],
    }


def test_exec_jsonl_event_types(codex_probe, codex_fixture) -> None:
    assert codex_probe("jsonl", codex_fixture("events.jsonl")) == [
        "thread.started",
        "turn.started",
        "item.completed",
        "turn.completed",
    ]


@pytest.mark.codex_app
def test_app_server_jsonrpc_message_methods(codex_probe, codex_fixture) -> None:
    assert codex_probe("jsonl", codex_fixture("app_server.jsonl")) == [
        "initialize",
        "notifications/initialized",
        "tools/list",
    ]
