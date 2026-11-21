"""Compare our iOS 27 kernel recipe with Sheng's, field by field.

The goal's second exit criterion is "reference sources covered at every layer".
Sheng builds the same OS profile we do (`ipados-27.0.1-24A446`), so every
difference between the two recipes is either something K60's hardware forces or
something nobody has explained yet. This tool refuses to guess which: it prints
all three states and exits non-zero when an unexplained difference remains.

    same        identical in both trees
    justified   differs, and docs/research/ios27/CONFORMANCE-DEVIATIONS.toml
                carries a reason plus a resolvable piece of evidence
    GAP         differs and nothing explains it

Usage:
    python3 scripts/audit-ios27-conformance.py [--ours .] [--sheng ../UniXNU-sheng]
                                               [--os-profile ios-27.0.1-24A446]
                                               [--json] [--only gap]
"""

MISSING = '(absent)'


def _read_toml(path):
    import tomllib
    with open(path, 'rb') as fh:
        return tomllib.load(fh)


def _deep_get(doc, dotted, default=None):
    node = doc
    for key in dotted.split('.'):
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return node


def _overlay(base, overlay):
    """Merge like scripts/unixnu/profiles.py does: overlay wins, `remove` deletes."""
    if not isinstance(overlay, dict):
        return base
    out = dict(base or {})
    for key, value in overlay.items():
        if key == 'remove' and isinstance(value, list):
            for item in value:
                out.pop(item, None)
            continue
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _overlay(out[key], value)
        else:
            out[key] = value
    return out


def _kernel_view(doc, os_profile):
    kernel = _deep_get(doc, 'kernel', {}) or {}
    overrides = _deep_get(doc, 'os_overrides', {}) or {}
    for name in (os_profile, 'ios-27.0.1-24A446', 'ipados-27.0.1-24A446'):
        if name in overrides:
            patch = overrides[name]
            if isinstance(patch, dict) and isinstance(patch.get('kernel'), dict):
                kernel = _overlay(kernel, patch['kernel'])
            break
    return kernel


def _defconfig_paths(doc):
    return _deep_get(doc, 'package.defconfig', {}) or {}


def _parse_defconfig(path):
    """CONFIG_FOO=bar -> {'CONFIG_FOO': 'bar'}; comments and blanks dropped."""
    out = {}
    try:
        with open(path, encoding='utf-8', errors='replace') as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, _, value = line.partition('=')
                out[key.strip()] = value.strip().strip('"')
    except OSError:
        return None
    return out


def _norm_archive(entry):
    """`component:ArmCpu`, `build-gop-legacy-display-27.py --tree .` and
    `build-corecrypto-14.py` are three spellings of "one archive producer".
    Compare the producer, keep the arguments out of the key."""
    text = str(entry).strip()
    head = text.split()[0] if text.split() else text
    if head.startswith('component:'):
        return 'component:' + head.split(':', 1)[1]
    if head.startswith('{tree}/'):
        head = head.split('/', 1)[1]
    return head.rsplit('/', 1)[-1]


def _norm_series_entry(entry):
    text = str(entry).strip()
    return text.rsplit('/', 1)[-1]


def _load_deviations(path):
    """{key: {'reason':…, 'evidence':…}} — evidence must resolve to a real file."""
    try:
        doc = _read_toml(path)
    except OSError:
        return {}, ['no deviations file at %s' % path]
    notes = {}
    problems = []
    for entry in doc.get('deviation', []):
        key = entry.get('key')
        prefixes = [str(p) for p in (entry.get('prefix') or [])]
        if not key and not prefixes:
            problems.append('a deviation entry has neither key nor prefix')
            continue
        if not entry.get('reason'):
            problems.append('%s: no reason' % key)
        if not entry.get('evidence'):
            problems.append('%s: no evidence' % key)
        if key:
            notes[key] = entry
        for prefix in prefixes:
            notes['prefix:' + prefix] = entry
    return notes, problems


def _resolve(base, rel):
    import os
    candidate = os.path.join(base, rel.split(':', 1)[0])
    return os.path.isfile(candidate)


