# Precedent parity ledger

Status date: 2026-11-23. Manifest: `docs/research/ios27/PRECEDENT-MANIFEST.toml`
(1460 items across nine reference repositories).

Every item carries one of `have`, `copied` or `not-applicable`; no item is
unjudged and no item carries the retired gap label. The manifest was rewritten with an explicit
TOML writer: `tomllib` load, dict mutation, JSON-quoted string emission,
`tomllib.loads` round-trip, then `os.replace`. The pre-write backup is kept
outside the repository at
`/mnt/e/k60-work/scratch/PRECEDENT-MANIFEST.toml.bak-20261123-104024`.

## Counts per repository

| Repository | Items | have | copied | not-applicable |
|---|---:|---:|---:|---:|
| asteroids | 180 | 85 | 1 | 94 |
| uke | 230 | 88 | 3 | 139 |
| cupid | 66 | 51 | 0 | 15 |
| vermeer | 52 | 40 | 1 | 11 |
| sheng | 144 | 83 | 1 | 60 |
| UniXNU-t970 | 278 | 87 | 0 | 191 |
| UniXNU-zizhan | 116 | 78 | 0 | 38 |
| UniXNU-pong | 118 | 87 | 0 | 31 |
| iOS 16 line (`patches/xnu`) | 276 | 261 | 15 | 0 |
| **Total** | **1460** | **860** | **21** | **579** |

`python3 scripts/check-goal-constraints.py --parity-only` exits 0:
`OK goal constraints: precedent parity is complete and every active item has
eight resolvable steps`.

## Former gap items: resolution

The six items reported by the 2026-11-22 ledger are no longer missing:

- The sheng umbrella patch (also present in asteroids and uke) landed in part as
  `patches/xnu-12377/0564-k60-sheng-27-bringup-part1.patch`; the remaining
  sections still need hand re-cutting, as recorded below.
- `uke/darwin26-posix-spawn-attrs.patch` is `0562-k60-darwin26-posix-spawn-attrs.patch`.
- `uke/native-4k-stack-shift.patch` and `vermeer/vermeer-kernel-stack-shift.patch`
  are both `0561-k60-4k-stack-shift.patch`; the separate 0563 file was removed as
  a duplicate.

## 同 SoC 与 16 线来源

The four sources below were added to the ledger on 2026-11-23. All three
external trees are `main` checkouts read without a working-tree checkout.

### UniXNU-t970

- Commit: `638dbdaa20c7560c82e239909f819b4d9d227cab` (branch `main`).
- Inventory: 169 `patches/xnu-ipados18` patches, 54 `board.toml` keys and 55
  `configs/pong_ipados18_defconfig` keys; 278 manifest items (87 `have`, 191
  `not-applicable`).
- Only two patches pass `git apply --check` on the xnu-3199e8bc base feed:
  `0003-pong-rootful-upgrade.patch` (dead PONG-only code) and
  `zzzzzzzzzzzz-pong-qsort-bounded-recursion.patch` (duplicate of the canonical
  zizhan qsort fix). The other 167 are Pong GPU/display/WiFi/ADSP/touch/battery
  patches whose target files (`bsd/dev/pong_*.c`,
  `iokit/Kernel/MiniIOMobileFramebuffer.cpp`, ...) do not exist in xnu-12377.

### UniXNU-zizhan

- Commit: `034a0b0037b28f4ff4e46703cbd4d9bb75db25e5` (branch `main`).
- Inventory: 20 patches, 41 board keys and 55
  `configs/zizhan_ipados18_gpu_defconfig` keys; 116 items (78 `have`, 38
  `not-applicable`).
- Four patches pass `git apply --check`: `0003-qsort-bounded-recursion.patch`
  is a real stage-0 gap; `0004-pong-panic-reset-hook.patch`,
  `0005-pong-thread-diagnostics.patch` and
  `0006-pong-resource-notify-during-config.patch` do not become 27 work (see
  below). The remaining 16 are display/panel/touch/CS-cache device patches and
  fail on missing Pong files or drifted context.

### UniXNU-pong

- Commit: `e0ee6df109b4b5dc706cac660d4f8210dc911dac` (branch `main`).
- Inventory: 9 patches, 54 board keys and 55 `configs/pong_ipados18_defconfig`
  keys; 118 items (87 `have`, 31 `not-applicable`).
- `0003-pong-rootful-upgrade.patch` is the same PONG-only rootful helper as the
  t970 copy; the other eight are Pong display/scheduler/CS-cache patches that
  fail on missing files or context drift.

### iOS 16 line (`patches/xnu`)

