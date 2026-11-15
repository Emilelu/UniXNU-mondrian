# ADSP embedded carrier plan

Date: 2026-11-15. Scope: frozen production carrier contract and offline host requirements for mondrian ADSP PAS1. The production reader, generator and checker exist; Lead owns build-strict/archive/manifest wiring and carrier installation. Battery verification and step ⑧ remain false.

## 1. Blob container format

The production K60A ABI is frozen by Lead (P-197) and implemented by [K60AdspImageReader.h](../../../drivers/PongPower/K60AdspImageReader.h), [K60AdspImageReader.c](../../../drivers/PongPower/K60AdspImageReader.c), [gen-k60-adsp-blob.py](../../../scripts/gen-k60-adsp-blob.py) and [check-adsp-blob.py](../../../scripts/check-adsp-blob.py). All integer fields are little-endian; the 24-byte records are packed without C struct padding.

| Field | Frozen production contract |
| --- | --- |
| Header | 12 bytes: `K60A`, `u32 count`, `u32 reserved=0` |
| Records | Sequential 24-byte `{u32 name_len, u32 mode, u64 size, u64 packed_size}`; first record begins at byte 12 |
| Names | Canonical `adsp.mdt` / `adsp.bNN`, NUL-terminated; `name_len=9` |
| Mode and size | Mode is `0644`; size is raw body bytes and `packed_size=size` (no compression) |
| Alignment | Name and body start at 8-byte boundaries; zero padding follows each record, name and body as needed |
| Length and limits | One cursor; final padded end equals supplied total; linked length includes all padding; count 1–64, nonzero sizes, total at most `UINT32_MAX` |
| Linked symbols | `const uint8_t k60_adsp_blob[]`, `const uint64_t k60_adsp_blob_len` |
| Errors | Malformed header/layout/bounds returns `-7`; unsupported mode or `packed_size != size` returns `-8` |

There is one accepted container shape: no flat format, compression, alternate dispatch, or second magic/version. Generator and checker source exist; Lead owns build-strict `--adsp-blob` wiring, archive/manifest integration and the linked production carrier. A generated blob is not yet integrated into the kernel, and the PAS/platform backend remains uninstalled.

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
| -6 | Valid container has no requested part, or linked carrier symbols are absent / length is zero |
| -7 | Malformed/truncated container or offset/size/padded-end bounds error |
| -8 | Unsupported mode (not `0644`) or `packed_size != size` |
| -1 | Invalid argument or prohibited state/source/destination alias |

Preflight the whole container before publishing any part or copying bytes: checked arithmetic, header/records/NUL names, mode/packed-size policy, unique canonical names, sequential bounded body ranges, zero padding and exact terminal cursor. Check `offset <= total && size <= total - offset`; unchecked `offset+size` can overflow. Failures leave destination/borrow outputs unchanged. A malformed present blob must not silently select another carrier. The existing explicit FAT initializer accepts an already mapped image, validates geometry before `k60_fat_open`, and requires bounded contiguous chains for stable borrowing; it performs no DT discovery or physical mapping.

`typedef int (*k60_owner_image_reader)(void *, K60OwnerImage *);` is a callback type, not a function named `k60_owner_image_reader()`. The supplied adapter is `k60_adsp_owner_image_open`, paired with `k60_adsp_owner_image_close`, after `k60_adsp_owner_reader_init`. Lead wires callbacks and persistent context into complete platform ops. For a composite platform context, wrappers must forward image open/close to its persistent `K60AdspOwnerReader` member; bare callbacks require that reader pointer directly. No `owner_install` call exists before the first acquire. The legacy FAT hook only reuses an already-ready reader; the later diagnostic probe is excluded by the early startup claim and cannot prepare the early source. Owner-open/source errors normalize to `-1000`; runtime acquisition failure maps to `-42`. Preserve the separate reader error family above.

Pin immutable blob bytes, mutable reader/owner state and disjoint writable metadata for the entire owner session. Published or uncertain/Poisoned ownership retains those pins indefinitely. A safe abort closes the exact opened image once; a second open or stale close cannot steal another session. Parsing and opening run before exclusive acquisition and mappings. Stage 3 (`k60_owner_auth_and_start`) reborrows payloads before AUTH, after INIT/MEM_SETUP and potentially earlier segment loads, so late read failures follow the owner cleanup/poison contract. BSS invokes load with a NULL source, copy_bytes=0 and the planned nonzero zero_bytes; stage 4’s final TCSR section remains build-existing plus self-parse only. See [PAS1 provider contract](PAS1-PROVIDER-CONTRACT.md) and [carrier lifetime](PAS1-PROVIDER-CARRIER.md).

