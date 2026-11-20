#!/usr/bin/env python3
"""Resolve every extern the ported sources declare to something that defines it.

A series can apply, the build table can be complete, and the link can still fail
on one symbol that lives in a component the kernel does not carry. This reads the
sources the patches install, takes each extern declaration, and names where the
definition is expected to come from: the patch set, the target tree, or a named
component.

A name in a file is not a definition: the call, the declaration, the comment and the
local variable all carry it. The declaration is read to its closing parenthesis and
only what follows decides.

usage: check-ios27-symbols.py --tree <xnu-work> [--sources <dir>...] [--self-test]
"""

import argparse
import os
import re
import sys

COMPONENTS = (
    ("coachz_baseband_", "QcomBaseband"),
    ("coachz_modem_data_", "QcomBaseband"),
    ("ArmSmmu4K", "ArmSmmu4K"),
    ("native_pong_ufs_", "PongUfs"),
    ("nativeVolume", "PongUfs"),
)

TREE_DIRS = ("osfmk", "bsd", "libkern", "iokit", "pexpert")
EXTERN = re.compile(r"\bextern\b([^;]*);", re.S)
NAME = re.compile(r"\b([A-Za-z_]\w*)\s*\(")
ARRAY = re.compile(r"\b([A-Za-z_]\w*)\s*\[\s*\]")
SKIP_WORDS = {"return", "if", "while", "for", "switch", "sizeof", "void", "int", "char",
              "const", "unsigned", "uint32_t", "uint64_t", "bool", "struct", "C"}
TYPE_LINE = re.compile(r"^[A-Za-z_][\w \t\*]*$")
KEYWORDS = {"return", "if", "while", "for", "switch", "sizeof", "else", "case", "do", "goto"}


def read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def source_files(sources):
    found = []
    for root in sources:
        if os.path.isfile(root):
            found.append(root)
            continue
        for base, _, names in os.walk(root):
            for name in names:
                if name.endswith((".c", ".h", ".cpp", ".mm")):
                    found.append(os.path.join(base, name))
    return sorted(found)


def extern_symbols(paths):
    found = {}
    for path in paths:
        text = read(path)
        if 'extern "C"' in text:
            text = text.replace('extern "C"', "")
        for match in EXTERN.finditer(text):
            body = match.group(1)
            names = [m.group(1) for m in NAME.finditer(body)]
            names += [m.group(1) for m in ARRAY.finditer(body)]
            for name in names:
                if name in SKIP_WORDS:
                    continue
                found.setdefault(name, path)
    return found


def neighbours(lines, index, step):
    position = index + step
    while 0 <= position < len(lines):
        if lines[position].strip():
            return lines[position].strip()
        position += step
    return ""


def defines(path, symbol, static=False):
    """True when the file defines the symbol rather than calling or declaring it.

    Four traps, each of which once produced a wrong answer: an underscore is a
    word character, so `\b` never matches the leading underscore of an assembly
    label; kernel style puts the return type on the line above the name; a
    multi-line call ends with a comma or a parenthesis exactly like a parameter
    list; and a static function cannot satisfy an extern however well it matches.
    The declaration is therefore joined until its parentheses balance, and only
    what follows the closing one decides."""
    lines = read(path).splitlines()
    word = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(symbol) + r"(?![A-Za-z0-9_])")
    for index, line in enumerate(lines):
        if path.endswith(".s"):
            if re.match(r"^\s*_?" + re.escape(symbol) + r"\s*:", line):
                return True
            if re.search(r"^\s*[A-Z_]*EXT\s*\(\s*_?" + re.escape(symbol) + r"\s*\)", line):
                return True
            continue
        if not word.search(line):
            continue
        stripped = line.strip()
        if stripped.startswith(("extern", "//", "/*", "*", "#")):
            continue
        if re.search(r"(\.|->)\s*" + re.escape(symbol) + r"(?![A-Za-z0-9_])", line):
            continue
        match = re.search(r"(?<![A-Za-z0-9_])" + re.escape(symbol) + r"\s*\(", line)
        if not match:
            lead = line[:line.find(symbol)].strip()
            if (line[:1] not in (" ", "\t") and "=" in line and lead
                    and TYPE_LINE.match(lead) and lead.split()[0] not in KEYWORDS
                    and not lead.startswith("static")
                    and re.search(r"(?<![A-Za-z0-9_])" + re.escape(symbol) + r"\s*[\[=]", line)):
                return True
            continue
        prefix = line[:match.start()].strip()
        if prefix:
            if not TYPE_LINE.match(prefix) or prefix.split()[0] in KEYWORDS:
                continue
            if prefix.startswith("static") != static:
                continue
        else:
            above = neighbours(lines, index, -1)
            if not TYPE_LINE.match(above) or above.endswith((";", ")")):
                continue
            if above.split()[0] in KEYWORDS or above.startswith("static") != static:
                continue
        depth = 0
        after = ""
        closed = False
        for offset in range(0, 14):
            if index + offset >= len(lines):
                break
            piece = line[match.start():] if offset == 0 else lines[index + offset]
            for position, character in enumerate(piece):
                if character == "(":
                    depth += 1
                elif character == ")":
                    depth -= 1
                    if depth == 0:
                        closed = True
                        after = piece[position + 1:]
                        break
            if closed:
                break
        if not closed:
            continue
        if ";" in after:
            continue
        if "{" in after:
            return True
        if neighbours(lines, index + offset, 1).startswith("{"):
            return True
        continue
    return False


