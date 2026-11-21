#!/usr/bin/env python3
"""check-ufs27-storage-switches.py -- do the RamBlock and VerifiedRoot switches agree with the tree?

Companion to `check-ufs27-storage-selection.py`, which covers the UFS archive.
This one covers the other two storage archives the 27 builder can force-load,
`build/ram-block/libRamBlock.a` and `build/verified-root-xnu/libVerifiedRootProbe.a`,
and it grades the three questions the Lead asked on 2026-11-21:

  1. closed claim -- when the switch is off, the builder must not link the
     archive anyway. Both blocks sit behind an `if` on the switch:
     `scripts/build-xnu-generic.sh:728` `if [ "$NATIVE_RAM_BLOCK" = 1 ] && ...`
     and `:765` `if [ "$OWNER_ROOT_PROBE" = 1 ]; then`. A block that links the
     archive outside its switch would put an unrequested archive into every
     27 kernel, so it is graded, not assumed.
  2. open claim -- when the switch is on, something must write exactly that
     path. The switch comes from the defconfig (`CONFIG_XNU_NATIVE_RAM_BLOCK`,
     `CONFIG_XNU_VERIFIED_ROOT_PROBE`); `xnu_env()` in
     UniXNU/scripts/unixnu/kernel.py:17-30 turns `CONFIG_XNU_*` into `XNU_*`.
     The producer has to be a `[kernel].archives` entry of the 27 profile that
     names the output directory the builder reads (see `archive_plan()` and
     `build_archives()` in UniXNU/scripts/unixnu/kernel.py:118-175), and its
     script has to exist here -- `build-arm-driver.py` recipes come from a
     catalog module this repository does not declare.
  3. readable failure -- when the switch is on and the archive is absent, the
     build must say so. Both blocks call a bare `test -f` (`:729`, `:767`) and
     the script runs under `set -euo pipefail` (`:9`), so the build exits 1
     printing nothing. A one-line `|| { echo ...; exit 1; }` makes the failure
     readable; until then the defect is graded.

Measured on 2026-11-21, the two switches are off and unmentioned in
`configs/mondrian_ios27_defconfig`, so the tree is *closed*: nothing links, and
that is correct for stage 0. What the gate still fails is the failure form and
the missing producers, because those become the F3 blocker the moment a switch
is turned on.

Usage:
  python3 scripts/check-ufs27-storage-switches.py [--profile ios-27.0.1-24A446]
      [--repo E:/k60-work/ufs27] [--json out.json] [--quiet]

Exit 0 when every graded piece lines up, 1 when a piece is missing (the same
convention as check-ufs27-storage-selection.py). `--quiet` prints only the
verdict line, so a build script can gate on it.
"""
import argparse
import json
import os
import re
import sys
import tomllib
from pathlib import Path

REPO = Path(os.environ.get("K60_REPO") or Path(__file__).resolve().parents[1])
DEFAULT_PROFILE = "ios-27.0.1-24A446"
GENERIC_BUILDER = "scripts/build-xnu-generic.sh"

# The two switches, in the order the 27 builder evaluates them.
SWITCHES = (
    {
        "area": "ram-block",
        "config": "XNU_NATIVE_RAM_BLOCK",
        "shell": "NATIVE_RAM_BLOCK",
        "variable": "RAM_BLOCK_ARCHIVE",
        "archive": "build/ram-block/libRamBlock.a",
        "object": "build/ram-block/NativeRamBlock.o",
        # The only producer in this tree writes the 16.6.1 directory instead.
        "known_producer": "scripts/build-pong-ram-block-macos.py",
        "known_output": "build/native-ram-block",
        "known_reader": ("scripts/build-xnu-4k-baseline.sh",
                         "RAM_BLOCK_ARCHIVE=$ROOT/build/native-ram-block/libNativeRamBlock.a"),
        "precondition": "the builder refuses this switch without XNU_NATIVE_AES=1 "
                        "(scripts/build-xnu-generic.sh:221-227) and skips the whole block under "
                        "XNU_SOURCE_STORAGE=1 (:728)",
    },
    {
        "area": "verified-root",
        "config": "XNU_VERIFIED_ROOT_PROBE",
        "shell": "OWNER_ROOT_PROBE",
        "variable": "VERIFIED_ROOT_ARCHIVE",
        "archive": "build/verified-root-xnu/libVerifiedRootProbe.a",
        "object": None,
        # The 16.6.1 line compiles the verified-root objects into the UFS archive
        # under a different switch name; nothing writes this path.
        "known_producer": "scripts/build-pong-ufs-probe-macos.py",
        "known_output": "build/native-ufs",
        "known_reader": ("scripts/build-xnu-4k-baseline.sh", "build/native-ufs/libNativeUfs.a"),
        "precondition": "the builder refuses this switch without XNU_SOURCE_CORECRYPTO14=1 and "
                        "XNU_CRYPTO_BOOTSTRAP=prelinked (scripts/build-xnu-generic.sh:287-291), and the policy "
                        "bundle it verifies against (UniXNU/scripts/policies/ipados-27.0.1-24A446) is empty",
    },
)


