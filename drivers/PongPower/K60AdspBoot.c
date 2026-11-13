/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* ADSP bring-up order: prove the image table is sane, copy it into the
 * carveout, let the secure monitor authenticate, then hand the span to the
 * DSP. Every step prints its own verdict so a single boot log says which
 * layer refused. */

#include "K60AdspPas.h"
#include "K60AdspImage.h"

#ifndef K60_HOST_TEST

#include <pexpert/pexpert.h>
#include <sys/systm.h>

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

#endif /* !K60_HOST_TEST */
