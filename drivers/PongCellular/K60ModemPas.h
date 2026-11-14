/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* PAS (peripheral authentication service) calls for the K60 modem (MSS).
 *
 * Sibling of drivers/PongPower/K60AdspPas.h. The encoders are the same
 * arithmetic -- SMC64, SiP owner, service 2 -- and are covered by a host test;
 * only the peripheral id differs, and that difference is the whole point of
 * this file: the modem is PAS id 4, not the ADSP's 1.
 *
 * Why 4 and not a value read from the DT: the live Android DT node
 * remoteproc-mss@04080000 carries no qcom,pas-id property at all (measured,
 * od reports "No such file or directory"). 4 comes from the cape platform
 * default recorded by the Pong ADT generator and from the reference port:
 *
 *   E:/k60-work/references/UniXNU-pong-upstream/scripts/make-pong-adt-ipados18.py:320
 *       ('pong,pas-id', struct.pack('<I', 4))
 *   E:/k60-work/references/phk110-port/drivers/modem/hakios.mpss.c:1050
 *       #define PAS_MPSS_DEFAULT 4   -- its comment: dt: qcom,pas-id of qcom,mss
 *
 * The IPA on this SoC is PAS id 15 and is out of scope here.
 *
 * Sources: docs/research/cellular/06-MODEM-PAS.md.
 */
#ifndef K60_MODEM_PAS_H
#define K60_MODEM_PAS_H

#include <stddef.h>
#include <stdint.h>

#define K60M_SCM_SVC_PIL 0x02u
#define K60M_SCM_PAS_INIT_IMAGE 0x01u
#define K60M_SCM_PAS_MEM_SETUP 0x02u
#define K60M_SCM_PAS_AUTH_AND_RESET 0x05u
#define K60M_SCM_PAS_SHUTDOWN 0x06u

#define K60M_SCM_VAL 0u
#define K60M_SCM_RW 2u

/* Peripheral id for the modem (MSS) on SM8475/cape. See the header comment. */
#define K60_PAS_MODEM 4u

/* Function id: SMC64 | SiP owner | service | command. */
static inline uint32_t
k60_modem_scm_fn(uint32_t svc, uint32_t cmd)
{
	return (1u << 30) | (2u << 24) | ((svc & 0xffu) << 8) | (cmd & 0xffu);
}

/* Argument-type word: count in bits 3:0, type i in bits 5+2i:4+2i. */
static inline uint32_t
k60_modem_scm_args(unsigned count, unsigned t0, unsigned t1, unsigned t2)
{
	return (count & 0xfu) | ((t0 & 3u) << 4) | ((t1 & 3u) << 6) | ((t2 & 3u) << 8);
}

/* A call succeeded only when both result registers are zero: x0 alone reports
 * the transport, x1 carries the payload verdict. */
static inline int
k60_modem_scm_ok(uint64_t x0, uint64_t x1)
{
	return x0 == 0 && x1 == 0;
}

/* Carrier probe: modem.b01 loads at the carveout base and its first 16 bytes
 * are the fixed pattern below (dumped from the shipped modem.b01). A staged
 * image therefore announces itself without any bookkeeping; anything else
 * means the carveout holds firmware or garbage that is not our image, and the
 * PAS handshake must not run. */
static inline int
k60_modem_carrier_ok(const void *at, size_t bytes)
{
	static const uint8_t head[16] = {
		0x0e, 0xc0, 0x00, 0x58, 0x00, 0xc0, 0x00, 0x58,
		0x00, 0xc0, 0x00, 0x58, 0x00, 0xc0, 0x00, 0x58,
	};
	const uint8_t *p = (const uint8_t *)at;
	size_t i;

	if (at == NULL || bytes < sizeof(head)) {
		return 0;
	}
	for (i = 0; i < sizeof(head); i++) {
		if (p[i] != head[i]) {
			return 0;
		}
	}
	return 1;
}

enum {
	K60ModemPasOk = 0,
	K60ModemPasDenied = -1,
	K60ModemPasBadArg = -2,
};

int k60_modem_auth_and_reset(void);
int k60_modem_init_image(uint64_t phys);
int k60_modem_mem_setup(uint64_t base, uint64_t span);
int k60_modem_shutdown(void);

/* True when the kernel glue reached the secure monitor at least once; the
 * boot log uses it to separate "SCM refused" from "SCM never called". */
int k60_modem_scm_tried(void);

#endif /* K60_MODEM_PAS_H */
