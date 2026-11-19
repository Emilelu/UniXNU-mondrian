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

## 15. Mission14: the reconnect is proven, the probe never starts

Mission14 carried the bounded probe from `a4b0fa9d` and the fresh-lease
reconnect proof from `8c2b34da`. Image
`E:/k60-work/artifacts/wifi-20261118sbl-mission14/boot.img`, 201,887,744
bytes, SHA256
`48024084de903efef7d85208017a4c6c6de6bd1fa83be2398a84a0b71108e066`,
built `2026-11-18T19:17:25+08:00` at head `8c2b34da`, WiFi archive
`626f852539e023bc27d3dee90dc9022933c92af7ec062343a43aa953ef9ec1e1`,
602-byte arguments ending `pong_wifi=2 k60_wifi_rsc=2` with
`k60_autoreset=900`. It flew once at 19:23:12; console is
`E:/k60-work/evidence/usblog-20261118-192255/console.log`, 436,946 B,
6,834 newline-terminated lines, SHA256
`cb25549c3ed89d58c2530b81e03b6241608dbbb5350622d7b84797bb12768449`.

The network came up the way mission13 did. `:1482` configd opens the
network stack with busy state 1 and no panic; `:1785`, `:1831` and
`:2071` are DISCOVERs; `:2077` the OFFER for 192.168.31.14 with mask
255.255.255.0, router and DNS 192.168.31.1 and a 43,200 s lease;
`:2249` the ACK; `:2289` `WiFi association test PASS`; `:2290`
`en0 address 192.168.31.14, packets in 71 out 120`.

The new part is the link edge. `:2299` arms the lifecycle test
(`automatic disconnect in 120 s`); `:3902` and `:3903` run it and
drop the station; `:3979` reconnects to the scanned network; `:4070`
prints `WiFi lifecycle test PASS: reconnected BSSID
c8:bf:4c:30:03:1c state=6 IPv4=1 lease=3/2`. The PASS line carries the
lease counter because the predicate now requires
`pong_wifi_net_has_lease()` after a reconnect: a stale IPv4 address
alone can no longer pass, and the judge checks that the fresh ACK
precedes the PASS. That check passed.

The probe still did not run, and this time the console says why.
`:529` `K60PROBE bytes=34728 resid=0 error=0` and `:531` `K60PROBE:
probe write=0 resid=0 len=34728` show the binary written, but `:530`
`K60PROBE plist vnode_open error=30` is EROFS: the job plist cannot be
created on the sealed root. The job itself does ride the curated cache
(`:526` `K60LC: curated launchd cache write=0 resid=0 len=10437`, 24
jobs including `com.pong.netprobe`), but launchd reads that cache at
`/System/Library/xpc/launchd.plist`, and the only code that can put it
there is the bindfs view at `userland/init.c:475`. This image runs the
34,904-byte helper (`:527`-`:528`), whose view table predates that entry,
and every bindfs view it did attempt failed with EPERM (`:554`, `:556`,
`:558`, `:560`, `result=-1 errno=1`), so the cache never becomes
launchd's input. Writing the job into the cache again therefore cannot fix
delivery; the next image must take launchd out of the path and fork the
probe from the init helper before `execve("/sbin/launchd")`, letting it
wait for the address.

Judge: 31 PASS, 7 FAIL, all seven the `k60probe` checks, so the overall
verdict is FAIL by our own prediction. Against the official page mission14
is the third full pass on the six items and the first with a measured
disconnect and reconnect.

## 16. Mission15: the Settings pane starts the wireless daemon

Mission15 carried `6253eafc` — the packet-filter tap, the 383 property lists,
the 470/471 flags, the current-network fallback and a reg-less `wlan` node in
`dts/mondrian.dts`. Image
`E:/k60-work/artifacts/wifi-20261118sbl-mission15/boot.img`, 201,887,744
bytes, SHA256
`8fedce4983f7e7e5f489e8da0dbeba47ee5d86642e7e81e9bf465a638819d2ca`,
built `2026-11-18T22:25:35+08:00` at head
`6253eafca83ff421b2ccf66e5ef1ac199950c562`, WiFi archive
`e2f6d7259c71dc33e8f2c25b254183566c3e80b6172a1687d7084a6e6285a4fe`,
602-byte arguments and `k60_autoreset=900`. It flew once at 22:32:23;
console is `E:/k60-work/evidence/usblog-20261118-223223/console.log`,
997,880 B, 12,500 newline-terminated lines, SHA256
`12a96da390ef1a4beba3c3d842cdc9e3ed879e4cff4e6d6398a1b5c8e0928609`.
The capture wrote `capture.ready` and the console but no `capture.json`,
as in mission13 and mission14; the flight ended on the automatic reset
(`K60AUTORESET: 900 s since boot; resetting to fastboot`), and the board was
returned to Android with `scripts/k60-device.sh android`.

The device tree is the gate. The ADT now publishes the `wlan` nub
(`:91-94` intc, pong-audio, **wlan**, ufshc, pong-touch, pong-buttons;
`:148` `registered platform cpus=8 arm-io=1 devices=6`, against 5 in
mission14), so launchd's `_LimitLoadToDeviceTree` condition for
`com.apple.wifid` is satisfied and the daemon finally runs:
`:1223` `KE 27 43 xpcproxy /usr/sbin/wifid`, `:1504`
`wifid[43:587] ----- WiFiManager starting, version: WiFiManager-1635.6 -----`,
and `:1863`, `:1967`, `:3919` `wifi-net: 80211 user client opened by wifid
type 0`. configd keeps opening its own client (`:1454`, `:1943`, `:3954`,
`:4001`, `:4013`, `:4017`) and wifivelocityd adds one (`:3925`), so three
userland daemons now speak the Apple80211 ABI to the driver.

The pane's own protocol works end to end. The tap is armed twice
(`:1463`/`:1465` and `:1538`/`:1540`, `packet filter tap mode 3` then
`0`), the daemon writes property lists from `:3913` on and the driver logs
them, and `IO80211InterfaceIPConfigurationBusy` moves `false` at `:3936`,
`true` at `:4008`, `false` at `:4363`, `true` at `:4708` and `false`
at `:4709`. The current-network query (type 103) is answered from the link
state at `:3995-:3997`, and the hardware channel list (type 254, 4824 bytes)
at `:3975-:3991`.

The join from the pane is proven, and it is the first person-driven join on
this port: `:8578` logs `wifi-net: join: ssid length 7, bssid given 0, key
length 32 cipher 6` — the 32-byte key wifid derived from the typed
passphrase — then `:8583` `connecting to c8:bf:4c:30:03:1d on 2412 MHz`,
`:8585` `associated`, `:8587-:8589` handshake, keys installed and
`connected`, and `:8590` `join finished: module result 0`. The judge check
`join from the pane` passes on that sequence; no credential is printed.

The network stayed up across the whole window. `:2013` OFFER
192.168.31.71, `:2037` REQUEST, `:2038` ACK; after the lifecycle
disconnect `:4005` REQUEST and `:4028` ACK; `:4030` `WiFi association test
PASS` and `:4031` `WiFi lifecycle test PASS: reconnected BSSID
c8:bf:4c:30:03:1c state=6 IPv4=1 lease=3/2`; `:9500` `en0 address
192.168.31.71, packets in 687 out 844`; `tcp443 in 302 out 368` by
`:12201`; the router ARPs the station in both directions.

Two limits are recorded rather than claimed.

1. The page still cannot be loaded, and the reason is the browser, not the
   link: `:9046-:9054` `Process[602…609] crashed: com.apple.WebKit. Too
   many corpses being created.` and `:9200` `KX! 154 596 MobileSafari
   exit=0 sig=9 ns=15 code=0xdead10cc`. The application-layer HTTP result
   therefore remains unproven, and its blocker belongs to the WebKit/GPU
   line, not to WiFi.
2. The pane's list does not show `Emilelu_5G`. The whole flight carries one
   scan request (type 10, `:4846`) and one result read (type 11,
   `:4852`), which the cursor protocol answers with a single BSS; the
   refresh types the pane uses are refused with `EOPNOTSUPP` (`:3998` type
   25, `:3999` 365, `:4000` 423, `:4102` 419, `:4104` 115, `:7216`
   422) and so is channels-info 207 (`:1982`), so wifid falls back to its
   boot-time cache. The driver's own BSS table held 17 entries after the
   first scan and 21 later (`PongWifi: runtime … BSS=17` / `BSS=21`), and
   the boot join associated at 5240 MHz (`:3431`), so the radio does see
   5 GHz; the gap is feeding the daemon's list. The next image must log every
   unhandled type with `req_val` and the first bytes, print the BSS table by
   band, answer 207, and give the pane a scan path.

Open question for that image: `dns in 0 out 0` for the entire flight, so no
plaintext UDP 53 was observed even though TLS flowed. It is recorded as a
tracing gap, not as a DNS defect, because no HTTP client survived to ask.

