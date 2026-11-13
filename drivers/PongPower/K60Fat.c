/* SPDX-License-Identifier: BSD-2-Clause-Patent */

#include "K60Fat.h"

static uint32_t
le16(const uint8_t *p)
{
	return (uint32_t)p[0] | ((uint32_t)p[1] << 8);
}

static uint32_t
le32(const uint8_t *p)
{
	return le16(p) | (le16(p + 2) << 16);
}

static uint32_t
fat_entry(const void *base, const K60FatVolume *vol, uint32_t cluster)
{
	const uint8_t *p = (const uint8_t *)base;
	uint32_t fat_off = vol->reserved_sectors * vol->bytes_per_sector;

	return le32(p + fat_off + cluster * 4u) & 0x0fffffffu;
}

static int
name_matches(const uint8_t *entry, const char *want)
{
	char flat[13];
	int n = 0;

	for (int i = 0; i < 8; i++) {
		char c = (char)entry[i];

		if (c == ' ') {
			continue;
		}
		flat[n++] = (c >= 'a' && c <= 'z') ? (char)(c - 32) : c;
	}
	if (entry[8] != ' ') {
		for (int i = 8; i < 11; i++) {
			char c = (char)entry[i];

			if (c == ' ') {
				continue;
			}
			flat[n++] = (c >= 'a' && c <= 'z') ? (char)(c - 32) : c;
		}
	}
	flat[n] = '\0';

	for (int i = 0; want[i] != '\0'; i++) {
		char c = want[i];

		if (c == '.') {
			continue;
		}
		if (c >= 'a' && c <= 'z') {
			c = (char)(c - 32);
		}
		if (flat[i] != c) {
			return 0;
		}
		if (flat[i] == '\0') {
			break;
		}
	}
	return flat[n] == '\0';
}

/* Walks the directory whose first cluster is `start`, returning the entry. */
static int
walk_dir(const void *base, const K60FatVolume *vol, uint32_t start,
    const char *name, uint32_t *first_cluster, uint32_t *length, int *is_dir)
{
	const uint8_t *p = (const uint8_t *)base;
	uint32_t cluster = start;
	uint32_t guard = 0;

	while (cluster >= 2 && cluster < vol->clusters + 2) {
		uint32_t base_off = (vol->data_start +
		    (cluster - 2) * vol->sectors_per_cluster) * vol->bytes_per_sector;

		for (uint32_t off = 0; off + 32 <= vol->cluster_bytes; off += 32) {
			const uint8_t *e = p + base_off + off;

			if (e[0] == 0x00) {
				return K60FatNoEntry;
			}
			/* deleted, long-name fragment, or volume label */
			if (e[0] == 0xe5 || (e[11] & 0x0f) == 0x0f || (e[11] & 0x08)) {
				continue;
			}
			if (name_matches(e, name)) {
				*first_cluster = (le16(e + 20) << 16) | le16(e + 26);
				*length = le32(e + 28);
				*is_dir = (e[11] & 0x10) != 0;
				return 0;
			}
		}
		cluster = fat_entry(base, vol, cluster);
		if (++guard > 65536u) {
			return K60FatBadChain;
		}
	}
	return K60FatNoEntry;
}

int
k60_fat_open(const void *base, size_t size, K60FatVolume *vol)
{
	const uint8_t *p = (const uint8_t *)base;

	if (base == NULL || vol == NULL || size < 1024) {
		return K60FatBadArg;
	}
	if (p[510] != 0x55 || p[511] != 0xaa) {
		return K60FatNoBpb;
	}
	vol->bytes_per_sector = le16(p + 11);
	vol->sectors_per_cluster = p[13];
	vol->reserved_sectors = le16(p + 14);
	vol->fats = p[16];
	vol->fat_sectors = le32(p + 36);
	vol->root_cluster = le32(p + 44);
	vol->total_sectors = le32(p + 32);
	if (!vol->bytes_per_sector || !vol->sectors_per_cluster || !vol->fats ||
	    !vol->fat_sectors) {
		return K60FatNoBpb;
	}
	vol->cluster_bytes = vol->bytes_per_sector * vol->sectors_per_cluster;
	vol->data_start = vol->reserved_sectors + vol->fats * vol->fat_sectors;
	vol->clusters = (vol->total_sectors - vol->data_start) /
	    vol->sectors_per_cluster;
	if (vol->clusters == 0) {
		return K60FatNoBpb;
	}
	return 0;
}

int
k60_fat_find(const void *base, const K60FatVolume *vol,
    const char *dir, const char *name, uint32_t *offset, uint32_t *length)
{
	uint32_t cluster = vol->root_cluster;
	uint32_t len = 0;
	int is_dir = 0;
	int rc;

	if (dir != NULL && dir[0] != '\0') {
		rc = walk_dir(base, vol, cluster, dir, &cluster, &len, &is_dir);
		if (rc != 0) {
			return rc;
		}
		if (!is_dir) {
			return K60FatNoEntry;
		}
	}
	rc = walk_dir(base, vol, cluster, name, &cluster, &len, &is_dir);
	if (rc != 0) {
		return rc;
	}
	if (is_dir) {
		return K60FatNoEntry;
	}
	*length = len;
	*offset = (vol->data_start + (cluster - 2) * vol->sectors_per_cluster) *
	    vol->bytes_per_sector;
	return 0;
}
