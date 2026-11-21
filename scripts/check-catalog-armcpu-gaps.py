#!/usr/bin/env python3
"""Check the three gaps that keep the catalog ArmCpu out of the 27 build.

Read-only and offline: it opens `board.toml`, `components.toml`, the ADT
generator and the catalog source in a sibling checkout, prints a verdict per
gap, and writes nothing. It never builds, never touches the device, and never
edits `board.toml`.

Each gap gets one of three verdicts, and the third one is a real answer:

  SATISFIED    the tree already satisfies the gap, so the catalog switch can
               stop counting it
  OPEN         the gap is still there, with the file:line that proves it
  UNKNOWN      cannot be judged here; the line says which input is missing
               (naming it is the point - "cannot read" folded into "fine" is
               the shape of P-279/P-290)

Exit code: 0 when every gap is SATISFIED, 1 when any gap is OPEN, 2 when none
is OPEN but at least one is UNKNOWN.

The three gaps (docs/research/ios27/FORK-DECISION.md):

  1 psci-node   catalog ArmCpu reads the IORegistry `/psci` node for its PSCI
                conduit, and the Pong ADT ships no such node
  2 sheng-smp   catalog secondaries are opt-in behind the `sheng-smp` boot arg
  3 sleep       the pinned catalog revision carries no platform sleep, and the
                27 archives leave PongPower out
"""

import argparse
import glob
import json
import os
import re
import subprocess
import sys
import tomllib

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:  # pragma: no cover - older interpreters
    pass

SATISFIED = "SATISFIED"
OPEN = "OPEN"
UNKNOWN = "UNKNOWN"

DEFAULT_LANE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG_REPO = "https://github.com/UniXNU/ArmCpu.git"


def read(path):
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read()


def parse_toml(path):
    with open(path, "rb") as handle:
        return tomllib.load(handle)


def line_of(path, needle, after=0):
    """First 1-based line containing needle, or 0."""
    try:
        text = read(path)
    except OSError:
        return 0
    for index, line in enumerate(text.splitlines(), 1):
        if index > after and needle in line:
            return index
    return 0


def merge(base, override):
    """Deep-merge an os_overrides entry over the base board manifest."""
    if isinstance(base, dict) and isinstance(override, dict):
        out = dict(base)
        for key, value in override.items():
            out[key] = merge(base[key], value) if key in base else value
        return out
    return override


def effective_manifest(board):
    profile = board.get("board", {}).get("os_profile", "")
    overrides = board.get("os_overrides", {})
    merged = merge(board, overrides.get(profile, {}))
    if profile in overrides:
        merged.pop("os_overrides", None)
    return merged, profile


def catalog_pin(components_path):
    """Return (revision, path) for ArmCpu from components.toml, or (None, None)."""
    if not os.path.exists(components_path):
        return None, None
    data = parse_toml(components_path)
    entries = data.get("component", data.get("components", []))
    if isinstance(entries, dict):
        entries = list(entries.values())
    for entry in entries:
        if isinstance(entry, dict) and entry.get("id") == "ArmCpu":
            return entry.get("revision"), entry.get("path")
    return None, None


def catalog_source(catalog_dir, revision):
    """Return (text, error). Reads <rev>:<path> out of the catalog checkout."""
    if not catalog_dir or not os.path.isdir(catalog_dir):
        return None, "no catalog checkout at %s" % (catalog_dir or "<none>")
    if not revision:
        return None, "components.toml names no ArmCpu revision"
    targets = ["ArmCpu.cpp"]
    try:
        listing = subprocess.run(
            ["git", "-C", catalog_dir, "ls-tree", "--name-only", revision],
            capture_output=True, text=True, check=True).stdout.split()
    except subprocess.CalledProcessError as error:
        return None, ("catalog checkout %s has no revision %s (%s)"
                      % (catalog_dir, revision,
                         (error.stderr or "").strip().splitlines()[-1:] or "git failed"))
    for name in listing:
        if name.endswith("ArmCpu.cpp"):
            targets = [name]
            break
    try:
        return subprocess.run(
            ["git", "-C", catalog_dir, "show", "%s:%s" % (revision, targets[0])],
            capture_output=True, text=True, check=True).stdout, None
    except subprocess.CalledProcessError as error:
        return None, "git show %s:%s failed: %s" % (revision, targets[0],
                                                    (error.stderr or "").strip())


def gap_psci(lane, adt_path, source, source_error):
    if source is None:
        return UNKNOWN, ["catalog source unreadable: %s" % source_error,
                         "missing input: a catalog checkout with the pinned revision"]
    reads_psci = bool(re.search(r"['\"]/psci['\"]", source))
    adt_line = line_of(adt_path, "psci")
    text = ""
    try:
        text = read(adt_path)
    except OSError:
        pass
    # A node is created when the generator names a child "psci"; writing the
    # /chosen psci-method property is not a node, so that line does not count.
    builds_node = any("psci" in line and "psci-method" not in line
                      for line in text.splitlines())
    evidence = ["catalog ArmCpu reads the /psci node: %s"
                % ("yes" if reads_psci else "no"),
                "ADT generator %s: first psci mention at line %d; publishes a psci "
                "node: %s" % (os.path.relpath(adt_path, lane), adt_line,
                              "yes" if builds_node else "no")]
    if not reads_psci:
        return SATISFIED, evidence + ["this revision takes its conduit elsewhere, so "
                                      "the missing node no longer matters"]
    if builds_node:
        return SATISFIED, evidence + ["the ADT now publishes a /psci node"]
    return OPEN, evidence + ["the ADT publishes no /psci node, so psciConduit() finds "
                             "nothing and CPU_ON would not be attempted"]


