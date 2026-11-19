#!/usr/bin/env python3
"""Check that every system header the carried sources compiled against exists
in the iOS 27 tree.

The 16 line build tree leaves one .d file per object under
build/xnu/ios-obj/<config>/bsd/DEVELOPMENT/.  Those files list the absolute
paths of everything the compiler opened, including headers from
<tree>/.cache/xnu-work/...  After 27 renames or removes a header, nothing says
so until a twenty minute kernel build fails on it -- 0627 and 0628 already
needed pong_smem.h, which was not in the tree at all (P-208).

Usage:
  check-ios27-deps.py --deps <obj dir> --work <16 tree> --tree <27 tree>
  check-ios27-deps.py --self-test

Exit codes: 0 every header is present, 1 some are missing, 2 the inputs are
unusable (missing directory, no .d file, unreadable 27 tree).
"""

import argparse
import os
import sys

DEFAULT_OBJECTS = (
    "pong_modem_link",
    "pong_modem_qrtr",
    "pong_modem_rmtfs",
    "pong_modem_memshare",
    "pong_modem_efs",
    "pong_ipa",
    "pong_modem_pas",
    "pong_modem_boot",
)

CARRY_PREFIXES = ("pong_", "qcom_glink")


def tokens(dep_path):
    """Read one .d file and return the paths it lists."""
    with open(dep_path, encoding="utf-8", errors="replace") as handle:
        text = handle.read()
    text = text.replace("\\\n", " ")
    return [token.rstrip(":") for token in text.split()]


def closure(deps_dir, work, objects):
    """Map tree relative header path -> objects that included it."""
    refs = {}
    seen = []
    for name in objects:
        dep = os.path.join(deps_dir, name + ".d")
        if not os.path.exists(dep):
            continue
        seen.append(name)
        for token in tokens(dep):
            if not token.startswith(work + os.sep):
                continue
            relative = token[len(work) + 1:]
            if os.path.basename(relative).startswith(CARRY_PREFIXES):
                continue
            refs.setdefault(relative, set()).add(name)
    return refs, seen


def check(refs, tree):
    """Return the headers that the 27 tree does not have."""
    return sorted(r for r in refs if not os.path.exists(os.path.join(tree, r)))


def run(deps_dir, work, tree, objects):
    if not os.path.isdir(deps_dir):
        print("K60 DEPS UNUSABLE no dependency directory at %s" % deps_dir)
        return 2
    if not os.path.isdir(work):
        print("K60 DEPS UNUSABLE no work tree at %s" % work)
        return 2
    if not os.path.isdir(tree):
        print("K60 DEPS UNUSABLE no 27 tree at %s" % tree)
        return 2
    refs, seen = closure(deps_dir, work, objects)
    if not seen:
        print("K60 DEPS UNUSABLE no .d file for any of: %s" % ", ".join(objects))
        return 2
    missing = check(refs, tree)
    if missing:
        print("K60 DEPS DRIFT %d of %d headers are not in the 27 tree" % (len(missing), len(refs)))
        for relative in missing:
            print("  MISS %s <- %s" % (relative, ", ".join(sorted(refs[relative]))))
        return 1
    print("K60 DEPS OK %d headers from %d objects, none missing" % (len(refs), len(seen)))
    return 0


def self_test():
    import tempfile

    root = tempfile.mkdtemp(prefix="k60-deps-")
    deps = os.path.join(root, "obj")
    work = os.path.join(root, "work")
    tree = os.path.join(root, "tree")
    for path in (deps, work, tree):
        os.makedirs(path)
    for relative in ("bsd/sys/proc.h", "osfmk/mach/port.h"):
        full = os.path.join(tree, relative)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        open(full, "w").close()

    def dep(name, paths):
        body = name + ".o: \\\n" + " \\\n".join("  " + p for p in paths) + "\n"
        with open(os.path.join(deps, name + ".d"), "w", encoding="utf-8") as handle:
            handle.write(body)

    dep("pong_modem_link", [os.path.join(work, "bsd/sys/proc.h"),
                            os.path.join(work, "osfmk/mach/port.h"),
                            os.path.join(work, "bsd/dev/pong_modem_qrtr.h"),
                            "/usr/include/stdint.h"])
    good = run(deps, work, tree, ("pong_modem_link",))
    dep("pong_ipa", [os.path.join(work, "bsd/sys/gone.h")])
    bad = run(deps, work, tree, ("pong_ipa",))
    empty = run(deps, work, tree, ("pong_audio",))
    if (good, bad, empty) == (0, 1, 2):
        print("K60 DEPS PASS closure measured, absence detected, junk refused")
        return 0
    print("K60 DEPS FAIL %d %d %d" % (good, bad, empty))
    return 1


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deps")
    parser.add_argument("--work")
    parser.add_argument("--tree")
    parser.add_argument("--objects", nargs="*", default=list(DEFAULT_OBJECTS))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if not (args.deps and args.work and args.tree):
        parser.error("--deps, --work and --tree are required unless --self-test")
    return run(args.deps, args.work, args.tree, tuple(args.objects))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
