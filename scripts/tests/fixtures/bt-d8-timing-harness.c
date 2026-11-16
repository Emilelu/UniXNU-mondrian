/* SPDX-License-Identifier: GPL-2.0-only */
/* This fixture includes the source extracted from the SHA-pinned d8 patches.
 * Only platform callbacks and the 0515 measurement's send boundary are fake.
 * No controller, UART, full QCA download, qbt_boot, or reset claim is made. */
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include "qbt_core.c"
#include "qbt_observation.inc"

static unsigned cases, checks;
static const char *case_name;
#define CHECK(expr) do { ++checks; if (!(expr)) { \
    fprintf(stderr, "FAIL case %u (%s) line %d: %s\n", cases, case_name, __LINE__, #expr); \
    exit(1); } } while (0)

struct fixture {
    struct qbt q;
    uint64_t ns, write_ns, send_ns, log_ns;
    uint64_t waits[20000];
    unsigned pumps, wait_count, inject_pump;
    uint64_t inject_at;
    uint8_t pending[16];
    size_t pending_length;
    bool uart_idle, blocked;
    int inject_error, send_error;
    unsigned sends, log_count;
    char log[512];
};
static struct fixture f;

static uint64_t fx_now(void *p) { return ((struct fixture *)p)->ns; }
static bool fx_drained(void *p) { return ((struct fixture *)p)->uart_idle; }
static int fx_clock(void *p, bool enabled) { (void)p; (void)enabled; return 0; }
static size_t fx_receive(void *p, const uint8_t *data, size_t length)
{ (void)p; (void)data; return length; }
static size_t fx_write(void *p, const uint8_t *data, size_t length)
{
    struct fixture *x = p; (void)data;
    x->ns += x->write_ns;
    return x->blocked ? 0 : length;
}
static void fx_pump(void *p)
{
    struct fixture *x = p;
    ++x->pumps;
    if (x->inject_pump && x->pumps >= x->inject_pump && x->ns >= x->inject_at) {
        x->inject_pump = 0;
        if (x->pending_length)
            CHECK(qbt_receive(&x->q, x->pending, x->pending_length) == x->pending_length);
        if (x->inject_error) qbt_fail(&x->q, x->inject_error);
    }
}
static void fx_wait(void *p, uint64_t next)
{
    struct fixture *x = p;
    CHECK(x->wait_count < sizeof(x->waits) / sizeof(x->waits[0]));
    x->waits[x->wait_count++] = next;
    CHECK(next >= x->ns);
    x->ns = next;
}
static void fx_log(void *p, int level, const char *text)
{
    struct fixture *x = p; (void)level;
    snprintf(x->log, sizeof(x->log), "%s", text);
    ++x->log_count; x->ns += x->log_ns;
}
static void begin(const char *name)
{
    ++cases; case_name = name; memset(&f, 0, sizeof f); f.uart_idle = true;
    f.q.ops.context = &f; f.q.ops.now_ns = fx_now; f.q.ops.uart_write = fx_write;
    f.q.ops.uart_drained = fx_drained; f.q.ops.clock = fx_clock;
    f.q.ops.pump = fx_pump; f.q.ops.wait_until = fx_wait;
    f.q.ops.receive = fx_receive; f.q.ops.log = fx_log;
    f.q.clock_on = true; f.q.info.state = 1;
}
static void waiting(uint16_t opcode)
{ f.q.waiting = true; f.q.wait_opcode = opcode; f.q.wait_event = 0; }
static void report(uint16_t opcode, uint8_t status, bool tlv)
{
    uint8_t bytes[] = {0x0e, 5, 1, (uint8_t)opcode, (uint8_t)(opcode >> 8), status, tlv ? 0x1e : 0};
    memcpy(f.q.event, bytes, sizeof bytes); f.q.event_length = sizeof bytes; event(&f.q);
}
static void schedule(uint16_t opcode, uint8_t status, bool tlv, unsigned pump, uint64_t at)
{
    uint8_t bytes[] = {4, 0x0e, 5, 1, (uint8_t)opcode, (uint8_t)(opcode >> 8), status, tlv ? 0x1e : 0};
    memcpy(f.pending, bytes, sizeof bytes); f.pending_length = sizeof bytes;
    f.inject_pump = pump; f.inject_at = at;
}
static int command(uint16_t opcode)
{
    const uint8_t data[] = {0x1e}; uint8_t reply[32]; size_t length = sizeof reply;
    return qbt_command(&f.q, opcode, data, sizeof data, 0, reply, &length);
}
static int qca_tlv_send_segment(struct hci_dev *hdev, int size,
                               const unsigned char *segment, int mode, int soc)
{
    (void)size; (void)segment; (void)mode; (void)soc;
    ++f.sends; f.ns += f.send_ns;
    ++hdev->q->stats.tlv_sent; ++hdev->q->stats.tlv_acks;
    return f.send_error;
}

