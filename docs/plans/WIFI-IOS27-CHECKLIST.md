# Wi-Fi on iOS 27.0.1 (24A446): checked list

## Read this first (hard facts, 2026-11-19)

- main is still the iOS 16 line (dddce57f). feat/bt-ios27-port (9f7c0d06) is the 27
  kernel line, and it does NOT contain the GPU/display line: 2a8dba3c is not its
  ancestor (629 behind / 86 ahead against main). Moving main to 27 is a real merge,
  not a fast-forward.
- patches/xnu/series (227 entries over 271 patch files, 16 KiB pages) and
  patches/xnu-12377/series (24 entries, 4 KiB pages) are two different patch sets.
  Measured 2026-11-19: the patches/xnu/series file is byte-identical on feat/bt-ios27-port
  (same sha256), i.e. the bt line kept the whole 16 set as its test bed and applies the
  12377 series instead. Most 16 entries do not apply to 12377 unchanged.
- The 27 kernel line carries no network patch at all. patches/xnu-12377/series is
  ptrauth, armcpu-sleep-hook and the 0500-0526 k60-bt-qbt-* Bluetooth series only.
- The wifi patch set (patches/wifi/series, 12 entries) exists on feat/bt-ios27-port
  byte for byte, but its targets do not: drivers/PongWifi/** is absent there, and so
  are scripts/build-k60-ath11k.py, scripts/build-k60-wifi-native.py,
  scripts/pong_paths.py, scripts/prepare-k60-wifi.py and
  scripts/build-xnu-4k-baseline.sh. Only drivers/NativeUfs/PongUfsTransport.cpp
  (0004) and scripts/build-pong-platform-macos.py (0006) exist. Porting wifi to 27 is
  therefore moving a tree, not applying a patch.
- The SoC layer we depend on is xNekom/UniXNU-sm8475-common feat/xnu-12377
  (20a30fd6), which feat/bt-ios27-port:unixnu.lock already pins as
  [source.sm8475] commit = 20a30fd623dbcfacdd71350a24fae67a2158884f.
- Nothing here has been on the device. Every step below is build-only until the fork
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

- [ ] B1 [DEV] Move drivers/PongWifi/** onto the 27 branch as a tree, not as
  patches/wifi/0001. Exit: git ls-tree origin/feat/bt-ios27-port:drivers/PongWifi
  lists PongWifiNet.cpp, PongWifiPlatform.cpp, PongWifiAbi.h, PongWifiScanPolicy.h.
- [ ] B2 [DEV] Carry the build scripts (build-k60-ath11k.py, build-k60-wifi-native.py,
  pong_paths.py, prepare-k60-wifi.py) and a 27 equivalent of
  build-xnu-4k-baseline.sh (it is absent on 27; the 4 KiB page size is now an
  arch-layer property). Exit: python3 scripts/build-k60-wifi-native.py completes
  against the 27 tree and prints the archive path.
- [ ] B3 [DEV] Add configs/mondrian_wifi_defconfig and
  configs/mondrian-wifi-sm8475.json to the 27 branch, with CONFIG_XNU_PONG_WIFI=y and
  CONFIG_XNU_BUILD_ARCHIVES=y. Exit: the defconfig names both switches and
  scripts/build-strict.sh selects libPongWifiNative.a.
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
- [ ] B6 [DEV] Re-run the width stamp against the 27 station archive. Exit:
  teardown27 rc=0 with no "has no abi/nw_abi.stamp" note.

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
  bed. The 27 line record is patches/xnu-12377/series (24 entries).
- [ ] D2 scripts/build-xnu-4k-baseline.sh does not exist on 27; the 4 KiB tables come
  from profiles/arch/arm64e there.
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
