# Wi-Fi 6 and WPA3 on the K60: what it takes

Status: plan, written 2026-11-18 from a read-only audit of the pinned trees.
No feature code is written yet. Branch `feat/wifi6-wpa3`.

The baseline this plan builds on is device-verified: the K60 joins a
WPA2-Personal network, negotiates HT and VHT, gets a lease through the native
DHCP path and carries traffic (missions 11, 13 and 14, recorded in
`docs/research/wifi/SBL-MISSION.md` §12–§15). 11ax (HE) is not negotiated and
WPA3-SAE is refused by construction.

## 1. Wi-Fi 6 (HE): the driver half is already there

`ath11k` already consumes the peer HE capability and the BSS HE operation:

- `E:/k60-work/impl/wifi/work/src/linux-7.0.14/drivers/net/wireless/ath/ath11k/mac.c:2352` `ath11k_peer_assoc_h_he()`
- `:2375` `if (!he_cap->has_he) return;` then `:2380` `arg->he_flag = true`
- `:2424-2432` copies `peer_he_cap_macinfo` / `peer_he_cap_phyinfo`
- `:2433` `arg->peer_he_ops = vif->bss_conf.he_oper.params & 0xffffff`
- `:6055-6076` fills `sband->iftype_data` from the firmware's HE caps

The station's side is what is missing, and one detail of the earlier draft was
wrong: **the station does not send an HE Operation element.** The peer
`HE Capabilities` element is ours to build, but `HE Operation` is the access
point's to send. Upstream does exactly that: `net/mac80211/mlme.c:1905-1943`
and `:2385-2395` attach only the local HE Capabilities (Ext EID 35) plus WMM
info, and the HE Operation (Ext EID 36) arrives in the beacon and association
response. A station that fabricates an HE Operation is advertising AP state.

The second correction is about timing. `ath11k` does not send the peer
association to the firmware when we call `add_station()`; it transmits it on
`BSS_CHANGED_ASSOC` (`ath11k/mac.c:3093-3145` and `:3701-3705`). So the HE
peer capability and `vif->bss_conf.he_oper` must be in place **before** that
notification, and the only trustworthy source for them is the association
response's IEs. `nw_sta.c:467-479` does not parse the association response IEs
at all today, so that parser comes first.

### Change set

All of it lands in the source rewrites of `scripts/build-k60-ath11k.py`
(tracked; the unpacked vendor tree stays untouched), plus a parser in
`nw_sta.c`:

1. Parse the association response IEs (`nw_sta.c:467-479`): record HE
   Capabilities, HE Operation, and the AP's HE MCS/NSS map.
2. `peer_caps()` (`:262-308`): fill `sta->deflink.he_cap` from the AP's
   element, narrowed to our own caps the same way HT and VHT already are, and
   set `has_he = true` only when the AP advertised HE.
3. Set `g_vif->bss_conf.he_oper` from the AP's HE Operation before the
   association-complete path that triggers `BSS_CHANGED_ASSOC`.
4. `build_cap_ies()` (`:194-214`) and `send_assoc()` (`:215-229`): add our
   HE Capabilities element next to `g_ht_ie` / `g_vht_ie`; do not add an HE
   Operation.
5. Gate everything on one flag so an 11ac access point takes today's path
   unchanged.

Width fallback: `nw_sta.c:237-245` and `:554-559` retry `add_chanctx`, but
`ath11k/mac.c:7517-7538` shows `add_chanctx` always returns 0; the width can
only fail later, at channel assign or start (`:8448-8455`). An 80 MHz retry
loop around `add_chanctx` therefore proves nothing and should be dropped rather
than extended.

### Verification

Host side first: `tests/sta_sim.c` gets captured HE beacons and association
responses, and asserts the parse, the narrowing rules, that we never emit an HE
Operation, and that an 11ac AP still takes the VHT path. On device the matrix
is: AP with HE disabled (must still associate VHT), 5 GHz HE 80 MHz, 2.4 GHz
HE, and HE with PMF. AP mode is not a lever: our stack is station-only
(`nw_sta.c:613`).

## 2. WPA3-SAE: migrate the control path first

The legacy station cannot be extended into WPA3. It rejects the network before
any crypto runs:

- `src/nw_sta.c:111-123` `rsn_check()` accepts CCMP + PSK only (`:119` AKM
  type 2) and returns `-2` when MFP is required (`:122`, `caps & 0x0040`).
- `:132-136` `send_auth()` always sends open-system transaction 1; there is no
  SAE commit or confirm.
- `:415-418` accepts only EAPOL key descriptor version 2; WPA3's AKM 8
  four-way uses version 3 (AES-CMAC).
- `:424` hardcodes the RSN IE to AKM PSK (`00 0f ac 2`).
- `src/nw_crypto.c:3-45` has SHA-1, HMAC-SHA-1, PBKDF2-SHA-1 and AES-128 only.
- `drivers/PongWifi/PongWifiNet.cpp:488-490` says "open/WPA2-personal, not
  enterprise or SAE" and returns `EOPNOTSUPP` for `auth_upper != 8`; `:511`
  reports auth type `0x8` only.

