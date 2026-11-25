"""Contracts for the Advanced CodeQL workflow.

CodeQL has a fixed set of analysis languages; ``bash`` is not one of them.
These tests parse ``.github/workflows/codeql.yml`` and pin the language matrix,
the triggers and the supply-chain baseline so an unsupported language cannot
silently reappear and break ``Initialize CodeQL`` again.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
CODEQL = REPO_ROOT / ".github" / "workflows" / "codeql.yml"

# The complete set of CodeQL languages this repository analyses. PowerShell is
# handled by the platform suite, not by CodeQL.
SUPPORTED_LANGUAGES = frozenset({"javascript-typescript", "python", "actions"})
# Languages that are either unsupported by CodeQL or out of scope here. In
# particular CodeQL rejects ``bash`` at the ``init`` step with
# "Did not recognize the following languages: bash".
UNSUPPORTED_LANGUAGES = frozenset(
    {"bash", "shell", "sh", "powershell", "css", "html", "ruby", "go", "java"}
)
V4_INIT_SHA = "1bd86f2fdb4b86187fa4059f16f31a3202acc9ea"


def _workflow():
    assert CODEQL.is_file(), f"{CODEQL} is missing"
    data = yaml.safe_load(CODEQL.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    # PyYAML resolves the bare YAML 1.1 key ``on`` to the boolean True.
    if True in data:
        data["on"] = data.pop(True)
    return data


def _matrix(workflow):
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    analyze = jobs["analyze"]
    assert isinstance(analyze, dict)
    strategy = analyze["strategy"]
    assert isinstance(strategy, dict)
    matrix = strategy["matrix"]
    assert isinstance(matrix, dict)
    include = matrix["include"]
    assert isinstance(include, list)
    return include


def _languages(workflow) -> list[str]:
    return [entry["language"] for entry in _matrix(workflow)]


def test_codeql_matrix_uses_exactly_supported_languages() -> None:
    languages = _languages(_workflow())
    assert set(languages) == SUPPORTED_LANGUAGES, (
        f"CodeQL matrix must be exactly {sorted(SUPPORTED_LANGUAGES)}, got {languages}"
    )
    assert len(languages) == len(SUPPORTED_LANGUAGES), "duplicate language in CodeQL matrix"


def test_codeql_matrix_has_no_unsupported_languages() -> None:
    languages = set(_languages(_workflow()))
    assert languages.isdisjoint(UNSUPPORTED_LANGUAGES), (
        f"unsupported CodeQL languages configured: {sorted(languages & UNSUPPORTED_LANGUAGES)}"
    )
    assert "bash" not in languages, "CodeQL does not support bash as an analysis language"


def test_codeql_matrix_entries_are_none_build_mode() -> None:
    for entry in _matrix(_workflow()):
        assert entry["build-mode"] == "none", f"unexpected build mode for {entry['language']}"


def test_codeql_workflow_triggers_are_preserved() -> None:
    triggers = _workflow()["on"]
    assert triggers["push"]["branches"] == ["main"]
    assert triggers["pull_request"]["branches"] == ["main"]
    assert triggers["schedule"] == [{"cron": "27 5 * * 3"}]


def test_codeql_workflow_uses_pinned_v4_actions_and_write_permissions() -> None:
    workflow = _workflow()
    assert workflow["permissions"] == {}
    job = workflow["jobs"]["analyze"]
    assert job["permissions"]["security-events"] == "write"
    steps = job["steps"]
    init = next(step for step in steps if step["name"] == "Initialize CodeQL")
    analyze = next(step for step in steps if step["name"] == "Perform CodeQL analysis")
    assert init["uses"] == f"github/codeql-action/init@{V4_INIT_SHA}"
    assert analyze["uses"] == f"github/codeql-action/analyze@{V4_INIT_SHA}"
    for step in steps:
        assert re.search(r"@[0-9a-f]{40}$", step["uses"]), (
            f"action is not SHA-pinned: {step['uses']}"
        )
