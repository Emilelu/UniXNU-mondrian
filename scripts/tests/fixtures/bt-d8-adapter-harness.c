/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * HOST-ONLY harness for the d8 Bluetooth adapter and firmware-download path.
 *
 * This file includes the real qbt_core.c, qbt_linux.c and btqca.c that the
 * Python runner reconstructs from the frozen 235-patch d8 series.  Only the
 * qbt_platform callbacks, the firmware bytes and the controller events are
 * synthetic.  Nothing here is a controller, UART, DMA, IBS or hardware result.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <errno.h>

#include "qbt_linux.h"
#include "btqca.h"

/* Test-only hooks implemented in bt-d8-adapter-support.c, which owns the
 * qbt_linux.c translation unit and its static startup owner. */
extern void fixture_set_startup_owner(struct qbt *q);
extern int fixture_startup_owner_is_null(void);

#define LOG_MAX 262144
#define FW_MAX 700

struct fixture {
    struct qbt *q;
    uint64_t now;
    unsigned tx_seq, responded_seq;
    uint16_t last_op;
    uint8_t last_subop;
    size_t last_n;
    int early_response, early_done;
    int late_at, no_response;
    int force_status, force_tlv_status, force_short, skip_patch;
    int short_version, long_version, fail_reset, fail_bdaddr;
    int fail_tlv_at, drop_tlv_at, tlv_cmds;
    int fw_patch_primary_missing, fw_patch_fallback_missing;
    int fw_nvm_primary_missing, fw_nvm_fallback_missing;
    int fw_requests;
    char fw_order[8][64];
    int fw_order_count;
    int allocs, frees;
    int fw_puts;
    int hci_rx_count;
    int flow_off, flow_on;
    char log[LOG_MAX];
    size_t log_len;
    uint8_t patch[FW_MAX], nvm[FW_MAX];
    size_t patch_len, nvm_len;
};

static struct fixture F;
static struct fixture *G;
static struct hci_dev H;
static int fails;

#define CHECK(cond, ...) do { \
    if (!(cond)) { fails++; printf("FAIL %s:%d: ", __FILE__, __LINE__); \
        printf(__VA_ARGS__); printf("\n"); } \
} while (0)

static void fx_log_append(const char *text, int level) {
    int n;
    if (!G || G->log_len >= sizeof(G->log) - 1) return;
    n = snprintf(G->log + G->log_len, sizeof(G->log) - G->log_len,
                 "%d|%s\n", level, text);
    if (n > 0) G->log_len += (size_t)n < sizeof(G->log) - G->log_len
                                 ? (size_t)n : sizeof(G->log) - G->log_len - 1;
}

static void *fx_allocate(void *ctx, size_t n) {
    (void)ctx; F.allocs++; return calloc(1, n);
}
static void fx_release(void *ctx, void *p, size_t n) {
    (void)ctx; (void)n; if (p) { F.frees++; free(p); }
}
static uint64_t fx_now(void *ctx) { (void)ctx; return F.now; }
static size_t fx_uart_write(void *ctx, const uint8_t *data, size_t n) {
    size_t i;
    (void)ctx;
    for (i = 0; i < n; i++) {
        /* The controller answers WAKE_IND with WAKE_ACK.  Without it a command
         * issued while tx_state is QBT_ASLEEP never leaves the transport. */
        if (data[i] == 0xfd) {
            uint8_t ack = 0xfc;
            (void)qbt_receive(F.q, &ack, 1);
            continue;
        }
    }
    i = 0;
    while (i < n && (data[i] < 1 || data[i] > 5)) i++;
    if (i + 2 < n) {
        uint16_t op = (uint16_t)(data[i + 1] | ((uint16_t)data[i + 2] << 8));
        unsigned plen = i + 3 < n ? data[i + 3] : 0;
        /* In QCA_SKIP_EVT_VSE mode the controller does not answer the
         * non-final TLV segments; only the last segment is acked.  A full
         * segment carries two bytes of TLV header on top of 243 bytes. */
        if (F.skip_patch && op == 0xfc00 && plen == 245) return n;
        if (F.skip_patch && op == 0xfc00 && plen < 245) F.skip_patch = 0;
        F.last_n = n;
        F.last_op = op;
        F.last_subop = i + 4 < n ? data[i + 4] : 0;
        F.tx_seq++;
    }
    return n;
}
static bool fx_uart_drained(void *ctx) { (void)ctx; return true; }
static int fx_uart_speed(void *ctx, uint32_t speed) { (void)ctx; (void)speed; return 0; }
static int fx_uart_flow(void *ctx, bool on) { (void)ctx; if (on) F.flow_on++; else F.flow_off++; return 0; }
static int fx_clock(void *ctx, bool on) { (void)ctx; (void)on; return 0; }
static void fx_wait_until(void *ctx, uint64_t target) {
    (void)ctx;
    if (target > F.now) F.now = target;
}
static size_t fx_receive(void *ctx, const uint8_t *data, size_t n) {
    (void)ctx;
    return qbt_receive(F.q, data, n);
}

