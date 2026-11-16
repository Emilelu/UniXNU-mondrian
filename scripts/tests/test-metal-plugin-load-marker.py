#!/usr/bin/env python3
"""Guard the load-time marker that proves the Metal plugin was inserted.

`MTLCreateSystemDefaultDevice()` answering nil left two indistinguishable cases:
the bundle was never loaded, or it loaded but no Metal entry point ran. This
wrapper's constructor prints the one line that separates them, so it must stay
present, must call the same report() helper, and must be compiled into the
bundle by the build script.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "drivers/PongMetal/PongMetalPlugin.mm"
BUILD = ROOT / "scripts/build-pong-metal-plugin.py"

MARKER = 'report("plugin loaded",0)'
CASES = []


def check(name, condition, detail=""):
    CASES.append((name, bool(condition), detail))


def main():
    source = PLUGIN.read_text(encoding="utf-8", errors="replace")
    build = BUILD.read_text(encoding="utf-8", errors="replace")

    check("the constructor exists",
          re.search(r"__attribute__\(\(constructor\)\)\s+static\s+void\s+\w+\(void\)", source) is not None)
    check("the constructor reports the load marker", MARKER in source)
    check("the marker uses the shared report helper",
          "static void report(const char *phase,int status)" in source)
    check("the marker carries no status code", 'report("plugin loaded",0)' in source)
    check("the plugin is compiled by the build script",
          "drivers/PongMetal/PongMetalPlugin.mm" in build)
    check("the build keeps the rpath that resolves the bridge",
          "-Wl,-rpath,@loader_path" in build)

    failed = [name for name, ok, _ in CASES if not ok]
    for name, ok, detail in CASES:
        print(("ok   " if ok else "FAIL ") + name + ((" - " + detail) if detail and not ok else ""))
    print(f"TESTS {'OK' if not failed else 'FAILED'} {len(CASES) - len(failed)}/{len(CASES)} case(s)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
