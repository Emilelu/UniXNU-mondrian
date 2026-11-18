# SBL mission poll: cache AMSS after the direct BHIe push

Written 2026-11-18. Scope: why the direct candidate's remaining failure is the
host's cached execution environment, the successor that polls `BHI_EXECENV`
after `mhi_download_amss_image()` and then creates the MHI devices for the
AMSS channels, and the prewritten acceptance criteria for
`wifi-20261118sbl-mission4`. This is the evidence record for the mission-poll
candidate; c8 remains HOLD.

## 0. Conclusion first

| question | answer |
|---|---|
| What did the direct candidate prove? | The direct BHIe push works: the 2026-11-18 01:29 flight logged `amss bhie load ret=0 exec_env=1`, then the device reported `exec_env=2` (AMSS), `pm_state=4` (`MHI_PM_M0`) and `mhi_state=2` (`MHI_STATE_M0`). See `SBL-DIRECT.md` §6. |
| Why did the direct candidate fail? | `mhi_sync_power_up` (`pm.c:1277-1295`) waits on `MHI_IN_MISSION_MODE(mhi_cntrl->ee)`, but the host cached `ee=1` (SBL). The only EE event consumed was `execenv=1`; no later EE event updated the cache even though the device had reached AMSS. |
| What changes in this candidate? | After the direct `mhi_download_amss_image()` returns 0, the same worker polls `mhi_get_exec_env` for up to 2500 x 10 ms. On `MHI_EE_AMSS` or `MHI_EE_WFW` it assigns `mhi_cntrl->ee = mission`, calls `mhi_create_devices(mhi_cntrl)` so the IPCR channels (`ee_mask = 0x4`, AMSS-only) are created, and calls `wake_up_all(&mhi_cntrl->state_event)`, so `mhi_sync_power_up` sees mission mode instead of a stale SBL value and wakes from its wait. |
| Is this the official path? | Yes. UniXNU-sheng `516a7804` `package/MhiBoot.c:117-119` has `MhiWaitMission`, which polls the execution environment until AMSS/WFW after the BHIe image. Stock Linux has no equivalent poll after `mhi_download_amss_image`; the cached EE is only refreshed by an EE event. |
| Is this proven on K60? | **Yes — MHI and QMI/scan.** The 2026-11-18 09:17 flight produced a valid console at `E:/k60-work/evidence/usblog-20261118-091754/console.log` (85,874 B, SHA256 `59063d2d702e359de9e89b80d24ea09c13dcac7fc436ef573ad5f3bb98cd2bd3`): `exec_env=2 ... cached ee updated` :683, `MHI powered up: ee=2 state=2` :687, `chip_id 0x12` :697, `fw_version 0x20070039` :699, `hardware registered, 102 channels` :722, `scan starts on 42 channels` :724, `en0 is up` :727, `scan 1 finished, 12 networks` :785, SpringBoard present. |

## 1. Why this is the next single variable

The direct candidate's console is complete:
`E:/k60-work/evidence/usblog-20261118-012938/console.log` (237,343 bytes,
3,591 lines, SHA256 `9fff4a26237a3b6e795263a0a241c4dd2ab6aa42a84adbdde6b28cdaa3609c05`).
It records:

- `:648` `Pong MHI: device is in SBL without an EE event, BHI_STATUS=0x8b9a74ae; pushing the AMSS image`.
- `:685` `Pong MHI: bhie tx_status=0x2 seq=0x2 expected=0x24e1b3ae ret=19369` — the remaining-jiffy count shows the BHIe wait returned early; most of the 20 s was spent without a mission poll, not in the transfer.
- `:687` `Pong MHI: amss bhie load ret=0 exec_env=1` — the vector-table transfer completed.
- `:691` `Pong MHI: timeout after 20000 ms ee=1 pm_state=4 exec_env=2 mhi_state=2 MHISTATUS=0x201 MHICTRL=0x200`.
  The device is already in AMSS/M0; the host's `ee` cache is still 1/SBL.

Because the direct console exposes `exec_env=2` only in the 20 s timeout line,
the earlier 5 s mission poll was too short to rely on. The mission3 candidate
polls for 25 s, but that poll starts only after `mhi_download_amss_image()`
returns; `mhi_sync_power_up` still gives up after its own fixed 20 s wait. The
mission4 candidate therefore raises `mhi_ctrl->ready_timeout_ms` to 60 s in
`ath11k_mhi_start` (generated `ath11k/mhi.c:450`) while keeping the 25 s poll.
This lets the sync waiter stay alive long enough for the poll to cache AMSS.
The value survives `mhi_prepare_for_power_up`: that function only initializes
the device contexts and BHI/BHIE offsets (`init.c:1108-1188`) and does not
write either timeout field.

The path is reachable on this board: the direct flight logged
`Pong MHI: serial=0x22d0a7f3 ee=0 fbc=1 fw_sz=0` at `:632`, so
`mhi_async_power_up` saw PBL and queued `DEV_ST_TRANSITION_PBL`; the PBL case
calls `mhi_fw_load_handler`, which calls `mhi_ready_state_transition` at
generated `mhi/boot.c:618` and then enters the direct block at `:624`.

`mhi_sync_power_up` is the waiter that turns a stale cache into the final
`-ETIMEDOUT`; the fix is intentionally confined to that wait plus the existing
mission poll. No QMI, WMI, PCIe, rail or DMA change is included.

## 2. Source anchors

The patch lives in the build generator, not in a checked-in copy of the Linux
source. `E:/hackios/k60-wifi/scripts/build-k60-ath11k.py`:

- `:331`: declares `int i, j, amss_ret;`.
- `:356-370`: assigns `amss_ret = mhi_download_amss_image(mhi_cntrl);`; only
  when it is zero, runs the bounded `for (j = 0; j < 2500; j++)` poll. On
  `MHI_EE_AMSS` or `MHI_EE_WFW` it assigns `mhi_cntrl->ee = mission`, calls
  `mhi_create_devices(mhi_cntrl)` at `:362` so the AMSS-only IPCR channels
  (`ee_mask = 0x4`) get MHI device objects, calls
  `wake_up_all(&mhi_cntrl->state_event)` and logs
  `Pong MHI: exec_env=%d after AMSS download; cached ee updated`; it stops on
  `MHI_EE_MAX` and sleeps 10 ms between samples.
- `:236-241`: appends `bool pong_sbl_pushed;` to the pinned `linux/mhi.h` copy
  after `bool fbc_download;`.
- `:330-379`: the bounded 200 x 10 ms `BHI_EXECENV` poll, BHI_STATUS success
  gate and direct push that are unchanged from the direct candidate.
- `:448-459`: the `pm.c` SBL one-shot latch remains; a later EE event cannot
  download twice.
- `:275-287`: the `mhi_fw_load_bhie` status diagnostic remains available.
- `:158-163`: the generated `ath11k/mhi.c` gets
  `ab_pci->mhi_ctrl->ready_timeout_ms = 60000;`; generated anchor
  `ath11k/mhi.c:450`.

Generated source anchors from the mission archive:

| file | anchor |
|---|---|
| `mhi/boot.c` | direct block at :624-674; ready transition call :618; push log :647; `mhi_cntrl->ee = MHI_EE_SBL` :648; latch :649; `amss_ret = mhi_download_amss_image` :650; mission poll :651-664; `mhi_cntrl->ee = mission` :655; `mhi_create_devices(mhi_cntrl)` :656; wake :657; mission log :658 |
| `mhi/pm.c` | guard :828; latch :834; fallback download :843 |
| `pinned/linux/mhi.h` | `bool pong_sbl_pushed;` at :445 |
| `ath11k/mhi.c` | `ready_timeout_ms = 60000` at :450 |

The poll runs after `mhi_ready_state_transition` has left `pm_state=MHI_PM_POR`
and before `mhi_sync_power_up` has changed it, so the register window is the
same one that just completed the BHIe transfer. No new MMIO lifetime is
introduced. `mhi_sync_power_up` is already sleeping in
`wait_event_timeout(state_event, ...)`; writing the cached EE without a wake
would still end in the 20 s timeout, so the `wake_up_all` is part of the same
fix. Once the cached EE names AMSS, the mission block's `mhi_create_devices`
must also run for the IPCR channels, because `nw_qrtr_mhi` calls
`mhi_prepare_for_transfer` as soon as the worker probes.

State-worker safety: the `mhi_create_devices` call runs inside
`mhi_fw_load_handler`, which is executed by `mhi_pm_st_worker`; the MHI event
tasklet can still run `mhi_pm_m0_transition`
(`E:/k60-work/impl/wifi/work/src/linux-7.0.14/drivers/bus/mhi/host/main.c:861-862`)
and `mhi_send_cmd` rings the command doorbell itself (`main.c:1298-1303`), so
the synchronous `device_add` -> `nw_qrtr_mhi` probe cannot deadlock on M0 or on
a skipped command ring. The direct console shows only the SBL EE event (`:668`);
no later mission-mode EE event is present, so the stock mission transition does
not destroy and recreate the IPCR devices on this path.

Failure triage: `mhi_get_exec_env`
(`E:/k60-work/impl/wifi/work/src/linux-7.0.14/drivers/bus/mhi/host/main.c:153-158`)
returns `MHI_EE_MAX` when the `BHI_EXECENV` read fails, and the mission poll
treats that value as a hard stop. If a flight reaches AMSS but misses the
`cached ee updated` line, inspect the BHI register lifetime and this break before
concluding that the 25 s poll is too short.

## 3. Candidate identity

| field | value |
|---|---|
| tag | `wifi-20261118sbl-mission4` |
| built_at | 2026-11-18T03:41:57+08:00 |
| branch / head | `fix/wifi-mission-timeout` / `91c21c7cc71de684dc0b98cbd6784afdb9d5f5f3` (dirty 0) |
| `boot.img` | `E:/k60-work/artifacts/wifi-20261118sbl-mission4/boot.img`, 201,887,744 B, SHA256 `7646f5caf1b6fd03628587df2cdc915a24d8aca7115816af379858d9e6ac4a26` |
| kernel | `1ee83183537da2488267e98031f9ef41fb94baba24a3507d81ead5ef7023f4b3` |
| payload kernel | `e308664056ce2cb167a2c385ff6e3af7610ec36bbb5504a31724629b0e986987` |
| WiFi archive | `abe04821139df9b184df82bdd04f355e9374615807ca5e62629846ea867563a7` |
| ath11k archive | `a3793b0c3f587b20d148f04938436b96aaa18ccc41f78c087d77cdd487f2b120` |
| manifest | `E:/k60-work/artifacts/wifi-20261118sbl-mission4/build-manifest.json` |
| args | 31 / 602 bytes, ending `pong_wifi=1 k60_wifi_rsc=2` |

This candidate is the mission-poll successor plus the `mhi_create_devices`
call and the 60 s `ready_timeout_ms` wait: stock six WLAN rails, `amss20.bin`, `k60_wifi_rsc=2`, no MHI pre-load,
no IPA rail, no c8 raw-register dump. The earlier queue image
`wifi-20261118sbl-gated` must not be re-flown; its first flight is recorded in
`SBL-QUEUE.md` §6. The direct image `wifi-20261118sbl-direct` was flown once and
its result is in `SBL-DIRECT.md` §6. The pre-device-creation mission image
`wifi-20261118sbl-mission` was built but never flown and is superseded.