def gap_bootarg(manifest, board_path):
    args = manifest.get("payload", {}).get("kernel_args", [])
    hits = [a for a in args if str(a).startswith("sheng-smp")]
    line = line_of(board_path, "sheng-smp")
    if hits:
        return SATISFIED, ["board.toml:%d carries %s" % (line or 0, hits[0])]
    return OPEN, ["board.toml:%d is the 27 kernel_args list and none of its %d entries "
                  "is sheng-smp=1; catalog probe() refuses every secondary without it"
                  % (line_of(board_path, "kernel_args = [", after=380) or 0, len(args))]


def gap_sleep(manifest, source, source_error):
    archives = manifest.get("kernel", {}).get("archives", [])
    includes = manifest.get("components", {}).get("include", [])
    has_power = any("PongPower" in str(x) for x in archives + includes)
    if source is None:
        return UNKNOWN, ["catalog source unreadable: %s" % source_error,
                         "missing input: a catalog checkout with the pinned revision"]
    has_sleep = "armcpu_sleep_register" in source
    evidence = ["catalog revision %s exports armcpu_sleep_register: %s"
                % ("pinned", "yes" if has_sleep else "no"),
                "the 27 archives/include carry PongPower: %s" % ("yes" if has_power else "no")]
    if has_sleep and has_power:
        return SATISFIED, evidence
    if not has_sleep and not has_power:
        return OPEN, evidence + ["neither side is ready: bump the pin to a revision with "
                                 "ArmCpuSleep.h AND archive PongPower"]
    if not has_sleep:
        return OPEN, evidence + ["the pin is older than 823c6b2/5f37026, the revision "
                                 "that added platform sleep"]
    return OPEN, evidence + ["the catalog would expect a board hook, but PongPower "
                             "(K60PlatformSleep.cpp:128) is outside the 27 archives"]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--lane-root", default=DEFAULT_LANE)
    ap.add_argument("--framework", default=None,
                    help="framework checkout holding components.toml")
    ap.add_argument("--catalog", default=None, help="catalog checkout (ArmCpu repo)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    lane = os.path.abspath(args.lane_root)
    framework = args.framework or os.path.join(os.path.dirname(lane), "UniXNU")
    catalog = args.catalog or os.path.join(os.path.dirname(lane), "ArmCpu")
    board_path = os.path.join(lane, "board.toml")
    adt_path = os.path.join(lane, "scripts", "make-pong-adt.py")
    components_path = os.path.join(framework, "components.toml")

    if not os.path.exists(board_path):
        print("FAIL: no board.toml under %s" % lane)
        return 2
    board = parse_toml(board_path)
    manifest, profile = effective_manifest(board)
    revision, _path = catalog_pin(components_path)
    source, source_error = catalog_source(catalog, revision)

    results = []
    for key, title, verdict, evidence in (
            ("psci-node", "the ADT has the /psci node the catalog reads",
             *gap_psci(lane, adt_path, source, source_error)),
            ("sheng-smp", "the 27 kernel_args opt the secondaries in",
             *gap_bootarg(manifest, board_path)),
            ("sleep", "the catalog can register a platform sleep board",
             *gap_sleep(manifest, source, source_error))):
        results.append({"gap": key, "requirement": title,
                        "verdict": verdict, "evidence": evidence})

    if args.json:
        print(json.dumps({"profile": profile, "revision": revision,
                          "catalog": catalog, "gaps": results}, ensure_ascii=False,
                         indent=2))
    else:
        print("catalog ArmCpu gaps for %s (pin %s)"
              % (profile, (revision or "<unresolved>")[:8]))
        for result in results:
            print("\n%-11s %-9s %s" % (result["gap"], result["verdict"],
                                       result["requirement"]))
            for line in result["evidence"]:
                print("    - %s" % line)

    verdicts = [r["verdict"] for r in results]
    if OPEN in verdicts:
        code = 1
    elif UNKNOWN in verdicts:
        code = 2
    else:
        code = 0
    if not args.json:
        print("\n%s" % ("all gaps satisfied: the catalog switch has no structural "
                        "blocker left" if code == 0 else
                        ("%d gap(s) still open" % verdicts.count(OPEN) if code == 1 else
                         "cannot judge %d gap(s): the missing input is named above"
                         % verdicts.count(UNKNOWN))))
    return code


if __name__ == "__main__":
    sys.exit(main())
