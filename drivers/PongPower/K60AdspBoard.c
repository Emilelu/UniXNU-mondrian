/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/* K60 ADSP board ownership service.
 *
 * Every callback answers one question with evidence this board can actually
 * produce, and refuses with a named error when the evidence does not exist:
 *
 *   available  arithmetic over the pinned config and this service's state; it
 *              never maps, reads or calls the monitor.
 *   exclusive  read-only SMEM window + partition proof, the early-owner startup
 *              CAS, and one fresh nonzero epoch. Any failure rolls back inside.
 *   resources  lease + exclusion + an independent stopped proof, then refuses:
 *              creating a power/XO/interconnect vote needs a TCS write, which
 *              docs/ops/HARD-RULES.md forbids outright. Inherited retention
 *              cannot be proved while the DSP is stopped, so this reports
 *              K60BoardUnsupported instead of inventing a vote.
 *   stopped    the inbound SMP2P item, read only.
 *   live       the retained token only; never the resource flag.
 *   scm_lock   one kernel-global, non-reentrant lock for every SCM client.
 *
 * No SMC is issued from this file: the host test links it without the PAS
 * transport, so a stray call would fail the link instead of the board. */
#include "K60AdspBoard.h"
#include "K60AdspOwner.h"
#ifdef KERNEL
#include <pexpert/pexpert.h>
#include <machine/machine_routines.h>
/* printf() lives in sys/systm.h, not pexpert.h (K60PmicRail.c:17-20). */
#include <sys/systm.h>
extern vm_offset_t ml_io_map_unmappable(vm_offset_t phys, vm_size_t size,
    unsigned int flags);
#else
#include <stdio.h>
#endif

#define SMP2P_MAGIC 0x504d5324u
#define SMP2P_VERSION 1u
#define SMP2P_MIN_BYTES 20u
#define SMP2P_MAX_BYTES 340u
#define SMP2P_MAX_ENTRIES 16u
#define SMP2P_ENTRY_BYTES 20u
#define TOKEN_MAGIC 0x4230364bu /* "K60B" little endian */
#define LEASE_MAGIC 0x4c36304bu /* "K60L" little endian */

static uint32_t rd(const K60Smem *s, uint32_t at)
{ return *(volatile uint32_t *)(s->base + at); }

static void fence(void)
{
#if defined(__aarch64__) && defined(KERNEL)
    __asm__ volatile("dmb osh" ::: "memory");
#endif
}

static int io_ok(const K60AdspBoardIo *io)
{
    return io && io->version == K60_ADSP_BOARD_VERSION && io->bytes == sizeof *io &&
        io->map && io->unmap;
}

/* The board is one known device: the lease binds this exact geometry, item
 * layout and protocol, never a discovered address. Mirrors the owner engine's
 * own pin list (K60AdspOwnerStages.c:27-35). */
static int config_ok(const K60BatteryConfig *c)
{
    return c && c->smem_base == UINT64_C(0x80900000) && c->smem_bytes == 0x200000u &&
        c->adsp_base == UINT64_C(0x9fd00000) && c->adsp_bytes == 0x3100000u &&
        c->mutex_base == 0x1f4100cu && c->ipcc_base == 0xed18000u &&
        c->remote_pid == 2u && c->ipcc_client == 3u && !c->ipcc_signal &&
        c->desc_item == 478u && c->tx_item == 479u && c->rx_item == 480u &&
        c->smp2p_item == 443u && c->protocol == 1u;
}

static int ready(const K60AdspBoard *b)
{ return b && b->initialized && !__atomic_load_n(&b->poisoned, __ATOMIC_ACQUIRE); }

static void poison(K60AdspBoard *b)
{ __atomic_store_n(&b->poisoned, 1u, __ATOMIC_RELEASE); }

/* A lease is proved by pointer identity AND by the contents of that exact
 * record: a token from an earlier grant is a different pointer, so it can never
 * be mistaken for the current one even if the epoch wrapped. */
static const K60AdspBoardLease *current(const K60AdspBoard *b)
{
    if (!b || !b->leased || !b->cookie) return 0;
    for (unsigned i = 0; i < K60_ADSP_BOARD_LEASE_SLOTS; ++i)
        if (b->cookie == (const void *)&b->lease[i]) return &b->lease[i];
    return 0;
}

