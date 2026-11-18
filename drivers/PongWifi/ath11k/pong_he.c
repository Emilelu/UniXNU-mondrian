/* HE (802.11ax) capability elements for the Pong station: encoding, parsing and the MCS/NSS narrowing.
 * See pong_he.h for the references and for why this file carries no kernel header. */
#include "pong_he.h"

static unsigned popcount8(unsigned v) { unsigned n = 0; while (v) { n += v & 1u; v >>= 1; } return n; }

unsigned pong_he_mcs_size(const uint8_t phy[11])
{
    unsigned n = 4;
    if (phy[0] & PONG_HE_WIDTH_160) n += 4;
    if (phy[0] & PONG_HE_WIDTH_80P80) n += 4;
    return n;
}

unsigned pong_he_ppe_size(uint8_t hdr, const uint8_t phy[11])
{
    if (!(phy[6] & PONG_HE_PPE_PRESENT)) return 0;
    /* A seven-bit header: the RU index bitmask (bits 3-6) counts the RUs, bits 0-2 hold NSS - 1. Each pair of
     * (RU, NSS) entries carries a 6-bit threshold, and the header itself rounds the field up to a byte. */
    unsigned n = popcount8(hdr & 0x78u);
    n *= 1u + (hdr & 0x07u);
    n = n * 6u + 7u;
    return (n + 7u) / 8u;
}

const uint8_t *pong_he_find_ie(const uint8_t *ies, unsigned len, uint8_t id, unsigned *body_len)
{
    unsigned i = 0;
    if (!ies) return 0;
    while (i + 2 <= len) {
        const unsigned eid = ies[i], elen = ies[i + 1];
        if (i + 2 + elen > len) return 0;   /* a truncated element ends the walk; nothing after it can be trusted */
        if (eid == id) { if (body_len) *body_len = elen; return ies + i + 2; }
        i += 2 + elen;
    }
    return 0;
}

const uint8_t *pong_he_find_ext(const uint8_t *ies, unsigned len, uint8_t extid, unsigned *body_len)
{
    unsigned i = 0;
    if (!ies) return 0;
    while (i + 2 <= len) {
        const unsigned eid = ies[i], elen = ies[i + 1];
        if (i + 2 + elen > len) return 0;
        if (eid == PONG_HE_ELEM_ID && elen >= 1 && ies[i + 2] == extid) {
            if (body_len) *body_len = elen - 1;
            return ies + i + 3;
        }
        i += 2 + elen;
    }
    return 0;
}

static uint16_t read_le16(const uint8_t *p) { return (uint16_t)(p[0] | (p[1] << 8)); }
static void write_le16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)(v & 0xff); p[1] = (uint8_t)(v >> 8); }

int pong_he_parse_cap(const uint8_t *body, unsigned len, struct pong_he_cap *out)
{
    unsigned need, w = 0;
    if (!body || !out || len < PONG_HE_CAP_FIXED) return -1;
    out->mac[0] = 0; out->ppe_len = 0;
    for (unsigned i = 0; i < 6; i++) out->mac[i] = body[i];
    for (unsigned i = 0; i < 11; i++) out->phy[i] = body[6 + i];
    for (unsigned i = 0; i < 6; i++) out->mcs[i] = 0;
    need = PONG_HE_CAP_FIXED + pong_he_mcs_size(out->phy);
    if (len < need) return -1;
    out->mcs[w++] = read_le16(body + PONG_HE_CAP_FIXED);
    out->mcs[w++] = read_le16(body + PONG_HE_CAP_FIXED + 2);
    if (out->phy[0] & PONG_HE_WIDTH_160) { out->mcs[2] = read_le16(body + PONG_HE_CAP_FIXED + 4); out->mcs[3] = read_le16(body + PONG_HE_CAP_FIXED + 6); }
    if (out->phy[0] & PONG_HE_WIDTH_80P80) {
        const unsigned base = PONG_HE_CAP_FIXED + (out->phy[0] & PONG_HE_WIDTH_160 ? 8u : 4u);
        out->mcs[4] = read_le16(body + base); out->mcs[5] = read_le16(body + base + 2);
    }
    if (out->phy[6] & PONG_HE_PPE_PRESENT) {
        if (len < need + 1) return -1;
        out->ppe_len = pong_he_ppe_size(body[need], out->phy);
        if (out->ppe_len > PONG_HE_PPE_MAX || len < need + out->ppe_len) return -1;
        for (unsigned i = 0; i < out->ppe_len; i++) out->ppe[i] = body[need + i];
    }
    return 0;
}

