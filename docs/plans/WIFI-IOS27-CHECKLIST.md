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
- The 27 side has one Wi-Fi-specific kernel patch: 0542-k60-association-event-cluster.patch.
  The event carries a 24 B kernel header, 16 B en0 name descriptor and 540 B result; the
  old code rejected totals over configuration-derived MLEN, while the patch permits Apple
  IEEE80211 events up to MCLBYTES and allocates a cluster when needed. The actual patch
  applies to the pinned 12377 source and its offline regression compares the original and
  patched block. The remaining series entries cover ptrauth, Bluetooth, CPU/boot and other
  K60 work; see the per-entry audit in docs/research/wifi/SHENG-KERNEL-REFERENCE.md.
  drivers/PongWifi is carried as a tree plus six ABI files, not as patches/wifi/*.
- Reference sources include UniXNU-sheng for the kernel and driver layers, as required
  by the lead's audit request (separate from agent-message iron rule 12). Both trees use
  the same iOS 27 family; sheng origin/main is pinned at c8f92b208068eeaa4cd2b0f592671f04ee70076e
  for this audit. docs/research/wifi/SHENG-KERNEL-REFERENCE.md compares all 25 sheng
  series entries with our 31; it separates the 540-byte event fix from sheng's chosen
  launchd-cache/supplicant integration, which does not establish a universal C2 requirement.
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

## A. Reference layouts implemented and checked offline

These checks establish the implementation and its fixtures. They do not establish the
wire contract of the actual 24A446 consumer. The sheng scan/result and capability
references include IO80211 26C5035r (macOS), so C1-C3 still need target evidence.

- [x] A1 Reference scan record: 0x8e8 bytes, elements[2048] at 0x8c, timestamp at 0x8d0.
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
- [x] B2 [DEV] Historical driver-symbol criterion only. A scratch link produced
  non-zero PongWifi definitions, but it used nine scratch definitions and is not a
  bootable or reproducible current-build acceptance. A stub-free raw link still needs
  a complete arm64e station archive. F1 prelink/panic-stub and DarwinBoot arm64e
  MH_FILESET issues are downstream platform gates, separate from that raw link.
  Main 3cc8cbc9 dispatches build-xnu-4k-baseline.sh by board.toml os_profile: 16.6.1
  keeps PONG, ios-27.0.1-24A446 uses build-xnu-generic.sh with BCM2837. The device
  fixes retained here are the Linux-capable build-firehose.sh, canonical
  0530-k60-spi-availability.patch and the XNU_PONG_WIFI force-load hook. The driver
  has no PONG machine-configuration conditional that silently compiles it out.
  Both archive builders accept --target; use arm64e for the 27 kernel. An arm64
  archive can be ignored while the rest of a kernel links, so a successful link alone
  is insufficient. build-k60-ath11k.py derives the ld -r architecture from the target.
  For stage 0, --smmu4k-kit adds ArmSmmu4K objects that the 16 line gets from the
  Adreno archive; do not use it when the kernel already force-loads those definitions.
  --no-host-hooks removes the pong_ufs_ready and k60_usblog_console_up waits behind
  PONG_WIFI_HOST_HOOKS. These options close platform imports, not the station gap.
  Main 0540/0541 answers imports from our ArmCpu fork, which shadowed catalog ArmCpu;
  that was not an intrinsic 12377 export gap. Lead's current libcc_kext.a is arm64e.
  Read-only inspection accepts none of the three existing station candidates. The only
  arm64e one still defines neither nw_wifi_power nor nw_wifi_scan_frequencies;
  teardown27g imports both. Source definitions in nw_mainline.c do not prove packaging.
  scripts/check-wifi-station-api.py searches source text (its expression also matches
  prototypes), so a green result is supplementary only. The archive evidence and
  acceptance inputs are in SHENG-KERNEL-REFERENCE.md section H.1 and
  docs/research/wifi/evidence/ios27-station-contract.json.
  scripts/build-wifi27-kernel.sh consumes an existing driver archive, runs the kernel
  build with --os ios-27.0.1-24A446, then counts symbols; it compiles neither station
  nor driver archive. Its six host cases verify the wrapper, not a completed build.
  On relocation, rewrite absolute paths in generated make/dependency/compile records
  together with the whole tree. The earlier partial move cannot support a claim that
  ext4 buys nothing; the later complete move was materially faster. Missing jobserver
  propagation is a separate issue. Do not promise a universal cold-build duration.
  Fresh-tree prerequisites include valid submodule admin directories, immutable
  reference content (separate mode-only drift), actual ArmCpu/ArmDTPlatform archives
  and aligned target/deployment settings. Historical workarounds in SBL-MISSION
  section 66 are not current framework acceptance; recheck the selected revision.
- [x] B3 [DEV] Wire wifi into the 27 side without touching the 16 default (done
  2026-11-20): configs/mondrian_ios27_wifi_defconfig carries every stage-0 switch plus
  CONFIG_XNU_PONG_WIFI=y, and board.toml keeps the 27 default on
  mondrian_ios27_defconfig, so a first 24A446 boot still gets the stage-0 kernel.
  scripts/tests/test-wifi-ios27-config.py asserts the ten properties that matter (both
  switches, the stage-0 boundary kept, the 27 override unchanged, the 16 mapping
  unchanged, build-strict.sh reading the .config and exporting the archive, the link
  force-loading it, and the refusal when the switch is on without an archive).
- [x] B4 [SOC] Confirm the 12377 kernel exports what the driver links against (done
  2026-11-20). llvm-nm --defined-only on the linked 27 image
  (mach.development.bcm2837.unstripped.noctf, 35,613,936 B) finds all three:
  _kev_post_msg, _mbuf_allocpacket, _ifnet_input. The three are kernel-side symbols, so
  the scratch stubs used to get that image linked do not affect the answer.
  The IO80211 side is ours: PongWifiNet.cpp:1153-1173 defines IO80211Controller and
  IO80211Interface as local stubs over IOService/IONetworkInterface, so the driver does
  not link against Apple IO80211Family. This does not prove which transport or framework
  the actual 24A446 userspace consumer uses.
  Symbol presence alone did not establish event delivery: the original kev_post_msg
  code rejects the 580 B envelope. Patch 0542 and its executable allocation/copy regression
  cover that kernel limit; subscriber delivery still needs runtime verification.
- [ ] B5 [SOC] 4 KiB pages: the 27 kernel uses 4 KiB tables, the 16 driver was written
  against 16 KiB. Exit: the archive builds with the 27 page shift and the selftest
  offsetof asserts still hold. This is a page/DMA/SMMU check, independent of B6 width.
- [x] B6 [DEV] Re-run the width stamp against the 27 station archive (done 2026-11-20).
  Exit: teardown rc=0 with no "has no abi/nw_abi.stamp" note. Verified both ways: the
  stamped 27 station (ie_bytes=2048, header_sha256 ec0b8227...) rebuilds the kext with
  rc=0 and zero stamp notes, while the ath11k-badstamp fixture (ie_bytes=1024) stops the
  build with "carries ie_bytes=1024 but this build carries 2048: rebuild the station".
  The negative case is the point: a kext at 2048 over a station at 1024 disagrees about
  where elements end, and nothing at link time notices. The builder checks ie_bytes,
  not header_sha256; matching sidecars alone do not bind an archive to its build header
  or establish the two modern station API definitions. SBL-MISSION.md 67.7.

## C. The one shape only the 24A446 binary can settle

- [ ] C1 [SOC] Establish the actual 24A446 caller transport, then its envelope.
  Our existing 22H374 selector-0 path already accepts 0x3c30 input with a payload
  capacity of 0x3c00 at +8 and a 40-byte request at +0x3c08. Output capacity is not a
  fixed returned length: scalar GET can return 4 bytes and SET zero. newUserClient
  establishes a connection; it does not by itself establish the selector length
  contract. sheng's non-macOS branch refuses user clients while its macOS branch keeps
  one alongside ioctl. Exit: matching 24A446 caller/receiver analysis, or a target
  trace showing ioctl versus selector, request type, input size, output capacity,
  actual output size and return code. Do not infer a universal ioctl-only path.
- [ ] C2 [SOC] Determine whether the target 24A446 wifid requires a signed launchd
  supplicant/service or can use the Apple80211 ABI directly.
  sheng's sheng-wifi-launchd-cache.patch documents its own /usr/libexec/unixnu-wpa_supplicant
  integration, not a universal requirement. Its check-wifi-launchd.py builds and signs a
  cache but reports hardware_service_started=False. Our 0527 patch supplies reusable
  XPC-cache mount machinery for Bluetooth; that does not prove Wi-Fi needs the same service.
  Exit: inspect the actual 24A446 Wi-Fi userspace path or obtain runtime evidence showing
  whether wifid scans with our kext alone / requires the service. Keep unchecked until then.
- [ ] C3 [DEV] kSupportedChannels flag word: sheng sets 0x80 on every entry of its static
  20-channel supported answer (package/WifiNet.cpp:695-699); we enumerate the live list
  without it (PongWifiNet.cpp:900-918). Exit is a ladder, not one log: L0 (field, writer,
  Ath12k uninvolved) is done; L1 disassembles the 16.6.1 wifid selector-27/254 reply
  parser for an 0x80 mask; L2 needs the 24A446 consumer binary; L3 is an on-device GET 27
  with the same-BSSID scan/current flags and the Settings row. Evidence at L0 or L1b keeps
  C3 open. Do not add 0x80 until the target-generation consumer is identified; a missing
  row alone is not evidence. Ladder and boundary: docs/research/wifi/SHENG-KERNEL-REFERENCE.md
  section I.

## D. Not true on 27 (do not carry these over)

- [ ] D1 patches/xnu/series (227 entries / 271 files, 16 KiB pages) does not apply to 12377. Most
  rows are ios16-*, native-4k-*, offline-* and mockfs-*; they belong to the 16 test
  bed. The 27 line record is patches/xnu-12377/series (31 entries). The trap is the OS
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
  bsd_init). Wifi must not depend on them: the 27 archive is built with
  --no-host-hooks, which drops the pong_ufs_ready and k60_usblog_console_up waits, so
  stage 0 does not need NativeUfs. 0004/0005 are the only wifi patches whose targets
  still exist; the driver tree itself is carried whole.
- [ ] D4 The 16 line reports 102 channels: 14 at 2.4 GHz, 29 at 5 GHz and 59 passive
  6 GHz entries. The 24A446 path hides the 59 passive entries, so after generation detection
  the expected count is 43 (14 + 29), not 88. A query before gModern27Client latches may
  still report 102; confirm the actual 27 wifid request order from its binary/log.
- [ ] D5 The 16 line kAuthType answers 0x8; 27 answers 0x10. A 27 log showing 0x8 means
  gModern27Client never latched: look for a 0x14e8 scan request or a 0x290 join before
  blaming the password.
- [ ] D6 Event descriptors: our legacy path posts one descriptor (name + payload),
  while the reference-aligned modern path posts two. This is producer behaviour; it
  does not establish what the target daemon requires. Check the received wire envelope
  and subscriber result before diagnosing a 24A446 event failure.

## E. Bring-up order once the fork reaches bsd_init

- [ ] E1 [DEV] Hand the Lead a verified 27 image with CONFIG_XNU_PONG_WIFI=y for a
  scheduled device boot with console capture attached. Exit: "wifi-net: station start"
  and "wifi: radio ... applied"; a boot that dies before bsd_init is a kernel result,
  not a Wi-Fi observation. Only the Lead owns the device slot.
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

## G. 飞行判据与本线的关系

- 权威 gate 是 `E:/hackios/k60-gates/scripts/check-ios27-artifacts.py`（395 行，
  sha256 `b6216d66…`）。本仓那份 232 行、没有 `--flight-ready`、不读 blockers 账本；
  它不能当判决，等 merge 刷新，不要手抄。
- 该 gate 检查镜像自洽（头、fileset、载荷重放、ADT、boot.img、prelink 计数、open blockers），
  **不读链接输入**。本线五种历史失败里，错架构归档、桩链接、镜像身份三类对它不可见。
  复核与两条建议断言：`docs/research/wifi/FLIGHT-CRITERIA-REVIEW.md`。
- 不要直接给 `IOS27-FLIGHT-BLOCKERS.toml` 加 Wi-Fi 归档条目：那是全局账本，一条 open
  会让所有 27 镜像拒飞，包括没有 `CONFIG_XNU_PONG_WIFI=y` 的 stage-0 试飞。
