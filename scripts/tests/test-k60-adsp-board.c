/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/* Offline only: never touches a device or physical memory.
 *
 * This binary links the real board service, the real SMEM parser and the real
 * startup arbitration, and nothing else. The PAS transport (K60AdspPas.c) is
 * deliberately absent, so any SMC the board tried to issue would fail the link
 * instead of the test: "the board issues no monitor call" is a link-time fact
 * here, not a comment.
 *
 * Scenarios, in the order the Lead required them:
 *   1 available()==0 performs zero SMEM/TCSR/SMC access
 *   2 a failed exclusive() rolls back every field it touched
 *   3 stopped() stays provable and stable across exclusive_release()
 *   4 scm_lock() is not reentrant, for one board and across two boards
 *   5 live() proves the retained token without any resource acquisition
 *   6 after the install gate accepts this table, available() is exactly 1
 *   7 the negative SMP2P evidence cases that stop a corrupt item from ever
 *     being read as "stopped";
 *   8 resources() separates never-measured, missing and invalid rail records,
 *     and reports retention only for two complete, sane measurements. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stddef.h>
#include "K60Smem.h"
#include "K60AdspOwner.h"
#include "K60AdspBoard.h"
#include "K60PmicRail.h"

#define SMEM_BYTES 0x200000u
#define SMEM_WORDS (SMEM_BYTES / 4u)
#define PART_AT 0x1000u
#define PART_BYTES 0x10000u
#define SMP2P_ITEM 443u
#define SMP2P_BYTES 40u

static unsigned cases;
static const char *scenario_name;
#define CHECK(test) do { if (!(test)) { \
    fprintf(stderr, "FAIL %s:%d: %s: %s\n", __FILE__, __LINE__, scenario_name, #test); \
    exit(1); } } while (0)

/* The startup CAS has no release, so the "no exclusion yet" case must run
 * before the first claim; every later scenario runs with owner 1 active. */
int k60_adsp_startup_claim(unsigned owner);
int k60_adsp_handoff_owner_active(void);

typedef struct {
    _Alignas(8) uint32_t memory[SMEM_WORDS];
    unsigned map_calls, unmap_calls, map_fail_on;
    unsigned mapped, short_unmaps;
    volatile uint8_t *base;
    size_t bytes;
    unsigned flags_seen;
    uint64_t physical_seen;
    K60AdspBoard board;
    K60AdspBoardIo io;
    uint32_t item_offset;
} Fixture;

static int io_map(void *ctx, uint64_t physical, size_t bytes, unsigned flags,
    volatile uint8_t **out)
{
    Fixture *f = ctx;
    CHECK(f && out && !*out);
    ++f->map_calls;
    f->physical_seen = physical;
    f->flags_seen = flags;
    if (f->map_calls == f->map_fail_on) return -1;
    CHECK(!f->mapped);
    f->base = (volatile uint8_t *)f->memory;
    f->bytes = bytes;
    f->mapped = 1;
    *out = f->base;
    return 0;
}

static void io_unmap(void *ctx, volatile uint8_t *base, size_t bytes)
{
    Fixture *f = ctx;
    CHECK(f && f->mapped && base == f->base);
    if (bytes != f->bytes) ++f->short_unmaps;
    f->mapped = 0;
    f->base = 0;
    f->bytes = 0;
    ++f->unmap_calls;
}

static void put(Fixture *f, uint32_t at, uint32_t value)
{
    CHECK(!(at & 3u) && at + 4u <= SMEM_BYTES);
    f->memory[at / 4] = value;
}

static const K60BatteryConfig pinned = {
    UINT64_C(0x80900000), SMEM_BYTES, 0xed18000u, 0x1f4100cu,
    UINT64_C(0x9fd00000), 0x3100000u, 2, 3, 0, 478, 479, 480, SMP2P_ITEM, 1, 0 };

/* Synthetic SMEM: TOC in the last page, one APPS<->remote partition, and, when
 * announce is set, the inbound SMP2P item the remote would publish. */
