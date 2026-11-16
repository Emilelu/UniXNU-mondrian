# WiFi IPA rail: Pong votes smpe3/vdd-wlan-ipa, K60 did not

Date: 2026-11-17
Status: candidate image built 2026-11-17 05:53 CST; not flown. c8 remains held.

## 0. Summary

Pong's QCA6490 board profile has a seventh WLAN rail, `vdd-wlan-ipa` on
`smpe3`/PMR735A S3 at 2.2 V. The K60 live DT has the same `rpmh-regulator-smpe3`
regulator node and the cnss node declares `qcom,vreg_ipa = "s3e"`, but the K60
WLAN profile in this repository carries only six rails and never votes smpe3.
Pong's services93/94 record Wi-Fi failing while the first smpe3 read returned
zero and working after the rail was physically ready. The K60 Android
`cnss2.ko` handles the same `qcom,vreg_ipa` rail through its AOP `wlan_pdc`
path; the XNU PongWifi platform has no AOP mailbox and votes only the six
RPMh rails.

This candidate adds the Pong rail as a single board-power variable. It is
based on the already-flown cache candidate (`7cce6e8a`), not on the separate
MHI-preload candidate, so the flight tests only the IPA rail. It does not
change MHI, the event ring, MSI, SMMU, firmware, or boot arguments.

## 1. The divergence

K60 live FDT `E:/k60-work/impl/bt/research/03-reverse/k60-live-fdt.dts:12525-12562`
has `qcom,cnss-qca6490@b0000000`; :12543 declares
`qcom,vreg_ipa = "s3e"`, and :12545-12556 lists six supplies
(vdd-wlan-aon/dig/io/rfa1/rfa2/ant-switch). It has no
`vdd-wlan-ipa-supply`. The regulator itself exists at
`E:/k60-work/impl/bt/research/03-reverse/k60-live-fdt.dts:6434-6446`:
`rpmh-regulator-smpe3`, child `regulator-pmr735a-s3`, min 0x493e0,
max 0x23e380, init 0x493e0, phandle 0x30f. Aliases `S3E` and `pmr735a_s3`
point to it at :34061-34062.

The current K60 profile
`E:/hackios/k60-wifi-ipa/configs/mondrian-wifi-sm8475.json:619-732` matches
the live DT's six rails. c7's console
`E:/k60-work/evidence/usblog-20261116-122546/console.log:486-495` shows only
five physical-ready rail lines (smpe2, smpb11, smpb10, smpc1, smpb12); ldoe7
is ppid 0 and silent. There is no smpe3 line because the generated table did
not contain smpe3.

Pong's profile
`E:/hackios/UniXNU-pong/configs/pong-wifi-sm8475.json:714-732` has the
additional object exactly:

- supply `vdd-wlan-ipa`
- resource `smpe3`, regulator `pmr735a_s3`
- request `[2200000, 2200000, 0, 0, 0]`
- physical `spmi_slave 4, peripheral 161, type 3, subtype 10`
- PPID = (4 << 8) | 161 = 1185 = 0x4a1. The same K60 live FDT has
  `qcom,pmr735a@4` at `E:/k60-work/impl/bt/research/03-reverse/k60-live-fdt.dts:10817`,
  i.e. PMR735A is SPMI slave 4 on K60 too, so the Pong slave number is not a
  guess from a different board.

Pong's evidence: `E:/hackios/UniXNU-pong/migration/ipados18/services94-native-volume-wlan.md:5`
says services93 Wi-Fi exited early because the first smpe3 model read was
zero; :18 says the next capture confirms smpe3 and all actual power rails
ready, QCA6490 using the Pong active-slot firmware completed MHI/QMI/WMI,
published en0, and scanned 19 BSS. `E:/hackios/UniXNU-pong/porting.toml:129`
records the user confirming services112 Wi-Fi works; services107 saw 29 BSS.
So Pong is a full-WiFi reference, not just an MHI/QMI reference.

