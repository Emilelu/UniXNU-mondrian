/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Read-only FAT32 lookup for the payload memory disk. XNU has no msdos
 * filesystem, so the ADSP segments are reached by walking the volume the same
 * way an installer would: BPB, FAT chain, 8.3 directory entries. */

#ifndef K60_FAT_H
#define K60_FAT_H

#include <stddef.h>
#include <stdint.h>

enum {
	K60FatBadArg = -1,
	K60FatNoBpb = -2,
	K60FatNoEntry = -3,
	K60FatBadChain = -4,
};

typedef struct {
	uint32_t bytes_per_sector;
	uint32_t sectors_per_cluster;
	uint32_t reserved_sectors;
	uint32_t fats;
	uint32_t fat_sectors;
	uint32_t root_cluster;
	uint32_t total_sectors;
	uint32_t data_start;      /* sector offset of cluster 2 */
	uint32_t cluster_bytes;
	uint32_t clusters;
} K60FatVolume;

/* Parses the BPB. `size` is the usable byte count of the image. */
int k60_fat_open(const void *base, size_t size, K60FatVolume *vol);

/* Finds `dir` (may be "" for the root) then `name`, 8.3 or long, into
 * (offset, length) relative to `base`. Both are compared case-insensitively
 * with the dot dropped, so "adsp.b01" matches the entry "ADSP    B01". */
int k60_fat_find(const void *base, const K60FatVolume *vol,
    const char *dir, const char *name, uint32_t *offset, uint32_t *length);

/* Reads the "<key>=<base>@<size>" form memdev.c accepts, so the same boot
 * argument that creates md0 also tells us where its bytes live. Numbers may be
 * decimal or 0x-prefixed hex. Returns 0 on success. */
int k60_md_parse(const char *args, size_t args_len, const char *key,
    uint64_t *base, uint64_t *size);

#endif /* K60_FAT_H */
