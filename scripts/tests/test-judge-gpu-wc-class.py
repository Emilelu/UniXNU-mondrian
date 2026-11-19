#!/usr/bin/env python3
"""test-judge-gpu-wc-class.py — 上机卡 o 的判读器必须做对的三件事。

1. **旧日志必须被判成「没有分类字段」**，而不是"维护量很小"。上一飞的
   `PONG VM: publish sample` 行没有 `trusted=`/`ibytes=`，如果判读器把缺失字段当 0，
   就会给出「维护主体是 imported 帧」这种凭空结论——这正是 P-237 的同一形状。
2. **零帧日志判无效**并返回 3（P-236），不是判失败。
3. **S5/S6 先于归因**：三类维护字节超过访问总量、或信任状态不自洽时，
   归因结论必须被拒绝，而不是照算。

用法：python3 scripts/tests/test-judge-gpu-wc-class.py
"""

import importlib.util
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(REPO, "scripts", "judge-gpu-wc-class.py")

FAILED = []


def load():
    spec = importlib.util.spec_from_file_location("judge_gpu_wc_class", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def case(name, condition, detail=""):
    if condition:
        print("ok   %s" % name)
    else:
        print("FAIL %s %s" % (name, detail))
        FAILED.append(name)


VALID_TAIL = """MiniIOMobileFramebuffer: 90 frames in 240000 ms
Pong Metal: c754/0 d700 p14 x4 R6 D0 F0 M18 C0 C0 status=0x0
Pong Metal: scanout frames=1130 at 240.004 s; last frame: wait=100 us copy=16000 us done=49 us; imports=1130 import=37 us encode=1491 us submit=6251 us gpu=8277 us sum=16056 us status=0x0
scanout copy texture untile source=5888 scanout=5760 rows=3200 status=0x0
"""

OLD_SAMPLE = """PONG VM: publish sample n=2688 objects=613 imported=39 owned=0 combined=574 bytes=690958336 us=10107 calls=565 cachebytes=139517952
"""


def sample(n, us, cachebytes, ibytes, obytes, wbytes, wskipped, trusted, bytes_=690958336):
    return ("PONG VM: publish sample n=%d objects=613 imported=39 owned=0 combined=574 "
            "bytes=%d us=%d calls=610 cachebytes=%d trusted=%d ibytes=%d obytes=%d "
            "wbytes=%d wskipped=%d\n" % (n, bytes_, us, cachebytes, trusted, ibytes, obytes,
                                         wbytes, wskipped))


def main():
    judge = load()

    rows = judge.samples(OLD_SAMPLE + VALID_TAIL)
    case("the old log still parses", len(rows) == 1, rows)
    case("a missing per-class field stays None, not zero",
         rows and rows[0]["ibytes"] is None and rows[0]["trusted"] is None, rows)

    ok, reasons = judge.validity(VALID_TAIL)
    case("a presenting run is valid", ok, reasons)
    zero_ok, zero_reasons = judge.validity("Early boot complete\nPong Metal: c0/0 d0 p14\n")
    case("a zero-frame run is invalid", not zero_ok, zero_reasons)
    case("the invalid reason names the missing compositor line",
         any("MiniIOMobileFramebuffer" in r for r in zero_reasons), zero_reasons)

    imported = VALID_TAIL + "".join(
        sample(32 * i, 10100, 141000000, 130000000, 0, 0, 590000000, 0) for i in range(1, 5))
    kind, ib, wb = judge.attribution(judge.samples(imported))
    case("imported-dominant samples attribute to imported", kind == "imported", (kind, ib, wb))

    combined = VALID_TAIL + "".join(
        sample(32 * i, 10300, 141000000, 2000000, 0, 138000000, 0, 0) for i in range(1, 5))
    kind, ib, wb = judge.attribution(judge.samples(combined))
    case("write-combined-dominant samples attribute to write-combined",
         kind == "write-combined", (kind, ib, wb))

    mixed = VALID_TAIL + "".join(
        sample(32 * i, 10200, 141000000, 70000000, 0, 70000000, 0, 0) for i in range(1, 5))
    kind, _, _ = judge.attribution(judge.samples(mixed))
    case("a 50/50 split is reported as mixed, not as a single owner", kind == "mixed", kind)

    trusted_only = VALID_TAIL + "".join(
        sample(32 * i, 2800, 1200000, 900000, 0, 0, 690000000, 1) for i in range(1, 5))
    rows = judge.samples(trusted_only)
    trusted_values = {r["trusted"] for r in rows}
    case("an all-trusted run keeps wbytes at zero",
         trusted_values == {1} and all(r["wbytes"] == 0 for r in rows), trusted_values)

    over = VALID_TAIL + sample(32, 10100, 141000000, 400000000, 0, 400000000, 0, 0)
    rows = judge.samples(over)
    case("S5 rejects samples whose classes exceed the visited total",
         any((r["ibytes"] + r["obytes"] + r["wbytes"]) > r["bytes"] for r in rows), rows)

    code, text = judge.report(imported)
    case("the report refuses to divide cachebytes by the call count",
         "禁止用 cachebytes/n" in text, text[-300:])
    case("a satisfied attribution still returns 0", code == 0, code)

    with tempfile.TemporaryDirectory() as scratch:
        log = os.path.join(scratch, "console.log")
        with open(log, "w", encoding="utf-8") as handle:
            handle.write("Early boot complete\nPong Metal: c0/0 d0 p14\n")
        done = subprocess.run([sys.executable, SCRIPT, log], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", check=False)
        case("a zero-frame log exits 3 (invalid, P-236)", done.returncode == 3, done.returncode)
        missing = subprocess.run([sys.executable, SCRIPT, os.path.join(scratch, "nope.log")],
                                 capture_output=True, text=True, encoding="utf-8",
                                 errors="replace", check=False)
        case("an unreadable log exits 2", missing.returncode == 2, missing.returncode)

    if FAILED:
        print("\nTESTS FAILED %d: %s" % (len(FAILED), ", ".join(FAILED)))
        return 1
    print("\nTESTS OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