Flight result on 2026-11-18 09:17: the watcher's wrapper booted mission4 while
another agent held fastboot (`E:/k60-work/scratch/boot-20261118-091754.log`:
`Sending 'boot.img' (197156 KB) OKAY [4.752s]`, `Booting OKAY [0.174s]`,
`Finished. Total time: 5.100s`). The capture initially lost `COM5`, but the late
console at `E:/k60-work/evidence/usblog-20261118-091754/console.log` (85,874 B,
1,438 lines, SHA256 `59063d2d702e359de9e89b80d24ea09c13dcac7fc436ef573ad5f3bb98cd2bd3`)
is a complete valid log: `Pong MHI: exec_env=2 after AMSS download; cached ee
updated` :683, `Pong MHI powered up: ee=2 state=2 serial=0x22d0a7f3` :687,
`ath11k: chip_id 0x12 ...` :697, `fw_version 0x20070039 ...` :699,
`wifi: hardware registered, 102 channels` :722, `wifi: scan starts on 42
channels` :724, `wifi-net: en0 is up, hardware address 00:03:7f:12:6e:b3` :727,
`wifi: scan 1 finished, 12 networks` :785. The judge passes all 9 checks. This
proves the 60 s ready wait, the 25 s BHI_EXECENV mission cache,
`mhi_create_devices`/IPCR readiness, and the QMI/board/firmware path; it does not
prove association, DHCP or HTTPS.

Offline checks performed:
- `python3 -m py_compile scripts/build-k60-ath11k.py` — pass.
- `python3 scripts/tests/test-wifi-sbl-mission.py` — all 29 source/artifact checks,
  0 failures.
- WSL `python3 scripts/verify-boot-image.py --manifest /mnt/e/...` — OK.
- WSL `python3 scripts/check-image-args.py --image /mnt/e/...` — OK (31
  arguments / 602 bytes).
- `boot.json` was written at build time with `hardware_tested: false`; the valid 2026-11-18 09:17 flight above supersedes that field for this record.
- `python3 /mnt/e/k60-work/scratch/judge-sbl-mission2.py` — positive synthetic mission4 log passes 9/9; negative log with `timeout after 60000 ms` and no cached-ee line fails/stops as designed.

## 4. Prewritten flight criteria

The image is only valid with a serial console captured before `fastboot boot`.

### Success — L1

- The device reaches SpringBoard (`Pong UI: ... entered SpringBoard`).
- The direct push line `Pong MHI: device is in SBL without an EE event, BHI_STATUS=0x...; pushing the AMSS image`
  appears with BHI_STATUS top bits 2.
- `Pong MHI: amss download begin entries=...` and `Pong MHI: amss bhie load ret=0 exec_env=1`
  appear.
- The new line `Pong MHI: exec_env=2 after AMSS download; cached ee updated`
  appears (or `exec_env=4` for WFW), with no matching `Pong MHI: timeout after 60000 ms`.
- No `qrtr: cannot start the IPCR channels`; the two IPCR MHI devices exist after
  `mhi_create_devices`.
- `ath11k: chip_id 0x12 ...` and `fw_version ...` appear, with no
  `ath11k: failed to power up mhi: -110`.

### Failure / stop

- No `cached ee updated` line and a `Pong MHI: timeout after 60000 ms` with
  `ee=1`: the poll did not see AMSS/WFW before the 60 s ready wait expired; stop
  and inspect the `exec_env` samples.
- `amss bhie load ret` non-zero: BHIe failed before the mission poll; stop.
- More than one `amss download begin`: the latch is not effective; stop.
- Any panic, cache-policy failure, duplicate download, or missing console: stop
  and follow the early-boot path. `Pong MHI: irq entered` is shim polling,
  not MSI proof.

## 5. What this candidate does not claim

It does not claim WiFi works end to end: association, DHCP and HTTPS remain
unproven. The flight proves MHI power-up, QMI board/firmware load, 102 channels,
`en0` up and scan (12 networks). It does not replace c8's audit status: c8 is still
HOLD and must not be built, booted or merged.

## 6. Mission5: private WPA2 association fixture

Mission4 proves MHI, QMI, 102 channels, `en0` and scan, but not association. Mission5
reuses the mission4 ath11k archive and rebuilds only the native WiFi archive with an
optional private fixture. `pong_wifi=2` starts the same worker and, when the fixture
is present, also enters the association test; this keeps the payload command line at
602 bytes, so no `pong_wifi_test=1` and no SSID/PSK is placed in boot args.

| field | value |
|---|---|
| tag | `wifi-20261118sbl-mission5` |
| built_at | 2026-11-18T10:09:02+08:00 |
| branch / head | `fix/wifi-mission-timeout` / `ac7d9b2b49567a014a5f14643bf6daa049508d64` (dirty 0) |
| `boot.img` | `E:/k60-work/artifacts/wifi-20261118sbl-mission5/boot.img`, 201,887,744 B, SHA256 `559fb736f996abea8ad80ba61e8c1ab73736d8e38a69c80f30f137fceedc039b` |
| kernel | `adc8180ba144f2e4537ceb6fc152f6e6480a9c928e43e4c03ad4e7bacad8d02a` |
| payload kernel | `69133fb1717d64a6e183d702017ab0c0f289d54aca21cc6bf70c9284eca62173` |
| WiFi archive | `4f345de15ea15ae87da83cae823fae904a98c1a418c46d0ad5aa8f9f2b1374f1` |
| ath11k archive | `a3793b0c3f587b20d148f04938436b96aaa18ccc41f78c087d77cdd487f2b120` |
| manifest | `E:/k60-work/artifacts/wifi-20261118sbl-mission5/build-manifest.json` |
| args | 31 / 602 bytes, ending `pong_wifi=2 k60_wifi_rsc=2` |

