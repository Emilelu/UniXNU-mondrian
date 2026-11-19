#!/usr/bin/env python3
"""Refuse a sampled log line that a short flight can never reach.

Three flights were wasted on three separate probes whose gate was
`if(!(++n & 31))` or `if(!(n % 60))`:

  * P-233  PongMetalScanout's frame report fired every 60 frames; the flight presented 22
           frames, so the flight card's "at least two samples" was unsatisfiable.
  * P-241  the telemetry rows were only emitted at 5/20/60 s; a 200 s flight went silent
           after 60 s and the steady-state criterion had no data.
  * P-233 again, 2026-11-19: the submit probe fired every 32nd submission, the flight made
           about fifteen, and the judge reported "no PONG SUB line ... the probe did not
           reach the image" while the string was provably in the kernel.

The shape is always the same: a sampling gate whose first sample needs more events than a
quiet flight produces, so the criterion that depends on it cannot pass and the log reads as
"the thing is fast" or "the probe is missing". Prose did not stop it three times, so this
gate looks for the pattern directly.

A gate is accepted when the same condition also admits an early sample, i.e. the file
contains `<= <k>` (or `< <k>`) for some small k in the same condition. `i % 8` inside a
loop that is itself bounded by the audit cadence is not a report gate; only lines that
call a reporting function are checked.
"""
import os
import re
import sys

REPO = os.environ.get('K60_REPO') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOTS = ('drivers',)

# A modulo/mask that gates a report, and the early-sample escape that makes it reachable.
GATE = re.compile(r'if\s*\(([^)]*?)(?:%|&)\s*(\d+)\s*\)')
EARLY = re.compile(r'<=\s*\d+|< *\d+')
REPORT = re.compile(r'\b(IOLog|printf|report|note|NBLOG|k60_log)\b')


def sources():
    for root in ROOTS:
        base = os.path.join(REPO, root)
        for directory, _, names in os.walk(base):
            for name in names:
                if name.endswith(('.c', '.h', '.cpp', '.mm', '.m')):
                    yield os.path.join(directory, name)


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')

    problems = []
    checked = 0
    for path in sources():
        try:
            text = open(path, encoding='utf-8', errors='replace').read()
        except OSError:
            continue
        lines = text.split('\n')
        for number, line in enumerate(lines, 1):
            match = GATE.search(line)
            if not match:
                continue
            divisor = int(match.group(2))
            if divisor < 4:                     # a 1-in-2 or 1-in-3 gate always fires early
                continue
            # `& 4095` and `% 4096` are page-alignment tests, not sampling: they appear inside
            # validity conditions next to a log call for unrelated reasons, and reporting them
            # would train the next person to add waivers to this gate.
            if divisor in (4095, 4096, 8191, 8192, 65535, 65536):
                continue
            # The report may be on this line or within the next three (a wrapped if body).
            window = ' '.join(lines[number - 1:number + 3])
            if not REPORT.search(window):
                continue
            checked += 1
            if not EARLY.search(match.group(1)):
                problems.append((path, number, line.strip(), divisor))

    rel = lambda p: os.path.relpath(p, REPO).replace('\\', '/')
    if problems:
        print('❌ %d sampled report(s) need more events than a quiet flight produces' % len(problems))
        for path, number, line, divisor in problems:
            print('   %s:%d  1 in %d, no early sample: %s' % (rel(path), number, divisor, line))
        print('   add an early window (`n <= 4 ||`), because a failed probe reads as "no data"')
        print('   and "no data" is read as "the cost is not there" (P-233, P-241).')
        return 1
    print('✅ probe cadence: %d sampled report(s), all reachable in a short flight' % checked)
    return 0


if __name__ == '__main__':
    sys.exit(main())
