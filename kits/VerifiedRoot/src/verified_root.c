/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#include "verified_root.h"

static uint64_t le(const uint8_t *p, unsigned n) {
    uint64_t v = 0;
    for (unsigned i = 0; i < n; ++i) v |= (uint64_t)p[i] << (8 * i);
    return v;
}
static int same(const uint8_t *a, const uint8_t *b, size_t n) {
    uint8_t diff = 0;
    for (size_t i = 0; i < n; ++i) diff |= a[i] ^ b[i];
    return diff == 0;
}
int vr_open(const uint8_t *p, size_t n, const uint8_t key[VR_KEY_BYTES], uint64_t minimum_generation,
            const struct vr_crypto *crypto, struct vr_view *out) {
    static const uint8_t magic[8] = {'V','R','O','O','T','0','1',0};
    static const uint8_t key_magic[8] = {'V','R','O','O','T','K','E','Y'};
    uint8_t digest[32];
    uint64_t bytes, count, generation;
    if (!out) return VR_FORMAT;
    *out = (struct vr_view){0};
    if (!p || !key || !crypto || !crypto->sha256 || !crypto->rsa3072_sha256 ||
        n < VR_HEADER_BYTES + VR_SIGNATURE_BYTES || !same(p, magic, 8) ||
        le(p + 8, 4) != 1 || le(p + 12, 4) != VR_HEADER_BYTES ||
        le(p + 16, 4) != VR_BLOCK_BYTES || le(p + 20, 4) != 0 || !minimum_generation) return VR_FORMAT;
    bytes = le(p + 24, 8);
    count = le(p + 32, 8);
    generation = le(p + 152, 8);
    if (!bytes || count != bytes / VR_BLOCK_BYTES + (bytes % VR_BLOCK_BYTES != 0) ||
        count > (SIZE_MAX - VR_HEADER_BYTES - VR_SIGNATURE_BYTES) / 32 ||
        n != VR_HEADER_BYTES + VR_SIGNATURE_BYTES + (size_t)count * 32 || generation < minimum_generation) return VR_FORMAT;
    if (!same(key, key_magic, 8) || !(key[8] & 0x80) || !(key[391] & 1) ||
        key[392] != 1 || key[393] != 0 || key[394] != 1 ||
        !crypto->sha256(key, VR_KEY_BYTES, digest) || !same(digest, p + 120, 32)) return VR_KEY;
    if (!crypto->sha256(p, VR_HEADER_BYTES, digest) ||
        !crypto->rsa3072_sha256(key, digest, p + VR_HEADER_BYTES)) return VR_SIGNATURE;
    const uint8_t *hashes = p + VR_HEADER_BYTES + VR_SIGNATURE_BYTES;
    if (!crypto->sha256(hashes, (size_t)count * 32, digest) || !same(digest, p + 88, 32)) return VR_HASH_TABLE;
    out->hashes = hashes;
    out->image_bytes = bytes;
    out->block_count = count;
    out->generation = generation;
    for (unsigned i = 0; i < 16; ++i) out->volume_uuid[i] = p[40 + i];
    for (unsigned i = 0; i < 32; ++i) out->image_sha256[i] = p[56 + i];
    return VR_OK;
}
int vr_verify_block(const struct vr_view *view, uint64_t index, const void *data, size_t n,
                    const struct vr_crypto *crypto) {
    uint8_t digest[32];
    if (!view || !view->hashes || !data || !crypto || !crypto->sha256 || index >= view->block_count) return VR_BLOCK;
    uint64_t remaining = view->image_bytes - index * VR_BLOCK_BYTES;
    size_t expected = remaining < VR_BLOCK_BYTES ? (size_t)remaining : VR_BLOCK_BYTES;
    if (n != expected || !crypto->sha256(data, n, digest) ||
        !same(digest, view->hashes + index * 32, 32)) return VR_BLOCK;
    return VR_OK;
}
