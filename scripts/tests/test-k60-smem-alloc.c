#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <stdint.h>
#include "../../drivers/PongPower/K60Smem.c"

#define TOTAL 8192u
static uint8_t mem[TOTAL];

static void setup(K60Smem *s, K60SmemPartition *p, uint32_t down)
{
    const uint32_t toc = TOTAL - 4096u;
    const uint32_t part = 0x100u;
    memset(mem, 0xEE, sizeof mem);
    memset(&mem[part], 0, 0x400u);
    s->base = mem; s->size = TOTAL;
    *(uint32_t *)&mem[toc] = TOC_MAGIC;
    *(uint32_t *)&mem[toc + 4] = 1;
    *(uint32_t *)&mem[toc + 8] = 1;
    *(uint32_t *)&mem[toc + 32] = part;
    *(uint32_t *)&mem[toc + 36] = 0x800u;
    *(uint32_t *)&mem[toc + 44] = 0x00010000u;   /* host0=0, host1=1 */
    *(uint32_t *)&mem[toc + 48] = 8;
    p->offset = part; p->size = 0x800u; p->cacheline = 8; p->host0 = 0; p->host1 = 1;
    *(uint32_t *)&mem[part] = PART_MAGIC;
    *(uint32_t *)&mem[part + 4] = 0x00010000u;
    *(uint32_t *)&mem[part + 8] = 0x800u;
    *(uint32_t *)&mem[part + 12] = PART_HEADER;
    *(uint32_t *)&mem[part + 16] = down;
}

int main(void)
{
    K60Smem s; K60SmemPartition p; uint32_t off = 0, len = 0;
    int fails = 0;

    setup(&s, &p, 0x400u);

    if (k60_smem_alloc(&s, &p, 0x1234, 24, &off, &len) != K60SmemOk) { printf("FAIL alloc\n"); fails++; }
    if (len != 24) { printf("FAIL len=%u\n", len); fails++; }
    if (*(uint32_t *)&mem[p.offset + PART_HEADER] != (CANARY | (0x1234u << 16))) { printf("FAIL canary\n"); fails++; }
    if (*(uint32_t *)&mem[p.offset + PART_HEADER + 4] != 24) { printf("FAIL bytes\n"); fails++; }
    if (*(uint32_t *)&mem[p.offset + PART_HEADER + 8] != 0) { printf("FAIL pad\n"); fails++; }
    if (*(uint32_t *)&mem[p.offset + 12] != PART_HEADER + ENTRY + 24) { printf("FAIL up\n"); fails++; }
    if (k60_smem_find(&s, &p, 0x1234, &off, &len) != K60SmemOk || len != 24) { printf("FAIL roundtrip\n"); fails++; }

    if (k60_smem_alloc(&s, &p, 0x1234, 24, &off, &len) != K60SmemExists) { printf("FAIL dup\n"); fails++; }

    if (k60_smem_alloc(&s, &p, 0x2222, 24, &off, &len) != K60SmemOk) { printf("FAIL alloc2\n"); fails++; }

    setup(&s, &p, PART_HEADER + ENTRY + 8);
    if (k60_smem_alloc(&s, &p, 0x3333, 16, &off, &len) != K60SmemNoSpace) { printf("FAIL nospace\n"); fails++; }
    if (*(uint32_t *)&mem[p.offset + 12] != PART_HEADER) { printf("FAIL up moved on failure\n"); fails++; }

    printf(fails ? "TESTS FAILED %d\n" : "TESTS OK %d\n", fails ? fails : 5);
    return fails != 0;
}
