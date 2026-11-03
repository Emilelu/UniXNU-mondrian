/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Minimal persistent console mirror. It does not touch VBAR, TTBR, the
 * framebuffer, scheduler state, IOKit, or storage. */
#ifndef PONG_RAMOOPS_CONSOLE_H
#define PONG_RAMOOPS_CONSOLE_H

#include <arm/caches_internal.h>
#include <machine/machine_routines.h>

#define PONG_RAMOOPS_PHYS_BASE 0xA7000000ULL
#define PONG_RAMOOPS_CONSOLE_BYTES 0x00200000U
#define PONG_RAMOOPS_HEADER_BYTES 12U
#define PONG_RAMOOPS_MAGIC 0x43474244U
#define PONG_RAMOOPS_DATA_BYTES (PONG_RAMOOPS_CONSOLE_BYTES - PONG_RAMOOPS_HEADER_BYTES)

struct pong_ramoops_header {
	volatile uint32_t sig;
	volatile uint32_t start;
	volatile uint32_t size;
};

/* Defined in arm_init.c: one copy shared by the whole kernel. */
extern vm_offset_t pong_ramoops_base;
extern uint32_t pong_ramoops_start;
extern uint32_t pong_ramoops_size;
extern volatile uint32_t pong_ramoops_busy;

void pong_ramoops_console_write(const char *text, int length);
int  pong_ramoops_console_init(void);

/* Read back what the mirror holds; used by the bring-up self check. */
vm_offset_t pong_ramoops_debug_base(void);
uint32_t    pong_ramoops_debug_start(void);
uint32_t    pong_ramoops_debug_size(void);

#endif /* PONG_RAMOOPS_CONSOLE_H */
