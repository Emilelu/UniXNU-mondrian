/*
 * Shared memory point-to-point: the 340-byte item both sides publish.
 *
 * Both the AP-owned item (item 428) and the modem-owned item (item 435) use
 * one layout: five header words, then sixteen 20-byte entries, each four
 * little-endian name words and one value word.  The value word is a bitfield
 * whose meaning belongs to the service that owns the entry: "slave-kernel"
 * reports ready/fatal, "ipa" is a question the modem asks and the AP answers.
 *
 * These helpers only touch memory the caller already mapped; every write is
 * ordered by the caller's own barrier, because the host test compiles on a
 * different architecture than the kernel.
 */

#ifndef _K60_MODEM_SMP2P_H_
#define _K60_MODEM_SMP2P_H_

#include <stddef.h>
#include <stdint.h>

#define K60_SMP2P_MAGIC          0x504d5324u
#define K60_SMP2P_VERSION        1u
#define K60_SMP2P_HEADER_WORDS   5u
#define K60_SMP2P_ENTRY_WORDS    5u
#define K60_SMP2P_ENTRIES        16u
#define K60_SMP2P_ITEM_BYTES     (K60_SMP2P_HEADER_WORDS * 4u + K60_SMP2P_ENTRIES * K60_SMP2P_ENTRY_WORDS * 4u)
#define K60_SMP2P_NAME_BYTES     16u

/* Value word of one entry; out of range reads as zero so a caller can never
 * reach outside the item it mapped. */
static inline uint32_t
k60_smp2p_entry_word(volatile uint32_t *item, int index)
{
	if (item == NULL || index < 0 || (uint32_t)index >= K60_SMP2P_ENTRIES) {
		return 0;
	}
	return item[K60_SMP2P_HEADER_WORDS +
	    (uint32_t)index * K60_SMP2P_ENTRY_WORDS + 4u];
}

/* Replace the masked bits of one entry's value word.  Returns 1 when it wrote,
 * 0 when the index is outside the item. */
static inline int
k60_smp2p_update(volatile uint32_t *item, int index, uint32_t mask, uint32_t value)
{
	volatile uint32_t *word;

	if (item == NULL || index < 0 || (uint32_t)index >= K60_SMP2P_ENTRIES) {
		return 0;
	}
	word = &item[K60_SMP2P_HEADER_WORDS +
	    (uint32_t)index * K60_SMP2P_ENTRY_WORDS + 4u];
	*word = (*word & ~mask) | (value & mask);
	return 1;
}

/* Header check: magic, version and a valid count that fits the item.  The
 * processor ids in word two are the caller's business, because the AP item
 * and the modem item legitimately name different local processors. */
static inline int
k60_smp2p_header(volatile uint32_t *item, size_t bytes, uint32_t *valid)
{
	uint32_t total;

	if (item == NULL || bytes < K60_SMP2P_HEADER_WORDS * 4u) {
		return 0;
	}
	if (item[0] != K60_SMP2P_MAGIC || (item[1] & 0xffu) != K60_SMP2P_VERSION) {
		return 0;
	}
	total = item[3] & 0xffffu;
	if (total > K60_SMP2P_ENTRIES || (item[3] >> 16) > total) {
		return 0;
	}
	if (valid != NULL) {
		*valid = item[3] >> 16;
	}
	return 1;
}

/* A name occupies all four name words: a shorter name is zero padded, and a
 * longer one cannot match because the sixteenth byte is already fixed. */
static inline int
k60_smp2p_name_matches(const volatile uint32_t *entry, const char *name)
{
	unsigned i;

	if (entry == NULL || name == NULL) {
		return 0;
	}
	/* Read the name only as far as its terminator: a caller passes a string
	 * literal, and the bytes past it are not ours to read. */
	for (i = 0; i < K60_SMP2P_NAME_BYTES; i++) {
		if (name[i] == '\0') {
			break;
		}
		if ((uint8_t)(entry[i / 4u] >> (8u * (i % 4u))) !=
		    (uint32_t)(uint8_t)name[i]) {
			return 0;
		}
	}
	/* The rest of the field is zero padded, so a stored byte there means the
	 * entry names something longer than the name just compared. */
	for (; i < K60_SMP2P_NAME_BYTES; i++) {
		if ((uint8_t)(entry[i / 4u] >> (8u * (i % 4u))) != 0u) {
			return 0;
		}
	}
	return 1;
}

/* Find one entry by name and hand back its value word.  Returns 1 when the
 * entry is present, 0 when it is not or the item header is not usable. */
static inline int
k60_smp2p_find(volatile uint32_t *item, size_t bytes, const char *name,
    uint32_t *value)
{
	uint32_t valid = 0, i;

	if (!k60_smp2p_header(item, bytes, &valid)) {
		return 0;
	}
	for (i = 0; i < valid; i++) {
		volatile uint32_t *entry = item + K60_SMP2P_HEADER_WORDS +
		    i * K60_SMP2P_ENTRY_WORDS;

		if (k60_smp2p_name_matches(entry, name)) {
			if (value != NULL) {
				*value = entry[4];
			}
			return 1;
		}
	}
	return 0;
}

#endif /* _K60_MODEM_SMP2P_H_ */
