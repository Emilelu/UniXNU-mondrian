#!/usr/bin/env python3
"""Check whether the recorded iOS 27 port expectations still hold.

Each expectation was measured once against a known-good 27 tree and written down
here with the reason. The script re-measures and reports drift, so a moving 27
tree fails loudly instead of being rediscovered patch by patch.
"""
import argparse
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATCHES = os.path.join(REPO, 'patches', 'xnu')

# patch -> (expected rc of git apply --check, reason)
PATCH_EXPECT = [
    ('0620-k60-modem-image.patch', 0, 'adds bsd/dev files only'),
    ('0621-k60-modem-pas.patch', 1, 'its call-site hunk waits for the 27 data mount'),
    ('0622-k60-modem-qrtr.patch', 0, 'adds bsd/dev files only'),
    ('0623-k60-ipa.patch', 0, 'adds bsd/dev files only'),
    ('0621-k60-io-submap-budget.patch', 1, 'not carried; 27 has no io_submap'),
    ('0624-k60-ipa-call-site.patch', 1, 'call sites are regenerated as 0629'),
]

SYMBOLS = ['ml_io_map_unmappable', 'kmem_alloc_contig', 'ptoa_64', 'flush_dcache64',
           'pmap_find_phys', 'PE_parse_boot_argn', 'kernel_map', 'kmem_free']

SEARCH = ['osfmk', 'bsd', 'libkern', 'pexpert', 'iokit']


def run(argv, cwd=None):
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True)


def patch_status(tree, name):
    path = os.path.join(PATCHES, name)
    if not os.path.exists(path):
        return None, 'patch file missing'
    result = run(['git', '-C', tree, 'apply', '--check', path])
    return result.returncode, (result.stderr or result.stdout).strip()


def symbol_present(tree, symbol):
    for sub in SEARCH:
        root = os.path.join(tree, sub)
        if not os.path.isdir(root):
            continue
        result = run(['grep', '-rlw', symbol, root, '--include=*.h', '--include=*.c'])
        if result.stdout.strip():
            return True
    return False


def include_present(tree, header):
    if header in ('stdint.h', 'stddef.h', 'stdbool.h'):
        return True
    for sub in SEARCH:
        root = os.path.join(tree, sub)
        if not os.path.isdir(root):
            continue
        result = run(['find', root, '-path', '*/' + header, '-print', '-quit'])
        if result.stdout.strip():
            return True
    return False


def includes_used():
    names = set()
    root = os.path.join(REPO, 'drivers', 'PongCellular')
    for entry in sorted(os.listdir(root)):
        if not entry.endswith(('.c', '.h')):
            continue
        with open(os.path.join(root, entry), encoding='utf-8', errors='replace') as handle:
            for line in handle:
                if line.startswith('#include <'):
                    names.add(line.split('<', 1)[1].split('>', 1)[0].strip())
    return sorted(names)


def anchor_state(tree):
    path = os.path.join(tree, 'bsd', 'kern', 'kern_exec.c')
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8', errors='replace') as handle:
        body = handle.read()
    return body.count('native_owner_data_stage = 3;')



ARTIFACT_DIR = os.path.join(REPO, 'patches', 'xnu-12377')
ARTIFACTS = ['0626-k60-modem-image.patch', '0627-k60-modem-qrtr.patch',
             '0628-k60-ipa.patch',
             '0629-kern-exec-call-sites.patch',
             '0630-k60-smem.patch', 'series-port.txt', 'conffiles-port.txt']


def patch_artifacts():
    return [n for n in ARTIFACTS if n.endswith(".patch")]


def sourced_from_patches():
    names = set()
    for name in patch_artifacts():
        path = os.path.join(ARTIFACT_DIR, name)
        if not os.path.exists(path):
            continue
        with open(path, encoding='utf-8') as handle:
            for line in handle:
                if line.startswith('+++ b/bsd/dev/') and line.rstrip().endswith('.c'):
                    names.add(line[6:].strip())
    return sorted(names)


