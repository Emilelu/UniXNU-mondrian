#!/usr/bin/env python3
"""Give the 27 line an arm64e libfirehose_kernel.a.

XNU's osfmk logging calls into libdispatch's firehose buffer. On this machine that
archive comes from the SDK seed, which was built for a 16.6.1 arm64 kernel, so ld
drops it for an arm64e kernel and reports five undefined __firehose_* symbols.

The real fix is to build libdispatch (scripts/build-firehose.sh does that on Linux,
but it needs .cache/libdispatch-work, which the 27 fetch does not produce yet). Until
then this writes a stub archive with the same symbols so the kernel can link and
boot to bsd_init; firehose is diagnostic logging, so the stubs cost the log stream,
not correctness. Replace by running build-firehose.sh once libdispatch is fetched.
"""
import argparse
import os
import struct
import subprocess
import sys
from pathlib import Path

SYMBOLS = [
    ("__firehose_buffer_create", "int __firehose_buffer_create(void) { return 0; }"),
    ("__firehose_buffer_tracepoint_reserve",
     "unsigned __firehose_buffer_tracepoint_reserve(unsigned a, unsigned b) { (void)a; (void)b; return 0; }"),
    ("__firehose_buffer_tracepoint_flush",
     "void __firehose_buffer_tracepoint_flush(unsigned a, unsigned b) { (void)a; (void)b; }"),
    ("__firehose_merge_updates", "int __firehose_merge_updates(void) { return 0; }"),
    ("__firehose_kernel_configuration_valid",
     "int __firehose_kernel_configuration_valid(void) { return 0; }"),
]

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("--tree", type=Path, required=True, help="resolved kernel tree")
ap.add_argument("--triple", default=os.environ.get("DARWIN_TRIPLE", "arm64e-apple-ios27.0"))
ap.add_argument("--check", action="store_true", help="report, do not build")
args = ap.parse_args()

tree = args.tree.resolve()
fakeroot = Path(os.environ.get("UNIXNU_SDKROOT") or tree / ".cache/fakeroot").resolve()
lib = fakeroot / "usr/local/lib/kernel/libfirehose_kernel.a"


def subtype(path):
    d = path.read_bytes()
    i = d.find(b"\xcf\xfa\xed\xfe")
    if i < 0:
        return None
    return struct.unpack("<II", d[i + 4:i + 12])[1]


if not lib.is_file():
    print(f"firehose: {lib} is absent; nothing to replace")
    if args.check:
        sys.exit(1)
else:
    st = subtype(lib)
    print(f"firehose: {lib} cpusubtype=0x{st:08x}" if st is not None else "firehose: unreadable")
    if st == 0x80000002:
        print("firehose: already arm64e, leaving it alone")
        sys.exit(0)
    if args.check:
        sys.exit(1)

if args.check:
    sys.exit(0)

work = tree / "build/firehose-stub"
work.mkdir(parents=True, exist_ok=True)
src = work / "firehose_stub.c"
src.write_text("/* Stubs for the firehose buffer API; see scripts/build-firehose-stub.py. */\n"
               + "\n".join(body for _, body in SYMBOLS) + "\n", encoding="utf-8")
obj = work / "firehose_stub.o"
clang = os.environ.get("CROSS_CLANG") or "clang"
subprocess.run([clang, "-target", args.triple, "-std=gnu11", "-Os", "-c", str(src), "-o", str(obj)],
               check=True)
old = lib.with_suffix(".a.arm64.bak")
if not old.exists():
    lib.replace(old)
subprocess.run(["xcrun", "libtool", "-static", "-o", str(lib), str(obj)], check=True)
st = subtype(lib)
print(f"firehose: wrote {lib} ({lib.stat().st_size} bytes) cpusubtype=0x{st:08x}")
print("firehose: NOTE these are stubs - run /opt/k60/trees/ios27-fw/scripts/build-firehose.sh "
      "with libdispatch fetched to restore the real buffer")
sys.exit(0 if st == 0x80000002 else 2)
