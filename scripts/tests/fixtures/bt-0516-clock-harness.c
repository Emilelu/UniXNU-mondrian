/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * HOST-ONLY harness for the 0516 UART-clock wake/refusal fix.
 *
 * It compiles the real bsd/dev/qbt/qbt_core.c that the Python runner
 * reconstructs from the current 236-patch series.  The platform, clock and
 * UART are synthetic.  This is not a controller, UART, DMA, IBS or hardware
 * result, and it does not replay the d8 timeline.
 *
 * The two scenarios are software-state tests of the three 986d631 behaviours:
 * a wake indication delivered inside clock(false) must re-arm the clock and
 * send its WAKE_ACK; a control byte queued while the clock is stopped must
 * wake it; a write an idle UART refuses must be retried at QBT_TX_POLL.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <errno.h>

#include "qbt_internal.h"

static int fails;
#define CHECK(cond, ...) do { \
    if (!(cond)) { fails++; printf("FAIL %s:%d: ", __FILE__, __LINE__); \
        printf(__VA_ARGS__); printf("\n"); } \
} while (0)

struct fixture {
    struct qbt *q;
    uint64_t now;
    int wake_armed, wake_in_stop, uart_stopped, clock_fail;
    unsigned clock_starts, clock_stops;
    unsigned tx_acks, tx_writes;
};

static struct fixture F;
static struct qbt_platform platform;

static void *fx_allocate(void *ctx, size_t n) { (void)ctx; return calloc(1, n); }
static void fx_release(void *ctx, void *p, size_t n) { (void)ctx; (void)n; free(p); }
static uint64_t fx_now(void *ctx) { (void)ctx; return F.now; }
static bool fx_drained(void *ctx) { (void)ctx; return true; }
static size_t fx_uart_write(void *ctx, const uint8_t *p, size_t n) {
    (void)ctx;
    if (F.uart_stopped) return 0;
    if (n && p[0] == 0xfc) F.tx_acks++;
    F.tx_writes += (unsigned)n;
    return n;
}
static int fx_speed(void *ctx, uint32_t speed) { (void)ctx; (void)speed; return 0; }
static int fx_flow(void *ctx, bool on) { (void)ctx; (void)on; return 0; }
static int fx_clock(void *ctx, bool on) {
    (void)ctx;
    if (on) {
        if (F.clock_fail) return -ENXIO;
        F.clock_starts++;
        return 0;
    }
    if (!F.wake_armed) return -EBUSY;
    F.clock_stops++;
    if (F.wake_in_stop) {
        uint8_t wake = 0xfd;
        /* A board can service its UART while it stops the clock. */
        F.wake_in_stop = 0;
        qbt_rx_wake(F.q);
        CHECK(qbt_receive(F.q, &wake, 1) == 1, "wake byte accepted in clock stop");
    }
    return 0;
}
static void fx_pump(void *ctx) { (void)ctx; }
static void fx_wait_until(void *ctx, uint64_t target) {
    (void)ctx;
    if (target > F.now) F.now = target;
}
static size_t fx_receive(void *ctx, const uint8_t *p, size_t n) {
    (void)ctx;
    return qbt_receive(F.q, p, n);
}
static int fx_firmware_get(void *ctx, const char *name, const uint8_t **data, size_t *size) {
    (void)ctx; (void)name; (void)data; (void)size;
    return -ENOENT;
}
static void fx_firmware_put(void *ctx, const uint8_t *data, size_t n) {
    (void)ctx; (void)data; (void)n;
}
static void fx_log(void *ctx, int level, const char *text) {
    (void)ctx; (void)level; (void)text;
}

static void reset_fixture(void) {
    if (F.q) { qbt_destroy(F.q); F.q = NULL; }
    memset(&F, 0, sizeof(F));
    memset(&platform, 0, sizeof(platform));
    platform.context = &F;
    platform.allocate = fx_allocate;
    platform.release = fx_release;
    platform.now_ns = fx_now;
    platform.uart_write = fx_uart_write;
    platform.uart_drained = fx_drained;
    platform.uart_speed = fx_speed;
    platform.uart_flow = fx_flow;
    platform.clock = fx_clock;
    platform.pump = fx_pump;
    platform.wait_until = fx_wait_until;
    platform.receive = fx_receive;
    platform.firmware_get = fx_firmware_get;
    platform.firmware_put = fx_firmware_put;
    platform.log = fx_log;
    F.now = 1000;
    F.wake_armed = 1;
    F.q = qbt_create(&platform);
    CHECK(F.q != NULL, "qbt_create");
}

static void make_ready(void) {
    F.q->info.state = 2;
    F.q->service = true;
    F.q->ibs = true;
    F.q->tx_state = QBT_ASLEEP;
}

/* A wake delivered inside clock(false) must not leave its ACK behind a
 * stopped clock; a control byte queued while stopped must wake the clock. */
