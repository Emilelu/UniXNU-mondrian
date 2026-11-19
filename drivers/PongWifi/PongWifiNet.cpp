// SPDX-License-Identifier: BSD-2-Clause-Patent
// The WiFi module's network side: the Ethernet interface the system routes through, the registry entries by which the wireless daemon and
// the network configuration find a wireless interface, and the Apple80211 requests (ioctls on that interface) the daemon uses to scan,
// join and read state. Nothing here talks to the radio: it calls the module's station interface (nw_abi.h) and turns what it answers into
// the structures the system's wireless framework reads.
//
// Layouts below are those the framework reads and writes; where a field's meaning is not known it is left zero. Every request is written
// to the log (type, direction, length) and a request that is not handled is refused, so which ones the framework needs shows in the log.
#include <IOKit/IOLib.h>
#include <IOKit/IOKitKeys.h>
#include <IOKit/IOPlatformExpert.h>
#include <IOKit/IOService.h>
#include <IOKit/IORegistryEntry.h>
#include <IOKit/IOUserClient.h>
#include <libkern/OSAtomic.h>
#include <libkern/c++/OSData.h>
#include <libkern/c++/OSNumber.h>
#include <libkern/c++/OSSerialize.h>
#include <sys/kern_event.h>
#include <sys/socket.h>
#include <sys/sockio.h>
#include <net/ethernet.h>
#include "PongWifiAbi.h"
#include "PongWifiScanPolicy.h"
#include <net/if.h>
#include <net/if_media.h>
#include <net/if_ether.h>
#include <net/kpi_interface.h>
extern "C" {
#include <net/bpf.h>
}
#include <net/if_types.h>
#include <netinet/in.h>
#include <sys/mbuf.h>
#include <kern/locks.h>
#include <kern/thread.h>
#include <kern/thread_call.h>
#include <sys/systm.h>
#include <sys/proc.h>
#include <stdarg.h>
#include "nw_abi.h"

extern "C" void pong_wifi_net_stop(void);
extern "C" void pong_wifi_station_stop(void);
#include "PongWifiLease.h"
#include "PongWifiNotify.h"
#include <pexpert/pexpert.h>
#include <kern/clock.h>

extern "C" bool pong_wifi_test_reconnect(void);
extern "C" unsigned nw_wifi_channel_list(unsigned *, unsigned);
extern "C" int nw_wifi_rssi_limits(int *,int *);
// WPA3 feasibility: the station exports this only when the builder injected the probe, so the call is weak.
extern "C" void nw_wifi_sae_probe(int group) __attribute__((weak_import));
// 24A446 scans name the channels they want; a station archive without the entry (the 22H374
// line) leaves the scan on every channel, which is what the framework did before.
extern "C" int nw_wifi_scan_frequencies(const uint8_t *ssid, size_t len, const uint32_t *mhz, size_t count)
    __attribute__((weak_import));
extern "C" volatile uint64_t pong_wifi_progress[3];
static bool gProgressDiagnostic;
extern "C" void native_wifi_logf(int level, const char *fmt, ...);
extern "C" void pong_wifi_wake(void);   // WifiProbe.cpp: the WiFi thread sends the queued frame now

#define SIOCSA80211 0x802869c8UL   // _IOW('i', 200, struct apple80211req)
#define SIOCGA80211 0xc02869c9UL   // _IOWR('i', 201, struct apple80211req)

// (the header declares it without C linkage; the symbol is the C one)
extern "C" int pong_kev_post(struct kev_msg *) __asm__("_kev_post_msg");

