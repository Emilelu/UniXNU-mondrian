#!/usr/bin/env python3
"""Host cases for scripts/check-audio27-builder.py, one per seam verdict.

Every verdict this checker can print is reproduced here, because a claim
without a case is a claim that rots the first time the driver changes shape.
"""

import json
import os
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


def tree(root, driver=DRIVER, framework=FRAMEWORK, unixnu=True, hook=True):
    gates = root / "gates"
    (gates / "scripts").mkdir(parents=True, exist_ok=True)
    (gates / "scripts" / "build-ios27-linux.sh").write_text(driver, encoding="utf-8")
    if hook:
        (gates / "scripts" / "k60-conf-files-hook.py").write_text(
            "# fixture: the target exists in the driver checkout\n", encoding="utf-8")
    framework_root = root / "UniXNU"
    if unixnu:
        (framework_root / "scripts" / "unixnu").mkdir(parents=True, exist_ok=True)
        (framework_root / "scripts" / "unixnu" / "kernel.py").write_text(framework, encoding="utf-8")
    return gates, framework_root


def call(gates, framework_root, seam, object_path=None):
    command = [sys.executable, str(CHECKER), "--tree", str(gates),
               "--unixnu", str(framework_root), "--seam", seam]
    if object_path is not None:
        command += ["--object", str(object_path)]
    done = subprocess.run(command, capture_output=True, text=True)
    return done.returncode, (done.stdout + done.stderr).strip()


def case_not_wired():
    with tempfile.TemporaryDirectory() as tmp:
        gates, framework_root = tree(pathlib.Path(tmp))
        code, out = call(gates, framework_root, "hook")
        assert code == 3 and "not wired yet" in out and "never names" in out, out
        code, out = call(gates, framework_root, "define")
        assert code == 3 and "compiles to nothing" in out, out
        code, out = call(gates, framework_root, "framework")
        assert code == 0 and "hands dict(os.environ)" in out, out


def case_wired():
    with tempfile.TemporaryDirectory() as tmp:
        gates, framework_root = tree(pathlib.Path(tmp), driver=WIRED)
        record = gates / "PongAudioAmp.o.json"
        record.write_text(json.dumps({"arguments": ["-D", "XNU_PONG_AUDIO=1"]}) + ",\n",
                          encoding="utf-8")
        for seam, needle in ((("hook"), "takes K60_CONF_FILES_HOOK"),
                             (("define"), "object record"),
                             (("framework"), "kernel.py:2")):
            code, out = call(gates, framework_root, seam, record)
            assert code == 0 and "BUILDER OK" in out and needle in out, (seam, out)


def case_hook_dropped():
    with tempfile.TemporaryDirectory() as tmp:
        broken = WIRED.replace("\"K60_CONF_FILES_HOOK=$ROOT/scripts/k60-conf-files-hook.py\" ", "")
        gates, framework_root = tree(pathlib.Path(tmp), driver=broken)
        code, out = call(gates, framework_root, "hook")
        assert code == 3, out  # the driver stopped naming it at all: waiting, not passing
        comment = WIRED.replace("python3 ./unixnu build kernel",
                                "# K60_CONF_FILES_HOOK is wired below" + chr(10) + "python3 ./unixnu build kernel")
        gates, framework_root = tree(pathlib.Path(tmp) / "again", driver=comment)
        code, out = call(gates, framework_root, "hook")
        assert code == 1, out
        assert "elsewhere" in out, out

        noted = DRIVER.replace(
            "python3 ./unixnu build kernel",
            "# K60_CONF_FILES_HOOK=$ROOT/scripts/k60-conf-files-hook.py is wired below" + chr(10) +
            "python3 ./unixnu build kernel")
        gates, framework_root = tree(pathlib.Path(tmp) / "noted", driver=noted)
        code, out = call(gates, framework_root, "hook")
        assert code == 1, out
        assert "only in a comment" in out, out


def case_hook_target_missing():
    """The driver names the hook, but the checkout it runs from has no such file."""
    with tempfile.TemporaryDirectory() as tmp:
        gates, framework_root = tree(pathlib.Path(tmp), driver=WIRED, hook=False)
        code, out = call(gates, framework_root, "hook")
        assert code == 3, out
        assert "hook not present -> seam inert" in out, out
        assert "BUILDER OK" not in out, out


