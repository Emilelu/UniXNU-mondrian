/* The RMTFS wire format, checked against the reference layout
 * (PongModemRmtfs.h:84-145) without a modem: every branch of the parser, the
 * two shapes of reply and the scatter guard over the shared window.
 */
#include "K60ModemRmtfs.h"

#include <stdio.h>
#include <string.h>

static int failures;

#define CHECK(what, condition) do { \
	if (!(condition)) { \
		printf("FAIL %s:%d %s\n", __FILE__, __LINE__, what); \
		failures++; \
	} \
} while (0)

/* Lays out a request: type 0, transaction, message, then the TLVs. */
static size_t
request(uint8_t *out, uint16_t transaction, uint16_t message)
{
	memset(out, 0, 256);
	out[0] = 0;
	out[1] = (uint8_t)transaction;
	out[2] = (uint8_t)(transaction >> 8);
	out[3] = (uint8_t)message;
	out[4] = (uint8_t)(message >> 8);
	return 7;
}

static size_t
put_tlv(uint8_t *out, size_t at, uint8_t type, const void *value, size_t bytes)
{
	const uint8_t *p = (const uint8_t *)value;

	out[at] = type;
	out[at + 1] = (uint8_t)bytes;
	out[at + 2] = (uint8_t)(bytes >> 8);
	memcpy(out + at + 3, p, bytes);
	return at + 3 + bytes;
}

static void
seal(uint8_t *out, size_t used)
{
	const size_t region = used - 7;

	out[5] = (uint8_t)region;
	out[6] = (uint8_t)(region >> 8);
}

static void
word(uint8_t *at, uint32_t value)
{
	at[0] = (uint8_t)value;
	at[1] = (uint8_t)(value >> 8);
	at[2] = (uint8_t)(value >> 16);
	at[3] = (uint8_t)(value >> 24);
}

static void
test_open(void)
{
	uint8_t buffer[256];
	K60RmtfsRequest r;
	size_t used;
	const char path[] = "/boot/modem_fs1";

	used = request(buffer, 0x1234, K60_RMTFS_OPEN);
	used = put_tlv(buffer, used, 1, path, sizeof(path) - 1);
	seal(buffer, used);
	CHECK("open parses", k60_rmtfs_parse(buffer, used, &r) == 0);
	CHECK("open transaction", r.transaction == 0x1234);
	CHECK("open message", r.message == K60_RMTFS_OPEN);
	CHECK("open path length", r.path_length == sizeof(path) - 1);
	CHECK("open path bytes", memcmp(r.path, path, sizeof(path) - 1) == 0);

	/* A terminating zero is not part of the name. */
	used = request(buffer, 1, K60_RMTFS_OPEN);
	used = put_tlv(buffer, used, 1, path, sizeof(path));
	seal(buffer, used);
	CHECK("open strips the zero", k60_rmtfs_parse(buffer, used, &r) == 0 &&
	    r.path_length == sizeof(path) - 1);

	/* A name longer than the field is a malformed request, not a longer name. */
	used = request(buffer, 1, K60_RMTFS_OPEN);
	used = put_tlv(buffer, used, 1, path, K60_RMTFS_MAX_PATH + 1);
	seal(buffer, used);
	CHECK("open refuses an oversized path",
	    k60_rmtfs_parse(buffer, used, &r) == -1);
}

