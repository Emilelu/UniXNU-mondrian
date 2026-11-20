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
| F0 | PAC gate on the old kernel: `PAC_PROBE=1 BOARD=mondrian shim/build.sh`, one boot | FEAT_PAuth measured on the board on 2026-11-18 (`ISAR1` `APA=0b0101`, `API=0`: the address keys arm64e uses, no generic keys); the key-register write and the `PACIA`/`AUTIA` round trip still need one boot with the fixed probe |
| F1 | This profile + SM8475 `xnu-12377` series + Xcode 26 build (or the Linux toolchain below) | `kernel.macho` is arm64e with minos 27.0 and `NOUNDEFS`; `payload.img` packs it byte for byte with a pinned `/chosen/random-seed`; the firmware volume builds from the recorded pin; `boot/boot.img` (112 B shim + FD + appended DTB + payload) passes `scripts/check-ios27-artifacts.py`; `scripts/check-ios27-granules.sh` passes |
| F2 | `XnuPrelink` against the 24A446 fixture | prelinked `MH_FILESET` with the roots closed and the map recorded (built on Linux 2026-11-18: 32 entries, 384 symbols on the `--allow-missing` stub, reference `6bbb66dc`); on device `arm_init` → `bsd_init` → root-mount panic, cupid parity |
| F3 | `PongUfs` on the 27 storage ABI; the userdata image is built | OS volume matched, APFS mounted, `launchd` execs |
| F4 | panel and touch | SpringBoard frame, then a tap opens Settings |

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
FEAT_PAuth with EPAC and PAuth2; `API = 0` only says the *generic* keys are
missing, and arm64e authenticates code and data pointers with the address keys
(APIA/APIB/APDA/APDB). The probe's gate required `apa && api && gpa && gpi`, and
printed GPA/GPI from `[15:12]`/`[19:16]` (JSCVT/FCMA) instead of
`[27:24]`/`[31:28]`.

So the hardware side is answered: SM8475 has PAC, as Armv9 requires. What the
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

## The crypto provider the Data gate needs

`scripts/check-bluetooth-data-gate-chain.py` prints what the 27 defconfig still lacks
before `CONFIG_XNU_OWNER_DATA_MOUNT` can be switched on. The first rule in that
chain is `XNU_VERIFIED_ROOT_PROBE`, which requires two values:

- `XNU_SOURCE_CORECRYPTO14=1`, already supplied by
  `profiles/arch/arm64e/configs/common.config:2`;
- `XNU_CRYPTO_BOOTSTRAP=prelinked`, currently overridden to `"source"` by
  `configs/mondrian_ios27_defconfig:12` while the OS profile asks for `prelinked`
  at `profiles/os/ios-27.0.1-24A446/configs/ios.config:1`.

Prelinked changes one compile flag, not the patch series:
`scripts/build-xnu-generic.sh:184-201` rebuilds `prng_random.o` with
`prng_random.o_CFLAGS_ADD=-UXNU_SOURCE_CORECRYPTO14`. Replaying the recorded 24C
compile command with `-D` gives a 53,856-byte object holding
`source_corecrypto14_bootstrap`, `source_corecrypto14_start_once` and
`corecrypto_kext_start`; with `-U` the object is 42,672 bytes and none of the
three symbols exist. So prelinked removes the kernel-side starter entirely, and
the boot kernel collection has to carry `com.apple.kec.corecrypto`.

It does. Run 44518998961's `kernel.macho` is an `MH_FILESET` with 32
`LC_FILESET_ENTRY` records, and the last one is `com.apple.kec.corecrypto`
(`scripts/check-xnu27-crypto-provider.py --kernel ... --mode prelinked` prints
`bluetooth-crypto-provider: OK`). The 16.6.1 line is the opposite shape: its
`kernel.macho` is `MH_EXECUTE` with no fileset, which is why that line runs
`source` and links `libcorecrypto_kernel_noasm-namespaced.a`
(`scripts/build-xnu-generic.sh:606-610`).

Two traps in reading that artifact:

- `LC_FILESET_ENTRY` is `0x80000035`, not `0x80000033` (`0x33` is
  `LC_DYLD_EXPORTS_TRIE`); a parser using the wrong constant reports zero
  entries on a collection that has 32.
