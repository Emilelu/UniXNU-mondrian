/* SPDX-License-Identifier: GPL-2.0-only */
/* Register model for the K60 GENI SE UART engine at 0x00894000.
 *
 * The board adapter in bsd/dev/qbt_k60.c cannot run on a host: it maps
 * MMIO, owns the Apps SMMU and talks to the GIC.  The engine below it,
 * bsd/dev/qbt/qbt_geni.c, only reaches the hardware through struct
 * qbt_geni_ops, so this file supplies that interface over a register file
 * and drives the real engine source.
 *
 * It is a model: it proves the sequence and the arithmetic, not the part.
 */
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "qbt_geni.h"
#include "qbt_geni_regs.h"

#define MODEL_REGS 0x1000u

struct model {
    uint32_t reg[MODEL_REGS];
    uint32_t enable[MODEL_REGS];
    uint8_t touched[MODEL_REGS];
    unsigned touched_count;
    uint8_t tx[QBT_GENI_TX_SIZE] __attribute__((aligned(64)));
    uint8_t rx[QBT_GENI_RX_COUNT][QBT_GENI_RX_SIZE] __attribute__((aligned(64)));
    uint8_t received[8192];
    size_t received_bytes;
    uint64_t now;
    unsigned barriers, syncs, wakeups, receives, irq_unmasked;
    bool last_irq_mask;
    size_t last_sync_bytes;
    bool last_sync_for_device, last_sync_tx;
};

static unsigned failures;
static unsigned assertions;

static void expect(bool ok, const char *what) {
    assertions++;
    if (ok) {
        printf("PASS %s\n", what);
    } else {
        failures++;
        printf("FAIL %s\n", what);
    }
}

static void expect_u32(uint32_t got, uint32_t want, const char *what) {
    assertions++;
    if (got == want) {
        printf("PASS %s = 0x%x\n", what, got);
    } else {
        failures++;
        printf("FAIL %s: got 0x%x want 0x%x\n", what, got, want);
    }
}

static void expect_int(int got, int want, const char *what) {
    assertions++;
    if (got == want) {
        printf("PASS %s = %d\n", what, got);
    } else {
        failures++;
        printf("FAIL %s: got %d want %d\n", what, got, want);
    }
}

static void touch(struct model *m, uint32_t off) {
    unsigned i = off / 4u;
    if (i >= MODEL_REGS) abort();
    if (!m->touched[i]) {
        m->touched[i] = 1;
        m->touched_count++;
    }
}

static uint32_t model_read(void *ctx, uint32_t off) {
    struct model *m = ctx;
    touch(m, off);
    return m->reg[off / 4u];
}

static void model_write(void *ctx, uint32_t off, uint32_t value) {
    struct model *m = ctx;
    unsigned i = off / 4u;
    touch(m, off);
    switch (off) {
    /* The clear registers drop status bits; the engine reads status first. */
    case G_M_CLEAR: m->reg[G_M_IRQ / 4u] &= ~value; break;
    case G_S_CLEAR: m->reg[G_S_IRQ / 4u] &= ~value; break;
    case G_TX_CLEAR: m->reg[G_TX_IRQ / 4u] &= ~value; break;
    case G_RX_CLEAR: m->reg[G_RX_IRQ / 4u] &= ~value; break;
    /* The set/unset registers gate the interrupt sources, not the status. */
    case G_TX_IRQ_SET: m->enable[G_TX_IRQ / 4u] |= value; break;
    case G_TX_IRQ_UNSET: m->enable[G_TX_IRQ / 4u] &= ~value; break;
    case G_RX_IRQ_SET: m->enable[G_RX_IRQ / 4u] |= value; break;
    case G_RX_IRQ_UNSET: m->enable[G_RX_IRQ / 4u] &= ~value; break;
    default: m->reg[i] = value; break;
    }
}

static void model_barrier(void *ctx) { ((struct model *)ctx)->barriers++; }

static void model_sync(void *ctx, const struct qbt_dma_buffer *b, size_t n,
                       bool for_device, bool tx) {
    struct model *m = ctx;
    m->syncs++;
    m->last_sync_bytes = n;
    m->last_sync_for_device = for_device;
    m->last_sync_tx = tx;
    (void)b;
}

static uint64_t model_now(void *ctx) { return ((struct model *)ctx)->now; }

static void model_irq_mask(void *ctx, bool masked) {
    struct model *m = ctx;
    m->last_irq_mask = masked;
    if (!masked) m->irq_unmasked++;
}

static void model_wake(void *ctx) { ((struct model *)ctx)->wakeups++; }

