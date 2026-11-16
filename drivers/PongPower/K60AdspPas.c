/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* PAS calls for the K60 ADSP: the SMC glue only. The encoders live in the
 * header so a host test can prove them without the device. */

#include "K60AdspPas.h"

#ifndef K60_HOST_TEST

#include <pexpert/pexpert.h>
#include <sys/systm.h>
#include <IOKit/IOLib.h>

static int k60_scm_called;

/* x0..x7 are the SMCCC argument registers; the secure monitor writes both the
 * result (x0) and the payload status (x1) back through the same registers, and
 * hands a session cookie back in x6 when it preempts the call. */
static void
k60_scm_raw(uint64_t fn, uint64_t arginfo, uint64_t a, uint64_t b, uint64_t c,
    uint64_t *rx0, uint64_t *rx1, uint64_t *rx6)
{
	register uint64_t x0 __asm__("x0") = fn;
	register uint64_t x1 __asm__("x1") = arginfo;
	register uint64_t x2 __asm__("x2") = a;
	register uint64_t x3 __asm__("x3") = b;
	register uint64_t x4 __asm__("x4") = c;
	register uint64_t x5 __asm__("x5") = 0;
	register uint64_t x6 __asm__("x6") = *rx6;
	register uint64_t x7 __asm__("x7") = 0;

	__asm__ volatile("smc #0"
	    : "+r"(x0), "+r"(x1), "+r"(x2), "+r"(x3), "+r"(x4), "+r"(x5),
	      "+r"(x6), "+r"(x7)
	    :
	    : "x8", "x9", "x10", "x11", "x12", "x13", "x14", "x15", "x16",
	      "x17", "memory");

	*rx0 = x0;
	*rx1 = x1;
	*rx6 = x6;
}

/* Reference behaviour (pong, same SoC): a busy monitor is retried after a
 * short sleep, and an interrupted call is resumed by re-issuing with the
 * interrupted function id and the cookie from x6. Without both, a single
 * transient refusal ends the bring-up with a verdict that names the wrong
 * layer. */
static int
k60_scm_call(uint32_t fn, uint32_t arginfo, uint64_t a, uint64_t b, uint64_t c,
    uint64_t *rx0, uint64_t *rx1)
{
	uint64_t x0 = 0, x1 = 0, x6 = 0;
	unsigned busy;

	for (busy = 0; busy < K60_SCM_EBUSY_TRIES; busy++) {
		uint64_t call = fn;
		unsigned resumes = 0;

		for (;;) {
			k60_scm_raw(call, arginfo, a, b, c, &x0, &x1, &x6);
			k60_scm_called = 1;
			if ((int64_t)x0 != (int64_t)K60_SCM_INTERRUPTED ||
			    resumes >= K60_SCM_RESUME_TRIES) {
				break;
			}
			if (resumes == 0) {
				printf("K60PAS cmd=%#x interrupted; resuming session=%#llx\n",
				    fn, (unsigned long long)x6);
			}
			resumes++;
			call = (uint64_t)K60_SCM_INTERRUPTED;
		}
		if ((int64_t)x0 != (int64_t)K60_SCM_V2_EBUSY) {
			break;
		}
		IOSleep(K60_SCM_EBUSY_WAIT_MS);
	}
	*rx0 = x0;
	*rx1 = x1;
	return k60_scm_ok(x0, x1) ? K60PasOk : K60PasDenied;
}

static int
k60_pas_call(uint32_t cmd, uint32_t arginfo, uint64_t a, uint64_t b, uint64_t c)
{
	uint64_t x0 = 0, x1 = 0;
	int r = k60_scm_call(k60_scm_fn(K60_SCM_SVC_PIL, cmd), arginfo, a, b, c, &x0, &x1);

	if (r != K60PasOk) {
		printf("K60PAS cmd=%#x rc=%d x0=%#llx x1=%#llx\n", cmd, r,
		    (unsigned long long)x0, (unsigned long long)x1);
	}
	return r;
}

int
k60_adsp_auth_and_reset(void)
{
	printf("K60PAS auth_and_reset pas=%u\n", K60_PAS_ADSP);
	return k60_pas_call(K60_SCM_PAS_AUTH_AND_RESET, k60_scm_args(1, 0, 0, 0),
	    K60_PAS_ADSP, 0, 0);
}

int
k60_adsp_init_image(uint64_t phys)
{
	return k60_pas_call(K60_SCM_PAS_INIT_IMAGE,
	    k60_scm_args(2, K60_SCM_VAL, K60_SCM_RW, 0), K60_PAS_ADSP, phys, 0);
}

int
k60_adsp_mem_setup(uint64_t base, uint64_t span)
{
	printf("K60PAS mem_setup base=%#llx span=%#llx\n",
	    (unsigned long long)base, (unsigned long long)span);
	return k60_pas_call(K60_SCM_PAS_MEM_SETUP, k60_scm_args(3, 0, 0, 0),
	    K60_PAS_ADSP, base, span);
}

int
k60_adsp_shutdown(void)
{
	return k60_pas_call(K60_SCM_PAS_SHUTDOWN, k60_scm_args(1, 0, 0, 0),
	    K60_PAS_ADSP, 0, 0);
}

int
k60_adsp_scm_tried(void)
{
	return k60_scm_called;
}

#endif /* !K60_HOST_TEST */
