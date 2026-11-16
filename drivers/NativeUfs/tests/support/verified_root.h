/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#ifndef VERIFIED_ROOT_H
#define VERIFIED_ROOT_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define VR_HEADER_BYTES 160u
#define VR_SIGNATURE_BYTES 384u
#define VR_KEY_BYTES 395u
#define VR_BLOCK_BYTES 4096u

enum vr_status { VR_OK, VR_FORMAT, VR_KEY, VR_SIGNATURE, VR_HASH_TABLE, VR_BLOCK };
struct vr_crypto {
    int (*sha256)(const void *, size_t, uint8_t[32]);
    int (*rsa3072_sha256)(const uint8_t[VR_KEY_BYTES], const uint8_t[32], const uint8_t[VR_SIGNATURE_BYTES]);
};
struct vr_view {
    const uint8_t *hashes;
    uint64_t image_bytes, block_count, generation;
    uint8_t volume_uuid[16], image_sha256[32];
};
/* Trusted key is supplied independently of the untrusted envelope. Both buffers
 * must remain immutable for the lifetime of the returned authenticated view. */
int vr_open(const uint8_t *, size_t, const uint8_t[VR_KEY_BYTES], uint64_t,
            const struct vr_crypto *, struct vr_view *);
int vr_verify_block(const struct vr_view *, uint64_t, const void *, size_t,
                    const struct vr_crypto *);
#ifdef __cplusplus
}
#endif
#endif
