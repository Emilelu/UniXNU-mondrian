#!/usr/bin/env python3
"""Unit tests for check-image-args.py.

The gate exists because two hand-packaged images on 2026-11-14 replaced a board
argument and overflowed the DarwinBoot ceiling; both boots produced zero console
bytes.  These cases pin the three shapes it must catch and the one it must pass.
"""
from __future__ import annotations

import pathlib
import struct
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "check-image-args.py"

PAGE = 4096
MAGIC = b"ANDROID!"
HEADER_SIZE_V4 = 1584
SHIM_BYTES = 112


def page_up(n):
    return (n + PAGE - 1) // PAGE * PAGE


def make_image(path: pathlib.Path, args: str, board: pathlib.Path) -> None:
    """Build the smallest image the gate can read: header + fake payload FAT."""
    import shutil

    mtools = shutil.which("mformat")
    if mtools is None:
        raise SystemExit("mformat not found (install mtools)")

    vol = pathlib.Path(tempfile.mkdtemp()) / "payload.img"
    subprocess.run([mtools, "-C", "-i", str(vol), "-T", "65536", "::"], check=True)
    subprocess.run(["mmd", "-i", str(vol), "::/EFI"], check=True)
    subprocess.run(["mmd", "-i", str(vol), "::/EFI/UniXNU"], check=True)
    toml = pathlib.Path(tempfile.mkdtemp()) / "unixnu.toml"
    toml.write_text(f'[[entry]]\nid = "xnu"\nargs = "{args}"\n')
    subprocess.run(["mcopy", "-i", str(vol), str(toml), "::/EFI/UniXNU/unixnu.toml"], check=True)

    rslot = vol.read_bytes()
    kslot = b"\x00" * 512
    header = bytearray(PAGE)
    header[0:8] = MAGIC
    struct.pack_into("<2I", header, 8, len(kslot), len(rslot))
    struct.pack_into("<I", header, 20, HEADER_SIZE_V4)
    struct.pack_into("<I", header, 40, 4)
    path.write_bytes(bytes(header) + kslot.ljust(page_up(len(kslot)), b"\x00") + rslot)


def run_gate(image: pathlib.Path, board: pathlib.Path):
    proc = subprocess.run([sys.executable, str(GATE), "--image", str(image),
                           "--board", str(board)], capture_output=True, text=True)
    return proc.returncode, proc.stdout


def main() -> int:
    tmp = pathlib.Path(tempfile.mkdtemp())
    board = tmp / "board.toml"
    board.write_text(
        '[payload]\n'
        'kernel_args = ["-v", "native-ufs=1", "debug=0x140", "epoch=1793709100"]\n')

    failures = 0

    def check(label, want_rc, want_text=None, args=None):
        nonlocal failures
        image = tmp / "boot.img"
        make_image(image, args, board)
        rc, out = run_gate(image, board)
        ok = rc == want_rc
        if want_text and want_text not in out:
            ok = False
        print(f"{'PASS' if ok else 'FAIL'} {label}")
        if not ok:
            failures += 1
            print(f"      rc={rc} want={want_rc}")
            for line in out.splitlines():
                print("      " + line)

    check("the board contract passes", 0,
          "image-arg-audit: OK",
          "-v native-ufs=1 debug=0x140 epoch=1793709100")

    check("a declared addition passes", 0,
          "image-arg-audit: OK",
          "-v native-ufs=1 debug=0x140 epoch=1793709100 pong_rail_probe=1")

    check("debug=1 is refused", 1,
          "DB_HALT",
          "-v native-ufs=1 debug=1 epoch=1793709100")

    check("a replaced board value is refused", 1,
          "was replaced",
          "-v native-ufs=1 debug=0x140 epoch=1")

    check("an undeclared addition is refused", 1,
          "not a declared addition",
          "-v native-ufs=1 debug=0x140 epoch=1793709100 mystery_flag=1")

    check("a missing board argument is refused", 1,
          "is missing from the image",
          "-v native-ufs=1 debug=0x140")

    long_args = "-v native-ufs=1 debug=0x140 epoch=1793709100 " + " ".join(
        f"k60bt_stage={i}" for i in range(40))
    check("a line over 607 bytes is refused", 1,
          "DarwinBoot accepts at most 607",
          long_args)

    if failures:
        print(f"TESTS OK 0 cases ({failures} failure(s))")
        return 1
    print("TESTS OK 7 cases (0 failure(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
