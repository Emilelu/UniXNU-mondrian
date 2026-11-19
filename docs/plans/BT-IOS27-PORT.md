# K60 Bluetooth on iOS 27 (feat/ios27)

Status: **source staged in the iOS 27 series, not built, not flown.** Eighteen
patches (0500, 0502b, 0501, 0502, 0507-0512, 0514-0520, 0521) now live in
`patches/xnu-12377/series`, the list the iOS 27 board actually selects, with
the platform hooks rebased onto the 95d9c8a1 tree and an empty firmware carrier
so 0510 has its input. No kernel has been built from this branch and no device
action was taken. The driver layer is additionally hardware-verified on the iOS
16.6.1 line: d11 (0518) completed the firmware download and d12 (0520)
registered both control names (see `k60-bt` D11/D12 plans).

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
| `bsd/dev/qbt_k60.c` | 2239 lines through 0520 |
| sha256 | `4a1a4e269fce5f2bf3d964f8610d3c7943f3329aed2dce2da681dd45705ef5fb` |
| `bsd/dev/qbt/qbt_transport.c` | 598 lines |
| sha256 | `72f8e3069a372be996777106a5251e3c5f092e5f942153b73113961e8ed13bc8` |

This is byte-identical to the iOS 16 `bt-0518-gic-intid` source. The driver
layer therefore needs no rewrite for xnu-12377; only the platform glue does.

The single exception is 0522: xnu-12377 split the kmem allocator API
(`kma_flags_t`, `KMA_*`, `kmem_alloc_contig`) out of `vm_kern.h` into the new
`vm_kern_xnu.h`, while 8792 still declared it in `vm_kern.h`, so the iOS 16
series compiled without an explicit include. 0522 adds
`#include <vm/vm_kern_xnu.h>`; after it the file is 2243 lines,
`4b973811ed805820d8b59c1e10a624f260b1769bcf24280f546cfedcd5eedc62`. The driver
logic is untouched.

This is a source-compatibility proof, not a build proof. It does not exercise
xnu-12377 headers, the IOKit build, or any hardware.

## 4. Platform hooks, as adapted

The four hooks that touch files a vanilla xnu-12377 does not have were rewritten
against the patched tree (vanilla plus the arch/soc/os/device series). Only the
hooks changed; every `bsd/dev/qbt*` hunk is the iOS 16 text apart from 0522.

| Patch | Adaptation |
| --- | --- |
| 0501 | `bsd/conf/files`: six qbt sources after `bsd/dev/unix_startup.c` (`qbt_k60.c`, `qbt/qbt_core.c`, `qbt/qbt_geni.c`, `qbt/qbt_transport.c`, `qbt/qbt_linux.c`, `qbt/btqca.c`). `bsd/conf/Makefile.arm64` unchanged. |
| 0502 | `bsd_init.c`, in `bsd_autoconf()` before `return result;`: `if (result == KERN_SUCCESS) { qbt_k60_start(); }`. The `ARM64_BOARD_CONFIG_PONG` guard is gone because this board is not PONG; `qbt_k60_start` itself checks the `k60bt` boot argument and fails closed. |
| 0509 | `iokit/Kernel/MiniBluetooth.cpp` is a standalone 198-line file with `IOService::getResourceService()` as provider instead of the `native_pong_ui_services_start` argument; `iokit/conf/files` adds it as `optional iokitcpp`; `bsd_init.c` calls `K60BluetoothPublish()` after `IOKitBSDInit()`. The `MiniDrivers.h` and `MiniIOSurface.cpp` hunks are dropped: those files are UniXNU iOS 16 additions (`MiniDrivers.h` comes from `0212-k60-empty-accelerator.patch`) and have no counterpart here. The published properties are unchanged: `device_type=bluetooth`, `compatible=qcom,wcn7850-bt`, `transport-encoding=1`, `transport-speed`, `local-mac-address`, `/chosen mac-address-bluetooth0`, `K60BluetoothRadio`. |
| 0510 | `osfmk/conf/files.arm64`: `osfmk/arm64/k60_bt_blob.s` after `lz4_encode_arm64.s`. The iOS 16 anchor sat next to `amcc_rorgn_common.c`, which xnu-12377 spells `amcc_rorgn_ppl_amcc.c`. |
| 0512 | `kern_exec.c`, `native_owner_data_prepare()` after `native_owner_data_stage = 4`: calls `qbt_k60_late_start()`. |
| 0519 | Unchanged: the `MiniBluetooth` speed line (`K60_BT_TRANSPORT_SPEED 3000000u`) matches the new file, the `qbt_transport.c` power nodes are portable. |
| 0520 | Unchanged: the `exec_extract_strings()` anchor moved to `bsd/kern/kern_exec.c:2049` but the surrounding context is identical. |
| 0522 | `bsd/dev/qbt_k60.c`: `#include <vm/vm_kern_xnu.h>` after `vm/vm_kern.h`. Without it 12377 reports `call to undeclared function 'kmem_alloc_contig'` and undeclared `KMA_*` flags at the DMA allocation. |
| 0521 | New file `osfmk/arm64/k60_bt_blob.s`: the empty carrier 0510 lists. The iOS 16 line generates it at build time from `scripts/gen-k60-bt-blob.py`; this repository has no such step, so the stub the generator emits without `--container` is carried as a patch. Replacing it with a real container is a patch refresh (5.2). |

