# The storage and baseband slice of the 95-item prelink gap

Read-only inventory. It lists unpaired targets that the reports attribute to storage
bundles and to QcomBaseband. It does not pair, bind or close a symbol.

## Inputs

| item | value |
|---|---|
| report | /opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/kernel/kernel.json (17,750 B) |
| output | /opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/kernel/kernel.macho (93,061,120 B; candidate_sha256 6b870f3606e52cb11a9f41e16eb378111e4cf04770d4ee61b1f05593102d7f27) |
| map | /opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/kernel/kernel.map.json (3,027,584 B) |
| reference | scripts/xnu-fileset-reference/mach.release.bcm2837.unstripped.noctf (reference_sha256 71d351ceaa0d032f9c554195278e58a35ee3983a9876fde39987af225e1ddc05) |
| missing | 21 bundles / 95 items / 19 distinct addresses |
| stubbed | 25 bundles / 205 items |
| closure_pointers_unmapped | 95 |
| stub_symbol | _unixnu_fileset_unmapped |
| missing_address_space | output collection |

The 95 report is the LTO reference run. The CI report 44518998961 is the non-LTO run
(28 bundles / 650 items / 133 distinct); it is used only for the delta in the last
section.

## What the two classes mean

/mnt/e/hackios/k60-gates/docs/research/ios27/PRELINK-CLOSURE.md:63-68 splits the
leftovers into two classes:

| class | addresses / items | treatment |
|---|---|---|
| data, examples __ZN*10gMetaClassE | 19 / 95 | rebind() leaves the Apple address when it finds no pair; 13 land in unrelated local segments, 6 outside every segment; AMFI owns two |
| functions | 131 / 205 | redirected to _unixnu_fileset_unmapped, which prints the call site |

The LTO report has exactly 95 missing items and 205 stubbed items. Therefore every
address in its missing table is in the data class, and the stubbed table is the
function-site class. This report follows the note's class name gMetaClass, but it
does not claim that a particular address is a particular class's gMetaClass: the
collection has no symbol for any of the six addresses below, and kernel.map.json has
no data or functions entry for them either.

## The six storage addresses

All six are in the output collection's __DATA_CONST, not in __TEXT_EXEC or
__PRELINK_TEXT. The root segment ranges used for that check are:

| segment | vmaddr | size |
|---|---|---|
| __PRELINK_TEXT | 0xfffffff00700c000 | 0xdc4000 |
| __DATA_CONST | 0xfffffff007dd0000 | 0x618000 |
| __TEXT_EXEC | 0xfffffff008434000 | 0x3050000 |
| __DATA | 0xfffffff00b6b0000 | 0x2f0000 |

