/* Host test for the GPT entry scanner the storage service resolves names with. */
#include <stdio.h>
#include <string.h>

#include "K60ModemEfs.h"
#include "K60ModemGpt.h"

static int failures;

static void
check(int ok, const char *what)
{
	if (!ok) {
		printf("FAIL %s\n", what);
		failures++;
	}
}

static void
put_le64(uint8_t *at, uint64_t value)
{
	for (unsigned i = 0; i < 8; i++) {
		at[i] = (uint8_t)(value >> (8 * i));
	}
}

static void
put_name(uint8_t *entry, const char *name)
{
	uint8_t *field = entry + K60_GPT_NAME_OFFSET;

	for (unsigned i = 0; i < K60_EFS_GPT_NAME_BYTES; i++) {
		field[i] = 0;
	}
	for (unsigned i = 0; name[i] != '\0' && i < K60_EFS_GPT_NAME_BYTES / 2; i++) {
		field[2 * i] = (uint8_t)name[i];
	}
}

static void
put_partition(uint8_t *entry, const char *name, uint64_t first, uint64_t last,
    int used)
{
	memset(entry, 0, K60_GPT_ENTRY_BYTES);
	if (used) {
		entry[0] = 0xa2;
		entry[1] = 0xa0;
	}
	put_le64(entry + 32, first);
	put_le64(entry + 40, last);
	put_name(entry, name);
}

int
main(void)
{
	uint8_t entries[4 * K60_GPT_ENTRY_BYTES];
	K60GptPartition found;

	put_partition(entries + 0 * K60_GPT_ENTRY_BYTES, "fsg", 1, 9, 0);
	put_partition(entries + 1 * K60_GPT_ENTRY_BYTES, "modemst1", 100, 199, 1);
	put_partition(entries + 2 * K60_GPT_ENTRY_BYTES, "fsg", 200, 263, 1);
	put_partition(entries + 3 * K60_GPT_ENTRY_BYTES, "userdata", 300, 999, 1);

	memset(&found, 0, sizeof found);
	check(k60_gpt_find(entries, sizeof entries, K60_GPT_ENTRY_BYTES, "modemst1",
	    &found) == 0, "modemst1 is found");
	check(found.first_lba == 100 && found.last_lba == 199, "modemst1 range");
	check(k60_gpt_partition_bytes(&found, 512) == 100 * 512, "100 sectors of 512");

	/* The unused slot carries the name fsg; it must not shadow the live one. */
	check(k60_gpt_find(entries, sizeof entries, K60_GPT_ENTRY_BYTES, "fsg",
	    &found) == 0, "fsg is found");
	check(found.first_lba == 200 && found.last_lba == 263, "fsg skips the unused slot");
	check(k60_gpt_partition_bytes(&found, 4096) == 64 * 4096, "64 sectors of 4096");

	check(k60_gpt_find(entries, sizeof entries, K60_GPT_ENTRY_BYTES, "fsc",
	    NULL) == -1, "an absent name is refused");
	check(k60_gpt_find(entries, sizeof entries, K60_GPT_ENTRY_BYTES, "modemst",
	    NULL) == -1, "a prefix is not a match");
	check(k60_gpt_find(entries, sizeof entries, 64, "fsg", &found) == -1,
	    "entries smaller than a GPT entry are refused");
	check(k60_gpt_find(entries, K60_GPT_ENTRY_BYTES / 2, K60_GPT_ENTRY_BYTES,
	    "fsg", &found) == -1, "a partial entry is refused");
	check(k60_gpt_find(NULL, sizeof entries, K60_GPT_ENTRY_BYTES, "fsg",
	    &found) == -1, "a NULL array is refused");
	check(k60_gpt_find(entries, sizeof entries, K60_GPT_ENTRY_BYTES, NULL,
	    &found) == -1, "a NULL name is refused");

	/* The storage service numbers its four images; resolve each by number. */
	{
		uint64_t first = 0, bytes = 0;

		check(k60_gpt_locate_storage(1, entries, sizeof entries,
		    K60_GPT_ENTRY_BYTES, 512, &first, &bytes) == 0,
		    "storage 1 resolves to modemst1");
		check(first == 100 && bytes == 100 * 512, "storage 1 range and length");
		check(k60_gpt_locate_storage(3, entries, sizeof entries,
		    K60_GPT_ENTRY_BYTES, 4096, &first, &bytes) == 0,
		    "storage 3 resolves to fsg");
		check(first == 200 && bytes == 64 * 4096, "storage 3 range and length");
		check(k60_gpt_locate_storage(4, entries, sizeof entries,
		    K60_GPT_ENTRY_BYTES, 512, &first, &bytes) == -1,
		    "storage 4 is absent from this table");
		check(k60_gpt_locate_storage(0, entries, sizeof entries,
		    K60_GPT_ENTRY_BYTES, 512, &first, &bytes) == -1,
		    "storage 0 has no name");
		check(k60_gpt_locate_storage(1, entries, sizeof entries,
		    K60_GPT_ENTRY_BYTES, 0, &first, &bytes) == -1,
		    "a zero sector size is refused");
		check(k60_gpt_locate_storage(1, entries, sizeof entries,
		    K60_GPT_ENTRY_BYTES, 512, NULL, NULL) == 0,
		    "the outputs are optional");
	}

	found.first_lba = 20;
	found.last_lba = 10;
	check(k60_gpt_partition_bytes(&found, 512) == 0, "an inverted range is zero");
	check(k60_gpt_partition_bytes(NULL, 512) == 0, "a NULL partition is zero");

	if (failures != 0) {
		printf("K60 GPT FAIL %d checks\n", failures);
		return 1;
	}
	printf("K60 GPT PASS name scan, unused slots, refusals\n");
	return 0;
}