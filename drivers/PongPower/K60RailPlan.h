/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/*
 * Pure ordering and rollback model for a K60 work-point transition. The
 * official power page asks for a work-point request plus a state readback,
 * with the target regulator, interconnect and thermal requirements applied in
 * a prescribed order (section 5, :108). This module models only the order and
 * the commit/rollback contract: it has no MMIO, no RPMh, no TCS writes and no
 * thermal sensor. A caller owns the actual register access and passes in
 * whether the thermal check allowed the move.
 *
 * Ordering rules:
 *   - raising a work point: regulator, interconnect, frequency, readback;
 *   - lowering a work point: frequency, interconnect, regulator, readback;
 *   - a frequency raise must not lower the voltage or the bandwidth;
 *   - when the frequency holds and voltage/bandwidth change, raises go
 *     first and drops follow in reverse order;
 *   - an upward move is refused unless thermal_ok is true.
 * The last confirmed point is the rollback target. Commit only after the
 * caller has read back and verified the target point.
 */
#ifndef K60_RAIL_PLAN_H
#define K60_RAIL_PLAN_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

/* One work point. khz and uv must be non-zero; bw may be zero when the
 * caller has no interconnect vote for this point. */
typedef struct {
    uint32_t khz;
    uint32_t uv;
    uint32_t bw;
} K60RailPoint;

enum k60_rail_stage {
    K60RailRegulator = 0,
    K60RailInterconnect,
    K60RailFrequency,
    K60RailReadback,
    K60RailStageCount
};

/* A step carries the complete target point, so a caller can apply the named
 * stage without remembering the other fields. */
typedef struct {
    enum k60_rail_stage stage;
    uint32_t khz;
    uint32_t uv;
    uint32_t bw;
} K60RailStep;

typedef struct {
    K60RailPoint confirmed;
} K60RailState;

/* Set the last confirmed point. A null state is ignored; a null or invalid
 * initial point clears the state to zero. */
void k60_rail_reset(K60RailState *state, const K60RailPoint *initial);

/* 1 when the point is non-null, khz > 0 and uv > 0. bw may be zero. */
int k60_rail_valid(const K60RailPoint *point);

/* Build the ordered steps from state->confirmed to target. Returns 0 on
 * success, -1 for a null argument, -2 when an upward move is refused by the
 * thermal gate, -3 when capacity is too small (count stays 0) and -4 for an
 * invalid point or a frequency raise that lowers voltage/bandwidth. On
 * success *count is the number of steps and always includes the readback. */
int k60_rail_plan(const K60RailState *state, const K60RailPoint *target,
    int thermal_ok, K60RailStep *out, unsigned capacity, unsigned *count);

/* Adopt target as the new confirmed point only when readback_ok is true.
 * Returns 0 on success, -1 for a null argument or a failed readback, -4 for
 * an invalid point. On failure the previous confirmed point is unchanged. */
int k60_rail_commit(K60RailState *state, const K60RailPoint *target,
    int readback_ok);

/* Build the steps that return from attempted to confirmed after a failed
 * readback. confirmed is the last known-good point and is never refused by
 * the thermal gate: it was already admitted. Returns 0 on success, -1 for a
 * null argument, -3 when capacity is too small (count stays 0) and -4 for an
 * invalid point or a faster confirmed point with less voltage/bandwidth. */
int k60_rail_rollback(const K60RailPoint *attempted,
    const K60RailPoint *confirmed, K60RailStep *out, unsigned capacity,
    unsigned *count);

const char *k60_rail_stage_name(enum k60_rail_stage stage);

#ifdef __cplusplus
}
#endif
#endif /* K60_RAIL_PLAN_H */
