/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* PAS (peripheral authentication service) calls for the K60 ADSP.
 *
 * The encoders are pure arithmetic and are covered by a host test; the SMC
 * itself is the only part that needs the device, and it follows the shape the
 * reference implementation uses: 64-bit standard call, SiP owner, service 2.
 */
#ifndef K60_ADSP_PAS_H
#define K60_ADSP_PAS_H

#include <stdint.h>

#define K60_SCM_SVC_PIL 0x02u
#define K60_SCM_PAS_INIT_IMAGE 0x01u
#define K60_SCM_PAS_MEM_SETUP 0x02u
#define K60_SCM_PAS_AUTH_AND_RESET 0x05u
#define K60_SCM_PAS_SHUTDOWN 0x06u

#define K60_SCM_VAL 0u
#define K60_SCM_RW 2u

#define K60_PAS_ADSP 1u
#define K60_ADSP_LOAD_BASE 0x86300000ull
#define K60_ADSP_LOAD_SPAN 0x3100000ull

/* Function id: SMC64 | SiP owner | service | command. */
static inline uint32_t
k60_scm_fn(uint32_t svc, uint32_t cmd)
{
	return (1u << 30) | (2u << 24) | ((svc & 0xffu) << 8) | (cmd & 0xffu);
}

/* Argument-type word: count in bits 3:0, type i in bits 5+2i:4+2i. */
static inline uint32_t
k60_scm_args(unsigned count, unsigned t0, unsigned t1, unsigned t2)
{
	return (count & 0xfu) | ((t0 & 3u) << 4) | ((t1 & 3u) << 6) | ((t2 & 3u) << 8);
}

/* A call succeeded only when both result registers are zero: x0 alone reports
 * the transport, x1 carries the payload verdict. */
static inline int
k60_scm_ok(uint64_t x0, uint64_t x1)
{
	return x0 == 0 && x1 == 0;
}

enum {
	K60PasOk = 0,
	K60PasDenied = -1,
	K60PasBadArg = -2,
};

int k60_adsp_auth_and_reset(void);
int k60_adsp_init_image(uint64_t phys);
int k60_adsp_mem_setup(uint64_t base, uint64_t span);
int k60_adsp_shutdown(void);

/* True when the kernel glue reached the secure monitor at least once; the
 * boot log uses it to separate "SCM refused" from "SCM never called". */
int k60_adsp_scm_tried(void);

#endif /* K60_ADSP_PAS_H */
