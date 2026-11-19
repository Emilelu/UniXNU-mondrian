/* Host self-test for the SAE authentication framing unit. Built and run by scripts/tests/test-pong-sae.py;
 * it links no kernel header and no board code, so it runs on the build host as part of offline verification. */
#include <stdio.h>
#include <string.h>
#include "pong_sae.h"

static unsigned checks, failed;
#define CHECK(cond, what) do { checks++; if (!(cond)) { failed++; printf("FAIL: %s (line %d)\n", what, __LINE__); } } while (0)

int main(void)
{
    uint8_t body[PONG_SAE_MAX_BODY], again[PONG_SAE_MAX_BODY], other[PONG_SAE_MAX_BODY];

    /* The commit size follows the group's parameter sizes. */
    CHECK(pong_sae_commit_body_len(PONG_SAE_GROUP_19) == 102, "group 19 is 6 + 32 + 64 bytes");
    CHECK(pong_sae_commit_body_len(PONG_SAE_GROUP_20) == 150, "group 20 is 6 + 48 + 96 bytes");
    CHECK(pong_sae_commit_body_len(0) == 0, "an unknown group has no body");
    CHECK(PONG_SAE_MAX_BODY >= pong_sae_commit_body_len(PONG_SAE_GROUP_20), "the buffer covers the largest body");

    /* The header is the station's commit: algorithm 3, transaction sequence 1, status 0. */
    memset(body, 0, sizeof body);
    unsigned len = pong_sae_commit_body(body, sizeof body, PONG_SAE_GROUP_19);
    CHECK(len == 102, "the body reports its length");
    CHECK(body[0] == 3 && body[1] == 0, "algorithm 3 is encoded little-endian first");
    CHECK(body[2] == 1 && body[3] == 0, "transaction sequence 1 says commit");
    CHECK(body[4] == 0 && body[5] == 0, "a commit carries no status");

    /* The payload is filler, deterministic, and different for another group. */
    unsigned nonzero = 0;
    for (unsigned i = PONG_SAE_BODY_HEADER; i < len; i++) nonzero += body[i] != 0;
    CHECK(nonzero > 90, "the commit body is filled, not zero");
    CHECK(pong_sae_commit_body(again, sizeof again, PONG_SAE_GROUP_19) == len && !memcmp(body, again, len),
          "the same group builds the same body");
    unsigned len20 = pong_sae_commit_body(other, sizeof other, PONG_SAE_GROUP_20);
    CHECK(len20 == 150, "group 20 builds its own length");
    CHECK(memcmp(body + PONG_SAE_BODY_HEADER, other + PONG_SAE_BODY_HEADER, 32) != 0, "another group builds another body");

    /* A short buffer and a null buffer are refused, and a refusal changes nothing. */
    uint8_t small[101]; memset(small, 0xa5, sizeof small);
    CHECK(pong_sae_commit_body(small, sizeof small, PONG_SAE_GROUP_19) == 0, "a short buffer is refused");
    CHECK(small[0] == 0xa5 && small[100] == 0xa5, "a refused write leaves the buffer alone");
    CHECK(pong_sae_commit_body(0, 256, PONG_SAE_GROUP_19) == 0, "a null buffer is refused");

    printf("%u checks passed, %u failed\n", checks - failed, failed);
    return failed ? 1 : 0;
}
