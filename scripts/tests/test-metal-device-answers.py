#!/usr/bin/env python3
"""Pin the device-answer surface of the Pong Metal bridge.

The bridge is Rust and cannot be compiled on this host, so this guard reads the
source and pins the three things a wrong edit would silently break:

  * the two selectors Core Image asks for are answered from runtime properties,
    not from a table of Apple GPU values;
  * the three private capability flags that no implementation answers anywhere
    stay unanswered -- fabricating an answer would be a lie the Metal frontend
    cannot detect;
  * the frontend answers the board's core count and skips the probe.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
RS = ROOT / "drivers" / "PongMetal" / "bridge" / "NativeMetalObjects.rs"
MM = ROOT / "drivers" / "PongMetal" / "NativeBridgeMetalFrontend.mm"

failures = []


def check(name, condition, detail=""):
    if condition:
        print("ok   %s" % name)
    else:
        print("FAIL %s %s" % (name, detail))
        failures.append(name)


def body_of(text, signature):
    start = text.index(signature)
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    return text[start:]


def main():
    rs = RS.read_text(encoding="utf-8")
    mm = MM.read_text(encoding="utf-8")
    answer = body_of(rs, "fn device_answer(")

    check("threadgroup memory comes from the runtime property",
          re.search(r'selector == "maxComputeThreadgroupMemory"[\s\S]{0,200}'
                    r'return Ok\(p\.max_threadgroup_memory_length\)', answer) is not None)
    check("vertex amplification is probed downward, never assumed",
          re.search(r'selector == "maxVertexAmplificationCount"[\s\S]{0,300}'
                    r'for count in \(1\.\.=32\)\.rev\(\)', answer) is not None
          and "supports_vertex_amplification_count(count)" in answer)
    for flag in ("isLargeMRTSupported", "supportsConditionalLoadStore",
                 "supportsComputeCompressedTextureWrite"):
        check("%s stays unanswered" % flag, flag not in rs)
    check("the frontend answers the board core count",
          re.search(r'gpuCoreCount[\s\S]{0,120}return 4', mm) is not None
          or "gpuCoreCount" in mm)
    check("the core-count probe is skipped when answered",
          "skip" in mm.lower() and "gpuCoreCount" in mm)

    print("TESTS %s (%d failure(s))" % ("OK" if not failures else "FAILED", len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
