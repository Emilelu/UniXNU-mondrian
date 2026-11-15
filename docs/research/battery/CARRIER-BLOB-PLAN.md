# ADSP embedded carrier plan

Date: 2026-11-15. Scope: offline design and host fixtures for mondrian ADSP PAS1. Lead owns the production generator, build integration and assembly carrier. Battery verification and step ⑧ remain false.

## 1. Blob container format

The current reader implements the Metal-style flat format below. Its source of truth is [K60AdspImageReader.h](../../../drivers/PongPower/K60AdspImageReader.h) and [K60AdspImageReader.c](../../../drivers/PongPower/K60AdspImageReader.c); the surveyed precedent is [gen-k60-metal-blob.py](../../../scripts/gen-k60-metal-blob.py). All integers are little-endian and packed, without C struct padding.

| Field | Current reader contract |
| --- | --- |
| Header | 4 bytes `K60A`, then `u32 count`; 8 bytes total |
| Table | `count` records of `{u16 name_len, u32 raw_size, u32 absolute_offset}`; 10 bytes each |
| Names | Concatenated canonical `adsp.mdt` / `adsp.bNN`, each 8 bytes, no NUL |
| Bodies | First begins at `align8(8 + 10*count + sum(name_len))`; each next begins at `align8(offset + raw_size)` |
| Padding and length | All padding zero; ordered contiguous padded extents; last padded end equals the supplied total |
| Limits | 1–64 entries, nonzero sizes, unique canonical names, total at most `UINT32_MAX` |
| Linked symbols | `const uint8_t k60_adsp_blob[]`, `const uint64_t k60_adsp_blob_len`; length includes every padding byte |

Lead’s latest reply proposes a different layout: 12-byte `{magic K60A, u32 count, u32 reserved}` followed by sequential records `{u32 nameLen, u32 mode, u64 size, u64 packedSize}`, each followed by its name and body. Names include NUL (`nameLen=9` for this inventory); both name and body starts are 8-byte aligned. No compression is proposed because the kernel path does not link zlib.

**These layouts are wire-incompatible.** The current reader treats byte 8 as the first flat entry: a zero proposed `reserved` becomes a zero name length and returns `-7`. Its canonical name length is 8, while the proposal uses 9; table offsets and record widths also differ. This task keeps production reader and stages unchanged. The host test models both layouts, proves current-reader rejection of the proposal, and gives Lead concrete totals. Before production integration, Lead must retain the current flat contract or agree an explicit version/magic/dispatch change. Reusing `K60A` alone cannot identify both layouts.

The proposal’s fixture uses reserved=0, mode=0644 as a test-only permission-mode assumption, `size=packedSize=raw bytes`, and body offsets derived from the cursor. These mode/size semantics still need Lead’s production contract. No new kernel dispatch is supplied here. Future assembly must align the blob base to 8 bytes (for example `.p2align 3`) and preserve the full cursor length, as required by P-196.

## 2. Packing the 26 image files

The captured input directory is `E:/k60-work/firmware/adsp` (`/mnt/e/k60-work/firmware/adsp` in WSL). All 26 `adsp.*` inputs were individually inspected. Only those 26 image files enter the blob: **23,505,092 B** = MDT 5,404 B + 25 pieces 23,499,688 B. The whole directory has 28 files / 23,506,308 B. `adspr.jsn` and `adspua.jsn` are QDSP6 loading metadata (1,216 B together) and are excluded; any future consumer must document its own ownership and loading phase.

The deterministic fixture order is shown below. Names are container keys; the final column is the number of zero bytes added after each body.