namespace {

struct apple80211req {
  char req_if_name[16];
  int32_t req_type;
  int32_t req_val;
  uint32_t req_len;
  user_addr_t req_data __attribute__((aligned(8)));
};

// request types
enum {
  kSsid = 1, kAuthType = 2, kCipherKey = 3, kChannel = 4, kPowerSave = 5, kTxPower = 7, kRate = 8, kBssid = 9, kScanReq = 10, kScanResult = 11,
  kCardCaps = 12, kState = 13, kPhyMode = 14, kOpMode = 15, kRssi = 16, kNoise = 17, kPower = 19, kAssociate = 20, kAssociateResult = 21,
  kDisassociate = 22, kSupportedChannels = 27, kLocale = 28, kDeauth = 29, kDriverVersion = 43, kHardwareVersion = 44, kCountryCode = 51,
  kRadioInfo = 54, kWowEnabled = 70, kVirtualRole = 96, kVirtualParent = 97, kScanReqMultiple = 86, kScanCacheClear = 90, kCurrentNetwork = 103, kRssiBounds = 106, kChannelsInfo = 207, kHwSupportedChannels = 254,
  kAbortScan = PONG_REQUEST_ABORT_SCAN, kProperty = 383, kFlagA = 470, kFlagB = 471,
};
// events
enum { kEvPowerChanged = 1, kEvSsidChanged = 2, kEvBssidChanged = 3, kEvLinkChanged = 4, kEvAssocDone = 9, kEvScanDone = 10, kEvRsnHandshakeDone = 20 };
// results of an association, as the framework numbers them
enum { kAssocPending = 0, kAssocOk = 1, kAssocFailed = 2, kAssocTimeout = 9, kAssocBadKey = 21 };

struct channel { uint32_t version, channel, flags; };
struct channels_list { uint32_t version, count; channel list[401]; uint32_t unused; };           // 4824 bytes
struct scan_result {                                                                              // 0x8e8 bytes
  uint32_t version; channel ch; uint16_t noise_known; int16_t noise, snr, rssi; uint16_t beacon_interval, capability; uint8_t bssid[6];
  uint8_t rate_count, unused0; uint32_t rates[15]; uint8_t ssid_length, ssid[32], unused1[3]; uint32_t age_ms; uint8_t flags, unused2;
  uint16_t elements_length; uint8_t elements[PONG_SCAN_ELEMENTS_BYTES];
  uint8_t filler[PONG_SCAN_TIMESTAMP_OFFSET - PONG_SCAN_ELEMENTS_OFFSET - PONG_SCAN_ELEMENTS_BYTES];
  uint64_t timestamp_ns;
  uint8_t tail[PONG_SCAN_RECORD_24A446 - PONG_SCAN_TIMESTAMP_OFFSET - 8];
};
// One record serves both framework generations (drivers/PongWifi/PongWifiAbi.h): the prefix through
// 0x8c is the same in 22H374's 1164-byte result and 24A446's 0x8e8-byte one. The element count
// follows the request (pong_scan_elements_room) and the timestamp sits past 68 filler bytes at
// 0x8d0, so a client that asked for 1164 bytes reads exactly the prefix it knows.
static_assert(sizeof(scan_result)==PONG_SCAN_RECORD_24A446 &&
  __builtin_offsetof(scan_result,elements)==PONG_SCAN_ELEMENTS_OFFSET &&
  __builtin_offsetof(scan_result,timestamp_ns)==PONG_SCAN_TIMESTAMP_OFFSET,"24A446 scan record ABI");
struct assoc_request {                                                                            // 592 bytes
  uint32_t version; uint16_t mode, auth_lower, auth_upper, unused0; uint32_t ssid_length; uint8_t ssid[32]; uint8_t bssid[6], unused1[2];
  uint32_t key_version, key_length, key_cipher; uint16_t key_flags, key_index; uint8_t key[64]; uint8_t rest[0x250 - 0x88];
};
// Native 22H374 IO80211 __performAssociation sends 0x384 bytes. Unlike
// the older 0x250 layout its lower/upper authentication fields are 32-bit.
// Decoding it as the legacy layout reads auth_upper as the SSID length.
struct assoc_request24 {
  uint32_t version; uint16_t mode, unused0; uint32_t auth_lower, auth_upper;
  uint32_t ssid_length; uint8_t ssid[32], bssid[6], unused1[2];
  uint32_t key_version, key_length, key_cipher; uint16_t key_flags, key_index;
  uint8_t key[64], rest[0x384-0x8c];
};
static_assert(sizeof(assoc_request24)==0x384 &&
  __builtin_offsetof(assoc_request24,ssid_length)==0x10 &&
  __builtin_offsetof(assoc_request24,bssid)==0x34 &&
  __builtin_offsetof(assoc_request24,key)==0x4c,"22H374 association ABI");
// 24A446 sends 0x290 bytes with the same field offsets; the driver reads only PONG_ASSOC_FIELDS_BYTES
// (through key[64]) and ignores the trailing remainder, so one struct decodes both generations.
static_assert(__builtin_offsetof(assoc_request24,key)+64==PONG_ASSOC_FIELDS_BYTES &&
  PONG_ASSOC_REQUEST_24A446==0x290,"24A446 association ABI");
struct link_event { uint8_t down, unused0[3]; int32_t rssi; uint16_t snr, noise; uint8_t unused1[4]; uint8_t involuntary, unused2[3]; uint32_t reason, subreason; uint8_t unused3[4]; };
static_assert(__builtin_offsetof(scan_result, ssid_length) == 0x60 && __builtin_offsetof(scan_result, age_ms) == 0x84,
              "scan result field offsets");
static_assert(sizeof(assoc_request) == 592 && __builtin_offsetof(assoc_request, key) == 0x48, "association layout");
// These two structs must agree field for field with the host-tested shapes in PongWifiAbi.h;
// a silent mismatch would decode a 24A446 request with the wrong offsets and nothing else would fail.
static_assert(__builtin_offsetof(assoc_request,ssid_length)==__builtin_offsetof(pong_assoc_request_legacy,network)+__builtin_offsetof(struct pong_assoc_parameters,ssid_length) &&
  __builtin_offsetof(assoc_request,bssid)==__builtin_offsetof(pong_assoc_request_legacy,network)+__builtin_offsetof(struct pong_assoc_parameters,bssid) &&
  __builtin_offsetof(assoc_request,key)==__builtin_offsetof(pong_assoc_request_legacy,network)+__builtin_offsetof(struct pong_assoc_parameters,key),"legacy association fields match the ABI header");
static_assert(__builtin_offsetof(assoc_request24,ssid_length)==__builtin_offsetof(pong_assoc_request_24a446,network)+__builtin_offsetof(struct pong_assoc_parameters,ssid_length) &&
  __builtin_offsetof(assoc_request24,bssid)==__builtin_offsetof(pong_assoc_request_24a446,network)+__builtin_offsetof(struct pong_assoc_parameters,bssid) &&
  __builtin_offsetof(assoc_request24,key)==__builtin_offsetof(pong_assoc_request_24a446,network)+__builtin_offsetof(struct pong_assoc_parameters,key),"24A446 association fields match the ABI header");
static_assert(sizeof(channels_list) == 4824, "channel list layout");
static_assert(sizeof(link_event) == 32, "link event layout");

ifnet_t gIf;
uint8_t gMac[6];
lck_grp_t *gGrp;
lck_mtx_t *gLock;
bool gCycleTest;
struct pong_wifi_lease_tracker gLease;

uint64_t lease_clock() {
  uint64_t ns = 0;
  absolutetime_to_nanoseconds(mach_continuous_time(), &ns);
  return ns / 1000000000ull;
}

bool gPower = true;
bool gFailed;
bool gKeyed;   // the last join used a passphrase
uint32_t gRxFrames, gRxErrors; int gRxLastError;
uint32_t gRxNoBuffer, gRxChains, gRxLongest;   // frames dropped for want of a buffer, frames that took a chain, the longest frame
struct { unsigned count, kicks, cleared, longest; bool kicked; } gStall;   // input thread stalls (check_input)   // frames handed to the stack, refused ones and the last refusal
int gAssocResult = kAssocPending;
bool gAssocModern27;   // the last join arrived through the 0x290-byte 24A446 request
bool gModern27Client;  // a 24A446-sized request arrived, so the daemon speaks the newer auth encoding
bool gJoinPending;     // a join request is queued in the station and its completion has not arrived
bool gLinkSuppressed;  // an explicit disconnect hides the link until a new join clears it
unsigned gScanCursor, gScanning, gScanServed;
nw_bss_info gSnap[64]; unsigned gSnapCount;   // the scan list frozen when a sweep completes, strongest first
// The channels the radio last visited and when the link came up: the reference port's scan policy
// (PongWifiScanPolicy.h) decides from these whether a request may take the radio off channel.
pong_scan_air gScanAir;
uint64_t gSnapAtNs;      // when the frozen list was taken
uint64_t gLinkUpMs;      // when the link came up, 0 while it is down
uint64_t scan_clock_ns();
static inline uint64_t scan_clock_ms() { return scan_clock_ns() / 1000000ull; }
// After an explicit disconnect the station's snapshot keeps reporting the old network until the firmware
// teardown finishes; the reference port hides it (visible_status) so the daemon does not read a link that
// the user has already left. A new join clears the suppression.
void visible_status(nw_wifi_status &st) {
  nw_wifi_status_get(&st);
  if (!gPower || gLinkSuppressed) {
    st.state = NW_STA_IDLE; st.ssid_len = 0; memset(st.ssid, 0, sizeof st.ssid);
    memset(st.bssid, 0, sizeof st.bssid); st.freq_mhz = 0; st.signal_dbm = 0;
  }
}
thread_call_t gNotifications;
pong_wifi_notification_queue gNotificationQueue;
enum { NotifyControl=1, NotifyScan, NotifyAssociate, NotifyLost, NotifyFailed };
enum { NotifyPower=1, NotifyLinkDown=2 };
bool gUserJoin;   // the wireless daemon joined, left or switched the radio itself: the unattended test join steps aside
uint32_t gLogged[256 / 32];

void log(int level, const char *fmt, ...) __attribute__((format(printf, 2, 3)));
void log(int level, const char *fmt, ...) {
  char line[160]; va_list ap; va_start(ap, fmt); vsnprintf(line, sizeof line, fmt, ap); va_end(ap);
  native_wifi_logf(level, "%s", line);
}

// The packet filter (bpf) tap. The address configuration's ARP monitor reads the router's replies through /dev/bpf, and an interface that is
// not a stock Ethernet driver has to hand every frame it receives and sends to the tap itself. Without it the interface stays busy for a
// minute after the link comes up and the Settings pane never stops spinning (evb10 run t36 against run t37).
volatile bpf_tap_mode gBpfMode;
bpf_packet_func volatile gBpfTap;
errno_t if_set_bpf_tap(ifnet_t, bpf_tap_mode mode, bpf_packet_func callback) {
  gBpfTap = mode ? callback : nullptr; gBpfMode = mode;
  static unsigned shown; if (shown++ < 6) log(6, "wifi-net: packet filter tap mode %u", mode);
  return 0;
}

// ---- events to the framework: class IEEE 802.11 (6), subclass 1 ----
// Two shapes, chosen by the daemon generation. 22H374 reads the interface name and the payload out of
// one descriptor (name first); 24A446 reads them from two (name, then payload). The reference port made
// that change in the same commit that added the 540-byte association event, and the older shape is the
// one this device's pane was proven with, so the generation decides rather than a blanket switch.
void post_event(uint32_t code, const void *payload, size_t length) {
  struct kev_msg msg; memset(&msg, 0, sizeof msg);
  msg.vendor_code = KEV_VENDOR_APPLE; msg.kev_class = 6; msg.kev_subclass = 1; msg.event_code = code;
  if (gModern27Client) {
    char name[16] = "en0";
    msg.dv[0].data_length = sizeof name; msg.dv[0].data_ptr = name;
    msg.dv[1].data_length = static_cast<uint32_t>(length); msg.dv[1].data_ptr = const_cast<void *>(payload);
    const int error = pong_kev_post(&msg);
    if (code != kEvScanDone) log(6, "wifi-net: event %u bytes %u -> %d", code, static_cast<unsigned>(length), error);
    return;
  }
  uint8_t data[16 + sizeof(pong_assoc_event27)]; if (length > sizeof data - 16) length = sizeof data - 16;
  memset(data, 0, 16); snprintf(reinterpret_cast<char *>(data), 16, "en0"); if (length) memcpy(data + 16, payload, length);
  msg.dv[0].data_length = static_cast<uint32_t>(16 + length); msg.dv[0].data_ptr = data;
  pong_kev_post(&msg);
}
// link state for the network configuration: the interface's flags and the stack's own link events
void post_link(bool up) {
  gLinkUpMs = up ? scan_clock_ms() : 0;
  if (!gIf) return;
  lck_mtx_lock(gLock);
  if (gLease.up != up) pong_wifi_lease_link(&gLease, up);
  lck_mtx_unlock(gLock);
  ifnet_set_flags(gIf, up ? IFF_RUNNING : 0, IFF_RUNNING);
  struct { struct net_event_data data; } payload; memset(&payload, 0, sizeof payload);
  payload.data.if_family = IFNET_FAMILY_ETHERNET; payload.data.if_unit = 0; snprintf(payload.data.if_name, sizeof payload.data.if_name, "en");
  struct kev_msg msg; memset(&msg, 0, sizeof msg);
  msg.vendor_code = KEV_VENDOR_APPLE; msg.kev_class = KEV_NETWORK_CLASS; msg.kev_subclass = KEV_DL_SUBCLASS; msg.event_code = up ? KEV_DL_LINK_ON : KEV_DL_LINK_OFF;
  msg.dv[0].data_length = sizeof payload; msg.dv[0].data_ptr = &payload;
  pong_kev_post(&msg);
}
// A requested disconnect is announced now, not when the station finishes its firmware teardown (the
// reference port's post_link_down): the link change carries involuntary=0, and the name events follow.
void post_link_down(bool involuntary, int reason) {
  post_link(false);
  link_event ev{}; ev.down = 1; ev.involuntary = involuntary ? 1 : 0; ev.reason = static_cast<uint32_t>(reason);
  post_event(kEvLinkChanged, &ev, sizeof ev);
  post_event(kEvSsidChanged, nullptr, 0);
  post_event(kEvBssidChanged, nullptr, 0);
}
// The association completion the daemon reads: 24A446 takes the 540-byte event, with the peer's address in
// the first attempt slot as the reference port fills it, and the older daemon the empty payload.
void post_association_result() {
  if (!gAssocModern27) { post_event(kEvAssocDone, nullptr, 0); return; }
  pong_assoc_event27 done{}; done.result = static_cast<uint32_t>(gAssocResult); done.has_result = 1;
  nw_wifi_status current; nw_wifi_status_get(&current);
  memcpy(done.attempts, current.bssid, 6);   // the first attempt slot, 52 bytes in the 540-byte event
  post_event(kEvAssocDone, &done, sizeof done);
}

// Socket/ifnet delivery can synchronously cause output or interface queries.
// The cooperative firmware dispatcher must remain free to drain that work.
// Queue bounded FIFO transitions under gLock, then deliver outside both the
// network lock and dispatcher context. Never coalesce a real down/up edge.
void queue_notification_locked(pong_wifi_notification event) {
  if(__atomic_load_n(&gFailed,__ATOMIC_ACQUIRE) && event.kind!=NotifyFailed)return;
  if(!pong_wifi_notification_push(&gNotificationQueue,event)) {
    log(3,"wifi-net: notification queue overflow; interface failed");
    __atomic_store_n(&gFailed,true,__ATOMIC_RELEASE);gPower=false;
    gAssocResult=kAssocFailed;gScanning=0;
    pong_wifi_notification_reset(&gNotificationQueue);
    pong_wifi_notification failure={NotifyFailed,1,0,0};
    pong_wifi_notification_push(&gNotificationQueue,failure);
  }
  thread_call_enter(gNotifications);
}
void deliver_notifications(thread_call_param_t,thread_call_param_t) {
  for(;;) {
    pong_wifi_notification event={};
    lck_mtx_lock(gLock);
    bool available=pong_wifi_notification_pop(&gNotificationQueue,&event);
    lck_mtx_unlock(gLock);
    if(!available)return;
    switch(event.kind) {
    case NotifyControl:
      if(event.result&NotifyLinkDown) {
        // An explicit disconnect while a join waits leaves the daemon waiting for an association result
        // the station will never post (the join it queued was replaced), so the failure is posted here.
        post_link_down(false, 0);
        if (gJoinPending) { gJoinPending = false; post_association_result(); }
      }
      if(event.result&NotifyPower)post_event(kEvPowerChanged,nullptr,0);
      break;
    case NotifyScan:post_event(kEvScanDone,nullptr,0);break;
    case NotifyAssociate:
      if(event.result==NW_RES_OK)post_link(true);
      // 24A446's assoc-done event is 540 bytes: the framework reads result at 0x214 and has_result
      // at 0x218 to decide whether the join succeeded, so the payload cannot be the legacy empty one.
      post_association_result();
      if(event.result==NW_RES_OK) {
        post_event(kEvSsidChanged,nullptr,0);post_event(kEvBssidChanged,nullptr,0);
        link_event link={};link.rssi=event.rssi;link.noise=static_cast<uint16_t>(-95);link.snr=static_cast<uint16_t>(event.rssi+95);
        post_event(kEvLinkChanged,&link,sizeof link);
        if(event.keyed)post_event(kEvRsnHandshakeDone,nullptr,0);
      }
      log(6,"wifi-net: association notifications delivered result %d",event.result);
      break;
    case NotifyLost: {
      post_link(false);link_event link={};link.down=1;link.involuntary=1;link.reason=static_cast<uint32_t>(event.result);
      post_event(kEvLinkChanged,&link,sizeof link);
      // The name events follow every link change the reference port reports, so the daemon drops the old
      // SSID/BSSID reading even when the loss was the access point's.
      post_event(kEvSsidChanged,nullptr,0);post_event(kEvBssidChanged,nullptr,0);break;
    }
    case NotifyFailed:
      post_link(false);
      if(event.result)post_event(kEvScanDone,nullptr,0);
      post_association_result();
      post_event(kEvPowerChanged,nullptr,0);break;
    }
  }
}
void notify_locked(unsigned events) {
  pong_wifi_notification event={NotifyControl,static_cast<int32_t>(events),0,0};
  queue_notification_locked(event);
}
// The daemon reads the list one record per call. A live table that gains or loses entries between two calls
// shifts the cursor and cuts its copy short (mission16: "served 32 of 33"), so a completed sweep is frozen.
void freeze_scan_list() {
  gSnapAtNs = scan_clock_ns();
  const int count = nw_wifi_bss_count(); gSnapCount = 0;
  for (int i = 0; i < count && gSnapCount < 64; i++) {
    nw_bss_info b; if (nw_wifi_bss_get(i, &b)) continue;
    unsigned at = gSnapCount;
    while (at && gSnap[at - 1].signal_dbm < b.signal_dbm) { gSnap[at] = gSnap[at - 1]; at--; }
    gSnap[at] = b; gSnapCount++;
  }
}
// The scan list counted by band. The Settings pane builds its list from these records, so a band that is
// missing here cannot appear there, and the strongest few per band say what the radio actually heard.
void log_scan_table() {
  const int count = nw_wifi_bss_count(); unsigned c24 = 0, c5 = 0, c6 = 0, hidden = 0;
  for (int i = 0; i < count; i++) {
    nw_bss_info b; if (nw_wifi_bss_get(i, &b)) continue;
    if (!b.ssid_len) { hidden++; continue; }
    if (b.freq_mhz < 3000) c24++; else if (b.freq_mhz < 5925) c5++; else c6++;
  }
  static unsigned tables; ++tables;
  log(6, "wifi-net: scan table %u %d BSS: 2.4 GHz %u, 5 GHz %u, 6 GHz %u, hidden %u", tables, count, c24, c5, c6, hidden);
  // The daemon keeps its own copy of this list, so a network that disappears between the two is rejected by the
  // daemon rather than missed by the radio. The first scans print every record with the fields a filter can use
  // (band, age, capability, element length) so the difference can be read off one console.
  if (tables > 3) return;
  for (int i = 0; i < count; i++) {
    nw_bss_info b; if (nw_wifi_bss_get(i, &b)) continue;
    // The 802.11d Country element: wifid tracks the advertised country per network and can reject a network whose
    // country differs from the local one, so the record dump must show which country each record carries.
    char cc[3] = { '-', '-', 0 };
    for (unsigned o = 0; o + 4 <= b.ie_len && o + 2 + b.ie[o + 1] <= b.ie_len; o += 2 + b.ie[o + 1])
      if (b.ie[o] == 7 && b.ie[o + 1] >= 2) { cc[0] = static_cast<char>(b.ie[o + 2]); cc[1] = static_cast<char>(b.ie[o + 3]); break; }
    log(6, "wifi-net: bss %d/%d %u MHz %d dBm age %u bssid %02x:%02x:%02x:%02x:%02x:%02x ie %u cap %04x cc %c%c %.*s",
        i, count, b.freq_mhz, b.signal_dbm, b.age_ms, b.bssid[0], b.bssid[1], b.bssid[2], b.bssid[3], b.bssid[4],
        b.bssid[5], b.ie_len, b.caps, cc[0], cc[1], b.ssid_len, reinterpret_cast<const char *>(b.ssid));
    // The element blob is what the daemon parses for security, rates and band capability, so a record it drops
    // despite being served differs here first. Print the inventory, the element-id list and the RSN bytes: the
    // 5 GHz record of this access point carries 384 bytes of elements against the 2.4 GHz record's 347, and only
    // the id list says which 34 bytes that is.
    unsigned ssid = 0, rates = 0, dsss = 0, cc_ie = 0, rsn = 0, rsn_at = 0, ht = 0, ht40 = 0, vht = 0, vw = 0, he = 0;
    for (unsigned o = 0; o + 2 <= b.ie_len && o + 2 + b.ie[o + 1] <= b.ie_len; o += 2 + b.ie[o + 1]) {
      const unsigned id = b.ie[o], len = b.ie[o + 1];
      switch (id) {
      case 0: ssid = len; break;
      case 1: rates = len; break;
      case 3: dsss = 1; break;
      case 7: cc_ie = 1; break;
      case 45: ht = 1; if (len > 1) ht40 = (b.ie[o + 2] >> 1) & 1u; break;
      case 48: rsn = len; rsn_at = o; break;
      case 191: vht = 1; if (len >= 4) { const unsigned cap = b.ie[o + 2] | (b.ie[o + 3] << 8); vw = (cap >> 2) & 3u; } break;
      case 255: if (len >= 1 && b.ie[o + 2] == 35) he = 1; break;
      }
    }
    log(6, "wifi-net: ies %02x:%02x:%02x:%02x:%02x:%02x ssid %u rates %u dsss %u cc %u rsn %u@%u ht %u ht40 %u vht %u vw %u he %u",
        b.bssid[0], b.bssid[1], b.bssid[2], b.bssid[3], b.bssid[4], b.bssid[5], ssid, rates, dsss, cc_ie, rsn, rsn_at,
        ht, ht40, vht, vw, he);
    char ids[240]; unsigned at = 0; ids[0] = 0;
    for (unsigned o = 0; o + 2 <= b.ie_len && o + 2 + b.ie[o + 1] <= b.ie_len; o += 2 + b.ie[o + 1]) {
      if (at + 10 >= sizeof ids) { at += static_cast<unsigned>(snprintf(ids + at, sizeof ids - at, " ...")); break; }
      at += static_cast<unsigned>(snprintf(ids + at, sizeof ids - at, "%s%u/%u", at ? " " : "", b.ie[o], b.ie[o + 1]));
    }
    log(6, "wifi-net: ie-list %02x:%02x:%02x:%02x:%02x:%02x %s", b.bssid[0], b.bssid[1], b.bssid[2], b.bssid[3],
        b.bssid[4], b.bssid[5], ids);
    if (rsn >= 8) {
      const uint8_t *r = b.ie + rsn_at + 2;
      char rh[80]; unsigned ro = 0; rh[0] = 0;
      const unsigned rn = rsn < 24 ? rsn : 24;
      for (unsigned x = 0; x < rn && ro + 3 < sizeof rh; x++)
        ro += static_cast<unsigned>(snprintf(rh + ro, sizeof rh - ro, "%02x", r[x]));
      log(6, "wifi-net: rsn %02x:%02x:%02x:%02x:%02x:%02x %u bytes %s",
          b.bssid[0], b.bssid[1], b.bssid[2], b.bssid[3], b.bssid[4], b.bssid[5], rsn, rh);
    }
  }
}
void on_scan_done() {
  freeze_scan_list();
  log_scan_table();
  lck_mtx_lock(gLock);gScanning=0;gScanCursor=0;
  pong_wifi_notification event={NotifyScan,0,0,0};queue_notification_locked(event);
  lck_mtx_unlock(gLock);
}
thread_call_t gCachedScan;
void cached_scan_done(thread_call_param_t,thread_call_param_t) { on_scan_done(); }
void on_connect_done(int result) {
  nw_wifi_status status={};nw_wifi_status_get(&status);
  lck_mtx_lock(gLock);
  gJoinPending = false;
  if (!gPower || gLinkSuppressed) {
    lck_mtx_unlock(gLock);
    log(6, "wifi-net: ignore join completion after explicit disconnect: %d", result);
    return;
  }
  if (result == NW_RES_OK && status.state != NW_STA_UP) {
    // Authorization without the link standing would tell the daemon the join succeeded and draw bars
    // for a link that is not there; the reference port ignores such a completion.
    gAssocResult = kAssocFailed;
    lck_mtx_unlock(gLock);
    log(6, "wifi-net: ignore authorization without an active link");
    return;
  }
  gAssocResult=result==NW_RES_OK?kAssocOk:result==NW_RES_BAD_KEY?kAssocBadKey:result==NW_RES_TIMEOUT?kAssocTimeout:kAssocFailed;
  // NW_RES_OK follows actual key installation/STA_AUTHORIZED for WPA2.
  pong_wifi_notification event={NotifyAssociate,result,status.signal_dbm,gKeyed?1u:0u};
  gLinkUpMs = result == NW_RES_OK ? scan_clock_ms() : 0;
  queue_notification_locked(event);lck_mtx_unlock(gLock);
  log(6,"wifi-net: join finished: module result %d",result);
}
void on_link_lost(int reason) {
  if (gLinkSuppressed) { log(6, "wifi-net: link lost during an explicit disconnect: reason %d", reason); return; }
  log(6,"wifi-net: link lost: reason %d",reason);
  lck_mtx_lock(gLock);gLinkUpMs=0;gAssocResult=kAssocFailed;gJoinPending=false;pong_wifi_notification event={NotifyLost,reason,0,0};queue_notification_locked(event);lck_mtx_unlock(gLock);
}
// The station refreshes the cached peer signal every time it moves three dB (nw_mainline.c
// nw_mainline_signal_update). The reference port turns that callback into a link change so the
// bars follow the link; without it the event table leaves link_update null and the daemon keeps
// the signal it read at association.
void on_link_update(const nw_wifi_status *status) {
  if (!gPower || gLinkSuppressed || status->state != NW_STA_UP || status->signal_dbm >= 0) return;
  link_event event{}; event.rssi = status->signal_dbm;
  event.noise = static_cast<uint16_t>(-95); event.snr = status->signal_dbm > -95 ? status->signal_dbm + 95 : 0;
  post_event(kEvLinkChanged, &event, sizeof event);
}
// The station starts a join only from IDLE (nw_sta.c start_connect): a request that meets a link already up
// is dropped, and the daemon would wait for an association event that never comes. Drain the old link first,
// as the reference port does, and report a timeout instead of starting a join that cannot run.
int drain_disconnect() {
  nw_wifi_disconnect(); pong_wifi_wake();
  for (unsigned waited = 0; waited < 2000; waited += 10) {
    nw_wifi_status current; nw_wifi_status_get(&current);
    if (current.state < NW_STA_AUTH) return 0;
    IOSleep(10);
  }
  log(4, "wifi-net: disconnect did not drain within 2000 ms");
  return ETIMEDOUT;
}

// What crosses the interface, for the traffic line: DHCP messages (type, transaction, offered address), ARP, TLS on port 443 and DNS, with
// the first packet of each direction logged so a run shows what the network is actually used for.
struct Kinds { uint32_t arp, ip4, dhcp, ip6, other, dns, https; } gKindsIn, gKindsOut;
void note_frame(const uint8_t *e, size_t n, bool out) {
  Kinds &k = out ? gKindsOut : gKindsIn; const unsigned type = n >= 14 ? (e[12] << 8 | e[13]) : 0; const char *dir = out ? "out" : "in";
  if (type == 0x0806) {
    k.arp++; static unsigned shown[2];
    if (n >= 42 && shown[out]++ < 12) log(6, "wifi-net: arp %s op %u %u.%u.%u.%u asks %u.%u.%u.%u", dir, e[21], e[28], e[29], e[30], e[31], e[38], e[39], e[40], e[41]);
    return; }
  if (type == 0x86dd) { k.ip6++; return; }
  if (type != 0x0800 || n < 34) { k.other++; return; }
  k.ip4++; const uint8_t *ip = e + 14; const unsigned ihl = (ip[0] & 15) * 4; const unsigned proto = ip[9];
  // TLS is where a webpage ends up and DNS is what names the server it goes to. The first packet of each direction is logged, so a run
  // shows whether the device reaches the network at all, not only that it was given an address.
  if (proto == 6 && n >= 14 + ihl + 20) {
    const uint8_t *tcp = ip + ihl; const unsigned sp = pong_wifi_be16(tcp), dp = pong_wifi_be16(tcp + 2), flags = tcp[13];
    if (sp == 443 || dp == 443) { k.https++; static unsigned shown[2];
      if (shown[out]++ < 24) log(6, "wifi-net: https %s %u.%u.%u.%u:%u -> %u.%u.%u.%u:%u flags 0x%02x len %u", dir,
          ip[12], ip[13], ip[14], ip[15], sp, ip[16], ip[17], ip[18], ip[19], dp, flags, pong_wifi_be16(ip + 2)); }
    return; }
  if (proto != 17 || n < 14 + ihl + 8) return;
  const uint8_t *udp = ip + ihl; const unsigned sp = udp[0] << 8 | udp[1], dp = udp[2] << 8 | udp[3];
  if (sp == 53 || dp == 53) { k.dns++; static unsigned shown[2];
    if (shown[out]++ < 12) { const uint8_t *d = udp + 8; const size_t dl = n - (d - e); char name[80] = ""; int at = 0;
      if (dl >= 12 && !(d[2] & 0x80)) for (size_t o = 12; o < dl && d[o] && at < 76;) {
        const unsigned l = d[o]; if (l > 63 || o + 1 + l > dl) break; if (at) name[at++] = '.';
        for (unsigned i = 0; i < l && at < 76; ++i) { const unsigned c = d[o + 1 + i]; name[at++] = c >= 33 && c < 127 && c != '.' && c != ' ' ? static_cast<char>(c) : '?'; }
        o += 1 + l; }
      name[at] = 0;
      if (name[0]) log(6, "wifi-net: dns %s query %s", dir, name); else log(6, "wifi-net: dns %s len %u", dir, static_cast<unsigned>(dl)); }
    return; }
  if (!((sp == 67 || sp == 68) && (dp == 67 || dp == 68))) return;
  k.dhcp++; const uint8_t *b = udp + 8; const size_t bl = n - (b - e); unsigned msg = 0;
  if (ihl >= 20 && !(pong_wifi_be16(ip + 6) & 0x3fff)) {
    const unsigned udpLen = pong_wifi_be16(udp + 4), ipLen = pong_wifi_be16(ip + 2);
    if (udpLen >= 8 + 241 && udpLen - 8 <= bl && ipLen >= ihl + udpLen && ipLen <= n - 14) {
      struct pong_wifi_lease lease = {};
      const unsigned mt = pong_wifi_dhcp_fields(b, udpLen - 8, gMac, &lease);
      if (mt && ((out && sp == 68 && dp == 67) || (!out && sp == 67 && dp == 68))) {
        lck_mtx_lock(gLock);
        pong_wifi_lease_packet(&gLease, out, mt, b, &lease, lease_clock());
        lck_mtx_unlock(gLock);
      }
    }
  }
  for (size_t o = 240; bl >= 240 && o + 2 <= bl && b[o] != 255; o += b[o] ? 2 + b[o + 1] : 1) if (b[o] == 53 && o + 2 < bl) { msg = b[o + 2]; break; }
  static unsigned shown[2]; if (shown[out]++ < 24 && bl >= 240)
    log(6, "wifi-net: dhcp %s type %u xid %02x%02x%02x%02x flags %02x%02x to %02x:%02x:%02x:%02x:%02x:%02x yiaddr %u.%u.%u.%u", dir, msg, b[4], b[5], b[6], b[7], b[10], b[11],
        e[0], e[1], e[2], e[3], e[4], e[5], b[16], b[17], b[18], b[19]);
  // An offer or acknowledgement: the network settings the server hands out (mask, router, name servers, lease), to tell a server that
  // gives no IPv4 name server from a client that drops one.
  if (out || (msg != 2 && msg != 5)) return;
  char opts[124]; int at = 0;   // fits the 160-byte log line
  for (size_t o = 240; o + 2 <= bl && b[o] != 255 && at >= 0 && at < static_cast<int>(sizeof opts) - 24; o += b[o] ? 2 + b[o + 1] : 1) {
    if (!b[o]) continue;
    const unsigned code = b[o], len = b[o + 1]; const uint8_t *v = b + o + 2;
    if (o + 2 + len > bl) break;
    if ((code == 1 || code == 3 || code == 6 || code == 54) && len >= 4)
      for (unsigned i = 0; i + 4 <= len && at < static_cast<int>(sizeof opts) - 24; i += 4)
        at += snprintf(opts + at, sizeof opts - at, " %u=%u.%u.%u.%u", code, v[i], v[i + 1], v[i + 2], v[i + 3]);
    else if (code == 51 && len == 4) at += snprintf(opts + at, sizeof opts - at, " 51=%u", v[0] << 24 | v[1] << 16 | v[2] << 8 | v[3]);
    else at += snprintf(opts + at, sizeof opts - at, " %u", code);
  }
  log(6, "wifi-net: dhcp %s type %u options%s", dir, msg, opts);
}
void on_rx(const uint8_t *eth, size_t length) {
  if (!gIf || length < 14) return;
  note_frame(eth, length, false);
  // Two bytes ahead of the Ethernet header put the IP header on a 4-byte boundary. The packet may come back as a chain (a frame larger
  // than one cluster, or no large cluster free): each buffer gets only what fits in it. Setting the whole length on the first one (as
  // before) let the stack read past that buffer's end (i469: a data abort in m_copydata reading across a page).
  enum : size_t { Align = 2 };
  mbuf_t m = nullptr;
  if (mbuf_allocpacket(MBUF_DONTWAIT, length + Align, nullptr, &m) || !m) { gRxNoBuffer++; return; }
  if (length > gRxLongest) gRxLongest = static_cast<uint32_t>(length);
  if (mbuf_next(m)) gRxChains++;
  size_t done = 0; bool first = true;
  for (mbuf_t n = m; n; n = mbuf_next(n)) {
    size_t room = mbuf_maxlen(n) - mbuf_leadingspace(n);
    if (first) { if (room < Align + 14) break; mbuf_setdata(n, static_cast<uint8_t *>(mbuf_datastart(n)) + mbuf_leadingspace(n) + Align, 0); room -= Align; }
    const size_t take = length - done < room ? length - done : room;
    memcpy(mbuf_data(n), eth + done, take); mbuf_setlen(n, take); done += take; first = false;
  }
  if (done != length) { gRxNoBuffer++; mbuf_freem(m); return; }
  mbuf_pkthdr_setlen(m, length); mbuf_pkthdr_setrcvif(m, gIf);
  { bpf_packet_func tap = gBpfTap; if (tap && (gBpfMode & BPF_MODE_INPUT)) tap(gIf, m); }   // the whole frame, before the header is set apart
  mbuf_pkthdr_setheader(m, mbuf_data(m)); mbuf_adj(m, 14);   // the stack wants the Ethernet header apart from the payload
  struct ifnet_stat_increment_param inc; memset(&inc, 0, sizeof inc); inc.packets_in = 1; inc.bytes_in = static_cast<uint32_t>(length);
  const errno_t e = ifnet_input(gIf, m, &inc);
  if (e) { gRxErrors++; gRxLastError = e; } else gRxFrames++;
}
const struct nw_wifi_events gEvents = { on_scan_done, on_connect_done, on_link_lost, on_rx, nullptr, nullptr, on_link_update };

// ---- the interface ----
errno_t if_output(ifnet_t, mbuf_t m) {
  size_t length = mbuf_pkthdr_len(m);
  if (length >= 14 && length <= 2000) {
    uint8_t frame[2000]; mbuf_copydata(m, 0, length, frame);
    note_frame(frame, length, true);
    { bpf_packet_func tap = gBpfTap; if (tap && (gBpfMode & BPF_MODE_OUTPUT)) tap(gIf, m); }
    if (nw_wifi_tx(frame, length)) log(6, "wifi-net: a frame was dropped (queue full)");
    else {ifnet_stat_increment_out(gIf, 1, static_cast<uint32_t>(length), 0); pong_wifi_wake();}
  }
  mbuf_freem(m);
  return 0;
}
void if_event_stub(ifnet_t, const struct kev_msg *) {}

// ---- Apple80211 ----
void fill_channel(channel &c, uint32_t mhz) {
  c.version = 1;
  if (mhz >= 4900) { c.channel = (mhz - 5000) / 5; c.flags = 0x2 | 0x10; } else { c.channel = mhz == 2484 ? 14 : (mhz - 2407) / 5; c.flags = 0x2 | 0x8; }
}
uint64_t scan_clock_ns() {
  uint64_t ns=0;absolutetime_to_nanoseconds(mach_continuous_time(),&ns);return ns;
}
// The 5 GHz record of this access point is the only one of 38 records the daemon drops, and its element blob is the
// one the station clamps: the 2.4 GHz record carries 347 bytes and parses to the end, the 5 GHz record reports 384
// bytes (the size of the station's copy) and its element walk stops after 318, leaving 66 bytes that never form a
// whole element. A list that ends in the middle of an element is a malformed record, and that is the one difference
// no element inventory shows. Serve the record the access point sent, ended at the last complete element. The
// station's own association uses the beacon directly, not this record, so nothing on the air changes. Test
// branch only.
void fill_result(scan_result &record, const nw_bss_info &b,uint32_t request_bytes) {
  memset(&record, 0, sizeof record);scan_result &r=record;
  r.version = 1; fill_channel(r.ch, b.freq_mhz); r.noise_known = 1; r.noise = -95; r.rssi = b.signal_dbm; r.snr = b.signal_dbm + 95;
  r.beacon_interval = b.beacon_int; r.capability = b.caps; memcpy(r.bssid, b.bssid, 6); r.ssid_length = b.ssid_len; memcpy(r.ssid, b.ssid, 32);
  r.age_ms = b.age_ms;
  static unsigned announced; r.elements_length = 0; unsigned used = 0;
  // A 22H374 client asks for 1164 bytes and gets 1024 element bytes; a 24A446 client asks for 0x8e8
  // and gets the full 2048. The record says how many of them are meaningful.
  const uint32_t room = pong_scan_elements_room(request_bytes ? request_bytes : PONG_SCAN_RECORD_24A446);
  for (unsigned o = 0; o + 2 <= b.ie_len; o += 2 + b.ie[o + 1]) {
    const unsigned id = b.ie[o], len = b.ie[o + 1];
    if (o + 2 + len > b.ie_len) break;   // a blob the station clamped at 384 ends in the middle of an element
    used = o + 2 + len;
    if (r.elements_length + 2 + len <= room) { memcpy(r.elements + r.elements_length, b.ie + o, 2 + len); r.elements_length += 2 + len; }
  }
  if (used < b.ie_len && announced++ < 3) log(6, "wifi-net: scan record tail %u of %u bytes is an incomplete element and is not served", b.ie_len - used, b.ie_len);
  r.rate_count = 0;
  // The record says when the network was heard, not when it was sampled: the hand-out clock minus the
  // age the station measures at this bss_get, exactly as the reference port stamps it
  // (sheng_wifi_scan_result_stamp). Rounding the age upward made an old observation look newer than
  // the frame, and a frozen sample time left a cached list looking stale while it was served.
  const uint64_t now_ns = scan_clock_ns();
  const uint64_t age_ns = uint64_t(b.age_ms) * 1000000ull;
  record.timestamp_ns = now_ns > age_ns ? now_ns - age_ns : 0;
}
int copy_out(const apple80211req &rq, const void *src, size_t size, bool kernel = false) {
  if (rq.req_len == 0 || !rq.req_data) return EINVAL;
  const size_t n = rq.req_len < size ? rq.req_len : size;
  if (kernel) { memcpy(reinterpret_cast<void *>(rq.req_data), src, n); return 0; }
  return copyout(src, rq.req_data, n);
}
// A get that gives no buffer takes a single value in req_val; one with a buffer gets {version, value}.
int answer_value(apple80211req &rq, uint32_t value, bool kernel = false) {
  if (rq.req_len == 0 || !rq.req_data) { rq.req_val = static_cast<int32_t>(value); return 0; }
  const uint32_t w[2] = { 1, value }; return copy_out(rq, w, sizeof w, kernel);
}
// The raw bytes, their length in req_len.
int answer_bytes(apple80211req &rq, const void *src, uint32_t size, bool kernel = false) {
  if (!rq.req_data) return EINVAL;
  const uint32_t n = rq.req_len < size ? rq.req_len : size; rq.req_len = size;
  if (kernel) { memcpy(reinterpret_cast<void *>(rq.req_data), src, n); return 0; }
  return copyout(src, rq.req_data, n);
}
int copy_in(const apple80211req &rq, void *dst, size_t size, bool kernel = false) {
  if (!rq.req_data) return EINVAL;
  memset(dst, 0, size);
  const size_t n = rq.req_len < size ? rq.req_len : size;
  if (kernel) { memcpy(dst, reinterpret_cast<const void *>(rq.req_data), n); return 0; }
  return copyin(rq.req_data, dst, n);
}
// A request the driver does not implement has to be identifiable from one console rather than guessed at from its
// number: log the value, the length and the first bytes (the first two of each type, then one in 64).
void log_unhandled(bool set, int type, const apple80211req &rq, bool kernel) {
  static uint32_t seen[2][512 / 32]; static unsigned skipped;
  const unsigned t = static_cast<unsigned>(type) & 511u, word = 1u << (t % 32);
  const bool first = !(seen[set][t / 32] & word);
  seen[set][t / 32] |= word;
  if (!first && ++skipped % 64) return;
  uint8_t head[16]; memset(head, 0, sizeof head); size_t n = 0;
  if (set && rq.req_len && rq.req_data && !copy_in(rq, head, sizeof head, kernel))
    n = rq.req_len < sizeof head ? rq.req_len : sizeof head;
  char text[40]; int at = 0;
  for (size_t i = 0; i < n && at < 34; i++) at += snprintf(text + at, sizeof text - at, "%02x", head[i]);
  log(6, "wifi-net: refused %s %d val %d len %u%s%s", set ? "set" : "get", type, rq.req_val, rq.req_len,
      n ? " starts " : "", n ? text : "");
}
unsigned gResultsShown;
// The regulatory country as the access points announce it (802.11d: the Country element, id 7, of the strongest network that has one), else "XX".
void country(char cc[3]) {
  cc[0] = 'X'; cc[1] = 'X'; cc[2] = 0; int best = -200; nw_bss_info b;
  for (int i = 0, n = nw_wifi_bss_count(); i < n; ++i) {
    if (nw_wifi_bss_get(i, &b) || b.signal_dbm <= best) continue;
    for (unsigned o = 0; o + 2 <= b.ie_len && o + 2 + b.ie[o + 1] <= b.ie_len; o += 2 + b.ie[o + 1])
      if (b.ie[o] == 7 && b.ie[o + 1] >= 2 && b.ie[o + 2] >= 'A' && b.ie[o + 2] <= 'Z' && b.ie[o + 3] >= 'A' && b.ie[o + 3] <= 'Z') {
        cc[0] = static_cast<char>(b.ie[o + 2]); cc[1] = static_cast<char>(b.ie[o + 3]); best = b.signal_dbm; break; }
  }
}
int map_state(unsigned s) { switch (s) { case NW_STA_SCANNING: return 1; case NW_STA_AUTH: return 2; case NW_STA_ASSOC: case NW_STA_KEYS: return 3; case NW_STA_UP: return 4; default: return 0; } }

int apple80211(bool set, apple80211req &rq, bool kernel = false) {
  if (__atomic_load_n(&gFailed,__ATOMIC_ACQUIRE) && (set || rq.req_type != kPower)) return ENETDOWN;
  // Both native selector 0 and the socket tunnel hold gLock here.
  if (rq.req_type == PONG_WIFI_TEST_RECONNECT)
    return set && gCycleTest && pong_wifi_test_reconnect() ? 0 : EOPNOTSUPP;
  if (rq.req_type == PONG_WIFI_GET_LEASE) {
    if (set) return EOPNOTSUPP;
    if(gProgressDiagnostic) {
      static unsigned queries;
      if((queries++%5)==0) {
        uint64_t ns=0;absolutetime_to_nanoseconds(mach_absolute_time(),&ns);
        log(6,"wifi-net: dispatcher phase=%llu age-ms=%llu generation=%llu where=%llu fn-offset=%llx depth=%llu",pong_wifi_progress[0],ns/1000000ull-pong_wifi_progress[1],pong_wifi_progress[2],nw_wifi_where[0],nw_wifi_where[1],nw_wifi_where[2]);
      }
    }
    const auto lease = pong_wifi_lease_snapshot(&gLease, lease_clock());
    return answer_bytes(rq, &lease, sizeof(lease), kernel);
  }
  nw_wifi_status st; visible_status(st);
  const int type = rq.req_type;
  // (not on the stack: the largest answer is 4824 bytes)
  union Out { uint8_t raw[5120]; channels_list chans; scan_result res; };
  Out *outp = static_cast<Out *>(IOMallocData(sizeof(Out)));
  if (!outp) return ENOMEM;
  memset(outp, 0, sizeof(Out));
  struct Free { Out *p; ~Free() { IOFreeData(p, sizeof(Out)); } } freeOut{outp};
  Out &out = *outp;
  uint32_t *w = reinterpret_cast<uint32_t *>(out.raw);
  if (set) {
    switch (type) {
    case kPower: { uint32_t in[6]; if(rq.req_len<12)return EINVAL; if (copy_in(rq, in, sizeof in, kernel)) return EFAULT; gUserJoin = true; gPower = in[2] != 0; log(6, "wifi-net: power set %u", in[2]);
      if (!gPower) { gLinkSuppressed = true; gAssocResult = kAssocFailed; gJoinPending = false; nw_wifi_disconnect(); pong_wifi_wake(); notify_locked(NotifyLinkDown); }
      // The reference tells the station itself, so the radio really leaves the air on 24A446; the
      // 22H374 daemon kept its proven behaviour (disconnect only) until a 27 daemon is seen.
      if (gModern27Client) { nw_wifi_power(gPower ? 1 : 0); pong_wifi_wake(); }
      notify_locked(NotifyPower); return 0; }
    case kScanReq: case kScanReqMultiple: {
      if(!gPower)return ENETDOWN;
      if(rq.req_len<20)return EINVAL;
      // 24A446 asks for the networks by name in request 86 (PongWifiAbi.h): the names sit at 0xc,
      // 40 bytes each, the scan type at 0x200 and the channels at 0x210. Request 10 keeps the
      // single name at 0x14 and its channels at 0x44. Both shapes are parsed here so a named scan
      // (airportd's hidden-network probe) reaches the radio instead of being read as a wildcard.
      const uint32_t held = rq.req_len < sizeof out.raw ? rq.req_len : sizeof out.raw;
      if (copy_in(rq, out.raw, held, kernel)) return EFAULT;
      uint32_t ssidLength = 0, scanType = 0; const uint8_t *ssid = nullptr;
      uint32_t mhz[PONG_SCAN_FREQUENCIES_MAX]; uint32_t frequencies = 0;
      if (type == kScanReqMultiple) {
        if (pong_scan_multiple_parse(out.raw, held, &scanType, &ssid, &ssidLength)) return EINVAL;
        // 0x14e8 bytes is the 24A446 scan request, a size no 22H374 client sends: from here on the
        // daemon is the newer one, and its auth upper value is 0x10 where 22H374 used 0x8.
        if (rq.req_len == PONG_SCAN_MULTIPLE_BYTES) gModern27Client = true;
        frequencies = pong_scan_frequencies(out.raw, held, PONG_SCAN_MULTIPLE_CHANNEL_COUNT,
                                            PONG_SCAN_MULTIPLE_CHANNELS, mhz);
      } else {
        if (held < 20) return EINVAL;
        memcpy(&ssidLength, out.raw + 16, 4); ssid = out.raw + 20;
        // The request-10 prefix is the reference port's layout: the scan type sits at 0x34, and the
        // type 3 shortcut (answer from the results already held) has to work on this shape too.
        if (held >= PONG_SCAN_ONE_TYPE + 4u) memcpy(&scanType, out.raw + PONG_SCAN_ONE_TYPE, 4);
        frequencies = pong_scan_frequencies(out.raw, held, PONG_SCAN_ONE_CHANNEL_COUNT,
                                            PONG_SCAN_ONE_CHANNELS, mhz);
      }
      log(6, "wifi-net: scan request type %d len %u val %d ssid %u channels %u type %u", type, rq.req_len, rq.req_val, ssidLength, frequencies, scanType);
      // The daemon's scan request carries a channel filter ahead of the SSID; the filter decides what the pane may see.
      static unsigned reqs; if (++reqs <= 8) { uint32_t wds[4]; memcpy(wds, out.raw, sizeof wds); log(6, "wifi-net: scan request prefix %08x %08x %08x %08x", wds[0], wds[1], wds[2], wds[3]); }
      if(ssidLength>32 || (type == kScanReq && held<20+ssidLength))return EINVAL;
      // The results already held are what was asked for: read them from the start, run no scan.
      if (scanType == PONG_SCAN_TYPE_CACHED && nw_wifi_bss_count() > 0) {
        gScanCursor = 0; gScanServed = 0; gResultsShown = 24; return 0; }
      // The reference port's scan policy (PongWifiScanPolicy.h): while a join is under way, and for 15 s
      // after the link came up, the radio stays on the access point's channel and the request is answered
      // from the held networks; on a settled link it goes on the air unless every channel it names was
      // already scanned in the last 20 s.
      const uint64_t now_ms = scan_clock_ms();
      const int link = st.state >= NW_STA_UP ? PONG_LINK_UP : st.state >= NW_STA_AUTH ? PONG_LINK_JOINING : PONG_LINK_NONE;
      const uint64_t link_ms = (gLinkUpMs && now_ms >= gLinkUpMs) ? now_ms - gLinkUpMs : 0;
      if (!pong_scan_on_air(&gScanAir, link, link_ms, nw_wifi_bss_count() > 0, mhz, frequencies, now_ms)) {
        if (!gCachedScan) gCachedScan = thread_call_allocate(cached_scan_done, nullptr);
        if (!gCachedScan) return ENOMEM;
        static unsigned answered; if (++answered <= 8 || answered % 64 == 0) log(6, "wifi-net: scan %u answered from the held networks (link %d, up %llu s)", answered, link, static_cast<unsigned long long>(link_ms / 1000));
        gScanning = 1; gScanCursor = 0; gScanServed = 0; gResultsShown = 24; uint64_t at; clock_interval_to_deadline(2000, kMillisecondScale, &at); thread_call_enter_delayed(gCachedScan, at); return 0; }
      gScanning = 1; gScanCursor = 0; gScanServed = 0; gResultsShown = 0;
      // A scan of every band took 15.7 s on this radio, past the 12 s the framework waits, so the
      // channels the request names are what the radio visits when the station knows how to take them.
      const bool asked = frequencies != 0 && nw_wifi_scan_frequencies != nullptr;
      if (asked ? nw_wifi_scan_frequencies(ssid, ssidLength, mhz, frequencies)
                : nw_wifi_scan(ssidLength ? ssid : nullptr, ssidLength)) { gScanning = 0; return EBUSY; }
      pong_scan_air_mark(&gScanAir, mhz, frequencies, now_ms);
      pong_wifi_wake();return 0; }
    case kAssociate: {
      if(!gPower)return ENETDOWN;
      assoc_request24 a={};
      // 24A446 sends 0x290 bytes and 22H374 0x384; both carry the same fields through key[64] at
      // 0x4c, so one struct decodes either. Only the legacy 0x250 request moves key to 0x48.
      const bool modern27=rq.req_len==PONG_ASSOC_REQUEST_24A446;
      const bool darwin24=rq.req_len>=PONG_ASSOC_REQUEST_24A446 && rq.req_len<=PONG_ASSOC_REQUEST_22H374;
      size_t keyOffset;
      if(darwin24) {
        const size_t want = rq.req_len < sizeof(a) ? rq.req_len : sizeof(a);
        if(copy_in(rq,&a,want,kernel))return EFAULT;
        keyOffset=__builtin_offsetof(assoc_request24,key);
      } else if(rq.req_len==sizeof(assoc_request)) {
        assoc_request legacy={};
        if(copy_in(rq,&legacy,sizeof(legacy),kernel))return EFAULT;
        a.version=legacy.version;a.mode=legacy.mode;
        a.auth_lower=legacy.auth_lower;a.auth_upper=legacy.auth_upper;
        a.ssid_length=legacy.ssid_length;memcpy(a.ssid,legacy.ssid,sizeof(a.ssid));
        memcpy(a.bssid,legacy.bssid,sizeof(a.bssid));
        a.key_version=legacy.key_version;a.key_length=legacy.key_length;a.key_cipher=legacy.key_cipher;
        a.key_flags=legacy.key_flags;a.key_index=legacy.key_index;
        memcpy(a.key,legacy.key,sizeof(a.key));memset(&legacy,0,sizeof(legacy));
        keyOffset=__builtin_offsetof(assoc_request,key);
      } else return EINVAL;
      if(a.version!=1 || !a.ssid_length || a.ssid_length>32 || a.key_length>64 ||
          rq.req_len<keyOffset+a.key_length) {memset(&a,0,sizeof(a));return EINVAL;}
      // The station implements open/WPA2-personal, not enterprise or SAE.
      // Preserve native failure for unsupported authentication, not an open join.
      // 22H374 names WPA2 personal 0x8, 24A446 names it 0x10 (the reference port answers 0x10 on 27):
      // both are the same personal WPA2 join here, anything else stays unsupported.
      if(a.auth_upper && a.auth_upper!=8 && a.auth_upper!=0x10) {memset(&a,0,sizeof(a));return EOPNOTSUPP;}
      const bool hasBssid = (a.bssid[0] | a.bssid[1] | a.bssid[2] | a.bssid[3] | a.bssid[4] | a.bssid[5]) != 0;
      const bool hasKey = a.key_length != 0 && a.key_length <= 64; char pass[65]; memset(pass, 0, sizeof pass); if (hasKey) memcpy(pass, a.key, a.key_length);
      // cipher 6: the daemon already derived the pairwise master key (32 bytes); the module takes it as 64 hex digits
      unsigned keyLength = a.key_length;
      if (hasKey && a.key_cipher == 6 && a.key_length == 32) { static const char hex[] = "0123456789abcdef"; for (int i = 0; i < 32; i++) { pass[2 * i] = hex[a.key[i] >> 4]; pass[2 * i + 1] = hex[a.key[i] & 15]; } keyLength = 64; }
      // A join while a link is up drains first (drain_disconnect): the station ignores a join request that
      // arrives in any state other than IDLE, so switching networks from the pane would otherwise never run.
      nw_wifi_status current; nw_wifi_status_get(&current);
      if (current.state >= NW_STA_AUTH) {
        log(6, "wifi-net: switching network: draining state %u", current.state);
        if (drain_disconnect()) { memset(&a,0,sizeof(a)); gAssocResult = kAssocFailed; return ETIMEDOUT; }
        gLinkUpMs = 0;
      }
      // The reference rejects a credential it cannot interpret (cipher 6 carries the 32-byte PMK,
      // cipher 10 an 8..63-byte passphrase) instead of passing it on as a password or an open network.
      // 22H374 clients keep their previous acceptance; the newer daemon gets the strict set.
      if (modern27 && a.key_length && !((a.key_cipher == 6 && a.key_length == 32) ||
                                        (a.key_cipher == 10 && a.key_length >= 8 && a.key_length <= 63))) {
        memset(&a,0,sizeof(a)); return EINVAL; }
      gAssocResult = kAssocPending; gJoinPending = true; gLinkSuppressed = false; gUserJoin = true; gAssocModern27 = modern27; if (modern27) gModern27Client = true;
      log(6, "wifi-net: join: ssid length %u, bssid given %d, key length %u cipher %u", a.ssid_length, hasBssid, a.key_length, a.key_cipher);
      gKeyed = hasKey; int r = nw_wifi_connect(a.ssid, a.ssid_length, hasBssid ? a.bssid : nullptr, hasKey ? pass : nullptr, hasKey ? keyLength : 0);
      if (r) { gAssocResult = kAssocFailed; gJoinPending = false; }   // the request never reached the station
      memset(pass, 0, sizeof pass); memset(&a, 0, sizeof a);
      if(!r)pong_wifi_wake();
      return r ? EINVAL : 0; }
    case kDisassociate: case kDeauth: gUserJoin = true; gLinkUpMs = 0; gLinkSuppressed = true; gAssocResult = kAssocFailed; gJoinPending = false;
      log(6, "wifi-net: leave"); nw_wifi_disconnect();pong_wifi_wake(); notify_locked(NotifyLinkDown); return 0;
    case kScanCacheClear: case kLocale: case kCountryCode: case kPowerSave: case kAuthType: case kCipherKey: return 0;
    case kAbortScan: return 0;   // accepted; a running scan still runs to its end (seconds) and reports it
    // Settings the module has no use for, that the wireless daemon sends at every state change (a property list, two flags): taking them
    // without effect is what a driver with nothing to configure does; refusing makes the daemon repeat them and log errors.
    case kProperty: {
      static int seen; uint8_t buf[320];
      if (seen < 150 && rq.req_data) {
        ++seen;
        memset(buf, 0, sizeof buf);
        if (copy_in(rq, buf, sizeof buf - 1, kernel)) return 0;
        for (unsigned i = 0; i < sizeof buf; i++) if (buf[i] < 32 || buf[i] > 126) buf[i] = ' ';
        buf[sizeof buf - 1] = 0;
        // the document's own text starts at "<dict>"; the long header before it is the same every time
        const char *d = strnstr(reinterpret_cast<char *>(buf + 8), "<dict>", sizeof buf - 8);
        log(6, "wifi-net: property list %.200s", d ? d : reinterpret_cast<char *>(buf + 8)); }
      return 0; }
    case kFlagA: case kFlagB: return 0;
    default: log_unhandled(true, type, rq, kernel); return EOPNOTSUPP;
    }
  }
  switch (type) {
  // A station that is off is off even while the daemon's power bit is still set (the reference port
  // answers gPower && state != NW_STA_OFF): saying 1 here makes the daemon skip the re-enable.
  case kPower: w[0] = 1; w[1] = 1; w[2] = (gPower && st.state != NW_STA_OFF) ? 1 : 0; return copy_out(rq, w, 24, kernel);
  case kState: return answer_value(rq, static_cast<uint32_t>(gPower ? map_state(st.state) : 0), kernel);
  case kOpMode: return answer_value(rq, 1, kernel);   // station
  case kAuthType: w[0] = 1; w[1] = 1; w[2] = gKeyed ? (gModern27Client ? 0x10 : 0x8) : 0; w[3] = 0; return copy_out(rq, w, 16, kernel);   // {version, lower: open system, upper: WPA2 personal in the daemon's own encoding}
  case kPowerSave: return answer_value(rq, 0, kernel);
  // en0 is the physical infrastructure station, not P2P/AWDL. A physical
  // interface has role zero and no virtual parent. These discovery queries
  // must not be confused with unsupported virtual-interface creation.
  case kVirtualRole: return answer_value(rq, 0, kernel);
  case kVirtualParent: return answer_bytes(rq, out.raw, 0, kernel);
  case kWowEnabled: return answer_value(rq, 0, kernel); // no WoW suspend path exposed
  case kCardCaps: {   // a bitmap, bit n in byte n / 8: AES, AES-CCM, power management, short slot and preamble, WPA2, WME, short guard interval at 20 MHz
    static const uint8_t has[] = { 2, 3, 6, 9, 10, 14, 17, 19 };
    for (uint8_t b : has) out.raw[b / 8] |= static_cast<uint8_t>(1u << (b % 8));
    // A 12-byte request is the 24A446 extent, and it is the one whose scanner tests bits 22 and 46
    // (PongWifiAbi.h): without 22 a scan that names networks fails at once with -3903 and never
    // reaches this driver; without 46 the framework reads results before the scan-done event.
    if (rq.req_len <= PONG_WIFI_CAPS_BYTES) { uint8_t caps[PONG_WIFI_CAPS_BYTES]; pong_wifi_caps_fill(caps);
      for (unsigned i = 0; i < PONG_WIFI_CAPS_BYTES; ++i) out.raw[i] = caps[i]; }
    // 22H374 asks for 19 capability bytes (older clients ask for 12).
    // Preserve that negotiated extent and zero unsupported extension bits;
    // truncating the newer bitmap to 12 makes interface discovery incomplete.
    const uint32_t bytes=rq.req_len>19?19:rq.req_len;
    return answer_bytes(rq, out.raw, bytes, kernel); }
  case kPhyMode: w[0] = 1; w[1] = 0x1 | 0x2 | 0x4 | 0x8 | 0x10 | 0x20 | 0x40; w[2] = st.state == NW_STA_UP ? 0x8 : 0; return copy_out(rq, w, 12, kernel);
  case kSsid: if (st.state < NW_STA_ASSOC) return ENOENT; return answer_bytes(rq, st.ssid, st.ssid_len, kernel);
  case kBssid: if (st.state < NW_STA_ASSOC) return ENOENT; return answer_bytes(rq, st.bssid, 6, kernel);
  case kChannel: if (st.state < NW_STA_AUTH) return ENOENT; w[0] = 1; fill_channel(*reinterpret_cast<channel *>(out.raw + 4), st.freq_mhz); return copy_out(rq, w, 16, kernel);
  case kRssiBounds: {
    static_assert(sizeof(int)==4,"Apple80211 signed RSSI words");
    int bounds[4]={1,0,0,0};
    if(nw_wifi_rssi_limits(&bounds[1],&bounds[2]))return EOPNOTSUPP;
    // The station imposes no additional RSSI admission policy. Use its
    // representable floor for this legacy gate; CoreWiFi retains its own
    // -80/-90 dBm candidate quality policy and actual RSSI measurements.
    // Refusing this query leaves wifid's threshold at zero and rejects
    // every ordinary negative-dBm result before issuing an association.
    bounds[3]=bounds[1];
    return copy_out(rq,bounds,sizeof(bounds),kernel);
  }
  case kRssi: case kNoise: {   // {version, radios, unit (0: dBm), per chain[4], aggregate, extension per chain[4], its aggregate}
    if (type == kRssi && st.state != NW_STA_UP) return ENOENT;
    const int32_t dbm = type == kRssi ? static_cast<int32_t>(st.signal_dbm) : -95;
    // The status bar draws its bars from this query, not from the scan record, so every answer is logged with the
    // value it carried: a bar count that disagrees with the record can then be read off one console.
    static unsigned asks; if (asks++ < 60) log(6, "wifi-net: %s query -> %d dBm (link state %d)", type == kRssi ? "rssi" : "noise", dbm, static_cast<int>(st.state));
    const uint32_t v = static_cast<uint32_t>(dbm);
    w[0] = 1; w[1] = 1; w[2] = 0; for (int i = 3; i < 13; i++) w[i] = v; return copy_out(rq, w, 13 * 4, kernel); }
  // The station caches the peer's PHY rate at every status update (nw_abi.h tx_rate_100kbps), so the
  // daemon is told the rate in use rather than a constant that would be wrong at every VHT width.
  case kRate: return answer_value(rq, st.state == NW_STA_UP ? st.tx_rate_100kbps / 10 : 0, kernel);
  case kTxPower: return answer_value(rq, 15, kernel);
  case kDriverVersion: case kHardwareVersion: { const char *v = type == kDriverVersion ? "nativewifi 1" : "QCA6490 (ath11k/WCN6855)"; strlcpy(reinterpret_cast<char *>(out.raw), v, 256); return copy_out(rq, out.raw, 256, kernel); }
  case kCountryCode: { char cc[3]; country(cc); return answer_bytes(rq, cc, 3, kernel); }   // the two letters and a NUL (the daemon asks with a 3-byte buffer)
  case kAssociateResult: return answer_value(rq, static_cast<uint32_t>(gAssocResult), kernel);
  case kSupportedChannels: case kHwSupportedChannels: {
    out.chans.version = 1; unsigned n = 0, g24 = 0, g5 = 0;
    uint32_t frequencies[401];unsigned actual=nw_wifi_channel_list(frequencies,401);
    // CWFChannel compares the complete flag word for supported membership.
    // Keep the band/width representation consistent with scan/current/
    // history channels rather than adding ACTIVE only to this answer.
    // A 24A446 daemon is told only about the channels the station can scan. Its 6 GHz entries are
    // passive and a scan never visits them, so announcing them offers the pane networks the radio
    // cannot hear (the reference port leaves them out of its answer); the 22H374 answer stays as the
    // image that proved the pane. No flag word changes: only whole entries are dropped.
    for(unsigned i=0;i<actual && n<401;i++){
      if(gModern27Client && frequencies[i] >= PONG_BAND_6GHZ_MIN)continue;
      fill_channel(out.chans.list[n],frequencies[i]);(frequencies[i]<3000?g24:g5)++;n++;}
    static unsigned shown; if (!shown++) {
      log(6, "wifi-net: supported channels %u: 2.4 GHz %u, 5/6 GHz %u", n, g24, g5);
      for (unsigned i = 0; i < n && i < 4; i++) log(6, "wifi-net: channel %u: number %u flags 0x%x", frequencies[i], out.chans.list[i].channel, out.chans.list[i].flags); }
    out.chans.count = n; return copy_out(rq, &out.chans, sizeof out.chans, kernel); }
  case kScanResult: {
    if (rq.req_len == PONG_SCAN_RECORD_24A446) gModern27Client = true;   // a 24A446 daemon asks for the 2280-byte record
    const int count = gSnapCount ? static_cast<int>(gSnapCount) : nw_wifi_bss_count();
    nw_bss_info b; bool bad = false;
    // A held network that has not been heard for a minute is passed over (the reference port's policy):
    // one whose access point went out of range leaves the list instead of being handed out forever. The
    // frozen list carries the age each record had when the sweep ended, so the time since is added back.
    const uint64_t now_ns = scan_clock_ns();
    while (gScanCursor < static_cast<unsigned>(count)) {
      if (gSnapCount) b = gSnap[gScanCursor];
      else if (nw_wifi_bss_get(static_cast<int>(gScanCursor), &b)) { bad = true; break; }
      if (gSnapCount) {
        const uint64_t held_ns = uint64_t(b.age_ms) * 1000000ull + (now_ns > gSnapAtNs ? now_ns - gSnapAtNs : 0);
        b.age_ms = held_ns / 1000000ull > 0xffffffffull ? 0xffffffffu : static_cast<uint32_t>(held_ns / 1000000ull);
      }
      if (!pong_scan_held_stale(b.age_ms)) break;
      ++gScanCursor;
    }
    if (gScanCursor >= static_cast<unsigned>(count) || bad) {   // after the last record
      static unsigned ends;
      if (++ends % 16 == 1) log(6, "wifi-net: scan result end after serving %u of %d records", gScanServed, count);
      gScanCursor = 0; gScanServed = 0; return EIO; }
    gScanCursor++; ++gScanServed; fill_result(out.res, b,rq.req_len);
    // A 5 GHz record the daemon drops despite being served is a field problem, so print its encoded words.
    if (b.freq_mhz >= 3000 && gScanServed <= 6) {
      const uint32_t *wds = reinterpret_cast<const uint32_t *>(&out.res);
      log(6, "wifi-net: 5ghz %u words %08x %08x %08x %08x %08x %08x %08x %08x %08x %08x %08x %08x",
          gScanServed, wds[0], wds[1], wds[2], wds[3], wds[4], wds[5], wds[6], wds[7], wds[8], wds[9], wds[10], wds[11]);
      // The element blob decides the security type the daemon parses, so print its head for the same records.
      const uint8_t *ie = reinterpret_cast<const uint8_t *>(&out.res.elements);
      log(6, "wifi-net: 5ghz %u ie %02x%02x%02x%02x%02x%02x%02x%02x %02x%02x%02x%02x%02x%02x%02x%02x",
          gScanServed, ie[0],ie[1],ie[2],ie[3],ie[4],ie[5],ie[6],ie[7],ie[8],ie[9],ie[10],ie[11],ie[12],ie[13],ie[14],ie[15]);
    }
    // The daemon's list is only as complete as what it read: log what it consumed, not just the first few.
    if (count <= 40 || gScanServed <= 3 || gScanServed % 8 == 0) log(6, "wifi-net: scan result served %u of %d: %u MHz, %d dBm, %.*s", gScanServed, count, b.freq_mhz, b.signal_dbm, b.ssid_len, reinterpret_cast<const char *>(b.ssid));
    return copy_out(rq, &out.res, sizeof(out.res), kernel); }
  case kCurrentNetwork: {
    if (rq.req_len == PONG_SCAN_RECORD_24A446) gModern27Client = true;
    if (st.state < NW_STA_ASSOC) return ENOENT;
    nw_bss_info b; const int count = nw_wifi_bss_count();
    for (int i = 0; i < count; i++) {
      if (!nw_wifi_bss_get(i, &b) && !memcmp(b.bssid, st.bssid, 6)) {
        fill_result(out.res, b,rq.req_len);
        // The scan record is a snapshot; the daemon's current-network answer is what the bars follow,
        // so answer with the live peer signal the station refreshes instead of the sweep's value.
        out.res.rssi = st.signal_dbm;
        out.res.snr = st.signal_dbm > -95 && st.signal_dbm < 0 ? st.signal_dbm + 95 : 0;
        return copy_out(rq, &out.res, sizeof(out.res), kernel);
      }
    }
    // Joined by a join that did not scan first (a network the Settings pane did not list): the access point is not in the scan list, so
    // describe it from the link's own state. Answering "no such network" while associated makes the wireless daemon think the link is gone.
    memset(&b, 0, sizeof b); memcpy(b.bssid, st.bssid, 6); b.ssid_len = st.ssid_len; memcpy(b.ssid, st.ssid, 32); b.freq_mhz = st.freq_mhz; b.signal_dbm = st.signal_dbm;
    b.caps = static_cast<uint16_t>(0x0001 | (gKeyed ? 0x0010 : 0)); b.beacon_int = 100;
    fill_result(out.res, b, rq.req_len);
    out.res.rssi = st.signal_dbm;
    out.res.snr = st.signal_dbm > -95 && st.signal_dbm < 0 ? st.signal_dbm + 95 : 0;
    return copy_out(rq, &out.res, sizeof(out.res), kernel); }
  default: log_unhandled(false, type, rq, kernel); return EOPNOTSUPP;
  }
}

errno_t if_ioctl(ifnet_t, unsigned long cmd, void *data) {
  if(!gLock)return ENXIO;
  switch (cmd) {
  case SIOCGA80211: case SIOCSA80211: {
    apple80211req *rq = static_cast<apple80211req *>(data);
    if(!rq)return EINVAL;
    const uint32_t len = rq->req_len; const int32_t val = rq->req_val;
    const bool set=cmd==SIOCSA80211;
    // A user-page fault must not retain the driver state lock: scan/join
    // completions on the station worker need that lock too. The native
    // user-client tunnel already uses this copy-before/after-lock pattern.
    // A 24A446 scan request is 0x14e8 bytes (PongWifiAbi.h), past the 5120 this path used to
    // accept: the framework reaches the driver by ioctl on this generation, so refusing that
    // length turns every named scan into EINVAL before it is parsed.
    if(len>PONG_SCAN_REQUEST_MAX || (len && !rq->req_data))return EINVAL;
    void *bytes=len?IOMallocZeroData(len):nullptr;
    if(len && !bytes)return ENOMEM;
    struct Buffer {void *p;size_t n;~Buffer(){if(p){bzero(p,n);IOFreeData(p,n);}}} buffer{bytes,len};
    if(set && len && copyin(rq->req_data,bytes,len))return EFAULT;
    apple80211req local=*rq;
    local.req_data=reinterpret_cast<user_addr_t>(bytes);
    lck_mtx_lock(gLock);
    int e=apple80211(set,local,true);
    // every request with its answer, for the first few hundred; then a type's first one only
    static unsigned shown; const int type = rq->req_type; const bool first = type >= 0 && type < 256 && !(gLogged[type / 32] & (1u << (type % 32)));
    if (type >= 0 && type < 256) gLogged[type / 32] |= 1u << (type % 32);
    if (shown < 300 || first) { ++shown; log(6, "wifi-net: request %u: type %d %s len %u val %d -> %d (len %u val %d)", shown, type, set ? "set" : "get", len, val, e, local.req_len, local.req_val); }
    lck_mtx_unlock(gLock);
    if(!e && !set && len) {
      const size_t n=local.req_len<len?local.req_len:len;
      if(n && copyout(bytes,rq->req_data,n))e=EFAULT;
    }
    rq->req_val=local.req_val;rq->req_len=local.req_len;
    return e;
  }
  case SIOCGIFMEDIA: {
    struct ifmediareq *m = static_cast<struct ifmediareq *>(data);
    nw_wifi_status st; nw_wifi_status_get(&st);
    // the framework lists wireless interfaces by this media type
    m->ifm_current = IFM_IEEE80211 | IFM_AUTO; m->ifm_mask = 0; m->ifm_status = IFM_AVALID | (st.state == NW_STA_UP ? IFM_ACTIVE : 0);
    m->ifm_active = IFM_IEEE80211 | IFM_AUTO;
    const int requested=m->ifm_count;
    m->ifm_count = 1;
    // Darwin first asks for the count, then supplies ifm_ulist. Returning
    // count=1 without copying the entry leaves userspace's list uninitialized.
    if (requested > 0 && m->ifm_ulist) {
      const int medium=IFM_IEEE80211 | IFM_AUTO;
      return copyout(&medium, (user_addr_t)m->ifm_ulist, sizeof(medium));
    }
    return 0;
  }
  case SIOCSIFFLAGS: case SIOCSIFMTU: case SIOCADDMULTI: case SIOCDELMULTI: case SIOCSIFADDR: case SIOCSIFMEDIA: return 0;
  default: { static unsigned said; if (said++ < 16) log(6, "wifi-net: interface request %lx not handled", cmd); return EOPNOTSUPP; }
  }
}

// ---- registry entries (see the top of the file in the build: the classes are registered late) ----
}  // namespace

