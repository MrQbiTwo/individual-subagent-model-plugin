"""Static contract for the generated-release-notes REST endpoint in publish.yml.

Release run ``45778570666`` failed in ``create-github-release`` with
``gh: Not Found (HTTP 404)`` because the render step called
``repos/$GH_REPO/generate-notes`` instead of the real REST route
``POST /repos/{owner}/{repo}/releases/generate-notes``. This module reads the
workflow as text (no PyYAML needed) and pins the endpoint, the explicit HTTP
method and the required request fields so that 404 cannot regress.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

PUBLISH = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "publish.yml"

# The only valid route for GitHub's generated release notes.
ENDPOINT = "repos/$GH_REPO/releases/generate-notes"
# The invalid bare endpoint that produced HTTP 404 in run 45778570666.
BARE_ENDPOINT = re.compile(r"repos/\$GH_REPO/generate-notes\b")
# Any /generate-notes segment not immediately following /releases.
BARE_SEGMENT = re.compile(r"(?<!releases)/generate-notes\b")
JOB_HEADING = re.compile(r"^  [A-Za-z_][A-Za-z0-9_-]*:\s*$")
STEP_HEADING = re.compile(r"^      - name:\s")
RENDER_STEP = "      - name: Render the release body from the template"


def _release_job() -> str:
    assert PUBLISH.is_file(), f"{PUBLISH} is missing"
    lines = PUBLISH.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.strip() != "create-github-release:" or not line.startswith("  "):
            continue
        collected = [line]
        for following in lines[index + 1 :]:
            if JOB_HEADING.match(following):
                break
            collected.append(following)
        return "\n".join(collected)
    raise AssertionError("create-github-release job is missing from publish.yml")


def _render_step(job: str) -> str:
    lines = job.splitlines()
    for index, line in enumerate(lines):
        if line != RENDER_STEP:
            continue
        collected = [line]
        for following in lines[index + 1 :]:
            if STEP_HEADING.match(following):
                break
            collected.append(following)
        return "\n".join(collected)
    raise AssertionError("render step is missing from the release job")


def test_generated_notes_endpoint_includes_releases_segment() -> None:
    """The render step must call the /releases/generate-notes REST route."""
    step = _render_step(_release_job())
    assert ENDPOINT in step, "expected POST /repos/{owner}/{repo}/releases/generate-notes"


def test_no_bare_generate_notes_endpoint() -> None:
    """No /generate-notes segment may appear without the /releases prefix."""
    step = _render_step(_release_job())
    assert BARE_ENDPOINT.search(step) is None, "bare repos/$GH_REPO/generate-notes endpoint present"
    assert BARE_SEGMENT.search(step) is None, "bare /generate-notes segment present"


def test_generated_notes_request_uses_post_explicitly() -> None:
    """gh api must send POST explicitly rather than relying on -f inference."""
    step = _render_step(_release_job())
    assert re.search(r"gh api\s+[^\n]*-X POST", step) is not None, "request must use -X POST"


def test_generated_notes_request_keeps_required_fields() -> None:
    """tag_name, optional previous_tag_name and --jq .body must be preserved."""
    step = _render_step(_release_job())
    assert '-f tag_name="$REF"' in step
    assert '-f previous_tag_name="$previous"' in step
    assert "--jq .body" in step
