/* Host test for K60ModemBoot.c: the real table and loader, a recording PAS
 * shim, a recording rail vote, and no device. It proves the order the secure
 * monitor requires:
 *
 *   rails -> init_image(metadata page) -> mem_setup -> auth_reset
 *
 * and that a failed step stops the chain (no later SMC is attempted). Both
 * diagnostics must stop at their own barrier: phase 1 after mem_setup, phase 2
 * after the rail votes and before the first PAS command.
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

/* Must match the phase defines in K60ModemBoot.c. */
#define PHASE_FULL 0
#define PHASE_METADATA_ONLY 1
#define PHASE_RAILS_ONLY 2

int k60_modem_bring_up(void *window, size_t window_bytes, K60ModemRead read,
    int phase);

enum {
    OP_RAILS = 1,
    OP_INIT = 2,
    OP_MEM = 3,
    OP_AUTH = 4,
};

static int calls[8];
static int ncalls;
static uint64_t init_phys;
static int rails_rc;
static int init_rc;
static int mem_rc;
static int auth_rc;
static int failures;

static void
reset(int new_rails_rc, int new_init_rc, int new_mem_rc, int new_auth_rc)
{
    ncalls = 0;
    init_phys = 0;
    rails_rc = new_rails_rc;
    init_rc = new_init_rc;
    mem_rc = new_mem_rc;
    auth_rc = new_auth_rc;
}

static void
record(int op)
{
    if (ncalls < (int)(sizeof(calls) / sizeof(calls[0]))) {
        calls[ncalls] = op;
    }
    ncalls++;
}

int
k60_modem_rails_vote(void)
{
    record(OP_RAILS);
    return rails_rc;
}

int
k60_modem_init_image(uint64_t phys)
{
    record(OP_INIT);
    init_phys = phys;
    return init_rc;
}

int
k60_modem_mem_setup(uint64_t base, uint64_t span)
{
    (void)base;
    (void)span;
    record(OP_MEM);
    return mem_rc;
}

int
k60_modem_auth_and_reset(void)
{
    record(OP_AUTH);
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
    static const int full[] = { OP_RAILS, OP_INIT, OP_MEM, OP_AUTH };
    static const int metadata_only[] = { OP_INIT, OP_MEM };
    static const int rails_only[] = { OP_RAILS };
    static const int rails_init[] = { OP_RAILS, OP_INIT };
    static const int rails_init_mem[] = { OP_RAILS, OP_INIT, OP_MEM };
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

    reset(0, 0, 0, 0);
    rc = k60_modem_bring_up(window, K60_MODEM_WINDOW, stub_read, PHASE_FULL);
    expect(rc == K60ModemPasOk, "full sequence rc");
    expect(order_is(full, 4), "rails come first, then the PAS order");
    expect(init_phys == (uint64_t)EXPECT_METADATA, "init_image metadata address");
    expect(ncalls == 4, "init_image called once");

    reset(0, 0, 0, 0);
    rc = k60_modem_bring_up(window, K60_MODEM_WINDOW, stub_read,
        PHASE_METADATA_ONLY);
    expect(rc == K60ModemPasOk, "diagnostic sequence rc");
    expect(order_is(metadata_only, 2), "metadata-only stops after mem_setup");

    /* Phase 2 is the rail-only diagnostic: one vote, then no PAS command. */
    reset(0, 0, 0, 0);
    rc = k60_modem_bring_up(window, K60_MODEM_WINDOW, stub_read,
        PHASE_RAILS_ONLY);
    expect(rc == K60ModemPasOk, "rails-only rc");
    expect(order_is(rails_only, 1), "rails-only sends no PAS command");

    reset(-7, 0, 0, 0);
    rc = k60_modem_bring_up(window, K60_MODEM_WINDOW, stub_read, PHASE_FULL);
    expect(rc == -7, "rail failure rc");
    expect(order_is(rails_only, 1), "rail failure stops before init_image");

    reset(0, -5, 0, 0);
    rc = k60_modem_bring_up(window, K60_MODEM_WINDOW, stub_read, PHASE_FULL);
    expect(rc == -5, "init failure rc");
    expect(order_is(rails_init, 2), "init failure stops the chain");

    reset(0, 0, -5, 0);
    rc = k60_modem_bring_up(window, K60_MODEM_WINDOW, stub_read, PHASE_FULL);
    expect(rc == -5, "mem_setup failure rc");
    expect(order_is(rails_init_mem, 3), "mem_setup failure stops before auth");

    reset(0, 0, 0, -5);
    rc = k60_modem_bring_up(window, K60_MODEM_WINDOW, stub_read, PHASE_FULL);
    expect(rc == -5, "auth failure rc");
    expect(order_is(full, 4), "auth failure reached the last step");

    reset(0, 0, 0, 0);
    rc = k60_modem_bring_up(window, K60_MODEM_WINDOW, failing_read, PHASE_FULL);
    expect(rc == K60ModemReadFailed, "copy failure rc");
    expect(ncalls == 0, "copy failure votes no rail and sends no SMC");

    reset(0, 0, 0, 0);
    rc = k60_modem_bring_up(NULL, 0, NULL, PHASE_FULL);
    expect(rc == K60ModemPasOk, "already staged rc");
    expect(order_is(full, 4), "already staged still runs the full order");

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
    printf("TESTS OK 12\n");
    return 0;
}