def case_tree_environment():
    """K60_REPO selects the measured checkout; an explicit --tree overrides it."""
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        absent, framework_root = tree(root / "absent", driver=WIRED, hook=False)
        present, _ = tree(root / "present", driver=WIRED)
        environment = dict(os.environ, K60_REPO=str(absent), K60_GATES=str(present))
        command = [sys.executable, str(CHECKER), "--unixnu", str(framework_root), "--seam", "hook"]
        default = subprocess.run(command, env=environment, capture_output=True, text=True)
        assert default.returncode == 3, default.stdout + default.stderr
        assert "hook not present -> seam inert" in default.stdout, default.stdout
        assert str(absent) in default.stdout, default.stdout
        explicit = subprocess.run(command + ["--tree", str(present)], env=environment,
                                  capture_output=True, text=True)
        assert explicit.returncode == 0 and "BUILDER OK" in explicit.stdout, explicit.stdout


def case_hook_exported_split():
    """The 27 driver assigns the path, then exports the name on its own line."""
    with tempfile.TemporaryDirectory() as tmp:
        split = DRIVER.replace(
            "python3 ./unixnu build kernel",
            'if [ -f "$ROOT/scripts/k60-conf-files-hook.py" ]; then' + chr(10) +
            "\tK60_CONF_FILES_HOOK=\"$ROOT/scripts/k60-conf-files-hook.py\"" + chr(10) +
            "\texport K60_CONF_FILES_HOOK" + chr(10) +
            "fi" + chr(10) +
            "python3 ./unixnu build kernel")
        gates, framework_root = tree(pathlib.Path(tmp), driver=split)
        code, out = call(gates, framework_root, "hook")
        assert code == 0, out
        assert "through the environment" in out, out

        unset = split.replace("fi" + chr(10), "fi" + chr(10) + "unset K60_CONF_FILES_HOOK" + chr(10))
        gates, framework_root = tree(pathlib.Path(tmp) / "unset", driver=unset)
        code, out = call(gates, framework_root, "hook")
        assert code == 1, out

        # One exported assignment followed by an unset is the same cancellation.
        single = DRIVER.replace(
            "python3 ./unixnu build kernel",
            'export K60_CONF_FILES_HOOK="$ROOT/scripts/k60-conf-files-hook.py"' + chr(10) +
            "unset K60_CONF_FILES_HOOK" + chr(10) +
            "python3 ./unixnu build kernel")
        gates, framework_root = tree(pathlib.Path(tmp) / "single-unset", driver=single)
        code, out = call(gates, framework_root, "hook")
        assert code == 1, out

        # An export after the kernel command reaches nothing.
        after = DRIVER.replace(
            "python3 ./unixnu build kernel",
            "python3 ./unixnu build kernel" + chr(10) +
            'export K60_CONF_FILES_HOOK="$ROOT/scripts/k60-conf-files-hook.py"')
        gates, framework_root = tree(pathlib.Path(tmp) / "after", driver=after)
        code, out = call(gates, framework_root, "hook")
        assert code == 1, out


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


def case_define_text_only():
    """The old green: the driver names the define, but no object was measured."""
    with tempfile.TemporaryDirectory() as tmp:
        gates, framework_root = tree(pathlib.Path(tmp), driver=WIRED)
        code, out = call(gates, framework_root, "define")
        assert code == 3, out
        assert "text alone is not evidence" in out, out
        assert "BUILDER OK" not in out, out


def case_define_object_missing():
    """A selected record path that does not exist is a failure, not a skip."""
    with tempfile.TemporaryDirectory() as tmp:
        gates, framework_root = tree(pathlib.Path(tmp), driver=WIRED)
        code, out = call(gates, framework_root, "define", gates / "missing.o.json")
        assert code == 1, out
        assert "define 没到编译器，胶水编成空壳" in out, out
        assert "not a file or directory" in out, out
        assert "BUILDER OK" not in out, out


def case_define_object_without_macro():
    """The record exists but the macro is absent: the glue is an empty shell."""
    with tempfile.TemporaryDirectory() as tmp:
        gates, framework_root = tree(pathlib.Path(tmp), driver=WIRED)
        record = gates / "PongAudioAmp.o.json"
        record.write_text(json.dumps({"arguments": ["-D", "SOMETHING_ELSE=1"]}) + ",\n",
                          encoding="utf-8")
        code, out = call(gates, framework_root, "define", record)
        assert code == 1, out
        assert "define 没到编译器，胶水编成空壳" in out, out
        assert "no -DXNU_PONG_AUDIO=1" in out, out
        assert "BUILDER OK" not in out, out


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
    cases = [case_not_wired, case_wired, case_hook_target_missing, case_hook_dropped,
             case_hook_exported_split, case_tree_environment,
             case_define_exported_by_dash, case_define_text_only,
             case_define_object_missing, case_define_object_without_macro,
             case_framework_replaces_environment, case_framework_absent, case_no_gates]
    for case in cases:
        case()
    print("TESTS OK %d cases" % len(cases))


if __name__ == "__main__":
    main()