| Name | Raw bytes | Tail padding to 8 |
| --- | ---: | ---: |
| `adsp.mdt` | 5,404 | 4 |
| `adsp.b00` | 884 | 4 |
| `adsp.b01` | 6,952 | 0 |
| `adsp.b02` | 3,216,484 | 4 |
| `adsp.b03` | 25,720 | 0 |
| `adsp.b04` | 34,632 | 0 |
| `adsp.b05` | 710,336 | 0 |
| `adsp.b06` | 220 | 4 |
| `adsp.b07` | 4,892 | 4 |
| `adsp.b08` | 2,306,824 | 0 |
| `adsp.b09` | 237,576 | 0 |
| `adsp.b10` | 720 | 0 |
| `adsp.b11` | 9,960 | 0 |
| `adsp.b12` | 131,232 | 0 |
| `adsp.b13` | 83,220 | 4 |
| `adsp.b14` | 3,167,652 | 4 |
| `adsp.b15` | 108,732 | 4 |
| `adsp.b16` | 280 | 0 |
| `adsp.b17` | 185,008 | 0 |
| `adsp.b18` | 11,511,192 | 0 |
| `adsp.b19` | 503,816 | 0 |
| `adsp.b20` | 1,936 | 0 |
| `adsp.b21` | 201,084 | 4 |
| `adsp.b22` | 103,736 | 0 |
| `adsp.b23` | 942,080 | 0 |
| `adsp.b25` | 4,520 | 0 |
| **Total** | **23,505,092** | **36** |

`adsp.b24` is absent because segment 24 is pure BSS (7,245,824 zero bytes). Do not fabricate a file or require a read for it. `adsp.b00` is the 884-byte header prefix; `adsp.b25` is the 4,520-byte hash piece. Their combined 5,404 bytes duplicate MDT content, so disk/container inventory is not the copied PT_LOAD total. Captured MDT SHA256: `1238098817957c4d3cd0995fd413332751ac8082ea315e6e1d9bdb247cadc694`.

## 3. Named reader and owner contract

The named-read ABI is `typedef int (*K60AdspRead)(const char *part, void *dst, uint32_t bytes);`. The contextual entry point is `int k60_adsp_reader_read(K60AdspReader *, const char *, void *, uint32_t);`; the linked-symbol wrapper is `int k60_adsp_read(const char *, void *, uint32_t);`. Canonical names are as above; aliases `mdt` and `adsp` select `adsp.mdt`.

| Result | Meaning at named-reader boundary |
| --- | --- |
| 0 | Whole exact-size part copied, with no page rounding |
| -5 | Requested/returned size mismatch, including a partial part; destination unchanged |
| -6 | Valid container has no requested part, or linked carrier symbols are absent |
| -7 | Malformed/truncated container or offset/size/padded-end bounds error |
| -1 | Invalid argument or prohibited state/source/destination alias |

Preflight the whole container before publishing any part or copying bytes: checked arithmetic, header/table/names, unique nonempty canonical names, ordered aligned nonoverlapping ranges, zero padding, exact terminal cursor. Check `offset <= total && size <= total - offset`; unchecked `offset+size` can overflow. Failures leave destination/borrow outputs unchanged. A malformed present blob must not silently select another carrier. The existing explicit FAT initializer accepts an already mapped image, validates geometry before `k60_fat_open`, and requires bounded contiguous chains for stable borrowing; it performs no DT discovery or physical mapping.

`typedef int (*k60_owner_image_reader)(void *, K60OwnerImage *);` is a callback type, not a function named `k60_owner_image_reader()`. The supplied adapter is `k60_adsp_owner_image_open`, paired with `k60_adsp_owner_image_close`, after `k60_adsp_owner_reader_init`. Lead wires callbacks and persistent context into complete platform ops. Owner-open/source errors normalize to `-1000`; runtime acquisition failure maps to `-42`. Preserve the separate reader error family above.

Pin immutable blob bytes, mutable reader/owner state and disjoint writable metadata for the entire owner session. Published or uncertain/Poisoned ownership retains those pins indefinitely. A safe abort closes the exact opened image once; a second open or stale close cannot steal another session. Parsing and opening run before exclusive acquisition and mappings. Stage 3 (`k60_owner_auth_and_start`) reborrows payloads before AUTH, after INIT/MEM_SETUP and potentially earlier segment loads, so late read failures follow the owner cleanup/poison contract. BSS invokes load with a NULL source, copy_bytes=0 and the planned nonzero zero_bytes; stage 4’s final TCSR section remains build-existing plus self-parse only. See [PAS1 provider contract](PAS1-PROVIDER-CONTRACT.md) and [carrier lifetime](PAS1-PROVIDER-CARRIER.md).

## 4. Independent host fixture

[test-k60-adsp-blob.c](../../../scripts/tests/test-k60-adsp-blob.c) is a standalone host fixture, integrated into [run-k60-handoff-host.sh](../../../scripts/tests/run-k60-handoff-host.sh). It reads the captured 26 inputs and packs containers in host memory; it is not a production generator and emits no kernel carrier or assembly.

