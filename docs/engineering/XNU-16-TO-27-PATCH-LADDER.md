# The kernel patch ladder: iOS 16.6.1 series to the 27 series

Date: 2026-11-20. Read-only survey for the baseline line. No code was changed,
nothing was booted, and no patch was added to any series.

Question: the 27 line carries `patches/xnu-12377/series`, the 16.6.1 line carries
`patches/xnu/series` with 236 entries. Only the second set has been proven on
hardware. Which of the 16-line patches are load-bearing for a kernel that reaches
`bsd_init`, and what does the 27 line have in their place?

## 1. The 27 line applies four series, not one

`board.toml:369`, inside `[os_overrides."ios-27.0.1-24A446".kernel]`, sets:

```
patch_series = ["arch:patches/xnu/series",
                "soc:patches/xnu-12377/series",
                "os:patches/xnu/series",
                "device:patches/xnu-12377/series"]
```

`scripts/unixnu/patches.py:10 plan()` walks that list in order (`:12`), resolves
each entry (`component:` prefix or a first segment inside `ctx.profile_roots`),
and refuses duplicates (`:28`). Measured entry counts:

| Layer | Series file | Entries | What it is |
| --- | --- | --- | --- |
| arch | `UniXNU/profiles/arch/arm64e/patches/xnu/series` | 65 | the 12377 port: darwin26 syscalls/KPI, four-KiB work, native-* platform shims |
| soc | `UniXNU-sm8475-common/patches/xnu/series` | 0 | three comment lines: "Empty for now" |
| os | `UniXNU/profiles/os/ios-27.0.1-24A446/patches/xnu/series` | 4 | `zzz-boot-progress.patch`, `darwin26-syscalls.patch`, `darwin26-kpi.patch`, `darwin26-shared-region.patch` |
| device | `patches/xnu-12377/series` (this repository) | 25 | ptrauth discriminator, the ArmCpu sleep hook, the K60 Bluetooth 0500-0527 set |
| **total** | | **94** | |

So "the 23-patch series" in `docs/plans/BT-IOS27-PORT.md` is one quarter of the
story: 69 patches arrive from the framework checkout before the device series is
read. Any statement about what the 27 kernel contains has to name all four.

A patch file that exists in the framework's `patches/xnu-12377/` directory is not
applied unless a selected series lists it. `native-smp-secondary.patch` is the
counter-example: it sits in `UniXNU/patches/xnu/` and no series entry names it.

## 2. How each verdict was reached

Four signals, strongest first. A verdict below cites at least two.

1. **Pristine-file check.** The 24C build tree keeps the upstream tree at
   `.cache/xnu-work` (`HEAD = ac9718fb1af618d5ce8678d0dc6e8a58f252216f`,
   `xnu-12377.121.6`). `git -C .../.cache/xnu-work show HEAD:<path>` shows what
   the patch would meet *before* any series is applied. This is what separates
"the 27 line lacks it" from "upstream 12377 no longer has the defect".
2. **Added-line overlap.** For each same-name pair, the fraction of the 16-line
   `+` lines that also appear in the 27-line patch.
3. **Name match.** Strip the `z` ordering prefix and the three- or four-digit
   prefix. 55 of the 236 entries then share a name with an entry in the 94.
4. **Series membership** (§1): with four files, a name present in the framework
   directory still says nothing about whether it is applied.

## 3. Hardware-independent patches: present, or provably unnecessary

The 16 line carries a platform layer that predates the framework split: the
same work now lives in the arch series. Measured overlap for the pairs that
matter for a kernel that runs at all:

| 16-line entry | 27-line entry | Overlap of 16 `+` lines |
| --- | --- | --- |
| `apple-only-cpu-tunables` | same name, arch | 100% |
| `armvirt-platform-personality` | same name, arch | 100% |
| `cxx-flag-dependencies` | same name, arch | 100% |
| `kernel-sdk-root` | same name, arch | 75% |
| `local-availability`, `non-apple-cache-monitor`, `null-root-media` | same names, arch | 100% |
| `mockfs-*` (5 entries) | same names, arch | 100% |
| `native-4k-bootstrap-capacity` | same name, arch | 100% |
| `native-4k-signature-hash-cache` | same name, arch | 77% (108 of 139) |
| `native-4k-user-abi` | same name, arch | 81% (9 of 11) |
| `native-arm-pan` | same name, arch | 80% |
| `native-dt-panic-region` | same name, arch | 100% |
| `native-priv-work-interval`, `native-work-interval-soft-fail`, `native-work-interval-trace` | same names, arch | 100% |
| `native-union-getattrlistbulk` | same name, arch | 100% |
| `non-apple-iommu-bootstrap` | same name, arch | 60% (6 of 10) |
| `source-machine-layer` | same name, arch | 50% (4 of 8) |
| `zzx-pmap-sync-64bit-pa` | same name, arch | 50% (1 of 2) |

The partial pairs are not gaps: the missing `+` lines are the PONG machine
configuration and the 16.6.1 prelink format, both replaced on this line by
`bcm2837-machine-config.patch` and the `XnuPrelink` kit.

### 16-only entries, checked one by one

| 16-line patch | What it forces | Verdict on 12377 | Evidence |
| --- | --- | --- | --- |
| `architectural-timer-entry` | adds `XNU_NATIVE_ARCH_TIMER` to the `#if defined(BCM2837)` timer route in `osfmk/arm64/start.s` | not needed: the block does not exist upstream | pristine `start.s` is 879 lines and contains no `BCM2837`; the timer comes from `BCM2837.h:12` |
| `disabled-deferred-reclaim` | deletes an unused `(void) indices;` in `osfmk/vm/vm_user.c` | not needed | pristine file is 2438 lines, no `indices` |
| `native-trust-cache-runtime` | makes `startup.c`'s trust-cache call reachable without a `BCM2837` guard | already better upstream | pristine `osfmk/kern/startup.c:864` calls `kernel_bootstrap_log("trust_cache_init")` with no machine guard; `grep BCM2837` finds nothing |
| `non-apple-pmap-field` | renames a `reserved10` field in `osfmk/arm/pmap/pmap.h` | not needed: the structure has moved | pristine `pmap.h:431` `reserved10` (Rosetta branch), `:473-477` `reserved11`, `:479` `reserved13`; no collision |
| `native-volatile-panic-region` | 128 KiB static panic buffer under `#if defined(PONG) && defined(XNU_PONG_VOLATILE_PANIC_LOG)` in `pexpert/arm/pe_init.c` | device-line, replaced | 27 uses `native-dt-panic-region.patch` with `CONFIG_XNU_DT_PANIC_REGION=y` (`configs/mondrian_ios27_defconfig:13`) |
| `native-ram-block-personality` | adds the NativeRamBlock IOKit personality | present, gated | `UniXNU/patches/xnu-12377/native-aes-personality.patch:31-35` adds it under `XNU_NATIVE_RAM_BLOCK` |
| `ios16-native-ufs-personality` | adds the NativeUfs personality | present, gated | `native-aes-personality.patch:40-48` adds `NativeUfs` and `NativeUfsRoot` under `XNU_NATIVE_UFS`; the 27 defconfig sets `CONFIG_XNU_NATIVE_UFS=n` |
| `sheng-platform-power` | `sheng_pmgr_run()` from `bsd_init.c` under `XNU_SHENG_PMGR` | missing, and belongs to F3/F4 | no series entry defines `XNU_SHENG_PMGR`; it is a power hook, not a boot step |
| `ios16-external-archive-dependencies` | `XNU_EXTERNAL_KERNEL_ARCHIVES` bookkeeping | superseded | arch entry `external-archive-dependencies.patch`, same purpose, different text |
| `ios16-modern-clang` | removes `-enable-trivial-auto-var-init-zero-...` from `makedefs/MakeInc.def` | not needed | pristine `MakeInc.def` no longer carries the flag |
| `ios16-clang-uio-driverkit-compat` | replaces `uio_stackbuf_t` buffers with an aligned `char[]` in `bsd/kern/sys_generic.c` | not needed | pristine `sys_generic.c` contains `uio_stackbuf_t` zero times |
| `ios16-disabled-perf-link` | `#if KPERF` guards in ktrace plus `pmap_pending_preemption` | not required for bring-up | no series entry needs it; KPERF follows the machine configuration |
| `ios16-sparse-prelink-index` | sparse prelink index in `kalloc.c` | not needed: different prelink format | pristine `kalloc.c` has no `sparse_prelink`; 27 uses `fileset-reference-*` and the `XnuPrelink` kit |

