# iOS 27.0.1 on mondrian (`feat/ios27`)

`main` is the iOS 16.6.1 (20G81) port. This branch retargets the same board to
the arm64e line: iOS 27.0.1 build 24A446, presented as an **iPhone 16 Pro Max**
(`iPhone17,2` / `D94AP`), on XNU `12377.121.6` with the Darwin 26 system calls
and the Darwin 26 KPIs patched in.

The phone profile is `profiles/os/ios-27.0.1-24A446`. It is shipped here
because UniXNU main has no iPhone profile; `scripts/install-os-profile.sh`
copies it into the framework checkout before `defconfig`. The profile is
`arch = "arm64e"` and `page_size = 4096`.

## Why iPhone17,2

It is the only iOS 27 profile with a complete prelink fixture and a phone
identity. `obaosp/UniXNU-cupid` (Xiaomi 12, SM8450, the same X2 / A710 / A510
generation) took it to BSD init, so its kernelcache pins, AMFI early-init
address, roots and `original-classes.json` are reused here unchanged. The other
iPhone 27 entries in the registry are either missing (`iphone-27.0.1-24A446` on
marble) or a second fixture to validate (`...-iphone16pro` on shennong), which
is work without a payoff at stage 0.

## Inputs

| Input | Value |
| --- | --- |
| IPSW | `iPhone17,2_27.0.1_24A446_Restore.ipsw`, 12,314,041,166 bytes, sha256 `2b846dfd495f17eb074dacc6d892529df7f18587afdf930645747cd42286f538` |
| kernelcache | decompressed arm64e Mach-O (`MH_FILESET`, 305 entries), sha256 `fa07057bf34f33af1ec26681ad0c87c13e5aaa548a300740eddb0e92876e5f95` |
| OS volume | `E3F4AED0-4454-4D5B-833C-E27E99C4F67B` |
| SystemOS volume | `8B599D21-9ABD-4050-8BA2-C61349890BED` |
| toolchain | Xcode 26: xnu-12377 uses the four-argument `__ptrauth` qualifier |

The IPSW is downloaded and unpacked on macOS: `./unixnu userdata --os 27`
needs `/usr/bin/aea` for the encrypted images. The host does not need the
phone for any of it. The driver takes the URL directly (`unixnu fetch --ipsw
PATH_OR_URL`), so the 12.3 GB download does not have to be driven by hand.

The SoC layer's `xnu-12377` series lives on the `feat/xnu-12377` branch of
`xNekom/UniXNU-sm8475-common`. `feeds.toml` names that fork and pins the
commit, so a clean checkout fetches it without a local module:

```sh
./unixnu fetch -D ../UniXNU-mondrian-ios27
```

`Emilelu/UniXNU-sm8475-common` does not carry the branch; keep both URLs in
mind when a later change needs to go upstream.

## What carries over from the iOS 16 line

The kernel does not: 8796 → 12377, 16 KiB → 4 KiB, HFS → APFS, shim → UEFI.
What does carry over is the hardware work, and it is the reason mondrian is a
better starting point than cupid:

- SM8475 UFS 3.1 facts and GCC offsets, and the `PongUfs` windows that already
  publish APFS OS / SystemOS / Data on this board (iOS 16.6.1 branch).
- The command-mode panel (one `CTL_START` per frame, autorefresh clearing) and
  the DSI-DMA brightness path with its low page, measured in `ios-mondrian`.
- Goodix touch on QUPv3 SPI, verified on this board.
- The SPMI v7 key map and the PAC probe (`ios-mondrian/shim/pac.c`).

## Components come from the catalog

`drivers/ArmCpu` and `drivers/ArmDTPlatform` used to exist in this repository
and were the iOS 16 line's hand-written drivers. A directory under the device
repository resolves with origin `device`, which outranks the catalog, so both
silently replaced `UniXNU/ArmCpu` and `UniXNU/ArmDTPlatform` in every build.
That is how the first stage-0 build stopped at `ArmCpu/ArmCpuSleep.h`: the
arch profile's archive recipe asks for the catalog driver, the tree had the
older local one, and the input was simply absent.