- Snapshot: `05f97415e539fb4cf3a7208111df69504aead9ff` (before this ledger
  commit); 276 `.patch` files, 240 `patches/xnu/series` entries, 43 files not
  listed in `series`, and seven series entries pointing at `../usb/*.patch`
  files that do not exist under `patches/xnu`.
- 15 files are already `copied` into the 27 series: 0214→0544, 0243→0548,
  0300→0547, 0308→0549, 0334b→0550, 0500/0501/0502/0502b verbatim,
  `zzzz-pong-virtual-timer`→0541, `zzzzz-pong-ramoops-minimal`→0546,
  `zzzzz-pong-video-console`→0543, `psci-smp`→0540,
  `cpu-start-completion`→0532 and `v-crypto`→0533. The other 261 are `have`
  because the 16.6.1 tree itself carries them.
- 73 patches pass `git apply --check` on the 27 base feed and 203 fail. Of the
  73 passing patches, four are already copied (0214, 0500,
  `cpu-start-completion`, `v-crypto`); the other 69 are not in the 27 series.
  Eleven of the 15 copied files fail base-feed apply because they were re-cut
  when landed (0243, 0300, 0308, 0334b, 0501, 0502, 0502b, virtual-timer,
  ramoops, video-console, psci-smp). All 69 passing-but-uncopied files are enumerated in
  `E:/k60-work/scratch/parity-expand-report.md`, Appendix A.
- Two stage-0 assets do not apply to the base feed as-is and must be re-cut:
  `0306-k60-console-snapshot.patch` and `0331-k60-prevlog-replay.patch`; the
  second half of the trust-cache fix, `zzzz...-k60-trustcache-ready-guard.patch`,
  is in the same state.

### Real gaps from these four sources

These are the entries that are genuinely absent from the 27 series and worth
carrying into stage-0 work. `E:/k60-work/scratch/parity-expand-report.md` gives
the per-patch `git apply --check` output and the duplicate analysis against
0561-0571 for every one.

1. **qsort bounded recursion — zizhan `0003-qsort-bounded-recursion.patch`**
   (canonical; t970's `zzzzzzzzzzzz-pong-qsort-bounded-recursion.patch` is the
   same fix). `git apply --check` PASS on xnu-3199e8bc. The patch changes only
   `bsd/kern/qsort.c` so the smaller partition recurses and the larger one is
   handled iteratively; the zizhan header records the motivating panic
   (`kalloc_type sorts its views on the 16 KB boot interrupt stack: always
   recursing on the left side overflowed it (zizhan g16 panic, pc qsort+0x20)`,
   `UniXNU-zizhan/patches/xnu-ipados18/0003-qsort-bounded-recursion.patch:21`).
   The same hazard exists in our tree: `osfmk/kern/kalloc.c:1490`, `:1882` and
   `:2002` call `qsort`, and `osfmk/mach/arm/vm_param.h:385` sets
   `KERNEL_STACK_SIZE` to `4*4096` (16 KB) with `INTSTACK_SIZE` `(4*4096)` at
   `:388`. Neither the 27 nor the 16 series has a qsort patch, and no
   0561-0571 patch touches `bsd/kern/qsort.c`.
2. **`native-4k-bootstrap-capacity.patch`** — 2,300 B, touches
   `osfmk/arm/pmap/pmap.h`, `osfmk/arm64/start.s` and
   `osfmk/arm64/genassym.c`; `git apply --check` PASS. The 27 base reserves
   only `BOOTSTRAP_TABLE_SIZE (ARM_PGBYTES * 8)` at
   `osfmk/arm/pmap/pmap.h:112-120` because `ARM64_LARGE_MEMORY` is 0
   (`makedefs/MakeInc.def:438`). For the K60's 5 GiB (`board.toml:129`,
   `bootimg`/`dram_size = 0x140000000`) the two bootstrap roots plus one L2 per
   1 GiB in each of V=P and KVA need 12 pages; the existing start.s comment
   (`osfmk/arm64/start.s:603-606`) still assumes a 2 GiB/8-page device. The
   patch raises the native-4K reserve to 16 pages and adds the overflow guard.
3. **Trust-cache bootstrap pair — `zzzz...-k60-trustcache-defer-img4.patch`
   plus `zzzz...-k60-trustcache-ready-guard.patch`** — the first is 2,428 B and
   applies PASS; the second is the same fix's query-side guard but fails at
   `bsd/kern/kern_trustcache.c:442` and must be re-cut. In the 27 base
   `osfmk/kern/startup.c:864` calls `trust_cache_runtime_init()` before IOKit
   brings up AppleImage4; `libkern/img4/interface.c:6` leaves `img4if = NULL`
   and the existing code panics at `bsd/kern/kern_trustcache.c:406`
   (`image4 interface not available`). The pair lets the static runtime
   initialize without img4 and makes queries return `KERN_NOT_FOUND` until the
   runtime is ready.
