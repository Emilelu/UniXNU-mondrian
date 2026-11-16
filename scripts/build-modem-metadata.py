#!/usr/bin/env python3
"""Build the PAS metadata page for the K60 modem (MSS).

PAS_INIT_IMAGE takes one page holding the image's ELF header (with its program
headers) followed by the hash segment.  The split firmware keeps both inside
modem.mdt: the first PT_NULL segment is the header, the last PT_NULL segment
carries the hash (p_flags >> 24 == 2).  The blob is therefore

    modem.mdt[header.offset : header.offset + header.filesz]
  + modem.mdt[hash.offset   : hash.offset   + hash.filesz]

This tool proves that layout against the shipped modem.mdt and, when the split
files are given, against modem.b00 and modem.b31; it then writes the blob and a
one-line receipt (size, crc32, sha256).  It does not decide where the page
lives: the UEFI carrier copies the blob to K60_MODEM_METADATA_PA and the kernel
passes that physical address to PAS_INIT_IMAGE.

Run:
  python3 scripts/build-modem-metadata.py \
      --mdt /mnt/e/k60-work/firmware/modem/modem.mdt \
      --b00 /mnt/e/k60-work/firmware/modem/modem.b00 \
      --b31 /mnt/e/k60-work/firmware/modem/modem.b31 \
      --out /mnt/e/k60-work/artifacts/modem-metadata.bin
"""

import argparse
import hashlib
import struct
import sys
import zlib
from pathlib import Path

ELF_MAGIC = b"\x7fELF"
PT_NULL = 0
PT_LOAD = 1
HASH_TYPE = 2
ELF32_EHDR = 52
ELF32_PHDR = 32

class MetadataError(Exception):
    pass

def _u32(data, offset):
    return struct.unpack_from("<I", data, offset)[0]

def parse_metadata(mdt):
    """Return (blob, header_phdr, hash_phdr) for an ELF32 modem.mdt."""
    if len(mdt) < ELF32_EHDR or mdt[:4] != ELF_MAGIC or mdt[4] != 1:
        raise MetadataError("modem.mdt is not ELF32 (bad magic or class)")
    e_phoff = _u32(mdt, 28)
    e_phentsize, e_phnum = struct.unpack_from("<HH", mdt, 42)
    if e_phentsize != ELF32_PHDR:
        raise MetadataError("unexpected e_phentsize %d, want %d" % (e_phentsize, ELF32_PHDR))
    if e_phnum == 0:
        raise MetadataError("e_phnum is zero")
    if e_phoff + e_phnum * e_phentsize > len(mdt):
        raise MetadataError("program header table runs past the end of modem.mdt")
    phdrs = []
    for index in range(e_phnum):
        off = e_phoff + index * e_phentsize
        p_type, p_offset, p_vaddr, p_paddr, p_filesz, p_memsz, p_flags, p_align = \
            struct.unpack_from("<IIIIIIII", mdt, off)
        phdrs.append({"type": p_type, "offset": p_offset, "vaddr": p_vaddr,
                      "paddr": p_paddr, "filesz": p_filesz, "memsz": p_memsz,
                      "flags": p_flags, "align": p_align, "index": index})
    header = next((p for p in phdrs if p["type"] == PT_NULL and p["offset"] == 0 and p["filesz"]), None)
    if header is None:
        raise MetadataError("no PT_NULL header segment at offset 0")
    hash_seg = next((p for p in phdrs if p["type"] == PT_NULL and (p["flags"] >> 24) == HASH_TYPE), None)
    if hash_seg is None:
        raise MetadataError("no PT_NULL hash segment (p_flags >> 24 == 2)")
    if header["offset"] + header["filesz"] > len(mdt):
        raise MetadataError("header segment runs past the end of modem.mdt")
    if hash_seg["filesz"] == 0:
        raise MetadataError("hash segment is empty")
    # Split firmware keeps the hash appended right after the header: on the
    # K60 mdt the hash segment's p_offset is the image offset 109,117,440,
    # far past the 5,909-byte file.  A full modem.mbn keeps it at p_offset,
    # so accept that only when it actually lies inside the file.
    hash_off = hash_seg["offset"]
    if not (header["filesz"] <= hash_off and hash_off + hash_seg["filesz"] <= len(mdt)):
        hash_off = header["filesz"]
    if hash_off + hash_seg["filesz"] > len(mdt):
        raise MetadataError("hash segment runs past the end of modem.mdt")
    blob = mdt[header["offset"]:header["offset"] + header["filesz"]] + \
           mdt[hash_off:hash_off + hash_seg["filesz"]]
    return blob, header, hash_seg, phdrs

def check_split(blob, b00, b31):
    """Prove the blob equals b00 followed by the hash bytes of b31."""
    if b00 is not None:
        if b00 != blob[:len(b00)] or len(b00) != 1076:
            raise MetadataError("modem.b00 is not the 1,076-byte header")
    if b31 is not None:
        if len(b31) < 4808 or b31[:4808] != blob[-4808:]:
            raise MetadataError("modem.b31 does not carry the 4,808-byte hash")

def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mdt", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--b00", type=Path)
    parser.add_argument("--b31", type=Path)
    args = parser.parse_args(argv)
    try:
        mdt = args.mdt.read_bytes()
        blob, header, hash_seg, phdrs = parse_metadata(mdt)
        check_split(blob, args.b00.read_bytes() if args.b00 else None,
                    args.b31.read_bytes() if args.b31 else None)
        expected = header["filesz"] + hash_seg["filesz"]
        if len(blob) != expected:
            raise MetadataError("blob is %d bytes, header+hash says %d" % (len(blob), expected))
        if blob[:4] != ELF_MAGIC:
            raise MetadataError("blob does not start with the ELF magic")
        loads = sum(1 for p in phdrs if p["type"] == PT_LOAD)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(blob)
        print("metadata size=%d crc32=0x%08x sha256=%s header=%d hash=%d "
              "phnum=%d load=%d" % (
                  len(blob), zlib.crc32(blob) & 0xffffffff,
                  hashlib.sha256(blob).hexdigest(), header["filesz"],
                  hash_seg["filesz"], len(phdrs), loads))
        return 0
    except (OSError, MetadataError, struct.error) as exc:
        print("FAIL %s" % exc)
        return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