// 22H374's IO80211 library first binds through the interface user client.
// Its selector 0 tunnels the SAME Apple80211 requests as the socket path;
// refusing IOServiceOpen leaves modern CoreWiFi without a usable binding.
// Layout derived from the selected runtime, not an older IO80211 vtable.
struct Apple80211MethodRequest {
  uint32_t command, length;
  uint8_t bytes[0x3c00];
  apple80211req request;
};
static_assert(sizeof(Apple80211MethodRequest)==0x3c30 &&
              __builtin_offsetof(Apple80211MethodRequest,request)==0x3c08,
              "22H374 Apple80211 selector 0 layout");

class Pong80211UserClient : public IOUserClient {
  OSDeclareDefaultStructors(Pong80211UserClient);
  static uint32_t capacity(IOExternalMethodArguments *a) {
    return a->structureOutputDescriptor ? a->structureOutputDescriptorSize : a->structureOutputSize;
  }
  static bool output(IOExternalMethodArguments *a,const void *data,uint32_t bytes) {
    if(bytes>capacity(a))return false;
    if(a->structureOutputDescriptor) {
      // MIG supplies an unwired virtual descriptor for OOL requests.
      // writeBytes walks physical segments; it does not fault/wire pages.
      // Pair ownership locally and finish before returning to the caller.
      auto memory=a->structureOutputDescriptor;
      if(bytes) {
        IOReturn result=memory->prepare(kIODirectionIn);
        if(result!=kIOReturnSuccess)return false;
        const bool copied=memory->writeBytes(0,data,bytes)==bytes;
        memory->complete(kIODirectionIn);
        if(!copied)return false;
      }
      a->structureOutputDescriptorSize=bytes;
    } else {
      if(bytes && !a->structureOutput)return false;
      if(bytes)memcpy(a->structureOutput,data,bytes);
      a->structureOutputSize=bytes;
    }
    return true;
  }
public:
  bool initWithTask(task_t task,void *security,UInt32 type,OSDictionary *properties) override {
    return type==0 && IOUserClient::initWithTask(task,security,type,properties);
  }
  IOReturn clientClose() override { terminate();return kIOReturnSuccess; }
  IOReturn externalMethod(uint32_t selector,IOExternalMethodArguments *a,
      IOExternalMethodDispatch *,OSObject *,void *) override {
    if(!a || a->scalarInputCount || a->scalarOutputCount)return kIOReturnBadArgument;
    const uint64_t inputBytes=a->structureInputDescriptor ?
        a->structureInputDescriptor->getLength() : a->structureInputSize;
    if(selector==1 || selector==7) {
      if(inputBytes || capacity(a)!=1)return kIOReturnBadArgument;
      // Standard ioctl tunnel implemented; Apple's separate fast-path is
      // not implemented. These describe this client, not radio abilities.
      const uint8_t supported=selector==1;
      return output(a,&supported,1)?kIOReturnSuccess:kIOReturnBadArgument;
    }
    if(selector!=0)return kIOReturnUnsupported;
    if(inputBytes!=sizeof(Apple80211MethodRequest) || capacity(a)>0x3c00 || !gLock)
      return kIOReturnBadArgument;
    auto packet=static_cast<Apple80211MethodRequest *>(IOMallocData(sizeof(Apple80211MethodRequest)));
    if(!packet)return kIOReturnNoMemory;
    struct Free {Apple80211MethodRequest *p;~Free(){
      auto bytes=reinterpret_cast<volatile uint8_t *>(p);
      for(size_t i=0;i<sizeof(*p);i++)bytes[i]=0;
      IOFreeData(p,sizeof(*p));}} release{packet};
    if(a->structureInputDescriptor) {
      // The native envelope is 15KiB, larger than MIG's in-band limit.
      // services88 read this descriptor without prepare(), which can reach
      // IOGMD's fatal "not wired for the IODMACommand" path. The pages
      // belong to this one request, never to the radio's DMA arena.
      auto memory=a->structureInputDescriptor;
      IOReturn result=memory->prepare(kIODirectionOut);
      if(result!=kIOReturnSuccess)return result;
      const bool copied=memory->readBytes(0,packet,sizeof(*packet))==sizeof(*packet);
      memory->complete(kIODirectionOut);
      if(!copied)return kIOReturnNotReadable;
    } else {
      if(!a->structureInput)return kIOReturnBadArgument;
      memcpy(packet,a->structureInput,sizeof(*packet));
    }
    if((packet->command!=SIOCGA80211 && packet->command!=SIOCSA80211) ||
       packet->length>sizeof(packet->bytes) ||
       strncmp(packet->request.req_if_name,"en0",sizeof(packet->request.req_if_name)))
      return kIOReturnBadArgument;
    const bool set=packet->command==SIOCSA80211;
    const uint32_t outCapacity=capacity(a);
    // The library puts payload length at +4 and payload at +8. The copied
    // user pointer at +3c28 is never followed. Scalar GETs return req_val;
    // bind's version sanity query instead supplies a 256-byte output only.
    const bool scalar=!set && !packet->length && outCapacity==sizeof(uint32_t);
    apple80211req rq=packet->request;
    rq.req_len=scalar?0:(packet->length ? packet->length : (!set?outCapacity:0));
    if(!set && rq.req_len>outCapacity)return kIOReturnBadArgument;
    rq.req_data=rq.req_len?reinterpret_cast<user_addr_t>(packet->bytes):0;
    int result;
    {
      struct Guard {Guard(){lck_mtx_lock(gLock);}~Guard(){lck_mtx_unlock(gLock);}} guard;
      result=apple80211(set,rq,true);
    }
    static unsigned logged;static uint32_t seen[2][1024/32];
    const unsigned type=static_cast<unsigned>(rq.req_type);
    const bool first=type<1024 && !(__atomic_fetch_or(&seen[set][type/32],1u<<(type%32),__ATOMIC_RELAXED)&(1u<<(type%32)));
    if(__atomic_fetch_add(&logged,1u,__ATOMIC_RELAXED)<96 || first || (set && (rq.req_type==kAssociate || rq.req_type==kCipherKey || rq.req_type==kAuthType)))log(6,"wifi-net: native client type %d %s bytes=%u -> %d",
        rq.req_type,set?"set":"get",packet->length,result);
    // IO80211's wrapper preserves these errno values; do not turn an
    // unsupported request or failed association into a successful result.
    if(result)return static_cast<IOReturn>(result);
    if(set)return output(a,nullptr,0)?kIOReturnSuccess:kIOReturnBadArgument;
    const uint32_t bytes=scalar?sizeof(rq.req_val):(rq.req_len<outCapacity?rq.req_len:outCapacity);
    return output(a,scalar?static_cast<const void *>(&rq.req_val):packet->bytes,bytes)?
        kIOReturnSuccess:kIOReturnBadArgument;
  }
};
OSDefineMetaClassAndStructors(Pong80211UserClient,IOUserClient);
class IO80211Controller : public IOService {OSDeclareDefaultStructors(IO80211Controller);};
OSDefineMetaClassAndStructors(IO80211Controller,IOService);
class IONetworkInterface : public IOService {OSDeclareDefaultStructors(IONetworkInterface);};
OSDefineMetaClassAndStructors(IONetworkInterface,IOService);
class IO80211Interface : public IONetworkInterface {
  OSDeclareDefaultStructors(IO80211Interface);
public:
  IOReturn newUserClient(task_t task,void *security,UInt32 type,OSDictionary *properties,IOUserClient **out) override {
    if(type!=0)return kIOReturnUnsupported;
    char who[32] = "?"; proc_selfname(who, sizeof who);
    log(6, "wifi-net: 80211 user client opened by %s type %u", who, static_cast<unsigned>(type));
    auto client=OSTypeAlloc(Pong80211UserClient);
    if(!client || !client->initWithTask(task,security,type,properties)) {
      OSSafeReleaseNULL(client);return kIOReturnNotPermitted;
    }
    if(!client->attach(this)){client->release();return kIOReturnError;}
    if(!client->start(this)){client->detach(this);client->release();return kIOReturnError;}
    *out=client;return kIOReturnSuccess;
  }
};
OSDefineMetaClassAndStructors(IO80211Interface,IONetworkInterface);

