# Retained Goodix module initialization audit (2026-11-14)

Status: offline binary evidence only. No touch code, firmware, build, device or serial action is authorized by this report. Root cause and step ⑧ remain unproven. Cross-reference: [stage-one matrix](13-STAGE-ONE-ROOT-CAUSE-MATRIX.md).

## Identity and reproducibility

- Input: E:/k60-work/scratch/goodix_core.ko (WSL /mnt/e/k60-work/scratch/goodix_core.ko), 614,896 bytes.
- SHA-256 before/after analysis: 381b1969f45a65b5922387091b6a8e8bacd452ab5b135eab3824b079c6e6b977.
- ELF64, little-endian, AArch64, **ET_REL**; retained symbol and RELA tables; no DWARF. Earlier ET_EXEC descriptions were incorrect. The .text file offset is 0x14000. All instruction addresses below are .text-relative offsets, not loaded virtual addresses.
- Embedded metadata: vermagic 5.10.160-gki-gf555d54c041a; scmversion gf205246a249c; Build-ID c82140295cf1e2d2c56f0a1cf9c4488ee0004491; dependencies xiaomi_touch, sched-walt, panel_event_notifier. Embedded source path names touchfeature_v2/touch_driver/m11a/goodix_9916r/goodix_ts_core.c and compatible xiaomi,m11a-spi.
- Metadata does **not** establish acquisition from this K60, exact source/build lineage, or that this module was loaded on the unit. Conclusions apply to this retained binary and its normal, unmodified operation table.

Use existing WSL tools; the earlier MSYS readelf-not-found result did not establish WSL tool absence. These are read-only commands, not build commands:

~~~bash
sha256sum /mnt/e/k60-work/scratch/goodix_core.ko
readelf -h /mnt/e/k60-work/scratch/goodix_core.ko
readelf -sW /mnt/e/k60-work/scratch/goodix_core.ko
readelf -rW /mnt/e/k60-work/scratch/goodix_core.ko
llvm-objdump -dr --start-address=0x3110 --stop-address=0x32b4 /mnt/e/k60-work/scratch/goodix_core.ko
llvm-objdump -dr --start-address=0xbadc --stop-address=0xbc90 /mnt/e/k60-work/scratch/goodix_core.ko
llvm-objdump -dr --start-address=0x11104 --stop-address=0x12068 /mnt/e/k60-work/scratch/goodix_core.ko
llvm-objdump -dr --start-address=0x12068 --stop-address=0x12198 /mnt/e/k60-work/scratch/goodix_core.ko
llvm-objdump -dr --start-address=0x2c070 --stop-address=0x2c230 /mnt/e/k60-work/scratch/goodix_core.ko
llvm-objdump -dr --start-address=0x1700 --stop-address=0x23d0 /mnt/e/k60-work/scratch/goodix_core.ko
llvm-objdump -dr --start-address=0x136e8 --stop-address=0x13b9c /mnt/e/k60-work/scratch/goodix_core.ko
llvm-objdump -dr --start-address=0x18bc8 --stop-address=0x18cec /mnt/e/k60-work/scratch/goodix_core.ko
~~~

Relocation records are necessary: an unrelocated BL/B label can point misleadingly at another local label. The retained-module subagent completed the bounded power/confirm disassemblies and call-table tracing; the Lead independently cross-checked the file digest/header, probe callsite, confirm instructions and CFI jump relocations. This is not runtime evidence.

## Operation-table resolution

The hardware table brl_hw_ops.llvm.2012013027667833008 is .data+0x5f0, size 0xb8. Probe installs it at 0xafbc/0xafcc/0xafdc; the last instruction stores it at core+0x280 (640 decimal, not 0x640). The pointer is reloaded from that same offset by the wrapper, confirm and version callers. Function names below omit the common retained symbol suffix, which readelf displays as $281df2f6a13b4a657a6eb0b25804b81b.

