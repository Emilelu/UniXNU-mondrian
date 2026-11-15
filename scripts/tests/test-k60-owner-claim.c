/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
#include "test-k60-owner-fixture.h"
static OwnerFixture f;

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
    return fx_done("claim");
}
