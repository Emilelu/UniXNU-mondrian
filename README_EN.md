# UniXNU-mondrian

UniXNU device support for the Redmi K60 (**mondrian**, Qualcomm **SM8475**).

- Firmware: [uefi-mondrian](https://github.com/Emilelu/uefi-mondrian)
- Core: [Emilelu/UniXNU](https://github.com/Emilelu/UniXNU) (branch `k60`)
- SoC: [Emilelu/UniXNU-sm8475-common](https://github.com/Emilelu/UniXNU-sm8475-common)

## Status (2026-10-30)

| Area | State | Notes |
| --- | --- | --- |
| UEFI boot chain | OK | ABL -> `fastboot boot` -> BootShim -> UEFI -> UniXNU menu |
| Display | OK | ABL splash framebuffer + SimpleFbDxe GOP, 1440x3200, 5760 B stride; no GPU acceleration |
| Buttons | OK | Official KeypadDevice chain + `K60KeypadDeviceLib` (SPMI PON/GPIO) |
| Tools -> Advanced Logger | OK | 4 MB Advanced Logger + QR frames; OneSend captures the DXE log |
| XNU kernel | OK | builds on Linux (WSL) and on the macOS CI; `kernel.macho` 53.5 MB with prelink |
| Board ADT / payload / boot image | OK | 192 MiB payload + Android boot v4 image; verify with `scripts/verify-k60-boot-img.sh` |
| UFS root (SHNGROOT) | OK | OS and SystemOS read-only windows, union-mounted on `/` |
| `/private/var` (Data) | RO only | real UFS Data window at offset `7,780,433,920`, 32 MiB, mounts read-only |
| keybag / MKB | FAIL | Data is not writable, so `systembag.kb` cannot be written and MKB goes fatal |
| Touch / GPU / audio / network / camera | TODO | not started; the GPU driver source (with `submit/`) is already in `drivers/PongAdreno/` but not linked |

Measured: XNU reaches `launchd` and the service chain proceeds to `watchdogd`
(pid 95); `/private/var` mounts for the first time from the real UFS Data window,
read-only.

## Open blockers (2026-10-30)

1. **The APFS read-write mount hangs** after the space-manager scan. A bounded
   `K60UFS write#N` trace is in place (`drivers/NativeUfs/`); it has not yet told
   us whether the UFS write itself stalls or APFS stalls internally.
2. **32 MiB Data is too small.** The same-SoC sirius board hit ENOSPC on a 32 MiB
   Data volume and trapped in watchdogd (`brk #1`). Growing it needs a new APFS
   seed, which only `hdiutil`/`newfs_apfs` on macOS can produce.
3. **Switching filesystems has a prerequisite.** The 20G81 kernelcache contains
   `com.apple.filesystems.hfs` and `com.apple.filesystems.tmpfs`, but neither is
   in this repository's prelink root list, so `mount("hfs")` / `mount("tmpfs")`
   currently fails with ENODEV. The core prelink configuration has to change first.

## Build

Four sibling trees are required. Apply the core patch first:

```sh
git clone --recurse-submodules -b k60 https://github.com/Emilelu/UniXNU
git clone https://github.com/Emilelu/UniXNU-sm8475-common
git clone https://github.com/Emilelu/UniXNU-mondrian
git clone --recurse-submodules https://github.com/Emilelu/uefi-mondrian

cd UniXNU
../UniXNU-mondrian/scripts/k60-macos-preflight.sh      # core patches + auto-slide prelink wrapper
./unixnu defconfig mondrian_defconfig -D ../UniXNU-mondrian
./unixnu fetch -D ../UniXNU-mondrian
./unixnu build kernel -D ../UniXNU-mondrian
```

On Linux (WSL) the kernel and the prelink step both build without macOS; the
toolchain comes from `scripts/linux/setup-toolchain.py` and `unixnu fetch`
pulls `kernelcache.decompressed` from the IPSW. Only the Data seed
(`scripts/k60-make-data-seed.py`) still needs macOS.

```sh
python3 scripts/k60-prelink-local.py \
  --kernel mach.development.pong.unstripped \
  --prelinked out/ipsw/20G81/kernelcache.decompressed \
  --output kernel.macho
```

Firmware:

```sh
./unixnu build firmware --uefi ../uefi-mondrian -D ../UniXNU-mondrian
```

## Data safety

- Bring-up uses `fastboot boot` only: no partition is written.
- XNU root/Data use a dedicated `unixnu` partition (SHNGROOT OS/SystemOS windows
  plus a trailing Data window), never Android `userdata`; see
  `docs/DUAL-SYSTEM.md`.
- Never flash `persist` or run `flash all`.
- Run `--dry-run` and back up the manifest before any partition write.

## Known debt

- `boot-manifest-hash` is board-specific but lives in the shared OS profile of the
  core repo; it belongs in this repository's ADT section.
- Six build-environment patches sit at the tail of `patches/xnu/series` and have to
  be re-applied on every upstream bump.
- 22 further patches are not in `series` and have not been triaged.

## License

Device code is BSD-2-Clause-Patent; imported components keep their own SPDX
headers and licenses. See `THIRD_PARTY_NOTICES.md`.
