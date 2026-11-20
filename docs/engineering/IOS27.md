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

The host half of that last sentence has a recipe on this branch:
`scripts/build-native-ufs-linux.py` compiles the three units with the flags of a recorded
IOKit compile, adds `-D XNU_NATIVE_UFS=1 -D XNU_SOURCE_STORAGE=1` plus
`build/storage-abi/include`, and archives `libNativeUfs.a` with `llvm-ar`. Against the
24A446 tree it produces `NativeUfs.o` 212,256 bytes, `PongUfsTransport.o` 331,112 bytes,
`verified_root.o` 10,936 bytes and a 556,720-byte archive, within eight bytes of the
archive the 16.6.1 recipe builds. Without `build/storage-abi/include` the transport unit
stops at `IOKit/storage/IOBlockStorageDevice.h`, so that include is not optional for it;
the script prints a note rather than failing because the other two units do not need it.
The script reports and stops: selecting the component in `board.toml` and linking the
archive from the 27 builder stay with the owners of those files, so the table above still
shows four gaps.

Linking is the other half, and it does not hold yet. Adding the archive to the recorded kernel
link turns fourteen undefined symbols into twenty-six. Eleven of the twelve new ones belong to
`IOBlockStorageDevice`: `__ZTV20IOBlockStorageDevice`, its meta-class, `init`, `@free` and
the five dispatch slots the vtable names. The twelfth, `_armcpu_timer_interrupts`, comes from
`NativeUfs.o` and disappears once `libArmCpu.a` is force-loaded beside it.

The cause is structural rather than a missing file. The 16.6.1 kernel is one `MH_EXECUTE`
image that defines those eleven symbols itself (`llvm-nm --defined-only` lists
`__ZTV20IOBlockStorageDevice` and ten more). On 27 the same classes ship in the separate
fileset entry `com.apple.iokit.IOStorageFamily`: the class-name strings sit at file offsets
0xa0f345, 0xa0f7e3 and 0xa0f7fd, all inside that entry, and the kernel proper therefore cannot
resolve a vtable that lives in a sibling entry. Three ways out, none of them free: bind the
eleven imports to the addresses the prelinked entry exports, which is what
`scripts/bind-ios16-storage.py` does for 16.6.1 off `mac-build/storage-abi/interface-audit.json`;
ship the driver as its own kext entry instead of force-loading it into the kernel; or give the
link a stub object for the class. Until one of them lands, `XNU_NATIVE_UFS=1` fails at the
link on 27, and a green kernel build only means the switch is still off.

`scripts/check-xnu27-storage-link.py` runs that comparison: it links the recorded kernel twice, reports every new undefined symbol with its class and referrers, and writes the delta to `report.json`. On the 24A446 object tree it exits 0 with `gap` and lists the eleven imports; `--require-linkable` turns the gap into a failure, so the day a bindings object lands the checker starts failing and has to be retired.

To reproduce the check by hand: read
`build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/.LDFLAGS` (NUL-separated), run the recorded
`clang++` with `-target arm64e-apple-ios27.0` and the Apple `ld` from
`/opt/unixnu-linux/CommandLineTools/usr/bin` on `PATH` (the recorded line expects the build's
own shim), append `-Wl,-filelist,link.filelist -o <out>`, and diff the undefined symbols with
and without `-Wl,-force_load,libNativeUfs.a`.



### The pinned kernelcache carries no symbols either

The binding route above assumes the prelinked entry still names its methods. It does not, and
the pin is now measurable offline. The 24A446 kernelcache fetches without the 10 GiB IPSW:
the builder calls @@ipsw.kernelcache()@@ (@@scripts/unixnu/ipsw.py:259@@), which reads the
@@KernelCache@@ member of @@profile.toml@@ with HTTP range requests, runs @@lzfse -decode@@ and
keeps the arm64 slice at @@out/ipsw/24A446/kernelcache.decompressed@@. The result is 77,987,840
bytes with sha256 @@fa07057bf34f33af1ec26681ad0c87c13e5aaa548a300740eddb0e92876e5f95@@, which is
the pin at @@profiles/os/ios-27.0.1-24A446/profile.toml:35@@.

