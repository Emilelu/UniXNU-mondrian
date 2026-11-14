/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Host test for the modem PAS encoders: pure arithmetic, no device needed. */
#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "K60ModemPas.h"

static void check_fn(void)
{
	/* SMC64 (bit 30) | SiP owner (2 << 24) | service 2 | command 5 */
	assert(k60_modem_scm_fn(K60M_SCM_SVC_PIL, K60M_SCM_PAS_AUTH_AND_RESET) ==
	    ((1u << 30) | (2u << 24) | (0x02u << 8) | 0x05u));
	/* The owner and service must not bleed into each other. */
	assert((k60_modem_scm_fn(0x02u, 0x00u) & 0xffu) == 0);
	assert(((k60_modem_scm_fn(0x02u, 0x00u) >> 8) & 0xffu) == 0x02u);
	assert(((k60_modem_scm_fn(0x02u, 0x00u) >> 24) & 0x3fu) == 0x02u);
	assert((k60_modem_scm_fn(0x02u, 0x00u) >> 30) == 1u);
	/* Out-of-range service/command are masked, not shifted in. */
	assert(k60_modem_scm_fn(0x1ffu, 0x1ffu) == k60_modem_scm_fn(0xffu, 0xffu));
}

static void check_args(void)
{
	/* one argument, no type bits */
	assert(k60_modem_scm_args(1, 0, 0, 0) == 1u);
	/* init_image: two arguments, VAL then RW */
	assert(k60_modem_scm_args(2, K60M_SCM_VAL, K60M_SCM_RW, 0) ==
	    (2u | (K60M_SCM_VAL << 4) | (K60M_SCM_RW << 6)));
	assert(k60_modem_scm_args(2, K60M_SCM_VAL, K60M_SCM_RW, 0) == 0x2u + (2u << 6));
	/* mem_setup: three arguments, no types */
	assert(k60_modem_scm_args(3, 0, 0, 0) == 3u);
	/* the count field is 4 bits and never carries into the type fields */
	assert((k60_modem_scm_args(0x1f, 0, 0, 0) >> 4) == 0);
}

static void check_ok(void)
{
	assert(k60_modem_scm_ok(0, 0) == 1);
	assert(k60_modem_scm_ok(0, 1) == 0);   /* transport fine, payload refused */
	assert(k60_modem_scm_ok(1, 0) == 0);   /* transport failed */
	assert(k60_modem_scm_ok(~0ull, ~0ull) == 0);
}

static void check_carrier(void)
{
	/* modem.b01 starts with this 16-byte pattern; the carrier check must
	 * accept exactly it. */
	static const unsigned char head[16] = {
	    0x0e, 0xc0, 0x00, 0x58, 0x00, 0xc0, 0x00, 0x58,
	    0x00, 0xc0, 0x00, 0x58, 0x00, 0xc0, 0x00, 0x58,
	};
	assert(k60_modem_carrier_ok(head, sizeof(head)));
	assert(!k60_modem_carrier_ok(head, 15));          /* too short */
	assert(!k60_modem_carrier_ok(head, 0));
	unsigned char flip[16];
	memcpy(flip, head, sizeof(flip));
	flip[0] ^= 0x01u;                                 /* first byte wrong */
	assert(!k60_modem_carrier_ok(flip, sizeof(flip)));
	memcpy(flip, head, sizeof(flip));
	flip[15] ^= 0x80u;                                /* last byte wrong */
	assert(!k60_modem_carrier_ok(flip, sizeof(flip)));
}

static void check_constants(void)
{
	assert(K60_PAS_MODEM == 4u);
	assert(K60M_SCM_PAS_INIT_IMAGE == 0x01u);
	assert(K60M_SCM_PAS_MEM_SETUP == 0x02u);
	assert(K60M_SCM_PAS_AUTH_AND_RESET == 0x05u);
	assert(K60M_SCM_PAS_SHUTDOWN == 0x06u);
}

int main(void)
{
	check_fn();
	check_args();
	check_ok();
	check_carrier();
	check_constants();
	printf("TESTS OK 5 groups (fn, args, ok, carrier, constants)\n");
	return 0;
}
