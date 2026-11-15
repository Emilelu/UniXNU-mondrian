#!/usr/bin/env python3
"""Check 0619 against the exact supported predecessor sections, without a build.

--xnu is an existing pre-0619 patched tree for handoff.c/h and IOKitBSDInit.
The late hook fixture is the exact 0614 postimage, since old global build trees
may contain obsolete late hooks. This is not a full kernel-series replay.
"""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[2]
TARGETS = ('bsd/dev/pong_handoff.c', 'bsd/dev/pong_handoff.h',
           'bsd/dev/pong_adsp_startup.c', 'iokit/bsddev/IOKitBSDInit.cpp',
           'bsd/kern/kern_exec.c')


def sections(text):
    lines = text.splitlines(keepends=True)
    anchors = [i for i in range(len(lines)-1)
               if lines[i].startswith('--- ') and lines[i+1].startswith('+++ ')]
    for i, start in enumerate(anchors):
        end = anchors[i+1] if i+1 < len(anchors) else len(lines)
        path = lines[start+1][4:].strip().split('\t')[0]
        if path.startswith('b/'):
            path = path[2:]
        if path not in TARGETS:
            continue
        body = lines[start:end]
        stop = next((j for j in range(2, len(body))
                     if body[j].startswith('diff --git ')), len(body))
        yield path, ''.join(body[:stop])