What that file does not contain:

- @@com.apple.iokit.IOStorageFamily@@ sits at file offset 0xa0e670 with @@filetype 11@@, ten load
  commands, @@LC_SYMTAB@@ @@nsyms 0@@, and neither @@LC_DYLD_INFO_ONLY@@ nor
  @@LC_DYLD_EXPORTS_TRIE@@. Every kext entry in the collection is stripped the same way, so
  the eleven imports cannot be read out of it.
- Its @@__DATA_CONST@@ (virtual address 0xfffffff008313f98, 0x5c40 bytes) is not a 190-slot
  table either. Decoding the words as chained rebases against the kernel base
  0xfffffff007004000, which the three segments confirm (@@__TEXT@@ 0xa0e670 maps to
  0xfffffff007a12670, @@__TEXT_EXEC@@ 0x3303fd0 to 0xfffffff00a307fd0, @@__DATA_CONST@@
  0x130ff98 to 0xfffffff008313f98), leaves 235 of 2952 words in a code segment, 52 in a data
  segment and 2665 outside every segment of all 305 entries.
- The longest contiguous run of code pointers is 113 slots at 0xfffffff0083196d8, and all 113
  point into @@com.apple.kernel@@'s @@__TEXT_EXEC@@, not into this entry. The first words of
  this entry's own table are eleven code pointers, eleven more, then a data pointer
  (0xfffffff00b978b60) and a zero word.

So the 16.6.1 derivation cannot be replayed by reading the collection: the slot order still has
to come from compiling @@IOBlockStorageDevice.cpp@@ with a macOS toolchain and reading its
DWARF, and whether that order lines up with a fileset entry whose table does not look like a
vtable is unproven. Shipping the driver as its own kext entry is the route that matches what
Apple itself does; the bindings route now carries an extra unknown that the 16.6.1 line never
had.

## What the storage exports say

**Where this stands (2026-11-20):** the storage preflight is `pending` while
`CONFIG_XNU_NATIVE_UFS` is off, and pending is not a pass. Against this
branch's configs it fails on one thing only: 190/190 slots agree with Apple's
table, both report bindings (collection and kernelcache) match, and one target,
`0xfffffff007044478`, is still inside the input `__TEXT` instead of the
output layout.

The link experiment in the previous section ends with eleven undefined
IOBlockStorageDevice symbols. Two ways out were on the table: bind them (A) or
ship the driver as its own fileset entry (B). The choice is not a matter of
taste, it is one question about the artifact:

> Does com.apple.iokit.IOStorageFamily export those symbols?

`scripts/check-ios27-storage-exports.py` answers it for any kernelcache,
prelinked kernel or kernel-collection member, offline:

```sh
python3 scripts/check-ios27-storage-exports.py \
  --kernelcache out/ipsw/24A446/kernelcache.decompressed --out out/storage-exports.json
```

It walks the fileset entries, reads every export trie and symbol table, and
reports per symbol whether an entry exports it (with the address), defines it
in a symbol table, or holds nothing but the string. Exit status is 0 for both
answers; `--require-exported` is for the day the artifact is supposed to
carry them.

| Input | Shape | Entries with an export trie | Symbols |
| --- | --- | --- | --- |
| `kernelcache.decompressed` (24A446, pinned by `kernelcache_sha256`) | MH_FILESET, 305 entries | 0 | none exported, none defined |
| our prelinked `kernel.macho` (run 44518998961) | MH_FILESET, 32 entries | 0 | none exported, none defined |
| iOS 16.6.1 `kernel.macho` (control) | MH_EXECUTE, 50,123 symbols | 0 | all eleven defined, e.g. `__ZTV20IOBlockStorageDevice` at `0xfffffff0060fbf50` |