- `entry_id` is an offset from the start of its own load command, so the name
  sits at `command_offset + entry_id`. Reading it as a file offset yields empty
  names.

Prelinked is a build configuration the host can check today; it is not a runtime
guarantee. With it the kernel starts no corecrypto of its own, so the provider
exists only once the kext that owns the entry has started; a root probe that
runs earlier sees no crypto. That ordering is the first thing F3 has to measure
on the board, and the checker reports `hardware_verified: false` for exactly
that reason.

The one-line change is not applied here: `configs/mondrian_ios27_defconfig:12`
would become `CONFIG_XNU_CRYPTO_BOOTSTRAP="prelinked"`, and that line is the
only one that moves. The kernel series and the framework patches stay as they
are, so a build either links the same kernel minus the starter or fails at the
first kext that needs the provider.

## What the source storage closure still needs

`scripts/check-xnu27-source-storage.py --root .` reads the repository and prints the six
pieces the Data gate's last rule needs, each with the file and line that decides it.
Today it reports four gaps:

| Piece | State | Evidence |
| --- | --- | --- |
| the driver sources | present | `drivers/NativeUfs/NativeUfs.cpp` and `PongUfsTransport.cpp` |
| the 27 profile selects the component | gap | `board.toml:360` `include = ["ArmDTPlatform", "ArmCpu", "XnuPrelink"]` |
| the defconfig builds it | gap | `configs/mondrian_ios27_defconfig:20` `CONFIG_XNU_NATIVE_UFS=n` |
| the builder links this branch's archive | gap | `scripts/build-xnu-generic.sh:652` links `build/sheng-ufs/libPongUfs.a` under `XNU_NATIVE_UFS`; this line carries `drivers/NativeUfs`, not the sheng runtime |
| a patch installs the IOKit personality | present, from the arch layer | `UniXNU/patches/xnu-12377/native-aes-personality.patch` adds two NativeUfs entries to `iokit/KernelConfigTables.cpp`; neither carries `IONameMatch = ufshc`, which only costs a probe on every platform node because `NativeUfs::probe` filters on the DT `compatible` string (`drivers/NativeUfs/NativeUfs.cpp:58-64`) |
| the signed policy bundle | gap, and it cannot live in a repository | no bundle under `UniXNU/scripts/policies/ios-27.0.1-24A446`; `kits/VerifiedRoot` and `scripts/build-sheng-source-storage.py` do ship with the framework |

The single exception to the order is the first row of the chain rather than of this
table: `CONFIG_XNU_CRYPTO_BOOTSTRAP=prelinked` is a config line the host can check today
(see the section above), while every row here needs code or a key that does not exist
yet. The last step, turning on `BOOT_MANIFEST`, `CACHE_STARTUP`, `CACHE_MOUNT`,
`ROOT_AUDIT` and `ROOT_TRUST`, is what `scripts/check-bluetooth-data-gate-chain.py`
prints, and the two reporters agree on the order, so a green run of both is the
acceptance for F3.

The personality row is the one this table got wrong first: the device series has no such
patch, but the arch series applies before it, so a reporter that reads only
`patches/xnu-12377/series` reports a gap that is not there. The checker now walks every
layer named in `board.toml` `patch_series` and names the layer a patch came from, which is
also why the count above fell from five to four.

The entry compiles. Replaying the recorded compile of
`iokit/KernelConfigTables.cpo.json` from the 24A446 build tree against the series-applied
file with `-D XNU_NATIVE_UFS=1 -D XNU_NATIVE_RAM_BLOCK=1` returns 0 and a 3,536-byte object;
without those two defines the same record produces the shipped object. The replay needs the
record's `directory` as the working directory (`meta_features.h` is generated per directory)
and the compiler at `argv[0]`, because the stored `arguments` start at the first flag.

Two facts that keep the table honest. The 16.6.1 builder already links
`build/native-ufs/libNativeUfs.a` at `scripts/build-xnu-4k-baseline.sh:1054` and again at
`:1278`, so the archive shape is proven; what is missing is the 27 build selecting it.
And the 27 line builds on Linux, where nothing compiles `drivers/NativeUfs` yet, so
the component row needs a host recipe as well as the selection.

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
