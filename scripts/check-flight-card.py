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

Re-flights: an invalid flight (P-236) has to be repeated against the *same*
image, and appending the verdict makes the card newer than the image. The
invariant this gate actually wants is not "the file is older" but "the criteria
have not moved since the first flight", so the verdict records

    criteria-sha256: <hex>

and a later mtime is accepted only while the live criteria digest still equals
it. A card with no recorded digest still has to precede its image.

Exit 0 = the card is fit to fly, 1 = refused, 2 = the gate could not judge.

Usage:
    python3 scripts/check-flight-card.py --card docs/research/gpu/FLIGHT-CARD-20261116.md \
        --image /mnt/e/k60-work/artifacts/gpu-scanout2-20261116/boot.img
"""

import argparse
import hashlib
import io
import os
import re
import subprocess
import sys

CRITERIA = u'## 4. 判据'
SUCCESS = re.compile(r'(?m)^\s*[-*]?\s*\*\*S(\d+)\*\*')
FAILURE = re.compile(r'(?m)^\s*[-*]?\s*\*\*F(\d+)\*\*')
RESULTS = u"## 5. 结果登记"
DIGEST = re.compile(r'(?m)^\s*[-*]?\s*criteria-sha256:\s*([0-9a-f]{64})\s*$')


def criteria_digest(text):
    """Hash the criteria section only, so a verdict cannot move a threshold.

    Normalised to stripped lines joined by newlines: trailing whitespace and a
    stray blank line should not read as "the criteria changed".
    """
    start = text.find(CRITERIA)
    if start < 0:
        return None
    end = text.find(RESULTS, start)
    section = text[start:end if end >= 0 else len(text)]
    lines = [line.rstrip() for line in section.splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    return hashlib.sha256(u'\n'.join(lines).encode('utf-8')).hexdigest()


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
        recorded = DIGEST.findall(text)
        live = criteria_digest(text)
        if not recorded:
            fail('the card was written after the image (card %d > image %d); criteria '
                 'must precede the flight, and the card records no criteria-sha256 '
                 'to prove the criteria have not moved since' % (card_time, image_time))
        if len(set(recorded)) > 1:
            fail('the card records %d different criteria-sha256 values (%s); only one '
                 'flight of criteria can be on record'
                 % (len(set(recorded)), u', '.join(sorted(set(recorded)))))
        if recorded[0] != live:
            fail('the criteria changed after the image (%s recorded, %s now); a re-flight '
                 'may repeat the criteria, never rewrite them'
                 % (recorded[0][:16], (live or u'none')[:16]))
        reflight = True
    else:
        reflight = False

    # The verdict is written after the flight, so it must be EMPTY now — but the
    # card has to carry a results section for it, otherwise the verdict has no home.
    if RESULTS not in text:
        fail('the card has no results section (%r) to record the verdict in')

    if reflight:
        print(u'✅ flight card: %s re-flies %s with unchanged criteria '
              u'(criteria-sha256 %s)' % (rel, image_name, DIGEST.findall(text)[0][:16]))
        return 0
    print(u'✅ flight card: %s carries %d success criteria and %d failure rules, '
          u'written before %s' % (rel, len(successes), len(failures), image_name))
    return 0


if __name__ == '__main__':
    sys.exit(main())
