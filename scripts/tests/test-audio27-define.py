#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Host cases for the per-object define that switches the audio glue on.

The glue is compiled only under -DXNU_PONG_AUDIO, and that define has to
reach exactly one object. Three things can go wrong, and all of them look
like a green build:

  1. the variable is handed over as EXTRA_MAKE_ARGS, which
     scripts/build-xnu-generic.sh resets to an empty array at :166;
  2. the variable survives but the shell is dash, which drops environment
     names that are not valid shell identifiers (the dot in the name);
  3. the documentation drifts back to the form that does not work.

So the cases below run a builder-shaped harness rather than trusting the
text, and one case reads the wiring page to keep the two in step.
"""
import os
import pathlib
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[2]
WIRING = REPO / "docs/research/audio/IOS27-WIRING.md"
BUILDER = REPO / "scripts/build-xnu-generic.sh"
FLAG = "-DXNU_PONG_AUDIO=1"
NAME = "PongAudioAmp.o_CFLAGS_ADD"

MAKEFILE = (
    "PongAudioAmp.o_CFLAGS_ADD += -DFROM_CONF" + chr(10)
    + "all:" + chr(10)
    + chr(9) + "@echo \"make sees: [$(PongAudioAmp.o_CFLAGS_ADD)]\"" + chr(10))
BUILDER_BODY = (
    "#!/usr/bin/env bash" + chr(10)
    + "set -eu" + chr(10)
    + "EXTRA_MAKE_ARGS=()" + chr(10)
    + "EXTRA_MAKE_ARGS+=(\"XNU_KERNEL_CHAINED_FIXUPS=0\")" + chr(10)
    + "make -s -f \"$(dirname \"$0\")/fake.mk\" \"${EXTRA_MAKE_ARGS[@]}\"" + chr(10))

def harness(work):
    root = work / "harness"
    (root / "sub").mkdir(parents=True)
    (root / "fake.mk").write_text(MAKEFILE)
    (root / "builder.sh").write_text(BUILDER_BODY)
    return root

def run(root, shell, extra):
    env = dict(os.environ)
    env.update(extra)
    done = subprocess.run([shell, "builder.sh"], cwd=str(root), env=env,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return done.returncode, done.stdout

def main():
    work = pathlib.Path(tempfile.mkdtemp(prefix="audio27-define-"))
    root = harness(work)
    cases = 0

    code, out = run(root, "bash", {"EXTRA_MAKE_ARGS": NAME + "=" + FLAG})
    assert code == 0, out
    assert FLAG not in out, out
    assert "[-DFROM_CONF]" in out, out
    cases += 1
    print("  ok   EXTRA_MAKE_ARGS is reset by the builder, so it delivers nothing")

    code, out = run(root, "bash", {NAME: FLAG})
    assert code == 0, out
    assert "make sees: [" + FLAG + " -DFROM_CONF]" in out, out
    cases += 1
    print("  ok   a dotted environment name reaches make under bash, appended to conf")

    def env_seen(shell):
        env = dict(os.environ)
        env[NAME] = FLAG
        done = subprocess.run([shell, "-c", "env"], env=env,
                              stdout=subprocess.PIPE, text=True)
        return NAME in done.stdout

    shell = pathlib.Path("/bin/sh").resolve()
    if "dash" in shell.name:
        assert env_seen("bash") is True, "bash lost the dotted name"
        assert env_seen(str(shell)) is False, "dash kept a dotted name"
        cases += 1
        print("  ok   dash drops the dotted name, which is why the page says bash")
        code, out = run(root, "sh", {})
        assert code != 0, out
        cases += 1
        print("  ok   dash cannot run the builder at all: its arrays are bash only")
    else:
        print("  skip dash is not /bin/sh here; the bash case above still holds")

    text = WIRING.read_text()
    assert NAME + "=" + FLAG + " bash scripts/build-xnu-generic.sh" in text, "wiring page lacks the working form"
    assert "静默无效" in text, "the page no longer says why the environment form is dropped"
    cases += 1
    print("  ok   the wiring page shows the form that works, not the inert one")

    if BUILDER.is_file():
        body = BUILDER.read_text()
        assert "EXTRA_MAKE_ARGS=()" in body, "the builder no longer resets the array"
        assert ":166" in text, "the page no longer names the line that resets it"
        cases += 1
        print("  ok   the builder still resets the array at the line the page names")
    else:
        print("  skip no scripts/build-xnu-generic.sh in this tree (it comes from main)")

    print("TESTS OK %d cases" % cases)
    return 0

if __name__ == "__main__":
    sys.exit(main())
