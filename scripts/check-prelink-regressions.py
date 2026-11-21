#!/usr/bin/env python3
"""Keep the prelink residue from growing, the way the framework does it.

The upstream 27 profile carries a `regression_policy` and the build refuses a record
that adds a gap (`scripts/unixnu/kernel.py:300`, `check_prelink_regressions`). This is
the same rule for our own tree, so the numbers in the flight ledger cannot quietly get
worse between builds.

Two differences from the framework copy, both deliberate:

* the record is given explicitly, so this runs against an artifact without a build;
* an empty `required_original_branches` list is allowed only with a dated waiver
  (`required_original_branches_waiver` with `reason` and `review_after`). Our kit does
  not emit `native_original_branches` yet, and a clause that can never fail is not a
  clause (P-290), so the waiver expires and turns the gate red on its review date.

Exit codes: 0 no gap grew, 1 a gap grew or a required branch is missing, 2 the record
is absent (a generic kernel has no prelink record: cannot judge is not a pass, P-279).
"""

import argparse
import datetime
import json
import sys
from pathlib import Path

MASK = (1 << 64) - 1
HERO = 0


def load_record(path):
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as error:
        print(f'FAIL: {path} is not JSON: {error}')
        return None


def original_address(target, slide):
    """Record addresses are collection-relative; the policy is keyed by native address."""
    return hex((int(target, 16) - slide) & MASK)


def grown(record, policy):
    slide = int(record.get('collection_slide', '0x0'), 16)
    problems = []
    for kind in ('missing', 'stubbed'):
        allowed_by_owner = policy.get(kind, {})
        for owner, targets in (record.get(kind) or {}).items():
            for target, count in targets.items():
                allowed = allowed_by_owner.get(owner, {}).get(original_address(target, slide), 0)
                if count > allowed:
                    problems.append(f'{kind} grew: {owner} original {original_address(target, slide)} '
                                    f'has {count} site(s), the policy allows {allowed}')
    for owner in allowed_by_owner_points(policy, record, slide):
        problems.append(owner)
    return problems


def allowed_by_owner_points(policy, record, slide):
    """A policy entry that no longer matches anything is a stale bound, not a pass."""
    problems = []
    for kind in ('missing', 'stubbed'):
        for owner, targets in (policy.get(kind) or {}).items():
            present = {original_address(target, slide)
                       for target in (record.get(kind) or {}).get(owner, {})}
            for target in targets:
                if target not in present:
                    problems.append(f'{kind}: the policy still allows {owner} original {target}, '
                                    f'which no longer appears; tighten the policy (P-259)')
    return problems


def branch_problems(record, policy, today):
    required = list(policy.get('required_original_branches') or [])
    present = {entry['symbol'] for entry in record.get('native_original_branches') or []}
    if required:
        missing = [name for name in required if name not in present]
        if missing:
            return [f'the record lacks required original branch(es): {", ".join(missing)}']
        return []
    waiver = policy.get('required_original_branches_waiver') or {}
    review = waiver.get('review_after')
    if not review:
        return ['no required_original_branches and no dated waiver: the clause cannot fail (P-290)']
    if today > datetime.date.fromisoformat(review):
        return [f'the required_original_branches waiver expired on {review}: '
                f'{waiver.get("reason", "no reason recorded")}']
    return []


def write_policy(record, path, force):
    if path.exists() and not force:
        return f'{path} exists; pass --write --force to replace it'
    slide = int(record.get('collection_slide', '0x0'), 16)
    document = {
        'record_sha256': record.get('candidate_sha256'),
        'collection_slide': record.get('collection_slide', '0x0'),
        'description': 'Baseline of the K60 27 stage-0 prelink residue: these are the gaps '
                       'that exist today, and the gate only stops them from growing.',
        'missing': {owner: {original_address(target, slide): count
                            for target, count in targets.items()}
                    for owner, targets in (record.get('missing') or {}).items()},
        'stubbed': {owner: {original_address(target, slide): count
                            for target, count in targets.items()}
                    for owner, targets in (record.get('stubbed') or {}).items()},
        'required_original_branches': [],
        'required_original_branches_waiver': {
            'reason': 'kits/XnuPrelink does not emit native_original_branches yet, so the '
                      'record has none to require; the waiver exists so the empty clause is '
                      'visible and expires instead of passing forever',
            'review_after': '2026-11-28',
        },
    }
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + '\n')
    return None


def main(argv=None):
    here = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--record', type=Path,
                        default=Path('/opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/'
                                     'mondrian_ios27/kernel/kernel.json'))
    parser.add_argument('--policy', type=Path,
                        default=here / 'docs/engineering/IOS27-PRELINK-POLICY.json')
    parser.add_argument('--write', action='store_true', help='record this build as the baseline')
    parser.add_argument('--force', action='store_true', help='replace an existing policy')
    parser.add_argument('--today', help='override the date the waiver is judged against')
    arguments = parser.parse_args(argv)

    record = load_record(arguments.record)
    if record is None:
        print(f'note: no prelink record at {arguments.record}; a generic kernel build has none, '
              f'so this gate could not judge (P-279)')
        return 2
    if arguments.write:
        problem = write_policy(record, arguments.policy, arguments.force)
        if problem:
            print(f'FAIL: {problem}')
            return 1
        print(f'OK prelink policy: recorded the residue of {record.get("candidate_sha256")} '
              f'as the baseline in {arguments.policy}')
        return 0
    if not arguments.policy.is_file():
        print(f'FAIL: no policy at {arguments.policy}; run me with --write after a build (P-279)')
        return 1
    policy = json.loads(arguments.policy.read_text())
    today = (datetime.date.fromisoformat(arguments.today) if arguments.today
             else datetime.date.today())

    problems = grown(record, policy) + branch_problems(record, policy, today)
    for problem in problems:
        print(f'FAIL: {problem}')
    if problems:
        return 1
    gaps = sum(sum(targets.values()) for targets in (record.get('missing') or {}).values())
    gaps += sum(sum(targets.values()) for targets in (record.get('stubbed') or {}).values())
    print(f'OK prelink policy: {gaps} gap(s) recorded, none larger than the baseline')
    return 0


if __name__ == '__main__':
    sys.exit(main())