def static_in_same_file(paths, symbol):
    """A static definition in the same translation unit as the extern.

    That pair only makes sense under conditional compilation: one branch
    declares the symbol for a host test, the other defines it for the kernel.
    The linker never sees both, so the extern is answered."""
    for path in paths:
        if defines(path, symbol, static=True):
            return path
    return None


def preference(path):
    """A definition in the arm tree outranks the same name in another port."""
    score = 9
    for rank, needle in enumerate(("/arm64/", "/arm/", "/kern/")):
        if needle in path:
            score = min(score, rank)
    if "/x86_64/" in path or "/i386/" in path:
        score += 5
    return score


def tree_definitions(tree, symbols):
    answer = {}
    if not tree:
        return answer
    remaining = set(symbols)
    for part in TREE_DIRS:
        base = os.path.join(tree, part)
        if not os.path.isdir(base):
            continue
        for root, _, names in os.walk(base):
            for name in names:
                if not name.endswith((".c", ".h", ".cpp", ".mm", ".s")):
                    continue
                path = os.path.join(root, name)
                try:
                    if os.path.getsize(path) > 2_000_000:
                        continue
                except OSError:
                    continue
                text = read(path)
                for symbol in list(remaining):
                    if symbol not in text:
                        continue
                    if defines(path, symbol):
                        candidate = os.path.relpath(path, tree)
                        chosen = answer.get(symbol)
                        if chosen is None or preference(candidate) < preference(chosen):
                            answer[symbol] = candidate
                            if answer[symbol].startswith(("osfmk/arm", "bsd/arm")):
                                remaining.discard(symbol)
            if not remaining:
                return answer
    return answer


def component_for(symbol):
    for prefix, component in COMPONENTS:
        if symbol.startswith(prefix):
            return component
    return None


def resolve(tree, sources, extra_paths=()):
    paths = source_files(sources) + list(extra_paths)
    if not paths:
        return None, ["no sources to read"]
    externs = extern_symbols(paths)
    from_set = {name: path for name, path in externs.items()
                if any(defines(p, name) for p in paths)}
    pending = {name: path for name, path in externs.items() if name not in from_set}
    in_tree = tree_definitions(tree, pending)
    pending = {name: path for name, path in pending.items() if name not in in_tree}
    conditional = {name: static_in_same_file(paths, name) for name in pending}
    pending = {name: path for name, path in pending.items() if not conditional[name]}
    component = {name: component_for(name) for name in pending}
    unresolved = sorted(name for name, comp in component.items() if not comp)
    return {
        "externs": externs,
        "set": from_set,
        "tree": in_tree,
        "conditional": {n: p for n, p in conditional.items() if p},
        "component": {n: c for n, c in component.items() if c},
        "unresolved": unresolved,
    }, []


