/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
#include "test-k60-owner-fixture.h"
static OwnerFixture f;
static uint8_t snapshot[FX_SMEM_BYTES];
static void failed(int rc)
{
    CHECK(k60_owner_build_handoff(&f.session, &f.plan) == rc);
    fx_failed(&f); fx_reported(&f, 4, rc); CHECK(f.shutdown_calls == 1);
    CHECK(!(f.session.completed & 2u));
}
int main(void)
{
    fx_case(&f, "build reads real ready 443 and self-parses without SMEM mutation"); fx_start(&f);
    memcpy(snapshot, fx_bytes(&f), sizeof snapshot);
    CHECK(!(f.session.completed & 2u)); CHECK(!k60_owner_build_handoff(&f.session, &f.plan));
    CHECK(f.session.phase == K60OwnerBuilt && f.session.completed == 15u);
    CHECK(f.session.lease.flags == 15u && f.session.lease.epoch == f.epoch && f.session.lease.token == &f.session);
    CHECK(f.session.lease.version == K60_ADSP_OWNER_VERSION && f.session.lease.bytes == sizeof f.session.lease);
    CHECK(f.ready_calls == 1 && f.lock_calls == 4 && f.unlock_calls == 4 && f.allocations == 3);
    CHECK(!memcmp(snapshot, fx_bytes(&f), sizeof snapshot) && !f.property_writes);
    { K60AdspGlinkHandoff h; CHECK(!k60_adsp_handoff_parse(f.session.blob, sizeof f.session.blob, &f.config, &h));
      CHECK(h.epoch == f.epoch && h.flags == 15u && h.remote_restart_flag == 1);
      uint32_t n; CHECK(h.desc_offset == fx_item(&f, 478, &n) && h.desc_bytes == n);
      CHECK(h.tx_offset == fx_item(&f, 479, &n) && h.tx_bytes == n);
      CHECK(h.rx_offset == fx_item(&f, 480, &n) && h.rx_bytes == n); }
    fx_reported(&f, 4, 0);

    fx_case(&f, "required14 never returns lease or publishes a property"); fx_start(&f); f.plan.required = 14;
    failed(K60PublishBuildFailed); CHECK(!f.ready_calls && f.lock_calls == 2 && !f.commit_calls);

    fx_case(&f, "stale plan epoch rejected before readiness"); fx_start(&f); ++f.plan.epoch;
    failed(K60PublishBuildFailed); CHECK(!f.ready_calls);

    fx_case(&f, "missing public authentication fact cannot be inferred from completion"); fx_start(&f);
    f.session.evidence &= ~K60AdspAuthenticated; failed(K60PublishBuildFailed); CHECK(!f.ready_calls);

    fx_case(&f, "ready callback failure shuts down without discovery lock"); fx_start(&f); f.ready_rc = -1;
    failed(K60PublishNotReady); CHECK(f.lock_calls == 2);

    fx_case(&f, "ready callback cannot fabricate remote readiness"); fx_start(&f); f.remote_not_ready = 1;
    failed(K60PublishNotReady); CHECK(f.ready_calls == 1 && f.lock_calls == 3 && f.unlock_calls == 3);

    fx_case(&f, "missing remote 443 is not allocated while DSP runs"); fx_start(&f);
    fx_put(&f, FX_PART + 32, 442u << 16 | 0xa5a5u);
    failed(K60PublishNotReady); CHECK(f.allocations == 3);

    fx_case(&f, "ready callback size must match plan"); fx_start(&f); f.ready_bytes = 20;
    failed(K60PublishNotReady); CHECK(f.lock_calls == 2);

    fx_case(&f, "dirty descriptor refuses takeover"); fx_start(&f);
    { uint32_t n, off = fx_item(&f, 478, &n); fx_put(&f, off + 4, 1); }
    failed(K60PublishDirtyDescriptor);

    fx_case(&f, "corrupt live partition is rejected before builder"); fx_start(&f);
    fx_put(&f, FX_PART + 8, 0); failed(K60PublishPartitionFailed);

    fx_case(&f, "first build lock failure has no unowned unlock"); fx_start(&f); f.lock_fail_on = 3;
    failed(K60PublishLockFailed); CHECK(f.lock_calls == 3 && f.unlock_calls == 2);

    fx_case(&f, "final serialization lock failure releases discovery lock"); fx_start(&f); f.lock_fail_on = 4;
    failed(K60PublishLockFailed); CHECK(f.lock_calls == 4 && f.unlock_calls == 3);

    fx_case(&f, "real consumer parse failure cannot mint a lease"); fx_start(&f); f.corrupt_parse_on_lock = 4;
    failed(K60PublishBuildFailed); CHECK(f.lock_calls == 4 && f.unlock_calls == 4);

    fx_case(&f, "lost ownership after discovery fails before serialization"); fx_start(&f);
    f.live_fail_on = f.live_calls + 2; failed(K60PublishPasFailed); CHECK(f.lock_calls == 3);

    fx_case(&f, "lost ownership after self-parse still returns no lease"); fx_start(&f);
    f.live_fail_on = f.live_calls + 3; failed(K60PublishPasFailed); CHECK(f.lock_calls == 4);
    return fx_done("build");
}
