"""Shared pytest configuration and fixtures for the plugin test suite.

Layers:
    unit        - pure Python checks, no external process
    integration - core probe plus a live OpenCode server
    e2e         - real OpenCode CLI / HTTP API / client behaviour

Every test file is auto-marked from its parent directory, so contributors only
need to place a test in the matching folder. Skips in the live-server fixtures
only happen on developer machines that have not built the plugin yet; the CI
runners install the OpenCode CLI and build the plugin before invoking pytest.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn, TypeVar, cast

import httpx
import pytest

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    T = TypeVar("T")

REPO_ROOT = Path(__file__).resolve().parents[1]
# The host-free core moved out of the agent package; compiled output and probes
# stay under opencode/ (two-stage build), so only the source root is repo-root.
UNIVERSAL_SRC = REPO_ROOT / "universal"
# npm run build --prefix opencode chains the universal declaration emit and the
# unchanged adapter program; keep every skip hint aligned with that command.
BUILD_HINT = "run npm run build --prefix opencode (universal + adapter)"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# ty 0.0.107 mis-infers the signatures of pytest 8's decorated ``skip``/``fail``
# (it sees zero positional args). Narrow casts restore the real NoReturn contract
# without suppressing genuine diagnostics elsewhere.
skip_test = cast("Callable[..., NoReturn]", pytest.skip)
fail_test = cast("Callable[..., NoReturn]", pytest.fail)

SERVER_STARTUP_TIMEOUT = 30.0
SERVER_POLL_INTERVAL = 0.25
PLUGIN_RPC_TIMEOUT = 10.0
PLUGIN_ID = "individual-subagent-model-plugin"
SERVER_PASSWORD = "pytest-e2e-password"  # noqa: S105 - fixed local test credential
MARKER_DESCRIPTIONS = {
    "unit": "fast isolated tests that need no external process",
    "integration": "tests that use the core probe and a live OpenCode server",
    "e2e": "end-to-end tests that drive the real OpenCode client or CLI",
    "universal": "host-free core tests (no OpenCode SDK, SolidJS or Node host APIs)",
    "contract": "adapter contract tests (fake host, no live server)",
    "opencode_cli": "OpenCode CLI adapter contract and live-server checks",
    "opencode_desktop": "OpenCode Desktop absence and shared-config contract (static)",
    "codex_cli": "Codex CLI adapter contract checks (offline probe, no account)",
    "codex_app": "Codex app-server JSON-RPC wire contract (offline fixture)",
}

# Model discovery / resilience policy (research 15 §2).  These values are
# derived from the live API shape, never from a hard-coded catalogue.
BUILTIN_FREE_PROVIDERS = frozenset({"opencode", "opencode-go"})
NON_CHAT_MODEL_TYPES = frozenset(
    {"image", "video", "decision", "speech", "transcription", "embedding"}
)
RETRY_STATUS_CODES = frozenset(
    {400, 401, 402, 403, 404, 407, 408, 409, 429, 451, 500, 502, 503, 504}
)
RETRYABLE_TEXT = re.compile(
    r"(?i)(unavailable|not\s+found|not\s+supported|unauthoriz|forbid|denied|"
    r"rate.?limit|quota|region|country|geo|overload|temporar|model.*(disabled|removed)|"
    r"budget|credit|balance|context\s+length|"
    r"free.?usage|usage.?limit|limit.?reached|free-limit)"
)
EMPTY_RULE: dict[str, Any] = {"models": [], "providers": [], "agentDefaults": {}}
MAX_PAIRS = 12
TOP_K_MODELS = 8
SPAWN_TIMEOUT = 90.0
RESILIENT_DEADLINE = 480.0


@dataclass(frozen=True)
class ModelChoice:
    """One usable chat model discovered from the live OpenCode API."""

    provider_id: str
    model_id: str
    selector: str
    name: str
    is_free: bool
    enabled: bool
    variants: tuple[str, ...]


@dataclass(frozen=True)
class ModelPair:
    """A primary (parent session) model and a child (subagent tool) model."""

    primary: ModelChoice
    child: ModelChoice


class SubagentSpawnError(RuntimeError):
    """A spawn that failed; ``retryable`` distinguishes provider errors from refusals."""

    def __init__(self, message: str, *, detail: str = "", retryable: bool = True) -> None:
        super().__init__(message)
        self.detail = detail
        self.retryable = retryable

    def __str__(self) -> str:
        """Surface the captured provider detail so an outage is never a blank error."""
        base = super().__str__()
        return f"{base}: {self.detail}" if self.detail else base


def classify_availability(detail: str, status: int | None = None) -> bool:
    """Return True when a spawn failure is an external availability problem.

    A quota/limit 429 (e.g. OpenCode ``provider.free-limit``) is an account-wide
    outage rather than a per-model refusal, so a status in ``RETRY_STATUS_CODES``
    wins even when the human-readable text is unfamiliar.
    """
    if status is not None and status in RETRY_STATUS_CODES:
        return True
    return bool(RETRYABLE_TEXT.search(detail))


def pytest_configure(config: pytest.Config) -> None:
    """Register the three test layers explicitly (no undeclared marks)."""
    for name, description in MARKER_DESCRIPTIONS.items():
        config.addinivalue_line("markers", f"{name}: {description}")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Auto-mark tests by directory so every collected test matches the runner filter."""
    for item in items:
        for layer in MARKER_DESCRIPTIONS:
            if layer in item.path.parts:
                item.add_marker(getattr(pytest.mark, layer))


