/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* K60 IPA data path M0 skeleton plus M1 firmware staging.
 *
 * M0 carries the register-map constants and the version decoder so later
 * stages cannot invent a different base address. M1 validates a monolithic
 * ipa_fws image, clears the 64 KiB ipa_fw_region, copies its load segments to
 * their p_paddr offsets and builds the metadata block at the last 8 KiB.
 * Nothing maps the IPA or GSI registers and no PAS call is made here; the
 * caller owns the PAS 15 transitions and the GSI reset.
 */

#include "K60Ipa.h"
#include "K60ModemPas.h"

#ifdef K60_HOST_TEST
#include <stdio.h>
#include <string.h>
#else
#include <pexpert/pexpert.h>
#include <sys/systm.h>

/* osfmk/arm/machine_routines.h:703; declared here keeps the include path out
 * of the leaky kernel header set (same choice as K60ModemBoot.c). */
extern vm_offset_t ml_io_map_unmappable(vm_offset_t phys, vm_size_t size,
    uint32_t flags);
#endif

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
_Static_assert(K60_IPA_METADATA_BASE + K60_IPA_METADATA_BYTES ==
    K60_IPA_FW_REGION_BASE + K60_IPA_FW_REGION_BYTES,
    "IPA metadata must be the last 8 KiB of the 64 KiB firmware region");

const char k60_ipa_marker[] = "K60IPA M1 staging linked";

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
k60_ipa_firmware_stage(const void *blob, uint64_t size, void *region,
    uint64_t region_size, void *metadata, uint64_t metadata_size,
    K60IpaFirmwarePlan *plan)
{
    K60MdtImage image;
    K60IpaFirmwarePlan local;
    int rc;

    if (!blob || !region || !metadata) {
        return K60IpaBadArgument;
    }
    rc = k60_ipa_firmware_check(blob, size, &local);
    if (rc != K60IpaOk) {
        return rc;
    }
    if (region_size < local.span) {
        return K60IpaFirmwareTooLarge;
    }
    if (metadata_size < local.metadata) {
        return K60IpaFirmwareTooLarge;
    }
    rc = k60_mdt_parse(&image, size, k60_ipa_blob_read, (void *)blob);
    if (rc != K60MdtOk) {
        return K60IpaFirmwareBadImage;
    }
    memset(region, 0, (size_t)region_size);
    for (uint32_t i = 0; i < image.count; i++) {
        const K60MdtSegment *s = &image.segment[i];
        uint64_t offset;

        if (!s->load) {
            continue;
        }
        rc = k60_mdt_place(&image, i, K60_IPA_FW_REGION_BASE, region_size,
            &offset);
        if (rc != K60MdtOk) {
            return K60IpaFirmwareLayout;
        }
        memcpy((uint8_t *)region + offset,
            (const uint8_t *)blob + s->file_offset, (size_t)s->file_size);
        if (s->memory_size > s->file_size) {
            memset((uint8_t *)region + offset + s->file_size, 0,
                (size_t)(s->memory_size - s->file_size));
        }
    }
    rc = k60_mdt_metadata(&image, k60_ipa_blob_read, (void *)blob,
        metadata, metadata_size);
    if (rc != K60MdtOk) {
        return K60IpaFirmwareLayout;
    }
    if (plan) {
        *plan = local;
    }
    return K60IpaOk;
}

#ifndef K60_HOST_TEST
static int
k60_ipa_scm_call(uint32_t fn, uint32_t arginfo, uint64_t a, uint64_t b,
    uint64_t c, uint64_t *rx0, uint64_t *rx1)
{
    register uint64_t x0 __asm__("x0") = fn;
    register uint64_t x1 __asm__("x1") = arginfo;
    register uint64_t x2 __asm__("x2") = a;
    register uint64_t x3 __asm__("x3") = b;
    register uint64_t x4 __asm__("x4") = c;
    register uint64_t x5 __asm__("x5") = 0;
    register uint64_t x6 __asm__("x6") = 0;
    register uint64_t x7 __asm__("x7") = 0;

    __asm__ volatile("smc #0"
        : "+r"(x0), "+r"(x1), "+r"(x2), "+r"(x3)
        : "r"(x4), "r"(x5), "r"(x6), "r"(x7)
        : "memory");

    *rx0 = x0;
    *rx1 = x1;
    return k60_modem_scm_ok(x0, x1) ? K60IpaOk : K60IpaPasDenied;
}

static int
k60_ipa_pas_call(uint32_t cmd, uint32_t arginfo, uint64_t a, uint64_t b,
    uint64_t c)
{
    uint64_t x0 = 0, x1 = 0;
    int rc = k60_ipa_scm_call(k60_modem_scm_fn(K60M_SCM_SVC_PIL, cmd),
        arginfo, a, b, c, &x0, &x1);

    if (rc != K60IpaOk) {
        printf("K60IPA scm cmd=%#x rc=%d x0=%#llx x1=%#llx\n", cmd, rc,
            (unsigned long long)x0, (unsigned long long)x1);
    }
    return rc;
}