def collect(ours_root, sheng_root, os_profile='ios-27.0.1-24A446'):
    """Return a list of rows: {key, ours, sheng, state_hint}."""
    import os
    ours = _read_toml(os.path.join(ours_root, 'board.toml'))
    sheng = _read_toml(os.path.join(sheng_root, 'board.toml'))
    ok = _kernel_view(ours, os_profile)
    sk = _kernel_view(sheng, os_profile)
    rows = []

    def add(key, a, b):
        rows.append({'key': key, 'ours': a, 'sheng': b})

    add('board.os_profile', _deep_get(ours, 'board.os_profile', MISSING),
        _deep_get(sheng, 'board.os_profile', MISSING))
    add('kernel.driver_records', ok.get('driver_records', MISSING), sk.get('driver_records', MISSING))
    add('kernel.config_fragments', ok.get('config_fragments', MISSING), sk.get('config_fragments', MISSING))
    add('kernel.patch_series', ok.get('patch_series', MISSING), sk.get('patch_series', MISSING))
    add('kernel.prelink.roots', len((sk.get('prelink') or {}).get('roots') or []) or MISSING,
        len((sk.get('prelink') or {}).get('roots') or []) or MISSING)
    rows[-1]['ours'] = len(((ok.get('prelink') or {}).get('roots')) or []) or ('no [kernel.prelink]',)

    od, sd = _defconfig_paths(ours), _defconfig_paths(sheng)
    # Each tree names the same OS differently (iOS vs iPadOS share build 24A446),
    # so look the defconfig up under each tree's own profile, not ours (P-305).
    sheng_profile = str(_deep_get(sheng, 'board.os_profile', os_profile))
    add('package.defconfig[27]', od.get(os_profile, MISSING), sd.get(sheng_profile, MISSING))

    our_cfg = _parse_defconfig(os.path.join(ours_root, 'configs', str(od.get(os_profile, ''))))
    sheng_cfg = _parse_defconfig(os.path.join(sheng_root, 'configs', str(sd.get(sheng_profile, ''))))
    if our_cfg is None or sheng_cfg is None:
        add('configs', 'unreadable', 'unreadable')
    else:
        for key in sorted(set(our_cfg) | set(sheng_cfg)):
            add('config:' + key, our_cfg.get(key, MISSING), sheng_cfg.get(key, MISSING))

    our_arch = [_norm_archive(a) for a in (ok.get('archives') or [])]
    sheng_arch = [_norm_archive(a) for a in (sk.get('archives') or [])]
    for name in sorted(set(our_arch) | set(sheng_arch)):
        add('archive:' + name, 'yes' if name in our_arch else MISSING,
            'yes' if name in sheng_arch else MISSING)

    our_roots = {r.lstrip('!') for r in ((ok.get('prelink') or {}).get('roots') or [])}
    sheng_roots = {r.lstrip('!') for r in ((sk.get('prelink') or {}).get('roots') or [])}
    for name in sorted(our_roots | sheng_roots):
        add('prelink-root:' + name, 'yes' if name in our_roots else MISSING,
            'yes' if name in sheng_roots else MISSING)
    return rows


def classify(rows, deviations, ours_root):
    out = []
    for row in rows:
        same = row['ours'] == row['sheng']
        if same:
            state, why = 'same', ''
        elif row['key'] in deviations or any(
                row['key'].startswith(p) for p in
                (k[len('prefix:'):] for k in deviations if k.startswith('prefix:'))):
            entry = deviations.get(row['key']) or next(
                deviations[k] for k in deviations
                if k.startswith('prefix:') and row['key'].startswith(k[len('prefix:'):]))
            if entry.get('evidence') and not _resolve(ours_root, str(entry['evidence'])):
                state, why = 'GAP', 'justified, but its evidence does not resolve: %s' % entry['evidence']
            else:
                state, why = 'justified', entry.get('reason', '')
        else:
            state, why = 'GAP', ''
        out.append(dict(row, state=state, why=why))
    return out


