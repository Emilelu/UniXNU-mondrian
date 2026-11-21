#!/usr/bin/env python3
"""check-ufs27-storage-selection.py -- does the 27 profile reach the storage archive?

Static, offline, no build. It answers the one question the Data gate turns on:
*can this checkout produce the archive the 27 builder force-loads?* Three
independent pieces have to line up, and each fails on its own:

  1. selection   -- every identifier in the 27 `components.include` must resolve
                    against the framework catalog. The framework only accepts a
                    `legacy_name` identifier (NativeUfs is ShengUfs's legacy
                    name) when it already holds a *module* for that component,
                    and modules come from feeds: `components.selected()` in
                    UniXNU/scripts/unixnu/components.py:22-45 and
                    `official_alias()` at :87-95. This checker therefore treats
                    an alias as resolvable only when a feed or a submodule in
                    this repository names the component's own repository --
                    a vendored directory is not a module.
  2. production  -- `CONFIG_XNU_NATIVE_UFS=y` turns on the link in
                    scripts/build-xnu-generic.sh:646-653, which force-loads
                    $ROOT/build/native-ufs/libNativeUfs.a.  `test -f` on that
                    path means the build stops there unless a recipe in
                    27 `kernel.archives` writes exactly that file.  Script
                    entries are resolved by UniXNU/scripts/unixnu/kernel.py:141-175.
  3. link        -- eleven IOBlockStorageDevice symbols are not in the 27 kernel
                    collection's export set (docs/engineering/IOS27.md:385-396).
                    Recorded here as a note, not graded: that half belongs to the
                    storage-abi bindings, not to this repository's config.

Usage:
  python3 scripts/check-ufs27-storage-selection.py [--profile ios-27.0.1-24A446]
      [--framework E:/hackios/UniXNU] [--json out.json] [--quiet]

Exit 0 when every graded piece lines up, 1 when a piece is missing. `--quiet`
prints only the verdict line, so a build script can gate on it.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

REPO = Path(os.environ.get("K60_REPO") or Path(__file__).resolve().parents[1])
DEFAULT_PROFILE = "ios-27.0.1-24A446"
UFS_ARCHIVE = "build/native-ufs/libNativeUfs.a"
GENERIC_BUILDER = "scripts/build-xnu-generic.sh"
# A representative subset of the eleven undefined storage symbols, spelled as
# llvm-nm prints them; the full list is in docs/engineering/IOS27.md:385-396.
SAMPLE_SYMBOLS = (
    "__ZTV20IOBlockStorageDevice",
    "__ZN20IOBlockStorageDevice4initEP12OSDictionary",
    "__ZN20IOBlockStorageDevice4freeEv",
    "__ZN20IOBlockStorageDevice5startEP9IOService",
    "__ZN20IOBlockStorageDevice18doAsyncReadWriteEP16IOMemoryDescriptoryyP18IOStorageAttributesP18IOStorageCompletion",
)


def main_checkout():
    """Root of the canonical checkout this worktree belongs to, or None."""
    try:
        common = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--git-common-dir"],
                                capture_output=True, text=True, timeout=20, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    path = Path(common)
    if not path.is_absolute():
        path = (REPO / path).resolve()
    # <checkout>/.git/worktrees/<name> and <checkout>/.git both reduce to <checkout>.
    for parent in path.parents:
        if (parent / ".git").exists() and not (parent / ".git").is_symlink():
            return parent
    return path.parent


def framework_repo(explicit):
    root = main_checkout()
    candidates = [explicit, os.environ.get("K60_FRAMEWORK_REPO"), REPO.parent / "UniXNU"]
    if root:
        candidates.append(root.parent / "UniXNU")
    for candidate in candidates:
        if candidate and (Path(candidate) / "components.toml").is_file():
            return Path(candidate).resolve()
    return None


def source_identity(url):
    value = re.sub(r"^git@([^:]+):", r"https://\1/", url or "")
    value = re.sub(r"^ssh://git@", "https://", value)
    value = re.sub(r"^https?://", "", value).rstrip("/")
    return value.removesuffix(".git").lower()


def declared_sources(repo):
    """Every repository this checkout could fetch: feeds, submodules, board pins."""
    urls = []
    feeds = repo / "feeds.toml"
    if feeds.is_file():
        data = tomllib.loads(feeds.read_text(encoding="utf-8"))
        for source in data.get("source", []):
            urls.append(source.get("git", ""))
    for base in (repo, repo.parent):
        modules = base / ".gitmodules"
        if modules.is_file():
            urls += re.findall(r"url\s*=\s*(\S+)", modules.read_text(encoding="utf-8"))
    board = repo / "board.toml"
    if board.is_file():
        urls += re.findall(r'git\s*=\s*"([^"]+)"', board.read_text(encoding="utf-8"))
    return {source_identity(url) for url in urls if url}


def catalog(framework):
    entries = tomllib.loads((framework / "components.toml").read_text(encoding="utf-8")).get("component", [])
    return {entry["id"]: entry for entry in entries}


def profile(board, name):
    overrides = board.get("os_overrides", {})
    if name not in overrides:
        raise SystemExit(f"board.toml: no os_overrides entry {name!r}")
    return overrides[name]


def line_of(path, needle):
    """1-based line number of the first line containing needle, or None."""
    if not path.is_file():
        return None
    for number, text in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if needle in text:
            return number
    return None


def grade(board, entries, sources, profile_name, repo):
    problems, facts = [], []
    override = profile(board, profile_name)
    include = override.get("components", {}).get("include", [])
    archives = override.get("kernel", {}).get("archives", [])
    defconfig_name = override.get("kernel", {}).get("defconfig", "")
    defconfig = REPO / "configs" / defconfig_name
    board_line = (line_of(repo / "board.toml", '"NativeUfs"')
                  or line_of(repo / "board.toml", 'include = ["ArmDTPlatform"'))
    archives_line = line_of(repo / "board.toml", f'"{archives[-1]}"') if archives else None
    defconfig_line = line_of(defconfig, "CONFIG_XNU_NATIVE_UFS")

    # 1. selection -----------------------------------------------------------
    for identifier in include:
        if identifier in entries:
            facts.append(("selection", "OK", f"board.toml:{board_line} include {identifier!r} is a catalog id"))
            continue
        spec = next((e for e in entries.values() if e.get("legacy_name") == identifier), None)
        if spec is None:
            problems.append(("selection", "GAP",
                             f"board.toml:{board_line} include {identifier!r} is neither a catalog id nor a legacy name"))
            continue
        wanted = {source_identity(spec.get("repository", "")), "github.com/unixnu/" + identifier.lower()}
        hit = sorted(wanted & sources)
        if hit:
            facts.append(("selection", "OK",
                          f"board.toml:{board_line} include {identifier!r} is a legacy name for {spec['id']}; "
                          f"a declared source names that repository ({hit[0]})"))
        else:
            problems.append(("selection", "GAP",
                             f"board.toml:{board_line} include {identifier!r} is {spec['id']}'s legacy name, but no feed "
                             f"or submodule names {source_identity(spec.get('repository', ''))} -- components.selected() "
                             f"raises 'unknown component: {identifier}' before any recipe runs"))

    # 2. production ----------------------------------------------------------
    recipe = next((entry for entry in archives if "build-native-ufs-linux.py" in entry), None)
    if recipe is None:
        problems.append(("production", "GAP",
                         f"board.toml:{archives_line} kernel.archives names no build-native-ufs-linux.py recipe, so "
                         f"{UFS_ARCHIVE} is never written and {GENERIC_BUILDER}:648 test -f fails"))
    elif "--out build/native-ufs" not in recipe:
        problems.append(("production", "GAP",
                         f"the recipe {recipe!r} does not pass --out build/native-ufs, so it writes "
                         f"out/native-ufs-linux/libNativeUfs.a while the builder reads {UFS_ARCHIVE}"))
    else:
        facts.append(("production", "OK", f"board.toml:{archives_line} recipe {recipe!r} writes {UFS_ARCHIVE}"))

    # 3. switch agreement ----------------------------------------------------
    if defconfig_line and not recipe:
        problems.append(("switch", "GAP",
                         f"{defconfig.relative_to(REPO)}:{defconfig_line} CONFIG_XNU_NATIVE_UFS=y, but the archive it "
                         f"links has no producer in this profile"))
    elif defconfig_line:
        facts.append(("switch", "OK", f"{defconfig.relative_to(REPO)}:{defconfig_line} CONFIG_XNU_NATIVE_UFS=y "
                                     f"agrees with the recipe above"))

    # 4. link note -----------------------------------------------------------
    facts.append(("link", "NOTE",
                  f"eleven IOBlockStorageDevice symbols stay undefined until the storage-abi bindings land "
                  f"(docs/engineering/IOS27.md:385-396, e.g. {SAMPLE_SYMBOLS[0]}); not graded here"))
    return problems, facts


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--profile", default=DEFAULT_PROFILE)
    parser.add_argument("--framework", type=Path, default=None)
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    framework = framework_repo(args.framework)
    if framework is None:
        raise SystemExit("no framework checkout: pass --framework or set K60_FRAMEWORK_REPO")
    board = tomllib.loads((REPO / "board.toml").read_text(encoding="utf-8"))
    problems, facts = grade(board, catalog(framework), declared_sources(REPO), args.profile, REPO)

    if args.json:
        args.json.write_text(json.dumps({"profile": args.profile, "framework": str(framework),
                                         "problems": problems, "facts": facts}, indent=2) + "\n",
                             encoding="utf-8")
    if not args.quiet:
        for area, status, text in facts + problems:
            print(f"  {status:<4} {area:<11} {text}")
    print(f"ufs27-storage-selection: {len(problems)} gap(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
