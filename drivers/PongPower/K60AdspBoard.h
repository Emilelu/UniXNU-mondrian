/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/* K60 ADSP board ownership: the persistent facts, exclusion and SCM
 * serialization that the PAS1 provider cannot infer from a boot argument, the
 * startup CAS, a successful PAS SHUTDOWN, or a discovered RPMh address.
 *
 * The ten callbacks fill K60AdspPlatformOwnership (K60AdspPlatform.h:18-39).
 * What each one actually proves on this board, and what it deliberately does
 * not prove, is listed in docs/research/battery/PAS1-PROVIDER-INSTALL.md.
 *
 * Hardware boundary (docs/ops/HARD-RULES.md:24-119): this file never maps
 * 0x17a00000, never writes a TCS word, never triggers an RPMh transaction and
 * never issues an SMC. resources() records and re-proves the retention the
 * Android warm boot already applied; it cannot create a vote, so it fails
 * closed instead of pretending one exists. */
#ifndef K60_ADSP_BOARD_H
#define K60_ADSP_BOARD_H
#include "K60AdspPlatform.h"
#include "K60Smem.h"
#ifdef __cplusplus
extern "C" {
#endif
#define K60_ADSP_BOARD_VERSION 1u
/* VM_WIMG_DEFAULT: the SMEM window is DDR, not device memory. Same flag the
 * legacy reader uses for its DDR windows (K60AdspBoot.c:197-203). */
#define K60_ADSP_BOARD_MAP_FLAGS 0x2u
enum {
    K60BoardOk = 0,
    K60BoardBadArgument = -60,   /* geometry, null argument or call order */
    K60BoardNotExcluded = -61,   /* the early handoff owner does not hold the CAS */
    K60BoardNotStopped = -62,    /* no independent stopped proof */
    K60BoardUnsupported = -63,   /* a real vote would be required (HR-01) */
    K60BoardBusy = -64,          /* already leased, mapped or locked */
    K60BoardNoLease = -65,       /* no lease, or the token does not match it */
    K60BoardPoisoned = -66,      /* an earlier callback left uncertain state */
    K60BoardMapFailed = -67,     /* the read-only SMEM window could not be made */
    K60BoardBadPartition = -68   /* mapped memory is not the expected SMEM */
};
/* Read-only window access, injected so host tests can count every physical
 * access and so a kernel build keeps ml_io_map_unmappable out of this file. */
typedef struct {
    uint32_t version, bytes;
    int (*map)(void *, uint64_t, size_t, unsigned, volatile uint8_t **);
    void (*unmap)(void *, volatile uint8_t *, size_t);
    void *context;
} K60AdspBoardIo;
/* One lease record per grant. The ring is small on purpose: a lease is only
 * handed out again after an exclusive_release, so two slots already guarantee
 * that consecutive grants return different tokens. A stale token is rejected by
 * pointer identity before the epoch is even compared. */
#define K60_ADSP_BOARD_LEASE_SLOTS 2u
typedef struct {
    uint32_t magic, epoch;
    uint8_t token[8];             /* lease identity, contents bind the epoch */
} K60AdspBoardLease;
typedef struct {
    K60AdspPlatformOwnership ownership;
    K60AdspBoardIo io;
    K60BatteryConfig config;      /* pinned by exclusive(), zero when unleased */
    K60Smem smem;                 /* read-only window, zero when unmapped */
    K60SmemPartition partition;   /* geometry proved when the window was made */
    K60AdspBoardLease lease[K60_ADSP_BOARD_LEASE_SLOTS];
    unsigned slot;                /* index of the current grant */
    void *cookie;                 /* &lease[slot] while leased */
    uint32_t epoch, sequence;
    unsigned initialized, leased, resources, mapped, poisoned;
    int last_rc;
} K60AdspBoard;
/* Initialize once per boot with a complete io table. Zeroes all lease state;
 * no physical access. Returns K60BoardOk. */
int k60_adsp_board_init(K60AdspBoard *, const K60AdspBoardIo *);
/* The ownership table to hand to k60_adsp_platform_ownership_install(); NULL
 * until init succeeded. The pointer is the board itself, so it stays stable. */
const K60AdspPlatformOwnership *k60_adsp_board_ownership(const K60AdspBoard *);
/* Read-only diagnostic line for the boot log. */
void k60_adsp_board_report(K60AdspBoard *);
#ifdef KERNEL
/* ml_io_map_unmappable(phys,bytes,VM_WIMG_DEFAULT) backed io. This tree has no
 * ml_io_unmap, so the read-only window is retained for the boot (same choice as
 * patches/xnu/0500-k60-bt-qbt-new-files.patch:344). */
const K60AdspBoardIo *k60_adsp_board_kernel_io(void);
#endif
#ifdef __cplusplus
}
#endif
#endif