| address | bundle carrying the item | class | output segment | also referenced by |
|---|---|---|---|---|
| 0xfffffff007e87df8 | com.apple.iokit.IOStorageFamily | data/global (gMetaClass class) | __DATA_CONST | com.apple.iokit.IOHIDFamily; com.apple.iokit.IOReportFamily; com.apple.iokit.IOSurface |
| 0xfffffff007e89b80 | com.apple.iokit.IOStorageFamily | data/global (gMetaClass class) | __DATA_CONST | com.apple.driver.AppleARMPlatform; com.apple.driver.AppleM2ScalerCSCDriver; com.apple.driver.AppleMobileFileIntegrity; com.apple.filesystems.apfs; com.apple.iokit.IOAVFamily; com.apple.iokit.IOAudio2Family; com.apple.iokit.IOGPUFamily; com.apple.iokit.IOHIDFamily; com.apple.iokit.IOMobileGraphicsFamily; com.apple.iokit.IOSurface; com.apple.security.sandbox |
| 0xfffffff007e89b98 | com.apple.iokit.IOStorageFamily | data/global (gMetaClass class) | __DATA_CONST | com.apple.driver.AppleARMPlatform; com.apple.driver.AppleARMWatchdogTimer; com.apple.driver.ApplePMGR; com.apple.filesystems.apfs; com.apple.iokit.IOAVFamily; com.apple.iokit.IOHIDFamily; com.apple.iokit.IOMobileGraphicsFamily; com.apple.security.sandbox |
| 0xfffffff007e89ba0 | com.apple.iokit.IOStorageFamily | data/global (gMetaClass class) | __DATA_CONST | com.apple.driver.AppleARMPlatform; com.apple.driver.AppleM2ScalerCSCDriver; com.apple.driver.AppleMobileFileIntegrity; com.apple.filesystems.apfs; com.apple.iokit.CoreAnalyticsFamily; com.apple.iokit.IOAVFamily; com.apple.iokit.IOAudio2Family; com.apple.iokit.IOGPUFamily; com.apple.iokit.IOHIDFamily; com.apple.iokit.IOMobileGraphicsFamily; com.apple.iokit.IOSurface; com.apple.security.AppleImage4; com.apple.security.sandbox |
| 0xfffffff007e89ba8 | com.apple.iokit.IOStorageFamily | data/global (gMetaClass class) | __DATA_CONST | com.apple.driver.AppleARMPlatform; com.apple.driver.AppleARMWatchdogTimer; com.apple.filesystems.apfs; com.apple.iokit.IOAVFamily; com.apple.iokit.IOAudio2Family; com.apple.iokit.IOHIDFamily; com.apple.iokit.IOMobileGraphicsFamily; com.apple.iokit.IOSurface |
| 0xfffffff007e8a9e0 | com.apple.iokit.IOStorageFamily | data/global (gMetaClass class) | __DATA_CONST | com.apple.driver.AppleARMPlatform; com.apple.driver.ApplePMGR; com.apple.driver.IODARTFamily; com.apple.filesystems.apfs; com.apple.iokit.CoreAnalyticsFamily; com.apple.iokit.IOAVFamily; com.apple.iokit.IOCryptoAcceleratorFamily; com.apple.iokit.IOGPUFamily; com.apple.iokit.IOHIDFamily; com.apple.iokit.IOMobileGraphicsFamily; com.apple.iokit.IOSurface; com.apple.security.sandbox |

The six are six items and six distinct addresses: 6.3% of the 95 items but 31.6% of
the 19 distinct data addresses. They are not storage-private. One address is also
referenced by three other bundles; the other five are referenced by eight to thirteen
other bundles. Naming any of them as a storage class without a symbol or a
site-level binding would be a guess.

kernel.map.json has 16,899 matched functions and 781 matched data entries; none of
the six addresses is a key in either table. That is why the class column says
data/global rather than a class name.

## QcomBaseband

Zero. There is no QcomBaseband bundle in the LTO report, and none in the CI report
either.

- board.toml:361 selects only ArmDTPlatform, ArmCpu, XnuPrelink and NativeUfs for
  ios-27.0.1-24A446. QcomBaseband is not in that list.
- /mnt/e/hackios/UniXNU/components.toml:563-581 is the QcomBaseband component: a
  bridge for the SC7180 IPA v4.2 path, with board dependencies for modem boot,
  firmware, power, DMA, GLINK/QRTR and rmtfs. Its verified_devices list is empty.
- docs/plans/DOCS-DRIVERS-ALL.md:459 records the K60 decision: QcomBaseband is not
  selected because the first version has no cellular requirement.

A QcomBaseband pairing list needs a build that selects the component. Stage 0 does
not, so the 95-item table cannot contain a QcomBaseband row. Reading zero as "no
baseband risk" would be wrong for any later build that does select it.

## AppleEffaceableStorage

The LTO report has zero missing items for this bundle and two stubbed sites. The CI
report has two missing addresses, 0xfffffff007e89620 (shared with IOStorageFamily)
and 0xfffffff00b793e60 (both in __DATA), for 3 items, plus 33 stubbed sites / 34
references. The LTO reference resolved both missing addresses. The two stubbed
sites are function sites, not data targets.

## CI 44518998961 versus the LTO report

| report | missing bundles / items | distinct | IOStorageFamily | AppleEffaceableStorage | QcomBaseband |
|---|---|---|---|---|---|
| LTO 95 | 21 / 95 | 19 | 6 / 6 | 0 / 0 | 0 |
| CI 44518998961 | 28 / 650 | 133 | 16 / 18 | 2 / 3 | 0 |

