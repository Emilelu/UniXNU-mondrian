/* Host self-test for the HE capability codec. Built and run by scripts/tests/test-pong-he.py; it links no kernel
 * header and no board code, so it can run on the build host as part of the offline verification step. */
#include <stdio.h>
#include <string.h>
#include "pong_he.h"

static unsigned checks, failed;
#define CHECK(cond, what) do { checks++; if (!(cond)) { failed++; printf("FAIL: %s (line %d)\n", what, __LINE__); } } while (0)

static void put_cap_body(uint8_t *b, unsigned *len, const uint8_t mac[6], const uint8_t phy[11], const uint16_t mcs[6], unsigned mcs_bytes)
{
    unsigned at = PONG_HE_CAP_FIXED;
    memset(b, 0, 64);
    memcpy(b, mac, 6); memcpy(b + 6, phy, 11);
    for (unsigned i = 0; i < mcs_bytes / 2; i++) { b[at + 2 * i] = (uint8_t)(mcs[i] & 0xff); b[at + 2 * i + 1] = (uint8_t)(mcs[i] >> 8); }
    *len = at + mcs_bytes;
}

int main(void)
{
    uint8_t phy[11] = {0}, mac[6] = {0x01, 0x02, 0x03, 0x04, 0x05, 0x06};
    uint16_t mcs[6] = {0x1111, 0x2222, 0x3333, 0x4444, 0x5555, 0x6666};
    uint8_t body[64], elem[64];
    unsigned len = 0, blen = 0;

    /* Sizes follow the capability bits. */
    CHECK(pong_he_mcs_size(phy) == 4, "no width bits means one 4-byte map pair");
    phy[0] = PONG_HE_WIDTH_160;
    CHECK(pong_he_mcs_size(phy) == 8, "160 MHz adds 4 bytes");
    phy[0] = (uint8_t)(PONG_HE_WIDTH_160 | PONG_HE_WIDTH_80P80);
    CHECK(pong_he_mcs_size(phy) == 12, "160 and 80+80 add 8 bytes");

    memset(phy, 0, sizeof phy);
    CHECK(pong_he_ppe_size(0x08, phy) == 0, "no PPE bit means no PPE field");
    phy[6] = PONG_HE_PPE_PRESENT;
    CHECK(pong_he_ppe_size(0x00, phy) == 1, "an empty PPE header is one byte");
    CHECK(pong_he_ppe_size(0x08, phy) == 2, "one RU pair with one stream needs two bytes");
    CHECK(pong_he_ppe_size(0x0b, phy) == 4, "one RU pair with four streams needs four bytes");

    /* The element walker skips what is not HE and refuses a truncated list. */
    {
        uint8_t ies[80]; unsigned at = 0;
        ies[at++] = 221; ies[at++] = 3; ies[at++] = 0x51; ies[at++] = 0x08; ies[at++] = 0x01;   /* vendor element first */
        ies[at++] = PONG_HE_ELEM_ID; ies[at++] = (uint8_t)(1 + PONG_HE_CAP_FIXED + 8);
        ies[at++] = PONG_HE_EXT_CAP;
        uint8_t tmp[64]; unsigned tlen = 0; put_cap_body(tmp, &tlen, mac, phy, mcs, 8);
        memcpy(ies + at, tmp, tlen); at += tlen;
        ies[at++] = PONG_HE_ELEM_ID; ies[at++] = 7; ies[at++] = PONG_HE_EXT_OPER;
        ies[at++] = 0x00; ies[at++] = 0x00; ies[at++] = 0x40; ies[at++] = 0x00; ies[at++] = 0x02; ies[at++] = 0x00;
        const uint8_t *cap = pong_he_find_ext(ies, at, PONG_HE_EXT_CAP, &blen);
        CHECK(cap && blen == PONG_HE_CAP_FIXED + 8, "the HE capability body is found after a vendor element");
        CHECK(cap && cap[0] == mac[0], "the body starts at the MAC capabilities");
        const uint8_t *oper = pong_he_find_ext(ies, at, PONG_HE_EXT_OPER, &blen);
        CHECK(oper && blen == 6, "the HE operation body is found");
        CHECK(pong_he_find_ext(ies, at - 1, PONG_HE_EXT_OPER, &blen) == 0, "a truncated list is refused");
        CHECK(pong_he_find_ie(ies, at, 221, &blen) == ies + 2 && blen == 3, "a plain element is still found");
    }

    /* Parse and encode agree, including the optional PPE field. */
    phy[0] = PONG_HE_WIDTH_160; phy[6] = PONG_HE_PPE_PRESENT;
    put_cap_body(body, &len, mac, phy, mcs, 8);
    body[len++] = 0x08; body[len++] = 0x40;   /* PPE header, then a 6-bit threshold set */
    struct pong_he_cap cap;
    CHECK(pong_he_parse_cap(body, len, &cap) == 0, "a well-formed capability body parses");
    CHECK(cap.phy[0] == phy[0] && cap.phy[6] == phy[6], "the PHY capability bytes survive the parse");
    CHECK(cap.mcs[0] == 0x1111 && cap.mcs[1] == 0x2222 && cap.mcs[2] == 0x3333 && cap.mcs[3] == 0x4444, "the 160 MHz maps land in their own fields");
    CHECK(cap.ppe_len == 2 && cap.ppe[0] == 0x08 && cap.ppe[1] == 0x40, "the PPE field keeps its header");
    CHECK(pong_he_parse_cap(body, len - 1, &cap) == -1, "a truncated PPE field is refused");
    CHECK(pong_he_parse_cap(body, 10, &cap) == -1, "a body shorter than the fixed fields is refused");
    CHECK(pong_he_parse_cap(body, len, &cap) == 0 && pong_he_cap_ie_len(&cap) == 2 + 1 + PONG_HE_CAP_FIXED + 8 + 2, "the element length counts the extension id");
    CHECK(pong_he_write_cap_ie(&cap, elem, sizeof elem) == (int)pong_he_cap_ie_len(&cap), "the element encodes at that length");
    CHECK(elem[0] == PONG_HE_ELEM_ID && elem[1] == (uint8_t)(1 + PONG_HE_CAP_FIXED + 8 + 2) && elem[2] == PONG_HE_EXT_CAP, "the element header names the HE capability extension");
    {
        const uint8_t *back = pong_he_find_ext(elem, pong_he_cap_ie_len(&cap), PONG_HE_EXT_CAP, &blen);
        struct pong_he_cap again;
        CHECK(back && pong_he_parse_cap(back, blen, &again) == 0 && memcmp(&again.phy, &cap.phy, sizeof cap.phy) == 0 && again.mcs[2] == cap.mcs[2], "the encoded element parses back to the same capability");
    }
    CHECK(pong_he_write_cap_ie(&cap, elem, 4) == 0, "a short output buffer is refused");

    /* Narrowing: the peer's transmit map is bounded by our receive map and the reverse, per stream. */
    {
        struct pong_he_cap own, peer;
        memset(&own, 0, sizeof own); memset(&peer, 0, sizeof peer);
        own.mcs[0] = 0x0000;   /* receive: MCS 0-7 on every stream */
        own.mcs[1] = 0x5555;   /* transmit: MCS 0-7 on one stream only, MCS 0-9 on the others */
        peer.mcs[0] = 0x5555;  /* peer receives up to MCS 0-9 */
        peer.mcs[1] = 0xAAAA;  /* peer transmits up to MCS 0-11 */
        pong_he_narrow(&own, &peer);
        CHECK(peer.mcs[0] == 0x5555, "our transmit map caps the peer's receive map per stream");
        CHECK(peer.mcs[1] == 0x0000, "our receive map caps the peer's transmit map");
        own.mcs[0] = 0xFFFF;   /* receive stream counts unsupported */
        peer.mcs[1] = 0x0000;
        pong_he_narrow(&own, &peer);
        CHECK(peer.mcs[1] == 0xFFFF, "a stream we cannot receive is not left as a peer transmit stream");
    }

    /* Widths we do not run leave the peer's capability: the bit and its maps go, and the element gets shorter. */
    {
        struct pong_he_cap own, peer;
        memset(&own, 0, sizeof own); memset(&peer, 0, sizeof peer);
        peer.phy[0] = PONG_HE_WIDTH_160;
        peer.mcs[0] = 0x0000; peer.mcs[1] = 0x0000; peer.mcs[2] = 0x1111; peer.mcs[3] = 0x2222;
        pong_he_narrow(&own, &peer);
        CHECK((peer.phy[0] & PONG_HE_WIDTH_160) == 0, "a width our radio lacks is cleared on the peer");
        CHECK(pong_he_cap_ie_len(&peer) == 2 + 1 + PONG_HE_CAP_FIXED + 4, "clearing the width shortens the encoded element");
        own.phy[0] = PONG_HE_WIDTH_160; own.mcs[2] = 0x2222; own.mcs[3] = 0x2222;
        peer.phy[0] = PONG_HE_WIDTH_160; peer.mcs[2] = 0x1111; peer.mcs[3] = 0x2222;
        pong_he_narrow(&own, &peer);
        CHECK((peer.phy[0] & PONG_HE_WIDTH_160) != 0 && peer.mcs[2] == 0x1111, "a width both sides run keeps the peer's map");
    }

    /* HE Operation: little-endian parameters, then the basic MCS/NSS set. */
    {
        const uint8_t op[6] = {0x1c, 0x00, 0x40, 0x00, 0x02, 0x00};
        struct pong_he_oper o;
        CHECK(pong_he_parse_oper(op, sizeof op, &o) == 0, "a six-byte operation body parses");
        CHECK(o.params == 0x0040001c, "the parameters are read little-endian");
        CHECK(o.nss_set == 0x0002, "the basic MCS/NSS set is read little-endian");
        CHECK(pong_he_parse_oper(op, 5, &o) == -1, "a short operation body is refused");
    }

    printf("pong-he: %u checks passed, %u failed\n", checks - failed, failed);
    return failed ? 1 : 0;
}
