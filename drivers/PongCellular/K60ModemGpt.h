/*
 * Find a partition by name in a raw GPT entry array.
 *
 * The modem storage images (modemst1, modemst2, fsg, fsc) are ordinary GPT
 * partitions on LUN 0, so the storage service has to resolve a name to a byte
 * range before it can copy anything. This file only does the parsing: the read
 * of the entry array itself belongs to whatever owns the UFS transport.
 *
 * A GPT entry is 128 bytes: 16 type GUID (all zero means unused), 16 unique
 * GUID, 8 first LBA, 8 last LBA, 8 attributes, then 72 bytes holding 36
 * UTF-16LE characters of name.
 */
#ifndef _K60_MODEM_GPT_H_
#define _K60_MODEM_GPT_H_

#include <stddef.h>
#include <stdint.h>

#define K60_GPT_ENTRY_BYTES   128u
#define K60_GPT_NAME_OFFSET    56u
#define K60_GPT_TYPE_BYTES     16u

/* Byte range of one partition, in the sectors the entry array was read with. */
typedef struct {
	uint64_t first_lba;
	uint64_t last_lba;
} K60GptPartition;

/*
 * Look for name among count entries of entry_bytes each. Entries whose type
 * GUID is all zero were never written and are skipped; the first match wins.
 * Returns 0 on a match, -1 when the name is absent, and -1 for a malformed
 * array (entry_bytes below 128, a name that does not fit, or a NULL pointer).
 */
int k60_gpt_find(const void *entries, size_t entries_bytes,
    uint32_t entry_bytes, const char *name, K60GptPartition *out);

/* Bytes covered by a matched partition; 0 when last_lba is before first_lba. */
uint64_t k60_gpt_partition_bytes(const K60GptPartition *partition,
    uint32_t sector_bytes);

/*
 * Resolves a storage id from the storage service (1 modemst1, 2 modemst2,
 * 3 fsg, 4 fsc) to its partition and byte length. Returns 0 on success and -1
 * for an unknown id, an absent name, or an empty partition.
 */
int k60_gpt_locate_storage(uint32_t storage, const void *entries,
    size_t entries_bytes, uint32_t entry_bytes, uint32_t sector_bytes,
    uint64_t *first_lba, uint64_t *image_bytes);

#endif /* _K60_MODEM_GPT_H_ */