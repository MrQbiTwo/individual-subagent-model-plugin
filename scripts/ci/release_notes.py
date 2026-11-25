#!/usr/bin/env python3
"""Render .github/release-template.md for the tag-push release job.

Commit subjects and first-time contributors come from git; the tested
application/CLI versions and the build toolchain come from the package
manifest and ci.yml; the full changelog comes from GitHub's generated notes.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

PLACEHOLDERS = (
    "CHANGES",
    "CONTRIBUTORS",
    "APP_VERSION",
    "CLI_VERSION",
    "NODE_VERSION",
    "TYPESCRIPT_VERSION",
    "FULL_CHANGELOG",
)


def render(template: str, values: dict[str, str]) -> str:
    """Substitute every known placeholder; fail if one is missing."""
    for key in PLACEHOLDERS:
        token = "{{" + key + "}}"
        if token not in template:
            raise ValueError(f"template is missing {token}")
        template = template.replace(token, values[key])
    return template


def _git(root: Path, *args: str) -> list[str]:
    proc = subprocess.run(
        ("git", *args), cwd=root, capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        return []
    return [line for line in proc.stdout.splitlines() if line.strip()]


def commit_changes(root: Path, tag: str, previous: str) -> list[str]:
    """Subject lines of non-merge commits in this release."""
    revision = f"{previous}..{tag}" if previous else tag
    return _git(root, "log", "--no-merges", "--format=%s", revision)


def new_contributors(root: Path, tag: str, previous: str) -> list[str]:
    """Authors who appear in this release but not before it."""
    fmt = "--format=%an <%ae>"
    revision = f"{previous}..{tag}" if previous else tag
    current = set(_git(root, "log", fmt, revision))
    if not previous:
        return sorted(current)
    return sorted(current - set(_git(root, "log", fmt, previous)))


def full_changelog(generated: str, tag: str, previous: str, repo: str) -> str:
    """Take GitHub's generated Full Changelog line, or build its compare link."""
    match = re.search(r"^\*\*Full Changelog\*\*:.*$", generated, re.MULTILINE)
    if match:
        return match.group(0)
    if previous and repo:
        return (
            f"**Full Changelog**: https://github.com/{repo}/compare/{previous}...{tag}"
        )
    return "_No previous tag: this is the first release._"


def collect_versions(root: Path) -> dict[str, str]:
    """Read the versions actually used by CI from the manifest and ci.yml."""
    package = json.loads((root / "opencode/package.json").read_text(encoding="utf-8"))
    workflow = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    cli = re.search(r"OPENCODE_VERSION:\s*'([^']+)'", workflow)
    node = re.search(r"node-version:\s*'([^']+)'", workflow)
    if cli is None or node is None:
        raise ValueError("cannot read the tested CLI / Node.js version from ci.yml")
    return {
        "APP_VERSION": package["version"],
        "CLI_VERSION": cli.group(1),
        "NODE_VERSION": node.group(1),
        "TYPESCRIPT_VERSION": package["devDependencies"]["typescript"].lstrip("^"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--previous", default="")
    parser.add_argument("--generated-notes", required=True)
    parser.add_argument("--repo", default="")
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[2]
    template = (root / args.template).read_text(encoding="utf-8")
    generated = (root / args.generated_notes).read_text(encoding="utf-8")
    values = collect_versions(root)
    changes = commit_changes(root, args.tag, args.previous)
    contributors = new_contributors(root, args.tag, args.previous)
    values["CHANGES"] = (
        "\n".join(f"- {subject}" for subject in changes)
        or "- No commits since the previous tag."
    )
    values["CONTRIBUTORS"] = (
        "\n".join(f"- {author}" for author in contributors) or "- None in this release."
    )
    values["FULL_CHANGELOG"] = full_changelog(
        generated, args.tag, args.previous, args.repo
    )
    output = root / args.output
    output.write_text(render(template, values), encoding="utf-8")
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