## 4. The boot-critical device patches

Reaching `bsd_init` needs five things from the device layer. Four are
accounted for; two rows below are the ones this survey flags.

| Requirement | 16-line patch | 27-line equivalent | Status |
| --- | --- | --- | --- |
| machine configuration | `zzzz-pong-machine` (138 `+` lines) | `UniXNU/patches/xnu-12377/bcm2837-machine-config.patch`: `config/MASTER.arm64.bcm2837` plus `pexpert/pexpert/arm64/BCM2837.h` (42 lines: `NO_MONITOR`, `NO_ECORE`, `define BCM2837`, `define ARM_ARCH_TIMER`, `__ARM_COHERENT_CACHE__ 1`, `CPMU_PMC_COUNT 10`) | covered; three more 27 patches extend the same header (`native-arm-pan`, `native-pac-keys`, `no-apple-cpu-counters`) |
| interrupt controller | `zzzzzzzzzzzzzzzzzzzzz-pong-psci-smp` (GIC + PSCI) | `drivers/ArmCpu/ArmCpu.cpp` publishes the GIC SPI owners and the interrupt controller | covered for GIC; see the PSCI row |
| CPU start | same patch, `psci_smp.c`/`.h` | `ArmCpu.cpp:760 pong_cpu_start()` called from `ArmDTPlatform.cpp:224`; `ArmCpu.cpp:568 initCPU(true)`, `:569 psci_smp_init()`, `:570-579 processor_start` per CPU | **resolved**: `0540-k60-psci-smp.patch` (branch `feat/xnu27-psci-target`) adds `osfmk/arm64/psci_smp.c`/`.h` and the `conf/files` entry |
| virtual timer | `zzzz-pong-virtual-timer` | none; upstream `arm_init_timer()` runs with `BCM2837`, so the `#if !defined(PONG)` guard is false and the `CNTP_CTL_EL0` write executes | **resolved**: `0541-k60-virtual-timer-guard.patch` puts the write behind `K60_VIRTUAL_TIMER_SKIP_CNTP_CTL 1` |
| CPU start completion | `zzzzzzzzzzzzzzzzzzzzzz-pong-cpu-start-completion` | `patches/xnu-12377/0532-k60-cpu-start-completion.patch`, but the definition sits inside `#if defined(PONG)` while the 27 build is `BCM2837` | **resolved**: `0542-k60-cpu-start-completion.patch` supplies the `!PONG` copy |
| panic region | `native-volatile-panic-region` | `native-dt-panic-region.patch` + `CONFIG_XNU_DT_PANIC_REGION=y` | covered |
| visible console | `zzzzzzzzzz-pong-console-init`, `zzzzzzzzzzzzzzzz-pong-console-sink-dedup`, `zzzzz-pong-video-console`, the `03xx` usblog/panic set | `os:zzz-boot-progress.patch` (the boot-progress page) | different mechanism; not a bring-up blocker, but also not the same evidence |

### The PSCI gap, in detail

`drivers/ArmCpu/ArmCpu.cpp:18` declares `extern "C" void psci_smp_init(void);`
and `:569` calls it, immediately after `initCPU(true)` and before the
`processor_start` loop. Nothing in the 27 selection defines it:

* `git grep -n psci_smp_init emilelu/main` returns three sites: the driver's two
  lines, `patches/xnu/zzzzzzzzzzzzzzzzzzzzz-pong-psci-smp.patch:360` (16-line
  series, not selected) and `patches/xnu-ipados18/0247-k60-psci-flat-targets.patch:64`
  (the darwin24 line).
