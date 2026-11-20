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

| Input | Where the pin lives |
| --- | --- |
| IPSW | `profiles/os/ios-27.0.1-24A446/profile.toml`: name, byte size, sha256 and URL of `iPhone17,2` 27.0.1 (24A446) |
| kernelcache | same profile: the decompressed arm64e `MH_FILESET` sha256, the 305-entry count and the AMFI early-init address |
| OS / SystemOS volumes | `board.toml` `root_match_volume_uuid` and the profile's volume table |
| toolchain | Xcode 26, because xnu-12377 uses the four-argument `__ptrauth` qualifier; the Linux host path is below |

The IPSW is never downloaded whole: `unixnu` reads the zip directory and the
members it needs with HTTP range requests, and the 24A446 kernelcache comes out
of that path already decompressed by `lzfse`. The one macOS-shaped step in the
framework is AEA decryption of the `.dmg.aea` OS/SystemOS members
(`scripts/unixnu/ipsw.py` calls `/usr/bin/aea`); `ipsw fw aea` decrypts the same
archives on Linux, so `./unixnu userdata --os 27` only needs that patch, not a
Mac. Neither is done yet.

The SoC layer's `xnu-12377` series lives on the `feat/xnu-12377` branch of
`xNekom/UniXNU-sm8475-common`. `feeds.toml` names that fork and pins the
commit, so a clean checkout fetches it without a local module:

```sh
./unixnu fetch --device ../UniXNU-mondrian-ios27
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
sudo python3 UniXNU/scripts/linux/setup-toolchain.py --jobs 12 /opt/unixnu-linux
sh scripts/build-ios27-linux.sh
```

`scripts/build-ios27-linux.sh` applies the framework patches, fetches, configures,
builds the kernel with the prelink and packs the payload with the synthetic
`MONDRIAN` chip id. Extra arguments go to `unixnu build kernel`. The prelink
reads the 24A446 kernelcache out of Apple's CDN with HTTP range requests, so the
12.3 GB IPSW is never downloaded whole. With `UNIXNU_UEFI` pointing at a staged
`uefi-mondrian` checkout (submodules initialised, `nasm` and `acpi-tools`
installed) the script also builds the firmware volume and packs
`boot/boot.img`; without it the script stops after the payload.

```sh
git clone https://github.com/Emilelu/uefi-mondrian.git ~/ios27-src/uefi-mondrian
cd ~/ios27-src/uefi-mondrian && git submodule update --init --depth 1
UNIXNU_UEFI=$HOME/ios27-src/uefi-mondrian sh scripts/build-ios27-linux.sh
```

The firmware is a normal EDK II `CLANGPDB` build of `Mu_Basecore` `6f805f2` plus
the five `Resources/MuPatches/` fixes `board.toml` lists; it is not
reproducible by design (`FIRMWARE-REBUILD.md` §2), so a rebuilt volume is judged
on the device, not by its hash.

The last step is `scripts/check-ios27-artifacts.py`, which reads the three
artifacts back: the Mach-O header (arm64e `MH_EXECUTE`, `NOUNDEFS`, iOS 27),
that `payload.img` still carries that exact kernel, that the ADT still pins
`/chosen/random-seed` and the T8140 identity, and that `boot.img` holds the
shim, the firmware volume, the appended device tree and the payload byte for
byte. It prints the boot image's size and sha256.

`scripts/check-ios27-geometry.py` runs before the build and costs a second: it
compares the DTS arena, `[payload].dram_size` and the managed window with the
six `/memory` regions this board reported on 2026-10-20. XNU builds the physmap
from `/chosen/dram-base` and `dram-size`, so an arena that crosses one of the
holes between those regions still builds and boots into nothing (P-231).

That path needs no Mac and no phone. XNU's makefiles still ask for macOS
tools, so install the three shims once:

```sh
sudo install -m 755 scripts/linux/ditto /usr/local/bin/ditto
sudo mv /usr/sbin/sysctl /usr/sbin/sysctl.procps
sudo install -m 755 scripts/linux/sysctl /usr/sbin/sysctl
sudo install -m 755 scripts/linux/sw_vers /usr/local/bin/sw_vers
```

