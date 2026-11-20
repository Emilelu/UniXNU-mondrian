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

## The two series are not one series

`patches/xnu/series` (the iOS 16.6.1 line) and `patches/xnu-12377/series`
(this line) are two patch sets, not one set with different OS parameters.

| | `patches/xnu/series` | `patches/xnu-12377/series` |
| --- | --- | --- |
| Entries | 236 on `main`, 227 here | 24 (2 upstream + 22 Bluetooth) |
| Kernel | xnu-8796 (Darwin 22) | xnu-12377 (Darwin 26 calls) |
| Page granule | Apple's 16 KiB baseline, forced to 4 KiB on K60 by `native-4k-bootstrap-capacity.patch`, `native-4k-signature-hash-cache.patch` and `native-4k-user-abi.patch` | 4 KiB from the 12377 machine config: `PONG.h` never defines `__ARM_16K_PG__`, so `ARM_PGSHIFT` is 12 (`scripts/check-ios27-granules.sh` asserts it) |
| Selected by | `main` | `feat/ios27` and this branch |

Both K60 kernels run with 4 KiB pages, but they get there differently. The 16
line starts from an Apple kernel that assumes 16 KiB and patches the arithmetic
back to 4 KiB (`vm_map_set_page_shift` in `bsd/kern/mach_loader.c`,
`PAGE_SHIFT_CONST` in `osfmk/arm/arm_init.c`). The 12377 line never had
16 KiB in the first place: the K60 machine config header
(`pexpert/pexpert/arm64/PONG.h`) does not define `__ARM_16K_PG__`, so
`osfmk/arm64/proc_reg.h` yields `ARM_PGSHIFT` 12. Only `VMAPPLE.h` and
`H13.h` define it.

Most iOS 16 entries do not apply to 12377 at all: the code they patch was
rewritten (KPI layers, `pmap`, the arm64 machine config, the storage stack). A
patch that does apply usually needs its context and often its API re-derived —
see §4 of `docs/plans/BT-IOS27-PORT.md` for what that looked like for the
Bluetooth series.

## What "iOS 27 baseline" means here

`configs/mondrian_ios27_defconfig` is a **stage-0** configuration: it stops at
`bsd_init`. Its own comment says so:

```
# Stage 0 stops at bsd_init: no root, no panel, no GPU. PongUfs returns in F3
CONFIG_XNU_NATIVE_UFS=n
CONFIG_XNU_NATIVE_ADRENO=n
CONFIG_XNU_NATIVE_LEGACY_DISPLAY=n
```

So "the iOS 27 baseline" means **the kernel reaches `bsd_init`**, not "hardware
works on iOS 27". Storage, display, GPU, touch and every peripheral still have
to be ported to the 27 ABIs (F3 and later, §Phases). Reading a green build or a
`bsd_init` boot as "27 is usable" is the mistake this section exists to
prevent.

## Components come from the catalog

`drivers/ArmCpu` and `drivers/ArmDTPlatform` used to exist in this repository
and were the iOS 16 line's hand-written drivers. A directory under the device
repository resolves with origin `device`, which outranks the catalog, so both
silently replaced `UniXNU/ArmCpu` and `UniXNU/ArmDTPlatform` in every build.
That is how the first stage-0 build stopped at `ArmCpu/ArmCpuSleep.h`: the
arch profile's archive recipe asks for the catalog driver, the tree had the
older local one, and the input was simply absent.

The fork archived both as `drivers/armcpu-darwin24` and
`drivers/armdtplatform-darwin24`, outside the build. **This repository keeps the
device copies under their original names**, because the 16.6.1 line is what
`main` boots and it needs them: `drivers/ArmCpu/ArmCpu.cpp` carries the
platform-sleep hook (`#9` power line, 43 references to `armcpu_sleep` /
`ArmCpuSleep.h`) and `drivers/ArmDTPlatform/ArmDTPlatform.cpp` carries the wifi
and thermal start hooks (`pong_wifi_start_optional`, `k60_thermal_start`).
Archiving them here would delete the only code that touches `ml_arm_sleep`, so
the two OS profiles share one set of device drivers instead.

