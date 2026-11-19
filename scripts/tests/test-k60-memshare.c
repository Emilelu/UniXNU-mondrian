/* Host test for the memshare wire shapes. */
#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "K60ModemMemshare.h"

static size_t
put_tlv(uint8_t *out, size_t at, uint8_t type, const void *value, size_t bytes)
{
	out[at] = type;
	out[at + 1] = (uint8_t)(bytes & 0xffu);
	out[at + 2] = (uint8_t)(bytes >> 8);
	memcpy(out + at + 3, value, bytes);
	return at + 3 + bytes;
}

static size_t
put_u32(uint8_t *out, size_t at, uint8_t type, uint32_t value)
{
	uint8_t raw[4];

	raw[0] = (uint8_t)(value & 0xffu);
	raw[1] = (uint8_t)((value >> 8) & 0xffu);
	raw[2] = (uint8_t)((value >> 16) & 0xffu);
	raw[3] = (uint8_t)(value >> 24);
	return put_tlv(out, at, type, raw, 4);
}

static uint32_t
le16(const uint8_t *at)
{
	return (uint32_t)at[0] | ((uint32_t)at[1] << 8);
}

static uint32_t
le32(const uint8_t *at)
{
	return le16(at) | (le16(at + 2) << 16);
}

/* header with a message id; the payload length is filled in by the caller */
static size_t
header(uint8_t *out, uint16_t message)
{
	memset(out, 0, 64);
	out[0] = 0;
	out[2] = 1;                 /* transaction = 0x0100 */
	out[3] = (uint8_t)(message & 0xffu);
	out[4] = (uint8_t)(message >> 8);
	return 7;
}

static void
set_length(uint8_t *out, size_t used)
{
	const size_t payload = used - 7;

	out[5] = (uint8_t)(payload & 0xffu);
	out[6] = (uint8_t)(payload >> 8);
}