The control matters: on the 16.6.1 kernel the reader finds every symbol, so a
"nothing" answer is a fact about the artifact and not about the reader. Both
27 artifacts answer `not-exported`: not one of the 305 Apple entries
carries an export trie or a symbol table, and IOStorageFamily itself has
`nsyms 0`, no `LC_DYLD_INFO_ONLY`, no `LC_DYLD_EXPORTS_TRIE`. Apple links
the kernel collection itself, so there is no sibling-symbol namespace left in
the shipped file to bind against.

Consequence:

- **A is out** for this artifact. It needs exported addresses, and the only
  copy of them was in Apple's build tree.
- **B is the route**: NativeUfs becomes its own fileset entry, the way real iOS
  storage drivers ship. The cost is that the kext packaging path has no
  evidence yet; the builder only knows how to `-force_load` archives into
  `com.apple.kernel`.
- **C (a stub) stays forbidden**: a stub that always succeeds makes "no
  storage" and "broken storage" the same sentence.

### The constant that cost a rebuild

The first version of this reader reported "0 fileset entries" for a kernel that
has 32 of them. It used `0x80000033` as `LC_FILESET_ENTRY`; that value is
`LC_DYLD_EXPORTS_TRIE`. The fileset entry is `0x80000035`. Two traps sit
behind that one number:

- the name is not at the file offset in `entry_id`: `entry_id` is relative to
  the start of the load command, so the name begins at `command + entry_id`;
- the name strings do exist in the file either way, which is why the wrong
  constant still looked plausible: `strings` finds
  `com.apple.kec.corecrypto` whether or not a fileset entry carries it.

The remembering aid is the pair: 0x33 trie, 0x35 entry.

## Route B: the driver as its own fileset entry

The exports audit settled that route A cannot be finished offline: no entry of
the pinned 24A446 kernelcache keeps an export trie or a symbol table, and the
same holds for our own product. A definition-backed binding therefore has to
come from a sibling entry assembled at prelink time, which is route B. This
section is the design, not the implementation: the builder and XnuPrelink stay
frozen while F1 runs, and `scripts/check-ios27-storage-entries.py` measures the
one fact that tells whether the route has been taken.

### What B changes

1. The driver stops being an archive that joins the kernel link. Today
   `scripts/build-xnu-generic.sh:649` points `UFS_ARCHIVE` at
   `build/native-ufs/libNativeUfs.a` and the kernel links it with
   `-Wl,-force_load`, so the link needs every symbol the archive imports --
   including the eleven `IOBlockStorageDevice` members that only the sibling
   entry defines (`scripts/check-xnu27-storage-link.py` reports exactly those
   eleven plus `_armcpu_timer_interrupts`).
2. The same objects become an `MH_KEXT_BUNDLE` (filetype 11) with a
   `kmod_info`, an `OSBundleLibraries` list naming
   `com.apple.iokit.IOStorageFamily` and `com.apple.kec.corecrypto`, and
   `_PrelinkExecutableLoadAddr` set. That is the shape
   `kits/XnuPrelink/emit_prelink_orig.py:117` parses out of
   `__PRELINK_INFO`; a module that is not filetype 11 is rejected there.
3. The prelink step has to accept a component that is not in the original
   kernelcache. `kits/XnuPrelink/native_prelink.py:130` `plan()` derives the
   closure from the roots' `OSBundleLibraries` and resolves every pointer in
   `_PrelinkLinkKASLROffsets`; a pointer into an undeclared component fails
   with `Undeclared pointer dependency`. Our bundle must therefore declare the
   storage family and be listed as a root.
4. The product's outer fileset has to list the bundle. Our 32 entries come from
   the original collection plus the roots the profile selects
   (`profiles/os/ios-27.0.1-24A446/profile.toml` `[kernel.prelink] roots`), and
   nothing in `scripts/build-xnu-generic.sh` assembles a kext of our own.

### The one fact that decides it