That leaves one consequence to remember for F1: with `drivers/ArmCpu` present,
`scripts/unixnu/feeds.py` resolves the `ArmCpu` component with origin `device`
before it reaches the catalog, so a stage-0 build in this repository gets the
sleep-hooked copy rather than the catalog one. Two ways out, both confined to the
27 profile: build F1 from a checkout that does not carry `drivers/ArmCpu` (the
fork's shape), or add an explicit catalog selection for that profile. Neither is
done yet. The stage-0 component set itself is still the catalog set
`ArmDTPlatform`, `ArmCpu`, `XnuPrelink`; the catalog `ArmCpu` starts the
secondary CPUs itself (there is no `pong_cpu_start()`), and the catalog
`ArmDTPlatform` has an `armdt_platform_clock_register` hook instead of the old
`boot-epoch` sample.

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

Two packages are outside `setup-toolchain.py` and outside the checkout, and
nothing fails until the firmware step starts, so they are worth installing before
the first run: `nasm` assembles the PEI modules and `iasl` compiles the Silicium
ACPI tables. On Ubuntu 24.04 the ACPI compiler is packaged as `acpica-tools`
(`acpi-tools` is the name some other distributions use, so ask `apt-cache policy`
rather than trusting the older spelling):

```sh
sudo apt-get install -y nasm acpica-tools
nasm --version   # NASM version 2.16.01
iasl -v          # ASL+ Optimizing Compiler/Disassembler version 20230628
```

Measured on 2026-11-20; both were `Installed: (none)` on the F1 host until then,
which is why the payload succeeded and the firmware volume could not be built.

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
| F0 | PAC gate on the old kernel: `PAC_PROBE=1 BOARD=mondrian shim/build.sh`, one boot | one core reports FEAT_PAuth on 2026-11-18 (`ISAR1` `APA=0b0101`, `API=0`); the same probe must sample every enabled core, and the key-register write plus the `PACIA`/`AUTIA` round trip still need one boot with the fixed probe |
| F1 | This profile + SM8475 `xnu-12377` series + Xcode 26 build (or the Linux toolchain below) | `kernel.macho` is arm64e with minos 27.0 and `NOUNDEFS`; `payload.img` packs **the declared transform** of it (the payload step copies the kernel and runs `patch-armcpu-validate.py`, which rewrites eight bytes -- P-277) with a pinned `/chosen/random-seed`; the firmware volume builds from the recorded pin; `boot/boot.img` (112 B shim + FD + appended DTB + payload) passes `scripts/check-ios27-artifacts.py`; `scripts/check-ios27-granules.sh` passes. This is a *structural* pass: F1 does not claim the image can boot |
| F2 | `XnuPrelink` against the 24A446 fixture | prelinked `MH_FILESET` whose map is **closed** -- no owner-target reference without an address and no site left on `_unixnu_fileset_unmapped` -- and whose header **the loader compiled into the volume** accepts. That loader is not the catalog pin: `board.toml [firmware].packages` puts `{uefi}/Platforms/Xiaomi` third and `{tree}/package` fourth, so the source compiled today is `Platforms/Xiaomi/DarwinBootPkg/Driver/DarwinBoot.c`, which reads `cpusubtype == 0 && filetype == 2` and has no fileset branch at all; `scripts/check-ios27-firmware.py` names the file. Then on device `arm_init` → `bsd_init` → root-mount panic, cupid parity. An image carrying 384 unresolved references and 2,688 stub sites is not an F2 pass (as built on Linux 2026-11-18, reference `6bbb66dc`), and `check-ios27-artifacts.py --flight-ready` refuses it on three recorded blockers in `IOS27-FLIGHT-BLOCKERS.toml` |
| F3 | `PongUfs` on the 27 storage ABI; the userdata image is built | OS volume matched, APFS mounted, `launchd` execs |
| F4 | panel and touch | SpringBoard frame, then a tap opens Settings |

### What the official arm64e page requires, and where this board stands

`docs/zh/porting/arm64e.md` (live page re-read 2026-11-20) makes arm64e conditional on five checks,
and records the result in the device's `porting.toml`. They are not a whitelist of marketing names;
they are measurements. Our position:

| Requirement (official wording) | How it is checked | Our status |
| --- | --- | --- |
| Every enabled CPU implements FEAT_PAuth (address and generic keys) | `ID_AA64ISAR1_EL1` APA or API, GPA or GPI non-zero; or `ID_AA64ISAR2_EL1` APA3 and GPA3 | **partial** 2026-11-18: one core reported `ISAR1 APA=0b0101` -- `FEAT_PAuth` with EPAC, PAuth2, FPAC and FPACCOMBINE, so PAC itself is present -- but the probe sampled 1 of 8 cores and decoded GPA/GPI from the wrong bits (power lane, 2026-11-20), so "every enabled CPU" is not established |
| XNU runs at EL1 and can write the five key registers | writing `APIAKey`/`APIBKey`/`APDAKey`/`APDBKey`/`APGAKey` at EL1 does not trap | **not measured** -- needs the fixed F0 probe |
| PAC instructions do not trap at EL1 or EL0 | `PACIA` changes a pointer and `AUTIA` restores it, on every core | **not measured** -- same probe |
| The SoC is listed under SoC support | the SoC repository exists and is listed | `UniXNU-sm8475-common` exists; the page's device table names only sheng/SM8550, so this needs an upstream row rather than a local claim |
| Native 4 KiB first-level translation | same as the arm64 profile | **measured**: `granules: 4 KiB BCM2837, TCR_EL1_BOOT=0x00000022a5192519, ARM_PGBYTES=4096` |

Three of the five are therefore still open -- the all-core PAC census and the two EL1 measurements, which
are the same probe. That is the honest answer to
"how far away is the first bootable iOS 27 image": the gap is not the ARMv9 SKU or the absence of
published Darwin 26 sources -- the profile already runs `xnu-12377.121.6` with the Darwin 26 system
calls and KPIs (`profiles/os/ios-27.0.1-24A446/patches/xnu/series:2` says exactly that), which is the
same construction sheng uses -- it is these two measurements plus the loader and prelink work below.

The page also states the fact that governs F2: **an iPadOS 27 kernelcache is `MH_FILESET` with its
symbol table stripped, and kext code calls straight into the kernel, so the arm64 prelink step does
not apply.** Read literally, that says the instrument that produced our 384 unresolved references and
2,688 stub sites may be the wrong instrument for this OS profile. Settling that is F2 work; until it
is settled the flight gate treats the map as unproven, not as fine.

### What the first PAC capture says

`ios-mondrian`'s probe ran once on the board (2026-11-18; the capture names the
iOS 16 shim, and the image's own hash was not recorded, so treat the command as
reproducible only from that repository):

