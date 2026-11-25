#!/usr/bin/env python3
"""Semantic-version helpers shared by the CI workflows.

Only the plain ``X.Y.Z`` core form of SemVer 2.0.0 is accepted here. Git tag
names carry a leading ``v``; that prefix is removed explicitly by ``from_tag``
so a tag name can never be mistaken for a version string.
"""
from __future__ import annotations

import argparse
import re
import sys

# SemVer 2.0.0 core version: no leading zeroes in any numeric component.
_VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def is_valid(version: str) -> bool:
    """Return True when *version* is a plain ``X.Y.Z`` SemVer core version."""
    return isinstance(version, str) and _VERSION_RE.fullmatch(version) is not None


def from_tag(tag: str) -> str:
    """Strip a single leading ``v`` from a git tag, if present."""
    return tag.removeprefix("v")


def compare(a: str, b: str) -> int:
    """Return -1, 0 or 1 when *a* is less than, equal to, or greater than *b*."""
    if not is_valid(a) or not is_valid(b):
        raise ValueError(f"invalid semantic version: {a!r} or {b!r}")
    parts_a = tuple(int(part) for part in a.split("."))
    parts_b = tuple(int(part) for part in b.split("."))
    return (parts_a > parts_b) - (parts_a < parts_b)


def main(argv: list[str] | None = None) -> int:
    """Expose the helpers to shell scripts with shell-friendly exit codes."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    valid = commands.add_parser("is-valid", help="print true/false; exit 1 when invalid")
    valid.add_argument("version")

    tag = commands.add_parser("from-tag", help="print the version without a leading v")
    tag.add_argument("tag")

    compare_cmd = commands.add_parser("compare", help="print -1, 0 or 1")
    compare_cmd.add_argument("a")
    compare_cmd.add_argument("b")

    newer = commands.add_parser("newer", help="exit 0 when a > b, otherwise exit 1")
    newer.add_argument("a")
    newer.add_argument("b")

    args = parser.parse_args(argv)

    if args.command == "is-valid":
        ok = is_valid(args.version)
        print("true" if ok else "false")
        return 0 if ok else 1

    if args.command == "from-tag":
        print(from_tag(args.tag))
        return 0

    try:
        result = compare(args.a, args.b)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.command == "compare":
        print(result)
        return 0

    # "newer": a non-zero exit code is a normal "no newer version" answer.
    return 0 if result > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
