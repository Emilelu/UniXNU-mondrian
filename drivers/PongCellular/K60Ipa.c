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
#include <string.h>
#else
#include <sys/systm.h>
#endif

#define K60_IPA_METADATA_BYTES 0x2000u

static int
k60_ipa_blob_read(void *context, uint64_t offset, void *to, size_t length)
{
    const uint8_t *blob = context;

    memcpy(to, blob + offset, length);
    return 0;
}

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
k60_ipa_firmware_check(const void *blob, uint64_t size, K60IpaFirmwarePlan *plan)
{
    K60MdtImage image;
    uint32_t load = 0;
    int rc;

    if (!blob || !plan) {
        return K60IpaBadArgument;
    }
    rc = k60_mdt_parse(&image, size, k60_ipa_blob_read, (void *)blob);
    if (rc != K60MdtOk) {
        return K60IpaFirmwareBadImage;
    }
    for (uint32_t i = 0; i < image.count; i++) {
        if (image.segment[i].load) {
            load++;
        }
    }
    plan->span = k60_mdt_span(&image);
    plan->metadata = k60_mdt_metadata_size(&image);
    plan->load_segments = load;
    plan->relocatable = image.relocatable;
    if (image.elf64 || !image.relocatable || image.min_address != 0 ||
        plan->span > K60_IPA_FW_REGION_BYTES ||
        plan->metadata > K60_IPA_METADATA_BYTES) {
        return K60IpaFirmwareLayout;
    }
    return K60IpaOk;
}

int
k60_ipa_probe(void)
{
    printf("K60IPA M0 skeleton: cfg=0x%x gsi=0x%x irq=%u/%u state=not-ready\n",
        K60_IPA_CFG_BASE, K60_GSI_BASE, K60_IPA_IRQ, K60_GSI_IRQ);
    return K60IpaNotReady;
}
