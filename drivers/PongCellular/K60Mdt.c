/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Ported from pong-power QcomMdt.c, Copyright (c) 2026 UniXNU contributors. */
#include "K60Mdt.h"

#define PT_LOAD_ 1u

static uint16_t le16(const uint8_t *p) {return (uint16_t)(p[0] | (uint16_t)p[1] << 8);}
static uint32_t le32(const uint8_t *p) {return (uint32_t)le16(p) | (uint32_t)le16(p + 2) << 16;}
static uint64_t le64(const uint8_t *p) {return (uint64_t)le32(p) | (uint64_t)le32(p + 4) << 32;}
static int fits(uint64_t at, uint64_t length, uint64_t size) {return at <= size && length <= size - at;}

int k60_mdt_parse(K60MdtImage *image, uint64_t file_size, K60MdtRead read, void *context)
{
    uint8_t e[64];
    if (!image || !read) return K60MdtReadError;
    *image = (K60MdtImage){0};
    image->hash = -1;
    image->file_size = file_size;
    if (file_size < 52 || read(context, 0, e, file_size < 64 ? 52 : 64)) return file_size < 52 ? K60MdtTooSmall : K60MdtReadError;
    if (e[0] != 0x7f || e[1] != 'E' || e[2] != 'L' || e[3] != 'F' || e[5] != 1 /* little endian */) return K60MdtNotElf;
    const int elf64 = e[4] == 2;
    if (!elf64 && e[4] != 1) return K60MdtNotElf;
    if (elf64 && file_size < 64) return K60MdtTooSmall;
    const uint64_t phoff = elf64 ? le64(e + 32) : le32(e + 28);
    const unsigned phentsize = elf64 ? le16(e + 54) : le16(e + 42), phnum = elf64 ? le16(e + 56) : le16(e + 44);
    if (phentsize != (elf64 ? 56u : 32u) || !phnum) return K60MdtBadHeaders;
    if (phnum > K60_MDT_MAX_SEGMENTS) return K60MdtTooMany;
    if (!fits(phoff, (uint64_t)phentsize * phnum, file_size)) return K60MdtBadHeaders;
    image->elf64 = (uint8_t)elf64;
    image->count = phnum;
    uint64_t lo = UINT64_MAX, hi = 0;
    for (unsigned i = 0; i < phnum; ++i) {
        uint8_t p[56];
        if (read(context, phoff + (uint64_t)i * phentsize, p, phentsize)) return K60MdtReadError;
        K60MdtSegment *s = &image->segment[i];
        const uint32_t type = le32(p);
        if (elf64) {
            s->flags = le32(p + 4); s->file_offset = le64(p + 8); s->address = le64(p + 24);
            s->file_size = le64(p + 32); s->memory_size = le64(p + 40);
        } else {
            s->file_offset = le32(p + 4); s->address = le32(p + 12); s->file_size = le32(p + 16);
            s->memory_size = le32(p + 20); s->flags = le32(p + 24);
        }
        if ((s->flags & K60_MDT_TYPE_MASK) == K60_MDT_TYPE_HASH) {
            if (image->hash < 0) image->hash = (int)i;
            continue;
        }
        if (type != PT_LOAD_ || !s->memory_size) continue;
        if (s->file_size > s->memory_size) return K60MdtBadHeaders;
        if (s->address + s->memory_size < s->address) return K60MdtBadHeaders;
        s->load = 1;
        if (s->flags & K60_MDT_RELOCATABLE) image->relocatable = 1;
        if (s->address < lo) lo = s->address;
        if (s->address + s->memory_size > hi) hi = s->address + s->memory_size;
    }
    if (image->hash < 0) return K60MdtNoHash;
    if (hi == 0) return K60MdtNoSegments;
    image->header_size = image->segment[0].file_size;
    /* The first program header (PT_NULL) covers the ELF header and the program headers themselves. */
    if (!image->header_size || !fits(0, image->header_size, file_size) || image->header_size < phoff + (uint64_t)phentsize * phnum)
        return K60MdtBadHeaders;
    image->min_address = lo;
    image->max_address = hi;
    return K60MdtOk;
}

uint64_t k60_mdt_metadata_size(const K60MdtImage *image)
{
    return image->header_size + image->segment[image->hash].file_size;
}

