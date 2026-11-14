/* SPDX-License-Identifier: BSD-2-Clause-Patent
 *
 * The codec half's whole boot sequence as one machine: LPI pads, VA/TX macro
 * clock gates, controller probe, controller init, enumerate, identity.
 *
 * The four files next to this one each own one step and none of them waits.
 * Something has to own the order and the budget, and that is this file: it
 * walks the steps, spends the caller's poll budget on the reads, and stops at
 * the first thing that does not answer instead of pressing on into the next
 * register block. Pressing on is how the 2026-11-09 GENI hang happened (HR-02).
 *
 * Order is the reference's (S:PongWcd938.h:79-118) and it is not negotiable:
 * the pads carry the clock and data lines, the macro gates start the frame
 * generator, and only then can the controller answer a version read.
 *
 * The gate is inside start(): pong_codec_may_touch_lpass() needs the macro
 * vote, the DCODEC vote and the clock acknowledgement, all three from the
 * Lead's PAS1 path. Until they exist the caller passes false and gets
 * PongCodecProbeErrLpass without a single register access.
 *
 *   S  /mnt/e/k60-work/references/pong-power/PongWcd938.h:79-118
 *   W  docs/research/audio/SOUNDWIRE.md §5, §6, §8
 */
#ifndef PONG_CODEC_PROBE_H
#define PONG_CODEC_PROBE_H

#include <stdbool.h>
#include <stdint.h>

#include "PongCodecLpi.h"
#include "PongCodecMacro.h"
#include "PongCodecPlan.h"
#include "PongCodecSwr.h"

typedef struct {
	PongCodecLpiIo lpi;
	PongCodecMacroIo macro;
	PongSwrIo swr;
} PongCodecProbeIo;

/* The three step outcomes, plus Failed, matching the two state machines so a
 * caller can loop on one vocabulary. */
enum {
	PongCodecProbeRunning = 0,  /* did work; call again */
	PongCodecProbeWaiting = 1,  /* a read is outstanding; call again */
	PongCodecProbeDone = 2,
	PongCodecProbeFailed = 3
};

enum {
	PongCodecProbeOk = 0,
	PongCodecProbeErrLpass = 1,    /* the three LPASS votes are not in */
	PongCodecProbeErrLpi = 2,
	PongCodecProbeErrMacro = 3,
	PongCodecProbeErrSwr = 4,      /* probe/init/read refused or failed */
	PongCodecProbeErrTimeout = 5,  /* the poll budget ran out on a read */
	PongCodecProbeErrNotFound = 6, /* no slave reported the WCD938x id */
	PongCodecProbeErrIdentity = 7  /* the codec did not answer 0x50/0x51 */
};

/* Where the machine is. Exposed because the boot log prints it: "stopped at
 * stage 5" is worth more than "the codec probe failed". */
enum {
	PongCodecStageLpi = 0,
	PongCodecStageMacro = 1,
	PongCodecStageSwrProbe = 2,
	PongCodecStageSwrInit = 3,
	PongCodecStageSwrEnv = 4,
	PongCodecStageEnumerate = 5,
	PongCodecStageSlaveId = 6,
	PongCodecStageIdentity = 7,
	PongCodecStageFinished = 8
};

typedef struct {
	PongCodecProbeIo io;
	PongCodecLpi lpi;
	PongCodecMacro macro;
	PongSwr swr;
	unsigned stage;
	unsigned substep;        /* the two reads of one slave id, or of 0x50/0x51 */
	unsigned max_polls;      /* per read; the caller's budget, never ours */
	unsigned polls;          /* polls already spent on the outstanding read */
	unsigned read_pending;   /* a read we started and have not collected */
	unsigned slave;          /* 1..11, the slave being examined */
	uint8_t last;            /* the byte the last completed read returned */
	uint8_t identity_lo;     /* the first of the two identity bytes */
	unsigned found_slave;    /* 0 = none */
	uint64_t found_id;
	unsigned identity;       /* pong_swr_codec_identity(), valid at Done */
	uint8_t error;
	unsigned reads, timeouts;
} PongCodecProbe;

/* lpass_ready is pong_codec_may_touch_lpass()'s answer, passed in rather than
 * recomputed: the votes live in the Lead's power path, not here. max_polls is
 * how many times the caller is willing to come back for one answer; the
 * reference waits 5 ms per poll for up to 200 polls, but the boot path decides
 * that, so this file only counts. Returns 0, or -1 with error = ErrLpass when
 * the gate is shut or the callbacks are incomplete - in both cases nothing was
 * read or written. */
int pong_codec_probe_start(PongCodecProbe *p, const PongCodecProbeIo *io,
    bool lpass_ready, unsigned max_polls);

/* One unit of work: one LPI step, one macro step, one register access, or one
 * poll. Returns Running/Waiting/Done/Failed. Stepping a finished machine
 * returns Done and touches nothing; stepping a failed one returns Failed. */
int pong_codec_probe_step(PongCodecProbe *p);

static inline bool
pong_codec_probe_done(const PongCodecProbe *p)
{
	return p->stage == PongCodecStageFinished;
}

static inline bool
pong_codec_probe_failed(const PongCodecProbe *p)
{
	return p->error != PongCodecProbeOk;
}

#endif /* PONG_CODEC_PROBE_H */