def report(result):
    if result is None:
        return 2
    print("K60 SYMBOLS ok   %d externs read from the ported sources"
          % len(result["externs"]))
    if result["set"]:
        print("K60 SYMBOLS ok   %d answered by the patch set" % len(result["set"]))
    if result["tree"]:
        print("K60 SYMBOLS ok   %d answered by the target tree" % len(result["tree"]))
    if result.get("conditional"):
        names = sorted(result["conditional"])
        print("K60 SYMBOLS ok   %d symbol(s) are static in their own file, live only "
              "under another configuration: %s" % (len(names), " ".join(names[:3])))
    if result["component"]:
        by_component = {}
        for name, comp in result["component"].items():
            by_component.setdefault(comp, []).append(name)
        for comp in sorted(by_component):
            names = sorted(by_component[comp])
            print("K60 SYMBOLS note %d symbol(s) need the %s component: %s"
                  % (len(names), comp, " ".join(names[:3]) + (" ..." if len(names) > 3 else "")))
    if result["unresolved"]:
        print("K60 SYMBOLS FAILED %d symbol(s) resolve nowhere: %s"
              % (len(result["unresolved"]), " ".join(result["unresolved"][:5])))
        return 1
    print("K60 SYMBOLS OK every extern the patches declare has a named provider")
    return 0


def self_test():
    import tempfile
    failed = 0
    with tempfile.TemporaryDirectory(prefix="k60-symbols-") as base:
        src = os.path.join(base, "src")
        os.makedirs(src)
        treesrc = os.path.join(base, "tree", "osfmk", "arm64")
        os.makedirs(treesrc)
        assembly = os.path.join(base, "tree", "osfmk", "arm64", "caches_asm.s")
        with open(assembly, "w") as handle:
            handle.write("_flush_dcache64:\n\tret\n")
        with open(os.path.join(treesrc, "clock.c"), "w") as handle:
            handle.write("void\ndelay(int micro)\n{\n}\n")
        with open(os.path.join(src, "a.c"), "w") as handle:
            handle.write("extern void delay(int);\n"
                         "extern void flush_dcache64(addr64_t, unsigned, boolean_t);\n"
                         "extern int coachz_baseband_poll(void);\n"
                         "extern int nowhere_symbol(void);\n"
                         "extern int local_symbol(void);\n"
                         "int\nlocal_symbol(void)\n{\n  return 0;\n}\n"
                         "static void trap(void) { local_symbol(); }\n")
        result, errors = resolve(os.path.join(base, "tree"), [src])
        if errors:
            print("K60 SYMBOLS FAILED self-test: %s" % errors[0])
            failed += 1
        else:
            if "delay" not in result["tree"]:
                print("K60 SYMBOLS FAILED self-test: delay not found in the tree")
                failed += 1
            if "flush_dcache64" not in result["tree"]:
                print("K60 SYMBOLS FAILED self-test: an assembly label was not read")
                failed += 1
            if result["component"].get("coachz_baseband_poll") != "QcomBaseband":
                print("K60 SYMBOLS FAILED self-test: coachz not mapped to its component")
                failed += 1
            if "trap" in result["conditional"] or "local_symbol" in result["conditional"]:
                print("K60 SYMBOLS FAILED self-test: a normal definition was called conditional")
                failed += 1
            if "local_symbol" not in result["set"]:
                print("K60 SYMBOLS FAILED self-test: a kernel-style definition was missed")
                failed += 1
            if result["unresolved"] != ["nowhere_symbol"]:
                print("K60 SYMBOLS FAILED self-test: unresolved was %r" % (result["unresolved"],))
                failed += 1
    if failed:
        return 1
    print("K60 SYMBOLS PASS patch set, arm64 tree, assembly label, missing symbol")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree")
    ap.add_argument("--sources", nargs="*", help="directories or single files")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sources = args.sources or [os.path.join(here, "drivers", "PongCellular"),
                               os.path.join(here, "drivers", "NativeUfs")]
    if args.self_test:
        return self_test()
    if not args.tree:
        print("usage: check-ios27-symbols.py --tree <xnu-work> [--self-test]")
        return 2
    result, errors = resolve(args.tree, sources)
    if errors:
        print("K60 SYMBOLS INVALID %s" % errors[0])
        return 2
    return report(result)


if __name__ == "__main__":
    sys.exit(main())
