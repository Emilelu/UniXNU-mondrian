# Wi-Fi on iOS 27.0.1 (24A446): checked list

## Read this first (hard facts, 2026-11-19)

Rewritten 2026-11-20, when main itself became the 27 line.

- main is the iOS 27 line (stage 0: an arm64e kernel that stops at bsd_init, profile
  ios-27.0.1-24A446 as an iPhone 17,2 on xnu-12377). The iOS 16 line is archived as
  archive/ios16-20261120, and feat/bt-ios27-port is deleted; its content is in main.
- Both operating systems are still reachable from one main: board.toml maps
  [package.defconfig] ipados-16.6.1-20G81 = mondrian_defconfig and
  ios-27.0.1-24A446 = mondrian_ios27_defconfig, and [os_overrides."ios-27.0.1-24A446"]
  removes kernel.pong_native_driver_source and the PongUfs component. A 27 change must
  not alter the 16 default.
- patches/xnu/series (16 KiB pages) and patches/xnu-12377/series (4 KiB pages) are two
  patch sets that main carries side by side; the 27 profile's patch_series is
  arch:patches/xnu/series + soc:patches/xnu-12377/series + os:patches/xnu/series +
  device:patches/xnu-12377/series. Most 16 entries do not apply to 12377 unchanged.
- The 27 side has no network patch at all: patches/xnu-12377/series is ptrauth,
  armcpu-sleep-hook and the 0500-0526 k60-bt-qbt-* Bluetooth series only. drivers/PongWifi
  is present in main as the proven 16 tree, and the 24A446 ABI is carried on top of it
  (branch feat/wifi-ios27-tree), so wifi still moves as a tree plus six files, not as
  patches/wifi/*.
- The SoC layer is xNekom/UniXNU-sm8475-common feat/xnu-12377 (20a30fd6), pinned by
  main's unixnu.lock as [source.sm8475] commit =
  20a30fd623dbcfacdd71350a24fae67a2158884f.
- Pitfall numbering moved: main already uses P-230 through P-253 for GPU, gate and
  boot-lock work, while the wifi bring-up notes kept P-230-P-241 on the old branch.
  Anything ported from there is renumbered before it lands.
- Nothing here has been on the device. Every step below is build-only until the 27 line
  reaches bsd_init.

## Legend

- [SOC] depends on the xNekom SoC layer (feat/xnu-12377) or the 12377 kernel ABI.
- [DEV] can be done in this device repository, offline, today.
- Exit criteria name the exact log line or field value that closes the step.

## A. Shapes already landed on feat/wifi-ios27-abi (done, build-verified)

- [x] A1 24A446 scan record: 0x8e8 bytes, elements[2048] at 0x8c, timestamp at 0x8d0.
  Exit: the static_assert on sizeof(scan_result) == PONG_SCAN_RECORD_24A446 compiles,
  and the host selftest prints "50 checks passed, 0 failed".
- [x] A2 Association request 0x290, completion event 540 bytes (result at 0x214,
  has_result at 0x218). Exit: same selftest, the three layout checks pass.
- [x] A3 Request-86 scan (0x14e8): names at 0xc, type at 0x200, channels at 0x210;
  request-10 type at 0x34. Exit: test-pong-abi.py reports 0 failure.
- [x] A4 Capability bits 22/46 in a 12-byte answer. Exit: kCardCaps answers 12 bytes
  when req_len <= 12.
- [x] A5 Teardown: stopRequested -> nw_wifi_stop(); the network-stack client string
  pong-wifi-stop quiesces the interface. Exit: llvm-nm --defined-only shows
  _pong_wifi_station_stop and _pong_wifi_net_stop.
- [x] A6 Element-width stamp: the station build writes abi/nw_abi.stamp
  (ie_bytes=2048); the kext build refuses a mismatch with the P-230 message.
  Exit: a deliberately wrong stamp fails the kext build with that exact RuntimeError.
- [x] A7 Scan policy port (PongWifiScanPolicy.h): 60 s held, 15 s settle, 20 s rescan.
  Exit: the selftest eleven policy checks pass.
- [x] A8 Reference answer surface: pending join, strict 24A446 credentials, drain before
  join, explicit-disconnect suppression, rate, live RSSI, power switch, event logging,
  6 GHz channels hidden, two-descriptor events. Exit: test-wifi-sbl-mission.py prints
  0 failure(s).

## B. What the 27 kernel line must gain before wifi can even link

- [x] B1 [DEV] Put the 24A446 ABI on the branch feat/wifi-ios27-tree (done 2026-11-20): the six files
  (PongWifiNet.cpp, PongWifiPlatform.cpp, PongWifiAbi.h, PongWifiScanPolicy.h,
  ath11k/pong_sae.c, ath11k/pong_sae.h) plus their host tests, on top of main's
  drivers/PongWifi tree. Exit: scripts/tests/test-wifi-sbl-mission.py and
  test-pong-abi.py print 0 failure(s), and compile-teardown2.sh builds the kext against
  both nw_abi.h generations (16 header + ath11k-abi1, 27 header + ath11k-abi27).
- [x] B2 [DEV] Run the 27 kernel through the generic builder and prove the driver is in
  it (done 2026-11-20 for the driver half; a clean link without the scratch stubs still
  waits on [SOC] psci_smp_* and the fork's 27 station archive, see the exit note below). The builder question is settled by main's 3cc8cbc9: scripts/build-xnu-4k-baseline.sh
  now dispatches on board.toml [board] os_profile through scripts/pick-xnu-builder.sh, so
  the 16.6.1 line keeps the Pong builder (MACHINE_CONFIGS=PONG) and every other profile -
  including ios-27.0.1-24A446 - runs scripts/build-xnu-generic.sh, the framework builder,
  which has no PONG.h to find. Three things still stood between that and a 27 link, all
  device-side and all fixed on feat/wifi-ios27-tree:
  (a) scripts/build-firehose.sh was the 16 copy (34 lines, unconditional xcodebuild) and,
  because tree assembly copies the device repository last, it shadowed the framework's
  Linux-capable version (60 lines, xcrun clang + libtool). It is now the framework file
  byte for byte.
  (b) xnu ships its own Availability macros in EXTERNAL_HEADERS/Availability.h and that
  copy stops at __API_AVAILABLE, while 12377's libsyscall headers annotate with
  __SPI_AVAILABLE (gethostuuid.h:41, spawn/spawn.h:64-78), which only a Darwin 26 SDK
  defines. prepare-xnu.py copies that header into the fakeroot on every build, so the
  build died in libcc_kext on gethostuuid.h and no fakeroot edit survived. Fixed by
  patches/xnu-12377/availability-spi.patch (empty fallback definition) in the device series.
  (c) the generic builder never linked a wifi archive. scripts/build-xnu-generic.sh now
  arms the same XNU_PONG_WIFI=1 -> -Wl,-force_load,$PONG_WIFI_ARCHIVE path the Pong
  builder has.
  Exit, and this is the part that matters: a successful link is not proof - -force_load
  over an archive whose objects were compiled out also links, and so does one whose objects
  are the wrong CPU subtype: the 27 kernel is arm64e while both builders defaulted to
  arm64-apple-ios16.0, and ld only warned "ignoring file … built for iOS-arm64" before
  linking a kernel with zero driver symbols. Both scripts now take --target, and
  build-k60-ath11k.py derives the ld -r arch from it (ld -r run as arm64 drops every
  arm64e member and libtool then writes an empty archive). Two more wifi-side undefined
  symbols had to be closed: ArmSmmu4KBuild / ArmSmmu4KProgramDisabledContext, which the
  16.6.1 line gets from libPongAdrenoPlatform.a and the stage-0 line does not link
  (--smmu4k-kit compiles drivers/PongAdreno/ArmSmmu4K into the driver; never arm it on a
  kernel that force-loads the Adreno platform), and pong_ufs_ready / k60_usblog_console_up,
  which only the 16.6.1 kernel exports (weak declarations do not work under arm64e - taking
  a function's address needs authentication and ld still reports it undefined - so
  --no-host-hooks compiles both waits out behind PONG_WIFI_HOST_HOOKS). After that the
  driver contributes no undefined symbol. What still stops a clean 27 link is not wifi:
  psci_smp_* and pong_cpu_startup_finished (12377 has no osfmk/arm64/psci_smp.c; the 16
  patch also creates PONG.h and does not apply), the two llvm profile internals in an
  arm64 libcc_kext.a, and nw_wifi_power / nw_wifi_scan_frequencies from the fork's 27
  station. To count the symbols anyway, a scratch-only stub archive defined those nine
  names for one link (never committed, never flown): 35,613,936 B image, 30 PongWifi
  symbols, -force_load visible in the link command. Proof of the driver, not a shippable
  kernel. The 27 image must define a
  non-zero number of PongWifi symbols, checked by scripts/check-wifi-symbols.py (exit 1 on
  zero, self-tested by scripts/tests/test-wifi-symbols.py), and
  scripts/check-wifi-station-api.py cross-checks the nw_wifi_* the archive leaves undefined
  against the station tree (2 referenced, 2 defined on the fork's 27 tree). Build with --os
  ios-27.0.1-24A446 after scripts/install-os-profile.sh; with --os ipados-27.0.1-24A446 it
  applies the 16 series and dies at osfmk/arm64/start.s:33. scripts/build-wifi27-kernel.sh
  runs that whole path in one command and finishes by counting symbols (6 cases in
  scripts/tests/test-build-wifi27-kernel.py).
  Cost of a cold 27 kernel on this host, measured 2026-11-20: 2,154 sources under the xnu
  work tree compile at 2.7-4.4 objects per minute, so the bootstrap pass alone is 8-13
  hours. Do not chase the filesystem: three tests settled that the wall clock is the make
  graph, not I/O. A copy of the whole tree on ext4 recompiled from zero at the same rate
  (rsync of 482 MB, 927 objects carried over, then every object rebuilt), so relocation
  buys nothing and loses the work already done. Forcing MAKEFLAGS=-j8 on the outer make
  changed nothing either. The cause is visible in the log: the outer make at
  scripts/build-xnu-generic.sh:841 passes MAKEJOBS to the sub-make without a jobserver, so
  the sub-make prints "jobserver unavailable: using -j1" (33 times) and compiles one file
  at a time while eight cores idle at load 3. The second pass is cheap: XNU_BOOTSTRAP only
  gates the archive block at scripts/build-xnu-generic.sh:604, so the compile flags are
  identical and make relinks what the first pass already built.
  Two more things bite before that check can run on a fresh 27 tree, and neither is the driver:
  an uninitialised submodule and an executable-bit-only dirty reference tree. The first is
  drivers/QcaBluetooth/.git pointing at a worktree admin directory that no longer exists, which
  makes git submodule foreach fatal and unixnu stop with git failed (128); re-running
  git submodule update --init drivers/QcaBluetooth fixes it. The second is refer/corecrypto-2023
  reporting 1798 modified files that are all mode 100644 -> 100755 with zero content change,
  because the 9p copy marks everything executable; build-corecrypto-14.py:36 refuses that as
  'The crypto reference must stay immutable' until git config core.fileMode false is set in the
  assembled tree. The 27 board's own archive list also names component:ArmDTPlatform and
  component:ArmCpu, but neither carries a build recipe in components.toml, so archive_plan() skips
  them and build-fileset-release-reference.py then fails on the missing
  build/armdt-platform/libArmDTPlatform.a; the 16.6.1 list has no release-reference step, which is
  why this only shows on 27. Finally the target version disagrees with itself: version_env() sets
  UNIXNU_IOS_VERSION from the profile (27.0.1) while linux_env() pins DARWIN_TRIPLE to
  arm64-apple-ios17.0, so kernel_target.check_object expects (2, 27<<16) and rejects the objects it
  just built. Until the framework makes the triple follow the profile, a 27 run has to force both
  sides to 17.0. Tracked in SBL-MISSION.md 66.
- [x] B3 [DEV] Wire wifi into the 27 side without touching the 16 default (done
  2026-11-20): configs/mondrian_ios27_wifi_defconfig carries every stage-0 switch plus
  CONFIG_XNU_PONG_WIFI=y, and board.toml keeps the 27 default on
  mondrian_ios27_defconfig, so a first 24A446 boot still gets the stage-0 kernel.
  scripts/tests/test-wifi-ios27-config.py asserts the ten properties that matter (both
  switches, the stage-0 boundary kept, the 27 override unchanged, the 16 mapping
  unchanged, build-strict.sh reading the .config and exporting the archive, the link
  force-loading it, and the refusal when the switch is on without an archive).
- [ ] B4 [SOC] Confirm the 12377 kernel exports what the driver links against:
  kev_post_msg, mbuf_allocpacket, ifnet_input, IOService/IOUserClient.
  The IO80211 side is ours: PongWifiNet.cpp:1153-1173 defines IO80211Controller and
  IO80211Interface as local stubs over IOService/IONetworkInterface, so the driver does
  not link against Apple IO80211Family at all; only 27 wifid talks to the real one.
  Exit: llvm-nm --defined-only on the 12377 kernel or its prelink report shows
  _kev_post_msg, _mbuf_allocpacket and _ifnet_input.
- [ ] B5 [SOC] 4 KiB pages: the 27 kernel uses 4 KiB tables, the 16 driver was written
  against 16 KiB. Exit: the archive builds with the 27 page shift and the selftest
  offsetof asserts still hold.
- [x] B6 [DEV] Re-run the width stamp against the 27 station archive (done 2026-11-20).
  Exit: teardown rc=0 with no "has no abi/nw_abi.stamp" note. Verified both ways: the
  stamped 27 station (ie_bytes=2048, header_sha256 ec0b8227...) rebuilds the kext with
  rc=0 and zero stamp notes, while the ath11k-badstamp fixture (ie_bytes=1024) stops the
  build with "carries ie_bytes=1024 but this build carries 2048: rebuild the station".
  The negative case is the point: a kext at 2048 over a station at 1024 disagrees about
  where elements end, and nothing at link time notices. SBL-MISSION.md 67.7.

## C. The one shape only the 24A446 binary can settle

- [ ] C1 [SOC] Selector-0 envelope: 27 IO80211Interface::newUserClient may be
  0x3c30 in / 0x3c00 out instead of the 16 line 0x2000 / 0x1f00. Exit: the 24A446
  IO80211Family binary is disassembled and the two lengths are read from the
  externalMethod dispatch table; the driver outCapacity check is then set to that
  number and a request of that size is answered.
- [ ] C2 [SOC] Does 27 wifid require the signed launchd unixnu-wpa_supplicant /
  org.unixnu.wifi.control service (sheng route), or does it accept any correct
  Apple80211 ABI (ours)? Exit: launchctl print on 27 shows the service, or the console
  shows wifid scanning with our kext alone.
- [ ] C3 [DEV] kSupportedChannels flag word: the reference sets 0x80; we enumerate the
  live list without it (as zizhan does). Exit: on 27, Settings lists the 5 GHz row; if
  it does not, add 0x80 behind the gModern27Client gate and re-check.

## D. Not true on 27 (do not carry these over)

- [ ] D1 patches/xnu/series (227 entries / 271 files, 16 KiB pages) does not apply to 12377. Most
  rows are ios16-*, native-4k-*, offline-* and mockfs-*; they belong to the 16 test
  bed. The 27 line record is patches/xnu-12377/series (24 entries). The trap is the OS
  key: a 27 build must pass --os ios-27.0.1-24A446, because board.toml's
  [os_overrides."ios-27.0.1-24A446"] is what selects the 12377 series; with --os
  ipados-27.0.1-24A446 the 16 series is applied and apple-only-cpu-tunables.patch fails
  at osfmk/arm64/start.s:33.
- [ ] D2 the 16 builder's machine configuration does not exist on 27. 12377 has no
  config/MASTER.arm64.PONG (the arch profile adds MASTER.arm64.bcm2837 instead), so a
  build that forces MACHINE_CONFIGS=PONG dies with "Unsupported CURRENT_MACHINE_CONFIG
  PONG" in MakeInc.kernel before any driver is compiled. That is why the same entry
  script dispatches: 16.6.1 keeps PONG, 27 runs build-xnu-generic.sh on BCM2837.
- [ ] D3 configs/mondrian_ios27_defconfig deliberately sets CONFIG_XNU_NATIVE_UFS=n,
  CONFIG_XNU_NATIVE_ADRENO=n and CONFIG_XNU_NATIVE_LEGACY_DISPLAY=n (stage 0 stops at
  bsd_init). Wifi must not depend on any of them; our driver needs only the
  ArmDTPlatform and NativeUfs hooks, which is why 0004/0005 are the only wifi patches
  whose targets still exist.
- [ ] D4 The 16 line answers "wifi-net: supported channels 102: 2.4 GHz 14, 5/6 GHz 88"
  because 59 passive 6 GHz entries are in the station list; the 24A446 path hides them,
  so a 27 log must read 88 (14 + 74), or 102 only before the first scan request sets
  gModern27Client.
- [ ] D5 The 16 line kAuthType answers 0x8; 27 answers 0x10. A 27 log showing 0x8 means
  gModern27Client never latched: look for a 0x14e8 scan request or a 0x290 join before
  blaming the password.
- [ ] D6 Event descriptors: 16 posts one descriptor (16-byte en0 name + payload), 27
  posts two (name, then payload). A 27 daemon that logs "event 6 bytes 0" is reading
  the old shape.

## E. Bring-up order once the fork reaches bsd_init

- [ ] E1 [DEV] Build a 27 image with CONFIG_XNU_PONG_WIFI=y and fly it with the console
  attached. Exit: "wifi-net: station start" and "wifi: radio ... applied" in the
  console; a boot that dies before bsd_init is a kernel problem, not a wifi one.
- [ ] E2 [DEV] Open Settings -> Wi-Fi by hand inside the 15-minute window
  (k60_autoreset=900). Exit: a WiFiScanObserverNetwork line naming Emilelu_5G with
  BSSID c8:bf:4c:30:03:1c and a negative RSSI.
- [ ] E3 [DEV] Join the 5 GHz AP from Settings. Exit: "wifi: connected", then
  "wifi-net: en0 address 192.168.31.x, packets in ... out ...".
- [ ] E4 [DEV] Reconnect test. Exit: "WiFi lifecycle test PASS: reconnected BSSID
  c8:bf:4c:30:03:1c state=6 IPv4=1".

## F. Deliberately out of scope

- WPA3/SAE wiring (parked by the user; kmu1757/UniXNU-t970 BSD-2 clean-room unit in
  drivers/T970Wifi/T970WifiWpa3.c is the eventual base).
- mission37 (kernel association test behind a default-off boot-arg, plus log throttle):
  not scheduled.
- The application-layer HTTP work (WebKit 0xdead10cc) belongs to the lead.
- Registering the wifi archive in [components]/[kernel] archives: the UniXNU catalog
  schema builds from source_files only, so this needs a schema extension first. The
  archive is still selected by CONFIG_XNU_PONG_WIFI / XNU_PONG_WIFI_ARCHIVE, and
  scripts/check-kernel-archives.py now inspects it.