4. **`source-corecrypto14-bootstrap.patch`** — 1,408 B, applies PASS. The 27
   build flags in
   `/opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/tree/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/compile_commands.json`
   include `-DXNU_SOURCE_CORECRYPTO14=1`, but the 27 base tree has no
   `corecrypto_kext_start` caller (grep: 0 hits). The 16-line patch adds the
   `STARTUP(EARLY_BOOT, STARTUP_RANK_FIRST, ...)` bootstrap; the build input
   has a newer, more defensive variant at
   `E:/k60-work/artifacts/modem-carrier-verify/port-run2/framework/patches/xnu-12377/source-corecrypto14-bootstrap.patch`
   that must be reconciled before landing. Without this the source corecrypto
   provider is linked but never started.
5. **`zzx-pmap-sync-64bit-pa.patch`** — 402 B, applies PASS. The 27 base still
   does `flush_dcache((vm_offset_t) (pp << PAGE_SHIFT), PAGE_SIZE, TRUE)` at
   `osfmk/arm/pmap/pmap.c:7238`; `pp` is a 32-bit `ppnum_t`
   (`osfmk/mach/vm_types.h:77`), so on the K60's 5 GiB the shift truncates
   physical page numbers above 4 GiB. The patch uses `ptoa(pp)`. It touches
   `pmap.c` but not any hunk of 0566.
6. **`0306-k60-console-snapshot.patch`** — 16,001 B, touches
   `bsd/dev/k60_console_export.c`, `bsd/dev/k60_usblog.c`,
   `osfmk/arm/arm_init.c` and `osfmk/arm64/pong_ramoops_console.h`.
   Base-feed `git apply --check` fails with
   `bsd/dev/k60_console_export.c: No such file or directory` and
   `bsd/dev/k60_usblog.c: No such file or directory`. The file is created by
   0548, the usblog file by 0547, and the ramoops header by 0546, so this patch
   must be re-cut after those three land; `CARRY-OVER-INVENTORY.md:27` records
   it as `移植（0300 之后）`.
7. **`0331-k60-prevlog-replay.patch`** — 2,990 B, touches
   `osfmk/arm/arm_init.c` and `bsd/dev/k60_usblog.c`. Base-feed
   `git apply --check` fails at `osfmk/arm/arm_init.c:281` and on the missing
   usblog file. It depends on `pong_ramoops_console_init` from 0546 and the
   usblog file from 0547; `CARRY-OVER-INVENTORY.md:28` records it as `移植`.
   It shares only the `arm_init.c` file with 0564, not a hunk, so it is not a
   duplicate of 0561-0571.

### All 16-line patches that apply but are not in 27

The following 69 files pass `git apply --check` on xnu-3199e8bc but are not present in the 27 series. Only the first group is stage-0 must-copy; the other groups are named so the disposition is auditable rather than implied.

