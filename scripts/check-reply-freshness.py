#!/usr/bin/env python3
"""Check that every lane report got a Lead reply, promptly (2026-11-21 user rule).

Each lane writes `reply-<lane>*.md` under the scratch directory and the Lead answers
in the same file. A report nobody answered, or one whose answer predates it, is what
this gate refuses: the agent then works from stale instructions (iron-12) and the
Lead looks like it queues instead of answering.

Format read from each file:
    delivery: steer
    delivery: followup, steer-rejected: <reason>
    lead-reply: 2026-11-21T15:40

Rules:
  * a file containing a report (`【`) must carry a `delivery:` line;
  * it must also carry `lead-reply:`; if the file has been touched more than ten
    minutes after that timestamp, the report is newer than the answer -> FAIL within
    24 h, a note up to 72 h, and a stale note after that.

Paths: `K60_SCRATCH` if set, else the WSL mount, else the Windows path, so the gate
runs the same way under WSL python and MSYS python.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import pathlib
import re
import sys

WSL_SCRATCH = pathlib.Path('/mnt/e/iOS Port/Work/scratch')
WIN_SCRATCH = pathlib.Path('E:/iOS Port/Work/scratch')
SCRATCH = pathlib.Path(os.environ.get('K60_SCRATCH')
                       or (WSL_SCRATCH if WSL_SCRATCH.is_dir() else WIN_SCRATCH))
PROMPT_HOURS = 24
STALE_HOURS = 72
REPLY = re.compile(r'^lead-reply:\s*(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}).*$', re.MULTILINE)
DELIVERY = re.compile(r'^delivery:\s*(steer|followup,\s*steer-rejected:\s*\S.+)$',
                      re.MULTILINE)
REPORT = re.compile(r'【[^】]*汇报】')


def parse_time(text):
    return dt.datetime.strptime(text, '%Y-%m-%dT%H:%M')


def check(path, now, prompt_hours=PROMPT_HOURS, stale_hours=STALE_HOURS):
    text = path.read_text(encoding='utf-8', errors='replace')
    problems, notes = [], []
    if not REPORT.search(text):
        return problems, notes
    if not DELIVERY.search(text):
        problems.append('%s: has a report but no "delivery: steer|followup, '
                        'steer-rejected:" line' % path.name)
    match = REPLY.search(text)
    touched = dt.datetime.fromtimestamp(path.stat().st_mtime)
    if match is None:
        age = (now - touched).total_seconds() / 3600.0
        line = '%s: a report is waiting for a Lead reply (%.1f h old)' % (path.name, age)
        if age <= prompt_hours:
            problems.append(line + '; answer it this round')
        elif age <= stale_hours:
            notes.append(line)
        else:
            notes.append(line + '; stale, ask whether the lane is still alive')
        return problems, notes
    replied = parse_time(match.group(1))
    if touched > replied + dt.timedelta(minutes=10):
        problems.append('%s: report written at %s is newer than lead-reply %s; answer it'
                        % (path.name, touched.strftime('%Y-%m-%dT%H:%M'),
                           replied.strftime('%Y-%m-%dT%H:%M')))
    return problems, notes


def selftest():
    import tempfile

    cases = 0

    def fixture(body, age_minutes=0):
        handle = tempfile.NamedTemporaryFile('w', suffix='.md', delete=False,
                                             encoding='utf-8', newline='\n')
        handle.write(body)
        handle.close()
        path = pathlib.Path(handle.name)
        stamp = dt.datetime.now() - dt.timedelta(minutes=age_minutes)
        os.utime(path, (stamp.timestamp(), stamp.timestamp()))
        return path

    now = dt.datetime.now()
    answered = '【audio-agent 进度汇报】\ndelivery: steer\nlead-reply: %s\n' % (
        (now - dt.timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'))
    problems, _ = check(fixture(answered, 60), now)
    assert not problems, problems
    cases += 1

    no_reply = '【audio-agent 进度汇报】\ndelivery: steer\n'
    problems, _ = check(fixture(no_reply, 30), now)
    assert problems and 'waiting for a Lead reply' in problems[0], problems
    cases += 1

    no_delivery = '【bt-agent 进度汇报】\nlead-reply: %s\n' % now.strftime('%Y-%m-%dT%H:%M')
    problems, _ = check(fixture(no_delivery, 10), now)
    assert any('delivery:' in problem for problem in problems), problems
    cases += 1

    newer = '【wifi-agent 进度汇报】\ndelivery: steer\nlead-reply: %s\n' % (
        (now - dt.timedelta(hours=5)).strftime('%Y-%m-%dT%H:%M'))
    problems, _ = check(fixture(newer, 0), now)
    assert any('newer than lead-reply' in problem for problem in problems), problems
    cases += 1

    quiet = 'no report here\n'
    problems, notes = check(fixture(quiet, 5), now)
    assert not problems and not notes, (problems, notes)
    cases += 1

    print('%d/%d checks passed' % (cases, cases))
    print('OK the reply gate refuses an unanswered, an unlabelled and a stale-answer report')
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scratch', type=pathlib.Path, default=SCRATCH)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args(argv)
    if args.self_test:
        return selftest()
    if not args.scratch.is_dir():
        print('FAIL: %s is not here; an absent inbox is not an answered one (P-279)'
              % args.scratch)
        return 2
    now = dt.datetime.now()
    files = sorted(args.scratch.glob('reply-*.md'))
    problems, notes = [], []
    for path in files:
        found, observed = check(path, now)
        problems += found
        notes += observed
    for note in notes:
        print('note reply: %s' % note)
    for problem in problems:
        print('FAIL reply: %s' % problem)
    if problems:
        return 1
    print('OK reply-freshness: %d report file(s), every waiting report has an answer'
          % len(files))
    return 0


if __name__ == '__main__':
    sys.exit(main())
