# Why three build-20 targets are not reachable before `console_init` (static evidence)

Status: offline mechanism note, 2026-11-21. Branch `feat/xnu27-data-gate`.
No build, boot, device access or kit change was made for this note.

## Short answer

Build 20 reports three unresolved targets: one leaf assigned to
`com.apple.driver.AppleARMWatchdogTimer`, and two zero-fill globals assigned to
`com.apple.iokit.IOHIDFamily` and `com.apple.security.sandbox`. They are data,
not entry points. The whole file-backed root code is 65,126,400 bytes
(16,281,600 instructions); a scan for `ADRP+ADD`, `ADRP+LDR`, `ADR`, direct
`B`/`BL`, exact 64-bit data words, and root chained-fixup rebases finds no
reference to any of the three.

XNU's `console_init()` is at `osfmk/kern/startup.c:585`. The first IOKit entry
in the bootstrap thread is `PE_init_iokit()` at `:806`, after console. All three
owners are kexts, so none of their code runs before console either. Under the
scan coverage below, the static reachability scan is zero, all three are data
rather than entry points, and before `console_init` only XNU core runs. The
ledger reason should therefore say
`三者在 console 前不可达（静态证据），残余=间接构造未证`. This is a statement
about static reachability, not a claim that an indirect construction can never
call them.

This is a reachability result, not a loadability result. `mapping_complete` and
`loadable` stay false; a loader or prelink consumer that rejects an unresolved
binding can still fail before any C code runs. The two questions must stay
separate.

## 1. Artifact and binding

The evidence is the build-20 output pair read at 06:33 on 2026-11-21:

    /opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/kernel/kernel.macho
      93,061,120 B
      sha256 652237c6bf5476f216298df9ac71044ec51aa2349c3c31871e822810e163a19e

    /opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/kernel/kernel.json
      14,078 B
      sha256 7569eb24e61d3d833ec508b5318beff04676f6a38317ff4df81c080d3b678d62

At scan time the file was uid 1000 and readable. The path was replaced by a
root-owned artifact with mtime 14:12 after the scan, so this note binds to the
hashes above, not to whatever now sits at the same path. The report records
`candidate_sha256: dee01c54a73edf594bbe866ae020cb3331d31afe3edc4616b1a6fc0a34fbaad0`,
which is not the on-disk hash; both are 93,061,120 B, and the two agree on the
three target addresses and on the segment layout, but the exact relation between
the report's candidate field and the final file is not established here. Section
8 records the writer facts and what would prove that relation.

`kernel.json` records:

    missing  3 bundles / 3 targets / 3 reference records
             0xfffffff007044478  com.apple.driver.AppleARMWatchdogTimer
             0xfffffff00b72fce8  com.apple.iokit.IOHIDFamily
             0xfffffff00b739538  com.apple.security.sandbox
    stubbed  25 bundles / 203 distinct targets / 205 reference sites
    closure_pointers_unmapped 3
    mapping_complete false
    loadable false
    runtime_qualified false
    early_security_init  com.apple.driver.AppleMobileFileIntegrity
                         0xfffffff00921000c

The `missing` map is `bundle -> {target: count}`; it names the owner and the
target, but not the referring instruction or slot. The scan below therefore
looks for the target itself, not for the count.

## 2. Where the three targets land

All addresses are output-collection addresses.

| target | report owner | build-20 placement | bytes at the VA | kind |
| --- | --- | --- | --- | --- |
| `0xfffffff007044478` | `com.apple.driver.AppleARMWatchdogTimer` | root `__PRELINK_TEXT,__text`; file offset `0x40478` | 16 zero bytes, then 16 `0xff` bytes | data leaf; not a function prologue |
| `0xfffffff00b72fce8` | `com.apple.iokit.IOHIDFamily` | root `__DATA`; child `com.apple.kernel` `__DATA,__common` at `0xfffffff00b6f9000 + 0xbef90`, `S_ZEROFILL`; file offset `0x472bce8` | zero | zero-fill global |
| `0xfffffff00b739538` | `com.apple.security.sandbox` | root `__DATA`; same `__DATA,__common`; file offset `0x4735538` | zero | zero-fill global |

The leaf is called a leaf in the report; in build 20 its address is in the
merged root `__PRELINK_TEXT` segment, not in the child
`AppleARMWatchdogTimer`'s emitted `__TEXT,__cstring`
(`0xfffffff00717fae0 + 0x1a77`) or its `__DATA_CONST,__const`
(`0xfffffff007f0c4d0`). The bytes are `00..00 ff..ff`: this is not an
instruction sequence a caller can enter as code.