static int fx_firmware_get(void *ctx, const char *name, const uint8_t **data, size_t *size) {
    (void)ctx;
    if (F.fw_order_count < 8)
        snprintf(F.fw_order[F.fw_order_count++], 64, "%s", name);
    F.fw_requests++;
    if (strstr(name, "wcnhpbtfw")) {
        if (F.fw_patch_primary_missing) return -ENOENT;
        *data = F.patch; *size = F.patch_len; return 0;
    }
    if (strstr(name, "hpbtfw")) {
        if (F.fw_patch_fallback_missing) return -ENOENT;
        *data = F.patch; *size = F.patch_len; return 0;
    }
    if (strstr(name, "wcnhpnv")) {
        if (F.fw_nvm_primary_missing) return -ENOENT;
        *data = F.nvm; *size = F.nvm_len; return 0;
    }
    if (strstr(name, "hpnv")) {
        if (F.fw_nvm_fallback_missing) return -ENOENT;
        *data = F.nvm; *size = F.nvm_len; return 0;
    }
    return -ENOENT;
}
static void fx_firmware_put(void *ctx, const uint8_t *data, size_t n) {
    (void)ctx; (void)data; (void)n;
    F.fw_puts++;
}
static void fx_log(void *ctx, int level, const char *text) {
    (void)ctx; fx_log_append(text, level);
}

static void send_event(uint8_t op_lo, uint8_t op_hi, const uint8_t *payload,
                       size_t payload_len) {
    uint8_t buf[512];
    size_t n = 0;
    if (payload_len > 500) payload_len = 500;
    buf[n++] = 4;                    /* HCI event packet */
    buf[n++] = 0x0e;                 /* command complete */
    buf[n++] = (uint8_t)(3 + payload_len);
    buf[n++] = 1;                    /* ncmd */
    buf[n++] = op_lo; buf[n++] = op_hi;
    memcpy(buf + n, payload, payload_len); n += payload_len;
    fx_receive(NULL, buf, n);
}

static void send_tlv(int status) {
    uint8_t p[2] = { (uint8_t)status, 0x1e };
    send_event(0x00, 0xfc, p, sizeof(p));
}
static void send_version(void) {
    uint8_t p[15];
    uint32_t product = 1;
    uint16_t patch = 1, rom = 0x0201;
    uint32_t soc = 0x00001211;
    memset(p, 0, sizeof(p));
    p[1] = 0x19;                    /* EDL_PATCH_VER_REQ_CMD */
    memcpy(p + 3, &product, 4);
    memcpy(p + 7, &patch, 2);
    memcpy(p + 9, &rom, 2);
    memcpy(p + 11, &soc, 4);
    send_event(0x00, 0xfc, p, F.short_version ? 5 :
               F.long_version ? sizeof(p) + 1 : sizeof(p));
}
static void send_board_id(void) {
    uint8_t p[5] = { 0, 0x23, 0, 0, 0 };
    send_event(0x00, 0xfc, p, sizeof(p));
}
static void send_build_info(void) {
    const char label[] = "synthetic";
    uint8_t p[3 + sizeof(label)];
    p[0] = 0; p[1] = 0x20; p[2] = (uint8_t)(sizeof(label) - 1);
    memcpy(p + 3, label, sizeof(label) - 1);
    send_event(0x00, 0xfc, p, sizeof(p) - 1 + 1);
}
static void send_bdaddr(void) {
    uint8_t p[7] = { 0, 0, 0, 0, 0, 0, 0 };
    send_event(0x09, 0x10, p, sizeof(p));
}
static void send_generic(uint16_t op, int status) {
    uint8_t p[1] = { (uint8_t)status };
    send_event((uint8_t)(op & 0xff), (uint8_t)(op >> 8), p, sizeof(p));
}
static void send_short(uint16_t op) {
    /* A command-complete event with no return parameters. */
    send_event((uint8_t)(op & 0xff), (uint8_t)(op >> 8), NULL, 0);
}