The CI set has 17 distinct storage addresses (16 IOStorageFamily plus one
AppleEffaceable-only). The LTO set has 6. Eleven CI-only addresses were resolved by
the LTO reference: 0xfffffff007dec770, 0xfffffff007e88578, 0xfffffff007e89620,
0xfffffff007e89b78, 0xfffffff007e89b88, 0xfffffff007e8b7d0, 0xfffffff00b792da8,
0xfffffff00b792dd0, 0xfffffff00b793e60, 0xfffffff00b7944c0, 0xfffffff00b794760.
The six retained are exactly the six above. Ten of the resolved addresses are
IOStorageFamily; 0xfffffff00b793e60 is the AppleEffaceable-only one.

The six retained addresses are all shared with at least three other bundles; the
LTO reference resolved the other ten IOStorageFamily addresses and the
AppleEffaceable-only one. That is consistent with the six being common IOKit data
rather than storage-private data, but it is not proof of identity.
The two reports also differ in candidate size and reference, so this delta is
directional, not a controlled experiment.

## Reproduce the filter

    import json, pathlib
    r = json.loads(pathlib.Path('/opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/kernel/kernel.json').read_text())
    for bundle, values in sorted(r['missing'].items()):
        if 'Storage' in bundle or 'Qcom' in bundle or 'Baseband' in bundle:
            print(bundle, len(values), sum(values.values()), sorted(values))

The expected output is one IOStorageFamily line (6 6, the six addresses above) and
no QcomBaseband or Baseband line. The segment table comes from the root Mach-O
LC_SEGMENT_64 records; llvm-objdump --macho --private-headers shows the same ranges.

## Limits

- This inventory does not close prelink-map-unresolved. The storage slice is 6 of
  95 items, all data; there is no function target in it.
- It does not name the six symbols, does not bind them, and does not prove that any
  of them is a gMetaClass object. The next evidence needed is a symbol name or a
  site-level binding with evidence, for example through the kit's
  fixtures/fileset-*-symbols.json extension point.
- It does not change check-ios27-storage-preflight.py or
  docs/research/storage/ROUTE-D-PLAN.md. Storage and route-D stay frozen.
- Hardware is not involved.

The six addresses are in missing-storage-baseband.tsv for scripted use; that file carries addresses and bundle owners, not class names.

## Candidate pairing: why the six stay unnamed

This section tries the pairing the 95-item note leaves open. The answer is negative:
none of the six can be paired with a class, and the evidence says they are not
IOStorageFamily-local classes at all.

### Which kernel.macho was readable

The LTO output named in the input table, /opt/k60/.../kernel.macho, is root:root
0600 and cannot be read by this session. The readable CI artifact 44518998961
kernel.macho (93,077,504 B, candidate_sha256 4e57f1822d352022b2a825f93ac41d653a149c63872a6cca8e42d505a0bb9f86)
contains the same six addresses and was used for the symbol and byte checks below.
The LTO output may differ in symbols; this section does not claim otherwise.

### Conclusion: the candidates converge, but no name is unique

Under two premises - the readable artifact has no symbol table, and the six byte
images are not OSMetaClass headers - the candidates can only converge to the
base-class set OSObject, IOService, IORegistryEntry, OSDictionary, OSSymbol,
OSString and IOMemoryDescriptor (with OSMetaClass, OSCollection, OSArray, OSData,
OSNumber, OSSet and OSIterator also possible in principle). No row can be
uniquely named. The family's own classes are excluded: their gMetaClass objects
would sit in the family's own __DATA_CONST 0xfffffff008313f98 + 0x5c40, while all
six addresses are in the root __DATA_CONST 0xfffffff007dd0000 + 0x618000. The six
are shared with three to thirteen non-storage bundles, so a storage-private class
cannot explain them; a kernel base class can.

The owner field in kernel.json is the bundle that carries the reference, not the
bundle that defines the target. That distinction is why the bundle-local
__DATA_CONST test is the decisive one: all six addresses fail it, and no symbol
in the readable artifact names them.

### Why no kernel symbol names them

The CI artifact's com.apple.kernel entry has LC_SYMTAB nsyms 221,793. llvm-nm on
the normalized child prints 27,666 defined symbols. Exactly five are gMetaClass
symbols, all unrelated template classes:

- DescriptorMixedData10gMetaClassE at 0xfffffff00b331990
- N13OSValueObjectIPFvjiPKvjPvEE10gMetaClassE at 0xfffffff00b365544
- ZN13OSValueObjectIiE10gMetaClassE at 0xfffffff00b282890
- regateTestTypeE10gMetaClassE at 0xfffffff00b3e4b4c
- SValueObjectI14PMAssertStructE10gMetaClassE at 0xfffffff00b2fbea8

None is at one of the six addresses, and none is IOService, IORegistryEntry,
OSObject, OSDictionary, OSSymbol, OSString or IOMemoryDescriptor. The
com.apple.iokit.IOStorageFamily entry has LC_SYMTAB nsyms 0. There is no same-named
__ZN...10gMetaClassE in the readable kernel.macho to point at, so the VA and size
columns cannot be filled with a real symbol.

llvm-nm also warns that sizes with --print-size for Mach-O files are always zero.
Mach-O nlist_64 has no size field. The only size available is the fixed OSMetaClass
layout size, 40 bytes, from
E:/hackios/UniXNU/out/mondrian/ios-27.0.1-24A446/mondrian_ios27/tree/.cache/xnu-work/libkern/libkern/c++/OSMetaClass.h:1037-1064
(reserved at 8, superClassLink at 16, className at 24, classSize at 32,
instanceCount at 36). That is not the size of a class's instances and is not a
symbol size.

### Why the object bytes do not name the class

The six addresses do not hold a readable OSMetaClass header in either artifact.
In the CI artifact 0xfffffff007e87df8 is all 0xff, 0xfffffff007e8a9e0 is zero, and
the other four hold encoded words such as 0x1000000478d818. The Apple 24A446
kernelcache holds the same encoded words. At 0xfffffff007e89b80 the five words are
0x1000000478d818, 0x1000000478d9e8, 0x10000004790030, 0x10000004790498 and
0x1000000478db00. If this were an OSMetaClass object, classSize at +0x20 would be
0x478db00, which is not a plausible class size; className at +0x18 would be
0x10000004790498, which does not read as an OSSymbol. The constructor that sets
classSize and className is OSMetaClass.cpp:574-606; it runs at boot, not in the
file. The static object is therefore uninitialized or fixup-encoded here, and the
class name is not recoverable from these bytes.

### Verdict

No candidate pair exists in the readable evidence. The six addresses satisfy the
8-byte alignment criterion, fail the bundle-__DATA_CONST criterion, and cannot
satisfy the vtable/OSMetaClass-offset criterion because they are not class headers.
The evidence is consistent with shared base-class data targets and does not support a storage-private class; the exact target remains unproven. They must not
be used to derive a storage class ABI, and they do not change the 190-slot table or
the PENDING-safe storage preflight. They also do not close prelink-map-unresolved.

### F3 preflight: what moves it off PENDING

