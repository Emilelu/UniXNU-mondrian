/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Host run of the amplifier probe against zeroed MMIO.
 *
 * The stub headers prove the glue compiles; this proves the entry point also
 * runs: every register window comes back as a zeroed page, so the probe must
 * walk its early path, print what it looks at, and stop at the first hardware
 * answer that is missing - without crashing, hanging or sanitizer noise.
 *
 * PROBE_GATE selects the boot argument the probe reads:
 *   1  behave as if "pong_audio_probe=1" was passed (default)
 *   0  no argument, so the probe must return 0 and print nothing
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int pong_audio_amp_probe(void);

#define MAX_PAGES 32
static unsigned char *pages[MAX_PAGES];
static uintptr_t keys[MAX_PAGES];
static unsigned count;

uintptr_t
ml_io_map(uintptr_t phys, size_t size)
{
	unsigned i;
	(void)size;
	for (i = 0; i < count; ++i) {
		if (keys[i] == phys) {
			return (uintptr_t)pages[i];
		}
	}
	if (count == MAX_PAGES) {
		abort();
	}
	pages[count] = calloc(1, 65536);
	if (pages[count] == NULL) {
		abort();
	}
	keys[count] = phys;
	return (uintptr_t)pages[count++];
}

uintptr_t
ml_io_map_wcomb(uintptr_t phys, size_t size)
{
	return ml_io_map(phys, size);
}

void
delay_for_interval(uint64_t interval, uint64_t scale)
{
	(void)interval;
	(void)scale;
}

int
PE_parse_boot_argn(const char *name, void *out, int max)
{
	const char *gate = getenv("PROBE_GATE");

	if (strcmp(name, "pong_audio_probe") != 0) {
		return 0;
	}
	if (gate != NULL && gate[0] == '0') {
		return 0;
	}
	if (max < (int)sizeof(uint32_t)) {
		return 0;
	}
	*(uint32_t *)out = 1u;
	return 1;
}

int
main(void)
{
	int rc = pong_audio_amp_probe();

	printf("PROBE RC %d\n", rc);
	return 0;
}
