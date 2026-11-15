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
    K60AdspReaderMissing=-6, K60AdspReaderBounds=-7,
    /* Well-formed container whose mode or size policy is not production:
     * mode != 0644 or packed_size != size. Distinct from header/bounds -7. */
    K60AdspReaderUnsupported=-8 };
#define K60_ADSP_BLOB_MAX_ENTRIES 64u
#define K60_ADSP_BLOB_MODE 0644u
/* Production K60A container, fixed and derived from one cursor (no second
 * shape is accepted):
 *   12-byte LE header: {u32 magic 'K60A', u32 count 1..64, u32 reserved 0}
 *   count x sequential records at the cursor:
 *     u32 name_len (includes the trailing NUL; canonical names are 9),
 *     u32 mode (fixed 0644), u64 size (raw body bytes),
 *     u64 packed_size (no compression in the kernel: must equal size),
 *   then the name_len name bytes, then the size body bytes.
 * Every name and body starts on an 8-byte boundary; each name and body block
 * is zero padded to the next 8-byte boundary; the final cursor is the total
 * container length. Linked symbols: const uint8_t k60_adsp_blob[] and
 * const uint64_t k60_adsp_blob_len, which includes ALL padding (P-196).
 * mode != 0644 or packed_size != size fails K60AdspReaderUnsupported, never
 * K60AdspReaderBounds. The generator/checker ship in scripts; Lead owns the
 * build flags, archive/manifest wiring and actual linked carrier. */
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
 * -5; absent carrier/part -6; malformed/out-of-bounds source -7; non-production
 * mode or packed size -8. Output state, name and destination must be disjoint;
 * destination cannot alias backing bytes. */
int k60_adsp_reader_read(K60AdspReader *, const char *, void *, uint32_t);
int k60_adsp_reader_borrow(K60AdspReader *, const char *, const uint8_t **, size_t *);
int k60_adsp_read(const char *, void *, uint32_t); /* K60AdspRead ABI, linked only */
/* Returns source for one validated plan segment; BSS needs no callback/read.
 * Used by stage 3, never the stage-4 final TCSR serialization section. */
int k60_adsp_image_segment(const K60OwnerImage *, const K60AdspMdtSegment *, const uint8_t **, size_t *);
int k60_adsp_owner_reader_init(K60AdspOwnerReader *, const K60AdspReader *, uint8_t *, size_t);
/* Production binding for k60_adsp_owner_image_open/close: read the linked
 * k60_adsp_blob carrier first; when the carrier is absent (k60_adsp_blob_len
 * is zero or the weak symbols are unresolved) fall back to the existing
 * k60_adsp_note_window/FAT route through the platform k60_adsp_legacy_reader
 * hook, matching the bt k60_bt_addon_load_blob() fallback shape. A present
 * but malformed carrier fails -7/-8 and never falls back. */
int k60_adsp_owner_reader_linked(K60AdspOwnerReader *, uint8_t *, size_t);
int k60_adsp_owner_image_open(void *, K60OwnerImage *);
void k60_adsp_owner_image_close(void *, K60OwnerImage *);
#ifdef __cplusplus
}
#endif
#endif
