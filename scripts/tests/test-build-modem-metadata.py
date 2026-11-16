#!/usr/bin/env python3
"""Host test for scripts/build-modem-metadata.py (no device, no kernel build)."""

import importlib.util
import struct
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "build_modem_metadata", REPO / "scripts/build-modem-metadata.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

HASH = b"H" * 4808
B00 = b"B" * 1076

def build_mdt(hash_payload=HASH, phnum=3, phentsize=32, magic=b"\x7fELF"):
    data_off = 52 + phentsize * phnum
    load = b"L" * 32
    hash_off = data_off + len(load)
    buf = bytearray(data_off + len(hash_payload))
    buf[:4] = magic
    buf[4] = 1
    struct.pack_into("<I", buf, 28, 52)
    struct.pack_into("<HH", buf, 42, phentsize, phnum)
    def phdr(index, p_type, p_offset, filesz, memsz, flags):
        struct.pack_into("<IIIIIIII", buf, 52 + index * 32, p_type, p_offset, 0, 0,
                         filesz, memsz, flags, 0)
    phdr(0, 0, 0, data_off, data_off, 0)
    phdr(1, 1, data_off, len(load), len(load), 7 << 24)
    phdr(2, 0, hash_off, len(hash_payload), len(hash_payload), 2 << 24)
    buf[data_off:data_off + len(load)] = load
    buf[hash_off:hash_off + len(hash_payload)] = hash_payload
    return bytes(buf), bytes(buf[:data_off]) + hash_payload

def expect_error(label, fn):
    try:
        fn()
    except MOD.MetadataError:
        return 0
    print("FAIL %s did not raise MetadataError" % label)
    return 1

def main():
    failures = 0
    mdt, want = build_mdt()
    blob, header, hash_seg, phdrs = MOD.parse_metadata(mdt)
    if blob != want:
        print("FAIL valid blob differs")
        failures += 1
    if header["filesz"] != 52 + 32 * 3 or hash_seg["filesz"] != len(HASH):
        print("FAIL segment sizes")
        failures += 1
    MOD.check_split(blob, blob[:1076], HASH)
    failures += expect_error("bad magic", lambda: MOD.parse_metadata(build_mdt(magic=b"XXXX")[0]))
    failures += expect_error("bad phentsize", lambda: MOD.parse_metadata(build_mdt(phentsize=16)[0]))
    failures += expect_error("no hash", lambda: MOD.parse_metadata(build_mdt(hash_payload=b"")[0]))
    failures += expect_error("b00 mismatch", lambda: MOD.check_split(blob, b"X" * 1076, HASH))
    failures += expect_error("b31 mismatch", lambda: MOD.check_split(blob, blob[:1076], b"X" * 4808))
    truncated = build_mdt()[0][:-100]
    failures += expect_error("truncated hash", lambda: MOD.parse_metadata(truncated))
    split = bytearray(build_mdt()[0])
    split = bytearray(split[:52 + 32 * 3] + split[-len(HASH):])  # hash appended, image offset stale
    struct.pack_into("<I", split, 52 + 2 * 32 + 4, 0x06814000)
    expected_split = bytes(split[:52 + 32 * 3]) + HASH
    blob2, _, _, _ = MOD.parse_metadata(split)
    if blob2 != expected_split:
        print("FAIL split-mdt hash offset was not resolved to header end")
        failures += 1
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "meta.bin"
        rc = MOD.main(["--mdt", str(Path(tmp) / "modem.mdt"), "--out", str(out)])
        # the file does not exist yet: this call must fail cleanly
        if rc != 1:
            print("FAIL missing mdt was not refused")
            failures += 1
    print("TESTS OK" if failures == 0 else "TESTS FAILED %d" % failures)
    return 0 if failures == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