static void respond(void) {
    uint16_t op = F.last_op ? F.last_op : F.q->wait_opcode;
    uint8_t sub = F.last_subop;
    if (op == 0x0c03 && F.fail_reset) { send_generic(op, 1); return; }
    if (op == 0xfc14 && F.fail_bdaddr) { send_generic(op, 1); return; }
    if (op == 0xfc00 && sub == 0x1e) {
        F.tlv_cmds++;
        if (F.drop_tlv_at && F.tlv_cmds == F.drop_tlv_at) return;
        int status = 0;
        if (F.force_tlv_status >= 0) { status = F.force_tlv_status; F.force_tlv_status = -1; }
        else if (F.fail_tlv_at && F.tlv_cmds == F.fail_tlv_at) status = 1;
        send_tlv(status);
        return;
    }
    if (op == 0xfc00 && sub == 0x19) { send_version(); return; }
    if (op == 0xfc00 && sub == 0x23) { send_board_id(); return; }
    if (op == 0xfc00 && sub == 0x20) { send_build_info(); return; }
    if (op == 0x1009) { send_bdaddr(); return; }
    if (F.force_short) { F.force_short = 0; send_short(op); return; }
    int status = 0;
    if (F.force_status >= 0) { status = F.force_status; F.force_status = -1; }
    send_generic(op, status);
}

static void fx_pump(void *ctx) {
    (void)ctx;
    if (!F.q || !F.q->waiting) return;
    if (F.early_response && !F.early_done) {
        F.early_done = 1;
        F.responded_seq = F.tx_seq;
        respond();
        return;
    }
    if (F.no_response) return;
    if (F.late_at && F.now < (uint64_t)F.late_at) return;
    if (F.tx_seq == F.responded_seq) return;
    F.responded_seq = F.tx_seq;
    respond();
}

static const struct qbt_platform platform = {
    .context = &F,
    .allocate = fx_allocate,
    .release = fx_release,
    .now_ns = fx_now,
    .uart_write = fx_uart_write,
    .uart_drained = fx_uart_drained,
    .uart_speed = fx_uart_speed,
    .uart_flow = fx_uart_flow,
    .clock = fx_clock,
    .pump = fx_pump,
    .wait_until = fx_wait_until,
    .receive = fx_receive,
    .firmware_get = fx_firmware_get,
    .firmware_put = fx_firmware_put,
    .log = fx_log,
};

static void make_patch(int mode, int size) {
    uint32_t type_len, total, dlen;
    memset(F.patch, 0, sizeof(F.patch));
    F.patch_len = (size_t)size;
    type_len = ((uint32_t)(size - 4) << 8) | 1u;
    memcpy(F.patch, &type_len, 4);
    total = (uint32_t)(size - 4);
    dlen = (uint32_t)(size - 28);
    memcpy(F.patch + 4, &total, 4);
    memcpy(F.patch + 8, &dlen, 4);
    F.patch[4 + 10] = (uint8_t)mode;
    for (int i = 28; i < size; i++) F.patch[i] = 0xaa;
}
static void make_nvm(int size) {
    uint32_t type_len;
    int off = 4;
    memset(F.nvm, 0, sizeof(F.nvm));
    F.nvm_len = (size_t)size;
    type_len = ((uint32_t)(size - 4) << 8) | 2u;
    memcpy(F.nvm, &type_len, 4);
    /* TAG BD_ADDR, len 6 */
    F.nvm[off] = 2; F.nvm[off + 1] = 0; F.nvm[off + 2] = 6; F.nvm[off + 3] = 0;
    off += 12; off += 6;
    /* TAG HCI, len 3 */
    F.nvm[off] = 17; F.nvm[off + 1] = 0; F.nvm[off + 2] = 3; F.nvm[off + 3] = 0;
    off += 12; off += 3;
    /* TAG DEEP_SLEEP, len 1 */
    F.nvm[off] = 27; F.nvm[off + 1] = 0; F.nvm[off + 2] = 1; F.nvm[off + 3] = 0;
    off += 12; off += 1;
    (void)off;
}

static void reset_fixture(void) {
    if (F.q) { qbt_destroy(F.q); F.q = NULL; }
    memset(&F, 0, sizeof(F));
    G = &F;
    F.now = 1000;
    F.force_status = -1;
    F.force_tlv_status = -1;
    make_patch(0, 500);
    make_nvm(500);
    F.q = qbt_create(&platform);
    CHECK(F.q != NULL, "qbt_create");
    memset(&H, 0, sizeof(H));
    if (F.q) { H.q = F.q; H.dev.q = F.q; }
}

static int log_has(const char *needle) {
    return strstr(F.log, needle) != NULL;
}
static int log_count(const char *needle) {
    int n = 0; const char *p = F.log;
    while ((p = strstr(p, needle)) != NULL) { n++; p += strlen(needle); }
    return n;
}