```
ISAR1 0x0010011101211052   ISAR2 0x0000000000000000
FEAT APA 5  API 0          GPA 1  GPI 0
RESULT no FEAT_PAuth -> arm64 only (max IOS 18)
```

The verdict line is wrong and the probe was wrong with it. `APA = 0b0101` is
FEAT_PAuth with EPAC, PAuth2, FPAC and FPACCOMBINE (the power lane decoded the
field table on 2026-11-20); `API = 0` only says the *generic* keys are
missing, and arm64e authenticates code and data pointers with the address keys
(APIA/APIB/APDA/APDB). The probe's gate required `apa && api && gpa && gpi`, and
printed GPA/GPI from `[15:12]`/`[19:16]` (JSCVT/FCMA) instead of
`[27:24]`/`[31:28]`; it also read one core, so an eight-core board was answered
by one sample.

So one core of eight has PAC, which is what Armv9 requires of the core that was sampled -- not yet the
same statement as every enabled CPU having it. What the
capture does **not** contain is the second and third steps — the key registers
read back at EL1 and `PACIA`/`AUTIA` changing a pointer — because the probe
stopped at its own gate. Those are one boot away with the fixed probe, and the
kernel side of the gate is not passed until they are recorded.

The probe lives in `ios-mondrian`'s `shim/`, and that checkout is worked in
parallel for the iOS 16 line, so the fix travels as
`patches/ios-mondrian/pac-probe-arm64e-gate.patch`: it applies to `shim/pac.c`
and `docs/PAC_PROBE.md` and changes nothing unless `PAC_PROBE=1` is exported
(`shim.c` calls `pac_probe()` only under that define). Build the probe from a
copy of that shim, never in the shared checkout, so its `out/` stays the iOS 16
line's.

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
and is never applied. It sits under `legacy/` for a mechanical reason:
`apply-core-patches.sh` globs every top-level `patches/unixnu-core/*.patch` and
sets `status=1` when one neither applies nor reverse-applies, which is what
this one does against today's framework: it fails on `UniXNURamDiskDxe.c` at
line 161, on `UniXNURamDiskDxe.inf` at line 11 and on `Config.c` at line 35,
all inside the framework's own `package/UniXNUPkg` tree. Its content is also upstream or superseded: the boot-image `verify()`
change is in the framework, and the K60 initrd/ramoops/config deltas live in
`uefi-mondrian`'s vendored `Platforms/Xiaomi/UniXNUPkg`, which resolves ahead of
the framework's copy.

