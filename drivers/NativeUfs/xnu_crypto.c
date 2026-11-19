/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#include "verified_root.h"
#include <libkern/crypto/sha2.h>
#include <libkern/crypto/rsa.h>
#include <corecrypto/ccsha2.h>

static int hash(const void *data, size_t n, uint8_t out[32]) {
    SHA256_CTX context;
    SHA256_Init(&context);
    SHA256_Update(&context, data, n);
    SHA256_Final(out, &context);
    return 1;
}
static int verify(const uint8_t key[VR_KEY_BYTES], const uint8_t digest[32], const uint8_t signature[VR_SIGNATURE_BYTES]) {
    rsa_pub_ctx public_key = {0};
    bool valid = false;
    int error = rsa_make_pub(&public_key, 3, key + 392, 384, key + 8);
    if (error) return 0;
    error = rsa_verify_pkcs1v15(&public_key, ccoid_sha256, 32, digest,
                               VR_SIGNATURE_BYTES, signature, &valid);
    return error == 0 && valid;
}
const struct vr_crypto vr_xnu_crypto = {hash, verify};
