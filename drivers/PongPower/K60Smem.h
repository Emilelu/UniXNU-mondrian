/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/* Adapted from pong-power c37179ed QcomSmem.h/c. Hardware mutex ownership is
 * required for discovery; this battery transport never allocates/reset items. */
#ifndef K60_SMEM_H
#define K60_SMEM_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

typedef struct { volatile uint8_t *base; uint32_t size; } K60Smem;
typedef struct { uint32_t offset, size, cacheline; uint16_t host0, host1; } K60SmemPartition;
enum { K60SmemOk = 0, K60SmemNoTable = -1, K60SmemNoPartition = -2,
       K60SmemBadPartition = -3, K60SmemCorrupt = -4, K60SmemMissing = -5 };
int k60_smem_partition(const K60Smem *, uint16_t, uint16_t, K60SmemPartition *);
int k60_smem_find(const K60Smem *, const K60SmemPartition *, uint16_t, uint32_t *, uint32_t *);
#ifdef __cplusplus
}
#endif
#endif
