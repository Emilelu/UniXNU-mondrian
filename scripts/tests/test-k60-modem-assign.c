/* Host test for the SCM memory-ownership record (k60_modem_assign_record).
 * Every offset is pinned against PongModemMemshare.h:26-49; the kernel build
 * uses the same inline helper, so a drifting layout fails here first. */
#include "K60ModemPas.h"

#include <stdio.h>
#include <string.h>

static unsigned failures;

static uint64_t get_le(const uint8_t *at, unsigned bytes)
{
	uint64_t value = 0;
	unsigned i;

	for (i = 0; i < bytes; i++) {
		value |= (uint64_t)at[i] << (8 * i);
	}
	return value;
}

static void check(const char *what, uint64_t got, uint64_t want)
{
	if (got != want) {
		printf("FAIL %s: got %#llx want %#llx\n", what,
		    (unsigned long long)got, (unsigned long long)want);
		failures++;
	}
}

int main(void)
{
	uint8_t record[K60M_ASSIGN_RECORD];
	uint32_t sources = 0;
	uint32_t destinations = 0;
	int rc;

	memset(record, 0xaa, sizeof(record));
	rc = k60_modem_assign_record(record, sizeof(record), 0x90000000ull, 0x280000u,
	    K60M_OWNER_HLOS, K60M_OWNER_MSS, 0xd0000000ull, &sources, &destinations);
	check("return", (uint64_t)(rc + 1), 1);
	check("physical", get_le(record, 8), 0x90000000ull);
	check("rounded", get_le(record + 8, 8), 0x280000ull);
	check("source vmid", get_le(record + 64, 4), K60M_VMID_HLOS);
	check("sources", sources, 1);
	check("dest vmid", get_le(record + 128, 4), K60M_VMID_MSS);
	check("dest perm", get_le(record + 132, 4), 6);
	check("destinations", destinations, 1);
	check("arg3 length", get_le(record + 192, 8), 4);
	check("arg4 pointer", get_le(record + 200, 8), 0xd0000080ull);
	check("arg5 length", get_le(record + 208, 8), 24);
	check("tail untouched", get_le(record + 216, 8), 0);

	/* Rounding is up to a page, and a two-way handoff lists both VMIDs. */
	memset(record, 0, sizeof(record));
	rc = k60_modem_assign_record(record, sizeof(record), 0x1000ull, 0x1001u,
	    K60M_OWNER_HLOS, K60M_OWNER_HLOS | K60M_OWNER_MSS, 0x20000000ull,
	    &sources, &destinations);
	check("pair return", (uint64_t)(rc + 1), 1);
	check("pair rounded", get_le(record + 8, 8), 0x2000u);
	check("pair sources", sources, 1);
	check("pair destinations", destinations, 2);
	/* With both owners listed, Pong grants the shared read/write value 6. */
	check("pair dest0 perm", get_le(record + 132, 4), 6);
	check("pair dest1 vmid", get_le(record + 128 + 24, 4), K60M_VMID_MSS);
	check("pair dest1 perm", get_le(record + 128 + 24 + 4, 4), 6);
	check("pair arg5 length", get_le(record + 208, 8), 48);

	/* A single HLOS destination keeps the exclusive read/write value 7. */
	memset(record, 0, sizeof(record));
	rc = k60_modem_assign_record(record, sizeof(record), 0x3000ull, 0x1000u,
	    K60M_OWNER_MSS, K60M_OWNER_HLOS, 0x20000000ull, &sources, &destinations);
	check("hlos return", (uint64_t)(rc + 1), 1);
	check("hlos source vmid", get_le(record + 64, 4), K60M_VMID_MSS);
	check("hlos dest vmid", get_le(record + 128, 4), K60M_VMID_HLOS);
	check("hlos dest perm", get_le(record + 132, 4), 7);

	/* The three refusals: short buffer, empty size, unknown owner bit. */
	check("short buffer", (uint64_t)(k60_modem_assign_record(record, 64, 0x1000ull,
	    0x1000u, K60M_OWNER_HLOS, K60M_OWNER_MSS, 0, NULL, NULL) + 1), 0);
	check("empty size", (uint64_t)(k60_modem_assign_record(record,
	    sizeof(record), 0x1000ull, 0u, K60M_OWNER_HLOS, K60M_OWNER_MSS, 0,
	    NULL, NULL) + 1), 0);
	check("owner bits", (uint64_t)(k60_modem_assign_record(record,
	    sizeof(record), 0x1000ull, 0x1000u, 8u, K60M_OWNER_MSS, 0, NULL,
	    NULL) + 1), 0);

	/* NULL outputs are allowed: the caller may only want the record. */
	check("null outputs", (uint64_t)(k60_modem_assign_record(record,
	    sizeof(record), 0x1000ull, 0x1000u, K60M_OWNER_HLOS, K60M_OWNER_MSS,
	    0, NULL, NULL) + 1), 1);

	if (failures != 0) {
		printf("K60 MODEM ASSIGN FAIL %u\n", failures);
		return 1;
	}
	printf("K60 MODEM ASSIGN PASS offsets, rounding, ownership bits, refusals\n");
	return 0;
}