static int scenario_clock_wake_in_stop(void) {
    unsigned acks, starts;
    reset_fixture();
    make_ready();
    F.wake_in_stop = 1;
    qbt_step(F.q);
    CHECK(F.q->stats.clock_sleeps == 1, "one clock stop: %llu",
          (unsigned long long)F.q->stats.clock_sleeps);
    CHECK(F.q->stats.clock_reverts == 1, "one stop reverted by wake: %llu",
          (unsigned long long)F.q->stats.clock_reverts);
    CHECK(F.q->clock_on, "clock back on after wake in stop");
    CHECK(F.q->rx_awake, "peer awake after WAKE_IND");
    CHECK(F.q->control_length == 1, "WAKE_ACK queued: %u", F.q->control_length);

    acks = F.tx_acks;
    qbt_step(F.q);
    CHECK(F.tx_acks == acks + 1, "WAKE_ACK sent after revert: %u", F.tx_acks);
    CHECK(F.q->control_length == 0, "control queue drained");

    /* Same control path with the clock already stopped.  The old code
     * returned early because pending was false. */
    F.q->clock_on = false;
    F.q->rx_awake = false;
    F.q->tx_state = QBT_ASLEEP;
    F.q->control[0] = 0xfc;
    F.q->control_length = 1;
    acks = F.tx_acks; starts = F.clock_starts;
    qbt_step(F.q);
    CHECK(F.clock_starts == starts + 1, "control byte called clock(true)");
    CHECK(F.tx_acks == acks + 1, "control byte sent: %u", F.tx_acks);
    CHECK(F.q->control_length == 0, "stopped-clock control queue drained");
    return fails == 0;
}

/* An idle UART that refuses a write must be retried at QBT_TX_POLL, not
 * spun on zero, and the same helper must cover data writes. */
static int scenario_clock_refused_write(void) {
    unsigned i;
    uint8_t acl[6] = {2, 1, 0, 1, 0, 0};
    reset_fixture();
    make_ready();
    F.q->ibs = false;
    F.q->tx_state = QBT_AWAKE;
    F.q->control[0] = 0xfc;
    F.q->control_length = 1;
    F.uart_stopped = 1;

    for (i = 0; i < 5; i++) {
        uint64_t before = F.now, next;
        qbt_step(F.q);
        CHECK(F.q->control_length == 1, "refused control still queued");
        CHECK(F.tx_acks == 0, "refused control not acked");
        next = qbt_deadline(F.q);
        CHECK(next == before + QBT_TX_POLL,
              "refused control deadline is one poll: %llu vs %llu",
              (unsigned long long)next,
              (unsigned long long)(before + QBT_TX_POLL));
        F.now = next;
    }
    CHECK(F.q->stats.tx_refused == 5, "five refused writes counted: %llu",
          (unsigned long long)F.q->stats.tx_refused);

    F.uart_stopped = 0;
    qbt_step(F.q);
    CHECK(F.tx_acks == 1, "control sent after the UART resumes: %u", F.tx_acks);
    CHECK(F.q->control_length == 0, "control queue drained");
    CHECK(F.q->write_retry_at == 0, "retry timer cleared by a successful write");

    CHECK(qbt_transmit(F.q, acl, sizeof(acl)) == 0, "ACL frame queued");
    F.uart_stopped = 1;
    qbt_step(F.q);
    CHECK(F.q->tx_length == sizeof(acl), "refused data still queued: %u", F.q->tx_length);
    CHECK(F.q->stats.tx_bytes == 0, "refused data wrote no bytes: %llu",
          (unsigned long long)F.q->stats.tx_bytes);
    CHECK(qbt_deadline(F.q) == F.now + QBT_TX_POLL,
          "refused data deadline is one poll");
    CHECK(F.q->stats.tx_refused == 6, "data refusal counted: %llu",
          (unsigned long long)F.q->stats.tx_refused);

    F.uart_stopped = 0;
    qbt_step(F.q);
    CHECK(F.q->tx_length == 0, "data sent after the UART resumes: %u", F.q->tx_length);
    CHECK(F.q->stats.tx_bytes == sizeof(acl), "data bytes written: %llu",
          (unsigned long long)F.q->stats.tx_bytes);
    return fails == 0;
}

int main(int argc, char **argv) {
    struct { const char *name; int (*fn)(void); } cases[] = {
        {"clock_wake_in_stop", scenario_clock_wake_in_stop},
        {"clock_refused_write", scenario_clock_refused_write},
    };
    if (argc < 2) { printf("usage: %s <scenario>|all\n", argv[0]); return 2; }
    for (unsigned i = 0; i < sizeof(cases)/sizeof(cases[0]); i++) {
        if (strcmp(argv[1], "all") == 0 || strcmp(argv[1], cases[i].name) == 0) {
            fails = 0;
            int ok = cases[i].fn();
            printf("RESULT %s %s failures=%d\n", cases[i].name, ok ? "PASS" : "FAIL", fails);
            if (!ok) return 1;
            if (strcmp(argv[1], "all") != 0) return 0;
        }
    }
    if (strcmp(argv[1], "all") != 0) { printf("unknown scenario %s\n", argv[1]); return 2; }
    return 0;
}
