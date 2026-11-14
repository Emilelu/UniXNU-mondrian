#!/usr/bin/env python3
"""Check 0617 against the exact supported predecessor sections, without a build.

--xnu is an existing pre-0617 patched tree for handoff.c/h and IOKitBSDInit.
The late hook fixture is the exact 0614 postimage, since old global build trees
may contain obsolete late hooks. This is not a full kernel-series replay.
"""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[2]
TARGETS = ('bsd/dev/pong_handoff.c', 'bsd/dev/pong_handoff.h',
           'bsd/dev/pong_adsp_startup.c', 'iokit/bsddev/IOKitBSDInit.cpp',
           'bsd/kern/kern_exec.c')


def sections(text):
    lines = text.splitlines(keepends=True)
    anchors = [i for i in range(len(lines)-1)
               if lines[i].startswith('--- ') and lines[i+1].startswith('+++ ')]
    for i, start in enumerate(anchors):
        end = anchors[i+1] if i+1 < len(anchors) else len(lines)
        path = lines[start+1][4:].strip().split('\t')[0]
        if path.startswith('b/'):
            path = path[2:]
        if path not in TARGETS:
            continue
        body = lines[start:end]
        stop = next((j for j in range(2, len(body))
                     if body[j].startswith('diff --git ')), len(body))
        yield path, ''.join(body[:stop])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--xnu', required=True, type=Path)
    args = parser.parse_args()
    if not shutil.which('patch'):
        raise SystemExit('GNU patch is required')
    with tempfile.TemporaryDirectory(prefix='k60-handoff-patches-') as tmp:
        root = Path(tmp)
        for name in TARGETS[:2] + TARGETS[3:4]:
            source = args.xnu / name
            if not source.is_file():
                raise SystemExit('predecessor source missing: ' + str(source))
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        late = root / TARGETS[4]
        late.parent.mkdir(parents=True, exist_ok=True)
        predecessor = (REPO / 'patches/xnu/0614-k60-adsp-call-site.patch').read_text().splitlines(keepends=True)
        late.write_text(''.join(line[1:] for line in predecessor[3:]
                               if line.startswith((' ', '+'))))
        patch = REPO / 'patches/xnu/0617-k60-adsp-glink-handoff.patch'
        touched = []
        for target, text in sections(patch.read_text()):
            (root / target).parent.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-d', str(root)],
                                    input=text, capture_output=True, text=True)
            if result.returncode:
                raise SystemExit(target + '\n' + result.stdout + result.stderr)
            touched.append(target)
        assert set(touched) == set(TARGETS)
        expected = {
            TARGETS[0]: ('K60HandoffBuild.c', {'"K60HandoffBuild.h"': '"pong_handoff.h"'}),
            TARGETS[1]: ('K60HandoffBuild.h', {'"K60Smem.h"': '"pong_smem.h"'}),
            TARGETS[2]: ('K60AdspStartup.c', {}),
        }
        for path, (canonical, replacements) in expected.items():
            want = (REPO / 'drivers/PongPower' / canonical).read_text()
            for before, after in replacements.items():
                want = want.replace(before, after)
            assert (root / path).read_text() == want, path + ': canonical source differs'
        early = (root / TARGETS[3]).read_text()
        assert early.index('(void)k60_adsp_handoff_publish();') < early.index('IOService::publishResource("IOBSD")')
        assert early.index('IOService::publishResource("IOBSD")') < early.index('\n\tk60_physical_battery_start();')
        assert 'if (k60_adsp_startup_claim(2u))' in late.read_text()
        assert late.read_text().count('(void)k60_adsp_probe_from_handoff();') == 1
        print('TESTS OK: 5 integration sections, 3 canonical mirrors, early order and late exclusion')
        print('Scope: predecessor fixture only; full clean-tree kernel build remains required')


if __name__ == '__main__':
    main()
