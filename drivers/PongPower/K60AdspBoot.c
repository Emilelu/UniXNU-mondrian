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
#include <sys/vnode.h>
#include <sys/namei.h>
#include <sys/uio.h>
#include <sys/fcntl.h>

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
 * is present, because the firmware reader does not exist yet: the point of
 * this probe is to make the plan run in a real boot and to name the first
 * failing layer instead of leaving the whole path untested. */
/* The payload volume is a memory disk the kernel already mounts as msdos at
 * /private/var/pong/md0 for the Metal delivery, so the same handle can carry
 * the ADSP segments. Path is fixed; a missing file names itself. */
static int
k60_adsp_ramdisk_reader(const char *part, void *dst, uint32_t bytes)
{
	char path[128];
	vfs_context_t ctx = vfs_context_current();
	struct vnode *vp = NULL;
	int resid = 0;
	int error;

	snprintf(path, sizeof(path), "/private/var/pong/md0/ADSP/%s", part);
	error = vnode_lookup(path, 0, &vp, ctx);
	if (error != 0) {
		printf("K60PAS lookup %s err=%d\n", path, error);
		return -1;
	}
	error = vn_rdwr(UIO_READ, vp, (caddr_t)dst, (int)bytes, 0,
	    UIO_SYSSPACE, 0, vfs_context_ucred(ctx), &resid, vfs_context_proc(ctx));
	vnode_put(vp);
	if (error != 0 || resid != 0) {
		printf("K60PAS read %s err=%d resid=%d\n", part, error, resid);
		return -1;
	}
	return 0;
}

int
k60_adsp_probe_from_handoff(void)
{
	int enabled = 0;

	if (!PE_parse_boot_argn("pong_adsp", &enabled, sizeof(enabled)) || enabled == 0) {
		return 0;
	}
	printf("K60PAS probe begin\n");
	return k60_adsp_bring_up((void *)(uintptr_t)K60_ADSP_BASE,
	    (size_t)K60_ADSP_WINDOW, k60_adsp_ramdisk_reader);
}

#endif /* !K60_HOST_TEST */