| Group | Count | Files |
|---|---:|---|
| Stage-0 must-copy (4) | 4 | `native-4k-bootstrap-capacity.patch`, `source-corecrypto14-bootstrap.patch`, `zzx-pmap-sync-64bit-pa.patch`, `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-k60-trustcache-defer-img4.patch` |
| Device drivers (8) | 8 | `0503-k60-audio-aw882xx.patch`, `0504-k60-audio-pong-audio.patch`, `0602-k60-physical-battery.patch`, `0611-k60-smem-handoff.patch`, `0612-k60-adsp-image.patch`, `0613-k60-adsp-pas.patch`, `0615-k60-md-window.patch`, `0624-k60-quiet-managed-page-report.patch` |
| IOKit/USB crash guards (11) | 11 | `0335-k60-setprop-guard.patch`, `0337-k60-checkin-compat.patch`, `0344-k60-client-uaf-probe.patch`, `0350-k60-getprop-null-guard.patch`, `0351-k60-property-guards.patch`, `0358-k60-deny-analytics-open.patch`, `0359-k60-proptable-guards.patch`, `0360-k60-null-lock-safety.patch`, `0361-k60-childset-guard.patch`, `0363-k60-attach-expansion.patch`, `0384-k60-pid-hibernate.patch` |
| Cryptex (3) | 3 | `0390-k60-cryptex-app-access.patch`, `0396-k60-cryptex-app-access2.patch`, `0397-k60-cryptex-path-redirect.patch` |
| Userland/security, not stage-0 (5) | 5 | `0220-k60-coredump-off.patch`, `0241-k60-skip-launch-constraints.patch`, `0310-k60-amfi-keep-first.patch`, `0320-k60-skip-firmware-mount.patch`, `zzyc-owner-skip-launch-constraints.patch` |
| Build/misc (7) | 7 | `armvirt-platform-personality.patch`, `cxx-flag-dependencies.patch`, `external-archive-dependencies.patch`, `local-availability.patch`, `pgz-aligned-validation.patch`, `public-entitlements-header.patch`, `null-root-media.patch` |
| mockfs (5) | 5 | `mockfs-intermediate-lookup.patch`, `mockfs-memory-device-width.patch`, `mockfs-statfs.patch`, `mockfs-test-file.patch`, `mockfs-typed-allocation.patch` |
| Native platform, userland (7) | 7 | `native-aes-personality.patch`, `native-dt-panic-region.patch`, `native-priv-work-interval.patch`, `native-union-getattrlistbulk.patch`, `native-volatile-panic-region.patch`, `native-work-interval-soft-fail.patch`, `native-work-interval-trace.patch` |
| Offline/owner, userland (9) | 9 | `offline-component-load-probes.patch`, `offline-legacy-start.patch`, `offline-native-gpu-broker.patch`, `offline-owner-boot-manifest.patch`, `offline-owner-cache-carrier.patch`, `offline-owner-root-binding-audit.patch`, `offline-owner-root-crypto-probe.patch`, `offline-owner-z-air-init.patch`, `offline-owner-zz-pong-release-launchd.patch` |
| Pong userland (8) | 8 | `zzzzzzz-pong-resource-publication.patch`, `zzzzzzzzzz-pong-development-library-policy.patch`, `zzzzzzzzzzzz-pong-disable-swap-backend.patch`, `zzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-init-envp-default.patch`, `zzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-init-envp-plumbing.patch`, `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-prelink-security-init.patch`, `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-duplicate-class-soft.patch`, `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-union-lower-directory.patch` |
| sheng platform power (1) | 1 | `sheng-platform-power.patch` |
| source pthread bootstrap, dead flag (1) | 1 | `source-pthread-bootstrap.patch` |

### Not copied

- **t970 `0003-pong-rootful-upgrade.patch` and pong
  `0003-pong-rootful-upgrade.patch`** — the whole helper is under
  `#if defined(PONG) && (DEVELOPMENT || DEBUG)` and xnu-12377 does not define
  `PONG` (`makedefs/MakeInc.kernel:22` stops on `PONG`). The APFS upgrade caller
  lives in the 22H374 APFS binary, not in XNU; the function would be dead code.
- **zizhan `0004-pong-panic-reset-hook.patch`** — the 27 series already resets
  directly in `0550-k60-autoreset-27.patch`; nothing sets
  `pong_panic_reset_hook` (grep in xnu-3199e8bc: 0 hits), so the hook would
  stay NULL.
- **zizhan `0005-pong-thread-diagnostics.patch`** — 587 added lines of
  PONG-only thread/gesture diagnostics
  (`pong_dump_waiting_threads`, `pong_thread_sampler_start`,
  `pong_gesture_sample`); device diagnostic scaffold, not stage-0.
- All remaining t970 (167), zizhan (16) and pong (8) failures are
  precedent-specific device patches. Their target files do not exist in
  xnu-12377 (`bsd/dev/pong_*.c`, `iokit/Kernel/MiniIOMobileFramebuffer.cpp`,
  `iokit/Kernel/MiniIOSurface.cpp`, `pexpert/pexpert/arm64/PONG.h`, ...) or
  their hunk context is anchored to the Pong device tree. Per-patch reasons are
  in the manifest and in `E:/k60-work/scratch/parity-expand-report.md`.

### Cannot decide in this task

- **zizhan `0006-pong-resource-notify-during-config.patch`** — applies cleanly,
  but every hunk is under `#if defined(PONG)` in
  `iokit/Kernel/IOService.cpp`; 27 does not define `PONG`. Whether our stage-0
  root mount hits the AppleImage4/IOAESAccelerator wait that this patch works
  around cannot be decided without a boot log (build and flight are forbidden
  in this task).
- **16-line `0219-k60-iowatchdog.patch` + `0221-k60-watchdog-status.patch`** —
  `CARRY-OVER-INVENTORY.md:30` asks to evaluate whether 0550 already covers
  them. Both fail to apply to the base feed (`MiniIOSurface.cpp` missing;
  `kern_exec.c:7345` context drift), and whether the watchdog status adds
  anything over 0550 can only be answered on hardware.
