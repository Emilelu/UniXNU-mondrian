/* Host test for K60ModemBoot.c: the real table and loader, a recording PAS
 * shim, and no device. It proves the order the secure monitor requires:
 *
 *   init_image(metadata page) -> mem_setup -> auth_reset
 *
 * and that a failed step stops the chain (no later SMC is attempted). The
 * diagnostic phase must stop after mem_setup and never reach auth_reset.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "K60ModemImage.h"
#include "K60ModemPas.h"

/* Must match K60ModemBoot.c and ImageCarrierLib.c; the build gate compares
 * the two files. Kept as a literal here so the test can fail if the driver
 * ever changes the page without changing the expectation. */
#define EXPECT_METADATA 0xB7FF0000u
#define EXPECT_METADATA_BYTES 5884u

int k60_modem_bring_up(void *window, size_t window_bytes, K60ModemRead read,
    int phase);

enum {
    OP_INIT = 1,
    OP_MEM = 2,
    OP_AUTH = 3,
};

static int calls[8];
static int ncalls;
static uint64_t init_phys;
static int init_rc;
static int mem_rc;
static int auth_rc;
static int failures;

static void
reset(int new_init_rc, int new_mem_rc, int new_auth_rc)
{
    ncalls = 0;
    init_phys = 0;
    init_rc = new_init_rc;
    mem_rc = new_mem_rc;
    auth_rc = new_auth_rc;
}

int
k60_modem_init_image(uint64_t phys)
{
    if (ncalls < (int)(sizeof(calls) / sizeof(calls[0]))) {
        calls[ncalls] = OP_INIT;
    }
    ncalls++;
    init_phys = phys;
    return init_rc;
}

int
k60_modem_mem_setup(uint64_t base, uint64_t span)
{
    (void)base;
    (void)span;
    if (ncalls < (int)(sizeof(calls) / sizeof(calls[0]))) {
        calls[ncalls] = OP_MEM;
    }
    ncalls++;
    return mem_rc;
}

int
k60_modem_auth_and_reset(void)
{
    if (ncalls < (int)(sizeof(calls) / sizeof(calls[0]))) {
        calls[ncalls] = OP_AUTH;
    }
    ncalls++;
    return auth_rc;
}

int
k60_modem_shutdown(void)
{
    return K60ModemPasOk;
}

int
k60_modem_scm_tried(void)
{
    return 1;
}

static int
stub_read(const char *part, void *dst, uint32_t bytes)
{
    if (!part || !dst) {
        return -1;
    }
    memset(dst, 0xa5, bytes);
    return 0;
}

static int
failing_read(const char *part, void *dst, uint32_t bytes)
{
    (void)part;
    (void)dst;
    (void)bytes;
    return -1;
}

static void
expect(int condition, const char *what)
{
    if (!condition) {
        printf("FAIL %s\n", what);
        failures++;
    }
}

static int
order_is(const int *want, int count)
{
    int i;

    if (ncalls != count) {
        return 0;
    }
    for (i = 0; i < count; i++) {
        if (calls[i] != want[i]) {
            return 0;
        }
    }
    return 1;
}

int
main(void)
{
    static const int full[] = { OP_INIT, OP_MEM, OP_AUTH };
    static const int metadata_only[] = { OP_INIT, OP_MEM };
    static const int init_only[] = { OP_INIT };
    static const int init_mem[] = { OP_INIT, OP_MEM };
    uint8_t *window;
    int rc;

    window = malloc(K60_MODEM_WINDOW);
    if (!window) {
        printf("FAIL out of memory\n");
        return 1;
    }

    /* The table itself is real; a wrong window would let the copy pass by
     * accident, so pin the two ends. */
    expect(K60_MODEM_SEGMENTS == 30, "table segment count");
    expect(k60_modem_segments[0].paddr == K60_MODEM_BASE, "first segment base");
    expect(K60_MODEM_WINDOW == 0x13200000ul, "window size");

    reset(0, 0, 0);
    rc = k60_modem_bring_up(window, K60_MODEM_WINDOW, stub_read, 0);
    expect(rc == K60ModemPasOk, "full sequence rc");
    expect(order_is(full, 3), "full sequence order");
    expect(init_phys == (uint64_t)EXPECT_METADATA, "init_image metadata address");
    expect(ncalls == 3, "init_image called once");

    reset(0, 0, 0);
    rc = k60_modem_bring_up(window, K60_MODEM_WINDOW, stub_read, 1);
    expect(rc == K60ModemPasOk, "diagnostic sequence rc");
    expect(order_is(metadata_only, 2), "diagnostic stops after mem_setup");

    reset(-5, 0, 0);
    rc = k60_modem_bring_up(window, K60_MODEM_WINDOW, stub_read, 0);
    expect(rc == -5, "init failure rc");
    expect(order_is(init_only, 1), "init failure stops the chain");

    reset(0, -5, 0);
    rc = k60_modem_bring_up(window, K60_MODEM_WINDOW, stub_read, 0);
    expect(rc == -5, "mem_setup failure rc");
    expect(order_is(init_mem, 2), "mem_setup failure stops before auth");

    reset(0, 0, -5);
    rc = k60_modem_bring_up(window, K60_MODEM_WINDOW, stub_read, 0);
    expect(rc == -5, "auth failure rc");
    expect(order_is(full, 3), "auth failure reached the last step");

    reset(0, 0, 0);
    rc = k60_modem_bring_up(window, K60_MODEM_WINDOW, failing_read, 0);
    expect(rc == K60ModemReadFailed, "copy failure rc");
    expect(ncalls == 0, "copy failure sends no SMC");

    reset(0, 0, 0);
    rc = k60_modem_bring_up(NULL, 0, NULL, 0);
    expect(rc == K60ModemPasOk, "already staged rc");
    expect(order_is(full, 3), "already staged still runs the PAS order");

    expect((EXPECT_METADATA & 0xfffu) == 0, "metadata page alignment");
    expect(EXPECT_METADATA >= 0xA8300000u &&
        (uint64_t)EXPECT_METADATA + EXPECT_METADATA_BYTES <= 0xB8000000ull,
        "metadata page inside ABL staging");
    expect((uint64_t)EXPECT_METADATA + EXPECT_METADATA_BYTES <= 0x100000000ull,
        "metadata page below 4 GiB");

    free(window);
    if (failures) {
        printf("TESTS FAILED %d\n", failures);
        return 1;
    }
    printf("TESTS OK 9\n");
    return 0;
}
