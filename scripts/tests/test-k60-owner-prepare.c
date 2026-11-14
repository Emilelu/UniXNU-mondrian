/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
#include "test-k60-owner-fixture.h"
static OwnerFixture f;
static void failed(void)
{
    CHECK(k60_owner_prepare_pas1(&f.session) == K60_ADSP_OWNER_UNAVAILABLE);
    fx_failed(&f); fx_reported(&f, 2, K60_ADSP_OWNER_UNAVAILABLE);
}
int main(void)
{
    fx_case(&f, "prepare allocates exactly three stopped host FIFOs"); fx_claim(&f);
    CHECK(!k60_owner_prepare_pas1(&f.session)); CHECK(f.session.phase == K60OwnerPrepared);
    CHECK(f.session.completed == 5 && !(f.session.completed & 2u));
    CHECK((f.session.evidence & K60AdspFreshHostFifos) && !(f.session.evidence & K60AdspAuthenticated));
    CHECK(f.allocations == 3 && fx_get(&f, FX_PART + 12) == f.baseline_up + 32 + 16 + 4096 + 16 + 4096 + 16);
    for (uint16_t id = 478; id <= 480; ++id) {
        uint32_t n = 0, want = id == 478 ? 32 : 4096; fx_item(&f, id, &n); CHECK(n == want);
    }
    CHECK(fx_get(&f, FX_PART + 12) > f.baseline_up);
    CHECK(!memcmp(fx_bytes(&f) + f.remote_offset, f.remote_before, sizeof f.remote_before));
    fx_zero_lease(&f); fx_reported(&f, 2, 0);

    fx_case(&f, "pre-existing host allocation blocks reuse even when zero"); fx_claim(&f);
    { K60Smem smem = {fx_bytes(&f), FX_SMEM_BYTES}; K60SmemPartition part; uint32_t off, n;
      CHECK(!k60_smem_partition(&smem, 0, 2, &part)); CHECK(!k60_smem_alloc(&smem, &part, 478, 32, &off, &n));
      f.baseline_up = fx_get(&f, FX_PART + 12); }
    failed(); CHECK(f.allocations == 0);

    fx_case(&f, "malformed SMEM partition fails without host allocation"); fx_claim(&f);
    fx_put(&f, FX_PART + 8, FX_PART_BYTES - 8); failed(); CHECK(f.allocations == 0);

    fx_case(&f, "bad partition free mark is rejected before allocation"); fx_claim(&f);
    fx_put(&f, FX_PART + 12, 31); failed(); CHECK(f.allocations == 0);

    fx_case(&f, "stopped proof is required before lock and allocator"); fx_claim(&f);
    f.running = 1;
    CHECK(k60_owner_prepare_pas1(&f.session) == K60_ADSP_OWNER_UNAVAILABLE); fx_zero_lease(&f);
    CHECK(f.lock_calls == 1 && f.session.phase == K60OwnerPoisoned);
    CHECK(!f.unmap_calls && !f.release_calls); fx_reported(&f, 2, K60_ADSP_OWNER_UNAVAILABLE);

    fx_case(&f, "prepare mutex acquisition failure does not unlock"); fx_claim(&f);
    f.lock_fail_on = 2; failed(); CHECK(f.lock_calls == 2 && f.unlock_calls == 1 && !f.allocations);

    fx_case(&f, "partial allocator failure is not rolled back or retryable"); fx_claim(&f);
    { uint32_t size = f.baseline_up + 16 + 32 + 16 + 4096 + 16 + 4096 - 8;
      fx_put(&f, FX_PART + 8, size); fx_put(&f, FX_PART + 16, size);
      fx_put(&f, FX_SMEM_BYTES - 4096 + 36, size); }
    failed(); CHECK(f.allocations == 2 && fx_get(&f, FX_PART + 12) > f.baseline_up);

    fx_case(&f, "incomplete epoch live lease fails before prepare lock"); fx_claim(&f);
    f.live_value = 0; failed(); CHECK(f.lock_calls == 1 && f.allocations == 0);

    fx_case(&f, "bad first allocator entry is rejected transactionally"); fx_claim(&f);
    fx_put(&f, FX_PART + 32, 443u << 16); failed(); CHECK(f.allocations == 0);

    fx_case(&f, "allocator refuses host desc collisions including stale zero item"); fx_claim(&f);
    { K60Smem smem = {fx_bytes(&f), FX_SMEM_BYTES}; K60SmemPartition part; uint32_t off, n;
      CHECK(!k60_smem_partition(&smem, 0, 2, &part)); CHECK(!k60_smem_alloc(&smem, &part, 480, 4096, &off, &n));
      memset(fx_bytes(&f) + off, 0, n); f.baseline_up = fx_get(&f, FX_PART + 12); }
    failed(); CHECK(f.allocations == 0);

    fx_case(&f, "failed prepare reports once and closes mapping and image"); fx_claim(&f);
    f.lock_fail_on = 2; failed(); CHECK(f.unmap_calls == 1 && f.close_calls == 1);
    CHECK(f.resources_release_calls == 1 && f.release_calls == 1);
    CHECK(!strcmp(f.cleanup, "UCRE"));
    return fx_done("prepare");
}
