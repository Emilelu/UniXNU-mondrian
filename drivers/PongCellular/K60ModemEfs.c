/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* The EFS image table and the scatter-to-copy mapping. Protocol only: no UFS,
 * no SCM, no allocation, so the host test and the kernel share it. */

#include "K60ModemEfs.h"

typedef struct {
	const char *boot;
	const char *partition;
} K60EfsImage;

static const K60EfsImage k60_efs_images[K60_EFS_IMAGE_COUNT] = {
	{ "/boot/modem_fs1", "modemst1" },
	{ "/boot/modem_fs2", "modemst2" },
	{ "/boot/modem_fsg", "fsg" },
	{ "/boot/modem_fsc", "fsc" },
};

const char *
k60_efs_partition(uint32_t storage)
{
	if (storage == 0 || storage > K60_EFS_IMAGE_COUNT) {
		return NULL;
	}
	return k60_efs_images[storage - 1].partition;
}

const char *
k60_efs_boot_path(uint32_t storage)
{
	if (storage == 0 || storage > K60_EFS_IMAGE_COUNT) {
		return NULL;
	}
	return k60_efs_images[storage - 1].boot;
}

int
k60_efs_name_matches(const void *entry, size_t entry_bytes, const char *name)
{
	const uint8_t *at = (const uint8_t *)entry;
	size_t units;
	size_t i;

	if (entry == NULL || name == NULL || entry_bytes < 2) {
		return -1;
	}
	units = entry_bytes / 2;
	if (units > K60_EFS_GPT_NAME_BYTES / 2) {
		units = K60_EFS_GPT_NAME_BYTES / 2;
	}
	for (i = 0; i < units; i++) {
		const uint16_t unit = (uint16_t)(at[2 * i] | (uint16_t)(at[2 * i + 1] << 8));

		if (name[i] == '\0') {
			/* The entry may not run past the end of the name. */
			return unit == 0 ? 0 : -1;
		}
		if (unit != (uint16_t)(uint8_t)name[i]) {
			return -1;
		}
	}
	/* The name is longer than the entry: only a zero terminated entry can
	 * match, and a 36-unit entry is never terminated. */
	return -1;
}

int
k60_efs_plan(const K60RmtfsRequest *request, uint64_t image_bytes,
    uint64_t window_base, uint64_t window_bytes, K60EfsSpan *out, size_t cap)
{
	size_t written = 0;
	size_t i;

	if (request == NULL || out == NULL || request->message != K60_RMTFS_RW) {
		return -1;
	}
	if (request->vectors == 0 || request->vectors > cap ||
	    request->vectors > K60_RMTFS_MAX_VECS) {
		return -1;
	}
	for (i = 0; i < request->vectors; i++) {
		const K60RmtfsVec *vec = &request->table[i];
		const uint64_t image_offset = (uint64_t)vec->block_offset * K60_RMTFS_BLOCK;
		const uint64_t bytes = (uint64_t)vec->block_length * K60_RMTFS_BLOCK;

		if (vec->block_length == 0) {
			/* A zero-length scatter entry is malformed on the wire; the
			 * protocol check refuses it, so the plan must not quietly drop
			 * it and report success for the rest. */
			return -1;
		}
		if (image_offset > image_bytes || bytes > image_bytes - image_offset) {
			return -1;
		}
		if (vec->physical < window_base ||
		    (uint64_t)vec->physical - window_base > window_bytes ||
		    bytes > window_bytes - ((uint64_t)vec->physical - window_base)) {
			return -1;
		}
		out[written].image_offset = image_offset;
		out[written].buffer_offset = (uint64_t)vec->physical - window_base;
		out[written].bytes = (uint32_t)bytes;
		written++;
	}
	if (written == 0) {
		return -1;
	}
	return (int)written;
}

int
k60_efs_copy(const K60EfsSpan *spans, size_t count, int direction,
    uint8_t *image, size_t image_bytes, uint8_t *window, size_t window_bytes)
{
	if (spans == NULL || image == NULL || window == NULL || count == 0) {
		return -1;
	}
	if (direction != K60_EFS_TO_WINDOW && direction != K60_EFS_TO_IMAGE) {
		return -1;
	}
	for (size_t i = 0; i < count; i++) {
		const K60EfsSpan *span = &spans[i];

		if ((uint64_t)span->bytes > image_bytes ||
		    span->image_offset > image_bytes - span->bytes) {
			return -1;
		}
		if ((uint64_t)span->bytes > window_bytes ||
		    span->buffer_offset > window_bytes - span->bytes) {
			return -1;
		}
		for (uint32_t b = 0; b < span->bytes; b++) {
			uint64_t from = direction == K60_EFS_TO_WINDOW ?
			    span->image_offset + b : span->buffer_offset + b;
			uint64_t to = direction == K60_EFS_TO_WINDOW ?
			    span->buffer_offset + b : span->image_offset + b;

			if (direction == K60_EFS_TO_WINDOW) {
				window[to] = image[from];
			} else {
				image[to] = window[from];
			}
		}
	}
	return 0;
}

int
k60_efs_serve_read(const K60RmtfsRequest *request, K60EfsRead read,
    void *context, uint8_t *image, size_t image_bytes, uint8_t *window,
    size_t window_bytes, uint64_t window_base)
{
	K60EfsSpan spans[K60_RMTFS_MAX_VECS];
	int count;

	if (request == NULL || read == NULL || image == NULL || window == NULL) {
		return -1;
	}
	if (request->message != K60_RMTFS_RW || request->direction != 0) {
		return -1;      /* only the modem's read direction is served */
	}
	if (request->storage == 0 || request->storage > K60_EFS_IMAGE_COUNT) {
		return -1;
	}
	if (k60_rmtfs_check_vectors(request, image_bytes, window_base,
	    window_bytes) != 0) {
		return -1;
	}
	count = k60_efs_plan(request, image_bytes, window_base, window_bytes,
	    spans, K60_RMTFS_MAX_VECS);
	if (count <= 0) {
		return -1;
	}
	for (int i = 0; i < count; i++) {
		if (read(context, request->storage, spans[i].image_offset,
		    image + spans[i].image_offset, spans[i].bytes) != 0) {
			return -1;
		}
	}
	if (k60_efs_copy(spans, (size_t)count, K60_EFS_TO_WINDOW, image,
	    image_bytes, window, window_bytes) != 0) {
		return -1;
	}
	return 0;
}

int
k60_efs_serve_write(const K60RmtfsRequest *request, uint8_t *image,
    size_t image_bytes, const uint8_t *window, size_t window_bytes,
    uint64_t window_base)
{
	K60EfsSpan spans[K60_RMTFS_MAX_VECS];
	int count;

	if (request == NULL || image == NULL || window == NULL) {
		return -1;
	}
	if (request->message != K60_RMTFS_RW || request->direction != 1) {
		return -1;      /* only the modem's write direction lands here */
	}
	if (request->storage == 0 || request->storage > K60_EFS_IMAGE_COUNT) {
		return -1;
	}
	if (k60_rmtfs_check_vectors(request, image_bytes, window_base,
	    window_bytes) != 0) {
		return -1;
	}
	count = k60_efs_plan(request, image_bytes, window_base, window_bytes,
	    spans, K60_RMTFS_MAX_VECS);
	if (count <= 0) {
		return -1;
	}
	if (k60_efs_copy(spans, (size_t)count, K60_EFS_TO_IMAGE, image,
	    image_bytes, (uint8_t *)window, window_bytes) != 0) {
		return -1;
	}
	return 0;
}