static void build(Fixture *f, int announce, uint32_t state, uint32_t restart)
{
    memset(f, 0, sizeof *f);
    const uint32_t toc = SMEM_BYTES - 4096u;
    put(f, toc, 0x434f5424u);
    put(f, toc + 4, 1);
    put(f, toc + 8, 1);
    put(f, toc + 32, PART_AT);
    put(f, toc + 36, PART_BYTES);
    put(f, toc + 44, 2u << 16);
    put(f, toc + 48, 8);
    put(f, PART_AT, 0x54525024u);
    put(f, PART_AT + 4, 2u << 16);
    put(f, PART_AT + 8, PART_BYTES);
    put(f, PART_AT + 12, 32);
    put(f, PART_AT + 16, PART_BYTES);
    if (announce) {
        K60Smem smem = { (volatile uint8_t *)f->memory, SMEM_BYTES };
        K60SmemPartition part;
        uint32_t n = 0;
        CHECK(!k60_smem_partition(&smem, 0, 2, &part));
        CHECK(!k60_smem_alloc(&smem, &part, SMP2P_ITEM, SMP2P_BYTES, &f->item_offset, &n));
        CHECK(n == SMP2P_BYTES);
        put(f, f->item_offset, 0x504d5324u);
        put(f, f->item_offset + 4, 1);
        put(f, f->item_offset + 8, 2);
        put(f, f->item_offset + 12, 0x10001u);
        put(f, f->item_offset + 16, restart);
        memcpy((uint8_t *)f->memory + f->item_offset + 20u, "slave-kernel", 13);
        put(f, f->item_offset + 36, state);
    }
    f->io = (K60AdspBoardIo){ K60_ADSP_BOARD_VERSION, sizeof f->io, io_map, io_unmap, f };
    CHECK(!k60_adsp_board_init(&f->board, &f->io));
}

static void start(const char *name) { scenario_name = name; ++cases; }

static uint32_t before[SMEM_WORDS], after[SMEM_WORDS];
static size_t before_used, after_used;

static void snapshot(Fixture *f, uint32_t *out, size_t *used)
{
    size_t n = 0;
    for (size_t i = 0; i < SMEM_WORDS; ++i) if (f->memory[i]) out[n++] = (uint32_t)i;
    *used = n;
}

/* 1. A zero verdict is arithmetic only: no window, no read, no monitor call. */
static void scenario_available_is_free(Fixture *f)
{
    start("available=0 touches no SMEM/TCSR and issues no SMC");
    K60BatteryConfig bad = pinned;
    bad.smem_base = UINT64_C(0x80901000); /* discovered, not the pinned board */
    CHECK(k60_adsp_board_ownership(&f->board) == &f->board.ownership);
    CHECK(f->board.ownership.available(&f->board, &bad) == 0);
    bad = pinned;
    bad.smp2p_item = 444;
    CHECK(f->board.ownership.available(&f->board, &bad) == 0);
    bad = pinned;
    bad.protocol = 2;
    CHECK(f->board.ownership.available(&f->board, &bad) == 0);
    CHECK(f->board.ownership.available(&f->board, NULL) == 0);
    /* An uninitialized board is unavailable, never optimistic. */
    K60AdspBoard fresh;
    memset(&fresh, 0, sizeof fresh);
    CHECK(k60_adsp_board_ownership(&fresh) == NULL);
    CHECK(f->map_calls == 0 && f->unmap_calls == 0);
    CHECK(f->board.epoch == 0 && !f->board.leased && !f->board.mapped);
    /* available()==1 is still free: it must not map the window either. */
    CHECK(f->board.ownership.available(&f->board, &pinned) == 1);
    CHECK(f->map_calls == 0 && f->unmap_calls == 0 && !f->board.mapped);
    CHECK(f->board.ownership.live(&f->board, NULL, 0) == 0);
    CHECK(f->board.ownership.stopped(&f->board, NULL) == 0);
    CHECK(f->map_calls == 0);
}

