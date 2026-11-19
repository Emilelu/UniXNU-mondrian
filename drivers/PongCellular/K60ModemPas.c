/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* PAS calls for the K60 modem: the SMC glue only. The encoders live in the
 * header so a host test can prove them without the device.
 *
 * Every line this file prints starts with K60MODEM: so a boot log can be
 * filtered for the modem alone. Nothing here runs unless the caller was
 * reached through the pong_modem boot argument. */

#include "K60ModemPas.h"

#ifndef K60_HOST_TEST

/* Host regression replaces only the instruction; the transaction loop and
 * public PAS entry points below are the production implementation. */
#ifdef K60_MODEM_SCM_TEST
#include <stdio.h>
extern void k60_modem_scm_invoke(uint64_t regs[8]);
#else
#include <pexpert/pexpert.h>
#include <sys/systm.h>

static void
k60_modem_scm_invoke(uint64_t regs[8])
{
	register uint64_t x0 __asm__("x0") = regs[0];
	register uint64_t x1 __asm__("x1") = regs[1];
	register uint64_t x2 __asm__("x2") = regs[2];
	register uint64_t x3 __asm__("x3") = regs[3];
	register uint64_t x4 __asm__("x4") = regs[4];
	register uint64_t x5 __asm__("x5") = regs[5];
	register uint64_t x6 __asm__("x6") = regs[6];
	register uint64_t x7 __asm__("x7") = regs[7];

	__asm__ volatile("smc #0"
	    : "+r"(x0), "+r"(x1), "+r"(x2), "+r"(x3), "+r"(x4), "+r"(x5),
	      "+r"(x6), "+r"(x7)
	    :
	    : "x8", "x9", "x10", "x11", "x12", "x13", "x14", "x15",
	      "x16", "x17", "cc", "memory");

	regs[0] = x0;
	regs[1] = x1;
	regs[6] = x6;
}
#endif

static int k60_modem_scm_called;

static int
k60_modem_scm_call(uint32_t fn, uint32_t arginfo, uint64_t a, uint64_t b,
    uint64_t c, uint64_t d, uint64_t *rx0, uint64_t *rx1, unsigned *calls_out)
{
	uint64_t regs[8];
	uint64_t context = 0;
	unsigned calls;

	/* QCOM_SCM_INTERRUPTED resumes the same transaction, rather than starting
	 * PAS_INIT_IMAGE again. Reload original x1..x5/x7 on every entry and pass
	 * the returned x6 back unchanged. Only x0=1 requests continuation. */
	for (calls = 0; calls < K60M_SCM_MAX_CALLS; calls++) {
		regs[0] = calls == 0 ? fn : K60M_SCM_INTERRUPTED;
		regs[1] = arginfo;
		regs[2] = a;
		regs[3] = b;
		regs[4] = c;
		regs[5] = d;
		regs[6] = context;
		regs[7] = 0;
		k60_modem_scm_called = 1;
		k60_modem_scm_invoke(regs);
		context = regs[6];
		if (regs[0] != K60M_SCM_INTERRUPTED) {
			break;
		}
	}

	*rx0 = regs[0];
	*rx1 = regs[1];
	*calls_out = calls;
	if (regs[0] == K60M_SCM_INTERRUPTED) {
		return K60ModemPasInterrupted;
	}
	return k60_modem_scm_ok(regs[0], regs[1]) ? K60ModemPasOk : K60ModemPasDenied;
}

static int
k60_modem_pas_call(uint32_t cmd, uint32_t arginfo, uint64_t a, uint64_t b,
    uint64_t c)
{
	uint64_t x0 = 0, x1 = 0;
	unsigned calls = 0;
	int r = k60_modem_scm_call(k60_modem_scm_fn(K60M_SCM_SVC_PIL, cmd),
	    arginfo, a, b, c, 0, &x0, &x1, &calls);

	if (r != K60ModemPasOk) {
		printf("K60MODEM scm cmd=%#x rc=%d calls=%u x0=%#llx x1=%#llx\n", cmd, r,
		    calls, (unsigned long long)x0, (unsigned long long)x1);
	} else if (calls > K60M_SCM_LOG_CALLS) {
		printf("K60MODEM scm cmd=%#x ok calls=%u\n", cmd, calls);
	}
	return r;
}

/* SCM 0x0c/0x16 asks the monitor to move the ownership of a physical range
 * between the AP and the modem. The record, the source vmid list and the
 * destination list are the three buffers the call references; they were
 * built by k60_modem_assign_record() in a 4 KiB scratch page. The type word
 * marks all four arguments as plain values, which is the shape the sibling
 * PAS calls already use on this monitor. A refusal is reported, never
 * papered over: the caller still answers the modem with the physical
 * address and the flight tells us whether access worked. */
int
k60_modem_assign_call(uint64_t scratch)
{
	uint64_t x0 = 0, x1 = 0;
	unsigned calls = 0;
	const uint32_t arginfo = k60_modem_scm_args(4, K60M_SCM_VAL, K60M_SCM_VAL,
	    K60M_SCM_VAL);
	int r = k60_modem_scm_call(k60_modem_scm_fn(K60M_SCM_SVC_MEM,
	    K60M_SCM_MEM_ASSIGN), arginfo, scratch, 16, scratch + 64,
	    scratch + 192, &x0, &x1, &calls);

	printf("K60MODEM scm mem_assign rc=%d calls=%u x0=%#llx x1=%#llx scratch=%#llx\n",
	    r, calls, (unsigned long long)x0, (unsigned long long)x1,
	    (unsigned long long)scratch);
	return r;
}

int
k60_modem_auth_and_reset(void)
{
	return k60_modem_pas_call(K60M_SCM_PAS_AUTH_AND_RESET,
	    k60_modem_scm_args(1, 0, 0, 0), K60_PAS_MODEM, 0, 0);
}

int
k60_modem_init_image(uint64_t phys)
{
	return k60_modem_pas_call(K60M_SCM_PAS_INIT_IMAGE,
	    k60_modem_scm_args(2, K60M_SCM_VAL, K60M_SCM_RW, 0), K60_PAS_MODEM,
	    phys, 0);
}

int
k60_modem_mem_setup(uint64_t base, uint64_t span)
{
	return k60_modem_pas_call(K60M_SCM_PAS_MEM_SETUP,
	    k60_modem_scm_args(3, 0, 0, 0), K60_PAS_MODEM, base, span);
}

int
k60_modem_shutdown(void)
{
	return k60_modem_pas_call(K60M_SCM_PAS_SHUTDOWN,
	    k60_modem_scm_args(1, 0, 0, 0), K60_PAS_MODEM, 0, 0);
}

int
k60_modem_scm_tried(void)
{
	return k60_modem_scm_called;
}

#endif /* !K60_HOST_TEST */