def conffile_entries():
    path = os.path.join(ARTIFACT_DIR, 'conffiles-port.txt')
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as handle:
        return [line.split(chr(9))[0] for line in handle if line.strip()]


def conf_entries_in_tree(tree):
    total = 0
    root = os.path.join(tree, 'bsd', 'conf')
    for base, _dirs, files in os.walk(root):
        for name in files:
            try:
                text = open(os.path.join(base, name), encoding='utf-8',
                            errors='replace').read()
            except OSError:
                continue
            total += sum(1 for line in text.splitlines()
                         if 'pong_' in line or 'qcom_glink' in line)
    return total


def smmu_in_tree(tree):
    found = run(['grep', '-rIl', 'ArmSmmu4KBuild', tree])
    return bool(found.stdout.strip())



def smmu_definitions(tree):
    # Files outside our own patches that name the SMMU builder.
    found = run(['grep', '-rIl', 'ArmSmmu4KBuild', tree])
    names = [line for line in found.stdout.splitlines() if line.strip()]
    return [name for name in names if '/bsd/dev/pong_' not in name]


def patch_targets():
    """Every path the three ported patches touch, from their diff headers."""
    names = set()
    for name in patch_artifacts():
        path = os.path.join(ARTIFACT_DIR, name)
        if not os.path.exists(path):
            continue
        with open(path, encoding='utf-8') as handle:
            for line in handle:
                if line.startswith('+++ b/'):
                    names.add(line[6:].strip())
    return sorted(names)


def probe_symbols():
    """Both call sites 0629 inserts need a definition from the earlier patches."""
    wanted = (("0626-k60-modem-image.patch", "k60_modem_probe_from_handoff"),
              ("0628-k60-ipa.patch", "k60_ipa_probe_from_handoff"))
    missing = []
    for name, symbol in wanted:
        path = os.path.join(ARTIFACT_DIR, name)
        text = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
        if symbol not in text:
            missing.append("%s lacks %s" % (name, symbol))
    return missing


def patch_sections():
    """Per patch: the files it touches and how many of its sections are new files."""
    result = []
    for name in patch_artifacts():
        path = os.path.join(ARTIFACT_DIR, name)
        if not os.path.exists(path):
            continue
        targets, fresh = [], 0
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("new file mode"):
                    fresh += 1
                elif line.startswith("+++ b/"):
                    targets.append(line[6:].strip())
        result.append((name, targets, fresh))
    return result


def quoted_includes():
    """Every #include "x" the ported patches add, with the file that adds it."""
    pairs = []
    for name in patch_artifacts():
        path = os.path.join(ARTIFACT_DIR, name)
        if not os.path.exists(path):
            continue
        current = ''
        with open(path, encoding='utf-8', errors='replace') as handle:
            for line in handle:
                if line.startswith('+++ b/'):
                    current = line[6:].strip()
                elif line.startswith('+#include "'):
                    header = line.split('"')[1]
                    pairs.append((current, header))
    return pairs


def installed_headers():
    """Headers the patch set itself installs, by basename."""
    names = set()
    for target in patch_targets():
        if target.endswith('.h'):
            names.add(os.path.basename(target))
    return names


def compare(expected, actual):
    """Drift is any measured rc that differs from the recorded one."""
    return expected == actual


CALL_SITE_PATCH = '0629-kern-exec-call-sites.patch'
CALL_SITE_TARGET = 'bsd/kern/kern_exec.c'

PORT_SERIES = os.path.join(ARTIFACT_DIR, 'series-port.txt')


def read_series(path=None):
    """The bare patch names a 27 series must list, comments dropped."""
    path = path or PORT_SERIES
    names = []
    if not os.path.exists(path):
        return names
    with open(path, encoding='utf-8') as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            names.append(line)
    return names


def integrated_tree(tree):
    """A tree that already carries the ported sources is past the patches."""
    return os.path.exists(os.path.join(tree, 'bsd', 'dev', 'pong_modem_link.c'))


