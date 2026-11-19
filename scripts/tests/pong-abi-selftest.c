/* Host self-test for the framework ABI shapes in PongWifiAbi.h. Built and run by
 * scripts/tests/test-pong-abi.py; it needs no kernel header, so it runs on the build host. */
#include <stdio.h>
#include <string.h>
#include "PongWifiAbi.h"
#include "PongWifiScanPolicy.h"

static unsigned checks, failed;
#define CHECK(cond, what) do { checks++; if (!(cond)) { failed++; printf("FAIL: %s (line %d)\n", what, __LINE__); } } while (0)

static void put32(uint8_t *at, uint32_t v) { memcpy(at, &v, 4); }

int main(void)
{
    /* The element room follows the request, never the record: a client that asked for the
     * 22H374 count must not be told to read 2048 element bytes past what it received. */
    CHECK(pong_scan_elements_room(PONG_SCAN_RECORD_24A446) == PONG_SCAN_ELEMENTS_BYTES, "the 24A446 record has room for 2048 element bytes");
    CHECK(pong_scan_elements_room(PONG_SCAN_RECORD_22H374) == 1024, "the 22H374 record has room for 1024");
    CHECK(pong_scan_elements_room(PONG_SCAN_ELEMENTS_OFFSET) == 0, "a request that ends at the element offset has no room");
    CHECK(pong_scan_elements_room(64) == 0, "a short request has no room");
    CHECK(pong_scan_elements_room(0xffffffffu) == PONG_SCAN_ELEMENTS_BYTES, "the room is capped at the array");

    /* The association completion the newer framework dereferences without a length check. */
    CHECK(sizeof(struct pong_assoc_event27) == 540, "the 24A446 completion event is 540 bytes");
    CHECK(offsetof(struct pong_assoc_event27, result) == 0x214, "the result sits at 0x214");
    CHECK(offsetof(struct pong_assoc_event27, has_result) == 0x218, "its validity flag sits at 0x218");

    /* Association requests: the reference port's three layouts, checked by the host compiler. */
    CHECK(sizeof(struct pong_assoc_parameters) == 0x7c, "the network prefix is 0x7c bytes");
    CHECK(offsetof(struct pong_assoc_parameters, key_length) == 0x30 && offsetof(struct pong_assoc_parameters, key_cipher) == 0x34, "key length and cipher sit at 0x30 and 0x34");
    CHECK(offsetof(struct pong_assoc_parameters, key) == 0x3c, "the key starts at 0x3c of the prefix");
    CHECK(sizeof(struct pong_assoc_request_legacy) == 0x250 && offsetof(struct pong_assoc_request_legacy, network) == 0x0c, "the legacy request is 0x250 bytes with the network at 0x0c");
    CHECK(sizeof(struct pong_assoc_request_24a446) == 0x290 && offsetof(struct pong_assoc_request_24a446, network) == 0x10, "the 24A446 request is 0x290 bytes with the network at 0x10");
    CHECK(offsetof(struct pong_assoc_request_24a446, network) + offsetof(struct pong_assoc_parameters, ssid_length) == 0x10 &&
          offsetof(struct pong_assoc_request_24a446, network) + offsetof(struct pong_assoc_parameters, bssid) == 0x34, "ssid length and bssid sit at 0x10 and 0x34");
    CHECK(offsetof(struct pong_assoc_request_24a446, network) + offsetof(struct pong_assoc_parameters, key) == 0x4c &&
          offsetof(struct pong_assoc_request_24a446, network) + offsetof(struct pong_assoc_parameters, key) + 64 == PONG_ASSOC_FIELDS_BYTES, "the 24A446 key ends at the field limit");
    CHECK(sizeof(struct pong_assoc_request_22h374) == PONG_ASSOC_REQUEST_22H374 &&
          offsetof(struct pong_assoc_request_22h374, network) + offsetof(struct pong_assoc_parameters, key) == 0x4c, "the 22H374 request keeps the same field offsets");

    /* Card capabilities: the two scan bits decide whether a named scan reaches this driver. */
    uint8_t caps[PONG_WIFI_CAPS_BYTES];
    pong_wifi_caps_fill(caps);
    CHECK(sizeof caps == 12, "the 24A446 capability answer is twelve bytes");
    CHECK((caps[PONG_WIFI_CAP_NAMED_SCAN / 8] >> (PONG_WIFI_CAP_NAMED_SCAN % 8)) & 1, "a scan that names networks is advertised");
    CHECK((caps[PONG_WIFI_CAP_SCAN_DONE_EVENT / 8] >> (PONG_WIFI_CAP_SCAN_DONE_EVENT % 8)) & 1, "the framework is told to wait for the scan-done event");
    CHECK(caps[0] & 0x04, "AES is still advertised");

    /* Request 86: one name and no wildcard is probed by name. */
    static uint8_t req[PONG_SCAN_MULTIPLE_BYTES];
    uint32_t type = 0, length = 0;
    const uint8_t *ssid = 0;
    memset(req, 0, sizeof req);
    put32(req + PONG_SCAN_SSID_COUNT, 1);
    put32(req + PONG_SCAN_SSIDS + 4, 10);
    memcpy(req + PONG_SCAN_SSIDS + 8, "Emilelu_5G", 10);
    put32(req + PONG_SCAN_TYPE, PONG_SCAN_TYPE_CACHED);
    CHECK(pong_scan_multiple_parse(req, sizeof req, &type, &ssid, &length) == 0, "a one-name request parses");
    CHECK(type == PONG_SCAN_TYPE_CACHED, "the scan type is read from 0x200");
    CHECK(length == 10 && ssid == req + PONG_SCAN_SSIDS + 8, "the name is the one entry's name");

    /* A wildcard entry means every network, so the single name is not a name to probe. */
    put32(req + PONG_SCAN_SSID_COUNT, 2);
    put32(req + PONG_SCAN_SSIDS + PONG_SCAN_SSID_ENTRY + 4, 0);
    CHECK(pong_scan_multiple_parse(req, sizeof req, &type, &ssid, &length) == 0, "a name plus a wildcard parses");
    CHECK(ssid == 0 && length == 0, "a wildcard keeps the scan on every network");

    /* Bounds: too many names, a name longer than 32 bytes, a request that ends too early. */
    put32(req + PONG_SCAN_SSID_COUNT, PONG_SCAN_SSID_MAX + 1);
    CHECK(pong_scan_multiple_parse(req, sizeof req, &type, &ssid, &length) == -1, "more names than the request can carry is refused");
    put32(req + PONG_SCAN_SSID_COUNT, 1);
    put32(req + PONG_SCAN_SSIDS + 4, 33);
    CHECK(pong_scan_multiple_parse(req, sizeof req, &type, &ssid, &length) == -1, "a name longer than 32 bytes is refused");
    put32(req + PONG_SCAN_SSIDS + 4, 10);
    CHECK(pong_scan_multiple_parse(req, PONG_SCAN_TYPE, &type, &ssid, &length) == -1, "a request shorter than its scan type is refused");
    CHECK(pong_scan_multiple_parse(NULL, sizeof req, &type, &ssid, &length) == -1, "no request is refused");

    /* Channels: both bands, the 14th exception, and a band this driver does not report. */
    CHECK(pong_scan_channel_mhz(1, PONG_SCAN_CHANNEL_2GHZ) == 2412, "channel 1 is 2412 MHz");
    CHECK(pong_scan_channel_mhz(14, PONG_SCAN_CHANNEL_2GHZ) == 2484, "channel 14 is 2484 MHz");
    CHECK(pong_scan_channel_mhz(15, PONG_SCAN_CHANNEL_2GHZ) == 0, "channel 15 is not a 2.4 GHz channel");
    CHECK(pong_scan_channel_mhz(48, PONG_SCAN_CHANNEL_5GHZ) == 5240, "channel 48 is 5240 MHz");
    CHECK(pong_scan_channel_mhz(0, PONG_SCAN_CHANNEL_5GHZ) == 0, "channel 0 is not a channel");
    CHECK(pong_scan_channel_mhz(36, 0) == 0, "a channel with no band flag is not reported");

    /* The frequency list: distinct, in order, and empty whenever the request cannot be trusted. */
    uint32_t mhz[PONG_SCAN_FREQUENCIES_MAX];
    static uint8_t one[0x400];
    memset(one, 0, sizeof one);
    put32(one + PONG_SCAN_ONE_CHANNEL_COUNT, 3);
    put32(one + PONG_SCAN_ONE_CHANNELS + 4, 1);  put32(one + PONG_SCAN_ONE_CHANNELS + 8, PONG_SCAN_CHANNEL_2GHZ);
    put32(one + PONG_SCAN_ONE_CHANNELS + 16, 48); put32(one + PONG_SCAN_ONE_CHANNELS + 20, PONG_SCAN_CHANNEL_5GHZ);
    put32(one + PONG_SCAN_ONE_CHANNELS + 28, 48); put32(one + PONG_SCAN_ONE_CHANNELS + 32, PONG_SCAN_CHANNEL_5GHZ);
    uint32_t n = pong_scan_frequencies(one, sizeof one, PONG_SCAN_ONE_CHANNEL_COUNT, PONG_SCAN_ONE_CHANNELS, mhz);
    CHECK(n == 2 && mhz[0] == 2412 && mhz[1] == 5240, "the list is distinct and in order");
    put32(one + PONG_SCAN_ONE_CHANNEL_COUNT, 0);
    CHECK(pong_scan_frequencies(one, sizeof one, PONG_SCAN_ONE_CHANNEL_COUNT, PONG_SCAN_ONE_CHANNELS, mhz) == 0, "no channels means every band");
    put32(one + PONG_SCAN_ONE_CHANNEL_COUNT, PONG_SCAN_CHANNELS_READ + 1);
    CHECK(pong_scan_frequencies(one, sizeof one, PONG_SCAN_ONE_CHANNEL_COUNT, PONG_SCAN_ONE_CHANNELS, mhz) == 0, "more channels than are read is every band");
    put32(one + PONG_SCAN_ONE_CHANNEL_COUNT, 3);
    CHECK(pong_scan_frequencies(one, PONG_SCAN_ONE_CHANNELS + 12, PONG_SCAN_ONE_CHANNEL_COUNT, PONG_SCAN_ONE_CHANNELS, mhz) == 0, "a list past the bytes copied is every band");

    /* The scan policy: a joined link keeps the radio on the access point's channel while the join runs
     * and for the settle window, and a network not heard for a minute leaves the list. */
    struct pong_scan_air air;
    memset(&air, 0, sizeof air);
    uint32_t chans[2] = { 2412, 5240 };
    CHECK(pong_scan_held_stale(PONG_SCAN_HELD_MS) == 0, "a record at the held limit is still fresh");
    CHECK(pong_scan_held_stale(PONG_SCAN_HELD_MS + 1) == 1, "a record past the limit is stale");
    CHECK(pong_scan_on_air(&air, PONG_LINK_NONE, 0, 1, NULL, 0, 1000) == 1, "a scan with no link goes on the air");
    CHECK(pong_scan_on_air(&air, PONG_LINK_JOINING, 0, 1, chans, 2, 1000) == 0, "a scan while joining stays off the air");
    CHECK(pong_scan_on_air(&air, PONG_LINK_UP, PONG_SCAN_LINK_SETTLE_MS - 1, 1, chans, 2, 1000) == 0, "a scan inside the settle window stays off the air");
    CHECK(pong_scan_on_air(&air, PONG_LINK_UP, PONG_SCAN_LINK_SETTLE_MS, 1, chans, 2, 1000) == 1, "a settled link scans a channel it has not visited");
    CHECK(pong_scan_on_air(&air, PONG_LINK_UP, PONG_SCAN_LINK_SETTLE_MS, 0, chans, 2, 1000) == 1, "with nothing held a scan always goes on the air");
    pong_scan_air_mark(&air, chans, 2, 5000);
    CHECK(pong_scan_air_recent(air.at_ms[0], 5000 + PONG_SCAN_RESCAN_MS - 1) == 1, "a channel scanned a moment ago is recent");
    CHECK(pong_scan_on_air(&air, PONG_LINK_UP, 60000, 1, chans, 2, 5000 + PONG_SCAN_RESCAN_MS) == 1, "after the rescan window the channel is visited again");
    CHECK(pong_scan_on_air(&air, PONG_LINK_UP, 60000, 1, chans, 1, 5100) == 0, "the same channel is not rescanned inside the window");
    pong_scan_air_mark(&air, NULL, 0, 9000);
    CHECK(pong_scan_on_air(&air, PONG_LINK_UP, 60000, 1, chans, 2, 9500) == 0, "a full-band scan covers every channel briefly");

    printf("%u checks passed, %u failed\n", checks, failed);
    return failed ? 1 : 0;
}