static int leased(const K60AdspBoard *b, void *cookie)
{
    const K60AdspBoardLease *l = current(b);
    return l && cookie == b->cookie && l->magic == LEASE_MAGIC &&
        l->epoch == b->epoch && b->epoch;
}

static void lease_set(K60AdspBoardLease *l, uint32_t epoch)
{
    for (unsigned i = 0; i < sizeof *l; ++i) ((uint8_t *)l)[i] = 0;
    l->magic = LEASE_MAGIC;
    l->epoch = epoch;
    l->token[0] = (uint8_t)TOKEN_MAGIC;
    l->token[1] = (uint8_t)(TOKEN_MAGIC >> 8);
    l->token[2] = (uint8_t)(TOKEN_MAGIC >> 16);
    l->token[3] = (uint8_t)(TOKEN_MAGIC >> 24);
    l->token[4] = (uint8_t)epoch;
    l->token[5] = (uint8_t)(epoch >> 8);
    l->token[6] = (uint8_t)(epoch >> 16);
    l->token[7] = (uint8_t)(epoch >> 24);
}

static int token_ok(const K60AdspBoard *b)
{
    const K60AdspBoardLease *l = current(b);
    return l && l->token[0] == (uint8_t)TOKEN_MAGIC &&
        l->token[1] == (uint8_t)(TOKEN_MAGIC >> 8) &&
        l->token[2] == (uint8_t)(TOKEN_MAGIC >> 16) &&
        l->token[3] == (uint8_t)(TOKEN_MAGIC >> 24) &&
        l->token[4] == (uint8_t)b->epoch && l->token[5] == (uint8_t)(b->epoch >> 8) &&
        l->token[6] == (uint8_t)(b->epoch >> 16) && l->token[7] == (uint8_t)(b->epoch >> 24);
}

/* Drop the lease and the read-only window. Every step is unconditional, so a
 * failed acquire can call this from any intermediate state. */
static void release_all(K60AdspBoard *b)
{
    if (b->mapped) {
        b->io.unmap(b->io.context, b->smem.base, (size_t)b->smem.size);
        b->mapped = 0;
    }
    b->smem.base = 0;
    b->smem.size = 0;
    for (unsigned i = 0; i < sizeof b->partition; ++i) ((uint8_t *)&b->partition)[i] = 0;
    for (unsigned i = 0; i < sizeof b->lease; ++i) ((uint8_t *)b->lease)[i] = 0;
    for (unsigned i = 0; i < sizeof b->config; ++i) ((uint8_t *)&b->config)[i] = 0;
    b->cookie = 0;
    b->epoch = 0;
    b->leased = 0;
    b->resources = 0;
}

static int map_window(K60AdspBoard *b)
{
    volatile uint8_t *base = 0;
    int rc;
    if (b->mapped) return K60BoardOk;
    rc = b->io.map(b->io.context, b->config.smem_base, (size_t)b->config.smem_bytes,
        K60_ADSP_BOARD_MAP_FLAGS, &base);
    if (rc || !base) return K60BoardMapFailed;
    b->smem.base = base;
    b->smem.size = (uint32_t)b->config.smem_bytes;
    b->mapped = 1;
    /* The window is only useful if it really is this board's SMEM table. */
    if (k60_smem_partition(&b->smem, 0, (uint16_t)b->config.remote_pid, &b->partition))
        return K60BoardBadPartition;
    return K60BoardOk;
}

/* Read-only SMP2P verdict. 1 = stopped, 0 = not stopped, -1 = present but
 * malformed, -2 = no proof available. Never writes. */
static int stopped_state(const K60AdspBoard *b)
{
    uint32_t off = 0, n = 0;
    int rc;
    if (!b->mapped || !b->smem.base) return -2;
    rc = k60_smem_find(&b->smem, &b->partition, (uint16_t)b->config.smp2p_item, &off, &n);
    /* Never announced by the remote: nothing has been started yet. */
    if (rc == K60SmemMissing) return 1;
    if (rc != K60SmemOk || (off & 3u) || n < SMP2P_MIN_BYTES || n > SMP2P_MAX_BYTES)
        return rc == K60SmemOk ? -1 : -2;
    if (rd(&b->smem, off) != SMP2P_MAGIC || (rd(&b->smem, off + 4) & 255u) != SMP2P_VERSION ||
        rd(&b->smem, off + 8) != b->config.remote_pid) return -1;
    const uint32_t count = rd(&b->smem, off + 12);
    const uint32_t total = count & 65535u, valid = count >> 16;
    fence();
    if (total > SMP2P_MAX_ENTRIES || valid > total ||
        SMP2P_MIN_BYTES + valid * SMP2P_ENTRY_BYTES > n) return -1;
    /* A pending restart request means the remote is not stably stopped. */
    if (rd(&b->smem, off + 16) & 1u) return 0;
    static const uint8_t name[16] = "slave-kernel";
    for (uint32_t i = 0; i < valid; ++i) {
        unsigned j = 0;
        for (; j < 16; ++j) if (b->smem.base[off + 20u + i * 20u + j] != name[j]) break;
        if (j == 16) {
            const uint32_t state = rd(&b->smem, off + 36u + i * 20u);
            fence();
            /* bit 2 = the remote announced itself; bit 0 = fatal/restart ack. */
            return state == 0 ? 1 : 0;
        }
    }
    return 1; /* announced nothing: still stopped */
}