/* ---- scenario A: Linux HCI adapter ---- */
static int scenario_adapter_status(void) {
    uint8_t addr[6] = {0xee,0x98,0xc5,0x8a,0x6b,0x4e};
    struct sk_buff *s;
    reset_fixture();
    fixture_set_startup_owner(F.q);
    F.force_status = 0xff;
    s = __hci_cmd_sync_ev(&H, 0xfc14, 6, addr, 0, HCI_INIT_TIMEOUT);
    CHECK(IS_ERR(s) && PTR_ERR(s) == -EIO, "nonzero HCI status is -EIO, got %ld",
          IS_ERR(s) ? (long)PTR_ERR(s) : 0L);
    F.force_status = -1;
    s = __hci_cmd_sync_ev(&H, 0xfc14, 6, addr, 0, HCI_INIT_TIMEOUT);
    CHECK(!IS_ERR(s) && s->len == 1 && s->data[0] == 0,
          "successful HCI status is visible");
    if (!IS_ERR(s)) kfree_skb(s);
    fixture_set_startup_owner(NULL);
    return fails == 0;
}

static int scenario_adapter_short(void) {
    uint8_t addr[6] = {0xee,0x98,0xc5,0x8a,0x6b,0x4e};
    struct sk_buff *s;
    reset_fixture();
    fixture_set_startup_owner(F.q);
    F.force_short = 1;
    s = __hci_cmd_sync_ev(&H, 0xfc14, 6, addr, 0, HCI_INIT_TIMEOUT);
    CHECK(IS_ERR(s) && PTR_ERR(s) == -EIO, "empty command-complete payload is -EIO");
    fixture_set_startup_owner(NULL);
    return fails == 0;
}

static int scenario_adapter_timeout(void) {
    uint8_t addr[6] = {0xee,0x98,0xc5,0x8a,0x6b,0x4e};
    struct sk_buff *s;
    reset_fixture();
    fixture_set_startup_owner(F.q);
    F.no_response = 1;
    s = __hci_cmd_sync_ev(&H, 0xfc14, 6, addr, 0, HCI_INIT_TIMEOUT);
    CHECK(IS_ERR(s) && PTR_ERR(s) == -ETIMEDOUT, "no event is -ETIMEDOUT");
    CHECK(F.q->stats.timeouts >= 1, "timeouts counter");
    fixture_set_startup_owner(NULL);
    return fails == 0;
}

static int scenario_adapter_tlv_status(void) {
    uint8_t cmd[2] = {0x1e, 0};
    struct sk_buff *s;
    reset_fixture();
    fixture_set_startup_owner(F.q);
    F.force_tlv_status = 1;
    s = __hci_cmd_sync_ev(&H, 0xfc00, 2, cmd, 0, HCI_INIT_TIMEOUT);
    CHECK(IS_ERR(s) && PTR_ERR(s) == -ETIMEDOUT,
          "nonzero TLV ack does not complete the wait");
    CHECK(F.q->stats.tlv_acks == 1, "nonzero TLV ack counted: %llu",
          (unsigned long long)F.q->stats.tlv_acks);
    CHECK(F.q->stats.tlv_final_status == 1, "final status records 1");
    fixture_set_startup_owner(NULL);
    return fails == 0;
}

static int scenario_adapter_late(void) {
    uint8_t addr[6] = {0xee,0x98,0xc5,0x8a,0x6b,0x4e};
    struct sk_buff *s;
    reset_fixture();
    fixture_set_startup_owner(F.q);
    F.late_at = (int)QBT_COMMAND_TIMEOUT;
    s = __hci_cmd_sync_ev(&H, 0xfc14, 6, addr, 0, HCI_INIT_TIMEOUT);
    CHECK(!IS_ERR(s), "late event can satisfy the predicate");
    CHECK(F.now >= QBT_COMMAND_TIMEOUT, "late event arrived at the deadline");
    if (!IS_ERR(s)) kfree_skb(s);
    fixture_set_startup_owner(NULL);
    return fails == 0;
}

static int scenario_adapter_early(void) {
    uint8_t addr[6] = {0xee,0x98,0xc5,0x8a,0x6b,0x4e};
    uint8_t reply[64]; size_t len = sizeof(reply);
    int e;
    reset_fixture();
    F.early_response = 1;
    F.no_response = 1;             /* only the event before TX can complete it */
    e = qbt_command(F.q, 0xfc14, addr, 6, 0, reply, &len);
    CHECK(e == 0, "same-opcode event before TX completes the wait: %d", e);
    CHECK(F.tx_seq == 1, "the command was still sent after the early event");
    return fails == 0;
}

