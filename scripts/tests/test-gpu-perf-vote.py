#!/usr/bin/env python3
"""Assert the runtime GPU level vote (t970 z164) keeps its contract.

Why this test exists: the startup vote asks for one level and never revisits it, so a
boot runs at the device tree's initial-pwrlevel whatever the workload does. t970 added a
second vote once GX is up. A mistake here is expensive in two directions - voting before
the GMU owns GX hangs the boot, and voting without a ceiling turns a firmware problem into
a busyloop - so the boundaries are asserted instead of trusted.

Each case names the property and the line that must carry it; a fixture change that breaks
the contract fails here rather than on the device.
"""
import os
import pathlib
import sys

# The checkout is supplied by the caller (the gate runs every line of this file from the
# tree it is judging); a literal path here would judge a different tree than the one asked.
ROOT = pathlib.Path(os.environ.get("K60_REPO") or pathlib.Path(__file__).resolve().parents[2])
GMU_C = ROOT / "drivers/PongAdreno/PongAdrenoGmu.c"
SCANOUT = ROOT / "drivers/PongMetal/PongMetalScanout.h"
GMU_H = ROOT / "drivers/PongAdreno/PongAdrenoGmu.h"
PLATFORM = ROOT / "drivers/PongAdreno/PongAdrenoPlatform.cpp"

results = []


def case(name):
    def wrap(fn):
        results.append((name, fn))
        return fn
    return wrap


def body(text, signature):
    start = text.find(signature)
    if start < 0:
        return ""
    end = text.find("\n}", start)
    return text[start:end if end > 0 else len(text)]


@case("the vote is declared in the header next to the device it votes on")
def _():
    t = GMU_H.read_text(encoding="utf-8")
    assert "PongAdrenoGmuVotePerf(PongGpuGmuDevice *" in t, "no declaration"
    assert "perf_gpu_index" in t and "perf_bus_index" in t, "the indices are not remembered"


@case("the startup vote records which level and bus it asked for")
def _():
    t = GMU_C.read_text(encoding="utf-8")
    assert "d->perf_gpu_index=" in t, "startup does not record the GPU index"
    assert "d->perf_bus_index=" in t, "startup does not record the bus index"


@case("the runtime vote sends the same HFI message the startup vote sends")
def _():
    b = body(GMU_C.read_text(encoding="utf-8"), "PongGpuStatus PongAdrenoGmuVotePerf")
    assert "PongAdrenoHfiSend(&d->hfi,30,vote,3," in b, "not HFI id 30 with three words"


@case("the payload keeps the bus level startup voted instead of inventing one")
def _():
    b = body(GMU_C.read_text(encoding="utf-8"), "PongGpuStatus PongAdrenoGmuVotePerf")
    assert "{1,gpu_index,d->perf_bus_index}" in b, "the DDR field is not the startup value"


@case("level 0 and level 14 are refused as caller bugs, not sent to firmware")
def _():
    b = body(GMU_C.read_text(encoding="utf-8"), "PongGpuStatus PongAdrenoGmuVotePerf")
    assert "gpu_index<1 || gpu_index>13" in b, "the table bounds are not enforced"
    assert "return PongGpuArgument;" in b


@case("the vote refuses before the GMU owns the GX domain")
def _():
    b = body(GMU_C.read_text(encoding="utf-8"), "PongGpuStatus PongAdrenoGmuVotePerf")
    assert "!d->power_started || !d->gpu_held" in b, "no power/hold prerequisite"
    assert "PongGpuPrerequisite" in b


@case("a poisoned or busy channel is refused instead of queued")
def _():
    b = body(GMU_C.read_text(encoding="utf-8"), "PongGpuStatus PongAdrenoGmuVotePerf")
    assert "d->poisoned || d->hfi.poisoned" in b, "poison is not checked"
    assert "d->hfi.pending_header)return PongGpuBusy" in b, "a pending header is not refused"