static int available_cb(void *ctx, const K60BatteryConfig *c)
{
    K60AdspBoard *b = ctx;
    return ready(b) && io_ok(&b->io) && config_ok(c) ? 1 : 0;
}

static int exclusive_cb(void *ctx, const K60BatteryConfig *c, uint32_t *epoch, void **cookie)
{
    K60AdspBoard *b = ctx;
    int rc;
    if (!b || !epoch || !cookie) return K60BoardBadArgument;
    *epoch = 0;
    *cookie = 0;
    if (!ready(b) || !io_ok(&b->io) || !config_ok(c)) return K60BoardBadArgument;
    if (b->leased || b->mapped) return K60BoardBusy;
    /* Exclusion is a fact, not an assumption: the early handoff owner holds the
     * startup CAS, so the late legacy loader can never claim owner 2 and can
     * never reset or restart the DSP behind this lease (K60AdspStartup.c:5-13,
     * patches/xnu/0619-k60-adsp-glink-handoff.patch:346-351). */
    if (k60_adsp_handoff_owner_active() != 1) return K60BoardNotExcluded;
    b->config = *c;
    rc = map_window(b);
    if (rc) { release_all(b); return rc; }
    const uint32_t next = b->sequence + 1u;
    if (!next) { release_all(b); return K60BoardBadArgument; }
    b->sequence = next;
    b->epoch = next;
    b->slot = (b->slot + 1u) % K60_ADSP_BOARD_LEASE_SLOTS;
    lease_set(&b->lease[b->slot], b->epoch);
    b->cookie = &b->lease[b->slot];
    b->leased = 1;
    *epoch = b->epoch;
    *cookie = b->cookie;
    return K60BoardOk;
}

static void exclusive_release_cb(void *ctx, void *cookie)
{
    K60AdspBoard *b = ctx;
    /* A successful release cannot fail and cannot be conditional: a stale or
     * foreign token still drops this board's lease rather than leaving it set. */
    if (!b || !b->initialized) return;
    (void)cookie;
    release_all(b);
}

static int resources_cb(void *ctx, void *cookie)
{
    K60AdspBoard *b = ctx;
    if (!ready(b) || !leased(b, cookie)) return K60BoardNoLease;
    if (k60_adsp_handoff_owner_active() != 1) return K60BoardNotExcluded;
    const int state = stopped_state(b);
    if (state < 0) { poison(b); return K60BoardNotStopped; }
    if (state != 1) return K60BoardNotStopped;
    /* HR-01: retaining power/XO/interconnect means writing an RPMh TCS, and
     * that is forbidden with no exception. The Android warm boot already
     * enabled these rails, so XNU inherits them by never voting, but an
     * inherited vote cannot be proved while the DSP is stopped. Refuse with the
     * reason instead of reporting retention this service does not hold. */
    b->last_rc = K60BoardUnsupported;
    return K60BoardUnsupported;
}

static void resources_release_cb(void *ctx, void *cookie)
{
    K60AdspBoard *b = ctx;
    if (!b) return;
    /* Nothing was ever voted, so there is nothing to undo; the flag must still
     * fall so a later live() cannot be confused with retention. */
    b->resources = 0;
    (void)cookie;
}

static int stopped_cb(void *ctx, void *cookie)
{
    K60AdspBoard *b = ctx;
    if (!ready(b) || !leased(b, cookie)) return 0;
    const int state = stopped_state(b);
    if (state < 0) { poison(b); return 0; }
    return state == 1 ? 1 : 0;
}

