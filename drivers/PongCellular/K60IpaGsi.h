/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* K60 IPA GSI 3.0 command DMA owner (M2, host-testable).
 *
 * This is the C port of the Pong baseband PongModemIpaDma.h command-DMA
 * owner (BSD-2-Clause-Patent). It keeps the Pong GSI3.0 register offsets and
 * the Pong sequence: EE0 event ownership, event0/command12 allocation, event
 * and command ring context programming, IPA endpoint 14 DMA mode, and the
 * IPA5.1 header/context/filter/route table commands.
 *
 * M2 scope and integration boundaries:
 *  - All MMIO goes through K60IpaGsiCallbacks. The host test supplies byte
 *    arrays; the kernel supplies ml_io_map_unmappable() views of the GSI
 *    window (0x3e04000, 0xfc000 bytes) and the IPA register block
 *    (0x3f40000, 0x20000 bytes).
 *  - The caller owns both DMA blocks: a 1 MiB ring block and a 0x8000 table
 *    block, both physically contiguous. In the kernel they come from
 *    kmem_alloc_contig(); the ring must be 64 KiB aligned and the tables page
 *    aligned. They stay owned until k60_ipa_gsi_stop().
 *  - The SMMU context for those blocks is not programmed here. The caller
 *    must establish the SID 0x5c0 mapping (K60IpaSmmu in the kernel) and pass
 *    the resulting IOVAs. The 0x8000 table block is reserved for that
 *    builder and is only zeroed by this module.
 *  - Completion is polled from the event shadow at ring+0x18000. GSI IRQ 432
 *    is neither installed nor acknowledged here; a later kernel glue layer
 *    may use it to call k60_ipa_gsi_poll() sooner. Without that glue the
 *    command path remains polled, matching Pong's conservative owner.
 *  - No dynamic allocation and no C++: every buffer is caller supplied, so
 *    the same code runs in the host test and in the kernel.
 */

#ifndef K60_IPA_GSI_H
#define K60_IPA_GSI_H

#include <stddef.h>
#include <stdint.h>

#include "K60Ipa.h"

