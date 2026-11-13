/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Host test for the PAS encoders: pure arithmetic, no device needed. */
#include <assert.h>
#include <stdio.h>

#include "K60AdspPas.h"

static void check_fn(void)
{
	/* SMC64 (bit 30) | SiP owner (2 << 24) | service 2 | command 5 */
	assert(k60_scm_fn(K60_SCM_SVC_PIL, K60_SCM_PAS_AUTH_AND_RESET) ==
	    ((1u << 30) | (2u << 24) | (0x02u << 8) | 0x05u));
	/* The owner and service must not bleed into each other. */
	assert((k60_scm_fn(0x02u, 0x00u) & 0xffu) == 0);
	assert(((k60_scm_fn(0x02u, 0x00u) >> 8) & 0xffu) == 0x02u);
	assert(((k60_scm_fn(0x02u, 0x00u) >> 24) & 0x3fu) == 0x02u);
	assert((k60_scm_fn(0x02u, 0x00u) >> 30) == 1u);
	/* Out-of-range service/command are masked, not shifted in. */
	assert(k60_scm_fn(0x1ffu, 0x1ffu) == k60_scm_fn(0xffu, 0xffu));
}

static void check_args(void)
{
	/* one argument, no type bits */
	assert(k60_scm_args(1, 0, 0, 0) == 1u);
	/* init_image: two arguments, VAL then RW */
	assert(k60_scm_args(2, K60_SCM_VAL, K60_SCM_RW, 0) ==
	    (2u | (K60_SCM_VAL << 4) | (K60_SCM_RW << 6)));
	assert(k60_scm_args(2, K60_SCM_VAL, K60_SCM_RW, 0) == 0x2u + (2u << 6));
	/* mem_setup: three arguments, no types */
	assert(k60_scm_args(3, 0, 0, 0) == 3u);
	/* the count field is 4 bits and never carries into the type fields */
	assert((k60_scm_args(0x1f, 0, 0, 0) >> 4) == 0);
}

static void check_ok(void)
{
	assert(k60_scm_ok(0, 0) == 1);
	assert(k60_scm_ok(0, 1) == 0);   /* transport fine, payload refused */
	assert(k60_scm_ok(1, 0) == 0);   /* transport failed */
	assert(k60_scm_ok(~0ull, ~0ull) == 0);
}

static void check_constants(void)
{
	assert(K60_PAS_ADSP == 1u);
	assert(K60_ADSP_LOAD_BASE == 0x86300000ull);
	assert(K60_ADSP_LOAD_SPAN == 0x3100000ull);
	assert(K60_SCM_PAS_INIT_IMAGE == 0x01u);
	assert(K60_SCM_PAS_MEM_SETUP == 0x02u);
	assert(K60_SCM_PAS_AUTH_AND_RESET == 0x05u);
}

int main(void)
{
	check_fn();
	check_args();
	check_ok();
	check_constants();
	printf("TESTS OK 4 groups (fn, args, ok, constants)\n");
	return 0;
}