/* 2. Every failure path leaves the board exactly as it was. */
static void scenario_exclusive_rolls_back(Fixture *f)
{
    uint32_t epoch = 0xdeadbeefu;
    void *cookie = (void *)&epoch;
    start("exclusive failure rolls back epoch, token, cookie and window");
    /* (a) no exclusion witness yet: the late legacy loader could still run. */
    CHECK(k60_adsp_handoff_owner_active() == 0);
    CHECK(f->board.ownership.exclusive(&f->board, &pinned, &epoch, &cookie) ==
        K60BoardNotExcluded);
    CHECK(epoch == 0 && cookie == NULL);
    CHECK(!f->board.leased && !f->board.mapped && f->board.epoch == 0 &&
        f->board.cookie == NULL && f->board.sequence == 0);
    CHECK(f->map_calls == 0 && f->unmap_calls == 0);
    /* (b) the read-only window cannot be made. */
    CHECK(k60_adsp_startup_claim(1u));
    CHECK(k60_adsp_handoff_owner_active() == 1);
    f->map_fail_on = f->map_calls + 1;
    epoch = 0xdeadbeefu;
    cookie = (void *)&epoch;
    CHECK(f->board.ownership.exclusive(&f->board, &pinned, &epoch, &cookie) == K60BoardMapFailed);
    CHECK(epoch == 0 && cookie == NULL);
    CHECK(!f->board.leased && !f->board.mapped && f->board.epoch == 0 &&
        f->board.cookie == NULL && f->board.sequence == 0 && !f->board.resources);
    CHECK(f->map_calls == 1 && f->unmap_calls == 0);
    /* (c) mapped, but not this board's SMEM: rolled back, mapping released. */
    Fixture *g = malloc(sizeof *g);
    CHECK(g != NULL);
    build(g, 0, 0, 0);
    put(g, SMEM_BYTES - 4096u, 0x434f5425u);
    epoch = 0xdeadbeefu;
    cookie = (void *)&epoch;
    CHECK(g->board.ownership.exclusive(&g->board, &pinned, &epoch, &cookie) ==
        K60BoardBadPartition);
    CHECK(epoch == 0 && cookie == NULL);
    CHECK(!g->board.leased && !g->board.mapped && g->board.epoch == 0 && !g->mapped);
    CHECK(g->map_calls == 1 && g->unmap_calls == 1 && !g->short_unmaps);
    free(g);
    /* (d) bad arguments are refused before anything happens. */
    epoch = 0;
    cookie = NULL;
    CHECK(f->board.ownership.exclusive(&f->board, &pinned, NULL, &cookie) ==
        K60BoardBadArgument);
    CHECK(f->board.ownership.exclusive(&f->board, &pinned, &epoch, NULL) ==
        K60BoardBadArgument);
    CHECK(f->board.ownership.exclusive(&f->board, NULL, &epoch, &cookie) ==
        K60BoardBadArgument);
    CHECK(!f->board.leased && f->map_calls == 1);
}

/* 3. The stopped proof must not evaporate when the lease is dropped, and the
 *    remote state must be byte-identical through all of it. */
