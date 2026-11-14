/* SPDX-License-Identifier: BSD-2-Clause-Patent
 *
 * The LPI pad and slew programming the codec half needs before any LPASS
 * macro or SoundWire register may be touched, as a step-at-a-time sequencer.
 *
 * Four pads carry the SoundWire clock and data lines (pins 0, 1, 2 and 14),
 * and the slew block holds two bits per pin. The reference writes all four
 * pads first and the slew register last (S:PongWcd938.h:80-82); doing it in
 * any other order leaves the clock line driving before its slew is set.
 *
 * Each step is one read and one write. Nothing here waits, for the same
 * reason as the two state machines next to it: the boot path owns the budget.
 *
 *   S  /mnt/e/k60-work/references/pong-power/PongWcd938.h:79-82
 *   W  docs/research/audio/SOUNDWIRE.md §5
 */
#ifndef PONG_CODEC_LPI_H
#define PONG_CODEC_LPI_H

#include <stdbool.h>
#include <stdint.h>

#include "PongCodecPlan.h"

/* The pads and the slew block are two different mappings (0x03440000 and
 * 0x034da000), so one pair of callbacks cannot serve both: register 0 of the
 * pinctrl block is pad 0, and register 0 of the slew block is the slew value.
 * Keeping them apart here is what stops a slew write from landing on pad 0. */
typedef struct {
	uint32_t (*read)(void *ctx, uint32_t reg);
	void (*write)(void *ctx, uint32_t reg, uint32_t value);
	void *ctx;                  /* LPI pinctrl block */
	uint32_t (*slew_read)(void *ctx, uint32_t reg);
	void (*slew_write)(void *ctx, uint32_t reg, uint32_t value);
	void *slew_ctx;             /* slew block */
} PongCodecLpiIo;

/* Four pads, then the slew register: five steps in that order. */
#define PONG_CODEC_LPI_STEPS 5u

typedef struct {
	PongCodecLpiIo io;
	unsigned step;              /* 0..3 pads, 4 slew, 5 done */
	uint32_t pad_old[4];        /* what each pad held before we wrote it */
	uint32_t pad_new[4];
	uint32_t slew_old, slew_new;
	unsigned writes;
} PongCodecLpi;

/* Records the callbacks and puts the sequencer on step 0. The caller decides
 * when to start; the LPI block is only reachable once the LPASS power and
 * clock votes are in, so pong_codec_may_touch_lpass() gates the call site. */
void pong_codec_lpi_start(PongCodecLpi *l, const PongCodecLpiIo *io);

/* Performs one step. Returns true when there is more to do, false when the
 * sequencer has finished. Calling it after it finished is a no-op that also
 * returns false, so a caller looping on the return value terminates. */
bool pong_codec_lpi_step(PongCodecLpi *l);

bool pong_codec_lpi_done(const PongCodecLpi *l);

#endif /* PONG_CODEC_LPI_H */