/* ---- scenario B: complete download and fallback ---- */
static int scenario_download_success(void) {
    struct qca_btsoc_version ver = {1, 1, 0x0201, 0x1211};
    int e;
    reset_fixture();
    fixture_set_startup_owner(F.q);
    e = qca_uart_setup(&H, QCA_BAUDRATE_115200, QCA_WCN6855, ver, NULL, NULL);
    fixture_set_startup_owner(NULL);
    CHECK(e == 0, "download success: %d", e);
    CHECK(log_has("QCA controller version 0x12110201"), "version line");
    CHECK(log_has("tlv done type=1 segs=3 sent=3 acks=3 final=0 ret=0"),
          "patch summary");
    CHECK(log_has("tlv done type=2 segs=3 sent=6 acks=6 final=0 ret=0"),
          "nvm summary");
    CHECK(log_has("boot: rampatch done"), "rampatch done");
    CHECK(log_has("boot: nvm done"), "nvm done");
    CHECK(log_has("boot: hci reset done"), "reset done");
    CHECK(log_has("boot: bdaddr check done"), "bdaddr check done");
    CHECK(F.fw_requests == 2 && F.fw_puts == 2,
          "patch and NVM buffers are each released once: requests=%d puts=%d",
          F.fw_requests, F.fw_puts);
    return fails == 0;
}

static int scenario_download_fallback_success(void) {
    struct qca_btsoc_version ver = {1, 1, 0x0201, 0x1211};
    int e;
    reset_fixture();
    F.fail_tlv_at = 5;             /* patch 3 + NVM first segment 2 */
    fixture_set_startup_owner(F.q);
    e = qca_uart_setup(&H, QCA_BAUDRATE_115200, QCA_WCN6855, ver, NULL, NULL);
    fixture_set_startup_owner(NULL);
    CHECK(e == 0, "fallback success: %d", e);
    /* Host libc spells ETIMEDOUT 110; the XNU image spells it 60.  The
     * semantic assertion is the segment count and the timeout result. */
    CHECK(log_has("tlv done type=2 segs=2 sent=5 acks=5 final=1 ret=-110"),
          "first NVM attempt is 2 segments and a timeout");
    CHECK(log_has("tlv done type=2 segs=3 sent=8 acks=8 final=0 ret=0"),
          "fallback segs are 3 and sent/acks are cumulative");
    CHECK(log_has("QCA Downloading qca/wcnhpnv21g.bin"), "primary NVM name");
    CHECK(log_has("QCA Downloading qca/hpnv21g.bin"), "fallback NVM name");
    CHECK(log_has("boot: nvm done"), "fallback reached nvm done");
    CHECK(!log_has("sent=0 acks=0"), "sent/acks never reset inside the boot");
    return fails == 0;
}

static int scenario_download_fallback_failure(void) {
    struct qca_btsoc_version ver = {1, 1, 0x0201, 0x1211};
    int e;
    reset_fixture();
    F.fail_tlv_at = 5;
    F.drop_tlv_at = 6;
    fixture_set_startup_owner(F.q);
    e = qca_uart_setup(&H, QCA_BAUDRATE_115200, QCA_WCN6855, ver, NULL, NULL);
    fixture_set_startup_owner(NULL);
    CHECK(e == -ETIMEDOUT, "both NVM attempts fail: %d", e);
    CHECK(log_count("tlv done type=2") == 2, "two NVM summaries");
    CHECK(!log_has("boot: nvm done"), "no nvm done");
    CHECK(F.fw_order_count >= 3, "primary and fallback were requested");
    return fails == 0;
}

static int scenario_download_nvm_missing(void) {
    struct qca_btsoc_version ver = {1, 1, 0x0201, 0x1211};
    int e;
    reset_fixture();
    F.fw_nvm_primary_missing = 1;
    fixture_set_startup_owner(F.q);
    e = qca_uart_setup(&H, QCA_BAUDRATE_115200, QCA_WCN6855, ver, NULL, NULL);
    fixture_set_startup_owner(NULL);
    CHECK(e == 0, "missing primary NVM falls back to hpnv: %d", e);
    CHECK(log_has("QCA Failed to request file: qca/wcnhpnv21g.bin"), "primary miss logged");
    CHECK(log_has("QCA Downloading qca/hpnv21g.bin"), "fallback requested");
    return fails == 0;
}

