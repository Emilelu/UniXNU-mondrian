#!/usr/bin/env python3
"""Verify that every `anchor-drift` verdict in the iOS16 patch report points at text
that actually exists in the 27 tree.

A patch can only be re-cut when the anchor it needs is present. The 2026-11-23
classification marked 35 patches as anchor-drift; spot checks showed several of
its anchors (`if (actual != device ||`, `k60_watch_thread`) do not exist in the
27 `bsd/kern/kern_exec.c` at all, so those patches are not anchor drift — they
target code this tree never had. P-311.
"""
import argparse
import pathlib
import re
import sys

ANCHOR = re.compile(r'anchor=`([^`]+)`')
CATEGORY = ('A', 'anchor-drift')


def rows(path):
    lines = pathlib.Path(path).read_text(encoding='utf-8', errors='replace').splitlines()
    header = lines[0].split('\t')
    for line in lines[1:]:
        if not line.strip():
            continue
        yield dict(zip(header, line.split('\t')))


def anchor_of(note):
    match = ANCHOR.search(note or '')
    return match.group(1) if match else None


def check(report, tree):
    problems = []
    counted = 0
    for row in rows(report):
        if row.get('category') not in CATEGORY:
            continue
        counted += 1
        anchor = anchor_of(row.get('note'))
        target = row.get('target_file') or ''
        if not anchor:
            problems.append(f"{row['patch']}: no anchor in note")
            continue
        found = False
        for name in target.split(';'):
            path = pathlib.Path(tree) / name
            if path.is_file() and anchor in path.read_text(encoding='utf-8', errors='replace'):
                found = True
                break
        if not found:
            problems.append(f"{row['patch']}: anchor not found in 27 tree: {anchor!r}")
    return counted, problems


def series_tree(feed, series, workdir):
    """Replay our own series on a shared clone so anchors inside files we add resolve."""
    import subprocess
    import tempfile
    work = pathlib.Path(tempfile.mkdtemp(prefix='anchor-', dir=workdir))
    subprocess.run(['git', 'clone', '-q', '--shared', str(feed), str(work)], check=True)
    applied = failed = 0
    for line in pathlib.Path(series).read_text(encoding='utf-8').splitlines():
        entry = line.strip()
        if not entry or entry.startswith('#'):
            continue
        patch = pathlib.Path(series).parent / entry
        rc = subprocess.run(['git', '-C', str(work), 'apply', str(patch)], capture_output=True)
        applied += rc.returncode == 0
        failed += rc.returncode != 0
    print(f'note: replayed series on a shared clone: {applied} applied, {failed} failed')
    return work


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', default='/mnt/e/iOS Port/Work/scratch/ios16-anchor-report.tsv')
    parser.add_argument('--tree', default='/opt/k60/trees/ios27-out/feeds/xnu-3199e8bc')
    parser.add_argument('--series', help='replay this series on a shared clone and check against it')
    parser.add_argument('--workdir', default='/mnt/e/iOS Port/Work/scratch')
    args = parser.parse_args()
    tree = series_tree(args.tree, args.series, args.workdir) if args.series else args.tree
    counted, problems = check(args.report, tree)
    for problem in problems:
        print(f'FAIL {problem}')
    print(f'{counted} anchor-drift row(s), {len(problems)} without a live anchor')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