static void
test_close_sync_alloc(void)
{
	uint8_t buffer[256];
	K60RmtfsRequest r;
	size_t used;
	uint8_t storage[4];
	uint32_t size = 0x280000;

	word(storage, 3);
	used = request(buffer, 7, K60_RMTFS_CLOSE);
	used = put_tlv(buffer, used, 1, storage, 4);
	seal(buffer, used);
	CHECK("close parses", k60_rmtfs_parse(buffer, used, &r) == 0);
	CHECK("close storage", r.storage == 3);

	used = request(buffer, 8, K60_RMTFS_SYNC);
	used = put_tlv(buffer, used, 1, storage, 4);
	seal(buffer, used);
	CHECK("sync parses", k60_rmtfs_parse(buffer, used, &r) == 0 &&
	    r.storage == 3);

	word(storage, 1);
	used = request(buffer, 9, K60_RMTFS_ALLOC);
	used = put_tlv(buffer, used, 1, storage, 4);
	{
		uint8_t big[4];

		word(big, size);
		used = put_tlv(buffer, used, 2, big, 4);
	}
	seal(buffer, used);
	CHECK("alloc parses", k60_rmtfs_parse(buffer, used, &r) == 0);
	CHECK("alloc storage", r.storage == 1);
	CHECK("alloc size", r.alloc_bytes == size);

	/* An alloc without a size cannot be answered. */
	used = request(buffer, 9, K60_RMTFS_ALLOC);
	used = put_tlv(buffer, used, 1, storage, 4);
	seal(buffer, used);
	CHECK("alloc without size is refused",
	    k60_rmtfs_parse(buffer, used, &r) == -1);
}

static void
test_read_write(void)
{
	uint8_t buffer[256];
	K60RmtfsRequest r;
	size_t used;
	uint8_t direction = 1;
	uint8_t force = 0;
	uint8_t storage[4];
	uint8_t list[1 + 2 * 12];

	word(storage, 2);
	list[0] = 2;
	word(list + 1, 4);          /* block offset 4 -> byte 2048 */
	word(list + 5, 0x10001000); /* physical */
	word(list + 9, 2);          /* two blocks */
	word(list + 13, 0);
	word(list + 17, 0x10002000);
	word(list + 21, 1);

	used = request(buffer, 0x4242, K60_RMTFS_RW);
	used = put_tlv(buffer, used, 2, &direction, 1);
	used = put_tlv(buffer, used, 4, &force, 1);
	used = put_tlv(buffer, used, 1, storage, 4);
	used = put_tlv(buffer, used, 3, list, sizeof(list));
	seal(buffer, used);
	CHECK("rw parses", k60_rmtfs_parse(buffer, used, &r) == 0);
	CHECK("rw storage", r.storage == 2);
	CHECK("rw direction", r.direction == 1);
	CHECK("rw vectors", r.vectors == 2);
	CHECK("rw first offset", r.table[0].block_offset == 4);
	CHECK("rw first physical", r.table[0].physical == 0x10001000);
	CHECK("rw second length", r.table[1].block_length == 1);

	/* A count that does not fill the list is a malformed request. */
	used = request(buffer, 1, K60_RMTFS_RW);
	used = put_tlv(buffer, used, 2, &direction, 1);
	used = put_tlv(buffer, used, 4, &force, 1);
	used = put_tlv(buffer, used, 1, storage, 4);
	list[0] = 3;
	used = put_tlv(buffer, used, 3, list, sizeof(list));
	seal(buffer, used);
	CHECK("rw refuses a short list", k60_rmtfs_parse(buffer, used, &r) == -1);
}

static void
test_malformed(void)
{
	uint8_t buffer[256];
	K60RmtfsRequest r;
	size_t used;

	used = request(buffer, 1, K60_RMTFS_CLOSE);
	seal(buffer, used);
	CHECK("short body is refused", k60_rmtfs_parse(buffer, used, &r) == -1);
	CHECK("short body truncated at six", k60_rmtfs_parse(buffer, 6, &r) == -1);

	used = request(buffer, 1, 9);
	seal(buffer, used);
	CHECK("unknown message is refused", k60_rmtfs_parse(buffer, used, &r) == -1);
	CHECK("unknown message keeps the number", r.message == 9);

	buffer[0] = 2; /* a response is not a request */
	used = request(buffer, 1, K60_RMTFS_CLOSE);
	buffer[0] = 2;
	seal(buffer, used);
	CHECK("response type is refused", k60_rmtfs_parse(buffer, used, &r) == -1);

	used = request(buffer, 1, K60_RMTFS_CLOSE);
	buffer[5] = 0xf0; /* region longer than the message */
	CHECK("region beyond the message is refused",
	    k60_rmtfs_parse(buffer, used, &r) == -1);
	CHECK("null request is refused", k60_rmtfs_parse(buffer, used, NULL) == -1);
}