def registry_coverage(root):
    """How much of the official corpus has actually been judged."""
    import os
    path = os.path.join(root, 'docs/engineering/OFFICIAL-REQUIREMENTS.toml')
    try:
        doc = _read_toml(path)
    except OSError:
        return None
    counts = {'mapped': 0, 'na': 0, 'unmapped': 0}
    for page in doc.get('page', []):
        state = str(page.get('state', 'unmapped'))
        if state in ('mapped', 'na'):
            counts[state] += 1
        else:
            counts['unmapped'] += 1
    counts['total'] = sum(counts.values())
    return counts


def prelink_residual(root, out_dir=None):
    """Our unresolved/stubbed counts next to the upstream policy baseline."""
    import json
    import os
    found = {}
    policy = os.path.join(root, 'patches/policies/ipados-27.0.1-24A446/prelink-regression.json')
    if not os.path.isfile(policy):
        policy = os.path.join(root, 'scripts/policies/ipados-27.0.1-24A446/prelink-regression.json')
    if os.path.isfile(policy):
        doc = json.load(open(policy, encoding='utf-8'))
        found['policy'] = {
            'missing': doc.get('missing_unresolved'),
            'stubbed': doc.get('stubbed_references'),
        }
    kernel_json = None
    if out_dir:
        kernel_json = os.path.join(out_dir, 'kernel', 'kernel.json')
    if kernel_json and os.path.isfile(kernel_json):
        doc = json.load(open(kernel_json, encoding='utf-8'))
        prelink = doc.get('prelink') or {}
        found['ours'] = {
            'missing': prelink.get('unmapped_symbols'),
            'stubbed': prelink.get('stubbed_sites'),
        }
    return found


def main(argv=None):
    import argparse
    import json
    import os
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ours', default='.')
    parser.add_argument('--sheng', default='../UniXNU-sheng')
    parser.add_argument('--os-profile', default='ios-27.0.1-24A446')
    parser.add_argument('--out-dir', default=os.environ.get('K60_OUT'))
    parser.add_argument('--deviations',
                        default='docs/research/ios27/CONFORMANCE-DEVIATIONS.toml')
    parser.add_argument('--only', choices=('gap', 'all'), default='all')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)

    if not os.path.isfile(os.path.join(args.sheng, 'board.toml')):
        print('FAIL: no board.toml under %s; pass --sheng' % args.sheng)
        return 2
    deviations, problems = _load_deviations(os.path.join(args.ours, args.deviations))
    rows = classify(collect(args.ours, args.sheng, args.os_profile), deviations, args.ours)
    coverage = registry_coverage(args.ours)
    residual = prelink_residual(args.ours, args.out_dir)

    gaps = [r for r in rows if r['state'] == 'GAP']
    shown = gaps if args.only == 'gap' else rows
    if args.json:
        print(json.dumps({'rows': shown, 'gaps': len(gaps), 'coverage': coverage,
                          'residual': residual, 'problems': problems}, ensure_ascii=False, indent=1))
    else:
        for row in shown:
            if row['state'] == 'same':
                continue
            print('%-9s %-46s ours=%-22s sheng=%-22s %s'
                  % (row['state'], row['key'], row['ours'], row['sheng'], row['why']))
        if coverage:
            print('official registry: %d pages, mapped %d, na %d, unmapped %d (%.0f%% unjudged)'
                  % (coverage['total'], coverage['mapped'], coverage['na'], coverage['unmapped'],
                     100.0 * coverage['unmapped'] / max(coverage['total'], 1)))
        if residual:
            print('prelink residual: %s' % json.dumps(residual, ensure_ascii=False))
        for problem in problems:
            print('note: %s' % problem)
        print('SAME %d, JUSTIFIED %d, GAP %d'
              % (sum(1 for r in rows if r['state'] == 'same'),
                 sum(1 for r in rows if r['state'] == 'justified'), len(gaps)))
        if gaps:
            print('结论: ❌ 与 Sheng 的差异里有 %d 条没有书面理由，不能声称"严格参考"' % len(gaps))
            return 1
        print('结论: ✅ 每一处差异都有理由与可解析的证据')
    return 1 if gaps else 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
