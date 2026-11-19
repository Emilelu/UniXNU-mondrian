#!/usr/bin/env python3
"""Pin the official BHI_EXECENV/SBL direct-push and mission-poll path.

Why this test exists: c7 reaches MHI READY with ee=0 and exec_env=1 (SBL) but
never receives an EE event. The official MhiBoot.c polls BHI_EXECENV and sends
the BHIe image when it reads SBL. The first K60 attempt queued
DEV_ST_TRANSITION_SBL and failed during teardown. The direct successor proves
the BHIe transfer works, but the host keeps cached ee=1 while the device is
already AMSS/M0. This test pins the next single-variable step: poll
BHI_EXECENV after the direct AMSS download and cache AMSS/WFW before
mhi_sync_power_up resumes.

Run: python3 scripts/tests/test-wifi-sbl-mission.py
"""
from __future__ import annotations

import os
import pathlib
import plistlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
BUILDER = ROOT / "scripts" / "build-k60-ath11k.py"
PLATFORM = ROOT / "drivers" / "PongWifi" / "PongWifiPlatform.cpp"
NET = ROOT / "drivers" / "PongWifi" / "PongWifiNet.cpp"
FAILS = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + name + (("  " + detail) if detail else ""))
    if not ok:
        FAILS.append(name)