// The network configuration's interface namer waits for a service of this class, opens it and only then publishes that IOKit is quiet;
// everything that lists interfaces (the wireless daemon among them) waits for that. Interfaces here are named when they are made, so the
// naming request it sends is refused; a success would tell it the name was given when nothing was named.
class IONetworkStackUserClient : public IOUserClient {
  OSDeclareDefaultStructors(IONetworkStackUserClient);
 public:
  bool start(IOService *provider) APPLE_KEXT_OVERRIDE {
    if (!IOUserClient::start(provider)) return false;
    char who[32] = "?";
    proc_selfname(who, sizeof who);
    IOService *root = IOService::getServiceRoot();
    log(6, "wifi-net: the network stack was opened by %s; the registry's busy state is %u", who,
        static_cast<unsigned>(root ? root->getBusyState() : 0));
    return true;
  }
  IOReturn setProperties(OSObject *properties) APPLE_KEXT_OVERRIDE {
    static unsigned said;
    if (said++ < 16) {
      char text[200] = "?";
      if (OSSerialize *s = OSSerialize::withCapacity(512)) { if (properties && properties->serialize(s)) strlcpy(text, s->text(), sizeof text); s->release(); }
      log(6, "wifi-net: network stack command %s", text);
      // A registry write carrying pong-wifi-stop asks the interface to quiesce and the station to stop.
      bool stopCommand = false;
      for (const char *q = text; *q && !stopCommand; ++q)
        stopCommand = __builtin_strncmp(q, "pong-wifi-stop", 14) == 0;
      if (stopCommand) {
        log(6, "wifi-net: station stop requested by the network stack client");
        pong_wifi_net_stop(); pong_wifi_station_stop();
      }
    }
    return kIOReturnUnsupported;
  }
  IOReturn clientClose() APPLE_KEXT_OVERRIDE {
    log(6, "wifi-net: the network stack client closed");
    terminate(); return kIOReturnSuccess;
  }
  // The namer may also drive the interface lookup through external methods
  // rather than properties; report them, and refuse a request that would tell
  // the caller an interface was named when nothing was named.
  IOReturn externalMethod(uint32_t selector, IOExternalMethodArguments *arguments,
      IOExternalMethodDispatch *dispatch, OSObject *target, void *reference) APPLE_KEXT_OVERRIDE {
    static unsigned said;
    if (said++ < 8) log(6, "wifi-net: network stack method %u in %u out %u", selector,
        arguments ? arguments->scalarInputCount : 0, arguments ? arguments->scalarOutputCount : 0);
    return kIOReturnUnsupported;
  }
};
OSDefineMetaClassAndStructors(IONetworkStackUserClient, IOUserClient);
class IONetworkStack : public IOService {
  OSDeclareDefaultStructors(IONetworkStack);
 public:
  // The real one names its user client class as a property; do the same so a reader of the registry finds it.
  bool start(IOService *provider) APPLE_KEXT_OVERRIDE {
    if (!IOService::start(provider)) return false;
    setProperty(kIOUserClientClassKey, "IONetworkStackUserClient");
    return true;
  }
  IOReturn newUserClient(task_t task, void *security, UInt32 type, OSDictionary *properties, IOUserClient **handler) APPLE_KEXT_OVERRIDE {
    IONetworkStackUserClient *client = OSTypeAlloc(IONetworkStackUserClient);
    // The 3-argument overload skips IORegistryEntry::init() when getPropertyTable()
    // already reports the global fallback, leaving fRegistryTable null for attach().
    if (!client || !client->initWithTask(task, security, type, properties)) { OSSafeReleaseNULL(client); return kIOReturnNoMemory; }
    if (!client->attach(this)) { client->release(); return kIOReturnError; }
    if (!client->start(this)) { client->detach(this); client->release(); return kIOReturnError; }
    log(6, "wifi-net: the network stack was opened (type %u)", static_cast<unsigned>(type));
    *handler = client; return kIOReturnSuccess;
  }
};
OSDefineMetaClassAndStructors(IONetworkStack, IOService);