static int scenario_download_patch_fallback(void) {
    struct qca_btsoc_version ver = {1, 1, 0x0201, 0x1211};
    int e;
    reset_fixture();
    F.fw_patch_primary_missing = 1;
    fixture_set_startup_owner(F.q);
    e = qca_uart_setup(&H, QCA_BAUDRATE_115200, QCA_WCN6855, ver, NULL, NULL);
    fixture_set_startup_owner(NULL);
    CHECK(e == 0, "missing primary rampatch falls back: %d", e);
    CHECK(log_has("QCA Downloading qca/hpbtfw21.tlv"), "rampatch fallback requested");
    CHECK(log_has("boot: rampatch done"), "rampatch fallback done");
    return fails == 0;
}

static int scenario_download_skip_mode(void) {
    struct qca_btsoc_version ver = {1, 1, 0x0201, 0x1211};
    int e;
    reset_fixture();
    make_patch(1, 500);            /* QCA_SKIP_EVT_VSE: __hci_cmd_send */
    F.skip_patch = 1;
    fixture_set_startup_owner(F.q);
    e = qca_uart_setup(&H, QCA_BAUDRATE_115200, QCA_WCN6855, ver, NULL, NULL);
    fixture_set_startup_owner(NULL);
    CHECK(e == 0, "skip-mode download: %d", e);
    CHECK(F.q->stats.tlv_acks == 4,
          "skip mode acks the final patch segment plus all NVM segments");
    CHECK(log_has("tlv done type=1 segs=3"), "patch summary in skip mode");
    CHECK(log_has("boot: nvm done"), "skip mode reached nvm done");
    return fails == 0;
}

/* ---- scenario C: qbt_boot lifecycle ---- */
static int scenario_boot_success(void) {
    uint8_t addr[6] = {0xee,0x98,0xc5,0x8a,0x6b,0x4e};
    int e;
    reset_fixture();
    e = qbt_boot(F.q, 115200, addr);
    CHECK(e == 0, "qbt_boot success: %d", e);
    CHECK(F.q->info.state == 2, "state ready");
    CHECK(F.q->info.error == 0, "error cleared");
    CHECK(F.q->info.baud == 115200, "baud 115200");
    CHECK(F.q->info.soc == 0x1211, "soc id");
    CHECK(F.q->info.rom == 0x0201, "rom version");
    CHECK(F.q->stats.resets == 1, "successful boot counts one reset");
    CHECK(F.q->boot_deadline == 0, "boot deadline disarmed");
    CHECK(fixture_startup_owner_is_null(), "startup owner released");
    CHECK(F.q->ibs == true, "ibs armed");
    CHECK(log_has("boot: return e=0"), "boot return line");
    return fails == 0;
}

static int scenario_boot_failure_cleanup(void) {
    uint8_t addr[6] = {0xee,0x98,0xc5,0x8a,0x6b,0x4e};
    int e;
    reset_fixture();
    F.fail_tlv_at = 5;
    F.drop_tlv_at = 6;
    e = qbt_boot(F.q, 115200, addr);
    CHECK(e == -ETIMEDOUT, "qbt_boot failure: %d", e);
    CHECK(F.q->info.state == 3, "state failed");
    CHECK(F.q->info.error == -ETIMEDOUT, "error recorded");
    CHECK(F.q->boot_deadline == 0, "boot deadline disarmed after failure");
    CHECK(fixture_startup_owner_is_null(), "startup owner released after failure");
    CHECK(F.q->ibs == false, "ibs cleared");
    CHECK(F.q->command_length == 0 && F.q->command_offset == 0,
          "command state cleared");
    CHECK(F.q->retry_at == 0 && F.q->idle_at == 0, "timers cleared");
    CHECK(F.q->stats.resets == 0, "failed boot does not count a reset");
    CHECK(!log_has("boot: set bdaddr done"), "set bdaddr skipped");
    return fails == 0;
}

static int scenario_boot_fallback_success(void) {
    uint8_t addr[6] = {0xee,0x98,0xc5,0x8a,0x6b,0x4e};
    int e;
    reset_fixture();
    F.fail_tlv_at = 5;
    e = qbt_boot(F.q, 115200, addr);
    CHECK(e == 0, "qbt_boot survives NVM fallback: %d", e);
    CHECK(F.q->info.state == 2, "state ready after fallback");
    CHECK(log_has("QCA Downloading qca/hpnv21g.bin"), "fallback in boot path");
    CHECK(log_has("boot: set bdaddr done e=0"), "bdaddr set after fallback");
    return fails == 0;
}

static int scenario_adapter_version_mismatch(void) {
    struct qca_btsoc_version ver;
    int e;
    reset_fixture();
    fixture_set_startup_owner(F.q);
    F.short_version = 1;
    e = qca_read_soc_version(&H, &ver, QCA_WCN6855);
    CHECK(e == -EILSEQ, "short version payload is -EILSEQ: %d", e);
    fixture_set_startup_owner(NULL);
    return fails == 0;
}

