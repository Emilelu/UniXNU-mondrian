/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#include <kern/startup.h>
#include <kern/debug.h>
#include <libkern/section_keywords.h>
#include <mach/kmod.h>

extern kern_return_t pthread_start(kmod_info_t *, void *);
SECURITY_READ_ONLY_LATE(kern_return_t) source_pthread_status = KERN_FAILURE;

static void
source_pthread_bootstrap(void)
{
	static kmod_info_t info = {
		.info_version = KMOD_INFO_VERSION,
		.name = "source-libpthread",
		.version = "519.120.4",
	};
	source_pthread_status = pthread_start(&info, NULL);
	if (source_pthread_status != KERN_SUCCESS) {
		panic("source libpthread registration failed: %d", source_pthread_status);
	}
}
STARTUP(EARLY_BOOT, STARTUP_RANK_SECOND, source_pthread_bootstrap);