The two globals are assigned by the report to IOHIDFamily and sandbox, but both
VAs land in the kernel entry's `__DATA,__common` zero-fill region
(`0xfffffff00b6f9000 + 0xbef90`). The kernel entry's `__DATA` is only
`0x4c000` bytes file-backed, so these VAs are beyond its file-backed part; the
file contains zeros there. A zero-fill global has no file initializer to
mis-bind. The owner-side reference, whatever its form, is not a value stored in
the target.

## 3. Scan range and method

The scanner is a read-only scratch script at
`E:/k60-work/scratch/scan-console-targets.py`; it is not a repository tool.
It parses the root Mach-O and all fileset children, keeps section headers, and
scans three file-backed root ranges:

| root segment | VA range | file bytes | instructions |
| --- | --- | ---: | ---: |
| `__TEXT` | `0xfffffff007004000 + 0x8000` | 32,768 | 8,192 |
| `__PRELINK_TEXT` | `0xfffffff00700c000 + 0xdc4000` | 14,434,304 | 3,608,576 |
| `__TEXT_EXEC` | `0xfffffff008434000 + 0x3050000` | 50,659,328 | 12,664,832 |
| **total** | | **65,126,400** | **16,281,600** |

These are the whole file-backed root executable ranges. The collection has 34
sections marked executable; every one lies inside these ranges. The child
`__KLD,__text` section at `0xfffffff00b480000 + 0x1b14` has flags 0 but its
bytes lie inside root `__TEXT_EXEC` and are scanned anyway.

Instruction decode:

* `ADRP`: mask `0x9F000000 == 0x90000000`; sign-extend the 21-bit immediate;
  page = `(pc & ~0xFFF) + (imm << 12)`.
* For each `ADRP`, look forward up to 12 instructions. Stop at any control-flow
  instruction or another `ADRP`.
* `ADD` immediate: mask `0x7F000000 == 0x11000000`, with `sf=1`, `op=0`,
  `S=0`; use `imm12`, shifted by 12 when bit 22 is set, with the same base
  register.
* `LDR` unsigned offset: mask `0xFFC00000 == 0xF9400000`; use
  `imm12 * 8`, with the same base register.
* `ADR`: mask `0x9F000000 == 0x10000000`; target = `pc + imm21`.
* Direct `B`/`BL`: mask `0x7C000000 == 0x14000000`; sign-extend the 26-bit
  immediate; target = `pc + (imm << 2)`.
* The common-write check stops a window when a normal instruction form writes
  the `ADRP` register. A miss can only widen the window; it cannot hide a
  matching `ADD`/`LDR`.

The data scan reads every 8-byte aligned 64-bit word in every root segment and
compares it with the three exact target values.

Chained fixups are decoded separately from the root
`LC_DYLD_CHAINED_FIXUPS` (`dataoff 87,801,856`, `datasize 1,412`) at image base
`0xfffffff007004000`. The format-8 word uses target bits 0-29 and next bits
51-62; the target address is `image_base + target`. The child entries expose no
separate fixup blob in this collection; the root blob is the only one.

## 4. Result

| channel | count | hits |
| --- | ---: | ---: |
| `ADRP+ADD` / `ADRP+LDR` | 778,823 `ADRP` | 0 |
| `ADR` | 120,261 | 0 |
| direct `B`/`BL` | 319,458 `B` + 688,334 `BL` | 0 |
| exact 64-bit data words | every aligned word in all root segments | 0 |
| root chained-fixup rebases | 48,488 targets / 1,111 distinct | 0 |

Per text range: `__TEXT` had 8,192 instructions, 0 `ADRP`, 14 `ADR`;
`__PRELINK_TEXT` had 3,608,576 instructions, 14,593 `ADRP`, 119,657 `ADR`;
`__TEXT_EXEC` had 12,664,832 instructions, 764,230 `ADRP`, 590 `ADR`.
The total is 16,281,600 instructions, 778,823 `ADRP`, 120,261 `ADR`, zero
target hits. The data scan and the fixup decode are independent checks, not
substitutes for the instruction scan. Format-8 fixup decoding can be noisy;
the 48,488/1,111 counts are decode output, and the zero is used only as a
supporting check.

## 5. Startup order

The XNU 27 source used by this build is under
`/opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/tree/.cache/xnu-work`.
The relevant lines in `osfmk/kern/startup.c` are:

| line | event |
| ---: | --- |
| 523 | `kernel_bootstrap()` entry |
| 584-585 | `kernel_bootstrap_log("console_init")`; `console_init()` |
| 629-630 | `kernel_bootstrap_log("code_signing_init")`; `code_signing_init()` |
| 678 | `kernel_thread_create(kernel_bootstrap_thread, ...)` |
| 707 | `kernel_bootstrap_thread()` entry |
| 805-806 | `kernel_bootstrap_log("PE_init_iokit")`; `PE_init_iokit()` |
| 926 | `bsd_init()` |

