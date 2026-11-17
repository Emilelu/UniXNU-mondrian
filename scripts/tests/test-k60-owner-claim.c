/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
#include "test-k60-owner-fixture.h"
static OwnerFixture f;

/* Count the real SMEM allocator, not a fixture-derived approximation. The host
 * link uses --wrap=k60_smem_alloc; reset after synthetic remote-item setup. */
#include "K60AdspBoard.h"
#include "K60AdspRouteA.h"
/* The claim test is about the production owner engine and its refusal path;
 * it does not provide physical AOSS/TCS windows, so Route A must fail here. */
int k60_adsp_route_a_acquire(const K60RouteAIo *io, K60RouteAResult *out)
{
    (void)io; (void)out;
    return -1;
}
int k60_adsp_startup_claim(unsigned owner);
static unsigned alloc_calls, board_maps, board_unmaps;
static int board_resource_rc;
static K60AdspBoard board;
int __real_k60_smem_alloc(const K60Smem *, const K60SmemPartition *, uint16_t, uint32_t,
    uint32_t *, uint32_t *);
int __wrap_k60_smem_alloc(const K60Smem *s, const K60SmemPartition *p, uint16_t id,
    uint32_t bytes, uint32_t *at, uint32_t *n)
{
    ++alloc_calls;
    return __real_k60_smem_alloc(s, p, id, bytes, at, n);
}
static int board_map(void *ctx, uint64_t physical, size_t bytes, unsigned flags,
    volatile uint8_t **out)
{
    OwnerFixture *x = ctx;
    CHECK(physical == x->config.smem_base && bytes == FX_SMEM_BYTES);
    CHECK(flags == K60_ADSP_BOARD_MAP_FLAGS && out && !*out);
    ++board_maps; *out = fx_bytes(x); return 0;
}
static void board_unmap(void *ctx, volatile uint8_t *base, size_t bytes)
{
    CHECK(base == fx_bytes(ctx) && bytes == FX_SMEM_BYTES); ++board_unmaps;
}
static int board_exclusive(void *ctx, const K60BatteryConfig *c, uint32_t *epoch, void **cookie)
{
    OwnerFixture *x = ctx; ++x->exclusive_calls;
    return board.ownership.exclusive(&board, c, epoch, cookie);
}
static void board_release(void *ctx, void *cookie)
{
    OwnerFixture *x = ctx; ++x->release_calls;
    board.ownership.exclusive_release(&board, cookie);
}
static int board_resources(void *ctx, void *cookie)
{
    OwnerFixture *x = ctx; ++x->resources_calls;
    board_resource_rc = board.ownership.resources(&board, cookie);
    return board_resource_rc;
}
static int board_stopped(void *ctx, void *cookie)
{
    OwnerFixture *x = ctx; ++x->stopped_calls;
    return board.ownership.stopped(&board, cookie);
}
static void board_resources_release(void *ctx, void *cookie)
{
    OwnerFixture *x = ctx; ++x->resources_release_calls;
    board.ownership.resources_release(&board, cookie);
}
static int board_live(void *ctx, void *cookie, uint32_t epoch)
{
    OwnerFixture *x = ctx; ++x->live_calls;
    return board.ownership.live(&board, cookie, epoch);
}
static void production_board_refusal(void)
{
    static uint8_t original[FX_SMEM_BYTES];
    fx_case(&f, "real board refusal stops production acquire before every mutation");
    /* Remote is stopped. Otherwise a stopped-proof failure could mask a broken
     * resources callback and falsely make this a passing negative test. */
    fx_put(&f, f.remote_offset + 16, 0);
    fx_put(&f, f.remote_offset + 36, 0);
    memcpy(original, f.memory, sizeof original);
    K60AdspBoardIo io = {K60_ADSP_BOARD_VERSION, sizeof io, board_map, board_unmap, &f};
    CHECK(!k60_adsp_board_init(&board, &io));
    CHECK(k60_adsp_startup_claim(1u) == 1);
    CHECK(k60_adsp_startup_claim(2u) == 0);
    f.ops.exclusive = board_exclusive; f.ops.exclusive_release = board_release;
    f.ops.resources = board_resources; f.ops.resources_release = board_resources_release;
    f.ops.stopped = board_stopped; f.ops.live = board_live;
    alloc_calls = board_maps = board_unmaps = 0;
    CHECK(!k60_adsp_owner_install(&f.ops, &f));
    CHECK(k60_adsp_owner_acquire(&f.config, &f.wrapper_lease) == K60_ADSP_OWNER_UNAVAILABLE);
    CHECK(board_resource_rc == K60BoardUnsupported);
    CHECK(f.reader_calls == 1 && f.exclusive_calls == 1 && f.resources_calls == 1);
    CHECK(f.stopped_calls == 1 && f.close_calls == 1 && f.release_calls == 1);
    CHECK(f.owner->phase == K60OwnerFailed && !f.owner->evidence && !f.owner->resources_held);
    CHECK(!board.resources && board.last_rc == K60BoardUnsupported);
    CHECK(!board.leased && !board.mapped && board_maps == 1 && board_unmaps == 1);
    /* The board's read-only exclusion window is expected; map_smem below is
     * the later writable owner mapping, which must never be acquired. */
    CHECK(!f.map_calls && !f.unmap_calls && !alloc_calls && !f.allocations);
    CHECK(!f.lock_calls && !f.unlock_calls);
    CHECK(!f.init_calls && !f.mem_calls && !f.load_calls && !f.auth_calls);
    CHECK(!f.ready_calls && !f.shutdown_calls && !f.resources_release_calls);
    CHECK(fx_zero(&f.wrapper_lease, sizeof f.wrapper_lease));
    CHECK(!memcmp(original, f.memory, sizeof original));
    CHECK(k60_adsp_owner_publish(&f.wrapper_lease, &f.publish, &f) == K60PublishPasFailed);
    CHECK(!f.root_calls && !f.exists_calls && !f.commit_calls && !f.property_writes);
    /* A refused acquisition cannot be retried or turned into a lease. */
    CHECK(k60_adsp_owner_acquire(&f.config, &f.wrapper_lease) == K60_ADSP_OWNER_UNAVAILABLE);
    CHECK(f.resources_calls == 1 && !alloc_calls && !f.map_calls && !f.auth_calls);
    CHECK(!memcmp(original, f.memory, sizeof original));
    printf("TESTS OK real-board refusal: map_smem=0 alloc=0 init=0 mem=0 load=0 auth=0 publish=0\n");
}

