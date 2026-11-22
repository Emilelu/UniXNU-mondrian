# UFS27 defconfig draft — the F3 switch and the keys that come with it

Status: **draft for the Lead**, 2026-11-22. `configs/mondrian_ios27_defconfig`
is not modified on this branch; the diff lives in
[`UFS27-DEFCONFIG-F3.patch`](UFS27-DEFCONFIG-F3.patch) and applies cleanly:

```sh
patch -p1 --dry-run -d <checkout> < docs/research/storage/UFS27-DEFCONFIG-F3.patch
# checking file configs/mondrian_ios27_defconfig
```

The patch changes one setting — `CONFIG_XNU_NATIVE_UFS=n` → `y` — and rewrites
the comment above it. Everything else below is a *connected key*: a setting that
the same change would need, or must deliberately leave alone. The table is the
answer to "what else moves when this switch moves", measured against this tree,
16.6.1 and the two community 27 defconfigs.

## 1. The switch itself

`scripts/build-xnu-generic.sh:646-653` appends
`-Wl,-force_load,$ROOT/build/native-ufs/libNativeUfs.a` when
`XNU_NATIVE_UFS=1` (the value comes from `CONFIG_XNU_NATIVE_UFS` through
`xnu_env()`). The archive's producer is `scripts/build-native-ufs-linux.py`,
which now compiles the driver to exactly that path (`--out build/native-ufs`);
`scripts/check-native-ufs-archive.py` grades the pair. With the switch off the
builder is quiet; with it on and the archive missing, the bare `test -f` at
`:648` ends the build with no message — that is why the producer had to exist
before this draft.

The link is still not closed: the archive imports the eleven
`IOBlockStorageDevice` symbols, which the 27 kernel collection does not export
(the fileset-entry route, owned by the bt line). The draft therefore opens the
switch only; it does not claim a bootable kernel.

## 2. Connected keys

| Key | This tree today | 16.6.1 | cupid 27 | asteroids 27 | Verdict for F3 |
| --- | --- | --- | --- | --- | --- |
| `CONFIG_XNU_NATIVE_UFS` | `n` (`:25`) | `y` (`:34`) | `y` | absent | **this patch: `y`** |
| `CONFIG_XNU_OWNER_DATA_UFS` | absent → producer defines `XNU_PONG_UFS_DATA=0` | `y` (`:47`) | absent | absent | **set `y` if the driver is to carry the Data path**; the producer reads this key in `build-native-ufs-linux.py` |
| `CONFIG_XNU_OWNER_DATA_MOUNT` | absent | `y` (`:43`) | absent | `y` | **not in this patch**; opening it needs the eight-rule chain below |
| `CONFIG_XNU_OWNER_DATA_VOLUME_UUID` | absent | `"1BCD69FF-24A5-48B1-94B6-8FE592B2F597"` (`:54`) | absent | zero UUID | only with `OWNER_DATA_MOUNT=y`, and must be the observed volume |
| `CONFIG_XNU_SOURCE_STORAGE` | absent | absent | `y` | `y` | **the decision that unlocks Data mount without the verifier**; see §3 |
| `CONFIG_XNU_VERIFIED_ROOT_PROBE` | absent → `NATIVE_VERIFIED_BLOCK=0` | `n` (`:77`) | absent | absent | **stay off**; the 27 policy directory `UniXNU/scripts/policies/ipados-27.0.1-24A446` is empty |
| `CONFIG_XNU_NATIVE_AES` | `n` (`:15` exists) | `n` | absent | absent | **stay off**; under `CONFIG_XNU_CRYPTO_BOOTSTRAP="source"` the builder refuses it (`:199-203`) |
| `CONFIG_XNU_NATIVE_RAM_BLOCK` | `n` (`:32` in 16.6.1 only) | `n` | absent | absent | **stay off**; needs AES, and the six `native_ufs_store_*` callbacks have no definition in either tree |

Notes on the table: "absent" means the key does not appear in that file, so the
builder sees the shell default (0). The 16.6.1 column is
`configs/mondrian_defconfig`; the community columns are
`/e/k60-work/references/community/{cupid,asteroids}/configs/*_ios27_defconfig`.

## 3. What actually gates `CONFIG_XNU_OWNER_DATA_MOUNT`

`scripts/check-bluetooth-data-gate-chain.py --defconfig configs/mondrian_ios27_defconfig`
prints the chain the builder enforces (`:426-515`), and on this tree it is:

```
XNU_OWNER_DATA_MOUNT      -> needs XNU_OWNER_BOOT_MANIFEST=1
XNU_OWNER_BOOT_MANIFEST   -> needs XNU_OWNER_CACHE_STARTUP=1
XNU_OWNER_CACHE_STARTUP   -> needs XNU_OWNER_CACHE_MOUNT=1
XNU_OWNER_CACHE_MOUNT     -> needs XNU_OWNER_ROOT_TRUST=1
XNU_OWNER_ROOT_TRUST      -> needs XNU_OWNER_ROOT_AUDIT=1 + (XNU_NATIVE_VIRTIO_BLOCK=1 or XNU_SOURCE_STORAGE=1)
XNU_OWNER_ROOT_AUDIT      -> needs XNU_VERIFIED_ROOT_PROBE=1 or XNU_SOURCE_STORAGE=1
XNU_VERIFIED_ROOT_PROBE   -> needs XNU_SOURCE_CORECRYPTO14=1 + XNU_CRYPTO_BOOTSTRAP=prelinked
```

With stage 0's `CONFIG_XNU_CRYPTO_BOOTSTRAP="source"` the `VERIFIED_ROOT_PROBE`
branch is unreachable by construction (the Lead's ruling of 2026-11-21), so the
only path to a mounted Data volume is `CONFIG_XNU_SOURCE_STORAGE=y`. That is
what both community 27 defconfigs set, and it is the key this draft deliberately
does **not** add: it changes three builder gates at once
(`scripts/build-xnu-generic.sh:221`, `:297`, `:307`), so it belongs to the same
decision as the Data gate, not to the UFS switch.

## 4. Order of application

1. Land this draft (switch only). `scripts/check-ufs27-storage-selection.py`
   stays at `0 gap(s)` because the archive now has a producer.
2. Run `scripts/check-native-ufs-archive.py` against a real build tree; it
   reports `skip` until the switch is in that tree's defconfig, then `ok` only
   when `build/native-ufs/libNativeUfs.a` carries `NativeUfs5start` and
   `PongUfsBlock`.
3. Decide `CONFIG_XNU_SOURCE_STORAGE` (Data mount) separately, with the chain
   in §3 as the acceptance test.
4. Leave `CONFIG_XNU_VERIFIED_ROOT_PROBE`, `CONFIG_XNU_NATIVE_AES`,
   `CONFIG_XNU_NATIVE_RAM_BLOCK` off until their own producers exist.

## 5. What this document does not claim

- It does not claim the eleven `IOBlockStorageDevice` symbols are resolved; that
  is the bt line's fileset-entry route.
- It does not claim the 27 kernel boots or mounts Data.
- It does not touch `configs/mondrian_ios27_defconfig` in this branch: the
  patch is a draft, and the Lead applies it.
