/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* printf, the one delay primitive, and the ns/us constant it is scaled by. */
#ifndef PONG_STUB_SYS_SYSTM_H
#define PONG_STUB_SYS_SYSTM_H
#include <stdarg.h>
#include <stdint.h>
int printf(const char *format, ...);
/* V: xnu osfmk/kern/clock.h, delay_for_interval(uint64_t, uint64_t) */
void delay_for_interval(uint64_t interval, uint64_t scale);
#define NSEC_PER_USEC 1000ull
#endif
