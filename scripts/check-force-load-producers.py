#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Every -force_load in the generic builder must name an archive with a producer.

scripts/build-xnu-generic.sh force-loads about twenty archives. Each one is a
promise: the link fails at a bare `test -f` if the file is not there, and the
builder itself never writes it. This gate binds every promise to a producer and
reports the evidence, so "the path is in the linker line but nobody writes it"
(the P-267 shape) is a red gate instead of a build-time surprise.

Every piece of evidence carries a lineage:

  16    only the 16.6.1 line produces it -- the macOS `*-macos.py` producers and
        build-xnu-4k-baseline.sh. The 27 profile never runs those, so a 16-only
        row is NOT evidence that the 27 link can be satisfied;
  27    only the 27 line produces it -- build-native-ufs-linux.py and the
        generic builder's own recipes;
  both  the shared device-repo scripts and UniXNU/components.toml, used by both
        profiles.

Without --strict every row is graded and 16-only evidence prints
`[NOTE 16.6.1-only]` so nobody mistakes it for a 27 producer. With --strict the
16-only rows are not counted: a row whose only evidence is 16 becomes a gap.

Evidence, strongest first:
  local      a build-*.py or build-*.sh in this repo (other than the 27 linker
             itself) writes the archive's directory;
  catalog    a component in UniXNU/components.toml declares that output path
             (the framework builds it from the component recipe).
No evidence at all is a gap, exit 1. The gate is static: it never builds, never
runs a recipe and never needs the toolchain.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BUILDER = "scripts/build-xnu-generic.sh"
SITE = re.compile(r"-force_load,(?:\$\{)?\$?(ROOT/[^\"'\s]+|[A-Za-z_][A-Za-z0-9_]*)")
ASSIGN = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
LINKERS = {"build-xnu-generic.sh"}
LINEAGE_16 = {"build-xnu-4k-baseline.sh"}


def lineage(name: str) -> str:
    """Classify one evidence source as 16-only, 27-only or shared."""
    if name in LINEAGE_16 or name.endswith("-macos.py"):
        return "16"
    if name == "build-native-ufs-linux.py" or name in LINKERS:
        return "27"
    return "both"


def assignments(lines: list[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in lines:
        match = ASSIGN.match(line)
        if not match:
            continue
        name, value = match.group(1), match.group(2).strip().strip('"')
        if "$(" in value:
            continue
        value = value.replace("${ROOT}", "").replace("$ROOT", "")
        value = re.sub(r"^\$\{[^}]+\:-", "", value)
        value = value.rstrip("}").lstrip("/")
        if value.startswith("build/"):
            found[name] = value
    return found


def catalog_outputs(framework: Path | None) -> dict[str, str]:
    """Map an output path to the component id that declares it."""
    if not framework:
        return {}
    path = framework / "components.toml"
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    outputs: dict[str, str] = {}
    component = "?"
    for line in text.splitlines():
        match = re.match(r"^\s*id\s*=\s*\"([^\"]+)\"", line)
        if match:
            component = match.group(1)
        for quoted in re.findall(r"\"(build/[^\"]+)\"", line):
            outputs[quoted] = component
    return outputs


def local_producers(archive: str, scripts: list[Path]) -> list[str]:
    directory = str(Path(archive).parent)
    name = Path(archive).name
    found = []
    for script in scripts:
        if script.name in LINKERS:
            continue
        text = script.read_text(encoding="utf-8", errors="replace")
        if directory in text or name in text:
            found.append(script.name)
    return found


def label(name: str) -> str:
    where = lineage(name)
    if where == "16":
        return "%s [NOTE 16.6.1-only]" % name
    return "%s [%s]" % (name, where)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--builder", default=BUILDER)
    parser.add_argument("--framework", type=Path, default=None,
                        help="default: $K60_FRAMEWORK_REPO or <repo>/../UniXNU")
    parser.add_argument("--strict", action="store_true",
                        help="ignore 16.6.1-only evidence: it cannot justify a 27 link")
    args = parser.parse_args()

    repo = args.repo.resolve()
    builder = repo / args.builder
    if not builder.is_file():
        print("FAIL builder not found: %s" % builder)
        return 2
    framework = args.framework
    if framework is None:
        candidates = [os.environ.get("K60_FRAMEWORK_REPO"), repo.parent / "UniXNU",
                      Path("E:/hackios/UniXNU"), Path("/e/hackios/UniXNU")]
        for candidate in candidates:
            if candidate and (Path(candidate) / "components.toml").is_file():
                framework = Path(candidate)
                break
    outputs = catalog_outputs(framework)

    lines = builder.read_text(encoding="utf-8", errors="replace").splitlines()
    values = assignments(lines)
    scripts = sorted((repo / "scripts").glob("build-*.py")) + sorted((repo / "scripts").glob("build-*.sh"))

    problems: list[str] = []
    graded = 0
    for number, line in enumerate(lines, 1):
        if "force_load" not in line:
            continue
        match = SITE.search(line)
        if not match:
            problems.append("%s:%d cannot parse force_load: %s" % (args.builder, number, line.strip()))
            continue
        token = match.group(1)
        if token.startswith("ROOT/"):
            archive = token[len("ROOT"):].lstrip("/")
            variable = "literal"
        else:
            variable = token.lstrip("$")
            archive = values.get(variable, "")
        if not archive.startswith("build/"):
            problems.append("%s:%d %s does not resolve to a build/ path" % (args.builder, number, variable))
            continue
        graded += 1
        evidence = [(name, lineage(name)) for name in local_producers(archive, scripts)]
        if archive in outputs:
            evidence.append(("component:%s" % outputs[archive], "both"))
        if not evidence:
            print("  GAP  %-52s no producer in this tree or the catalog" % archive)
            problems.append("%s:%d %s has no producer" % (args.builder, number, archive))
            continue
        counted = [item for item in evidence if item[1] != "16"]
        if args.strict and not counted:
            print("  GAP  %-52s only 16.6.1 evidence: %s" % (archive, ", ".join(label(name) for name, _ in evidence)))
            problems.append("%s:%d %s has only 16.6.1 evidence, not a 27 producer" % (args.builder, number, archive))
            continue
        shown = evidence if not args.strict else counted
        suffix = ""
        if any(where == "16" for _, where in evidence):
            suffix = " (strict: 16.6.1-only rows ignored)" if args.strict else ""
        print("  OK   %-52s <- %s%s" % (archive, ", ".join(label(name) for name, _ in shown), suffix))

    print("force-load-producers: %d site(s), %d gap(s)%s" % (graded, len(problems), " (strict)" if args.strict else ""))
    for problem in problems:
        print("     " + problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
