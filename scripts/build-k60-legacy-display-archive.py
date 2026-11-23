#!/usr/bin/env python3
"""Produce build/native-legacy-display/libNativeLegacyDisplay.late.a for the tree.

Called by board.toml [kernel].archives as `build-k60-legacy-display-archive.py --tree .`:

  1. stage the GopFramebuffer component under drivers/ if it is missing;
  2. generate OriginalLegacyFramebufferABI.h with the 24A446 fixture;
  3. compile the component with the Linux recipe (scripts/build-k60-driver.sh);
  4. copy the archive to the .late.a name the kernel builder force-loads;
  5. write build-report.json (archive_sha256 + source_sha256).
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

STAGE0_TRACE_STUBS = """/* Stage-0 links the display component without the GPU addon. */
typedef unsigned int u32;
typedef unsigned long long u64;
__attribute__((weak)) int native_gpu_trace_enabled(void) { return 0; }
__attribute__((weak)) void native_gpu_trace_record(u32 e, u32 p, const u64 *v, u32 c)
{ (void)e; (void)p; (void)v; (void)c; }
__attribute__((weak)) u32 native_gpu_trace_snapshot(void *o, u32 b)
{ (void)o; (void)b; return 0; }
__attribute__((weak)) int native_adreno_fences(u32 *s, u32 *r)
{ (void)s; (void)r; return 0; }
__attribute__((weak)) int native_adreno_fences_detail(u32 *a, u32 *b, u32 *c)
{ (void)a; (void)b; (void)c; return 0; }
"""

REFERENCE = Path("/mnt/e/k60-work/references/GopFramebuffer")
FILES = ("NativeLegacyDisplay.cpp", "NativeGOPresenter.cpp", "NativeLegacyRequest.h",
         "NativeGOPWire.h", "NativeHalfCodes.h", "NativeGpuTrace.h")


def run(cmd, **kw):
    print("+", " ".join(str(c) for c in cmd))
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", default=".")
    tree = Path(ap.parse_args().tree).resolve()
    scripts = tree / "scripts"
    out = tree / "build/native-legacy-display"
    out.mkdir(parents=True, exist_ok=True)

    component = tree / "drivers/GopFramebuffer"
    if not component.is_dir():
        if not REFERENCE.is_dir():
            raise SystemExit(f"GopFramebuffer component missing and no reference at {REFERENCE}")
        shutil.copytree(REFERENCE, component)

    env = {"UNIXNU_XNU_ARCH": "arm64e", "UNIXNU_IOS_VERSION": "27.0",
           "PYTHONPATH": str(scripts)}
    run([sys.executable, scripts / "gen-legacy-display-abi.py"], env={**__import__("os").environ, **env})
    run([scripts / "build-k60-driver.sh", tree, "NativeLegacyDisplay"],
        env={**__import__("os").environ, **env})

    archive = out / "libNativeLegacyDisplay.a"
    if not archive.is_file():
        raise SystemExit("the driver build produced no archive")

    abi = scripts.parent / "kits/mondrian/display-abi"
    extra = []
    for name in ("original-bindings", "original-addresses"):
        source = abi / (name + ".S")
        if source.is_file():
            obj = out / (name + ".o")
            run(["clang", "-target", "arm64e-apple-ios27.0", "-c", str(source), "-o", str(obj)])
            extra.append(obj)
    stub = out / "display-no-gpu-trace.c"
    stub.write_text(STAGE0_TRACE_STUBS, encoding="utf-8")
    obj = out / "display-no-gpu-trace.o"
    run(["clang", "-target", "arm64e-apple-ios27.0", "-c", str(stub), "-o", str(obj)])
    extra.append(obj)
    if extra:
        run(["llvm-ar", "rcs", str(archive), *[str(o) for o in sorted(out.glob("*.o"))]])
    shutil.copyfile(archive, out / "libNativeLegacyDisplay.late.a")
    run([sys.executable, scripts / "write-display-report.py", tree])


if __name__ == "__main__":
    main()