## What the sheng port already answers

`E:/hackios/UniXNU-sheng` maintains the same OS profile
(`"os_profile" = "ipados-27.0.1-24A446"`, `board.toml:9`) on an SM8550 board, so
its `patches/xnu-12377/series` is a second opinion on the same kernel. It has 17
entries against our 30. Reading the difference answers a question our series
cannot answer from the inside: which of our patches exist because xnu-12377
lacks something, and which exist because we replace a catalog component.

**Fork-induced.** `drivers/ArmCpu/ArmCpu.cpp` in this repository is a 779-line
fork of the Darwin 22 CPU provider; the catalog component
(`components.toml` `id = "ArmCpu"`, `revision = 93a5030c`, 823 lines) starts the
secondary CPUs itself through `psciCall (hvc, 0xc4000003ULL, affinity &
0xff00ffffffULL, entry, 0)` at `drivers/ArmCpu/ArmCpu.cpp:773` and declares
none of `psci_smp_init`, `psci_smp_start_cpu`, `psci_smp_cpu_running`,
`psci_smp_cpu_off`, `pong_cpu_startup_finished`. Sheng has no `drivers/ArmCpu`
at all and lists `component:ArmCpu` in its archives, which is why its kernel
never needed any of the five symbols. Our four patches in that family —
`armcpu-sleep-hook.patch` (a kernel-side definition because ld64-port rejects an
undefined weak *data* symbol from a force-loaded archive), `0532`, `0540` (a real
241-line `psci_smp.c`) and `0541` — are the price of the fork, not a gap in
12377. Replacing the fork with the catalog component removes them; until then
they are what makes the link complete.

**Toolchain-induced.** `ptrauth-string-discriminator.patch` and
`0533-k60-v-crypto-syntax.patch` exist only because we build on Linux with
upstream clang: the four-argument `__ptrauth(...)` spelling and the q-register
crypto mnemonics are Apple-clang extensions. Sheng builds on macOS
(`.github/workflows/package.yml`: `runs-on: macos-26`, then `xcodebuild`) and
carries neither.

**Board-induced.** `0541-k60-virtual-timer-guard.patch` skips the
`CNTP_CTL_EL0` write because this firmware leaves the EL1 physical timer in a
state the kernel must not touch. Sheng's patches never mention `CNTP_CTL`. The
iOS 16 line already had the same guard (`patches/xnu/zzzz-pong-virtual-timer.patch`),
so this is the board, not Darwin 26.

**Genuinely missing from 12377, and we do not have it.**
`zzzz-sheng-ipados27-bringup.patch` (35 files) carries the `T0SZ_USER != T0SZ_BOOT`
work: `osfmk/arm64/proc_reg.h` gains
`#if defined(BCM2837) && !defined(__ARM_16K_PG__) && defined(__arm64e__) #define T0SZ_USER 17ULL`
so user pmaps get four-level tables and a 47-bit TTBR0 range, with the pmap
geometry, `TCR_EL1` rewrite and `start.s` changes that follow from it. Its
comment states the reason: arm64e user code expects pointer-authentication codes
above bit 46, and libobjc strips `isa` with a 43-bit mask. Nothing in
`patches/xnu-12377/` or `patches/xnu/` mentions `T0SZ_USER` or `TTBR0`. Stage 0
stops at `bsd_init` and never enters EL0, so this does not block F1, but any
phase that runs userland will meet it — and sheng has already written the
answer.

The remaining 22 entries on both sides are per-driver work (BT, wifi, storage,
appsync, tracing) whose overlap is only `bsd/kern/kern_exec.c` and
`bsd/kern/bsd_init.c` as anchor files; they are not competing solutions to the
same problem.

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
