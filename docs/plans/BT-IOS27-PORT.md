# K60 Bluetooth on iOS 27 (feat/ios27)

Status: **source staged in the iOS 27 series, not built, not flown.** The
fifteen patches (0501, 0502, 0507-0512, 0514-0520) now live in
`patches/xnu-12377/series`, the list the iOS 27 board actually selects, with
the platform hooks rebased onto the 95d9c8a1 tree. No kernel has been built from
this branch and no device action was taken. The driver layer is additionally
hardware-verified on the iOS 16.6.1 line: d11 (0518) completed the firmware
download and d12 (0520) registered both control names (see `k60-bt` D11/D12
plans).

## 1. Target

| Item | Value |
| --- | --- |
| Device repository | `xNekom/UniXNU-mondrian`, branch `feat/ios27` |
| Base commit | `95d9c8a1849e1befed0852ff78f7674089345e6c` |
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

## 3. Driver compatibility evidence

A clean archive of the fork was patched with 0500, 0502b and the qbt paths of
0507-0520 using `git apply --include='bsd/dev/qbt*'`. All patches apply, and the
result is:

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

## 4. Platform hooks, as adapted

The four hooks that touch files a vanilla xnu-12377 does not have were rewritten
against the patched tree (vanilla plus the arch/soc/os/device series). Only the
hooks changed; every `bsd/dev/qbt*` hunk is the iOS 16 text.

| Patch | Adaptation |
| --- | --- |
| 0501 | `bsd/conf/files`: six qbt sources after `bsd/dev/unix_startup.c` (`qbt_k60.c`, `qbt/qbt_core.c`, `qbt/qbt_geni.c`, `qbt/qbt_transport.c`, `qbt/qbt_linux.c`, `qbt/btqca.c`). `bsd/conf/Makefile.arm64` unchanged. |
| 0502 | `bsd_init.c`, in `bsd_autoconf()` before `return result;`: `if (result == KERN_SUCCESS) { qbt_k60_start(); }`. The `ARM64_BOARD_CONFIG_PONG` guard is gone because this board is not PONG; `qbt_k60_start` itself checks the `k60bt` boot argument and fails closed. |
| 0509 | `iokit/Kernel/MiniBluetooth.cpp` is a standalone 198-line file with `IOService::getResourceService()` as provider instead of the `native_pong_ui_services_start` argument; `iokit/conf/files` adds it as `optional iokitcpp`; `bsd_init.c` calls `K60BluetoothPublish()` after `IOKitBSDInit()`. The `MiniDrivers.h` and `MiniIOSurface.cpp` hunks are dropped: those files are UniXNU iOS 16 additions (`MiniDrivers.h` comes from `0212-k60-empty-accelerator.patch`) and have no counterpart here. The published properties are unchanged: `device_type=bluetooth`, `compatible=qcom,wcn7850-bt`, `transport-encoding=1`, `transport-speed`, `local-mac-address`, `/chosen mac-address-bluetooth0`, `K60BluetoothRadio`. |
| 0510 | `osfmk/conf/files.arm64`: `osfmk/arm64/k60_bt_blob.s` after `lz4_encode_arm64.s`. The iOS 16 anchor sat next to `amcc_rorgn_common.c`, which xnu-12377 spells `amcc_rorgn_ppl_amcc.c`. |
| 0512 | `kern_exec.c`, `native_owner_data_prepare()` after `native_owner_data_stage = 4`: calls `qbt_k60_late_start()`. |
| 0519 | Unchanged: the `MiniBluetooth` speed line (`K60_BT_TRANSPORT_SPEED 3000000u`) matches the new file, the `qbt_transport.c` power nodes are portable. |
| 0520 | Unchanged: the `exec_extract_strings()` anchor moved to `bsd/kern/kern_exec.c:2049` but the surrounding context is identical. |

`0507` and `0508` must stay before `0509`: 0509's include block
(`mach/vm_param.h`, `mach/vm_statistics.h`, `pexpert/arm64/board_config.h`)
depends on the headers 0508 adds. Applying 0509 on 0500+0502b alone fails at
`bsd/dev/qbt_k60.c:47`.

## 5. Status of the plan

1. **P0 - carry and stage the driver stack. Done.** Fifteen patches in
   `patches/xnu-12377/series`; the iOS 16 `patches/xnu/series` is back to its
   pre-Bluetooth 227 lines.