| Table slot | .data location | ABS64 target | CFI JUMP26 destination |
|---|---|---|---|
| power_on +0 | 0x5f0 | 0x2c070 | 0x2c074 -> brl_power_on @0x11104, size 0xc40 |
| dev_confirm +8 | 0x5f8 | 0x2c178 | 0x2c17c -> brl_dev_confirm @0x11d44, size 0x324 |
| read_version +0x60 | 0x650 | 0x2c100 | 0x2c104 -> brl_read_version @0x136e8, size 0x4b4 |
| read +0x38 | 0x628 | 0x2c0f0 | 0x2c0f4 -> brl_read @0x124f4 |
| write +0x40 | 0x630 | 0x2c0f8 | 0x2c0fc -> brl_write @0x12578 |

The write/read operations used by confirm are slots +0x40/+0x38, distinct from +8; they are not reversed. brl_read at 0x12508/0x12514 loads core+0x138 and bus+0x10; brl_write at 0x1258c/0x12598 uses core+0x138 and bus+0x18. Both forward transport status w0. Do not infer the complete initialization sequence by searching only for a direct call inside brl_power_on.

Each indirect read/write call also has a CFI guard. Its fast-path check rotates (target - 0x2c0f0) by 3 and accepts the two jump-table entries 0x2c0f0/0x2c0f8; other targets call __cfi_slowpath with type ID 0xdfe51f326c5bf514 and resume the original call only if that handler returns. These are type checks, not transfer retries, and type compatibility alone does not establish read/write semantics.

## Actual caller sequence