`python3 scripts/check-ios27-storage-entries.py --kernelcache <kernel.macho>`
prints the entry list and says whether any name matches `NativeUfs` or
`native-ufs`. Against the F1 product it answers:

    entries: 32
    no entry matches NativeUfs, native-ufs
    ios27-storage-entries: absent

An absent entry is the correct answer today and exits 0; `--require-entry`
turns it into a failure, which is the form a gate wants once the route is
implemented. The reader reuses the Mach-O parser of
`scripts/check-ios27-storage-exports.py`, so the two answers cannot disagree
about what an entry is.

### Acceptance criteria for B

- the checker answers `present` for the product, and the matching entry is a
  kext bundle whose `kmod_info` start and stop are non-zero;
- the prelink report carries no `Undeclared pointer dependency` for the new
  component, and the component extents do not overlap the native segments;
- `scripts/check-xnu27-storage-link.py` reports no new imports for the kernel
  image itself: the eleven storage symbols must have left the kernel link;
- `hardware_verified` stays false in every report until F3 boots with the
  switch on.

### Why B may be unnecessary

The reference board on the same profile does not take route B. It compiles the
public base class and registers it late, which removes the eleven imports
without assembling a fileset entry; the next section records that in detail.
B stays the fallback if that route is rejected, and the checker above measures
either.

## What the sheng board already solved

`E:/hackios/UniXNU-sheng` is the same profile as this line
(`board.toml:9` `os_profile = "ipados-27.0.1-24A446"`), an SM8550 board, and
its kernel lane runs. It is a required reference source for the kernel and
driver layers, and it answers three questions this line had been asking alone.

### Which of its 18 patches touch the Data gate or storage

The device series is `patches/xnu-12377/series`, 18 entries. Four of them are
storage or root-start work:

- `source-storage-runtime.patch`, 10 lines: `bsd/kern/bsd_init.c:796` gains
  `extern void native_source_storage_start(void) __attribute__((weak_import));`
  guarded by `if (&native_source_storage_start)`, so the runtime starts after
  `vfsinit()` and an image without the archive boots unchanged.
- `zzzz-sheng-ipados27-bringup.patch`, 35 files: `osfmk/arm/cpu_common.c`
  (patch line 788) adds `sheng_sigp_recover()` -- definition at patch line
  801, call sites 818 and 828, the cross-file declaration at 1137 and its call
  at 1151 -- with the comment that this fixes "random early hangs and UFS root
  failures under SMP: the I/O thread's wakeup IPI to that core was silently
  dropped".
- `zzzzzzzzzz-sheng-sigp-reinit-assert.patch` relaxes the same file's assert
  using the `sheng_sigp_recovered` counter, so a recovered SIGP is not
  reported as a failed re-init.
- `sheng-bluetooth-runtime.patch` and `sheng-wifi-launchd-cache.patch`, both
  `bsd/kern/kern_exec.c`: they mount `/private/var/ngpu/bluetooth-lib` over
  `/usr/lib` and `bluetooth-bin` over `/usr/sbin` through
  `native_gpu_addon_mount`, gated by `sheng-bluetooth`.

The other 12 are outside storage: idle, amp, the audio addon mount, three
latency/trace patches, the wifi association event, appsync runtime and user
trust, and three profile/diagnostic patches.

