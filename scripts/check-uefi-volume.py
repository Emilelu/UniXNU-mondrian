#!/usr/bin/env python3
"""Keep an official requirement honest: the drivers it names must be in the volume.

The page `drivers/uefi-drivers` says the firmware volume carries DiskIoDxe,
EnhancedFatDxe and the UniXNU ramdisk driver. Three audits disagreed about
whether we ship them, and none of them read the two files that decide it: the
FDF's `[FV.FvMain]` and the `!include` chain it pulls in. This gate reads both,
then checks that EDK II actually produced an EFI image for every driver it
found, so "listed in a .inc" cannot pass on its own.

    python3 scripts/check-uefi-volume.py --uefi /mnt/e/iOS Port/Sources/Repos/UEFI/uefi-mondrian
    python3 scripts/check-uefi-volume.py --uefi ... --require MdeModulePkg/.../DiskIoDxe.inf

Exit 0 when every required driver is in the volume and built, 1 when one is
missing, 2 when the platform cannot be read at all (unknown is not a pass).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PLATFORM = Path('Platforms/Xiaomi/mondrianPkg')
FDF = 'mondrian.fdf'
VOLUME = 'FV.FvMain'
BUILD_GLOB = 'Build/*/*/AARCH64'

# The drivers the official page requires, as INF paths inside the volume.
REQUIRED = (
    'UniXNUPkg/Application/UniXNU/UniXNU.inf',
    'UniXNUPkg/Driver/UniXNUDxe/UniXNUDxe.inf',
    'DarwinBootPkg/Driver/DarwinBoot.inf',
    'UniXNUPkg/Driver/UniXNURamDiskDxe/UniXNURamDiskDxe.inf',
    'MdeModulePkg/Universal/Disk/DiskIoDxe/DiskIoDxe.inf',
    'FatPkg/EnhancedFatDxe/Fat.inf',
)

# porting/uefi-firmware.md#required-integration also fixes two library mappings in the DSC.
LIBRARIES = (
    'HobLib|MdePkg/Library/DxeHobLib/DxeHobLib.inf',
    'FdtLib|MdePkg/Library/BaseFdtLib/BaseFdtLib.inf',
)

INCLUDE = re.compile(r'^\s*!include\s+(\S+)\s*$')
INF_LINE = re.compile(r'^\s*INF\s+(\S+)\s*$')
SECTION = re.compile(r'^\s*\[([^\]]+)\]\s*$')


class Failure(SystemExit):
    pass


def include_chain(path: Path, seen: set[Path] | None = None) -> list[Path]:
    """Every file reachable from `path` through `!include`, in file order."""
    seen = seen if seen is not None else set()
    if path in seen:
        return []
    seen.add(path)
    out = [path]
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        match = INCLUDE.match(line)
        if match:
            child = (path.parent / match.group(1)).resolve()
            if child.is_file():
                out.extend(include_chain(child, seen))
    return out


def volume_infs(fdf: Path) -> tuple[list[str], list[str]]:
    """INFs listed under `[FV.FvMain]`, following the includes it names."""
    if not fdf.is_file():
        raise Failure(f'FAIL: no {fdf}; the flash volume layout is unknown, which is not a pass')
    text = fdf.read_text(encoding='utf-8', errors='replace').splitlines()
    inside = False
    own: list[str] = []
    files: list[Path] = []
    for line in text:
        section = SECTION.match(line)
        if section:
            inside = section.group(1).strip() == VOLUME
            continue
        if not inside:
            continue
        inc = INCLUDE.match(line)
        if inc:
            child = (fdf.parent / inc.group(1)).resolve()
            if child.is_file():
                files.extend(include_chain(child))
            continue
        inf = INF_LINE.match(line)
        if inf:
            own.append(inf.group(1))
    pulled: list[str] = []
    for path in files:
        for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
            inf = INF_LINE.match(line)
            if inf:
                pulled.append(inf.group(1))
    return own, pulled


def built(uefi: Path, inf: str) -> bool:
    """EDK II writes <Name>.efi next to the package that owns the INF."""
    name = Path(inf).stem
    stem = Path(inf).parts[0]
    for root in uefi.glob(BUILD_GLOB):
        if (root / (name + '.efi')).is_file():
            return True
        # Some platforms nest the output under the package directory.
        if (root / stem).is_dir() and (root / stem / (name + '.efi')).is_file():
            return True
    return False



def dsc_text(dsc: Path, roots: tuple[Path, ...]) -> str:
    """The DSC with every !include it can resolve, so a module listed in an include still counts."""
    if not dsc.is_file():
        return ''
    text = dsc.read_text(encoding='utf-8', errors='replace')
    out = [text]
    for name in INCLUDE.findall(text):
        for root in (dsc.parent,) + roots:
            candidate = root / name
            if candidate.is_file():
                out.append(candidate.read_text(encoding='utf-8', errors='replace'))
                break
    return '\n'.join(out)


def dsc_integration(dsc: Path, roots: tuple[Path, ...] = ()) -> dict:
    """The two halves of porting/uefi-firmware.md#required-integration that live in the DSC."""
    text = dsc_text(dsc, roots)
    components = {inf: (inf in text) for inf in REQUIRED}
    mapped = {entry: (entry in text) for entry in LIBRARIES}
    return {'components': components, 'libraries': mapped, 'text': text}

def libraries(dsc: Path) -> dict:
    """The two library mappings the official page fixes in [LibraryClasses]."""
    text = dsc.read_text(encoding='utf-8', errors='replace') if dsc.is_file() else ''
    return {entry: entry in text for entry in LIBRARIES}


