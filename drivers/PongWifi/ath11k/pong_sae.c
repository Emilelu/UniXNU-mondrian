/* SAE authentication framing for the Pong station. See pong_sae.h for the references and for why this file
 * carries no kernel header. */
#include "pong_sae.h"

/* The group's two sizes: the scalar and one coordinate of the element. P-256 coordinates are 32 bytes, P-384's 48. */
static unsigned group_shape(unsigned group, unsigned *scalar, unsigned *coordinate)
{
    switch (group) {
    case PONG_SAE_GROUP_19: *scalar = 32; *coordinate = 32; return 1;
    case PONG_SAE_GROUP_20: *scalar = 48; *coordinate = 48; return 1;
    default: return 0;
    }
}

unsigned pong_sae_commit_body_len(unsigned group)
{
    unsigned scalar = 0, coordinate = 0;
    if (!group_shape(group, &scalar, &coordinate)) return 0;
    return PONG_SAE_BODY_HEADER + scalar + 2u * coordinate;
}

unsigned pong_sae_commit_body(uint8_t *out, unsigned capacity, unsigned group)
{
    unsigned scalar = 0, coordinate = 0;
    if (!out || !group_shape(group, &scalar, &coordinate)) return 0;
    const unsigned body = PONG_SAE_BODY_HEADER + scalar + 2u * coordinate;
    if (capacity < body) return 0;
    out[0] = (uint8_t)(PONG_SAE_ALG & 0xff);
    out[1] = (uint8_t)(PONG_SAE_ALG >> 8);
    out[2] = (uint8_t)(PONG_SAE_SEQ_COMMIT & 0xff);
    out[3] = (uint8_t)(PONG_SAE_SEQ_COMMIT >> 8);
    out[4] = 0;   /* status: a commit carries none */
    out[5] = 0;
    /* Filler that cannot be mistaken for a real commit: it is deterministic, so the host test can compare runs. */
    for (unsigned i = PONG_SAE_BODY_HEADER; i < body; i++)
        out[i] = (uint8_t)(0x9eu ^ (uint8_t)(i * 31u) ^ (uint8_t)group);
    return body;
}
