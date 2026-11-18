/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/*
 * Pure ownership and reference-count bookkeeping for K60 peripheral power
 * votes. The official power page asks for explicit ownership and reference
 * counts, and for dependent DMA and interrupts to stop before a resource is
 * released; this file models only that bookkeeping and the release order.
 *
 * No MMIO, no RPMh and no TCS writes: HR-01 keeps the RSC window off limits
 * and allows only a single read-only DRV-2 sample under four conditions, so a
 * vote here is a claim recorded by a driver, not a rail command. The module
 * has no caller yet; the host test pins the arithmetic.
 */
#ifndef K60_POWER_VOTE_PLAN_H
#define K60_POWER_VOTE_PLAN_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

#define K60_VOTE_RESOURCES 16u
#define K60_VOTE_OWNERS 32u

/* How a resource may be shared. A free resource takes the mode of its first
 * owner; a shared holder then coexists with other shared holders only, and an
 * exclusive holder keeps everyone else out until the last release. */
enum k60_vote_mode { K60VoteFree, K60VoteShared, K60VoteExclusive };

/* Release order the caller must follow before the vote is dropped: stop the
 * DMA that targets the resource, mask its interrupt, then release the vote.
 * The module cannot check the first two; it names the order so a caller and
 * its host test agree on it. */
enum k60_vote_step { K60VoteStopDma, K60VoteMaskIrq, K60VoteDropVote, K60VoteStepCount };

typedef struct {
    uint16_t counts[K60_VOTE_RESOURCES];
    uint32_t owners[K60_VOTE_RESOURCES];
    uint8_t modes[K60_VOTE_RESOURCES];
} K60VoteState;

void k60_vote_reset(K60VoteState *state);

/* Record owner's claim on resource. Returns 0 on success, -1 for a null state
 * or an out-of-range id, -2 when the resource's current mode keeps this owner
 * out (an exclusive holder already owns it, or a shared holder asks for an
 * exclusive claim), -3 when this owner already holds the resource. One owner
 * holds at most one claim, so count always equals the number of owner bits. */
int k60_vote_acquire(K60VoteState *state, unsigned resource, unsigned owner,
    enum k60_vote_mode mode);

/* Drop one claim. Returns 1 when that was the last claim (the caller may now
 * power the resource down, after the steps above), 0 while claims remain, -1
 * for a null state, a bad id or a claim this owner does not hold. */
int k60_vote_release(K60VoteState *state, unsigned resource, unsigned owner);

unsigned k60_vote_count(const K60VoteState *state, unsigned resource);
int k60_vote_held_by(const K60VoteState *state, unsigned resource, unsigned owner);
enum k60_vote_mode k60_vote_mode(const K60VoteState *state, unsigned resource);

/* The three release steps in order; returns K60VoteStepCount. */
unsigned k60_vote_release_steps(enum k60_vote_step *out, unsigned capacity);
const char *k60_vote_step_name(enum k60_vote_step step);

#ifdef __cplusplus
}
#endif
#endif /* K60_POWER_VOTE_PLAN_H */
