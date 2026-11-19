/* Contract for the ADSP PAS image loader (see K60AdspImage.c). */

#ifndef K60_ADSP_IMAGE_H
#define K60_ADSP_IMAGE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

enum {
    K60AdspBadArg = -1,
    K60AdspBadSegment = -2,
    K60AdspOutsideWindow = -3,
    K60AdspOverlap = -4,
    K60AdspReadFailed = -5, /* partial/exact-size failure */
    K60AdspPartMissing = -6, /* reader source/name absent */
    K60AdspReadBounds = -7, /* reader container/range invalid */
    K60AdspMismatch = -9, /* read-back differs from the firmware file */
};

typedef struct {
    uint32_t paddr; /* firmware LINK address (adsp.mdt p_paddr) */
    uint32_t bytes;
    uint32_t bss;
    const char *part;
} K60AdspSegment;

#include "pong_adsp_table.h" /* needs K60AdspSegment, declared above */

typedef struct {
    uint32_t base; /* BOARD carveout the bytes are copied to */
    uint32_t window;
    uint32_t segments;
    uint32_t copied;
    uint32_t zeroed;
} K60AdspPlan;

/* read(part, dst, bytes) fills dst from the named firmware file; 0 on success. */
#ifndef K60_ADSP_READ_TYPE_DEFINED
#define K60_ADSP_READ_TYPE_DEFINED
typedef int (*K60AdspRead)(const char *part, void *dst, uint32_t bytes);
#endif

/* Validates the table only; no allocation, no device access. */
int k60_adsp_plan(K60AdspPlan *plan);

/* Same, for an explicit destination: board_base must be 4 KiB aligned.
 * K60_ADSP_LINK_BASE is where the firmware was linked, never where it runs;
 * segment paddr keeps its link value and is relocated on copy. */
int k60_adsp_plan_at(K60AdspPlan *plan, uint32_t board_base);

/* Copies every segment and zeroes every bss tail. window is the PAS carveout. */
int k60_adsp_copy(void *window, size_t window_bytes, K60AdspRead read);

#endif /* K60_ADSP_IMAGE_H */
