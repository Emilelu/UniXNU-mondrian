/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
#include "K60PowerVotePlan.h"

void k60_vote_reset(K60VoteState *state)
{
    if (!state) return;
    for (unsigned i = 0; i < K60_VOTE_RESOURCES; ++i) {
        state->counts[i] = 0;
        state->owners[i] = 0;
        state->modes[i] = K60VoteFree;
    }
}

int k60_vote_acquire(K60VoteState *state, unsigned resource, unsigned owner,
    enum k60_vote_mode mode)
{
    if (!state || resource >= K60_VOTE_RESOURCES || owner >= K60_VOTE_OWNERS) return -1;
    if (mode != K60VoteShared && mode != K60VoteExclusive) return -1;
    const uint32_t bit = 1u << owner;
    if (state->owners[resource] & bit) return -3;
    const uint8_t current = state->modes[resource];
    if (state->counts[resource]) {
        if (current == K60VoteExclusive) return -2;
        if (mode == K60VoteExclusive) return -2;
    }
    state->counts[resource] = (uint16_t)(state->counts[resource] + 1);
    state->owners[resource] |= bit;
    if (!current) state->modes[resource] = (uint8_t)mode;
    return 0;
}

int k60_vote_release(K60VoteState *state, unsigned resource, unsigned owner)
{
    if (!state || resource >= K60_VOTE_RESOURCES || owner >= K60_VOTE_OWNERS) return -1;
    const uint32_t bit = 1u << owner;
    if (!state->counts[resource] || !(state->owners[resource] & bit)) return -1;
    state->counts[resource] = (uint16_t)(state->counts[resource] - 1);
    state->owners[resource] &= ~bit;
    if (!state->counts[resource]) {
        state->owners[resource] = 0;
        state->modes[resource] = K60VoteFree;
        return 1;
    }
    return 0;
}

unsigned k60_vote_count(const K60VoteState *state, unsigned resource)
{
    if (!state || resource >= K60_VOTE_RESOURCES) return 0;
    return state->counts[resource];
}

int k60_vote_held_by(const K60VoteState *state, unsigned resource, unsigned owner)
{
    if (!state || resource >= K60_VOTE_RESOURCES || owner >= K60_VOTE_OWNERS) return 0;
    return (state->owners[resource] & (1u << owner)) != 0;
}

enum k60_vote_mode k60_vote_mode(const K60VoteState *state, unsigned resource)
{
    if (!state || resource >= K60_VOTE_RESOURCES) return K60VoteFree;
    return (enum k60_vote_mode)state->modes[resource];
}

unsigned k60_vote_release_steps(enum k60_vote_step *out, unsigned capacity)
{
    if (!out || capacity < K60VoteStepCount) return 0;
    out[0] = K60VoteStopDma;
    out[1] = K60VoteMaskIrq;
    out[2] = K60VoteDropVote;
    return K60VoteStepCount;
}

const char *k60_vote_step_name(enum k60_vote_step step)
{
    switch (step) {
    case K60VoteStopDma: return "stop-dma";
    case K60VoteMaskIrq: return "mask-irq";
    case K60VoteDropVote: return "drop-vote";
    default: return "unknown";
    }
}
