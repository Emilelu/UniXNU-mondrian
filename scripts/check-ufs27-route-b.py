#!/usr/bin/env python3
"""Grade the four route-B rings this row owns, without a build.

Route B ships `drivers/NativeUfs` as its own fileset entry instead of forcing its
archive into `com.apple.kernel`, so that its eleven `IOBlockStorageDevice`
imports resolve against the sibling `com.apple.iokit.IOStorageFamily` entry at
prelink time. `docs/research/storage/UFS27-ROUTE-B-WIRING.md` is the checklist;
this script is the part of it that can run today.

Four rings, one row each:

    bundle   a recipe links the storage objects into MH_KEXT_BUNDLE
    plist    drivers/NativeUfs/Info.plist carries the two keys the loader needs
    link     the kernel link no longer force-loads the same objects
    readers  the four acceptance readers exist and parse

The rings are graded for *coherence*, not for completeness, because at stage 0
most of them are legitimately absent. Pending is the expected state and exits 0.
A gap is a state that cannot be true at the same time as another state:

    - the kernel force-loads the archive while a bundle recipe also claims it
      (two carriers, one driver: whichever product loses, it loses silently)
    - the force-load is gone and no bundle recipe exists (the driver is in no
      product at all, and every reader would report "absent", not "broken")
    - a bundle recipe exists but the plist has no CFBundleExecutable
    - the plist carries one of the two keys and not the other
    - an acceptance reader is missing or does not compile

Usage:

    python3 scripts/check-ufs27-route-b.py [--repo .] [--framework <UniXNU>]

Exit code 0 when nothing is incoherent, 1 when a gap is printed. Ring 5 of the
checklist (the prelink emitter cannot add an entry) is not graded here: it is
framework-owned and no product can reach it yet.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import plistlib
import re
import subprocess
from pathlib import Path

STORAGE_ARCHIVE = "build/native-ufs/libNativeUfs.a"
DRIVER_DIR = "drivers/NativeUfs"
PLIST = "drivers/NativeUfs/Info.plist"
BUNDLE_PRODUCER = "NativeUfs.kext"
REQUIRED_LIBRARIES = ("com.apple.iokit.IOStorageFamily", "com.apple.kec.corecrypto")
KERNEL_BUILDERS = ("scripts/build-xnu-generic.sh", "scripts/build-xnu-4k-baseline.sh")
DEFCONFIG = "configs/mondrian_ios27_defconfig"
UFS_SWITCH = "CONFIG_XNU_NATIVE_UFS"
READERS = (
    "scripts/check-ios27-storage-entries.py",
    "scripts/check-ios27-storage-exports.py",
    "scripts/check-ios27-storage-vtable.py",
    "scripts/check-ios27-storage-preflight.py",
)
# A link flag, not prose: `-kext` or `-bundle` as a standalone argument.
BUNDLE_FLAG = re.compile(r"(?<![\w-])-(?:kext|bundle)(?![\w-])")
FORCE_LOAD = re.compile(r"-force_load|force_load,")


def find_framework(repo: Path, explicit: str | None) -> Path | None:
    """Locate a UniXNU checkout; the vendored builder is compared against it."""
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    env = os.environ.get("K60_FRAMEWORK_REPO")
    if env:
        candidates.append(Path(env))
    candidates.append(repo.parent / "UniXNU")
    try:
        common = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        common = ""
    if common:
        gitdir = Path(common)
        if not gitdir.is_absolute():
            gitdir = (repo / gitdir).resolve()
        candidates.append(gitdir.parent.parent)
    for candidate in candidates:
        if (candidate / "scripts" / "unixnu" / "kernel.py").is_file():
            return candidate
    return None


def rel(repo: Path, path: Path) -> str:
    try:
        return path.relative_to(repo).as_posix()
    except ValueError:
        return path.as_posix()


def bundle_recipe(repo: Path) -> tuple[str, str] | None:
    """First *builder* under scripts/ that links a bundle, with its line.

    Graders and verifiers are skipped: a checker that names the flag is not a
    producer, and matching one would make this script grade itself.
    """
    for path in sorted((repo / "scripts").glob("*")):
        if path.suffix not in (".py", ".sh") or not path.is_file():
            continue
        if path.name.startswith(("check-", "verify-", "test-")):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        hits = []
        for number, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or not (BUNDLE_FLAG.search(line) or "MH_KEXT_BUNDLE" in line):
                continue
            # A recipe usually names the flag in a comment and uses it further
            # down; prefer the line that actually invokes the linker.
            weight = 0 if stripped.startswith(("ld", '"$LD', "$LD", "${LD")) else 1
            hits.append((weight, number, stripped))
        if hits:
            hits.sort()
            _weight, number, stripped = hits[0]
            return f"{rel(repo, path)}:{number}", stripped
    return None


def force_load_sites(repo: Path) -> list[str]:
    """Every builder line that force-loads the storage archive.

    The builders assign the archive to a variable first (`UFS_ARCHIVE=…`
    at :647 and `:646-653` respectively), then pass `-Wl,-force_load,$UFS_ARCHIVE`,
    so the match is the force-load of whatever variable holds a native-ufs path.
    """
    sites: list[str] = []  # a site guarded by XNU_NATIVE_UFS_BUNDLE is not a carrier
    for name in KERNEL_BUILDERS:
        path = repo / name
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        holders = {
            match.group(1)
            for line in lines
            if (match := re.match(r"\s*([A-Za-z_]\w*)=(?!=).*(?:native-ufs|NativeUfs)", line))
        }
        for number, line in enumerate(lines, 1):
            if not FORCE_LOAD.search(line):
                continue
            if any("XNU_NATIVE_UFS_BUNDLE" in above for above in lines[max(0, number - 5) : number]):
                # docs/research/storage/UFS27-FORCE-LOAD-REMOVAL.patch guards the
                # block with the bundle switch; with that switch set, route B is
                # the chosen carrier and this block cannot fire.
                continue
            for holder in holders:
                if f"${holder}" in line or f"${{{holder}}}" in line:
                    sites.append(f"{name}:{number}")
                    break
            else:
                if "native-ufs" in line or "NativeUfs" in line:
                    sites.append(f"{name}:{number}")
    return sites


def switch_is_on(path: Path) -> bool:
    """Whether the 27 profile turns the UFS archive on; a dormant block is no carrier."""
    if not path.is_file():
        return False
    match = re.search(
        rf"^{UFS_SWITCH}\s*=\s*\"?([^\"\s#]+)\"?",
        path.read_text(encoding="utf-8", errors="replace"),
        re.MULTILINE,
    )
    return bool(match) and match.group(1).lower() in ("y", "yes", "1", "true")


def read_plist(repo: Path) -> dict | None:
    path = repo / PLIST
    if not path.is_file():
        return None
    try:
        with path.open("rb") as handle:
            return plistlib.load(handle)
    except (OSError, plistlib.InvalidFileException, ValueError):
        return None


def personality_names(plist: dict) -> list[str]:
    personalities = plist.get("IOKitPersonalities") or {}
    if not isinstance(personalities, dict):
        return []
    names: list[str] = []
    for name, body in personalities.items():
        if not isinstance(body, dict):
            continue
        match = body.get("IONameMatch") or body.get("IOMatchCategory") or ""
        if isinstance(match, str) or isinstance(match, list):
            names.append(f"{name} -> {match}")
    return names


def reader_state(repo: Path) -> tuple[list[str], list[str]]:
    """(present, broken) — broken means it will not even compile."""
    present, broken = [], []
    for name in READERS:
        path = repo / name
        if not path.is_file():
            broken.append(f"{name}: missing")
            continue
        present.append(name)
        try:
            compile(path.read_text(encoding="utf-8", errors="replace"), str(path), "exec")
        except SyntaxError as error:
            broken.append(f"{name}: does not compile (line {error.lineno}: {error.msg})")
    return present, broken


def grade(repo: Path, framework: Path | None) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    recipe = bundle_recipe(repo)
    sites = force_load_sites(repo)
    plist = read_plist(repo)
    switch = switch_is_on(repo / DEFCONFIG)
    # A force-load inside `if [ "${XNU_NATIVE_UFS:-0}" = 1 ]` is only a carrier
    # once the switch is on; at stage 0 the block exists and never runs.
    carriers = (len(sites) if switch else 0) + (1 if recipe else 0)

    # --- ring 2: the bundle -------------------------------------------------
    if recipe:
        rows.append(("OK", "bundle", f"a recipe links a bundle: {recipe[0]} `{recipe[1]}`"))
    else:
        rows.append(
            (
                "PEND",
                "bundle",
                "no recipe links a bundle: scripts/*.py|*.sh carry no -kext/-bundle flag and no "
                "MH_KEXT_BUNDLE, so the storage objects only ever become an archive "
                f"({STORAGE_ARCHIVE})",
            )
        )

    # --- ring 3: the plist --------------------------------------------------
    if plist is None:
        rows.append(("OK", "plist", f"{PLIST} is absent; nothing claims a bundle identity"))
    else:
        libraries = plist.get("OSBundleLibraries")
        personalities = personality_names(plist)
        have = libraries if isinstance(libraries, dict) else {}
        missing_libraries = [name for name in REQUIRED_LIBRARIES if name not in have]
        has_libraries = not missing_libraries
        if has_libraries and personalities:
            rows.append(
                (
                    "OK",
                    "plist",
                    f"{PLIST} declares {', '.join(REQUIRED_LIBRARIES)} and {len(personalities)} "
                    f"personalities ({personalities[0]})",
                )
            )
        elif has_libraries or personalities:
            half = "OSBundleLibraries" if has_libraries else "IOKitPersonalities"
            rows.append(
                (
                    "GAP",
                    "plist",
                    f"{PLIST} carries {half} but not both keys -- a bundle with libraries and no "
                    "personality never probes the ufshc node, and one with a personality and no "
                    f"libraries fails dependency planning (missing: {', '.join(missing_libraries) or 'the personality'})",
                )
            )
        else:
            rows.append(
                (
                    "PEND",
                    "plist",
                    f"{PLIST} has neither OSBundleLibraries nor IOKitPersonalities; route B needs "
                    f"{', '.join(REQUIRED_LIBRARIES)} and a personality matching the ufshc node "
                    "(the five keys patches/xnu/ios16-native-ufs-personality.patch installs for route A)",
                )
            )
        if recipe and not plist.get("CFBundleExecutable"):
            rows.append(
                ("GAP", "plist", f"{recipe[0]} links a bundle but {PLIST} has no CFBundleExecutable")
            )

    # --- ring 4: the kernel link -------------------------------------------
    dormant = f" ({DEFCONFIG} has {UFS_SWITCH} off, so the force-load never runs)" if sites and not switch else ""
    if carriers > 1:
        rows.append(
            (
                "GAP",
                "link",
                f"two carriers: {', '.join(sites)} force-loads {STORAGE_ARCHIVE} while {recipe[0]} "
                "also links the same objects into a bundle",
            )
        )
    elif carriers == 0 and switch:
        rows.append(
            (
                "GAP",
                "link",
                f"{UFS_SWITCH} is on and nothing links the storage objects: no builder force-loads "
                f"{STORAGE_ARCHIVE} and no bundle recipe exists, so the switch claims a product that no "
                "carrier builds",
            )
        )
    elif carriers == 0:
        rows.append(
            (
                "PEND",
                "link",
                "no carrier: no builder force-loads the storage archive and no bundle recipe exists, "
                "which is the stage-0 state while the switch is off",
            )
        )
    elif recipe and sites:
        rows.append(
            (
                "OK",
                "link",
                f"one carrier: {recipe[0]} links the bundle{dormant}; the removal of "
                f"{', '.join(sites)} is the Lead's diff, and until it lands the force-load only "
                "returns with the switch",
            )
        )
    elif recipe:
        rows.append(("OK", "link", f"one carrier: {recipe[0]} links the bundle and no builder force-loads {STORAGE_ARCHIVE}"))
    elif switch:
        rows.append(
            (
                "GAP",
                "link",
                f"{UFS_SWITCH} is on and {', '.join(sites)} force-loads {STORAGE_ARCHIVE} into the kernel: "
                "the driver is route A while the switch claims a bundle",
            )
        )
    else:
        rows.append(
            (
                "PEND",
                "link",
                f"{', '.join(sites)} force-loads {STORAGE_ARCHIVE} into the kernel (route A shape), "
                f"and no bundle recipe exists; {UFS_SWITCH} is off, so nothing is linked today",
            )
        )

    # The builder here is a vendored copy; a local edit is a P-255 defect even
    # when the edit itself is correct, because scripts/refresh-xnu-generic.py
    # overwrites the file from the framework checkout.
    if framework is not None:
        here = repo / "scripts" / "build-xnu-generic.sh"
        there = framework / "scripts" / "build-xnu-generic.sh"
        if here.is_file() and there.is_file():
            mine = hashlib.sha256(here.read_bytes()).hexdigest()
            theirs = hashlib.sha256(there.read_bytes()).hexdigest()
            if mine != theirs:
                rows.append(
                    (
                        "NOTE",
                        "link",
                        "the vendored builder differs from the framework copy "
                        f"({mine[:8]} vs {theirs[:8]}); it is refreshed by "
                        "scripts/refresh-xnu-generic.py:15, so the difference belongs upstream",
                    )
                )

    # --- ring 7: the readers ------------------------------------------------
    present, broken = reader_state(repo)
    if broken:
        rows.append(("GAP", "readers", "; ".join(broken)))
    else:
        rows.append(
            (
                "PEND",
                "readers",
                f"{len(present)} readers present and compiling, none runnable yet: each needs a "
                "kernel.macho or kernelcache this host does not have",
            )
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=".", help="device repository checkout")
    parser.add_argument("--framework", default=None, help="UniXNU checkout to resolve the builder")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    framework = find_framework(repo, args.framework)

    print(f"repo      {repo.as_posix()}")
    print(f"framework {(framework.as_posix() if framework else 'not found')}")
    rows = grade(repo, framework)
    for status, area, text in rows:
        print(f"  {status:<4} {area:<8} {text}")
    gaps = sum(1 for status, _, _ in rows if status == "GAP")
    pending = sum(1 for status, _, _ in rows if status == "PEND")
    print(f"ufs27-route-b: {gaps} gap(s), {pending} pending")
    return 1 if gaps else 0


if __name__ == "__main__":
    raise SystemExit(main())