The private fixture was generated from a saved WPA2-Personal profile with
`E:/k60-work/scratch/make-wifi-fixture.ps1`: `ssid_bytes=14`, `psk_bytes=13`.
`PongWifiTestInputs.h` is 250 B, SHA256
`5fa9598ebb5a2e7495476fbf2215815ec9191101eb188a79416c53bf73e5912e`; the plaintext
JSON exists only at `E:/k60-work/scratch/wifi-test-private.json`, has a user-only ACL,
and is never logged, committed or placed in boot args. The builder reads it through
`PONG_WIFI_TEST_CONFIG` while compiling the native archive. `PongWifiPlatform.cpp`
`ed38ea74` accepts either the old `pong_wifi_test=1` or the byte-neutral
`pong_wifi=2` mode at `:579`, and its `pong_wifi_start_optional` gate accepts 1/2 at
`:733`.

The 18-check flight judge expects `PongWifi: association test RUNNING: scanned target,
request=0`, `WiFi association test PASS: authenticated link and IPv4 address`,
`wifi-net: en0 address ...`, `wifi-net: dhcp in type ...`, `wifi-net: dhcp out type
...`, and non-zero `wifi-net: in ... dhcp` / `wifi-net: out ... dhcp` traffic counters.
It stops on `WiFi association test SKIP`/`FAIL`, any MHI timeout, BHIe `ret=-`, power-up
`-110`, IPCR failure and duplicate AMSS. Offline checks: `build-strict` eight-step 36
checks passed; `image-arg-audit: OK (31 arguments, 602 bytes)`; `verify-boot-image: OK`;
judge positive/negative controls pass/fail as designed.

The image was flown once on 2026-11-18 10:38:37. The console
`E:/k60-work/evidence/usblog-20261118-103831/console.log` (82,266 B, 1,382 lines,
SHA256 `3b947808aa383cdec5bee903c2be325b4932f44c6e680793d60de451c3666ac2`)
passed MHI/QMI/102 channels/en0/scan, but the association test did not run: there is no
`PongWifi: association test RUNNING`, no `WiFi association test SKIP`/`FAIL`, no
DHCP line and no IPv4 address. `:728` has the station ready, `:817` has scan 1
finished with 12 networks, but `:730/:874/:892/:992` say
`wifi-net: en0 address none, packets in 0 out 0`. The runtime state at
`:873/:891/:991` is 1, which `nw_abi.h:54` defines as `NW_STA_IDLE`, not
`NW_STA_SCANNING`; the earlier "scan state gate" explanation was therefore wrong, and
the gate was satisfied. Mission5 is not a valid association result and must not be
re-flown. A pass would prove association, DHCP/IPv4 and RX/TX only; HTTPS/webpage remains
a separate userland check.

## 7. Mission6: the state gate did not explain the absence

Mission6 changed the gate to
`if(!attempted&&(st.state==NW_STA_IDLE||st.state==NW_STA_SCANNING))` anyway, to rule the
state check out; the enum correction above shows this was not the root cause. The
byte-neutral `pong_wifi=2` trigger and the private fixture were unchanged.

| field | value |
|---|---|
| tag | `wifi-20261118sbl-mission6` |
| built_at | 2026-11-18T10:57:39+08:00 |
| branch / head | `fix/wifi-mission-timeout` / `8bc687f895f12e07cd03ff5231df4b1d9e99ca9c` (dirty 0) |
| `boot.img` | `E:/k60-work/artifacts/wifi-20261118sbl-mission6/boot.img`, 201,887,744 B, SHA256 `78b7ac33069739b208d511040321d6a80db085d63c05b15b94885beb7cd426b2` |
| kernel | `3fe49e5119c17390c013dad20713ac7fcbcbc1101074536a3634b9778ce151c2` |
| payload kernel | `227272abfda42afa705b426df7720c73499d7f2df82b3b09ac34a881176a78e3` |
| ADT | `e17cdc8c0bd4dfdf9b3976f5cd7f426b11000536f78741dbb182d57cd1974737` |
| WiFi archive | `abaed3b7ebb4f6ca9ba34540347bad8f6115b801f4e5a9bf26299d30069071cd` |
| ath11k archive | `a3793b0c3f587b20d148f04938436b96aaa18ccc41f78c087d77cdd487f2b120` |
| manifest | `E:/k60-work/artifacts/wifi-20261118sbl-mission6/build-manifest.json` |
| args | 31 / 602 bytes, ending `pong_wifi=2 k60_wifi_rsc=2` |

Source commit `75e5e842` changed the gate; test commit `8bc687f8` pins the scan-state gate
and the `pong_wifi=2` parse in `scripts/tests/test-wifi-sbl-mission.py` (31 checks pass
against the mission6 build tree). Offline checks: `build-strict` eight-step 36 checks
passed, `image-arg-audit: OK (31 arguments, 602 bytes)`, `verify-boot-image: OK`; the
mission6 judge is the mission5 18-check script with positive/negative controls.