2. **P1 - assemble the patched xnu-12377 base. Done offline.** A tree built from
   vanilla plus the four series was used as the adaptation base; the adapted
   patches were then validated against it from scratch (§5.1).
3. **P2 - port the platform hooks. Done offline** (§4). No build has run.
4. **P3 - build and inspect. Open.** Blocked on one missing build step: the
   generated `osfmk/arm64/k60_bt_blob.s` (§5.2).
5. **P4 - hardware only when iOS 27 reaches `bsd_init`.** Until then, every
   kernel/firmware flight stays on the iOS 16 line.

### 5.1 Series staging and validation

`board.toml` selects four series: `arch:patches/xnu/series`,
`soc:patches/xnu-12377/series`, `os:patches/xnu/series`, and
`device:patches/xnu-12377/series`. The Bluetooth patches are now in the fourth.

Validation: a fresh checkout of the pre-Bluetooth state (base tree + 0500 +
0502b) was patched with the series in order; all fifteen applied with no reject,
and the results are byte-identical to the adaptation tree:

| File | sha256 |
| --- | --- |
| `bsd/dev/qbt_k60.c` | `4a1a4e269fce5f2bf3d964f8610d3c7943f3329aed2dce2da681dd45705ef5fb` |
| `bsd/kern/kern_exec.c` | `39c1b5ebe32ed38f2937d1067a44c0799d07493c11c6cabd5be5987e52cde747` |
| `bsd/kern/bsd_init.c` | `94c8e15f91e4beeb1c81589523d29e662d131f7da467a44a73a3a9f2fa74b3f3` |
| `iokit/Kernel/MiniBluetooth.cpp` | `5a526df5da263777276e29e547c5fe1e5c652d5199b49ce1a1015e10bb78075f` |

The series order is 0501, 0502, 0507, 0508, 0509, 0510, 0511, 0512, 0514,
0515, 0516, 0517, 0518, 0519, 0520. There is no 0513, as on the iOS 16 line.

### 5.2 The missing build step: the firmware blob

0510 lists `osfmk/arm64/k60_bt_blob.s` in `osfmk/conf/files.arm64`, but that
file is a generated product, not a tracked source. On the iOS 16 line
`scripts/build-xnu-4k-baseline.sh:317-323` runs
`scripts/gen-k60-bt-blob.py --assembly --output <tree>/osfmk/arm64/k60_bt_blob.s`
before compiling.

`scripts/build-ios27-linux.sh` has no such step (it runs
`apply-core-patches.sh`, `unixnu fetch`, `defconfig mondrian_ios27_defconfig`,
`unixnu build kernel`, `unixnu build payload`), and `gen-k60-bt-blob.py` is not
in this repository. Until both are wired, P3 fails at the compile step with a
missing `k60_bt_blob.s`.

Without `--container` the generator emits a one-byte stub with length zero:
every line still builds, and the kernel falls back to the empty GpuAddon range,
which is what a Bluetooth-free F1 image looks like.

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

1. Wire the blob generator into the iOS 27 build path (§5.2), then run P3 and
   confirm the fifteen patches appear in the kernel log and `qbt_k60_start` is
   linked. Offline: no hardware proof.
2. `[payload.runtime]` wiring plus the OS image and signing inputs (§6).
3. Hardware only once the fork's `ios27-arm64e` area reaches `bsd_init`.

Until then the iOS 16.6.1 line stays the only hardware testbed, and every
kernel/firmware flight is recorded there (d11 PASS, d12 observation).

## 8. Open risks

- The fork's iOS 27 port has no Bluetooth phase and no BT component; this branch
  is ahead of the fork's own bring-up order.
- The series applies, but nothing has compiled it. The first real build may still
  find header or link differences that a textual apply cannot see.
- `k60_bt_blob.s` is generated on the iOS 16 line by a script this repository
  does not carry yet, so a plain `build-ios27-linux.sh` run stops at 0510's
  missing input.
- The iOS 27 userland Bluetooth stack (`bluetoothd`, BlueTool) is a separate
  problem from the kernel transport. Passing firmware download does not make
  Bluetooth usable; §6 lists the wiring it needs.
- Rollback images are restored: d8 `0297012d47eb727bd52c164076bd60bdf90ee47d56eacdf19a89142f794fef2b`
  and d10 `6c631bc42a41117e6330a614558edc9240d67554ea3d053ca414fae89c872d69`
  are both byte-exact in `E:/k60-work/artifacts`.