int
k60_ipa_firmware_start(const void *blob, uint64_t size)
{
    K60IpaFirmwarePlan plan;
    vm_offset_t firmware, metadata;
    int rc;

    if (!blob) {
        return K60IpaBadArgument;
    }
    rc = k60_ipa_firmware_check(blob, size, &plan);
    if (rc != K60IpaOk) {
        printf("K60IPA firmware check failed rc=%d size=%llu\n", rc,
            (unsigned long long)size);
        return rc;
    }
    printf("K60IPA firmware plan span=%#llx metadata=%#llx loads=%u\n",
        (unsigned long long)plan.span, (unsigned long long)plan.metadata,
        plan.load_segments);
    /* Both IPA regions are DDR carveouts, not device memory: use the same
     * VM_WIMG_DEFAULT flag K60ModemBoot and K60AdspBoot use. */
    firmware = ml_io_map_unmappable((vm_offset_t)K60_IPA_FW_REGION_BASE,
        (vm_size_t)K60_IPA_FW_REGION_BYTES, 0x2);
    if (firmware == 0) {
        printf("K60IPA cannot map firmware region %#x\n",
            K60_IPA_FW_REGION_BASE);
        return K60IpaMapFailed;
    }
    metadata = ml_io_map_unmappable((vm_offset_t)K60_IPA_METADATA_BASE,
        (vm_size_t)K60_IPA_METADATA_BYTES, 0x2);
    if (metadata == 0) {
        printf("K60IPA cannot map metadata region %#x\n",
            K60_IPA_METADATA_BASE);
        return K60IpaMapFailed;
    }
    rc = k60_ipa_firmware_stage(blob, size, (void *)firmware,
        K60_IPA_FW_REGION_BYTES, (void *)metadata, K60_IPA_METADATA_BYTES,
        &plan);
    if (rc != K60IpaOk) {
        printf("K60IPA firmware stage failed rc=%d\n", rc);
        return rc;
    }
    printf("K60IPA firmware staged at %#x metadata=%#x\n",
        K60_IPA_FW_REGION_BASE, K60_IPA_METADATA_BASE);
    rc = k60_ipa_pas_call(K60M_SCM_PAS_INIT_IMAGE,
        k60_modem_scm_args(2, K60M_SCM_VAL, K60M_SCM_RW, 0),
        K60_IPA_PAS_ID, K60_IPA_METADATA_BASE, 0);
    if (rc != K60IpaOk) {
        printf("K60IPA init_image failed rc=%d\n", rc);
        return rc;
    }
    printf("K60IPA init_image ok\n");
    rc = k60_ipa_pas_call(K60M_SCM_PAS_MEM_SETUP,
        k60_modem_scm_args(3, 0, 0, 0), K60_IPA_PAS_ID,
        K60_IPA_FW_REGION_BASE, plan.span);
    if (rc != K60IpaOk) {
        printf("K60IPA mem_setup failed rc=%d\n", rc);
        return rc;
    }
    printf("K60IPA mem_setup ok base=%#x span=%#llx\n",
        K60_IPA_FW_REGION_BASE, (unsigned long long)plan.span);
    rc = k60_ipa_pas_call(K60M_SCM_PAS_AUTH_AND_RESET,
        k60_modem_scm_args(1, 0, 0, 0), K60_IPA_PAS_ID, 0, 0);
    if (rc != K60IpaOk) {
        printf("K60IPA auth_and_reset failed rc=%d\n", rc);
        return rc;
    }
    printf("K60IPA auth_and_reset ok\n");
    {
        volatile uint8_t *cfg = (volatile uint8_t *)(uintptr_t)
            ml_io_map_unmappable((vm_offset_t)K60_IPA_CFG_BASE, 0x1000, 0x7);
        uint32_t version, comp;

        if (cfg == NULL) {
            printf("K60IPA cannot map cfg page %#x\n", K60_IPA_CFG_BASE);
            return K60IpaMapFailed;
        }
        version = *(volatile uint32_t *)(cfg + K60_IPA_VERSION_REG);
        comp = *(volatile uint32_t *)(cfg + K60_IPA_COMP_HW_VERSION_REG);
        printf("K60IPA version=%#x comp=%#x\n", version, comp);
        if (version == 0 || version == 0xffffffffu) {
            printf("K60IPA IPAREADY not set\n");
            return K60IpaNotReady;
        }
    }
    return K60IpaOk;
}
#else /* K60_HOST_TEST */
int
k60_ipa_firmware_start(const void *blob, uint64_t size)
{
    (void)blob;
    (void)size;
    return K60IpaNotReady;
}
#endif /* K60_HOST_TEST */

int
k60_ipa_probe(void)
{
    printf("K60IPA probe: cfg=0x%x gsi=0x%x irq=%u/%u state=not-ready\n",
        K60_IPA_CFG_BASE, K60_GSI_BASE, K60_IPA_IRQ, K60_GSI_IRQ);
    return K60IpaNotReady;
}