K60 Android evidence: the shipped Android device tree
`E:/k60-work/evidence/thermal-android-20261114/vendor_boot.dts:10042-10080`
has the same cnss node with `qcom,vreg_ipa = "s3e"` at :10060 and the six
supplies at :10062-10073, and no `vdd-wlan-ipa-supply`. Its
`rpmh-regulator-smpe3` is at :5803-5815, with aliases `S3E`/`pmr735a_s3`
at :21243-21244. So the same PMIC resource exists on K60 Android even though
the supply is not modelled as a Linux regulator consumer.

`E:/k60-work/evidence/thermal-android-20261114/vb/root/lib/modules/cnss2.ko`
contains the strings `qcom,vreg_ipa`, `vdd-wlan-aon`, `vdd-wlan-dig`,
`vdd-wlan-io`, `vdd-wlan-rfa1`, `vdd-wlan-rfa2`, and the AOP message
format `{class: wlan_pdc, ss: %s, res: %s.%s, %s: %d}` plus
`{class: wlan_pdc, ss: rf, res: pdc, enable: 0}`. K60 Android therefore
does have code that manages the s3e rail, through AOP rather than the six
RPMh votes this XNU port performs.

This is a board-power candidate, not a proven MHI cause. c7 reached PCIe link,
BAR, SMMU isolation and MHI READY, and failed waiting for an EE event; a
missing rail could leave the device unable to finish SBL, but the experiment
must decide that.

## 2. The candidate change

Worktree: `E:/hackios/k60-wifi-ipa`, branch `feat/wifi-ipa-rail`, based on
cache candidate `7cce6e8a` (c7 baseline + DMA cache fix).

1. `configs/mondrian-wifi-sm8475.json:733-755` adds `extra_rails` with the
   exact Pong `vdd-wlan-ipa` object above. The original six `rails` remain
   byte-for-byte the K60 live-DT set; `scripts/build-k60-wifi-native.py:43-46`
   still validates only those six against the live FDT.
2. `scripts/build-k60-wifi-native.py:53-56` emits every `extra_rails` row
   into `kPongWifiRails` before the two analogue LDOs. The generated header
   has exactly nine rows: six K60 rails, smpe3 2200/2200/1185/3/10, ldoc10
   1200/1200/0/0/0, ldob5 880/880/0/0/0.
3. `drivers/PongWifi/PongWifiPlatform.cpp:200-203` raises the capacity from
   8 to 9 and documents "six K60 DT rails + Pong vdd-wlan-ipa + two analogue
   LDOs = 9". It still fails closed on an unexpected count and still requires
   every rail to be found in cmd-db and to follow the RPMh request.
4. `scripts/tests/test-wifi-ipa-rail.py` pins the six original rails, the
   exact IPA object (supply/resource/regulator/voltage/SPMI PPID), the builder
   loop, the platform capacity, and rejects six negative mutants.

The candidate does not include `nw_mhi_pre_load`; the base ath11k archive is
the cache-branch archive with `contexts programmed before image` count 0 and
`Pong MHI` count 18.

## 3. Built artifact

All paths are on the build host / WSL:

| Item | Value |
|---|---|
| tag | `wifi-20261117ipa-rail` |
| boot image | `E:/k60-work/artifacts/wifi-20261117ipa-rail/boot.img` |
| boot SHA-256 | `183eebf62b9d3ef504bfa4a1880788b41e9aa4c92b11ee98232cadc52d6fb17c` |
| size | 201,887,744 B |
| manifest | `E:/k60-work/artifacts/wifi-20261117ipa-rail/build-manifest.json` |
| manifest SHA-256 | `4325e63007840b54d4777be424572260def4daff3d52f85a50723f1745eb679f` |
| repo | `feat/wifi-ipa-rail` @ `7b55493a31a368e320daaae718ef9c86c4599106`, dirty 0 |
| kernel | `d187ee75be9c362f574d0feead1303d2bfd4da6211dcaeb41a9053cc07dfa278` |
| payload kernel | `977865b2262f8bd6f9a60c8c6e04fc02bf5d45a87c2a3a4ee16909820a63f4cf` |
| WiFi archive | `97129b551bc6c7c8b044c515ce31cee435d79bbb534654ce409d248736c79596` |
| base ath11k archive | `413ad0a6ea19bad1a8c1630fead2cef702c7edc36d10c8a0fa864efea543bd97` |
| args | 31 items / 602 B, ends `pong_wifi=1 k60_wifi_rsc=2` |
| series | 227 files, `59d8037521a5b07b`, file `bb14a480c6b2ea4b465f409d862394f0ea25cce178d19a63b7253fab3511f9d4` |

