#!/usr/bin/env python3
"""Board-input preflight for the iOS 27 image (mondrian).

Loader-source questions belong to `scripts/check-ios27-firmware.py`; this gate
covers what that one does not read: the board inputs the build consumes, the FD
window, and the protocol revision DarwinBoot compares at handoff.

Runs in the EDK II build tree, before the firmware is built, through
`[firmware] preflight` in the device repository's board.toml:

    [firmware]
    preflight = ["scripts/check-ios27-board-inputs.py"]

The build driver runs `python3 <script> [args...]` with the working directory set
to the assembled build tree and `UNIXNU_DEVICE` / `UNIXNU_UEFI` exported.

Every check answers one question and prints one line. The exit code is the only
thing the build driver reads:

    0   every check passed
    1   at least one check failed  -- the build must stop
    2   no check failed, but at least one could not be judged because an input
        is absent -- "cannot judge" is not a pass, so the build stops too

`--allow-unknown` turns 2 into 0 for the case where a check is structurally
unjudgeable in offline work; it never turns 1 into 0.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tomllib
from dataclasses import dataclass, asdict
from pathlib import Path

PASS, FAIL, UNKNOWN = "pass", "fail", "unknown"

# The four EDK II modules the boot path needs; the paths are the ones the
# porting page lists (docs/zh/porting/uefi-firmware.md, "UniXNU 和 DarwinBoot
# 通过 INF 加入").
REQUIRED_MODULES = (
    "Platforms/Xiaomi/UniXNUPkg/Application/UniXNU/UniXNU.inf",
    "Platforms/Xiaomi/UniXNUPkg/Driver/UniXNUDxe/UniXNUDxe.inf",
    "Platforms/Xiaomi/UniXNUPkg/Driver/UniXNURamDiskDxe/UniXNURamDiskDxe.inf",
    "Platforms/Xiaomi/DarwinBootPkg/Driver/DarwinBoot.inf",
)

# The fileset loader landed in revision 0x00020000: before it, DarwinBoot
# rejected any image carrying kexts, which is every iOS 27 kernel.
MIN_LOADER_REVISION = 0x0002_0000
LOADER_HEADER = "Platforms/Xiaomi/UniXNUPkg/Include/Protocol/UniXNULoader.h"

UUID_RE = re.compile(r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$")


@dataclass
class Result:
    check: str
    state: str
    detail: str


def load_toml(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def check_board(board: dict) -> Result:
    firmware = board.get("firmware")
    if not firmware:
        return Result("board", FAIL, "board.toml has no [firmware] table")
    for key in ("config", "dsc", "fd"):
        if not firmware.get(key):
            return Result("board", FAIL, f"[firmware] is missing {key!r}")
    return Result("board", PASS, f"config={firmware['config']} dsc={firmware['dsc']}")


def check_dsc(uefi: Path | None, board: dict) -> Result:
    if uefi is None:
        return Result("dsc", UNKNOWN, "no UEFI checkout given (--uefi or UNIXNU_UEFI)")
    firmware = board.get("firmware") or {}
    if not firmware.get("dsc"):
        return Result("dsc", UNKNOWN, "no [firmware] dsc to look for")
    dsc = uefi / firmware["dsc"]
    if not dsc.is_file():
        return Result("dsc", FAIL, f"missing {dsc}")
    return Result("dsc", PASS, str(dsc))


def check_modules(uefi: Path | None) -> Result:
    if uefi is None:
        return Result("modules", UNKNOWN, "no UEFI checkout given")
    missing = [rel for rel in REQUIRED_MODULES if not (uefi / rel).is_file()]
    if missing:
        return Result("modules", FAIL, "missing " + ", ".join(missing))
    return Result("modules", PASS, f"{len(REQUIRED_MODULES)} modules present")


def check_fd_window(uefi: Path | None, config_name: str) -> Result:
    """The FD must sit on a 4 KiB boundary, be a whole number of blocks, and,
    once built, must not have outgrown its reserved window."""
    if uefi is None:
        return Result("fd-window", UNKNOWN, "no UEFI checkout given")
    cfg_path = uefi / "Resources/Configs" / f"{config_name}.toml"
    if not cfg_path.is_file():
        return Result("fd-window", FAIL, f"missing {cfg_path}")
    section = load_toml(cfg_path).get("uefi_fd")
    if not section:
        return Result("fd-window", FAIL, f"{cfg_path} has no [uefi_fd]")
    base, size = section.get("base"), section.get("size")
    if not isinstance(base, int) or not isinstance(size, int):
        return Result("fd-window", FAIL, "[uefi_fd] base/size must be integers")
    if base % 0x1000 or size % 0x1000 or size <= 0:
        return Result("fd-window", FAIL, f"base={base:#x} size={size:#x} not 4 KiB aligned")
    built = uefi / "Build" / "mondrianPkg"
    candidates = sorted(built.glob("*/FV/SILICIUM_UEFI.fd")) if built.is_dir() else []
    if not candidates:
        return Result("fd-window", PASS, f"reserved {size:#x} at {base:#x}; no built FD to compare")
    fd = candidates[-1]
    actual = fd.stat().st_size
    if actual > size:
        return Result("fd-window", FAIL, f"built FD {actual:#x} exceeds window {size:#x} ({fd})")
    if actual == size:
        # Full to the last block: any addition to the firmware fails next time,
        # so say so now instead of letting the next change discover it.
        return Result("fd-window", PASS, f"built FD {actual:#x} exactly fills {size:#x} at {base:#x} (no headroom)")
    return Result("fd-window", PASS, f"built FD {actual:#x} fits {size:#x} at {base:#x}")


def check_loader_revision(uefi: Path | None) -> Result:
    if uefi is None:
        return Result("loader-revision", UNKNOWN, "no UEFI checkout given")
    header = uefi / LOADER_HEADER
    if not header.is_file():
        return Result("loader-revision", FAIL, f"missing {header}")
    text = header.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"^\s*#define\s+UNIXNU_LOADER_REVISION(?!\w)\s+(0x[0-9A-Fa-f]+|\d+)", text, re.MULTILINE)
    if not match:
        return Result("loader-revision", FAIL, f"no UNIXNU_LOADER_REVISION in {header}")
    revision = int(match.group(1), 0)
    if revision < MIN_LOADER_REVISION:
        return Result(
            "loader-revision",
            FAIL,
            f"{revision:#010x} < {MIN_LOADER_REVISION:#010x}: DarwinBoot would reject the fileset image",
        )
    return Result("loader-revision", PASS, f"{revision:#010x}")


def check_payload_inputs(board: dict) -> Result:
    payload = board.get("payload") or {}
    adt = payload.get("adt") or {}
    problems = []
    chip_id = adt.get("chip_id")
    if not isinstance(chip_id, str) or not re.fullmatch(r"[0-9A-Fa-f]{4}", chip_id):
        problems.append(f"payload.adt.chip_id={chip_id!r} is not four hex digits")
    seed = payload.get("random_seed")
    if seed is not None and not str(seed).isdigit():
        problems.append(f"payload.random_seed={seed!r} is not an integer")
    uuid = payload.get("root_match_volume_uuid")
    if uuid is not None and not UUID_RE.match(str(uuid)):
        problems.append(f"payload.root_match_volume_uuid={uuid!r} is not a UUID")
    if problems:
        return Result("payload-inputs", FAIL, "; ".join(problems))
    return Result("payload-inputs", PASS, f"chip_id={chip_id} seed={seed} uuid={uuid}")


def run(board_path: Path, uefi: Path | None) -> list[Result]:
    board = load_toml(board_path)
    config_name = (board.get("firmware") or {}).get("config") or ""
    results = [
        check_board(board),
        check_dsc(uefi, board),
        check_modules(uefi),
        check_fd_window(uefi, config_name),
        check_loader_revision(uefi),
        check_payload_inputs(board),
    ]
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--device", type=Path, help="device repository (default: $UNIXNU_DEVICE)")
    parser.add_argument("--uefi", type=Path, help="UEFI checkout (default: $UNIXNU_UEFI)")
    parser.add_argument("--json", action="store_true", help="one JSON object instead of lines")
    parser.add_argument(
        "--allow-unknown",
        action="store_true",
        help="exit 0 when a check could not be judged (never rescues a failure)",
    )
    args = parser.parse_args(argv)

    device = args.device or (Path(os.environ["UNIXNU_DEVICE"]) if os.environ.get("UNIXNU_DEVICE") else None)
    uefi = args.uefi or (Path(os.environ["UNIXNU_UEFI"]) if os.environ.get("UNIXNU_UEFI") else None)

    if device is None:
        print("preflight: no device repository (--device or UNIXNU_DEVICE)", file=sys.stderr)
        return 2
    board_path = device / "board.toml"
    if not board_path.is_file():
        print(f"preflight: missing {board_path}", file=sys.stderr)
        return 2
    try:
        results = run(board_path, uefi)
    except tomllib.TOMLDecodeError as error:
        print(f"preflight: {board_path} is not valid TOML: {error}", file=sys.stderr)
        return 1

    failed = [item for item in results if item.state == FAIL]
    unknown = [item for item in results if item.state == UNKNOWN]
    if args.json:
        print(
            json.dumps(
                {
                    "board": str(board_path),
                    "uefi": str(uefi) if uefi else None,
                    "results": [asdict(item) for item in results],
                    "failed": len(failed),
                    "unknown": len(unknown),
                },
                ensure_ascii=False,
            )
        )
    else:
        for item in results:
            print(f"preflight: {item.state:<7} {item.check:<16} {item.detail}")

    if failed:
        return 1
    if unknown:
        if args.allow_unknown:
            print(f"preflight: {len(unknown)} check(s) could not be judged; continuing because --allow-unknown")
            return 0
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