unsigned pong_he_cap_ie_len(const struct pong_he_cap *cap)
{
    if (!cap) return 0;
    return 2 + 1 + PONG_HE_CAP_FIXED + pong_he_mcs_size(cap->phy) + cap->ppe_len;
}

int pong_he_write_cap_ie(const struct pong_he_cap *cap, uint8_t *out, unsigned out_len)
{
    unsigned elem, total, at;
    if (!cap || !out) return 0;
    elem = 1 + PONG_HE_CAP_FIXED + pong_he_mcs_size(cap->phy) + cap->ppe_len;   /* extension id counts in the length */
    total = 2 + elem;
    if (elem > 255 || out_len < total) return 0;
    out[0] = PONG_HE_ELEM_ID; out[1] = (uint8_t)elem; out[2] = PONG_HE_EXT_CAP;
    for (unsigned i = 0; i < 6; i++) out[3 + i] = cap->mac[i];
    for (unsigned i = 0; i < 11; i++) out[9 + i] = cap->phy[i];
    at = 20;
    write_le16(out + at, cap->mcs[0]); at += 2;
    write_le16(out + at, cap->mcs[1]); at += 2;
    if (cap->phy[0] & PONG_HE_WIDTH_160) { write_le16(out + at, cap->mcs[2]); at += 2; write_le16(out + at, cap->mcs[3]); at += 2; }
    if (cap->phy[0] & PONG_HE_WIDTH_80P80) { write_le16(out + at, cap->mcs[4]); at += 2; write_le16(out + at, cap->mcs[5]); at += 2; }
    for (unsigned i = 0; i < cap->ppe_len; i++) out[at + i] = cap->ppe[i];
    return (int)total;
}

/* One 16-bit map holds eight 2-bit stream fields; the peer's transmit field may not exceed our receive field and the
 * peer's receive field may not exceed our transmit field. A field that was not supported stays unsupported. */
static uint16_t intersect16(uint16_t own, uint16_t peer)
{
    uint16_t r = 0;
    for (unsigned i = 0; i < 8; i++) {
        const unsigned o = (own >> (2 * i)) & 3u, p = (peer >> (2 * i)) & 3u;
        unsigned v = p;
        if (p != PONG_HE_MCS_NOT_SUPPORTED) v = (o == PONG_HE_MCS_NOT_SUPPORTED) ? PONG_HE_MCS_NOT_SUPPORTED : (o < p ? o : p);
        r |= (uint16_t)(v << (2 * i));
    }
    return r;
}

void pong_he_narrow(const struct pong_he_cap *own, struct pong_he_cap *peer)
{
    if (!own || !peer) return;
    /* The peer receives with our transmit capability and transmits with our receive capability: the two maps cross. */
    peer->mcs[0] = intersect16(own->mcs[1], peer->mcs[0]);
    peer->mcs[1] = intersect16(own->mcs[0], peer->mcs[1]);
    if (peer->phy[0] & PONG_HE_WIDTH_160) {
        if (own->phy[0] & PONG_HE_WIDTH_160) {
            peer->mcs[2] = intersect16(own->mcs[3], peer->mcs[2]);
            peer->mcs[3] = intersect16(own->mcs[2], peer->mcs[3]);
        } else {
            /* We do not run 160 MHz: the peer's maps go away and the bit with them, which shortens the element. */
            peer->phy[0] = (uint8_t)(peer->phy[0] & ~PONG_HE_WIDTH_160);
            peer->mcs[2] = 0xffff; peer->mcs[3] = 0xffff;
        }
    }
    if (peer->phy[0] & PONG_HE_WIDTH_80P80) {
        if (own->phy[0] & PONG_HE_WIDTH_80P80) {
            peer->mcs[4] = intersect16(own->mcs[5], peer->mcs[4]);
            peer->mcs[5] = intersect16(own->mcs[4], peer->mcs[5]);
        } else {
            peer->phy[0] = (uint8_t)(peer->phy[0] & ~PONG_HE_WIDTH_80P80);
            peer->mcs[4] = 0xffff; peer->mcs[5] = 0xffff;
        }
    }
}

int pong_he_parse_oper(const uint8_t *body, unsigned len, struct pong_he_oper *out)
{
    if (!body || !out || len < 6) return -1;
    out->params = (uint32_t)body[0] | ((uint32_t)body[1] << 8) | ((uint32_t)body[2] << 16) | ((uint32_t)body[3] << 24);
    out->nss_set = read_le16(body + 4);
    return 0;
}