The current-layout fixture is read back through the real named reader, compared byte-for-byte against direct file input, then parsed through the real MDT parser/owner adapter. Compare all 24 planned segments with direct-read planning, copy 23,494,284 B, BSS 25,925,684 B and relocated span `0x3100000` = 51,380,224 B. Copy+BSS = 49,419,968 B; the remaining 1,960,256 B are gaps, not missing payload. Segment 10 has link address `0x86e0b2c0`, relocated address `0xa080b2c0`, copy 720 and zero 2,672; segment 24 requires no piece read.

The sequential-proposal fixture has an independent host-only validator: check names, the fixture permission mode 0644, raw/packed size equality, name/body alignment, padding, bounded disjoint extents and exact terminal cursor. Feed that valid proposal to the current production reader and assert `-7`. This is evidence of incompatibility, not proof of a production decoder for the proposal. Negative cases must leave outputs unchanged and cover malformed names/table/padding/ranges/truncation plus named-reader -5/-6/-7. The existing reader and 77 owner-stage scenarios remain regression requirements. This round does not build a kernel/image or access a device, boot path or serial port.

Validation on 2026-11-15: the integrated offline runner passed, including this fixture’s 1,931 checks, 55 malformed flat containers, 85 malformed proposal containers and four negative inventory cases. Direct-file and blob-owner plans match every top-level field, every field of all 24 segments and metadata bytes; both avoid a b24 read. The original 77 owner scenarios and both 19-group reader variants also pass. A separate ASan/UBSan fixture run passed without findings. Durable full-suite log: `E:/k60-work/artifacts/adsp-blob-20261115/final/host-tests.log` (14,336 B, 352 lines, SHA256 `26a6ec88a415da08111f1133dacdfb104daf8a74ffcc486027bdf8edc4f80eff`). The runner’s arm64 adapter syntax check is not a kernel link or production-carrier test.

## 5. Expected total length and self-check

Let `A(x) = (x + 7) & ~7` using checked wide arithmetic. Raw sum `R=23,505,092`; nine 4-byte tails add 36, so `S=sum(A(raw_size))=23,505,128`.

For the **current flat contract**, initialize the body cursor once from table+names, then advance it by the actual padded body end:

```text
cursor = A(8 + 26*10 + 26*8) = A(476) = 480
for each entry:
    absolute_offset = cursor
    cursor = A(cursor + raw_size)
k60_adsp_blob_len = total = cursor = 480 + S = 23,505,608 B
```

For the **strict sequential proposal**, start the record cursor at 12; do not silently insert a different header. Align each name after its 24-byte record, then align the data after its 9-byte NUL name, then align the body end:

```text
cursor = 12
for each entry:
    record = cursor; cursor += 24
    cursor = A(cursor); name_offset = cursor; cursor += 9
    cursor = A(cursor); data_offset = cursor; cursor += raw_size
    cursor = A(cursor)
proposed_total = cursor = A(12) + 26*(24 + A(9)) + S
                       = 16 + 1,040 + 23,505,128 = 23,506,184 B
```

The first record is `[12,36)`, name `[40,49)`, body starts at 56. For the first 5,404-byte MDT, its body is `[56,5460)` and the next record starts at 5464. Putting that name at byte 36 violates the stated name alignment; the resulting 23,506,176-byte variant is not this proposal. Strict proposal overhead is 576 B more than current flat layout.

In both models derive the allocation, final serialized length and linked length constant from that same cursor; never use `len(head)+sum(raw_sizes)`. Self-check every `[offset,offset+size)` against total, 8-byte body offsets, nonempty names and no overlaps; validate padding and require `cursor == total`, rejecting both truncation and extra bytes. Final scoped checks pass: documentation consistency (193 checks), README table, ownership, secrets, battery build prerequisites (six checks), patch parsing and whitespace. The porting-path check remains nonzero: candidate and unchanged-HEAD baseline both have the same 54 errors, with none introduced or resolved; it is not waived or reported green. Gate logs are under `E:/k60-work/artifacts/adsp-blob-20261115/final/`. None of these checks establishes PAS authentication, GLINK communication or battery readings.
