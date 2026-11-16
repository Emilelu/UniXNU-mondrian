#!/usr/bin/env python3
"""Guard the two claims a firmware-volume manual must not make (P-216).

The firmware volume is not reproducible: LLD derives a CodeView build-id from
its input set, and the volume is compressed, so one changed GUID rewrites the
whole compressed section.  Three rebuilds from one pin on 2026-11-16 gave three
hashes (`4bbe7601`, `ce12d145`, `77ad2474`, `9f20de15388a`), while the same
payload with a rebuilt volume booted to SpringBoard 129.

So the manual must not:

  1. claim that the same source yields the same bytes, or that rebuilding is
     deterministic;
  2. present a firmware-volume hash as an identity ("same firmware", "proves it
     is the same build") instead of as one build's identifier.

`docs/engineering/PITFALLS.md` is deliberately NOT audited: quoting a wrong
statement is a pitfall entry's job, and a gate that forbids the quote would
forbid the lesson.  Only documents that state current operating rules are read.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Documents that state current operating rules.  Missing files are skipped so
# the gate can run from a branch that has not merged the manual yet.
MANUALS = ('docs/engineering/FIRMWARE-REBUILD.md',)

# Sentences that claim reproducibility.  Matched per line; the wording differs
# between sections, so the patterns stay narrow and literal.
REPRODUCIBLE_CLAIMS = (
    re.compile(r'同样的源码\s*\+\s*同样的 pin\s*(?:⇒|=>|→)\s*同一个 FD'),
    re.compile(r'同源\s*(?:⇒|=>|→)\s*同字节'),
    re.compile(r'它是确定性的'),
    re.compile(r'the same source[^.\n]{0,40}(?:⇒|=>|yields)[^.\n]{0,20}same bytes', re.I),
    re.compile(r'reproducible[^.\n]{0,30}firmware volume', re.I),
)

# A hash becomes a wrong claim only when the same line also treats it as an
# identity.  Listing hashes in a table is exactly what the manual should do.
HASH = re.compile(r'`?[0-9a-f]{12,64}`?', re.I)
IDENTITY_CLAIM = re.compile(
    r'身份|同一个固件|同一份固件|同一份源码|可复现|可重现|identity|reproducib|same firmware', re.I
)
BUILD_MARKER = re.compile(
    r'一次构建|本次构建|one build|this build|build identifier|构建标识|不是身份|not an identity', re.I
)

# Lines that explicitly refute the claim are the fix, not the defect.
QUOTE_ALLOWANCE = re.compile(
    r'这句是错的|是错的|是错误的|不可比|不能当|不要用|不得再出现|不\*\*是\*\*确定性|refus|不是「身份」|不是确定性', re.I
)


def check(repo: Path = REPO, manuals=None) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    notes: list[str] = []
    docs = MANUALS if manuals is None else manuals
    seen = 0
    for rel in docs:
        path = repo / rel
        if not path.is_file():
            notes.append(f'skip: {rel} is not in this tree')
            continue
        seen += 1
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if QUOTE_ALLOWANCE.search(line):
                continue
            for pattern in REPRODUCIBLE_CLAIMS:
                if pattern.search(line):
                    problems.append(
                        f'{rel}:{number}: claims the firmware volume is reproducible '
                        f'({pattern.pattern}); three rebuilds from one pin gave three '
                        f'hashes (P-216)'
                    )
                    break
            if HASH.search(line) and IDENTITY_CLAIM.search(line) and not BUILD_MARKER.search(line):
                problems.append(
                    f'{rel}:{number}: presents a firmware-volume hash as an identity rather '
                    f'than as one build\'s identifier (P-216)'
                )
    if not seen:
        notes.append('skip: no firmware-volume manual is present')
    return problems, notes


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default=str(REPO), help='repository root')
    args = parser.parse_args(argv)
    problems, notes = check(Path(args.repo))
    for note in notes:
        print(f'note: {note}')
    if problems:
        print('FAIL: the firmware-volume manual makes an unreproducible claim', file=sys.stderr)
        for problem in problems:
            print(f'  - {problem}', file=sys.stderr)
        return 1
    print('✅ firmware volume: the manual does not claim it is reproducible')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