The F3 storage preflight stays PENDING. It can become PASS only when one of two
things exists: (a) a symbol-bearing 24A446 artifact, even a third-party extracted
OSMetaClass list, that maps the six addresses to class names; or (b) kit-side
class-name pairing (the Lead's work). A guessed name, a name without the address,
or an address without a symbol does not move it; this report does not claim either
condition is met.

## Build 20: the five IOStorageFamily stub targets

Build 20 (2026-11-21) is a separate measurement from the CI artifact. The
kernel.macho hash is 652237c6bf54 (32 fileset entries, 0 loader violations) and
the boot image is 5c060f27. The blocker text in
E:/k60-work/scratch/msg-b20.txt names three unpinned data targets in three
bundles and 203 stubbed function sites in 25 bundles; the task statement says
205 stubbed. The pair is not a discrepancy: facts.json has 131 stubbed targets
whose 205 reference sites (sum of items) group into 203 distinct bundle-target
pairs (sum of bundles). The blocker's 203 is the pair count and the task's 205 is
the reference count, both from the same facts.json and sites_all.json. Neither
number is silently interchanged. The raw build-20 kernel.json is root:root 0600, so the five
addresses below were read from the Lead's
E:/k60-work/scratch/stubs/facts.json, which classify.py generated from that
kernel.json. facts.json has 131 targets; these five are its IOStorageFamily set.

The five are all starts of com.apple.kernel __TEXT_EXEC,__text functions. The
other caller column names the second bundle that imports the same target; the
site section is the section of the importing slot, not of the target.

| target | size and section | other caller | site section | classification | stage 0 |
| --- | --- | --- | --- | --- | --- |
| 0xfffffff00ad71480 | 0x38 B, __TEXT_EXEC,__text, after _qbt_transport_active | AppleEffaceableStorage | __auth_got | shared CRC32 table loop; not a class | no |
| 0xfffffff00b2a7e74 | 0x11c B, __TEXT_EXEC,__text, after IOService::_ClaimSystemWakeEvent_Invoke | IOHIDFamily | __auth_got | IOService-family _Invoke-shaped method; our missing IOService variant | no |
| 0xfffffff00b2a7f90 | 0x11c B, same shape and neighbour | IOHIDFamily | __auth_got | IOService-family _Invoke-shaped method; our missing IOService variant | no |
| 0xfffffff00b335fe0 | 0x68 B, __TEXT_EXEC,__text, after IOSubMemoryDescriptor::makeMapping | IOGPUFamily | __const | IOMemoryDescriptor / IOSubMemoryDescriptor variant | no |
| 0xfffffff00b3360a8 | 0x80 B, __TEXT_EXEC,__text, after IOSubMemoryDescriptor::prepare | IOGPUFamily | __const | IOMemoryDescriptor / IOSubMemoryDescriptor variant | no |

### What the disassembly says

0xfffffff00ad71480 is a CRC32 table loop. It starts with bti c and cbz x2, sets
w8 to the complement of w0, loads bytes from x1 one at a time, looks each byte
up in a 32-bit table at 0xfffffff007013870, and folds the result with eor and
lsr #8. It ends with mvn w0,w8 and ret. This is a shared checksum utility, not
a class object and not a storage method. The readable kernel.map.json already
names _z_crc32 at 0xfffffff00b29a50c (native 0xfffffff007a7029c), so a CRC32
facility is not storage-private either.

0xfffffff00b2a7e74 and 0xfffffff00b2a7f90 are two 0x11c-byte functions with
the IOService _Invoke shape. Each checks [x0+0x20] == 2, reads [x0+0x18],
tests [x0+0x10] >= 0x6c and [x0+0x14] >= 0x3c, calls vtable+0x38 through
blraa, compares the result with 0xfffffff00b794498, writes 60 to [x20+4], and
stores fields at +0x24, +0x1c and +0x34. The exact method names are not in the
map; the neighbour is the IOService::_ClaimSystemWakeEvent_Invoke family. They
are IOService methods that the source does not provide, not IOBlockStorageDevice
members.

0xfffffff00b335fe0 is 0x68 bytes. It calls 0xfffffff00b326da4, loads
[x21+0x60], authenticates vtable+0xf8 and tail-calls through braa.
0xfffffff00b3360a8 is 0x80 bytes. It calls 0xfffffff00b3315a0, calls
vtable+0xa0, compares and updates [x8+0x28] and [x8+0x20], and returns 1 or the
field. Their neighbours are IOSubMemoryDescriptor::makeMapping and ::prepare.
They are IOMemoryDescriptor-family methods, not storage-driver methods.

### Which class, and which is Apple's IOBlockStorageDevice family

The five split as two IOService methods, two IOMemoryDescriptor-family methods
and one shared CRC32 utility. None is an IOBlockStorageDevice-family member.
The family's 190-slot table is a separate object in
docs/engineering/ios27-storage-vtable.tsv; none of these five addresses appears
in that table or in IOS27-STORAGE-VTABLE.md (zero grep hits). The 190-slot
table therefore does not gain a row, and these five do not derive a storage
class ABI.

Stage 0 does not reach them. They are import slots in IOStorageFamily
__auth_got and __const (plus the named other caller). The slots are fixed up
when the kext loads, and IOStorageFamily is not loaded before the stage-0
panic. IOService and IOMemoryDescriptor exist earlier, but these particular
stubs are not executed until the kext loads. If F3 loads IOStorageFamily they
become load-time reachable; that is not stage 0.

### Verdict

The five are shared base-class and utility dependencies of IOStorageFamily, not
the storage class the family needs and not Apple's IOBlockStorageDevice family.
The storage blocker remains PENDING and prelink-map-unresolved is not closed by
this analysis. No name is guessed for any of the five.