#ifdef __cplusplus
extern "C" {
#endif

#define K60_IPA_GSI_RING_BYTES          0x00100000u
#define K60_IPA_GSI_TABLE_BYTES         0x00008000u
#define K60_IPA_GSI_RING_ALIGN          0x00010000u
#define K60_IPA_GSI_PAGE_SIZE           0x00001000u
#define K60_IPA_GSI_TRE_BYTES           16u
#define K60_IPA_GSI_TRE_COUNT           256u
#define K60_IPA_GSI_EVENT_OFFSET        0x00010000u
#define K60_IPA_GSI_EVENT_BYTES         0x00001000u
#define K60_IPA_GSI_EVENT_SHADOW_OFFSET 0x00018000u
#define K60_IPA_GSI_PAYLOAD_OFFSET      0x00020000u
#define K60_IPA_GSI_PAYLOAD_BYTES       32u
#define K60_IPA_GSI_HEADER_OFFSET       0x00030000u
#define K60_IPA_GSI_HEADER_BYTES        0x00010000u
#define K60_IPA_GSI_TABLE_OFFSET        0x00040000u
#define K60_IPA_GSI_TABLE_BLOCK_BYTES   0x00001000u
#define K60_IPA_GSI_ENDPOINT            14u
#define K60_IPA_GSI_ENDPOINT_OFFSET     (0x1000u + K60_IPA_GSI_ENDPOINT * 0x80u)
#define K60_IPA_GSI_MAX_BATCH           8u
#define K60_IPA_GSI_MAX_PAYLOAD         24u

/* Extra negative status codes used below; the API also returns K60IpaOk,
 * K60IpaBadArgument, K60IpaNotReady and K60IpaGsiBusy from K60Ipa.h. */
enum {
    K60IpaGsiNoDevice = -10,
    K60IpaGsiNoMemory = -11,
    K60IpaGsiInvalid = -12,
    K60IpaGsiIoError = -13,
    K60IpaGsiTimeout = -14,
};

typedef uint32_t (*K60IpaGsiRead32)(void *cookie, uint32_t offset);
typedef void (*K60IpaGsiWrite32)(void *cookie, uint32_t offset, uint32_t value);
typedef void (*K60IpaGsiDelayUs)(void *cookie, uint32_t microseconds);
typedef uint64_t (*K60IpaGsiNowMs)(void *cookie);

enum {
    K60IpaGsiSyncClean = 1,
    K60IpaGsiSyncInvalidate = 2,
};

/* Optional cache maintenance hook. "clean" publishes CPU-written ring,
 * payload and table bytes to the device; "invalidate" makes device-written
 * event pages visible to the CPU. NULL is allowed for coherent host tests. */
typedef void (*K60IpaGsiSync)(void *cookie, const void *address, size_t bytes,
    int direction);

typedef struct {
    K60IpaGsiRead32 read_gsi;
    K60IpaGsiWrite32 write_gsi;
    K60IpaGsiRead32 read_reg;
    K60IpaGsiWrite32 write_reg;
    K60IpaGsiDelayUs delay_us;
    K60IpaGsiNowMs now_ms;
    K60IpaGsiSync sync;
    void *cookie;
} K60IpaGsiCallbacks;

typedef struct {
    K60IpaGsiCallbacks callbacks;
    uint8_t *ring;          /* 1 MiB contiguous DMA block, CPU view */
    size_t ring_size;
    uint64_t ring_iova;     /* SID 0x5c0 IOVA of ring, 64 KiB aligned */
    uint8_t *tables;        /* 0x8000 SMMU table block, CPU view */
    size_t tables_size;
    uint64_t tables_iova;
    uint32_t gsi_bytes;     /* size of the GSI window reachable by callbacks */
} K60IpaGsiConfig;

typedef struct {
    K60IpaGsiConfig config;
    K60IpaGsiCaps caps;
    uint32_t stage;
    uint32_t channels;
    uint32_t events;
    uint32_t channel_state;
    uint32_t event_state;
    uint32_t restricted;
    uint32_t sram_bytes;
    uint32_t producer;
    uint32_t event_read;
    uint32_t last_tre;
    uint32_t last_event;
    uint32_t completed_commands;
    uint32_t failure_regs[8];
    uint64_t deadline_ms;
    int error;
    int pending;
    int initialized;
} K60IpaGsi;

/* Bind a caller-owned context to its callbacks and DMA blocks. This clears
 * the 1 MiB ring and 0x8000 tables. It performs no MMIO. */
int k60_ipa_gsi_init(K60IpaGsi *gsi, const K60IpaGsiConfig *config);

/* Post-firmware capability check through the same callbacks. Unlike the
 * pre-PAS k60_ipa_gsi_check() in K60Ipa.c, this expects EE0 to be enabled:
 * status must not be all-ones, bit 0 must be set, there must be more than
 * the command channel and at least one event, and command12/event0 must be
 * unowned. */
int k60_ipa_gsi_check_caps(K60IpaGsi *gsi, K60IpaGsiCaps *caps);

/* Start EE0 ownership, event0 and command channel 12, program both ring
 * contexts and IPA endpoint 14, then submit the first HDR_INIT_LOCAL command.
 * Returns with stage 5 and one command pending; drive k60_ipa_gsi_poll(). */
int k60_ipa_gsi_start(K60IpaGsi *gsi);

/* Advance the staged IPA5.1 initialization and complete pending commands.
 * Returns K60IpaOk when a step completed (or there was nothing to do),
 * K60IpaNotReady while a command is still outstanding, or a negative error. */
int k60_ipa_gsi_poll(K60IpaGsi *gsi);

/* Submit one immediate command through command channel 12 (1..24 payload
 * bytes; the slot itself is 32 bytes). Only one batch may be outstanding. */
int k60_ipa_gsi_submit(K60IpaGsi *gsi, uint32_t opcode, const void *payload,
    size_t payload_bytes);

/* Reset command channel 12 if it was started and clear the local software
 * state. Caller memory and its SMMU mapping remain owned by the caller. */
int k60_ipa_gsi_stop(K60IpaGsi *gsi);

#ifdef __cplusplus
}
#endif

#endif /* K60_IPA_GSI_H */