static void scenario_stopped_survives_release(Fixture *f)
{
    uint32_t epoch = 0, next_epoch = 0;
    void *cookie = NULL, *next_cookie = NULL;
    start("stopped stays provable and byte-identical across exclusive_release");
    snapshot(f, before, &before_used);
    CHECK(!f->board.ownership.exclusive(&f->board, &pinned, &epoch, &cookie));
    CHECK(epoch != 0 && cookie != NULL && f->board.leased && f->board.mapped);
    CHECK(f->physical_seen == pinned.smem_base && f->bytes == SMEM_BYTES);
    CHECK(f->flags_seen == K60_ADSP_BOARD_MAP_FLAGS);
    CHECK(f->board.ownership.stopped(&f->board, cookie) == 1);
    CHECK(f->board.ownership.live(&f->board, cookie, epoch) == 1);
    /* Retention cannot be created (HR-01); the owner engine releases resources
     * before the exclusion, so exercise exactly that order. */
    CHECK(f->board.ownership.resources(&f->board, cookie) == K60BoardUnsupported);
    f->board.ownership.resources_release(&f->board, cookie);
    CHECK(!f->board.resources);
    CHECK(f->board.ownership.stopped(&f->board, cookie) == 1);
    const uint32_t held_epoch = epoch;
    f->board.ownership.exclusive_release(&f->board, cookie);
    /* Without the exclusion there is no proof to give: never a stale 1. */
    CHECK(f->board.ownership.stopped(&f->board, cookie) == 0);
    CHECK(f->board.ownership.live(&f->board, cookie, held_epoch) == 0);
    CHECK(!f->board.leased && !f->board.mapped && f->board.epoch == 0);
    CHECK(f->unmap_calls == 1 && !f->mapped && !f->short_unmaps);
    snapshot(f, after, &after_used);
    CHECK(before_used == after_used);
    CHECK(!memcmp(before, after, before_used * sizeof before[0]));
    /* Stable, not lucky: a new lease proves the same fact with a new epoch, and
     * the old token opens nothing. */
    CHECK(!f->board.ownership.exclusive(&f->board, &pinned, &next_epoch, &next_cookie));
    CHECK(next_epoch != held_epoch && next_cookie != cookie);
    CHECK(f->board.ownership.stopped(&f->board, next_cookie) == 1);
    CHECK(f->board.ownership.stopped(&f->board, cookie) == 0);
    CHECK(f->board.ownership.live(&f->board, cookie, held_epoch) == 0);
    CHECK(f->board.ownership.live(&f->board, next_cookie, next_epoch) == 1);
    CHECK(f->board.ownership.live(&f->board, next_cookie, held_epoch) == 0);
    f->board.ownership.exclusive_release(&f->board, next_cookie);
    snapshot(f, after, &after_used);
    CHECK(before_used == after_used);
    CHECK(!memcmp(before, after, before_used * sizeof before[0]));
}

/* 4. One lock for every SCM client, and no recursive success. */
static void scenario_scm_lock_not_reentrant(Fixture *f, Fixture *other)
{
    start("scm_lock is non-reentrant for one board and across boards");
    CHECK(f != other);
    CHECK(!f->board.ownership.scm_lock(&f->board));
    CHECK(f->board.ownership.scm_lock(&f->board) == K60BoardBusy);
    /* A second board is a second SCM client, not a second lock. */
    CHECK(other->board.ownership.scm_lock(&other->board) == K60BoardBusy);
    f->board.ownership.scm_unlock(&f->board);
    CHECK(!other->board.ownership.scm_lock(&other->board));
    /* Unlocking a board that does not hold it must not free the lock. */
    f->board.ownership.scm_unlock(&f->board);
    CHECK(other->board.ownership.scm_lock(&other->board) == K60BoardBusy);
    other->board.ownership.scm_unlock(&other->board);
    CHECK(!f->board.ownership.scm_lock(&f->board));
    f->board.ownership.scm_unlock(&f->board);
}

/* 5. live() is the token and nothing else: no resource call ever succeeded. */
static void scenario_live_without_resources(Fixture *f)
{
    uint32_t epoch = 0;
    void *cookie = NULL;
    start("live proves the token while resources() is unavailable");
    CHECK(!f->board.ownership.exclusive(&f->board, &pinned, &epoch, &cookie));
    CHECK(f->board.ownership.resources(&f->board, cookie) == K60BoardUnsupported);
    CHECK(!f->board.resources);
    CHECK(f->board.ownership.live(&f->board, cookie, epoch) == 1);
    CHECK(f->board.ownership.live(&f->board, cookie, epoch + 1u) == 0);
    CHECK(f->board.ownership.live(&f->board, &epoch, epoch) == 0);
    CHECK(f->board.ownership.live(&f->board, cookie, 0) == 0);
    /* The token contents bind the epoch: corrupting them invalidates live. */
    K60AdspBoardLease *l = (K60AdspBoardLease *)f->board.cookie;
    CHECK(l != NULL);
    l->token[4] ^= 0xffu;
    CHECK(f->board.ownership.live(&f->board, cookie, epoch) == 0);
    f->board.ownership.exclusive_release(&f->board, cookie);
}