The image was flown once on 2026-11-18 11:01:47. The console
`E:/k60-work/evidence/usblog-20261118-110147/console.log` (88,387 B, 1,466 lines,
SHA256 `CF4DF6ADB2509EB0D5B2DF5BAAA66F05CAE0FB5FF76E40BA731941A90D40A9D5`)
passed MHI/QMI/102 channels/en0/scan: `:666` cached ee=2, `:670` powered up ee=2
state=2, `:680` chip_id 0x12, `:682` fw_version 0x20070039, `:699` 102 channels,
`:703` scan 42 channels, `:707` en0 up `00:03:7f:12:b9:88`, `:773` scan 1 finished
14 networks. It still has no association RUNNING/SKIP/FAIL, no DHCP line and no IPv4
address; `:872/:891/:908` show BSS=20 but state=1. The 18-check judge passes 11 checks
and fails association request/PASS, en0 address, DHCP in/out and RX/TX. A kernel data
abort panic at `:1420` (pc=0xfffffff0084218c4 lr=0xfffffff008425b84 esr=0x96000005
far=0x0) follows SpringBoard and may cut the 60 s deadline; it is not obviously
WiFi-related. Mission6 must not be re-flown; its one-shot marker exists.

## 8. Mission7: probe the association hook

Mission7 removes the remaining ambiguity before another flight. The private fixture,
rather than a particular `pong_wifi` number, enables the test; an unconditional
`PongWifi: association probe: ... pong_wifi_test=<found>/<value> pong_wifi=<found>/<value>
fixture=<ssid bytes>/<key bytes> state=<state>` line records what the kernel actually
parsed. If no scanned BSS matches the fixture, it logs the target length and FNV-1a hash
plus one `bss[i] len=... hash=... freq=...` line per scan result, so the next flight can
distinguish "test disabled" from "target not visible" without printing SSIDs or keys.
It also tolerates a driver-reported trailing NUL in `ssid_len`. Source shape is pinned by
`scripts/tests/test-wifi-sbl-mission.py`; the images are built with the same private
WPA2 fixture and 602-byte args, and no credential ever enters the repository, the console
or the boot arguments.

### Flight result

Mission7 was flown once on 2026-11-18 11:35:48. The console is
`E:/k60-work/evidence/usblog-20261118-113548/console.log` (82,932 B, 1,394 lines,
SHA256 `d4986302bd51548f451817c0b04a01d3880c8c22b9450dea63af73076967b20d`).
MHI, QMI, the 102 channels, `en0` and the scan still pass (`:691` BHIe ret=0,
`:701` cached ee=2, `:705` powered up, `:715` chip_id 0x12, `:717` fw_version
0x20070039, `:723` 102 channels, `:727` en0 up `00:03:7f:12:b6:64`). The probe
proves the test was enabled: `:729 PongWifi: association probe:
pong_wifi_test=0/0 pong_wifi=1/2 fixture=14/13 state=1`. The wildcard scan found
9 networks (`:765`), but none matched the fixture: `:766 PongWifi: association
target absent: target_len=14 target_hash=980ca5d7 bss=9 failed=0 state=1`; the
per-BSS lines list lengths/hashes and frequencies 2412 through 5745. There is no
association RUNNING/PASS/FAIL and no DHCP address; the 18-check judge passes 11.
The 60 s deadline did not elapse before the kernel data abort at `:1367`
(pc=0xfffffff0084218c4 lr=0xfffffff008425b84 esr=0x96000005 far=0x0), so the next
candidate needs repeated or directed scans and an access point that is actually
visible. Mission7 must not be re-flown; its one-shot marker exists.

## 9. Mission8: the first WPA2 association, and the stack-open panic

Mission8 keeps mission7's probe and directed rescan but points the fixture at the
access point that is actually visible: Emilelu_5G (SSID 10 bytes, PSK 11 bytes).
The plaintext exists only in `E:/k60-work/scratch/wifi-test-emilelu5g.json`; the
generated header carries byte counts only and no credential enters the repository,
the console or the boot arguments.

| field | value |
|---|---|
| tag | `wifi-20261118sbl-mission8` |
| built_at | 2026-11-18T12:02:44+08:00 |
| branch / head | `fix/wifi-mission-timeout` / `2cd63b69c26bcae2a3e25e228f22e901a6c9901d` (dirty 0) |
| `boot.img` | `E:/k60-work/artifacts/wifi-20261118sbl-mission8/boot.img`, 201,887,744 B, SHA256 `1414ca38461cc763ba6b05f31bf46ecbb0cc3f296ec0687c7e3630d89bdd1ba5` |
| kernel | `47202ba7ef4d6242cdbd11dd510243b79f8f4e72c2ebc626c6a3889cd6e638fe` |
| payload kernel | `30d27427a1990e5c07c9cb535f69c478e27bc529994e8e3fa8790555fdd986cb` |
| ADT | `3ed7ea4997de1d52ad1ecc8bc2fb66513241d2774d4786c11b8b42331d6df45f` |
| WiFi archive | `0ba97fb0b2f501116ec1d4b819be0e28222ad79d94c17702e807c0beea20788e` |
| manifest | `E:/k60-work/artifacts/wifi-20261118sbl-mission8/build-manifest.json` |
| args | 31 / 602 bytes, ending `pong_wifi=2 k60_wifi_rsc=2` |

The image was flown once on 2026-11-18 12:07:49. The console
`E:/k60-work/evidence/usblog-20261118-120749/console.log` (87,208 B, 1,459 lines,
SHA256 `A98BAE37F9136965255847592B27B4F4E20B46BDD6FC2EFE6A2939BABBF83B8D`)
keeps the proven MHI/QMI/102-channel/en0/scan chain and then completes a WPA2
join: `:728 PongWifi: association test RUNNING: scanned target, request=0`;
`:730 wifi: scan 1 finished (aborted), 4 networks`; `:737 wifi: connecting to
c8:bf:4c:30:03:1c on 5240 MHz, signal -52 dBm`; `:759 wifi: associated, waiting
for the key handshake`; `:761`/`:763` handshake messages 2 and 4;
`:765 wifi: keys installed after message 4 completed`; `:766 wifi: connected`;
`:767 wifi-net: join finished: module result 0`; `:768 wifi-net: association
notifications delivered result 0`. `:890 PongWifi: runtime state=6` is
`NW_STA_UP`, but `:891 wifi-net: en0 address none, packets in 1 out 0`.