namespace {

IOService *publish(IOService *service, IOService *provider, const char *name) {
  if (!service || !service->attach(provider)) { OSSafeReleaseNULL(service); return nullptr; }
  service->setName(name);
  if (!service->start(provider)) { service->detach(provider); service->release(); return nullptr; }
  service->registerService();
  return service;
}
void publish_registry(const char *ifname) {
  IOService *platform = IOService::getPlatform();
  // The real one lives at IOService:/IOResources/IONetworkStack, and the interface namer looks for it there.
  IOService *resources = IOService::getResourceService();
  if (IONetworkStack *stack = OSTypeAlloc(IONetworkStack)) {
    if (!resources || !stack->init() || !publish(stack, resources, "IONetworkStack")) log(3, "wifi-net: the network stack service did not start (resources %d)", resources != nullptr);
    else stack->release(); }
  IO80211Controller *controller = OSTypeAlloc(IO80211Controller);
  IO80211Interface *wlan = OSTypeAlloc(IO80211Interface);
  if (!platform || !controller || !wlan || !controller->init() || !wlan->init()) { OSSafeReleaseNULL(controller); OSSafeReleaseNULL(wlan); log(3, "wifi-net: registry objects not made"); return; }
  if (OSData *mac = OSData::withBytes(gMac, 6)) { controller->setProperty("IOMACAddress", mac); mac->release(); }
  controller->setProperty("IOBuiltin", true);
  // This board already attached and named the real DLIL interface en0.
  // InterfaceNamer must not try to rename it through IONetworkStack.
  controller->setProperty("SelfNamed", true);
  controller = static_cast<IO80211Controller *>(publish(controller, platform, "PongWLANController"));
  if (!controller) { wlan->release(); log(3, "wifi-net: the controller did not start"); return; }
  wlan->setProperty("IOInterfaceName", ifname); wlan->setProperty("BSD Name", ifname); wlan->setProperty("IOInterfaceNamePrefix", "en");
  if (OSNumber *n = OSNumber::withNumber(static_cast<unsigned long long>(IFT_ETHER), 32)) { wlan->setProperty("IOInterfaceType", n); n->release(); }
  if (OSNumber *n = OSNumber::withNumber(0ULL, 32)) { wlan->setProperty("IOInterfaceUnit", n); n->release(); }
  if (OSData *mac = OSData::withBytes(gMac, 6)) {wlan->setProperty("IOMACAddress", mac);mac->release();}
  wlan->setProperty("IOBuiltin", true); wlan->setProperty("IOPrimaryInterface", true); wlan->setProperty("IO80211InterfaceRole", "Infrastructure");
  wlan->setProperty("NativeSandboxGrantProcess","wifid,configd");
  wlan->setProperty("IOUserClientClass","Pong80211UserClient");
  if (!publish(wlan, controller, "PongWLAN")) log(3, "wifi-net: the interface service did not start"); else wlan->release();
  controller->release();
}

// en0's IPv4 addresses and packet counts, for the log.
void log_traffic() {
  if (!gIf) return;
  char text[64] = "none"; ifaddr_t *list = nullptr;
  if (!ifnet_get_address_list_family(gIf, &list, AF_INET) && list) {
    if (list[0]) { struct sockaddr_in a; memset(&a, 0, sizeof a);
      if (!ifaddr_address(list[0], reinterpret_cast<struct sockaddr *>(&a), sizeof a)) { const uint8_t *b = reinterpret_cast<const uint8_t *>(&a.sin_addr); snprintf(text, sizeof text, "%u.%u.%u.%u", b[0], b[1], b[2], b[3]); } }
    ifnet_free_address_list(list); }
  struct ifnet_stats_param stats; memset(&stats, 0, sizeof stats); ifnet_stat(gIf, &stats);
  char tx[160]; nw_wifi_tx_reasons(tx, sizeof tx);
  log(6, "wifi-net: en0 address %s, packets in %llu out %llu; frames to the stack %u, refused %u (last %d)", text, static_cast<unsigned long long>(stats.packets_in),
      static_cast<unsigned long long>(stats.packets_out), gRxFrames, gRxErrors, gRxLastError);
  log(6, "wifi-net: tx %s", tx);
  log(6, "wifi-net: in arp %u ip4 %u dhcp %u ip6 %u other %u", gKindsIn.arp, gKindsIn.ip4, gKindsIn.dhcp, gKindsIn.ip6, gKindsIn.other);
  log(6, "wifi-net: out arp %u ip4 %u dhcp %u ip6 %u other %u", gKindsOut.arp, gKindsOut.ip4, gKindsOut.dhcp, gKindsOut.ip6, gKindsOut.other);
  log(6, "wifi-net: tcp443 in %u out %u, dns in %u out %u", gKindsIn.https, gKindsOut.https, gKindsIn.dns, gKindsOut.dns);
  log(6, "wifi-net: input stalls %u, kicks %u, cleared after a kick %u, longest %u s", gStall.count, gStall.kicks, gStall.cleared, gStall.longest);
  log(6, "wifi-net: rx no buffer %u, chained %u, longest frame %u", gRxNoBuffer, gRxChains, gRxLongest);
  IOService *root = IOService::getServiceRoot();
  log(6, "wifi-net: registry busy state %u", root ? static_cast<unsigned>(root->getBusyState()) : 0);
}

}  // namespace