* The same patch adds `osfmk/arm64/psci_smp.c` and `psci_smp.h`; `git show
  HEAD:osfmk/arm64/psci_smp.c` in the 24C tree answers `does not exist`.
* `UniXNU/kits/` and `UniXNU/drivers/` contain no occurrence.

The reference is strong, not weak, so this is a link error rather than a
silently missing feature. The line already carries the weaker version of this
problem: `patches/xnu-12377/series` explains `armcpu-sleep-hook.patch` with
"ArmCpu's weak_import sleep hook has no definition in any component; ld64-port
rejects the unresolved weak data symbol when the archive joins the kernel
link", and the patch provides the storage in `machine_routines.c`.

Nobody has seen the error yet because the last six `main` runs fail earlier:
run `44599554246` (head `34a0e4c6`) stops in `Build the kernel and the payload`
while applying the device's framework patches --
`patches/unixnu-core/fileset-reference-linux.patch does not apply` and
`patches/unixnu-core/linux-aea-decrypt.patch does not apply` against
`FRAMEWORK_REF=563595abedfdfa413ad583b66b6176d82007e633`, after which
`scripts/build-ios27-linux.sh` refuses to continue. The build never reaches the
kernel link, so the PSCI reference has never been resolved.

**Resolution (2026-11-20).** `0540-k60-psci-smp.patch` carries the 16-line
`psci_smp.c` and `psci_smp.h` onto the 12377 shape: `PSCI_CPU_ON`,
`PSCI_AFFINITY_INFO`, the five-second arrival wait, the cache clean of the
boot segments before the first `CPU_ON`, and `psci_smp_cpu_off()` for the
quiesce path. It does not touch `start.s`, so the secondary cores enter at the
upstream reset vector and no exception-capture table is installed; the fault
record therefore stays invalid and a core that dies before the kernel runs
shows up as the five-second timeout instead. `processor.c:915` still asserts
`KERN_SUCCESS` when the device tree publishes more than one CPU, so the first
multi-core boot has to publish one core or relax that assert.

### The timer write, in detail

`zzzz-pong-virtual-timer` is nine lines in `osfmk/arm64/machine_routines.c`: it
puts the `CNTP_CTL_EL0` write inside `#if !defined(PONG)` and records why --
"Pong's EL1 physical-timer write faults under the existing firmware. XNU uses
CNTV throughout this path; leave the unavailable CNTP bank to firmware."

No patch in `UniXNU/patches/xnu-12377/` or `patches/xnu-12377/` mentions
`CNTP_CTL_EL0` (`grep -l` finds none), and the 24C tree's `machine_routines.c`
contains two occurrences, so the write is compiled in. The 27 machine
configuration is `BCM2837`, not `PONG`, so the 16-line guard would not
suppress it even if the patch were carried over verbatim. Either the fault was
specific to the 16-line timer path, or the 27 line faults at `arm_init_timer()`
before `bsd_init`. One boot decides it; until then it stays a candidate, not a
confirmed gap.

**Resolution (2026-11-20).** `0541-k60-virtual-timer-guard.patch` keeps the
write but wraps it in `#if K60_VIRTUAL_TIMER_SKIP_CNTP_CTL`, default 1, rather
than reusing the 16-line `#if !defined(PONG)`: the 27 machine configuration
is `BCM2837`, so the old guard would silently not apply. Setting the macro to
0 restores the upstream write for one build if the fault turns out to be
16-line specific.

## 5. Missing items, sorted by the stage that needs them

### F2 -- needed for a kernel that reaches `bsd_init`

| # | Item | Why it is F2 | How to falsify |
| --- | --- | --- | --- |
| 1 | PSCI SMP glue (`osfmk/arm64/psci_smp.c` + `.h`, `psci_smp_init()`) | `ArmCpu.cpp:569` calls it on the boot path, before any secondary starts; a strong reference cannot link | `nm -u` the staged kernel object, or read the link error; or `git grep -n psci_smp_init` over the 94-entry selection |
| 2 | Physical-timer suppression at `arm_init_timer()` | if the CNTP write faults on this firmware, the kernel dies before the first `bsd_init` line | the last log line before the stop; `CNTP_CTL_EL0` appears twice in the built `machine_routines.c` and in no patch |

