#!/usr/bin/env python3
"""Static check: K60 WiFi DMA descriptor options must not encode cache mode.

kIOMemoryMapperNone is 0x800 and kIOMapCacheMask is 0xf00 in this SDK. Passing
both maps to cache mode 12, not write-combine. The working Pong platform leaves
the descriptor neutral and marks only the owned wired arena pages VM_WIMG_WCOMB.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLATFORM = ROOT / "drivers/PongWifi/PongWifiPlatform.cpp"


def check(text):
    failures = []

    def need(cond, msg):
        if not cond:
            failures.append(msg)

    buffer_fn = text[text.index("IOBufferMemoryDescriptor *buffer("):text.index("bool allocateArena()")]
    need("kIOMemoryMapperNone" not in buffer_fn.split("inTaskWithOptions", 1)[1].split(";", 1)[0],
         "buffer() options still contain kIOMemoryMapperNone")
    need("getPhysicalSegment(0,&span,kIOMemoryMapperNone)" in buffer_fn,
         "buffer() no longer queries the physical segment with MapperNone")

    arena_fn = text[text.index("bool allocateArena()"):text.index("int smmuRead32(")]
    options = arena_fn.split("inTaskWithOptions", 1)[1].split(";", 1)[0]
    need("kIOMemoryPageable" in options, "arena is not pageable")
    need("kIOMemoryMapperNone" not in options, "arena options still contain kIOMemoryMapperNone")
    need("kIOMapWriteCombineCache" not in options, "arena options still contain kIOMapWriteCombineCache")
    need("prepare()" in arena_fn, "arena is not wired with prepare()")
    need("bzero(arenaVa,ArenaBytes)" in arena_fn, "arena is not zeroed after wiring")

    iso = text[text.index("bool isolation()"):text.index("struct Block")]
    need("clean(arenaVa,ArenaBytes)" in iso, "arena is not cleaned before device use")
    need("pmap_set_cache_attributes" in iso, "arena pages are not marked WCOMB")
    need("VM_WIMG_WCOMB" in iso, "arena pages are not marked VM_WIMG_WCOMB")
    need("pmap_cache_attributes" in iso and "VM_WIMG_MASK" in iso,
         "WCOMB policy is not verified")
    need("ranges[i].physical" in iso and "for(size_t i=1;i<count;i++)" in iso,
         "WCOMB is not applied to arena ranges (MSI page excluded)")
    return failures


def mutant(text, old, new):
    assert old in text, old
    return text.replace(old, new, 1)


def main(path=PLATFORM):
    text = path.read_text()
    failures = check(text)
    if failures:
        for failure in failures:
            print("FAIL:", failure)
        return 1

    # The test must reject the exact regressions it was written for.
    cases = [
        ("arena MapperNone+WC", mutant(text, "kIODirectionInOut)|IOOptionBits(kIOMemoryPageable),bytes", "kIODirectionInOut)|IOOptionBits(kIOMemoryMapperNone)|IOOptionBits(kIOMapWriteCombineCache),bytes")),
        ("missing pageable", mutant(text, "IOOptionBits(kIOMemoryPageable),bytes", "IOOptionBits(0),bytes")),
        ("missing clean", mutant(text, " clean(arenaVa,ArenaBytes);", "")),
        ("missing WC verify", mutant(text, " pmap_set_cache_attributes(ppnum_t((ranges[i].physical+off)>>12),VM_WIMG_WCOMB);", "")),
        ("missing prepare", mutant(text, "  if(arena->prepare()!=kIOReturnSuccess) {", "  if(false) {")),
        ("buffer MapperNone", mutant(text, "IOOptionBits(kIOMemoryPhysicallyContiguous)|IOOptionBits(uncached?kIOMapWriteCombineCache:0)", "IOOptionBits(kIOMemoryPhysicallyContiguous)|IOOptionBits(kIOMemoryMapperNone)|IOOptionBits(uncached?kIOMapWriteCombineCache:0)")),
    ]
    for name, bad in cases:
        if not check(bad):
            print("FAIL: test did not reject", name)
            return 1

    print("PASS: WiFi DMA descriptors are neutral and arena pages are verified WCOMB (%d negative cases)" % len(cases))
    return 0


if __name__ == "__main__":
    sys.exit(main())
