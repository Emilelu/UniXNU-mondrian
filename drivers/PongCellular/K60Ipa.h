/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* K60 IPA data path: constant definitions and the M0 compile-time skeleton.
 *
 * The live DT describes the IPA wrapper at 0x3e00000 with a 2 MiB
 * qcom,entire-ipa-block-size. The IPA register block is the wrapper plus
 * qcom,ipa-cfg-offset 0x140000, and the GSI has its own view at 0x3e04000.
 * This header records those facts without touching a register; M0 only
 * proves the kernel can carry the definitions and the probe symbol.
 *
 * Sources: docs/research/cellular/20-IPA-V51-DATA-PATH.md sections 2 and 4,
 *          docs/research/cellular/02-DT-TRUTH.md, dataipa ipa5.0/ipa_hwio.h.
 */

#ifndef K60_IPA_H
#define K60_IPA_H

#include <stdint.h>

#include "K60Mdt.h"

#define K60_IPA_WRAPPER_BASE          0x03e00000u
#define K60_IPA_BLOCK_BYTES           0x00200000u
#define K60_IPA_CFG_OFFSET            0x00140000u
#define K60_IPA_CFG_BASE              (K60_IPA_WRAPPER_BASE + K60_IPA_CFG_OFFSET)
#define K60_IPA_CFG_BYTES             0x00084000u
#define K60_GSI_BASE                  0x03e04000u
#define K60_GSI_BYTES                 0x000fc000u
#define K60_IPA_COMP_HW_VERSION_REG   0x00000024u
#define K60_IPA_VERSION_REG           0x00000028u
#define K60_IPA_COMP_HW_VERSION_ADDR  (K60_IPA_CFG_BASE + K60_IPA_COMP_HW_VERSION_REG)
#define K60_IPA_VERSION_ADDR          (K60_IPA_CFG_BASE + K60_IPA_VERSION_REG)
#define K60_IPA_IRQ                   654u
#define K60_GSI_IRQ                   432u
#define K60_IPA_PAS_ID                15u
#define K60_IPA_FW_NAME               "ipa_fws"
#define K60_IPA_FW_REGION_BASE        0x8b900000u
#define K60_IPA_FW_REGION_BYTES       0x00010000u
#define K60_IPA_GSI_REGION_BASE       0x8b910000u
#define K60_IPA_GSI_REGION_BYTES      0x0000a000u
#define K60_GSI_CH_DOORBELL_BASE      0x03e28000u
#define K60_GSI_EV_DOORBELL_BASE      0x03e28800u
#define K60_GSI_STATUS                0x03e29000u

enum {
    K60IpaOk = 0,
    K60IpaNotReady = -1,
    K60IpaBadArgument = -2,
    K60IpaFirmwareBadImage = -3,
    K60IpaFirmwareLayout = -4,
};

typedef struct {
    uint32_t raw;
    uint32_t major;
    uint32_t minor;
    uint32_t step;
} K60IpaVersion;

/* Decode IPA_COMP_HW_VERSION: major[31:28], minor[23:16], step[15:0]. */
K60IpaVersion k60_ipa_decode_comp_hw_version(uint32_t raw);

/* Offline check of an ipa_fws image against the K60 carveout layout. It parses
 * the ELF headers and reports the span and metadata size without mapping or
 * allocating anything; M1 uses the same parse before the PAS calls. */
typedef struct {
    uint64_t span;
    uint64_t metadata;
    uint32_t load_segments;
    uint32_t relocatable;
} K60IpaFirmwarePlan;

int k60_ipa_firmware_check(const void *blob, uint64_t size, K60IpaFirmwarePlan *plan);

/* M0 probe: reports that the data path is intentionally absent.  It must not
 * map MMIO, write a register or call PAS; those begin in M1. */
int k60_ipa_probe(void);

extern const char k60_ipa_marker[];

#endif /* K60_IPA_H */
