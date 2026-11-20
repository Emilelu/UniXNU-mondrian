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

The same six rows are in missing-storage-baseband.tsv for scripted use.