| Instruction offset | Decisive operation | Meaning |
|---|---|---|
| 0xbadc | CALL26 goodix_ts_power_on | Wrapper dispatches power_on(core, true): 0x31c0 loads slot 0, 0x31dc sets w1=1, 0x31e8 BLR x20. |
| 0xbae0 | CBNZ w0, 0xbcdc | Power-on error takes an error path. |
| 0xbae4 / 0xbae8 | LDR x8,[x19,#640]; LDR x21,[x8,#8] | Load dev_confirm from the installed table. |
| 0xbb08 | BLR x21 | Invoke shared BRL dev-confirm after power_on returns. |
| 0xbb0c | CBZ w0, 0xbb68 | Zero result skips an error log. Nonzero logs at 0xbb64, then falls through to 0xbb68; confirm failure is nonfatal at this caller. |
| 0xbc4c / 0xbc50 | LDR x8,[x19,#640]; LDR x21,[x8,#96] | Load read_version. |
| 0xbc74 | BLR x21 | Version read follows confirm, including after confirm failure. |

Between confirm and version are notifier/wakeup/tools/queue setup and logging. No explicit reset or sleep occurs at this callsite. brl_power_on itself has no dev_confirm call: its direct calls at 0x111f8/0x1164c relocate to brl_select_spi_mode @0x17208, not confirm.

## Power, reset and family scope

Probe request strings identify core offsets +396 as IOVDD GPIO, +392 as AVDD GPIO and +384 as RESET GPIO. On the requested on branch, GPIO >=1 selects a raw output-high API; otherwise a nonnull regulator pointer selects regulator_enable. A missing regulator pointer skips the rail action, but not the delay. The common path requests IOVDD action -> usleep_range(3000,3100) at 0x11178 -> AVDD action -> usleep_range(15000,15100) at 0x111a8 -> RESET high at 0x111b8. GPIO return values are ignored. These are software requests, not proof of successful rail/GPIO actions, measured electrical timing, voltage or board polarity.

The type check at 0x111d0 compares against 4/Berlin-A. Other types branch to 0x11660, request msleep(100), and return before caller dev-confirm. Thus the type-6/Berlin-D path in this binary is **IOVDD +3 ms -> AVDD +15 ms -> RESET high +100 ms -> return -> caller dev-confirm -> version**. This differs from the separately retained Goodix upstream reference's reset-high +4 ms -> confirm -> post-confirm delay; do not silently merge the two source sequences.

The successful non-type-4 power-on path has no RESET-low pulse. Probe previously requests RESET GPIO at 0xb0a8 with flags 0 (the output-low request); this is distinct from a low pulse inside power_on. Separate brl_reset @0x12068 sets RESET low at 0x12114, requests 2.0-2.1 ms at 0x12120, sets high at 0x12130, waits the caller delay, then calls brl_select_spi_mode at 0x12164; it has no confirm call. Do not transplant that reset routine into the power-on sequence without a reason.

The compatible decoder goodix_get_ic_type @0x18fa4 tests substrings 9916 at 0x1909c/0x190b0 and spi at 0x190b8/0x190c4, then takes the BerlinD path and sets type 6 at 0x19284. The SPI probe stores the returned type at bus+4 at 0x1750. This proves the retained binary mapping, not the unit's actual runtime DT selection. The shared table/probe confirm has no family guard: it is invoked for the binary's Berlin-D path, but is neither Berlin-D-exclusive nor proof that every Berlin-D device requires it.

Error policy must also be kept distinct. A nonzero power-wrapper result at 0xbae0 goes to probe cleanup before confirm. In the power callback, regulator-enable failures enter shared low/off cleanup; regulator-disable status assignments at 0x119ac/0x11c70 can overwrite the earlier enable error, even with zero. Thus an enable failure is not guaranteed to propagate. Confirm nonzero only logs and continues. The version callback reads 28 bytes at 0x1000c for type 4, otherwise 0x10014; it checks the checksum and retries up to three attempts, with 5.0-5.1 ms requested delay for a bus error and 10-11 ms for a checksum error. It performs no peripheral write itself. The first negative version result can enter firmware recovery; a nonzero second version result at 0xc274 takes cleanup and returns the saved error. No explicit power-off call occurs in the inspected final probe cleanup tails. Recovery helpers were not exhaustively audited, so this is not a proof that the complete probe path has no further peripheral writes.

## Exact confirm behavior

- At 0x11d7c, MOV x8,#0xaaaaaaaaaaaaaaaa; 0x11d80 initializes rx[8]=zero and tx[8]=eight AA bytes once, not between attempts.
- At 0x11d84, load write slot +0x40; 0x11d9c sets address 0x10000, 0x11da0 sets length 8, 0x11da8 invokes write.
- At 0x11db0, load read slot +0x38; 0x11dc8/0x11dcc set the same address/length; 0x11dd4 invokes read.
- Attempts call write/read at 0x11da8/0x11dd4, 0x11e18/0x11e44 and 0x11e88/0x11eb4. The six TBNZ w0,#31 tests at 0x11dac, 0x11dd8, 0x11e1c, 0x11e48, 0x11e8c and 0x11eb8 go straight to shared epilogue 0x11ec8. A negative transfer returns that exact status immediately: no local retry, mismatch delay or confirm-failure log. Lower transport routines may have separate retry policies.
- At 0x11ddc/0x11de0 and the corresponding later compares, all eight rx bytes are compared with tx. A match returns the last read status unchanged; the epilogue does not force zero. The caller at 0xbb0c requires exactly zero, not merely a nonnegative status.
- Only a readback mismatch advances to another attempt. There are three total write/read attempts, not three retries. Each mismatch requests usleep_range(5000,5100), including the final mismatch at 0x11ef8-0x11f00. After the third mismatch it logs all eight returned bytes at 0x11f80 and sets w0=-22 at 0x11f84. All-mismatch requested sleep totals 15.0-15.3 ms, not a measured elapsed duration. There is no chip-type test in the complete 0x324-byte function.
- The non-Berlin-A version path reads 28 bytes at 0x10014; that is a later operation, not evidence that confirm can be skipped.

## SPI dispatch and wire-format comparison

The independent transport audit verified the same input SHA-256 before analysis. The SPI probe installs goodix_spi_bus (.bss+0x30, size 32): bus_type=1 and the decoded IC selector at bus+0/+4 (0x1750), device at +8 (0x1764), read/write callbacks at +0x10/+0x18 (0x1760). The comparison at 0x174c and selection at 0x175c choose read_bra only for selector 4; the previously traced selector-6 path uses the standard read. Relocations resolve the SPI CFI stubs: 0x2c214 -> write @0x204c, 0x2c21c -> read_bra @0x19bc, and 0x2c22c -> standard read @0x1ca0. The wrappers at 0x1252c/0x125b0 dispatch through those bus slots and forward w0. A nearby I2C-looking disassembler label is a CFI type-base annotation, not evidence of I2C dispatch.

| Retained operation | Transmitted bytes and received-data offset | Transfer and decisive anchors |
|---|---|---|
| Standard read (selector !=4) | F1 + BE32 address + three FF bytes + N zero clocking bytes; copy N bytes from RX+8 | One full-duplex transfer of N+8; 0x1dd4/0x1dd8 dummy bytes, 0x1df8 pointers, 0x1dfc length, 0x1e20 spi_sync, 0x1e2c-0x1e38 copy |
| read_bra (selector 4 only) | F1 + BE32 address + four FF bytes + N zero clocking bytes; copy from RX+9 | One full-duplex transfer of N+9; 0x1aec dummy bytes, 0x1b0c pointers, 0x1b10 length, 0x1b34 spi_sync, 0x1b40-0x1b4c copy |
| Write (both paths) | F0 + BE32 address + N payload bytes; RX pointer null | One transfer of N+5; 0x213c-0x2164 address, 0x2158/0x2168 payload at +5, 0x2170 length, 0x2190 TX pointer, 0x21b4 spi_sync |

The read clocking tails are zero from allocations through the retained kzalloc wrapper @0x23b0. Each function initializes and links one spi_transfer/message; the relevant flag byte remains zero, including cs_change. SPI setup requests mode 0 and 8 bits per word at 0x1708-0x1718. Thus the code requests header, dummy bytes and data in one transfer, not an address transaction followed by a separate read transaction. This does not prove physical pin roles, CS polarity or continuity, actual clock frequency, controller segmentation/gaps, or any live response.

Status/retry policy differs from the active patch. The retained routines return raw spi_sync status, not a byte count or chip ACK. Reads copy on a nonnegative result; allocation failure returns -12. read_bra has one spi_sync and no local retry. Standard read calls at 0x1e20/0x1f28/0x1f44 and write calls at 0x21b4/0x22a0/0x22c0 allow at most three total attempts, retrying only negative status with the same buffers/message and returning the latest result. Each failed attempt, including the final one, passes 0x8312b0 to __const_udelay; this audit does not resolve that helper into measured time. These functions do not validate actual_length or check protocol ACK/status bytes, and contain no chunking. Their status-success path alone is not controller communication proof.

The active patch's F1/BE32/three-FF/RX+8 and F0/BE32/payload framing therefore agree at source level with this retained standard path. This is evidence against an obvious static framing mismatch, not proof that its GPIO implementation produces the requested waveform. No need to add a fourth dummy byte for selector 6 is established. The active patch performs one lower-level transfer per register operation and collapses status into boolean success, rather than reproducing the retained retry/status contract. Whether this difference contributes to the all-default version bytes is unproven.

## Exact version checksum, layout and retry policy

The independent version audit verified the input SHA-256 before and after analysis. brl_read_version @0x136e8 (size 0x4b4) reads 28 bytes using the hardware read slot +0x38. The selector is loaded from bus+4; 0x13758/0x13770 choose address 0x1000c for selector 4 and 0x10014 otherwise. The actual checksum call at 0x1381c-0x13828 is checksum_cmp(buffer,28,0), with CALL26 relocation to 0x18bc8, not goodix_append_checksum.

For this selected zero-mode call, bytes 0..25 are summed as unsigned bytes modulo 65536, then compared with LE16 stored at bytes 26..27. Instructions 0x18c08, 0x18c8c-0x18cc8 and 0x18cd0-0x18ce0 establish that rule. It is not a complement, zero-sum, CRC or 16-bit-word sum. All first 26 bytes participate, including those whose semantics are unknown. The active patch's version checksum predicate agrees with this rule; agreement for this version packet does not establish every event/config packet layout. The generic helper's nonzero mode was not selected here and must not be used to justify this version checksum.

| Proven output use | Bytes | Binary evidence and limit |
|---|---|---|
| ROM PID | 0..5 | Success copies six bytes into separately zeroed scratch, then logs rom_pid at 0x13988-0x139e0 |
| ROM VID | 6..8 | Pointer +6 and length 3 at 0x13a34/0x13a40; no numerical byte-order interpretation proven |
| Patch PID start | 10 | pid log at 0x13a90 and patch_pid consumer at 0xed94; unbounded %s does not prove an eight-byte declared array or NUL validation |
| Patch VID | 18..21 | Pointer +18/length 4 at 0x13ae4/0x13af0; consumer loads each byte at 0xedb4-0xedc0 |
| Sensor ID | 23 | Byte load and sensor_id log at 0x13b38-0x13b44 |
| Stored checksum | 26..27 | LE16 comparison described above |

No semantics for bytes 9, 22, 24 or 25 are established by these consumers; do not label them reserved, flags or validity fields. Successful validation copies all 28 bytes unchanged to the caller at 0x13968-0x13984. No PID, sensor, termination or plausibility check beyond the checksum is performed here. In particular, a zero-filled buffer satisfies this additive checksum mathematically; the active patch's explicit rejection of buffers containing only 00-or-FF bytes, including mixtures, is a separate plausibility policy, not evidence of a checksum mismatch in the retained callback.

There are three total version attempts. Any nonzero read result follows 0x13818 ->0x13778, logs that result and the zero-based attempt, requests usleep_range(5000,5100), and normalizes the failure to -1. A checksum mismatch follows 0x1382c, logs/dumps 28 bytes, requests usleep_range(10000,11000), and normalizes to -2. Both delays occur even after the third failed attempt. Shared increment/limit instructions 0x137e4-0x137ec bound the loop; mixed failures return the last category, not the original I/O errno. Success copies the full buffer and returns zero; failure leaves caller output untouched. The callback itself performs no peripheral write, but the already noted surrounding firmware-recovery helpers were not exhaustively audited.

The active goodix_probe performs a single version read per invocation. Its initial failure at touch_thread ->bring_up exits before the later resume-reset/second probe, so that later probe is not an initial-version retry. A future proposal must explicitly choose its retry, status and plausibility policies rather than claim the current implementation matches the retained binary. None of these static differences independently establishes the present K60 root cause.

## Follow-up source/test-oracle audit (2026-11-14 11:24 +08:00)

The active touch patch reviewed here has SHA-256 c9fb7e6a129d74178bac22b45fb3e6a401428b0acdaecbd736e087dae2d7cced. Its goodix_read at patch lines 654-670 sends F1, a big-endian 32-bit address, three FF bytes and length zero bytes in one 8+length transfer; it copies received bytes from offset 8. goodix_write at lines 674-685 sends F0, the same big-endian address and payload in one 5+length transfer. These are source-level framing facts, not proof of a physical waveform or controller response.

The active goodix_checksum_ok at lines 692-697 compares the unsigned-byte sum of all but the last two bytes, modulo 65536, with the final little-endian 16-bit value. However scripts/tests/test-brl-parse.py (reviewed SHA-256 545a27e44401b1873e1bc6fb69d8c3351f9b03b9727d4efcb376893e3ecd4b6d) independently implements an 8-bit negative-sum checksum at lines 19-21, places it only at byte 7, and never imports or executes the patch function. Its request decoder at line 56 uses reset value 1, whereas the active patch defines GOODIX_REQUEST_RESET as 3. This is a stale oracle, not a current driver unit test.

A read-only rerun printed 10/11 and exited 1: TOUCH|REQUEST with count 2 returned reset=False while expecting True. Its old raw-frame check still reported a pass by testing only the returned count, even though that same run printed checksum 0x7a and rejected the frame; zero from the error tuple is not proof of a valid zero-contact event.

A separate in-memory differential of the inspected active predicate makes the checksum disagreement explicit: 80 00 01 00 00 00 00 7f is accepted by the legacy 8-bit header construction but rejected by the active predicate (payload sum 129, LE16 tail 32512); 80 00 01 00 00 00 81 00 passes the active predicate (129 equals 129). The old bytes 80 19 00 e8 08 e8 08 01 fail it (625 versus 264). These synthetic calculations do not execute the driver and do not establish the layout or validity of a live frame. No test or implementation file was modified. Step 7 must remain open until a separately authorized, source-coupled test covers the active checksum and request policy.

## GPIO-SPI source audit (2026-11-14)

The same active patch digest is used here; no GPIO access was performed. Source lines 578-588 configure CS high, MISO as a no-pull input, CLK low and MOSI low. Lines 602-626 reject zero or greater-than-1032-byte transfers, assert CS once, send bytes MSB first, set MOSI while CLK is low, request a delay, raise CLK, request another delay, sample MISO, then lower CLK. After all bytes it requests a final delay and deasserts CS. This is a mode-0-shaped software sequence, not a measurement of pad routing, voltage, edge placement or a working controller. Writes use a volatile store plus dsb sy at lines 87-90; a GPIO readback or barrier is not an electrical observation.

The configured bb_delay_us is 2 (line 593). Each data bit requests two such waits: the delay-only arithmetic is 4 microseconds per bit (250 kHz), before GPIO/barrier/loop overhead or scheduling; it is not a measured 333 kHz or proof of the comment's claimed prior working rate. At line 622 the thread additionally requests sleep_ms(1) after each 64th transferred byte while CS stays asserted and CLK is low, including when that byte ends the transfer. A 28-byte version read is 36 wire bytes and does not enter this explicit yield; a 2-byte IC-info length read is 10 wire bytes and also does not. A longer IC-info transfer of L+8 wire bytes requests floor((L+8)/64) such sleeps. Therefore these explicit 64-byte yields cannot explain the captured failure on the initial 28-byte version read. Their effect on a later long IC-info frame remains an unmeasured protocol-timing question, not a proven fault or permission to change timing.

An independent source-only review confirmed one configuration/log contract mismatch: k60touchhz accepts any value from 1 through 15000000 and stores it in spi_hz (lines 1275-1284), and the worker logs SPI<=that value (line 1167). The GPIO fallback never uses spi_hz: bb_delay_us stays fixed at 2 and has no other assignment. Thus a lower requested maximum does not control GPIO timing. This is proven source-level behavior, not measured electrical overspeed or evidence that this mismatch caused the present default-byte response. It does not authorize changing arguments, timing or pins. The same review found no reachable byte-buffer overflow, pin-index mismatch or reversed bit order on the audited validated paths; absence of those static findings is not hardware validation. Sampling occurs late in the high phase, not at an edge-triggered sampling instant. No explicit inter-transfer CS-high minimum is enforced.

The returned true means only completion of the software loop; there is no controller ACK, waveform validation, transfer-error input or physical timeout check in this fallback. The identification guard goodix_dummy_data at lines 701-706 rejects any buffer whose every byte is either 00 or FF, including mixtures, not merely a uniformly all-zero or all-FF buffer. This is an extra plausibility policy relative to the retained version callback. Such a message alone cannot distinguish absent supply, lane role, reset, sampling or protocol faults; it does not prove all received bytes were identical. No implementation/test file was changed and this source audit does not complete step 7.

## Retained IC-info layout and validation audit (2026-11-14)

The independent binary audit completed on the same retained KO digest. The brl_get_ic_info body is .text+0x13b9c, size 4088, ending at 0x14b94. The operation-table relocation at .data+0x658 (brl_hw_ops+104) selects its CFI entry at 0x2bfe8; JUMP26 at 0x2bfec resolves to that body. Its read operation is ops+56. These are section-relative relocation facts, not a claim that this module was loaded on the K60.

The callback reads a two-byte little-endian length L from address 0x10068 when the inspected discriminator equals 4, otherwise 0x10070, then reads L bytes from that same address into a 1024-byte stack buffer. It rejects L>=1024, risk data and the mode-0 byte-sum/LE16 checksum. Up to three total attempts are made for read/risk/checksum failures, with usleep_range(5000,5100) after each failed attempt, including the final one; an oversized length increments the attempt count without that sleep. Conversion/count errors and missing mandatory addresses are not read-retried. Exhaustion/conversion failure returns -22. The buffer is cleared once before the retry loop, not before every attempt: an unread tail is initially zero, but after a shorter retry it can retain earlier-attempt bytes. The independently reread W[0:2] is copied into the output length; no equality comparison with the first L was found.

The wire prefix is 32 bytes: length, 16 version bytes, ten feature bytes and four one-byte channel/button/force quantities. Five subsequent lists each contain a u8 count followed by count u16 values, in scan-rate, mutual, self-TX, self-RX and stylus order. The callback enforces respective count maxima 5,10,10,10,8. Thus the wire misc start is P=37+2*sum(counts), from 37 through 123; do not confuse this variable wire cursor with the fixed decoded-output misc offset 123. The callback copies 142 misc bytes without padding insertion. The structural size 179+2*sum(counts) describes the consumed prefix/lists/misc; adding a trailing two-byte checksum would give 181..267 bytes for that layout. This arithmetic is not a length condition implemented by this callback and is not a measured live-record length.

Relocations, byte-preserving copies and named diagnostic consumers establish these misc-relative fields: +0 u32 command address, +18 u32 firmware-buffer address, +44 u32 touch-data address and +50 u16 point_struct_len. In particular .text+0x14494/0x1449c preserve misc bytes +32..47, and +0x14490/0x14498 preserve +48..63. The +48 u16 is copied and printed as the second Touch-Data quantity, but this module audit did not establish the name or meaning touch_data_head_len. The event path inspected by the auditor uses a fixed 26-byte pre-read and continuation from address+26 rather than dynamically sizing those reads from +48/+50. Do not turn a diagnostic quantity into a proven header length.

The retained module's diagnostics associate misc+52/+54 with panel-X/panel-Y labels; this conflicts with the active patch's blanket reserved1/reserved2 comment at lines 799-800. Diagnostic names do not prove the physical coordinate limits, raw units, or the installed controller's exact ABI. No ADT-axis change follows: the current 14400x32000 raw-coordinate convention remains unchanged. Mandatory nonzero checks in this callback cover command, firmware-buffer and touch-data addresses (.text+0x14b18..0x14b2c).

The KO does not visibly enforce a minimum complete prefix/misc length, a cursor bound against L-2, or P+142<=L. Some compiler checks protect the 1024-byte stack object instead. That is a reported-length validation limitation, not evidence of a reachable stack overflow or permission to copy the limitation. Conversely the active patch at lines 761-795 checks a minimum length, repeated length equality, checksum-excluded list bounds and at least 52 misc bytes before its field accesses. It does not impose the KO's five per-list maxima, requires the unproven +48 quantity to equal 8, requires +50 to equal 8, and does not mirror the KO's command/fw-buffer nonzero checks. These are policy/layout differences requiring a separately authorized source-coupled test, not an instruction to relax bounds or duplicate vendor behavior blindly.

This settles static offsets only. No valid live IC-info record was obtained; the captured candidate fails the earlier version-read plausibility guard, so neither +48 semantics nor these later parser policies explain that captured failure by themselves. Keep the old 0x10308/0x10309 question downstream. No touch code, tests, DT, arguments or device state was changed; steps 7 and 8 remain open.

## Consequence for the current driver and next test

The current patch's narrow statement that retained brl_power_on contains no confirm is consistent with this binary. An inference that the complete retained initialization path therefore needs no confirm is not: the caller invokes it. This corrects a source-comparison error, but does not establish that the omitted handshake causes this K60 failure, nor that adding it will produce touch input.

A later implementation proposal must keep the hypotheses separate: prove or qualify rail/physical-lane state first; specify a bounded AA echo transaction after reset settle; log transfer status, transmitted/returned bytes and retry count; compare valid version/IC-info checksums. Match the retained binary's nonfatal confirm-failure behavior only if that behavior is intentionally chosen; making the test fatal is a different policy and must not be called a faithful port. Preserve the current no-device/no-RSC restrictions. The old 0x10308/0x10309 offset remains downstream until a valid live frame exists.

Local static/host verification for such a separately authorized change must cover exact 8-byte echo; mismatches; negative transfer errors; bounded three-attempt behavior; no Berlin-A-only operations on D; and the chosen failure policy. Hardware acceptance still requires real increasing accepted report counts and visible response. This offline audit is evidence for step ③, not a completed repair, a step-⑦ artifact test, or step ⑧.

## Rebase and offline regression review (2026-11-14 11:06 +08:00)

The requested rebase completed locally: feat/touch-power HEAD e8e7dd1ce1d36225c935013b5b09406b432c2587 is based on fetched main 90d82717b075b0226048f3894c5c65330c7266d5. Backup ref backup/touch-before-main-20261114-1102 preserves the prior local HEAD 906e14d290627f5b8d73bdd05f3695cc3a2ddddb and the three existing Wi-Fi documentation commits. The owned pending documentation was recovered from retained stash 8ff4cc83000490422bb99370244e16966ff36afd; neither that stash nor unrelated recovery state was deleted. No rewritten history has been pushed.

Post-rebase byte comparisons passed: scripts/build-strict.sh and scripts/check-build-applied.py equal that main snapshot; board.toml, dts/ and patches/xnu/ equal the pre-rebase backup. No new touch implementation, boot argument or patch-series edit was introduced. Offline regression results: test-build-strict-gates.py 4 cases/0 failures; test-verify-boot-image.py 8 cases/0 failures; Lead PMIC synthetic host regression 16 cases/0 failures, compiled with KERNEL undefined. The strict-gate cases use throwaway stub repositories and verify that a red gate prevents kernel invocation; these are not kernel/firmware builds, real boot-image artifact checks or hardware tests. The PMIC fixture does not validate the live auxiliary-data schema, rail ACK or voltage.

## Post-rebase gate verdict (2026-11-14 11:18 +08:00)

The documentation checker passed 187 checks; the README table consistency check and git diff whitespace check passed. The standard secrets checker passed for 903 tracked files. Because this report was still untracked, its complete 99-line pre-verdict revision was also inspected separately against the same four credential-pattern categories, with zero hits; this is not a claim that the tracked-file scanner included it. The added verdict contains no credentials.

The explicitly scoped full registry run completed with exit 1: 70 registered entries, 24 distinct commands, 10 failures and 37 existing registry waivers. Failed entries were iron-2, iron-3, iron-4, iron-5, hard-5, hard-10, hard-11, hard-33, P-165 and P-166. Four failures concern the pending tracked documentation; the research/build gate remains incomplete, the porting and input-mirror checks remain red, and P-165/P-166 report three mirror-only Bluetooth probe patches (0507, 0508 and 0509). This audit does not waive any of them and did not run destructive mirror synchronization or a build to make them green.

Final inspected scope was three modified tracked documentation files plus this new report. Local HEAD remained e8e7dd1ce1d36225c935013b5b09406b432c2587; the local origin/feat/touch-power tracking ref remained 1b1e76d94bea0d262c170710589e5ff1df4cbe8e. No audit commit, rewritten-history push, kernel/firmware build, device/serial action or new MMIO access was performed. Publication and any implementation remain separate decisions after the unresolved gates and remote-history review.

## Completed follow-up validation (2026-11-14)

The required independent SPI/version audits and subsequent GPIO-source/IC-info audits have completed. Binary conclusions use the retained KO digest above; the GPIO reviewer inspected only the stated active-patch digest. After recording all findings, the documentation checker again passed 187 checks; README table consistency and git diff whitespace checks passed. The standard secrets check passed for 903 tracked files. The complete 189-line pre-verdict revision of this untracked report (SHA-256 ae1265ecba44e332da1605663bba5c73afeb7abe586fde65f5c6897aa0fb1e49) was separately read through OPS and scanned in memory against the same four credential-pattern categories with zero hits; this replacement verdict contains no credentials. No background work remains required for these audits.

Protected-input comparison again passed against backup/touch-before-main-20261114-1102 for board.toml, dts/ and patches/xnu/. The two strict-build/P-165 scripts still equal main snapshot 90d82717b075b0226048f3894c5c65330c7266d5. Scope remains three modified tracked documentation files and this new report. No implementation/test file, kernel/firmware build, device/serial action, MMIO, commit or push was performed. The full registry was not rerun in this follow-up; its explicitly recorded 11:18 verdict remains a failed run, not an all-green waiver. Steps 7 and 8 remain false.

## Earlier gate history (not the post-rebase verdict)

At the 2026-11-14 04:32 +08:00 registry run, the worktree was feat/touch-power at 1b1e76d94bea0d262c170710589e5ff1df4cbe8e, equal to origin/feat/touch-power. The documentation gate passed 187 checks; the README table check and diff whitespace check passed; the read-only mirror check reported 726 identical inputs. The standard secrets gate passed for 890 tracked files, but did not include this still-untracked report; review its content separately before staging/publication.

The full rules registry failed 9 entries: iron-2, hard-5, hard-10 and hard-11 for pending tracked documentation; iron-3 for incomplete eight-step research; iron-4 and hard-33 for porting-gate failures; P-165 and P-166 for the current applied-build record. These failures are not waived by this report. The evidence files remain uncommitted/unpushed pending the required resolution or authorized written waivers. No touch driver, firmware, DT, protected blob, boot argument or patch-series change was made, and no build or hardware action was performed for this audit.