Checks already run:

- `python3 scripts/verify-boot-image.py --manifest ...` -> `OK`
- `python3 scripts/check-image-args.py --image ...` -> `OK (31 arguments, 602 bytes)`
- `python3 scripts/tests/test-wifi-ipa-rail.py` -> `PASS` (6 negative cases)
- generated `PongWifiInputs.h` has the nine rows listed above
- cache ath11k archive SHA-256
  `413ad0a6ea19bad1a8c1630fead2cef702c7edc36d10c8a0fa864efea543bd97`,
  pre-load marker count 0

## 4. Flight criteria (prewritten, one variable)

This image may be flown once, with the console capture attached before boot.
Success and failure are judged from the console, not from "the boot looked
normal".

**Setup / one variable**

- Compare against cache candidate `7cce6e8a`; the only executable change is
  the seventh Pong WLAN rail plus its test/TREE-OWNERS registry entry.
- Do not combine with the MHI-preload candidate or c8. Do not change boot
  args, MHI context programming, `seg_len`, MSI target, INTID, SMMU policy,
  firmware, or the cache-policy fix.

**Success — L1 (this experiment passes)**

All of:

1. Boot reaches SpringBoard with a console log; no panic and no boot-death
   before the WiFi driver runs.
2. The console contains a new physical-ready line for the IPA rail, in the
   same format as the six existing rails, with PPID 0x4a1 and 2200 mV:
   `PongWifi: rail smpe3 physical ready PPID=4a1 2200mV ...`.
3. The c7 timeout line is absent:
   `Pong MHI: timeout after 20000 ms ee=0 pm_state=2 exec_env=1 ...`
4. The event-ring path advances. At least one of:
   - `Pong MHI: event type=` appears, or
   - `Pong MHI: EE event execenv=` appears, or
   - the device advances `exec_env` past SBL.
5. `required SM8475 rail missing in cmd-db` and
   `physical WLAN supply did not follow RPMh request` are absent.
6. `ath11k: failed to power up mhi` is absent.

`Pong MHI: irq entered` is not hardware-MSI proof: the shim polls registered
IRQs every millisecond. It is not required for L1 and its presence alone is not
success.

**Failure / stop**

- Same c7 timeout with no smpe3 line: the profile edit did not reach the
  generated table or the rail path; stop and inspect the generated header.
- The smpe3 line appears but the same c7 timeout still occurs with no
  event/EE/exec_env advance: the IPA rail was voted but is not the MHI
  blocker; stop and reassess, do not fly c8 as a fallback.
- `required SM8475 rail missing in cmd-db` or `physical WLAN supply did not
  follow RPMh request`: stop; the rail is not physically available/ready.
- `WiFi owned DMA cache policy not established`: stop; the cache fix did not
  survive this build.
- Panic, black screen, or no console before WiFi: stop; boot-death triage.

**Success — L2/L3 (follow-on, not this experiment)**

- L2: QMI service/channel bring-up, MHI mission mode, 102 channels.
- L3: `en0`/IO80211 interface published and a scan returns BSS entries.

## 5. Relation to the other candidates

- DMA cache policy: already flown at 2026-11-17 02:17, failed L1 with the same
  c7 timeout; it remains a necessary static fix and is included in this
  candidate's parent.
- MHI pre-load: separate candidate `E:/k60-work/artifacts/wifi-20261117mhi-preload/boot.img`
  SHA-256 `ae27680067b54cdc710df4f046e80509f0e930d517bfc080ae43b1aaff573d87`;
  it is not in this image and must not be combined with this flight.
- c8/`5eacc301`: one-branch held experiment with duplicate SBL, failure
  propagation and context/power lifetime gaps; remains HOLD.
