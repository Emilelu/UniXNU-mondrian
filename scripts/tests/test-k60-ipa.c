/* Host test for the K60 IPA M0 skeleton: constants, version decode, inert probe. */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "K60Ipa.h"

_Static_assert(K60_IPA_CFG_BASE == 0x03f40000u, "cfg base");
_Static_assert(K60_GSI_BASE == 0x03e04000u, "gsi base");
_Static_assert(K60_IPA_VERSION_ADDR == 0x03f40028u, "version register");
_Static_assert(K60_IPA_IRQ == 654u, "ipa irq");
_Static_assert(K60_GSI_IRQ == 432u, "gsi irq");

static int
test_blob_read(void *context, uint64_t offset, void *to, size_t length)
{
    memcpy(to, (const uint8_t *)context + offset, length);
    return 0;
}

int
main(int argc, char **argv)
{
    const K60IpaVersion v = k60_ipa_decode_comp_hw_version(0x51000002u);
    K60IpaFirmwarePlan plan;

    if (v.major != 5u || v.minor != 0x100u || v.step != 2u) {
        printf("FAIL version decode %u.%u.%u\n", v.major, v.minor, v.step);
        return 1;
    }
    if (k60_ipa_probe() != K60IpaNotReady) {
        printf("FAIL M0 probe must stay inert\n");
        return 1;
    }
    if (k60_ipa_marker[0] == '\0') {
        printf("FAIL marker missing\n");
        return 1;
    }
    printf("K60 IPA M0 PASS version=%u.%u.%u cfg=%#x gsi=%#x\n",
        v.major, v.minor, v.step, K60_IPA_CFG_BASE, K60_GSI_BASE);
    {
        unsigned char regs[0x1000];

        memset(regs, 0, sizeof(regs));
        if (k60_ipa_resources_prepare(NULL, 0) != K60IpaBadArgument) {
            printf("FAIL resource short buffer\n");
            return 1;
        }
        if (k60_ipa_resources_prepare(regs, sizeof(regs)) != K60IpaNotReady) {
            printf("FAIL resource zero version\n");
            return 1;
        }
        *(volatile uint32_t *)(regs + 0x28) = 0x51000002u;
        *(volatile uint32_t *)(regs + 0x2c) = 0x100u;
        *(volatile uint32_t *)(regs + 0x54) = 0x1234u;
        *(volatile uint32_t *)(regs + 0x58) = 0xabcd1234u;
        *(volatile uint32_t *)(regs + 0x4b0) = 0x80000000u;
        *(volatile uint32_t *)(regs + 0x6a0) = 0xffffffffu;
        *(volatile uint32_t *)(regs + 0x6a4) = 0xffffffffu;
        if (k60_ipa_resources_prepare(regs, sizeof(regs)) != K60IpaOk) {
            printf("FAIL resource prepare\n");
            return 1;
        }
        if (*(volatile uint32_t *)(regs + 0x2c) != 0x180u ||
            *(volatile uint32_t *)(regs + 0x54) != 0x1200u ||
            *(volatile uint32_t *)(regs + 0x58) != 0x1200u ||
            *(volatile uint32_t *)(regs + 0x4ac) != 0x180e8eu ||
            *(volatile uint32_t *)(regs + 0x4b4) != 0xb63u ||
            (*(volatile uint32_t *)(regs + 0x4b0) & 0x80000000u) == 0 ||
            *(volatile uint32_t *)(regs + 0x6a0) != 0xc0e00ecfu ||
            *(volatile uint32_t *)(regs + 0x6a4) != 0xffffff9fu) {
            printf("FAIL resource register values\n");
            return 1;
        }
        printf("K60 IPA RES PASS\n");
    }
    if (argc > 1) {
        FILE *f = fopen(argv[1], "rb");
        long size;
        unsigned char *blob;
        if (!f) {
            printf("FAIL open %s\n", argv[1]);
            return 1;
        }
        fseek(f, 0, SEEK_END);
        size = ftell(f);
        fseek(f, 0, SEEK_SET);
        blob = malloc((size_t)size);
        if (!blob || fread(blob, 1, (size_t)size, f) != (size_t)size) {
            printf("FAIL read %s\n", argv[1]);
            return 1;
        }
        fclose(f);
        if (k60_ipa_firmware_check(blob, (uint64_t)size, &plan) != K60IpaOk) {
            printf("FAIL firmware check %s\n", argv[1]);
            return 1;
        }
        printf("K60 IPA FW PASS size=%ld span=%#llx metadata=%#llx loads=%u reloc=%u\n",
            size, (unsigned long long)plan.span, (unsigned long long)plan.metadata,
            plan.load_segments, plan.relocatable);
        {
            K60MdtImage image;
            K60IpaFirmwarePlan staged;
            unsigned char *region = calloc(1, K60_IPA_FW_REGION_BYTES);
            unsigned char *metadata = calloc(1, K60_IPA_METADATA_BYTES);
            if (!region || !metadata) {
                printf("FAIL alloc\n");
                return 1;
            }
            if (k60_mdt_parse(&image, (uint64_t)size, test_blob_read, blob) != K60MdtOk) {
                printf("FAIL mdt parse\n");
                return 1;
            }
            if (k60_ipa_firmware_stage(blob, (uint64_t)size, region,
                    K60_IPA_FW_REGION_BYTES, metadata, K60_IPA_METADATA_BYTES,
                    &staged) != K60IpaOk) {
                printf("FAIL stage\n");
                return 1;
            }
            if (staged.span != plan.span || staged.metadata != plan.metadata ||
                staged.load_segments != plan.load_segments) {
                printf("FAIL staged plan mismatch\n");
                return 1;
            }
            if (metadata[0] != 0x7f || metadata[1] != 'E' ||
                metadata[2] != 'L' || metadata[3] != 'F') {
                printf("FAIL metadata ELF magic\n");
                return 1;
            }
            for (uint32_t i = 0; i < image.count; i++) {
                uint64_t offset;
                if (!image.segment[i].load || image.segment[i].file_size == 0) {
                    continue;
                }
                if (k60_mdt_place(&image, i, K60_IPA_FW_REGION_BASE,
                        K60_IPA_FW_REGION_BYTES, &offset) != K60MdtOk ||
                    memcmp(region + offset, blob + image.segment[i].file_offset,
                        (size_t)image.segment[i].file_size) != 0) {
                    printf("FAIL segment %u placement\n", i);
                    return 1;
                }
            }
            if (k60_ipa_firmware_stage(blob, (uint64_t)size, region,
                    plan.span - 1, metadata, K60_IPA_METADATA_BYTES, NULL) !=
                K60IpaFirmwareTooLarge) {
                printf("FAIL short region accepted\n");
                return 1;
            }
            if (k60_ipa_firmware_stage(blob, (uint64_t)size, region,
                    K60_IPA_FW_REGION_BYTES, metadata, plan.metadata - 1, NULL) !=
                K60IpaFirmwareTooLarge) {
                printf("FAIL short metadata accepted\n");
                return 1;
            }
            printf("K60 IPA STAGE PASS span=%#llx metadata=%#llx loads=%u\n",
                (unsigned long long)staged.span,
                (unsigned long long)staged.metadata, staged.load_segments);
            free(region);
            free(metadata);
        }
        free(blob);
    }
    return 0;
}