Not a patch, but the same lane: `configs/sheng_ipados27_defconfig:8-20` is the
complete Data gate configuration this line's
`scripts/check-xnu27-source-storage.py` measures --
`CONFIG_XNU_SOURCE_STORAGE=y`, `CONFIG_XNU_SOURCE_STORAGE_TABLES="userdata"`,
`CONFIG_XNU_NATIVE_RAM_BLOCK=y`, `CONFIG_XNU_OWNER_ROOT_AUDIT=y`,
`CONFIG_XNU_OWNER_ROOT_TRUST=y`, `CONFIG_XNU_OWNER_CACHE_MOUNT=y`,
`CONFIG_XNU_OWNER_CACHE_STARTUP=y`, `CONFIG_XNU_OWNER_BOOT_MANIFEST=y`,
`CONFIG_XNU_OWNER_DATA_MOUNT=y`, `CONFIG_XNU_OWNER_UNION_SYSTEMOS=y`, and
`CONFIG_XNU_OWNER_DATA_VOLUME_UUID="2A5E9027-D9E1-40F9-983C-41BD3F1994F5"`;
`board.toml:20` selects `component:ShengUfs` and
`build-sheng-source-storage.py --policy-dir scripts/policies/ipados-27.0.1-24A446`,
and `board.toml:28` lists `com.apple.iokit.IOStorageFamily`,
`com.apple.kec.corecrypto` and `com.apple.filesystems.apfs` among the
prelink roots.

### Which of our 29 device patches it already solved

- Bluetooth runtime mounting: our `0526-k60-bt-runtime-mount.patch` and
  `0527-k60-bt-launchd-cache.patch` are the same mechanism as
  `sheng-bluetooth-runtime.patch` -- the same two source directories over the
  same two system paths through `native_gpu_addon_mount`, behind a boot
  argument. Ours adds the stage/status counters and lives in its own
  `native_bt_runtime_prepare()`; theirs sits inside
  `native_gpu_addon_prepare()`. Neither is wrong, and nothing needs to move.
- The PSCI glue: sheng's series has no `psci_smp`, no
  `pong_cpu_startup_finished` and no `ArmCpu` patch at all, because
  `board.toml:20` selects the catalog `component:ArmCpu`, which carries its
  own `psciCall()` (`E:/hackios/ArmCpu/ArmCpu.cpp:699`, PSCI_VERSION at
  `:1259`). Our 0540/0541 exist because `drivers/ArmCpu` in this device
  repository shadows that component and declares six `extern "C"` entry
  points. **This is the one place where this line reinvented something the
  catalog already ships**, and the honest reading is that 0540 is a repair of
  the shadowing, not new capability.
- SIGP recovery: we carry nothing comparable, and its comment names this
  line's F3 failure mode (UFS root failures under SMP). It is the first thing
  to evaluate when the Data mount starts failing per-CPU.

### Did we reinvent the storage route

No -- and that is the important part, because sheng's answer is a fourth route
that neither A nor B describes:

- `scripts/build-sheng-source-storage.py` prepares the public headers from a
  pinned `IOStorageFamily` feed (`scripts/prepare-storage-headers.py`,
  revision `7edb88fbae296fb7c8ce2f64e115e116e566d51c`; this tree already
  carries the prepared result at `build/storage-abi/include` with a
  `headers.json` naming feed `IOStorageFamily-a4f5240a`).
- It compiles `IOBlockStorageDevice.cpp` from that feed, replacing
  `OSDefineMetaClassAndAbstractStructors(IOBlockStorageDevice,IOService)` with
  a deferred metaclass whose parent is `native_source_storage_parent()`.
- `package/SourceStorage.cpp:243` defines that parent as
  `OSMetaClass::getMetaClassWithName("IOBlockStorageDevice")` captured after
  `OSKextLoadKextWithIdentifier("com.apple.iokit.IOStorageFamily")` succeeds
  (`package/SourceStorage.cpp:264` `native_source_storage_start()`), and
  panics unless `getClassSize() == sizeof(IOBlockStorageDevice)`. Registration
  then runs through `preModLoad()`/`postModLoad()`, and the UFS service is
  created by `native_ufs_source_create()`.

The consequence: the eleven storage symbols are compiled into the archive
itself, the original family stays loaded and serves as the metaclass parent, and
no sibling-entry import is needed. The cost is compiling Apple's public
`IOBlockStorageDevice.cpp` from the pinned feed -- the license file ships with
it (`APPLE_LICENSE`), and the headers are already prepared on this host. That
path is viable on this board and is evaluated first on the evidence above; B
stays the fallback. Note that `scripts/check-ios27-storage-entries.py` measures
route B only: under route D the correct answer is still `absent`.

