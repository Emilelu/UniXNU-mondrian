/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Memshare request parsing and response building.  Self contained: the seven
 * byte QMI header and the TLVs are little endian, and the shapes are the ones
 * references/pong-baseband/PongModemMemshare.h uses. */

#include "K60ModemMemshare.h"

static uint16_t
k60_memshare_le16(const uint8_t *at)
{
	return (uint16_t)((uint16_t)at[0] | ((uint16_t)at[1] << 8));
}

static uint32_t
k60_memshare_le32(const uint8_t *at)
{
	return (uint32_t)k60_memshare_le16(at) |
	    ((uint32_t)k60_memshare_le16(at + 2) << 16);
}

static uint64_t
k60_memshare_le64(const uint8_t *at)
{
	return (uint64_t)k60_memshare_le32(at) |
	    ((uint64_t)k60_memshare_le32(at + 4) << 32);
}

static void
k60_memshare_put16(uint8_t *at, uint16_t value)
{
	at[0] = (uint8_t)(value & 0xffu);
	at[1] = (uint8_t)(value >> 8);
}

static void
k60_memshare_put32(uint8_t *at, uint32_t value)
{
	k60_memshare_put16(at, (uint16_t)(value & 0xffffu));
	k60_memshare_put16(at + 2, (uint16_t)(value >> 16));
}

static void
k60_memshare_put64(uint8_t *at, uint64_t value)
{
	k60_memshare_put32(at, (uint32_t)(value & 0xffffffffu));
	k60_memshare_put32(at + 4, (uint32_t)(value >> 32));
}

/* A required TLV: present with exactly four bytes.  An optional one may be
 * absent (returns 0 with *found cleared) but must still be four bytes when
 * the modem sent it. */
static int
k60_memshare_u32(const uint8_t *tlvs, size_t bytes, uint8_t tag, uint32_t *value,
    int *found)
{
	size_t at = 0;

	if (found != NULL) {
		*found = 0;
	}
	while (at + 3u <= bytes) {
		const uint8_t type = tlvs[at];
		const uint16_t length = k60_memshare_le16(tlvs + at + 1);

		if (at + 3u + length > bytes) {
			return K60MemshareMalformed;
		}
		if (type == tag) {
			if (length != 4u) {
				return K60MemshareMalformed;
			}
			*value = k60_memshare_le32(tlvs + at + 3);
			if (found != NULL) {
				*found = 1;
			}
			return K60MemshareOk;
		}
		at += 3u + length;
	}
	return K60MemshareOk;
}

