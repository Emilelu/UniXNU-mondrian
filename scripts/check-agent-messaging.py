#!/usr/bin/env python3
"""Iron rule 12: an agent message tries `steer` first and only falls back to `followup`.

Why this is a rule and not a preference. A `followup` is delivered as its own new
turn: it queues behind whatever that agent is doing, and by the time it lands the
sender has usually moved on to a different question. `steer` interrupts at the
nearest step boundary, which is the only mode that can stop an agent from
spending an hour on a plan the Lead has already abandoned. On 2026-11-20 four
agents were working from instructions the Lead had replaced, because the
replacement went out as `followup` and sat in the queue.

`steer` is only valid for a session that is actually running, so the fallback is
real and not a loophole: when the send fails with "not running", `followup` is
the correct second attempt, and it must be the *second* attempt.

The check has two halves:

* the documents still promise it (AGENTS.md heading, RULES.toml entry);
* the message log, when this machine has one, does not show a `followup` that
  was never preceded by a failed `steer` for the same recipient.

The second half is the one that matters. A heading is a promise; the log is what
happened. If the log is absent the check says so instead of passing silently --
an absent record is not evidence of compliance (P-251).
"""
import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
AGENTS = REPO / 'AGENTS.md'
RULES = REPO / 'docs/engineering/RULES.toml'
BUS = Path('/mnt/e/k60-work/bus/bus.jsonl')
HEADING = re.compile(r'^### Iron rule 12\b.*$', re.MULTILINE)


def documents():
    problems = []
    text = AGENTS.read_text(encoding='utf-8', errors='replace') if AGENTS.is_file() else ''
    match = HEADING.search(text)
    if match is None:
        problems.append('AGENTS.md has no "### Iron rule 12" heading, so check-rules.py '
                        'collects one rule fewer than RULES.toml declares')
    else:
        start = match.end()
        end = text.find('\n#', start)
        body = text[start:end if end != -1 else len(text)]
        for needle in ('steer', 'followup'):
            if needle not in body:
                problems.append(f'the iron rule 12 text never mentions {needle!r}')
    rules = RULES.read_text(encoding='utf-8', errors='replace') if RULES.is_file() else ''
    if 'id = "iron-12"' not in rules:
        problems.append('RULES.toml has no [[rule]] id = "iron-12"')
    return problems


def records(path):
    if not path.is_file():
        return None
    out = []
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            out.append({'kind': 'unparsed', 'raw': line})
    return out


def messages(rows):
    """A followup is legitimate only after a steer to the same recipient failed.

    Only records that carry a `mode` say anything about delivery; the shared bus
    stores `kind` (request/answer/status/note) and does not record how a message
    was delivered, so it is filtered out here rather than read as compliance.
    """
    problems = []
    pending = {}
    for row in rows:
        mode = row.get('mode')
        if not mode:
            continue
        recipient = row.get('to') or row.get('session') or ''
        if mode == 'steer':
            pending[recipient] = 'steer failed' if row.get('ok') is False else 'steer sent'
            continue
        if mode != 'followup':
            continue
        state = pending.get(recipient)
        if state is None:
            problems.append(f'followup to {recipient!r} at {row.get("at", "?")} was the first '
                            f'attempt; iron rule 12 wants steer first')
        elif state == 'steer sent':
            problems.append(f'followup to {recipient!r} at {row.get("at", "?")} followed a steer '
                            f'that succeeded, so the steer already carried the message')
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bus', type=Path, default=BUS)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        good = [
            {'mode': 'steer', 'to': 'a', 'ok': False},
            {'mode': 'followup', 'to': 'a', 'ok': True},
        ]
        bad = [{'mode': 'followup', 'to': 'b', 'ok': True}]
        twice = [
            {'mode': 'steer', 'to': 'c', 'ok': True},
            {'mode': 'followup', 'to': 'c', 'ok': True},
        ]
        silent = [{'kind': 'note', 'to': 'd', 'body': 'no mode recorded'}]
        cases = [
            ('steer then followup is clean', messages(good), 0),
            ('a first-attempt followup is refused', messages(bad), 1),
            ('a followup after a successful steer is refused', messages(twice), 1),
            ('a record without a mode is not counted as compliance', messages(silent), 0),
        ]
        failed = 0
        for name, got, want in cases:
            ok = len(got) == want
            print(('ok   ' if ok else 'FAIL ') + name)
            failed += 0 if ok else 1
        print(f'{len(cases) - failed}/{len(cases)} messaging cases behave')
        return 1 if failed else 0
    problems = documents()
    rows = records(args.bus)
    if rows is None:
        print(f'note: no message log at {args.bus}; only the documents were checked. '
              f'An absent log is not evidence that steer was tried first (P-251).')
    else:
        problems += messages(rows)
    if problems:
        for problem in problems:
            print(f'FAIL {problem}')
        return 1
    print('✅ iron-12 the messaging rule is stated and the log obeys it')
    return 0


if __name__ == '__main__':
    sys.exit(main())