- **16-line `0230-k60-exc-resource-early-out.patch`** — base-feed apply fails
  at `osfmk/kern/task.c:7500`; whether the early-out path is reachable in
  stage-0 cannot be decided without a build and a boot log.

## Ambiguous items

- **`zzzz-sheng-ipados27-bringup.patch` is an umbrella patch.** It mixes the
  boot-critical items above with board-specific launchd-cache overlays and
  trace logging. The verdict applies to the patch as a whole because the
  manifest is per artefact; splitting it into sub-items would be more precise.
- **`native-4k-stack-shift` / `vermeer-kernel-stack-shift`** only matter when a
  component actually reads `unixnu_kernel_stack_shift`. The XnuPrelink fixtures
  in the precedent bind those reads; if our prelink does not, the fix can wait,
  but it remains a real 4 KiB-page correctness gap.
- **`uke-owner-boot-set-recheck`** is recorded as `have`: our
  `patches/xnu/offline-owner-boot-manifest.patch` protects the same identity,
  but it refuses to replace an existing `boot-manifest-hash` instead of
  accepting a matching existing set. The policy is equivalent, the code path is
  not identical.
- **`uke-systemos-root-identity`** is `not-applicable` because the 27 stage-0
  recipe does not enable `XNU_OWNER_UNION_SYSTEMOS`, so there is no union root
  whose `MNT_ROOTFS` flag must be published. The 16.6.1 union path uses
  `patches/xnu/offline-owner-systemos-mount.patch`; that patch tracks
  `native_owner_cache_native_union` but does not set `MNT_ROOTFS` on the union
  upper. Re-open this item before enabling the union on 27.
- **`payload.runtime.*`** keys are `not-applicable`: our `board.toml` has no
  `[payload.runtime]` block. The 27 payload is assembled by the framework boot
  scripts (Bluetooth userspace is a separate build step), not by an
  installable OS-image runtime. A future product that adopts `payload.runtime`
  should re-open the Bluetooth, WiFi and trust-component keys as must-copy.
- **`payload.panic_screen`** is `not-applicable`: our payload leaves the probe
  panic screen off because it patches fixed `panic()` padding in the reference
  kernel (`board.toml:120-124`); the kernel video console carries the panic
  text instead.
- **`payload.adt.persistent_data`** is `not-applicable`: the precedent publishes
  a persistent Data range in the ADT, while our Pong scratch Data uses the
  `PackedRAMDisk` contract only (`scripts/pong_adt_contract.py:86`).
- **`CONFIG_XNU_SOURCE_STORAGE*` and `CONFIG_XNU_EXTRA_LD_ARCHIVES`** are
  `not-applicable` because the stage-0 27 recipe deliberately omits the
  source-storage userdata adapter (`docs/research/ios27/CONFORMANCE.md`,
  section II). They are not hardware limitations; a future stage that adopts
  source storage should re-open them as must-copy items.
- **`CONFIG_XNU_QCOM_PMIC_RTC`** is `not-applicable`: mondrian has no PMIC RTC
  driver; its clock comes from the UEFI/ADT platform path.
- **Board identity values** (`adt.chosen.bytes.boot-manifest-hash`,
  `owner-boot-manifest-domain`, `adt.product.string.model`, GPU register maps,
  `bootimg.dtb`, `firmware.image.*`) are `not-applicable` because they are the
  precedent board's own hardware values, not mechanisms. `have` is reserved
  for keys that our `board.toml`, OS profile or ADT generator actually emits.

## sheng umbrella, section-by-section status

- Part 1 (27 of 35 sections) landed as `patches/xnu-12377/0564-k60-sheng-27-bringup-part1.patch` (53,849 B, applies to xnu-12377 unchanged).
- Remaining sections need hand re-cutting: `bsd/kern/bsd_init.c` (context drift at :800), `bsd/kern/kern_exec.c`, `iokit/Kernel/IOUserClient.cpp`, `osfmk/arm/pmap/pmap.c`, `osfmk/arm64/arm_vm_init.c`, `osfmk/arm64/sleh.c`, `osfmk/vm/vm_shared_region_pager.c`.
- `pexpert/pexpert/arm64/BCM2837.h` is not applicable: xnu-12377 has no `pexpert/pexpert/arm64` directory at all (checked on the feed).
- Three-way apply cannot work for these: `git apply -3` reports `does not match index`, i.e. the sheng blobs are not in our object store.
