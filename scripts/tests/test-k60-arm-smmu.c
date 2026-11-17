/* SPDX-License-Identifier: MIT */
/* Host regression: the K60 IPA SMMU ranges use a Device-nGnRE mapping at
 * 0x146a8000/0x2000. The shared ArmSmmu4K builder must accept writeback=2 and
 * the context encoder must publish MAIR index 2 instead of hard-coding 0xff44. */
#include <stdio.h>
#include <string.h>
#include "ArmSmmu4K.h"
#include "ArmSmmu4KContext.h"
int main(void) {
    uint64_t tables[8u * 512u];
    memset(tables, 0xa5, sizeof(tables));
    ArmSmmu4KConfig config = {32u, 36u, 0x10000000ull, 267u};
    ArmSmmu4KRange ranges[3] = {
        {0x146a8000ull, 0x146a8000ull, 0x2000ull, 3u, 2u, 2u},
        {0x20000000ull, 0x20000000ull, 0x100000ull, 3u, 1u, 3u},
        {0x80900000ull, 0x80900000ull, 0x9000ull, 3u, 0u, 2u},
    };
    ArmSmmu4KResult result;
    memset(&result, 0, sizeof(result));
    ArmSmmu4KStatus st = ArmSmmu4KBuild(&config, ranges, 3u, tables, 8u, &result);
    if (st != ArmSmmu4KSuccess || result.mair != 0x4ff44 ||
        result.table_pages != 6u || result.leaf_pages != 267u) {
        printf("K60 ARM SMMU FAIL build=%d mair=%#llx tables=%zu leaves=%zu\n",
            (int)st, (unsigned long long)result.mair, result.table_pages,
            result.leaf_pages);
        return 1;
    }
    ArmSmmu4KContextConfig ctx;
    memset(&ctx, 0, sizeof(ctx));
    ctx.lower = &config;
    ctx.lower_tables = &result;
    ctx.id0 = 0x40000000u;
    ctx.id2 = 0x1555u;
    ctx.asid = 0x5c0u;
    ctx.coherent_walk = 1u;
    ctx.polled_faults = 1u;
    ctx.ignore_top_byte = 1u;
    ctx.shared_asid = 1u;
    ArmSmmu4KContextImage image;
    memset(&image, 0, sizeof(image));
    ArmSmmu4KStatus ce = ArmSmmu4KEncodeContext(&ctx, &image);
    ArmSmmu4KStatus vr = ArmSmmu4KValidateContextReadback(&ctx, &image);
    if (ce != ArmSmmu4KSuccess || vr != ArmSmmu4KSuccess || image.mair0 != 0x4ff44) {
        printf("K60 ARM SMMU FAIL context=%d readback=%d mair0=%#x\n",
            (int)ce, (int)vr, image.mair0);
        return 1;
    }
    printf("K60 ARM SMMU PASS mair=%#llx tables=%zu leaves=%zu mair0=%#x\n",
        (unsigned long long)result.mair, result.table_pages, result.leaf_pages,
        image.mair0);
    return 0;
}