int
main(void)
{
	uint8_t msg[64];
	uint8_t reply[64];
	K60MemshareRequest request;
	size_t used;
	size_t length;
	uint32_t sequence = 9;

	/* allocate with every field the reference requires */
	used = header(msg, K60_MEMSHARE_ALLOCATE);
	used = put_u32(msg, used, 1, 0x280000);
	used = put_u32(msg, used, 2, 1);
	used = put_u32(msg, used, 3, 0);
	used = put_u32(msg, used, 4, 7);
	used = put_u32(msg, used, 0x11, 11);
	assert(used == 7 + 35);
	set_length(msg, used);
	assert((used - 7) < 256);
	assert(k60_memshare_parse(msg, used, &request) == K60MemshareOk);
	assert(request.message == K60_MEMSHARE_ALLOCATE);
	assert(request.bytes == 0x280000);
	assert(request.client == 1);
	assert(request.processor == 0);
	assert(request.sequence == 7);
	assert(request.alignment == 11);
	assert(request.error == K60_MEMSHARE_ERROR_NONE);

	/* a second client is refused while parsing */
	used = header(msg, K60_MEMSHARE_ALLOCATE);
	used = put_u32(msg, used, 1, 0x1000);
	used = put_u32(msg, used, 2, 2);
	used = put_u32(msg, used, 3, 0);
	used = put_u32(msg, used, 4, 1);
	set_length(msg, used);
	assert(k60_memshare_parse(msg, used, &request) == K60MemshareOk);
	assert(request.error == K60_MEMSHARE_ERROR_ARGUMENT);

	/* zero bytes is a no-memory answer, not a malformed request */
	used = header(msg, K60_MEMSHARE_ALLOCATE);
	used = put_u32(msg, used, 1, 0);
	used = put_u32(msg, used, 2, 1);
	used = put_u32(msg, used, 3, 0);
	used = put_u32(msg, used, 4, 2);
	set_length(msg, used);
	assert(k60_memshare_parse(msg, used, &request) == K60MemshareOk);
	assert(request.error == K60_MEMSHARE_ERROR_NO_MEMORY);

	/* query: client 2 is the last legal one, 3 is not */
	used = header(msg, K60_MEMSHARE_QUERY);
	used = put_u32(msg, used, 1, 2);
	set_length(msg, used);
	assert(k60_memshare_parse(msg, used, &request) == K60MemshareOk);
	assert(request.client == 2);
	assert(request.error == K60_MEMSHARE_ERROR_NONE);
	used = header(msg, K60_MEMSHARE_QUERY);
	used = put_u32(msg, used, 1, 3);
	set_length(msg, used);
	assert(k60_memshare_parse(msg, used, &request) == K60MemshareOk);
	assert(request.error == K60_MEMSHARE_ERROR_ARGUMENT);

	/* free: a thirteen byte extent, no client TLV means any client */
	{
		uint8_t extent[K60_MEMSHARE_EXTENT_BYTES];

		extent[0] = K60_MEMSHARE_EXTENT_VERSION;
		memset(extent + 1, 0x11, 8);
		extent[9] = 0x00;
		extent[10] = 0x00;
		extent[11] = 0x28;
		extent[12] = 0x00;
		used = header(msg, K60_MEMSHARE_FREE);
		used = put_tlv(msg, used, 1, extent, sizeof(extent));
		set_length(msg, used);
		assert(k60_memshare_parse(msg, used, &request) == K60MemshareOk);
		assert(request.client == 0xffffffffu);
		assert(request.physical == 0x1111111111111111ull);
		assert(request.extent_bytes == 0x280000);
		assert(request.error == K60_MEMSHARE_ERROR_NONE);

		extent[0] = 2;                          /* wrong version */
		used = header(msg, K60_MEMSHARE_FREE);
		used = put_tlv(msg, used, 1, extent, sizeof(extent));
		set_length(msg, used);
		assert(k60_memshare_parse(msg, used, &request) == K60MemshareMalformed);
	}

	/* an unknown message still parses and asks for "not supported" */
	used = header(msg, 0x99);
	set_length(msg, 7);
	assert(k60_memshare_parse(msg, used, &request) == K60MemshareOk);
	assert(request.error == K60_MEMSHARE_ERROR_UNSUPPORTED);

	/* malformed headers */
	assert(k60_memshare_parse(NULL, 8, &request) == K60MemshareBadArgument);
	assert(k60_memshare_parse(msg, 6, &request) == K60MemshareBadArgument);
	used = header(msg, K60_MEMSHARE_QUERY);
	msg[5] = 40;                               /* claims more than it has */
	assert(k60_memshare_parse(msg, used, &request) == K60MemshareMalformed);
	used = header(msg, K60_MEMSHARE_QUERY);
	msg[0] = 2;                                /* a response, not a request */
	set_length(msg, 7);
	assert(k60_memshare_parse(msg, used, &request) == K60MemshareMalformed);

	/* allocate reply: result, sequence, extent */
	length = k60_memshare_build_reply(reply, sizeof(reply),
	    request.transaction, K60_MEMSHARE_ALLOCATE, 0, 0, &sequence,
	    0x90001000ull, 0x280000);
	assert(length == 14 + 7 + 16);
	assert(reply[0] == 2);
	assert(le16(reply + 1) == request.transaction);
	assert(le16(reply + 3) == K60_MEMSHARE_ALLOCATE);
	assert(le16(reply + 5) == length - 7);
	assert(reply[7] == 0x02);
	assert(le16(reply + 8) == 4);
	assert(le16(reply + 10) == 0);
	assert(le16(reply + 12) == 0);
	assert(reply[14] == 0x10);
	assert(le16(reply + 15) == 4);
	assert(le32(reply + 17) == 9);
	assert(reply[21] == 0x11);
	assert(le16(reply + 22) == K60_MEMSHARE_EXTENT_BYTES);
	assert(reply[24] == K60_MEMSHARE_EXTENT_VERSION);
	assert(le32(reply + 25) == 0x90001000u);
	assert(le32(reply + 29) == 0u);             /* physical high word */
	assert(le32(reply + 33) == 0x280000);

	/* a refusal carries only the result TLV */
	length = k60_memshare_build_reply(reply, sizeof(reply), 3,
	    K60_MEMSHARE_ALLOCATE, K60_MEMSHARE_ERROR_NO_MEMORY, 0, NULL, 0, 0);
	assert(length == 14);
	assert(le16(reply + 10) == 1);
	assert(le16(reply + 12) == K60_MEMSHARE_ERROR_NO_MEMORY);

	/* query reply carries the client limit */
	length = k60_memshare_build_reply(reply, sizeof(reply), 4,
	    K60_MEMSHARE_QUERY, 0, K60_MEMSHARE_MAXIMUM, NULL, 0, 0);
	assert(length == 21);
	assert(reply[14] == 0x10);
	assert(le32(reply + 17) == K60_MEMSHARE_MAXIMUM);

	/* the buffer has to hold the whole reply */
	assert(k60_memshare_build_reply(reply, 13, 0, K60_MEMSHARE_QUERY, 0, 0,
	    NULL, 0, 0) == 0);
	assert(k60_memshare_build_reply(reply, 20, 0, K60_MEMSHARE_QUERY, 0, 0,
	    NULL, 0, 0) == 0);
	assert(k60_memshare_build_reply(reply, 36, 0, K60_MEMSHARE_ALLOCATE, 0, 0,
	    &sequence, 0x1000, 0x1000) == 0);

	/* regions: aligned, non zero and entirely below the ceiling */
	assert(k60_memshare_region_ok(0x90000000ull, 0x280000, 1ull << 32) == 0);
	assert(k60_memshare_region_ok(0x90000008ull, 0x280000, 1ull << 32) == -1);
	assert(k60_memshare_region_ok(0, 0x280000, 1ull << 32) == -1);
	assert(k60_memshare_region_ok(0x90000000ull, 0, 1ull << 32) == -1);
	assert(k60_memshare_region_ok(0xfffff000ull, 0x280000, 1ull << 32) == -1);
	assert(k60_memshare_region_ok(0xffd80000ull, 0x280000, 1ull << 32) == 0);
	assert(k60_memshare_region_ok(0xffd80000ull, 0x280001, 1ull << 32) == -1);

	printf("K60 MEMSHARE PASS parse, replies, regions\n");
	return 0;
}
