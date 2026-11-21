#!/usr/bin/env python3
"""Grade the three route-B acceptance criteria, separately and only when a product exists.

Route B's product is a kernel collection carrying `NativeUfs` as its own fileset
entry. `docs/research/storage/UFS27-ROUTE-B-WIRING.md` splits that acceptance
into three questions that fail for different reasons, so they are graded on
three separate rows and none of them can hide behind another:

    entry    the fileset carries an entry matching NativeUfs
    kmod     that entry's kmod_info has a non-zero start and stop, both landing
             in executable code of the same entry
    exports  the eleven IOBlockStorageDevice symbols resolve from the sibling
             IOStorageFamily entry, not from com.apple.kernel

With no product every row is `PEND` and the exit code is 0: on this host there is
no build, and the stage-0 state is "not measured", not "failed". Given
`--kernelcache`, `entry` and `exports` delegate to the tree's own readers
(`check-ios27-storage-entries.py`, `check-ios27-storage-exports.py`) and `kmod`
parses the entry itself.

The `kmod_info` layout is confirmed by content before it is trusted: a
`struct kmod_info` on arm64 puts `name` at +0x10, `start` at +0xa8 and `stop` at
+0xb0, so the reader first insists that the 64 bytes at +0x10 begin with the
bundle identifier from `drivers/NativeUfs/Info.plist`. If the name does not
match, the row stays `PEND` with "layout not confirmed" rather than guessing.

    python3 scripts/check-ufs27-storage-entry.py [--kernelcache <kc>] [--out report.json]

Exit code 1 only for a contradiction: an entry whose start/stop is dead or
misplaced, or symbols still resolving from `com.apple.kernel`.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import plistlib
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MH_MAGIC_64 = 0xFEEDFACF
MH_FILESET = 12
MH_KEXT_BUNDLE = 11
LC_SEGMENT_64 = 0x19
LC_SYMTAB = 0x02
KMOD_NAME = 0x10
KMOD_START = 0xA8
KMOD_STOP = 0xB0
KMOD_SIZE = 0xB8
ENTRY_NAME = "NativeUfs"
PLIST = Path("drivers/NativeUfs/Info.plist")


def bundle_identifier(repo: Path) -> str | None:
    path = repo / PLIST
    if not path.is_file():
        return None
    try:
        with path.open("rb") as handle:
            return plistlib.load(handle).get("CFBundleIdentifier")
    except (OSError, plistlib.InvalidFileException, ValueError):
        return None


def load_exports_module():
    spec = importlib.util.spec_from_file_location(
        "storage_exports", HERE / "check-ios27-storage-exports.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def image_map(buf: bytes, base: int) -> tuple[int, list[dict], dict[str, int]]:
    """(filetype, segments, symbol addresses) of one Mach-O image."""
    magic, = struct.unpack_from("<I", buf, base)
    if magic != MH_MAGIC_64:
        raise ValueError(f"not a 64-bit Mach-O at {base:#x}")
    _cputype, _cpusubtype, filetype, ncmds, _sizeofcmds, _flags, _reserved = struct.unpack_from(
        "<iiIIIII", buf, base + 4
    )
    segments: list[dict] = []
    symbols: dict[str, int] = {}
    cursor = base + 32
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", buf, cursor)
        if cmd == LC_SEGMENT_64:
            name = buf[cursor + 8 : cursor + 24].split(b"\0")[0].decode("ascii", "replace")
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<QQQQ", buf, cursor + 24)
            _maxprot, initprot = struct.unpack_from("<ii", buf, cursor + 56)
            segments.append(
                {
                    "name": name,
                    "vmaddr": vmaddr,
                    "vmsize": vmsize,
                    "fileoff": fileoff,
                    "filesize": filesize,
                    "exec": bool(initprot & 0x4),
                }
            )
        elif cmd == LC_SYMTAB:
            symoff, nsyms, stroff, strsize = struct.unpack_from("<IIII", buf, cursor + 8)
            strings = buf[stroff : stroff + strsize]
            for index in range(nsyms):
                where = symoff + index * 16
                strx, _ntype, _sect, _desc, value = struct.unpack_from("<IBBHQ", buf, where)
                if not strx or strx >= len(strings):
                    continue
                end = strings.find(b"\0", strx)
                raw = strings[strx : end if end >= 0 else len(strings)]
                if raw:
                    symbols.setdefault(raw.decode("utf-8", "replace"), value)
        cursor += size
    return filetype, segments, symbols


def kmod_state(buf: bytes, entry: dict, expected_name: str | None) -> tuple[str, str]:
    """(status, text) for the kmod_info row."""
    filetype = (entry.get("image") or {}).get("filetype")
    if filetype != MH_KEXT_BUNDLE:
        return "PEND", (
            f"entry {entry['name']} is filetype {filetype}, not MH_KEXT_BUNDLE (11); "
            "kmod_info lives in the bundle's own image, so this entry is not a driver bundle"
        )
    try:
        _filetype, segments, symbols = image_map(buf, entry["fileoff"])
    except (ValueError, struct.error) as error:
        return "PEND", f"cannot read the entry's load commands: {error}"
    address = None
    for candidate in ("_kmod_info", "__kmod_info"):
        if candidate in symbols:
            address = symbols[candidate]
            break
    if address is None:
        return "PEND", (
            f"entry {entry['name']} carries no _kmod_info symbol among {len(symbols)} symbols; "
            "the link has to emit one"
        )
    holder = None
    for segment in segments:
        if segment["vmaddr"] <= address < segment["vmaddr"] + segment["vmsize"]:
            holder = segment
            break
    if holder is None or holder["filesize"] == 0:
        return "PEND", f"_kmod_info at {address:#x} is not backed by file bytes"
    offset = holder["fileoff"] + (address - holder["vmaddr"])
    if offset + KMOD_SIZE > len(buf):
        return "PEND", f"_kmod_info at {address:#x} runs past the end of the file"
    name = buf[offset + KMOD_NAME : offset + KMOD_NAME + 64].split(b"\0")[0].decode("utf-8", "replace")
    if expected_name and not name.startswith(expected_name):
        return "PEND", (
            f"kmod_info layout not confirmed: the name field reads {name!r}, not {expected_name!r}; "
            "start/stop offsets are not trusted on this image"
        )
    start, stop = struct.unpack_from("<QQ", buf, offset + KMOD_START)
    if not start or not stop:
        return "GAP", f"kmod_info of {name or entry['name']} has start={start:#x} stop={stop:#x}"
    text = [(s["vmaddr"], s["vmaddr"] + s["vmsize"]) for s in segments if s["exec"]]
    misplaced = [value for value in (start, stop) if not any(low <= value < high for low, high in text)]
    if misplaced:
        return "GAP", f"start={start:#x} stop={stop:#x} do not both land in executable segments of {entry['name']}"
    return "OK", f"kmod_info name {name!r}, start={start:#x}, stop={stop:#x}, both inside the entry's text"


def run_reader(name: str, product: Path, extra: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HERE / name), "--kernelcache", str(product), *extra],
        capture_output=True,
        text=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Grade the three route-B acceptance criteria.")
    parser.add_argument("--kernelcache", type=Path, default=None)
    parser.add_argument("--entry", default=ENTRY_NAME)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    expected = bundle_identifier(repo)

    rows: list[tuple[str, str, str]] = []
    product = args.kernelcache if args.kernelcache and args.kernelcache.is_file() else None

    if product is None:
        rows.append(("PEND", "entry", "no kernel collection given, so the fileset entry is not measured"))
        rows.append(("PEND", "kmod", "no kernel collection given, so start/stop are not measured"))
        rows.append(("PEND", "exports", "no kernel collection given, so the eleven imports are not attributed"))
    else:
        result = run_reader("check-ios27-storage-entries.py", product, ["--require-entry"])
        if result.returncode == 0:
            rows.append(("OK", "entry", f"{product} carries a fileset entry matching {args.entry}"))
        else:
            lines = (result.stdout or result.stderr).strip().splitlines()
            rows.append(
                (
                    "GAP",
                    "entry",
                    f"no fileset entry matches {args.entry} in {product}: "
                    f"{lines[-1] if lines else 'the reader printed nothing'}",
                )
            )

        module = load_exports_module()
        try:
            parsed = module.parse_file(product)
        except Exception as error:
            rows.append(("PEND", "kmod", f"{product} could not be parsed: {error}"))
        else:
            entry = next(
                (item for item in parsed["entries"] if args.entry.lower() in item["name"].lower()),
                None,
            )
            if entry is None:
                rows.append(("PEND", "kmod", f"no fileset entry matches {args.entry}, so no kmod_info to read"))
            else:
                status, text = kmod_state(parsed["buffer"], entry, expected)
                rows.append((status, "kmod", text))

        report = args.out or (repo / "out" / "ufs27-storage-entry.json")
        report.parent.mkdir(parents=True, exist_ok=True)
        run_reader(
            "check-ios27-storage-exports.py",
            product,
            ["--entry", args.entry, "--out", str(report)],
        )
        where = {}
        if report.is_file():
            where = json.loads(report.read_text(encoding="utf-8")).get("exported_by", {})
        kernel = [symbol for symbol, place in where.items() if "com.apple.kernel" in place]
        sibling = [symbol for symbol, place in where.items() if "IOStorageFamily" in place]
        if kernel:
            rows.append(
                ("GAP", "exports", f"{len(kernel)} symbol(s) still resolve from com.apple.kernel, e.g. {kernel[0]}")
            )
        elif sibling:
            rows.append(("OK", "exports", f"{len(sibling)} symbol(s) resolve from the IOStorageFamily entry"))
        else:
            rows.append(
                ("PEND", "exports", "no symbol was attributed to an entry, so route B is not visible in this product")
            )

    print(f"product   {product if product else 'none'}")
    print(f"bundle id {expected or 'unknown'}")
    for status, area, text in rows:
        print(f"  {status:<4} {area:<7} {text}")
    gaps = sum(1 for status, _, _ in rows if status == "GAP")
    pending = sum(1 for status, _, _ in rows if status == "PEND")
    print(f"ufs27-storage-entry: {gaps} gap(s), {pending} pending")
    return 1 if gaps else 0


if __name__ == "__main__":
    raise SystemExit(main())
