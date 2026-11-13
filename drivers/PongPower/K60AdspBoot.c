/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* ADSP bring-up order: prove the image table is sane, copy it into the
 * carveout, let the secure monitor authenticate, then hand the span to the
 * DSP. Every step prints its own verdict so a single boot log says which
 * layer refused. */

#include "K60AdspPas.h"
#include "K60AdspImage.h"
#include "K60Fat.h"

#ifndef K60_HOST_TEST

#include <pexpert/pexpert.h>
#include <sys/systm.h>
#include <sys/vnode.h>
#include <sys/namei.h>
#include <sys/uio.h>
#include <sys/fcntl.h>

/* osfmk/arm/machine_routines.h:703; declaring it here keeps the
 * include path out of the leaky kernel header set. */
extern vm_offset_t ml_io_map(vm_offset_t phys, vm_size_t size);

int
k60_adsp_bring_up(void *window, size_t window_bytes, K60AdspRead read)
{
	K60AdspPlan plan;
	uint32_t i;
	int rc;

	rc = k60_adsp_plan(&plan);
	if (rc != 0) {
		printf("K60PAS plan rc=%d\n", rc);
		return rc;
	}
	printf("K60PAS plan rows=%u copied=%u zeroed=%u base=%#x window=%#x\n",
	    plan.segments, plan.copied, plan.zeroed, plan.base, plan.window);

	rc = k60_adsp_copy(window, window_bytes, read);
	if (rc != 0) {
		printf("K60PAS copy rc=%d\n", rc);
		return rc;
	}
	printf("K60PAS copy ok\n");

	rc = k60_adsp_auth_and_reset();
	if (rc != K60PasOk) {
		printf("K60PAS auth refused rc=%d\n", rc);
		return rc;
	}
	printf("K60PAS auth ok\n");

	for (i = 0; i < K60_ADSP_SEGMENTS; i++) {
		const K60AdspSegment *s = &k60_adsp_segments[i];

		if (s->bytes == 0) {
			continue;
		}
		rc = k60_adsp_init_image((uint64_t)s->paddr);
		if (rc != K60PasOk) {
			printf("K60PAS init seg=%u addr=%#x bytes=%u rc=%d\n",
			    i, s->paddr, s->bytes, rc);
			return rc;
		}
	}
	printf("K60PAS init all segments ok\n");

	rc = k60_adsp_mem_setup((uint64_t)K60_ADSP_BASE, (uint64_t)K60_ADSP_WINDOW);
	if (rc != K60PasOk) {
		printf("K60PAS mem_setup refused rc=%d\n", rc);
		return rc;
	}
	printf("K60PAS mem_setup ok base=%#x span=%#x\n",
	    (unsigned)K60_ADSP_BASE, (unsigned)K60_ADSP_WINDOW);
	return K60PasOk;
}


/* Called from the Data-mount path (patch 0614). Off unless the boot argument
 * is present, so the shipped baseline never takes this path. */
/* This XNU has no msdos filesystem and 0404's mount never ran, so the old
 * /private/var/pong/md0 path could never resolve. md0 is a contiguous block
 * device whose base and size the firmware already wrote into the
 * [pv]md0=<base>@<size> token that bsd/dev/memdev.c consumes, so we parse the
 * same token and walk the FAT volume ourselves. */
static K60FatVolume k60_fat_vol;
static const void *k60_fat_base;
static int k60_fat_ready;

static int
k60_adsp_md_window(uint64_t *base, uint64_t *size)
{
	const char *args = PE_boot_args();

	if (args == NULL) {
		printf("K60PAS no boot arguments\n");
		return -1;
	}
	if (k60_md_parse(args, 256, "pmd0", base, size) != 0) {
		printf("K60PAS no pmd0 boot argument; the ramdisk has no known base\n");
		return -1;
	}
	printf("K60PAS pmd0 base=%#llx size=%#llx\n",
	    (unsigned long long)*base, (unsigned long long)*size);
	return 0;
}

static int
k60_adsp_ramdisk_reader(const char *part, void *dst, uint32_t bytes)
{
	uint32_t offset = 0, length = 0;
	int rc;

	if (!k60_fat_ready) {
		printf("K60PAS fat volume not opened\n");
		return -1;
	}
	rc = k60_fat_find(k60_fat_base, &k60_fat_vol, "ADSP", part, &offset,
	    &length);
	if (rc != 0) {
		printf("K60PAS fat find %s rc=%d\n", part, rc);
		return -1;
	}
	if (length != bytes) {
		printf("K60PAS fat size %s have=%u want=%u\n", part, length, bytes);
		return -1;
	}
	memcpy(dst, (const uint8_t *)k60_fat_base + offset, (size_t)length);
	return 0;
}

int
k60_adsp_probe_from_handoff(void)
{
	uint64_t base = 0, size = 0;
	vm_offset_t window;
	int enabled = 0;

	if (!PE_parse_boot_argn("pong_adsp", &enabled, sizeof(enabled)) || enabled == 0) {
		return 0;
	}
	printf("K60PAS probe begin\n");
	if (k60_adsp_md_window(&base, &size) != 0) {
		return -1;
	}
	k60_fat_base = (const void *)(uintptr_t)base;
	if (k60_fat_open(k60_fat_base, (size_t)size, &k60_fat_vol) != 0) {
		printf("K60PAS fat open failed; not a readable volume\n");
		return -1;
	}
	k60_fat_ready = 1;
	printf("K60PAS fat open ok bps=%u spc=%u root=%u clusters=%u\n",
	    k60_fat_vol.bytes_per_sector, k60_fat_vol.sectors_per_cluster,
	    k60_fat_vol.root_cluster, k60_fat_vol.clusters);

	window = ml_io_map((vm_offset_t)K60_ADSP_BASE,
	    (vm_size_t)K60_ADSP_WINDOW);
	if (window == 0) {
		printf("K60PAS cannot map the carveout\n");
		return -1;
	}
	return k60_adsp_bring_up((void *)window, (size_t)K60_ADSP_WINDOW,
	    k60_adsp_ramdisk_reader);
}

#endif /* !K60_HOST_TEST */
