/* HE (802.11ax) capability elements for the Pong station.
 *
 * The station announces what its radio can do (HE Capabilities element, 802.11ax-2021 9.4.2.248) and describes the
 * access point with what the access point announced, narrowed to the radio: the peer's transmit MCS map is bounded by
 * our receive map and the peer's receive map by our transmit map, and a channel width we do not run loses both its
 * map and its capability bit (802.11ax-2021 26.17.3.2). The HE Operation element (9.4.2.249) carries the peer's
 * parameters that the driver forwards to the firmware.
 *
 * The codec works on element bytes only and includes no kernel header, so the encoding and the narrowing are
 * unit-tested on the host (scripts/tests/test-pong-he.py); the kernel types stay in the station code. */
#ifndef PONG_HE_H
#define PONG_HE_H

#include <stdint.h>

#define PONG_HE_ELEM_ID 255   /* WLAN_EID_EXTENSION */
#define PONG_HE_EXT_CAP 35    /* WLAN_EID_EXT_HE_CAPABILITY */
#define PONG_HE_EXT_OPER 36   /* WLAN_EID_EXT_HE_OPERATION */

#define PONG_HE_CAP_FIXED 17  /* MAC capabilities 6 bytes + PHY capabilities 11 bytes */
#define PONG_HE_MCS_MAX 12    /* 80 MHz, 160 MHz and 80+80 MHz maps, 4 bytes each */
#define PONG_HE_PPE_MAX 25

/* HE PHY capabilities byte 0: the widths that change the size of the MCS/NSS field. */
#define PONG_HE_WIDTH_160 0x08
#define PONG_HE_WIDTH_80P80 0x10
/* HE PHY capabilities byte 6: the PPE threshold field is present. */
#define PONG_HE_PPE_PRESENT 0x80

/* IEEE80211_HE_MCS_NOT_SUPPORTED: the 2-bit value saying a stream count is not supported. */
#define PONG_HE_MCS_NOT_SUPPORTED 3

struct pong_he_cap {
    uint8_t mac[6];
    uint8_t phy[11];
    /* rx/tx maps in the order the element encodes them: 80 MHz, then 160 MHz and 80+80 MHz when their bits are set. */
    uint16_t mcs[6];
    uint8_t ppe[PONG_HE_PPE_MAX];
    unsigned ppe_len;
};

struct pong_he_oper {
    uint32_t params;
    uint16_t nss_set;
};

/* Element walkers: return the body after the element id (and, for the extension form, after the extension id). */
const uint8_t *pong_he_find_ie(const uint8_t *ies, unsigned len, uint8_t id, unsigned *body_len);
const uint8_t *pong_he_find_ext(const uint8_t *ies, unsigned len, uint8_t extid, unsigned *body_len);

/* Sizes the element's own fields imply; both accept a truncated body length and report the required size. */
unsigned pong_he_mcs_size(const uint8_t phy[11]);
unsigned pong_he_ppe_size(uint8_t hdr, const uint8_t phy[11]);

/* Parse and encode the HE Capabilities element body. Returns 0 / the element length in bytes, -1 / 0 on a bad body. */
int pong_he_parse_cap(const uint8_t *body, unsigned len, struct pong_he_cap *out);
unsigned pong_he_cap_ie_len(const struct pong_he_cap *cap);
int pong_he_write_cap_ie(const struct pong_he_cap *cap, uint8_t *out, unsigned out_len);

/* Narrow the access point's capability to what the local radio can run with it, in place. */
void pong_he_narrow(const struct pong_he_cap *own, struct pong_he_cap *peer);

int pong_he_parse_oper(const uint8_t *body, unsigned len, struct pong_he_oper *out);

#endif
