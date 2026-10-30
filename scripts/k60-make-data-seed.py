#!/usr/bin/env python3
"""Build the K60 Data seed: a small raw APFS volume carrying the OS image's private/var.

Runs on macOS only (hdiutil/diskutil). The OS volume image is pulled from the
remote IPSW with HTTP range requests - the multi-GB IPSW is never downloaded as
a whole. The output is a raw 32 MiB APFS container (NXSB magic at byte 32) plus
a JSON report (volume UUID, hashes, copy counts) written next to it.

    python3 k60-make-data-seed.py --profile profiles/os/<p>/profile.toml --output k60-data-seed.dbr
"""
import argparse
import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import plistlib
import tomllib

CHUNK = 8 << 20


class RangeFile(io.RawIOBase):
    """A read-only seekable view of a remote file, fetched with range requests and a small block cache."""

    def __init__(self, url, block=CHUNK):
        self.url, self.block, self.cache = url, block, {}
        request = urllib.request.Request(url, method='HEAD')
        with urllib.request.urlopen(request, timeout=60) as response:
            self.size = int(response.headers['Content-Length'])
        probe = urllib.request.Request(url, headers={'Range': 'bytes=0-0'})
        with urllib.request.urlopen(probe, timeout=60) as response:
            if response.status != 206:
                raise SystemExit('the IPSW URL does not support HTTP range requests')

    def seekable(self):
        return True

    def readable(self):
        return True

    def seek(self, offset, whence=0):
        if whence == 1:
            offset += self.position
        elif whence == 2:
            offset += self.size
        self.position = offset
        return self.position

    def tell(self):
        return self.position

    def read(self, amount=-1):
        if amount is None or amount < 0:
            amount = self.size - self.position
        if amount <= 0 or self.position >= self.size:
            return b''
        end = min(self.position + amount, self.size)
        parts, pos = [], self.position
        while pos < end:
            index = pos // self.block
            start, stop = index * self.block, (index + 1) * self.block
            if index not in self.cache:
                if len(self.cache) >= 8:
                    self.cache.clear()
                request = urllib.request.Request(self.url, headers={'Range': f'bytes={start}-{stop - 1}'})
                with urllib.request.urlopen(request, timeout=300) as response:
                    self.cache[index] = response.read()
            block = self.cache[index]
            parts.append(block[pos - start:end - start])
            pos = min(stop, end)
        self.position = end
        return b''.join(parts)

    def readinto(self, buffer):
        data = self.read(len(buffer))
        buffer[:len(data)] = data
        return len(data)


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, default=Path('profiles/os/ipados-16.6.1-20G81/profile.toml'))
    parser.add_argument('--output', type=Path, default=Path('k60-data-seed.dbr'))
    parser.add_argument('--size', default='32m',
                        help='hdiutil -size value for the APFS container (default 32m; '
                             'read-write mounts need far more than that)')
    args = parser.parse_args()
    if sys.platform != 'darwin':
        raise SystemExit('this script needs macOS hdiutil and diskutil')
    profile = tomllib.load(open(args.profile, 'rb'))
    ipsw = profile['ipsw']
    print(f"ipsw: {ipsw['product']} {ipsw['version']} ({ipsw['build']}) <- {ipsw['url']}", flush=True)

    stream = RangeFile(ipsw['url'])
    archive = zipfile.ZipFile(stream)
    manifest = plistlib.loads(archive.read('BuildManifest.plist'))
    if (manifest['ProductVersion'], manifest['ProductBuildVersion']) != (ipsw['version'], ipsw['build']) \
            or ipsw['product'] not in manifest['SupportedProductTypes']:
        raise SystemExit(f"this IPSW is {manifest['ProductVersion']} ({manifest['ProductBuildVersion']}) "
                         f"for {', '.join(manifest['SupportedProductTypes'])}")
    identity = next(item for item in manifest['BuildIdentities']
                    if item['Info']['DeviceClass'] == ipsw['device_class']
                    and item['Info']['RestoreBehavior'] == 'Erase'
                    and int(item['ApChipID'], 16) == ipsw['chip_id']
                    and int(item['ApBoardID'], 16) == ipsw['board_id'])
    member = identity['Manifest']['OS']['Info']['Path']
    entry = archive.getinfo(member)
    print(f'ipsw: extracting OS ({member}, {entry.file_size >> 20} MiB via range requests)', flush=True)

    with tempfile.TemporaryDirectory(prefix='k60-seed-') as temp:
        temp = Path(temp)
        dmg = temp / Path(member).name
        digest = hashlib.sha256()
        with archive.open(member) as source, dmg.open('xb') as target:
            while chunk := source.read(CHUNK):
                target.write(chunk)
                digest.update(chunk)
        if dmg.stat().st_size != entry.file_size:
            raise SystemExit('incomplete extraction of the OS volume image')
        source_sha256 = digest.hexdigest()
        print(f'ipsw: OS volume image sha256 {source_sha256}', flush=True)

        attached = plistlib.loads(subprocess.check_output(
            ['hdiutil', 'attach', '-nobrowse', '-readonly', '-noverify', '-noautofsck', '-plist', str(dmg)]))
        whole_disk = attached['system-entities'][0]['dev-entry']
        mounts = [Path(e['mount-point']) for e in attached['system-entities'] if e.get('mount-point')]
        try:
            os_root = next((m for m in mounts if (m / 'sbin/launchd').is_file()), None)
            if os_root is None:
                raise SystemExit(f'no mounted volume carries sbin/launchd; mounts: {[str(m) for m in mounts]}')
            print(f'os: system volume at {os_root}', flush=True)
            launchd_sha256 = sha256_of(os_root / 'sbin/launchd')
            os_volume_uuid = None
            for entity in attached['system-entities']:
                if entity.get('mount-point') == str(os_root):
                    os_volume_uuid = plistlib.loads(subprocess.check_output(
                        ['diskutil', 'info', '-plist', entity['dev-entry']]))['VolumeUUID']
                    break
            if os_volume_uuid is None:
                raise SystemExit('could not read the OS volume UUID for root matching')
            print(f'os: volume UUID {os_volume_uuid}', flush=True)

            image = args.output.resolve()
            if image.exists():
                raise SystemExit(f'refusing to overwrite an existing seed: {image}')
            subprocess.run(['hdiutil', 'create', '-size', args.size, '-layout', 'NONE', '-fs', 'APFS',
                            '-volname', 'OwnerData', '-type', 'UDTO', str(image)], check=True)
            # hdiutil create appends .cdr to UDTO images whose name lacks it.
            created = image if image.is_file() else image.with_name(image.name + '.cdr')
            print(f'seed: created {created}', flush=True)
            # macOS /var is a symlink to /private/var: resolve it or the plist mount-point never matches.
            mount = (temp / 'seed').resolve()
            mount.mkdir()
            attached = plistlib.loads(subprocess.check_output(
                ['hdiutil', 'attach', '-nobrowse', '-owners', 'off', '-mountpoint', str(mount), '-plist', str(created)]))
            volume_device = None
            try:
                volumes = [e for e in attached['system-entities'] if e.get('mount-point') == str(mount)]
                if len(volumes) != 1:
                    raise SystemExit(f'expected exactly one newly formatted volume at {mount}; '
                                     f'got: {[e.get("mount-point") for e in attached["system-entities"]]}')
                volume_device = volumes[0]['dev-entry']
                volume_uuid = plistlib.loads(subprocess.check_output(
                    ['diskutil', 'info', '-plist', volume_device]))['VolumeUUID']
                source = os_root / 'private/var'
                count = total = 0
                if source.is_dir():
                    for current, dirs, files in os.walk(source, followlinks=False):
                        dirs[:] = [name for name in dirs if name != 'staged_system_apps']
                        destination = mount / Path(current).relative_to(source)
                        destination.mkdir(exist_ok=True)
                        os.chmod(destination, stat.S_IMODE(Path(current).stat().st_mode))
                        for name in list(dirs) + files:
                            src, dst = Path(current) / name, destination / name
                            if src.is_symlink():
                                os.symlink(os.readlink(src), dst)
                                if name in dirs:
                                    dirs.remove(name)
                            elif src.is_file():
                                shutil.copy2(src, dst)
                                count += 1
                                total += src.stat().st_size
                else:
                    print('os: WARNING - the OS volume has no private/var; the seed keeps only the runtime directories', flush=True)
                for name in ('keybags', 'mobile/tmp', 'tmp', 'run'):
                    (mount / name).mkdir(parents=True, exist_ok=True)
                os.chmod(mount / 'tmp', 0o1777)
                print(f'seed: copied {count} files ({total} bytes) from {source}', flush=True)
            finally:
                subprocess.run(['hdiutil', 'detach', attached['system-entities'][0]['dev-entry']], check=True)
        finally:
            subprocess.run(['hdiutil', 'detach', whole_disk], capture_output=True)

    data = created.read_bytes()
    if len(data) % 512 == 0 and data[-512:-508] == b'koly':
        print('seed: stripping the 512-byte UDIF trailer', flush=True)
        data = data[:-512]
        created.write_bytes(data)
    if len(data) != 32 * 1024 ** 2 or data[32:36] != b'NXSB':
        raise SystemExit(f'unexpected seed image: {len(data)} bytes, magic {data[32:36]!r}; '
                         'host formatting did not produce a raw 32 MiB APFS container')
    if created != image:
        created.rename(image)
    report = {'volume_uuid': volume_uuid, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
              'source_member': member, 'source_sha256': source_sha256, 'launchd_sha256': launchd_sha256,
              'os_volume_uuid': os_volume_uuid,
              'source_regular_files': count, 'source_regular_bytes': total,
              'seed': 'Original OS private/var excluding staged_system_apps; symlinks preserved; runtime directories added',
              'guest_mutable': True, 'initial_seed_signature_verified': False,
              'production_storage_qualified': False}
    image.with_suffix(image.suffix + '.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
