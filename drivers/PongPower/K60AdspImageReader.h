/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
#ifndef K60_ADSP_IMAGE_READER_H
#define K60_ADSP_IMAGE_READER_H
#include "K60Fat.h"
#include "K60AdspOwnerStages.h"
#ifdef __cplusplus
extern "C" {
#endif
#ifndef K60_ADSP_READ_TYPE_DEFINED
#define K60_ADSP_READ_TYPE_DEFINED
typedef int (*K60AdspRead)(const char *part, void *dst, uint32_t bytes);
#endif
enum { K60AdspReaderBadArgument=-1, K60AdspReaderReadFailed=-5,
    K60AdspReaderMissing=-6, K60AdspReaderBounds=-7 };
#define K60_ADSP_BLOB_MAX_ENTRIES 64u
/* K60A: 8-byte LE {magic,count}; count packed 10-byte LE {u16 name_len,
 * u32 size,u32 absolute_offset}; concatenated names; zero padding to 8 bytes;
 * ordered, nonoverlapping bodies each zero padded to 8 bytes. Linked symbols:
 * const uint8_t k60_adsp_blob[] and const uint64_t k60_adsp_blob_len, including
 * ALL body padding. No generator, build flags or real blob are supplied here. */
typedef struct {
    const uint8_t *base;
    size_t bytes;
    K60FatVolume fat;
    unsigned mode;
} K60AdspReader;
/* Zero-initialize/configure before use. Caller pins source/state/metadata for
 * the full session (indefinitely after published/poisoned result). Only firmware
 * source bytes are immutable; metadata is writable/disjoint and state mutates.
 * No concurrent initialization or caller-directed close during engine use. */
typedef struct {
    K60AdspReader source;
    uint8_t *metadata;
    size_t capacity;
    unsigned active;
    K60OwnerImage *opened_image;
} K60AdspOwnerReader;
int k60_adsp_reader_blob(K60AdspReader *, const void *, size_t);
int k60_adsp_reader_linked(K60AdspReader *);
/* Explicit mapped-DT/FAT fallback; never discovers/maps physical memory itself.
 * Existing k60_fat_open is called only after strict geometry validation. Files
 * must be contiguous for stable borrowing; fragmented/corrupt chains fail -7. */
int k60_adsp_reader_fat(K60AdspReader *, const void *, size_t);
/* Canonical adsp.mdt/adsp.bNN; mdt and adsp aliases both select adsp.mdt.
 * All errors leave destination/borrow outputs unchanged. Exact size mismatch is
 * -5; absent carrier/part -6; malformed/out-of-bounds source -7. Output state,
 * name and destination must be disjoint; destination cannot alias backing bytes. */
int k60_adsp_reader_read(K60AdspReader *, const char *, void *, uint32_t);
int k60_adsp_reader_borrow(K60AdspReader *, const char *, const uint8_t **, size_t *);
int k60_adsp_read(const char *, void *, uint32_t); /* K60AdspRead ABI, linked only */
/* Returns source for one validated plan segment; BSS needs no callback/read.
 * Used by stage 3, never the stage-4 final TCSR serialization section. */
int k60_adsp_image_segment(const K60OwnerImage *, const K60AdspMdtSegment *, const uint8_t **, size_t *);
int k60_adsp_owner_reader_init(K60AdspOwnerReader *, const K60AdspReader *, uint8_t *, size_t);
int k60_adsp_owner_image_open(void *, K60OwnerImage *);
void k60_adsp_owner_image_close(void *, K60OwnerImage *);
#ifdef __cplusplus
}
#endif
#endif
