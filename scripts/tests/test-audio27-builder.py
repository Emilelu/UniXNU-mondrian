#!/usr/bin/env python3
"""Host cases for scripts/check-audio27-builder.py.

Each case writes a small k60-gates-shaped tree and a framework-shaped tree,
then asks the checker what it sees. The point is that every failure this
checker can report is reproduced here: a claim without a case is a claim that
will rot the first time the driver changes shape.
"""

import pathlib
import subprocess
import sys
import tempfile

CHECKER = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "check-audio27-builder.py"

DRIVER = chr(10).join([
    "#!/bin/sh",
    "set -eu",
    "ROOT=$(CDPATH= cd -- \"$(dirname -- \"$0\")/..\" && pwd)",
    "cd \"$ROOT/../UniXNU\"",
    "python3 ./unixnu build kernel --device \"$ROOT\" \"$@\"",
    "",
])

FRAMEWORK = chr(10).join([
    "def build(ctx, modules):",
    "    env = dict(os.environ)",
    "    env['ZERO_AR_DATE'] = '1'",
    "    run(['bash', script], cwd=ctx.tree, env=env)",
    "",
])


def tree(root, driver=DRIVER, framework=FRAMEWORK):
    gates = root / "gates"
    (gates / "scripts").mkdir(parents=True, exist_ok=True)
    (gates / "scripts" / "build-ios27-linux.sh").write_text(driver, encoding="utf-8")
    unixnu = root / "UniXNU"
    (unixnu / "scripts" / "unixnu").mkdir(parents=True, exist_ok=True)
    (unixnu / "scripts" / "unixnu" / "kernel.py").write_text(framework, encoding="utf-8")
    return gates, unixnu


def call(gates, unixnu):
    done = subprocess.run([sys.executable, str(CHECKER), "--gates", str(gates), "--unixnu", str(unixnu)],
                          capture_output=True, text=True)
    return done.returncode, done.stdout + done.stderr


WIRED = DRIVER.replace(
    "python3 ./unixnu build kernel",
    "env \"K60_CONF_FILES_HOOK=$ROOT/scripts/k60-conf-files-hook.py\" "
    "\"PongAudioAmp.o_CFLAGS_ADD=-DXNU_PONG_AUDIO=1\" python3 ./unixnu build kernel")


def case_not_wired():
    with tempfile.TemporaryDirectory() as tmp:
        gates, unixnu = tree(pathlib.Path(tmp))
        code, out = call(gates, unixnu)
        assert code == 0, out
        assert "not wired yet" in out, out
        assert "compiles in and never runs" in out, out


def case_wired():
    with tempfile.TemporaryDirectory() as tmp:
        gates, unixnu = tree(pathlib.Path(tmp), driver=WIRED)
        code, out = call(gates, unixnu)
        assert code == 0, out
        assert "BUILDER OK" in out, out
        assert "kernel.py:2" in out, out


def case_hook_missing():
    with tempfile.TemporaryDirectory() as tmp:
        broken = WIRED.replace("\"K60_CONF_FILES_HOOK=$ROOT/scripts/k60-conf-files-hook.py\" ", "")
        gates, unixnu = tree(pathlib.Path(tmp), driver=broken)
        code, out = call(gates, unixnu)
        assert code == 1, out
        assert "without K60_CONF_FILES_HOOK" in out, out


def case_define_exported_by_dash():
    with tempfile.TemporaryDirectory() as tmp:
        broken = WIRED.replace(
            "env \"K60_CONF_FILES_HOOK=$ROOT/scripts/k60-conf-files-hook.py\" "
            "\"PongAudioAmp.o_CFLAGS_ADD=-DXNU_PONG_AUDIO=1\" ",
            "env \"K60_CONF_FILES_HOOK=$ROOT/scripts/k60-conf-files-hook.py\" ")
        broken = broken.replace("cd \"$ROOT/../UniXNU\"",
                                "export PongAudioAmp.o_CFLAGS_ADD=-DXNU_PONG_AUDIO=1" + chr(10) + "cd \"$ROOT/../UniXNU\"")
        gates, unixnu = tree(pathlib.Path(tmp), driver=broken)
        code, out = call(gates, unixnu)
        assert code == 1, out
        assert "without PongAudioAmp.o_CFLAGS_ADD" in out, out


def case_framework_replaces_environment():
    with tempfile.TemporaryDirectory() as tmp:
        narrow = FRAMEWORK.replace("env = dict(os.environ)", "env = {}")
        gates, unixnu = tree(pathlib.Path(tmp), driver=WIRED, framework=narrow)
        code, out = call(gates, unixnu)
        assert code == 1, out
        assert "no longer starts from" in out, out


def case_no_gates():
    with tempfile.TemporaryDirectory() as tmp:
        code, out = call(pathlib.Path(tmp) / "absent", pathlib.Path(tmp) / "UniXNU")
        assert code == 3, out
        assert "no build driver" in out, out


def main():
    cases = [case_not_wired, case_wired, case_hook_missing, case_define_exported_by_dash,
             case_framework_replaces_environment, case_no_gates]
    for case in cases:
        case()
    print("TESTS OK %d cases" % len(cases))


if __name__ == "__main__":
    main()
