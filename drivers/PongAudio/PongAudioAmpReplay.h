/* SPDX-License-Identifier: BSD-2-Clause-Patent
 *
 * The ordered write plan for one AW88261: what to write, in what order, and
 * which registers cannot be written with the value the tuning file literally
 * contains.
 *
 * Why a plan and not a loop. Mainline's aw88261_dev_reg_update()
 * (M: aw88261.c:393-490) is not "write 57 pairs": four of them are special.
 *
 *   0x04 SYSCTRL   three bits (PWDN, AMPPD, HMUTE) must keep whatever the
 *                  hardware currently says, so the write needs a read first;
 *                  ULS_HMUTE is then forced on. Writing the ACF's 0x3240
 *                  literally would clear the amplifier's power-down state.
 *   0x08 I2SCTRL3  the transmit enable bit is cleared, whatever the file says.
 *   0x05 SYSCTRL2  carries the volume; mainline rewrites it after the table
 *                  with the mute volume, keeping the top six bits.
 *   0x50 VSNTM1    absent from the file and computed from the fuse reads.
 *
 * Everything else is a straight 3-byte I2C write of (register, value). Keeping
 * that decision in a pure function means the host test can pin every step of
 * the sequence, and the kernel file only moves bytes.
 *
 * Order is part of the data: registers latch against each other, so the plan
 * follows the file's order and appends the two computed writes at the end, the
 * same order mainline uses (table, then vcalb, then volume).
 *
 * Pure: no MMIO, no kernel headers.
 */
#ifndef PONG_AUDIO_AMP_REPLAY_H
#define PONG_AUDIO_AMP_REPLAY_H

#include <stdbool.h>
#include <stdint.h>

#include "PongAudioAcf.h"

/* M: aw88261.c:1056 + aw88261.h:385 a soft reset is a plain write of 0x55aa to
 * register 0, and the chip needs the documented settling time before the table
 * is loaded (M: aw88261.c:1056-1060). */
#define PONG_REPLAY_RESET_REG     0x00u
#define PONG_REPLAY_RESET_VALUE   0x55aau

/* M: aw88261.h:242-243, 387-395 volume is 10 bits: a 6-bit step count in dB
 * steps of 48 (six dB in eighths) and a 6-bit remainder; 720 is "muted". */
#define PONG_REPLAY_MUTE_VOL      (90u * 8u)
#define PONG_REPLAY_VOL_STEP      (6u * 8u)
#define PONG_REPLAY_VOL_MASK      0x03ffu
#define PONG_REPLAY_VOL_KEEP      0xfc00u

/* What the transport has to do for one step. */
enum {
	PongReplayWrite,    /* write *value as is */
	PongReplaySysctrl,  /* read 0x04, merge with pong_replay_sysctrl(), write */
	PongReplayTxOff,    /* *value already has the transmit enable bit cleared */
	PongReplayVcalb,    /* write pong_acf_vcalb()'s result */
	PongReplayVolume    /* read 0x05, write pong_replay_volume() of that */
};

/* One reset, one step per register pair, then vcalb and the volume. */
static inline uint32_t
pong_replay_steps(uint32_t pairs)
{
	return pairs + 3u;
}

/* The step at an index, or false when the index is past the plan or names a
 * register the pass must not write. *value is the value the transport should
 * write, except for PongReplaySysctrl (the file's literal, to be merged),
 * PongReplayVcalb and PongReplayVolume (computed by the transport). */
static inline bool
pong_replay_at(const uint16_t *profile, uint32_t pairs, uint32_t index,
    uint8_t *action, uint8_t *reg, uint16_t *value)
{
	uint16_t r, v;

	if (profile == 0 || index >= pong_replay_steps(pairs)) {
		return false;
	}
	if (index == 0u) {
		*action = PongReplayWrite;
		*reg = PONG_REPLAY_RESET_REG;
		*value = PONG_REPLAY_RESET_VALUE;
		return true;
	}
	if (index <= pairs) {
		r = profile[(index - 1u) * 2u];
		v = profile[(index - 1u) * 2u + 1u];
		/* The file never carries these two, but a hand-edited table must
		 * not be able to smuggle them into the pass. */
		if (r == PONG_ACF_REG_VSNTM1 || r >= PONG_ACF_REG_LIMIT) {
			return false;
		}
		*reg = (uint8_t)r;
		if (r == PONG_ACF_REG_SYSCTRL) {
			*action = PongReplaySysctrl;
			*value = v;
		} else if (r == PONG_ACF_REG_I2SCTRL3) {
			*action = PongReplayTxOff;
			*value = (uint16_t)(v & (uint16_t)~PONG_ACF_I2STXEN);
		} else {
			*action = PongReplayWrite;
			*value = v;
		}
		return true;
	}
	if (index == pairs + 1u) {
		*action = PongReplayVcalb;
		*reg = (uint8_t)PONG_ACF_REG_VSNTM1;
		*value = 0u;
		return true;
	}
	*action = PongReplayVolume;
	*reg = (uint8_t)PONG_ACF_REG_SYSCTRL2;
	*value = 0u;
	return true;
}

/* M: aw88261.c:420-434. PWDN, AMPPD and HMUTE come from the hardware, every
 * other bit from the file, and ULS_HMUTE is forced on. The read is not an
 * optimisation: without it the write would clear the power-down state that the
 * chip is in and start an amplifier that has no bit clock. */
static inline uint16_t
pong_replay_sysctrl(uint16_t acf_value, uint16_t hw_value)
{
	uint16_t v = (uint16_t)((acf_value & (uint16_t)~PONG_ACF_SYSCTRL_KEEP) |
	    (hw_value & PONG_ACF_SYSCTRL_KEEP));

	v &= (uint16_t)~PONG_ACF_SYSCTRL_ULS_HMUTE;
	v |= PONG_ACF_SYSCTRL_ULS_HMUTE;
	return v;
}

/* M: aw88261.h:387-395 DB_TO_REG_VAL. */
static inline uint16_t
pong_replay_db_to_reg(uint32_t db)
{
	return (uint16_t)(((db / PONG_REPLAY_VOL_STEP) << 6) +
	    (db % PONG_REPLAY_VOL_STEP));
}

/* M: aw88261.c:28-46 the volume write keeps the register's top six bits and
 * replaces the ten that carry the attenuation. */
static inline uint16_t
pong_replay_volume(uint16_t hw_sysctrl2)
{
	return (uint16_t)((pong_replay_db_to_reg(PONG_REPLAY_MUTE_VOL) &
	    PONG_REPLAY_VOL_MASK) | (hw_sysctrl2 & PONG_REPLAY_VOL_KEEP));
}

#endif /* PONG_AUDIO_AMP_REPLAY_H */