`ditto` merges the libplatform headers, `/usr/sbin/sysctl` answers
`hw.physicalcpu`, `hw.logicalcpu` and `hw.memsize` (the absolute path is in
XNU's Makefile; the procps binary moves to `sysctl.procps` and still handles
everything else), and `sw_vers` supplies `HOST_OS_VERSION`.

xnu-12377 spells one qualifier the Apple way (`__ptrauth` with a fourth string
argument); upstream clang rejects it. The device series carries
`ptrauth-string-discriminator.patch`, which keeps Apple clang's spelling and
uses the three-argument form otherwise. Only `ucred.cr_label` is affected.

The **fileset reference** (the prelink's comparison kernel) builds on this host
too. `board.toml` builds it without `--lto` because cctools-port's ld64 reads no
LLVM bitcode and the pinned LLVM 24 has no `llvm-link`; the map then records a
non-LTO reference hash. XNU's own PGO support calls two LLVM profile-runtime
entry points that a macOS SDK supplies (`libclang_rt.profile`), so
`patches/unixnu-core/fileset-reference-linux.patch` stubs them — the comparison
kernel never runs. The LTO reference is still the better order model for the
matcher; a Mac build should replace it before the map is treated as final.

On a WSL host whose checkouts live under `/mnt/c`, point `UNIXNU_OUT` at ext4:

```sh
export HOME=/home/<user>        # the Windows session exports a Windows HOME
export UNIXNU_OUT=$HOME/ios27-out
python3 ./unixnu build kernel --device ../UniXNU-mondrian-ios27
```

drvfs put every clang in I/O wait and produced about six objects a minute with
the machine 95% idle; the feeds, refer clones and objects belong on ext4 and
only the repositories stay on `/mnt/c`.

The userdata image builds here too. The 24A446 OS/SystemOS members are AEA
archives; outside macOS `scripts/unixnu/ipsw.py` now calls `ipsw fw aea`, which
unwraps the key and decrypts in Go (`patches/unixnu-core/linux-aea-decrypt.patch`).
The decrypted raw disks matched the profile's pins byte for byte
(`4b8719fe…` and `f6d10101…`), so the Linux path reproduces the macOS result.

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
| F0 | PAC gate on the old kernel: `PAC_PROBE=1 BOARD=mondrian shim/build.sh`, one boot | FEAT_PAuth measured on the board on 2026-11-18 (`ISAR1` `APA=0b0101`, `API=0`: the address keys arm64e uses, no generic keys); the second capture died with a data abort before the key read-back, and the probe's key table and exception frame were corrected offline — the corrected image is unmeasured |
| F1 | This profile + SM8475 `xnu-12377` series + Xcode 26 build (or the Linux toolchain below) | `kernel.macho` is arm64e with minos 27.0 and `NOUNDEFS`; `payload.img` packs it byte for byte with a pinned `/chosen/random-seed`; the firmware volume builds from the recorded pin; `boot/boot.img` (112 B shim + FD + appended DTB + payload) passes `scripts/check-ios27-artifacts.py`; `scripts/check-ios27-geometry.py` and `scripts/check-ios27-granules.sh` pass |
| F2 | `XnuPrelink` against the 24A446 fixture | prelinked `MH_FILESET` with the roots closed and the map recorded (built on Linux 2026-11-18: 32 entries, 384 symbols on the `--allow-missing` stub, reference `6bbb66dc`); on device `arm_init` → `bsd_init` → root-mount panic, cupid parity |
| F3 | `PongUfs` on the 27 storage ABI; the userdata image is built | OS volume matched, APFS mounted, `launchd` execs |
| F4 | panel and touch | SpringBoard frame, then a tap opens Settings |

### What the PAC captures say

The first run (2026-11-18; the image's own hash was not recorded) answered the
hardware question but printed a wrong verdict:

```
ISAR1 0x0010011101211052   ISAR2 0x0000000000000000
FEAT APA 5  API 0          GPA 1  GPI 0
RESULT no FEAT_PAuth -> arm64 only (max IOS 18)
```

`APA = 0b0101` is FEAT_PAuth with EPAC and PAuth2; `API = 0` only says the
*generic* keys are missing, and arm64e authenticates code and data pointers with
the address keys (APIA/APIB/APDA/APDB). The gate required `apa && api && gpa &&
gpi`, and printed GPA/GPI from `[15:12]`/`[19:16]` (JSCVT/FCMA) instead of
`[27:24]`/`[31:28]`.

The second run used the corrected gate and printed `FEAT_PAuth present`, then
died before the next line: `PANIC SYNC`, `SLOT 4`, `ESR 0x96000006` (same EL,
translation fault level 2, read), `FAR 0x80000008`. The capture does not include
`ELR`, so the faulting instruction was not identified. The probe also runs
before `mmu_enable`, and ABL enters with the MMU off, where a translation fault
should be impossible.

Disassembling the image offline found a defect that invalidates the key step
whatever the abort was. The `KEY_REGS` table was shifted one `op2`: "APIA" wrote
APIAKEYHI and APIBKEYLO, "APIB" wrote APIBKEYHI and `S3_0_C2_C1_4` — an encoding
the architecture does not allocate — and the D and A-G pairs were shifted the
same way. APIAKEYLO, APDAKEYLO, APDBKEYLO and APGAKEYLO were never written. The
same image also restored the exception frame with `add sp, #240` where the frame
is 272 bytes, and loaded the stashed `x29`/`x30` 16 bytes low, so the panic's
`X29`/`X30` and the IRQ return path were garbage.

The probe now uses `op2` 0..3 for A/B and D/A-B and 0..1 for A-G, fixes the
frame arithmetic, and prints `SCTLR`, `VBAR`, `TTBR0` and `TCR` in every panic, so the
next data abort says which map produced it. The corrected image and its sha are
recorded in `porting.toml`; it has not been booted, so the key read-back and the
`PACIA`/`AUTIA` round trip are still unmeasured. An unallocated `msr` should
raise an undefined instruction, not a data abort, so the abort itself also stays
open until that capture has an `ELR`.

Reading the next capture:

| Line | Meaning | What follows |
| --- | --- | --- |
| `KEY RB ok` | every written key read back at EL1 | the `PACIA`/`AUTIA` lines decide |
| `KEY RB MISMATCH` | a write was ignored or routed elsewhere | stop: the keys are not usable at EL1 |
| `PACIA is a NOP` | `EnIA` is set and the pointer did not change | stop: no usable PAC at EL1 |
| `AUTIA did not restore` | signing happened, authentication did not | stop: PAC unusable |
| `RESULT OK arm64e-capable at EL1` | all three F0 steps measured | F2 |
| `PANIC SYNC` | a fault before the result | decode the next row |
| `ELR`, `VBAR`, `SCTLR`, `TTBR0`, `TCR` | the faulting instruction and the map in use | `ELR - (VBAR - 0x1000)` is the offset into `shim.elf`; `aarch64-linux-gnu-addr2line -e shim.elf <offset>` names the function |

The subtraction is needed because the image is linked at 0 and ABL loads it
wherever it chooses; `VBAR` is the vector table at image + 0x1000, so it also
gives the load base. `SCTLR.M` says whether the MMU was on at the fault.

The probe lives in `ios-mondrian`'s `shim/`, and that checkout is worked in
parallel for the iOS 16 line, so the fix travels as
`patches/ios-mondrian/pac-probe-arm64e-gate.patch`: it applies to `shim/pac.c`,
`shim/shim.c`, `shim/start.S` and `docs/PAC_PROBE.md`, and changes nothing
unless `PAC_PROBE=1` is exported (`shim.c` calls `pac_probe()` only under that
define). Build the probe from a copy of that shim, never in the shared checkout,
so its `out/` stays the iOS 16 line's.

## Framework patches this branch carries

`scripts/apply-core-patches.sh` applies every top-level
`patches/unixnu-core/*.patch` and reports already-applied ones, so it is safe
on every build. Two patches today:

- `linux-arm64e-target.patch`: the driver's Linux environment hardcoded
  `arm64-apple-ios17.0` and an arm64 `libcc_kext.a`, which made the arm64e
  kernel's compile records carry an iOS 17 deployment and the linker ignore the
  profile archive. The patch reads the arch and OS profile instead.
- `deterministic-platform-seed.patch`: `adt.random_seed` is a hexadecimal value
  repeated to fill the 256-byte `/chosen/random-seed`; unconfigured boards keep
  the fresh random seed. See the seed trap below for why this branch pins it.
- `fileset-reference-linux.patch`: the reference kernel's two LLVM
  profile-runtime calls return zero, because a host without the macOS SDK has no
  `libclang_rt.profile` and the comparison kernel never runs.
- `linux-aea-decrypt.patch`: outside macOS the IPSW's `.dmg.aea` members are
  decrypted by `ipsw fw aea` instead of `/usr/bin/aea`; the macOS branch is
  unchanged.

`patches/xnu-prelink/*.patch` patches the `kits/XnuPrelink` submodule instead:

- `reference-sections.patch`: `isection` compares section names, so a reference
  symbol that sits in no section (`section_of` answers `?`) is skipped rather
  than crashing the matcher on a missing separator.

`patches/unixnu-core/legacy/k60-unixnu-core.patch` belongs to the 16.6.1 line
and is never applied: its boot-image `verify()` change is upstream now, and the
K60 initrd/ramoops/config deltas are in `uefi-mondrian`'s vendored
`Platforms/Xiaomi/UniXNUPkg`, which resolves ahead of the framework's copy.

## Traps

- **The prelink is bound to two hashes** (kernelcache and native kernel) and the
  map also records the reference kernel's hash. Every kernel rebuild regenerates
  the map; budget one prelink run per kernel change, not per driver change.
- **A non-LTO reference is a weaker order model.** The matcher anchors on unique
  symbols and on function order; with `--lto` unavailable here the reference
  keeps per-object order instead of the merged order Apple's release build has.
  The 2026-11-18 map left 384 symbols unmapped (out of about 2,600) and relies on
  the profile's `--allow-missing`; fewer would be better, and the honest fix is a
  reference rebuilt with Xcode 26.
- **arm64e is documented for sheng only.** SM8450 is the closest attempt and it
  does not boot yet. This branch is exploration, not a supported recipe.
- **SM8450 has no UFS block driver; SM8475 does.** ShengUfs offsets are not an
  offset of SM8450's, and PongUfs is not ShengUfs. Do not copy either.
- **Stage 0 keeps storage, display and GPU off.** They add ABIs that would hide
  the first failure behind a driver.
- **A device `scripts/` file outranks the framework's.** The tree copies the
  framework, the SoC and then this repository over one another, so a same-named
  local script silently replaces the official one. Check `scripts/legacy/`
  before adding one.
- **Deleting a device script does not delete its copy in the build tree.**
  Delete `out/<board>/<profile>/<config>/tree/scripts/<name>` too, or the next
  build keeps running the removed version.
- **The ADT seed sets the physmap slide.** `devicetree.py` used to write
  `os.urandom` into `/chosen/random-seed`, so every rebuild moved the slide and
  `docs/research/ios-mondrian-traps.md` measured about one slide in three dying
  in `pmap_map_bd` on this phone. `board.toml` now pins
  `[payload."adt"].random_seed`, which the framework patch below turns into 256
  bytes of `0x11` (the reference board table's value, repeated to fill the four
  seeds xnu-12377 reads). The generated ADT is therefore byte-identical from
  one build to the next and a boot failure is a kernel change, not a reseeded
  slide; the FAT image around it still differs in the directory timestamps
  mtools writes at build time. Stage 0 only: a shipped system must not carry a
  seed published in this repository.
