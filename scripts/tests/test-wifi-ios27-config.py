#!/usr/bin/env python3
"""Host checks for the iOS 27 wifi configuration wiring.

The 27 kernel is a stage-0 kernel first and a wifi kernel second: this asserts the
wifi switch lives in its own defconfig while the 27 default stays exactly what the
first 24A446 boot gets, and that build-strict.sh still turns the switch into the
force-load the driver needs.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WIFI27 = ROOT / "configs" / "mondrian_ios27_wifi_defconfig"
STAGE0 = ROOT / "configs" / "mondrian_ios27_defconfig"
WIFI16 = ROOT / "configs" / "mondrian_wifi_defconfig"
BOARD = ROOT / "board.toml"
STRICT = ROOT / "scripts" / "build-strict.sh"

checks = []


def check(name, ok, detail=""):
    checks.append((name, ok, detail))


def read(path):
    # The board files carry Chinese comments; the host locale is gbk on Windows.
    return Path(path).read_text(encoding="utf-8")


text = read(WIFI27)
stage0 = read(STAGE0)
board = read(BOARD)
strict = read(STRICT)

check("the 27 wifi defconfig turns the driver on",
      "CONFIG_XNU_PONG_WIFI=y" in text)
check("it keeps the archive build the driver's defconfig needs",
      "CONFIG_XNU_BUILD_ARCHIVES=y" in text)
check("it does not reopen the stage-0 storage, display or GPU boundary",
      all(line in text for line in ("CONFIG_XNU_NATIVE_UFS=n",
                                    "CONFIG_XNU_NATIVE_ADRENO=n",
                                    "CONFIG_XNU_NATIVE_LEGACY_DISPLAY=n")))
check("it carries every stage-0 switch unchanged",
      all(line in text for line in stage0.splitlines() if line.startswith("CONFIG_")),
      "each CONFIG_ line of mondrian_ios27_defconfig appears in the wifi variant")
check("the 27 profile still builds the stage-0 kernel by default",
      'defconfig = "mondrian_ios27_defconfig"' in board,
      "board.toml [os_overrides.\"ios-27.0.1-24A446\".kernel]")
check("the 16 profile still maps to its own defconfig",
      '"ipados-16.6.1-20G81" = "mondrian_defconfig"' in board)
check("the 27 wifi defconfig is not wired as the 27 default",
      "mondrian_ios27_wifi_defconfig" not in board,
      "an explicit defconfig run, not a board default")
check("the build reads the switch out of the generated .config",
      "grep -q '^CONFIG_XNU_PONG_WIFI=y' \"$M/.config\"" in strict,
      "scripts/build-strict.sh:202")
check("the build hands the archive to the kernel link",
      "export XNU_PONG_WIFI_ARCHIVE=$WIFI_ARCHIVE" in strict)
linker = read(ROOT / "scripts" / "build-xnu-4k-baseline.sh")
check("the kernel link force-loads the wifi archive",
      "force_load,$PONG_WIFI_ARCHIVE" in linker,
      "scripts/build-xnu-4k-baseline.sh:1020")
check("the build refuses to link the switch without an archive",
      "no wifi archive was given" in strict)
check("the 16 wifi defconfig is untouched by this file",
      read(WIFI16).count("CONFIG_XNU_PONG_WIFI=y") == 1)

failed = [c for c in checks if not c[1]]
for name, ok, detail in checks:
    print(("PASS  " if ok else "FAIL  ") + name + (("  [" + detail + "]") if detail and not ok else ""))
print("summary: %d failure(s)" % len(failed))
raise SystemExit(1 if failed else 0)