`0507` and `0508` must stay before `0509`: 0509's include block
(`mach/vm_param.h`, `mach/vm_statistics.h`, `pexpert/arm64/board_config.h`)
depends on the headers 0508 adds. Applying 0509 on 0500+0502b alone fails at
`bsd/dev/qbt_k60.c:47`.

## 5. Status of the plan

1. **P0 - carry and stage the driver stack. Done.** Twenty patches in
   `patches/xnu-12377/series`; the iOS 16 `patches/xnu/series` is back to its
   pre-Bluetooth 227 lines.
2. **P1 - assemble the patched xnu-12377 base. Done offline.** A tree built from
   vanilla plus the four series was used as the adaptation base; the adapted
   patches were then validated against it from scratch (§5.1).
3. **P2 - port the platform hooks. Done offline** (§4). No build has run.
4. **P3 - build and inspect. Done for the build half** (§5.3). The twenty
   patches build and prelink on a Linux runner; hardware inspection waits for
   iOS 27 to reach `bsd_init`.
5. **P4 - hardware only when iOS 27 reaches `bsd_init`.** Until then, every
   kernel/firmware flight stays on the iOS 16 line.

### 5.1 Series staging and validation

`board.toml` selects four series: `arch:patches/xnu/series`,
`soc:patches/xnu-12377/series`, `os:patches/xnu/series`, and
`device:patches/xnu-12377/series`. The Bluetooth patches are now in the fourth.

Validation: a fresh checkout of the pre-Bluetooth tree (vanilla xnu-12377 plus
the arch, soc and os series, with the qbt files removed) was patched with this
series in order; all twenty applied with no reject, and the results are
byte-identical to the adaptation tree:

| File | sha256 |
| --- | --- |
| `bsd/dev/qbt_k60.c` | `65e29a1afd5c3ee85b98cd1db2bdbe5f727a83422040f21fac0af758ba10a803` |
| `bsd/dev/qbt/qbt_transport.c` | `5a80bb039d91db1297400ceeb5cc583205ef192565ac78090655b20a98afc634` |
| `bsd/dev/qbt/qbt_transport.h` | `b0cb4d138a8ee9c36cd8ac619e033ed0371607caf703546a8bab015304b56e54` |
| `bsd/kern/kern_exec.c` | `39c1b5ebe32ed38f2937d1067a44c0799d07493c11c6cabd5be5987e52cde747` |
| `bsd/kern/bsd_init.c` | `94c8e15f91e4beeb1c81589523d29e662d131f7da467a44a73a3a9f2fa74b3f3` |
| `iokit/Kernel/MiniBluetooth.cpp` | `5a526df5da263777276e29e547c5fe1e5c652d5199b49ce1a1015e10bb78075f` |
| `osfmk/arm64/k60_bt_blob.s` | `a0e788aacf276750a51372ed47abc90323f7f6d6e2b4dfe230d70611429d9784` |

The series order is 0500, 0502b, 0501, 0502, 0507, 0508, 0509, 0510, 0511, 0512, 0514,
0515, 0516, 0517, 0518, 0519, 0520, 0521, 0522, 0523. There is no 0513.

### 5.2 The firmware carrier

0510 lists `osfmk/arm64/k60_bt_blob.s` in `osfmk/conf/files.arm64`, but that
file is a generated product, not a tracked source. On the iOS 16 line
`scripts/build-xnu-4k-baseline.sh:317-323` runs
`scripts/gen-k60-bt-blob.py --assembly --output <tree>/osfmk/arm64/k60_bt_blob.s`
before compiling, and that step does not exist here.

0521 therefore carries the file itself: the exact stub the generator emits
without `--container`, twelve lines, one zero byte and a length of zero. The
kernel builds, links, and falls back to the empty GpuAddon range, which is the
right shape for an F1 image that has no firmware staged.

To embed a real container, apply the series, run the generator in the tree and
refresh the patch:

```
scripts/gen-k60-bt-blob.py --assembly --output osfmk/arm64/k60_bt_blob.s \
    --container /path/to/pong-bt-firmware.bin
```

`scripts/gen-k60-bt-blob.py` is in this repository (copied from the iOS 16
line, identical sha256). It validates the NGPUADD2 container the same way
`k60_addon_find` does at runtime, so a container that would fail on the device
fails the build instead.

