#!/usr/bin/env python3
"""Package the version-independent power carry set so another checkout can take it
without fetching this branch.

docs/research/power/CARRY.toml already pins what travels (eight pure C modules and
three console judges, each with its test and case count). That manifest can only be
*compared* against a target tree; it cannot move the bytes. The iOS 27 checkout at
E:/hackios/xnekom-ios27 cannot even see this branch: its origin is a different fork
and its fetch refspec names one branch (docs/research/power/08-IOS27-POWER-PORT.md
2.2). This script turns the manifest into the thing that can move: a directory that
mirrors the repository paths, plus a sha256 manifest and a README that says what to
run after copying it in.

    python3 scripts/make-power-carry-bundle.py                  # build/power-carry-bundle
    python3 scripts/make-power-carry-bundle.py --out /some/dir
    python3 scripts/make-power-carry-bundle.py --tar            # also build/...tar.gz

Copy with `cp -a build/power-carry-bundle/. <target-tree>/` (paths are relative to
the repository root), then:

    python3 scripts/check-power-carry.py --target <target-tree>

which must print SAME for every module file and every judge, followed by
`power-carry: OK`. Exit 0 when the bundle matches the manifest, 1 when a pinned file
is missing or its hash moved, 2 when the manifest itself is unusable.
"""
from __future__ import annotations

import argparse
import hashlib
import pathlib
import re
import shutil
import sys
import tarfile
import tomllib

ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = "docs/research/power/CARRY.toml"
DEFAULT_OUT = "build/power-carry-bundle"

# Files the target tree needs in order to run and re-check the carry at all.
EXTRA = [
    MANIFEST,
    "docs/research/power/08-IOS27-POWER-PORT.md",
    "docs/research/power/09-CHARGE-AUTH.md",
    "docs/research/power/10-THERMAL-MAP.md",
    "docs/research/power/HW-CONTRACTS.toml",
    "docs/research/power/HW-CONTRACTS-IOS27.md",
    "scripts/check-power-carry.py",
    "scripts/check-power-portability.py",
    # its fixture exercises this gate end to end
    "scripts/check-ios27-power-preflight.py",
    # test-power-carry.py builds a nested bundle, so the tool travels too
    "scripts/make-power-carry-bundle.py",
    "scripts/tests/run-k60-power-host.sh",
    # The runner calls the python half too; a bundle without it would fail at
    # the first suite in the target tree.
    "scripts/tests/test-power-carry.py",
    "scripts/tests/test-check-ios27-power-preflight.py",
]

README = """# power carry bundle ({modules} modules, {judges} judges)

Mirrors repository paths. From the target tree root:

```sh
cp -a <this bundle>/. .
python3 scripts/check-power-carry.py --target .
bash scripts/tests/run-k60-power-host.sh build/power-host   # {checks} checks in {suites} suites
```

That single command is also the acceptance test for the bundle itself: it prints
`power-python: OK (6 suites)` after the C suites, so a copy that lost a test file or
a header fails here instead of passing quietly. The 2026-11-20 build was run inside a
bare bundle directory (no git) and passed both halves.

The bundle also carries every file `docs/research/power/HW-CONTRACTS.toml` cites, so
`python3 scripts/check-hw-contracts.py` answers with 23 verified contracts inside the
copy - those files are the ones the 27 line rewires.

Each judge keeps its own fixture; run them before reading a real console:

```sh
python3 scripts/tests/test-judge-k60-handoff-console.py   # 33 cases
python3 scripts/tests/test-judge-k60-sleep-console.py     # 28 cases
python3 scripts/tests/test-judge-k60-mode1-console.py     # 14 cases
```

See docs/research/power/08-IOS27-POWER-PORT.md section 2 for what still has to be
rewired by hand (property numbers, read_random, the sleep-report macro).
"""


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: pathlib.Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


RUNNER = "scripts/tests/run-k60-power-host.sh"


def runner_deps() -> list[str]:
    """Every source or test file the host runner compiles or calls.

    The bundle has to be self-sufficient: a checkout that cannot fetch this
    branch gets the runner too, and the runner fails on the first suite whose
    file is missing (that is how the C suites were found absent).
    """
    text = (ROOT / RUNNER).read_text(encoding="utf-8")
    joined = text.replace("\\\n", " ")
    deps: list[str] = []
    for line in joined.splitlines():
        stripped = line.strip()
        if not stripped.startswith(("run ", "run_py ")):
            continue
        words = stripped.split()
        if words[0] == "run":
            files = [w for w in words[3:] if not w.isdigit()]
        else:
            files = [w for w in words[2:] if "/" in w and not w.startswith('-')]
        for rel in files:
            if rel.startswith("scripts/") or rel.startswith("drivers/"):
                if rel not in deps:
                    deps.append(rel)
    return deps


INCLUDE_RE = re.compile(r'^\s*#\s*include\s*"([^"]+)"', re.MULTILINE)


