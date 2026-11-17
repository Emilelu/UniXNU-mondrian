/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* K60 IPA data path M0 skeleton.
 *
 * M0 is deliberately inert. It carries the register-map constants and the
 * version decoder so later stages cannot invent a different base address,
 * but it maps no MMIO and performs no PAS call. The only runtime entry point
 * returns K60IpaNotReady; no existing modem path calls it yet.
 */

#include "K60Ipa.h"

#ifdef K60_HOST_TEST
#include <stdio.h>
#else
#include <sys/systm.h>
#endif

_Static_assert(K60_IPA_CFG_BASE == 0x03f40000u,
    "IPA register block must be wrapper 0x3e00000 + cfg offset 0x140000");
_Static_assert(K60_GSI_BASE == 0x03e04000u,
    "GSI view must match the live DT gsi-base");
_Static_assert(K60_IPA_VERSION_ADDR == 0x03f40028u,
    "IPA_VERSION must be the IPA register block plus 0x28");
_Static_assert(K60_IPA_IRQ == 654u && K60_GSI_IRQ == 432u,
    "IPA/GSI GIC interrupts must match the live DT");
_Static_assert(K60_IPA_PAS_ID == 15u,
    "IPA firmware uses PAS id 15 on this board");

const char k60_ipa_marker[] = "K60IPA M0 skeleton linked";

K60IpaVersion
k60_ipa_decode_comp_hw_version(uint32_t raw)
{
    K60IpaVersion version;

    version.raw = raw;
    version.major = (raw & 0xf0000000u) >> 28;
    version.minor = (raw & 0x0fff0000u) >> 16;
    version.step = raw & 0x0000ffffu;
    return version;
}

int
k60_ipa_probe(void)
{
    printf("K60IPA M0 skeleton: cfg=0x%x gsi=0x%x irq=%u/%u state=not-ready\n",
        K60_IPA_CFG_BASE, K60_GSI_BASE, K60_IPA_IRQ, K60_GSI_IRQ);
    return K60IpaNotReady;
}