## Route D: the deferred metaclass, in five questions

Route D compiles Apple's public `IOBlockStorageDevice.cpp` from the pinned feed,
replaces its registration macro with a metaclass initialiser that resolves its
parent at run time, and links that object into the kernel instead of importing
the class from the sibling entry. The lead asked five questions before this
route may be planned; each is answered below by a measurement on this host, not
by an argument. Nothing here has run on the board, and `hardware_verified` stays
false in every report.

### 1. Which pin, and is the clone on this host

`profiles/os/ios-27.0.1-24A446/profile.toml:108` reads:

    # Apple sources of the macOS 26.5 release that pairs with xnu-12377.121.6 (same pins as ipados-27.0.1-24A446).

and the entry it introduces is the pin: `:110 name = "IOStorageFamily"`,
`:112 git = "https://github.com/apple-oss-distributions/IOStorageFamily.git"`,
`:113 ref = "IOStorageFamily-337.100.1"`,
`:114 commit = "7edb88fbae296fb7c8ce2f64e115e116e566d51c"`.

Two clones exist and both sit exactly on that commit:
`/home/emilelu/ios27-out/feeds/IOStorageFamily-a4f5240a` and
`/opt/k60/trees/ios27-out/feeds/IOStorageFamily-a4f5240a`. The source file itself
is `IOBlockStorageDevice.cpp` in either: line 2 is the 1998-2015 Apple
copyright, lines 4-21 the APSL 2.0 header, line 28
`OSDefineMetaClassAndAbstractStructors(IOBlockStorageDevice,IOService)` -- the
single line route D rewrites.

A pin proves where the code came from. It does not prove the binary ships that
ABI, which is question 2.

### 2. Does the 24A446 binary agree with the pin

`com.apple.iokit.IOStorageFamily` in the pinned kernelcache
(`/home/emilelu/kc24A446/ipsw/24A446/kernelcache.decompressed`, sha256
`fa07057bf34f33af1ec26681ad0c87c13e5aaa548a300740eddb0e92876e5f95`,
`MH_FILESET`, 318 load commands, 305 entries) is a `MH_KEXT_BUNDLE` at
`fileoff 0xa0e670`. Its segments are `__TEXT` `0xfffffff007a12670` size
`0x2030`, `__TEXT_EXEC` `0xfffffff00a307fd0` size `0x1c884`, `__DATA`
`0xfffffff00b9789e0` size `0x3b9`, `__DATA_CONST` `0xfffffff008313f98` size
`0x5c40` and `__LINKEDIT` `0xfffffff00b9ec000` size `0x73b91`.

The class size is written into the binary at three call sites. Each xref of the
class-name string -- file offsets `0x3307c24`, `0x3307cc8` and `0x33080e0` -- is
immediately preceded by the word `52801203`, `mov w3,#0x90`. The global
metaclass constructor at `0xfffffff00a30c0d8` takes the name in `x1` and
`0x90` in `w3` as well. `0x90` is 144, and the pinned source compiles to
`sizeof(IOBlockStorageDevice) == 144` (a `-fdump-record-layouts` probe
against `build/storage-abi/include` reports size 144, align 8). The two agree
byte for byte on the one number the run-time assertion checks.

The vtable is `__ZTV20IOBlockStorageDevice` at `__DATA_CONST`
`0xfffffff008314d88` (file `0x1310d88`, header two words of zero); the protected
constructor at `0xfffffff00a30bc6c` writes `vtable+0x10` into `x0` and signs it
with `pacda` and `movk x17,#0xcda1`, and slot 7 is the `getMetaClass` getter
returning the metaclass at `0xfffffff00b978bb0` (file `0x4974bb0`).

