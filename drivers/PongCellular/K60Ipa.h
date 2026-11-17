/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* K60 IPA data path: constants, firmware validation and M1 staging.
 *
 * The live DT describes the IPA wrapper at 0x3e00000 with a 2 MiB
 * qcom,entire-ipa-block-size. The IPA register block is the wrapper plus
 * qcom,ipa-cfg-offset 0x140000, and the GSI has its own view at 0x3e04000.
 * M0 records those facts without touching a register. M1 adds offline image
 * validation, a staging routine for the 64 KiB ipa_fw_region, the PAS 15
 * load, and a handoff probe that reads IPA/ipa_fws.mbn from the payload FAT.
 *
 * Sources: docs/research/cellular/20-IPA-V51-DATA-PATH.md sections 2 and 4,
 *          docs/research/cellular/02-DT-TRUTH.md, dataipa ipa5.0/ipa_hwio.h.
 */

#ifndef K60_IPA_H
#define K60_IPA_H

#include <stddef.h>
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
#define K60_IPA_METADATA_OFFSET       0x0000e000u
#define K60_IPA_METADATA_BYTES        0x00002000u
#define K60_IPA_METADATA_BASE         (K60_IPA_FW_REGION_BASE + K60_IPA_METADATA_OFFSET)
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
    K60IpaFirmwareTooLarge = -5,
    K60IpaMapFailed = -6,
    K60IpaPasDenied = -7,
    K60IpaClockFailed = -8,
    K60IpaGsiBusy = -9,
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

/* M1 staging: copies a validated monolithic ipa_fws image into the caller's
 * firmware region and writes its metadata blob into the caller's metadata
 * buffer. Pure memory movement, so the host tests exercise the same code as
 * the kernel. Both buffers must be writable and sized from the passed sizes;
 * the region is zeroed before the segments are placed. */
int k60_ipa_firmware_stage(const void *blob, uint64_t size, void *region,
    uint64_t region_size, void *metadata, uint64_t metadata_size,
    K60IpaFirmwarePlan *plan);

/* M1 resource prerequisites: applies the native IPA5.1 QMB/timer and
 * source/destination resource tables to a mapped IPA register block. The
 * function only touches memory supplied by the caller, so the host test uses
 * the same code as the kernel. It refuses a zero or all-ones version. */
int k60_ipa_resources_prepare(void *registers, size_t bytes);

/* M1 load: stages the image into the live IPA firmware carveout and hands it
 * to PAS 15 (INIT_IMAGE, MEM_SETUP, AUTH_AND_RESET). It refuses a GSI EE0
 * already enabled by another owner and reports channels/events afterwards.
 * This maps MMIO and makes SMC calls; it is not built in the host tests. */
int k60_ipa_firmware_start(const void *blob, uint64_t size);

/* M0 probe: reports that the data path is intentionally absent.  It must not
 * map MMIO, write a register or call PAS; those begin in M1. */
int k60_ipa_probe(void);

/* M1 caller: reads IPA/ipa_fws.mbn from the payload FAT (md0) when the
 * pong_ipa boot argument is non-zero, then stages it and runs PAS 15. */
int k60_ipa_probe_from_handoff(void);

/* memdev calls this for md0; base and size are page numbers, matching
 * k60_adsp_note_window. */
void k60_ipa_note_window(uint64_t base, uint64_t size);

extern const char k60_ipa_marker[];

#endif /* K60_IPA_H */