def line_of(path, needle):
    """1-based line number of the first line containing needle, or None."""
    if not path.is_file():
        return None
    for number, text in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if needle in text:
            return number
    return None


def switch_state(defconfig, name):
    """(state, line) for CONFIG_<name> in a defconfig; absent means off."""
    if not defconfig.is_file():
        return False, None
    for number, text in enumerate(defconfig.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        match = re.search(rf'^CONFIG_{name}\s*=\s*"?([^"\s#]+)"?', text)
        if match:
            return match.group(1).lower() in ("y", "yes", "1", "true"), number
    return False, None


def guard_line(lines, assignment):
    """Index of the `if` that guards the archive assignment, or None.

    Walks back from the assignment to the nearest `if`; the 27 builder puts the
    assignment inside its switch block, so a nearer `if` that does not mention
    the switch means the block escaped its guard.
    """
    for index in range(assignment, max(-1, assignment - 40), -1):
        text = lines[index].lstrip()
        if text.startswith("if [") or text.startswith("if !") or text.startswith("if [["):
            return index
    return None


def readable_failure(lines, test_index):
    """True when the `test -f` line reports a message before aborting."""
    window = [lines[test_index]] + lines[test_index + 1:test_index + 3]
    return any("||" in text and ("echo" in text or "printf" in text or "exit" in text) for text in window)


def producer_for(entries, switch, repo):
    """The archives entry that writes this switch's archive, or None."""
    directory = switch["archive"].rsplit("/", 1)[0]
    for entry in entries:
        if directory not in entry:
            continue
        script = entry.split()[0]
        if not script.endswith(".py"):
            continue
        if (repo / "scripts" / script).is_file():
            return entry, script
        return None, script
    return None, None


def grade(board, repo, profile_name):
    problems, facts = [], []
    override = board["os_overrides"].get(profile_name)
    if override is None:
        raise SystemExit(f"board.toml: no os_overrides entry {profile_name!r}")
    entries = override.get("kernel", {}).get("archives", [])
    defconfig = repo / "configs" / override.get("kernel", {}).get("defconfig", "")
    defconfig_line = line_of(defconfig, "CONFIG_") if defconfig.is_file() else None
    builder = repo / GENERIC_BUILDER
    if not builder.is_file():
        raise SystemExit(f"missing builder: {builder}")
    lines = builder.read_text(encoding="utf-8", errors="replace").splitlines()
    archives_line = line_of(repo / "board.toml", '"build-fileset-release-reference.py --tree ."')

    for switch in SWITCHES:
        area, name = switch["area"], switch["config"]
        on, config_line = switch_state(defconfig, name)
        relative = defconfig.relative_to(repo).as_posix()
        where = f"{relative}:{config_line}" if config_line else relative

        # 1. closed claim: the archive assignment must sit inside its switch ----
        assignment = next((index for index, text in enumerate(lines)
                           if re.match(rf'\s*{switch["variable"]}=', text)), None)
        if assignment is None:
            problems.append((area, "GAP", f"{GENERIC_BUILDER} has no {switch['variable']} assignment, so this "
                                          f"checker cannot read the link block; re-anchor it"))
        else:
            guard = guard_line(lines, assignment)
            guarded = guard is not None and f'"${switch["shell"]}"' in lines[guard]
            archive_line = assignment + 1
            if guarded:
                facts.append((area, "OK", f"{GENERIC_BUILDER}:{guard + 1} guards {switch['variable']} on "
                                          f"${switch['shell']} = 1 ({GENERIC_BUILDER}:{archive_line} "
                                          f"reads {switch['archive']})"))
            else:
                problems.append((area, "GAP", f"{GENERIC_BUILDER}:{archive_line} assigns "
                                              f"{switch['variable']} outside any ${switch['shell']} guard, so the "
                                              f"archive would be linked even with the switch off"))

        # 2. open claim: a producer for exactly that path ----------------------
        entry, missing_script = producer_for(entries, switch, repo)
        if missing_script and entry is None:
            problems.append((area, "GAP", f"board.toml:{archives_line} names {missing_script}, which this "
                                          f"checkout does not have under scripts/ -- the entry writes "
                                          f"{switch['archive']} only on paper"))
        elif entry:
            if on:
                facts.append((area, "OK", f"{where} CONFIG_{name}=y and board.toml:{archives_line} recipe "
                                          f"{entry!r} writes {switch['archive']}: open state"))
            else:
                facts.append((area, "OK", f"board.toml:{archives_line} recipe {entry!r} writes "
                                          f"{switch['archive']}"))
                facts.append((area, "NOTE", f"{where} CONFIG_{name} is off, so the producer is wired but unused; "
                                            f"the recipe still runs on every build, so flip the switch in the "
                                            f"same change that adds it"))
        elif on:
            problems.append((area, "GAP", f"{where} CONFIG_{name}=y, but board.toml:{archives_line} names no "
                                          f"recipe that writes {switch['archive']} -- the switch opens onto a "
                                          f"missing artefact"))
        else:
            producer_line = line_of(repo / switch["known_producer"], switch["known_output"])
            reader_path, reader_needle = switch["known_reader"]
            reader_line = line_of(repo / reader_path, reader_needle)
            detail = ""
            if producer_line:
                detail = (f"; the only producer here, {switch['known_producer']}:{producer_line}, writes "
                          f"{switch['known_output']}/")
                if reader_line:
                    detail += (f" and the 16.6.1 builder reads it there ({reader_path}:{reader_line}), while "
                               f"this generic builder reads {switch['archive']}")
            facts.append((area, "OK", f"closed state: {where} CONFIG_{name} is off and no recipe claims to write "
                                      f"{switch['archive']} -- nothing to produce and nothing to link{detail}"))

        # 3. readable failure: a bare `test -f` dies silently ------------------
        test_index = next((index for index, text in enumerate(lines)
                           if re.match(rf'\s*test -f "\${switch["variable"]}"', text)), None)
        if test_index is None:
            facts.append((area, "NOTE", f"{GENERIC_BUILDER} has no test -f on ${switch['variable']}; the link "
                                        f"block may have moved -- re-anchor this checker"))
        elif readable_failure(lines, test_index):
            facts.append((area, "OK", f"{GENERIC_BUILDER}:{test_index + 1} test -f on "
                                      f"${switch['variable']} reports a message before exiting"))
        else:
            problems.append((area, "GAP", f"{GENERIC_BUILDER}:{test_index + 1} is a bare test -f on "
                                          f"${switch['variable']}; under set -euo pipefail ({GENERIC_BUILDER}:9) "
                                          f"the build exits 1 with no output, so a missing {switch['archive']} "
                                          f"looks like a silent stop -- add `|| {{ echo ...; exit 1; }}`"))
        # Reported, not graded: the builder's own precondition for this switch.
        if switch.get("precondition"):
            facts.append((area, "NOTE", switch["precondition"]))
    return problems, facts


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--profile", default=DEFAULT_PROFILE)
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    repo = args.repo.resolve()

    board = tomllib.loads((repo / "board.toml").read_text(encoding="utf-8"))
    problems, facts = grade(board, repo, args.profile)
    if args.json:
        args.json.write_text(json.dumps({"profile": args.profile, "problems": problems,
                                         "facts": facts}, indent=2) + "\n", encoding="utf-8")
    if not args.quiet:
        for area, status, text in facts + problems:
            print(f"  {status:<4} {area:<13} {text}")
    print(f"ufs27-storage-switches: {len(problems)} gap(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