`console_init()` is before code signing, before the bootstrap thread is created,
and before the only IOKit entry in that thread. Prelinked kexts do not execute
from their place in the collection before IOKit is initialized; their startup
is reached from `PE_init_iokit()` at `:806`. The report's only
`early_security_init` hook is AppleMobileFileIntegrity at
`0xfffffff00921000c`; none of the three owners has an early hook.

The three owners are `AppleARMWatchdogTimer`, `IOHIDFamily` and
`security.sandbox`, all kexts. Therefore:

1. Before `:585`, only XNU core startup code runs.
2. That core code has no `ADRP+ADD`/`ADRP+LDR`, `ADR`, direct branch, exact
   data word or chained-fixup rebase to any of the three targets.
3. After `:585` but before `:806`, console is already initialized; a kext
   fault there is not a pre-console fault.
4. Kext code that could consume an owner-side binding first runs at or after
   `:806`.

So the three addresses are not reachable by an instruction fetch or data load
from kernel or kext code before `console_init`. They are also not functions
whose prologue could be entered: two have no file-backed initializer and one has
`00..00 ff..ff` at its VA.

## 6. What this does not prove

The scan does not decode `MOVZ`/`MOVK` synthesis, arbitrary base-plus-offset
arithmetic from a different pointer, indirect dispatch through a register, or a
runtime registration that computes the address. It also does not prove that the
bootloader, the prelink consumer or a loader-side binding pass accepts the
image. The report already says `loadable: false`; this note does not change
that.

The report's `missing` value is 1 per target, but it carries no referring
instruction or slot address. If that 1 is a loader binding record rather than a
materialized site, it is consumed when the owner kext loads, after console. If
it is a site, the scan did not find it in the forms above; that would be a
separate discrepancy for the kit owner to explain. The reachability conclusion
does not depend on which reading is true, because the owner kext is not running
before console in either case.

## 7. Consequence

For build 20, these three targets are not viable causes of a stop before
`console_init`. If build 20 stops before the console milestone, the next places
to look are the loader/boot chain and early XNU, not these three addresses. The
prelink map is still incomplete and the image is still not loadable; closing
that is a separate problem (a symbol-bearing same-build artifact, or an explicit
policy decision), not something this note claims to solve.

No class name, symbol name or binding target was guessed. No kit, kernel.json,
preflight entry or shared tree was modified.

## 8. Unresolved evidence: the candidate hash is not the final hash

The report and the file disagree on the digest:

    report candidate_sha256  dee01c54a73edf594bbe866ae020cb3331d31afe3edc4616b1a6fc0a34fbaad0
    file sha256              652237c6bf5476f216298df9ac71044ec51aa2349c3c31871e822810e163a19e
    both bytes               93,061,120

The two agree on the three target addresses and on the segment layout, but the
report's field is not the final file hash. That is an unresolved binding, not a
rounding difference.

The kit writer makes the mismatch informative. In
`kits/NativePrelink/emit_prelink.py`:

* `:341` sets `candidate_sha256=hashlib.sha256(output).hexdigest()`;
* `:344` returns `bytes(output), report`;
* `:363` receives `image, report = emit(...)`;
* `:367` writes `args.output.write_bytes(image)`;
* `:368` writes the sibling `.json` report.

There is no copy, strip or transcode between the buffer that is hashed and the
buffer that is written. If this exact kit version produced both files in one
run, `candidate_sha256` would equal the file hash. It does not, so at least one
of these is true: a later stage rewrote `kernel.macho`; the report came from a
different producer or kit version; or the two files are not a pair from the same
run. The note does not choose among them.

What would prove the relation:

1. Record the kit HEAD and the exact producer command, rerun `emit()` from the
   same inputs, and compare the returned digest with the file digest.
2. Add a post-write check after `:367`: hash `args.output.read_bytes()` and
   compare it with `report['candidate_sha256']`. If that check fails, the file
   was rewritten after `emit()`.
3. Identify every later stage that touches `kernel.macho` (strip, sign, patch,
   copy) and its log line; a same-size rewrite still changes the digest.
4. Compare `candidate_bytes` and `original_executable_sha256` with the final
   file; size agreement is not byte agreement.

This is the P-294 instance: the path was replaced in place at 14:12, so the
evidence must bind to the hash, not to the path. Until the relation is shown,
the three-target scan binds to `652237c6...`, not to `candidate_sha256`.
