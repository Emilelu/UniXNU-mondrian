/* Contract for the modem (MSS) PAS image loader (see K60ModemImage.c).
 *
 * Sibling of drivers/PongPower/K60AdspImage.h. Same shape on purpose: one
 * table-driven loader per PAS subsystem, no ELF parsing at boot. The facts
 * below come from the live Android DT and the shipped modem.mdt:
 *
 *   /reserved-memory/mpss_region@8bc00000  reg = 0x8bc00000 / 0x13200000
 *   modem.mdt                              ELF32, e_phnum 32, 30 PT_LOAD
 *
 * Sources: docs/research/cellular/02-DT-TRUTH.md (DT bytes),
 *          docs/research/cellular/05-MODEM-IMAGE.md (segment table).
 */

#ifndef K60_MODEM_IMAGE_H
#define K60_MODEM_IMAGE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

enum {
    K60ModemBadArg = -1,
    K60ModemBadSegment = -2,
    K60ModemOutsideWindow = -3,
    K60ModemOverlap = -4,
    K60ModemReadFailed = -5,
};

typedef struct {
    uint32_t paddr;
    uint32_t bytes;
    uint32_t bss;
    const char *part;
} K60ModemSegment;

#include "pong_modem_table.h" /* needs K60ModemSegment, declared above */

typedef struct {
    uint32_t base;
    uint32_t window;
    uint32_t segments;
    uint32_t copied;
    uint32_t zeroed;
} K60ModemPlan;

/* read(part, dst, bytes) fills dst from the named firmware file; 0 on success. */
typedef int (*K60ModemRead)(const char *part, void *dst, uint32_t bytes);

/* Validates the table only; no allocation, no device access. */
int k60_modem_plan(K60ModemPlan *plan);

/* Copies every segment and zeroes every bss tail. window is the mpss carveout. */
int k60_modem_copy(void *window, size_t window_bytes, K60ModemRead read);

#endif /* K60_MODEM_IMAGE_H */
