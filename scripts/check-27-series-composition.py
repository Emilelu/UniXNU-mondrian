#!/usr/bin/env python3
"""Print the 27 patch series the way the framework resolves it, not the way a
device-only checkout would.

`board.toml:369` lists four layers:

    patch_series = ["arch:patches/xnu/series", "soc:patches/xnu-12377/series",
                    "os:patches/xnu/series", "device:patches/xnu-12377/series"]

Each `arch:` / `soc:` / `os:` / `device:` prefix is resolved against
`ctx.profile_roots` (scripts/unixnu/profiles.py:45), and those roots live in the
FRAMEWORK tree plus the fetched SoC feed -- not in the device repository. Read
from the device repository alone, `arch:patches/xnu/series` and
`os:patches/xnu/series` both point at `profiles/...` which does not exist there,
so they silently resolve to nothing and the composition looks 3-4 patches
shorter. A replay built on that shorter list applies the OS layer's
`zzz-boot-progress.patch` before the SoC layer's `sheng-platform-power.patch`
has inserted the `sheng_pmgr_run()` context its fourth hunk needs, and the
replay reports "the 27 series cannot be applied from a clean tree" (P-266).

This script exists so that claim can be checked in one command.

    scripts/check-27-series-composition.py --framework <fw> --device <dev> \
        [--soc <feed checkout>] [--log <build log>]

With --log it compares the composition against the `== kernel: patch NAME`
lines a real build printed and exits 1 on any difference. Without --log it
prints the composition and the per-layer counts.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - python < 3.11
    tomllib = None

PREFIXES = ("arch", "soc", "os", "device")


def read_series(path: pathlib.Path) -> list[str]:
    """Entries of one series file, as bare basenames, in order."""
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        out.append(entry.split("/")[-1])
    return out


def board_kernel(device: pathlib.Path, profile: str | None) -> dict:
    if tomllib is None:
        raise SystemExit("python 3.11 or newer is required to read board.toml")
    with (device / "board.toml").open("rb") as handle:
        data = tomllib.load(handle)
    chosen = dict(data.get("os_overrides", {}).get(profile or data["board"]["os_profile"], {}))
    chosen.pop("remove", None)
    kernel = dict(data.get("kernel", {}))
    kernel.update(chosen.get("kernel", {}))
    return kernel


def roots(framework: pathlib.Path, device: pathlib.Path, soc: pathlib.Path | None,
          profile: str) -> dict[str, pathlib.Path]:
    arch = "arm64"
    profile_toml = framework / "profiles" / "os" / profile / "profile.toml"
    if profile_toml.is_file() and tomllib is not None:
        with profile_toml.open("rb") as handle:
            arch = tomllib.load(handle).get("os", {}).get("arch", "arm64")
    table = {
        "arch": framework / "profiles" / "arch" / arch,
        "os": framework / "profiles" / "os" / profile,
        "device": device,
    }
    if soc is not None:
        table["soc"] = soc
    return table


def composition(framework: pathlib.Path, device: pathlib.Path, soc: pathlib.Path | None,
                profile: str | None) -> tuple[list[tuple[str, str]], dict[str, int]]:
    kernel = board_kernel(device, profile)
    profile = profile or None
    if profile is None:
        with (device / "board.toml").open("rb") as handle:
            profile = tomllib.load(handle)["board"]["os_profile"]
    table = roots(framework, device, soc, profile)
    layers: list[tuple[str, str]] = []
    counts: dict[str, int] = {}
    for reference in kernel.get("patch_series") or []:
        prefix, sep, rest = str(reference).partition(":")
        if not sep:
            prefix, rest = "device", str(reference)
        root = table.get(prefix)
        if root is None:
            raise SystemExit(f"no root for prefix {prefix!r} ({reference}); pass --soc")
        series = root / rest
        names = read_series(series)
        counts[f"{prefix}:{rest}"] = len(names)
        layers.extend((prefix, name) for name in names)
    return layers, counts


def from_log(path: pathlib.Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return re.findall(r"^== kernel: patch (\S+)", text, re.MULTILINE)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--framework", required=True, type=pathlib.Path)
    parser.add_argument("--device", required=True, type=pathlib.Path)
    parser.add_argument("--soc", type=pathlib.Path)
    parser.add_argument("--profile")
    parser.add_argument("--log", type=pathlib.Path)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    layers, counts = composition(args.framework, args.device, args.soc, args.profile)
    names = [name for _, name in layers]

    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        print(f"FAIL the composition applies a patch twice: {', '.join(duplicates)}")
        return 1

    if not args.quiet:
        for layer, name in layers:
            print(f"{layer:<7} {name}")
        print()
        for reference, count in counts.items():
            print(f"{reference:<32} {count}")
        print(f"{'total':<32} {len(names)}")

    if args.log is None:
        return 0

    applied = from_log(args.log)
    if applied == names:
        print(f"OK the composition matches the build: {len(names)} patches, same order")
        return 0

    print(f"FAIL composition has {len(names)} patches, the build applied {len(applied)}")
    if len(names) != len(applied):
        longer, shorter = ("composition", "build") if len(names) > len(applied) else ("build", "composition")
        print(f"  {longer} has more than {shorter}")
    for index, (want, got) in enumerate(zip(names, applied)):
        if want != got:
            print(f"  first difference at position {index + 1}: composition {want!r}, build {got!r}")
            break
    else:
        print(f"  the first {min(len(names), len(applied))} agree")
    only_composition = [name for name in names if name not in applied]
    only_build = [name for name in applied if name not in names]
    if only_composition:
        print(f"  only in composition: {', '.join(only_composition)}")
    if only_build:
        print(f"  only in the build: {', '.join(only_build)}")
    return 1


if __name__ == "__main__":
    sys.exit(main())