/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
#include "test-k60-owner-fixture.h"
static OwnerFixture f;
static void failed(void)
{
    CHECK(k60_owner_auth_and_start(&f.session) == K60_ADSP_OWNER_UNAVAILABLE);
    fx_failed(&f); fx_reported(&f, 3, K60_ADSP_OWNER_UNAVAILABLE);
}
int main(void)
{
    fx_case(&f, "INIT metadata once then MEM COPY ZERO AUTH"); fx_prepare(&f);
    CHECK(!(f.session.evidence & K60AdspAuthenticated) && !(f.session.completed & 2u));
    CHECK(!k60_owner_auth_and_start(&f.session));
    CHECK(!strcmp(f.pas_trace, "IMCZA") && f.init_calls == 1 && f.mem_calls == 1);
    CHECK(f.load_calls == 1 && f.auth_calls == 1 && f.piece_calls == 2);
    CHECK(!memcmp(f.loaded, f.payload, 8) && fx_zero(f.loaded + 8, 16));
    CHECK(f.session.phase == K60OwnerStarted && f.session.evidence == 15u);
    CHECK(f.session.completed == 13u && !(f.session.completed & 2u));
    CHECK(f.lock_calls == 2 && f.unlock_calls == 2); fx_zero_lease(&f); fx_reported(&f, 3, 0);

    fx_case(&f, "INIT callback failure prevents MEM and AUTH"); fx_prepare(&f); f.init_rc = -1;
    failed(); CHECK(!strcmp(f.pas_trace, "I") && !f.mem_calls && !f.auth_calls && !f.shutdown_calls);
    CHECK(!strcmp(f.cleanup, "UCRE"));

    fx_case(&f, "MEM callback failure prevents COPY and AUTH"); fx_prepare(&f); f.mem_rc = -1;
    failed(); CHECK(!strcmp(f.pas_trace, "IM") && !f.load_calls && !f.auth_calls && !f.shutdown_calls);

    fx_case(&f, "piece must remain readable at load time"); fx_prepare(&f); f.piece_fail_on = 2;
    failed(); CHECK(f.piece_calls == 2 && !f.load_calls && !f.auth_calls && !f.shutdown_calls);

    fx_case(&f, "piece length cannot shrink between validation and load"); fx_prepare(&f); f.piece_short_on = 2;
    failed(); CHECK(!f.load_calls && !f.auth_calls && !f.shutdown_calls);

    fx_case(&f, "load failure cannot reach AUTH"); fx_prepare(&f); f.load_rc = -1;
    failed(); CHECK(!strcmp(f.pas_trace, "IMC") && !f.auth_calls && !f.shutdown_calls);

    fx_case(&f, "AUTH failure shuts down then proves stopped before release"); fx_prepare(&f); f.auth_rc = -1;
    failed(); CHECK(f.auth_calls == 1 && f.shutdown_calls == 1 && !f.running);
    CHECK(!strcmp(f.cleanup, "STUCRE"));
    { unsigned closes = f.close_calls; k60_owner_abort(&f.session); CHECK(f.close_calls == closes); }

    fx_case(&f, "failed AUTH with failed shutdown retains recovery resources"); fx_prepare(&f);
    f.auth_rc = -1; f.shutdown_rc = -1;
    CHECK(k60_owner_auth_and_start(&f.session) == K60_ADSP_OWNER_UNAVAILABLE);
    CHECK(f.session.phase == K60OwnerPoisoned && f.shutdown_calls == 1);
    CHECK(f.session.reserved && f.session.resources_held && f.session.mapped && f.session.image_open);
    fx_zero_lease(&f); CHECK(!f.unmap_calls && !f.close_calls && !f.resources_release_calls && !f.release_calls);
    CHECK(!strcmp(f.cleanup, "S"));
    k60_owner_abort(&f.session); CHECK(f.shutdown_calls == 1); fx_outside(&f);

    fx_case(&f, "shutdown success still requires independent stopped proof"); fx_prepare(&f);
    f.auth_rc = -1; f.stop_after_shutdown = 0;
    CHECK(k60_owner_auth_and_start(&f.session) == K60_ADSP_OWNER_UNAVAILABLE);
    CHECK(f.session.phase == K60OwnerPoisoned && !strcmp(f.cleanup, "ST"));
    fx_zero_lease(&f); CHECK(f.session.reserved && f.session.mapped && !f.release_calls);

    fx_case(&f, "lost exclusive lease after AUTH triggers shutdown cleanup"); fx_prepare(&f);
    f.lose_live_after_auth = 1; failed(); CHECK(f.shutdown_calls == 1 && !strcmp(f.cleanup, "STUCRE"));

    fx_case(&f, "lost lease before AUTH prevents any PAS callback"); fx_prepare(&f); f.live_value = 0;
    failed(); CHECK(!f.init_calls && !f.auth_calls && !f.shutdown_calls);

    fx_case(&f, "abort after started success shuts down and clears ownership"); fx_start(&f);
    k60_owner_abort(&f.session); fx_failed(&f);
    CHECK(!strcmp(f.cleanup, "STUCRE") && f.shutdown_calls == 1);
    return fx_done("auth");
}
