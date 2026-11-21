#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Check that every git feed in feeds.toml is checked out at its pinned commit.

A feed pin is the only thing that makes a fetched tree reproducible.  The
framework materialises it under

    <out>/feeds/<repo-stem>-<sha1(url + "\n" + pin)[:8]>

so the expected path is a function of the pin itself.  This gate recomputes that
path and compares the checkout's HEAD with the commit in feeds.toml.  It is
offline: it never fetches, checks out or contacts a remote.

Exit status:
  0  every git feed is at its pinned commit
  1  a checkout is at another commit, or its origin is another repository
  2  cannot judge: no pin, no checkout, no feeds directory, or unreadable git
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - python < 3.11
    tomllib = None

REPO = Path(os.environ.get("K60_REPO") or Path(__file__).resolve().parents[1])
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


def clone_dir(feeds_dir: Path, git: str, commit: str) -> Path:
    """The path feeds.py creates for one pinned source (same formula)."""
    key = hashlib.sha1(f"{git}\n{commit}".encode()).hexdigest()[:8]
    return Path(feeds_dir) / f"{Path(git).stem}-{key}"


def git_output(path: Path, *args: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(path), *args],
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def normalise(url: str) -> str:
    return url.rstrip("/").removesuffix(".git")


def check(feeds: Path, feeds_dirs: list[Path]) -> tuple[list[str], list[str], list[str]]:
    """Return (passed, failed, unjudged) descriptions for every git source."""
    if tomllib is None:
        return [], [], [f"{feeds}: python 3.11 or newer is required to read feeds.toml"]
    try:
        data = tomllib.loads(feeds.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        return [], [], [f"{feeds}: cannot read feeds.toml: {exc}"]

    sources = [item for item in data.get("source", []) if isinstance(item, dict)]
    git_sources = [item for item in sources if item.get("git") and not item.get("local")]
    if not git_sources:
        return [], [], [f"{feeds}: no git [[source]] entries to judge"]

    passed: list[str] = []
    failed: list[str] = []
    unjudged: list[str] = []
    missing_dirs = [str(path) for path in feeds_dirs if not Path(path).is_dir()]

    for source in git_sources:
        name = str(source.get("name") or source["git"])
        git = str(source["git"])
        commit = str(source.get("commit") or "").strip()
        if not commit:
            unjudged.append(f"{name}: feeds.toml has no commit pin; cannot judge")
            continue
        if not FULL_SHA.match(commit):
            unjudged.append(f"{name}: commit pin {commit!r} is not a 40-character sha; cannot judge")
            continue

        candidates = [clone_dir(base, git, commit) for base in feeds_dirs]
        existing = next((path for path in candidates if (path / ".git").exists()), None)
        if existing is None:
            where = ", ".join(str(path) for path in candidates) or "(no --feeds-dir)"
            if missing_dirs:
                unjudged.append(f"{name}: feeds directory absent ({', '.join(missing_dirs)}); expected {where}")
            else:
                unjudged.append(f"{name}: no checkout for pin {commit[:12]} at {where}; run unixnu fetch")
            continue

        head = git_output(existing, "rev-parse", "HEAD")
        origin = git_output(existing, "remote", "get-url", "origin")
        if head is None:
            unjudged.append(f"{name}: {existing} is not a readable git checkout; cannot judge")
            continue
        if origin is None:
            unjudged.append(f"{name}: {existing} has no origin; cannot judge")
            continue
        if normalise(origin) != normalise(git):
            failed.append(
                f"{name}: {existing} has origin {origin!r}, feeds.toml names {git!r}"
            )
            continue
        if head.lower() != commit.lower():
            failed.append(
                f"{name}: feeds.toml pins {commit}, but {existing} is at {head}"
            )
            continue
        passed.append(f"{name}: {head} at {existing}")

    return passed, failed, unjudged


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feeds", default=str(REPO / "feeds.toml"),
                        help="feeds.toml to read (default: repository feeds.toml)")
    parser.add_argument("--feeds-dir", action="append", default=None,
                        help="fetch output directory (repeatable; default: $K60_FEEDS_DIR, "
                             "then $K60_OUT/feeds, then <repo>/../UniXNU/out/feeds)")
    args = parser.parse_args(argv)

    if args.feeds_dir:
        feed_dirs = [Path(item) for item in args.feeds_dir]
    elif os.environ.get("K60_FEEDS_DIR"):
        feed_dirs = [Path(os.environ["K60_FEEDS_DIR"])]
    elif os.environ.get("K60_OUT"):
        feed_dirs = [Path(os.environ["K60_OUT"]) / "feeds"]
    else:
        feed_dirs = [REPO.parent / "UniXNU" / "out" / "feeds"]

    feeds = Path(args.feeds)
    if not feeds.is_file():
        print(f"UNJUDGED feed pins: {feeds} does not exist; cannot judge", file=sys.stderr)
        return 2

    passed, failed, unjudged = check(feeds, feed_dirs)
    for line in passed:
        print(f"PASS {line}")
    for line in failed:
        print(f"FAIL {line}", file=sys.stderr)
    for line in unjudged:
        print(f"UNJUDGED {line}", file=sys.stderr)

    if failed:
        print(f"❌ feed pins: {len(failed)} failed, {len(passed)} passed, "
              f"{len(unjudged)} unjudged", file=sys.stderr)
        return 1
    if unjudged:
        print(f"❌ feed pins: cannot judge ({len(unjudged)} unjudged, "
              f"{len(passed)} passed)", file=sys.stderr)
        return 2
    print(f"✅ feed pins: {len(passed)} git feed(s) at their pinned commit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