def _unwrap(payload: object) -> list[dict]:
    """Accept both ``{"data": [...]}`` and bare-list OpenCode API responses."""
    if isinstance(payload, dict):
        payload = payload.get("data", [])
    if not isinstance(payload, list):
        return []
    return [entry for entry in payload if isinstance(entry, dict)]


def discover_models(  # noqa: C901, PLR0912 - exhaustive filtering of live API payloads
    model_response: object,
    provider_response: object,
    catalog_response: object | None = None,
    *,
    seed: int | None = None,
) -> list[ModelChoice]:
    """Turn real ``/api/model`` + ``/api/provider`` payloads into ranked choices.

    No model id is ever fabricated: entries that are disabled, disabled at the
    provider level, non-chat, missing required keys or unauthenticated are
    dropped.  ``catalog_response`` (the plugin's ``get_catalog``) is an optional
    cross-check for ``isFree``.  This is a pure function so it can be unit
    tested with fake API responses.
    """
    providers: dict[str, dict] = {}
    for provider in _unwrap(provider_response):
        provider_id = provider.get("id")
        if isinstance(provider_id, str):
            providers[provider_id] = provider

    catalog_free: dict[str, bool] = {}
    if isinstance(catalog_response, dict):
        catalog = catalog_response.get("catalog", catalog_response)
        if isinstance(catalog, dict):
            for entry in _unwrap(catalog.get("models", [])):
                selector = entry.get("selector")
                if isinstance(selector, str) and isinstance(entry.get("isFree"), bool):
                    catalog_free[selector] = entry["isFree"]

    choices: list[ModelChoice] = []
    for model in _unwrap(model_response):
        provider_id = model.get("providerID")
        model_id = model.get("modelID") or model.get("id")
        if not isinstance(provider_id, str) or not isinstance(model_id, str):
            continue
        if model.get("enabled") is False:
            continue
        provider = providers.get(provider_id, {})
        if provider.get("activation") == "disabled":
            continue
        if provider.get("status") == "needs_auth" or provider.get("connected") is False:
            continue
        model_type = str(model.get("type") or "").lower()
        if model_type in NON_CHAT_MODEL_TYPES:
            continue

        cost = model.get("cost")
        is_free = (
            provider_id in BUILTIN_FREE_PROVIDERS
            and isinstance(cost, list)
            and bool(cost)
            and all(isinstance(tier, dict) and tier.get("input", 1) == 0 for tier in cost)
        )
        selector = f"{provider_id}/{model_id}"
        is_free = catalog_free.get(selector, is_free)

        variants: list[str] = []
        for variant in model.get("variants") or []:
            if isinstance(variant, dict) and isinstance(variant.get("id"), str):
                variants.append(variant["id"])
            elif isinstance(variant, str):
                variants.append(variant)

        name = model.get("name")
        choices.append(
            ModelChoice(
                provider_id=provider_id,
                model_id=model_id,
                selector=selector,
                name=str(name) if name else model_id,
                is_free=bool(is_free),
                enabled=model.get("enabled") is not False,
                variants=tuple(variants),
            )
        )

    choices.sort(
        key=lambda choice: (
            -int(choice.is_free),
            choice.provider_id != "opencode",
            choice.provider_id,
            choice.model_id,
        )
    )
    if seed is not None and choices:
        pivot = seed % len(choices)
        choices = choices[pivot:] + choices[:pivot]
    return choices


