#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Compare the host stub headers with what the 27 tree actually declares.

The stubs in scripts/tests/portability are written by this repository. Every
host build (run.sh, run-symbols.sh, run-deps.sh, run-warnings.sh, the probe
runner) compiles against them, so a stub that is wider than the kernel hides
exactly the class of mistake it exists to catch: on 2026-11-20 the stub said
delay_for_interval(uint64_t, uint64_t) while osfmk/kern/clock.h:327 takes two
uint32_t, so a 64-bit argument at the call site would have passed every host
gate and truncated on the device.

  python3 scripts/check-audio27-stubs.py <xnu-tree>
  # STUBS OK 5/5 declarations match xnu-12377.121.6 ac9718f

The comparison is the same canonical form check-audio27-kernel-api.py uses:
return type plus parameter types, parameter names ignored.
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from importlib.machinery import SourceFileLoader  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent


def api_module():
    """The api checker, for canonical() and declarations()."""
    path = HERE / "check-audio27-kernel-api.py"
    return SourceFileLoader("audio27api", str(path)).load_module()


NAMES = ("ml_io_map", "ml_io_map_wcomb", "PE_parse_boot_argn",
         "delay_for_interval", "printf")


def stub_text(name):
    """The line that declares name in the stub headers, or None."""
    base = HERE.parent / "scripts/tests/portability"
    word = re.compile(r"\b%s\b" % re.escape(name))
    for path in sorted(base.rglob("*.h")):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines(True)
        except OSError:
            continue
        for index, line in enumerate(lines):
            if word.search(line) and not line.lstrip().startswith(("/*", "*")):
                return path.relative_to(base), "".join(lines[index:index + 4])
    return None, None


def looks_like_prototype(name, text):
    """True when the matched line declares name, not a macro body that uses it."""
    first = text.splitlines()[0].strip() if text.strip() else ""
    if not first or "#" in first:
        return False
    head = first.split(name, 1)[0].strip()
    if not head:
        return False
    return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_ \t*]*$", head))


def main(argv):
    if len(argv) < 2:
        sys.stderr.write("usage: check-audio27-stubs.py <xnu-tree>\n")
        return 2
    api = api_module()
    root = api.resolve(pathlib.Path(argv[1]))
    if root is None:
        print("STUBS: no bsd/conf/files under %s" % argv[1])
        return 1

    compared, missing, drifted = 0, [], []
    for name in NAMES:
        where, text = stub_text(name)
        if text is None:
            missing.append("no stub declares %s" % name)
            continue
        hits = [hit for hit in api.declarations(root, name)
                if looks_like_prototype(name, hit[1])]
        if not hits:
            missing.append("the tree does not declare %s" % name)
            continue
        want = api.canonical(text)
        found = api.canonical(hits[0][1])
        compared += 1
        if want != found:
            drifted.append("%s: the stub (%s) says %s, %s says %s"
                            % (name, where, want, hits[0][0], found))
    if missing or drifted:
        for line in missing + drifted:
            print("STUB DRIFT: %s" % line)
        print("STUBS FAILED: %d declaration(s) compared, %d missing, %d drifted"
              % (compared, len(missing), len(drifted)))
        return 1
    print("STUBS OK %d/%d declarations match %s" % (compared, len(NAMES),
                                                        api.version(root)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
