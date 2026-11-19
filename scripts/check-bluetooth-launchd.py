#!/usr/bin/env python3
"""Check the launchd cache the Bluetooth runtime ships.

BlueTool runs from a launchd job whose stock definition is UserName=mobile. The
kernel side of the fix is 0527, which mounts a rewritten
/System/Library/xpc/launchd.plist; the content of that file is produced by the
framework's merge_launchd_cache() from the overrides the userspace stager
reports. Three things can go wrong, and none of them is visible in a build:

  * the override names a job the OS cache does not have;
  * the merged job is not root, so xpcproxy keeps dropping the power request;
  * the merge damages a neighbouring job.

With --cache the checker re-runs the merge on the real cache and compares. It
needs the framework checkout for that; without it, the overrides are checked
structurally and the cache is reported as unchecked.

Usage:
    python3 scripts/check-bluetooth-launchd.py --report stage/report.json
    python3 scripts/check-bluetooth-launchd.py --report stage/report.json \
        --cache /path/to/System/Library/xpc/launchd.plist --framework ../UniXNU
"""
import argparse
import importlib.util
import json
import pathlib
import plistlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
LABEL = "com.apple.BlueTool"
FIELDS = {"UserName": str, "EnableTransactions": bool, "EnablePressuredExit": bool,
          "ThrottleInterval": int}


def load_framework(path):
    module_path = pathlib.Path(path) / "scripts" / "build-boot-runtime.py"
    if not module_path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("unixnu_build_boot_runtime", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def structural(overrides, failures):
    if LABEL not in overrides:
        failures.append(f"{LABEL} has no override; it would keep running as mobile")
        return
    changes = overrides[LABEL]
    if changes.get("UserName") != "root":
        failures.append(f"{LABEL} UserName is {changes.get('UserName')!r}, not 'root'")
    if changes.get("EnablePressuredExit") is not False:
        failures.append(f"{LABEL} EnablePressuredExit is not false; the job may be reaped early")
    for label, change in overrides.items():
        if not isinstance(change, dict) or not change:
            failures.append(f"{label} override is empty or not a mapping")
            continue
        for key, value in change.items():
            if key not in FIELDS:
                failures.append(f"{label}: unsupported override field {key}")
            elif type(value) is not FIELDS[key]:
                failures.append(f"{label}: {key} has type {type(value).__name__}")


def merge_check(framework, cache, overrides, failures):
    before = plistlib.loads(cache.read_bytes())
    jobs = before["LaunchDaemons"]
    labels = {}
    for key, job in jobs.items():
        labels.setdefault(job.get("Label"), []).append(key)
    for label in overrides:
        found = labels.get(label, [])
        if len(found) != 1:
            failures.append(f"{label} appears {len(found)} times in the OS cache, expected once")
    if failures:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        empty = pathlib.Path(tmp) / "daemons"
        empty.mkdir()
        destination = pathlib.Path(tmp) / "launchd.plist"
        report = framework.merge_launchd_cache(cache, empty, destination, None, overrides)
        after = plistlib.loads(destination.read_bytes())
    for label, change in overrides.items():
        key = labels[label][0]
        merged = after["LaunchDaemons"][key]
        for field, value in change.items():
            if merged.get(field) != value:
                failures.append(f"{label}: {field} is {merged.get(field)!r} after the merge")
        for field in ("Label", "ProgramArguments", "MachServices"):
            if merged.get(field) != jobs[key].get(field):
                failures.append(f"{label}: the merge changed {field}")
    changed = [key for key in jobs if after["LaunchDaemons"].get(key) != jobs[key]]
    expected = {labels[label][0] for label in overrides}
    for key in changed:
        if key not in expected:
            failures.append(f"the merge changed an unrelated job: {key}")
    return report, len(jobs), len(changed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, help="the userspace stager's report.json")
    parser.add_argument("--cache", help="the OS launchd.plist to merge against")
    parser.add_argument("--framework", help="a UniXNU checkout, for the real merge")
    parser.add_argument("--out")
    args = parser.parse_args()

    failures = []
    report = json.loads(pathlib.Path(args.report).read_text())
    overrides = report.get("launchd_job_overrides") or {}
    print(f"overrides: {', '.join(sorted(overrides)) or 'none'}")
    structural(overrides, failures)

    merged = None
    if args.cache:
        framework = load_framework(args.framework) if args.framework else None
        if framework is None:
            print("cache: not checked (no framework checkout given)")
        else:
            merged = merge_check(framework, pathlib.Path(args.cache), overrides, failures)
            if merged:
                info, total, changed = merged
                print(f"cache: {total} jobs, {len(info['added_jobs'])} added, {changed} changed")

    for label, change in sorted(overrides.items()):
        if not failures:
            print(f"PASS {label}: {', '.join(f'{k}={v!r}' for k, v in change.items())}")

    if args.out:
        out = pathlib.Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.json").write_text(json.dumps({
            "overrides": overrides,
            "cache_checked": merged is not None,
            "failures": failures,
            "hardware_verified": False,
        }, indent=2) + "\n")
        print(f"report: {out / 'report.json'}")

    if failures:
        for failure in failures:
            print(f"FAIL {failure}")
        print("bluetooth-launchd: FAILED")
        return 1
    print("bluetooth-launchd: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