static int scenario_adapter_version_overlong(void) {
    struct qca_btsoc_version ver;
    int e;
    reset_fixture();
    fixture_set_startup_owner(F.q);
    F.long_version = 1;
    e = qca_read_soc_version(&H, &ver, QCA_WCN6855);
    CHECK(e == -EILSEQ, "overlong version payload is -EILSEQ: %d", e);
    fixture_set_startup_owner(NULL);
    return fails == 0;
}

static int scenario_download_alt_already_bin(void) {
    struct qca_btsoc_version ver = {1, 1, 0x0201, 0x1211};
    int e;
    reset_fixture();
    fixture_set_startup_owner(F.q);
    e = qca_uart_setup(&H, QCA_BAUDRATE_115200, QCA_WCN6855, ver,
                       "synthetic.bin", NULL);
    fixture_set_startup_owner(NULL);
    CHECK(e == -ENOENT, "already-.bin NVM request fails once: %d", e);
    CHECK(F.fw_order_count == 2, "patch then one NVM request: %d",
          F.fw_order_count);
    CHECK(strcmp(F.fw_order[1], "qca/synthetic.bin") == 0,
          "NVM name is unchanged: %s", F.fw_order[1]);
    CHECK(F.fw_puts == 1, "only the successful patch was released: %d",
          F.fw_puts);
    return fails == 0;
}

static int scenario_download_alt_name(void) {
    struct qca_btsoc_version ver = {1, 1, 0x0201, 0x1211};
    int e;
    reset_fixture();
    fixture_set_startup_owner(F.q);
    e = qca_uart_setup(&H, QCA_BAUDRATE_115200, QCA_WCN6855, ver,
                       "synthetic.tlv", NULL);
    fixture_set_startup_owner(NULL);
    CHECK(e == -ENOENT, "both synthetic NVM names fail: %d", e);
    CHECK(F.fw_order_count == 3, "patch, .tlv, .bin requests: %d",
          F.fw_order_count);
    CHECK(strcmp(F.fw_order[1], "qca/synthetic.tlv") == 0,
          "first NVM name: %s", F.fw_order[1]);
    CHECK(strcmp(F.fw_order[2], "qca/synthetic.bin") == 0,
          "alt NVM name: %s", F.fw_order[2]);
    CHECK(F.fw_puts == 1, "only the successful patch was released: %d",
          F.fw_puts);
    return fails == 0;
}

static int scenario_boot_patch_fail(void) {
    uint8_t addr[6] = {0xee,0x98,0xc5,0x8a,0x6b,0x4e};
    int e;
    reset_fixture();
    F.fw_patch_primary_missing = 1;
    F.fw_patch_fallback_missing = 1;
    e = qbt_boot(F.q, 115200, addr);
    CHECK(e == -ENOENT, "rampatch failure stops the boot: %d", e);
    CHECK(F.q->info.state == 3, "state failed after rampatch failure");
    CHECK(F.q->info.error == -ENOENT, "rampatch error recorded: %d",
          F.q->info.error);
    CHECK(F.q->boot_deadline == 0, "boot deadline disarmed after patch failure");
    CHECK(fixture_startup_owner_is_null(), "startup owner released after patch failure");
    CHECK(!log_has("QCA Downloading qca/wcnhpnv21g.bin"),
          "NVM is not requested after rampatch failure");
    return fails == 0;
}

static int scenario_boot_bdaddr_fail(void) {
    uint8_t addr[6] = {0xee,0x98,0xc5,0x8a,0x6b,0x4e};
    int e;
    reset_fixture();
    F.fail_bdaddr = 1;
    e = qbt_boot(F.q, 115200, addr);
    CHECK(e == -EIO, "bdaddr failure is returned: %d", e);
    CHECK(F.q->info.state == 3, "state failed after bdaddr failure");
    CHECK(F.q->info.error == -EIO, "bdaddr error recorded: %d", F.q->info.error);
    CHECK(F.q->boot_deadline == 0, "boot deadline disarmed after bdaddr failure");
    CHECK(fixture_startup_owner_is_null(), "startup owner released after bdaddr failure");
    CHECK(log_has("boot: set bdaddr done e=-5"), "bdaddr stage reports -EIO");
    return fails == 0;
}

