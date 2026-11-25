#!/usr/bin/env python3
"""Idempotent GitHub failure-tracker helper used by the CI workflows.

Every failing pipeline shares one tracking issue per category (selected by a
stable set of marker labels). Subsequent failures edit that same issue instead
of opening duplicates. All GitHub interaction goes through the preinstalled
``gh`` CLI; the token is supplied via ``GH_TOKEN`` and is never printed.

Environment variables read by ``main``:
    GH_TOKEN     GitHub token (required).
    GH_REPO      ``owner/repo`` (required).
    LABELS       Comma-separated marker labels (default: bug,github-actions).
    TITLE        Title used when a new issue must be created.
    BODY_FILE    Path to a prepared Markdown body.
    FAIL_OS      Runner label, used to build a body when BODY_FILE is absent.
    RUN_URL      Workflow run URL, used to build a body when BODY_FILE is absent.
    DETAILS      Optional extra text appended to a generated body.
    REOPEN       Set to 1/true/yes to reopen an edited issue.
    ISSUE_STATE  Issue lookup state: open (default), all or closed.
"""
from __future__ import annotations

import argparse
import json
import os as _os
import subprocess
import sys
import tempfile
from collections.abc import Sequence

DEFAULT_LABELS = "bug,github-actions"


def build_body(os: str, run_url: str, details: str = "") -> str:
    """Build the Markdown body for a failure tracker, quoting the runner and run.

    The parameter is named ``os`` to match the calling convention in the CI
    helpers; the ``os`` module is imported as ``_os`` to avoid a name clash.
    """
    lines = [
        "Automated CI failure detected.",
        "",
        f"- **Runner:** `{os}`",
        f"- **Workflow run:** {run_url}",
    ]
    if details:
        lines.extend(["", details])
    lines.extend(
        [
            "",
            (
                "This issue is maintained automatically: later failures update this "
                "same issue instead of opening a new one. Keep it open while the "
                "pipeline is failing; closing a release tracker re-runs the build."
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def choose_action(existing_number: int | None) -> str:
    """Return ``edit`` when an issue exists, otherwise ``create``."""
    return "edit" if existing_number is not None else "create"


def _gh(args: Sequence[str], token: str) -> tuple[int, str, str]:
    """Run ``gh`` with the token isolated in the child environment."""
    env = dict(_os.environ)
    env["GH_TOKEN"] = token
    env["GH_NO_UPDATE_NOTIFIER"] = "1"
    process = subprocess.run(
        ["gh", *args], env=env, capture_output=True, text=True, check=False
    )
    return process.returncode, process.stdout.strip(), process.stderr.strip()


def find_issue(
    labels: Sequence[str], state: str, repo: str, token: str
) -> int | None:
    """Return the number of the single open/matching tracker, if one exists.

    Repeated ``--label`` flags are combined with AND by ``gh issue list``, so
    only issues carrying the full marker set are considered.
    """
    args = [
        "issue",
        "list",
        "--repo",
        repo,
        "--state",
        state,
        "--limit",
        "1",
        "--json",
        "number",
    ]
    for label in labels:
        args.extend(["--label", label])

    code, out, err = _gh(args, token)
    if code != 0:
        print(f"warning: gh issue list failed: {err}", file=sys.stderr)
        return None
    try:
        issues = json.loads(out)
    except json.JSONDecodeError:
        return None
    if not issues:
        return None
    number = issues[0].get("number")
    return int(number) if number is not None else None


def _enable_reopen_from_env() -> bool:
    return _os.environ.get("REOPEN", "").strip().lower() in {"1", "true", "yes"}


def main(argv: list[str] | None = None) -> int:
    """Create or update the tracker described by the environment/arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", default=_os.environ.get("LABELS", DEFAULT_LABELS))
    parser.add_argument("--title", default=_os.environ.get("TITLE", ""))
    parser.add_argument("--body-file", default=_os.environ.get("BODY_FILE", ""))
    parser.add_argument(
        "--state",
        default=_os.environ.get("ISSUE_STATE", "open"),
        choices=("open", "all", "closed"),
        help="state used when searching for the existing tracker",
    )
    parser.add_argument(
        "--reopen", action="store_true", default=_enable_reopen_from_env()
    )
    parser.add_argument(
        "--on-success",
        action="store_true",
        help="comment on an existing tracker instead of creating/updating one",
    )
    parser.add_argument(
        "--comment",
        default=_os.environ.get("SUCCESS_COMMENT", ""),
        help="comment text used with --on-success",
    )
    args = parser.parse_args(argv)

    token = _os.environ.get("GH_TOKEN", "")
    repo = _os.environ.get("GH_REPO", "")
    if not token or not repo:
        print("GH_TOKEN and GH_REPO must be set", file=sys.stderr)
        return 2

    labels = [label.strip() for label in args.labels.split(",") if label.strip()]
    if not labels:
        print("at least one label is required", file=sys.stderr)
        return 2

    number = find_issue(labels, args.state, repo, token)

    if args.on_success:
        if number is None:
            return 0
        comment = args.comment or (
            "Automated checks are green; this tracker can be closed manually."
        )
        code, _, err = _gh(
            ["issue", "comment", str(number), "--repo", repo, "--body", comment],
            token,
        )
        if code != 0:
            print(f"warning: could not comment on issue #{number}: {err}", file=sys.stderr)
        return 0 if code == 0 else 1

    body_file = args.body_file
    temporary = False
    if not body_file:
        fail_os = _os.environ.get("FAIL_OS", "")
        run_url = _os.environ.get("RUN_URL", "")
        if not fail_os or not run_url:
            print(
                "provide BODY_FILE or both FAIL_OS and RUN_URL to build a body",
                file=sys.stderr,
            )
            return 2
        fd, body_file = tempfile.mkstemp(prefix="ci-issue-body-", suffix=".md")
        with _os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(build_body(fail_os, run_url, _os.environ.get("DETAILS", "")))
        temporary = True
    elif not _os.path.isfile(body_file):
        print(f"body file not found: {body_file}", file=sys.stderr)
        return 2

    title = args.title or "CI failure (auto-tracked)"
    try:
        if choose_action(number) == "edit":
            code, _, err = _gh(
                ["issue", "edit", str(number), "--repo", repo, "--body-file", body_file],
                token,
            )
            if code != 0:
                print(f"error: could not edit issue #{number}: {err}", file=sys.stderr)
            elif args.reopen:
                # Reopen is harmless when the tracker is already open.
                reopen_code, _, reopen_err = _gh(
                    ["issue", "reopen", str(number), "--repo", repo], token
                )
                if reopen_code != 0:
                    print(
                        f"warning: could not reopen issue #{number}: {reopen_err}",
                        file=sys.stderr,
                    )
        else:
            code, _, err = _gh(
                [
                    "issue",
                    "create",
                    "--repo",
                    repo,
                    "--title",
                    title,
                    "--body-file",
                    body_file,
                    "--label",
                    ",".join(labels),
                ],
                token,
            )
            if code != 0:
                print(f"error: could not create tracking issue: {err}", file=sys.stderr)
    finally:
        if temporary:
            _os.unlink(body_file)

    return 0 if code == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