static void events(void)
{
    begin("TLV success report completes a matching wait"); waiting(0xfc00); report(0xfc00, 0, true);
    CHECK(f.q.stats.tlv_acks == 1 && f.q.stats.tlv_final_status == 0 && f.q.complete);
    CHECK(f.q.reply_length == 7 && f.q.reply[6] == 0x1e);

    begin("TLV error report counts but cannot complete"); waiting(0xfc00); report(0xfc00, 1, true);
    CHECK(f.q.stats.tlv_acks == 1 && f.q.stats.tlv_final_status == 1 && !f.q.complete);
    CHECK(f.q.reply_length == 0);

    begin("TLV report counts independently of waiting"); report(0xfc00, 1, true);
    CHECK(f.q.stats.tlv_acks == 1 && !f.q.complete);

    begin("generic command complete is independent of TLV ack"); waiting(0xfc00); report(0xfc00, 0, false);
    CHECK(f.q.complete && f.q.stats.tlv_acks == 0);

    begin("generic nonzero status still completes core wait"); waiting(0x1234); report(0x1234, 7, false);
    CHECK(f.q.complete && f.q.reply[5] == 7 && f.q.stats.tlv_acks == 0);

    begin("wrong opcode does not complete"); waiting(0x1234); report(0x1235, 0, false);
    CHECK(!f.q.complete && f.q.stats.unmatched_events == 1);

    begin("later TLV reports overwrite final status"); report(0xfc00, 1, true); report(0xfc00, 0, true);
    CHECK(f.q.stats.tlv_acks == 2 && f.q.stats.tlv_final_status == 0);

    begin("nonzero command status completes then qbt_command returns EIO");
    { uint8_t bytes[] = {4, 0x0f, 4, 7, 1, 0x34, 0x12};
      memcpy(f.pending, bytes, sizeof bytes); f.pending_length = sizeof bytes; f.inject_pump = 2;
      CHECK(command(0x1234) == -EIO && !f.q.waiting && f.q.complete); }
}
static void deadlines(void)
{
    begin("transport error precedes predicate and both deadlines");
    f.ns = 100; f.q.complete = true; f.q.info.error = -EIO; f.q.boot_deadline = 99;
    CHECK(run(&f.q, 99, 1) == -EIO && f.q.stats.timeouts == 0);

    begin("completion predicate precedes expired deadlines");
    f.ns = 100; f.q.complete = true; f.q.boot_deadline = 99;
    CHECK(run(&f.q, 99, 1) == 0 && f.q.stats.timeouts == 0);

    begin("empty queue predicate precedes boot expiry");
    f.ns = 100; f.q.boot_deadline = 99;
    CHECK(run(&f.q, 99, 0) == 0 && f.q.stats.timeouts == 0);

    begin("boot deadline equality wins over command equality");
    f.ns = 100; f.q.boot_deadline = 100;
    CHECK(run(&f.q, 100, 1) == -ETIMEDOUT && f.q.stats.timeouts == 1);
    CHECK(strstr(f.log, "budget exhausted") && f.log_count == 1);

    begin("command deadline before boot deadline");
    f.ns = 100; f.q.boot_deadline = 200;
    CHECK(run(&f.q, 100, 1) == -ETIMEDOUT && strstr(f.log, "command timeout"));

    begin("service command timeout leaves boot logging disabled");
    f.ns = 100;
    CHECK(run(&f.q, 100, 1) == -ETIMEDOUT && !f.log_count);

    begin("pump event at exact deadline precedes expiry");
    waiting(0xfc00); f.ns = 100; f.q.boot_deadline = 100; schedule(0xfc00, 0, true, 1, 100);
    CHECK(run(&f.q, 100, 1) == 0 && f.q.stats.timeouts == 0);

    begin("pump late event after both deadlines still precedes expiry");
    waiting(0xfc00); f.ns = 101; f.q.boot_deadline = 100; schedule(0xfc00, 0, true, 1, 101);
    CHECK(run(&f.q, 100, 1) == 0 && f.q.stats.timeouts == 0);

    begin("simultaneous pump fault wins over pump reply");
    waiting(0xfc00); schedule(0xfc00, 0, true, 1, 0); f.inject_error = -EIO;
    CHECK(run(&f.q, 100, 1) == -EIO && f.q.complete && f.q.stats.timeouts == 0);

    begin("run sleep is bounded by command deadline, not boot deadline");
    f.q.boot_deadline = 50;
    CHECK(run(&f.q, 100, 1) == -ETIMEDOUT && f.wait_count == 1);
    CHECK(f.waits[0] == 100 && f.ns == 100 && strstr(f.log, "budget exhausted"));
}
static void scheduler(void)
{
    begin("scheduler ignores command and boot timeout fields");
    f.q.boot_deadline = 1; waiting(0xfc00);
    CHECK(qbt_deadline(&f.q) == UINT64_MAX);
    f.q.info.state = 3; CHECK(qbt_deadline(&f.q) == UINT64_MAX);

    begin("scheduler queue and control work are immediately runnable");
    f.q.control_length = 1; CHECK(qbt_deadline(&f.q) == 0);
    f.q.control_length = 0; f.q.command_length = 4; CHECK(qbt_deadline(&f.q) == 0);
    f.uart_idle = false; CHECK(qbt_deadline(&f.q) == UINT64_MAX);

    begin("scheduler IBS wake retry and awake idle deadlines");
    f.q.tx_state = QBT_WAKING; f.q.retry_at = 17; CHECK(qbt_deadline(&f.q) == 17);
    f.q.tx_state = QBT_AWAKE; f.q.ibs = true; f.q.idle_at = 23;
    CHECK(qbt_deadline(&f.q) == 23);

    begin("wire drain wait polls at 1ms and respects command bound");
    f.uart_idle = false;
    CHECK(qbt_drain(&f.q, QBT_TX_POLL * 2 + 3) == -ETIMEDOUT);
    CHECK(f.wait_count == 3 && f.waits[0] == QBT_TX_POLL);
    CHECK(f.waits[1] == QBT_TX_POLL * 2 && f.waits[2] == QBT_TX_POLL * 2 + 3);

    begin("qbt_delay pumps and waits without checking expired boot budget");
    f.ns = 100; f.q.boot_deadline = 50; qbt_delay(&f.q, 1);
    CHECK(f.ns == 1000100 && f.q.stats.timeouts == 0 && !f.log_count);
}
static void commands(void)
{
    begin("qbt_command clears complete and old reply before send");
    f.q.complete = true; f.q.reply_length = 7; f.q.reply[0] = 0xff;
    CHECK(command(0xfc00) == -ETIMEDOUT);
    CHECK(!f.q.complete && f.q.reply_length == 0 && !f.q.waiting);
    CHECK(f.q.stats.commands == 1 && f.q.stats.tlv_sent == 1 && f.q.stats.tlv_acks == 0);

    begin("TX queue timeout counts enqueue but no reply");
    f.blocked = true; f.q.boot_deadline = QBT_TX_POLL;
    CHECK(command(0xfc00) == -ETIMEDOUT && f.q.stats.tlv_sent == 1);
    CHECK(f.q.command_length == 5 && !f.q.waiting && !f.q.complete);
    CHECK(f.wait_count == 1 && strstr(f.log, "budget exhausted"));

    begin("late same-opcode reply after new wait is accepted");
    schedule(0xfc00, 0, true, 1, 0);
    CHECK(command(0xfc00) == 0 && f.q.complete && !f.q.waiting);
    CHECK(f.q.stats.tlv_sent == 1 && f.q.stats.tlv_acks == 1);
    CHECK(f.pumps == 3); /* reply was accepted before the newly queued TX */

    begin("old report before new command does not preserve complete");
    report(0xfc00, 0, true); CHECK(!f.q.complete && f.q.stats.tlv_acks == 1);
    CHECK(command(0xfc00) == -ETIMEDOUT && f.q.stats.tlv_acks == 1);

    begin("nonzero TLV reply increments ack then times out");
    schedule(0xfc00, 1, true, 2, 0);
    CHECK(command(0xfc00) == -ETIMEDOUT && f.q.stats.tlv_acks == 1);
    CHECK(f.q.stats.tlv_final_status == 1 && !f.q.complete && !f.q.waiting);

    begin("local TX drain after boot budget can succeed before timeout check");
    f.ns = 101; f.q.boot_deadline = 100;
    { const uint8_t data[] = {0x1e};
      CHECK(qbt_send_command(&f.q, 0xfc00, data, sizeof data) == 0); }
    CHECK(f.q.stats.tlv_sent == 1 && f.q.stats.timeouts == 0 && !f.log_count);

    begin("second command has fresh complete but unchanged boot budget and stats");
    f.ns = 101; f.q.boot_deadline = 100; schedule(0xfc00, 0, true, 1, 101);
    CHECK(command(0xfc00) == 0 && f.q.boot_deadline == 100);
    CHECK(command(0xfc00) == -ETIMEDOUT && f.q.boot_deadline == 100);
    CHECK(f.q.stats.tlv_sent == 2 && f.q.stats.tlv_acks == 1);

    begin("busy and invalid commands do not enqueue or increment sent");
    f.q.waiting = true; CHECK(command(0xfc00) == -EBUSY);
    CHECK(qbt_send_command(&f.q, 0xfc00, NULL, 1) == -EINVAL && f.q.stats.tlv_sent == 0);
}
static void observations(void)
{
    struct hci_dev h = {.q = &f.q}; struct timing_config config = {0, 2}; unsigned count;
    begin("0515 sub-ms duration truncates to zero and includes failed attempt");
    count = 6; f.send_ns = 999999; f.send_error = -ETIMEDOUT;
    CHECK(measured_segment(&h, &config, &count) == -ETIMEDOUT && count == 7);
    CHECK(strstr(f.log, "i=6 size=243 dt_ms=0") && strstr(f.log, "sent=1 acks=1"));
    CHECK(f.sends == 1 && f.log_count == 1);

    begin("0515 duration is sampled before log callback overhead");
    count = 0; f.send_ns = 1000000; f.log_ns = 9000000;
    CHECK(measured_segment(&h, &config, &count) == 0 && count == 1);
    CHECK(strstr(f.log, "dt_ms=1 e=0") && f.ns == 10000000);

    begin("0515 summary reads cumulative counters and current final");
    f.q.stats.tlv_sent = 630; f.q.stats.tlv_acks = 28; f.q.stats.tlv_final_status = 1;
    measured_summary(&h, &config, 21, -ETIMEDOUT);
    CHECK(strstr(f.log, "type=2 segs=21 sent=630 acks=28 final=1") && f.log_count == 1);
}
int main(void)
{
    events(); deadlines(); scheduler(); commands(); observations();
    printf("PASS: %u source-C scenarios, %u assertions\n", cases, checks);
    return 0;
}
