#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""The chaining conf/files hook has to fail loudly and say what it wrote."""
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

ANCHOR = 'bsd/dev/unix_startup.c\t\t\tstandard'


def seed(root, anchor=True):
    """A 27-shaped tree: sources in place, conf/files in place."""
    (root / "bsd/conf").mkdir(parents=True, exist_ok=True)
    (root / "bsd/dev").mkdir(parents=True, exist_ok=True)
    for name in ("PongAudioGeniI2c.c", "PongAudioAmp.c"):
        (root / "bsd/dev" / name).write_text("/* fixture */" + chr(10))
    body = "bsd/dev/vfs_syscalls.c\t\t\tstandard" + chr(10)
    if anchor:
        body += ANCHOR + chr(10)
    (root / "bsd/conf/files").write_text(body)
    return root


def hook():
    return str(pathlib.Path(__file__).resolve().parent.parent / "k60-conf-files-hook.py")


def run(tree, extra=None, anchor=None):
    env = dict(os.environ)
    env.pop("K60_CONF_FILES_HOOK_EXTRA", None)
    env.pop("K60_CONF_FILES_ANCHOR", None)
    if extra:
        env["K60_CONF_FILES_HOOK_EXTRA"] = extra
    if anchor:
        env["K60_CONF_FILES_ANCHOR"] = anchor
    return subprocess.run([sys.executable, hook(), str(tree)], capture_output=True, text=True, env=env)


def audio_lines(root):
    return sum(1 for line in (root / "bsd/conf/files").read_text().splitlines() if "PongAudio" in line)


def case_ok(tmp):
    tree = seed(tmp / "ok")
    done = run(tree)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "K60: conf-files hook ok audio=2 extra=0" in done.stdout, done.stdout
    assert audio_lines(tree) == 2


def case_missing_anchor(tmp):
    tree = seed(tmp / "noanchor", anchor=False)
    done = run(tree)
    assert done.returncode == 1, done.stdout
    assert "K60: conf-files hook FAILED: audio exited 1" in done.stdout, done.stdout
    assert audio_lines(tree) == 0


def case_extra_ok(tmp):
    tree = seed(tmp / "extra")
    appender = tmp / "extra_ok.py"
    appender.write_text("import sys\nfrom pathlib import Path\npath = Path(sys.argv[1]) / 'bsd/conf/files'\npath.write_text(path.read_text() + 'bsd/dev/Extra.c\t\t\tstandard\\n')\n")
    done = run(tree, extra=str(appender))
    assert done.returncode == 0, done.stdout + done.stderr
    assert "extra=1" in done.stdout, done.stdout
    assert "bsd/dev/Extra.c" in (tree / "bsd/conf/files").read_text()


def case_extra_fails(tmp):
    tree = seed(tmp / "bad")
    appender = tmp / "extra_bad.py"
    appender.write_text("import sys" + chr(10) + "sys.exit(3)" + chr(10))
    done = run(tree, extra=str(appender))
    assert done.returncode == 1, done.stdout
    assert "K60: conf-files hook FAILED: extra0 exited 3" in done.stdout, done.stdout


def case_unseeded(tmp):
    tree = tmp / "bare"
    tree.mkdir()
    done = run(tree)
    assert done.returncode == 1, done.stdout
    assert "K60: conf-files hook FAILED: no bsd/conf/files" in done.stdout, done.stdout


def main():
    cases = [case_ok, case_missing_anchor, case_extra_ok, case_extra_fails, case_unseeded]
    root = pathlib.Path(tempfile.mkdtemp(prefix="confhook-"))
    try:
        for case in cases:
            case(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print("TESTS OK %d cases" % len(cases))
    return 0


if __name__ == "__main__":
    sys.exit(main())
