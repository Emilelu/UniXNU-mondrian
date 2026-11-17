/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Ported from pong-power QcomMdt.h, Copyright (c) 2026 UniXNU contributors,
 * SPDX-License-Identifier: BSD-2-Clause-Patent. Renamed to the K60 namespace.
 *
 * Qualcomm signed firmware images (.mbn, an ELF32 or ELF64 whose program headers carry the segment types in p_flags) as the peripheral
 * authentication service takes them: the metadata handed to the secure world (the ELF and program headers followed by the hash
 * segment), the extent of the loadable segments and where each one goes in the carveout. Pure parsing over a read callback: no
 * allocation, no hardware, so the same code runs in the kernel and in the host tests. */
#ifndef K60_MDT_H
#define K60_MDT_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

#define K60_MDT_MAX_SEGMENTS 64u
#define K60_MDT_TYPE_MASK (7u << 24)
#define K60_MDT_TYPE_HASH (2u << 24)
#define K60_MDT_RELOCATABLE (1u << 27)

/* Reads length bytes at offset of the image file into to; returns 0 on success. */
typedef int (*K60MdtRead)(void *context, uint64_t offset, void *to, size_t length);

typedef struct {
    uint64_t file_offset, file_size, memory_size, address;  /* address: p_paddr */
    uint32_t flags;
    uint8_t load;  /* a loadable segment (PT_LOAD, not the hash, memory size not zero) */
} K60MdtSegment;

typedef struct {
    uint8_t elf64;
    uint32_t count;
    K60MdtSegment segment[K60_MDT_MAX_SEGMENTS];
    int hash;                        /* index of the hash segment */
    uint64_t header_size;            /* p_filesz of the first program header: ELF header plus program headers */
    uint64_t min_address, max_address;  /* of the loadable segments */
    uint8_t relocatable;
    uint64_t file_size;
} K60MdtImage;

enum {
    K60MdtOk = 0,
    K60MdtReadError = -1,
    K60MdtNotElf = -2,
    K60MdtBadHeaders = -3,
    K60MdtNoHash = -4,
    K60MdtTooMany = -5,
    K60MdtNoSegments = -6,
    K60MdtOutside = -7,
    K60MdtTooSmall = -8,
};

/* Parses the ELF and program headers of an image of file_size bytes. */
int k60_mdt_parse(K60MdtImage *image, uint64_t file_size, K60MdtRead read, void *context);

/* Bytes of the metadata blob for the authentication service: the header part and the hash segment. */
uint64_t k60_mdt_metadata_size(const K60MdtImage *image);

/* Writes the metadata blob (k60_mdt_metadata_size bytes) to to. The hash segment must lie inside the file: images split into .bNN
 * files are joined into one .mbn on the host before they are installed. */
int k60_mdt_metadata(const K60MdtImage *image, K60MdtRead read, void *context, uint8_t *to, uint64_t capacity);

/* Bytes the loadable segments span (the end rounded up to 4 KiB, minus the lowest address): the size to hand to the memory setup call
 * of a relocatable image. */
uint64_t k60_mdt_span(const K60MdtImage *image);

/* Offset of a loadable segment inside a carveout of region_size bytes at region_base: relocatable images are placed by their offset from
 * the lowest segment, fixed ones by their address. Returns K60MdtOutside if the segment does not fit. */
int k60_mdt_place(const K60MdtImage *image, unsigned index, uint64_t region_base, uint64_t region_size, uint64_t *offset);

/* A split image (NAME.b00, NAME.b01, ... as found on the device's firmware partition) read as the joined image: the bytes of program
 * header i's segment come from piece i (NAME.bNN) at the segment's file offset, piece 0 being the ELF and program headers; whatever
 * lies between the pieces reads as zero. The pieces are the caller's files. */
typedef int (*K60MdtPieceRead)(void *context, unsigned piece, uint64_t offset, void *to, size_t length);
typedef struct {
    uint32_t count;
    struct {uint64_t offset, size;} piece[K60_MDT_MAX_SEGMENTS];  /* size 0: no piece file for this header */
    uint64_t size;                                                  /* bytes of the joined image */
} K60MdtSplit;

/* Lays out the pieces from the headers (the bytes of NAME.b00, or the start of NAME.mdt). */
int k60_mdt_split(K60MdtSplit *split, const uint8_t *headers, size_t length);
/* Reads a range of the joined image. */
int k60_mdt_split_read(const K60MdtSplit *split, K60MdtPieceRead read, void *context, uint64_t offset, void *to, size_t length);

#ifdef __cplusplus
}
#endif
#endif