Reading that table needs the right pointer format. The outer
`LC_DYLD_CHAINED_FIXUPS` declares `pointer_format = 8`, which is
`dyld_chained_ptr_64_kernel_cache_rebase`
(`/opt/unixnu-linux/CommandLineTools/SDKs/MacOSX.sdk/usr/include/foreign/mach-o/fixup-chains.h:173`:
`target:30`, `cacheLevel:2`, `diversity:16`, `addrDiv:1`, `key:2`, `next:12`,
`isAuth:1`) with base `0xfffffff007004000`. Decoded that way the table has
**190 slots**, then three zero words, then the next table. Decoded as
`ARM64E_KERNEL` (the first guess) the same bytes produce 260 slots and a table
that runs into its neighbour -- a wrong answer that still looks plausible.

The strongest check is not the count but the signature: the 190 slots of the
source object and the 190 slots of the binary carry the **same `diversity`
value in 190 of 190 positions**. A vtable copied from a different build, or
built from a different header, would differ in at least one discriminator.
Per-slot evidence is at `E:/k60-work/scratch/bt-route-d/vtable-slots.json` and
the reader that produced it at `E:/k60-work/scratch/bt-route-d/audit_binary.py`.

### 3. Does the object build for this target

The compile is a replay of a recorded IOKit command line, not a fresh guess:
`build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/iokit/DEVELOPMENT/KernelConfigTables.cpo.json`
(537 arguments, `--target=arm64e-apple-ios27.0`,
`-fptrauth-function-pointer-type-discrimination`). With the source and output
swapped, `/opt/unixnu-linux/llvm/bin/clang-24` emits
`/tmp/src4th/IOBlockStorageDevice.o`: `cputype 0x100000c`,
`cpusubtype 0x80000002`, `filetype 1`, and it defines
`__ZTV20IOBlockStorageDevice`, `__ZN20IOBlockStorageDevice10gMetaClassE`
and `__ZN20IOBlockStorageDevice9MetaClassC2Ev`. That is the object the link
test in question 4 uses.

### 4. Do the definitions coexist with the sibling entry

They are not supposed to coexist: the eleven imports are meant to disappear
because the object defines them. The link replay measures whether that happened.
`scripts/check-xnu27-storage-link.py` forces the archive into the recorded kernel
link twice; the same test run by hand with the deferred object added gives:

| link | undefined symbols | what the archive added |
| --- | --- | --- |
| control | 14 | -- |
| `libNativeUfs.a` | 26 | 11 `IOBlockStorageDevice` members + `_armcpu_timer_interrupts` |
| `libNativeUfs.a` + `IOBlockStorageDevice.o` | 16 | `_armcpu_timer_interrupts` + `_native_source_storage_parent` |
| `libNativeUfs.a` + `IOBlockStorageDevice.o` + `libArmCpu.a` | 15 | `_native_source_storage_parent` only |

Not one `IOBlockStorageDevice` or `OSMetaClass` symbol is undefined in the
last two rows: the implicit `OSMetaClass` constructor the source calls is
satisfied by the kernel, and the eleven members come from the object. The one
surviving name, `native_source_storage_parent`, is defined by
`package/SourceStorage.cpp` in the same runtime that would be linked next -- it
is the deliberate seam, not a leak.

At run time the two copies are separate objects with separate names. The
original family loads first (`OSKextLoadKextWithIdentifier`), the runtime takes
its `IOBlockStorageDevice` metaclass, and our class registers under
`UniXNUBlockStorageDevice` with that metaclass as parent, so the OSMetaClass
registry never sees two entries with one name. What the two do share is the
vtable layout and its PAC discriminators, which question 2 measured as equal.
The run-time guard is explicit: `package/SourceStorage.cpp:273-278` compares
`getClassSize()` with `sizeof(IOBlockStorageDevice)` and panics on a mismatch.

The limits are real: no instance has been created on the board, the load order
inside a fileset boot is unproven, and a `native-source-storage` value other
than 1 leaves the whole runtime unloaded.

