#!/usr/bin/env python3
"""Tests for check-bluetooth-launchd.py, on synthetic stager reports."""
import json
import pathlib
import plistlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
CHECK = ROOT / "scripts" / "check-bluetooth-launchd.py"
# The device repository sits next to the framework checkout in both places this
# runs: ../UniXNU locally and $GITHUB_WORKSPACE/UniXNU in CI.
FRAMEWORK = ROOT.parent / "UniXNU"
HAVE_FRAMEWORK = (FRAMEWORK / "scripts" / "build-boot-runtime.py").is_file()

GOOD = {"com.apple.BlueTool": {"UserName": "root", "EnableTransactions": True,
                              "EnablePressuredExit": False, "ThrottleInterval": 3}}
failures = []


def case(name, ok, overrides=None, cache=None, framework=None):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        report = tmp / "report.json"
        report.write_text(json.dumps({"launchd_job_overrides": GOOD if overrides is None else overrides}))
        command = [sys.executable, str(CHECK), "--report", str(report)]
        if cache is not None:
            command += ["--cache", str(cache)]
        if framework is not None:
            command += ["--framework", str(framework)]
        result = subprocess.run(command, capture_output=True, text=True)
        passed = result.returncode == 0
        if passed != ok:
            failures.append(f"{name}: expected {'pass' if ok else 'fail'}, rc={result.returncode}\n{result.stdout}{result.stderr}")
            print(f"FAIL {name}")
        else:
            print(f"PASS {name}")


def write_cache(tmp, jobs):
    cache = pathlib.Path(tmp) / "launchd.plist"
    cache.write_bytes(plistlib.dumps({"LaunchDaemons": jobs}, fmt=plistlib.FMT_BINARY))
    return cache


def bluetool(user="mobile", pressured=True):
    return {"Label": "com.apple.BlueTool", "ProgramArguments": ["/usr/sbin/BlueTool", "-R"],
            "UserName": user, "ThrottleInterval": 0, "POSIXSpawnType": "Adaptive",
            "MachServices": {"com.apple.BlueTool": True}, "EnablePressuredExit": pressured}


def neighbour():
    return {"Label": "com.apple.notifyd", "ProgramArguments": ["/usr/sbin/notifyd"],
            "UserName": "root"}


case("the stager report as written passes", True)
case("no override fails", False, overrides={})
case("a mobile override fails", False, overrides={"com.apple.BlueTool": dict(GOOD["com.apple.BlueTool"], UserName="mobile")})
case("pressured exit left on fails", False, overrides={"com.apple.BlueTool": dict(GOOD["com.apple.BlueTool"], EnablePressuredExit=True)})
case("an unknown field fails", False, overrides={"com.apple.BlueTool": dict(GOOD["com.apple.BlueTool"], KeepAlive=True)})
case("a string throttle interval fails", False, overrides={"com.apple.BlueTool": dict(GOOD["com.apple.BlueTool"], ThrottleInterval="3")})
case("an int for a bool fails", False, overrides={"com.apple.BlueTool": dict(GOOD["com.apple.BlueTool"], EnableTransactions=1)})

with tempfile.TemporaryDirectory() as tmp:
    cache = write_cache(tmp, {"/System/Library/LaunchDaemons/com.apple.BlueTool.plist": bluetool(),
                              "/System/Library/LaunchDaemons/com.apple.notifyd.plist": neighbour()})
    if HAVE_FRAMEWORK:
        case("the merge against a real cache passes", True, cache=cache, framework=FRAMEWORK)
        case("a cache without the job fails", False, cache=write_cache(tmp, {"/System/Library/LaunchDaemons/com.apple.notifyd.plist": neighbour()}), framework=FRAMEWORK)
    else:
        print(f"SKIP the merge cases: no framework at {FRAMEWORK}")
    case("a cache is not merged without a framework", True, cache=cache)

print(f"TESTS {'OK' if not failures else 'FAILED'} ({len(failures)} failure(s))")
sys.exit(1 if failures else 0)