def check_default_off_callsite(early, root):
    """Execute the patched IOKitBSDInit body; the access stubs never use MMIO."""
    start = early.index('kern_return_t\nIOKitBSDInit(')
    end = early.index('\n}\n', start) + 3
    body = early[start:end]
    compiler = shutil.which('c++') or shutil.which('clang++')
    if not compiler:
        raise SystemExit('a host C++ compiler is required for call-site assertions')
    fixture = r'''
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#define IOPOLLED_COREFILE 0
using kern_return_t = int;
constexpr int kIOReturnSuccess = 0;
static bool present;
static unsigned parsed, parse_calls, publish_calls, smem_accesses;
static unsigned tcsr_accesses, pas_calls, startup_claims, battery_calls;
static unsigned event_count, events[4];
static int publisher_result;
static void reset(bool found, unsigned value, int result = 0) {
    present = found; parsed = value; publisher_result = result;
    parse_calls = publish_calls = smem_accesses = tcsr_accesses = pas_calls = 0;
    startup_claims = battery_calls = event_count = 0;
}
extern "C" bool PE_parse_boot_argn(const char *name, void *value, int bytes) {
    assert(std::strcmp(name, "pong_handoff_publish") == 0);
    assert(bytes == int(sizeof(unsigned)));
    assert(*static_cast<unsigned *>(value) == 0u);
    ++parse_calls;
    /* Also exercise a parser that writes a value but returns false. */
    *static_cast<unsigned *>(value) = parsed;
    return present;
}
extern "C" int k60_adsp_handoff_publish(void) {
    ++publish_calls;
    /* Non-vacuous access boundary: an enabled dispatch reaches every spy.
     * These represent the publisher's downstream effects, not real hardware. */
    ++startup_claims; ++pas_calls; ++tcsr_accesses; ++smem_accesses;
    events[event_count++] = 1;
    return publisher_result;
}
struct IOService {
    static void publishResource(const char *name) {
        assert(std::strcmp(name, "IOBSD") == 0);
        events[event_count++] = 2;
    }
};
extern "C" void k60_physical_battery_start(void) {
    ++battery_calls; events[event_count++] = 3;
}
'''
    cases = r'''
static void check(bool found, unsigned value, bool enabled, int result = 0) {
    reset(found, value, result);
    assert(IOKitBSDInit() == kIOReturnSuccess);
#if XNU_K60_PHYSICAL_BATTERY
    assert(parse_calls == 1u && battery_calls == 1u);
    assert(publish_calls == unsigned(enabled));
    assert(smem_accesses == unsigned(enabled));
    assert(tcsr_accesses == unsigned(enabled));
    assert(pas_calls == unsigned(enabled));
    assert(startup_claims == unsigned(enabled));
    assert(event_count == (enabled ? 3u : 2u));
    unsigned next = 0;
    if (enabled) assert(events[next++] == 1u);
    assert(events[next++] == 2u && events[next++] == 3u);
#else
    (void)enabled;
    assert(!parse_calls && !publish_calls && !smem_accesses && !tcsr_accesses);
    assert(!pas_calls && !startup_claims && !battery_calls);
    assert(event_count == 1u && events[0] == 2u);
#endif
}
int main() {
    check(false, 0u, false);
    check(false, 1u, false);
    check(true, 0u, false);
    check(true, 2u, false);
    check(true, UINT32_MAX, false);
    check(true, 1u, true);
    check(true, 1u, true, -1000);
    std::puts("PASS: 7 call-site cases; disabled path has zero SMEM/TCSR/PAS/claim access");
}
'''
    for physical_battery in (0, 1):
        source = root / ('callsite-' + str(physical_battery) + '.cpp')
        binary = source.with_suffix('')
        source.write_text(fixture + '\n' + body + '\n' + cases)
        subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                        '-DXNU_K60_PHYSICAL_BATTERY=' + str(physical_battery),
                        str(source), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
    print('TESTS OK: exact patched call site, 14 host cases across battery on/off')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--xnu', required=True, type=Path)
    args = parser.parse_args()
    if not shutil.which('patch'):
        raise SystemExit('GNU patch is required')
    with tempfile.TemporaryDirectory(prefix='k60-handoff-patches-') as tmp:
        root = Path(tmp)
        for name in TARGETS[:2] + TARGETS[3:4]:
            source = args.xnu / name
            if not source.is_file():
                raise SystemExit('predecessor source missing: ' + str(source))
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        late = root / TARGETS[4]
        late.parent.mkdir(parents=True, exist_ok=True)
        predecessor = (REPO / 'patches/xnu/0614-k60-adsp-call-site.patch').read_text().splitlines(keepends=True)
        late.write_text(''.join(line[1:] for line in predecessor[3:]
                               if line.startswith((' ', '+'))))
        patch = REPO / 'patches/xnu/0619-k60-adsp-glink-handoff.patch'
        touched = []
        for target, text in sections(patch.read_text()):
            (root / target).parent.mkdir(parents=True, exist_ok=True)
            result = subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-d', str(root)],
                                    input=text, capture_output=True, text=True)
            if result.returncode:
                raise SystemExit(target + '\n' + result.stdout + result.stderr)
            touched.append(target)
        assert set(touched) == set(TARGETS)
        expected = {
            TARGETS[0]: ('K60HandoffBuild.c', {'"K60HandoffBuild.h"': '"pong_handoff.h"'}),
            TARGETS[1]: ('K60HandoffBuild.h', {'"K60Smem.h"': '"pong_smem.h"'}),
            TARGETS[2]: ('K60AdspStartup.c', {}),
        }
        for path, (canonical, replacements) in expected.items():
            want = (REPO / 'drivers/PongPower' / canonical).read_text()
            for before, after in replacements.items():
                want = want.replace(before, after)
            assert (root / path).read_text() == want, path + ': canonical source differs'
        early = (root / TARGETS[3]).read_text()
        assert early.index('(void)k60_adsp_handoff_publish();') < early.index('IOService::publishResource("IOBSD")')
        assert early.index('IOService::publishResource("IOBSD")') < early.index('\n\tk60_physical_battery_start();')
        assert '#include <pexpert/pexpert.h>' in early
        check_default_off_callsite(early, root)
        assert 'if (k60_adsp_startup_claim(2u))' in late.read_text()
        assert late.read_text().count('(void)k60_adsp_probe_from_handoff();') == 1
        print('TESTS OK: 5 integration sections, 3 canonical mirrors, early order and late exclusion')
        print('Scope: predecessor fixture only; full clean-tree kernel build remains required')


if __name__ == '__main__':
    main()