### 5.3 Builds: Linux CI, with the Bluetooth series

F1 and F2 no longer need a Mac: the framework's Linux path
(`scripts/linux/setup-toolchain.py` plus
`patches/unixnu-core/fileset-reference-linux.patch`) builds and prelinks the
kernel. This branch runs it on GitHub Actions
(`.github/workflows/ios27-kernel.yml`, branch `ci/ios27-kernel`): the runner
installs the prebuilt `/opt/unixnu-linux` toolchain from the
`toolchain-linux-20261119` release, checks out the framework at a pinned
commit, installs the OS profile and runs `scripts/build-ios27-linux.sh`.

Run [44395638974](https://github.com/Emilelu/UniXNU-mondrian/actions/runs/44395638974)
(head `6f27fbc`, 2026-11-18T20:52:54Z to 21:04:39Z) succeeded:

| Artifact | Size | sha256 |
| --- | --- | --- |
| `kernel/kernel.macho` | 93,077,504 B | `bf737397a915fd659d9c1a89c0addd7263d6a6190f3071d5c9311c544f1d8122` |
| `payload/payload.img` | 201,326,592 B | `36e0014faade8601d517608ab0d3916c2fccb5cec9cdf1ea911a9292d58eaeb4` |

`xnu-patches.list` names 96 patches, with 0500, 0502b, 0501, 0502 and
0507-0522 in series order. The kernel carries the driver's strings and table
names, for example `[bluetooth sk] ctl_register com.apple.uart.sk.bluetooth`,
the 0520 alias `com.apple.uart.bluetooth`, `[bluetooth power]` and
`K60 BT: no IOKit resource service; bluetooth not published`.

Run [44466443708](https://github.com/Emilelu/UniXNU-mondrian/actions/runs/44466443708)
(head `b689f94`, 2026-11-19T05:37:28Z to 05:52:57Z) then added 0523 and also
succeeded: `kernel/kernel.macho` 93,077,504 B
`04765d4eb2a1bb6c953ded6009af9733026477e6d4d2255332c76842eccd870b`,
`payload/payload.img` 201,326,592 B
`d571b254de20625c63441764ee3a80ca567ed55808add3aff1aabdf09aa2d7f1`.
`xnu-patches.list` names 97 patches, with 0523 last, and the kernel carries
the new `[bluetooth sk] TIOCSETA cflag=%#llx speed=%llu/%llu %s error=%d`
log, so the client-requested reclock is linked.

The run before 0522 stopped at `bsd/dev/qbt_k60.c:1851` with
`call to undeclared function 'kmem_alloc_contig'`; 0522 fixes it (§3). The
only errors left in the logs are the bootstrap pass, the documented false
negative: the release reference link reports `RELEASE reference exit 2`,
removes 67 unavailable forced exports and links again with exit 0. ArmCpu and
ArmDTPlatform pass their `-Werror` arm64e object audits.

What this proves: the Bluetooth series compiles and links into an arm64e
xnu-12377 kernel that the profile's prelink step accepts, so the build half of
P3 is closed. What it does not prove: no hardware has run this kernel, iOS 27
on SM8475 has not reached `bsd_init`, and every P4 item stays open.

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

1. P3's build half is done: two CI runs (§5.3) produced `kernel.macho` and
   `payload.img` with the whole series, including the reclock. What remains is
   hardware: `qbt_k60_start` must actually run under iOS 27, which waits for
   `bsd_init`. To embed firmware first, see 5.2.
2. `[payload.runtime]` wiring plus the OS image and signing inputs (§6).
3. Hardware only once the fork's `ios27-arm64e` area reaches `bsd_init`.

Until then the iOS 16.6.1 line stays the only hardware testbed, and every
kernel/firmware flight is recorded there (d11 PASS, d12 observation).

## 8. Open risks

- The fork's iOS 27 port has no Bluetooth phase and no BT component; this branch
  is ahead of the fork's own bring-up order.
- The series compiles and prelinks on Linux CI, but nothing has run it on
  hardware; runtime differences a build cannot see may still appear.
- The carrier is an empty stub. A build from this branch links, but the kernel
  has no firmware to hand the controller until 0521 is refreshed with a real
  container (5.2).
- The iOS 27 userland Bluetooth stack (`bluetoothd`, BlueTool) is a separate
  problem from the kernel transport. Passing firmware download does not make
  Bluetooth usable; §6 lists the wiring it needs.
- Rollback images are restored: d8 `0297012d47eb727bd52c164076bd60bdf90ee47d56eacdf19a89142f794fef2b`
  and d10 `6c631bc42a41117e6330a614558edc9240d67554ea3d053ca414fae89c872d69`
  are both byte-exact in `E:/k60-work/artifacts`.