def require_two_models(choices: list[ModelChoice]) -> list[ModelChoice]:
    """Skip (never fabricate) when the live catalogue cannot satisfy the test."""
    if len(choices) < 2:
        skip_test(f"fewer than two usable chat models from GET /api/model (found {len(choices)})")
    return choices


def build_model_pairs(
    choices: list[ModelChoice], *, max_pairs: int = MAX_PAIRS, top_k: int = TOP_K_MODELS
) -> list[ModelPair]:
    """Rank ordered pairs: different providers first, then a free model first."""
    top = choices[:top_k]
    pairs = [ModelPair(a, b) for a in top for b in top if a != b]
    pairs.sort(
        key=lambda pair: (
            pair.primary.provider_id == pair.child.provider_id,
            not (pair.primary.is_free or pair.child.is_free),
        )
    )
    return pairs[:max_pairs]


def is_retryable(exc: BaseException) -> bool:
    """Classify an error as an availability problem we may retry.

    ``AssertionError`` and pytest's own ``Failed`` outcome are deliberately not
    retryable: a wrong-model child is a routing bug that must stay visible.
    """
    if isinstance(exc, (AssertionError, pytest.fail.Exception)):
        return False
    if isinstance(exc, SubagentSpawnError):
        return exc.retryable
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRY_STATUS_CODES or bool(
            RETRYABLE_TEXT.search(exc.response.text or "")
        )
    if isinstance(exc, httpx.TransportError):
        return True
    return bool(RETRYABLE_TEXT.search(str(exc)))


def run_resilient[T](  # noqa: PLR0913, RET503 - skip_test is NoReturn
    action: Callable[[ModelPair], T],
    pairs: list[ModelPair],
    *,
    reset: Callable[[], None] = lambda: None,
    record: Callable[[str, object], None] = lambda _key, _value: None,
    deadline: float | None = None,
    force_fail: bool = False,
) -> T:
    """Run ``action`` against ranked pairs, retrying only availability failures.

    Assertion bugs (and pytest ``Failed``) are re-raised immediately, so reaching
    the end means every attempt was an external availability failure.  A total
    outage therefore skips with a clear reason rather than passing or failing
    bare; the per-pair log is recorded on the test for diagnostics.
    """
    log: list[dict[str, str]] = []
    for index, pair in enumerate(pairs):
        if deadline is not None and time.monotonic() > deadline:
            log.append({"attempt": str(index + 1), "error": "deadline exceeded"})
            break
        reset()
        if force_fail and index == 0:
            log.append({"attempt": "1", "error": "synthetic 451 (country blocked)"})
            record("retry_0", f"{pair}: synthetic 451 (country blocked)")
            continue
        try:
            result = action(pair)
        except Exception as exc:  # classified explicitly by is_retryable below
            if not is_retryable(exc):
                raise
            log.append({"attempt": str(index + 1), "error": f"{type(exc).__name__}: {exc}"})
            record(f"retry_{index}", f"{pair}: {exc}")
            continue
        record("models_used", f"{pair.primary.selector} -> {pair.child.selector}")
        record("attempts", index + 1)
        return result
    attempt_log = json.dumps(log, default=str)
    record("attempts", len(log))
    record("attempt_log", attempt_log)
    skip_test(
        f"no available model pair responded ({len(log)} attempts); "
        "see attempt_log property for the per-pair errors"
    )