/* 6. The wiring fact the Lead asked for: availability is off until the install
 *    gate accepts this table, and exactly 1 afterwards.
 *
 * The real gate and the real availability expression live in
 * K60AdspPlatformNative.cpp:360-375 and :81-85, which are C++ against IOKit and
 * cannot be linked into a host binary; the runner's arm64 pass compiles the real
 * file. These two helpers are line-for-line replicas of those two functions, so
 * what is asserted here is the same acceptance rule the kernel applies. */
static unsigned gate_state;                       /* ownershipInstallation */
static const K60AdspPlatformOwnership *gate_source;
static void *gate_context;

static int gate_complete(const K60AdspPlatformOwnership *o)
{
    return o && o->version == K60_ADSP_PLATFORM_VERSION && o->bytes == sizeof(*o) &&
        o->available && o->exclusive && o->exclusive_release && o->resources &&
        o->resources_release && o->stopped && o->live && o->scm_lock && o->scm_unlock;
}

static int gate_installed(void) { return gate_state == 2u; }

static int gate_install(const K60AdspPlatformOwnership *o, void *context)
{
    if (!gate_complete(o)) return K60_ADSP_OWNER_UNAVAILABLE;
    if (gate_installed())
        return gate_source == o && gate_context == context ? 1 : K60_ADSP_OWNER_UNAVAILABLE;
    if (!__sync_bool_compare_and_swap(&gate_state, 0u, 1u)) return K60_ADSP_OWNER_UNAVAILABLE;
    gate_source = o; gate_context = context;
    __atomic_store_n(&gate_state, 2u, __ATOMIC_RELEASE);
    return 0;
}

/* K60AdspPlatformNative.cpp:81-85 verbatim in shape: healthy() && validConfig()
 * && board.available(...)==1. */
static int native_available(void *context, const K60BatteryConfig *c)
{
    return gate_installed() && context == gate_context && gate_source &&
        gate_source->available(context, c) == 1;
}

static void scenario_install_turns_available_on(void)
{
    Fixture *f = malloc(sizeof *f);
    CHECK(f != NULL);
    start("available() is 0 before the install gate and exactly 1 after it");
    /* A board that has never been touched: no lease, no window, no counter. */
    build(f, 1, 0, 0);
    CHECK(f->map_calls == 0 && f->unmap_calls == 0 && !f->board.mapped);
    /* Not installed: this is the stage=1 rc=-1000 a device run shows when the
     * board service is never installed. */
    CHECK(!gate_installed());
    CHECK(native_available(&f->board, &pinned) == 0);
    /* A table that was never initialized can never pass the gate. */
    K60AdspBoard fresh;
    memset(&fresh, 0, sizeof fresh);
    CHECK(k60_adsp_board_ownership(&fresh) == NULL);
    CHECK(gate_install(k60_adsp_board_ownership(&fresh), &fresh) ==
        K60_ADSP_OWNER_UNAVAILABLE);
    /* The real table passes: version, size and all ten callbacks. */
    const K60AdspPlatformOwnership *o = k60_adsp_board_ownership(&f->board);
    CHECK(o != NULL && gate_complete(o) == 1);
    /* The context is the board itself, exactly as K60HandoffRuntime.cpp:63
     * passes &board: the callbacks receive the same pointer they were built on. */
    CHECK(gate_install(o, &f->board) == 0);
    CHECK(gate_installed());
    /* Exactly 1, not merely nonzero, through both layers. */
    CHECK(f->board.ownership.available(&f->board, &pinned) == 1);
    CHECK(native_available(&f->board, &pinned) == 1);
    /* Still free: availability is arithmetic, never a physical access. */
    CHECK(f->map_calls == 0 && f->unmap_calls == 0 && !f->board.mapped);
    /* An installed table does not make some other board available. */
    K60BatteryConfig bad = pinned;
    bad.adsp_bytes = 0x2800000u;
    CHECK(native_available(&f->board, &bad) == 0);
    CHECK(native_available(&f->board, NULL) == 0);
    CHECK(native_available(&fresh, &pinned) == 0);
    /* Re-installing the same table and context is "already ours" (1); any other
     * context or a table missing one callback is a failure, never a 1. */
    CHECK(gate_install(o, &f->board) == 1);
    CHECK(gate_install(o, NULL) == K60_ADSP_OWNER_UNAVAILABLE);
    K60AdspPlatformOwnership cut = *o;
    cut.live = NULL;
    CHECK(gate_complete(&cut) == 0);
    CHECK(gate_install(&cut, &f->board) == K60_ADSP_OWNER_UNAVAILABLE);
    cut = *o;
    cut.bytes = sizeof(cut) - 1u;
    CHECK(gate_install(&cut, &f->board) == K60_ADSP_OWNER_UNAVAILABLE);
    /* The gate is a one-way door for the boot: a later failed install cannot
     * take the accepted table back out. */
    CHECK(gate_installed() && native_available(&f->board, &pinned) == 1);
    /* Availability never opened the window, at any point above. */
    CHECK(f->map_calls == 0 && f->unmap_calls == 0 && !f->board.mapped);
    /* And the gate is what the owner engine actually consults: with the table
     * installed, acquisition proceeds past stage 1 into the real exclusion and
     * stopped proof instead of failing unavailable. */
    uint32_t epoch = 0;
    void *cookie = NULL;
    CHECK(f->board.ownership.exclusive(&f->board, &pinned, &epoch, &cookie) == K60BoardOk);
    CHECK(epoch != 0 && cookie != NULL);
    CHECK(f->board.ownership.stopped(&f->board, cookie) == 1);
    CHECK(f->board.ownership.live(&f->board, cookie, epoch) == 1);
    CHECK(f->board.ownership.resources(&f->board, cookie) == K60BoardUnsupported);
    f->board.ownership.exclusive_release(&f->board, cookie);
    free(f);
}

