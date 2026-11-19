#!/usr/bin/env python3
"""The coherence flag must be assigned before the client can submit, and the skip it enables must be
observable in a flight.

Why this test exists: NativeAdrenoVm::publishMapped() and acquireImported() have always contained
`if (coherentMapping(...) || importedUntouched(...)) continue;`, and NativeAdrenoUserClient.cpp has a
third copy of the same predicate. All three need `native_adreno_io_coherent` to be nonzero, and for a
long time nothing in the tree ever assigned it, so all three were dead code: every submission cleaned
and invalidated ~93 MiB of imported frames, which is the 6.6-10.1 ms measured inside
[MTLCommandBuffer commit] by flights usblog-20261118-201603 and -233946.

A structural test cannot prove the hardware is coherent -- only the probe's two DRAM directions can --
so this test proves the weaker but regression-prone part: that the probe runs, that its result reaches
the flag before publication, that the operator can force or disable it, and that a flight can see both
the flag and the number of mappings the flag made the VM skip. Losing any of those turns a measurable
optimisation back into an invisible constant.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
GLUE = ROOT / "drivers/PongAdreno/PongAdrenoNativeGlue.cpp"
VM = ROOT / "drivers/PongAdreno/submit/NativeAdrenoVm.cpp"
CLIENT = ROOT / "drivers/PongAdreno/submit/NativeAdrenoUserClient.cpp"

failures = []


def check(name, condition, detail=""):
    if condition:
        print(f"  ok   {name}")
    else:
        failures.append(f"{name}{': ' + detail if detail else ''}")
        print(f"  FAIL {name}{': ' + detail if detail else ''}")


def read(path):
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


glue = read(GLUE)
vm = read(VM)
client = read(CLIENT)

print("the probe is present and puts the result in the flag")
check("glue file exists", bool(glue), str(GLUE))
check("the probe function exists", "bool coherenceProbe(" in glue)
check("it is called with the boot-arg default of 2 (probe)",
      re.search(r"unsigned\s+coherent\s*=\s*2\s*;", glue) is not None,
      "the default must be 2, not 1: forcing coherence without a proof is how frames corrupt silently")
check("the boot argument is named pong_gpu_coherent",
      'PE_parse_boot_argn("pong_gpu_coherent"' in glue)
check("a failed probe leaves the flag off",
      re.search(r"native_adreno_io_coherent\s*=\s*coherenceProbe\([^;]*\)\s*\?\s*1\s*:\s*0\s*;", glue) is not None)
check("forcing is possible (pong_gpu_coherent=1)",
      re.search(r"native_adreno_io_coherent\s*=\s*coherent\s*==\s*1\s*;", glue) is not None)
check("the flight line names the flag and the probe row",
      'IO coherence %s (pong_gpu_coherent=%u, probe %s)' in glue)

print("the assignment precedes publication")
assign_at = glue.find("native_adreno_io_coherent=")
publish_at = glue.find("native_adreno_publish(device->vm")
check("both sites are in the file", assign_at >= 0 and publish_at >= 0)
check("the flag is set before native_adreno_publish()",
      assign_at >= 0 and publish_at >= 0 and assign_at < publish_at,
      "a client that submits before the flag is set takes the maintenance path it was meant to skip")

print("both probe directions are actually proved, not assumed")
check("the read direction copies a page the CPU dirtied", "gpuCopyPage(device,iova,iova+4096)" in glue)
check("the read direction requires the new values to survive", "k[2]==1024" in glue)
check("the write direction shows the GPU's values through cached loads", "k[4]==1024" in glue)
check("the write direction also checks DRAM", "k[5]==1024" in glue)
check("dirtiness is measured through an uncached mapping", "ml_io_map_unmappable" in glue and "0x7 /* VM_WIMG_IO */" in glue)
check("the probe retries until the lines really are dirty", re.search(r"attempt<8", glue) is not None)
check("no stale line outlives the free", "NativeAdrenoMaintainOwnedPages(buf,kBytes,NativeAdrenoCleanInvalidate)" in glue)

print("the skip it enables is real, and the flight can see it")
check("publishMapped still skips imported maps", vm.count("importedUntouched(m.memory)") >= 2,
      "both publishMapped() and acquireImported() must keep the predicate")
check("the user client still skips imported read-only maps", "native_adreno_io_coherent" in client)
check("the VM defines the flag and its skip counters",
      "volatile uint32_t native_adreno_io_coherent" in vm
      and "native_adreno_coherent_skips[4]" in vm)
check("the sample line prints the flag", "coherent=%u" in vm)
check("the sample line prints how many mappings were skipped", "skipped=%llu" in vm)
check("the skipped count is the publishMapped slot",
      "native_adreno_coherent_skips[2]" in vm,
      "slot 2 is publishMapped; slot 3 is acquireImported and would not match this line's cost")
check("the sampler also reports the first submissions",
      re.search(r"sample\s*=\s*\(\+\+calls\s*<=\s*4\s*\|\|", vm) is not None,
      "an idle flight can submit only a handful of times; a every-32nd cadence then reports nothing, "
      "which reads as 'no cost' instead of 'not measured' (P-233)")

print("the probe is not gated behind a build flag that is off")
defconfig = ROOT / "configs/mondrian_defconfig"
text = read(defconfig)
# libPongAdrenoPlatform.a is linked by PONG_ADRENO_PLATFORM, not by XNU_NATIVE_ADRENO
# (build-xnu-4k-baseline.sh:1216/1240/1323); CONFIG_XNU_NATIVE_ADRENO=n is the unrelated upstream archive.
check("the adreno platform archive is configured in", "CONFIG_XNU_PONG_ADRENO_PLATFORM=y" in text)
check("the glue file is compiled into that archive", "PongAdrenoNativeGlue" in read(ROOT / "scripts/build-pong-adreno-platform-linux.py"))

if failures:
    print(f"\nTESTS FAILED ({len(failures)})")
    for failure in failures:
        print(f"  - {failure}")
    sys.exit(1)
print("\nTESTS OK: the coherence probe runs before publication and the skip it enables is observable")