The 18-check mission8 judge passes 11 checks: SpringBoard, BHI_STATUS SBL push,
AMSS begin, BHIe ret=0, cached ee, chip_id, fw_version, hardware registered,
scan starts, association request, en0 up. It fails association PASS, en0
address, DHCP in/out and RX/TX because PASS requires a real IPv4 address, and
its scan-finished regex does not accept `(aborted)`. Authentication,
association, the four-way handshake and key installation are device-proven;
address configuration is not.

### The network-stack open panic

At `:1215` configd starts (`KE 38 36 xpcproxy /usr/libexec/configd`). At
`:1416 K60ATTACH filled expansion this=0xfffffff37c070b40
cls=IONetworkStackUserClient`, then `:1424 K60KEXC msg=Kernel data abort.
pc=0xfffffff0084218c4 lr=0xfffffff008425b84 esr=0x96000005 far=0x0` and
`:1451 K60PANIC: ring kept; restart reason -> bootloader`. The saved registers
have `x0=0`, `x19=0xfffffff37c070b40` (the client) and
`x20=0xfffffff37bdf55c0` (the IONetworkStack service). The pc is
`IORegistryEntry::makeLink` +0x34; the lr is
`IORegistryEntry::attachToParent` +0xa8, called from
`IONetworkStack::newUserClient` +0x84.

`makeLink` reads `[this+0x18]` (the registry table) and dereferences it, but
the client never ran `IORegistryEntry::init()`. Mission8's
`IOUserClient::initWithTask(task, security, type)` three-argument overload
begins with `if (getPropertyTable() || super::init()) return reserve();`. On a
fresh object `getPropertyTable()` reports the global fallback table, so the
condition is true and `super::init()` is skipped; `reserve()` allocates only
IOUserClient's expansion record. `attach()` then walks a null registry table and
panics before configd can send a DHCP request. The four-argument overload
`initWithTask(task, security, type, properties)` first calls
`super::init(properties)` and only then the three-argument overload, which is the
sequence `IOService::newUserClient` uses. Mission9 changes
`PongWifiNet.cpp` to pass its `properties` argument and pins that shape in
`scripts/tests/test-wifi-sbl-mission.py`.

Mission8 must not be re-flown; its one-shot marker exists.
## 10. Mission9: the stack opens, and nothing asks for an address

Mission9 carries the four-argument `initWithTask` and changes nothing else.
Tag `wifi-20261118sbl-mission9`, built 2026-11-18T12:37:33+08:00 from
`f64552e7977564b3e48be74014755f522a5a2997` (clean tree), image
`bf2c03488e757e4c6b027ed325d89b3de4d771f62473fa0b4fe9cbb7810d6783`
(201,887,744 bytes), kernel `b66a31f410b1023d053617f18c988cdaebb70104364e18b48937fe16bcf937f0`,
payload kernel `57c2fcd4eba9ce1bf69a45e4c9faad28498223d35fd4060a63760d0958c333fb`,
ADT `206617d9a93f237bba3a34eec7a6e0f505891060246c308ad77e3e3f808f13e2`, WiFi archive
`20bddc0a980a9bb186bd4ad213d7110a6ae2420b732b15d361b79828260c6ba2`, and 602-byte
arguments ending `pong_wifi=2 k60_wifi_rsc=2`.

The flight at 13:02:46 (`E:/k60-work/evidence/usblog-20261118-130246/console.log`,
257,335 bytes, 3,941 lines, SHA256
`5d0d5eec9aad2302d5914823394ba2c3186ce16d0c8616f5c932d0af462cff76`) keeps the whole
association chain: `:790` the directed rescan, `:900` association RUNNING, `:906`
connecting `c8:bf:4c:30:03:1c` at 5240 MHz, `:907` associated, `:911` keys installed,
`:912` connected. At `:1431` the stack user client opens:
`PongWifi[6]: wifi-net: the network stack was opened (type 0)`, with the K60UF
record showing `rsv_before == rsv_after` and no panic. The panic is gone.

What does not happen is transmission. `en0` reports `packets in 1 ... out 0` at
`:922`, and the inbound count climbs to 31 while the outbound stays zero through
every later `log_traffic` line. There is no `wifi-net: dhcp in/out` line, no IPv4
address, no `wifi-net: network stack command` and no `native client type` line, so
the stack user client was opened but never asked to name or configure anything.
configd appears once (`:1244 KE 35 36 xpcproxy /usr/libexec/configd`) with no exit
record and no network activity. At the 60 s deadline `:1855` reports
`PongWifi: association test FAIL: target_found=1 state=6 result=0 IPv4=0`.

The 21-check judge scores 15 PASS and 6 FAIL: association PASS, en0 address, DHCP
in, DHCP out, RX traffic and TX traffic. Mission9 must not be re-flown; its
one-shot marker exists.

## 11. Mission10: the namer opens the stack, and still nothing asks

Mission10 moves the service where the interface namer looks and answers it the way
the reference implementation does: IONetworkStack is published under
`IOService::getResourceService()` (`IOService:/IOResources/IONetworkStack`), the
service advertises `kIOUserClientClassKey`, the user client's `start()` prints who
opened it and the registry's busy state, and the naming request returns
`kIOReturnUnsupported` so the caller cannot believe an interface was named. Tag
`wifi-20261118sbl-mission10`, built 2026-11-18T13:47:42+08:00 from
`37bd434152b90080d05cc0fd66b932655b8f1823` (clean tree), image
`0b2af9b3eea7210b91f1664aa267ff4f05fbb4ba4526ad833a24dce1f717273b`
(201,887,744 bytes), kernel `85740f06e4b18612a74710d47bad8563d0dbacc0686ad41bd07a239068d41e51`,
payload kernel `6b251b9a2b76c818f685149284e68ce4d76501ad73d5eaa2f6db86d8fb3b54f1`,
ADT `ad52bcf976cefc409962a57bbd9e53b0ab0b7f657cb3f3304e34db9254b7e7fb`, WiFi archive
`75d762f3d7ed9842cb43f2a62e2b81abe42da28aae1b56cd13478049a3453e42`, 602-byte arguments.

