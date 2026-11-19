/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Host test for k60_charge_hmac: RFC 4231 vectors against a local SHA-256, so
 * the construction in K60ChargeHmac.h is checked with real digests instead of
 * the stand-in the state-machine test uses. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define K60_CHARGE_HMAC_HOST 1

typedef struct { uint32_t h[8]; uint64_t len; uint8_t buf[64]; unsigned used; } SHA256_CTX;

static uint32_t ror(uint32_t x, unsigned n) { return (x >> n) | (x << (32 - n)); }
static const uint32_t K[64] = {
    0x428a2f98u, 0x71374491u, 0xb5c0fbcfu, 0xe9b5dba5u, 0x3956c25bu, 0x59f111f1u,
    0x923f82a4u, 0xab1c5ed5u, 0xd807aa98u, 0x12835b01u, 0x243185beu, 0x550c7dc3u,
    0x72be5d74u, 0x80deb1feu, 0x9bdc06a7u, 0xc19bf174u, 0xe49b69c1u, 0xefbe4786u,
    0x0fc19dc6u, 0x240ca1ccu, 0x2de92c6fu, 0x4a7484aau, 0x5cb0a9dcu, 0x76f988dau,
    0x983e5152u, 0xa831c66du, 0xb00327c8u, 0xbf597fc7u, 0xc6e00bf3u, 0xd5a79147u,
    0x06ca6351u, 0x14292967u, 0x27b70a85u, 0x2e1b2138u, 0x4d2c6dfcu, 0x53380d13u,
    0x650a7354u, 0x766a0abbu, 0x81c2c92eu, 0x92722c85u, 0xa2bfe8a1u, 0xa81a664bu,
    0xc24b8b70u, 0xc76c51a3u, 0xd192e819u, 0xd6990624u, 0xf40e3585u, 0x106aa070u,
    0x19a4c116u, 0x1e376c08u, 0x2748774cu, 0x34b0bcb5u, 0x391c0cb3u, 0x4ed8aa4au,
    0x5b9cca4fu, 0x682e6ff3u, 0x748f82eeu, 0x78a5636fu, 0x84c87814u, 0x8cc70208u,
    0x90befffau, 0xa4506cebu, 0xbef9a3f7u, 0xc67178f2u,
};
static void sha_block(SHA256_CTX *c, const uint8_t *p)
{
    uint32_t w[64], a, b, d, e, f, g, h, cc, t1, t2;
    for (unsigned i = 0; i < 16; ++i)
        w[i] = (uint32_t)p[i * 4] << 24 | (uint32_t)p[i * 4 + 1] << 16 |
               (uint32_t)p[i * 4 + 2] << 8 | p[i * 4 + 3];
    for (unsigned i = 16; i < 64; ++i) {
        uint32_t s0 = ror(w[i - 15], 7) ^ ror(w[i - 15], 18) ^ (w[i - 15] >> 3);
        uint32_t s1 = ror(w[i - 2], 17) ^ ror(w[i - 2], 19) ^ (w[i - 2] >> 10);
        w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    a = c->h[0]; b = c->h[1]; cc = c->h[2]; d = c->h[3];
    e = c->h[4]; f = c->h[5]; g = c->h[6]; h = c->h[7];
    for (unsigned i = 0; i < 64; ++i) {
        uint32_t s1 = ror(e, 6) ^ ror(e, 11) ^ ror(e, 25);
        uint32_t ch = (e & f) ^ (~e & g);
        t1 = h + s1 + ch + K[i] + w[i];
        uint32_t s0 = ror(a, 2) ^ ror(a, 13) ^ ror(a, 22);
        uint32_t maj = (a & b) ^ (a & cc) ^ (b & cc);
        t2 = s0 + maj;
        h = g; g = f; f = e; e = d + t1; d = cc; cc = b; b = a; a = t1 + t2;
    }
    c->h[0] += a; c->h[1] += b; c->h[2] += cc; c->h[3] += d;
    c->h[4] += e; c->h[5] += f; c->h[6] += g; c->h[7] += h;
}
static void SHA256_Init(SHA256_CTX *c)
{
    static const uint32_t init[8] = {0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u,
        0xa54ff53au, 0x510e527fu, 0x9b05688cu, 0x1f83d9abu, 0x5be0cd19u};
    memcpy(c->h, init, sizeof init); c->len = 0; c->used = 0;
}
static void SHA256_Update(SHA256_CTX *c, const void *data, size_t bytes)
{
    const uint8_t *p = data;
    c->len += bytes;
    while (bytes) {
        unsigned room = 64 - c->used;
        unsigned take = bytes < room ? (unsigned)bytes : room;
        memcpy(c->buf + c->used, p, take);
        c->used += take; p += take; bytes -= take;
        if (c->used == 64) { sha_block(c, c->buf); c->used = 0; }
    }
}
static void SHA256_Final(uint8_t out[32], SHA256_CTX *c)
{
    const uint64_t bits = c->len * 8;
    uint8_t pad = 0x80;
    SHA256_Update(c, &pad, 1);
    pad = 0;
    while (c->used != 56) SHA256_Update(c, &pad, 1);
    for (int i = 7; i >= 0; --i) { uint8_t byte = (uint8_t)(bits >> (i * 8)); SHA256_Update(c, &byte, 1); }
    for (unsigned i = 0; i < 8; ++i) {
        out[i * 4] = (uint8_t)(c->h[i] >> 24); out[i * 4 + 1] = (uint8_t)(c->h[i] >> 16);
        out[i * 4 + 2] = (uint8_t)(c->h[i] >> 8); out[i * 4 + 3] = (uint8_t)c->h[i];
    }
}
#include "K60ChargeHmac.h"

static unsigned checks, failures;
static void hex(const uint8_t digest[32], char out[65])
{
    for (unsigned i = 0; i < 32; ++i) sprintf(out + i * 2, "%02x", digest[i]);
    out[64] = 0;
}
static void expect(const char *name, const uint8_t *key, uint32_t keyBytes,
    const uint8_t *msg, uint32_t bytes, const char *want)
{
    uint8_t digest[32]; char got[65];
    k60_charge_hmac(key, keyBytes, msg, bytes, digest);
    hex(digest, got);
    ++checks;
    if (strcmp(got, want) != 0) { ++failures; printf("FAIL %s: got %s want %s\n", name, got, want); }
}
int main(void)
{
    uint8_t key[131];
    memset(key, 0x0b, 20);
    expect("rfc4231-1", key, 20, (const uint8_t *)"Hi There", 8,
        "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7");
    expect("rfc4231-2", (const uint8_t *)"Jefe", 4,
        (const uint8_t *)"what do ya want for nothing?", 28,
        "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843");
    memset(key, 0xaa, 20);
    expect("rfc4231-3", key, 20, (const uint8_t *)"\xdd" "\xdd" "\xdd" "\xdd" "\xdd" "\xdd"
        "\xdd" "\xdd" "\xdd" "\xdd" "\xdd" "\xdd" "\xdd" "\xdd" "\xdd" "\xdd" "\xdd"
        "\xdd" "\xdd" "\xdd" "\xdd" "\xdd" "\xdd" "\xdd" "\xdd" "\xdd" "\xdd" "\xdd"
        "\xdd" "\xdd" "\xdd" "\xdd" "\xdd" "\xdd" "\xdd" "\xdd" "\xdd" "\xdd" "\xdd"
        "\xdd" "\xdd" "\xdd" "\xdd" "\xdd" "\xdd" "\xdd" "\xdd" "\xdd" "\xdd" "\xdd", 50,
        "773ea91e36800e46854db8ebd09181a72959098b3ef8c122d9635514ced565fe");
    memset(key, 0xaa, 131);
    expect("rfc4231-6", key, 131,
        (const uint8_t *)"Test Using Larger Than Block-Size Key - Hash Key First", 54,
        "60e431591ee0b67f0d8a26aacbf5b77f8e0bc6213728c5140546040f0ee37f54");
    memset(key, 0xaa, 131);
    expect("rfc4231-7", key, 131,
        (const uint8_t *)"This is a test using a larger than block-size key and a larger "
        "than block-size data. The key needs to be hashed before being used by the HMAC algorithm.", 152,
        "9b09ffa71b942fcb27635fbcd5b0e944bfdc63644f0713938a7f51535c3a35e2");
    printf("TESTS %s %u checks (%u failures)\n", failures ? "FAILED" : "OK", checks, failures);
    return failures != 0;
}
