#!/usr/bin/env python3
"""Tests for scripts/check-io-map-budget.py (P-219).

The gate reads an *applied* xnu-work tree, so every fixture is a miniature tree
with `osfmk/arm/io_map.c` and a few `bsd/dev/*.c` files.  The interesting cases
are the ones that made the first version lie: the submap size is written as a
shift expression, and a declaration of `ml_io_map` is not a call site.
"""

import importlib.util
import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
GATE = os.path.join(os.path.dirname(HERE), "check-io-map-budget.py")


def load_gate():
    spec = importlib.util.spec_from_file_location("k60_io_map_budget", GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        handle.write(text)


class Tree(object):
    def __init__(self, submap="(8ul << 20)"):
        self.root = tempfile.mkdtemp(prefix="k60-iomap-")
        write(os.path.join(self.root, "osfmk/arm/io_map.c"),
              "extern vm_offset_t virtual_space_start;\n"
              "#define IO_MAP_SIZE            %s\n" % submap)

    def driver(self, name, text):
        write(os.path.join(self.root, "bsd/dev", name), text)

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.gate = load_gate()
        self.trees = []

    def tearDown(self):
        for tree in self.trees:
            tree.cleanup()

    def tree(self, submap="(8ul << 20)"):
        made = Tree(submap)
        self.trees.append(made)
        return made

    def test_a_shift_expression_is_the_submap_size(self):
        # First version read `int("8ul", 0)` and reported an 8-byte submap, so a
        # healthy tree failed and a full one passed for the wrong reason.
        made = self.tree("(8ul << 20)")
        size, source = self.gate.io_map_size(made.root)
        self.assertEqual(size, 8 << 20)
        self.assertEqual(source, "osfmk/arm/io_map.c")

    def test_a_plain_hex_submap_size_is_read(self):
        made = self.tree("(0x2000000)")
        size, _ = self.gate.io_map_size(made.root)
        self.assertEqual(size, 32 << 20)

    def test_a_declaration_is_not_a_call_site(self):
        made = self.tree()
        made.driver("drv.c",
                    "extern vm_offset_t ml_io_map(vm_offset_t, vm_size_t);\n"
                    "void f(void) { ml_io_map(0x1000, 0x1000); }\n")
        rows = list(self.gate.call_sites(made.root))
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual(rows[0][3], 0x1000)

    def test_a_named_define_is_resolved(self):
        made = self.tree()
        made.driver("drv.c",
                    "#define WINDOW_SIZE 0x40000u\n"
                    "void f(void) { ml_io_map(0x1000, WINDOW_SIZE); }\n")
        rows = list(self.gate.call_sites(made.root))
        self.assertEqual(rows[0][3], 0x40000)

    def test_a_total_that_overflows_the_submap_fails(self):
        made = self.tree("(1ul << 20)")
        made.driver("drv.c",
                    "#define BIG 0x200000u\n"
                    "void f(void) { ml_io_map(0x1000, BIG); }\n")
        problems, notes = self.gate.measure(made.root)
        self.assertEqual(len(problems), 1)
        self.assertIn("KERN_NO_SPACE", problems[0])
        self.assertIn("P-219", problems[0])

    def test_a_total_that_fits_passes(self):
        made = self.tree("(8ul << 20)")
        made.driver("drv.c",
                    "#define SMALL 0x100000u\n"
                    "void f(void) { ml_io_map(0x1000, SMALL); }\n")
        problems, _ = self.gate.measure(made.root)
        self.assertEqual(problems, [])

    def test_a_nearly_full_submap_warns_without_failing(self):
        made = self.tree("(1ul << 20)")
        made.driver("drv.c",
                    "#define MOST 0xd0000u\n"
                    "void f(void) { ml_io_map(0x1000, MOST); }\n")
        problems, notes = self.gate.measure(made.root)
        self.assertEqual(problems, [])
        self.assertTrue(any(">75%" in n for n in notes), notes)

    def test_comments_do_not_count_as_call_sites(self):
        made = self.tree()
        made.driver("drv.c",
                    "/* ml_io_map(0x1000, 0x400000); */\n"
                    "// ml_io_map(0x2000, 0x400000);\n"
                    "void f(void) { ml_io_map(0x3000, 0x1000); }\n")
        rows = list(self.gate.call_sites(made.root))
        self.assertEqual(len(rows), 1, rows)

    def test_a_missing_tree_skips_instead_of_guessing(self):
        buffer = io.StringIO()
        argv = sys.argv
        sys.argv = [GATE]
        os.environ.pop("K60_XNU_TREE", None)
        try:
            with redirect_stdout(buffer):
                code = self.gate.main()
        finally:
            sys.argv = argv
        self.assertEqual(code, 0)
        self.assertIn("skip:", buffer.getvalue())

    def test_a_directory_that_is_not_a_tree_skips(self):
        made = self.tree()
        shutil.rmtree(os.path.join(made.root, "osfmk"))
        buffer = io.StringIO()
        argv = sys.argv
        sys.argv = [GATE, "--tree", made.root]
        try:
            with redirect_stdout(buffer):
                code = self.gate.main()
        finally:
            sys.argv = argv
        self.assertEqual(code, 0)
        self.assertIn("skip:", buffer.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=1)