/* 7. A corrupt or announced SMP2P item must never be read as "stopped". */
static void scenario_stopped_needs_evidence(Fixture *f)
{
    uint32_t epoch = 0;
    void *cookie = NULL;
    Fixture *g = malloc(sizeof *g);
    CHECK(g != NULL);
    start("stopped refuses announced, restarting and corrupt SMP2P states");
    /* Announced and live (bit 2 set): not stopped. */
    build(g, 1, 2, 0);
    CHECK(!g->board.ownership.exclusive(&g->board, &pinned, &epoch, &cookie));
    CHECK(g->board.ownership.stopped(&g->board, cookie) == 0);
    g->board.ownership.exclusive_release(&g->board, cookie);
    /* Announced, quiet, but a restart is still pending: not stably stopped. */
    build(g, 1, 0, 1);
    CHECK(!g->board.ownership.exclusive(&g->board, &pinned, &epoch, &cookie));
    CHECK(g->board.ownership.stopped(&g->board, cookie) == 0);
    g->board.ownership.exclusive_release(&g->board, cookie);
    /* Announced, quiet, no restart request: stopped. */
    build(g, 1, 0, 0);
    CHECK(!g->board.ownership.exclusive(&g->board, &pinned, &epoch, &cookie));
    CHECK(g->board.ownership.stopped(&g->board, cookie) == 1);
    /* A corrupt SMP2P header is not evidence of anything: the board poisons
     * itself rather than guess, and every later proof stays refused. */
    put(g, g->item_offset, 0x504d5325u);
    CHECK(g->board.ownership.stopped(&g->board, cookie) == 0);
    CHECK(g->board.poisoned == 1);
    CHECK(g->board.ownership.live(&g->board, cookie, epoch) == 0);
    CHECK(g->board.ownership.stopped(&g->board, cookie) == 0);
    CHECK(g->board.ownership.available(&g->board, &pinned) == 0);
    CHECK(g->board.ownership.exclusive(&g->board, &pinned, &epoch, &cookie) ==
        K60BoardBadArgument);
    g->board.ownership.exclusive_release(&g->board, cookie);
    free(g);
    /* No item at all: the remote never announced itself, which is the one
     * missing-item case that IS stopped. */
    Fixture *empty = malloc(sizeof *empty);
    CHECK(empty != NULL);
    build(empty, 0, 0, 0);
    CHECK(!empty->board.ownership.exclusive(&empty->board, &pinned, &epoch, &cookie));
    CHECK(empty->board.ownership.stopped(&empty->board, cookie) == 1);
    empty->board.ownership.exclusive_release(&empty->board, cookie);
    free(empty);
    (void)f;
}