Both are small, self-contained kernel patches of the same shape as
`armcpu-sleep-hook.patch`. Both are written and verified offline on branch
`feat/xnu27-psci-target` (0540, 0541), and a third link reference surfaced with
them: `0532-k60-cpu-start-completion.patch` defines
`pong_cpu_startup_finished()` only inside `#if defined(PONG)`, while
`ArmCpu.cpp:580` calls it unconditionally on `BCM2837`; 0542 supplies the
`!PONG` copy. None of the three is on `main` yet: `main` at `189e3cb7` carries a
63-entry device series without them.

### F3 / F4 -- needed after the kernel runs

| Item | Stage | Evidence |
| --- | --- | --- |
| `[payload.runtime]` cannot be built on Linux (`hdiutil`, `codesign` CDHash) | F3 | `docs/engineering/IOS27.md`, Known limitation |
| the Bluetooth runtime mounts sit behind `XNU_OWNER_DATA_MOUNT` | F3 | `docs/engineering/IOS27.md`, Known debt; `scripts/check-bluetooth-runtime-gate.py` |
| `XNU_NATIVE_UFS` / `XNU_NATIVE_RAM_BLOCK` personalities exist but are off | F3 | `native-aes-personality.patch:31-48`; `configs/mondrian_ios27_defconfig:20` sets UFS to `n` |
| `offline-owner-systemos-mount` is 40% of the 16-line size (178 of 436 lines) | F3 | added-line overlap; the missing part is the 16-line storage personality |
| `sheng-platform-power` (`XNU_SHENG_PMGR`) | F3/F4 | no series entry defines the switch |
| display, touch, GPU, usblog, panic UI (`03xx`, `PongAdreno`, `PongMetal`) | F4 | stage 0 stops at `bsd_init`; `CONFIG_XNU_NATIVE_ADRENO=n` |

## 6. What would make this survey wrong

Each gap above has one cheap disproof, and all three are read-only:

```
# the link question, without a build
git -C <24C tree> grep -n psci_smp_init   # three sites, none a definition
# the shipped object, once a build links
llvm-nm -u <DEVELOPMENT_ARM64_BCM2837>/bsd/kern/kern_exec.o
# the gate question
python3 scripts/check-bluetooth-runtime-gate.py --defconfig configs/mondrian_ios27_defconfig
```

The timer row needs one boot, and only Lead can run it.

## 7. Sources

* `board.toml:363`, `:369`, `:378` -- defconfig, the four series, the driver record.
* `configs/mondrian_ios27_defconfig` -- eight `CONFIG_XNU_*` entries; stage 0 stops at
  `bsd_init`, PongUfs returns in F3, display in F4.
* `UniXNU/scripts/unixnu/patches.py:10-28` -- series resolution and duplicate check.
* `UniXNU/profiles/arch/arm64e/patches/xnu/series` (65), `UniXNU-sm8475-common/patches/xnu/series`
  (0), `UniXNU/profiles/os/ios-27.0.1-24A446/patches/xnu/series` (4),
  `patches/xnu-12377/series` (25).
* `drivers/ArmCpu/ArmCpu.cpp:18`, `:562`, `:569`, `:570-579`, `:760`;
  `drivers/ArmDTPlatform/ArmDTPlatform.cpp:224`.
* `patches/xnu-12377/armcpu-sleep-hook.patch` -- the precedent for a driver-owned
  symbol the kernel must satisfy.
* `/mnt/e/hackios/k60-bt/patches/xnu/series` -- 242 lines, 236 entries; the 16-line base.
* pristine 12377: `.cache/xnu-work` at `ac9718fb` (`xnu-12377.121.6`).
* CI: run `44599554246` (head `34a0e4c6`), step `f1 / Build the kernel and the payload`.