def reverse_status(tree, name):
    path = os.path.join(ARTIFACT_DIR, name)
    if not os.path.exists(path):
        return None, 'patch file missing'
    result = run(['git', '-C', tree, 'apply', '--reverse', '--check', path])
    return result.returncode, (result.stderr or result.stdout).strip()


def conf_text(tree):
    chunks = []
    root = os.path.join(tree, 'bsd', 'conf')
    for base, _dirs, files in os.walk(root):
        for name in files:
            try:
                with open(os.path.join(base, name), encoding='utf-8',
                          errors='replace') as handle:
                    chunks.append(handle.read())
            except OSError:
                continue
    return chr(10).join(chunks)


def call_sites(tree):
    path = os.path.join(tree, 'bsd', 'kern', 'kern_exec.c')
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8', errors='replace') as handle:
        body = handle.read()
    return {name: body.count(name)
            for name in ('k60_modem_probe_from_handoff', 'k60_ipa_probe_from_handoff')}


def check_integrated(tree):
    """The other half: a tree the patches and the build wiring already reached."""
    drift = 0
    series = read_series()
    if not series:
        print('K60 READY INVALID series-port.txt lists no patch')
        return 2
    print('K60 READY note integrated tree: %d patches expected applied' % len(series))
    for name in series:
        rc, note = reverse_status(tree, name)
        if rc is None:
            drift += 1
            print('K60 READY DRIFT %s: %s; generate it with --anchor-auto once the tree '
                  'stages the data mount' % (name, note))
            continue
        if rc == 0:
            print('K60 READY ok   %s is applied' % name)
        else:
            drift += 1
            print('K60 READY DRIFT %s is not applied (reverse check rc=%d)' % (name, rc))
    targets = patch_targets()
    absent = [t for t in targets if not os.path.exists(os.path.join(tree, t))]
    if absent:
        drift += 1
        print('K60 READY DRIFT %d patch target(s) missing from the tree: %s'
              % (len(absent), ' '.join(absent[:4])))
    else:
        print('K60 READY ok   all %d patch targets exist in the tree' % len(targets))
    entries = conffile_entries() or []
    text = conf_text(tree)
    missing = [e for e in entries if e not in text]
    if not entries:
        drift += 1
        print('K60 READY DRIFT conffiles-port.txt is empty')
    elif missing:
        drift += 1
        print('K60 READY DRIFT %d build entr(y/ies) absent from bsd/conf: %s'
              % (len(missing), ' '.join(os.path.basename(m) for m in missing[:4])))
    else:
        print('K60 READY ok   all %d build entries are in bsd/conf' % len(entries))
    counts = call_sites(tree)
    if counts is None:
        print('K60 READY INVALID no bsd/kern/kern_exec.c under the tree')
        return 2
    bad = [name for name, count in counts.items() if count != 1]
    if bad:
        drift += 1
        print('K60 READY DRIFT call sites are not exactly once: '
              + ' '.join('%s=%d' % (name, counts[name]) for name in bad))
    else:
        print('K60 READY ok   both probe call sites appear once in kern_exec.c')
    anchors = anchor_state(tree)
    if anchors != 1:
        drift += 1
        print('K60 READY DRIFT anchor lines=%s, expected exactly one' % anchors)
    else:
        print('K60 READY ok   the data mount anchor line is still there')
    owners = smmu_definitions(tree)
    if owners:
        print('K60 READY note ArmSmmu4K arrived with %s: the weak fallback can go'
              % os.path.basename(owners[0]))
    else:
        print('K60 READY ok   only our own sources name ArmSmmu4KBuild, the weak '
              'fallback is what answers')
    if drift:
        print('K60 READY CHANGED %d expectation(s) drifted' % drift)
        return 1
    print('K60 READY OK the integrated tree carries every ported patch and its wiring')
    return 0


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tree', help='root of the iOS 27 XNU source tree')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.tree or not os.path.isdir(args.tree):
        print('K60 READY INVALID tree not found: %r' % (args.tree,))
        return 2
    if integrated_tree(args.tree):
        return check_integrated(args.tree)
    return check_pristine(args.tree)


