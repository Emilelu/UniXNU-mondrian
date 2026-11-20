/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Host test for the K60 IPA runtime allocation bound.
 *
 * kmem_alloc_contig's fifth argument is the highest physical page number it
 * may return, so a zero there bounds nothing. The kernel path therefore asks
 * k60_ipa_runtime_ceiling() for a page number below the 36-bit IPA DMA limit
 * and re-checks the address it got back with k60_ipa_runtime_address_fits().
 * Both are plain integer arithmetic, so the whole window can be exercised
 * here: the highest page that still fits, the first page that does not, the
 * refusals for an empty or impossible request, and the wrap that a naive
 * physical + bytes would read as a small number.
 */

#include <stdio.h>
#include <stdint.h>

#include "K60Ipa.h"

static unsigned failures;

static void
expect(int condition, const char *what)
{
    if (!condition) {
        printf("FAIL %s\n", what);
        failures++;
    }
}

static void
expect_bound(uint64_t bytes, uint64_t page)
{
    uint64_t ceiling = 0;

    expect(k60_ipa_runtime_ceiling(bytes, page, &ceiling) == K60IpaOk,
        "ceiling accepted");
    expect(ceiling * page + bytes <= K60_IPA_RUNTIME_DMA_LIMIT,
        "ceiling stays under the limit");
    expect((ceiling + 1u) * page + bytes > K60_IPA_RUNTIME_DMA_LIMIT,
        "one page higher would cross it");
    expect(k60_ipa_runtime_address_fits(ceiling * page, bytes) == 1,
        "the highest legal address fits");
    expect(k60_ipa_runtime_address_fits((ceiling + 1u) * page, bytes) == 0,
        "the first illegal address is refused");
}

int
main(void)
{
    uint64_t ceiling = 0;
    const uint64_t page = 0x1000u;
    const uint64_t page16k = 0x4000u;

    /* Four requests the IPA path really makes: one page, a 16 KiB page, the
     * 1 MiB ring and the 20 MiB filter/route tables. */
    expect_bound(0x1000u, page);
    expect_bound(0x1000u, page16k);
    expect_bound(0x100000u, page);
    expect_bound(0x1400000u, page);

    /* A 4 KiB request on a 4 KiB page leaves every page below 2^36 but the
     * last one; 2^24 - 1 is the highest whose page still fits. */
    expect(k60_ipa_runtime_ceiling(0x1000u, page, &ceiling) == K60IpaOk &&
        ceiling == (1u << 24) - 1u, "four kilobytes leaves 2^24 - 1 pages");
    expect(k60_ipa_runtime_ceiling(0x1400000u, page, &ceiling) == K60IpaOk &&
        ceiling == (1u << 24) - 0x1400u,
        "twenty megabytes moves the ceiling down by its own size");

    /* Refusals: no bytes, no page size, nowhere to put the answer, and a
     * request that cannot fit below the limit at all. */
    expect(k60_ipa_runtime_ceiling(0u, page, &ceiling) == K60IpaBadArgument,
        "zero bytes is refused");
    expect(k60_ipa_runtime_ceiling(0x1000u, 0u, &ceiling) == K60IpaBadArgument,
        "zero page size is refused");
    expect(k60_ipa_runtime_ceiling(0x1000u, page, NULL) == K60IpaBadArgument,
        "no output pointer is refused");
    expect(k60_ipa_runtime_ceiling(K60_IPA_RUNTIME_DMA_LIMIT, page, &ceiling) ==
        K60IpaBadArgument, "a request as large as the limit is refused");
    expect(k60_ipa_runtime_ceiling(K60_IPA_RUNTIME_DMA_LIMIT + 0x1000u, page,
        &ceiling) == K60IpaBadArgument, "a request larger than it is refused");

    /* Readback: zero, the exact limit, one byte past it, and a sum that
     * wraps. The wrap is the case a bare physical + bytes > limit misses. */
    expect(k60_ipa_runtime_address_fits(0u, 0x1000u) == 0,
        "physical zero is refused");
    expect(k60_ipa_runtime_address_fits(K60_IPA_RUNTIME_DMA_LIMIT - 0x1000u,
        0x1000u) == 1, "an address ending exactly at the limit fits");
    expect(k60_ipa_runtime_address_fits(K60_IPA_RUNTIME_DMA_LIMIT - 0xfffu,
        0x1000u) == 0, "an address ending one byte past it does not");
    expect(k60_ipa_runtime_address_fits(UINT64_MAX - 0xfffu, 0x1000u) == 0,
        "a wrapping sum is refused");
    expect(k60_ipa_runtime_address_fits(0x1000u, 0u) == 0,
        "zero bytes is refused");

    if (failures != 0u) {
        printf("K60 IPA RUNTIME CEILING FAILED %u check(s)\n", failures);
        return 1;
    }
    printf("K60 IPA RUNTIME CEILING PASS bound, readback, refusals, wrap\n");
    return 0;
}