extern "C" void pong_wifi_net_diagnostics(void) { log_traffic(); }
extern "C" bool pong_wifi_net_has_ipv4(void) {
  if (!gIf) return false;
  ifaddr_t *list = nullptr; bool valid = false;
  if (!ifnet_get_address_list_family(gIf, &list, AF_INET) && list) {
    for (unsigned i = 0; list[i]; ++i) {
      struct sockaddr_in a; memset(&a, 0, sizeof a);
      if (ifaddr_address(list[i], reinterpret_cast<struct sockaddr *>(&a), sizeof a)) continue;
      const uint8_t *b = reinterpret_cast<const uint8_t *>(&a.sin_addr);
      if (b[0] && b[0] != 127 && b[0] < 224 && !(b[0] == 169 && b[1] == 254)) valid = true;
    }
    ifnet_free_address_list(list);
  }
  return valid;
}

/* The test asks the station to leave by itself, so nothing else may be relied on
 * to report the edge: the address that configd installed before the disconnect
 * would otherwise outlive the link and look like the new association's. */
extern "C" void pong_wifi_net_link_down(void) { post_link(false); }
/* True only while the lease tracker holds an acknowledgement it witnessed after
 * the last link edge, which is what makes a reconnected address fresh. */
extern "C" bool pong_wifi_net_has_lease(void) {
  if (!gLock) return false;
  lck_mtx_lock(gLock);
  const bool live = pong_wifi_lease_snapshot(&gLease, lease_clock()).version != 0;
  lck_mtx_unlock(gLock);
  return live;
}
extern "C" void pong_wifi_net_lease_counters(unsigned long long *link, unsigned long long *sequence) {
  if (!gLock) { *link = 0; *sequence = 0; return; }
  lck_mtx_lock(gLock);
  *link = gLease.link; *sequence = gLease.sequence;
  lck_mtx_unlock(gLock);
}