static int live_cb(void *ctx, void *cookie, uint32_t epoch)
{
    K60AdspBoard *b = ctx;
    /* The retained token only. Resource acquisition is deliberately not
     * consulted: the header requires live to prove the lease on its own. */
    if (!ready(b) || !leased(b, cookie) || epoch != b->epoch) return 0;
    if (k60_adsp_handoff_owner_active() != 1) return 0;
    return token_ok(b) ? 1 : 0;
}

/* One lock for every SCM client on this kernel: the monitor transaction is
 * global, so a second lock while held is busy, not a recursive success. The
 * holder is recorded because unlock returns void and cannot fail: a board that
 * does not hold the lock must never free the holder's claim. */
static K60AdspBoard *scm_holder;

static int scm_lock_cb(void *ctx)
{
    K60AdspBoard *b = ctx;
    if (!ready(b)) return K60BoardBadArgument;
    if (!__sync_bool_compare_and_swap(&scm_holder, (K60AdspBoard *)0, b))
        return K60BoardBusy;
    __sync_synchronize();
    return K60BoardOk;
}

static void scm_unlock_cb(void *ctx)
{
    K60AdspBoard *b = ctx;
    if (!b || !b->initialized) return;
    /* Only the recorded holder releases it; anyone else is a no-op, which is
     * the only behaviour a void release can safely have. */
    __sync_synchronize();
    (void)__sync_bool_compare_and_swap(&scm_holder, b, (K60AdspBoard *)0);
}

int k60_adsp_board_init(K60AdspBoard *b, const K60AdspBoardIo *io)
{
    if (!b || !io_ok(io)) return K60BoardBadArgument;
    for (unsigned i = 0; i < sizeof *b; ++i) ((uint8_t *)b)[i] = 0;
    b->io = *io;
    b->ownership.version = K60_ADSP_PLATFORM_VERSION;
    b->ownership.bytes = sizeof b->ownership;
    b->ownership.available = available_cb;
    b->ownership.exclusive = exclusive_cb;
    b->ownership.exclusive_release = exclusive_release_cb;
    b->ownership.resources = resources_cb;
    b->ownership.resources_release = resources_release_cb;
    b->ownership.stopped = stopped_cb;
    b->ownership.live = live_cb;
    b->ownership.scm_lock = scm_lock_cb;
    b->ownership.scm_unlock = scm_unlock_cb;
    b->initialized = 1;
    return K60BoardOk;
}

const K60AdspPlatformOwnership *k60_adsp_board_ownership(const K60AdspBoard *b)
{ return b && b->initialized ? &b->ownership : 0; }

void k60_adsp_board_report(K60AdspBoard *b)
{
    if (!b) return;
    printf("K60ADSP board initialized=%u leased=%u resources=%u mapped=%u "
        "poisoned=%u epoch=%u scm=%u rc=%d%c", b->initialized, b->leased,
        b->resources, b->mapped, __atomic_load_n(&b->poisoned, __ATOMIC_ACQUIRE),
        b->epoch,
        (unsigned)(__atomic_load_n(&scm_holder, __ATOMIC_ACQUIRE) == b), b->last_rc, 10);
}

#ifdef KERNEL
static int kernel_map(void *ctx, uint64_t physical, size_t bytes, unsigned flags,
    volatile uint8_t **out)
{
    (void)ctx;
    if (!out || !bytes || !physical || physical > UINT64_MAX - bytes) return -1;
    const vm_offset_t va = ml_io_map_unmappable((vm_offset_t)physical,
        (vm_size_t)bytes, flags ? flags : K60_ADSP_BOARD_MAP_FLAGS);
    if (!va) return -1;
    *out = (volatile uint8_t *)(uintptr_t)va;
    return 0;
}

static void kernel_unmap(void *ctx, volatile uint8_t *base, size_t bytes)
{
    /* This tree has no ml_io_unmap: the read-only window is retained for the
     * boot, the same choice the BT port records at
     * patches/xnu/0500-k60-bt-qbt-new-files.patch:344. */
    (void)ctx; (void)base; (void)bytes;
}

static const K60AdspBoardIo kernel_io = { K60_ADSP_BOARD_VERSION, sizeof kernel_io,
    kernel_map, kernel_unmap, 0 };

const K60AdspBoardIo *k60_adsp_board_kernel_io(void)
{ return &kernel_io; }
#endif