@case("the wait for the firmware reply has a ceiling, so a mute GMU is a timeout")
def _():
    b = body(GMU_C.read_text(encoding="utf-8"), "PongGpuStatus PongAdrenoGmuVotePerf")
    assert "1000000" in b and "PongGpuTimeout" in b, "no bounded wait"


@case("the level is only remembered after the firmware accepted the vote")
def _():
    b = body(GMU_C.read_text(encoding="utf-8"), "PongGpuStatus PongAdrenoGmuVotePerf")
    tail = b[b.find("PongAdrenoHfiPoll"):]
    assert "d->perf_gpu_index=gpu_index" in tail, "the index is written before a reply"
    assert "++d->perf_votes" in tail, "the vote count is not kept"


@case("the call site runs after CP start succeeded, so GX is already up")
def _():
    t = PLATFORM.read_text(encoding="utf-8")
    cp = t.find("PongAdrenoCpStart(&gmu)")
    vote = t.find("PongAdrenoGmuVotePerf(&gmu,perf,&vote)")
    assert cp > 0 and vote > cp, "the vote is not after a successful CP start"
    # The gate has to sit between the CP start and the vote, not merely somewhere before
    # it: a window of fixed width silently passed while the comment block grew.
    assert "if(!cp_status)" in t[cp:vote], "the vote is not gated on CP succeeding"
    assert t[cp:vote].count("if(!cp_status)") == 1, "more than one CP gate, which one runs?"


@case("the vote is opt-in: no boot argument means no vote")
def _():
    t = PLATFORM.read_text(encoding="utf-8")
    vote = t.find("PongAdrenoGmuVotePerf(&gmu,perf,&vote)")
    window = t[vote - 400:vote]
    assert 'PE_parse_boot_argn("gperf"' in window, "the boot argument is not read"
    assert "perf>0" in window, "level 0 would be sent as a request"


@case("the vote prints one line naming the argument and the level it settled on")
def _():
    t = PLATFORM.read_text(encoding="utf-8")
    assert 'record("GPU level vote from gperf"' in t, "no verdict line"
    assert "gmu.perf_gpu_index,gmu.perf_bus_index" in t, "the line omits the indices"


@case("asking for a level vote also asks for a measurement of it")
def _():
    t = SCANOUT.read_text(encoding="utf-8")
    assert 'const char perfKey[]="gperf=";' in t, "the plugin does not look at gperf"
    assert "bench=24;" in t, "a static screen would leave the vote unmeasured again"


@case("the bench repeats inside the offer, before the kernel retires the mapping")
def _():
    t = SCANOUT.read_text(encoding="utf-8")
    bench = t.find("scanout bench n=")
    assert bench > 0, "no bench line"
    # The bench must sit in the first-frame block, which runs before PongScanoutComplete:
    # presenting after Complete would read pages the kernel already released (P-244).
    complete = t.find("PongScanoutComplete")
    assert complete == -1 or bench < complete, "the bench runs after the mapping is retired"


@case("the bench line carries the six numbers the judge needs, and a status")
def _():
    t = SCANOUT.read_text(encoding="utf-8")
    for field in ("import=%llu us", "encode=%llu us", "submit=%llu us", "gpu=%llu us",
                  "sum=%llu us", "status=0x%x"):
        assert field in t, "the bench line omits %s" % field


@case("the bench count is capped and stops on the first failed copy")
def _():
    t = SCANOUT.read_text(encoding="utf-8")
    assert "value>120?120:value" in t, "no cap on the count"
    bench = t.find("scanout bench n=")
    tail = t[bench:bench + 1600]
    assert "if(repeat!=gpupresent::kOk)break;" in tail, "a failure does not stop the loop"


def main():
    failures = 0
    for name, fn in results:
        try:
            fn()
        except AssertionError as error:
            failures += 1
            print("FAIL %s: %s" % (name, error))
        else:
            print("ok   %s" % name)
    print("\n%d case(s), %d failure(s)" % (len(results), failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
