/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#ifndef PONG_DSI_PANEL_H
#define PONG_DSI_PANEL_H

#include <stdint.h>

/*
 * K60 panel bring-up over the SM8475 DSI0 command FIFO.
 *
 * Call pong_panel_bringup() once, early in display startup (the panel must be
 * out of Sleep Out and in Display On before the first frame is scanned out,
 * otherwise the canvas has content but the panel stays black).
 */
extern "C" bool pong_panel_bringup(void);

/* 0..4095 (12 bit DCS 0x51); returns 0 on success. */
extern "C" int pong_panel_set_brightness(uint32_t level);

/* Switch the m11a timing group to 120 Hz once. 0 = switched; negative =
 * the DCS write failed; -100 = bring-up not complete. */
extern "C" int pong_panel_switch_120(void);

/* Last brightness written (0 when bring-up has not succeeded yet). */
extern "C" uint32_t pong_panel_brightness(void);

/* Refresh rate the panel is actually running, observed from the INTF1 TE/frame
 * counters (60 when no observation is available; 0 when the panel is down). */
extern "C" uint32_t pong_panel_refresh_hz(void);

/* Wire order for DCS 0x51: a 12 bit DBV, most significant byte first, which is
 * the order Android produces for this panel's bl-inverted-dbv. */
static inline void pong_panel_dbv_bytes(uint32_t level, uint8_t out[2])
{
	out[0] = (uint8_t)(level >> 8);
	out[1] = (uint8_t)level;
}

/* 0 = bring-up succeeded; negative = last failure code; -100 = not attempted. */
extern "C" int pong_panel_status(void);

/* After completed copies: bounded120s clock/power-guarded INTF1 inherited
 * count60->1 correction, one attempt independent of gprobe. gprobe=1 also
 * logs interface counters; post-write readback/transfer deltas are logged. */
extern "C" void pong_panel_sample(void);

#endif /* PONG_DSI_PANEL_H */
