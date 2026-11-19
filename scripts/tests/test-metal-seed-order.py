#!/usr/bin/env python3
"""The metal seed markers must be published only after the bundle and the
client list exist. A process that starts inside the old window saw
.publish == "1" with no .clients and kept a nil Metal device for the whole
boot, which is exactly the intermittent first-frame failure.

Source: drivers/PongMetal/seeds/k60_metal_seeds.c (k60_metal_seeds_deploy).
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE = ROOT / "drivers/PongMetal/seeds/k60_metal_seeds.c"


def deploy_body(text):
    match = re.search(r"k60_metal_seeds_deploy\(void\)\s*\{(.*?)\n\}", text, re.S)
    if not match:
        raise SystemExit("FAIL: k60_metal_seeds_deploy not found")
    return match.group(1)


def positions(body):
    names = ["PongAdrenoMetal.bundle/Info.plist", "PongAdrenoMetal.clients", "PongAdrenoMetal.publish"]
    return [body.index(name) for name in names]


def main():
    body = deploy_body(SOURCE.read_text())
    info, clients, publish = positions(body)
    checks = []
    checks.append(("bundle is written before the client list", info < clients))
    checks.append(("the client list is written before the publish marker", clients < publish))
    checks.append(("the publish marker is written last", publish == max(info, clients, publish)))
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(("PASS " if ok else "FAIL ") + name)
    if failed:
        print("FAIL: the metal seed order still publishes before the bundle is complete")
        return 1
    print("TESTS OK 3 case(s) (0 failure(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
