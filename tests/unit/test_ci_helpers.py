"""Contracts for the CI helper scripts implemented by the automation task.

These tests are skipped while the helper modules do not exist yet and become
active as soon as ``scripts/ci/semver.py`` and ``scripts/ci/update_issue.py``
are added. No GitHub token or network access is needed here.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

semver = pytest.importorskip(
    "scripts.ci.semver",
    reason="CI helper scripts are added by the automation task",
)
update_issue = pytest.importorskip(
    "scripts.ci.update_issue",
    reason="CI helper scripts are added by the automation task",
)


def test_semver_compare_numeric_not_lexicographic() -> None:
    assert semver.compare("2.3.2", "2.3.10") < 0
    assert semver.compare("2.10.0", "2.3.10") > 0
    assert semver.compare("2.3.2", "2.3.2") == 0


def test_semver_is_valid() -> None:
    assert semver.is_valid("1.2.3") is True
    assert semver.is_valid("v1.2.3") is False
    assert semver.is_valid("01.2.3") is False
    assert semver.is_valid("1.2") is False


def test_semver_from_tag() -> None:
    assert semver.from_tag("v2.3.2") == "2.3.2"
    assert semver.from_tag("2.3.2") == "2.3.2"


def test_build_body_contains_context() -> None:
    body = update_issue.build_body(os="windows-11-arm", run_url="http://x")
    assert "windows-11-arm" in body
    assert "http://x" in body


def test_choose_action() -> None:
    assert update_issue.choose_action(existing_number=None) == "create"
    assert update_issue.choose_action(existing_number=7) == "edit"
