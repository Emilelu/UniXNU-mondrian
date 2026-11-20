#!/usr/bin/env python3
"""Compile the board device tree the way the payload step does, before building.

`dts/mondrian.dts` is consumed exactly once in the whole toolchain: the payload
step runs `dtc` on it (`scripts/unixnu/devicetree.py:407-411`) to produce
`device-tree/hardware.dtb`. Nothing else in the repository parses it, so a
syntax error in that file survives every gate and surfaces eight build steps
later -- which is how `585fe75a` left a bare comment body at line 100 for a day
and stopped both the 27 and the 16.6.1 payload (P-275).

This script is the missing early consumer. It reads `[device_tree]` from
`board.toml`, resolves the source and every `include_dirs` entry through the
same prefix rules the framework uses (`scripts/unixnu/profiles.py:68-83`), and
runs `dtc` on it.

    scripts/check-device-tree.py [--device <repo>] [--soc <feed checkout>] \
        [--out <out tree>] [--dtc <path>] [--keep]

Exit 0 when dtc accepts the tree, 1 when it does not (dtc's own message is
printed verbatim -- the line and column are the whole point), and 2 when the
tree cannot be found, which is a different problem from a broken one.

`soc:` include directories live in the fetched SoC feed, not in this
repository, so when `--soc` is not given the script looks for a feed under
`--out <out>/feeds/UniXNU-*-common-*` that actually contains the includes the
source asks for. If it cannot find one it says so and exits 2 rather than
declaring the tree fine.
"""
from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import sys
import tempfile

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - python < 3.11
    tomllib = None


def read_board(device: pathlib.Path) -> dict:
    if tomllib is None:
        raise SystemExit("python 3.11 or newer is required to read board.toml")
    with (device / "board.toml").open("rb") as handle:
        return tomllib.load(handle)


def includes_wanted(source: pathlib.Path) -> list[str]:
    """The /include/ directives in the source, as written."""
    wanted = []
    for line in source.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith('/include/'):
            parts = stripped.split('"')
            if len(parts) >= 2:
                wanted.append(parts[1])
    return wanted


def find_soc_feed(out: pathlib.Path, wanted: list[str]) -> pathlib.Path | None:
    """The fetched feed whose dts/ directory supplies every /include/ name."""
    feeds = out / "feeds"
    if not feeds.is_dir():
        return None
    for candidate in sorted(feeds.iterdir()):
        dts = candidate / "dts"
        if dts.is_dir() and all((dts / name).is_file() for name in wanted):
            return dts
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", type=pathlib.Path, default=pathlib.Path("."))
    parser.add_argument("--soc", type=pathlib.Path,
                        help="directory holding the SoC includes (feed's dts/), or a feed root")
    parser.add_argument("--out", type=pathlib.Path,
                        help="output tree to search for the feed when --soc is not given")
    parser.add_argument("--dtc", default="dtc")
    parser.add_argument("--keep", action="store_true", help="keep the compiled dtb and print its path")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    device = args.device.resolve()
    if not (device / "board.toml").is_file():
        print(f"NO TREE no board.toml under {device}")
        return 2

    spec = read_board(device).get("device_tree", {})
    source_ref = spec.get("source")
    if not source_ref:
        print("NO TREE board.toml has no [device_tree].source")
        return 2
    source = device / source_ref.partition(":")[2] if ":" in source_ref else device / source_ref
    if not source.is_file():
        print(f"NO TREE the device tree source is not on disk: {source}")
        return 2

    include_dirs: list[pathlib.Path] = []
    wanted = includes_wanted(source)
    for entry in spec.get("include_dirs", []):
        prefix, _, relative = str(entry).partition(":")
        if prefix == "soc":
            if args.soc is not None:
                root = args.soc.resolve()
                # Accept either the feed root or its dts/ directory.
                root = root if (root / relative).is_dir() else root
                include_dirs.append(root if root.name == relative else root / relative)
                continue
            if args.out is None:
                print(f"NO TREE include_dirs has {entry!r} but neither --soc nor --out was given")
                return 2
            found = find_soc_feed(args.out.resolve(), wanted)
            if found is None:
                print(f"NO TREE no feed under {args.out.resolve() / 'feeds'} supplies "
                      f"{', '.join(wanted) or 'the includes'}; pass --soc")
                return 2
            include_dirs.append(found)
        else:
            include_dirs.append(device / relative)

    dtc = shutil.which(args.dtc) if not pathlib.Path(args.dtc).is_file() else args.dtc
    if dtc is None:
        print(f"NO TOOL dtc is not on PATH ({args.dtc}); apt-get install device-tree-compiler")
        return 2

    workdir = pathlib.Path(tempfile.mkdtemp(prefix="k60-dts-"))
    output = workdir / "hardware.dtb"
    command = [str(dtc), "-I", "dts", "-O", "dtb", "-o", str(output)]
    for directory in include_dirs:
        command += ["-i", str(directory)]
    command.append(str(source))

    done = subprocess.run(command, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        print(f"FAIL dtc rejected {source.relative_to(device)}")
        for line in (done.stdout + done.stderr).strip().splitlines():
            print(f"  {line}")
        return 1

    size = output.stat().st_size if output.is_file() else 0
    if not args.quiet:
        nodes = subprocess.run([str(dtc), "-I", "dtb", "-O", "dts", str(output)],
                               capture_output=True, text=True, check=False)
        count = sum(1 for line in nodes.stdout.splitlines() if line.strip().endswith("{")) if nodes.returncode == 0 else 0
        print(f"OK {source.relative_to(device)} compiles: {size} bytes, {count} nodes")
        for directory in include_dirs:
            print(f"  include {directory}")
    if args.keep:
        print(f"  kept {output}")
    else:
        shutil.rmtree(workdir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
