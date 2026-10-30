#!/usr/bin/env python3
"""Install a GPT-wrapped APFS Data disk into the K60 unixnu SHNGROOT.

K60 keeps its Darwin root in a dedicated "unixnu" partition (32 GiB, LBA
53342976..61731583) instead of Pong's userdata, so the geometry and the device
node differ from install-pong-ufs-data.py. Everything else follows that script:
read the 4 KiB SHNGROOT directory, refuse unless the layout is the expected
OS/SystemOS pair, place the new window beyond the occupied range with a guard,
fsync the data, and only then commit the directory with its new entry.

Use --dry-run to validate geometry and the planned layout without writing.
"""
import argparse
import hashlib
import json
import struct
import subprocess
import sys
from pathlib import Path

FIRST_4K = 53342976
LAST_4K = 61731583
BLOCK = 4096
PARTITION_BYTES = (LAST_4K - FIRST_4K + 1) * BLOCK
TARGET = '/dev/block/by-name/unixnu'
GUARD_BYTES = 16 * 1024 ** 2
TAIL_RESERVE = 1024 ** 3
ENTRY = 128
HEADER = 4096



def adb_local_path(path, adb_exe):
    """adb.exe is a Windows binary: it cannot open WSL paths like /tmp/x.
    Convert to the Windows form whenever the adb we are driving is an .exe."""
    path = Path(path)
    if str(adb_exe).lower().endswith('.exe'):
        out = subprocess.run(['wslpath', '-w', str(path)], capture_output=True, text=True)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    return str(path)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--adb', type=Path, required=True)
    p.add_argument('--serial', required=True)
    p.add_argument('--disk-image', type=Path, required=True,
                   help='GPT disk image for the Data window')
    p.add_argument('--volume-uuid', required=True,
                   help='APFS volume UUID inside that image, upper case')
    p.add_argument('--offset', type=lambda v: int(v, 0), required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--dry-run', action='store_true',
                   help='validate and print the plan, write nothing')
    a = p.parse_args()

    image = a.disk_image.resolve()
    size = image.stat().st_size
    if not size or size % BLOCK or a.offset % (1024 ** 2):
        raise SystemExit('disk image must be whole 4 KiB and the offset whole MiB')
    head = image.read_bytes()[:1024]
    if head[512:520] != b'EFI PART':
        raise SystemExit('disk image must start with a GPT (EFI PART at offset 512)')

    out = a.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    adb = [str(a.adb), '-s', a.serial]

    def run(args, **kw):
        return subprocess.run(args, check=True, **kw)

    def shell(command):
        return run(adb + ['shell', command], capture_output=True, text=True).stdout.strip()

    state = run(adb + ['get-state'], capture_output=True, text=True).stdout.strip()
    if state not in ('recovery', 'device'):
        raise SystemExit(f'adb state is {state!r}; recovery is required for writes')

    target = shell('readlink -f ' + TARGET)
    if not target:
        raise SystemExit('unixnu partition not found')
    name = target.rsplit('/', 1)[-1]
    parent = shell(f'basename $(dirname $(readlink -f /sys/class/block/{name}))')
    geometry = dict(
        device=target,
        bytes=int(shell('blockdev --getsize64 ' + TARGET)),
        start_512=int(shell(f'cat /sys/class/block/{name}/start')),
        sectors_512=int(shell(f'cat /sys/class/block/{name}/size')),
        logical_block_bytes=int(shell(f'cat /sys/class/block/{parent}/queue/logical_block_size')),
    )
    print('geometry:', json.dumps(geometry), flush=True)
    if (geometry['bytes'] != PARTITION_BYTES or geometry['start_512'] != FIRST_4K * 8 or
            geometry['sectors_512'] * 512 != PARTITION_BYTES or
            geometry['logical_block_bytes'] != BLOCK):
        raise SystemExit('unixnu geometry differs from the board constants; refusing')

    if shell(f'ls /sys/class/block/{name}/holders'):
        raise SystemExit('unixnu has active device-mapper holders')
    mounts = shell('cat /proc/mounts').splitlines()
    if any(line.split() and line.split()[0] in (target, TARGET) for line in mounts):
        raise SystemExit('unixnu must be unmounted')

    raw = run(adb + ['exec-out', 'dd', 'if=' + TARGET, 'bs=4096', 'count=1', 'status=none'],
              capture_output=True).stdout
    if len(raw) != HEADER or raw[:8] != b'SHNGROOT':
        raise SystemExit('existing SHNGROOT directory unavailable')
    version, count, total = struct.unpack_from('<IIQ', raw, 8)
    if version != 1 or count not in (2, 3) or total > PARTITION_BYTES:
        raise SystemExit('unsupported SHNGROOT directory')
    records = []
    for i in range(count):
        win_name, offset, length, blockBytes, flags = struct.unpack_from('<32sQQII', raw, 24 + ENTRY * i)
        win_name = win_name.split(b'\0')[0].decode('ascii')
        if blockBytes != 512 or flags != 1 or not length or offset < HEADER or offset + length > total:
            raise SystemExit('invalid existing window geometry')
        records.append(dict(name=win_name, offset=offset, size=length))
    names = {r['name'] for r in records}
    if len(names) != count or names not in ({'OS', 'SystemOS'}, {'OS', 'SystemOS', 'Data'}):
        raise SystemExit('expected the OS/SystemOS pair and no extra windows')
    if any(r['name'] == 'Data' for r in records):
        raise SystemExit('a Data window already exists; this script only adds the first one')

    occupied = max(r['offset'] + r['size'] for r in records)
    end = a.offset + size
    if a.offset < occupied + GUARD_BYTES:
        raise SystemExit(f'offset must be at least {occupied + GUARD_BYTES} (occupied + 16 MiB)')
    if end > PARTITION_BYTES - TAIL_RESERVE:
        raise SystemExit('window would eat the tail reserve')
    if size > PARTITION_BYTES // 4:
        raise SystemExit('window larger than a quarter of the partition')

    plan = dict(target=target, geometry=geometry, existing_windows=records,
                data=dict(offset=a.offset, size=size, volume_uuid=a.volume_uuid,
                          image=str(image), image_sha256=hashlib.sha256(image.read_bytes()).hexdigest()),
                image_bytes=end, dry_run=a.dry_run)
    print(json.dumps(plan, indent=2), flush=True)
    if a.dry_run:
        print('dry run: nothing written', flush=True)
        return 0

    before = out / 'shngroot-before.bin'
    before.write_bytes(raw)
    header = bytearray(raw)
    struct.pack_into('<IIQ', header, 8, 1, count + 1, max(total, end))
    struct.pack_into('<32sQQII32s40s', header, 24 + ENTRY * count,
                     b'Data', a.offset, size, 512, 1, bytes(32), bytes(40))
    header[4064:] = hashlib.sha256(bytes(header[:4064])).digest()
    after = out / 'shngroot-with-data.bin'
    after.write_bytes(bytes(header))

    remote = '/tmp/k60-data-window.cdr'
    remote_header = '/tmp/k60-shngroot-with-data.bin'
    run(adb + ['push', '-z', 'lz4', adb_local_path(image, a.adb), remote])
    print(shell('dd if=' + remote + ' of=' + TARGET +
                ' bs=' + str(1024 ** 2) + ' seek=' + str(a.offset // (1024 ** 2)) +
                ' count=' + str(size // (1024 ** 2)) + ' conv=notrunc,fsync'), flush=True)
    shell('rm -f ' + remote)
    run(adb + ['push', adb_local_path(after, a.adb), remote_header])
    print(shell('dd if=' + remote_header + ' of=' + TARGET +
                ' bs=4096 count=1 conv=notrunc,fsync'), flush=True)
    shell('rm -f ' + remote_header)
    shell('sync')
    plan['state'] = 'installed'
    (out / 'installation.json').write_text(json.dumps(plan, indent=2) + '\n')
    print('Data window installed; no readback performed', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