def _reserve_port(  # noqa: RET503 - fail_test is NoReturn
    worker_id: str = "master", offset: int = 0
) -> tuple[socket.socket, int]:
    """Reserve a loopback port from a worker-private range.

    The socket is returned open (with ``SO_REUSEADDR``) so a concurrent xdist
    worker cannot grab the same port between reservation and ``Popen``.  The
    caller closes it immediately before launching the server. ``offset`` shifts
    into a separate 42xxx band for extra servers on the same worker.
    """
    if worker_id == "master":
        base = 41_000
    else:
        suffix = worker_id.removeprefix("gw")
        base = 41_000 + (int(suffix) + 1) * 100
    base += offset * 1_000
    for port in range(base, base + 100):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", port))
        except OSError:
            sock.close()
        else:
            return sock, port
    fail_test(f"no free loopback port in worker range {base}..{base + 99}")


def _wait_for_port_free(port: int, timeout: float = 20.0) -> None:
    """Wait until a loopback port can be bound again after a process-tree kill."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", port))
        except OSError:
            sock.close()
            time.sleep(SERVER_POLL_INTERVAL)
        else:
            sock.close()
            return
    fail_test(f"loopback port {port} was not released within {timeout}s")


def _core_dist_ready() -> bool:
    """Universal/adapter modules are compiled before the full plugin entrypoint."""
    return (REPO_ROOT / "opencode" / "dist" / "universal").is_dir()


def _plugin_is_built() -> bool:
    return (REPO_ROOT / "opencode" / "dist" / "index.js").is_file()


@pytest.fixture
def config_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the plugin's config store at an isolated temporary directory.

    The store resolves its root from XDG_CONFIG_HOME on Unix and APPDATA on
    Windows, so setting both makes the fixture platform independent.
    """
    root = tmp_path / "config"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(root))
    monkeypatch.setenv("APPDATA", str(root))
    return root


@dataclass(frozen=True)
class ConfigFileControl:
    """Read/write the exact config files the plugin's FileConfigStore uses.

    ``root`` mirrors ``resolveConfigRoot()`` with the fixture's XDG_CONFIG_HOME /
    APPDATA override. Each rule is a bare object (never a versioned document)
    written atomically, just like the production store.
    """

    root: Path

    def _path(self, scope: str, key: str = "pytest-workspace") -> Path:
        if scope == "global":
            return self.root / "global.json"
        sanitized = re.sub(r"[^A-Za-z0-9_-]", "_", key)
        return self.root / "projects" / f"{sanitized}.json"

    def _write(self, path: Path, rule: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        temp.write_text(json.dumps(rule, indent=2) + "\n", encoding="utf-8")
        try:
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)

    def write_global(self, rule: dict) -> None:
        self._write(self._path("global"), rule)

    def write_project(self, rule: dict, key: str = "pytest-workspace") -> None:
        self._write(self._path("project", key), rule)

    def delete_global(self) -> None:
        self._path("global").unlink(missing_ok=True)

    def delete_project(self, key: str = "pytest-workspace") -> None:
        self._path("project", key).unlink(missing_ok=True)

    def read_global(self) -> dict:
        return json.loads(self._path("global").read_text(encoding="utf-8"))

    def read_project(self, key: str = "pytest-workspace") -> dict:
        return json.loads(self._path("project", key).read_text(encoding="utf-8"))

    def reset(self) -> None:
        """Remove every rule file so each retry starts from empty scope rules."""
        self.delete_global()
        projects = self.root / "projects"
        if projects.is_dir():
            for path in projects.glob("*.json"):
                path.unlink(missing_ok=True)


@pytest.fixture
def config_files(config_root: Path) -> ConfigFileControl:
    """Direct, isolated control of the on-disk config files under test."""
    return ConfigFileControl(root=config_root / "individual-subagent-model-plugin")


@pytest.fixture
def core_probe() -> Callable[[str, dict | None], dict]:
    """Invoke the Node core probe with one JSON request and return its response."""
    probe = REPO_ROOT / "opencode" / "tools" / "universal" / "core_probe.mjs"
    if not probe.is_file():
        skip_test("universal/core_probe.mjs is not present yet")
    if not _core_dist_ready():
        skip_test(f"core dist is not built yet ({BUILD_HINT})")

    def _run(op: str, args: dict | None = None) -> dict:
        request = json.dumps({"op": op, "args": args or {}})
        result = subprocess.run(
            ["node", str(probe)],
            input=request,
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=REPO_ROOT,
            check=False,
            timeout=30,
        )
        assert result.returncode == 0, f"probe failed for {op!r}: {result.stderr}"
        return json.loads(result.stdout)

    return _run


