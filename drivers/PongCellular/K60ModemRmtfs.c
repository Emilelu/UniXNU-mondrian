/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#include "K60ModemRmtfs.h"

#include <string.h>

#define K60_RMTFS_TYPE_REQUEST 0u
#define K60_RMTFS_TYPE_RESPONSE 2u
#define K60_RMTFS_TLV_RESULT 0x02u
#define K60_RMTFS_TLV_VALUE 0x10u

static uint16_t
le16(const uint8_t *at)
{
	return (uint16_t)(at[0] | (uint16_t)at[1] << 8);
}

static uint32_t
le32(const uint8_t *at)
{
	return (uint32_t)le16(at) | (uint32_t)le16(at + 2) << 16;
}

static void
put16(uint8_t *at, uint16_t value)
{
	at[0] = (uint8_t)value;
	at[1] = (uint8_t)(value >> 8);
}

/* One TLV walk over the region that starts after the seven byte header. */
static const uint8_t *
tlv(const uint8_t *tlvs, size_t length, uint8_t type, size_t *size)
{
	size_t at = 0;

	while (at + 3 <= length) {
		const uint8_t kind = tlvs[at];
		const size_t span = le16(tlvs + at + 1);

		if (at + 3 + span > length) {
			return NULL;
		}
		if (kind == type) {
			if (size != NULL) {
				*size = span;
			}
			return tlvs + at + 3;
		}
		at += 3 + span;
	}
	return NULL;
}

static int
take_word(const uint8_t *tlvs, size_t length, uint8_t type, uint32_t *out)
{
	size_t size = 0;
	const uint8_t *field = tlv(tlvs, length, type, &size);

	if (field == NULL || size != 4) {
		return -1;
	}
	*out = le32(field);
	return 0;
}

static int
take_byte(const uint8_t *tlvs, size_t length, uint8_t type, uint32_t *out)
{
	size_t size = 0;
	const uint8_t *field = tlv(tlvs, length, type, &size);

	if (field == NULL || size != 1) {
		return -1;
	}
	*out = field[0];
	return 0;
}

int
k60_rmtfs_parse(const void *bytes, size_t length, K60RmtfsRequest *out)
{
	const uint8_t *p = (const uint8_t *)bytes;
	const uint8_t *tlvs;
	size_t region;
	size_t span = 0;
	const uint8_t *field;
	int rc = 0;

	if (bytes == NULL || out == NULL || length < 7) {
		return -1;
	}
	memset(out, 0, sizeof(*out));
	if (p[0] != K60_RMTFS_TYPE_REQUEST) {
		return -1;
	}
	out->transaction = le16(p + 1);
	out->message = le16(p + 3);
	region = le16(p + 5);
	if (region > length - 7) {
		return -1;
	}
	tlvs = p + 7;
	switch (out->message) {
	case K60_RMTFS_OPEN: {
		field = tlv(tlvs, region, 1, &span);
		if (field == NULL || span == 0 || span > K60_RMTFS_MAX_PATH) {
			return -1;
		}
		if (field[span - 1] == 0) {
			span--;
		}
		memcpy(out->path, field, span);
		out->path_length = span;
		break;
	}
	case K60_RMTFS_CLOSE:
	case K60_RMTFS_SYNC:
		rc = take_word(tlvs, region, 1, &out->storage);
		break;
	case K60_RMTFS_RW: {
		size_t list_size = 0;
		const uint8_t *list;

		if (take_byte(tlvs, region, 2, &out->direction) != 0 ||
		    take_byte(tlvs, region, 4, &out->force) != 0 ||
		    take_word(tlvs, region, 1, &out->storage) != 0) {
			rc = -1;
			break;
		}
		list = tlv(tlvs, region, 3, &list_size);
		if (list == NULL || list_size < 1) {
			rc = -1;
			break;
		}
		if (list[0] == 0 || list[0] > K60_RMTFS_MAX_VECS ||
		    1u + (size_t)list[0] * 12u != list_size) {
			rc = -1;
			break;
		}
		out->vectors = list[0];
		for (size_t i = 0; i < out->vectors; i++) {
			const uint8_t *v = list + 1 + 12 * i;

			out->table[i].block_offset = le32(v);
			out->table[i].physical = le32(v + 4);
			out->table[i].block_length = le32(v + 8);
		}
		break;
	}
	case K60_RMTFS_ALLOC:
		if (take_word(tlvs, region, 1, &out->storage) != 0 ||
		    take_word(tlvs, region, 2, &out->alloc_bytes) != 0) {
			rc = -1;
		}
		break;
	default:
		rc = -1;
		break;
	}
	return rc;
}

uint32_t
k60_rmtfs_build_reply(uint8_t *out, size_t cap, uint16_t message,
    uint16_t transaction, uint16_t result, const void *value, size_t value_bytes)
{
	size_t used = 7;
	const uint8_t *payload = (const uint8_t *)value;

	if (out == NULL || cap < 14) {
		return 0;
	}
	if (value_bytes != 0 && (payload == NULL || cap < 14 + 3 + value_bytes)) {
		return 0;
	}
	out[0] = K60_RMTFS_TYPE_RESPONSE;
	put16(out + 1, transaction);
	put16(out + 3, message);
	/* Result TLV: error flag then the code, exactly as the reference sends. */
	out[used++] = K60_RMTFS_TLV_RESULT;
	put16(out + used, 4);
	used += 2;
	put16(out + used, result != 0 ? 1 : 0);
	put16(out + used + 2, result);
	used += 4;
	if (result == 0 && value_bytes != 0) {
		out[used++] = K60_RMTFS_TLV_VALUE;
		put16(out + used, (uint16_t)value_bytes);
		used += 2;
		memcpy(out + used, payload, value_bytes);
		used += value_bytes;
	}
	put16(out + 5, (uint16_t)(used - 7));
	return (uint32_t)used;
}

int
k60_rmtfs_check_vectors(const K60RmtfsRequest *request, uint64_t image_bytes,
    uint64_t window_base, uint64_t window_bytes)
{
	if (request == NULL || image_bytes == 0 || window_bytes == 0) {
		return -1;
	}
	if (request->vectors == 0 || request->vectors > K60_RMTFS_MAX_VECS) {
		return -1;
	}
	for (size_t i = 0; i < request->vectors; i++) {
		const uint64_t offset = (uint64_t)request->table[i].block_offset *
		    K60_RMTFS_BLOCK;
		const uint64_t span = (uint64_t)request->table[i].block_length *
		    K60_RMTFS_BLOCK;
		const uint64_t physical = request->table[i].physical;

		if (span == 0 || offset > image_bytes || span > image_bytes - offset) {
			return -1;
		}
		if (physical < window_base ||
		    physical - window_base > window_bytes ||
		    span > window_bytes - (physical - window_base)) {
			return -1;
		}
	}
	return 0;
}