static void rejected(void)
{
    CHECK(k60_owner_claim(&f.session, &f.config, &f.ops, &f) == K60_ADSP_OWNER_UNAVAILABLE);
    fx_zero_lease(&f); CHECK(!f.map_calls && !f.lock_calls && !f.auth_calls && !f.property_writes);
    fx_reported(&f, 1, K60_ADSP_OWNER_UNAVAILABLE);
}
int main(void)
{
    fx_case(&f, "claim keeps all ownership evidence private"); fx_claim(&f);
    CHECK(f.session.phase == K60OwnerClaimed && f.session.completed == 1);
    CHECK(f.session.evidence == (K60AdspResourcesHeld | K60AdspGlinkExclusive));
    CHECK(f.session.image_plan.prefix_bytes == FX_PREFIX && f.session.image_plan.hash_bytes == FX_HASH);
    CHECK(f.session.image_plan.count == 1 && f.session.image_plan.segment[0].source_is_piece == 1);
    CHECK(f.session.epoch == f.epoch && f.session.cookie == &f); fx_zero_lease(&f);
    CHECK(f.map_calls == 1 && f.lock_calls == 1 && f.unlock_calls == 1);
    CHECK(!f.allocations && fx_get(&f, FX_PART + 12) == f.baseline_up);
    fx_reported(&f, 1, 0); k60_owner_abort(&f.session); fx_failed(&f);
    CHECK(!strcmp(f.cleanup, "UCRE"));

    fx_case(&f, "missing required callback fails before any mapping"); f.ops.load = NULL; rejected();
    CHECK(!f.available_calls && !f.reader_calls);

    fx_case(&f, "missing carrier reader fails before any mapping"); f.ops.image_reader = NULL; rejected();
    CHECK(!f.available_calls && !f.reader_calls);

    fx_case(&f, "ops ABI version must match"); ++f.ops.version; rejected();
    CHECK(!f.available_calls);

    fx_case(&f, "only true K60 resource tuple is accepted"); ++f.config.mutex_base; rejected();
    CHECK(!f.available_calls);

    fx_case(&f, "backend unavailable stops before opening image"); f.available_value = 0; rejected();
    fx_failed(&f); CHECK(f.available_calls == 1 && !f.reader_calls);

    fx_case(&f, "image reader failure is transactional"); f.reader_rc = -9; rejected();
    fx_failed(&f); CHECK(f.reader_calls == 1 && !f.close_calls && !f.exclusive_calls);

    fx_case(&f, "reader success without handle is rejected and closed"); f.bad_handle = 1; rejected();
    fx_failed(&f); CHECK(f.close_calls == 1 && !f.exclusive_calls);

    fx_case(&f, "bad Hexagon MDT rejected before exclusion or map"); f.mdt[18] = 0; rejected();
    fx_failed(&f); CHECK(f.close_calls == 1 && !f.exclusive_calls && !f.piece_calls);

    fx_case(&f, "short borrowed piece rejected during real MDT validation"); f.piece_short_on = 1; rejected();
    fx_failed(&f); CHECK(f.piece_calls == 1 && f.close_calls == 1 && !f.exclusive_calls);

    fx_case(&f, "exclusive failure closes image only"); f.exclusive_rc = -1; rejected();
    fx_failed(&f); CHECK(!strcmp(f.cleanup, "C") && !f.resources_calls && !f.release_calls);

    fx_case(&f, "resource failure releases exclusion after stopped proof"); f.resources_rc = -1; rejected();
    fx_failed(&f); CHECK(!strcmp(f.cleanup, "CE") && f.stopped_calls == 1);
    CHECK(!f.resources_release_calls);

    fx_case(&f, "running PAS is refused before SMEM mapping"); f.running = 1; rejected();
    CHECK(f.session.phase == K60OwnerPoisoned && f.session.reserved && f.session.resources_held);
    CHECK(f.session.image_open && !f.shutdown_calls && !f.release_calls && !f.close_calls);

    fx_case(&f, "SMEM map acquisition failure releases cleanly"); f.map_rc = -1;
    CHECK(k60_owner_claim(&f.session, &f.config, &f.ops, &f) == K60_ADSP_OWNER_UNAVAILABLE);
    fx_failed(&f); CHECK(f.map_calls == 1 && !f.unmap_calls && !f.lock_calls);
    CHECK(!strcmp(f.cleanup, "CRE"));

    fx_case(&f, "wrong SMEM mapping extent rejected before lock"); f.bad_mapping = 1;
    CHECK(k60_owner_claim(&f.session, &f.config, &f.ops, &f) == K60_ADSP_OWNER_UNAVAILABLE);
    fx_failed(&f); CHECK(f.unmap_calls == 1 && !f.lock_calls);

    fx_case(&f, "claim lock failure never unlocks an unowned mutex"); f.lock_fail_on = 1;
    CHECK(k60_owner_claim(&f.session, &f.config, &f.ops, &f) == K60_ADSP_OWNER_UNAVAILABLE);
    fx_failed(&f); CHECK(f.lock_calls == 1 && !f.unlock_calls && f.unmap_calls == 1);
    fx_case(&f, "unaligned SMEM base is unmapped before mutex or SMEM reads"); f.misaligned_map = 1;
    CHECK(k60_owner_claim(&f.session, &f.config, &f.ops, &f) == K60_ADSP_OWNER_UNAVAILABLE);
    fx_failed(&f); CHECK(f.map_calls == 1 && f.unmap_calls == 1 && !f.lock_calls && !f.unlock_calls);
    CHECK(!f.allocations && !strcmp(f.cleanup, "UCRE"));
    production_board_refusal();
    return fx_done("claim");
}
