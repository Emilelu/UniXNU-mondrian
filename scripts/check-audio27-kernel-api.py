#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Check the four kernel interfaces the audio glue names, in a real XNU tree.

scripts/tests/portability/run-deps.sh proves the glue needs nothing beyond the
six names in IOS27-WIRING.md section 1, but it proves that against stub headers
this repository writes. The other half - that those four kernel interfaces are
still declared the same way in the 27 baseline - cannot be faked: it is a fact
about the tree.

  python3 scripts/check-audio27-kernel-api.py <xnu-tree>
  # API OK 4/4 xnu-12377.121.6 ac9718f

Two things are checked per name: that the tree declares it, and that the
declaration takes and returns what the glue assumes. A renamed function is
easy to notice; a widened or reordered parameter list is not, and the stub
headers cannot see it either because this repository writes them.

The tree may be the seeded repository or the XNU sources themselves; both are
searched. Generated headers, the wiring's own files and other architectures are
skipped, and a header that calls the name counts before one that only mentions
it, so the line printed is the declaration the port will use.
"""
import pathlib
import re
import subprocess
import sys

# name -> (why the wiring table names it, the declaration the glue assumes)
API = {
    "ml_io_map": ("maps a physical window for the pad and I2C registers",
                  "vm_offset_t ml_io_map(vm_offset_t, vm_size_t)"),
    "ml_io_map_wcomb": ("the write-combining map the playback buffer needs",
                        "vm_offset_t ml_io_map_wcomb(vm_offset_t, vm_size_t)"),
    "PE_parse_boot_argn": ("reads pong_audio_probe=1, the probe gate",
                           "boolean_t PE_parse_boot_argn(const char *, void *, int)"),
    "delay_for_interval": ("the write-then-read settling delay",
                           "void delay_for_interval(uint32_t, uint32_t)"),
}
SEARCH = ("bsd", "osfmk", "pexpert", "libkern")
SKIP_DIRS = ("i386", "x86", "x86_64")
SKIP_FILES = ("static_if.h",)
SKIP_PREFIX = ("PongAudio", "K60")


def resolve(tree):
    """The XNU sources for either layout: a seeded repo, or the sources themselves."""
    for root in (tree / ".cache/xnu-work", tree):
        if (root / "bsd/conf/files").is_file():
            return root
    return None


def declarations(root, name):
    """Where the name lives, declarations first; one hit per header."""
    word = re.compile(r"\b%s\b" % re.escape(name))
    call = re.compile(r"\b%s\s*\(" % re.escape(name))
    calls, mentions = [], []
    for part in SEARCH:
        base = root / part
        if not base.is_dir():
            continue
        for path in base.rglob("*.h"):
            if path.name in SKIP_FILES or path.name.startswith(SKIP_PREFIX):
                continue
            if any(part_name in SKIP_DIRS for part_name in path.parts):
                continue
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as handle:
                    lines = handle.readlines()
            except OSError:
                continue
            for index, line in enumerate(lines):
                if word.search(line):
                    where = "%s:%d" % (path.relative_to(root), index + 1)
                    (calls if call.search(line) else mentions).append(
                        (where, "".join(lines[index:index + 8])))
                    break
    return calls + mentions


def arguments(text):
    """The parameter types of a declaration, names dropped."""
    start = text.find("(")
    if start < 0:
        return []
    depth, end = 0, -1
    for index in range(start, len(text)):
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            depth -= 1
            if depth == 0:
                end = index
                break
    if end < 0:
        return []
    body = text[start + 1:end]
    parts, depth, current = [], 0, ""
    for char in body:
        if char == "," and depth == 0:
            parts.append(current)
            current = ""
            continue
        if char in "([":
            depth += 1
        elif char in ")]":
            depth -= 1
        current += char
    parts.append(current)

    types = []
    for part in parts:
        # A parameter name is an identifier after a space or a star; a bare
        # "vm_offset_t" is a type and must survive, and "char *name" keeps its
        # star once the name is gone.
        text = part.strip()
        hit = re.search(r"(\*\s*|\s+)([A-Za-z_][A-Za-z0-9_]*)$", text)
        if hit:
            text = text[:hit.start()] + ("*" if hit.group(1).startswith("*") else "")
        norm = "".join(text.split())
        if norm:
            types.append(norm)
    return types


def canonical(text):
    """'extern vm_offset_t ml_io_map(vm_offset_t a, vm_size_t b);' -> 'vm_offset_t ml_io_map(vm_offset_t, vm_size_t)'."""
    flat = " ".join(text.split()).replace("( ", "(").replace(" )", ")")
    flat = re.sub(r"\bextern\b", "", flat).strip()
    flat = flat.split(";")[0].strip()
    name = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", flat)
    if not name:
        return flat
    ret = flat[:name.start(1)].strip()
    return "%s %s(%s)" % (ret, name.group(1), ", ".join(arguments(flat)))


def version(root):
    try:
        done = subprocess.run(["git", "-C", str(root), "log", "-1", "--format=%s %h"],
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              universal_newlines=True)
        if done.returncode == 0 and done.stdout.strip():
            return done.stdout.strip()
    except OSError:
        pass
    return "unknown revision"


def main(argv):
    if len(argv) < 2:
        sys.stderr.write("usage: check-audio27-kernel-api.py <xnu-tree>\n")
        return 2
    root = resolve(pathlib.Path(argv[1]))
    if root is None:
        print("API: no bsd/conf/files under %s (neither .cache/xnu-work nor the "
              "tree itself)" % argv[1])
        return 1

    missing, drifted = [], []
    for name in sorted(API):
        why, expected = API[name]
        hits = declarations(root, name)
        if not hits:
            missing.append(name)
            continue
        where, text = hits[0]
        found = canonical(text)
        expected = canonical(expected)
        if found != expected:
            drifted.append("%s: %s declares %s, the glue assumes %s"
                           % (name, where, found, expected))
            print("  %-20s %s  (SIGNATURE CHANGED)" % (name, where))
        else:
            print("  %-20s %s  (%s)" % (name, where, why))
    if missing:
        print("API FAILED: %d of %d names absent from %s: %s"
              % (len(missing), len(API), root, ", ".join(missing)))
        return 1
    if drifted:
        for line in drifted:
            print("API FAILED: " + line)
        return 1
    print("API OK %d/%d %s" % (len(API), len(API), version(root)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
