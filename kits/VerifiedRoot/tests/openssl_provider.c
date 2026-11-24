/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#include "verified_root.h"
#include <openssl/evp.h>
#include <openssl/rsa.h>
#include <openssl/core_names.h>
#include <openssl/param_build.h>

static int hash(const void *data, size_t n, uint8_t out[32]) {
    unsigned size = 0;
    return EVP_Digest(data, n, out, &size, EVP_sha256(), NULL) == 1 && size == 32;
}
static int verify(const uint8_t key[VR_KEY_BYTES], const uint8_t digest[32], const uint8_t sig[VR_SIGNATURE_BYTES]) {
    int ok = 0;
    BIGNUM *modulus = BN_bin2bn(key + 8, 384, NULL);
    BIGNUM *exponent = BN_bin2bn(key + 392, 3, NULL);
    OSSL_PARAM_BLD *builder = OSSL_PARAM_BLD_new();
    OSSL_PARAM *params = NULL;
    EVP_PKEY_CTX *make = NULL, *check = NULL;
    EVP_PKEY *public_key = NULL;
    if (!modulus || !exponent || !builder ||
        OSSL_PARAM_BLD_push_BN(builder, OSSL_PKEY_PARAM_RSA_N, modulus) != 1 ||
        OSSL_PARAM_BLD_push_BN(builder, OSSL_PKEY_PARAM_RSA_E, exponent) != 1) goto done;
    params = OSSL_PARAM_BLD_to_param(builder);
    make = EVP_PKEY_CTX_new_from_name(NULL, "RSA", NULL);
    if (!params || !make || EVP_PKEY_fromdata_init(make) != 1 ||
        EVP_PKEY_fromdata(make, &public_key, EVP_PKEY_PUBLIC_KEY, params) != 1) goto done;
    check = EVP_PKEY_CTX_new(public_key, NULL);
    if (!check || EVP_PKEY_verify_init(check) != 1 ||
        EVP_PKEY_CTX_set_rsa_padding(check, RSA_PKCS1_PADDING) <= 0 ||
        EVP_PKEY_CTX_set_signature_md(check, EVP_sha256()) <= 0) goto done;
    ok = EVP_PKEY_verify(check, sig, VR_SIGNATURE_BYTES, digest, 32) == 1;
done:
    EVP_PKEY_CTX_free(check);
    EVP_PKEY_free(public_key);
    EVP_PKEY_CTX_free(make);
    OSSL_PARAM_free(params);
    OSSL_PARAM_BLD_free(builder);
    BN_free(exponent);
    BN_free(modulus);
    return ok;
}
static const struct vr_crypto provider = {hash, verify};
int vr_host_open(const uint8_t *p, size_t n, const uint8_t *key, uint64_t generation, struct vr_view *view) {
    return vr_open(p, n, key, generation, &provider, view);
}
int vr_host_block(const struct vr_view *view, uint64_t index, const void *data, size_t n) {
    return vr_verify_block(view, index, data, n, &provider);
}
