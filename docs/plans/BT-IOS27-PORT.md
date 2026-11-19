# K60 Bluetooth on iOS 27 (feat/ios27)

Status: **source staged in the iOS 27 series, built on Linux CI, not flown.**
Twenty-three patches (0500, 0502b, 0501, 0502, 0507-0512, 0514-0523, 0525, 0526, 0527) now live in
`patches/xnu-12377/series`, the list the iOS 27 board actually selects, with
the platform hooks rebased onto the 95d9c8a1 tree, an empty firmware carrier so
0510 has its input, and the Bluetooth device-tree node now shipped in
`dts/mondrian.dts`. Three Linux CI builds (§5.3) have produced a prelinked
kernel and payload; no device action was taken on this line. The driver layer is additionally hardware-verified on the iOS
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
3. **P2 - port the platform hooks. Done offline** (§4); the Linux CI builds of §5.3 now compile and link them.
4. **P3 - build and inspect. Done for the build half** (§5.3). The twenty-three
   patches build and prelink on a Linux runner; hardware inspection waits for
   iOS 27 to reach `bsd_init`.
5. **P4 - hardware only when iOS 27 reaches `bsd_init`.** Until then, every
   kernel/firmware flight stays on the iOS 16 line.

### 5.1 Series staging and validation

`board.toml` selects four series: `arch:patches/xnu/series`,
`soc:patches/xnu-12377/series`, `os:patches/xnu/series`, and
`device:patches/xnu-12377/series`. The Bluetooth patches are now in the fourth.

Validation: the fresh base `12068a8` (vanilla xnu-12377 with 0500 and 0502b
already applied) received the other twenty-one patches in series order; all
applied with no reject, and the results are byte-identical to the adaptation
tree:

| File | sha256 |
| --- | --- |
| `bsd/dev/qbt_k60.c` | `f63e9249779e3bedca8f7a0a7b447d159ffc23f981b0fdaf21c09743abe38fcd` (2324 lines) |
| `bsd/dev/qbt/qbt_transport.c` | `5a80bb039d91db1297400ceeb5cc583205ef192565ac78090655b20a98afc634` |
| `bsd/dev/qbt/qbt_transport.h` | `b0cb4d138a8ee9c36cd8ac619e033ed0371607caf703546a8bab015304b56e54` |
| `bsd/kern/kern_exec.c` | `5da7db94674a84c14a4ee29b57c7f3a1dd61fb208e5644318edad071914836ff` |
| `bsd/kern/bsd_init.c` | `94c8e15f91e4beeb1c81589523d29e662d131f7da467a44a73a3a9f2fa74b3f3` |
| `iokit/Kernel/MiniBluetooth.cpp` | `f668fcc3cc52cdaaba4f60e3d4368900c0b35a8757bb2f494f64afa40c2d8b82` (206 lines) |
| `osfmk/arm64/k60_bt_blob.s` | `a0e788aacf276750a51372ed47abc90323f7f6d6e2b4dfe230d70611429d9784` |

The series order is 0500, 0502b, 0501, 0502, 0507, 0508, 0509, 0510, 0511, 0512, 0514,
0515, 0516, 0517, 0518, 0519, 0520, 0521, 0522, 0523, 0525, 0526, 0527. There is no 0513.

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