def check(uefi: Path, required: tuple[str, ...] = REQUIRED) -> dict:
    platform = uefi / PLATFORM
    if not platform.is_dir():
        raise Failure(f'FAIL: no platform at {platform}; nothing to read')
    own, pulled = volume_infs(platform / FDF)
    present = set(own) | set(pulled)
    rows = []
    for inf in required:
        rows.append({
            'inf': inf,
            'listed': any(one == inf or one.endswith(inf) for one in present),
            'built': built(uefi, inf),
        })
    dsc = platform / 'mondrian.dsc'
    roots = (uefi, uefi / 'Silicon/Qualcomm')
    integration = dsc_integration(dsc, roots)
    return {'platform': platform, 'own': own, 'pulled': pulled, 'rows': rows,
            'libraries': integration['libraries'], 'components': integration['components'],
            'dsc': dsc}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uefi', default='/mnt/e/iOS Port/Sources/Repos/UEFI/uefi-mondrian')
    parser.add_argument('--require', action='append', default=[],
                        help='an additional INF the volume must carry')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args(argv)
    if args.self_test:
        return self_tests()
    required = REQUIRED + tuple(args.require)
    result = check(Path(args.uefi), required)
    print(f'volume: {VOLUME} lists {len(result["own"])} INF directly, '
          f'{len(result["pulled"])} more through its includes')
    bad = 0
    for row in result['rows']:
        mark = 'ok  ' if row['listed'] and row['built'] else 'FAIL'
        if mark == 'FAIL':
            bad += 1
        why = []
        if not row['listed']:
            why.append('not in the volume')
        if not row['built']:
            why.append('never built')
        suffix = f' ({", ".join(why)})' if why else ''
        print(f'{mark} {Path(row["inf"]).stem}{suffix}')
    for inf, listed in result['components'].items():
        if listed:
            continue
        bad += 1
        print(f'FAIL {Path(inf).stem} (not in the DSC [Components]; an FDF INF line alone '
              f'does not build it)')
    for entry, mapped in result['libraries'].items():
        if mapped:
            continue
        bad += 1
        print(f'FAIL {entry.split("|")[0]} (not mapped in the DSC [LibraryClasses])')
    if bad:
        print(f'FAIL {bad} required item(s) from porting/uefi-firmware.md#required-integration '
              f'are missing; the page\'s claim does not hold')
        return 1
    print(f'OK {len(result["rows"])} required driver(s) are listed and built, '
          f'{len(result["libraries"])} library mapping(s) are in the DSC')
    return 0


def self_tests() -> int:
    import tempfile
    cases = []

    def make(fdf: str, inc: str, build: tuple[str, ...], required=REQUIRED) -> dict:
        root = Path(tempfile.mkdtemp())
        platform = root / PLATFORM
        (platform / 'Include').mkdir(parents=True)
        (platform / FDF).write_text(fdf, encoding='utf-8')
        if inc:
            (platform / 'Include' / 'DXE.inc').write_text(inc, encoding='utf-8')
        out = root / 'Build' / 'mondrianPkg' / 'DEBUG' / 'AARCH64'
        out.mkdir(parents=True)
        for name in build:
            (out / name).write_text('x', encoding='utf-8')
        return check(root, required)

    head = '[FV.FvMain]\n'
    inc_dxe = '\n'.join(f'  INF {i}' for i in REQUIRED) + '\n'
    names = tuple(Path(i).stem + '.efi' for i in REQUIRED)
    cases.append(('volume.included_drivers_pass',
                  make(head + '  !include Include/DXE.inc\n', inc_dxe, names),
                  lambda r: all(x['listed'] and x['built'] for x in r['rows'])))
    cases.append(('volume.driver_missing_from_include_fails',
                  make(head + '  !include Include/DXE.inc\n',
                       '\n'.join(f'  INF {i}' for i in REQUIRED[:-1]) + '\n', names),
                  lambda r: [x['inf'] for x in r['rows'] if not x['listed']] == [REQUIRED[-1]]))
    cases.append(('volume.listed_but_not_built_fails',
                  make(head + '  !include Include/DXE.inc\n', inc_dxe, names[:-1]),
                  lambda r: [x['inf'] for x in r['rows'] if not x['built']] == [REQUIRED[-1]]))
    cases.append(('volume.direct_inf_counts',
                  make(head + '\n'.join(f'  INF {i}' for i in REQUIRED) + '\n',
                       '', names),
                  lambda r: all(x['listed'] for x in r['rows'])))
    cases.append(('volume.section_scope_respected',
                  make('[FV.Other]\n  !include Include/DXE.inc\n[FV.FvMain]\n', inc_dxe, names),
                  lambda r: not any(x['listed'] for x in r['rows'])))
    failed = 0
    for name, result, predicate in cases:
        try:
            good = predicate(result)
        except Exception as error:  # noqa: BLE001 - a test that raises is a failure
            print(f'FAIL {name}: {error}')
            failed += 1
            continue
        if not good:
            print(f'FAIL {name}')
            failed += 1
        else:
            print(f'ok   {name}')
    try:
        check(Path('/nonexistent-uefi'))
    except Failure as error:
        if 'nothing to read' in str(error):
            print('ok   volume.missing_platform_refused')
        else:
            print(f'FAIL volume.missing_platform_refused: {error}')
            failed += 1
    else:
        print('FAIL volume.missing_platform_refused')
        failed += 1
    print(f'{len(cases) + 1 - failed}/{len(cases) + 1} checks passed')
    if failed:
        return 1
    print('OK the gate reads the volume through its includes and needs a built image')
    return 0


if __name__ == '__main__':
    sys.exit(main())
