/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/* Offline check of the peripheral vote ownership and reference counts. No
 * rail is touched: the module is pure bookkeeping and has no caller yet. */
#include <stdio.h>
#include <string.h>
#include "../../drivers/PongPower/K60PowerVotePlan.h"

static unsigned failures, checks;

static void check(const char *name, long got, long want)
{
    ++checks;
    if (got != want) {
        ++failures;
        printf("FAIL %s: got %ld want %ld\n", name, got, want);
    }
}

static void check_text(const char *name, const char *got, const char *want)
{
    ++checks;
    if (!got || strcmp(got, want)) {
        ++failures;
        printf("FAIL %s: got %s want %s\n", name, got ? got : "(null)", want);
    }
}

int main(void)
{
    K60VoteState state;
    enum k60_vote_step steps[3];

    k60_vote_reset(&state);
    check("reset count", k60_vote_count(&state, 3), 0);
    check("reset mode", k60_vote_mode(&state, 3), K60VoteFree);
    check("reset held", k60_vote_held_by(&state, 3, 1), 0);

    check("shared owner1", k60_vote_acquire(&state, 3, 1, K60VoteShared), 0);
    check("count 1", k60_vote_count(&state, 3), 1);
    check("owner1 held", k60_vote_held_by(&state, 3, 1), 1);
    check("owner2 not held", k60_vote_held_by(&state, 3, 2), 0);
    check("mode shared", k60_vote_mode(&state, 3), K60VoteShared);
    check("duplicate claim", k60_vote_acquire(&state, 3, 1, K60VoteShared), -3);
    check("count after duplicate", k60_vote_count(&state, 3), 1);

    check("shared owner2", k60_vote_acquire(&state, 3, 2, K60VoteShared), 0);
    check("count 2", k60_vote_count(&state, 3), 2);
    check("exclusive owner3 refused", k60_vote_acquire(&state, 3, 3, K60VoteExclusive), -2);
    check("duplicate wins over mode", k60_vote_acquire(&state, 3, 1, K60VoteExclusive), -3);
    check("exclusive owner4 refused", k60_vote_acquire(&state, 3, 4, K60VoteExclusive), -2);
    check("count still 2", k60_vote_count(&state, 3), 2);
    check("release owner1", k60_vote_release(&state, 3, 1), 0);
    check("owner1 bit cleared", k60_vote_held_by(&state, 3, 1), 0);
    check("owner2 still held", k60_vote_held_by(&state, 3, 2), 1);
    check("count 1 after release", k60_vote_count(&state, 3), 1);
    check("mode still shared", k60_vote_mode(&state, 3), K60VoteShared);
    check("last release", k60_vote_release(&state, 3, 2), 1);
    check("count 0", k60_vote_count(&state, 3), 0);
    check("mode free", k60_vote_mode(&state, 3), K60VoteFree);
    check("release unheld", k60_vote_release(&state, 3, 2), -1);

    check("exclusive owner5", k60_vote_acquire(&state, 4, 5, K60VoteExclusive), 0);
    check("mode exclusive", k60_vote_mode(&state, 4), K60VoteExclusive);
    check("shared owner6 refused", k60_vote_acquire(&state, 4, 6, K60VoteShared), -2);
    check("exclusive owner6 refused", k60_vote_acquire(&state, 4, 6, K60VoteExclusive), -2);
    check("exclusive release last", k60_vote_release(&state, 4, 5), 1);

    check("owner 0", k60_vote_acquire(&state, 5, 0, K60VoteShared), 0);
    check("owner 0 held", k60_vote_held_by(&state, 5, 0), 1);
    check("owner 31", k60_vote_acquire(&state, 5, 31, K60VoteShared), 0);
    check("owner 31 held", k60_vote_held_by(&state, 5, 31), 1);
    check("count 2 boundaries", k60_vote_count(&state, 5), 2);
    check("release owner 0", k60_vote_release(&state, 5, 0), 0);
    check("release owner 31", k60_vote_release(&state, 5, 31), 1);

    check("resource 15", k60_vote_acquire(&state, 15, 1, K60VoteShared), 0);
    check("resource 16 rejected", k60_vote_acquire(&state, 16, 1, K60VoteShared), -1);
    check("owner 32 rejected", k60_vote_acquire(&state, 15, 32, K60VoteShared), -1);
    check("null acquire", k60_vote_acquire(0, 0, 0, K60VoteShared), -1);
    check("null release", k60_vote_release(0, 0, 0), -1);
    check("free mode rejected", k60_vote_acquire(&state, 6, 1, K60VoteFree), -1);
    check("null count", k60_vote_count(0, 0), 0);
    check("null mode", k60_vote_mode(0, 0), K60VoteFree);
    check("null held", k60_vote_held_by(0, 0, 0), 0);

    memset(steps, 0, sizeof steps);
    check("step count", k60_vote_release_steps(steps, 3), K60VoteStepCount);
    check("step 0", steps[0], K60VoteStopDma);
    check("step 1", steps[1], K60VoteMaskIrq);
    check("step 2", steps[2], K60VoteDropVote);
    check("tight steps", k60_vote_release_steps(steps, 2), 0);
    check("null steps", k60_vote_release_steps(0, 3), 0);
    check_text("name stop dma", k60_vote_step_name(K60VoteStopDma), "stop-dma");
    check_text("name mask irq", k60_vote_step_name(K60VoteMaskIrq), "mask-irq");
    check_text("name drop vote", k60_vote_step_name(K60VoteDropVote), "drop-vote");
    check_text("name unknown", k60_vote_step_name((enum k60_vote_step)99), "unknown");

    k60_vote_reset(&state);
    check("reset clears resource 15", k60_vote_count(&state, 15), 0);
    check("reset clears mode", k60_vote_mode(&state, 4), K60VoteFree);

    printf("TESTS %s %u checks (%u failure%s)\n", failures ? "FAILED" : "OK",
        checks, failures, failures == 1 ? "" : "s");
    return failures != 0;
}