/* 8. resources() tells three different failures apart, and only reports
 *    retention when the ledger holds two complete, sane measurements. */
static void rail_record(K60RailRecord *r, uint32_t id, uint32_t level,
    unsigned slot, unsigned complete, unsigned valid, const char *missing,
    const char *why)
{
    memset(r, 0, sizeof *r);
    r->resource_id = id;
    r->address = complete ? id : 0;
    r->level = level;
    r->tcs_slot = slot;
    r->complete = complete;
    r->valid = valid;
    r->missing = missing;
    r->why = why;
}

static void scenario_rails_three_state(void)
{
    Fixture *f = malloc(sizeof *f);
    K60RailRecord lcx, lmx;
    uint32_t epoch = 0;
    void *cookie = NULL;

    CHECK(f != NULL);
    start("resources separates never-measured, missing and invalid rails");
    build(f, 1, 0, 0);
    CHECK(f->board.ownership.exclusive(&f->board, &pinned, &epoch, &cookie) == K60BoardOk);
    CHECK(f->board.ownership.stopped(&f->board, cookie) == 1);
    /* A lease with no ledger at all is 'never measured', not 'rails absent'. */
    CHECK(k60_rail_ledger() == NULL);
    CHECK(f->board.ownership.resources(&f->board, cookie) == K60BoardUnsupported);
    CHECK(f->board.resources == 0);
    /* A ledger that exists but has an incomplete rail is a different answer:
     * the field that stopped the read must be named, and retention is still
     * not reported. */
    rail_record(&lcx, 0x30010u, 0, 0, 0, 0, "tcs slot", NULL);
    rail_record(&lmx, 0x31000u, 0x8u, 4, 1, 1, NULL, NULL);
    k60_rail_ledger_store(0x20700u, &lcx, &lmx);
    CHECK(k60_rail_ledger() != NULL);
    CHECK(f->board.ownership.resources(&f->board, cookie) == K60BoardUnsupported);
    CHECK(f->board.resources == 0);
    /* Complete but self-inconsistent is the third answer, and it must not be
     * reported with the same wording as a missing field. */
    rail_record(&lcx, 0x30010u, 0, 3, 1, 0, NULL, "level read back as 0");
    k60_rail_ledger_store(0x20700u, &lcx, &lmx);
    CHECK(f->board.ownership.resources(&f->board, cookie) == K60BoardUnsupported);
    CHECK(f->board.resources == 0);
    /* Only two complete, valid measurements report inherited retention. */
    rail_record(&lcx, 0x30010u, 0x10u, 3, 1, 1, NULL, NULL);
    k60_rail_ledger_store(0x20700u, &lcx, &lmx);
    CHECK(f->board.ownership.resources(&f->board, cookie) == K60BoardOk);
    CHECK(f->board.resources == 1 && f->board.last_rc == K60BoardOk);
    /* The grant still needs the lease: the ledger alone is not authority. */
    CHECK(f->board.ownership.resources(&f->board, NULL) == K60BoardNoLease);
    /* Releasing drops the flag, not the measurement. */
    f->board.ownership.resources_release(&f->board, cookie);
    CHECK(f->board.resources == 0);
    CHECK(k60_rail_ledger() != NULL);
    f->board.ownership.exclusive_release(&f->board, cookie);
    free(f);
}

int main(void)
{
    static Fixture base, second;
    build(&base, 1, 0, 0);
    build(&second, 1, 0, 0);
    scenario_available_is_free(&base);
    scenario_exclusive_rolls_back(&base);
    scenario_stopped_survives_release(&base);
    scenario_scm_lock_not_reentrant(&base, &second);
    scenario_live_without_resources(&base);
    scenario_stopped_needs_evidence(&base);
    scenario_install_turns_available_on();
    scenario_rails_three_state();
    /* The report line is a diagnostic, not a proof: it must not crash. */
    k60_adsp_board_report(&base.board);
    printf("TESTS OK board-ownership: %u scenarios\n", cases);
    return 0;
}
