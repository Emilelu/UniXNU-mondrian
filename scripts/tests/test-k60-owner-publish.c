/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
#include "test-k60-owner-fixture.h"
static OwnerFixture f;
static void failed(int rc)
{
    CHECK(k60_owner_publish(&f.session, &f.publish, &f) == rc);
    fx_failed(&f); fx_reported(&f, 5, rc);
    CHECK(f.shutdown_calls == 1 && !strcmp(f.cleanup, "STUCRE"));
}
int main(void)
{
    fx_case(&f, "current-epoch success commits once and pins all resources"); fx_build(&f);
    CHECK(!k60_owner_publish(&f.session, &f.publish, &f));
    CHECK(f.session.phase == K60OwnerPublished && f.session.completed == 31u);
    CHECK(f.commit_calls == 1 && f.property_writes == 1 && !memcmp(f.property, f.session.blob, sizeof f.property));
    CHECK(f.session.lease.flags == 15u && f.session.lease.epoch == f.epoch);
    CHECK(f.session.reserved && f.session.resources_held && f.session.mapped && f.session.image_open);
    CHECK(!f.shutdown_calls && !f.unmap_calls && !f.close_calls && !f.resources_release_calls && !f.release_calls);
    fx_reported(&f, 5, 0);
    k60_owner_abort(&f.session);
    CHECK(f.session.phase == K60OwnerPublished && f.session.lease.token == &f.session);
    CHECK(!f.shutdown_calls && !f.unmap_calls && !f.close_calls && !f.resources_release_calls && !f.release_calls);

    fx_case(&f, "registry root absent returns -43 without property attempt"); fx_build(&f); f.root_value = 0;
    failed(-43); CHECK(f.root_calls == 1 && !f.exists_calls && !f.commit_calls && f.ready_calls == 1);

    fx_case(&f, "existing property returns -41 and never commits"); fx_build(&f); f.exists_value = 1;
    failed(-41); CHECK(f.exists_calls == 1 && !f.commit_calls && f.ready_calls == 1);

    fx_case(&f, "atomic duplicate commit race preserves -41"); fx_build(&f); f.commit_rc = K60PublishExists;
    failed(-41); CHECK(f.commit_calls == 1 && !f.property_writes);

    fx_case(&f, "property commit failure maps to property failure"); fx_build(&f); f.commit_rc = -7;
    failed(K60PublishPropertyFailed); CHECK(f.commit_calls == 1 && !f.property_writes);

    fx_case(&f, "lost exclusive ownership is rejected before second ready wait"); fx_build(&f); f.live_value = 0;
    failed(K60PublishPasFailed); CHECK(!f.commit_calls && f.ready_calls == 1);

    fx_case(&f, "stale lease epoch cannot publish current blob"); fx_build(&f); --f.session.lease.epoch;
    failed(K60PublishPasFailed); CHECK(!f.commit_calls);

    fx_case(&f, "ready callback failure at publication releases owner safely"); fx_build(&f); f.ready_rc = -1;
    failed(K60PublishNotReady); CHECK(f.ready_calls == 2 && !f.commit_calls);

    fx_case(&f, "remote restart mismatch between build and commit refuses lease"); fx_build(&f); f.ready_restart = 0;
    failed(K60PublishNotReady); CHECK(!f.commit_calls);

    fx_case(&f, "corrupt blob is rejected by actual consumer parser"); fx_build(&f); f.session.blob[0] ^= 1;
    failed(K60PublishBuildFailed); CHECK(!f.commit_calls);

    fx_case(&f, "valid blob for previous epoch is rejected"); fx_build(&f);
    fx_le32(f.session.blob + 16, f.epoch - 1);
    failed(K60PublishBuildFailed); CHECK(!f.commit_calls);

    fx_case(&f, "missing publication callback is rejected without dereference"); fx_build(&f); f.publish.commit = NULL;
    CHECK(k60_owner_publish(&f.session, &f.publish, &f) == K60PublishInvalid);
    CHECK(f.session.phase == K60OwnerBuilt && !f.shutdown_calls && !f.release_calls);
    CHECK(!f.root_calls && !f.commit_calls && f.session.lease.flags == 15u);

    fx_case(&f, "failure cleanup that cannot stop retains resources and clears lease"); fx_build(&f);
    f.root_value = 0; f.shutdown_rc = -1;
    CHECK(k60_owner_publish(&f.session, &f.publish, &f) == K60PublishNotReady);
    CHECK(f.session.phase == K60OwnerPoisoned && f.shutdown_calls == 1 && !f.property_writes);
    CHECK(f.session.reserved && f.session.resources_held && f.session.mapped && f.session.image_open);
    fx_zero_lease(&f); CHECK(!f.close_calls && !f.release_calls && !f.unmap_calls && !f.resources_release_calls);
    fx_reported(&f, 5, K60PublishNotReady);
    fx_case(&f, "commit callback reentrant abort and publish cannot release owner"); fx_build(&f);
    f.commit_reenter = 1;
    CHECK(!k60_owner_publish(&f.session, &f.publish, &f));
    CHECK(f.session.phase == K60OwnerPublished && f.commit_calls == 1 && f.property_writes == 1);
    CHECK(!f.shutdown_calls && !f.unmap_calls && !f.release_calls && !f.session.operation_busy);

    fx_case(&f, "stale stage entries cannot dismantle a built owner"); fx_build(&f);
    CHECK(k60_owner_prepare_pas1(&f.session) == K60_ADSP_OWNER_UNAVAILABLE);
    CHECK(k60_owner_auth_and_start(&f.session) == K60_ADSP_OWNER_UNAVAILABLE);
    CHECK(k60_owner_build_handoff(&f.session, &f.plan) == K60PublishBuildFailed);
    CHECK(f.session.phase == K60OwnerBuilt && f.session.completed == 15u && f.session.lease.flags == 15u);
    CHECK(!f.shutdown_calls && !f.unmap_calls && !f.release_calls && f.allocations == 3);

    fx_case(&f, "stale entries and duplicate publish preserve terminal resources"); fx_build(&f);
    CHECK(!k60_owner_publish(&f.session, &f.publish, &f));
    CHECK(k60_owner_prepare_pas1(&f.session) == K60_ADSP_OWNER_UNAVAILABLE);
    CHECK(k60_owner_auth_and_start(&f.session) == K60_ADSP_OWNER_UNAVAILABLE);
    CHECK(k60_owner_build_handoff(&f.session, &f.plan) == K60PublishBuildFailed);
    CHECK(k60_owner_publish(&f.session, &f.publish, &f) == K60PublishExists);
    k60_owner_abort(&f.session);
    CHECK(f.session.phase == K60OwnerPublished && f.session.completed == 31u && f.property_writes == 1);
    CHECK(!f.shutdown_calls && !f.unmap_calls && !f.release_calls);

    /* The wrapper is intentionally one-shot; these scenarios share its real
     * persistent owner, rather than resetting private production state. */
    fx_case(&f, "wrapper rejects missing reader before one successful install");
    f.ops.image_reader = NULL;
    CHECK(k60_adsp_owner_install(&f.ops, &f) == K60_ADSP_OWNER_UNAVAILABLE);
    f.ops.image_reader = fx_reader;
    CHECK(!k60_adsp_owner_install(&f.ops, &f));
    CHECK(k60_adsp_owner_install(&f.ops, &f) == K60_ADSP_OWNER_UNAVAILABLE);
    CHECK(!f.map_calls && !f.reader_calls);

    fx_name = "wrapper acquire returns current complete persistent lease"; ++fx_cases;
    { K60BatteryConfig temporary = f.config;
      CHECK(!k60_adsp_owner_acquire(&temporary, &f.wrapper_lease));
      memset(&temporary, 0xcc, sizeof temporary); }
    CHECK(f.wrapper_lease.flags == 15u && f.wrapper_lease.epoch == f.epoch);
    CHECK(f.wrapper_lease.token == f.owner && f.owner != &f.session && f.owner->completed == 15u);
    CHECK(f.owner->ops.ready == fx_ready && !k60_adsp_owner_revalidate(&f.wrapper_lease));
    CHECK(f.allocations == 3 && !strcmp(f.pas_trace, "IMCZA"));

    fx_name = "wrapper forged epoch and token are harmless refusals"; ++fx_cases;
    { K60AdspOwnerLease forged = f.wrapper_lease;
      --forged.epoch; CHECK(k60_adsp_owner_revalidate(&forged) == K60_ADSP_OWNER_UNAVAILABLE);
      CHECK(k60_adsp_owner_publish(&forged, &f.publish, &f) == K60PublishPasFailed);
      k60_adsp_owner_abort(&forged);
      forged = f.wrapper_lease; forged.token = &f.session;
      CHECK(k60_adsp_owner_revalidate(&forged) == K60_ADSP_OWNER_UNAVAILABLE);
      CHECK(k60_adsp_owner_publish(&forged, &f.publish, &f) == K60PublishPasFailed);
      k60_adsp_owner_abort(&forged); }
    CHECK(!f.shutdown_calls && !f.commit_calls && f.owner->phase == K60OwnerBuilt);

    fx_name = "wrapper duplicate acquire returns zero lease without side effects"; ++fx_cases;
    { K60AdspOwnerLease duplicate; memset(&duplicate, 0xa5, sizeof duplicate);
      CHECK(k60_adsp_owner_acquire(&f.config, &duplicate) == K60_ADSP_OWNER_UNAVAILABLE);
      CHECK(fx_zero(&duplicate, sizeof duplicate)); }
    CHECK(f.reader_calls == 1 && f.map_calls == 1 && f.init_calls == 1 && f.allocations == 3);
    CHECK(!k60_adsp_owner_revalidate(&f.wrapper_lease));

    fx_name = "wrapper commit reentry refuses abort publish and revalidate"; ++fx_cases;
    f.commit_reenter = 2;
    CHECK(!k60_adsp_owner_publish(&f.wrapper_lease, &f.publish, &f));
    CHECK(f.property_writes == 1 && f.commit_calls == 1 && f.owner->phase == K60OwnerPublished);
    CHECK(!f.shutdown_calls && !f.unmap_calls && !f.close_calls && !f.release_calls);

    fx_name = "wrapper published abort retains persistent config and resources"; ++fx_cases;
    k60_adsp_owner_abort(&f.wrapper_lease);
    CHECK(!k60_adsp_owner_revalidate(&f.wrapper_lease));
    CHECK(k60_adsp_owner_publish(&f.wrapper_lease, &f.publish, &f) == K60PublishExists);
    CHECK(f.owner->phase == K60OwnerPublished && f.owner->completed == 31u && f.owner->config.smem_base == f.config.smem_base);
    CHECK(!f.shutdown_calls && !f.unmap_calls && !f.close_calls && !f.resources_release_calls && !f.release_calls);
    return fx_done("publish");
}
