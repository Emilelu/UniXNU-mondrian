/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/* Builds the 104-byte k60-adsp-glink-handoff lease from SMEM allocations.
 * Layout and validation rules: docs/research/battery/GLINK-HANDOFF.md.
 * This produces the lease only; the ADSP PAS1 owner must still be running. */
#ifndef K60_HANDOFF_BUILD_H
#define K60_HANDOFF_BUILD_H
#include <stdint.h>
#include "K60Smem.h"
#ifdef __cplusplus
extern "C" {
#endif

#define K60_HANDOFF_BYTES 104u
/* K6BH little endian: identical to K60_ADSP_HANDOFF_MAGIC in
 * K60BatteryConfig.h, because that validator is the only consumer. */
#define K60_HANDOFF_MAGIC 0x4842364bu
#define K60_HANDOFF_VERSION 1u

typedef struct {
    uint32_t required;          /* flags: K60AdspHandoffRequired bits */
    uint32_t epoch;             /* must be non-zero */
    uint64_t smem_base;
    uint32_t smem_bytes;
    uint64_t adsp_base;
    uint32_t adsp_bytes;
    uint16_t desc_item, tx_item, rx_item, smp2p_item;
    uint16_t remote_pid;
    uint32_t desc_bytes, tx_bytes, rx_bytes, smp2p_bytes;
    uint32_t host_tx_head, host_rx_tail, remote_restart_flag;
} K60HandoffPlan;

/* Allocates the four items and writes the lease into out[0..103].
 * Returns 0, or a negative K60Smem error, or -8 for an invalid plan. */
int k60_handoff_build(const K60Smem *, const K60SmemPartition *, const K60HandoffPlan *, uint8_t out[K60_HANDOFF_BYTES]);

#ifdef __cplusplus
}
#endif
#endif
