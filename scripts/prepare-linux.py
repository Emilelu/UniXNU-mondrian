#!/usr/bin/env python3
"""Regenerate pong/LaunchDaemons on Linux, without hdiutil or a macOS host.

prepare() in userland/build.py does the same job, but it reaches the 20G81
volumes through hdiutil, which only exists on macOS. Everything it needs is
readable through tools/apfs/apfs.py, so this script reimplements the part that
matters for a boot: read the stock job descriptors out of the OS volume, apply
the same CORE/DENY/BOOT_SKIP policy, and write the curated set as binary plists
that the kernel can deploy into a writable Data volume.

What is deliberately NOT reimplemented:
  * apply(): moves stock LaunchDaemons, renames sbin/launchd. The sealed root
    cannot be modified from here, and init binds over the live tree instead.
  * compile_init()/compile_ui(): they need the iOS SDK headers. The binaries
    those steps produce are already embedded in the kernel.

usage: prepare-linux.py --os-image IMAGE --out DIR [--limit N]
"""
import argparse
import ast
import json
import os
import plistlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
sys.path.insert(0, str(PROJECT / 'tools' / 'apfs'))

import apfs  # noqa: E402


def parse_constants():
    """Read the policy tables from build.py/mkjobs.py as data, not by import.

    Importing build.py would pull in subprocess/xcrun paths that do not exist
    here; the tables themselves are literals.
    """
    build = ast.parse((PROJECT / 'userland' / 'build.py').read_text())
    mk = ast.parse((PROJECT / 'userland' / 'mkjobs.py').read_text())
    found = {}

    def grab(tree, name):
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == name for t in node.targets):
                value = node.value
                # CORE is a multi-line literal followed by .split(); flatten the
                # adjacent string pieces the same way Python does.
                if isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute) \
                        and value.func.attr == 'split' and value.args == []:
                    value = value.func.value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    return value.value
                return ast.literal_eval(value)
        raise SystemExit('missing constant %s' % name)

    found['CORE'] = grab(build, 'CORE').split()
    found['BOOT_SKIP'] = grab(build, 'BOOT_SKIP')
    found['RESTORED_SOFTWARE'] = grab(build, 'RESTORED_SOFTWARE')
    found['TRIGGERS'] = grab(build, 'TRIGGERS')
    deny = grab(mk, 'DENY')
    found['DENY'] = tuple(w for w in deny if w not in found['RESTORED_SOFTWARE'])
    return found


def volume(image):
    container = apfs.Container(str(image))
    return container, apfs.pick_volume(container, None)


def read_path(vol, path):
    hit = vol.lookup(path)
    if hit is None:
        return None
    return vol.inode(hit[0]).contents()


def list_dir(vol, path):
    hit = vol.lookup(path)
    if hit is None or hit[1] != 4:
        return []
    return sorted(vol.dir_entries(hit[0]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--os-image', required=True)
    ap.add_argument('--cryptex-image')
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--limit', type=int, default=0, help='stop after N jobs (smoke test)')
    args = ap.parse_args()

    policy = parse_constants()
    CORE = set(policy['CORE'])
    DENY = policy['DENY']
    BOOT_SKIP = policy['BOOT_SKIP']
    TRIGGERS = policy['TRIGGERS']

    container, vol = volume(args.os_image)
    dest = args.out / 'pong' / 'LaunchDaemons'
    dest.mkdir(parents=True, exist_ok=True)

    report = []
    written = 0
    for folder in ('LaunchDaemons', 'LaunchAngels'):
        for name, fid, kind in list_dir(vol, '/System/Library/' + folder):
            if not name.endswith('.plist'):
                continue
            raw = vol.inode(fid).contents()
            try:
                job = plistlib.loads(raw)
            except Exception as exc:
                report.append(dict(source=name, action='unreadable', reason=str(exc)))
                continue
            label = job.get('Label', name[:-6])
            program = job.get('Program') or (job.get('ProgramArguments') or [''])[0]
            core = label in CORE
            reason = None
            if not program:
                reason = 'no program'
            elif not core and label in BOOT_SKIP:
                reason = 'Pong boot: ' + BOOT_SKIP[label]
            elif not core and any(s in label for s in DENY):
                reason = 'HackiOS unsupported-service policy'
            elif not core and not job.get('MachServices'):
                reason = 'non-core job without MachServices'
            action = 'excluded' if reason else ('boot' if core else 'on-demand')
            report.append(dict(source=folder + '/' + name, label=label, program=program,
                               action=action, reason=reason))
            if reason:
                continue
            if core:
                job.pop('_LimitLoadToDeviceTree', None)
            else:
                if label not in ('com.apple.contextstored', 'com.apple.biomed'):
                    for key in TRIGGERS:
                        job.pop(key, None)
            job['StandardErrorPath'] = job['StandardOutPath'] = '/dev/console'
            legacy = job.pop('EnvironmentalVariables', None)
            if isinstance(legacy, dict):
                job['EnvironmentVariables'] = {**legacy, **job.get('EnvironmentVariables', {})}
            interval = job.get('ThrottleInterval')
            if isinstance(interval, str) and interval.isdecimal():
                job['ThrottleInterval'] = int(interval)
            if label == 'com.apple.backboardd':
                job.setdefault('EnvironmentVariables', {}).update({
                    'OS_ACTIVITY_DT_MODE': 'YES',
                    'CA_FORCE_TIMER': '1', 'CA_DISABLE_DISPLAY_IDLE': '1',
                })
            (dest / (label + '.plist')).write_bytes(
                plistlib.dumps(job, fmt=plistlib.FMT_BINARY))
            written += 1
            if args.limit and written >= args.limit:
                break
        if args.limit and written >= args.limit:
            break

    counts = {'boot': 0, 'on-demand': 0, 'excluded': 0}
    for r in report:
        counts[r['action']] = counts.get(r['action'], 0) + 1
    (args.out / 'jobs-report.json').write_text(json.dumps(
        dict(written=written, counts=counts, jobs=report), indent=2, ensure_ascii=False))
    print(json.dumps(dict(written=written, counts=counts), indent=2))


if __name__ == '__main__':
    main()