The run-time chain leaves little room for ambiguity, which matters on a board
whose only log is the screen: every step panics with its own message.
`SourceStorage: metaclass initialized before original family` (`:245`) means
the class registered too early; `SourceStorage: IOStorageFamily load failed
%x` (`:272`) and `SourceStorage: APFS load failed %x` (`:286`) name the
missing bundle; `SourceStorage: original base layout %u differs from source
%lu` (`:277`) is the class-size mismatch that question 2 measured as equal
for 24A446; `root policy handoff or authentication failed` (`:283`) is the
policy table; and `SourceStorage: UFS %s failed (root step %u: %s)` (`:304`)
carries the driver's own root step and reason. A screenshot of any of these
names the stage without a serial console.

### 5. What blocks the Linux recipe

`scripts/build-sheng-source-storage.py` is the reference implementation of this
route. Its host assumptions, checked one by one on this machine:

- `xcrun --sdk macosx --show-sdk-path` (`prepare-storage-headers.py:29`) is a
  Linux shim here: it prints the literal word `macosx` and exits 0. It cannot
  stand in for an SDK. The prepared headers this tree already carries at
  `build/storage-abi/include` (with `headers.json` naming feed
  `IOStorageFamily-a4f5240a`) make that step unnecessary on this host.
- `llvm-objcopy --remove-section=__DATA,__mod_init_func` works (`rc 0`).
- `llvm-objcopy --globalize-symbol=__GLOBAL__sub_I_IOBlockStorageDevice.cpp`
  **fails**: `llvm-objcopy: error: option is not supported for MachO`. This
  is the one hard blocker, and the reason it is load-bearing is in the
  runtime: `package/SourceStorage.cpp:15-17` binds three of these constructor
  names with `__asm__` -- `source_storage_base_init` is
  `__GLOBAL__sub_I_IOBlockStorageDevice.cpp`, `source_storage_ufs_init` is
  `__GLOBAL__sub_I_NativeUfs.cpp`, `source_storage_ram_init` is
  `__GLOBAL__sub_I_NativeRamBlock.cpp` -- and calls them at `:289-291`
  between `preModLoad` (`:287`) and `postModLoad` (`:292`). The section
  has to leave `__mod_init_func` for that to be safe, because
  `OSRuntimeInitializeCPP` runs that section itself
  (`libkern/c++/OSRuntime.cpp:499-501`), which would register the class
  before the original family is loaded and trip
  `SourceStorage: metaclass initialized before original family` (`:245`).
  Leaving the section in place is therefore not a workaround; the two real
  alternatives are an explicit `extern "C"` wrapper emitted into the
  generated source, or renaming the constructor at generation time. Neither is
  written yet.
- `xcrun ar rcs` (`:240`) falls through to GNU `ar 2.42` and succeeds, so the
  archive step does not need macOS.
- `libtool` and `dwarfdump` are not on this path: the 27 recipe uses `ar`, and
  `dwarfdump` appears only in the 16-line binding derivation
  (`scripts/derive-ios16-storage-bindings.py`).

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

## The one target the prelink did not move

The round-17d map has 133 distinct owner targets with no address. All but one
sit in the output collection's `__DATA` or `__DATA_CONST`; the exception is
`0xfffffff007044478`, which fits the input `__TEXT`
(`0xfffffff007004000` + `0x1a0000`) and no output segment
(`0xfffffff007184000` + `0x1a0000`). It is a rebinding defect, separate from
the missing symbol table: the target was never translated, so naming the symbol
would not move it, and moving it would not name the symbol.

`scripts/check-ios27-prelink-closure.py --require-translated` fails while any
such target remains; on the pinned inputs it exits 1 and prints the address.

Opening the storage line is a separate gate, and its closing condition is three
checks in one run: `CONFIG_XNU_NATIVE_UFS=y` in the resolved config,
`--require-translated` reporting no target left in the input `__TEXT`, and
`scripts/check-ios27-storage-vtable.py --require-entry` passing on the built
collection.

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