static int scenario_boot_reset_fail(void) {
    uint8_t addr[6] = {0xee,0x98,0xc5,0x8a,0x6b,0x4e};
    int e;
    reset_fixture();
    F.fail_reset = 1;
    e = qbt_boot(F.q, 115200, addr);
    CHECK(e == -EIO, "HCI reset failure is returned: %d", e);
    CHECK(F.q->info.state == 3, "state failed after reset failure");
    CHECK(F.q->info.error == -EIO, "reset error recorded: %d", F.q->info.error);
    CHECK(F.q->boot_deadline == 0, "boot deadline disarmed after reset failure");
    CHECK(fixture_startup_owner_is_null(), "startup owner released after reset failure");
    CHECK(!log_has("boot: bdaddr check done"), "bdaddr check skipped after reset failure");
    return fails == 0;
}

static void scenario_all(void) {
    struct { const char *name; int (*fn)(void); } cases[] = {
        {"adapter_status", scenario_adapter_status},
        {"adapter_short", scenario_adapter_short},
        {"adapter_timeout", scenario_adapter_timeout},
        {"adapter_tlv_status", scenario_adapter_tlv_status},
        {"adapter_late", scenario_adapter_late},
        {"adapter_early", scenario_adapter_early},
        {"download_success", scenario_download_success},
        {"download_fallback_success", scenario_download_fallback_success},
        {"download_fallback_failure", scenario_download_fallback_failure},
        {"download_nvm_missing", scenario_download_nvm_missing},
        {"download_patch_fallback", scenario_download_patch_fallback},
        {"download_skip_mode", scenario_download_skip_mode},
        {"boot_success", scenario_boot_success},
        {"boot_failure_cleanup", scenario_boot_failure_cleanup},
        {"boot_fallback_success", scenario_boot_fallback_success},
        {"adapter_version_mismatch", scenario_adapter_version_mismatch},
        {"adapter_version_overlong", scenario_adapter_version_overlong},
        {"download_alt_already_bin", scenario_download_alt_already_bin},
        {"download_alt_name", scenario_download_alt_name},
        {"boot_patch_fail", scenario_boot_patch_fail},
        {"boot_bdaddr_fail", scenario_boot_bdaddr_fail},
        {"boot_reset_fail", scenario_boot_reset_fail},
    };
    for (unsigned i = 0; i < sizeof(cases)/sizeof(cases[0]); i++) {
        fails = 0;
        int ok = cases[i].fn();
        printf("RESULT %s %s failures=%d\n", cases[i].name, ok ? "PASS" : "FAIL", fails);
        if (F.log_len) {
            fwrite(F.log, 1, F.log_len, stdout);
            fputc('\n', stdout);
        }
        if (!ok) exit(1);
    }
}

int main(int argc, char **argv) {
    if (argc < 2) {
        printf("usage: %s <scenario>\n", argv[0]);
        return 2;
    }
    if (strcmp(argv[1], "all") == 0) {
        scenario_all();
        return 0;
    }
    struct { const char *name; int (*fn)(void); } cases[] = {
        {"adapter_status", scenario_adapter_status},
        {"adapter_short", scenario_adapter_short},
        {"adapter_timeout", scenario_adapter_timeout},
        {"adapter_tlv_status", scenario_adapter_tlv_status},
        {"adapter_late", scenario_adapter_late},
        {"adapter_early", scenario_adapter_early},
        {"download_success", scenario_download_success},
        {"download_fallback_success", scenario_download_fallback_success},
        {"download_fallback_failure", scenario_download_fallback_failure},
        {"download_nvm_missing", scenario_download_nvm_missing},
        {"download_patch_fallback", scenario_download_patch_fallback},
        {"download_skip_mode", scenario_download_skip_mode},
        {"boot_success", scenario_boot_success},
        {"boot_failure_cleanup", scenario_boot_failure_cleanup},
        {"boot_fallback_success", scenario_boot_fallback_success},
        {"adapter_version_mismatch", scenario_adapter_version_mismatch},
        {"adapter_version_overlong", scenario_adapter_version_overlong},
        {"download_alt_already_bin", scenario_download_alt_already_bin},
        {"download_alt_name", scenario_download_alt_name},
        {"boot_patch_fail", scenario_boot_patch_fail},
        {"boot_bdaddr_fail", scenario_boot_bdaddr_fail},
        {"boot_reset_fail", scenario_boot_reset_fail},
    };
    for (unsigned i = 0; i < sizeof(cases)/sizeof(cases[0]); i++) {
        if (strcmp(argv[1], cases[i].name) == 0) {
            fails = 0;
            int ok = cases[i].fn();
            printf("RESULT %s %s failures=%d\n", cases[i].name, ok ? "PASS" : "FAIL", fails);
            if (F.log_len) { fwrite(F.log, 1, F.log_len, stdout); fputc('\n', stdout); }
            return ok ? 0 : 1;
        }
    }
    printf("unknown scenario %s\n", argv[1]);
    return 2;
}