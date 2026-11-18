# Wi-Fi 6 and WPA3 on the K60: what it takes

Status: plan, revised 2026-11-18 after two read-only audits (HE association
semantics; SAE control path and crypto provider). The HE byte codec and its
legacy-station wiring have since landed on branch `feat/wifi6-wpa3` (see
§0.1); nothing has been flown yet.

The baseline is device-verified: the K60 joins a WPA2-Personal network,
negotiates HT and VHT, gets a lease through the native DHCP path, carries
traffic and survives a forced disconnect with a fresh lease (missions 11, 13
and 14, `docs/research/wifi/SBL-MISSION.md` §12–§15). 11ax (HE) is not
negotiated and WPA3-SAE is refused before authentication.

## 0. The order changed after the audit

`nw_sta.c` is **retired** in the shared driver repository: its README says the
production start path is cfg80211/mac80211 (`src/nw_mainline.c`), and the K60
build still compiles the retired path (`scripts/build-k60-ath11k.py:568-571`).
Adding HE to a retired file may be discarded work. So the first step is a
time-boxed probe, not a patch:

| Stage | Work | Gate |
|---|---|---|
| **P0** (half a day) | Can `build-k60-ath11k.py` switch to the `nw_mainline` manifest (cfg80211 + mac80211 + `nw_cfg80211_control.c`) and still link? | `tools/check-mainline-link.py` reports no missing kernel symbols; the bridge already in `:180-203` is the starting point |
| **P1** | Only if P0 fails: HE on the legacy path, in `shared/src/nw_sta.c` (see §2) | offline `tools/sta-sim.sh`, then the on-device matrix |
| **P2** (parallel) | EC/BN provider + `CONFIG_SAE` + SAE KATs on the host | host-only; `hardware_verified=false`; no device risk |
| **P3** | SAE through the migrated control path: auth type SAE with `auth_data`, AKM 8, `ieee80211w=2`, IGTK/SA Query | WPA3-only AP positive and negative tests |
| **P4** | If P0/P3 prove out of reach, the record says WPA2-PSK without PMF and WPA3 unsupported | `porting.toml` and this plan updated together |

### 0.1 What landed first, and why

The P0 probe answered its question without a build: the pinned tree carries
`net/mac80211` and `net/wireless` as git objects but not in the sparse
checkout, and the manifest needs a producer of the mainline link report that
neither tree has yet. Switching the build is therefore a driver-generation
change, not a manifest flip, and it stays ahead of any migration work.

The HE byte codec is independent of that choice, so it was written first:
`drivers/PongWifi/ath11k/pong_he.{c,h}` encodes the HE Capabilities element,
parses the access point's element and narrows the MCS/NSS maps, with no kernel
header, and is exercised on the host by `scripts/tests/test-pong-he.py`.
`scripts/build-k60-ath11k.py` injects the include, the globals and three call
sites into the generated station source. That wiring is the P1 experiment: it
runs on the legacy station the image actually flies, and it can be dropped when
the mainline path lands. It is not evidence that the retired station is the
production path.

## 1. Wi-Fi 6 (HE): what the station must actually do

`ath11k` already consumes the peer HE capability and the BSS HE operation:
`E:/k60-work/impl/wifi/work/src/linux-7.0.14/drivers/net/wireless/ath/ath11k/mac.c:2352`
`ath11k_peer_assoc_h_he()`, `:2375` `if (!he_cap->has_he) return;`,
`:2424-2432` copies `peer_he_cap_macinfo` / `peer_he_cap_phyinfo`, `:2433-2437`
sets `peer_he_ops` from `vif->bss_conf.he_oper.params`, and `:6055-6076`
fills `sband->iftype_data` from the firmware's caps. The station side is what
is missing.

### 1.1 Direction: we send HE Capabilities, the AP sends HE Operation

Upstream's association request writes HT, VHT and then **only** the HE
Capabilities element (Ext EID 35) before the WMM info:
`net/mac80211/mlme.c:1937-1943`. HE Operation (Ext EID 36) is parsed from the
AP's beacon/probe response into `bss_conf.he_oper` (`net/mac80211/he.c:210-220`)
and never sent by a station. A station that fabricates an HE Operation is
advertising BSS parameters it does not own.

There is also no HE fallback: if the association response lacks HT, VHT or WMM
the stack recovers from the beacon (`mlme.c:5441-5475`), but HE has no such
path. Anything HE that the association response does not carry is simply not
negotiated.

### 1.2 Where the peer state has to be set

The firmware is not told about the peer when we call `add_station()`
(`nw_sta.c:560`); that only walks vdev start and peer create
(`ath11k/mac.c:9880-9888` → `:7928-7945`). The WMI peer-assoc is sent from
the `BSS_CHANGED_ASSOC` notification (`nw_sta.c:479` →
`ath11k/mac.c:3701-3705` → `:3093-3145`). So three things must be in place
before `vif_cfg_changed(ASSOC)`:

- `sta->deflink.he_cap` with `has_he = true`,
- `vif->bss_conf.he_oper` (the AP's parameters),
- `vif->bss_conf.he_support` (without it `recalc_sta_he_txbf` returns
  immediately, `ath11k/mac.c:3044`).

### 1.3 `has_he` is a conjunction, not a copy

Upstream's order in `he.c:110-170` is: clear the struct; return if the element
is missing; **require the local interface's HE cap**
(`ieee80211_get_he_iftype_cap_vif`, `:131-134`); compute
`mcs_nss_size = ieee80211_he_mcs_nss_size(elem)` and
`ppe_size = ieee80211_he_ppe_size(...)`, then reject a short element
(`:139-147`); copy; only then set `has_he = true` at `:162`, followed by
the bandwidth recomputation and the per-bandwidth MCS intersection.

`cfg80211_find_ext_elem` does not validate length (`cfg80211.h:7441-7460`
says so explicitly), so the length check has to be ours;
`ieee80211_he_capa_size_ok` is available as a static inline
(`ieee80211-he.h:509-530`). `ath11k` satisfies the local-cap condition on this
board by filling `iftype_data` from the firmware (`mac.c:5969-6042`, `:5993`),
but the code must check it rather than assume it.

Two upstream behaviours worth copying exactly: an AP with
`he_mcs_nss_set == 0` is accepted on non-STRICT hardware (the comment names
iPhone 13, `mlme.c:562-570`), and a local 1-SS `rx/tx_mcs_80` outside MCS 0–7
disables HE and falls back to VHT (`mlme.c:541-557`).

### 1.4 Width is the hidden coupling

Today the only width source is the AP's Operation IE: `ap_width()`
(`nw_sta.c:160-181`) and `cap_bandwidth()` (`:187-192`) produce
`sta->deflink.bandwidth` (`:312`). But `ath11k` picks the phymode from
`bandwidth` (`mac.c:2817-2841`) and the MCS set from the phymode
(`:2516-2554`). A station whose `he_cap` says HE while `bandwidth` still
says VHT-width produces "HE capability, VHT phymode". Upstream derives the
width from the local capabilities (`vht.c:352-423`) and takes the minimum with
the AP's; that is the rule to adopt: `min(AP Operation, local HT/VHT/HE cap
bits)`.

The downgrade path is dead code: `nw_sta.c:242-245` retries `add_chanctx` at
20 MHz, but `ath11k/mac.c:7517-7539` always returns 0. The real failure is the
delayed vdev start (`mac.c:8422-8429`, `:7928-7945`) reached from
`nw_sta.c:317`, and on failure `:318` frees the station and reports
`NW_RES_FAILED` with no width retry. Worse, `start_connect` fixes the width
and builds the IEs (`:554-555`) before `bring_up_channel` could narrow it
(`:245`), so the IEs can claim a width the channel never got.

### 1.5 Integration point and tests

Do **not** put the HE implementation in `build-k60-ath11k.py`'s string
rewrites: that script rewrites the shared `shared/src/nw_sta.c` into
`out/nw_sta_pong.c` (`:529-566`) and `tools/sta-sim.sh:5-11` compiles the
shared file, so anything added by the script is invisible to the offline test —
step ⑦ would lose its unit-test evidence. Put the parse/build code in
`shared/src/nw_sta.c` and reuse the K60 pre-start hook the script already
installs (`:562-565`, which publishes basic rates before
`assign_vif_chanctx`): publish `he_oper`/`he_support` there, which is
naturally earlier than `:479`.

The offline harness does not run today: `tools/sta-sim.sh:5` first runs
`python3 tools/fetch-sources.py --check` and `deps/` does not exist, so the
pinned Linux tree has to be fetched before any test. The simulated station is
also 2.4 GHz only (`tests/sta_sim.c:132-135`, no `ht_cap`/`vht_cap`/
`iftype_data`; `beacon()` at `:45-53` builds SSID/rates/TIM/RSN only), so the
5 GHz band and the capability fixtures come before the HE assertions.

Assertions to add, each tied to a rule above: assoc request order
HT → VHT → HE → WMM and **no** 255/36; HE Cap length
`2 + 1 + 17 + mcs_nss + ppe` consistent with PHY_CAP0's 160/80+80 bits; the
exact bits cleared at 20/40/80/160 (`util.c:2501-2547`); AP
`he_mcs_nss_set == 0` accepted; truncated HE Cap leaves `has_he = false` and
falls back to VHT; local 1-SS MCS outside 0–7 falls back to VHT;
`he_cap`/`he_oper`/`he_support` set before `sta_state` is called.

### 1.6 Licensing and reuse

`Ath12kWifi` carries no LICENSE file (both audited trees), so it is formally
all-rights-reserved; the K60 build already compiles its `nw_sta.c`, which is a
pre-existing exposure this plan does not introduce but should not deepen before
the upstream repository gets a licence. The pinned Linux headers
(`mac80211.h`, `cfg80211.h`, `ieee80211-he.h`) are GPL-2.0-only, while
`ath11k/mac.c` is BSD-3-Clause-Clear. The boundary to keep: include structure
and constant definitions, write the algorithms from the documented behaviour
with the source line cited, do not copy GPL implementation bodies, and record
the reuse in `CREDITS.md`.

## 2. WPA3-SAE: migrate the control path first

The legacy station rejects WPA3 before any crypto runs, in `rsn_check()`
(`src/nw_sta.c:111-123`): `:117` requires CCMP, `:119` requires PSK,
`:121` returns `-2` without both, and `:122` returns `-2` when the AP
requires management-frame protection (`caps & 0x0040`), which SAE always does.
`start_connect` turns that into `NW_RES_UNSUPPORTED` (`:548`). The EAPOL
key-descriptor check (`:415-418`) is not the SAE gate: WPA3-SAE with CCMP also
uses descriptor version 2.

`PongWifiNet.cpp:488-490` states the same ceiling at the driver boundary
("open/WPA2-personal, not enterprise or SAE", `auth_upper != 8` →
`EOPNOTSUPP`), and `:511` reports auth type `0x8` only.

The production path is not compiled on the K60 at all
(`build-k60-ath11k.py:568-574`; the report still says
`wifi_operational=False`, `:606`). Even there, three limits block SAE:

1. `nw_cfg80211_control.c:168` allows `NL80211_AUTHTYPE_OPEN_SYSTEM` only,
   `:174` passes `.ie` but not `auth_data`/`auth_data_len` (the pinned
   `cfg80211.h:3246,3265` has the fields), and `:188` whitelists PSK and
   PSK-SHA256 only.
2. `userspace/driver_sheng.c:188-191` requires `auth_alg == WPA_AUTH_ALG_OPEN`
   with `auth_data_len == 0`; `:480-483` advertises no
   `WPA_DRIVER_FLAGS_SAE`.
3. `userspace/nw_supplicant_frontend.c:67-69` hardcodes
   `key_mgmt WPA-PSK WPA-PSK-SHA256`; `:84-85` writes `ieee80211w 1`
   (PMF optional) instead of `2`.

The pinned supplicant is genuine: 2.12, 4,247,413 B, SHA256
`08e23937e16d0155e55cab2b51f51fbe10d80a1aa91c4e15442645059b737ef6`, matching
`tools/source-lock.json:33-54`, and the archive contains `src/common/sae.c`
and `dragonfly.c`. What it lacks in our configuration is a crypto provider with
EC and bignum: `userspace/supplicant.config:1-16` selects
`CONFIG_CRYPTO=internal` with bundled LibTomMath, `sae.c:45`, `:1205`,
`:1309`, `:1460-1464` call `crypto_ec_*`, and `crypto_internal.c` defines
no `crypto_ec_*` or `crypto_bignum_*`; the provider lives only in
`crypto_openssl.c:2023,2108,2454,2501,2657` under `CONFIG_ECC`. The
`required` list in the lock also has to gain `src/common/sae.c`; today it
stops at `src/crypto/crypto.h`.

PMF is not a fallback either: the legacy station has no IGTK or SA Query code,
so until the control path moves the honest ceiling is WPA2-PSK **without** PMF.

## 3. Evidence required before any claim

1. HE: the association request carries HE Capabilities only (no 255/36); the
   association response carries HE Capabilities; the peer MCS/NSS map matches;
   the driver reports the HE phymode and the width actually used.
2. SAE: `auth alg=3` transactions 1 and 2 with status 0; RSN IE with AKM 8,
   MFPC=1, MFPR=1; EAPOL descriptor with PTK, GTK and IGTK installed and the
   port authorized; a lease and traffic afterwards.
3. Negative: wrong password on a WPA3-only AP must not associate; a WPA2 AP
   must still work; a PMF-required AP must refuse a non-PMF client.
4. Artefacts: console log, test report, `binary_sha256`; host tests never
   count as device evidence (every `tools/test-*.py` writes
   `hardware_verified=false`).
5. The on-device matrix cannot include "HE with PMF" until `rsn_check`'s
   MFPR rejection is lifted; that is an independent change, not part of HE.

## 4. Open questions

- Does the `nw_mainline` manifest actually link on this tree (P0), and does
  QCA6490's `interface_modes` in `ath11k/hw.c` advertise HE for the station?
- Does the pinned `cfg80211.h` expose `auth_data_len` to the glue without a
  header change?
- Which maintained EC/BN provider links against the iOS 16.6.1 arm64 target
  with a licence this project can carry?
- Does the shared station's `bandwidth` derivation need the same
  min(local, AP) rule before HE can be enabled at all?
