/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/* Adapted from pong-power c37179ed QcomSmem.c (BSD-2-Clause-Patent). No heap
 * allocation or cached Android data. Reads are aligned and partition-bounded. */
#include "K60Smem.h"

#define TOC_MAGIC 0x434f5424u
#define PART_MAGIC 0x54525024u
#define CANARY 0xa5a5u
#define PART_HEADER 32u
#define ENTRY 16u
static int fits(uint64_t at, uint64_t bytes, uint64_t size) { return at <= size && bytes <= size - at; }
static uint32_t rd(const K60Smem *s, uint32_t at)
{
    return *(volatile uint32_t *)(s->base + at);
}
static void acquire(void)
{
#if defined(__aarch64__) && defined(KERNEL)
    __asm__ volatile("dmb osh" ::: "memory");
#endif
}
static uint32_t align_up(uint32_t v, uint32_t n) { return (v + n - 1) & ~(n - 1); }
static int partition_bounds(const K60Smem *s, const K60SmemPartition *p, uint32_t *up, uint32_t *down)
{
    if (!s || !s->base || !p || s->size < 8192 || !fits(p->offset, p->size, s->size - 4096) ||
        (p->offset & 7) || p->size < 2 * ENTRY + PART_HEADER || p->cacheline < 8 ||
        p->cacheline > 4096 || (p->cacheline & (p->cacheline - 1))) return K60SmemBadPartition;
    const uint32_t hosts = (uint32_t)p->host0 | (uint32_t)p->host1 << 16;
    if (rd(s, p->offset) != PART_MAGIC || rd(s, p->offset + 4) != hosts ||
        rd(s, p->offset + 8) != p->size) return K60SmemBadPartition;
    *up = rd(s, p->offset + 12); *down = rd(s, p->offset + 16);
    acquire();
    if (*up < PART_HEADER || *up > *down || *down > p->size || (*up & 7) || (*down & 7))
        return K60SmemBadPartition;
    return K60SmemOk;
}

int k60_smem_partition(const K60Smem *s, uint16_t host, uint16_t remote, K60SmemPartition *out)
{
    if (!s || !s->base || !out || s->size < 8192 || (s->size & 4095)) return K60SmemNoTable;
    const uint32_t toc = s->size - 4096;
    if (rd(s, toc) != TOC_MAGIC || rd(s, toc + 4) != 1) return K60SmemNoTable;
    const uint32_t count = rd(s, toc + 8);
    if (count > (4096 - 32) / 48) return K60SmemNoTable;
    acquire();
    for (uint32_t i = 0; i < count; ++i) {
        const uint32_t e = toc + 32 + i * 48;
        const uint32_t offset = rd(s, e), size = rd(s, e + 4), hosts = rd(s, e + 12);
        const uint16_t h0 = (uint16_t)hosts, h1 = (uint16_t)(hosts >> 16);
        if (!offset || !size || !((h0 == host && h1 == remote) || (h0 == remote && h1 == host))) continue;
        const uint32_t cacheline = rd(s, e + 16);
        K60SmemPartition p = {offset, size, cacheline ? cacheline : 8, h0, h1};
        uint32_t up, down;
        const int rc = partition_bounds(s, &p, &up, &down);
        if (rc) return rc;
        *out = p;
        return K60SmemOk;
    }
    return K60SmemNoPartition;
}

int k60_smem_find(const K60Smem *s, const K60SmemPartition *p, uint16_t item, uint32_t *offset, uint32_t *size)
{
    if (!offset || !size) return K60SmemBadPartition;
    uint32_t up, down;
    const int rc = partition_bounds(s, p, &up, &down);
    if (rc) return rc;
    uint32_t at = PART_HEADER;
    while (at < up) {
        if ((at & 7) || !fits(at, ENTRY, up)) return K60SmemCorrupt;
        const uint32_t w0 = rd(s, p->offset + at), bytes = rd(s, p->offset + at + 4);
        const uint32_t pads = rd(s, p->offset + at + 8), header_pad = pads >> 16, data_pad = pads & 65535;
        if ((w0 & 65535) != CANARY || (header_pad & 7) || (bytes & 7) || data_pad > bytes ||
            !fits((uint64_t)at + ENTRY + header_pad, bytes, up)) return K60SmemCorrupt;
        if ((w0 >> 16) == item) {
            *offset = p->offset + at + ENTRY + header_pad; *size = bytes - data_pad;
            return K60SmemOk;
        }
        at += ENTRY + header_pad + bytes;
    }
    if (at != up) return K60SmemCorrupt;
    const uint32_t header = align_up(ENTRY, p->cacheline);
    if (p->size < header) return K60SmemCorrupt;
    at = p->size - header;
    while (at > down) {
        if ((at & 7) || !fits(at, ENTRY, p->size)) return K60SmemCorrupt;
        const uint32_t w0 = rd(s, p->offset + at), bytes = rd(s, p->offset + at + 4);
        const uint32_t pads = rd(s, p->offset + at + 8);
        if ((w0 & 65535) != CANARY || (bytes & 7) || (pads & 65535) > bytes || bytes > at ||
            at - bytes < down) return K60SmemCorrupt;
        if ((w0 >> 16) == item) {
            *offset = p->offset + at - bytes; *size = bytes - (pads & 65535);
            return K60SmemOk;
        }
        if (at - bytes == down) return K60SmemMissing;
        if ((uint64_t)bytes + header > at || at - bytes - header < down) return K60SmemCorrupt;
        at -= bytes + header;
    }
    return K60SmemMissing;
}
