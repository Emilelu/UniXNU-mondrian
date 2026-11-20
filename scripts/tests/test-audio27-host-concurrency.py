#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Four audio suite runs at once must not share a file.

The wiring dry run copies the driver into a temp tree and then runs
drivers/PongAudio/tests/run-tests.sh inside it. Both scripts take an optional
work directory: a caller that owns one passes it and keeps it, and the dry run
passes its own directory down to the host suite. This test starts four dry runs
at once, each on a directory it owns, and requires all four to finish with
DRYRUN OK and to leave the compiled binary in the directory it was given.

That is the regression for the 2026-11-20 collision: two preflights shared
${TMPDIR:-/tmp}/test-pong-audio-geni-i2c and the second exec failed with
"Text file busy".

Usage: python3 scripts/tests/test-audio27-host-concurrency.py
"""
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
DRY = ROOT / "scripts/tests/test-wiring-dry-run.sh"
HOST = ROOT / "drivers/PongAudio/tests/run-tests.sh"
BUSY = "Text file busy"


def spawn(command):
    return subprocess.Popen(command, cwd=str(ROOT), stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)


def finish(process, label):
    out, _ = process.communicate(timeout=300)
    assert process.returncode == 0, label + " exited " + str(process.returncode) + ":\n" + out
    return out


def case_four_at_once(root):
    dirs = [root / ("run%d" % number) for number in range(4)]
    processes = [spawn(["/bin/sh", str(DRY), str(directory)]) for directory in dirs]
    outputs = []
    try:
        for process, directory in zip(processes, dirs):
            outputs.append(finish(process, "dry run " + directory.name))
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
    for directory, out in zip(dirs, outputs):
        assert "DRYRUN OK" in out, out
        assert "TESTS OK" in out, out
        assert BUSY not in out, out
        assert (directory / "tree").is_dir(), out
        assert (directory / "host" / "test-pong-audio-geni-i2c").is_file(), out


def case_host_takes_workdir(root):
    directory = root / "host-only"
    done = subprocess.run(["/bin/sh", str(HOST), str(directory)], cwd=str(ROOT),
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "TESTS OK" in done.stdout, done.stdout
    assert (directory / "test-pong-audio-geni-i2c").is_file(), done.stdout


def case_usage(root):
    for command in ([DRY, "a", "b"], [HOST, "a", "b"]):
        done = subprocess.run(["/bin/sh"] + [str(item) for item in command], cwd=str(ROOT),
                              capture_output=True, text=True)
        assert done.returncode == 2, command
        assert "usage:" in (done.stdout + done.stderr), command


def main(argv):
    if any(argument in ("-h", "--help") for argument in argv):
        print((__doc__ or "").strip())
        return 0
    root = pathlib.Path(tempfile.mkdtemp(prefix="audio27-conc-"))
    cases = [case_four_at_once, case_host_takes_workdir, case_usage]
    try:
        for case in cases:
            case(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print("TESTS OK %d cases" % len(cases))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
