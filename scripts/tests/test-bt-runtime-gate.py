#!/usr/bin/env python3
"""Cases for scripts/check-bluetooth-runtime-gate.py."""
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
CHECK = ROOT / "scripts" / "check-bluetooth-runtime-gate.py"

GATE = "#if defined(XNU_OWNER_DATA_MOUNT) && XNU_OWNER_DATA_MOUNT"
SOURCE = f"""static int unrelated(void)
{{
	return 0;
}}

{GATE}
static void
native_bt_runtime_prepare(proc_t p, user_addr_t scratch)
{{
	return;
}}
#endif
"""

SERIES_WITH = "ptrauth-string-discriminator.patch\n0526-k60-bt-runtime-mount.patch\n0527-k60-bt-launchd-cache.patch\n"
SERIES_WITHOUT = "ptrauth-string-discriminator.patch\n0523-k60-bt-transport-set-rate.patch\n"

CASES = []
failures = []


def case(name, ok):
    CASES.append((name, ok))
    if not ok:
        failures.append(name)


def run(defconfig, series, source=SOURCE):
    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)
        tree = base / "tree"
        (tree / "bsd" / "kern").mkdir(parents=True)
        (tree / "bsd" / "kern" / "kern_exec.c").write_text(source)
        (base / "series").write_text(series)
        (base / "defconfig").write_text(defconfig)
        return subprocess.run(
            [
                sys.executable,
                str(CHECK),
                "--series",
                str(base / "series"),
                "--defconfig",
                str(base / "defconfig"),
                "--tree",
                str(tree),
            ],
            capture_output=True,
            text=True,
        )


on = "CONFIG_XNU_BUILD_ARCHIVES=y\nCONFIG_XNU_OWNER_DATA_MOUNT=y\n"
off = "CONFIG_XNU_BUILD_ARCHIVES=y\n# CONFIG_XNU_OWNER_DATA_MOUNT is not set\n"

r = run(off, SERIES_WITH)
case("closed gate with the mounts is the documented stage-0 state", r.returncode == 0)
case("it says the mounts are compiled out", "gated-off" in r.stdout)

r = run(on, SERIES_WITH)
case("open gate with the mounts passes", r.returncode == 0)
case("it reports the active state", "state: active" in r.stdout)

r = run(on, SERIES_WITHOUT)
case("open gate without 0526/0527 fails", r.returncode == 1)
case("the failure names the switch", "CONFIG_XNU_OWNER_DATA_MOUNT=y without" in r.stdout)

r = run(off, SERIES_WITHOUT)
case("closed gate without the mounts passes", r.returncode == 0)

r = run(off, SERIES_WITH, source="static int nothing;\n")
case("a tree without the prepare function fails", r.returncode == 1)
case("the failure names the function", "native_bt_runtime_prepare is missing" in r.stdout)

outside = SOURCE.replace(GATE, "#if 1").replace("#endif", "#endif")
r = run(off, SERIES_WITH, source=outside)
case("a prepare function outside the gate fails", r.returncode == 1)
case("the failure names the gate", "outside the XNU_OWNER_DATA_MOUNT gate" in r.stdout)

r = run("CONFIG_XNU_OWNER_DATA_MOUNT = y\n", SERIES_WITH)
case("spaces around the equals sign are accepted", r.returncode == 0)

commented = "# 0526-k60-bt-runtime-mount.patch\n# 0527-k60-bt-launchd-cache.patch\n"
r = run(on, commented)
case("a commented-out mount line does not count", r.returncode == 1)

for name, ok in CASES:
    print(("PASS " if ok else "FAIL ") + name)
print()
if failures:
    print(f"bluetooth-runtime-gate test: {len(failures)} failure(s)")
    sys.exit(1)
print(f"bluetooth-runtime-gate test: OK ({len(CASES)} case(s))")