static size_t model_receive(void *ctx, const uint8_t *bytes, size_t n) {
    struct model *m = ctx;
    m->receives++;
    if (m->received_bytes + n > sizeof(m->received)) n = sizeof(m->received) - m->received_bytes;
    memcpy(m->received + m->received_bytes, bytes, n);
    m->received_bytes += n;
    return n;
}

struct rig {
    struct model m;
    struct qbt_geni geni;
    struct qbt_dma_buffer tx, rx[QBT_GENI_RX_COUNT];
};

static void rig_init(struct rig *r) {
    memset(r, 0, sizeof(*r));
    r->tx.bytes = r->m.tx;
    r->tx.address = (uint64_t)(uintptr_t)r->m.tx;
    r->tx.capacity = sizeof(r->m.tx);
    for (unsigned i = 0; i < QBT_GENI_RX_COUNT; i++) {
        r->rx[i].bytes = r->m.rx[i];
        r->rx[i].address = (uint64_t)(uintptr_t)r->m.rx[i];
        r->rx[i].capacity = sizeof(r->m.rx[i]);
    }
    /* Protocol 2 microcode, idle engine, 8-deep FIFO: what a booted SE shows. */
    r->m.reg[G_FW_REV / 4u] = 0x00000200u;
    r->m.reg[G_HW_PARAM1 / 4u] = 8u << 16;
}

static struct qbt_geni_ops ops_for(struct model *m) {
    struct qbt_geni_ops ops = {
        .context = m,
        .read = model_read,
        .write = model_write,
        .barrier = model_barrier,
        .sync = model_sync,
        .now_ns = model_now,
        .irq_mask = model_irq_mask,
        .wake_worker = model_wake,
        .receive = model_receive,
    };
    return ops;
}

static int rig_prepare(struct rig *r) {
    struct qbt_geni_ops ops = ops_for(&r->m);
    return qbt_geni_prepare(&r->geni, &ops, &r->tx, r->rx);
}

/* Bring the engine to RUN at 3 Mbaud, the rate the board publishes. */
static void rig_run(struct rig *r) {
    rig_init(r);
    if (rig_prepare(r)) abort();
    if (qbt_geni_set_rate(&r->geni, 3000000u, 48000000u, 16u)) abort();
    if (qbt_geni_start(&r->geni)) abort();
}

static void scenario_prepare(void) {
    struct rig r;
    rig_init(&r);
    r.m.reg[G_FW_REV / 4u] = 0x00000100u;
    expect_int(rig_prepare(&r), -ENXIO, "protocol 1 microcode is refused");
    rig_init(&r);
    r.m.reg[G_STATUS / 4u] = G_M_ACTIVE;
    expect_int(rig_prepare(&r), -EBUSY, "an active sequencer is refused");
    rig_init(&r);
    r.m.reg[G_HW_PARAM1 / 4u] = 2u << 16;
    expect_int(rig_prepare(&r), -ENXIO, "a two-deep FIFO is refused");
    rig_init(&r);
    expect_int(rig_prepare(&r), 0, "prepare accepts a protocol 2 engine");
    expect_int((int)r.geni.state, QBT_GENI_STOPPED, "prepare leaves the engine stopped");
    expect_u32(r.m.reg[G_TX_PACK0 / 4u], 0x4380eu, "TX packing follows geni_se_config_packing");
    expect_u32(r.m.reg[G_RX_PACK1 / 4u], 0xc3e0eu, "RX packing follows geni_se_config_packing");
    expect_u32(r.m.reg[G_RX_WM / 4u], 2u, "RX watermark");
    expect_u32(r.m.reg[G_RX_RFR_WM / 4u], 6u, "RX RFR watermark is depth-2");
    expect_u32(r.m.reg[G_MANUAL_RFR / 4u], G_RFR_OFF, "prepare parks RTS");
    expect_u32(r.m.reg[G_IRQ_EN / 4u], 0u, "prepare leaves the engine IRQ off");
    expect(r.m.last_irq_mask, "prepare masks the GIC line");
}

