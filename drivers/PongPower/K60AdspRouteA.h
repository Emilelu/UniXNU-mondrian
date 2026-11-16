/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/* Route A: the early handoff resources callback performs the same two steps
 * that the working SM8475 reference (Zizhan) performs before PAS AUTH:
 * open the AOSS QMP channel and send "load_state on", then read the RPMh
 * command database and vote lcx/lmx through the applications RSC's TCS4.
 *
 * The callback is deliberately injected: this header has no board or kernel
 * dependency, so the host test can count every map, read and write. Physical
 * addresses and flags are constants of the K60 board, not discovered values.
 */
#ifndef K60_ADSP_ROUTE_A_H
#define K60_ADSP_ROUTE_A_H

#include <stddef.h>
#include <stdint.h>

#define K60_ROUTE_A_VERSION 1u
#define K60_ROUTE_A_AOSS_PHYS 0x0c300000ULL
#define K60_ROUTE_A_AOSS_BYTES 0x1000u
#define K60_ROUTE_A_IPCC_PHYS 0x0ed18000ULL
#define K60_ROUTE_A_IPCC_BYTES 0x1000u
#define K60_ROUTE_A_MAP_FLAGS 0x7u

typedef struct {
    uint32_t version, bytes;
    int (*map)(void *, uint64_t, size_t, unsigned, volatile uint8_t **);
    void (*unmap)(void *, volatile uint8_t *, size_t);
    /* Doorbell into the AOP's IPCC mailbox. The callback gets the mapped IPCC
     * window; production writes QCOM_IPCC_SEND, the host harness can answer the
     * simulated QMP handshake without any physical access. */
    void (*kick)(void *, volatile uint8_t *);
    /* Optional poll hook for a host harness; production passes NULL. */
    void (*tick)(void *);
    void *context;
} K60RouteAIo;

typedef struct {
    uint32_t qmp_open;
    uint32_t lcx_address, lmx_address;
    uint32_t lcx_index, lmx_index;
    uint32_t lcx_levels, lmx_levels;
} K60RouteAResult;

/* 0 when QMP is open, both rails were found and both TCS4 votes completed.
 * Negative otherwise; the caller must not treat a partial result as held. */
int k60_adsp_route_a_acquire(const K60RouteAIo *io, K60RouteAResult *out);

#endif /* K60_ADSP_ROUTE_A_H */