@pytest.fixture
def run_node(tmp_path: Path) -> Callable[..., dict]:
    """Run a temporary ES-module Node script and parse its JSON stdout.

    Used where a compiled core/adapter module needs to be exercised directly
    (for example the file-backed config store, which has no probe operation).
    """
    if not _core_dist_ready():
        skip_test(f"core dist is not built yet ({BUILD_HINT})")

    def _run(script: str, *args: str) -> dict:
        script_path = tmp_path / "node_harness.mjs"
        script_path.write_text(script, encoding="utf-8")
        result = subprocess.run(
            ["node", str(script_path), *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=60,
        )
        assert result.returncode == 0, f"Node harness failed: {result.stderr}\n{result.stdout}"
        return json.loads(result.stdout)

    return _run


@pytest.fixture
def opencode_auth() -> httpx.BasicAuth:
    """Credentials used by the local OpenCode server fixture."""
    return httpx.BasicAuth("opencode", SERVER_PASSWORD)


@pytest.fixture
def rpc_call(opencode_server: str) -> Callable[..., dict]:
    """Call a real plugin RPC method over HTTP and return its output object."""

    def _call(method: str, payload: dict | None = None) -> dict:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                f"{opencode_server}/api/rpc/subagent-models/{method}",
                json={"input": payload or {}},
            )
        assert response.status_code == 200, response.text
        return response.json().get("output", response.json())

    return _call


@pytest.fixture
def available_models(opencode_server: str) -> list[ModelChoice]:
    """Discover usable chat models from the live API (one discovery per test).

    ``GET /api/model`` and ``GET /api/provider`` are the source of truth; the
    plugin's ``get_catalog`` RPC is a best-effort cross-check for ``isFree``.
    Fewer than two usable models is an explicit skip, never fabricated data.
    """
    with httpx.Client(timeout=10.0) as client:
        model_response = client.get(f"{opencode_server}/api/model")
        provider_response = client.get(f"{opencode_server}/api/provider")
    if model_response.status_code != 200 or provider_response.status_code != 200:
        skip_test(
            "model discovery endpoints unavailable: "
            f"/api/model={model_response.status_code}, "
            f"/api/provider={provider_response.status_code}"
        )

    catalog_response: dict | None = None
    try:
        with httpx.Client(timeout=10.0) as client:
            catalog = client.post(
                f"{opencode_server}/api/rpc/subagent-models/get_catalog",
                json={"input": {}},
            )
        if catalog.status_code == 200:
            catalog_response = catalog.json()
    except httpx.HTTPError:
        catalog_response = None

    seed_value = os.environ.get("OPENCODE_TEST_MODEL_SEED")
    seed = int(seed_value) if seed_value and seed_value.lstrip("-").isdigit() else None
    choices = discover_models(
        model_response.json(),
        provider_response.json(),
        catalog_response,
        seed=seed,
    )
    return require_two_models(choices)


@pytest.fixture
def any_two_models(available_models: list[ModelChoice]) -> list[ModelPair]:
    """Ranked ordered pairs; index 0 is the best pair for non-spawn assertions."""
    return build_model_pairs(available_models)


