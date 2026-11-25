"""Unit-level checks for the runtime model-discovery and retry fixtures.

These tests use fake ``GET /api/model`` / ``GET /api/provider`` payloads so the
discovery, ranking, pair-building and retry logic can be verified without a
live OpenCode server.  They are pure and therefore safe under xdist.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from conftest import (
    ModelChoice,
    SubagentSpawnError,
    build_model_pairs,
    classify_availability,
    discover_models,
    is_retryable,
    require_two_models,
    run_resilient,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
E2E_DIR = REPO_ROOT / "tests" / "adapters" / "opencode_cli" / "e2e"

FORBIDDEN_LITERALS = (
    "opencode/hy4-flash-free",
    "openai/gpt-4o",
    "openrouter/anthropic/claude-sonnet-5.5#max",
)


def _model(
    provider_id: str,
    model_id: str,
    *,
    enabled: bool = True,
    cost: float = 0.0,
    model_type: str = "chat",
) -> dict:
    return {
        "id": model_id,
        "modelID": model_id,
        "providerID": provider_id,
        "name": model_id.upper(),
        "enabled": enabled,
        "type": model_type,
        "cost": [{"input": cost}],
        "variants": [{"id": "high"}, {"id": "max"}],
    }


def _provider(provider_id: str, **extra: object) -> dict:
    return {"id": provider_id, "name": provider_id.upper(), "activation": "auto", **extra}


def test_discover_models_filters_disabled_nonchat_and_unauthenticated() -> None:
    models = [
        _model("opencode", "free-a"),
        _model("opencode", "disabled", enabled=False),
        _model("openai", "vision", model_type="image"),
        _model("mystery", "needs-auth"),
        _model("openrouter", "paid", cost=3.0),
    ]
    providers = [
        _provider("opencode"),
        _provider("openai"),
        _provider("mystery", status="needs_auth"),
        _provider("openrouter"),
    ]

    choices = discover_models({"data": models}, {"data": providers})

    selectors = [choice.selector for choice in choices]
    assert selectors == ["opencode/free-a", "openrouter/paid"]
    assert all(choice.enabled for choice in choices)


def test_discover_models_prefers_catalog_free_flag_and_rejects_nonchat() -> None:
    models = [
        _model("opencode", "free-a"),
        _model("openrouter", "paid", cost=2.0),
    ]
    providers = [_provider("opencode"), _provider("openrouter")]
    catalog = {
        "catalog": {
            "models": [
                {"selector": "opencode/free-a", "isFree": True},
                {"selector": "openrouter/paid", "isFree": False},
            ]
        }
    }

    choices = discover_models(models, providers, catalog)

    assert choices[0].is_free is True
    assert choices[1].is_free is False
    assert choices[0].variants == ("high", "max")


def test_discover_models_ranks_free_and_opencode_first() -> None:
    models = [
        _model("zzz", "paid", cost=1.0),
        _model("opencode", "free", cost=0.0),
        _model("aaa", "paid", cost=1.0),
    ]
    providers = [_provider("opencode"), _provider("aaa"), _provider("zzz")]

    choices = discover_models(models, providers)

    assert [(c.provider_id, c.model_id) for c in choices] == [
        ("opencode", "free"),
        ("aaa", "paid"),
        ("zzz", "paid"),
    ]


def test_require_two_models_skips_with_clear_reason() -> None:
    one = ModelChoice(
        provider_id="opencode",
        model_id="only",
        selector="opencode/only",
        name="ONLY",
        is_free=True,
        enabled=True,
        variants=(),
    )

    with pytest.raises(pytest.skip.Exception, match="fewer than two usable chat models"):
        require_two_models([one])


def test_build_model_pairs_prefers_different_providers_and_caps_at_twelve() -> None:
    choices = [
        ModelChoice(
            provider_id=f"p{i}",
            model_id=f"m{i}",
            selector=f"p{i}/m{i}",
            name=f"M{i}",
            is_free=i == 0,
            enabled=True,
            variants=(),
        )
        for i in range(8)
    ]

    pairs = build_model_pairs(choices)

    assert len(pairs) == 12
    assert all(pair.primary != pair.child for pair in pairs)
    assert all(pair.primary.provider_id != pair.child.provider_id for pair in pairs[:7])


def test_is_retryable_never_retries_assertion_errors() -> None:
    assert is_retryable(AssertionError("child model was wrong")) is False


def test_is_retryable_classifies_availability_errors() -> None:
    request = httpx.Request("POST", "http://test.local/api/session")
    response = httpx.Response(451, text="country blocked", request=request)

    assert is_retryable(httpx.HTTPStatusError("451", request=request, response=response))
    assert is_retryable(httpx.ReadTimeout("timed out"))
    assert is_retryable(RuntimeError("model temporarily unavailable in this region"))
    assert is_retryable(RuntimeError("plain refusal")) is False


def test_run_resilient_retries_after_forced_451() -> None:
    pairs = build_model_pairs(
        [
            ModelChoice(
                provider_id="opencode",
                model_id="a",
                selector="opencode/a",
                name="A",
                is_free=True,
                enabled=True,
                variants=(),
            ),
            ModelChoice(
                provider_id="openrouter",
                model_id="b",
                selector="openrouter/b",
                name="B",
                is_free=False,
                enabled=True,
                variants=(),
            ),
        ]
    )
    recorded: dict[str, object] = {}

    result = run_resilient(
        lambda pair: pair.child.selector,
        pairs,
        record=recorded.__setitem__,
        force_fail=True,
    )

    assert result == "opencode/a"
    assert recorded["attempts"] == 2
    assert recorded["models_used"] == "openrouter/b -> opencode/a"
    assert "retry_0" in recorded


def _two_pairs() -> list:
    choices = [
        ModelChoice(
            provider_id="opencode",
            model_id="a",
            selector="opencode/a",
            name="A",
            is_free=True,
            enabled=True,
            variants=(),
        ),
        ModelChoice(
            provider_id="openrouter",
            model_id="b",
            selector="openrouter/b",
            name="B",
            is_free=False,
            enabled=True,
            variants=(),
        ),
    ]
    return build_model_pairs(choices)


def test_classify_availability_recognises_free_limit_429() -> None:
    """RED: a 429 free-usage-limit must be classified as an availability outage."""
    assert (
        classify_availability(
            "Free usage limit reached. Connect a provider or subscribe to OpenCode Go.", 429
        )
        is True
    )
    assert classify_availability("provider.free-limit", None) is True
    assert classify_availability("country blocked", 451) is True
    assert classify_availability("plain refusal", None) is False


def test_subagent_spawn_error_surfaces_detail() -> None:
    """RED: the captured provider detail must not be blank in the error message."""
    error = SubagentSpawnError(
        "no child subagent session appeared within 90.0s",
        detail="HTTP 429: Free usage limit reached",
    )
    assert "Free usage limit reached" in str(error)


def test_run_resilient_skips_after_all_pairs_fail_with_availability_errors() -> None:
    """RED: a total model outage must skip (not pass, not bare-fail) and record attempts."""
    recorded: dict[str, object] = {}

    def unavailable(_pair):
        raise SubagentSpawnError(
            "spawn failed", detail="HTTP 429: Free usage limit reached", retryable=True
        )

    with pytest.raises(pytest.skip.Exception, match="no available model pair responded"):
        run_resilient(unavailable, _two_pairs(), record=recorded.__setitem__)
    assert recorded["attempts"] == 2
    assert "attempt_log" in recorded


def test_run_resilient_propagates_assertion_error_as_hard_failure() -> None:
    """RED: an assertion bug must never be converted into a skip by the retry loop."""

    def buggy(_pair):
        raise AssertionError("child landed on the wrong model")

    with pytest.raises(AssertionError, match="wrong model"):
        run_resilient(buggy, _two_pairs())


def test_live_e2e_tests_contain_no_hardcoded_model_ids() -> None:
    sources = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(E2E_DIR.glob("test_*.py"))
    )

    for literal in FORBIDDEN_LITERALS:
        assert literal not in sources