def main() -> int:
    text = BUILDER.read_text(encoding="utf-8")

    check("MHI header grows one pong_sbl_pushed field",
          text.count("bool pong_sbl_pushed;") == 1,
          "count=%d" % text.count("bool pong_sbl_pushed;"))
    check("boot path pushes only when fbc and not latched",
          text.count("if (mhi_cntrl->fbc_download && !mhi_cntrl->pong_sbl_pushed) {") == 1)
    check("poll is bounded to 200 samples",
          "for (i = 0; i < 200; i++) {" in text)
    check("poll checks register validity before reading",
          "if (!MHI_REG_ACCESS_VALID(mhi_cntrl->pm_state))" in text)
    check("poll reads BHI_EXECENV",
          "ee = mhi_get_exec_env(mhi_cntrl);" in text)
    check("SBL sets the cached execution environment before the push",
          "mhi_cntrl->ee = MHI_EE_SBL;" in text)
    check("SBL logs BHI_STATUS before pushing",
          "BHI_STATUS=%#x; pushing the AMSS image" in text)
    check("SBL gates the push on BHI_STATUS success",
          "status = bhi >> 30;" in text and
          "if (status != BHI_STATUS_SUCCESS) {" in text)
    check("SBL stops on BHI_STATUS error",
          "if (status == BHI_STATUS_ERROR) {" in text)
    check("SBL calls the AMSS download exactly once in the boot path",
          text.count("amss_ret = mhi_download_amss_image(mhi_cntrl);") == 1,
          "count=%d" % text.count("amss_ret = mhi_download_amss_image(mhi_cntrl);"))
    check("SBL no longer queues the stock transition",
          "mhi_queue_state_transition(mhi_cntrl, DEV_ST_TRANSITION_SBL);" not in text)
    check("pm SBL handler has a one-shot latch",
          text.count("if (mhi_cntrl->pong_sbl_pushed) {") == 1 and
          text.count("mhi_cntrl->pong_sbl_pushed = true;") == 2)
    check("BHIE wait keeps the transfer status and sequence for the log",
          "u32 tx_status = 0, sequence_id;" in text and
          "Pong MHI: bhie tx_status=%#x seq=%#x expected=%#x ret=%d" in text)
    check("mission poll declares its own counters",
          "int i, j, amss_ret;" in text)
    check("mission poll runs only after a successful AMSS load",
          "amss_ret = mhi_download_amss_image(mhi_cntrl);" in text and
          "if (!amss_ret) {" in text)
    check("mission poll is bounded to 2500 samples",
          "for (j = 0; j < 2500; j++) {" in text)
    check("mission poll reads BHI_EXECENV",
          "enum mhi_ee_type mission = mhi_get_exec_env(mhi_cntrl);" in text)
    check("mission poll accepts AMSS or WFW",
          "if (mission == MHI_EE_AMSS || mission == MHI_EE_WFW) {" in text)
    check("mission poll caches the new execution environment",
          "mhi_cntrl->ee = mission;" in text)
    check("mission poll caches the EE, creates MHI devices, then wakes",
          text.count("mhi_create_devices(mhi_cntrl);") == 1 and
          0 <= text.find("mhi_cntrl->ee = mission;") <
          text.find("mhi_create_devices(mhi_cntrl);") <
          text.find("wake_up_all(&mhi_cntrl->state_event);"))
    check("mission poll wakes the power-up waiter",
          "wake_up_all(&mhi_cntrl->state_event);" in text)
    check("mission poll logs the cached EE",
          "exec_env=%d after AMSS download; cached ee updated" in text)
    check("ath11k MHI start raises the ready wait to 60 s",
          "ab_pci->mhi_ctrl->ready_timeout_ms = 60000;" in text)

    platform = PLATFORM.read_text(encoding="utf-8")
    check("association test is enabled by the private fixture",
          "enabled=kWifiTestSsidBytes&&kWifiTestKeyBytes;" in platform)
    check("association probe logs the parsed boot arguments",
          '"PongWifi: association probe: pong_wifi_test=%d/%u pong_wifi=%d/%u' in platform and
          'PE_parse_boot_argn("pong_wifi",&mode,sizeof mode)' in platform)
    check("association test accepts the scan state",
          "if(!attempted&&(st.state==NW_STA_IDLE||st.state==NW_STA_SCANNING)) {" in platform)
    check("association test reports an absent target with hashes",
          '"PongWifi: association target absent: target_len=%u target_hash=%08x' in platform and
          "ssidHash(b.ssid,b.ssid_len)" in platform)
    check("association test tolerates a trailing NUL in ssid_len",
          "b.ssid_len==kWifiTestSsidBytes+1" in platform and
          "!b.ssid[kWifiTestSsidBytes]" in platform)
    check("association test directs a rescan at an absent target",
          '"PongWifi: association rescan %u directed' in platform and
          "nw_wifi_scan(kWifiTestSsid,kWifiTestSsidBytes);" in platform)

    check("the booted volume is probed for the address configuration pieces",
          "void probeFiles()" in platform and
          '"/usr/libexec/wifid"' in platform and
          '"/System/Library/SystemConfiguration/IPConfiguration.bundle"' in platform and
          '"PongWifi: probe %s -> %s size=%llu' in platform)
    check("the association test outlives the link wait for an address",
          '"PongWifi: association test waits for the address configuration' in platform and
          "addressWait=true;deadline=now()+600000;" in platform)
    check("the association test reports the registry busy state while waiting",
          '"PongWifi: association test WAIT: state=%u IPv4=%u busy=%u' in platform and
          "getBusyState()" in platform)

    net = NET.read_text(encoding="utf-8")
    check("the network stack lives under IOResources where the namer looks",
          "IOService::getResourceService()" in net and "publish(stack, platform," not in net)
    check("the network stack service advertises its user client class",
          'kIOUserClientClassKey, "IONetworkStackUserClient"' in net)
    check("the naming request is refused, so the namer learns nothing was named",
          "return kIOReturnUnsupported;" in net and "network stack command %s" in net)
    check("the stack user client reports who opened it and the registry's busy state",
          "proc_selfname(who, sizeof who)" in net and "getBusyState()" in net)
    check("network stack user client initializes through the 4-argument overload",
          "initWithTask(task, security, type, properties)" in net and
          "initWithTask(task, security, type))" not in net)
    check("the interface reports the registry busy state",
          '"wifi-net: registry busy state %u"' in net)
    check("the stack user client reports external methods and its close",
          '"wifi-net: network stack method %u in %u out %u"' in net and
          '"wifi-net: the network stack client closed"' in net)
    check("the interface counts TLS and DNS traffic and names its opener",
          '"wifi-net: tcp443 in %u out %u, dns in %u out %u"' in net and
          '"wifi-net: dns %s query %s"' in net and
          '"wifi-net: 80211 user client opened by %s type %u"' in net and
          "k.https++" in net and "k.dns++" in net)

    # A built tree may be supplied for an end-to-end source-shape check. The
    # repository test still runs when no build is present: the builder anchors
    # above are the source of truth, and the generated files are a projection.
    build = pathlib.Path(os.environ.get("K60_SBL_BUILD_DIR",
                                        "E:/k60-work/build/wifi-sbl-mission4"))
    boot = build / "mhi" / "boot.c"
    pm = build / "mhi" / "pm.c"
    header = build / "pinned" / "linux" / "mhi.h"
    mhi_c = build / "mhi.c"
    if boot.is_file() and pm.is_file() and header.is_file() and mhi_c.is_file():
        btext = boot.read_text(encoding="utf-8")
        ptext = pm.read_text(encoding="utf-8")
        htext = header.read_text(encoding="utf-8")
        ctext = mhi_c.read_text(encoding="utf-8")
        check("generated boot.c has the direct SBL push",
              "BHI_STATUS=%#x; pushing the AMSS image" in btext and
              "status = bhi >> 30;" in btext and
              "if (status != BHI_STATUS_SUCCESS) {" in btext and
              "amss_ret = mhi_download_amss_image(mhi_cntrl);" in btext and
              "mhi_queue_state_transition(mhi_cntrl, DEV_ST_TRANSITION_SBL);" not in btext)
        check("generated boot.c has the mission poll",
              "for (j = 0; j < 2500; j++) {" in btext and
              "if (mission == MHI_EE_AMSS || mission == MHI_EE_WFW) {" in btext and
              "mhi_cntrl->ee = mission;" in btext and
              "mhi_create_devices(mhi_cntrl);" in btext)
        check("generated boot.c logs the BHIE transfer status",
              "bhie tx_status=%#x seq=%#x expected=%#x ret=%d" in btext)
        check("generated pm.c keeps the latch",
              "mhi_cntrl->pong_sbl_pushed = true;" in ptext)
        check("generated mhi.h has the latch field",
              "bool pong_sbl_pushed;" in htext)
        check("generated mhi.c raises the ready wait to 60 s",
              "ab_pci->mhi_ctrl->ready_timeout_ms = 60000;" in ctext and
              "ab_pci->mhi_ctrl->timeout_ms = MHI_TIMEOUT_DEFAULT_MS;" in ctext)
    else:
        print("  SKIP  generated tree not present at %s" % build)

    probe = ROOT / "userland" / "netprobe.c"
    ptext = probe.read_text(encoding="utf-8")
    check("the probe asks for a page and prints the status line",
          '"GET / HTTP/1.0\\r\\nHost: "' in ptext and
          "k60probe: %s status %d line %s\\n" in ptext and
          "k60probe: %s tag %d bytes %d\\n" in ptext and
          "k60probe: no HTTP response within %d s\\n" in ptext)
    mini_h = (ROOT / "userland" / "libmini" / "mini.h").read_text(encoding="utf-8")
    mini_c = (ROOT / "userland" / "libmini" / "mini.c").read_text(encoding="utf-8")
    check("libmini carries the connect system call",
          "SYS_connect = 98" in mini_h and
          "int     connect(int fd, const void *address, unsigned length);" in mini_h and
          "SC(SYS_connect, fd, address, length, 0, 0, 0)" in mini_c)
    p0616 = (ROOT / "patches" / "xnu" / "0616-k60-init-legacy-helper.patch").read_text(encoding="utf-8")
    length = int(re.search(r"#define K60_NETPROBE_LEN (\d+)", p0616).group(1))
    body = p0616.split("static const unsigned char k60_netprobe[K60_NETPROBE_LEN] = {", 1)[1].split("};", 1)[0]
    check("the kernel writes the probe beside the init helper",
          '/private/var/pong/k60probe"' in p0616 and
          "K60PROBE: probe write=%d resid=%d len=%d" in p0616 and
          "O_CREAT | O_WRONLY | O_TRUNC, 0755" in p0616 and
          len(re.findall(r"0x[0-9a-f]{2}", body)) == length,
          "len=%d bytes=%d" % (length, len(re.findall(r"0x[0-9a-f]{2}", body))))
    p0394 = (ROOT / "patches" / "xnu" / "0394-k60-launchd-cache.patch").read_text(encoding="utf-8")
    cache_len = int(re.search(r"#define K60_LAUNCHD_CACHE_LEN (\d+)", p0394).group(1))
    cbody = p0394.split("static const unsigned char k60_launchd_cache[K60_LAUNCHD_CACHE_LEN] = {", 1)[1].split("};", 1)[0]
    craw = bytes(int(x, 16) for x in re.findall(r"0x([0-9a-f]{2})", cbody))
    jobs = plistlib.loads(craw)["LaunchDaemons"]
    job = jobs.get("/System/Library/LaunchDaemons/com.pong.netprobe.plist", {})
    check("the curated cache starts the probe at load",
          len(craw) == cache_len and len(jobs) == 24 and
          job.get("Label") == "com.pong.netprobe" and
          job.get("ProgramArguments") == ["/private/var/pong/k60probe"] and
          job.get("RunAtLoad") is True,
          "len=%d jobs=%d label=%s" % (len(craw), len(jobs), job.get("Label")))
    check("the kernel materializes the probe plist where the cache points",
          "/System/Library/LaunchDaemons/com.pong.netprobe.plist" in p0616 and
          "K60PROBE plist bytes=%d resid=%d error=%d" in p0616 and
          "<key>Label</key><string>com.pong.netprobe</string>" in p0616 and
          "<key>RunAtLoad</key><true/>" in p0616)
    plat = (ROOT / "drivers" / "PongWifi" / "PongWifiPlatform.cpp").read_text(encoding="utf-8")
    net = (ROOT / "drivers" / "PongWifi" / "PongWifiNet.cpp").read_text(encoding="utf-8")
    check("the reconnect reports the link edge and proves a fresh lease",
          'extern "C" void pong_wifi_net_link_down(void) { post_link(false); }' in net and
          "pong_wifi_lease_snapshot(&gLease, lease_clock()).version != 0" in net and
          "pong_wifi_net_link_down();" in plat and
          "pong_wifi_net_has_ipv4()&&(!reconnecting||pong_wifi_net_has_lease())" in plat and
          "lease=%llu/%llu" in plat)
    check("the lifecycle test can disconnect and reconnect on its own",
          'autoCycle=enabled;' in plat and
          "WiFi lifecycle test armed: automatic disconnect in 120 s" in plat and
          "WiFi lifecycle test RUNNING: automatic disconnect" in plat and
          "WiFi lifecycle test PASS: reconnected BSSID" in plat and
          "WiFi lifecycle test FAIL: reconnect" in plat)

    dts = (ROOT / "dts" / "mondrian.dts").read_text(encoding="utf-8")
    wlan = re.search(r"\n\twlan \{(?P<body>[^}]*)\};", dts)
    check("the device tree carries the wlan node the daemon is limited to",
          bool(wlan) and
          'unixnu,adt-name = "wlan";' in wlan.group("body") and
          'device_type = "wlan";' in wlan.group("body") and
          '"marconi-wifi"' in wlan.group("body") and
          "reg =" not in wlan.group("body"),
          "found=%s" % bool(wlan))
    check("the interface hands every frame to the packet filter tap",
          "volatile bpf_tap_mode gBpfMode;" in net and
          "errno_t if_set_bpf_tap(ifnet_t, bpf_tap_mode mode, bpf_packet_func callback)" in net and
          "p.set_bpf_tap = if_set_bpf_tap;" in net and
          "if (tap && (gBpfMode & BPF_MODE_INPUT)) tap(gIf, m);" in net and
          "if (tap && (gBpfMode & BPF_MODE_OUTPUT)) tap(gIf, m);" in net and
          net.index("tap(gIf, m); }") < net.index("mbuf_pkthdr_setheader(m, mbuf_data(m));"))
    check("the daemon's property list and flags are accepted",
          "kProperty = 383, kFlagA = 470, kFlagB = 471," in net and
          'log(6, "wifi-net: property list %.200s", d ? d : reinterpret_cast<char *>(buf + 8));' in net and
          "case kFlagA: case kFlagB: return 0;" in net)
    check("the current network is answered from the link that exists",
          "Joined by a join that did not scan first" in net and
          "b.caps = static_cast<uint16_t>(0x0001 | (gKeyed ? 0x0010 : 0));" in net)
    check("a refused request names its value and its first bytes",
          "void log_unhandled(bool set, int type, const apple80211req &rq, bool kernel)" in net and
          'log(6, "wifi-net: refused %s %d val %d len %u%s%s"' in net and
          "default: log_unhandled(true, type, rq, kernel); return EOPNOTSUPP;" in net and
          "default: log_unhandled(false, type, rq, kernel); return EOPNOTSUPP;" in net)
    check("every scan prints its request and its per-band table",
          'log(6, "wifi-net: scan request type %d len %u val %d ssid %u channels %u type %u", type, rq.req_len, rq.req_val, ssidLength, frequencies, scanType);' in net and
          'log(6, "wifi-net: scan table %u %d BSS: 2.4 GHz %u, 5 GHz %u, 6 GHz %u, hidden %u"' in net and
          'log(6, "wifi-net: scan result end after serving %u of %d records", gScanServed, count);' in net and
          net.index("log_scan_table();") < net.index("pong_wifi_notification event={NotifyScan"))
    check("the first scans list every record with its age and BSSID",
          'log(6, "wifi-net: bss %d/%d %u MHz %d dBm age %u bssid %02x:%02x:%02x:%02x:%02x:%02x ie %u cap %04x cc %c%c %.*s"' in net and
          "if (b.ie[o] == 7 && b.ie[o + 1] >= 2) { cc[0]" in net and
          "if (tables > 3) return;" in net)
    check("the scan log says how many records the daemon read",
          "unsigned gScanCursor, gScanning, gScanServed;" in net and
          "gScanCursor++; ++gScanServed; fill_result(out.res, b,rq.req_len);" in net and
          'log(6, "wifi-net: scan result served %u of %d: %u MHz, %d dBm, %.*s"' in net and
          "gScanCursor = 0; gScanServed = 0; return EIO;" in net)
    check("the supported channel list reports both bands",
          'log(6, "wifi-net: supported channels %u: 2.4 GHz %u, 5/6 GHz %u", n, lo, hi);' in net and
          'log(6, "wifi-net: channel %u: number %u flags 0x%x", frequencies[i], out.chans.list[i].channel, out.chans.list[i].flags);' in net)
    check("the scan list is frozen when a sweep completes and sorted strongest first",
          "nw_bss_info gSnap[64]; unsigned gSnapCount;" in net and
          "gSnap[at - 1].signal_dbm < b.signal_dbm" in net and
          net.index("freeze_scan_list();") < net.index("log_scan_table();") and
          "gSnapCount ? static_cast<int>(gSnapCount) : nw_wifi_bss_count()" in net)
    check("a served 5 GHz record prints the words the daemon sees",
          "const uint32_t *wds = reinterpret_cast<const uint32_t *>(&out.res);" in net and
          'log(6, "wifi-net: 5ghz %u words %08x %08x' in net)
    check("the daemon's scan filter and every served record are in the log",
          'log(6, "wifi-net: scan request prefix %08x %08x %08x %08x"' in net and
          "if (count <= 40 || gScanServed <= 3 || gScanServed % 8 == 0)" in net and
          'log(6, "wifi-net: 5ghz %u ie %02x%02x%02x%02x%02x%02x%02x%02x' in net)
    check("every scan record prints its element inventory",
          'log(6, "wifi-net: ies %02x:%02x:%02x:%02x:%02x:%02x ssid %u rates %u dsss %u cc %u rsn %u@%u ht %u ht40 %u vht %u vw %u he %u"' in net and
          "vw = (cap >> 2) & 3u;" in net and
          "case 255: if (len >= 1 && b.ie[o + 2] == 35) he = 1; break;" in net)
    check("a scan record prints its element ids and RSN bytes",
          'log(6, "wifi-net: ie-list %02x:%02x:%02x:%02x:%02x:%02x %s"' in net and
          'snprintf(ids + at, sizeof ids - at, "%s%u/%u"' in net and
          'log(6, "wifi-net: rsn %02x:%02x:%02x:%02x:%02x:%02x %u bytes %s"' in net and
          "const unsigned rn = rsn < 24 ? rsn : 24;" in net)
    check("the production record path serves every element the access point sent",
          "if (o + 2 + len > b.ie_len) break;" in net and
          "drop_scan_element" not in net and
          '"wifi-net: scan record tail %u of %u bytes is an incomplete element and is not served"' in net and
          "synthetic copy" not in net and "K60A" not in net and "withheld" not in net and
          "memmove(&gSnap[" not in net)
    check("every rssi and noise query logs the value it answers with",
          "const int32_t dbm = type == kRssi ? static_cast<int32_t>(st.signal_dbm) : -95;" in net and
          '"wifi-net: %s query -> %d dBm (link state %d)"' in net)
    abi_hdr = (ROOT / "drivers" / "PongWifi" / "PongWifiAbi.h").read_text(encoding="utf-8")
    check("one scan record serves the 24A446 and 22H374 extents",
          "PONG_SCAN_RECORD_24A446 0x8e8u" in abi_hdr and
          "PONG_SCAN_ELEMENTS_BYTES 2048u" in abi_hdr and
          "uint8_t filler[PONG_SCAN_TIMESTAMP_OFFSET - PONG_SCAN_ELEMENTS_OFFSET - PONG_SCAN_ELEMENTS_BYTES];" in net and
          "const uint32_t room = pong_scan_elements_room(request_bytes ? request_bytes : PONG_SCAN_RECORD_24A446);" in net and
          "scan_result24" not in net and
          "return copy_out(rq, &out.res, sizeof(out.res), kernel);" in net)
    check("the power answer follows the station state",
          "(gPower && st.state != NW_STA_OFF) ? 1 : 0" in net)
    check("a 24A446 power switch reaches the station's own power path",
          "if (gModern27Client) { nw_wifi_power(gPower ? 1 : 0); pong_wifi_wake(); }" in net)
    check("the current-network answer carries the live signal",
          net.count("out.res.rssi = st.signal_dbm;") == 2 and net.count("out.res.snr = st.signal_dbm > -95") == 2)
    check("the rate query reports the cached peer rate",
          "st.state == NW_STA_UP ? st.tx_rate_100kbps / 10 : 0" in net)
    check("a record is stamped when it is handed out, from the age the station measures",
          "const uint64_t now_ns = scan_clock_ns();" in net and
          "const uint64_t age_ns = uint64_t(b.age_ms) * 1000000ull;" in net and
          "record.timestamp_ns = now_ns > age_ns ? now_ns - age_ns : 0;" in net and
          "sampled_ns" not in net)
    check("the newer daemon's auth encoding is accepted and answered",
          "gModern27Client ? 0x10 : 0x8" in net and "rq.req_len == PONG_SCAN_MULTIPLE_BYTES" in net and
          "a.auth_upper!=8 && a.auth_upper!=0x10" in net)
    check("a join answers pending until the station finishes, and the newer daemon's credentials are read as the reference does",
          "kAssocPending = 0" in net and
          "gAssocResult = kAssocPending; gJoinPending = true; gLinkSuppressed = false;" in net and
          "gUserJoin = true; gAssocModern27 = modern27;" in net and
          "modern27 && a.key_length && !((a.key_cipher == 6 && a.key_length == 32)" in net and
          "if (r) { gAssocResult = kAssocFailed; gJoinPending = false; }" in net)
    check("an explicit disconnect hides the link and answers a join that was waiting",
          "void visible_status(nw_wifi_status &st)" in net and
          "if (!gPower || gLinkSuppressed) {" in net and
          "void post_link_down(bool involuntary, int reason)" in net and
          "if (gJoinPending) {" in net and
          "post_event(kEvSsidChanged, nullptr, 0);" in net and
          "gLinkSuppressed = true; gAssocResult = kAssocFailed; gJoinPending = false;" in net and
          "if (gLinkSuppressed) { log(6, \"wifi-net: link lost during an explicit disconnect: reason %d\", reason); return; }" in net)
    check("a completion without a link and a lost link are reported as the reference does",
          "if (result == NW_RES_OK && status.state != NW_STA_UP) {" in net and
          "gAssocResult=kAssocFailed;gJoinPending=false;" in net and
          "post_event(kEvSsidChanged,nullptr,0);post_event(kEvBssidChanged,nullptr,0);break;" in net and
          "void post_association_result()" in net and
          "memcpy(done.attempts, current.bssid, 6);" in net)
    check("a join drains a link that is already up before asking the station",
          "int drain_disconnect()" in net and
          "for (unsigned waited = 0; waited < 2000; waited += 10)" in net and
          'log(4, "wifi-net: disconnect did not drain within 2000 ms");' in net and
          "if (drain_disconnect()) { memset(&a,0,sizeof(a)); gAssocResult = kAssocFailed; return ETIMEDOUT; }" in net)
    check("the abort-scan request is accepted instead of falling through",
          "PONG_REQUEST_ABORT_SCAN 382u" in abi_hdr and "kAbortScan = PONG_REQUEST_ABORT_SCAN" in net and
          "case kAbortScan: return 0;" in net)
    policy_hdr = (ROOT / "drivers" / "PongWifi" / "PongWifiScanPolicy.h").read_text(encoding="utf-8")
    check("the scan policy keeps the radio on channel during a join and drops stale records",
          '#include "PongWifiScanPolicy.h"' in net and
          "pong_scan_on_air(&gScanAir, link, link_ms" in net and
          "pong_scan_air_mark(&gScanAir, mhz, frequencies, now_ms);" in net and
          "pong_scan_held_stale(b.age_ms)" in net and
          "gLinkUpMs = result == NW_RES_OK ? scan_clock_ms() : 0;" in net and
          "PONG_SCAN_HELD_MS 60000u" in policy_hdr and
          "PONG_SCAN_LINK_SETTLE_MS 15000u" in policy_hdr and
          "PONG_SCAN_RESCAN_MS 20000u" in policy_hdr)
    check("request 10 takes its scan type from the same place the reference does",
          "PONG_SCAN_ONE_TYPE 0x34u" in abi_hdr and
          "memcpy(&scanType, out.raw + PONG_SCAN_ONE_TYPE, 4);" in net)
    check("a 24A446 scan request is parsed for its names, type and channels",
          "if (type == kScanReqMultiple) {" in net and
          "pong_scan_multiple_parse(out.raw, held, &scanType, &ssid, &ssidLength)" in net and
          "PONG_SCAN_MULTIPLE_CHANNEL_COUNT" in net and
          "const bool asked = frequencies != 0 && nw_wifi_scan_frequencies != nullptr;" in net and
          "PONG_WIFI_CAP_NAMED_SCAN 22u" in abi_hdr and
          "PONG_WIFI_CAP_SCAN_DONE_EVENT 46u" in abi_hdr and
          "if (rq.req_len <= PONG_WIFI_CAPS_BYTES)" in net)
    check("the 24A446 association request and completion event are decoded",
          "const bool modern27=rq.req_len==PONG_ASSOC_REQUEST_24A446;" in net and
          "gAssocModern27 = modern27;" in net and
          "pong_assoc_event27 done{}" in net and
          "post_event(kEvAssocDone, &done, sizeof done);" in net and
          "uint8_t data[16 + sizeof(pong_assoc_event27)];" in net and
          "sizeof(struct pong_assoc_event27) == 540" in abi_hdr)
    he_src = (ROOT / "drivers" / "PongWifi" / "ath11k" / "pong_he.c").read_text(encoding="utf-8")
    he_hdr = (ROOT / "drivers" / "PongWifi" / "ath11k" / "pong_he.h").read_text(encoding="utf-8")
    check("the station announces an HE capability element",
          "static u8 g_he_ie[2 + 1 + PONG_HE_CAP_FIXED + PONG_HE_MCS_MAX + PONG_HE_PPE_MAX];" in text and
          "if (g_he_ie_len) skb_put_data(skb, g_he_ie, g_he_ie_len);" in text and
          "k60 station: association request HT %u VHT %u HE %u bytes" in text)
    check("the peer entry carries the access point's narrowed HE capability",
          "struct ieee80211_sta_he_cap *h = &sta->deflink.he_cap;" in text and
          "pong_he_narrow(&own, &he_ap);" in text and
          "g_vif->bss_conf.he_oper.params = g_he_oper.params;" in text)
    check("the HE codec is a separate host-tested unit",
          "jobs += [(ROOT / 'drivers/PongWifi/ath11k/pong_he.c', out / 'pong_he.o', [])]" in text and
          "#define PONG_HE_ELEM_ID 255" in he_hdr and
          "peer->mcs[0] = intersect16(own->mcs[1], peer->mcs[0]);" in he_src and
          (ROOT / "scripts" / "tests" / "pong-he-selftest.c").is_file())

    net_src = NET.read_text(encoding="utf-8")
    check("the SAE probe is armed only by a boot argument",
          'extern "C" void nw_wifi_sae_probe(int group) __attribute__((weak_import));' in net_src and
          'PE_parse_boot_argn("sae", &sae, sizeof(sae))' in net_src and
          "jobs += [(ROOT / 'drivers/PongWifi/ath11k/pong_sae.c', out / 'pong_sae.o', [])]" in text and
          (ROOT / "scripts" / "tests" / "test-pong-sae.py").is_file())

    check("the framework ABI shapes are host-tested",
          (ROOT / "drivers" / "PongWifi" / "PongWifiAbi.h").is_file() and
          (ROOT / "scripts" / "tests" / "test-pong-abi.py").is_file() and
          (ROOT / "scripts" / "tests" / "pong-abi-selftest.c").is_file() and
          "a 24A446 scan request is parsed for its names, type and channels" in (ROOT / "scripts" / "tests" / "test-wifi-sbl-mission.py").read_text(encoding="utf-8"))

    native_src = (ROOT / "scripts" / "build-k60-wifi-native.py").read_text(encoding="utf-8")
    check("both builds carry a 2048-byte element array and the station clamp follows it",
          "uint8_t ie[2048];" in text and "uint8_t ie[2048];" in native_src and
          "raise RuntimeError('shared ABI element array differs')" in text and
          "raise RuntimeError('shared ABI element array differs')" in native_src and
          "sta.replace('#define IE_MAX 384', '#define IE_MAX 2048')" in text and
          "'-I', str(abi), '-include', 'PongCompat.h'," in text and
          "'-I'+str(abi),'-I'+str(shared/'drivers/Ath12kWifi/include')" in native_src)

    check("the station build records the element width the kext build checks",
          "(abi / 'nw_abi.stamp').write_text('ie_bytes=2048" in text and
          "hashlib.sha256((abi / 'nw_abi.h').read_bytes())" in text and
          "stamp=a.ath11k.parent/'abi'/'nw_abi.stamp'" in native_src and
          "but this build carries 2048: rebuild the station (P-230)" in native_src)
    check("a requested stop quiesces the interface and releases the station",
          'extern "C" void pong_wifi_station_stop(void);' in net_src and
          'extern "C" void pong_wifi_net_stop(void) {' in net_src and
          'pong_wifi_net_stop(); pong_wifi_station_stop();' in net_src and
          '__builtin_strncmp(q, "pong-wifi-stop", 14) == 0' in net_src and
          ' volatile uint32_t stopRequested;' in platform and
          'bool cleanStop=false;' in platform and
          'if(__atomic_load_n(&stopRequested,__ATOMIC_ACQUIRE)){cleanStop=true;break;}' in platform and
          'if(cleanStop){nw_wifi_stop();' in platform and
          'extern "C" void pong_wifi_station_stop(void) {' in platform)

    check("events are installed before the station starts",
          platform.index('if(!pong_wifi_net_prepare())') < platform.index('nw_wifi_start(&platform,&board)') and
          'nw_wifi_set_events(&gEvents)' in net_src)

    check("the peer signal refresh reaches the daemon as a link change",
          'void on_link_update(const nw_wifi_status *status) {' in net_src and
          'gEvents = { on_scan_done, on_connect_done, on_link_lost, on_rx, nullptr, nullptr, on_link_update }' in net_src and
          'event.rssi = status->signal_dbm;' in net_src and
          'post_event(kEvLinkChanged, &event, sizeof event);' in net_src)

    check("a 24A446 daemon reads events from two descriptors",
          'if (gModern27Client) {' in net_src and
          'msg.dv[0].data_length = sizeof name; msg.dv[0].data_ptr = name;' in net_src and
          'msg.dv[1].data_length = static_cast<uint32_t>(length); msg.dv[1].data_ptr = const_cast<void *>(payload);' in net_src and
          net_src.count('if (rq.req_len == PONG_SCAN_RECORD_24A446) gModern27Client = true;') == 2)
    check("a 24A446 event is logged with its size and result",
          'wifi-net: event %u bytes %u -> %d' in net_src and
          'if (code != kEvScanDone) log(6, "wifi-net: event %u bytes %u -> %d"' in net_src)
    check("the link settle window starts where the reference starts it",
          "gLinkUpMs = up ? scan_clock_ms() : 0;" in net_src)

    print("summary: %d failure(s)" % len(FAILS))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
