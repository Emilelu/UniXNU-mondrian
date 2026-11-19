#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Run every owner that has to add lines to bsd/conf/files, then say so once.

Why this exists. The generic builder calls the hook like this
(scripts/build-xnu-generic.sh:17-18):

    if [ -n "${K60_CONF_FILES_HOOK:-}" ] && [ -f ... ]; then
      python3 "${K60_CONF_FILES_HOOK}" "$ROOT" || echo "K60: conf/files hook failed"
    fi

Three consequences, all of them P-171/P-245 shaped:

  1. the hook is invoked with python3, so it has to be a Python file;
  2. its exit status is swallowed by the "|| echo", so a failure is one
     line in a log nobody greps;
  3. the variable holds one path, while at least two owners (audio, power)
     each need entries in the same file.

So the thing the builder points at is this file: it runs the audio appender,
then any K60_CONF_FILES_HOOK_EXTRA (colon separated, each called with the tree
as its only argument), and ends with one verdict line:

    K60: conf-files hook ok audio=2 extra=0 tree=/path/to/tree

and exits 1 with "K60: conf-files hook FAILED: <step> exited <n>" otherwise.
That verdict line is what makes the swallow visible: a green build log that
has no "conf-files hook ok" line is a build with no audio entries in it,
which is exactly the state the product checker (check-audio27-kernel.py)
then reports as AUDIO27 FAILED.

  python3 scripts/k60-conf-files-hook.py <tree>
  K60_CONF_FILES_ANCHOR=<line>      forwarded to the audio appender
  K60_CONF_FILES_HOOK_EXTRA=<a:b:c> other owners appenders
"""
import os
import pathlib
import subprocess
import sys

MARKER = "PongAudio"


def conf_files(tree):
    """The conf/files the tree actually builds from, or None."""
    for root in (tree / ".cache/xnu-work", tree):
        path = root / "bsd/conf/files"
        if path.is_file():
            return path
    return None


def count(path):
    return sum(1 for line in path.read_text(errors="replace").splitlines() if MARKER in line)


def run(name, command, tree):
    """One step, its output passed through, its status returned."""
    done = subprocess.run(command + [str(tree)], capture_output=True, text=True)
    sys.stdout.write(done.stdout)
    sys.stderr.write(done.stderr)
    return done.returncode


def main(argv):
    if len(argv) < 2:
        print("usage: k60-conf-files-hook.py <tree>", file=sys.stderr)
        return 2
    tree = pathlib.Path(argv[1]).resolve()
    if conf_files(tree) is None:
        print("K60: conf-files hook FAILED: no bsd/conf/files under %s (tree not seeded)" % tree)
        return 1
    here = pathlib.Path(__file__).resolve().parent
    audio = [sys.executable, str(here / "add-audio-conffiles.py")]
    anchor = os.environ.get("K60_CONF_FILES_ANCHOR", "")
    if anchor:
        audio += ["--anchor", anchor]
    steps = [("audio", audio)]
    extras = [item for item in os.environ.get("K60_CONF_FILES_HOOK_EXTRA", "").split(":") if item]
    for index, extra in enumerate(extras):
        command = [sys.executable, extra] if extra.endswith(".py") else [extra]
        steps.append(("extra%d" % index, command))
    for name, command in steps:
        code = run(name, command, tree)
        if code != 0:
            print("K60: conf-files hook FAILED: %s exited %d" % (name, code))
            return 1
    path = conf_files(tree)
    lines = count(path)
    if lines < 2:
        print("K60: conf-files hook FAILED: %d audio line(s) in %s, the appender said it wrote two" % (lines, path))
        return 1
    print("K60: conf-files hook ok audio=%d extra=%d tree=%s" % (lines, len(extras), tree))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
