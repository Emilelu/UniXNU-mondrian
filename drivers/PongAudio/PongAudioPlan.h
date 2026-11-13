/* SPDX-License-Identifier: BSD-2-Clause-Patent
 *
 * Pure decision helpers for the K60 speaker-amplifier probe.
 *
 * Everything here is a plain function over numbers: no MMIO, no kernel
 * headers. That is deliberate - it lets the probe's decision logic be proven by
 * a host unit test (drivers/PongAudio/tests), which is the only local evidence
 * available while the ADSP is still blocked (eight-step step 4, "verify").
 *
 * Sources for every rule: see PongAudioRegs.h and docs/research/audio/AMPS.md.
 */
#ifndef PONG_AUDIO_PLAN_H
#define PONG_AUDIO_PLAN_H

#include <stdbool.h>
#include <stdint.h>

#include "PongAudioRegs.h"

/* Physical address of one TLMM pad's register block. The GPIO register block
 * sits at TLMM base + 0x100000, one 0x1000 block per pad
 * (S:PongAudio.cpp:120-129, same shape as the touch patch:137). */
static inline uint32_t
pong_audio_pad_phys(uint32_t gpio)
{
	return PONG_AUDIO_TLMM_PHYS + PONG_AUDIO_TLMM_GPIO_OFF +
	    PONG_AUDIO_GPIO_STRIDE * gpio;
}

/* Pad config word: preserve everything outside the documented 10-bit field,
 * and declare APPS ownership only when the pad's eGPIO-exists bit says so
 * (touch patch:148-166). drive_ma is rounded down to the 2 mA field step;
 * a value below 2 mA means "no drive" rather than a negative field. */
static inline uint32_t
pong_audio_pad_config(uint32_t current, uint32_t pull, uint32_t function,
    uint32_t drive_ma, bool output)
{
	uint32_t next = current & ~0x3ffu;

	next |= pull & 0x3u;
	next |= (function & 0xfu) << 2;
	next |= ((drive_ma / 2u) - (drive_ma >= 2u ? 1u : 0u)) << 6;
	if (output) {
		next |= 1u << 9;
	}
	if (current & PONG_AUDIO_GPIO_EGPIO_EXISTS) {
		next |= PONG_AUDIO_GPIO_APPS_CTRL;
	}
	return next;
}

static inline uint32_t
pong_audio_pad_function(uint32_t cfg)
{
	return (cfg >> 2) & 0xfu;
}

static inline bool
pong_audio_pad_output(uint32_t cfg)
{
	return (cfg & (1u << 9)) != 0u;
}

static inline bool
pong_audio_pad_out_high(uint32_t io)
{
	return (io & 2u) != 0u;
}

/* A branch clock runs when the hardware gating branch is active or the
 * clock-off bit is clear (clk-branch.c:50-59; TouchProbe.cpp:406 - requiring
 * CLK_OFF == 0 on its own is a false negative). */
static inline bool
pong_audio_cbcr_running(uint32_t value)
{
	return !(value & PONG_AUDIO_CBCR_CLK_OFF) ||
	    (value & PONG_AUDIO_CBCR_HWCG);
}

/* Which of the three one-page GCC windows holds an offset: 0 = RCG window,
 * 1 = CBCR window, 2 = vote window, -1 = outside all three. *delta receives
 * the offset inside the chosen window. Three windows are 48 KiB of the 8 MiB
 * kernel-wide io_submap (osfmk/arm/io_map.c:66), not Pong's 640 KiB block. */
static inline int
pong_audio_gcc_window(uint32_t offset, uint32_t *delta)
{
	if (offset >= PONG_AUDIO_GCC_RCG_WIN &&
	    offset < PONG_AUDIO_GCC_RCG_WIN + PONG_AUDIO_WINDOW_SIZE) {
		*delta = offset - PONG_AUDIO_GCC_RCG_WIN;
		return 0;
	}
	if (offset >= PONG_AUDIO_GCC_CBC_WIN &&
	    offset < PONG_AUDIO_GCC_CBC_WIN + PONG_AUDIO_WINDOW_SIZE) {
		*delta = offset - PONG_AUDIO_GCC_CBC_WIN;
		return 1;
	}
	if (offset >= PONG_AUDIO_GCC_VOTE_WIN &&
	    offset < PONG_AUDIO_GCC_VOTE_WIN + PONG_AUDIO_WINDOW_SIZE) {
		*delta = offset - PONG_AUDIO_GCC_VOTE_WIN;
		return 2;
	}
	return -1;
}

/* A DFS level usable as the I2C source: the always-on reference and no
 * divider, judged the way the touch bring-up does (touch patch:313-324). */
static inline bool
pong_audio_dfs_level_ok(uint32_t cfg)
{
	return ((cfg >> 8) & 7u) == 0u && ((cfg >> 12) & 3u) == 0u &&
	    (cfg & 31u) <= 1u;
}

/* An AW882xx read answers two bytes over GENI I2C: the first byte of the FIFO
 * word is the value's high byte (S:PongAudio.cpp:108-110; GeniI2c.h: "the bytes
 * read, first byte in bits 7:0"). */
static inline uint16_t
pong_audio_amp_value(uint32_t rx)
{
	return (uint16_t)(((rx & 0xffu) << 8) | ((rx >> 8) & 0xffu));
}

/* Chip id names (H:340-350). Anything else stays "unknown" on purpose: this
 * probe reports what answered, it never infers a part. */
static inline const char *
pong_audio_amp_name(uint16_t chip_id)
{
	switch (chip_id) {
	case 0x2113: return "AW88261";
	case 0x2013: return "AW88264";
	case 0x2032: return "AW88266";
	case 0x2049: return "AW88395";
	case 0x2055: return "AW88256";
	case 0x2066: return "AW88166";
	case 0x2071: return "AW88350";
	case 0x2183: return "AW88399";
	case 0x2308: return "AW88230";
	default: return "unknown";
	}
}

#endif /* PONG_AUDIO_PLAN_H */
