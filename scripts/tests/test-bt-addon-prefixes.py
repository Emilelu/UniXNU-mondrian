#!/usr/bin/env python3
"""Cases for scripts/check-bluetooth-addon-prefixes.py."""
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
CHECK = ROOT / "scripts" / "check-bluetooth-addon-prefixes.py"

PATCH = """--- a/bsd/kern/kern_exec.c
+++ b/bsd/kern/kern_exec.c
@@
-	static const char bin_source[] = "/private/var/ngpu/bluetooth-bin";
+	static const char bin_source[] = "/private/var/ngpu/bluetooth-bin";
"""

STAGER = """report['directories'] = {'bluetooth-bin': 'userland/bin', 'bluetooth-lib': 'userland/lib'}
"""

FRAMEWORK = """            script('addon-add-dir.py', addon, candidate, 'xpc', cache.parent)
"""

CASES = []
failures = []


def case(name, ok):
    CASES.append((name, ok))
    if not ok:
        failures.append(name)


def run(patches, stager=STAGER, framework=FRAMEWORK):
    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)
        patch_dir = base / "patches"
        patch_dir.mkdir()
        for name, text in patches.items():
            (patch_dir / name).write_text(text, encoding='utf-8')
        stager_path = base / "stager.py"
        if stager is not None:
            stager_path.write_text(stager, encoding='utf-8')
        framework_path = base / "framework.py"
        if framework is not None:
            framework_path.write_text(framework, encoding='utf-8')
        return subprocess.run(
            [sys.executable, str(CHECK), "--patches", str(patch_dir), "--stager", str(stager_path),
             "--framework", str(framework_path)],
            capture_output=True, text=True,
        )


r = run({"0526.patch": PATCH})
case("staged and mounted prefix passes", r.returncode == 0)

r = run({"0526.patch": "# 中文注释\n" + PATCH})
case("a UTF-8 patch is read on a GBK host", r.returncode == 0)
case("it names the source patch", "0526.patch" in r.stdout)

r = run({"0526.patch": PATCH}, stager="")
case("a prefix nobody packs fails", r.returncode == 1)
case("the failure names the mount", "bluetooth-bin is mounted by 0526.patch" in r.stdout)

XPC_PATCH = PATCH + (
    "\n+\tstatic const char xpc_source[] = \"/private/var/ngpu/xpc\";\n"
)
r = run({"0527.patch": XPC_PATCH}, framework=None)
case("a missing framework is skipped, not failed", r.returncode == 0)
case("the skip is printed", "SKIP" in r.stdout)

r = run({})
case("no mounts at all passes", r.returncode == 0)
case("it says so", "kernel mounts: none" in r.stdout)

r = run({"0526.patch": PATCH}, stager="report['directories'] = {'bluetooth-bin': 'x'}\n")
case("a partly packed set still passes when every mount is covered", r.returncode == 0)

for name, ok in CASES:
    print(("PASS " if ok else "FAIL ") + name)
print()
if failures:
    print(f"bluetooth-addon-prefixes test: {len(failures)} failure(s)")
    sys.exit(1)
print(f"bluetooth-addon-prefixes test: OK ({len(CASES)} case(s))")
