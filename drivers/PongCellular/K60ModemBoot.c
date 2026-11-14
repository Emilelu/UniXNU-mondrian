/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Modem (MSS) bring-up order: prove the image table is sane, copy it into the
 * mpss carveout when a carrier supplies the bytes, let the secure monitor
 * authenticate, then hand the span to the modem.
 *
 * Every step prints exactly one verdict line, and a failure line names the
 * step and the return value that refused, so a single boot log says which
 * layer stopped:
 *
 *   K60MODEM plan rows=... copied=... zeroed=... base=... window=...
 *   K60MODEM copy ok            | K60MODEM copy failed rc=<n>
 *   K60MODEM auth_reset ok      | K60MODEM auth_reset failed rc=<n>
 *   K60MODEM init_image ok ...  | K60MODEM init_image failed seg=<n> ... rc=<n>
 *   K60MODEM mem_setup ok ...   | K60MODEM mem_setup failed rc=<n>
 *
 * Off by default: k60_modem_probe_from_handoff() returns before it prints or
 * maps anything unless the pong_modem boot argument is present and non-zero,
 * so the shipped baseline never touches 0x8bc00000 and never issues an SMC. */

#include "K60ModemPas.h"
#include "K60ModemImage.h"

#ifndef K60_HOST_TEST

#include <pexpert/pexpert.h>
#include <sys/systm.h>

/* osfmk/arm/machine_routines.h:703; declared here keeps the include path out
 * of the leaky kernel header set (same choice as K60AdspBoot.c). */
extern vm_offset_t ml_io_map_unmappable(vm_offset_t phys, vm_size_t size, uint32_t flags);

/* A 4 KiB page is enough to read the carrier signature; the 306 MiB window is
 * only mapped when a carrier has bytes to copy into it. */
#define K60_MODEM_PROBE_PAGE 0x1000

int
k60_modem_bring_up(void *window, size_t window_bytes, K60ModemRead read)
{
	K60ModemPlan plan;
	uint32_t i, images = 0;
	int rc;

	rc = k60_modem_plan(&plan);
	if (rc != 0) {
		printf("K60MODEM plan failed rc=%d\n", rc);
		return rc;
	}
	printf("K60MODEM plan rows=%u copied=%u zeroed=%u base=%#x window=%#x\n",
	    plan.segments, plan.copied, plan.zeroed, plan.base, plan.window);

	if (read != NULL) {
		rc = k60_modem_copy(window, window_bytes, read);
		if (rc != 0) {
			printf("K60MODEM copy failed rc=%d\n", rc);
			return rc;
		}
		printf("K60MODEM copy ok\n");
	} else {
		/* No carrier: the bytes are already in the carveout, which the
		 * caller proved by matching the carrier signature. */
		printf("K60MODEM copy skipped: image already staged at %#x\n",
		    plan.base);
	}

	rc = k60_modem_auth_and_reset();
	if (rc != K60ModemPasOk) {
		printf("K60MODEM auth_reset failed rc=%d\n", rc);
		return rc;
	}
	printf("K60MODEM auth_reset ok\n");

	for (i = 0; i < K60_MODEM_SEGMENTS; i++) {
		const K60ModemSegment *s = &k60_modem_segments[i];

		if (s->bytes == 0) {
			/* Pure bss row: nothing to authenticate for it. */
			continue;
		}
		rc = k60_modem_init_image((uint64_t)s->paddr);
		if (rc != K60ModemPasOk) {
			printf("K60MODEM init_image failed seg=%u addr=%#x bytes=%u rc=%d\n",
			    i, s->paddr, s->bytes, rc);
			return rc;
		}
		images++;
	}
	printf("K60MODEM init_image ok segments=%u\n", images);

	rc = k60_modem_mem_setup((uint64_t)K60_MODEM_BASE,
	    (uint64_t)K60_MODEM_WINDOW);
	if (rc != K60ModemPasOk) {
		printf("K60MODEM mem_setup failed rc=%d\n", rc);
		return rc;
	}
	printf("K60MODEM mem_setup ok base=%#x span=%#x\n",
	    (unsigned)K60_MODEM_BASE, (unsigned)K60_MODEM_WINDOW);
	return K60ModemPasOk;
}

/* Called from the Data-mount path (patch 0621). Silent and inert unless
 * pong_modem is present: an ordinary boot takes the early return on the first
 * line, so neither the carveout nor the secure monitor is touched. */
int
k60_modem_probe_from_handoff(void)
{
	vm_offset_t page;
	int enabled = 0;

	if (!PE_parse_boot_argn("pong_modem", &enabled, sizeof(enabled)) ||
	    enabled == 0) {
		return 0;
	}
	printf("K60MODEM probe begin\n");

	/* pong_modem=2 also asks the read-only QRTR enumeration to look at the
	 * modem that is already running: it sends one NEW_LOOKUP and folds the
	 * replies. It runs before the PAS sequence so a reset cannot hide it. */
	if (enabled >= 2) {
		extern int k60_modem_qrtr_probe(void);

		(void)k60_modem_qrtr_probe();
	}

	page = ml_io_map_unmappable((vm_offset_t)K60_MODEM_BASE,
	    (vm_size_t)K60_MODEM_PROBE_PAGE,
	    0x2 /* VM_WIMG_DEFAULT: the carveout is DDR, not device memory */);
	if (page == 0) {
		printf("K60MODEM cannot map the carveout head %#x\n",
		    (unsigned)K60_MODEM_BASE);
		return -1;
	}
	if (!k60_modem_carrier_ok((const void *)(uintptr_t)page,
	    K60_MODEM_PROBE_PAGE)) {
		printf("K60MODEM carrier absent: no modem image staged at %#x\n",
		    (unsigned)K60_MODEM_BASE);
		printf("K60MODEM pas skipped, nothing was handed to the secure monitor\n");
		return 0;
	}
	printf("K60MODEM carrier present at %#x\n", (unsigned)K60_MODEM_BASE);

	return k60_modem_bring_up(NULL, 0, NULL);
}

#endif /* !K60_HOST_TEST */