static void scenario_rate(void) {
    struct rig r;
    rig_init(&r);
    if (rig_prepare(&r)) abort();
    expect_int(qbt_geni_set_rate(&r.geni, 3000000u, 48000000u, 16u), 0,
               "3 Mbaud from 48 MHz at 16x is exact");
    expect_u32(r.m.reg[G_M_CLK / 4u], 0x11u, "M_CLK divider 1 with the clock on");
    expect_u32(r.m.reg[G_S_CLK / 4u], 0x11u, "S_CLK divider 1 with the clock on");
    expect_int(qbt_geni_set_rate(&r.geni, 3200000u, 48000000u, 16u), -ERANGE,
               "3.2 Mbaud from 48 MHz is refused, which is why the board publishes 3.0");
    expect_int(qbt_geni_set_rate(&r.geni, 3000000u, 48000000u, 8u), -EINVAL,
               "8x oversampling is refused");
    expect_int(qbt_geni_set_rate(&r.geni, 0u, 48000000u, 16u), -EINVAL, "a zero baud is refused");
}

static void scenario_start(void) {
    struct rig r;
    rig_run(&r);
    expect_int((int)r.geni.state, QBT_GENI_RUN, "start puts the engine in RUN");
    expect_u32(r.m.reg[G_S_CMD / 4u], (1u << 27) | (1u << 7), "S_CMD opens RFR");
    expect_u32(r.m.reg[G_IRQ_EN / 4u], G_IRQ_MASK, "the global engine IRQ is enabled");
    expect_u32(r.m.reg[G_RX_DMA_LEN / 4u], QBT_GENI_RX_SIZE, "the first RX DMA is armed");
    expect_u32(r.m.reg[G_RX_PTR_L / 4u], (uint32_t)r.rx[0].address, "RX buffer 0 is published");
    expect(r.m.last_sync_for_device && !r.m.last_sync_tx, "arming RX hands the buffer to the device");
    expect(!r.m.last_irq_mask, "start unmasks the GIC line");
    expect_int(qbt_geni_start(&r.geni), -EINVAL, "a second start is refused");
}

static void scenario_write(void) {
    struct rig r;
    rig_run(&r);
    const uint8_t h4[4] = { 0x01, 0x03, 0x0c, 0x00 };
    expect(qbt_geni_write(&r.geni, h4, sizeof(h4)) == sizeof(h4), "write accepts one H4 command");
    expect_u32(r.m.reg[G_TX_DMA_LEN / 4u], 4u, "TX DMA length follows the command");
    expect_u32(r.m.reg[G_TX_ATTR / 4u], 1u, "TX attribute is set");
    expect_u32(r.m.reg[G_M_CMD / 4u], 1u << 27, "M_CMD starts the primary sequencer");
    expect(r.m.last_sync_for_device && r.m.last_sync_tx, "TX is published before the doorbell");
    expect(!qbt_geni_drained(&r.geni), "the engine reports a busy TX");
    expect_int((int)qbt_geni_write(&r.geni, h4, sizeof(h4)), 0, "a second command is refused while busy");
    r.m.reg[G_TX_IRQ / 4u] = G_DONE;
    qbt_geni_service(&r.geni);
    expect(!r.geni.tx_busy, "the TX completion retires the command");
    expect_int((int)r.geni.stats.tx_bytes, 4, "the completion counts four bytes");
    expect(!r.m.last_sync_for_device && r.m.last_sync_tx, "TX is taken back from the device");
    expect(qbt_geni_drained(&r.geni), "the engine reports a drained TX");
}

static void scenario_receive(void) {
    struct rig r;
    rig_run(&r);
    const uint8_t event[6] = { 0x04, 0x0e, 0x04, 0x01, 0x03, 0x0c };
    memcpy(r.m.rx[0], event, sizeof(event));
    r.m.reg[G_RX_LEN_IN / 4u] = sizeof(event);
    r.m.reg[G_RX_IRQ / 4u] = G_DONE | G_EOT;
    qbt_geni_service(&r.geni);
    expect_int((int)r.m.receives, 1, "an RX completion reaches the transport once");
    expect_int((int)r.m.received_bytes, (int)sizeof(event), "the event bytes arrive intact");
    expect(memcmp(r.m.received, event, sizeof(event)) == 0, "the event content is unchanged");
    expect_u32(r.m.reg[G_RX_DMA_LEN / 4u], QBT_GENI_RX_SIZE, "the next RX DMA is armed");
    r.m.reg[G_RX_IRQ / 4u] = G_DONE;
    r.m.reg[G_RX_LEN_IN / 4u] = QBT_GENI_RX_SIZE + 1u;
    qbt_geni_service(&r.geni);
    expect_int((int)r.geni.state, QBT_GENI_FAILED, "an over-long RX completion fails the engine");
    expect_int(r.geni.error, -EOVERFLOW, "the over-long completion reports EOVERFLOW");
    expect_u32(r.m.reg[G_IRQ_EN / 4u], 0u, "a failed engine disables its IRQ");
}

