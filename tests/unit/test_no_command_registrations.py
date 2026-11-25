"""Positive proof that no command/UI contribution survives the removal.

The companion static guard (``scripts/ci/check_no_commands.py``) scans both the
TypeScript source and the generated ``dist`` bundles. These tests run that guard
and add independent, regex-only second passes so deleting an old command test
can never silently reintroduce a command contract.

Pure/static and xdist-safe: no server, no npm, no network.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "scripts" / "ci" / "check_no_commands.py"
OPENCODE = REPO_ROOT / "opencode"
TOOLS = OPENCODE / "tools"
DIST = OPENCODE / "dist"
UNIVERSAL = REPO_ROOT / "universal"

BANNED_PROBES = (
    "tui_command_registration_probe.mjs",
    "palette_section_probe.mjs",
    "model_picker_interaction_probe.mjs",
    "model_picker_probe.mjs",
    "picker_slot_color_probe.mjs",
    "gui_command_registration_probe.mjs",
)
BANNED_TOKENS = (
    "keymap.layer(",
    "registerCommands",
    "context.keymap",
    "ctx.command",
    "command.register",
    "slash:",
    "palette: true",
    "ctx.add(Command",
    "subagent-models-allowed",
    "subagent-models-allowed-global",
    "PROJECT_COMMAND_ID",
    "GLOBAL_COMMAND_ID",
    "allowed-global",
)
DIST_PATTERNS = (
    re.compile(r"keymap\s*\.\s*layer\s*\("),
    re.compile(r"\bpalette\s*:\s*true\b"),
    re.compile(r"\bslash\s*:"),
    re.compile(r"\bctx\s*\.\s*add\s*\(\s*Command\b"),
    re.compile(r"subagent-models-allowed(?:-global)?"),
    re.compile(r"\b(?:PROJECT|GLOBAL)_COMMAND_ID\b"),
    re.compile(r"\ballowed-global\b"),
)
SCAN_LOCATIONS = (
    *sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml")),
    REPO_ROOT / "scripts" / "run_tests.sh",
    REPO_ROOT / "scripts" / "run_tests.ps1",
    *sorted((REPO_ROOT / "scripts" / "ci").glob("*.py")),
)
# The checker necessarily contains the banned names in its own rule tables.
CHECKER_SOURCE = CHECKER.resolve()


def _run_checker() -> dict:
    assert CHECKER.is_file(), f"zero-command guard is missing: {CHECKER}"
    result = subprocess.run(
        [sys.executable, str(CHECKER)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    report = json.loads(result.stdout)
    assert result.returncode == 0, f"zero-command guard failed: {report}"
    return report


def test_no_command_registrations_in_source_or_dist() -> None:
    report = _run_checker()
    assert report["ok"] is True, report
    assert report["matches"] == [], report
    assert report["failures"] == [], report


def test_no_command_tokens_in_moved_universal_source() -> None:
    assert UNIVERSAL.is_dir(), "universal source tree is missing"
    hits: list[str] = []
    for path in sorted(UNIVERSAL.rglob("*.ts")) + sorted(UNIVERSAL.rglob("*.tsx")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            hits.extend(
                f"{path.relative_to(REPO_ROOT)}:{number}: {token}"
                for token in BANNED_TOKENS
                if token in line
            )
    assert hits == [], "command contract leaked into universal source:\n" + "\n".join(hits)


def test_command_probe_scripts_are_absent() -> None:
    present = sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in TOOLS.rglob("*.mjs")
        if path.name in BANNED_PROBES
    )
    assert present == [], f"deleted command/UI probes are still present: {present}"


def test_ci_and_runners_do_not_reference_command_probes() -> None:
    hits: list[str] = []
    for path in SCAN_LOCATIONS:
        if not path.is_file() or path.resolve() == CHECKER_SOURCE:
            continue
        text = path.read_text(encoding="utf-8")
        hits.extend(
            f"{path.relative_to(REPO_ROOT).as_posix()}: {token}"
            for token in (*BANNED_PROBES, *BANNED_TOKENS)
            if token in text
        )
    assert hits == [], "stale command/probe reference in CI or a runner:\n" + "\n".join(hits)


def test_no_palette_or_slash_contract_in_dist() -> None:
    assert DIST.is_dir(), "dist is not built (run npm run build --prefix opencode)"
    hits: list[str] = []
    for path in sorted(DIST.rglob("*.js")):
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), start=1):
            hits.extend(
                f"{path.relative_to(REPO_ROOT).as_posix()}:{number}: {pattern.pattern}"
                for pattern in DIST_PATTERNS
                if pattern.search(line)
            )
    assert hits == [], "command contract survived compilation:\n" + "\n".join(hits)
