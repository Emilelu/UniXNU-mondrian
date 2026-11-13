/* Host test for K60AdspImage.c: the real table, a 49 MB buffer, and a stub reader. */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "K60AdspImage.h"

static uint32_t reads_done;
static const char *expected_next;

static int stub_read(const char *part, void *dst, uint32_t bytes)
{
    if (expected_next && strcmp(part, expected_next) != 0) {
        printf("FAIL order: wanted %s got %s\n", expected_next, part);
        return -1;
    }
    memset(dst, 0xa5, bytes);   /* visible so bss zeroing is checkable */
    reads_done++;
    return 0;
}

static int failing_read(const char *part, void *dst, uint32_t bytes)
{
    (void)part; (void)dst; (void)bytes;
    return -1;
}

int main(void)
{
    const uint32_t window = K60_ADSP_WINDOW;
    uint8_t *buf = malloc(window);
    if (!buf) {
        printf("FAIL out of memory\n");
        return 1;
    }
    memset(buf, 0x11, window);

    K60AdspPlan plan;
    if (k60_adsp_plan(&plan) != 0) {
        printf("FAIL plan rejected its own table\n");
        return 1;
    }
    printf("plan segments=%u copied=%u zeroed=%u base=%#x window=%#x\n",
           plan.segments, plan.copied, plan.zeroed, plan.base, plan.window);

    if (plan.segments != K60_ADSP_SEGMENTS) {
        printf("FAIL segment count\n");
        return 1;
    }
    if ((uint64_t)plan.copied + plan.zeroed > window) {
        printf("FAIL footprint %u exceeds window %u\n", plan.copied + plan.zeroed, window);
        return 1;
    }

    int rc = k60_adsp_copy(buf, window, stub_read);
    if (rc != 0) {
        printf("FAIL copy rc=%d\n", rc);
        return 1;
    }

    uint32_t expected_reads = 0;
    for (uint32_t i = 0; i < K60_ADSP_SEGMENTS; i++) {
        if (k60_adsp_segments[i].bytes) {
            expected_reads++;
        }
    }
    if (reads_done != expected_reads) {
        printf("FAIL reads %u != %u\n", reads_done, expected_reads);
        return 1;
    }

    /* The first segment must be visible at its address, and its bss must be zero. */
    const K60AdspSegment *first = &k60_adsp_segments[0];
    const uint8_t *at = buf + (first->paddr - K60_ADSP_BASE);
    if (first->bytes && at[0] != 0xa5) {
        printf("FAIL first segment not copied (%#x)\n", at[0]);
        return 1;
    }
    if (first->bss && at[first->bytes] != 0) {
        printf("FAIL bss not zeroed (%#x)\n", at[first->bytes]);
        return 1;
    }

    /* Bytes after the last segment must stay untouched. */
    uint32_t end = 0;
    for (uint32_t i = 0; i < K60_ADSP_SEGMENTS; i++) {
        uint32_t e = k60_adsp_segments[i].paddr - K60_ADSP_BASE +
                     k60_adsp_segments[i].bytes + k60_adsp_segments[i].bss;
        end = e > end ? e : end;
    }
    if (end < window && buf[window - 1] != 0x11) {
        printf("FAIL byte after the last segment modified (%#x)\n", buf[window - 1]);
        return 1;
    }

    if (k60_adsp_copy(buf, window, failing_read) != K60AdspReadFailed) {
        printf("FAIL a failing reader was not reported\n");
        return 1;
    }
    if (k60_adsp_copy(NULL, window, stub_read) != K60AdspBadArg) {
        printf("FAIL NULL window accepted\n");
        return 1;
    }
    if (k60_adsp_copy(buf, window - 1, stub_read) != K60AdspBadArg) {
        printf("FAIL short window accepted\n");
        return 1;
    }

    printf("TESTS OK 6\n");
    free(buf);
    return 0;
}