The flight at 13:48:54 (`E:/k60-work/evidence/usblog-20261118-134854/console.log`,
259,781 bytes, 3,941 lines, SHA256
`c99924c9d289d49ac13339e303ef8e1ff8e2af2a3e8f24046e7441f1a5e31e29`) shows the namer
reaching the service: `:1455 wifi-net: the network stack was opened by configd;
the registry's busy state is 1`, then `:1456` the stack open (type 0) and no panic.
The association chain repeats (`:901` RUNNING, `:907` connecting, `:912` keys,
`:913` connected, `:903` a directed rescan finishing 33 networks). But the client
still never sends a naming or configuration command, no DHCP frame leaves, and the
inbound IPv4 count climbs while `out` stays zero. The 22-check judge scores 16 PASS
and 6 FAIL: association PASS, en0 address, DHCP in, DHCP out, RX traffic and TX
traffic. Mission10 must not be re-flown; its one-shot marker exists.

What this narrows it to: the service is findable, openable and observable, yet the
interface namer inside configd sends nothing. The namer waits for the registry to
go quiet (or times out after five minutes), while `k60_autoreset=300` reset the
board before the five-minute timeout could run. Mission11 tests that hypothesis
directly: the autoreset moves to 900 s, the association test keeps a 10-minute
deadline after the link comes up, and the driver logs the registry busy state,
a volume probe for `wifid`/`configd`/IPConfiguration and the naming-client
commands, so one flight distinguishes "no wifid on the volume" from "namer still
waiting".

## 12. Mission11: the address configuration arrives, and the network works

Mission11 keeps mission10's changes and moves the autoreset out of the way
(`k60_autoreset=900`), extends the association test's post-link deadline to ten
minutes, and logs the registry busy state, a volume probe and the naming-client
commands. Tag `wifi-20261118sbl-mission11`, built 2026-11-18T14:10:37+08:00 from
`ded2c5a4cf2094a57d00c1c88c3890f428051698` (clean tree), image
`56b20bf122d184e201077ad59da751a8d2d97668b7832d44d774a4a0712730e4`
(201,887,744 bytes), kernel `ade1c3cdd294473337c258e9472cffdb452ec491792d8572f53a79d6048751bf`,
payload kernel `76937f89f54a6e306d3fda829e2178f9ea4dc41f7fa669b127022641da86820e`,
ADT `b94d48dcb46394dd51e53d703648a19394d6bff4b6ef5fcb40ad871bf8ecde38`, WiFi archive
`c1edce2e0730e1d1164b9a1bbc5ed2b7cc613cbdac8449d2ca8a0312a267bb67`, and 602-byte
arguments ending `pong_wifi=2 k60_wifi_rsc=2`.

The flight at 14:11:40 (`E:/k60-work/evidence/usblog-20261118-141140/console.log`,
439,287 bytes, 6,836 lines, SHA256
`DE3F5AC656865DEFBD686CD291D2FD436136A1EFFC2B09E63A49EDE299A2844F`) is the first
one where the network carries traffic. After the association the native address
configuration runs: `:4021` `wifi-net: dhcp out type 1`, `:4098`
`wifi-net: dhcp in type 2` with `yiaddr 192.168.31.134`, `:4103` the REQUEST and
`:4112` the ACK. `:4130` reports `WiFi association test PASS: authenticated link
and IPv4 address`, and `:4131` `wifi-net: en0 address 192.168.31.134, packets in
51 out 39`. By the end of the log the interface has 21,752 packets in and 13,983
out, with DHCP 6, ARP 324 and IPv4 13,630 outbound. There is no panic.

The volume probe at `:481` reported `/usr/libexec/wifid` absent, which is correct
for this volume and irrelevant: the offline IPSW audit showed the binary lives at
`/usr/sbin/wifid`, and the DHCP exchange happened without it. configd (through
IPConfiguration) opened the network stack at `:1427` with busy state 1, and the
busy state never reached zero, yet the address configuration proceeded anyway, so
the namer's quiet-wait was not what gated DHCP.

The 26-check judge scores 26 PASS. All six criteria on the official network page
are now device-verified: scan, authentication, association, address
configuration, receive and send. HTTPS and webpage loading are not yet separately
proven; mission12 instruments TCP 443 and DNS traffic to settle that question.
Mission11 must not be re-flown; its one-shot marker exists.

## 13. Mission12: the trace is cut before the address, and mission13 asks from userland

Mission12 (tag `wifi-20261118sbl-mission12`, built 2026-11-18T15:04:57+08:00 from
`4d40456027b0b87e7747825dbf9adc8c9c1e9d8d`, clean tree, image
`5c3799772e8b5fcdc74eb6cfbddfe5d1845f1375619ee757307cd17e10a1a38f`,
201,887,744 bytes, WiFi archive `e2f79a1ba5442f810a93c64239a31293ba72ea013623cbbc3707b5f8cb10c23e`,
602-byte arguments ending `pong_wifi=2 k60_wifi_rsc=2`) added bounded TCP/443 and
outbound DNS counters, a DNS query-name log and the 80211 user-client opener.