static void scenario_fault(void) {
    struct rig r;
    rig_run(&r);
    r.m.reg[G_TX_IRQ / 4u] = G_DMA_ERROR;
    qbt_geni_service(&r.geni);
    expect_int((int)r.geni.state, QBT_GENI_FAILED, "a TX DMA error fails the engine");
    expect_int(r.geni.error, -EIO, "a DMA error reports EIO");
    expect_int((int)r.geni.stats.dma_errors, 1, "the DMA error is counted");
    expect_u32(r.geni.fault_irq[2], G_DMA_ERROR, "the failing TX status is retained");
    expect(r.m.last_irq_mask, "a failed engine masks the GIC line");
    expect_u32(r.m.reg[G_MANUAL_RFR / 4u], G_RFR_OFF, "a failed engine parks RTS");
}

static void scenario_quiesce(void) {
    struct rig r;
    rig_run(&r);
    r.m.now = 1000u;
    expect_int(qbt_geni_quiesce(&r.geni), -EINPROGRESS, "quiesce starts a cancel");
    expect_int((int)r.geni.state, QBT_GENI_CANCEL, "quiesce enters CANCEL");
    expect_u32(r.m.reg[G_S_CTRL / 4u], G_CANCEL, "S_CTRL asks the secondary sequencer to cancel");
    expect_u32(r.m.reg[G_MANUAL_RFR / 4u], G_RFR_OFF, "quiesce parks RTS");
    expect(qbt_geni_deadline(&r.geni) == 1000u + G_STOP_TIMEOUT_NS,
           "the cancel deadline is ten milliseconds out");
    r.m.now = 1000u + G_STOP_TIMEOUT_NS;
    qbt_geni_service(&r.geni);
    expect_int((int)r.geni.state, QBT_GENI_ABORT, "a cancel timeout escalates to ABORT");
    expect_u32(r.m.reg[G_S_CTRL / 4u], G_ABORT, "S_CTRL asks the sequencer to abort");
    r.m.now = 2000u + 2u * G_STOP_TIMEOUT_NS;
    qbt_geni_service(&r.geni);
    expect_int((int)r.geni.state, QBT_GENI_RESET, "a second timeout escalates to RESET");
    expect_u32(r.m.reg[G_RX_RESET / 4u], 1u, "the RX DMA is reset");
    r.m.reg[G_RX_IRQ / 4u] = G_RESET_DONE;
    qbt_geni_service(&r.geni);
    expect_int((int)r.geni.state, QBT_GENI_STOPPED, "the reset completion stops the engine");
    expect_u32(r.m.reg[G_IRQ_EN / 4u], 0u, "a stopped engine disables its IRQ");
}

static void scenario_flow(void) {
    struct rig r;
    rig_run(&r);
    qbt_geni_set_flow(&r.geni, false);
    expect_u32(r.m.reg[G_TX_CFG / 4u], 2u, "stopped flow control sets TX_CFG bit 1");
    expect_u32(r.m.reg[G_MANUAL_RFR / 4u], G_RFR_OFF, "stopped flow control parks RTS");
    qbt_geni_set_flow(&r.geni, true);
    expect_u32(r.m.reg[G_TX_CFG / 4u], 0u, "resumed flow control clears TX_CFG bit 1");
}

int main(int argc, char **argv) {
    const char *scenario = argc > 1 ? argv[1] : "all";
    struct rig probe;
    rig_init(&probe);
    if (rig_prepare(&probe)) abort();
    unsigned simulated = probe.m.touched_count;

    if (!strcmp(scenario, "all") || !strcmp(scenario, "prepare")) scenario_prepare();
    if (!strcmp(scenario, "all") || !strcmp(scenario, "rate")) scenario_rate();
    if (!strcmp(scenario, "all") || !strcmp(scenario, "start")) scenario_start();
    if (!strcmp(scenario, "all") || !strcmp(scenario, "write")) scenario_write();
    if (!strcmp(scenario, "all") || !strcmp(scenario, "receive")) scenario_receive();
    if (!strcmp(scenario, "all") || !strcmp(scenario, "fault")) scenario_fault();
    if (!strcmp(scenario, "all") || !strcmp(scenario, "quiesce")) scenario_quiesce();
    if (!strcmp(scenario, "all") || !strcmp(scenario, "flow")) scenario_flow();

    printf("registers_simulated=%u\n", simulated);
    if (failures) {
        printf("model: %u of %u assertion(s) failed\n", failures, assertions);
        return 1;
    }
    printf("model: OK (%u assertion(s))\n", assertions);
    return 0;
}
