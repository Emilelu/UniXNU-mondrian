#!/usr/bin/env python3
"""Host cases for scripts/check-audio27-builder.py, one per seam verdict.

Every verdict this checker can print is reproduced here, because a claim
without a case is a claim that rots the first time the driver changes shape.
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

WIRED = DRIVER.replace(
    "python3 ./unixnu build kernel",
    "env \"K60_CONF_FILES_HOOK=$ROOT/scripts/k60-conf-files-hook.py\" "
    "\"PongAudioAmp.o_CFLAGS_ADD=-DXNU_PONG_AUDIO=1\" python3 ./unixnu build kernel")


def tree(root, driver=DRIVER, framework=FRAMEWORK, unixnu=True):
    gates = root / "gates"
    (gates / "scripts").mkdir(parents=True, exist_ok=True)
    (gates / "scripts" / "build-ios27-linux.sh").write_text(driver, encoding="utf-8")
    framework_root = root / "UniXNU"
    if unixnu:
        (framework_root / "scripts" / "unixnu").mkdir(parents=True, exist_ok=True)
        (framework_root / "scripts" / "unixnu" / "kernel.py").write_text(framework, encoding="utf-8")
    return gates, framework_root


def call(gates, framework_root, seam):
    done = subprocess.run([sys.executable, str(CHECKER), "--gates", str(gates),
                           "--unixnu", str(framework_root), "--seam", seam],
                          capture_output=True, text=True)
    return done.returncode, (done.stdout + done.stderr).strip()


def case_not_wired():
    with tempfile.TemporaryDirectory() as tmp:
        gates, framework_root = tree(pathlib.Path(tmp))
        code, out = call(gates, framework_root, "hook")
        assert code == 0 and "not wired yet" in out and "never names" in out, out
        code, out = call(gates, framework_root, "define")
        assert code == 0 and "compiles to nothing" in out, out
        code, out = call(gates, framework_root, "framework")
        assert code == 0 and "hands dict(os.environ)" in out, out


def case_wired():
    with tempfile.TemporaryDirectory() as tmp:
        gates, framework_root = tree(pathlib.Path(tmp), driver=WIRED)
        for seam, needle in ((("hook"), "takes K60_CONF_FILES_HOOK"),
                             (("define"), "in the env prefix"),
                             (("framework"), "kernel.py:2")):
            code, out = call(gates, framework_root, seam)
            assert code == 0 and "BUILDER OK" in out and needle in out, (seam, out)


def case_hook_dropped():
    with tempfile.TemporaryDirectory() as tmp:
        broken = WIRED.replace("\"K60_CONF_FILES_HOOK=$ROOT/scripts/k60-conf-files-hook.py\" ", "")
        gates, framework_root = tree(pathlib.Path(tmp), driver=broken)
        code, out = call(gates, framework_root, "hook")
        assert code == 0, out  # the driver stopped naming it at all: waiting, not failing
        comment = WIRED.replace("python3 ./unixnu build kernel",
                                "# K60_CONF_FILES_HOOK is wired below" + chr(10) + "python3 ./unixnu build kernel")
        gates, framework_root = tree(pathlib.Path(tmp) / "again", driver=comment)
        code, out = call(gates, framework_root, "hook")
        assert code == 1, out
        assert "elsewhere" in out, out


def case_define_exported_by_dash():
    with tempfile.TemporaryDirectory() as tmp:
        broken = WIRED.replace(
            "env \"K60_CONF_FILES_HOOK=$ROOT/scripts/k60-conf-files-hook.py\" "
            "\"PongAudioAmp.o_CFLAGS_ADD=-DXNU_PONG_AUDIO=1\" ",
            "env \"K60_CONF_FILES_HOOK=$ROOT/scripts/k60-conf-files-hook.py\" ")
        broken = broken.replace("cd \"$ROOT/../UniXNU\"",
                                "export PongAudioAmp.o_CFLAGS_ADD=-DXNU_PONG_AUDIO=1" + chr(10) + "cd \"$ROOT/../UniXNU\"")
        gates, framework_root = tree(pathlib.Path(tmp), driver=broken)
        code, out = call(gates, framework_root, "define")
        assert code == 1, out
        assert "dash" in out, out


def case_framework_replaces_environment():
    with tempfile.TemporaryDirectory() as tmp:
        narrow = FRAMEWORK.replace("env = dict(os.environ)", "env = {}")
        gates, framework_root = tree(pathlib.Path(tmp), driver=WIRED, framework=narrow)
        code, out = call(gates, framework_root, "framework")
        assert code == 1 and "no longer starts from" in out, out


def case_framework_absent():
    with tempfile.TemporaryDirectory() as tmp:
        gates, framework_root = tree(pathlib.Path(tmp), driver=WIRED, unixnu=False)
        code, out = call(gates, framework_root, "framework")
        assert code == 3 and "no framework checkout" in out, out


def case_no_gates():
    with tempfile.TemporaryDirectory() as tmp:
        for seam in ("hook", "define"):
            code, out = call(pathlib.Path(tmp) / "absent", pathlib.Path(tmp) / "UniXNU", seam)
            assert code == 3 and "no build driver" in out, (seam, out)


def main():
    cases = [case_not_wired, case_wired, case_hook_dropped, case_define_exported_by_dash,
             case_framework_replaces_environment, case_framework_absent, case_no_gates]
    for case in cases:
        case()
    print("TESTS OK %d cases" % len(cases))


if __name__ == "__main__":
    main()
