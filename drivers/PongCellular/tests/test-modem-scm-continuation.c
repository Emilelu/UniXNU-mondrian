/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Host test for the real resumable SMC transaction loop in K60ModemPas.c.
 * Only the native SMC instruction is replaced; every public PAS entry point,
 * the retry loop and the argument reconstruction are the production code. */

#include <assert.h>
#include <stdint.h>
#include <stdio.h>

#include "K60ModemPas.h"

enum {
	MON_OK = 0,
	MON_INTERRUPT_ONCE,
	MON_INTERRUPT_FOREVER,
	MON_PAYLOAD_DENIED,
	MON_INTERRUPT_MANY,
	MON_INTERRUPT_THEN_DENIED,
	MON_TRANSPORT_ERROR,
	MON_LAST_CALL_SUCCESS,
};

static int mode;
static int calls;
static uint64_t first[8];
static uint64_t entered[8];
static uint64_t last[8];

static uint64_t
context_for_call(unsigned n)
{
	return 0x1234567800000000ull + n;
}

void
k60_modem_scm_invoke(uint64_t regs[8])
{
	int i;

	for (i = 0; i < 8; i++) {
		if (calls == 0) {
			first[i] = regs[i];
		}
		entered[i] = regs[i];
	}
	if (calls != 0) {
		assert(regs[0] == K60M_SCM_INTERRUPTED);
		for (i = 1; i <= 5; i++) {
			assert(regs[i] == first[i]);
		}
		assert(regs[6] == context_for_call((unsigned)calls));
		assert(regs[7] == first[7]);
	}
	calls++;

	if (mode == MON_INTERRUPT_FOREVER ||
	    (mode == MON_INTERRUPT_ONCE && calls == 1) ||
	    (mode == MON_INTERRUPT_MANY && calls <= 3) ||
	    (mode == MON_INTERRUPT_THEN_DENIED && calls <= 2) ||
	    (mode == MON_LAST_CALL_SUCCESS && calls < (int)K60M_SCM_MAX_CALLS)) {
		regs[0] = K60M_SCM_INTERRUPTED;
		regs[6] = context_for_call((unsigned)calls);
		/* Deliberately clobber input registers to prove they are reloaded. */
		for (i = 1; i <= 5; i++) {
			regs[i] = ~((uint64_t)calls + (unsigned)i);
		}
		regs[7] = ~0ull;
	} else if (mode == MON_PAYLOAD_DENIED) {
		regs[0] = 0;
		regs[1] = 0x82u;
		regs[6] = 0x5678u;
	} else if (mode == MON_INTERRUPT_THEN_DENIED) {
		regs[0] = (uint64_t)(int64_t)-22;
		regs[1] = 0x82u;
		regs[6] = 0x5678u;
	} else if (mode == MON_TRANSPORT_ERROR) {
		regs[0] = (uint64_t)(int64_t)-12;
		regs[1] = 0;
	} else {
		regs[0] = 0;
		regs[1] = 0;
		regs[6] = 0x5678u;
	}
	for (i = 0; i < 8; i++) {
		last[i] = regs[i];
	}
}

static void
check_init_args(void)
{
	assert(first[0] == k60_modem_scm_fn(K60M_SCM_SVC_PIL, K60M_SCM_PAS_INIT_IMAGE));
	assert(first[1] == k60_modem_scm_args(2, K60M_SCM_VAL, K60M_SCM_RW, 0));
	assert(first[2] == K60_PAS_MODEM);
	assert(first[3] == 0xB7FF0000u);
	assert(first[4] == 0 && first[5] == 0 && first[6] == 0 && first[7] == 0);
}