Judge: 22 PASS, 0 FAIL, 1 PENDING (the host-side application receipt), so the
verdict is PANE-ONLY. Against the official page the six items pass for the
fourth time and the Settings pane — the user's new acceptance item — is now
proven at the protocol level, with the person-visible list limited by the
scan gap above.

## 17. Mission16: every refused request is named, and the daemon's list is the one that drops 5 GHz

Mission16 (image 95e16e01def0a0efe782aa7a9c5de19e5f1225696b072f8f277a1d6384c786e9,
head d964770e, built 2026-11-18T23:31:57+08:00) was flown once at 00:23. Console
E:/k60-work/evidence/usblog-20261119-002257/console.log is 639,221 B, 8,729
lines, SHA256 565cf7890195720f2534a8f1c6a52b79899cea6a2fb05f7f83236135755534ce.

The diagnostics answered the first half of the question. The radio hears 5 GHz:
scan tables of 6 BSS (2.4 GHz 3, 5 GHz 1) at :790, 31 BSS (20/1) at :4376 and
eight tables of 33 BSS (2.4 GHz 20, 5 GHz 2, 6 GHz 0, hidden 11) from :4404,
with Emilelu_5G at 5240 MHz -50 dBm (:4380, :4408) and a neighbour at 5805 MHz
-86 dBm (:4409). The pane's scan request is type 10 length 5456 (:4389), the
driver serves the list one record at a time and logs "scan result served 32 of
33" at :4416 (the 32nd record is 2412 MHz, -81 dBm, empty SSID), and the
supported-channel query reports 102 channels: 2.4 GHz 14, 5/6 GHz 88 (:1816).

Every refused request is now named with its value, length and first bytes:
types [6, 18, 25, 57, 115, 207, 346, 353, 365, 386, 387, 419, 422, 423], among
them 419 set 136 bytes starting `01000000d0af…`, 115 get 1288, 207 get 10016
and 387 get 37. Those payloads are the next contract to read, not a guess to
encode.

The second half is the daemon. wifid's own log
`-[WiFiSettlementObserver _handleScanResults:...] scanType=2 client='Preferences'`
prints 27-entry lists (:5608, :6453 and later). They contain Emilelu at
c8:bf:4c:30:03:1d -50, the 5805 MHz neighbour as `d8f;-5G`
74:86:6f:79:28:1c -86 (the garbled text is how the daemon renders that SSID),
and an empty-SSID ce:bf:4c:30:03:1d -52, but never Emilelu_5G. The radio, the
driver table and the driver's own logs all carry 5240; the daemon's parsed list
does not. So the gap is in the record stream or in the daemon's handling of it,
not in the band.

Two explanations are recorded and neither is claimed yet. First, the table is
33 records deep and is served in table order; the daemon read 32 of them, and
whether the 5240 record is the one unread record is exactly what mission18's
per-record dump prints (index, age, BSSID, element length, capability, SSID).
Second, the daemon may drop that record over a field it cannot use even after
reading it. No code was changed on the strength of either.

Judge: 22 PASS, 0 FAIL, 1 PENDING (host HTTP receipt) = DIAG-ONLY. The pane
join still came from a person (:4425 connecting to c8:bf:4c:30:03:1d at
2412 MHz). mission16 must not be re-flown.

## 18. Mission17: the station associates with an 11ax access point

Mission17 (image 738c9125fcd2714d6a7ed0b197243f9a5d78bc5ace3ebc6b1a98f377267dcd37,
head 497e512c, built 2026-11-19T00:18:00+08:00) merged the Settings-pane line
with the HE codec and was flown once at 00:40:32. Console
E:/k60-work/evidence/usblog-20261119-004032/console.log is 467,035 B, 6,982
lines, SHA256 ba3b58c2e403291cbda83ef9b36bcd5bdaacfcdab460ed42f14c9a3f6292c3c6.

The station announces HE and the peer entry keeps it. At :799 the association
request states `HT 28 VHT 14 HE 31 bytes`; before it, :794 logs
`peer HE yes, MCS 80 rx fffa tx fffa, params 0x25003ff4 nss 0xfffc` for
c8:bf:4c:30:03:1c at 5240 MHz, width 80. The association completes and the key
handshake follows (:3311 onwards), so the access point accepted the request
that carries the HE element. The lifecycle test then reconnects at :3309 and a
daemon-initiated join at :4341 (ssid length 7, key length 32, cipher 6) moves
the link to 2412 MHz, where the request is `HT 28 VHT 0 HE 28 bytes` (:4347)
and the peer HE operation carries params 0x2b003ff4; :4420 reports
`WiFi lifecycle test PASS: reconnected BSSID c8:bf:4c:30:03:1d state=6 IPv4=1
lease=5/3`. The initial association PASS is :1676.

What this proves: the HE capability is encoded, sent, accepted, and the peer's
HE capability is parsed and narrowed into the station's own state on both
bands. What it does not prove: HE rate selection or throughput — no traffic
measurement was made, and the peer MCS map 0xfffa is recorded as the access
point's answer rather than interpreted.

The pane line stayed intact: the scan tables are 8 BSS (2.4 GHz 4, 5 GHz 1),
24 (14/1) and 29 (17/1), and the refused-type list now also includes 29.

Judge: 24 PASS, 0 FAIL, 1 PENDING (the host-side application receipt) = base
PASS, HE PASS. The page still cannot be loaded because WebKit is killed; that
remains the application-layer blocker and it belongs to the WebKit/GPU line.
mission17 must not be re-flown.

## 19. Mission18: the record is delivered; the country element is the next lead

Mission18 (image c094e5bf5b36fcf658058cb6aa1f38c29f3afa67ce0029431be700a434047e76,
head 7663471a, built 2026-11-19T00:55:25+08:00) prints every scan record for the
first three scans and was flown once at 01:00:09. Console
E:/k60-work/evidence/usblog-20261119-010007/console.log is 479,040 B, 7,115
lines, SHA256 3ca108dc887cc2598344360d0ef6a4f76bc580a8816bcc30abdd29513723f14b.

The 5240 record is delivered. The tables are 6 BSS (2.4 GHz 4, 5 GHz 1, hidden 1)
at :771, 27 (17/1, hidden 9) at :4402, and 29 (18/1, hidden 10) at :4443, :4697
and :5675. Emilelu_5G c8:bf:4c:30:03:1c, 5240 MHz, -51/-50 dBm, element length
384, capability 0x0511, sits at index 5 of every table, and the daemon read the
whole table: scan request type 10 len 5456 at :4116, records served 1/2/3/8/16/24,
and "scan result end after serving 27 of 27 records" at :4437. Mission16's
"served 32 of 33" had the same property. The record the pane loses therefore
reached wifid; the loss is on content, not on position.

The ages say what the module does: the 5240 entry ages 6 -> 1285 -> 2812 ms
between sweeps while 2.4 GHz entries reach 303,825 ms, so the module keeps the
last observation per BSSID instead of re-hearing every network on every sweep.

The flight could not observe the daemon's own list. No person opened Settings, so
wifid wrote no Preferences scan list this time (mission16 had two 27-entry lists
at :5608 and :6453). That comparison needs a flight with a person at the screen.

Country element. wifid logged "2 country code(s) currently advertised by 16
networks", "Country <BR> IE count 1", "Country <CN> IE count 15" and "Currently
highest country <CN>" at :5231-:5234. One network advertises a non-local country,
and CoreWiFi can drop a BSS whose advertised country conflicts with the local
one; that is the leading candidate for a record that is delivered and then
discarded.

Judge: the first run printed base=FAIL only because judge-wifi-mission16.py's
table regexes expected "scan table N BSS" without the ordinal mission18 added.
Accepting an optional ordinal makes the same console judge base=PASS dump=PASS;
the user group stays PENDING because no host receipt exists. No code was flown
twice, and mission18 must not be re-flown.

Two changes follow, neither yet on device. 1cb402db freezes the list when a
sweep completes, serves it strongest first, and prints the first twelve 32-bit
words of each served 5 GHz record. 49ee1b8a adds the record's Country element to
the per-record dump, so mission19 can show whether the dropped record is the
<BR> one.

## 20. Mission19: the 5 GHz record is well formed, served first, and says CN

Image `c1429161f1d02aa5fa7e875c911f2af0e013a6f8fd26b2f6d107458e41481320`
(201,887,744 B, built 2026-11-19T01:50:48+08:00, head `20e5a2b1`, wifi archive
`4afa1ef9`, 602-byte args, `k60_autoreset=900`), flown once at 01:53:37 into
`E:/k60-work/evidence/usblog-20261119-015237/console.log` (482,395 B, 7,147
lines, SHA256 `e83371ee852df28094a28c09be16bab09af43ec0887ddf934665c6a4e4dd70a9`).

The sorted frozen list works: the first sweep's table of 9 BSS (2.4 GHz 6, 5 GHz
1, hidden 2) at :781 was served with the 5 GHz record first —
"scan result served 1 of 32: 5240 MHz, -51 dBm, Emilelu_5G" at :4386 and
"served 2 of 34" at :4470. The record's own words, identical in both sweeps
(:4385, :4469), decode cleanly: version 1, channel 48 with flags 0x12, noise
-95 dBm, SNR 44, RSSI -51 dBm, beacon interval 100, capability 0x0511, BSSID
c8:bf:4c:30:03:1c, rate count 0.

