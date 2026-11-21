#!/usr/bin/env python3
"""Measure the `io_submap` budget (P-219).

`osfmk/arm/io_map.c` hands every `ml_io_map()` caller one shared submap.  When
it runs out, `kmem_alloc(io_submap, ..., KMA_NOFAIL)` panics:

    K60PANICARGS kmem_alloc(<map>, 1048576, 0x100021): failed with 3 @vm_kern.c:178

`0x100021` is `KMA_NOFAIL | KMA_PAGEABLE | KMA_PERMANENT`, which is exactly the
`ml_io_map` path, and the size is whichever window was asked for last.  The
console log stops before the driver prints anything about the region it wanted,
so the failure looks like "the driver never ran" (P-63 recorded the same shape
for touch; P-219 is the Bluetooth ladder hitting it).

This gate sums the sizes of every `ml_io_map()` call site in the applied tree
and compares the total against `IO_MAP_SIZE`.  It needs the applied tree: the
sizes live in `#define`s that only exist after the patch series is applied, and
a stale tree would report the previous build's budget (P-207).  Without a tree
it skips rather than guessing.
"""

import argparse
import glob
import os
import re
import sys

DEFAULT_SUBMAP = 8 << 20

SIZE_DEFINE = re.compile(
    r"#define\s+(\w+)\s+\(?\s*(0x[0-9a-fA-F]+|\d+)[uUlL]*\s*\)?")
# The size is written as a shift expression (`(8ul << 20)`), so capture the whole
# parenthesised expression and evaluate it instead of the leading literal.
IO_MAP_SIZE = re.compile(
    r"#define\s+IO_MAP_SIZE\s+\(?\s*((?:0x[0-9a-fA-F]+|\d+)[uUlL]*"
    r"(?:\s*<<\s*(?:0x[0-9a-fA-F]+|\d+)[uUlL]*)?)\s*\)?")
CALL = re.compile(r"ml_io_map\w*\s*\(([^;]*?)\)\s*;", re.S)
# A declaration, not a call: `extern vm_offset_t ml_io_map(vm_offset_t, vm_size_t)`
DECL_ARG = re.compile(r"^(?:const\s+)?(?:vm_offset_t|vm_size_t|uint64_t|uint32_t|"
                      r"size_t|uintptr_t|addr64_t|void\s*\*)\b")


def _eval_size(expr):
    """Evaluate `8ul << 20` / `0x100000` / `4096` into bytes."""
    expr = expr.replace(" ", "")
    if "<<" in expr:
        left, right = expr.split("<<", 1)
        return (int(left.rstrip("uUlL"), 0) << int(right.rstrip("uUlL"), 0))
    return int(expr.rstrip("uUlL"), 0)


def _strip_comments(text):
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"//[^\n]*", " ", text)


def _read(path):
    with open(path, errors="replace") as handle:
        return handle.read()


def io_map_size(tree):
    """Return (bytes, source) for the submap size in this tree."""
    path = os.path.join(tree, "osfmk/arm/io_map.c")
    if os.path.exists(path):
        text = _read(path)
        m = IO_MAP_SIZE.search(text)
        if m:
            return _eval_size(m.group(1)), "osfmk/arm/io_map.c"
    return DEFAULT_SUBMAP, "default"


def call_sites(tree):
    """Yield (file, line, expression, bytes-or-None) for every ml_io_map call."""
    pattern = os.path.join(tree, "bsd/dev/*.c")
    for path in sorted(glob.glob(pattern)):
        raw = _read(path)
        text = _strip_comments(raw)
        defines = {}
        for m in SIZE_DEFINE.finditer(text):
            try:
                defines[m.group(1)] = int(m.group(2), 0)
            except ValueError:
                continue
        name = os.path.basename(path)
        for m in CALL.finditer(text):
            parts = [p.strip() for p in m.group(1).split(",")]
            if len(parts) < 2:
                continue
            expr = parts[1]
            # Skip declarations: `extern vm_offset_t ml_io_map(vm_offset_t, vm_size_t)`
            if DECL_ARG.match(expr):
                continue
            value = None
            if re.fullmatch(r"0x[0-9a-fA-F]+[uUlL]*|\d+[uUlL]*", expr):
                value = int(expr.rstrip("uUlL"), 0)
            elif expr in defines:
                value = defines[expr]
            line = text[:m.start()].count("\n") + 1
            yield name, line, expr, value


def measure(tree):
    """Return (problems, notes) for the tree's io_submap budget."""
    problems = []
    notes = []
    limit, source = io_map_size(tree)
    total = 0
    unresolved = 0
    rows = []
    for name, line, expr, value in call_sites(tree):
        if value is None:
            unresolved += 1
            rows.append((name, line, expr, None))
            continue
        total += value
        rows.append((name, line, expr, value))

    notes.append("submap %s = 0x%x (%d bytes) from %s"
                 % (limit, limit, limit, source))
    notes.append("%d call site(s), %d unresolved; resolved total 0x%x (%.2f MiB)"
                 % (len(rows), unresolved, total, total / 1048576.0))

    if total > limit:
        problems.append(
            "the ml_io_map call sites in this tree ask for 0x%x (%.2f MiB) but "
            "IO_MAP_SIZE is only 0x%x (%.2f MiB); the window that does not fit "
            "panics inside kmem_alloc(io_submap, ..., KMA_NOFAIL) with "
            "KERN_NO_SPACE and the console log never names the driver (P-219)"
            % (total, total / 1048576.0, limit, limit / 1048576.0))
    elif total > limit * 3 // 4:
        notes.append("⚠ 0x%x of 0x%x used (>75%%); one more window may not fit"
                     % (total, limit))

    return problems, notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", default=None,
                    help="applied xnu-work tree (…/.cache/xnu-work)")
    args = ap.parse_args()

    tree = args.tree or os.environ.get("K60_XNU_TREE")
    if not tree:
        print("skip: no --tree and no K60_XNU_TREE; the sizes only exist in an "
              "applied tree (P-207: do not judge a stale one)")
        return 0
    if not os.path.isdir(os.path.join(tree, "osfmk/arm")):
        print("skip: %s does not look like an applied xnu-work tree" % tree)
        return 0

    # A tree without the define is not a tree with an 8 MiB submap: 12377 sizes
    # the submap per kmem_alloc instead of one shared constant, so falling back
    # to the 16-series number and printing a tick is a guess dressed as a check
    # (measured 2026-11-21 by the platform lane; P-279, P-290).
    _, source = io_map_size(tree)
    if source == "default":
        print("FAIL: %s/osfmk/arm/io_map.c declares no IO_MAP_SIZE; the 8 MiB fallback "
              "is the 16-series number, so this tree cannot be judged against it. "
              "Count the ml_io_map windows instead of borrowing a limit." % tree)
        return 2

    problems, notes = measure(tree)
    for note in notes:
        print(note)
    if problems:
        for problem in problems:
            print("❌ io_submap budget: " + problem)
        return 1
    print("✅ io_submap budget: every ml_io_map window fits")
    return 0


if __name__ == "__main__":
    sys.exit(main())
