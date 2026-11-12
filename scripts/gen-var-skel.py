#!/usr/bin/env python3
"""Generate pong/etc/var.skel and its seed tree on Linux.

build.py data_seed() does this on macOS, but only because it receives already
mounted volumes. Every read it performs goes through tools/apfs/apfs.py, so the
same walk works here. The skeleton is what the Pong helper expands into a fresh
Data volume; without it the helper logs "var.skel unavailable" and skips the
whole directory tree (missing Preferences, Caches, Containers, ...).

usage: gen-var-skel.py --os-image IMG --out DIR
"""
import argparse
import os
import plistlib
import posixpath
import shutil
import stat
import sys
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
sys.path.insert(0, str(PROJECT / 'tools' / 'apfs'))

import apfs  # noqa: E402

# Mirrors EXTRA in userland/build.py.
EXTRA = [
    ('db/uuidtext', 0o755, 272, 272), ('db/diagnostics/timesync', 0o755, 272, 272),
    ('containers', 0o755, 0, 0), ('containers/Data', 0o755, 0, 0),
    ('containers/Shared', 0o755, 0, 0), ('containers/Bundle', 0o755, 0, 0),
    ('mobile/Containers', 0o755, 501, 501), ('mobile/Containers/Data', 0o755, 501, 501),
    ('mobile/Containers/Shared', 0o755, 501, 501),
    ('mobile/Library/Caches', 0o755, 501, 501), ('mobile/Library/Preferences', 0o755, 501, 501),
    ('mobile/Library/Logs', 0o755, 501, 501), ('root/Library', 0o700, 0, 0),
    ('mobile/Library/Logs/CrashReporter', 0o755, 501, 501),
    ('mobile/Library/CoreDuet/Knowledge', 0o700, 501, 501),
    ('mobile/Library/IdentityServices/PDS', 0o700, 501, 501),
    ('root/Library/Caches', 0o700, 0, 0), ('root/Library/Preferences', 0o700, 0, 0),
    ('root/Library/Logs', 0o700, 0, 0), ('db/timezone', 0o755, 0, 0),
    ('cores', 0o1775, 0, 0),
]
SKIP_TOP = ('staged_system_apps', 'MobileAsset')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--os-image', required=True)
    ap.add_argument('--out', required=True, type=Path)
    args = ap.parse_args()

    data = args.out / 'data-root'
    if data.exists():
        shutil.rmtree(data)
    data.mkdir(parents=True)

    c = apfs.Container(args.os_image)
    v = apfs.pick_volume(c, None)
    metadata = {}
    oid = v.lookup('/private/var')[0]

    def extract(oid, rel):
        if rel and rel.split('/')[0] in SKIP_TOP:
            return
        ino = v.inode(oid)
        dest = data / rel if rel else data
        metadata[rel] = [ino.mode, ino.owner, ino.group]
        if ino.is_dir:
            dest.mkdir(parents=True, exist_ok=True)
            for name, child, _ in v.dir_entries(oid):
                extract(child, posixpath.join(rel, name) if rel else name)
        elif ino.is_link:
            target = os.fsdecode(ino.symlink_target_bytes())
            if os.path.lexists(dest):
                dest.unlink()
            dest.symlink_to(target)
        elif ino.is_reg:
            dest.write_bytes(ino.contents())
        else:
            metadata.pop(rel, None)
            return
        if not ino.is_link:
            os.chmod(dest, ino.mode & 0o7777)

    extract(oid, '')
    c.close()

    for rel, mode, uid, gid in EXTRA:
        parts = PurePosixPath(rel).parts
        for i in range(1, len(parts) + 1):
            p = '/'.join(parts[:i])
            (data / p).mkdir(parents=True, exist_ok=True)
            metadata.setdefault(p, [stat.S_IFDIR | 0o755, uid, gid])
        metadata.setdefault(rel, [stat.S_IFDIR | mode, uid, gid])

    for name in ('com.apple.purplebuddy.plist', 'com.apple.migration.plist'):
        rel = 'mobile/Library/Preferences/' + name
        src = PROJECT / 'userland' / 'var' / rel
        value = plistlib.loads(src.read_bytes())
        if name == 'com.apple.migration.plist':
            value['LastSystemVersion'] = '20G81'
            value['DMLastMigrationResults']['buildVersion'] = '20G81'
        dest = data / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(plistlib.dumps(value, fmt=plistlib.FMT_BINARY))
        metadata[rel] = [stat.S_IFREG | 0o644, 501, 501]

    for owner, uid, gid in (('mobile', 501, 501), ('root', 0, 0)):
        rel = owner + '/Library/Preferences/.GlobalPreferences.plist'
        path = data / rel
        value = plistlib.loads(path.read_bytes()) if path.exists() else {}
        value.update(AppleLanguages=['zh-Hans-CN'], AppleLocale='zh_CN')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(plistlib.dumps(value, fmt=plistlib.FMT_BINARY))
        metadata[rel] = [stat.S_IFREG | 0o644, uid, gid]

    link = 'db/timezone/zoneinfo'
    p = data / link
    if p.is_symlink() and os.readlink(p) == '/usr/share/zoneinfo':
        p.unlink()
    if not os.path.lexists(p):
        p.symlink_to('/usr/share/zoneinfo.default')
    metadata[link] = [stat.S_IFLNK | 0o755, 0, 0]

    for rel in ('db/diagnostics/.migrated', 'db/diagnostics/timesync/.migrated',
                'db/uuidtext/.migrated'):
        q = data / rel
        q.parent.mkdir(parents=True, exist_ok=True)
        q.touch()
        metadata[rel] = [stat.S_IFREG | 0o644, 272, 272]

    (data / '.pong-data-20G81').write_text('Pong development Data seed for 16.6.1 / 20G81\n')
    metadata['.pong-data-20G81'] = [stat.S_IFREG | 0o644, 0, 0]

    lines = []
    for rel, (mode, uid, gid) in sorted(metadata.items()):
        path = '/private/var' + ('/' + rel if rel else '')
        if stat.S_ISDIR(mode) and rel:
            lines.append(f'd\t{mode & 0o7777:o}\t{uid}\t{gid}\t{path}')
    for rel, (mode, uid, gid) in sorted(metadata.items()):
        path = '/private/var/' + rel
        if stat.S_ISLNK(mode):
            lines.append(f'l\t{os.readlink(data / rel)}\t{path}')
        elif stat.S_ISREG(mode):
            lines.append(f'f\t{mode & 0o7777:o}\t{uid}\t{gid}\t{path}\t/pong/var-seed/{rel}')
    skeleton = '\n'.join(lines) + '\n'
    sizes = {}
    for rel, (mode, _, _) in metadata.items():
        if stat.S_ISREG(mode):
            sizes[rel] = (data / rel).stat().st_size
    (args.out / 'pong').mkdir(exist_ok=True)
    (args.out / 'pong' / 'var.skel').write_text(skeleton)
    print(f'entries={len(metadata)} skeleton_bytes={len(skeleton.encode())} '
          f'reg_files={len(sizes)} bytes={sum(sizes.values())}')


if __name__ == '__main__':
    main()