static void
check_success_after_one_interrupt(void)
{
	mode = MON_INTERRUPT_ONCE;
	calls = 0;
	assert(k60_modem_init_image(0xB7FF0000u) == K60ModemPasOk);
	assert(calls == 2);
	check_init_args();
	assert(entered[0] == K60M_SCM_INTERRUPTED);
	assert(entered[1] == k60_modem_scm_args(2, K60M_SCM_VAL, K60M_SCM_RW, 0));
	assert(entered[2] == K60_PAS_MODEM && entered[3] == 0xB7FF0000u);
	assert(entered[4] == 0 && entered[5] == 0 && entered[6] == context_for_call(1) && entered[7] == 0);
	assert(last[0] == 0 && last[1] == 0 && last[6] == 0x5678u);
}

static void
check_x1_result_ignored(void)
{
	mode = MON_PAYLOAD_DENIED;
	calls = 0;
	assert(k60_modem_init_image(0xB7FF0000u) == K60ModemPasOk);
	assert(calls == 1);
	check_init_args();
	assert(last[0] == 0 && last[1] == 0x82u);
}

static void
check_interrupt_budget(void)
{
	mode = MON_INTERRUPT_FOREVER;
	calls = 0;
	assert(k60_modem_init_image(0xB7FF0000u) == K60ModemPasInterrupted);
	assert(calls == K60M_SCM_MAX_CALLS);
	check_init_args();
	assert(last[0] == K60M_SCM_INTERRUPTED);
}

static void
check_repeated_interrupts(void)
{
	mode = MON_INTERRUPT_MANY;
	calls = 0;
	assert(k60_modem_init_image(0xB7FF0000u) == K60ModemPasOk);
	assert(calls == 4);
	check_init_args();
}

static void
check_denied_after_resume(void)
{
	mode = MON_INTERRUPT_THEN_DENIED;
	calls = 0;
	assert(k60_modem_init_image(0xB7FF0000u) == K60ModemPasDenied);
	assert(calls == 3);
	assert(last[0] == (uint64_t)(int64_t)-22 && last[1] == 0x82u);
}

static void
check_transport_error(void)
{
	mode = MON_TRANSPORT_ERROR;
	calls = 0;
	assert(k60_modem_init_image(0xB7FF0000u) == K60ModemPasDenied);
	assert(calls == 1);
	assert(last[0] == (uint64_t)(int64_t)-12);
}

static void
check_success_at_budget(void)
{
	mode = MON_LAST_CALL_SUCCESS;
	calls = 0;
	assert(k60_modem_init_image(0xB7FF0000u) == K60ModemPasOk);
	assert(calls == (int)K60M_SCM_MAX_CALLS);
	assert(last[0] == 0 && last[1] == 0);
}

static void
check_other_entry_points(void)
{
	mode = MON_OK;
	calls = 0;
	assert(k60_modem_auth_and_reset() == K60ModemPasOk);
	assert(calls == 1);
	assert(first[0] == k60_modem_scm_fn(K60M_SCM_SVC_PIL,
	    K60M_SCM_PAS_AUTH_AND_RESET));
	assert(first[1] == k60_modem_scm_args(1, 0, 0, 0));
	assert(first[2] == K60_PAS_MODEM);

	calls = 0;
	assert(k60_modem_mem_setup(0x8BC00000u, 0x13200000u) == K60ModemPasOk);
	assert(calls == 1);
	assert(first[0] == k60_modem_scm_fn(K60M_SCM_SVC_PIL,
	    K60M_SCM_PAS_MEM_SETUP));
	assert(first[1] == k60_modem_scm_args(3, 0, 0, 0));
	assert(first[2] == K60_PAS_MODEM);
	assert(first[3] == 0x8BC00000u && first[4] == 0x13200000u);
}

int
main(void)
{
	check_success_after_one_interrupt();
	check_x1_result_ignored();
	check_interrupt_budget();
	check_repeated_interrupts();
	check_denied_after_resume();
	check_transport_error();
	check_success_at_budget();
	check_other_entry_points();
	printf("TESTS OK 8 groups (resume-once, x1-result-ignored, budget, repeated, resume-denied, transport-error, last-call, entry-points)\n");
	return 0;
}