int
k60_memshare_parse(const void *bytes, size_t length, K60MemshareRequest *out)
{
	const uint8_t *data = (const uint8_t *)bytes;
	const uint8_t *tlvs;
	size_t payload;
	int found;

	if (bytes == NULL || out == NULL || length < 7u) {
		return K60MemshareBadArgument;
	}
	if (data[0] != 0u) {
		return K60MemshareMalformed;               /* not a request */
	}
	payload = (size_t)k60_memshare_le16(data + 5);
	if (7u + payload > length) {
		return K60MemshareMalformed;
	}
	tlvs = data + 7;
	out->transaction = k60_memshare_le16(data + 1);
	out->message = k60_memshare_le16(data + 3);
	out->client = 0;
	out->processor = 0;
	out->sequence = 0;
	out->bytes = 0;
	out->alignment = 0;
	out->physical = 0;
	out->extent_bytes = 0;
	out->error = K60_MEMSHARE_ERROR_NONE;

	if (out->message == K60_MEMSHARE_QUERY) {
		if (k60_memshare_u32(tlvs, payload, 1, &out->client, NULL) != 0) {
			return K60MemshareMalformed;
		}
		if (k60_memshare_u32(tlvs, payload, 0x10, &out->processor,
		    &found) != 0) {
			return K60MemshareMalformed;
		}
		if (out->client > K60_MEMSHARE_CLIENT_LIMIT || out->processor != 0u) {
			out->error = K60_MEMSHARE_ERROR_ARGUMENT;
		}
		return K60MemshareOk;
	}

	if (out->message == K60_MEMSHARE_ALLOCATE) {
		if (k60_memshare_u32(tlvs, payload, 1, &out->bytes, NULL) != 0 ||
		    k60_memshare_u32(tlvs, payload, 2, &out->client, NULL) != 0 ||
		    k60_memshare_u32(tlvs, payload, 3, &out->processor, NULL) != 0 ||
		    k60_memshare_u32(tlvs, payload, 4, &out->sequence, NULL) != 0 ||
		    k60_memshare_u32(tlvs, payload, 0x11, &out->alignment,
		    &found) != 0) {
			return K60MemshareMalformed;
		}
		if (out->client != K60_MEMSHARE_CLIENT || out->processor != 0u ||
		    out->alignment > K60_MEMSHARE_ALIGNMENT_LIMIT) {
			out->error = K60_MEMSHARE_ERROR_ARGUMENT;
		} else if (out->bytes == 0u || out->bytes > K60_MEMSHARE_MAXIMUM) {
			out->error = K60_MEMSHARE_ERROR_NO_MEMORY;
		}
		return K60MemshareOk;
	}

	if (out->message == K60_MEMSHARE_FREE) {
		size_t at = 0;
		int have_extent = 0;

		/* no client TLV means any client may hand the extent back */
		out->client = 0xffffffffu;
		if (k60_memshare_u32(tlvs, payload, 0x10, &out->client, &found) != 0 ||
		    k60_memshare_u32(tlvs, payload, 0x11, &out->processor,
		    &found) != 0) {
			return K60MemshareMalformed;
		}
		while (at + 3u <= payload) {
			const uint8_t type = tlvs[at];
			const uint16_t extent = k60_memshare_le16(tlvs + at + 1);

			if (at + 3u + extent > payload) {
				return K60MemshareMalformed;
			}
			if (type == 1u) {
				if (extent != K60_MEMSHARE_EXTENT_BYTES ||
				    tlvs[at + 3] != K60_MEMSHARE_EXTENT_VERSION) {
					return K60MemshareMalformed;
				}
				out->physical = k60_memshare_le64(tlvs + at + 4);
				out->extent_bytes = k60_memshare_le32(tlvs + at + 12);
				have_extent = 1;
			}
			at += 3u + extent;
		}
		if (!have_extent) {
			return K60MemshareMalformed;
		}
		if (out->processor != 0u ||
		    (out->client != 0xffffffffu && out->client != K60_MEMSHARE_CLIENT)) {
			out->error = K60_MEMSHARE_ERROR_ARGUMENT;
		}
		return K60MemshareOk;
	}

	out->error = K60_MEMSHARE_ERROR_UNSUPPORTED;
	return K60MemshareOk;
}

size_t
k60_memshare_build_reply(uint8_t *out, size_t capacity, uint16_t transaction,
    uint16_t message, uint32_t error, uint32_t maximum, const uint32_t *sequence,
    uint64_t physical, uint32_t bytes)
{
	size_t used;

	if (out == NULL || capacity < 14u) {
		return 0;
	}
	out[0] = 2u;                                   /* response */
	k60_memshare_put16(out + 1, transaction);
	k60_memshare_put16(out + 3, message);
	out[7] = 0x02u;                                /* result TLV */
	k60_memshare_put16(out + 8, 4);
	k60_memshare_put16(out + 10, error != 0u ? 1u : 0u);
	k60_memshare_put16(out + 12, (uint16_t)error);
	used = 14u;

	if (error != 0u) {
		goto done;
	}
	if (message == K60_MEMSHARE_QUERY) {
		if (capacity < used + 7u) {
			return 0;
		}
		out[used++] = 0x10u;
		k60_memshare_put16(out + used, 4);
		used += 2;
		k60_memshare_put32(out + used, maximum);
		used += 4;
	} else if (message == K60_MEMSHARE_ALLOCATE) {
		if (capacity < used + 7u + 16u) {
			return 0;
		}
		out[used++] = 0x10u;
		k60_memshare_put16(out + used, 4);
		used += 2;
		k60_memshare_put32(out + used,
		    sequence != NULL ? *sequence : 0u);
		used += 4;
		out[used++] = 0x11u;
		k60_memshare_put16(out + used, K60_MEMSHARE_EXTENT_BYTES);
		used += 2;
		out[used++] = K60_MEMSHARE_EXTENT_VERSION;
		k60_memshare_put64(out + used, physical);
		used += 8;
		k60_memshare_put32(out + used, bytes);
		used += 4;
	}

done:
	k60_memshare_put16(out + 5, (uint16_t)(used - 7u));
	return used;
}

int
k60_memshare_region_ok(uint64_t physical, uint32_t bytes, uint64_t ceiling)
{
	uint64_t rounded;

	if (physical == 0u || bytes == 0u || (physical & 0xfffu) != 0u) {
		return -1;
	}
	rounded = ((uint64_t)bytes + 4095u) & ~(uint64_t)4095u;
	if (rounded == 0u || physical + rounded < physical) {
		return -1;
	}
	if (physical + rounded > ceiling) {
		return -1;
	}
	return 0;
}