def self_test():
    cases = [(0, 0, True), (1, 1, True), (0, 1, False), (1, 0, False)]
    for expected, actual, want in cases:
        if compare(expected, actual) is not want:
            print('K60 READY FAIL compare(%d, %d) != %r' % (expected, actual, want))
            return 1
    NL = chr(10)  # a real newline in the sample series
    import tempfile
    scratch = tempfile.mkdtemp(prefix='k60-series-')
    sample = os.path.join(scratch, 'series.txt')
    with open(sample, 'w', encoding='utf-8') as handle:
        handle.write('# a note' + NL + '0626-a.patch' + NL + '0627-b.patch' + NL)
    if read_series(sample) != ['0626-a.patch', '0627-b.patch']:
        print('K60 READY FAIL read_series dropped a name or kept a comment')
        return 1
    print('K60 READY PASS expectations compared, drift detected, series parsed')
    return 0


CONF_ANCHOR = "bsd/dev/unix_startup.c"


def conf_anchor(tree):
    # Every carried .c is appended to bsd/conf/files right after this line
    # (Lead decision 2026-11-20 07:41). If the line moves the appender has
    # nothing to hang on, so say so here instead of failing at build time.
    for name in ("files", "files.arm64"):
        path = os.path.join(tree, "bsd", "conf", name)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                words = line.split()
                if words and words[0] == CONF_ANCHOR:
                    return name
    return None

