/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Modem (MSS) bring-up order: prove the image table is sane, copy it into the
 * mpss carveout when a carrier supplies the bytes, hand the metadata page to
 * PAS_INIT_IMAGE, hand the span to PAS_MEM_SETUP, and only then let
 * PAS_AUTH_AND_RESET release the core.
 *
 * The order is the contract, not a preference. The secure monitor on this SoC
 * refuses AUTH_AND_RESET before INIT_IMAGE/MEM_SETUP, and INIT_IMAGE takes the
 * metadata page (ELF header plus the hash segment), not a segment address.
 * The old code called auth first and passed each PT_LOAD address to
 * init_image; that shape cannot work on this firmware.
 *
 * Every step prints exactly one verdict line, and a failure line names the
 * step and the return value that refused, so a single boot log says which
 * layer stopped:
 *
 *   K60MODEM plan rows=... copied=... zeroed=... base=... window=...
 *   K60MODEM copy ok            | K60MODEM copy failed rc=<n>
 *   K60MODEM init_image ok ...  | K60MODEM init_image failed ... rc=<n>
 *   K60MODEM mem_setup ok ...   | K60MODEM mem_setup failed rc=<n>
 *   K60MODEM diagnostic stop after mem_setup: auth_reset not sent
 *   K60MODEM auth_reset ok      | K60MODEM auth_reset failed rc=<n>
 *
 * Off by default: k60_modem_probe_from_handoff() returns before it prints or
 * maps anything unless the pong_modem boot argument is present and non-zero,
 * so the shipped baseline never touches 0x8bc00000 and never issues an SMC. */

#include "K60ModemPas.h"
#include "K60ModemImage.h"

#ifdef K60_HOST_TEST
#include <stdio.h>
#else
#include <pexpert/pexpert.h>
#include <sys/systm.h>

/* osfmk/arm/machine_routines.h:703; declared here keeps the include path out
 * of the leaky kernel header set (same choice as K60AdspBoot.c). */
extern vm_offset_t ml_io_map_unmappable(vm_offset_t phys, vm_size_t size, uint32_t flags);

/* A 4 KiB page is enough to read the carrier signature; the 306 MiB window is
 * only mapped when a carrier has bytes to copy into it. */
#define K60_MODEM_PROBE_PAGE 0x1000
#endif

/* The UEFI carrier writes the 5,884-byte PAS metadata blob (ELF header plus
 * the hash segment) into the last 64 KiB page of the ABL staging area, just
 * below the boot image. It stays below 4 GiB and is reserved, so the secure
 * monitor can read it. ImageCarrierLib.c names the same address and the build
 * gate compares the two; do not change one side alone. */
#define K60_MODEM_METADATA 0xB7FF0000u
#define K60_MODEM_METADATA_BYTES 5884u

/* Phase 1 is the pre-registered diagnostic: it proves init_image and
 * mem_setup without resetting a modem that may still be running. */
#define K60_MODEM_PHASE_FULL 0
#define K60_MODEM_PHASE_METADATA_ONLY 1

int
k60_modem_bring_up(void *window, size_t window_bytes, K60ModemRead read, int phase)
{
	K60ModemPlan plan;
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

	/* One call, with the metadata page. INIT_IMAGE must not be replayed per
	 * segment: the monitor reads the ELF header and the hash from this page
	 * to find every segment itself. */
	rc = k60_modem_init_image((uint64_t)K60_MODEM_METADATA);
	if (rc != K60ModemPasOk) {
		printf("K60MODEM init_image failed metadata=%#x rc=%d\n",
		    (unsigned)K60_MODEM_METADATA, rc);
		return rc;
	}
	printf("K60MODEM init_image ok metadata=%#x bytes=%u\n",
	    (unsigned)K60_MODEM_METADATA, (unsigned)K60_MODEM_METADATA_BYTES);

	rc = k60_modem_mem_setup((uint64_t)K60_MODEM_BASE,
	    (uint64_t)K60_MODEM_WINDOW);
	if (rc != K60ModemPasOk) {
		printf("K60MODEM mem_setup failed rc=%d\n", rc);
		return rc;
	}
	printf("K60MODEM mem_setup ok base=%#x span=%#x\n",
	    (unsigned)K60_MODEM_BASE, (unsigned)K60_MODEM_WINDOW);

	if (phase == K60_MODEM_PHASE_METADATA_ONLY) {
		printf("K60MODEM diagnostic stop after mem_setup: auth_reset not sent\n");
		return K60ModemPasOk;
	}

	rc = k60_modem_auth_and_reset();
	if (rc != K60ModemPasOk) {
		printf("K60MODEM auth_reset failed rc=%d\n", rc);
		return rc;
	}
	printf("K60MODEM auth_reset ok\n");
	return K60ModemPasOk;
}

#ifndef K60_HOST_TEST
/* Called from the Data-mount path (patch 0621). Silent and inert unless
 * pong_modem is present: an ordinary boot takes the early return on the first
 * line, so neither the carveout nor the secure monitor is touched.
 *
 * pong_modem=1: full sequence (init_image, mem_setup, auth_reset).
 * pong_modem=2: full sequence, then the read-only QRTR enumeration.
 * pong_modem=3: diagnostic, stop after mem_setup and never send auth_reset. */
int
k60_modem_probe_from_handoff(void)
{
	vm_offset_t page;
	int enabled = 0;
	int phase = K60_MODEM_PHASE_FULL;
	int rc;

	if (!PE_parse_boot_argn("pong_modem", &enabled, sizeof(enabled)) ||
	    enabled == 0) {
		return 0;
	}
	printf("K60MODEM probe begin mode=%d\n", enabled);
	if (enabled >= 3) {
		phase = K60_MODEM_PHASE_METADATA_ONLY;
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

	rc = k60_modem_bring_up(NULL, 0, NULL, phase);
	if (rc != K60ModemPasOk || phase == K60_MODEM_PHASE_METADATA_ONLY) {
		return rc;
	}

	/* QRTR needs the modem after AUTH_AND_RESET, not before it: the reset
	 * clears whatever name service the previous boot left behind. */
	if (enabled >= 2) {
		extern int k60_modem_qrtr_probe(void);

		(void)k60_modem_qrtr_probe();
	}
	return rc;
}
#endif /* !K60_HOST_TEST */