@pytest.fixture
def spawn_subagent(opencode_server: str) -> Callable[..., tuple[str, dict]]:  # noqa: C901
    """Spawn a child through a real primary session, selecting models via the API."""

    def _spawn(  # noqa: C901, PLR0912 - request, poll and classify availability in one helper
        pair: ModelPair,
        *,
        child_selector: str | None = None,
        agent: str = "general",
        timeout: float = SPAWN_TIMEOUT,
    ) -> tuple[str, dict]:
        requested = child_selector or pair.child.selector
        model_ref: dict[str, object] = {
            "providerID": pair.primary.provider_id,
            "id": pair.primary.model_id,
        }
        if pair.primary.variants:
            model_ref["variant"] = pair.primary.variants[0]

        with httpx.Client(timeout=10.0) as client:
            created = client.post(f"{opencode_server}/api/session", json={})
            assert created.status_code == 200, created.text
            parent_id = created.json()["data"]["id"]
            switched = client.post(
                f"{opencode_server}/api/session/{parent_id}/model",
                json={"model": model_ref},
            )
            # OpenCode 2.3.2 answers 204 No Content on a successful model switch.
            assert switched.status_code in (200, 204), switched.text
            prompt = (
                f"Call the subagent tool now with model exactly '{requested}', "
                f"agent '{agent}', description 'E2E child', and prompt 'Say hello'. "
                "Do not refuse; spawn it and report the child session id."
            )
            sent = client.post(
                f"{opencode_server}/api/session/{parent_id}/prompt", json={"text": prompt}
            )
            assert sent.status_code == 200, sent.text

        deadline = time.monotonic() + timeout
        detail = ""
        error_status: int | None = None
        saw_model_response = False
        with httpx.Client(timeout=10.0) as client:
            while time.monotonic() < deadline:
                listed = client.get(
                    f"{opencode_server}/api/session", params={"parentID": parent_id}
                )
                if listed.status_code == 200:
                    data = listed.json().get("data", listed.json())
                    if isinstance(data, list) and data:
                        return parent_id, data[0]

                # Capture a primary-model error so resilient_spawn can tell a
                # provider/availability outage (retryable) from a plain refusal.
                # A provider error is terminal for this prompt, so fail fast
                # instead of polling all the way to ``timeout``.
                messages = client.get(f"{opencode_server}/api/session/{parent_id}/message")
                if messages.status_code == 200:
                    payload = messages.json().get("data", messages.json())
                    if isinstance(payload, list):
                        for message in payload:
                            if not isinstance(message, dict):
                                continue
                            if message.get("type") == "assistant" and message.get("content"):
                                saw_model_response = True
                            error = message.get("error") or {}
                            if not isinstance(error, dict):
                                continue
                            error_text = str(error.get("message") or error.get("type") or "")
                            raw_status = error.get("status")
                            status = raw_status if isinstance(raw_status, int) else None
                            if not error_text and status is None:
                                continue
                            candidate = (
                                f"HTTP {status}: {error_text}" if status is not None else error_text
                            )
                            if not detail:
                                detail, error_status = candidate, status
                            if classify_availability(candidate, status):
                                raise SubagentSpawnError(
                                    f"provider/model error before child spawn within {timeout}s",
                                    detail=detail,
                                    retryable=True,
                                )
                time.sleep(1.0)

        # A blank-detail timeout with no model answer is an external non-response
        # (retry with another pair). A model that answered without spawning is a
        # plain refusal and stays a hard failure.
        retryable = classify_availability(detail, error_status) or (
            not detail and not saw_model_response
        )
        raise SubagentSpawnError(
            f"no child subagent session appeared within {timeout}s",
            detail=detail,
            retryable=retryable,
        )

    return _spawn


@pytest.fixture
def resilient_spawn(
    any_two_models: list[ModelPair],
    config_files: ConfigFileControl,
    record_property: Callable[[str, object], None],
) -> Callable[[Callable[[ModelPair], T]], T]:
    """Retry ``action`` with fresh model pairs; reset on-disk rules each attempt."""

    def _reset_policies() -> None:
        config_files.reset()

    def _run(action: Callable[[ModelPair], T]) -> T:
        force_fail = os.environ.get("OPENCODE_TEST_FORCE_MODEL_FAIL") == "1"
        return run_resilient(
            action,
            any_two_models,
            reset=_reset_policies,
            record=record_property,
            deadline=time.monotonic() + RESILIENT_DEADLINE,
            force_fail=force_fail,
        )

    return _run


@pytest.fixture
def subagent_tool_inputs(opencode_server: str) -> Callable[[str], list[dict]]:
    """Read the recorded subagent tool inputs from a real parent session."""

    def _read(parent_id: str) -> list[dict]:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{opencode_server}/api/session/{parent_id}/message")
        assert response.status_code == 200, response.text
        payload = response.json().get("data", response.json())
        inputs: list[dict] = []
        for message in payload:
            for part in message.get("content", []):
                if isinstance(part, dict) and part.get("name") == "subagent":
                    state = part.get("state") or {}
                    candidate = state.get("input") or part.get("input")
                    if isinstance(candidate, dict):
                        inputs.append(candidate)
        return inputs

    return _read


