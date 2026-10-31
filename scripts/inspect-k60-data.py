#!/usr/bin/env python3
"""Read-only K60 unixnu/Data inspection and host backup. No device write commands.

Offline:
  python3 scripts/inspect-k60-data.py offline --manifest shngroot.bin \
      --data-image data-window.img --output report.json
Recovery capture (root ADB, unixnu unmounted):
  python3 scripts/inspect-k60-data.py capture --adb /path/to/adb --serial SERIAL \
      --output-dir /path/to/new-backup-directory

A proposed larger Data window is only a layout preview. It does not resize APFS,
write a partition table, format a volume, delete files or switch the active Data.
"""
import argparse
import binascii
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import uuid

TARGET = '/dev/block/by-name/unixnu'
FIRST_4K = 53342976
LAST_4K = 61731583
PARTITION_BYTES = (LAST_4K - FIRST_4K + 1) * 4096
MIB, GIB = 2**20, 2**30
APFS_TYPE = uuid.UUID('7C3457EF-0000-11AA-AA11-00306543ECAC')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(8*MIB), b''):
            h.update(chunk)
    return h.hexdigest()


def manifest_info(raw, partition_bytes=PARTITION_BYTES):
    require(len(raw) == 4096 and raw[:8] == b'SHNGROOT', 'Invalid SHNGROOT block')
    require(hashlib.sha256(raw[:4064]).digest() == raw[4064:], 'SHNGROOT SHA-256 mismatch')
    version, count, total = struct.unpack_from('<IIQ', raw, 8)
    require(version == 1 and 2 <= count <= 4, 'Unsupported SHNGROOT version/count')
    require(4096 <= total <= partition_bytes and total % 4096 == 0, 'Invalid SHNGROOT image extent')
    windows = []
    for i in range(count):
        b = raw[24+128*i:24+128*(i+1)]
        name_bytes = b[:32].split(b'\0', 1)[0]
        name = name_bytes.decode('ascii')
        require(0 < len(name) < 32 and all(32 <= c < 127 for c in name_bytes), 'Bad window name')
        offset, size, logical, flags = struct.unpack_from('<QQII', b, 32)
        require(offset >= 4096 and offset % 4096 == 0 and size > 0 and size % 512 == 0,
                f'Unaligned window {name}')
        require(logical == 512 and flags == 1, f'Unsupported window attributes {name}')
        padded_end = offset + ((size + 4095) // 4096) * 4096
        require(padded_end <= total, f'Window exceeds SHNGROOT extent: {name}')
        require(not any(w['name'] == name for w in windows), 'Duplicate window name')
        require(not any(offset < w['physical_read_end'] and w['offset'] < padded_end for w in windows),
                f'Overlapping windows: {name}')
        windows.append({'name': name, 'offset': offset, 'size': size, 'end': offset+size,
                        'physical_read_end': padded_end, 'size_gib': size/GIB})
    names = {w['name'] for w in windows}
    require({'OS', 'SystemOS', 'Data'} <= names, 'Expected OS/SystemOS/Data windows')
    end = max(w['physical_read_end'] for w in windows)
    return {'version': version, 'count': count, 'image_extent_bytes': total,
            'manifest_sha256': hashlib.sha256(raw).hexdigest(), 'windows': windows,
            'unassigned_tail_bytes': partition_bytes-end,
            'unassigned_tail_gib': (partition_bytes-end)/GIB}


def gpt_apfs_info(path):
    """Validate both GPT headers/tables and report latest APFS checkpoint read-only."""
    path = Path(path)
    size = path.stat().st_size
    require(size % 512 == 0, 'Data disk is not sector-aligned')
    with path.open('rb') as f:
        def read(off, length):
            require(off >= 0 and length >= 0 and off+length <= size, 'Disk read out of bounds')
            f.seek(off)
            b = f.read(length)
            require(len(b) == length, 'Short disk read')
            return b
        def header(lba):
            h = bytearray(read(lba*512, 512))
            require(h[:8] == b'EFI PART', 'Missing GPT signature')
            revision, length, checksum, reserved = struct.unpack_from('<IIII', h, 8)
            require(revision == 0x10000 and 92 <= length <= 512 and reserved == 0, 'Invalid GPT header')
            struct.pack_into('<I', h, 16, 0)
            require(binascii.crc32(h[:length]) & 0xffffffff == checksum, 'GPT header CRC mismatch')
            cur, backup, first, last = struct.unpack_from('<QQQQ', h, 24)
            table, count, stride, crc = struct.unpack_from('<QIII', h, 72)
            require(cur == lba and backup < size//512 and first <= last < size//512,
                    'GPT disk geometry mismatch')
            require(not first <= cur <= last and not first <= backup <= last, 'GPT header overlaps usable range')
            require(0 < count <= 4096 and 128 <= stride <= 4096 and stride % 128 == 0, 'Invalid GPT array geometry')
            sectors = (count*stride + 511)//512
            require(table >= 2 and table+sectors <= size//512, 'GPT entry-array bounds invalid')
            require(table+sectors <= first or table > last, 'GPT entry array overlaps usable range')
            require(not table <= cur < table+sectors and not table <= backup < table+sectors, 'GPT array overlaps a header')
            if lba == 1:
                require(table+sectors <= first, 'Primary GPT array must precede usable space')
            else:
                require(table > last and table+sectors <= cur, 'Backup GPT array must follow usable space and precede its header')
            data = read(table*512, count*stride)
            require(binascii.crc32(data) & 0xffffffff == crc, 'GPT entry-array CRC mismatch')
            return h, data, (cur, backup, first, last, count, stride)
        h, entries, p = header(1)
        bh, bentries, bp = header(p[1])
        require(p[1] == size//512-1 and bp[1] == 1, 'GPT backup is not at disk end')
        require(h[56:72] == bh[56:72] and entries == bentries and p[2:] == bp[2:],
                'Primary/backup GPT mismatch')
        apfs = []
        occupied = []
        for i in range(p[4]):
            entry = entries[i*p[5]:(i+1)*p[5]]
            if entry[:16] == bytes(16):
                continue
            lo, hi = struct.unpack_from('<QQ', entry, 32)
            require(p[2] <= lo <= hi <= p[3], 'GPT partition bounds invalid')
            require(not any(lo <= xhi and xlo <= hi for xlo, xhi in occupied), 'GPT partitions overlap')
            occupied.append((lo, hi))
            if uuid.UUID(bytes_le=entry[:16]) == APFS_TYPE:
                apfs.append((lo, hi))
        require(len(apfs) == 1, 'Expected exactly one APFS physical store')
        lo, hi = apfs[0]
        raw = read(lo*512, 4096)
        require(raw[32:36] == b'NXSB', 'Missing APFS container superblock')
    # Project-owned read-only parser validates checksums and picks newest NXSB.
    tools = Path(__file__).resolve().parents[1]/'tools/apfs'
    require((tools/'apfs.py').is_file(), 'Run this script from the device repository scripts directory')
    sys.path.insert(0, str(tools))
    from apfs import Container, _uuid
    container = Container(str(path))
    try:
        capacity = container.nx['block_count'] * container.block_size
        require(capacity <= (hi-lo+1)*512, 'APFS capacity exceeds its GPT partition')
        volumes = [{'name': v.volname, 'uuid': _uuid(v.vol_uuid).upper(),
                    'allocated_bytes': v.alloc_count*container.block_size,
                    'files': v.num_files, 'directories': v.num_directories,
                    'snapshots': v.num_snapshots} for v in container.volumes()]
        return {'gpt_first_lba': lo, 'gpt_last_lba': hi, 'gpt_validated': True,
                'container_bytes': capacity, 'container_gib': capacity/GIB,
                'apfs_block_size': container.block_size, 'checkpoint_xid': container.xid,
                'container_uuid': _uuid(container.nx['uuid']).upper(), 'volumes': volumes}
    finally:
        container.close()



def usage_info(path, max_entries=200000):
    """Inspect file metadata locally; do not read/export file contents or follow links.

    Logical/file-stream allocations are NOT container-wide physical usage:
    clones/snapshots can share extents, and APFS metadata is not included.
    Paths in this local report may be private; never publish the Data backup.
    """
    tools = Path(__file__).resolve().parents[1]/'tools/apfs'
    require((tools/'apfs.py').is_file(), 'Project APFS reader missing')
    sys.path.insert(0,str(tools))
    from apfs import Container, pick_volume, ROOT_DIR_INO_NUM
    c=Container(str(path))
    try:
        v=pick_volume(c,None)
        pending=[('/',ROOT_DIR_INO_NUM)]
        seen_dirs=set()
        seen_streams=set()
        groups={}
        largest=[]
        count=0
        while pending:
            parent,oid=pending.pop()
            if oid in seen_dirs:
                continue
            seen_dirs.add(oid)
            for name,fid,dtype in v.dir_entries(oid):
                require(name not in ('.','..') and '/' not in name, 'Unsafe/corrupt directory entry')
                count+=1
                require(count<=max_entries,'Metadata walk limit exceeded; backup remains intact')
                file_path=parent.rstrip('/')+'/'+name
                if dtype==4:
                    pending.append((file_path,fid))
                    continue
                ino=v.inode(fid)
                if ino is None or not ino.is_reg:
                    continue
                if ino.private_id in seen_streams:
                    continue
                seen_streams.add(ino.private_id)
                logical,allocated=ino._dstream if ino._dstream else (0,0)
                parts=file_path.lstrip('/').split('/')
                group='/'+'/'.join(parts[:2])
                g=groups.setdefault(group,{'files':0,'logical_bytes':0,'stream_allocated_bytes':0})
                g['files']+=1; g['logical_bytes']+=logical; g['stream_allocated_bytes']+=allocated
                largest.append({'path':file_path,'logical_bytes':logical,'stream_allocated_bytes':allocated})
        return {'volume':v.volname,'walked_entries':count,'unique_regular_streams':len(seen_streams),
                'groups':dict(sorted(groups.items(),key=lambda kv:kv[1]['stream_allocated_bytes'],reverse=True)),
                'largest_files':sorted(largest,key=lambda x:x['stream_allocated_bytes'],reverse=True)[:40],
                'limits':'File-stream allocation is not physical container usage; clone/snapshot sharing and metadata differ. Paths are private local backup evidence.'}
    finally:
        c.close()


def preview(info, size_gib=22, offset_gib=8):
    """Side-by-side preview: preserve old Data bytes and both OS windows."""
    old = next(w for w in info['windows'] if w['name'] == 'Data')
    offset = offset_gib*GIB
    raw_capacity = size_gib*GIB
    disk_bytes = raw_capacity+2*MIB  # make-k60-gpt-data-image.py default wrapper
    end = offset+disk_bytes
    require(0 < size_gib <= 24 and offset_gib > 0, 'Invalid proposed layout')
    require(info['count'] < 4, 'No spare SHNGROOT entry for preserved previous Data')
    require(all(offset >= w['physical_read_end'] or end <= w['offset'] for w in info['windows']),
            'Proposed Data would overwrite an existing window')
    require(end <= PARTITION_BYTES-GIB, 'Proposed Data violates 1 GiB tail reserve')
    return {'mode': 'preview only; no image creation or device writes',
            'proposed_apfs_gib': size_gib, 'proposed_offset': offset,
            'proposed_gpt_window_bytes': disk_bytes, 'proposed_end': end,
            'tail_reserve_gib': (PARTITION_BYTES-end)/GIB,
            'previous_data_preserved': dict(old, proposed_name='DataPrevious'),
            'requirements': ['Capture current Data and verify both local/remote hashes first',
                             'Grow a COPY using supported APFS tools or migrate all metadata to a new container',
                             'Do not substitute a fresh empty seed for a data-preserving migration',
                             'Current UFS mount hook rejects >2 GiB; update/validate that branch before switching',
                             'First-install script cannot resize an existing Data window; use a validated plan',
                             'Switch SHNGROOT only after new filesystem and rollback plan are verified']}


def layout_preview(info):
    # Migration feasibility cannot invalidate an already verified read-only backup.
    try:
        return dict(feasible=True, **preview(info))
    except ValueError as error:
        return {'feasible': False, 'mode': 'preview only; no device writes', 'reason': str(error)}


def read_unit(offset, size):
    if offset % MIB == size % MIB == 0:
        return MIB
    if offset % 4096 == size % 4096 == 0:
        return 4096
    return 512


class Adb:
    def __init__(self, executable, serial, su=False):
        self.command = [executable, '-s', serial]
        self.su = su
    def run(self, *args, timeout=30, **kwargs):
        return subprocess.run(self.command+list(args), check=True, timeout=timeout, **kwargs)
    def text(self, *args, timeout=30):
        argv = ' '.join(args)
        if self.su:
            # One quoted device-side command: adb concatenates argv, so the
            # quotes must be inside the single host argument.
            return self.run('shell', "su -c '" + argv + "'", timeout=timeout,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode().strip()
        return self.run('shell', *args, timeout=timeout, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode().strip()
    def read(self, offset, size, output=None):
        require(offset >= 0 and size > 0 and offset % 512 == size % 512 == 0, 'Unaligned device read')
        require(offset + size <= PARTITION_BYTES, 'Device read exceeds unixnu')
        bs = read_unit(offset, size)
        dd = ('dd if='+TARGET+' bs='+str(bs)+' skip='+str(offset//bs)+
              ' count='+str(size//bs)+' status=none')
        if self.su:
            args = ['exec-out', "su -c '" + dd + "'"]
        else:
            args = ['exec-out', 'dd', 'if='+TARGET, 'bs='+str(bs), 'skip='+str(offset//bs),
                    'count='+str(size//bs), 'status=none']
        if output is None:
            b = self.run(*args, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
            require(len(b) == size, 'Short device read')
            return b
        with Path(output).open('xb') as f:
            self.run(*args, stdout=f, stderr=subprocess.PIPE, timeout=1200)
        require(Path(output).stat().st_size == size, 'Incomplete Data backup; leave partial file for inspection')


def capture(args):
    adb = Adb(args.adb, args.serial, su=bool(getattr(args, 'su', False)))
    props = {k: adb.text('getprop', k) for k in ('ro.bootmode','ro.twrp.version','ro.orangefox.version')}
    if adb.su:
        # Android running normally: root comes from KernelSU/Magisk, the device
        # never mounts unixnu, and every command below is a pure read.
        require('uid=0(' in adb.text('id'), 'Root (KernelSU/Magisk) required for Android capture')
        source = 'live Android root read-only (no recovery, no writes)'
    else:
        require(props['ro.bootmode'] == 'recovery' or props['ro.twrp.version'] or props['ro.orangefox.version'],
                'Enter recovery first, or pass --su for rooted Android; XNU ADB is never used')
        require('uid=0(' in adb.text('id'), 'Root recovery ADB required')
        source = 'live root recovery read-only'
    _ = source
    resolved = adb.text('readlink', '-f', TARGET)
    require(re.fullmatch(r'/dev/block/[A-Za-z0-9._-]+', resolved) is not None, 'Unexpected unixnu symlink')
    name = resolved.rsplit('/', 1)[1]
    geometry = {'resolved': resolved, 'bytes': int(adb.text('blockdev','--getsize64',TARGET)),
                'start_512': int(adb.text('cat',f'/sys/class/block/{name}/start')),
                'sectors_512': int(adb.text('cat',f'/sys/class/block/{name}/size')),
                'logical_block_bytes': int(adb.text('blockdev','--getss',TARGET))}
    require(geometry['bytes'] == PARTITION_BYTES and geometry['start_512'] == FIRST_4K*8
            and geometry['sectors_512']*512 == PARTITION_BYTES and geometry['logical_block_bytes'] == 4096,
            'Live unixnu geometry differs from qualified K60 layout')
    require(not adb.text('ls','-A',f'/sys/class/block/{name}/holders'), 'unixnu has mapped holders')
    mounts = adb.text('cat','/proc/mounts')
    require(not any(line.split()[0] in (TARGET,resolved) for line in mounts.splitlines() if line.split()),
            'unixnu must be unmounted; capture will not unmount it automatically')
    # Source paths may be aliases: mountinfo's major:minor identifies the device.
    rdev = adb.text('stat','-c','%t:%T',resolved)
    require(re.fullmatch(r'[0-9a-fA-F]+:[0-9a-fA-F]+',rdev) is not None, 'Unrecognized device major/minor')
    major, minor = (int(v,16) for v in rdev.split(':'))
    device_id = f'{major}:{minor}'
    mountinfo = adb.text('cat','/proc/self/mountinfo')
    require(not any(len(line.split()) >= 3 and line.split()[2] == device_id
                    for line in mountinfo.splitlines()), 'unixnu is mounted through a device alias')
    raw = adb.read(0,4096)
    info = manifest_info(raw)
    out = args.output_dir.resolve()
    out.mkdir(parents=True,exist_ok=False)
    (out/'shngroot.bin').write_bytes(raw)
    (out/'recovery-facts.json').write_text(json.dumps({'properties':props,'geometry':geometry,
                                                    'mounts':mounts,'mountinfo':mountinfo,'device_id':device_id},indent=2)+'\n')
    data = next(w for w in info['windows'] if w['name']=='Data')
    backup = out/'data-window.img'
    print('READ ONLY: backing up',data['size'],'bytes from unixnu offset',data['offset'],flush=True)
    adb.read(data['offset'],data['size'],backup)
    bs = read_unit(data['offset'], data['size'])
    # Hash a SECOND device read and compare. No remote temporary files, mounts or writes.
    cmd=(f'dd if={TARGET} bs={bs} skip={data["offset"]//bs} count={data["size"]//bs} status=none | sha256sum')
    hash_reply = adb.text(cmd, timeout=1200).split()
    require(bool(hash_reply), 'Empty remote hash response')
    remote = hash_reply[0].lower()
    require(re.fullmatch('[0-9a-f]{64}',remote) is not None, 'Invalid remote hash response')
    require(remote == digest_file(backup), 'Local/remote backup hashes differ')
    require(adb.read(0,4096) == raw, 'Manifest changed during backup')
    report = {'captured_at':dt.datetime.now(dt.timezone.utc).isoformat(), 'source':source,
              'geometry':geometry, 'manifest':info, 'data_backup_sha256':remote,
              'data_filesystem':gpt_apfs_info(backup), 'layout_preview':layout_preview(info)}
    if args.usage:
        report['directory_usage']=usage_info(backup)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    print('PASS: read-only backup size/hash, manifest, GPT and APFS capacity verified')


def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    subs=p.add_subparsers(dest='mode',required=True)
    off=subs.add_parser('offline',help='Inspect saved manifest and optional Data image')
    off.add_argument('--manifest',required=True,type=Path)
    off.add_argument('--data-image',type=Path)
    off.add_argument('--output',type=Path)
    off.add_argument('--usage',action='store_true',help='Read local file metadata to summarize space use; report paths may be private')
    cap=subs.add_parser('capture',help='Read/back up only in root recovery, never write device')
    cap.add_argument('--adb',required=True)
    cap.add_argument('--serial',required=True)
    cap.add_argument('--output-dir',required=True,type=Path)
    cap.add_argument('--usage',action='store_true',help='Summarize backup directory allocations locally')
    cap.add_argument('--su',action='store_true',help='Rooted Android instead of recovery: wrap reads in su -c (still read-only)')
    args=p.parse_args()
    try:
        if args.mode=='capture':
            capture(args)
        else:
            info=manifest_info(args.manifest.read_bytes())
            result={'source':'offline historical snapshot; not live phone state',
                    'partition_bytes':PARTITION_BYTES,'manifest':info,'layout_preview':layout_preview(info)}
            if args.data_image:
                require(args.data_image.stat().st_size == next(w['size'] for w in info['windows'] if w['name']=='Data'),
                        'Data image length does not match saved window')
                result['data_filesystem']=gpt_apfs_info(args.data_image)
                if args.usage:
                    result['directory_usage']=usage_info(args.data_image)
            rendered=json.dumps(result,indent=2)+'\n'
            if args.output:
                with args.output.open('x') as f: f.write(rendered)
            print(rendered,end='')
    except (ValueError,OSError,subprocess.SubprocessError) as e:
        p.exit(1,f'Data inspection stopped: {e}\n')


if __name__=='__main__':
    main()
