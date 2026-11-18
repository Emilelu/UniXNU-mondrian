# K60 Bluetooth on iOS 27 (feat/ios27)

Status: **work in progress, not built, not flown.** The source stack (0507-0520,
thirteen patches) is carried on local branch `feat/bt-ios27-port` of the xNekom
fork. No kernel was built from this branch and no device action was taken.
The driver layer is additionally hardware-verified on the iOS 16.6.1 line: d11
(0518) completed the firmware download and d12 (0520) registered both control
names (see `k60-bt` D11/D12 plans).

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
0519-k60-bt-userspace-power-nodes.patch (qbt paths only)
0520-k60-bt-uart-control-alias.patch   (qbt paths only)
```

using `git apply --include='bsd/dev/qbt*'`. All patches apply, and the result is:

| Property | Value |
| --- | --- |
| `bsd/dev/qbt_k60.c` | 2239 lines |
| sha256 | `4a1a4e269fce5f2bf3d964f8610d3c7943f3329aed2dce2da681dd45705ef5fb` |
| `bsd/dev/qbt/qbt_transport.c` | 598 lines |
| sha256 | `72f8e3069a372be996777106a5251e3c5f092e5f942153b73113961e8ed13bc8` |

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
| 0519 | `iokit/Kernel/MiniBluetooth.cpp` | Changes `K60_BT_TRANSPORT_SPEED` to 3000000. The file itself is a UniXNU addition, so this hunk rides on the 0509 port. Its `bsd/dev/qbt/qbt_transport.c` half is portable and already proven above. |
| 0520 | `bsd/kern/kern_exec.c` | Adds the `K60ARG` argv trace after `exec_extract_strings()`. The hook point exists in xnu-12377 at `kern_exec.c:1308`, so this is a small rebase, not a rewrite; the `qbt_transport.c` control alias is portable. |

A direct `git apply` against vanilla xnu-12377 fails for all three, as expected:
the target files or functions are not there yet. The full fork series also does
not apply to vanilla xnu-12377 (the first patch, `apple-only-cpu-tunables.patch`,
already expects a UniXNU-patched `osfmk/arm64/start.s`). The correct base is the
patched tree produced by the pinned UniXNU and UniXNU-sm8475-common components,
not the Apple tag alone.

## 5. Plan

1. **P0 - carry the driver stack.** Done on `feat/bt-ios27-port`: 0507-0518
   patches and the series entries are committed. They are staged in
   `patches/xnu/series` (the iOS 16 series); the iOS 27 board selects
   `patches/xnu-12377/series`, so **this branch does not yet build Bluetooth**.
   See §5.1.
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

### 5.1 Series staging and selection

`board.toml` selects four series: `arch:patches/xnu/series`,
`soc:patches/xnu-12377/series`, `os:patches/xnu/series`, and
`device:patches/xnu-12377/series`. The thirteen BT patches were appended to
`patches/xnu/series`, which the iOS 27 board does not read. This is deliberate:
moving them to `patches/xnu-12377/series` before 0501, 0502, 0509, 0510 and 0512
are rebased would make the F1 build fail at the first incompatible hunk.

Activation order once the hooks are rebased:

1. port 0501 (`bsd/conf/files` entries) to the xnu-12377 file list;
2. port 0502 (`bsd_init.c` start call) to the 24A446 init path;
3. port 0509 (MiniBluetooth service), 0510 (blob link) and 0512 (late start);
4. append the thirteen patches to `patches/xnu-12377/series` in the same order;
5. build and confirm the qbt source is compiled and `qbt_k60_start` is linked.

Until step 5 passes, this branch's BT code is source-carried but not selected,
and no iOS 27 build should be described as containing Bluetooth.

## 6. Userspace layer: what actually makes the adapter usable

Publishing the service is necessary but not sufficient. On iOS 27 the adapter is
driven by the QcaBluetooth component:

| Piece | Size | Role |
| --- | --- | --- |
| `userland/BlueTool.c` | 63 lines | XPC shim for `com.apple.BlueTool`: `RunBuiltinScript` reads `kern.qbt_power_on` / `kern.qbt_boot` and reports `kern.qbt_firmware` |
| `userland/Type0.c` | 217 lines | `QcaBTType0.dylib`, publishes the capability model into bluetoothd's slots |
| `tools/native_ios27.py` | 496 lines | address patches bound to bluetoothd `cfd94854d0a2efd3ca4a2de6e55349f43fd0d274a4b8bfa9937f29d9f7208cb1`, UUID `8E49197B-E6BC-3F3B-A8D3-DF4BEDD37F01` |
| `tools/build-userland.py` | 87 lines | build, sign, and verify that the hash, UUID and entitlements are unchanged |

sheng (iPadOS 27) and aston (24A446) validate this stack, including AirPods
pairing and A2DP. aston additionally reads `kern.qbt_power_on` from the kernel
because its sandbox denies the sysctl write.

**Gap on this board.** `board.toml` carries `[payload]` but no
`[payload.runtime]`. Without that section the framework never calls
`scripts/build-bluetooth-userspace.py` and never mounts the OS image, so a
kernel-only iOS 27 boot would publish the service and still have no working
BlueTool. The wiring needed is `bluetooth_tool`,
`bluetooth_target = "ios27"`, `audio_system_plugins = ["BTAudioHALPlugin.driver"]`
and an OS image to mount.

The iOS 16.6.1 line shows why this layer cannot be skipped. Stock 20G81 BlueTool
never opens the transport at all: it blocks in a synchronous MobileGestalt call
and dies on its own 30 s XPC watchdog, and 20G81's bluetoothd has no QCA support
in its chip table. Replacing that userland is the whole job on iOS 16; on iOS 27
it is already written.

## 7. What remains before "directly usable after migration"

1. P1/P2, the kernel side: assemble the patched xnu-12377 base and rebase
   0501, 0502, 0509, 0510 and 0512, plus the `MiniBluetooth.cpp` hunk of 0519
   and the `kern_exec.c` hunk of 0520 (§4).
2. Move the thirteen patches from `patches/xnu/series` into
   `patches/xnu-12377/series` only after step 1 applies cleanly.
3. `[payload.runtime]` wiring plus the OS image and signing inputs (§6).
4. Hardware only once the fork's `ios27-arm64e` area reaches `bsd_init`.

Until then the iOS 16.6.1 line stays the only hardware testbed, and every
kernel/firmware flight is recorded there (d11 PASS, d12 observation).

## 6. Open risks

- The fork's iOS 27 port has no Bluetooth phase and no BT component; this branch
  is ahead of the fork's own bring-up order.
- The eleven BT patches are staged in `patches/xnu/series`, not in the
  `device:patches/xnu-12377/series` list the iOS 27 board reads. No F1 image
  from this branch contains the qbt driver.
- The iOS 27 userland Bluetooth stack (`bluetoothd`, BlueTool) is a separate
  problem from the kernel transport. Passing firmware download does not make
  Bluetooth usable.
- The d8 rollback image `0297012d...` is currently missing from
  `E:/k60-work/artifacts/bt-d8-tlv`; restore it before any flight.