The Country element column (:4385 onward) does not single the record out:
Emilelu_5G advertises CN, Emilelu itself advertises no country element (--), and
the only BR networks are two unrelated 2.4 GHz observations (70:85:6c:da:71:2d
and CMCC-666 at 70:85:6c:d4:71:2e). The country lead from mission18 is
therefore not the explanation for the missing row.

Supported channels again answer 102 (2.4 GHz 14, 5/6 GHz 88) at :2040, with
2412/2417/2422/2427 numbered 1/2/3/4 and flags 0xa. The daemon's settlement
observer is created at :2031 with maxNetworks 10, maxScans 3, low 30, high 120.

No Preferences scan list exists in this console (the only
`WiFiSettlementObserver` line is the init at :2031): nobody opened Settings, so
the daemon's own list is still unobserved. The daemon did join on its own at
:4479 (ssid length 7, key length 32, cipher 6) and the baseline reconnected
(:4546, "lifecycle test PASS ... lease=5/3"). Judge: base=PASS dump=PASS
user=PENDING -> DIAG-ONLY.

Mission20 (f0c959f0) therefore only adds observation: the scan request's first
four words (the channel filter the daemon sends), every record it reads rather
than one in eight, and the first sixteen bytes of each served 5 GHz record's
element blob. It must be flown with a person at the screen who opens
Settings -> Wi-Fi and pulls to refresh; that console will carry both the
Preferences list and the records behind it.

## 21. What the reference trees actually contain (and do not)

The maintainer's directive for this span was "copy pong and zizhan". The two
trees were fetched again and compared line by line with our driver, so the
answer is a list of concrete deltas rather than an impression.

- **pong's wifi driver is a separate repository and it is alive:**
  `https://github.com/Chengdong-Yu/pong-wifi.git` at `d2e33ca` ("Import
  PongWifi from UniXNU-pong"), 1,803 lines total. The `UniXNU-pong` superproject
  itself 404s on GitHub, which is why `drivers/PongWifi` is an empty submodule
  directory locally. The clone now sits at `E:/k60-work/scratch/pong-wifi`.
- **zizhan** is unchanged at `034a0b0`; its `drivers/PongWifi` is the tree ours
  was derived from, down to the enum values and `fill_channel`.
- **Our driver is already a superset.** pong-wifi has no freezed scan list, no
  24-style record (timestamp at +0x8d0), no property-list handling, no tap, and
  it answers `kScanResult` from the live table exactly as we did before
  mission19. zizhan has the 22H374 record and the user-client tunnel; we have
  both plus the mission19 freeze/sort and the mission20 request and element
  dumps. Nothing in either tree handles types 25, 207, 419, 422, 423 or 115 —
  they are 20G81/22H374 daemon requests that both reference drivers refuse.
- **Three real deltas exist, and none is a drop-in fix for the missing row.**
  1. pong sets `flags |= 0x80` on every supported channel
     (`pong-wifi/PongWifiNet.cpp:427`), and evb10 does the same with a static
     table. zizhan deliberately does not, with the comment "CWFChannel compares
     the complete flag word for supported membership. Keep the band/width
     representation consistent with scan/current/history channels rather than
     adding ACTIVE only to this answer." Our tree follows zizhan, because a
     supported-channels entry whose flag word differs from the scan record's
     cannot match by that rule.
  2. pong skips `NL80211_BAND_6GHZ` when it enumerates channels
     (`pong-wifi/ath11k/PongAth11k.c:154`), because "the shared station scan
     policy and the Apple80211 channel codec currently publish only 2.4/5 GHz
     channels on this board". Our `nw_wifi_channel_list` does not skip it, which
     is why the type-254 answer has 102 entries (2.4 GHz 14, "5/6 GHz" 88) while
     the station sweeps 42 channels. The count is the clue, not the proof: this
     is a candidate for the next image, not a change to make under a running
     diagnosis.
  3. pong answers a scan while joined from the cached table
     (`pong-wifi/PongWifiNet.cpp:342-345`); that behaviour has been in our
     driver since mission15 and is unrelated to the row.

One new fact from the mission16 console (checked with
`scripts/diff-scan-list.py` and by direct search): the 5240 MHz BSSID
`c8:bf:4c:30:03:1c` appears in **no** daemon list at all — eight
`client='Preferences'` lists and seven `client='configd'` lists were logged in
that flight, and the neighbour at 5805 MHz (`74:86:6f:79:28:1c`, shown as
`d8f;-5G`) appears in both. So the drop happens inside wifid before any
client-specific filtering, and the pane is not the stage that loses it. That
makes mission20's pairing (full record dump + a list produced while Settings is
open) the right instrument, and it makes "copy more reference code" an empty
lever: neither reference project has a 20G81 daemon to copy from.

## 22. The one-field experiment mission20 should carry

