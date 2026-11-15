/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
#ifndef K60_ADSP_MDT_H
#define K60_ADSP_MDT_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define K60_ADSP_MDT_MAX_HEADERS 64u
#define K60_ADSP_MDT_RELOCATABLE (1u << 27)
#define K60_ADSP_MDT_HASH (2u << 24)
/* Read-only borrowed host/loader buffer, not a firmware/device reader. The
 * callback must perform no hardware access. Buffer lifetime covers prepare(). */
typedef int (*K60AdspMdtPiece)(void *, uint32_t index, const uint8_t **, size_t *);
typedef struct {
    uint32_t index, flags, file_offset, link_address;
    uint32_t copy_bytes, zero_bytes, source_is_piece;
    uint64_t destination;
} K60AdspMdtSegment;
typedef struct {
    uint32_t headers, count, hash_index, relocatable;
    uint32_t prefix_bytes, hash_bytes;
    uint64_t link_base, span, region_base, region_bytes;
    K60AdspMdtSegment segment[K60_ADSP_MDT_MAX_HEADERS];
} K60AdspMdtPlan;
enum {
    K60MdtOk = 0, K60MdtArgument = -1, K60MdtFormat = -2,
    K60MdtHeaders = -3, K60MdtHash = -4, K60MdtSegment = -5,
    K60MdtBounds = -6, K60MdtOverlap = -7, K60MdtPiece = -8,
    K60MdtCapacity = -9
};
/* Independently implemented from Qualcomm MDT format behavior documented by
 * Linux v6.1. Supports ELF32LE Hexagon ET_EXEC only; uniform relocation flags.
 * Validates every PT_LOAD source and produces metadata prefix+hash plus a plan.
 * Supports packed MDT metadata, contained monolithic bytes, or exact .bNN
 * borrowed buffers. BSS needs no piece. out and metadata must be writable and
 * disjoint from each other, mdt, and every callback-returned buffer. Inputs must
 * remain stable for the whole call, including during callbacks; source buffers
 * may alias one another. Size metadata for at least prefix_bytes+hash_bytes
 * (5404 for captured K60 MDT). These are caller preconditions, not runtime checks.
 * On error plan is zero, metadata is untouched. No allocation, payload copying,
 * physical mapping, SMC, authentication, resource vote or ownership claim. An
 * accepted format is NOT authenticated firmware. Existing PAS owner stays absent.
 */
int k60_adsp_mdt_prepare(const uint8_t *mdt, size_t mdt_bytes,
    uint64_t region_base, uint64_t region_bytes, K60AdspMdtPiece piece, void *context,
    uint8_t *metadata, size_t metadata_capacity, K60AdspMdtPlan *plan);
#ifdef __cplusplus
}
#endif
#endif
