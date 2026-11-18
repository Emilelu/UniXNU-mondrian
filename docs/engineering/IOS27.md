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
phone for any of it.

The SoC layer's `xnu-12377` series lives on this branch's
`UniXNU-sm8475-common` fork (`feat/xnu-12377`), not at the upstream commit the
feed pins. Until that fork is pushed and `feeds.toml` moves, fetch it locally:

```sh
./unixnu fetch --local-module soc:sm8475=../UniXNU-sm8475-common \
    -D ../UniXNU-mondrian-ios27
```

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

## Phases and exit criteria

| Phase | Work | Exit |
| --- | --- | --- |
| F0 | PAC gate on the old kernel: `PAC_PROBE=1 BOARD=mondrian shim/build.sh`, one boot | `RESULT OK arm64e-capable at EL1`; otherwise the branch stops |
| F1 | This profile + SM8475 `xnu-12377` series + Xcode 26 build | kernel and payload are arm64e 4 KiB; `check-xnu-granules.py` passes |
| F2 | `XnuPrelink` against the 24A446 fixture | `arm_init` → `bsd_init` → root-mount panic, cupid parity |
| F3 | `PongUfs` on the 27 storage ABI + `./unixnu userdata --os 27` | OS volume matched, APFS mounted, `launchd` execs |
| F4 | panel and touch | SpringBoard frame, then a tap opens Settings |

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