// Install worker callbacks before nw_wifi_start. The interface and its MAC
// are published only after the real station is ready. RX already drops
// frames before gIf exists; those buffers remain owned by the station.
extern "C" bool pong_wifi_net_prepare(void) {
  if (!gGrp) gGrp = lck_grp_alloc_init("pong-wifi-net", LCK_GRP_ATTR_NULL);
  if (!gGrp) return false;
  if (!gLock) gLock = lck_mtx_alloc_init(gGrp, LCK_ATTR_NULL);
  if (!gLock) return false;
  if (!gNotifications) gNotifications=thread_call_allocate(deliver_notifications,nullptr);
  if (!gNotifications) return false;
  nw_wifi_set_events(&gEvents);
  return true;
}

// Failure completes outstanding asynchronous requests; wifid must not wait
// indefinitely for scan/join events from a stopped firmware dispatcher.
extern "C" void pong_wifi_net_failed(void) {
  if (!gLock) return;
  lck_mtx_lock(gLock);
  __atomic_store_n(&gFailed,true,__ATOMIC_RELEASE); gPower = false;
  bool scanning = gScanning != 0;
  gScanning = 0; gScanCursor = 0; gAssocResult = kAssocFailed;
  if (gCachedScan) thread_call_cancel(gCachedScan);
  pong_wifi_notification_reset(&gNotificationQueue);
  if(gIf) { pong_wifi_notification event={NotifyFailed,scanning?1:0,0,0};queue_notification_locked(event); }
  lck_mtx_unlock(gLock);
}

