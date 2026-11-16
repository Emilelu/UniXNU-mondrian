/* SPDX-License-Identifier: BSD-2-Clause-Patent
 *
 * Pure TLMM values for the four TERT TDM speaker pads.
 *
 * The device tree hands the audio driver a pinctrl group (tert_tdm_pinctrl)
 * but no consumer of that group exists on our side: XNU has no pinctrl
 * framework, so the audio driver has to write the pads itself. This header
 * turns the device-tree facts into the two words the driver writes, so the
 * host test can pin them before anything touches hardware.
 *
 * Facts and where they come from:
 *   L:5315-5378  active group, pins gpio121/122/123/124
 *                gpio121 = mi2s2_sck, output-low, 2 mA, bias-disable
 *                gpio123 = mi2s2_ws,  output-low, 2 mA, bias-disable
 *                gpio122 = mi2s2_data0 (input), 2 mA, bias-disable
 *                gpio124 = mi2s2_data1 (input), 2 mA, bias-disable
 *   P:pinctrl-sm8450.c:33   ctl_reg = REG_SIZE * id, io_reg = ctl + 4
 *   P:pinctrl-sm8450.c:1537 [121] = PINGROUP(121, mi2s2_sck, ...)
 *                          [122] = PINGROUP(122, mi2s2_data0, ...)
 *                          [123] = PINGROUP(123, mi2s2_ws, ...)
 *                          [124] = PINGROUP(124, mi2s2_data1, sec_mi2s, ...)
 *
 * The mux value is the index inside the pin's function list, and that list
 * always starts with msm_mux_gpio at index 0, so mi2s2_* is function 1 on all
 * four pads (sec_mi2s on gpio124 is index 2 and is not used here).
 *
 * Register word layout (P:PongAudioRegs.h:35-36):
 *   CFG [1:0] pull, [5:2] function, [8:6] drive, [9] output enable
 *   IO  bit0 input level, bit1 output level
 * Drive strength is encoded as (mA / 2) - 1, so 2 mA is field value 0.
 */
#ifndef PONG_AUDIO_TLMM_H
#define PONG_AUDIO_TLMM_H

#include <stdbool.h>
#include <stdint.h>

#include "PongAudioPlan.h"

/* Pin order used by every table, log line and test below. */
enum {
	PongAudioTdmSck = 0,
	PongAudioTdmWs = 1,
	PongAudioTdmDin = 2,
	PongAudioTdmDout = 3,
	PongAudioTdmPinCount = 4
};

#define PONG_AUDIO_TDM_FN_MI2S2	1u	/* funcs[1]: mi2s2_sck/ws/data0/data1 */
#define PONG_AUDIO_TDM_DRIVE_MA		2u	/* L:active config drive-strength <2> */

/* gpio number of one TERT TDM pad; 0xffffffff means "no such pin". */
static inline uint32_t
pong_audio_tdm_gpio(unsigned pin)
{
	switch (pin) {
	case PongAudioTdmSck:
		return 121u;
	case PongAudioTdmWs:
		return 123u;
	case PongAudioTdmDin:
		return 122u;
	case PongAudioTdmDout:
		return 124u;
	default:
		return 0xffffffffu;
	}
}

/* The AP drives the bit clock and the word select; the two data pins are
 * inputs as far as the pad is concerned even though DIN carries RX data. */
static inline bool
pong_audio_tdm_is_output(unsigned pin)
{
	return pin == PongAudioTdmSck || pin == PongAudioTdmWs;
}

/* CFG word: no pull, mi2s2 function, 2 mA, output enable only on sck/ws. */
static inline uint32_t
pong_audio_tdm_cfg(unsigned pin)
{
	return pong_audio_pad_config(0u, PONG_AUDIO_GPIO_PULL_NONE,
	    PONG_AUDIO_TDM_FN_MI2S2, PONG_AUDIO_TDM_DRIVE_MA,
	    pong_audio_tdm_is_output(pin));
}

/* IO word: the clock and word select idle low (output-low in the active
 * group), and the data pads are inputs, so the output bit stays clear. */
static inline uint32_t
pong_audio_tdm_io(unsigned pin)
{
	(void)pin;
	return 0u;
}

static inline uint32_t
pong_audio_tdm_pad_phys(unsigned pin)
{
	return pong_audio_pad_phys(pong_audio_tdm_gpio(pin));
}

static inline uint32_t
pong_audio_tdm_io_phys(unsigned pin)
{
	return pong_audio_tdm_pad_phys(pin) + PONG_AUDIO_GPIO_IO;
}

/* Speaker switch: gpio52, active high. L:13329 spksw-gpio <0x3c 0x34 0x00>;
 * mixer_paths_waipio_mtp.xml:2132 sets aw882xx_spk_sw_gpio_switch to 1 on the
 * speaker path, and aw882xx.c:1711-1717 requests the line low at probe. */
#define PONG_AUDIO_SPKSW_ACTIVE_HIGH 1u

static inline uint32_t
pong_audio_spksw_cfg(uint32_t current)
{
	return pong_audio_pad_config(current, PONG_AUDIO_GPIO_PULL_NONE,
	    PONG_AUDIO_GPIO_FN_GPIO, 2u, true);
}

static inline uint32_t
pong_audio_spksw_io(bool on)
{
	return on ? 2u : 0u;
}
#endif /* PONG_AUDIO_TLMM_H */