int k60_mdt_metadata(const K60MdtImage *image, K60MdtRead read, void *context, uint8_t *to, uint64_t capacity)
{
    const K60MdtSegment *hash = &image->segment[image->hash];
    if (capacity < k60_mdt_metadata_size(image)) return K60MdtTooSmall;
    uint64_t hash_offset;
    /* A hash packed right behind the headers (the split .mdt form) or a hash segment inside the file. */
    if (image->header_size + hash->file_size == image->file_size) hash_offset = image->header_size;
    else if (fits(hash->file_offset, hash->file_size, image->file_size)) hash_offset = hash->file_offset;
    else return K60MdtOutside;
    if (read(context, 0, to, (size_t)image->header_size)) return K60MdtReadError;
    if (read(context, hash_offset, to + image->header_size, (size_t)hash->file_size)) return K60MdtReadError;
    return K60MdtOk;
}

/* The secure world takes the span with its end rounded up to a 4 KiB page and refuses an unaligned one. */
uint64_t k60_mdt_span(const K60MdtImage *image) {return ((image->max_address + 0xfff) & ~0xfffull) - image->min_address;}

int k60_mdt_place(const K60MdtImage *image, unsigned index, uint64_t region_base, uint64_t region_size, uint64_t *offset)
{
    if (index >= image->count || !image->segment[index].load) return K60MdtOutside;
    const K60MdtSegment *s = &image->segment[index];
    uint64_t at;
    if (image->relocatable) at = s->address - image->min_address;
    else if (s->address >= region_base) at = s->address - region_base;
    else return K60MdtOutside;
    if (!fits(at, s->memory_size, region_size)) return K60MdtOutside;
    if (s->file_size && !fits(s->file_offset, s->file_size, image->file_size)) return K60MdtOutside;
    *offset = at;
    return K60MdtOk;
}

int k60_mdt_split(K60MdtSplit *split, const uint8_t *headers, size_t length)
{
    if (!split || !headers) return K60MdtReadError;
    *split = (K60MdtSplit){0};
    if (length < 52) return K60MdtTooSmall;
    const uint8_t *e = headers;
    if (e[0] != 0x7f || e[1] != 'E' || e[2] != 'L' || e[3] != 'F' || e[5] != 1 || (e[4] != 1 && e[4] != 2)) return K60MdtNotElf;
    const int elf64 = e[4] == 2;
    if (elf64 && length < 64) return K60MdtTooSmall;
    const uint64_t phoff = elf64 ? le64(e + 32) : le32(e + 28);
    const unsigned phentsize = elf64 ? le16(e + 54) : le16(e + 42), phnum = elf64 ? le16(e + 56) : le16(e + 44);
    if (phentsize != (elf64 ? 56u : 32u) || !phnum) return K60MdtBadHeaders;
    if (phnum > K60_MDT_MAX_SEGMENTS) return K60MdtTooMany;
    if (!fits(phoff, (uint64_t)phentsize * phnum, length)) return K60MdtBadHeaders;
    split->count = phnum;
    for (unsigned i = 0; i < phnum; ++i) {
        const uint8_t *p = e + phoff + (uint64_t)i * phentsize;
        const uint64_t offset = elf64 ? le64(p + 8) : le32(p + 4), size = elf64 ? le64(p + 32) : le32(p + 16);
        if (offset + size < offset) return K60MdtBadHeaders;
        split->piece[i].offset = offset;
        split->piece[i].size = size;
        if (size && offset + size > split->size) split->size = offset + size;
    }
    /* piece 0 must be the headers themselves */
    if (split->piece[0].offset || split->piece[0].size < phoff + (uint64_t)phentsize * phnum) return K60MdtBadHeaders;
    return K60MdtOk;
}

int k60_mdt_split_read(const K60MdtSplit *split, K60MdtPieceRead read, void *context, uint64_t offset, void *to, size_t length)
{
    uint8_t *out = to;
    if (!split || !read || !to || !fits(offset, length, split->size)) return K60MdtOutside;
    while (length) {
        /* the piece holding offset, or else the distance to the next piece */
        uint64_t take = length, gap_end = split->size;
        int hit = -1;
        for (unsigned i = 0; i < split->count; ++i) {
            const uint64_t at = split->piece[i].offset, size = split->piece[i].size;
            if (!size) continue;
            if (offset >= at && offset - at < size) {hit = (int)i; break;}
            if (at > offset && at < gap_end) gap_end = at;
        }
        if (hit >= 0) {
            const uint64_t left = split->piece[hit].offset + split->piece[hit].size - offset;
            if (take > left) take = left;
            if (read(context, (unsigned)hit, offset - split->piece[hit].offset, out, (size_t)take)) return K60MdtReadError;
        } else {
            if (take > gap_end - offset) take = gap_end - offset;
            for (uint64_t i = 0; i < take; ++i) out[i] = 0;
        }
        out += take;
        offset += take;
        length -= (size_t)take;
    }
    return K60MdtOk;
}