static void
test_reply(void)
{
	uint8_t out[64];
	uint32_t id = 3;
	uint32_t used;
	uint8_t zero = 0;

	used = k60_rmtfs_build_reply(out, sizeof(out), K60_RMTFS_OPEN, 0x1234, 0,
	    &id, 4);
	CHECK("reply length", used == 21);
	CHECK("reply type", out[0] == 2);
	CHECK("reply transaction", out[1] == 0x34 && out[2] == 0x12);
	CHECK("reply message", out[3] == K60_RMTFS_OPEN);
	CHECK("reply region", out[5] == 14 && out[6] == 0);
	CHECK("reply result tlv", out[7] == 2 && out[8] == 4);
	CHECK("reply result code", out[10] == 0 && out[11] == 0);
	CHECK("reply value tlv", out[14] == 0x10 && out[15] == 4);
	CHECK("reply value", out[17] == 3);

	used = k60_rmtfs_build_reply(out, sizeof(out), K60_RMTFS_CLOSE, 1, 1, NULL, 0);
	CHECK("failed reply has no value", used == 14);
	CHECK("failed reply flags the error", out[10] == 1 && out[11] == 0);
	CHECK("failed reply carries the code", out[12] == 1 && out[13] == 0);

	used = k60_rmtfs_build_reply(out, sizeof(out), K60_RMTFS_SYNC, 2, 0, &zero, 1);
	CHECK("sync reply length", used == 18);
	CHECK("sync reply value", out[17] == 0);

	CHECK("reply refuses a small buffer",
	    k60_rmtfs_build_reply(out, 13, K60_RMTFS_SYNC, 1, 0, NULL, 0) == 0);
	CHECK("reply refuses a null value",
	    k60_rmtfs_build_reply(out, sizeof(out), K60_RMTFS_OPEN, 1, 0, NULL, 4) == 0);
}

static void
test_vectors(void)
{
	K60RmtfsRequest r;
	const uint64_t image = 0x2000;
	const uint64_t base = 0x10000000;
	const uint64_t window = 0x280000;

	memset(&r, 0, sizeof(r));
	r.vectors = 1;
	r.table[0].block_offset = 0;
	r.table[0].physical = (uint32_t)base;
	r.table[0].block_length = 2;
	CHECK("vector at the window base", k60_rmtfs_check_vectors(&r, image, base,
	    window) == 0);

	r.table[0].block_offset = 7; /* byte 3584, two blocks fit in 8192 */
	CHECK("vector at the image end", k60_rmtfs_check_vectors(&r, image, base,
	    window) == 0);

	r.table[0].block_offset = 8; /* byte 4096 to 5120 exceeds an 8192 image? no */
	CHECK("vector inside a larger image", k60_rmtfs_check_vectors(&r, 0x4000,
	    base, window) == 0);

	r.table[0].block_offset = 8;
	r.table[0].block_length = 16; /* 8192 bytes from 4096 */
	CHECK("vector past the image", k60_rmtfs_check_vectors(&r, image, base,
	    window) == -1);

	r.table[0].block_offset = 0;
	r.table[0].block_length = 0;
	CHECK("empty vector", k60_rmtfs_check_vectors(&r, image, base, window) == -1);

	r.table[0].block_length = 1;
	r.table[0].physical = (uint32_t)(base + window);
	CHECK("vector past the window", k60_rmtfs_check_vectors(&r, image, base,
	    window) == -1);

	r.table[0].physical = (uint32_t)(base - 512);
	CHECK("vector below the window", k60_rmtfs_check_vectors(&r, image, base,
	    window) == -1);

	r.table[0].physical = (uint32_t)base;
	CHECK("null request", k60_rmtfs_check_vectors(NULL, image, base, window) == -1);
	r.vectors = 0;
	CHECK("no vectors", k60_rmtfs_check_vectors(&r, image, base, window) == -1);
}

int
main(void)
{
	test_open();
	test_close_sync_alloc();
	test_read_write();
	test_malformed();
	test_reply();
	test_vectors();

	if (failures != 0) {
		printf("K60 RMTFS FAIL %d\n", failures);
		return 1;
	}
	printf("K60 RMTFS PASS parse, reply, window\n");
	return 0;
}
