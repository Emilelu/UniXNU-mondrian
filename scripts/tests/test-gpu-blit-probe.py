"""The blit control: same bytes, two destinations, one flight.

The 2026-11-19 telemetry flight proved the frame cost is one full screen copy
(5.3-22.8 ms for a commit that draws nothing) but could not say whether the
destination, the copy implementation or the bandwidth is the slow part. This
control answers that by copying the same bytes into a device buffer and then
into the firmware framebuffer. These cases pin the properties that make its
output readable, and pin the boot-argument gate that had been blind to every
key a driver reads through sysctlbyname("kern.bootargs").
"""

import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PRESENTER = os.path.join(ROOT, "drivers", "PongMetal", "GpuScanoutPresenter.h")
SCANOUT = os.path.join(ROOT, "drivers", "PongMetal", "PongMetalScanout.h")
GATE = os.path.join(ROOT, "scripts", "check-boot-args.py")
DOC = os.path.join(ROOT, "docs", "engineering", "BOOT-ARGS.md")


def read(path):
    return io.open(path, encoding="utf-8").read()


def main():
    presenter = read(PRESENTER)
    scanout = read(SCANOUT)
    gate = read(GATE)
    doc = read(DOC)
    failures = []

    def check(name, ok, why=""):
        if ok:
            print("  ok  %s" % name)
        else:
            print("  FAIL %s%s" % (name, (" -- " + why) if why else ""))
            failures.append(name)

    check("the presenter exposes a control", "bool runBlitProbe(const Frame &frame)" in presenter)
    check("the control runs at most once", "if (probeRan_ || !ready()" in presenter)
    check("the control keeps a device buffer of its own", "newBufferWithLength:scanout_.bytes" in presenter)
    check("it copies into that buffer", "timedCopy(source, probe_, bytes)" in presenter)
    check("it then copies that buffer into the framebuffer", "timedCopy(probe_, target_, bytes)" in presenter)
    check("both copies share one timed helper", presenter.count("timedCopy(") == 3,
          "expected one definition and two calls, found %d" % presenter.count("timedCopy("))
    check("the helper stamps around commit and complete",
          "[commands commit];\n        [commands waitUntilCompleted];" in presenter)
    check("the helper only reports a completed copy",
          "MTLCommandBufferStatusCompleted ? pongscanout::elapsedUs(a, b) : 0" in presenter)

    # Placement: the control must run after a real copy succeeded and before the kernel is
    # told the frame is retired, because PongAdrenoScanout.cpp releases the frame's mapping
    # in PongScanoutComplete. Outside that window the source pages are already unmapped.
    shape = scanout.find("scanout copy %s source=")
    probe = scanout.find("presenter->runBlitProbe(")
    complete = scanout.find("PongScanoutComplete,&done")
    check("the control runs after a successful copy",
          -1 < shape < probe, "shape line at %d, control at %d" % (shape, probe))
    check("the control runs before the mapping is released",
          -1 < probe < complete, "control at %d, complete at %d" % (probe, complete))
    check("the control only runs on a first successful frame",
          "if(!copies && result==gpupresent::kOk)" in scanout)
    check("its line names both destinations and the byte count",
          "src-to-device=%llu us device-to-scanout=%llu us" in scanout)
    check("a control that could not run says so", "scanout blit control could not run" in scanout)

    # `copy` must stay the time of present() alone: the control's own copies happen after the
    # t2 stamp, otherwise the number the previous card measured would silently grow.
    t2 = scanout.find("clock_gettime(CLOCK_MONOTONIC,&t2)")
    check("the copy span is stamped before the control",
          -1 < t2 < probe, "t2 at %d, control at %d" % (t2, probe))

    check("the control defaults on", "bool blitProbe=true;" in scanout)
    check("and can be turned off", '"pong_gpu_blit_probe=0"' in scanout)
    check("the reason it has no =1 form is written down",
          "596 of the 607 bytes" in scanout)

    # The gate gap: sysctlbyname("kern.bootargs") keys were invisible to check-boot-args.py,
    # so a driver could add an argument that no document mentions and the gate stayed green.
    check("the boot-arg gate scans literals a driver matches itself",
          r'\[\s*\]\s*=\s*"([A-Za-z0-9_.-]+)=' in gate)
    found = set(re.findall(r'\[\s*\]\s*=\s*"([A-Za-z0-9_.-]+)=', scanout))
    check("it therefore sees this driver's keys",
          "pong_gpu_scanout" in found and "pong_gpu_blit_probe" in found,
          "found %s" % sorted(found))
    check("the new key is documented", "### `pong_gpu_blit_probe`" in doc)
    check("the documentation states the default", "**未设时**：开" in doc)
    check("and warns that one bad frame is expected",
          "帧路径" in doc and "pong_gpu_blit_probe=0" in doc)

    if failures:
        print("TESTS FAILED: %d" % len(failures))
        return 1
    print("TESTS OK: the blit control separates destination from implementation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