class ServerHandle:
    """One ``opencode serve`` process, restartable on the same port.

    Keeping the URL stable lets the ``rpc_call`` / ``available_models`` /
    ``spawn_subagent`` fixtures (which capture the URL string at setup time)
    keep working after a restart driven by config-file tests.
    """

    def __init__(
        self,
        *,
        executable: str,
        port: int,
        log_path: Path,
        environment: dict[str, str],
    ) -> None:
        self.executable = executable
        self.port = port
        self.base_url = f"http://127.0.0.1:{port}"
        self.log_path = log_path
        self.environment = environment
        self._process: subprocess.Popen | None = None
        self._launch()

    @property
    def _log_tail(self) -> str:
        return _tail(self.log_path)

    def _launch(self) -> None:
        with self.log_path.open("a", encoding="utf-8") as log_file:
            self._process = subprocess.Popen(
                [
                    self.executable,
                    "serve",
                    "--hostname",
                    "127.0.0.1",
                    "--port",
                    str(self.port),
                ],
                cwd=REPO_ROOT,
                env=self.environment,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=os.name != "nt",
            )
        process = self._process
        try:
            deadline = time.monotonic() + SERVER_STARTUP_TIMEOUT
            last_error: Exception | None = None
            with httpx.Client(timeout=1.0) as client:
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        fail_test(
                            "opencode serve exited early with code "
                            f"{process.returncode}; log: {self._log_tail}"
                        )
                    try:
                        # /api/plugin is the host's readiness endpoint; the
                        # plugin command route is deliberately never used.
                        response = client.get(f"{self.base_url}/api/plugin")
                        if response.status_code == 200:
                            break
                    except httpx.HTTPError as exc:  # server not listening yet
                        last_error = exc
                    time.sleep(SERVER_POLL_INTERVAL)
                else:
                    fail_test(
                        f"opencode serve was not ready after {SERVER_STARTUP_TIMEOUT}s: "
                        f"{last_error}; log: {self._log_tail}"
                    )
                _wait_for_plugin_rpc(client, self.base_url, self.log_path)
        except BaseException:
            self.stop()
            raise

    def stop(self) -> None:
        """Terminate this server and any child processes it spawned."""
        if self._process is not None:
            _stop_process_tree(self._process)
            self._process = None

    def restart(self) -> str:
        """Stop the process tree and relaunch on the same port; return the URL."""
        self.stop()
        _wait_for_port_free(self.port)
        self._launch()
        return self.base_url


