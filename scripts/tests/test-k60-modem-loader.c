/* Host test for K60ModemImage.c: the real table, a 306 MiB buffer, a stub reader.
 *
 * The modem table has three rows with no file at all (b14, b21, b30), so this
 * test also proves the loader does not call the reader for them and still zeroes
 * their whole bss -- b21 alone is 156 MiB, larger than every copied byte of the
 * image combined, which is why "zero the carveout first" is not an option.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "K60ModemImage.h"

static uint32_t reads_done;
static uint32_t bytes_read;

static int stub_read(const char *part, void *dst, uint32_t bytes)
{
    if (!part) {
        printf("FAIL reader called with no part name\n");
        return -1;
    }
    memset(dst, 0xa5, bytes);   /* visible so bss zeroing is checkable */
    reads_done++;
    bytes_read += bytes;
    return 0;
}

static int failing_read(const char *part, void *dst, uint32_t bytes)
{
    (void)part; (void)dst; (void)bytes;
    return -1;
}

int main(void)
{
    const uint32_t window = K60_MODEM_WINDOW;
    uint8_t *buf = malloc(window);
    if (!buf) {
        printf("FAIL out of memory\n");
        return 1;
    }
    memset(buf, 0x11, window);

    K60ModemPlan plan;
    if (k60_modem_plan(&plan) != 0) {
        printf("FAIL plan rejected its own table\n");
        return 1;
    }
    printf("plan segments=%u copied=%u zeroed=%u base=%#x window=%#x\n",
           plan.segments, plan.copied, plan.zeroed, plan.base, plan.window);

    if (plan.segments != K60_MODEM_SEGMENTS) {
        printf("FAIL segment count\n");
        return 1;
    }
    if ((uint64_t)plan.copied + plan.zeroed > window) {
        printf("FAIL footprint %llu exceeds window %u\n",
               (unsigned long long)plan.copied + plan.zeroed, window);
        return 1;
    }
    /* The measured image: 109,060,761 bytes of file, 211,012,967 bytes of bss. */
    if (plan.copied != 109060761u || plan.zeroed != 211012967u) {
        printf("FAIL plan totals %u/%u disagree with modem.mdt\n", plan.copied, plan.zeroed);
        return 1;
    }

    int rc = k60_modem_copy(buf, window, stub_read);
    if (rc != 0) {
        printf("FAIL copy rc=%d\n", rc);
        return 1;
    }

    uint32_t expected_reads = 0;
    for (uint32_t i = 0; i < K60_MODEM_SEGMENTS; i++) {
        if (k60_modem_segments[i].bytes) {
            expected_reads++;
        }
    }
    if (reads_done != expected_reads) {
        printf("FAIL reads %u != %u\n", reads_done, expected_reads);
        return 1;
    }
    if (bytes_read != plan.copied) {
        printf("FAIL bytes read %u != copied %u\n", bytes_read, plan.copied);
        return 1;
    }

    /* Every row: copied bytes visible, bss zero, and the two do not overlap. */
    for (uint32_t i = 0; i < K60_MODEM_SEGMENTS; i++) {
        const K60ModemSegment *s = &k60_modem_segments[i];
        const uint8_t *at = buf + (s->paddr - K60_MODEM_BASE);
        if (s->bytes) {
            if (at[0] != 0xa5 || at[s->bytes - 1] != 0xa5) {
                printf("FAIL segment %u not copied (%#x..%#x)\n", i, at[0], at[s->bytes - 1]);
                return 1;
            }
        }
        if (s->bss) {
            if (at[s->bytes] != 0 || at[s->bytes + s->bss - 1] != 0) {
                printf("FAIL segment %u bss not zeroed\n", i);
                return 1;
            }
        }
    }

    /* Bytes after the last segment must stay untouched. */
    uint32_t end = 0;
    for (uint32_t i = 0; i < K60_MODEM_SEGMENTS; i++) {
        uint32_t e = k60_modem_segments[i].paddr - K60_MODEM_BASE +
                     k60_modem_segments[i].bytes + k60_modem_segments[i].bss;
        end = e > end ? e : end;
    }
    if (end < window && buf[window - 1] != 0x11) {
        printf("FAIL byte after the last segment modified (%#x)\n", buf[window - 1]);
        return 1;
    }
    if (end == window && buf[window - 1] != 0) {
        printf("FAIL last segment did not reach the carveout end (%#x)\n", buf[window - 1]);
        return 1;
    }

    if (k60_modem_copy(buf, window, failing_read) != K60ModemReadFailed) {
        printf("FAIL a failing reader was not reported\n");
        return 1;
    }
    if (k60_modem_copy(NULL, window, stub_read) != K60ModemBadArg) {
        printf("FAIL NULL window accepted\n");
        return 1;
    }
    if (k60_modem_copy(buf, window - 1, stub_read) != K60ModemBadArg) {
        printf("FAIL short window accepted\n");
        return 1;
    }
    if (k60_modem_plan(NULL) != K60ModemBadArg) {
        printf("FAIL NULL plan accepted\n");
        return 1;
    }

    printf("TESTS OK 7\n");
    free(buf);
    return 0;
}