// The teardown order the wiring guide asks for is: stop accepting requests,
// cancel the asynchronous work, then stop the station component. The last
// step runs on the platform worker, which calls nw_wifi_stop when asked to.
// The DMA arena is the one thing that cannot be released without a reset.
extern "C" void pong_wifi_net_stop(void) {
  if (!gLock) return;
  lck_mtx_lock(gLock);
  __atomic_store_n(&gFailed,true,__ATOMIC_RELEASE); gPower = false;
  gScanning = 0; gScanCursor = 0; gAssocResult = kAssocFailed;
  if (gCachedScan) thread_call_cancel(gCachedScan);
  pong_wifi_notification_reset(&gNotificationQueue);
  lck_mtx_unlock(gLock);
  log(6, "wifi-net: interface quiesced; no new scan or join is accepted");
}

// Called once the module has a station interface and a hardware address.
extern "C" void pong_wifi_net_start(const uint8_t mac[6]) {
  if (gIf) return;
  if (!pong_wifi_net_prepare()) { log(3, "wifi-net: event setup unavailable"); return; }
  memcpy(gMac, mac, 6);
  uint32_t diagnostic=0;gProgressDiagnostic=PE_parse_boot_argn("pong_wifi_diag",&diagnostic,sizeof diagnostic)&&diagnostic==1;
  uint32_t test = 0, cycle = 0;
  gCycleTest = PE_parse_boot_argn("pong_wifi_test", &test, sizeof(test)) && test == 1 &&
      PE_parse_boot_argn("pong_wifi_cycle", &cycle, sizeof(cycle)) && cycle == 1;
  // WPA3 feasibility (parked): a bare sae argument arms one SAE-sized authentication frame and costs four bytes of
  // the 607-byte command line. sae=2 would pick group 20, which the line cannot afford at the moment.
  uint32_t sae = 0;
  if (PE_parse_boot_argn("sae", &sae, sizeof(sae)) && nw_wifi_sae_probe) nw_wifi_sae_probe(sae == 2 ? 20 : 19);
  struct ifnet_init_eparams p; memset(&p, 0, sizeof p);
  p.ver = IFNET_INIT_CURRENT_VERSION; p.len = sizeof p; p.flags = IFNET_INIT_LEGACY | IFNET_INIT_NX_NOAUTO; p.name = "en"; p.unit = 0; p.family = IFNET_FAMILY_ETHERNET; p.subfamily = IFNET_SUBFAMILY_WIFI; p.type = IFT_ETHER;
  p.output = if_output; p.demux = ether_demux; p.add_proto = ether_add_proto; p.del_proto = ether_del_proto; p.check_multi = ether_check_multi; p.framer = ether_frameout;
  p.ioctl = if_ioctl; p.event = if_event_stub; p.set_bpf_tap = if_set_bpf_tap; static const uint8_t bcast[6] = { 0xff, 0xff, 0xff, 0xff, 0xff, 0xff }; p.broadcast_addr = bcast; p.broadcast_len = 6;
  // Without NX_NOAUTO the stack puts a compatibility nexus in front of a Wi-Fi "en" interface, and its input no longer goes through the
  // interface's own input thread.
  ifnet_t ifp = nullptr; errno_t e = ifnet_allocate_extended(&p, &ifp);
  if (e || !ifp) { log(3, "wifi-net: ifnet allocation failed: %d", e); return; }
  ifnet_set_mtu(ifp, 1500); ifnet_set_flags(ifp, IFF_BROADCAST | IFF_SIMPLEX | IFF_MULTICAST, 0xffff); ifnet_set_baudrate(ifp, 54000000ULL);
  ifnet_set_hdrlen(ifp, 14); ifnet_set_addrlen(ifp, 6); ifnet_set_eflags(ifp, IFEF_ENQUEUE_MULTI, IFEF_ENQUEUE_MULTI);
  e = ifnet_attach(ifp, nullptr);
  if (e) { log(3, "wifi-net: ifnet attach failed: %d", e); ifnet_release(ifp); return; }
  ifnet_set_lladdr(ifp, mac, 6);
  // A driver of its own interface attaches the packet filter itself: the DHCP client sends through it while the interface has no address.
  e = bpf_attach(ifp, DLT_EN10MB, 14, nullptr, nullptr); if (e) log(3, "wifi-net: packet filter attach failed: %d", e);
  gIf = ifp; ifnet_set_flags(ifp, IFF_UP, IFF_UP);
  publish_registry("en0");
  log(6, "wifi-net: en0 is up, hardware address %02x:%02x:%02x:%02x:%02x:%02x, capabilities 0x%x", mac[0], mac[1], mac[2], mac[3], mac[4], mac[5],
      ifnet_capabilities_enabled(ifp));
}
