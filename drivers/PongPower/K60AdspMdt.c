/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
#include "K60AdspMdt.h"
#define TYPE_MASK (7u << 24)
#define PAGE 4096u
static uint16_t u16(const uint8_t *p) { return (uint16_t)(p[0] | (uint16_t)p[1] << 8); }
static uint32_t u32(const uint8_t *p) { return (uint32_t)u16(p) | (uint32_t)u16(p + 2) << 16; }
static int within(uint64_t at, uint64_t n, uint64_t size) { return at <= size && n <= size - at; }
static const uint8_t *ph(const uint8_t *p, unsigned i) { return p + 52u + (size_t)i * 32u; }
static int ranges(uint64_t a, uint64_t an, uint64_t b, uint64_t bn)
{ return an && bn && a < b + bn && b < a + an; }
static int borrowed(K60AdspMdtPiece piece, void *ctx, uint32_t i, uint32_t n,
                    const uint8_t **out)
{
    size_t bytes = 0; const uint8_t *p = 0;
    if (!piece || piece(ctx, i, &p, &bytes) || !p || bytes != n) return K60MdtPiece;
    *out = p; return 0;
}
int k60_adsp_mdt_prepare(const uint8_t *mdt, size_t size,
    uint64_t base, uint64_t bytes, K60AdspMdtPiece piece, void *ctx,
    uint8_t *metadata, size_t capacity, K60AdspMdtPlan *out)
{
    K60AdspMdtPlan p = {0};
    if (!out) return K60MdtArgument;
    *out = p;
    if (!mdt || !metadata || !bytes || (base & (PAGE - 1u)) ||
        (bytes & (PAGE - 1u)) || bytes > UINT64_MAX - base) return K60MdtArgument;
    if (size < 52 || mdt[0] != 0x7f || mdt[1] != 'E' || mdt[2] != 'L' ||
        mdt[3] != 'F' || mdt[4] != 1 || mdt[5] != 1 || mdt[6] != 1 ||
        u16(mdt + 16) != 2 || u16(mdt + 18) != 164 || u32(mdt + 20) != 1)
        return K60MdtFormat;
    p.headers = u16(mdt + 44);
    if (u32(mdt + 28) != 52 || u16(mdt + 40) != 52 || u16(mdt + 42) != 32 ||
        p.headers < 2 || p.headers > K60_ADSP_MDT_MAX_HEADERS ||
        !within(52, (uint64_t)p.headers * 32, size)) return K60MdtHeaders;
    const uint8_t *first = ph(mdt, 0);
    p.prefix_bytes = u32(first + 16);
    if (u32(first) != 0 || u32(first + 4) ||
        (u32(first + 24) & TYPE_MASK) == K60_ADSP_MDT_HASH ||
        p.prefix_bytes < 52u + p.headers * 32u || p.prefix_bytes > size)
        return K60MdtHeaders;
    unsigned hashes = 0; uint64_t lo = UINT64_MAX, hi = 0;
    for (uint32_t i = 1; i < p.headers; ++i) {
        const uint8_t *h = ph(mdt, i);
        uint32_t flags = u32(h + 24), files = u32(h + 16), mem = u32(h + 20);
        if ((flags & TYPE_MASK) == K60_ADSP_MDT_HASH) {
            if (++hashes != 1 || !files) return K60MdtHash;
            p.hash_index = i; p.hash_bytes = files; continue;
        }
        if (u32(h) != 1) continue;
        if (files > mem) return K60MdtSegment;
        if (!mem) continue;
        uint32_t address = u32(h + 12), off = u32(h + 4), align = u32(h + 28);
        uint64_t end = (uint64_t)address + mem;
        if (end > (UINT64_C(1) << 32) || (uint64_t)off + files > (UINT64_C(1) << 32) ||
            (align > 1 && ((align & (align - 1u)) ||
            ((u32(h + 8) ^ off) & (align - 1u))))) return K60MdtBounds;
        uint32_t reloc = !!(flags & K60_ADSP_MDT_RELOCATABLE);
        if (p.count && p.relocatable != reloc) return K60MdtSegment;
        p.relocatable = reloc;
        K60AdspMdtSegment *s = &p.segment[p.count++];
        s->index = i; s->flags = flags; s->file_offset = off; s->link_address = address;
        s->copy_bytes = files; s->zero_bytes = mem - files;
        if (address < lo) lo = address;
        if (end > hi) hi = end;
    }
    if (hashes != 1) return K60MdtHash;
    if (!p.count || (lo & (PAGE - 1u))) return K60MdtSegment;
    p.link_base = lo; p.span = ((hi + PAGE - 1u) & ~(uint64_t)(PAGE - 1u)) - lo;
    p.region_base = base; p.region_bytes = bytes;
    if (p.span > bytes) return K60MdtBounds;
    const uint8_t *hash;
    uint64_t total = (uint64_t)p.prefix_bytes + p.hash_bytes;
    int packed = total == size;
    if (packed) hash = mdt + p.prefix_bytes;
    else if (within(u32(ph(mdt, p.hash_index) + 4), p.hash_bytes, size)) {
        uint32_t at = u32(ph(mdt, p.hash_index) + 4);
        if (at < p.prefix_bytes) return K60MdtHash;
        hash = mdt + at;
    } else {
        int rc = borrowed(piece, ctx, p.hash_index, p.hash_bytes, &hash);
        if (rc) return rc;
    }
    for (uint32_t i = 0; i < p.count; ++i) {
        K60AdspMdtSegment *s = &p.segment[i];
        uint64_t n = (uint64_t)s->copy_bytes + s->zero_bytes;
        uint64_t origin = p.relocatable ? lo : base;
        if (s->link_address < origin || !within((uint64_t)s->link_address - origin, n, bytes))
            return K60MdtBounds;
        s->destination = base + ((uint64_t)s->link_address - origin);
        for (uint32_t j = 0; j < i; ++j) {
            const K60AdspMdtSegment *prev = &p.segment[j];
            if (ranges(s->destination, n, prev->destination,
                       (uint64_t)prev->copy_bytes + prev->zero_bytes) ||
                ranges(s->file_offset, s->copy_bytes, prev->file_offset, prev->copy_bytes))
                return K60MdtOverlap;
        }
        if (!s->copy_bytes) continue;
        if (!packed && within(s->file_offset, s->copy_bytes, size)) {
            if (s->file_offset < p.prefix_bytes ||
                ranges(s->file_offset, s->copy_bytes,
                       u32(ph(mdt, p.hash_index) + 4), p.hash_bytes)) return K60MdtOverlap;
        } else {
            const uint8_t *payload;
            int rc = borrowed(piece, ctx, s->index, s->copy_bytes, &payload);
            if (rc) return rc;
            s->source_is_piece = 1;
        }
    }
    if (total > capacity || total > SIZE_MAX) return K60MdtCapacity;
    for (uint32_t i = 0; i < p.prefix_bytes; ++i) metadata[i] = mdt[i];
    for (uint32_t i = 0; i < p.hash_bytes; ++i) metadata[p.prefix_bytes + (size_t)i] = hash[i];
    *out = p;
    return 0;
}
