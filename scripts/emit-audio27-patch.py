#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Emit the 27 series patch that calls the audio probe from bsd_init().

The applier's INIT_BLOCK is the source of truth for the call site; this script
turns that block into the patch the 27 series carries, so the two cannot drift:
regenerate, compare the digest printed here with the one in the record.

The target is a pristine XNU source tree. Nothing in it is written: the block is
applied in memory, the difference is printed, and --check asks git whether the
result would apply.
"""
import argparse
import difflib
import hashlib
import importlib.util
import io
import pathlib
import re
import subprocess
import sys


def blob(text):
    """SHA-1 of the blob git would store, so the index line is the real one."""
    data = text.encode("utf-8")
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def add_function(diff, lines):
    """Append the enclosing C function to the hunk header.

    git does that so a reader knows where the change lands. difflib does not,
    and without it the emitted patch is not the bytes the series holds, so the
    record digest would always differ.
    """
    out = []
    for line in diff:
        if line.startswith("@@ "):
            hit = re.match(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
            start = int(hit.group(1)) - 1
            for back in range(min(start, len(lines)) - 1, -1, -1):
                text = lines[back].rstrip()
                if re.match(r"^[A-Za-z_][A-Za-z0-9_ *]*\([^;]*\)$", text):
                    line = hit.group(0) + " " + text + "\n"
                    break
        out.append(line)
    return out


def load_wiring(path):
    spec = importlib.util.spec_from_file_location("audio_wiring", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def emit(tree, wiring, context=1):
    """Return (patch text, hooked text) or raise LookupError with the reason.

    The default is one line of context, not three. The call site sits in
    bsd_init(), a function the Bluetooth patches already edit, and a -U3 hunk
    was measured failing inside the real sequence while applying cleanly on a
    pristine tree. One line keeps the anchor and nothing else.
    """
    path = tree / wiring.INIT_FILE
    if not path.is_file():
        raise LookupError("no %s under %s" % (wiring.INIT_FILE, tree))
    text = path.read_text(errors="replace")
    anchor = wiring.INIT_ANCHOR
    if anchor not in text:
        raise LookupError("anchor %r missing; pass --init-anchor"
                          % anchor)
    stripped = False
    if wiring.CALL in text:
        if wiring.INIT_BLOCK not in text:
            raise LookupError("%s carries a probe call this block did not write"
                              % wiring.INIT_FILE)
        # a tree the applier already wired: emit from the form before the block
        text = text.replace(wiring.INIT_BLOCK, "", 1)
        stripped = True
    at = text.index(anchor) + len(anchor)
    hooked = text[:at] + wiring.INIT_BLOCK + text[at:]
    diff = difflib.unified_diff(
        text.splitlines(True), hooked.splitlines(True),
        fromfile="a/" + wiring.INIT_FILE, tofile="b/" + wiring.INIT_FILE, n=context)
    diff = add_function(diff, text.splitlines())
    head = ["diff --git a/%s b/%s\n" % (wiring.INIT_FILE, wiring.INIT_FILE),
            "index %s..%s 100644\n" % (blob(text)[:7], blob(hooked)[:7])]
    return "".join(head) + "".join(diff), stripped


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("tree", help="pristine XNU source tree")
    parser.add_argument("--out", help="write the patch here instead of stdout")
    parser.add_argument("--expect", help="digest the patch must have")
    parser.add_argument("--check", action="store_true",
                        help="also ask git whether the patch applies")
    parser.add_argument("--context", type=int, default=1,
                        help="context lines per hunk (1 is the series form: the"
                             " sequence edits this function around the call)")
    parser.add_argument("--wiring", default=None,
                        help="apply-audio27-wiring.py to take the block from")
    args = parser.parse_args(argv[1:])

    here = pathlib.Path(__file__).resolve().parent
    wiring_path = pathlib.Path(args.wiring) if args.wiring else here / "apply-audio27-wiring.py"
    tree = pathlib.Path(args.tree)
    try:
        patch, stripped = emit(tree, load_wiring(wiring_path), args.context)
    except LookupError as error:
        print("audio patch: %s" % error, file=sys.stderr)
        return 1

    digest = hashlib.sha256(patch.encode("utf-8")).hexdigest()
    if args.out:
        pathlib.Path(args.out).write_text(patch)
    else:
        sys.stdout.write(patch)
    where = args.out or "stdout"
    print("audio patch: %s %d B sha256 %s" % (where, len(patch), digest),
          file=sys.stderr)
    if args.expect and digest != args.expect:
        print("audio patch: digest changed, the record says %s" % args.expect,
              file=sys.stderr)
        return 1
    if stripped:
        print("audio patch: the tree already carries the hook; emitted from its stripped form",
              file=sys.stderr)
    if args.check and not stripped:
        done = subprocess.run(["git", "-C", str(tree), "apply", "--check", "-"],
                              input=patch.encode("utf-8"), capture_output=True)
        if done.returncode != 0:
            sys.stderr.write(done.stderr.decode("utf-8", "replace"))
            print("audio patch: git says it would not apply", file=sys.stderr)
            return 1
        print("audio patch: APPLY CHECK OK", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
