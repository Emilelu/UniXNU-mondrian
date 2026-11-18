/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/* HMAC-SHA256 as the charge authentication protocol uses it. Kept in a header
 * so the host test can exercise the exact construction with RFC 4231 vectors
 * instead of a stand-in. Keys longer than one block are hashed first, as RFC
 * 2104 requires; the production keys are 32 bytes. */
#ifndef K60_CHARGE_HMAC_H
#define K60_CHARGE_HMAC_H
#include <stdint.h>
#include <string.h>
#ifndef K60_CHARGE_HMAC_HOST
#include <libkern/crypto/sha2.h>
#endif

static inline void k60_charge_hmac(const uint8_t *key, uint32_t keyBytes,
    const uint8_t *message, uint32_t bytes, uint8_t digest[32])
{
    uint8_t pad[64], inner[32], hashed[32];
    const uint8_t *k = key;
    uint32_t n = keyBytes;
    SHA256_CTX sha;
    if (keyBytes > sizeof pad) {
        SHA256_Init(&sha); SHA256_Update(&sha, key, keyBytes);
        SHA256_Final(hashed, &sha);
        k = hashed; n = sizeof hashed;
    }
    for (unsigned i = 0; i < sizeof pad; ++i) pad[i] = (i < n ? k[i] : 0) ^ 0x36;
    SHA256_Init(&sha); SHA256_Update(&sha, pad, sizeof pad);
    SHA256_Update(&sha, message, bytes); SHA256_Final(inner, &sha);
    for (unsigned i = 0; i < sizeof pad; ++i) pad[i] ^= 0x36 ^ 0x5c;
    SHA256_Init(&sha); SHA256_Update(&sha, pad, sizeof pad);
    SHA256_Update(&sha, inner, sizeof inner); SHA256_Final(digest, &sha);
    memset(pad, 0, sizeof pad); memset(inner, 0, sizeof inner);
    memset(hashed, 0, sizeof hashed); memset(&sha, 0, sizeof sha);
}
#endif
