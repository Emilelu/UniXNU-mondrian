/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* printf, the one delay primitive, and the ns/us constant it is scaled by. */
#ifndef PONG_STUB_SYS_SYSTM_H
#define PONG_STUB_SYS_SYSTM_H
#include <stdarg.h>
#include <stdint.h>
int printf(const char *format, ...);
/* V: xnu osfmk/kern/clock.h:327, delay_for_interval(uint32_t, uint32_t).
 * The 27 tree takes two uint32_t; this stub said uint64_t until 2026-11-20 and
 * so the host build could not have seen a width mismatch at the call site. */
void delay_for_interval(uint32_t interval, uint32_t scale_factor);
/* V: xnu osfmk/mach/clock_types.h:84, NSEC_PER_USEC 1000ull; kern/clock.h
 * includes that header, which is how the glue sees the constant. */
#define NSEC_PER_USEC 1000ull
#endif
