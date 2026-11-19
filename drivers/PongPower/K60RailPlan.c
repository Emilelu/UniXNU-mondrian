/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
#include "K60RailPlan.h"
#include <stddef.h>

int k60_rail_valid(const K60RailPoint *point)
{
    return point != NULL && point->khz > 0u && point->uv > 0u;
}

void k60_rail_reset(K60RailState *state, const K60RailPoint *initial)
{
    if (state == NULL) return;
    if (initial != NULL && k60_rail_valid(initial)) {
        state->confirmed = *initial;
    } else {
        state->confirmed.khz = 0;
        state->confirmed.uv = 0;
        state->confirmed.bw = 0;
    }
}

static void emit_step(K60RailStep *out, unsigned *count,
    enum k60_rail_stage stage, const K60RailPoint *target)
{
    out[*count].stage = stage;
    out[*count].khz = target->khz;
    out[*count].uv = target->uv;
    out[*count].bw = target->bw;
    (*count)++;
}

int k60_rail_plan(const K60RailState *state, const K60RailPoint *target,
    int thermal_ok, K60RailStep *out, unsigned capacity, unsigned *count)
{
    const K60RailPoint *from;
    unsigned khz_up, khz_down, uv_up, uv_down, bw_up, bw_down;
    unsigned need, n = 0;

    if (state == NULL || target == NULL || out == NULL || count == NULL) return -1;
    *count = 0;
    if (!k60_rail_valid(target) || !k60_rail_valid(&state->confirmed)) return -4;

    from = &state->confirmed;
    khz_up = target->khz > from->khz;
    khz_down = target->khz < from->khz;
    uv_up = target->uv > from->uv;
    uv_down = target->uv < from->uv;
    bw_up = target->bw > from->bw;
    bw_down = target->bw < from->bw;

    if (!khz_up && !khz_down && !uv_up && !uv_down && !bw_up && !bw_down) return 0;

    /* A faster point with less voltage or less bandwidth is not a valid
     * work point; refuse it before the thermal gate so the error is clear. */
    if (khz_up && (target->uv < from->uv || target->bw < from->bw)) return -4;
    if ((khz_up || uv_up || bw_up) && !thermal_ok) return -2;

    need = 1; /* readback */
    if (khz_up) {
        if (uv_up) need++;
        if (bw_up) need++;
        need++;
    } else if (khz_down) {
        need++;
        if (bw_up || bw_down) need++;
        if (uv_up || uv_down) need++;
    } else {
        if (uv_up) need++;
        if (bw_up) need++;
        if (bw_down) need++;
        if (uv_down) need++;
    }
    if (need > capacity) return -3;

    if (khz_up) {
        if (uv_up) emit_step(out, &n, K60RailRegulator, target);
        if (bw_up) emit_step(out, &n, K60RailInterconnect, target);
        emit_step(out, &n, K60RailFrequency, target);
    } else if (khz_down) {
        emit_step(out, &n, K60RailFrequency, target);
        if (bw_up || bw_down) emit_step(out, &n, K60RailInterconnect, target);
        if (uv_up || uv_down) emit_step(out, &n, K60RailRegulator, target);
    } else {
        /* Frequency holds: apply the raises first, then the drops in reverse
         * order, so the transient never asks for less than the confirmed
         * point. A single changed resource takes its own stage. */
        if (uv_up) emit_step(out, &n, K60RailRegulator, target);
        if (bw_up) emit_step(out, &n, K60RailInterconnect, target);
        if (bw_down) emit_step(out, &n, K60RailInterconnect, target);
        if (uv_down) emit_step(out, &n, K60RailRegulator, target);
    }
    emit_step(out, &n, K60RailReadback, target);
    *count = n;
    return 0;
}

int k60_rail_commit(K60RailState *state, const K60RailPoint *target,
    int readback_ok)
{
    if (state == NULL || target == NULL || !readback_ok) return -1;
    if (!k60_rail_valid(target)) return -4;
    state->confirmed = *target;
    return 0;
}

const char *k60_rail_stage_name(enum k60_rail_stage stage)
{
    switch (stage) {
    case K60RailRegulator: return "regulator";
    case K60RailInterconnect: return "interconnect";
    case K60RailFrequency: return "frequency";
    case K60RailReadback: return "readback";
    default: return "unknown";
    }
}