Its one flight at 15:08:51 is only partly captured:
`E:/k60-work/evidence/usblog-20261118-150851/console.log` is 53,012 bytes,
918 lines, SHA256 `3fb76775a4384cad815705cf6e705702c3b79b4d1ae611487f3fe334217b1235`,
and stops at `:912 PongWifi: association test waits for the address configuration`
after `:771` scan 1 finished 8 networks, `:896` RUNNING, `:899` the directed
rescan for the pending join, `:903` connecting to c8:bf:4c:30:03:1c on 5240 MHz at
-52 dBm, `:904` associated, `:907` message 4 acknowledged, `:908` keys installed,
`:909` connected and `:916` K60HB t=30; `:918` K60 USBLOG st=4 ev=1320 cfg=1
dtr=1 fl=0. The capture wrote capture.ready but no capture.json or footer, so the
truncation is a capture/host interruption, not a proven driver regression; the
slice contains no DHCP, DNS, TCP/443 or opener line either way. Mission12 must
not be re-flown; its one-shot marker exists. Its observation code stays in
mission13's tree but settles nothing by itself.

Mission13 (`wifi-20261118sbl-mission13`, built 2026-11-18T16:30 from
`a5fa535f9f2bbb28f287e8696ad4c5e4bd4d7aff`, clean tree, image
`6625d4b3fa235a62b25f7ae0745117dd2e4e3379671f3dfa0557704341ff1521`,
201,887,744 bytes, series fingerprint `d27beb4de6da6024` over 227 patches,
602-byte arguments) carries a purpose-built application probe instead of relying
on whatever userland happens to do: patch `0616` now also writes a 34,600-byte
static binary to `/private/var/pong/k60probe`, and patch `0394`'s launchd cache
gains `com.pong.netprobe` (24 jobs) which runs it at boot as root. The probe
polls the gateway 192.168.31.1:80 with raw `connect()`, prints the HTTP status
line and byte count, then requests example.com (93.184.216.34:80) and repeats the
gateway request three times 20 s apart, so one flight answers both "does an
application exchange complete" and "is the transfer sustained". It does not use
the dynamic CFNetwork path: the static binary has no dyld dependency
(`LC_UNIXTHREAD`, no `LC_LOAD_DYLINKER`), so it cannot fail the way libSystem
would.

Prediction: `k60probe: started`, `k60probe: <host> status <code> line <HTTP/1.x ...>`,
`k60probe: <host> tag <n> bytes <n>` and `k60probe: done` appear, while the six
official criteria stay PASS and no panic appears. If the job never runs, the next
step is the launchd cache and job permissions, not another DHCP attempt.

## 14. Mission13: the address configuration, the TLS traffic, and the probe that never ran

Mission13 (`wifi-20261118sbl-mission13`, built 2026-11-18T16:30 from
`a5fa535f9f2bbb28f287e8696ad4c5e4bd4d7aff`, clean tree, image
`6625d4b3fa235a62b25f7ae0745117dd2e4e3379671f3dfa0557704341ff1521`,
201,887,744 bytes, 602-byte arguments, series `d27beb4de6da6024`) was the
first flight to carry the application probe. The kernel wrote it
(`:502 K60PROBE bytes=34600 resid=0 error=0`, `:503 K60PROBE: probe write=0
resid=0 len=34600`) and the curated launchd cache loaded (`:499 K60LC`
`len=10437`), but no `k60probe:` line ever appeared: launchd never
attempted the job and no `execerr` names it. The probe delivery is
therefore unresolved and recorded as a limit, not as a WiFi defect.

The flight settled the network itself. Console
`E:/k60-work/evidence/usblog-20261118-164031/console.log` is 443,391 B,
6,821 newline-terminated lines, SHA256
`EA1EDD5977D07CDBBAD9B29EA19B693127E6933B39B3AD339282F1A7B0A508F0`; the
capture wrote no `capture.json`, only `capture.ready` and the console. The
stack opens at `:1429` by configd with busy state 1 and no panic;
`:1459` configd opens the 80211 user client; `:1468` and `:1594` are two
DHCP DISCOVERs; `:1597` the OFFER for 192.168.31.227 with mask
255.255.255.0, router and DNS 192.168.31.1 and a 43,200 s lease;
`:1845` the REQUEST; `:1864` the ACK; `:1918` `WiFi association test
PASS`; `:1919` `en0 address 192.168.31.227, packets in 20 out 31`.

Traffic then kept rising for the rest of the 900 s window. At `:6741-6746`
(and again `:6793-6795`) the interface reports 23,397 in / 28,455 out: in
arp 422 ip4 22,772 dhcp 2 ip6 203, out arp 433 ip4 27,565 dhcp 5 ip6 457,
and the new counters `tcp443 in 22,315 out 27,138`. The detail lines
`:3075-3122` show SYN (flags 0xc2) from ports 49166-49170 to
17.179.252.2:443, 218.77.196.37:443, 54.65.27.74:443 and
125.89.170.195:443, SYN-ACK 0x52 coming back, a 557-byte ClientHello,
1,480-byte server data and a 977-byte record: bidirectional TLS for
thirteen minutes without a panic. Mission11 carried the same traffic (its
out ip4 reached 13,630) but had no counter for it, so this is the first
flight that can state it.

Judge: 26/26 baseline PASS; the six `k60probe` checks FAIL, so the overall
verdict is FAIL by our own prediction. Against the official page (scan,
authentication, association, address configuration, receive, send)
mission13 is the second full pass and the strongest one: a fresh boot,
a new lease, and large receive and send counters. Reconnect was not
exercised: it needs `pong_wifi_test=1 pong_wifi_cycle=1` and a userland
`PONG_WIFI_TEST_RECONNECT` ioctl, none of which this image carried.
