/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* K60 IPA data path: constants, firmware validation and M1 staging.
 *
 * The live DT describes the IPA wrapper at 0x3e00000 with a 2 MiB
 * qcom,entire-ipa-block-size. The IPA register block is the wrapper plus
 * qcom,ipa-cfg-offset 0x140000, and the GSI has its own view at 0x3e04000.
 * M0 records those facts without touching a register. M1 adds offline image
 * validation, a staging routine for the 40 KiB ipa_gsi_region that carries the
 * image, the PAS 15 load, and a handoff probe that consumes the IPA firmware
 * copied by UEFI into the reserved ipa_fw_region at 0x8b900000.
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
/* The live DT names ipa_gsi_region in the IPA node's memory-regions
 * property; Android's PIL loads ipa_fws there, not into the region whose name
 * says firmware. The 64 KiB ipa_fw_region is used only as a metadata lease at
 * its last 8 KiB, disjoint from the image. */
#define K60_IPA_FW_REGION_BASE        0x8b900000u
#define K60_IPA_FW_REGION_BYTES       0x00010000u
#define K60_IPA_METADATA_OFFSET       0x0000e000u
#define K60_IPA_METADATA_BYTES        0x00002000u
#define K60_IPA_METADATA_BASE         (K60_IPA_FW_REGION_BASE + K60_IPA_METADATA_OFFSET)
#define K60_IPA_GSI_REGION_BASE       0x8b910000u
#define K60_IPA_GSI_REGION_BYTES      0x0000a000u
#define K60_IPA_FIRMWARE_BASE         K60_IPA_GSI_REGION_BASE
#define K60_IPA_FIRMWARE_BYTES        K60_IPA_GSI_REGION_BYTES
#define K60_GSI_CH_DOORBELL_BASE      0x03e28000u
#define K60_GSI_EV_DOORBELL_BASE      0x03e28800u
#define K60_GSI_STATUS                0x03e29000u
#define K60_GSI_STATUS_OFFSET         0x00025000u
#define K60_GSI_CHANNELS_OFFSET       0x00025040u
#define K60_GSI_EVENTS_OFFSET         0x00025050u
#define K60_GSI_CHANNEL_BASE          0x00014000u
#define K60_GSI_CHANNEL_STRIDE        0x00000080u
#define K60_GSI_EVENT_BASE            0x0001c000u
#define K60_GSI_COMMAND_CHANNEL       12u
#define K60_GSI_EVENT0                0u

/* M2 runtime: Pong IPA5.1 command-DMA context (PongModemIpaDma.h). The
 * stream is SID 0x5c0 in the apps SMMU, the ring lives at IOVA 0x20000000,
 * and the shared filter/route region is SMEM item 497 (0x9000 bytes). */
#define K60_IPA_RUNTIME_SID           0x000005c0u
#define K60_IPA_RUNTIME_IOVA          0x20000000u
#define K60_IPA_SMMU_BASE             0x15000000u
#define K60_IPA_SMMU_BYTES            0x00100000u
#define K60_IPA_SMEM_BASE             0x80900000u
#define K60_IPA_SMEM_BYTES            0x00200000u
#define K60_IPA_SMEM_ITEM             497u
#define K60_IPA_SMEM_MIN_BYTES        0x00009000u
/* TCSR SMEM mutex shared with the ADSP; allocation must hold it. */
#define K60_IPA_SMEM_MUTEX_BASE       0x1f43000u
#define K60_IPA_SMEM_MUTEX_BYTES      0x00001000u

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
    K60IpaSmmuFailed = -20,
    K60IpaRuntimeFailed = -21,
    K60IpaPasInterrupted = -22,
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

/* M2 precondition: reads the GSI capability and ownership registers in the
 * caller-provided view. It refuses an enabled EE0, too few channels or events,
 * and a command channel or event ring already owned by another manager. Pure
 * register reads, so the host test exercises the same code as the kernel. */
typedef struct {
    uint32_t status;
    uint32_t channels;
    uint32_t events;
    uint32_t command_state;
    uint32_t event_state;
} K60IpaGsiCaps;

int k60_ipa_gsi_check(void *gsi, size_t bytes, K60IpaGsiCaps *caps);

/* M1 load: stages the image into the live IPA firmware carveout and hands it
 * to PAS 15 (INIT_IMAGE, MEM_SETUP, AUTH_AND_RESET). It refuses a GSI EE0
 * already enabled by another owner and reports channels/events afterwards.
 * This maps MMIO and makes SMC calls; it is not built in the host tests. */
int k60_ipa_firmware_start(const void *blob, uint64_t size);

/* M0 probe: reports that the data path is intentionally absent.  It must not
 * map MMIO, write a register or call PAS; those begin in M1. */
int k60_ipa_probe(void);

/* M1 caller: maps ipa_fw_region at 0x8b900000 when the pong_ipa boot argument
 * is non-zero, then stages the UEFI-copied image and runs PAS 15. */
int k60_ipa_probe_from_handoff(void);

/* memdev calls this for md0; retained for compatibility, the firmware source
 * is the fixed UEFI window. */
void k60_ipa_note_window(uint64_t base, uint64_t size);

extern const char k60_ipa_marker[];

#endif /* K60_IPA_H */
