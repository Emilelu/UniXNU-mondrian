/*
 * Host test for the shared memory point-to-point layout.
 *
 * The item is a plain word array here: the kernel maps SMEM separately, and
 * these helpers must not depend on how the caller obtained the pointer.
 */

#include <stdio.h>
#include <string.h>

#include "K60ModemSmp2p.h"

static int failures;

#define CHECK(condition) do { \
	if (!(condition)) { \
		printf("FAIL line %d: %s\n", __LINE__, #condition); \
		++failures; \
	} \
} while (0)

static void
put_name(volatile uint32_t *entry, const char *name)
{
	unsigned i;

	for (i = 0; i < 4; i++) {
		entry[i] = 0;
	}
	for (i = 0; i < K60_SMP2P_NAME_BYTES && name[i] != '\0'; i++) {
		entry[i / 4u] |= (uint32_t)(uint8_t)name[i] << (8u * (i % 4u));
	}
}

static volatile uint32_t *
entry_at(volatile uint32_t *item, unsigned index)
{
	return item + K60_SMP2P_HEADER_WORDS + index * K60_SMP2P_ENTRY_WORDS;
}

static void
build_item(volatile uint32_t *item)
{
	unsigned i;

	for (i = 0; i < K60_SMP2P_ITEM_BYTES / 4u; i++) {
		item[i] = 0;
	}
	item[0] = K60_SMP2P_MAGIC;
	item[1] = K60_SMP2P_VERSION | (1u << 8);
	item[2] = 1u;
	item[3] = K60_SMP2P_ENTRIES | (2u << 16);
	put_name(entry_at(item, 0), "slave-kernel");
	entry_at(item, 0)[4] = 2u;
	put_name(entry_at(item, 1), "ipa");
	entry_at(item, 1)[4] = 1u;
}

static void
test_find(void)
{
	volatile uint32_t item[K60_SMP2P_ITEM_BYTES / 4u];
	uint32_t value = 0xffffffffu;

	build_item(item);
	CHECK(k60_smp2p_find(item, K60_SMP2P_ITEM_BYTES, "slave-kernel", &value) == 1);
	CHECK(value == 2u);
	CHECK(k60_smp2p_find(item, K60_SMP2P_ITEM_BYTES, "ipa", &value) == 1);
	CHECK(value == 1u);
	CHECK(k60_smp2p_find(item, K60_SMP2P_ITEM_BYTES, "master-kernel", &value) == 0);
	CHECK(k60_smp2p_find(item, K60_SMP2P_ITEM_BYTES, "ipa", NULL) == 1);
	/* Only the valid count is searched: a name in slot three stays invisible
	 * until the count covers it. */
	put_name(entry_at(item, 3), "rmtfs");
	entry_at(item, 3)[4] = 5u;
	CHECK(k60_smp2p_find(item, K60_SMP2P_ITEM_BYTES, "rmtfs", &value) == 0);
	item[3] = K60_SMP2P_ENTRIES | (4u << 16);
	CHECK(k60_smp2p_find(item, K60_SMP2P_ITEM_BYTES, "rmtfs", &value) == 1);
	CHECK(value == 5u);
}

static void
test_names(void)
{
	volatile uint32_t item[K60_SMP2P_ITEM_BYTES / 4u];

	build_item(item);
	CHECK(k60_smp2p_name_matches(entry_at(item, 0), "slave-kernel") == 1);
	CHECK(k60_smp2p_name_matches(entry_at(item, 0), "slave-kerne") == 0);
	CHECK(k60_smp2p_name_matches(entry_at(item, 0), "slave-kernels") == 0);
	CHECK(k60_smp2p_name_matches(entry_at(item, 1), "ip") == 0);
	CHECK(k60_smp2p_name_matches(NULL, "ipa") == 0);
	CHECK(k60_smp2p_name_matches(entry_at(item, 1), NULL) == 0);
	/* Sixteen bytes fill the field exactly. Anything beyond the sixteenth
	 * byte is outside the entry, so the comparison cannot see it. */
	put_name(entry_at(item, 2), "abcdefghijklmnop");
	CHECK(k60_smp2p_name_matches(entry_at(item, 2), "abcdefghijklmnop") == 1);
	CHECK(k60_smp2p_name_matches(entry_at(item, 2), "abcdefghijklmno") == 0);
}

static void
test_words(void)
{
	volatile uint32_t item[K60_SMP2P_ITEM_BYTES / 4u];

	build_item(item);
	CHECK(k60_smp2p_entry_word(item, 1) == 1u);
	CHECK(k60_smp2p_entry_word(item, -1) == 0u);
	CHECK(k60_smp2p_entry_word(item, (int)K60_SMP2P_ENTRIES) == 0u);
	CHECK(k60_smp2p_entry_word(NULL, 0) == 0u);
	/* The stop bit is bit zero of its own entry; clearing it must leave the
	 * ready bit the modem owns alone. */
	put_name(entry_at(item, 0), "master-kernel");
	entry_at(item, 0)[4] = 3u;
	CHECK(k60_smp2p_update(item, 0, 1u, 0u) == 1);
	CHECK(k60_smp2p_entry_word(item, 0) == 2u);
	CHECK(k60_smp2p_update(item, 0, 3u, 3u) == 1);
	CHECK(k60_smp2p_entry_word(item, 0) == 3u);
	CHECK(k60_smp2p_update(item, (int)K60_SMP2P_ENTRIES, 1u, 1u) == 0);
	CHECK(k60_smp2p_update(NULL, 0, 1u, 1u) == 0);
}

static void
test_header(void)
{
	volatile uint32_t item[K60_SMP2P_ITEM_BYTES / 4u];
	uint32_t valid = 0;

	build_item(item);
	CHECK(k60_smp2p_header(item, K60_SMP2P_ITEM_BYTES, &valid) == 1);
	CHECK(valid == 2u);
	item[0] = 0;
	CHECK(k60_smp2p_header(item, K60_SMP2P_ITEM_BYTES, &valid) == 0);
	build_item(item);
	item[1] = 2u;
	CHECK(k60_smp2p_header(item, K60_SMP2P_ITEM_BYTES, &valid) == 0);
	build_item(item);
	item[3] = (K60_SMP2P_ENTRIES + 1u) | (2u << 16);
	CHECK(k60_smp2p_header(item, K60_SMP2P_ITEM_BYTES, &valid) == 0);
	build_item(item);
	item[3] = 2u | (3u << 16);
	CHECK(k60_smp2p_header(item, K60_SMP2P_ITEM_BYTES, &valid) == 0);
	build_item(item);
	CHECK(k60_smp2p_header(item, 16, &valid) == 0);
	CHECK(k60_smp2p_header(NULL, K60_SMP2P_ITEM_BYTES, &valid) == 0);
	CHECK(k60_smp2p_header(item, K60_SMP2P_ITEM_BYTES, NULL) == 1);
}

int
main(void)
{
	test_find();
	test_names();
	test_words();
	test_header();
	if (failures != 0) {
		printf("K60 SMP2P FAIL %d\n", failures);
		return 1;
	}
	printf("K60 SMP2P PASS names, lookup, words, header\n");
	return 0;
}