def include_closure(files: list[str], depth: int = 0) -> list[str]:
    """Local headers reachable from the given files, relative to the repo root.

    The C suites include ../../drivers/ArmCpu/ArmCpuSleep.h and friends, so a
    bundle that copies only the test file does not compile in a foreign tree.
    """
    found: dict[str, None] = {}
    if depth > 6:
        return []
    for rel in files:
        path = ROOT / rel
        if not path.is_file():
            continue
        for match in INCLUDE_RE.finditer(path.read_text(encoding="utf-8", errors="replace")):
            name = match.group(1)
            if "/" not in name:
                # the runner compiles with -I drivers/PongPower, so a bare name
                # usually lives there
                for base in (path.parent, ROOT / "drivers" / "PongPower"):
                    if (base / name).is_file():
                        target = (base / name).resolve()
                        break
                else:
                    continue
            else:
                target = (path.parent / name).resolve()
            try:
                inner = target.relative_to(ROOT)
            except ValueError:
                continue
            key = inner.as_posix()
            if key.startswith(("drivers/", "scripts/")) and key not in found:
                found[key] = None
    nested = include_closure(list(found), depth + 1)
    for key in nested:
        found.setdefault(key, None)
    return list(found)


CONTRACTS = "docs/research/power/HW-CONTRACTS.toml"


def cite_closure() -> list[str]:
    """Every file the hardware-contract table cites, so the table can be checked here.

    docs/research/power/HW-CONTRACTS.toml is a list of file:line citations, and
    the bundle carries the checker for it. A bundle that shipped the table but
    not the lines it cites would ship a check that can only fail, so the cited
    sources travel too - they are also the files the 27 line has to rewire.
    """
    path = ROOT / CONTRACTS
    if not path.is_file():
        return []
    rows: list[str] = []
    for row in load(path).get("contract", []):
        for key in ("source", "mirror"):
            rel = str(row.get(key) or "").rpartition(":")[0]
            if rel and rel not in rows:
                rows.append(rel)
    return rows


def pinned(manifest: dict) -> list[tuple[str, str]]:
    """(relative path, expected sha256) for every file the manifest names."""
    rows: list[tuple[str, str]] = []
    for entry in manifest.get("module", []):
        for item in entry.get("files", []):
            rows.append((str(item.get("path") or ""), str(item.get("sha256") or "")))
        if entry.get("test"):
            rows.append((str(entry["test"]), ""))
    for entry in manifest.get("judge", []):
        if entry.get("path"):
            rows.append((str(entry["path"]), str(entry.get("sha256") or "")))
        if entry.get("test"):
            rows.append((str(entry["test"]), ""))
    for rel in EXTRA:
        rows.append((rel, ""))
    for rel in runner_deps():
        rows.append((rel, ""))
    for rel in cite_closure():
        rows.append((rel, ""))
    for rel in include_closure([r for r, _ in rows if r.endswith((".c", ".h", ".cpp"))]):
        rows.append((rel, ""))
    seen: dict[str, str] = {}
    for rel, want in rows:
        if rel and rel not in seen:
            seen[rel] = want
    return list(seen.items())


def build(out: pathlib.Path) -> tuple[int, list[str]]:
    manifest = load(ROOT / MANIFEST)
    rows = pinned(manifest)
    problems = [f"{rel}: not in this tree" for rel, _ in rows if not (ROOT / rel).is_file()]
    if problems:
        return 2, problems
    if out.exists():
        shutil.rmtree(out)
    lines: list[str] = []
    for rel, want in rows:
        source = ROOT / rel
        copy = out / rel
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, copy)
        got = sha256_file(source)
        if want and got != want:
            problems.append(f"{rel}: manifest says {want[:12]}, the tree has {got[:12]}")
        lines.append(f"{got}  {rel}")
    (out / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    suites = len(manifest.get("module", []))
    checks = sum(int(entry.get("checks") or 0) for entry in manifest.get("module", []))
    (out / "README.md").write_text(
        README.format(modules=len(manifest.get("module", [])), judges=len(manifest.get("judge", [])),
                      checks=checks, suites=suites + 2),
        encoding="utf-8", newline="\n")
    return (1 if problems else 0), problems


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    parser = argparse.ArgumentParser(description="package the power carry set")
    parser.add_argument("--out", default=str(ROOT / DEFAULT_OUT))
    parser.add_argument("--tar", action="store_true", help="also write <out>.tar.gz")
    args = parser.parse_args()
    out = pathlib.Path(args.out)
    code, problems = build(out)
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)
    if code == 2:
        print("power-carry-bundle: the manifest names files this tree does not have", file=sys.stderr)
        return 2
    count = len(list(out.rglob("*")))
    if args.tar:
        archive = out.with_suffix(".tar.gz")
        with tarfile.open(archive, "w:gz") as handle:
            handle.add(out, arcname=out.name)
        print(f"power-carry-bundle: {archive}")
    print(f"power-carry-bundle: {'OK' if code == 0 else 'FAIL'} ({out}, {count} path(s))")
    return code


if __name__ == "__main__":
    sys.exit(main())
