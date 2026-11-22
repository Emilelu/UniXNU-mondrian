# Precedent parity ledger

Status date: 2026-11-23. Manifest: `docs/research/ios27/PRECEDENT-MANIFEST.toml`
(672 items across five reference repositories).

Every item now carries one of `have`, `not-applicable` or `missing-must-copy`.
The manifest was rewritten with an explicit TOML writer: `tomllib` load, dict
mutation, JSON-quoted string emission, `tomllib.loads` round-trip, then
`os.replace`. The pre-write backup is kept outside the repository at
`/mnt/e/k60-work/scratch/PRECEDENT-MANIFEST.toml.bak-20261123-022748`.

## Counts per repository

| Repository | Items | have | not-applicable | missing-must-copy |
|---|---:|---:|---:|---:|
| asteroids | 180 | 86 | 93 | 1 |
| uke | 230 | 90 | 137 | 3 |
| cupid | 66 | 52 | 14 | 0 |
| vermeer | 52 | 41 | 10 | 1 |
| sheng | 144 | 91 | 52 | 1 |
| **Total** | **672** | **360** | **306** | **6** |

`unknown` is zero in every repository. `python3 scripts/check-goal-constraints.py`
no longer prints any `N of M artefact(s) unjudged` line.

## missing-must-copy

These are boot-relevant mechanisms that exist in a precedent and have no
equivalent in our tree.

1. **asteroids — `zzzz-sheng-ipados27-bringup.patch`**
   Source: `UniXNU-sheng:patches/xnu-12377/zzzz-sheng-ipados27-bringup.patch:1`
   (also present in the asteroids and uke trees with the same body).
   The bring-up bundle implements the 47-bit user pmap through
   `T0SZ_USER != T0SZ_BOOT` (`osfmk/arm/pmap/pmap.c`, `osfmk/arm64/proc_reg.h`),
   `sheng_sigp_recover()` for a core stuck in the SIGP-disabled state
   (`osfmk/arm/cpu_common.c`), a `vfs_vget` implementation for bindfs
   (`bsd/miscfs/bindfs/bind_vfsops.c`), and the staged-apps union
   (`bsd/kern/kern_exec.c`). Our `patches/xnu-12377/series` contains none of
   these.
2. **uke — `darwin26-posix-spawn-attrs.patch`**
   Source: `UniXNU-uke:patches/xnu-12377/darwin26-posix-spawn-attrs.patch:1`.
   Converts the 0x100-byte Darwin 26 `struct _posix_spawnattr` to the kernel
   layout. Read without conversion, every daemon misreads the kqworkloop soft
   limit as its crash count. No equivalent in our series.
3. **uke — `native-4k-stack-shift.patch`**
   Source: `UniXNU-uke:patches/xnu-12377/native-4k-stack-shift.patch:1`.
   Defines `unixnu_kernel_stack_shift` and `stack_addr_mask = roundup_pow2(
   kernel_stack_size + ptoa(3)) - 1` so prelinked components that measure stack
   room with `sp & mask` work on 4 KiB pages. Our 27 kernel is forced to 4 KiB
   pages (`docs/engineering/IOS27.md:73`) and our series has no equivalent.
4. **uke — `zzzz-sheng-ipados27-bringup.patch`**
   Source: `UniXNU-uke:patches/xnu-12377/zzzz-sheng-ipados27-bringup.patch:1`.
   Same mechanism set as item 1.
5. **vermeer — `vermeer-kernel-stack-shift.patch`**
   Source: `UniXNU-vermeer:patches/xnu-12377/vermeer-kernel-stack-shift.patch:1`.
   Same 4 KiB stack-address fix as item 3.
6. **sheng — `zzzz-sheng-ipados27-bringup.patch`**
   Source: `UniXNU-sheng:patches/xnu-12377/zzzz-sheng-ipados27-bringup.patch:1`.
   Same mechanism set as item 1.

`python3 scripts/check-goal-constraints.py` therefore still refuses the build
with exactly these six `verdict 'missing-must-copy' is not one of
have/copied/not-applicable` lines. The build freeze stays in force until they
are either copied in or reclassified with evidence.

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
- **`uke-systemos-root-identity`** is recorded as `have` through
  `patches/xnu/offline-owner-systemos-mount.patch`, which tracks
  `native_owner_cache_native_union` and the real root mount. It does not add
  the precedent's `uke_files_union_identity()` helper for `vfs_attrlist` and
  `vfs_syscalls`.
- **`payload.adt.persistent_data`** is `not-applicable`: the precedent publishes
  a persistent Data range in the ADT, while our Pong scratch Data uses the
  `PackedRAMDisk` contract only (`scripts/pong_adt_contract.py:86`).
- **`CONFIG_XNU_SOURCE_STORAGE*` and `CONFIG_XNU_EXTRA_LD_ARCHIVES`** are
  `not-applicable` because the stage-0 27 recipe deliberately omits the
  source-storage userdata adapter (`docs/research/ios27/CONFORMANCE.md`,
  section II). They are not hardware limitations; a future stage that adopts
  source storage should re-open them as `missing-must-copy`.
- **`CONFIG_XNU_QCOM_PMIC_RTC`** is `not-applicable`: mondrian has no PMIC RTC
  driver; its clock comes from the UEFI/ADT platform path.
- **Board identity values** (`adt.chosen.bytes.boot-manifest-hash`,
  `owner-boot-manifest-domain`, `adt.product.string.model`, GPU register maps,
  `bootimg.dtb`, `firmware.image.*`) are `not-applicable` because they are the
  precedent board's own hardware values, not mechanisms. `have` is reserved
  for keys that our `board.toml`, OS profile or ADT generator actually emits.