Both are now archived as `drivers/armcpu-darwin24` and
`drivers/armdtplatform-darwin24`, outside the build. The stage-0 component set
is therefore the catalog set: `ArmDTPlatform`, `ArmCpu`, `XnuPrelink`. The
catalog `ArmCpu` starts the secondary CPUs itself (there is no
`pong_cpu_start()`), and the catalog `ArmDTPlatform` has a
`armdt_platform_clock_register` hook instead of the old `boot-epoch` sample.

## Building F1 without Xcode (Linux host)

`UniXNU/scripts/linux/setup-toolchain.py` builds the clang that xnu's
`kalloc_type` signatures need (`__builtin_xnu_type_*`), cctools-port, mig and
lzfse under one prefix; the build driver uses it automatically when it exists.

```sh
cd UniXNU
sudo python3 scripts/linux/setup-toolchain.py --jobs 12 /opt/unixnu-linux
python3 ./unixnu defconfig mondrian_ios27_defconfig -D ../UniXNU-mondrian-ios27
python3 ./unixnu build kernel -D ../UniXNU-mondrian-ios27
```

That path needs no Mac and no phone. The 24.4 GiB userdata image still needs
macOS (`hdiutil` and `/usr/bin/aea`), so F3 keeps an Xcode 26 host even when F1
does not.

The 4 KiB granule assertion has its own script because the framework copy
(`scripts/check-xnu-granules.py`) does not yet pass the two defines xnu-12377
requires (`KERNEL_PRIVATE`, `VMAPPLE`):

```sh
sh scripts/check-ios27-granules.sh ../UniXNU/out/mondrian/ios-27.0.1-24A446/mondrian_ios27/tree
# granules: 4 KiB BCM2837, TCR_EL1_BOOT=0x00000022a5192519, ARM_PGBYTES=4096
```

## Phases and exit criteria

| Phase | Work | Exit |
| --- | --- | --- |
| F0 | PAC gate on the old kernel: `PAC_PROBE=1 BOARD=mondrian shim/build.sh`, one boot | `RESULT OK arm64e-capable at EL1`; otherwise the branch stops |
| F1 | This profile + SM8475 `xnu-12377` series + Xcode 26 build (or the Linux toolchain below) | kernel and payload are arm64e 4 KiB; `scripts/check-ios27-granules.sh` passes |
| F2 | `XnuPrelink` against the 24A446 fixture | `arm_init` → `bsd_init` → root-mount panic, cupid parity |
| F3 | `PongUfs` on the 27 storage ABI + `./unixnu userdata --os 27` | OS volume matched, APFS mounted, `launchd` execs |
| F4 | panel and touch | SpringBoard frame, then a tap opens Settings |

## The framework patch is not needed on this branch

`scripts/apply-core-patches.sh` refuses on a current UniXNU checkout, and that
is correct. `patches/unixnu-core/k60-unixnu-core.patch` was written against the
framework commit the 16.6.1 line used; on main today the boot-image `verify()`
already understands v3/v4, and the K60 initrd FAT scan, the ramoops dump, the
`-1` menu timeout and the volume diagnostics are in `uefi-mondrian`'s vendored
`Platforms/Xiaomi/UniXNUPkg` (it resolves ahead of the framework's copy). Do
not force the patch: it would be a third copy of the same fix.

## Traps

- **The prelink is bound to two hashes** (kernelcache and native kernel). Every
  kernel rebuild regenerates the map; budget one prelink run per kernel change,
  not per driver change.
- **arm64e is documented for sheng only.** SM8450 is the closest attempt and it
  does not boot yet. This branch is exploration, not a supported recipe.
- **SM8450 has no UFS block driver; SM8475 does.** ShengUfs offsets are not an
  offset of SM8450's, and PongUfs is not ShengUfs. Do not copy either.
- **Stage 0 keeps storage, display and GPU off.** They add ABIs that would hide
  the first failure behind a driver.
