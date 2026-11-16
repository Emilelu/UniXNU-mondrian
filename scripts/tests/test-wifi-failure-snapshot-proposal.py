#!/usr/bin/env python3
"""Static review of an UNAPPLIED snapshot proposal; never builds or writes sources."""
import argparse
import ast
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / 'scripts/proposals/wifi-failure-snapshot.diff'
PARSER = re.compile(r'^@@ -(\d+),(\d+) \+(\d+),(\d+) @@')


def in_memory_apply(text, patch):
    result = {}
    path = None
    hunks = []
    for line in patch.splitlines():
        if line.startswith('diff --git '):
            path = line.split(' b/', 1)[1]
            if path in result:
                raise AssertionError('duplicate section: ' + path)
            result[path] = []
        elif line.startswith('@@ '):
            match = PARSER.match(line)
            if not match:
                raise AssertionError('bad hunk: ' + line)
            hunks = [tuple(map(int, match.groups())), []]
            result[path].append(hunks)
        elif line.startswith(('--- ', '+++ ')):
            continue
        elif line[:1] in (' ', '+', '-'):
            hunks[1].append(line)
        elif line:
            raise AssertionError('bad patch line: ' + line)
    output = {}
    for path, hs in result.items():
        source = text[path].splitlines()
        delta = 0
        for (old, oldn, new, newn), body in hs:
            before = [x[1:] for x in body if x[0] in ' -']
            after = [x[1:] for x in body if x[0] in ' +']
            assert len(before) == oldn and len(after) == newn, path
            assert new == old + delta, path
            at = old - 1 + delta
            assert source[at:at + oldn] == before, (path, old)
            source[at:at + oldn] = after
            delta += newn - oldn
        output[path] = '\n'.join(source) + '\n'
    return output


def ring_ok(ptr, base, size, element):
    return bool(element and size and size % element == 0 and ptr >= base
                and ptr - base < size and (ptr - base) % element == 0)


def range_ok(cpu, bus, size, low=0, high=0xffffffff, base=0x100000,
             begin=0xa0001000, arena=0x4000000):
    cpu_ok = bool(cpu and size and cpu >= base and cpu-base < arena
                  and size <= arena-(cpu-base))
    mapped = bool(size and bus >= begin and bus-begin < arena
                  and size <= arena-(bus-begin))
    envelope = bool(size and low <= bus <= high and size-1 <= high-bus)
    return cpu_ok and mapped and envelope and bus-begin == cpu-base


class ProposalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        patch = PATCH.read_text()
        cls.paths = ('drivers/ArmCpu/ArmCpu.cpp',
                     'drivers/PongWifi/PongWifiPlatform.cpp',
                     'scripts/build-k60-ath11k.py')
        cls.before = {p: (ROOT / p).read_text() for p in cls.paths}
        cls.after = in_memory_apply(cls.before, patch)
        tree = ast.parse(cls.after[cls.paths[2]])
        functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                     and n.name in ('add_failure_snapshot', 'add_failure_pump_counters',
                                    'adapt_dispatcher_timers')]
        assert len(functions) == 3
        scope = {}
        exec(compile(ast.Module(body=functions, type_ignores=[]), '<proposal-only>', 'exec'), scope)
        cls.snapshot = staticmethod(scope['add_failure_snapshot'])
        cls.pump = staticmethod(scope['add_failure_pump_counters'])
        cls.adapt = staticmethod(scope['adapt_dispatcher_timers'])
        cls.tree = tree
        cls.helper = next(n.value.value for f in functions if f.name == 'add_failure_snapshot'
                          for n in f.body if isinstance(n, ast.Assign)
                          and isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'helper')

    def test_only_repository_paths_and_valid_generator(self):
        self.assertEqual(set(self.paths), set(self.after))
        self.assertNotIn('generated-ath11k/', PATCH.read_text())
        self.assertIn("if name == 'pm.c':\n            text = add_failure_snapshot(text)", self.after[self.paths[2]])
        self.assertIn("write_text(add_failure_pump_counters(", self.after[self.paths[2]])

    def test_dispatcher_unchanged_and_existing_counter(self):
        def body(s):
            return s.split('void ArmCpu::interrupt(void)', 1)[1].split('extern "C" IOReturn armcpu_spi_attach', 1)[0]
        self.assertEqual(body(self.before[self.paths[0]]), body(self.after[self.paths[0]]))
        self.assertEqual(body(self.before[self.paths[0]]).count('__atomic_fetch_add(&owner->count,1,__ATOMIC_RELAXED);'), 1)
        self.assertIn('__atomic_load_n(&owner->count,__ATOMIC_RELAXED)', self.after[self.paths[0]])

    def test_no_isr_logging_or_new_mmio_writes(self):
        p = self.after[self.paths[1]]
        isr = p.split('void irq(void *) {', 1)[1].split('void failureSnapshot', 1)[0]
        for token in ('IOLog(', 'log(', 'failureSnapshot(', 'IOMalloc'):
            self.assertNotIn(token, isr)
        snap = p.split('void failureSnapshot', 1)[1].split('void worker', 1)[0]
        for token in ('.w(', 'write32(', 'lx_pump(', 'parf.r(0x228)'):
            self.assertNotIn(token, snap)
        self.assertNotIn('write32(', self.after[self.paths[0]].split('armcpu_spi_snapshot', 1)[1].split('void ArmCpu::signalCPU', 1)[0])
        for token in ('mhi_write', 'mhi_set_', 'lx_pump(', 'writel('):
            self.assertNotIn(token, self.helper)

    def test_timeout_order_and_strict_anchors(self):
        source = ('int mhi_sync_power_up(struct mhi_controller *mhi_cntrl)\n{\n'
                  '\tif (ret)\n\t\tmhi_power_down(mhi_cntrl, false);\n\n'
                  '\treturn ret;\n}\nEXPORT_SYMBOL(mhi_sync_power_up);')
        changed = self.snapshot(source)
        self.assertIn('pong_timeout_snapshot(mhi_cntrl);\n\t\tmhi_power_down', changed)
        for bad in ('', source+source, changed):
            with self.assertRaises(RuntimeError):
                self.snapshot(bad)

    def test_ring_mapping_checks_and_nonatomic_label(self):
        for token in ('CH contexts', 'ER contexts', 'CMD contexts', 'ER allocation',
                      'ER active ring', 'host_rp_ok', 'shared_wp_ok', 'ctxt_wp_match',
                      'non-atomic CPU-visible', 'MHICTRLLIMIT_HIGHER', 'MHIDATALIMIT_HIGHER'):
            self.assertIn(token, self.helper)
        self.assertLess(self.helper.index('if(!nw_wifi_failure_range("ER contexts"'), self.helper.index('struct mhi_event_ctxt *e='))

    def test_range_boundaries(self):
        begin, base, size = 0xa0001000, 0x100000, 0x4000000
        self.assertTrue(range_ok(base, begin, size))
        self.assertTrue(range_ok(base+size-1, begin+size-1, 1))
        for cpu, bus, length in ((base, begin, 0), (0, begin, 1),
                                 (base+size, begin+size, 1), (base, begin-1, 1),
                                 (base, begin, size+1), (base+1, begin, 1),
                                 (base, (1 << 64)-1, 2)):
            self.assertFalse(range_ok(cpu, bus, length))
        self.assertTrue(range_ok(base, begin, 1, high=begin))
        self.assertFalse(range_ok(base, begin, 2, high=begin))
        self.assertFalse(range_ok(base, begin, 1, low=begin+1))

    def test_ring_boundaries(self):
        self.assertTrue(ring_ok(0x1000, 0x1000, 256, 16))
        self.assertTrue(ring_ok(0x10f0, 0x1000, 256, 16))
        for ptr, size, element in ((0x1100, 256, 16), (0xff0, 256, 16),
                                   (0x1001, 256, 16), (0x1000, 0, 16),
                                   (0x1000, 256, 0), (0x1000, 255, 16)):
            self.assertFalse(ring_ok(ptr, 0x1000, size, element))

    def test_external_generator_anchors_if_requested(self):
        if not SOURCE_ARGS.pm_source or not SOURCE_ARGS.shim_source:
            self.skipTest('external sources not supplied; use --pm-source and --shim-source')
        pm = Path(SOURCE_ARGS.pm_source).read_text()
        shim = Path(SOURCE_ARGS.shim_source).read_text()
        self.assertIn('pong_timeout_snapshot(mhi_cntrl);', self.snapshot(pm))
        adapted = self.adapt(shim)
        instrumented = self.pump(adapted)
        self.assertIn('Pong snapshot software pumps=', instrumented)
        for bad in ('', shim+shim, instrumented):
            with self.assertRaises(RuntimeError):
                self.pump(bad)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--pm-source')
    parser.add_argument('--shim-source')
    SOURCE_ARGS, extra = parser.parse_known_args()
    unittest.main(argv=[__file__, *extra], verbosity=2)
