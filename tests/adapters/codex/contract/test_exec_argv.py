"""``codex exec`` argv shape: fixed order, no shell string, no secret leakage."""

from __future__ import annotations

import re

import pytest

pytestmark = [pytest.mark.contract, pytest.mark.codex_cli]

EXPECTED_ARGV = [
    "exec",
    "--json",
    "-m",
    "my-model",
    "-c",
    'model_provider="myrouter"',
    "hi",
]
SECRET_VALUE = re.compile(r"\b(?:sk|rk|gh[pousr])-[A-Za-z0-9_-]{8,}\b")
SHELL_META = ("&&", "||", ";", "|", ">", "<", "$(", "`", "\n", "\r", "\0")


def test_exec_argv_is_exact(codex_probe) -> None:
    assert codex_probe("exec-args") == EXPECTED_ARGV


def test_exec_argv_has_no_shell_metacharacters_or_secrets(codex_probe) -> None:
    argv = codex_probe("exec-args")
    assert argv == EXPECTED_ARGV  # non-vacuous: the shape is pinned first
    assert all(isinstance(arg, str) for arg in argv)

    joined = " ".join(argv)
    for token in SHELL_META:
        assert token not in joined, f"shell metacharacter {token!r} leaked into argv: {argv}"
    assert SECRET_VALUE.search(joined) is None, "a secret-looking value leaked into argv"

    # The provider override is a quoted TOML value passed as one argv element,
    # never a shell command line.
    assert 'model_provider="myrouter"' in argv
    assert argv[-1] == "hi", "the prompt must be the last argv element"