The mission16 record dump leaves exactly one 5 GHz record per table (the
5240 MHz AP, `ie 384 cap 0x0511 cc CN`), while mission16's pane list shows a
*different* 5 GHz neighbour (`74:86:6f:79:28:1c`, shown as `d8f;-5G`, -86 dBm).
So wifid accepts 5 GHz records in general and rejects this one on a property of
the record, not of the band. The properties that differ are the SSID, the
capability word (0x0511 vs the neighbours' 0x1c31/0x0431), the element blob
and channel 48.

wifid carries band-steering strings (`known5ghzSsid`, `invalid 5ghzSsid`,
"companion network %@ is not a 5ghz network"), so one live hypothesis is that a
2.4 GHz SSID `X` plus a 5 GHz SSID `X_5G` is treated as one companion pair and
only the 2.4 GHz row is shown. That is testable in a single flight without new
code: open Settings -> Wi-Fi, record the list, rename the router's 5 GHz SSID
from `Emilelu_5G` to a name without the `_5G` suffix, pull to refresh, and see
whether the row appears. The same console then carries the mission20 dumps for
both states.

If the rename does not change anything, the remaining suspects are the
capability word and the element blob, and the next image should serve synthetic
clones of the one record to bisect them (same BSSID neighbourhood, one field
changed per clone). Both experiments are cheaper than further static analysis:
wifid is arm64e with chained fixups, `llvm-objdump --macho --objc-meta-data`
returns nothing for it, and the 20G81 iPhone 13 runtime has no iPadOS 18
counterpart in either reference tree, so there is no second binary to diff
against.


## 23. Mission21: the element inventory of the two bands

Mission21 (image 766606e0, 201,887,744 B, head 7e8b3310, built
2026-11-19T03:38:21+08:00, archive f6d168c7, 602 B args, k60_autoreset=900)
flew once at 03:39:24 into
E:/k60-work/evidence/usblog-20261119-033924/console.log (542,538 B / 7,854
lines / SHA256 10d9351965bd76ce67ffc0224cb5dfeb22b7f0c2ea89f159a68584bfeaa3e3e1).
The judge printed base=PASS dump=PASS list=UNOBSERVED, verdict DIAG-ONLY.

HE survived the merge into the pane branch: :822 association request HT 28
VHT 14 HE 31 bytes, :817 peer HE yes, MCS 80 rx fffa tx fffa, params
0x25003ff4 at 5240 MHz; after the daemon moved to 2412 MHz, :5112 requests
HT 28 VHT 0 HE 28 bytes with params 0x2b003ff4 (:5110). Association PASS at
:1821 and :5180, lifecycle PASS at :5181 (lease=5/3).

Scan tables: 11 BSS (2.4 GHz 8, 5 GHz 1, hidden 2) at :788, 28 (19/1,
hidden 8) at :4893, 35 (26/1, hidden 8) at :4994. The 5805 MHz neighbour
was not heard in this flight, so the only 5 GHz record is this access point
at 5240 MHz.

The element inventory is the new fact, and it shrinks the difference to one
group of fields. The same access point on 2.4 GHz (c8:bf:4c:30:03:1d)
carries ie 347, RSN 24 bytes at offset 37 and capability 0x0431; on 5 GHz
(c8:bf:4c:30:03:1c) it carries ie 384, RSN 24 bytes at offset 76 and
capability 0x0511. The RSN length is identical, three of the extra 37 bytes
are the longer SSID, and the remaining 34 bytes are other elements.
Mission22 prints the element-id list and the RSN bytes of both records and
serves a copy of the 5 GHz record under the unrelated name K60SYNTH, which
separates a name-based filter from a field-based one in a single screen.

No pane list was produced: the only WiFiSettlementObserver line is its init,
so nobody opened Settings and the daemon-side drop is still unobserved after
six flights. wifid's band strings (guess1..guess4, "2Ghz scanned network[%@]
has a matching known 5Ghz network") make the name hypothesis the first one
to test.

mission20 (b0ae4826, head fc8f5432, built 2026-11-19T02:25:38+08:00) was
superseded by mission21 before it flew and is recorded as
built-but-never-flown; its 193 MB artifact was deleted on 2026-11-19 05:07 so
the P-218 gate stops reporting an image nobody will fly (the hash and head above
are the whole record); mission22 (0d6a2f16, head d250f2c3, built
2026-11-19T03:57:47+08:00) is built, verified and unflown. K60EXC appears 64
times in every flight since mission17, so it is not a mission21 anomaly.

## 24. The pane list on mission22: the name is not the filter

mission22 (0d6a2f16, head d250f2c3, built 2026-11-19T03:57:47+08:00) flew at
05:14:20 with a person at the screen and was the first flight that held a
Preferences list and the per-record dumper at the same time:

| field | value |
|---|---|
| console | E:/k60-work/evidence/usblog-20261119-051413/console.log, 889,855 B, 11,636 lines, sha256 37e0079f09c8381492b543630e74400eda5a17badac7060d75e11bdb692bf87e |
| boot record | boot.json bootAccepted true, returnedToFastboot true, finished 05:29:47; the one-shot marker was written |
| pane lists | 24 lists for client=Preferences (37 observer lists in all); the last holds 40 entries |
| records | 55 distinct dumped records, 45 KEPT, 10 DROPPED |
| join timeline | ...1c on 5240 MHz at :856 and :3545, ...1d on 2412 MHz at :4938; the lists start at :5464, after the move to 2.4 GHz |

The pane does list 5 GHz: CMCC8888 at 5240 MHz -79 dBm (ie 332, cap 0x1531) and a
hidden 5240 MHz -82 dBm are both KEPT. Emilelu_5G (c8:bf:4c:30:03:1c, 5240 MHz,
-51 dBm, ie 384, cap 0x0511) is DROPPED. Its 2.4 GHz sibling (...:1d, cap 0x0431)
is KEPT and carries the same 24-byte RSN (0100000f ac040100 000fac04, WPA2-PSK
only, no SAE AKM), so the security type is not the difference either.

The renamed copy settled the name hypothesis: mission22 served K60SYNTH 24 times
and the daemon read every record of every sweep ("scan result end after serving
46 of 46" and "49 of 49"), yet no list holds its BSSID (c8:bf:4c:30:03:5c). A
name the daemon cannot band-steer is dropped exactly like the real one, so the
filter is a property of the record, not of the SSID.

What remains is the BSSID. ...:1c differs from the joined ...:1d in one bit, and
the copy shared those five leading bytes. mission24 therefore serves two copies
from the FRONT of the frozen list - K60SYNTH with the same first five bytes and
K60SYNTH2 with the OUI's first byte flipped (ca:bf:4c:30:03:1c) - because the
word dump only covers the first six 5 GHz records and a copy at the tail was
unobservable in mission22. A pane that lists only K60SYNTH2 hides 5 GHz siblings
by prefix; a pane that lists neither hides them by a record field; a pane that
lists both means the earlier copy was simply never read.

Two build facts from the same day: the kext's sae probe reference has to be a
weak_import, otherwise a pane image linked against the HE archive fails with
"_nw_wifi_sae_probe undefined" (the mission24 link caught it), and mission24
builds against the ath11k-sae1 archive so the symbol resolves; its boot line
carries no sae argument, so the probe stays off.

## 25. Mission24: the daemon drops the record itself, not its name and not its BSSID prefix

Image wifi-20261118sbl-mission24 (6ba9a0537326ddadded57a0ccaf7658d1fdcde2529f45f9f1fd39ca5938952bd, 201,887,744 bytes,
built 2026-11-19T05:55:25+08:00, 31 arguments / 602 bytes) was flown once at 06:06:12 with the supervisor
boot-and-capture.ps1; the capture is usblog-20261119-060604, console 1,180,114 bytes / 14,506 lines / SHA256
4201f716a09a1387. A person opened Settings -> Wi-Fi and pulled to refresh, so for the first time one flight carries
both the driver's record dump and the daemon's own Preferences list.

The image serves two copies of the 5240 MHz record from the front of the frozen list: K60SYNTH
(c8:bf:4c:30:03:5c, the last BSSID byte flipped) and K60SYNTH2 (ca:bf:4c:30:03:1c, the OUI first byte flipped).
The console shows both at served positions 2 and 3 of 33 and again of 40, and the daemon read whole sweeps
("scan result end after serving 33 of 33 records"). Its Preferences list, 41 entries over 44 records (30 kept,
14 dropped), holds Emilelu_5G zero times and neither copy's BSSID in any observer line either.

Conclusion: the filter is not the SSID (a renamed copy is dropped too), not band steering by name, and not a
BSSID-prefix merge with the joined 2.4 GHz sibling (a copy with a different OUI is dropped as well). The record
content is the filter. The router screenshot supplied by the user adds the missing context: this access point is
5 GHz on automatic channel 48 with 160/80/40/20 MHz and WPA3/WPA2 mixed security, while the 2.4 GHz radio is
40/20 MHz; the only 5 GHz records the pane lists in this flight are neighbours at ordinary widths.

The mission24 judge needed two fixes: judge21's element-inventory regex still expected the mission21 column set
(no ht40/vw), which turned a healthy flight into base=FAIL; it now accepts both formats and the same console
judges base=PASS inventory=SEEN. The full RSN is 24 bytes at element offset 82 (offset 76 in one sweep), and the
mission24 image still printed only the first 16 of them, which mission25 extends to all 24.

## 26. mission25（2026-11-19 06:46）：探针被 daemon 看见，过滤在元素区

镜像 wifi-20261118sbl-mission25/boot.img，SHA256 95629508…，head ec51f578，201,887,744 B，31 参数 / 602 B；飞于 06:46:57，07:02:24 回到 fastboot（boot.json accepted=true、returnedToFastboot=true），随后脚本恢复 Android。console E:/k60-work/evidence/usblog-20261119-064651/console.log 887,140 B / 11,567 lines / SHA256 fb5cfee0de94a37aabdedc8f4431e3bd87b4c7d59af527d4c39471f868694eed，含 100 行 wifi-net: probe、100 行 synthetic copy、26 条 Preferences 列表。本次多数扫描里 5 GHz 只有 1 条记录（2.4 GHz 25-28 条），探针直到后段出现第二条 5 GHz 记录（5180 MHz，88:c3:97:c6:0a:73，ie 382，cap 0x0511）才配对成功。

判据是人的观察：先看到 K60A、K60C、K60D，K60B 与 K60E 从未出现，且五条探针随刷新闪烁（m33078/m33082/m33085/m33105/m33110）。K60A 是被保留记录的原样改名（基线），K60B 是它加我们的元素区，K60C 是它加我们的 capability，K60D 是我们那条 5240 记录换成载体的元素区，K60E 是我们那条记录换成载体的 capability。A/C/D 出现、B/E 不出现，说明 capability 无辜，元素区就是把 daemon 推开的东西；把我们 5240 记录的元素区换成载体的，daemon 就收下（D）。

两条频段的元素清单（本次 console）：

- 5 GHz c8:bf:4c:30:03:1c：0/10 1/8 3/1 7/42 32/1 35/2 48/24 45/26 61/22 127/10 191/12 192/5 195/5 255/33 255/7 255/2 255/14 244/1 221/23 221/24 221/2
- 2.4 GHz c8:bf:4c:30:03:1d：0/7 1/8 3/1 5/4 42/1 50/4 48/24 45/26 61/22 74/14 127/10 191/12 192/5 255/26 255/7 255/2 255/14 244/1 221/23 221/24 221/22

5 GHz 独有：国家 IE 7（42 B）、功率约束 32/1、TPC 报告 35/2、VHT 发射功率包络 195/5、HE capability 33 B（2.4 GHz 为 26 B）、厂商 221/2。mission27 把这几项逐个加回载体，一次一个，用「哪一条让载体行消失」定位真正的字段，再从真实记录里删掉或收窄。

mission26（a978c829，只有一条 5 GHz 记录时回退到 2.4 GHz 载体）构建中途取消、未飞，镜像 wifi-20261118sbl-mission26 记为 built-not-flown。

## §27 mission30/31：先看被保留的 5 GHz 记录带了什么

2026-11-19 08:00–08:10。mission25 的口头判定（A/C/D 在、B/E 不在）只说明元素区是过滤器；mission27 的加法探针按「5 GHz 独有六项」设计，但缺一项离线证据：wifid 保留的其他 5 GHz 记录到底带不带这些元素。mission24 的 console（44 条 Preferences 列表、104 个 BSSID、57 个名字）把这一点补齐了。

- 被保留的 5 GHz 记录是 5200 MHz -78 Rh1 与 5200 MHz -77（空 SSID），元素清单分别为 `0 1 3 5 7 32 195 70 51 48 221 11 45 61 191 192 127 221 255 255 255 255` 和 `0 1 3 5 7 32 195 70 51 48 11 45 61 191 192 127 221 255 255 255 255 221`。
- 也就是说国家 IE 7、功率约束 32、VHT 发射功率 195、厂商 221、HE 255 都出现在被保留的 5 GHz 记录里，单独任何一条都不可能是过滤器。
- 目标记录 `0 1 3 5 7 32 35 48 45 61 127 191 192 195 255 255 255 255 244 221 221 2` 比它们多出 TPC 报告 35 与 IE 244，另外多一条 255，以及长度为 2 的厂商 IE（221/2，没有 OUI）。

方法上也有一条教训：只取最后一条 Preferences 列表比对时，大量记录显示 DROPPED，看起来像随机丢包；把 44 条列表取并集后，38 条有元素清单的记录里 33 条 KEPT，唯一被丢的 5 GHz 记录就是目标本身。逐条比对的结论必须基于并集。

mission30（d33ffe06，国家 + 畸形厂商过滤，五条减法探针）因此在起飞前被 mission31 取代：

- 真实记录送出前去掉 IE 7、IE 35、IE 244 与长度小于 4 的 221（`drop_scan_element()`）；
- 减法探针扩到八条：K60F 去 7、K60G 去 195、K60H 去 32 和 35、K60I 去 255/33、K60J 去 221/2、K60K 去 35、K60L 去 244、K60M 去 35 和 244；
- 加法探针仍是五条：K60A 是保留的 5 GHz 记录改名（基线），K60B..K60E 把目标的元素组逐组加回它；
- mission31 镜像 `E:/k60-work/artifacts/wifi-20261118sbl-mission31/boot.img`，201,887,744 B，SHA256 4abbc2a23ce83369c39be644e81a27e4c3929dbad5f3fb8fb08dcf85c4aa9a94，参数 31 条 / 602 B，verify-boot-image OK，归档里同时含 scan record elements filtered 与 target minus element 两个字符串。

判读：K60K/K60L/K60M 任一出现，35 或 244 就是过滤器，生产修法就是让它们离开记录；只有 K60A 出现而 Emilelu_5G 仍不见，则过滤器是共享元素的内容（HT/VHT/HE operation 的宽度与 80 MHz 频道结构不一致），下一版把 2.4 GHz 同族的 operation 内容换进目标记录再测。

mission27/28/29/30 均建于 2026-11-19 07:12–07:57、从未飞行，已被 31 取代；四个 artifact 目录已删除，`check-bisect-coverage.py --prefix wifi-` 现在只剩 mission31 一条待飞。


## 28. Mission32：元素区在 384 字节处被截断

把 mission24 console 的 44 条 Preferences 列表取并集，38 条带元素清单的记录里 33 条 KEPT、5 条 DROPPED，唯一被丢的 5 GHz 记录仍是目标 c8:bf:4c:30:03:1c 5240 -51 cap 0x0511（Emilelu_5G）。两条被保留的 5 GHz 记录是 3a:16:5a:1f:fb:a5 5200 -77 ie 307 与 38:16:5a:4f:fb:a5 5200 -78 ie 361，元素号集合都含国家 7、功率约束 32、VHT 发射功率 195、厂商 221、HE 255，所以单条元素不可能是过滤器；TPC 报告 35 与 IE 244 也出现在被保留的 2.4 GHz 记录里（含同族 c8:bf:4c:30:03:1d），同样排除。两频段 RSN 逐字节相同（24 B：01 00000fac04 0100 00000fac04 0200 00000fac02 000fac08 8c00，group CCMP / pairwise CCMP / AKM PSK+SAE / caps 0x008c），安全类型也被排除。

剩下的是元素区的形状：station 用 384 字节定长数组承载扫描元素（src/nw_sta.c:14 #define IE_MAX 384、:61 if (len > IE_MAX) len = IE_MAX;、:66 b.ie_len = len; memcpy(b.ie, ie, len);，ABI include/nw_abi.h:52 uint8_t ie[384];）。目标 5 GHz 记录报 ie 384（正好等于上限），但按 TLV 走到 318 B 就断了，剩 66 B 构不成完整元素；2.4 GHz 同族 347 B 走到底，两条被保留的 5 GHz 记录 307/361 B 也走到底。mission25 的两条探针与此一致：K60D（目标 + 载体完整 382 B 元素区）被保留，K60B（载体 + 我们 384 B 元素区）被丢——尾部残缺才是差异，而不是任何单条元素。

代码 a9e8e399 删掉 mission31 的元素过滤器（35/244 在被保留的记录里同样存在，过滤理由不成立），fill_result() 改为只送到最后一个完整元素，并在发生裁剪时打印 wifi-net: scan record tail %u of %u bytes is an incomplete element and is not served。站端源头未动：本次靠裁剪交付合法记录，如果仍不见行，下一版再把 IE_MAX 与 ABI 数组一起放大到 1024（station 与 kext 两处构建都要改）。

十三条探针照旧送出（K60A 基线、K60B..E 加法、K60F..M 减法），所以这一次飞行同时回答两个问题：真实记录裁剪后是否出现，以及哪条探针复现。

mission32 镜像 E:/k60-work/artifacts/wifi-20261118sbl-mission32/boot.img，201,887,744 B，SHA256 fd80093a4ad199c5e265dc4e0c1d4f7f3b8e75ce197f73959ccf3f93ca02e9ba，参数 31 条 / 602 B，check-image-args OK，verify-boot-image OK，未飞；mission31 目录已删，check-bisect-coverage.py --prefix wifi- 只剩 mission32 一条待飞。

判读：Emilelu_5G 出现，根因就是 384 字节截断，生产修法是交付完整或裁剪后的元素区；仍不出现，则把 ABI 数组放大后重测。

放大版已在 917c89ee 落地：两个构建脚本都从共享头生成 out/abi/nw_abi.h（uint8_t ie[384]; -> ie[1024];），station 的 #define IE_MAX 384 同步改成 1024，任一锚点不符就以 shared ABI element array differs 终止；下一次构建（mission33）自动带上它，mission32 的镜像仍按裁剪版交付。

尾部残缺不是唯一判据：把 mission24 console 的每条记录按 TLV 走一遍（PongWifiNet.cpp:412 的循环本身就在第一个不完整元素处停下，所以清单长度就是可走到的位置），used = Σ(2+len)、leftover = ie - used，再看它在 Preferences 并集里是否被保留：38 条记录里 33 条 KEPT、其中 17 条同样有整段走不完的尾巴；5 条 DROPPED 全部有尾巴。两条被保留的 5 GHz 记录 leftover 分别是 33 B 与 51 B，目标记录是 66 B。也就是说「末尾停在半个元素」这件事 wifid 并不是一律拒绝，mission32 的裁剪是一次必要的合法性修复，但能不能把行拉回来还要看飞行结果；真正能指名道姓的仍是十三条探针（K60F..M 每条去掉一组元素），以及放大 ABI 的下一版。

## §29 Mission33：元素区放大到 1024 字节

Station 的 384 字节上限不只影响尾部，它决定了 wifid 能看到的整条记录。917c89ee 之后，两个构建脚本都从共享头生成 out/abi/nw_abi.h（ie[384] → ie[1024]），station 的 IE_MAX 同步 1024；station 归档用 build-ath11k-abi1.sh 重新构建为 /opt/k60/trees/k60build/wifi/ath11k-abi1/libPongAth11k.a（SHA256 6ef0058f…），生成源码里 #define IE_MAX 1024，SAE 探针五行仍在。

mission33 镜像 E:/k60-work/artifacts/wifi-20261118sbl-mission33/boot.img，201,887,744 B，SHA256 446d5332847590f644e54905783f2e064675ff130e3fba3d2bbe7612d7c85bb8，head 1e31b49a，args 31 条 / 602 B，check-image-args OK，verify-boot-image OK；归档 SHA256SUMS 记的 station 就是 abi1 的 6ef0058f，native 侧 abi/nw_abi.h 含 uint8_t ie[1024]。

判读：目标 AP 的元素区在 384 上限下只能到 318 B，放大后应交付完整元素区（预计 ie≈642）。Emilelu_5G 出现即根因是 384 截断，生产修法就是保持放大；仍不出现则十三条探针照旧指名元素。mission32（fd80093a，裁剪版）在飞行前被 mission33 取代，artifact 目录已删，记 built-but-never-flown。

两半用的是同一份生成头这件事有实证：station 的编译参数里 `-I overlay -I abi -I shim/include ... -I shared/include`（`build-k60-ath11k.py:527-529`），`clang -E` 对一个只含 `#include "nw_abi.h"` 的探针文件解析出的就是 `ath11k-abi1/abi/nw_abi.h`；kext 侧 `-I abi` 排在 `-I shared/drivers/Ath12kWifi/include` 之前（`build-k60-wifi-native.py:110`），而 `drivers/PongWifi/` 下没有同名头可以抢先，所以两个目标文件看到的都是 1024 字节数组。station 的 `IE_MAX 1024` 与 ABI 的 `ie[1024]` 因此是同一次改动的两半，不存在「station 写 1024、kext 只读 384」的越界路径。


## §30 mission34：把共用元素的「内容」也变成探针（2026-11-19 09:16）

mission33（446d5332，head 1e31b49a）未飞就在飞行窗到来前被 mission34 取代，artifact 目录已删除，记 built-but-never-flown。

新代码 d91cfc2a（`drivers/PongWifi/PongWifiNet.cpp`）：`freeze_scan_list()` 排序后把表压到 45 条给 19 个探针留位（`if (gSnapCount > 45) gSnapCount = 45;`），并加第三组 6 个探针 K60N..K60S。前五条把两条记录都有的元素的**载荷**从守护进程会保留的 carrier 拷进目标记录：HT operation（61）、VHT operation（192）、VHT capabilities（191）、HT capabilities（45）、extended capabilities（127）；只有长度相同才拷（`memcpy(q.ie + to + 2, c.ie + co + 2, t.ie[to + 1])`），结构不动、偏移不变。K60S 是 mission32 没飞过的裁剪对照：把目标记录尾部不完整元素切掉后再交付。

为什么需要第三组：减法探针（K60F..K60M）会造出真实 AP 不会发的记录——少了 HT/VHT operation 的结构本身就不合法，命中可能只是「结构残缺」而不是「这个元素有罪」；换载荷保持结构合法，命中就直接指向内容。三组合起来（加一个元素 / 减一个元素 / 换一个元素的载荷）才能把过滤器夹到单个元素。

镜像：`E:/k60-work/artifacts/wifi-20261118sbl-mission34/boot.img` 201,887,744 B，SHA256 b08a14f8936e07e45fb117e330a82ae6654b25a9caaadb24a5c2a2a2929ef3a5，head d91cfc2a，args 31 条 / 602 B（`image-arg-audit: OK`），`verify-boot-image: OK`；native 归档里 `wifi-net: probe %s = target with %s` 存在，station 仍是 abi1 的 6ef0058f（`#define IE_MAX 1024`）。

判读：`judge-wifi-mission34.py` 打印 19 条探针各自的 KEPT/ABSENT 与真实 Emilelu_5G 行；`mission34-checklist.md` 是给人看的步骤。真名行出现即设置页这一项关闭；只出现某条探针则那条探针改动的元素就是过滤器。

## §31 2026-11-19 09:37 mission35：1024 字节元素区与 42 字节国家 IE 在真机上生效，但没有人打开设置页

镜像 E:/k60-work/artifacts/wifi-20261118sbl-mission35/boot.img 201,887,744 B，SHA256 7b654920e7c86d518381382342b20c2f95e6715aa1c1185459973e5deb108cc6，head d5c03c0d，09:33 构建，args 31 条 / 602 B（image-arg-audit: OK、verify-boot-image: OK）；station 是 abi1 的 6ef0058f（#define IE_MAX 1024，struct bss … ie[IE_MAX]），native 归档里 withheld from 存在。

飞行 09:37:33–09:52（boot.json startedAt 09:37:33.569，captureArmed/bootAccepted/returnedToFastboot 全 true），采集 E:/k60-work/evidence/usblog-20261119-093727/console.log 488,000 B / 7,196 行 / SHA256 6385bad479509de9609bd450231bcd2dfda67336c78491fce8cd0a7a88f46c8c。

两处改动都在真机上生效：wifi-net: bss 9/17 5240 MHz -52 dBm age 2041 bssid c8:bf:4c:30:03:1c ie 390 cap 0511 cc CN Emilelu_5G —— 记录报 ie 390，已超过旧的 384 上限，说明 1024 元素区在 station 与 kext 两端一致；wifi-net: country element of 42 bytes withheld from the 5240 MHz record 出现 3 次，42 字节的填充国家 IE 没有进入下发的记录。

但整趟没有一条 scan request，也没有任何 WiFiScanObserverNetwork 列表（Preferences 与 configd 都是 0）：wifid 一次扫描请求都没发，所以既没有 daemon 侧列表可对照，也没有真实行被观察。19 条探针每轮都生成（本次 carrier 是 2417 MHz 96:de:f9:b6:be:7e，冻结时 5 GHz 记录还没出现，走的是 2.4 GHz 回退），只是没有人打开设置页。

更正（2026-11-19 10:26）：先前把 boot 早期的 4 次 native client type 103 get bytes=1164 -> 0 读成「daemon 读走了扫描记录」是错的——103 在 Apple80211 枚举里是 kCurrentNetwork（PongWifiNet.cpp:76），返回的是当前已加入网络的那条 1164 字节记录，不是扫描表。按请求类型统计四趟采集（脚本 E:/k60-work/scratch/type-counts.sh）：mission16 有类型 10×1、11×1、103×28，mission24 有 10×1、11×1、103×22，mission25 有 10×1、11×1、103×24，而 mission35 是 10×0、11×0、103×8。也就是说这一趟 wifid 连一次扫描请求都没发（类型 10 为 0），扫描结果也从未被取走（类型 11 为 0），采集里的 scan starts on 42 channels 全是 station 自己的漫游扫描，与 daemon 无关。所以「0 条 Preferences」在这里是「daemon 没扫描」，不能当成「读了记录但没记日志」；设置页必须由人打开，这是硬前提。

判读 UNOBSERVED。教训：设置页那一步必须有人在，而且要落在窗口内；下一趟要么等用户确认在手机前再飞，要么把采集窗口拉到 25 分钟以上并在检测到 Preferences 列表后提前收尾。mission34（b08a14f8）保留为「只测 1024 元素区」的单变量对照，仍欠一次飞行或需要删除。

## §32 2026-11-19 10:19 wifid 20G81 的离线拆解：列表删除路径只剩 WAPI 一条

对 E:/k60-work/scratch/wifid-20G81（2,606,496 B，SHA256 96a3c5df…，arm64e）做两跳 xref：cstring → __os_log_fmt 描述符 → __TEXT,__text 的 adrp/add 立即数解码，并用 LC_FUNCTION_STARTS 划函数边界（笔记 E:/k60-work/scratch/wifid-filter-notes.md，171 行）。

结论：整份 wifid 里按「记录字段」删掉一条扫描 BSS 的只有 **WAPI 过滤器**。谓词在 0x1000a8274，取 scan record 字典（WiFiNetwork +0x10）的 key "WAPI"（CFNumber/SInt32），缺失按 0 处理；(v & 3) == 3 && (v & 0xc) != 0（即 v ∈ {7, 11, 15}）时丢弃。两个丢弃点：__WiFiDeviceProcessScanDoneEvent（0x100059828，门 ldrb w8,[x19,#0xa8]，循环 0x100059c10 打 "%s: filtered out WAPI network %@" 后不 append）与 __processScanBeaconCacheEntry（0x100052034，0x100052138 同一谓词，无门）。旁证 WiFiDeviceAssociateAsyncWithCommand（0x1000526f8）用它判 WAPI，WiFiDeviceSetWapiEnabled（0x1000569dc）写 device+0x1690。

负结果（省掉重复排查）：之前怀疑的六条 5 GHz/hidden/SSID 字符串**都不在列表删除路径上**——"%s: ignoring hidden network"（0x1001ec50c，引用点 0x10015a028）属于 WiFiPerfPerAssoc.m 的指标采样；invalid 5ghzSsid（0x1001ef303）、companion network …（0x1001ef02a）、2Ghz scanned network…（0x1001ef406）、Correspondng 5GHz network（0x1001ee53f）、guess1..4（0x1001efaf6）都属于 WiFiIDSSyncEngine 的 BSSID 猜测与口令继承，与列表无关；_nomap/(IE check)（0x100036d40/0x100036d70）是 GEO 质量上报。

意义：我们的记录没有 WAPI 标记（key 缺失 ⇒ v=0 ⇒ 保留），所以 **wifid 里不存在「按元素/频道/SSID 后缀丢弃」的路径**；mission25 的 B/E 两条探针被丢，最简解释仍是它们携带的目标元素区在旧 384 上限下被截断成不完整尾部（mission35 的 trim + 1024 元素区 + 扣留 42 字节国家 IE 正好把这一条修掉）。因此下一步仍是让带着干净记录的 mission35 在有人看设置页时飞一次；K60J（目标减 221/2）保留作为「畸形厂商元素」的对照，不是当前首选。

## §33 2026-11-19 10:22 先飞 mission34：单变量，且保留真实的国家元素

mission35 的两处改动已在真机上生效（ie 390 证明 1024 元素区两侧一致；42 字节国家 IE 被扣留的日志出现三次），但它同时改了两个变量，而且扣留本身可能有害：被 daemon 保留的两条 5 GHz 记录都带 6 字节国家 IE，CoreWiFi 把国家元素翻译成管制三元组，缺了它，5 GHz 信道可能被判成未知管制域，于是记录仍被丢掉——这会用一个新原因掩盖真正的修复。它还把两条探针变成空转：K60F（真实记录减国家元素）与修好后的真实记录完全相同，K60B（保留记录加我们的国家元素）在服务前就被扣留吃掉。

mission34（E:/k60-work/artifacts/wifi-20261118sbl-mission34/boot.img，201,887,744 B，SHA256 b08a14f8936e07e45fb117e330a82ae6654b25a9caaadb24a5c2a2a2929ef3a5，09:16 构建）只有一个变量：station 与 kext 都换成 1024 字节元素区（/opt/k60/trees/k60build/wifi/ath11k-abi1，#define IE_MAX 1024；native-sbl-mission34 的 abi/nw_abi.h 含 uint8_t ie[1024]，其 SHA256 81a5c2bdb563e759f9ddd4470288dad3977f1285837001e95a5541b39e54275c 与 build-manifest 的 wifi_archive 相同），记录照实携带 AP 的 42 字节国家 IE，19 条探针语义完整。所以它是「384 字节上限是否就是那一行消失的原因」最干净的一次判断：真实行出现即根因坐实、可直接收工；不出现则探针 K60B（国家）/K60D（目标元素）/K60J（厂商 221/2）指名下一个嫌疑。

mission35 不删，改为「若 K60B 被丢、而 K60F 被保留」时的第二发：届时扣留才是有证据的方向，且需要先把扣留从所有目标系探针里摘出去再飞。

## §34 2026-11-19 10:30 384 从来不是线上格式的限制，而是我们自己 ABI 的限制

把两处数组摆在一起看：

- 线上记录 scan_result（drivers/PongWifi/PongWifiNet.cpp:89）是 uint16_t elements_length; uint8_t elements[1024];，static_assert(sizeof(scan_result) == 1164 && offsetof(elements) == 0x8c)（:119-120）。20G81 的 wifid 每次正是按 **1164 字节**取这条记录（native client type 11 get bytes=1164），也就是说 daemon 侧本来就预期最多 1024 字节元素。
- 384 只出现在我们自己内部：station 的 src/nw_sta.c:14 #define IE_MAX 384，扫描时 if (len > IE_MAX) len = IE_MAX;（:61）再把 ie_len/ie 放进 include/nw_abi.h:52 uint8_t ie[384];（:66）。

所以目标 AP 的 390 字节元素区是**在我们自己的代码里**被截成 384 的，截断点落在某个元素的中间；线上那条「384 字节、走不到结尾」的记录不是 AP 发的，也不是 Apple 的格式，而是我们这个内部上限的产物。mission34 把 IE_MAX 与 nw_abi.h 一起抬到 1024（两侧同一次改动，见 §29 的引号包含证明），390 < 1024，记录因此第一次以 AP 原本的样子到达 wifid。这不是改协议，是我们自己的 ABI 追上它本来就在用的容量。

对照：被 daemon 保留的两条 5 GHz 记录元素区是 307 与 361 字节，都在旧的 384 以内、也都能完整走到结尾；唯一被丢的那条正是唯一越过 384 的。这条相关性现在有了机制解释：截断的是我们，不是 AP。

## §35 2026-11-19 10:33 mission34 飞行：单变量镜像，但窗口内仍无人打开设置页

镜像 E:/k60-work/artifacts/wifi-20261118sbl-mission34/boot.img 201,887,744 B，SHA256 b08a14f8936e07e45fb117e330a82ae6654b25a9caaadb24a5c2a2a2929ef3a5，09:16 构建；station /opt/k60/trees/k60build/wifi/ath11k-abi1（IE_MAX 1024），native 81a5c2bd… 与 build-manifest 的 wifi_archive 一致，abi/nw_abi.h 含 uint8_t ie[1024]。整趟只有一个变量：元素区从 384 抬到 1024；国家 IE 照实下发，探针语义完整。

飞行 10:33:06–10:48:33（boot.json imageSha256 B08A14F8…，captureArmed/bootAccepted/returnedToFastboot 全 true，bootExitCode 0），采集 E:/k60-work/evidence/usblog-20261119-103258/console.log 467,538 B / 6,949 行 / SHA256 591ebb97c8d5d78843f2efa35461878754c993cae2ebe6f1db3243dbf4cd4495；K60AUTORESET: 900 s since boot 结束后脚本尝试回 Android（日志里出现 Android up），但 10:50 复查时 USB 上既无 fastboot 也无 adb，需要用户看一眼手机。

判读：lists of client=Preferences: 0、scan request 0、scan result served 0——和 mission35 一样，窗口内没有人打开设置页，wifid 没有发出扫描请求，pane 状态不存在可观察的面。因此 19 条探针（K60A..K60S，本次 carrier 又是 2.4 GHz 回退 96:de:f9:b6:be:7e，因冻结时 5 GHz 只有 1 条记录）全部「ABSENT」只是无列表的必然结果，不能读成「daemon 丢掉了它们」。

可直接用的正面证据仍有一条：wifi-net: bss 9/10 5240 MHz -51 dBm age 552 bssid c8:bf:4c:30:03:1c ie 390 cap 0511 cc CN Emilelu_5G，且全会话 incomplete element 计数为 0——在 1024 元素区下，这条记录第一次以完整、可解析的形态存在于 kext 侧（旧的 384 上限下它会停在 318 字节）。

结论：mission34 不再欠飞行（P-218 清零），但 pane 判读依旧是 UNOBSERVED。要做到「显示并可用」，必须在一次 15 分钟窗口里有人打开 设置→无线局域网 并下拉刷新；设备内没有任何替代触发方式（/usr/bin 为空、无 uiopen/launchctl/notifyutil，wifid 的扫描请求只由设置页客户端产生）。

## 36. mission34b：设置页 5 GHz 行出现，pane 关闭

- 镜像：wifi-20261118sbl-mission34（boot.img 201,887,744 B，SHA256 b08a14f8936e07e45fb117e330a82ae6654b25a9caaadb24a5c2a2a2929ef3a5，head d91cfc2a，args 31/602，verify-boot-image OK）。只改了 station 的 1024 字节元素区，没有扣留国家 IE。
- 飞行：11:53:17 起飞，K60AUTORESET: 900 s since boot 结束；boot.json accepted/returned true；控制台 E:/k60-work/evidence/usblog-20261119-115312/console.log 1,023,926 B / 12,632 行 / SHA256 75af24fb5497e7d8c1f4871f39f6cd49ded9407830d1bbb49d2d506bb90a6fa3。
- 观察者：38 条 scan request、3,901 行 WiFiScanObserverNetwork、12 条 Preferences 列表、52 个不同 BSSID。
- 结果：真实记录出现——<WiFiScanObserverNetwork : 0x14b13d2d0 SSID='Emilelu_5G' BSSID='c8:bf:4c:30:03:1c' RSSI=-52>；judge-wifi-mission34.py 打印 REAL Emilelu_5G row: SEEN / VERDICT: PANE CLOSED；19 条探针 K60A..K60S 全部被 daemon 保留。
- 可用性同一趟成立：wifi: connecting to c8:bf:4c:30:03:1c on 5240 MHz、wifi: connected、WiFi lifecycle test PASS: reconnected BSSID c8:bf:4c:30:03:1c state=6 IPv4=1 lease=3/3、wifi-net: en0 address 192.168.31.232, packets in 1632 out 1897。用户目视确认「全都有」。
- 结论：5 GHz 行的根因就是我们自己 ABI 的 384 字节上限（§34）；1024 字节元素区是生产修复。mission35 的国家 IE 扣留没有必要，不进生产。
- 新开的两条观察（本轮未解）：
  - 状态栏 Wi-Fi 只显示一格，而设置页满格。设置页读的是记录里的 RSSI（-52/-47 dBm，满格强度）；状态栏走 kRssi（Apple80211 IOC 16），整趟只被问过 1 次（native client type 16 get，type 106 也 1 次），驱动按 PongWifiNet.cpp:853-856 回 version 1 / radios 1 / unit 0(dBm) / 各链 -47。所以要么状态栏没刷新，要么它读的不是 kRssi；下一版镜像给每次 kRssi 请求加日志，并记录当前网络记录的 rssi/age。
  - 触摸在复位前几分钟无响应。控制台 41 条 Pong touch HID: touch detection mode，最后一条在第 13,830 行（全文 14,029 行），之后约 200 行才 autoreset，说明触摸驱动到关机前仍在工作，症状更像关机/teardown 路径，不属于 Wi-Fi。


## 37. Mission36：干净镜像关掉 pane，状态栏的「一格」来自内核侧自动关联（2026-11-19 12:33）

- 镜像：`wifi-20261118sbl-mission36/boot.img`，201,887,744 B，SHA256 `8af8f58916d01d4078796c0c33b5a22967a8926ceabb9a2deaddf9821da20871`，head `45add8d1`，31 个参数 / 602 B（image-arg-audit OK，verify-boot-image OK）。相对 mission34b 只少了 19 条诊断探针和国家 IE 扣留，保留 1024 字节元素区与扫描记录尾部裁剪。
- 飞行：12:33:53 起飞，12:49:22 结束（boot.json captureArmed/bootAccepted/returnedToFastboot 全 true，bootExitCode 0）；console 1,206,266 B / 14,893 行 / SHA256 `4946a4326551ad488363ab39dc6950b3210a61d3a1b4d488bb6be4c92078170d`。
- 判据（judge-wifi-mission36.py，修正后）：68 次 scan request、53 条 client='Preferences' 列表、4,568 行 WiFiScanObserverNetwork、147 行 `SSID='Emilelu_5G' BSSID='c8:bf:4c:30:03:1c' RSSI=-39`、服务出的诊断探针 0 个 → `PANE CLOSED, PROBES GONE`。
- 用户确认（m34715）：设置页里有这一行，点进去能看到 IP；m34976 前后又确认从设置页重连 5 GHz 后状态栏满格。也就是说「显示并可用」在干净镜像上成立。
- 状态栏「一格」的成因（用户 m34735 解释并实测）：连接是内核侧 association test 自己建立的，设置页并没有保存这个网络，所以状态栏显示的是未保存/未知网络的一格；用户在设置页点一次重连后立刻满格。rssi 日志佐证两个频段的值几乎相同（5 GHz -50 dBm、2.4 GHz -47 dBm，noise 都是 -95），所以不是 RSSI 映射问题，而是「连接来源」问题。
- 日志量的观察（用户 m34694 的怀疑）：起飞到 12:40:20 共 437 KB ≈ 1.1 KB/s，其中 PongWifi 105,597 B（24%）、wifi-net 85,945 B（20%）、K60 USBLOG 轮询 12,876 B（3%）；这一飞桌面大约 6 分钟才出来，而 mission34b 约 3 分钟。尚未证明因果，但内核侧自动关联 + 每秒状态行是下一步要收紧的对象。
- 后续（mission37 方向，未起飞）：① 把 association test 改成 boot-arg 开关且默认关闭，避免它抢在设置页之前关联；② 把 `wifi-net: en0 address …` 这类每秒状态行降到 30 秒或挂到同一个开关后面；③ 不再需要 kRssi 逐条日志时把它一起关掉。

## §38 2026-11-19 13:25 iOS 27（24A446）ABI 迁移：扫描记录与关联事件落地（build-only）

- 用户决定主线转向 iOS 27（fork 的 ios27 分支目标 27.0.1），先在 k60-wifi 开 feat/wifi-ios27-abi，只移植 Apple80211 ABI，不移植协议栈。
- 参照 UniXNU-sheng origin/main c8f92b208068eeaa4cd2b0f592671f04ee70076e（board.toml os_profile = ipados-27.0.1-24A446）：扫描结果 0x8e8 = 2280 字节，元素区在 0x8c 处 2048 字节，元素区之后 68 字节填充，时间戳 0x8d0，尾部 16 字节；关联完成事件 540 字节，result 在 0x214，has_result 在 0x218；关联请求 0x290 字节（22H374 是 0x384，更旧是 0x250），字段偏移相同、只有尾部长度不同；kCardCaps 在 sheng 里是 12 字节。
- 本分支新增 drivers/PongWifi/PongWifiAbi.h（两代常量、pong_scan_elements_room、540 字节事件结构，C 与 C++ 双向 static_assert），PongWifiNet.cpp 用一个 0x8e8 记录同时服务 1164 与 2280 请求：fill_result 按 rq.req_len 计算元素容量，时间戳落在 0x8d0；kScanResult 与 kCurrentNetwork 把 sizeof(out.res) 交给 copy_out 按请求截断；kAssociate 接受 0x250/0x290/0x384 三种长度并记录 gAssocModern27；关联完成事件在 24A446 下改为 540 字节 payload（result=gAssocResult，has_result=1），post_event 缓冲从 128 改为 16+540。
- 构建证明：以 mission36 的参数在 WSL 里离线编译 /opt/k60/trees/k60build/wifi/native-abi27/libPongWifiNative.a 成功（scripts/build-k60-wifi-native.py，站档案 ath11k-abi1），说明 0x8e8 记录与 540 字节事件的 static_assert 在真实 ABI 头下成立；源码测试 summary: 0 failure(s)，check-boot-args 与 check-secrets 通过。
- 元素区改为 2048：27 的扫描记录允许 2048 字节元素，站侧 Ath12kWifi 的 nw_abi.h 仍是 ie[384]、nw_sta.c 仍是 IE_MAX 384（origin/main 的 submodule f087c7dd 实测），照搬就会在 27 上重演 P-230 的截断。本分支把两个 builder 都改为生成 ie[2048] 并把站的 IE_MAX 改成 2048，两处同步。
- 27 站档案构建证明：在 UniXNU/Ath12kWifi 的 f087c7dd 工作树上用 build-k60-ath11k.py --shared 构建出 /opt/k60/trees/k60build/wifi/ath11k-abi27/libPongAth11k.a（739,992 B，IE_MAX 2048，nw_abi.h ie[2048]）；再用这份 27 头编译 kext 也成功（native-abi27s）。27 头新增的 nw_board.diagnostics 字段与 nw_wifi_scan_frequencies 接口不影响现有代码：nw_board 是位置初始化，尾部字段零填充。
- 顺带发现：sheng 的 27 Wi-Fi 记录按 0x8e8 编写，但它自己的站仍按 384 截断元素区；宽 5 GHz 记录在他们那条线上也会被 wifid 丢掉。
- 未验证的风险：24A446 的 IO80211 用户客户端 selector 0 信封（0x3c30 输入、0x3c00 输出）是否与 22H374 相同，手上没有 27 的 IO80211Family/wifid 二进制，无法离线确认；这是唯一还可能在 27 上挡住宿主绑定的形状。等 fork 走到 bsd_init 再取 27 的二进制核对。
- 下一步：fork 的 ios27 分支能上机后，先跑 clean build 的八步流程，再按 mission36 的判据（设置页 Emilelu_5G 行、可加入、192.168.31.x 地址）验收。

## §39 2026-11-19 14:00 24A446 扫描请求与能力位：命名扫描、频道表、缓存结果

27 的扫描入口与 16 不是同一份请求。sheng 的 package/WifiScan.h 与 WifiNet.cpp（origin/main c8f92b2）给出三处必须照抄的形状，这一节记录它们在本驱动里的落点，全部离线验证，未上机（27 还没有可飞的内核）。

1. 能力位（请求 12，12 字节）。24A446 读两位决定扫描会不会到达驱动：bit 22（byte 2 bit 6）让「点名扫描」通过，缺它 Apple80211Scan 立刻 -3903 返回，驱动根本收不到请求；bit 46（byte 5 bit 6）让框架等扫描完成事件（最多 20 秒）再读结果，缺它就立刻读空表。现在 12 字节请求由 pong_wifi_caps_fill() 填 {2,3,6,9,10,14,17,19,22,46}，19 字节请求仍走 22H374 的老位图，16 的行为一个字节都没动。
2. 扫描请求 86（kScanReqMultiple，0x14e8 字节）。名字个数在 0x8，条目在 0xc（每条 40 字节：version、length、32 字节名字），扫描类型在 0x200（3 = 用手上已有的结果回答），频道在 0x210/0x214。请求 10 的频道个数在 0x44、表在 0x48，类型在 0x34（16 上没用到）。pong_scan_multiple_parse() 只取「恰好一个名字且无通配」时点名探测，否则全扫；pong_scan_frequencies() 把 12 字节频道项（flags 0x8 = 2.4 GHz，0x10 = 5 GHz，ch14=2484）折算成 MHz 去重后交给 nw_wifi_scan_frequencies。
3. 频道表为什么必须用。sheng 的记录：WCN7850 上全频道扫描约 15.7 秒，超过框架等待的 12 秒，每次都是空表。所以点名扫描要按请求里的频道走，不能全扫。
4. 27 站的新入口。Ath12kWifi f087c7dd 新增 int nw_wifi_scan_frequencies(const uint8_t *ssid, size_t len, const uint32_t *mhz, size_t count) 与 NW_WIFI_SCAN_FREQUENCIES_MAX 32；本驱动用 weak_import 声明它，站里没有这个符号（22H374 的 ath11k-abi1 归档）时退回 nw_wifi_scan，两个归档都能链。27 头文件里 nw_board 末尾多了 unsigned diagnostics，我们的 nw_board 实例是零初始化，不影响。

离线证据：scripts/tests/pong-abi-selftest.c 的 31 项检查（扫描记录空间、540 字节关联完成事件、能力位、请求 86 解析、频道折算、去重与越界拒绝）在 scripts/tests/test-pong-abi.py 里编译运行通过；脚本另查头文件常量与 PongWifiNet.cpp 的落点，18 项检查 0 失败。test-wifi-sbl-mission.py 新增一条「24A446 扫描请求被解析出名字、类型与频道」，全套 0 失败。编译两遍都对：对 16 头（ath11k-abi1）与对 27 头（ath11k-abi27）都产出 libPongWifiNative.a。

还没验证的仍是那一处：24A446 的 selector 0 信封（0x3c30 入 / 0x3c00 出）。它要等 fork 的 ios27 分支走到 bsd_init、拿到 27 的 IO80211Family 或 wifid 才能核对。kext 侧 24A446 的记录形状、请求解析与事件尺寸都已静态锁定，剩下的是绑定层。