def check_pristine(tree):
    drift = 0
    anchors = anchor_state(tree)
    for name, expected, reason in PATCH_EXPECT:
        if anchors and name == '0621-k60-modem-pas.patch':
            print('K60 READY note %s applies once the data mount is in the tree' % name)
            continue
        actual, note = patch_status(tree, name)
        if actual is None:
            print('K60 READY INVALID %s %s' % (name, note))
            return 2
        if compare(expected, actual):
            print('K60 READY ok   %s rc=%d (%s)' % (name, actual, reason))
        else:
            drift += 1
            print('K60 READY DRIFT %s expected rc=%d got rc=%d: %s'
                  % (name, expected, actual, note.splitlines()[0] if note else ''))
    missing = [s for s in SYMBOLS if not symbol_present(tree, s)]
    if missing:
        drift += 1
        print('K60 READY DRIFT kernel symbols missing: ' + ' '.join(missing))
    else:
        print('K60 READY ok   %d kernel symbols present' % len(SYMBOLS))
    headers = includes_used()
    absent = [h for h in headers if not include_present(tree, h)]
    if absent:
        drift += 1
        print('K60 READY DRIFT headers missing: ' + ' '.join(absent))
    else:
        print('K60 READY ok   %d includes resolve' % len(headers))
    missing = [n for n in ARTIFACTS
               if not os.path.exists(os.path.join(ARTIFACT_DIR, n))]
    if missing:
        drift += 1
        print('K60 READY DRIFT port artifacts missing: ' + ' '.join(missing))
    else:
        sources = sourced_from_patches()
        entries = conffile_entries() or []
        if entries != sources:
            drift += 1
            print('K60 READY DRIFT conffiles-port.txt lists %d entries, the patches install %d'
                  % (len(entries), len(sources)))
        else:
            print('K60 READY ok   %d port artifacts, %d build entries'
                  % (len(ARTIFACTS), len(entries)))
    targets = patch_targets()
    stray = [t for t in targets
             if not t.startswith('bsd/dev/') and t != CALL_SITE_TARGET]
    if not targets:
        drift += 1
        print('K60 READY DRIFT the patches list no file at all')
    elif stray:
        drift += 1
        print('K60 READY DRIFT outside bsd/dev and not the call-site file: ' + ' '.join(stray[:5]))
    else:
        print('K60 READY ok   %d patch targets, bsd/dev plus the one call-site file' % len(targets))
    sections = patch_sections()
    seen, twice, partial = {}, [], []
    for name, names, fresh in sections:
        if name == CALL_SITE_PATCH:
            continue
        if fresh != len(names):
            partial.append("%s %d/%d" % (name, fresh, len(names)))
        for target in names:
            seen.setdefault(target, []).append(name)
    twice = sorted(t for t, owners in seen.items() if len(owners) > 1)
    if partial:
        drift += 1
        print('K60 READY DRIFT sections that are not new files: ' + ' '.join(partial))
    elif twice:
        drift += 1
        print('K60 READY DRIFT two patches touch the same file: ' + ' '.join(twice[:3]))
    else:
        print('K60 READY ok   all %d sections create new files, no target twice' % len(seen))
    call_path = os.path.join(ARTIFACT_DIR, CALL_SITE_PATCH)
    calls = [sec for sec in sections if sec[0] == CALL_SITE_PATCH]
    if not os.path.exists(call_path):
        print('K60 READY note %s is not generated yet' % CALL_SITE_PATCH)
    elif len(calls) != 1 or calls[0][1] != [CALL_SITE_TARGET] or calls[0][2] != 0:
        drift += 1
        print('K60 READY DRIFT the call-site patch must modify exactly %s' % CALL_SITE_TARGET)
    else:
        print('K60 READY ok   the call-site patch modifies only %s' % CALL_SITE_TARGET)
    missing_probes = probe_symbols()
    if missing_probes:
        drift += 1
        print('K60 READY DRIFT ' + '; '.join(missing_probes))
    else:
        print('K60 READY ok   both probe symbols are defined by the patches')
    pairs = quoted_includes()
    own = installed_headers()
    unresolved = sorted({(src, hdr) for src, hdr in pairs
                         if hdr not in own and not include_present(tree, hdr)})
    if not pairs:
        drift += 1
        print('K60 READY DRIFT no carried file includes anything')
    elif unresolved:
        drift += 1
        print('K60 READY DRIFT %d quoted include(s) resolve nowhere: %s'
              % (len(unresolved),
                 ' '.join('%s (%s)' % (h, os.path.basename(f)) for f, h in unresolved[:4])))
    else:
        print('K60 READY ok   %d quoted includes resolve inside the patch set or the tree'
              % len({h for _f, h in pairs}))
    rail = [t for t in patch_artifacts() if "pong_pmic_rail" in open(os.path.join(ARTIFACT_DIR, t), encoding="utf-8").read()]
    if rail:
        drift += 1
        print("K60 READY DRIFT a ported patch still needs pong_pmic_rail: " + " ".join(rail))
    else:
        print("K60 READY ok   no ported patch needs the pmic rail driver")
    wired = conf_entries_in_tree(tree)
    if wired:
        drift += 1
        print('K60 READY DRIFT %d pong/glink lines appeared in bsd/conf: the build wiring landed'
              % wired)
    else:
        print('K60 READY ok   bsd/conf still lists no pong/glink source')
    if smmu_in_tree(tree):
        drift += 1
        print('K60 READY DRIFT ArmSmmu4KBuild is in the 27 tree: the weak fallback can be retired')
    else:
        print('K60 READY ok   ArmSmmu4K still absent from the 27 tree')
    anchors = anchor_state(tree)
    if anchors is None:
        print('K60 READY INVALID no bsd/kern/kern_exec.c under the tree')
        return 2
    if anchors == 1 and '0629-kern-exec-call-sites.patch' in ARTIFACTS and os.path.exists(
            os.path.join(ARTIFACT_DIR, '0629-kern-exec-call-sites.patch')):
        print('K60 READY ok   the tree stages the data mount and 0629 is generated')
    else:
        print('K60 READY note anchor lines=%d (expected 0 until the data mount lands)' % anchors)
    anchor_file = conf_anchor(tree)
    if anchor_file:
        print("K60 READY ok   the conffiles appender anchor %s is in %s" % (CONF_ANCHOR, anchor_file))
    else:
        drift += 1
        print("K60 READY DRIFT the conffiles appender anchor %s is missing from bsd/conf" % CONF_ANCHOR)
    if drift:
        print('K60 READY CHANGED %d expectation(s) drifted' % drift)
        return 1
    print('K60 READY OK every recorded expectation still holds')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