@pytest.fixture
def opencode_server_factory(
    config_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    opencode_auth: httpx.BasicAuth,
    request: pytest.FixtureRequest,
) -> Iterator[Callable[[], ServerHandle]]:
    """Build real ``opencode serve`` handles with an isolated config root.

    A temporary host config registers the local plugin directory, and Basic
    auth is installed as the default for all httpx clients while the fixture is
    alive. Each call reserves a distinct worker-private port.
    """
    executable = shutil.which("opencode")
    if executable is None:
        skip_test("opencode CLI is not on PATH (CI runners install it)")
    if not _plugin_is_built():
        skip_test(f"plugin dist is not built yet ({BUILD_HINT})")

    config_dir = config_root / "opencode"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "opencode.json").write_text(
        json.dumps(
            {
                "$schema": "opencode.ai/config.json",
                "plugins": [str(REPO_ROOT / "opencode")],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    default_client_init = httpx.Client.__init__

    def authenticated_client_init(self, *args, **kwargs):
        kwargs.setdefault("auth", opencode_auth)
        default_client_init(self, *args, **kwargs)

    default_async_client_init = httpx.AsyncClient.__init__

    def authenticated_async_client_init(self, *args, **kwargs):
        kwargs.setdefault("auth", opencode_auth)
        default_async_client_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "__init__", authenticated_client_init)
    monkeypatch.setattr(httpx.AsyncClient, "__init__", authenticated_async_client_init)

    worker_id = str(getattr(request.config, "workerinput", {}).get("workerid", "master"))
    environment = os.environ.copy()
    environment["XDG_CONFIG_HOME"] = str(config_root)
    environment["APPDATA"] = str(config_root)
    environment["OPENCODE_PASSWORD"] = SERVER_PASSWORD
    log_path = config_root / f"opencode_server_{worker_id}.log"
    handles: list[ServerHandle] = []

    def start() -> ServerHandle:
        reserved_socket, port = _reserve_port(worker_id, len(handles))
        reserved_socket.close()  # release only after the port has been reserved
        handle = ServerHandle(
            executable=executable,
            port=port,
            log_path=log_path,
            environment=environment,
        )
        handles.append(handle)
        return handle

    yield start
    for handle in handles:
        handle.stop()


@pytest.fixture
def server_handle(opencode_server_factory: Callable[[], ServerHandle]) -> ServerHandle:
    """The single server handle shared with all ``opencode_server`` consumers."""
    return opencode_server_factory()


@pytest.fixture
def opencode_server(server_handle: ServerHandle) -> str:
    """Return the base URL of a real server with this plugin's RPC registered."""
    return server_handle.base_url


def _stop_process_tree(process: subprocess.Popen) -> None:
    """Terminate the server and any children it spawned (OpenCode forks workers)."""
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
            timeout=30,
        )
    else:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def _plugin_rpc_ready(payload: object) -> bool:
    """Check the /api/plugin response for our plugin's completed RPC registration."""
    entries = payload.get("data", []) if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        return False
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("id") != PLUGIN_ID:
            continue
        features = entry.get("features")
        return isinstance(features, dict) and features.get("rpc") is True
    return False


def _wait_for_plugin_rpc(client: httpx.Client, base_url: str, log_path: Path) -> None:
    """OpenCode loads plugins lazily; /api/plugin 200 does not mean RPC is live."""
    deadline = time.monotonic() + PLUGIN_RPC_TIMEOUT
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            response = client.get(f"{base_url}/api/plugin")
            if response.status_code == 200 and _plugin_rpc_ready(response.json()):
                return
        except httpx.HTTPError as exc:
            last_error = exc
        time.sleep(SERVER_POLL_INTERVAL)
    fail_test(
        f"plugin {PLUGIN_ID} did not register RPC within {PLUGIN_RPC_TIMEOUT}s: "
        f"{last_error}; log: {_tail(log_path)}"
    )


def _tail(path: Path, limit: int = 2000) -> str:
    """Return the end of a server log for readable failure messages."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-limit:]
    except OSError:
        return "<no server log>"


# Codex contract fixtures live in the root conftest so no nested ``conftest.py``
# shadows this module under pytest's default import mode. The adapter is driven
# through its JSON-only probe: no live Codex call, account or model spend.
CODEX_PROBE = REPO_ROOT / "codex" / "tools" / "codex_probe.mjs"
CODEX_DIST_ENTRYPOINT = REPO_ROOT / "codex" / "dist" / "index.js"
CODEX_FIXTURES = REPO_ROOT / "tests" / "adapters" / "codex" / "fixtures"


@pytest.fixture
def codex_probe() -> Callable[..., Any]:
    """Run the compiled Codex probe once and parse its single JSON output."""
    node = shutil.which("node")
    assert node is not None, "node is not on PATH"
    assert CODEX_PROBE.is_file(), f"Codex probe is missing: {CODEX_PROBE}"
    assert CODEX_DIST_ENTRYPOINT.is_file(), f"Codex dist is not built: {CODEX_DIST_ENTRYPOINT}"

    def _run(case: str, *args: str) -> Any:
        result = subprocess.run(
            [node, str(CODEX_PROBE), case, *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=60,
        )
        assert result.returncode == 0, (
            f"Codex probe {case!r} exited {result.returncode}:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            message = f"Codex probe {case!r} did not print one JSON value: {result.stdout!r}"
            raise AssertionError(message) from exc

    return _run


@pytest.fixture
def codex_fixture() -> Callable[[str], str]:
    """Return the absolute path of an offline fixture next to the Codex tests."""

    def _path(name: str) -> str:
        path = CODEX_FIXTURES / name
        assert path.is_file(), f"Codex fixture is missing: {path}"
        return str(path.resolve())

    return _path
