#include <stdio.h>
#include <string.h>
#include "../../drivers/PongPower/K60Smem.c"
#include "../../drivers/PongPower/K60HandoffBuild.c"

#define TOTAL 32768u
static uint8_t mem[TOTAL];

int main(void)
{
    K60Smem s; K60SmemPartition p; K60HandoffPlan plan; uint8_t out[K60_HANDOFF_BYTES];
    const uint32_t toc = TOTAL - 4096u, part = 0x100u;
    int fails = 0, rc;

    memset(mem, 0, sizeof mem);
    s.base = mem; s.size = TOTAL;
    *(uint32_t *)&mem[toc] = TOC_MAGIC;
    *(uint32_t *)&mem[toc + 4] = 1;
    *(uint32_t *)&mem[toc + 8] = 1;
    *(uint32_t *)&mem[toc + 32] = part;
    *(uint32_t *)&mem[toc + 36] = 0x4000u;
    *(uint32_t *)&mem[toc + 44] = 0x00010000u;
    *(uint32_t *)&mem[toc + 48] = 8;
    p.offset = part; p.size = 0x4000u; p.cacheline = 8; p.host0 = 0; p.host1 = 1;
    *(uint32_t *)&mem[part] = PART_MAGIC;
    *(uint32_t *)&mem[part + 4] = 0x00010000u;
    *(uint32_t *)&mem[part + 8] = 0x4000u;
    *(uint32_t *)&mem[part + 12] = PART_HEADER;
    *(uint32_t *)&mem[part + 16] = 0x3c00u;

    memset(&plan, 0, sizeof plan);
    plan.required = 0x7u; plan.epoch = 1793709100u;
    plan.smem_base = 0x80900000ull; plan.smem_bytes = 0x200000u;
    plan.adsp_base = 0x9fd00000ull; plan.adsp_bytes = 0x3100000u;
    plan.desc_item = 0x501u; plan.tx_item = 0x502u; plan.rx_item = 0x503u; plan.smp2p_item = 0x504u;
    plan.remote_pid = 2; plan.desc_bytes = 32u; plan.tx_bytes = 4096u; plan.rx_bytes = 4096u;
    plan.smp2p_bytes = 40u; plan.remote_restart_flag = 1u;

    rc = k60_handoff_build(&s, &p, &plan, out);
    if (rc != 0) { printf("FAIL rc=%d\n", rc); fails++; }
    if (*(uint32_t *)(out + 0) != K60_HANDOFF_MAGIC) { printf("FAIL magic\n"); fails++; }
    if (*(uint32_t *)(out + 8) != 104u) { printf("FAIL bytes\n"); fails++; }
    if (*(uint32_t *)(out + 56) == 0 || *(uint32_t *)(out + 64) == 0) { printf("FAIL offsets\n"); fails++; }
    if (*(uint32_t *)(out + 92) != 0x504u) { printf("FAIL smp2p item\n"); fails++; }
    if (*(uint64_t *)(out + 24) != 0x80900000ull) { printf("FAIL smem base\n"); fails++; }

    /* Second build must reuse the same items, not duplicate them. */
    {
        uint8_t out2[K60_HANDOFF_BYTES];
        rc = k60_handoff_build(&s, &p, &plan, out2);
        if (rc != 0 || memcmp(out, out2, K60_HANDOFF_BYTES) != 0) { printf("FAIL idempotent\n"); fails++; }
    }

    /* A plan with a zero epoch must be refused before any allocation. */
    {
        const uint32_t up_before = *(uint32_t *)&mem[part + 12];
        uint8_t bad[K60_HANDOFF_BYTES];
        plan.epoch = 0;
        rc = k60_handoff_build(&s, &p, &plan, bad);
        if (rc != -8) { printf("FAIL epoch guard rc=%d\n", rc); fails++; }
        if (*(uint32_t *)&mem[part + 12] != up_before) { printf("FAIL partition touched\n"); fails++; }
    }

    printf(fails ? "TESTS FAILED %d\n" : "TESTS OK 7\n", fails);
    return fails != 0;
}