Run [44470953368](https://github.com/Emilelu/UniXNU-mondrian/actions/runs/44470953368)
(head `5f4c895`, 9m12s) builds the same twenty patches plus the Bluetooth
device-tree node added in `1e2e681`: the generated payload ADT carries
`bluetooth` twice and `qcom,wcn6855-bt` once, so `/arm-io/bluetooth` is now
part of the static contract instead of being created at runtime by
MiniBluetooth. `kernel/kernel.macho` still carries both
`com.apple.uart.sk.bluetooth` strings.

0525 makes the series accept the names the porting page uses: `bluetooth=1`
is an alias of `k60bt=1` (`k60bt` still wins when both are present), and
`log-bluetooth=N` caps the driver log level, default 3. The patch was proven on
hardware before this run: on 2026-11-19 16:31 the iOS 16.6.1 image carried only
`bluetooth=1`, the ladder ran to `boot: return e=0 baud=3000000`, the
controller reported version `0x12110201`, rampatch 146,068 B downloaded in 27
TLV segments, and both UART.SK control names registered with `error=0`
(evidence `usblog-20261119-163124` in the device repository). Run
[44491451065](https://github.com/Emilelu/UniXNU-mondrian/actions/runs/44491451065)
is the first iOS 27 build of the twenty-one-patch series.

The run before 0522 stopped at `bsd/dev/qbt_k60.c:1851` with
`call to undeclared function 'kmem_alloc_contig'`; 0522 fixes it (§3). The
only errors left in the logs are the bootstrap pass, the documented false
negative: the release reference link reports `RELEASE reference exit 2`,
removes 67 unavailable forced exports and links again with exit 0. ArmCpu and
ArmDTPlatform pass their `-Werror` arm64e object audits.

Runs [44491451065](https://github.com/Emilelu/UniXNU-mondrian/actions/runs/44491451065)
(15m29s) and [44492630013](https://github.com/Emilelu/UniXNU-mondrian/actions/runs/44492630013)
(27m50s) then built the same series from the `ci/ios27-kernel` branch. The first
attempt with the contract step,
[44497671661](https://github.com/Emilelu/UniXNU-mondrian/actions/runs/44497671661), failed
after 2m13s before compiling anything: `unixnu: missing file:
.../UniXNU/profiles/os/ios-27.0.1-24A446/profile.toml`. The profile install line
had been dropped from `scripts/build-ios27-linux.sh` when the CI branch was
rebuilt, so `38d7404` carries the workflow onto this branch and restores the
line. A second early failure, run 44508116480, was `curl: (22) ... 404` on the
toolchain: the release asset had been uploaded as a draft, whose URL answers
404, and the CDN kept answering 404 for a while after publication; `e837ab4`
retries the download instead of trusting `curl --retry`. Run
[44508963818](https://github.com/Emilelu/UniXNU-mondrian/actions/runs/44508963818)
(head `e837ab4`, 14m02s) then passed every step, including "Check the
Bluetooth contract", which runs `scripts/check-bluetooth-kernel.py` over the
built kernel and payload.

The workflow now lives on this branch, so `ci/ios27-kernel` has no unique
content and is deleted. `020dbb5` re-includes `firmware/bluetooth/qca/*.bin`,
because the extension rules further down `.gitignore` had left four NVM files
untracked while the manifest listed all 106 entries. `fea097e` moves
`check-bluetooth-dt.py`, `check-bluetooth-userspace.py` and their tests here
from the iOS 16 line; both run on this tree (15 and 16 cases).

0526 adds the runtime mount the userspace layer needs: when the boot
argument `k60bt-runtime=1` is present, `native_bt_runtime_prepare()` installs
the GPU addon carrier, mounts `/private/var/ngpu/bluetooth-lib` over
`/usr/lib` (visible through `/usr/lib/dyld`, owning
`/usr/lib/QcaBTType0.dylib`) and, only when that mount succeeded, mounts
`/private/var/ngpu/bluetooth-bin` over `/usr/sbin` (visible through
`/usr/sbin/notifyd`, owning `/usr/sbin/QcaBluetooth.runtime`). It sits outside
`native_gpu_addon_prepare()` because that function returns early when the GPU
addon argument is absent, which is the case on K60. Without the argument the
patch is inert, so the baseline build is unchanged.

Two later runs failed before compiling, and neither failure is in the code.
Run 44530120502 (head `8602d85`) and 44530500213 (head `e79e259`) spent six
download attempts on `curl: (22) ... 404` for the toolchain asset and then
either failed on `sha256sum` or fell through to a package mirror 503. The
release `toolchain-linux-20261119` had gone back to draft state, so its asset
URL answers 404 to everyone outside the repository; publishing it again
(`gh api -X PATCH .../releases/450511132 -F draft=false`) made the range
request answer 206 on the first try. A draft release is the one state the
workflow cannot retry its way out of, because the URL never becomes valid
while the draft flag is set.

Run [44516786407](https://github.com/Emilelu/UniXNU-mondrian/actions/runs/44516786407)
(head `e8a61f5`) was cancelled by the concurrency group before it built.
Run [44518998961](https://github.com/Emilelu/UniXNU-mondrian/actions/runs/44518998961)
(head `33f5229`, 2026-11-19T11:55:09Z to 12:12:31Z, 17m22s) is the first
successful build of the twenty-three-patch series: every step passed,
`kernel/kernel.macho` is
`4e57f1822d352022b2a825f93ac41d653a149c63872a6cca8e42d505a0bb9f86` and
`payload/payload.img` is 192 MiB. The "Check the Bluetooth contract" step
reported fourteen passes, covering the two UART control names, the power and
channel log prefixes, the three `kern.qbt_*` sysctls, `K60BluetoothRadio`,
the `/chosen` identity key, the `log-bluetooth` text and the four ADT
properties.

`feat/bt-ios27-port` is only the kernel and the device tree:
`[payload.runtime]` is not enabled and 0521 is a blob stub, so "iOS 27
baseline" does not mean "Bluetooth works on iOS 27".

What this proves: the Bluetooth series compiles and links into an arm64e
xnu-12377 kernel that the profile's prelink step accepts, so the build half of
P3 is closed. What it does not prove: no hardware has run this kernel, iOS 27
on SM8475 has not reached `bsd_init`, and every P4 item stays open.

### 5.4 The GENI platform check

The official page asks for a platform check in step 6: sheng compiles
`Sm8550GeniUart.c`, `Sm8550QupDma.c` and `ArmSmmu4K.c` against a
register model and runs it under ASan/UBSan. K60 has no SM8550 platform files,
but `bsd/dev/qbt/qbt_geni.c` reaches hardware only through
`struct qbt_geni_ops`, so it builds on the host.

`scripts/tests/fixtures/bt-geni-model.c` models 4096 registers with clear and
interrupt-set semantics, protocol 2 firmware (`G_FW_REV=0x00000200`) and an
eight-entry FIFO (`G_HW_PARAM1=8<<16`), the two conditions
`qbt_geni_prepare` checks. `scripts/check-bluetooth-geni.py` extracts the
engine from `patches/xnu-12377/0500` (or from a tree with `--tree`), builds
it with the model under ASan/UBSan and runs eight scenarios: prepare, rate,
start, write, receive, fault, quiesce and flow. The run reports 64 assertions
over 36 registers and always records `hardware_verified: false`.

The CI job runs it next to the contract step, so a patch that breaks either
the artifact strings or the engine behaviour fails the build.
`scripts/tests/test-bt-geni-model.py` covers 26 cases, including that a damaged
packing write in the model must turn the run red.

Boundary: the model covers register semantics and the DMA queue, not real
QUP/GENI timing, the SMMU or the pins.

### 5.5 The shared interrupt controller check

The second step-6 script on the official page checks SPI sharing: sheng
splices the SPI registration out of `ArmCpu.cpp` and compiles it with
`Sm8550Gcc.c`. Bluetooth takes INTID 619 (UART) and 240 (TLMM wake) from the
same distributor that UFS and PCIe use, so a broken `armcpu_spi_attach` is not
a Bluetooth-local failure.

`drivers/ArmCpu/ArmCpu.cpp` keeps that code in two blocks: the owner table
(`struct SpiOwner`, `gSpi[4]`, `gSpiUsed`, `gSpiRegistering`, `gDist`,
`gBootAffinity`) from `/* Published SPI owners, following Sheng` to
`class ArmCpu : public IOCPU`, and `armcpu_spi_attach` from
`extern "C" IOReturn armcpu_spi_attach(` to `void ArmCpu::signalCPU`.
`scripts/check-bluetooth-gic.py` splices both into
`scripts/tests/fixtures/bt-gic-shared.c` at its extract marker; one slice
would swallow the class declaration and fail on `OSSymbol` and `IOCPU`.

The fixture models the GICD registers and provides the minimal `IOReturn`,
`IOLock` and memory helpers. Two host adaptations matter: the `dsb sy`
barrier becomes `__atomic_thread_fence(__ATOMIC_SEQ_CST)`, and the fixture
carries no unused `panic` stub because the build uses `-Werror`.

The run makes 43 assertions over 16 distributor writes: 619 attaches cold, the
owner table records it, `S2CR` reads back with the low two bits set,
`IROUTER` is `0x80000000`, `GICD_ISENABLER` is set, `GICD_ICENABLER` is
cleared, the priority byte is `0xa0`, and the low word of `GICD_IROUTER` is
written first. 620 gets its edge bit `(n%16)*2+1` in the config register. A
duplicate owner returns `kIOReturnExclusiveAccess` without taking a slot,
INTIDs 27, 1020 and 1024 are bad arguments, a null handler is not ready, the
fifth owner exhausts the four slots, and eight threads that attach at once
produce only defined return codes, with the success count equal to `gSpiUsed`.

The CI job runs it right after the GENI step. The checker accepts both driver
layouts: `drivers/ArmCpu/ArmCpu.cpp` on the device tree and
`drivers/armcpu-darwin24/ArmCpu.cpp` in the fork.
`scripts/tests/test-bt-gic-shared.py` covers 20 cases; removing the duplicate
guard or the enable write turns the run red.

Boundary: the model covers register semantics and the owner table, not real GIC
timing, preemption or affinity, and `hardware_verified` stays false.

### 5.6 The power ladder check

The third official step-6 script is the power check. Sheng's version asserts the
shared WCN votes (`sheng_wcn_power_get`/`put`, one vote per radio). K60 has no
such object: since 0511 the ladder never votes a PMIC rail (RPMh/RSC is out of
reach), so a cold boot only logs `power: cold boot, rails not voted
(k60bt_warm=0)` and continues. What is checkable here is the order of step 2 of
the page.

`scripts/check-bluetooth-power.py` extracts `k60_bt_power_on()` and
`k60_bt_power_off()` from `bsd/dev/qbt_k60.c` by brace matching and asserts the
seventeen power-on steps and seven power-off steps in the official order: map
the windows, park the UART pins, BT_EN low, hold 100 ms, WLAN discharge,
BT_SW_CTRL as input, serial clock, stop and prepare the engine, attach the two
interrupts, pulse XO, BT_EN high, release XO, hold 60 ms, mux the pins, start
GENI. Twelve invariants follow: 587 and 208 with `(32u + SPI)`, the attach calls
taking an INTID, the four delays 100/60/100/100 ms, no `rpmh`/`spmi`/`pmic`
token in either body once comments are stripped, a cold boot that logs instead
of returning `-EOPNOTSUPP`, and `k60.powered = true` after BT_EN goes low.

Both trees pass 22 checks. `scripts/tests/test-bt-power-check.py` runs 18 cases
against synthetic sources: reordered steps, dropped steps, retuned delays, a bare
SPI, a rail vote inside the ladder, a refused cold boot, a missing or early
cleanup flag, a power-off that keeps the wake armed, a moved `k60_irq_mask`, and
a literal INTID. One case proves a comment that mentions a rail is not a vote.

The check is textual: it proves the code still says what the port decided, not
that the hardware followed. The timing and level evidence remains the bt-0525
console, lines 480-1342.

### 5.7 The runtime mount sits behind the Data mount gate

0527 completes the mount set: after the executables overlay succeeds, it mounts
`/private/var/ngpu/xpc` over `/System/Library/xpc`, visible through
`foreground_user_endpoints.plist` and owning `launchd.plist`. That is the file
the framework's `merge_launchd_cache()` rewrites (BlueTool's job to `root`) and
`sign_launchd_cache()` signs; without it `xpcproxy` keeps starting BlueTool as
`mobile`, which is what the bt-0525 console shows.

Both 0526 and 0527 live inside
`#if defined(XNU_OWNER_DATA_MOUNT) && XNU_OWNER_DATA_MOUNT` in
`bsd/kern/kern_exec.c`, because the addon is unpacked into `/private/var/ngpu`
on the Data volume and `native_gpu_addon_install()` needs that volume mounted
first. `configs/mondrian_ios27_defconfig` does not set
`CONFIG_XNU_OWNER_DATA_MOUNT`, so on this branch the whole block, mounts
included, is compiled out. That is not an oversight and not a defect: it is the
same stage-0 boundary as section 5.3. The ios27 kernel stops at `bsd_init`, so
no `load_init_program`, so nothing to mount over.

The consequence has to be stated plainly, because a green CI run is easy to
misread: the run 44518998961 kernel carries none of these strings
(`bluetooth-lib`, `bluetooth-bin`, `[bluetooth-runtime]`, all zero hits), and
`scripts/check-bluetooth-kernel.py --expect-runtime` fails against it by design.
The flag exists so the F3 build, the first one with Data mounted, can assert the
mounts instead of trusting a patch file. The iOS 16.6.1 line is the one that
sets `CONFIG_XNU_OWNER_DATA_MOUNT=y` (`configs/mondrian_defconfig:43`), and
0526/0527 are not in that series; they exist for the 27 line, waiting for the
gate to open.

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

**Component source.** `drivers/QcaBluetooth` is now a submodule pinned to
`effe4ec5c57cd400a5f818b21c9903fef237edbc`, the revision the pinned
framework's `components.toml` names. `feeds.resolve` scans the device
repository's `drivers/` directory before the framework's, so the module
resolves as `("driver", "QcaBluetooth")` exactly as it does for sheng, and
`runtime.py` can hand its path to the runtime builder as
`bluetooth_component`. The board still has no `[payload.runtime]` section, so
nothing calls it yet.

**What this branch now carries.** `scripts/build-bluetooth-userspace.py`
stages the services through the component's `tools/build-userland.py`, and
`scripts/stage-bluetooth-firmware.py` stages the pinned `hpbtfw*`/`hpnv*`
pair under `firmware/qca`, both mirroring sheng's contract: the framework's
`scripts/build-boot-runtime.py:254-272` mounts the OS image, runs the board
script with `--os-root`, reads `report['directories']` and writes
`bluetooth-service.json`. `scripts/tests/test-bt-userspace-stage.py` exercises
that contract against a stub component with the real firmware manifest (12/0):
directory map, runtime marker, staged firmware, corrupted-file rejection and
unexpected-name rejection. The wiring is deliberately not enabled yet, because
`[payload.runtime]` makes the payload build mount the 24A446 OS image, which
belongs to F3. The block to add then is:

```toml
[components]
include = ["ArmDTPlatform", "ArmCpu", "XnuPrelink", "QcaBluetooth"]

[payload.runtime]
tool = "scripts/build-boot-runtime.py"
target = "ios27"
build = "24A446"
bluetooth_tool = "scripts/build-bluetooth-userspace.py"
bluetooth_target = "ios27"
```

`QcaBluetooth` resolves through `ctx.modules[('driver', 'QcaBluetooth')]`
(`scripts/unixnu/runtime.py:77-80`) and reaches the stager as `--component`.
The stager itself runs anywhere; building the staged `BlueTool` and
`QcaBTType0.dylib` needs `xcrun iphoneos` and a real `codesign`, so the
per-boot payload build with this block enabled runs on a macOS host.

The iOS 16.6.1 line shows why this layer cannot be skipped. Stock 20G81 BlueTool
never opens the transport at all: it blocks in a synchronous MobileGestalt call
and dies on its own 30 s XPC watchdog, and 20G81's bluetoothd has no QCA support
in its chip table. Replacing that userland is the whole job on iOS 16; on iOS 27
it is already written.

### 6.1 Demonstrated against 24A446

On 2026-11-19 the stager built the whole layer against the 24A446 root file
system. The daemon extracted from the IPSW
(`043-69909-664.dmg.aea` → `043-69909-664.dmg`, `usr/sbin/bluetoothd`) is
byte-identical to the locked original: SHA-256
`cfd94854d0a2efd3ca4a2de6e55349f43fd0d274a4b8bfa9937f29d9f7208cb1`, UUID
`8E49197B-E6BC-3F3B-A8D3-DF4BEDD37F01`. The native adapter therefore needs no
re-targeting for this OS build.

| Output | Bytes | CDHash | SHA-256 |
| --- | --- | --- | --- |
| `bin/BlueTool` | 87,216 | `1c1c94b3c400d2525051be6c0815851c436206b6` | `aef741399ef23d3283721a708ff78a2ad6d9ea64357229cf2d11564dafe73d9f` |
| `bin/bluetoothd` | 13,092,096 | `7d6db4db44e30e52150c6ae63b3337f0f1fa6521` | `178444d651c734bdbff49b03503418b4c1264b45b80bc4c54a5d7dda13013d34` |
| `lib/QcaBTType0.dylib` | 102,096 | `4c000ee5244140a98ec23f1b11ec30b5fd12f15e` | `e815fe2f32a147b1f574ebccaf9e205503bbba41c723d184096fa3f0879147b7` |

The report records `native_entitlements_preserved: true` with 157
entitlements on the re-signed daemon, and `hardware_verified: false` — nothing
here has run on a device. The firmware manifest staged 40 `hpbtfw*`/`hpnv*`
files under `firmware/qca`.

The build host was a Mac with Command Line Tools only, which needed three small
files, all carried in `scripts/toolchain/` (see its README): a minimal
`xpc/xpc.h` header shim, because that SDK ships `libxpc` without headers; a
text `libxpc.tbd` stub, because it ships no `-lxpc` library either; and
`qca-bluetooth-extra-flags.diff`, because the component's
`tools/build-bluetool.py` took no extra compiler flags. With those, BlueTool
links a real `LC_LOAD_DYLIB /usr/lib/libxpc.dylib` instead of leaving the XPC
symbols unresolved. A full Xcode install needs none of them.

### 6.2 What bluetoothd actually looks for

`marconi-trace` disassembled the 20G81 daemon (file offset = vmaddr −
0x100000000) to settle why the console shows, in this order:

```
could not find BT_DEVICE_ADDRESS env variable      main 0x1000268c4 (getenv, needs 17 chars)
marconi-bt: Unable to match bluetooth service ...  main 0x1000269cc -> helper 0x100027940
marconi-bt: Not a valid MAC address (all 00s).     helper 0x100027b78 (6-byte global at 0x100847070)
bluetooth: Got local-mac-address: ee:98:c5:8a:6b:4e  main 0x1000269dc, same helper
```

The helper matches by **name only**: `IOServiceNameMatching(name)` builds
`{IONameMatch: name}`, `IOServiceGetMatchingService(kIOMainPortDefault, ...)`
resolves it, then `IORegistryEntrySearchCFProperty(service, "IODeviceTree",
CFSTR "local-mac-address", kCFAllocatorDefault, kIORegistryIterateRecursively)`
reads 6 bytes of `CFData`. Two calls are made: `marconi-bt` first, `bluetooth`
second. The first fails and prints both errors with the `marconi-bt` prefix; the
second succeeds on the node this branch publishes and `setenv`s
`BT_DEVICE_ADDRESS`.

Consequences, which correct the earlier reading of that console:

- **The MAC is already sourced.** The two `marconi-bt` lines are the *first*
  lookup failing, not a verdict on the address. The `bluetooth` node carries
  `local-mac-address` and the daemon reads it.
- **A `marconi-bt` alias would only silence a log line.** Nothing downstream
  depends on that name: the address comes from the second lookup either way, and
  `kIORegistryIterateRecursively` would find the property on an ancestor anyway.
  Adding the alias therefore changes no behaviour and is not worth a patch.
- The remaining daemon-side gate is elsewhere: `UniXNU-pong/userland/board_services18.py:84-89`
  limits `com.apple.bluetoothd` with `_LimitLoadToDeviceTree = ['bluetooth', 'marconi-bt']`
  and states *"requires a real Pong Bluetooth transport; none implemented"*. That
  is a userland-generator decision, not a device-tree fact, and this branch does
  not inherit it.

## 7. What remains before "directly usable after migration"

1. P3's build half is done: the CI runs in §5.3 produced `kernel.macho` and
   `payload.img` with the whole series, including the reclock and the
   device-tree node. What remains is
   hardware: `qbt_k60_start` must actually run under iOS 27, which waits for
   `bsd_init`. To embed firmware first, see 5.2.
2. `[payload.runtime]` wiring plus an OS image and `codesign` on the payload
   host. The staging half is built (§6.1): enabling the block makes the payload
   build emit the services instead of only the kernel.
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
