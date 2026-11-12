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


    /* Every documented offset must carry its documented field. The table is
     * copied from docs/research/battery/GLINK-HANDOFF.md, not from this code. */
    {
        static const struct { uint32_t at, value, mask; const char *name; } fields[] = {
            {0,  K60_HANDOFF_MAGIC, 0xffffffffu, "magic"},
            {4,  K60_HANDOFF_VERSION, 0xffffffffu, "version"},
            {8,  104u, 0xffffffffu, "bytes"},
            {12, 0x7u, 0xffffffffu, "flags"},
            {16, 1793709100u, 0xffffffffu, "epoch"},
            {20, 0u, 0xffffffffu, "pad20"},
            {24, 0x80900000u, 0xffffffffu, "smem_base lo"},
            {28, 0u, 0xffffffffu, "smem_base hi"},
            {32, 0x200000u, 0xffffffffu, "smem_bytes"},
            {36, 0u, 0xffffffffu, "pad36"},
            {40, 0x9fd00000u, 0xffffffffu, "adsp_base lo"},
            {44, 0u, 0xffffffffu, "adsp_base hi"},
            {48, 0x3100000u, 0xffffffffu, "adsp_bytes"},
            {52, 0u, 0xffffffffu, "pad52"},
            {60, 32u, 0xffffffffu, "desc_bytes"},
            {68, 4096u, 0xffffffffu, "tx_bytes"},
            {76, 4096u, 0xffffffffu, "rx_bytes"},
            {80, 0u, 0xffffffffu, "host_tx_head"},
            {84, 0u, 0xffffffffu, "host_rx_tail"},
            {88, 2u, 0xffffffffu, "remote_pid"},
            {92, 0x504u, 0xffffffffu, "smp2p_item"},
            {96, 1u, 0xffffffffu, "restart_flag"},
            {100, 0u, 0xffffffffu, "reserved"}
        };
        unsigned k;
        for (k = 0; k < sizeof fields / sizeof fields[0]; ++k) {
            const uint32_t got = *(uint32_t *)(out + fields[k].at) & fields[k].mask;
            if (got != fields[k].value) {
                printf("FAIL field %s @%u got=%#x want=%#x\n", fields[k].name, fields[k].at, got, fields[k].value);
                fails++;
            }
        }
        if (*(uint32_t *)(out + 56) == 0 || *(uint32_t *)(out + 64) == 0 ||
            *(uint32_t *)(out + 72) == 0) { printf("FAIL offset triple\n"); fails++; }
    }


    /* K60PmicGlink::discover() reads the descriptor as uint32_t and rejects a
     * smp2p state that is not 4-byte aligned, so every leased offset must be
     * 8-aligned and the sizes must survive the same read. */
    {
        const uint32_t offs[3] = {
            *(uint32_t *)(out + 56), *(uint32_t *)(out + 64),
            *(uint32_t *)(out + 72)
        };
        const uint32_t lens[3] = {
            *(uint32_t *)(out + 60), *(uint32_t *)(out + 68),
            *(uint32_t *)(out + 76)
        };
        unsigned k;
        /* The lease carries offsets for desc/tx/rx only; smp2p is re-found by
         * its item id, so +92 is an id and never an offset. */
        for (k = 0; k < 3; ++k) {
            if (offs[k] == 0 || (offs[k] & 7u) != 0) {
                printf("FAIL alignment item%u off=%#x\n", k, offs[k]);
                fails++;
            }
        }
        if (lens[0] != 32u || lens[1] < 256u || lens[2] < 256u) {
            printf("FAIL lease sizes\n");
            fails++;
        }
    }

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

    printf(fails ? "TESTS FAILED %d\n" : "TESTS OK 9\n", fails);
    return fails != 0;
}
