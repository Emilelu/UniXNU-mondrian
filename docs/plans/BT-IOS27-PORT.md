# K60 Bluetooth on iOS 27 (feat/ios27)

Status: **work in progress, not built, not flown.** The source stack is carried on
local branch `feat/bt-ios27-port` of the xNekom fork. No kernel was built from
this branch and no device action was taken.

## 1. Target

| Item | Value |
| --- | --- |
| Device repository | `xNekom/UniXNU-mondrian`, branch `feat/ios27` |
| Base commit | `96e07b135231dab0811f47e34b0a3be4fc515bdd` |
| OS profile | iOS 27.0.1, build 24A446, iPhone 16 Pro Max (iPhone17,2), arm64e |
| XNU | xnu-12377.121.6, commit `ac9718fb1af618d5ce8678d0dc6e8a58f252216f` |
| Hardware | Redmi K60 (mondrian, SM8475), QCA6490 Bluetooth over QUPV3_2 SE20 UART |

The iOS 16.6.1 / 20G81 line remains the only hardware testbed for the kernel and
firmware download. iOS 27 cannot yet reach a Bluetooth test point: the fork's
`ios27-arm64e` area is at status `planned` and covers F0-F4 only (PAC probe,
OS profile and kernel, prelink to `bsd_init`, PongUfs 27 ABI, panel/touch).

## 2. Source split

The Bluetooth work has two layers:

1. **Driver layer, OS-version independent.** `bsd/dev/qbt_k60.c`,
   `bsd/dev/qbt/*`, the UART/QUP engine, the firmware TLV downloader and the
   GIC routing. This is the K60 adaptation of QcaBluetooth plus the 0507-0518
   fixes.
2. **Platform glue, version-tied.** The MiniBluetooth publishing service, the
   embedded firmware blob section, and the `native_owner_data_prepare` late
   start hook.

## 3. Compatibility evidence

A clean archive of the fork was patched with:

```
0500-k60-bt-qbt-new-files.patch
0502b-k60-bt-qbt-kernel-stubs.patch
0507-k60-bt-readonly-probe.patch
0508-k60-bt-s2-smmu-rcg-reset.patch
0509-k60-bt-s3-identity-publish.patch   (qbt paths only)
0510-k60-bt-firmware-addon.patch        (qbt paths only)
0511-k60-bt-s4-unblock.patch
0512-k60-bt-late-start.patch            (qbt paths only)
0514-k60-bt-boot-observability.patch
0515-k60-bt-tlv-counters.patch
0516-k60-bt-qbt-uart-clock.patch
0517-k60-bt-power-order.patch
0518-k60-bt-gic-intid.patch
```

using `git apply --include='bsd/dev/qbt*'`. All patches apply, and the result is:

| Property | Value |
| --- | --- |
| `bsd/dev/qbt_k60.c` | 2239 lines |
| sha256 | `4a1a4e269fce5f2bf3d964f8610d3c7943f3329aed2dce2da681dd45705ef5fb` |

This is byte-identical to the iOS 16 `bt-0518-gic-intid` source. The driver
layer therefore needs no rewrite for xnu-12377; only the platform glue does.

This is a source-compatibility proof, not a build proof. It does not exercise
xnu-12377 headers, the IOKit build, or any hardware.

## 4. Platform hooks that still need a port

| Patch | Extra files | Why it is version-tied |
| --- | --- | --- |
| 0509 | `iokit/Kernel/MiniBluetooth.cpp` (new), `MiniDrivers.h`, `MiniIOSurface.cpp`, `iokit/conf/files` | Publishes the `bluetooth` service. The Mini* files are created by UniXNU's earlier iOS 16 series and are absent from vanilla xnu-12377. |
| 0510 | `osfmk/conf/files.arm64` | Adds the generated `osfmk/arm64/k60_bt_blob.s` to the kernel link. The assembly is a build product, not a tracked source file. |
| 0512 | `bsd/kern/kern_exec.c` | Calls `qbt_k60_late_start()` from UniXNU's `native_owner_data_prepare()`. That function does not exist in vanilla xnu-12377; it is added by the earlier device series and must be rebased to the 24A446 exec path. |

A direct `git apply` against vanilla xnu-12377 fails for all three, as expected:
the target files or functions are not there yet. The full fork series also does
not apply to vanilla xnu-12377 (the first patch, `apple-only-cpu-tunables.patch`,
already expects a UniXNU-patched `osfmk/arm64/start.s`). The correct base is the
patched tree produced by the pinned UniXNU and UniXNU-sm8475-common components,
not the Apple tag alone.

## 5. Plan

1. **P0 - carry the driver stack.** Done on `feat/bt-ios27-port`: 0507-0518
   patches and the series entries are committed.
2. **P1 - assemble the patched xnu-12377 base.** Check out the fork's pinned
   UniXNU and UniXNU-sm8475-common revisions, apply their arch/soc series, then
   the device series. Record the first failing patch; do not skip it.
3. **P2 - port the three platform hooks.** Prefer rebasing 0509/0510/0512 onto
   the 24A446 files over inventing a second Bluetooth service. Keep the qbt
   layer untouched.
4. **P3 - build and inspect.** Build the kernel, confirm the 0500-0518 patches
   appear in the kernel log, and check that `qbt_k60_start` is reachable. This
   is still offline: no hardware proof.
5. **P4 - hardware only when iOS 27 reaches `bsd_init`.** Until then, every
   kernel/firmware flight stays on the iOS 16 line.

## 6. Open risks

- The fork's iOS 27 port has no Bluetooth phase and no BT component; this branch
  is ahead of the fork's own bring-up order.
- The iOS 27 userland Bluetooth stack (`bluetoothd`, BlueTool) is a separate
  problem from the kernel transport. Passing firmware download does not make
  Bluetooth usable.
- The d8 rollback image `0297012d...` is currently missing from
  `E:/k60-work/artifacts/bt-d8-tlv`; restore it before any flight.
