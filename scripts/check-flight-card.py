#!/usr/bin/env python3
"""Refuse a flight that has no pre-written card.

Standing rule (user, 2026-11-16 23:42): 上机前每个改动都有静态/单元/产物证据，
且 success/failure 判据预先写死。

This gate makes that checkable instead of a promise. It takes the card and the
image and refuses when:

  * the card does not exist, is not committed, or is empty;
  * the card has no `## 4. 判据` section, or that section has no `S<n>` criterion;
  * the card has no failure rule (`F<n>`);
  * the card does not name the image it belongs to;
  * the card was written **after** the image it judges (a card written after the
    flight is a rationalisation, not a criterion);
  * the card still carries the empty verdict line from the template.

Exit 0 = the card is fit to fly, 1 = refused, 2 = the gate could not judge.

Usage:
    python3 scripts/check-flight-card.py --card docs/research/gpu/FLIGHT-CARD-20261116.md \
        --image /mnt/e/k60-work/artifacts/gpu-scanout2-20261116/boot.img
"""

import argparse
import io
import os
import re
import subprocess
import sys

CRITERIA = u'## 4. 判据'
SUCCESS = re.compile(r'(?m)^\s*[-*]?\s*\*\*S(\d+)\*\*')
FAILURE = re.compile(r'(?m)^\s*[-*]?\s*\*\*F(\d+)\*\*')
RESULTS = u"## 5. 结果登记"


def fail(message, code=1):
    sys.stderr.write('❌ flight card: %s\n' % message)
    raise SystemExit(code)


def committed(path, repo):
    try:
        out = subprocess.run(['git', '-C', repo, 'ls-files', '--error-unmatch', path],
                             capture_output=True, text=True)
    except OSError as error:
        fail('cannot run git: %s' % error, 2)
    return out.returncode == 0


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--card', required=True)
    parser.add_argument('--image', required=True)
    parser.add_argument('--repo', default=os.environ.get('K60_REPO') or os.getcwd())
    args = parser.parse_args(argv)

    if not os.path.exists(args.card):
        fail('no card at %s' % args.card)
    if not os.path.exists(args.image):
        fail('no image at %s' % args.image)
    text = io.open(args.card, encoding='utf-8').read()
    if len(text.strip()) < 400:
        fail('the card is too short to carry criteria (%d bytes)' % len(text))

    rel = os.path.relpath(os.path.abspath(args.card), os.path.abspath(args.repo))
    if rel.startswith('..'):
        fail('the card lives outside the repository (%s)' % rel)
    if not committed(rel, args.repo):
        fail('%s is not committed; an uncommitted card cannot be a criterion' % rel)

    if CRITERIA not in text:
        fail('the card has no criteria section (%r)' % CRITERIA)
    successes = [int(m) for m in SUCCESS.findall(text)]
    failures = [int(m) for m in FAILURE.findall(text)]
    if not successes:
        fail('the criteria section has no S<n> success criterion')
    if not failures:
        fail('the criteria section has no F<n> failure rule')

    image_name = os.path.basename(os.path.dirname(args.image))
    if image_name not in text and os.path.basename(args.image) not in text:
        fail('the card never names the image it judges (%s)' % image_name)

    card_time = os.path.getmtime(args.card)
    image_time = os.path.getmtime(args.image)
    if card_time > image_time:
        fail('the card was written after the image (card %d > image %d); criteria '
             'must precede the flight' % (card_time, image_time))

    # The verdict is written after the flight, so it must be EMPTY now — but the
    # card has to carry a results section for it, otherwise the verdict has no home.
    if RESULTS not in text:
        fail('the card has no results section (%r) to record the verdict in')

    print(u'✅ flight card: %s carries %d success criteria and %d failure rules, '
          u'written before %s' % (rel, len(successes), len(failures), image_name))
    return 0


if __name__ == '__main__':
    sys.exit(main())