The production path (`E:/k60-work/impl/wifi/work/src/UniXNU-sheng/drivers/Ath12kWifi`,
`nw_mainline.c` + `nw_cfg80211_control.c` + `driver_sheng.c`) is not compiled
on the K60 at all: `scripts/build-k60-ath11k.py:568-574` builds
`nw_crypto.c`, `nw_events.c`, `nw_mac80211.c`, `nw_sta.c`, the lx shim and
`PongAth11k.c`, and the generated report still says
`wifi_operational=False` (`:606`). Even there, three limits block SAE:

1. `nw_cfg80211_control.c:168` allows `NL80211_AUTHTYPE_OPEN_SYSTEM` only,
   `:174` passes `.ie` but not `auth_data` / `auth_data_len` (the pinned
   `cfg80211.h:3246,3265` already has the fields), and `:188` whitelists PSK
   and PSK-SHA256 only.
2. `userspace/driver_sheng.c:188-191` requires `auth_alg == WPA_AUTH_ALG_OPEN`
   with `auth_data_len == 0`, and `:480-483` advertises no
   `WPA_DRIVER_FLAGS_SAE`.
3. `userspace/nw_supplicant_frontend.c:67-69` hardcodes
   `key_mgmt WPA-PSK WPA-PSK-SHA256` and `:84-85` writes `ieee80211w 1`
   (PMF optional); WPA3 needs `2`.

The pinned supplicant is genuine: `https://w1.fi/releases/wpa_supplicant-2.12.tar.gz`
is 4,247,413 B with SHA256 `08e23937e16d0155e55cab2b51f51fbe10d80a1aa91c4e15442645059b737ef6`,
exactly `tools/source-lock.json:33-54`, and it carries `src/common/sae.c`,
`dragonfly.c` and `crypto_openssl.c`. What it does not carry in our
configuration is a crypto provider with EC and bignum: `userspace/supplicant.config:1-16`
selects `CONFIG_CRYPTO=internal` + bundled LibTomMath, while `sae.c:45`,
`:1205`, `:1309` and `:1460-1464` call `crypto_ec_*`, and
`crypto_internal.c` has no `crypto_ec_*` / `crypto_bignum_*` at all. The
provider exists only in `crypto_openssl.c:2023,2108,2454,2501,2657` under
`CONFIG_ECC`. So SAE needs a maintained EC/BN provider (OpenSSL or mbedTLS,
statically linked, licence recorded) — not a hand-written Dragonfly.

PMF is not a fallback either: the legacy station has no IGTK or SA Query code.
Until the control path moves, the honest ceiling is WPA2-PSK **without** PMF.

### Sequence

| Stage | Work | Gate |
|---|---|---|
| **P0** | HE plumbing on the legacy path behind one flag | offline `tests/sta_sim.c`; then the on-device matrix above |
| **P1** (parallel) | Add an EC/BN provider, `CONFIG_SAE`, SAE KATs on the host | `build-supplicant.py --target host`; `hardware_verified=false`; no device risk |
| **P2** (main cost) | Move the K60 from `nw_sta.c`'s hand-written SME to the shared cfg80211/mac80211 + `nw_cfg80211_control.c` + `driver_sheng.c` path, still WPA2 | WPA2 association/DHCP/throughput must not regress; `check-mainline-link.py` must report `legacy_station_linked=false` |
| **P3** | Open the three limits: SAE auth type + `auth_data`, AKM 8, `ieee80211w=2`; add IGTK/SA Query | WPA3-only AP positive and negative tests; `hardware_verified` only with a console log |
| **P4** | If P2 proves out of reach, the record says WPA2-PSK (no PMF), WPA3 unsupported | `porting.toml` and this plan updated together |

P2 is an order of magnitude larger than P0 or P1: it replaces the association,
key and MLME path, not a few functions.

## 3. Evidence required before any Wi-Fi 6 or WPA3 claim

1. HE: the association response carries HE Capabilities and HE Operation; our
   association request carries HE Capabilities only; the peer MCS/NSS map
   matches; the rate/width actually used is reported by the driver.
2. SAE: `auth alg=3` transaction 1 and 2 with status 0; RSN IE in the
   association exchange with AKM 8, MFPC=1, MFPR=1; EAPOL descriptor version 3
   with PTK, GTK and IGTK installed and the port authorized.
3. Data: a lease and traffic after the SAE association.
4. Negative: wrong password on a WPA3-only AP must not associate; a WPA2 AP
   must still work; a PMF-required AP must refuse a non-PMF client.
5. Artefacts: console log, the test report and `binary_sha256`; host tests
   never count as device evidence (every `tools/test-*.py` writes
   `hardware_verified=false`).

## 4. Open questions

- Does QCA6490's `interface_modes` in `ath11k/hw.c` advertise HE for the
  station interface on this firmware, or does the board file need a flag?
- Does the pinned `cfg80211.h` expose `auth_data_len` to the glue without a
  header change (the fields exist at `:3246,3265`)?
- Which maintained EC/BN provider can link against the iOS 16.6.1 arm64 target
  with the licenses this project can carry?