## 4. Independent host fixture

The production generator emits assembly and can optionally dump the binary container; the checker reconstructs the ordered assembly grammar and validates record fields, names, zero padding, body extents and declared cursor length. They are not build-strict/archive integration and do not establish that the blob is linked into a kernel.

Required host regressions use the captured MDT and real piece files and must independently assert: a 24-segment plan; copy total 23,494,284 B and BSS total 25,925,684 B; byte-exact copy of non-aligned b10 at 0x86e0b2c0; 26 records and exact container length 23,506,184 B; rejection of the obsolete flat shape with -7. Each assertion needs a negative mutation that fails when its corresponding invariant is broken. Root verified the final host suite with exit 0: 77 owner scenarios (claim17/prepare11/auth12/build15/publish22); five reader variants with 31 scenarios each; all five independent blob assertions and their negative mutations; publisher49, builder10, MDT16, notification21, battery27, dispatch14, five patch sections and three canonical mirrors. All 26 entries pass exact copy/borrow, and the generated 23,506,184-byte binary matches the independent builder byte-for-byte. Absent/zero-length carriers invoke the legacy fallback once; malformed/unsupported carriers invoke it zero times.

Host log: [host-tests.log](E:/k60-work/artifacts/adsp-carrier-20261115/final/host-tests.log), SHA256 `51bf1696ec950e112b29f92972e7e9f596c2a91180080e1c9ba79417921e22c1`. Reader/stages/Boot arm64 SDK syntax passes, SHA256 `6d3b5f1cc1bfbfdca7ba3cb9172317bed19469f26b12defbfeba2afb4817055e`; runtime C++ syntax also passes. These are host and syntax results; no kernel/archive link, image or hardware result is claimed.

Lead confirms the production generator/checker runtime result: 23,506,184 bytes, 26 records, raw input 23,505,092 bytes, SHA256 `663369461a9def3105884b34a574c119aaa2b95111c185a6f12de34158bcd319`. The final host-suite result above separately verifies the reader/owner and blob regressions. No kernel/image build or device/serial operation is claimed.

A size budget estimate adds the 23,506,184-byte container to a stated 105 MB kernel baseline: using decimal MB, 128,506,184 B total versus a 4.5 GiB (4,831,838,208 B) pool, leaving 4,703,332,024 B before linker sections, alignment and other allocations. If the baseline means 105 MiB, the corresponding total is 133,606,664 B and headroom is 4,698,231,544 B. These are arithmetic estimates, not measured linked-kernel or boot-pool usage.

## 5. Expected total length and self-check

For the frozen production ABI, let `A(x)=(x+7)&~7` with checked wide arithmetic. Raw input sum `R=23,505,092`; padding the 26 bodies to 8 bytes adds 36, so `S=sum(A(raw_size))=23,505,128`.

```text
cursor = 12
for each entry:
    record = cursor; cursor += 24
    cursor = A(cursor); name_offset = cursor; cursor += 9
    cursor = A(cursor); body_offset = cursor; cursor += raw_size
    cursor = A(cursor)
production_total = cursor = A(12) + 26*(24 + A(9)) + S
                              = 16 + 1,040 + 23,505,128
                              = 23,506,184 B
```

The first record is `[12,36)`, the first NUL name is `[40,49)`, and the first body starts at 56. The first MDT body is `[56,5460)`; after its four zero tail bytes the next record begins at 5464. The production generator derives serialized bytes and linked length from this same cursor. No flat-layout total or alternate K60A shape is supported.

Derive allocation, serialized length and linked length from this single cursor; never use `len(head)+sum(raw_sizes)`. Validate bounded extents, canonical NUL names, mode/packed policy, zero padding and exact terminal cursor. The final host suite passes as recorded above. Ten scoped checks pass: docs193, README table, ownership, secrets, battery, patch parse, working/staged whitespace, build-call fragment and checker negatives. Candidate and unchanged-HEAD porting checks both retain the same 54 inherited errors (no new errors); the porting gate remains nonzero and is not waived. Results: [publication-results.txt](E:/k60-work/artifacts/adsp-carrier-20261115/final/publication-results.txt). No check here establishes PAS authentication, GLINK communication or battery readings.
