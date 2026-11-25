"""Static branding audit for the "Individual Subagent Model" display name.

Runs from any working directory; all paths resolve from this file. Emits a
single JSON object on stdout: ``{"ok": bool, "checks": [...], "failures": [...]}``.
A non-zero exit status means at least one branding contract is broken.

The technical ``Plugin.define`` server id stays stable while user-facing
strings use the display name, so both halves are checked here.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DISPLAY = "Individual Subagent Model"
TECHNICAL = (
    "individual-subagent-model-plugin",
    "opencode-individual-subagent-model-plugin",
)
SERVER_ID = "individual-subagent-model-plugin"

_FENCE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_URL = re.compile(r"https?://[^\s)>]+")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def _read(relative: str) -> str:
    path = REPO_ROOT / relative
    if not path.is_file():
        raise AssertionError(f"missing file: {relative}")
    return path.read_text(encoding="utf-8")


def _prose(markdown: str) -> str:
    """Strip technical contexts so only user-facing prose remains."""
    markdown = _HTML_COMMENT.sub("", markdown)
    markdown = _FENCE.sub("", markdown)
    markdown = _INLINE_CODE.sub("", markdown)
    return _URL.sub("", markdown)


def _check_readme() -> None:
    readme = _read("README.md")
    non_blank = [line for line in readme.splitlines() if line.strip()]
    assert non_blank[5] == f"# {DISPLAY}", "README H1 must use the display name"
    prose = _prose(readme)
    assert DISPLAY in prose, "README prose must use the display name"
    for token in TECHNICAL:
        assert token not in prose, f"technical id in README prose: {token}"


def _check_contributing() -> None:
    prose = _prose(_read("CONTRIBUTING.md"))
    assert DISPLAY in prose, "CONTRIBUTING prose must use the display name"
    for token in TECHNICAL:
        assert token not in prose, f"technical id in CONTRIBUTING prose: {token}"


def _check_server_id() -> None:
    assert f'id: "{SERVER_ID}"' in _read(
        "opencode/src/adapters/opencode_cli/server.ts"
    ), "server Plugin.define id changed (host identity is stable)"


def _check_no_effort() -> None:
    """Verify that removed presentation-copy files stay absent."""
    for relative in (
        "opencode/src/adapters/opencode_cli/tui/allowlist_view.tsx",
        "opencode/dist/adapters/opencode_cli/tui/allowlist_view.js",
        "opencode/dist/adapters/opencode_cli/tui/commands.js",
    ):
        assert not (REPO_ROOT / relative).exists(), (
            f"removed UI copy file survived: {relative}"
        )


CHECKS: tuple[tuple[str, Callable[[], None]], ...] = (
    ("readme_display_name", _check_readme),
    ("contributing_display_name", _check_contributing),
    ("server_plugin_id_unchanged", _check_server_id),
    ("no_effort_in_user_facing_copy", _check_no_effort),
)


def main() -> int:
    failures: list[str] = []
    passed: list[str] = []
    for name, check in CHECKS:
        try:
            check()
        except (AssertionError, IndexError, OSError, UnicodeDecodeError) as error:
            failures.append(f"{name}: {error}")
        else:
            passed.append(name)
    payload = {"ok": not failures, "checks": passed, "failures": failures}
    print(json.dumps(payload))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
