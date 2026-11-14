/* SPDX-License-Identifier: BSD-2-Clause-Patent
 *
 * The VA and TX macro clock gates, as the nine read-modify-writes the
 * reference performs before the SoundWire master is opened (S:PongWcd938.h:84-86).
 *
 * Why a table and not nine lines: these registers are read-modify-write over
 * reset values this project has never observed on K60 (W:SOUNDWIRE.md §6 says
 * so in as many words). Keeping the nine steps as data lets the boot log print
 * what each one read and wrote, so the first on-device run answers the question
 * "was the reset value what the reference assumed" instead of hiding it.
 *
 * The two macros are separate mappings, so the callbacks are two pairs. Step
 * order is load-bearing: VA is enabled before TX, and the SWR_CONTROL pair is
 * set and then cleared inside VA, which is what starts the frame generator.
 *
 * Nothing here waits, for the same reason as the other three machines.
 *
 *   S  /mnt/e/k60-work/references/pong-power/PongWcd938.h:84-86
 *   W  docs/research/audio/SOUNDWIRE.md §6
 */
#ifndef PONG_CODEC_MACRO_H
#define PONG_CODEC_MACRO_H

#include <stdbool.h>
#include <stdint.h>

#include "PongCodecPlan.h"

typedef struct {
	uint32_t (*read)(void *ctx, uint32_t reg);
	void (*write)(void *ctx, uint32_t reg, uint32_t value);
	void *ctx;
} PongCodecMacroWindow;

typedef struct {
	PongCodecMacroWindow va;   /* 0x033f0000 */
	PongCodecMacroWindow tx;   /* 0x03220000 */
} PongCodecMacroIo;

#define PONG_CODEC_MACRO_STEPS 9u

/* One step of the sequence: which macro, which register, and the bit surgery.
 * value = (old & ~clear) | set. */
typedef struct {
	unsigned tx;               /* 0 = VA macro, 1 = TX macro */
	uint32_t reg;
	uint32_t clear;
	uint32_t set;
} PongCodecMacroStep;

typedef struct {
	PongCodecMacroIo io;
	unsigned step;
	uint32_t old[PONG_CODEC_MACRO_STEPS];   /* what each step read */
	uint32_t now[PONG_CODEC_MACRO_STEPS];   /* what each step wrote */
	unsigned writes;
} PongCodecMacro;

/* Returns the table entry for a step, so the log and the test read the same
 * data the sequencer walks. False when the index is out of range. */
bool pong_codec_macro_plan(unsigned index, PongCodecMacroStep *out);

void pong_codec_macro_start(PongCodecMacro *m, const PongCodecMacroIo *io);

/* One step: read, compute, write. True while steps remain, false when done.
 * Stepping a finished or unconfigured sequencer is a no-op. */
bool pong_codec_macro_step(PongCodecMacro *m);

bool pong_codec_macro_done(const PongCodecMacro *m);

#endif /* PONG_CODEC_MACRO_H */
