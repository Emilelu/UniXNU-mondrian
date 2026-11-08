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

/* 0..255; returns 0 on success. */
extern "C" int pong_panel_set_brightness(uint32_t level);

/* Last brightness written (0 when bring-up has not succeeded yet). */
extern "C" uint32_t pong_panel_brightness(void);

/* 0 = bring-up succeeded; negative = last failure code; -100 = not attempted. */
extern "C" int pong_panel_status(void);

#endif /* PONG_DSI_PANEL_H */
