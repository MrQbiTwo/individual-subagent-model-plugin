"""Audit repository sources for platform-subsystem coupling.

The plugin, its scripts and its tests must run natively on Linux, macOS and
Windows. This test fails if any tracked-looking source file contains a path,
environment variable or executable tied to a Linux compatibility layer.

The forbidden tokens are assembled at runtime so that this audit file does not
trip its own scan. The file itself is skipped explicitly as a second safeguard.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]

# Only directories inside REPO_ROOT are scanned; no external sibling needs an exclusion.
EXCLUDED_DIRS = {
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "dist",
    "node_modules",
    "reports",
}

TEXT_SUFFIXES = {
    "",
    ".cfg",
    ".gitignore",
    ".ini",
    ".js",
    ".json",
    ".jsonc",
    ".md",
    ".mjs",
    ".npmrc",
    ".ps1",
    ".py",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}

# Built from pieces so the literals do not appear in this file's own source.
FORBIDDEN_LITERALS = (
    "/" + "mnt" + "/",
    "wsl" + chr(46) + "exe",
    "wsl" + "path",
    "WSL" + chr(95) + "DISTRO_NAME",
    "WSL" + chr(95) + "ENV",
)
FORBIDDEN_PATTERN = re.compile(r"\bWSL" + chr(95) + r"[A-Z]")


def _source_files() -> list[Path]:
    files: list[Path] = []
    self_path = Path(__file__).resolve()
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in EXCLUDED_DIRS for part in path.relative_to(REPO_ROOT).parts):
            continue
        if path.resolve() == self_path:
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        files.append(path)
    return files


def test_no_platform_subsystem_tokens_in_sources() -> None:
    violations: list[str] = []
    for path in _source_files():
        try:
            text = path.read_text(encoding="utf-8", errors="strict")
        except (OSError, UnicodeDecodeError):
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            violations.extend(
                f"{path.relative_to(REPO_ROOT)}:{line_number}: literal {token!r}"
                for token in FORBIDDEN_LITERALS
                if token in line
            )
            match = FORBIDDEN_PATTERN.search(line)
            if match is not None:
                violations.append(
                    f"{path.relative_to(REPO_ROOT)}:{line_number}: pattern {match.group()!r}"
                )
    assert violations == [], "repository has platform-subsystem coupling:\n" + "\n".join(violations)


def test_runners_are_native_scripts() -> None:
    bash_runner = REPO_ROOT / "scripts" / "run_tests.sh"
    powershell_runner = REPO_ROOT / "scripts" / "run_tests.ps1"

    assert bash_runner.is_file(), "native Bash runner is missing"
    assert powershell_runner.is_file(), "native PowerShell runner is missing"

    bash_text = bash_runner.read_text(encoding="utf-8")
    powershell_text = powershell_runner.read_text(encoding="utf-8")

    assert bash_text.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in bash_text
    assert "python3" in bash_text
    assert "pwsh" in powershell_text or "python" in powershell_text
