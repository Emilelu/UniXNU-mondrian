#!/usr/bin/env python3
"""Audit the kernel command line that a boot image actually carries.

Why this exists: on 2026-11-14 two sub-agents could not build through
build-strict.sh (the eight-step flash gate was red on the touch line), so they
packaged images by hand with `unixnu build payload --kernel-arg ...`.  Nobody
looked at the resulting command line:

  * bt-s1-20261114b  610 bytes -> over DarwinBoot's 607-byte ceiling
                     (BootArgs.h: DARWIN_BOOT_LINE_LENGTH 608, DarwinBoot.c:681
                     rejects Index >= sizeof(CommandLine) - 1)
  * wifi-20261115a   replaced debug=0x140 with debug=1 -> DB_HALT, so any debug
                     trap halts, and replaced epoch with 1

Both boots produced zero console bytes and looked like kernel faults.

This gate reads the command line back out of the image, compares it with the
board contract, and refuses a line that could not have come from board.toml
plus a declared, documented addition.
"""
from __future__ import annotations

import argparse
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile
import tomllib
import zlib

PAGE = 4096
MAGIC = b"ANDROID!"
HEADER_SIZE_V4 = 1584
SHIM_BYTES = 112

# DarwinBoot: CHAR8 CommandLine[DARWIN_BOOT_LINE_LENGTH] with
# DARWIN_BOOT_LINE_LENGTH == 608 and the check `Index >= sizeof(CommandLine) - 1`.
DARWIN_BOOT_LINE_MAX = 607

# Additions that a per-line experiment may append to the board contract.  Every
# name here must also be documented in docs/engineering/BOOT-ARGS.md.
ALLOWED_ADDITIONS = {
    "pong_wifi", "k60_wifi_rsc", "k60_wifi_stage", "pong_wifi_dma_mib",
    "pong_wifi_diag", "pong_wifi_test", "pong_wifi_alt", "pong_wifi_band",
    "pong_wifi_cycle", "k60bt", "k60bt_stage", "k60bt_warm",
    "pong_audio_probe", "pong_rail_probe", "pong_adsp", "pong_touch_se",
}

# Values that are never acceptable in an experiment image, with the reason.
FORBIDDEN = {
    "debug=1": "DB_HALT (debug.h:513): any debug trap halts the kernel, so the "
               "boot stops silently. Use debug=0x140.",
    "epoch=1": "epoch=1 resets the clock baseline; keep the board value.",
}


def page_up(n: int) -> int:
    return (n + PAGE - 1) // PAGE * PAGE


def read_fat_file(volume: pathlib.Path, inner: str):
    tool = shutil.which("mtype")
    if tool is None:
        raise SystemExit("image-arg-audit: mtype not found (install mtools)")
    proc = subprocess.run([tool, "-i", str(volume), f"::{inner}"],
                          capture_output=True)
    if proc.returncode != 0:
        return None
    return proc.stdout


def image_args(image: pathlib.Path) -> list[str]:
    data = image.read_bytes()
    if len(data) < PAGE or data[:8] != MAGIC:
        raise SystemExit(f"image-arg-audit: {image.name} is not an Android boot image")
    ksize, rsize = struct.unpack_from("<2I", data, 8)
    hsize = struct.unpack_from("<I", data, 20)[0]
    hver = struct.unpack_from("<I", data, 40)[0]
    if hver != 4 or hsize != HEADER_SIZE_V4:
        raise SystemExit(f"image-arg-audit: header_version={hver} header_size={hsize}, this gate covers v4")

    r_off = PAGE + page_up(ksize)
    if r_off + rsize > len(data):
        raise SystemExit("image-arg-audit: ramdisk slot runs past the end of the file")
    rslot = data[r_off:r_off + rsize]

    with tempfile.NamedTemporaryFile(suffix=".img", delete=False) as tmp:
        tmp.write(rslot)
        vol = pathlib.Path(tmp.name)
    try:
        toml = read_fat_file(vol, "EFI/UniXNU/unixnu.toml")
    finally:
        vol.unlink(missing_ok=True)
    if toml is None:
        raise SystemExit("image-arg-audit: payload FAT has no EFI/UniXNU/unixnu.toml")

    text = toml.decode("utf-8", "replace")
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("args"):
            continue
        if "=" not in s:
            continue
        value = s.split("=", 1)[1].strip()
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        return value.split()
    raise SystemExit("image-arg-audit: payload TOML has no args entry")


def board_args(board: pathlib.Path) -> list[str]:
    """board.toml carries the contract under [payload] (measured, line 184)."""
    data = tomllib.loads(board.read_text())
    for section in ("payload", "kernel"):
        args = (data.get(section) or {}).get("kernel_args")
        if args:
            return list(args)
    raise SystemExit(f"image-arg-audit: {board} has no [payload].kernel_args")


def split_pair(token: str):
    if "=" not in token:
        return token, None
    name, value = token.split("=", 1)
    return name, value


def audit(image: pathlib.Path, board: pathlib.Path) -> list[str]:
    problems: list[str] = []
    got = image_args(image)
    want = board_args(board)

    line = " ".join(got)
    if len(line) > DARWIN_BOOT_LINE_MAX:
        problems.append(
            f"command line is {len(line)} bytes; DarwinBoot accepts at most "
            f"{DARWIN_BOOT_LINE_MAX} (BootArgs.h:608, DarwinBoot.c:681)")

    for token in got:
        reason = FORBIDDEN.get(token)
        if reason:
            problems.append(f"forbidden argument {token}: {reason}")

    board_pairs = dict(split_pair(t) for t in want)
    got_pairs = dict(split_pair(t) for t in got)

    for name, value in got_pairs.items():
        if name not in board_pairs:
            if name not in ALLOWED_ADDITIONS:
                problems.append(
                    f"argument {name} is not in board.toml kernel_args and is not a "
                    f"declared addition (ALLOWED_ADDITIONS in this gate)")
            continue
        if board_pairs[name] != value:
            problems.append(
                f"argument {name} was replaced: board.toml has {board_pairs[name]!r}, "
                f"the image has {value!r}")

    for name, value in board_pairs.items():
        if name not in got_pairs:
            problems.append(f"argument {name}={value} from board.toml is missing from the image")

    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image", required=True, type=pathlib.Path)
    ap.add_argument("--board", type=pathlib.Path,
                    default=pathlib.Path(__file__).resolve().parents[1] / "board.toml")
    args = ap.parse_args()

    if not args.image.is_file():
        print(f"image-arg-audit: no such image: {args.image}")
        return 2
    problems = audit(args.image, args.board)
    if problems:
        print("image-arg-audit: REFUSED")
        for p in problems:
            print("  -", p)
        return 1
    got = image_args(args.image)
    print(f"image-arg-audit: OK ({len(got)} arguments, {len(' '.join(got))} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
