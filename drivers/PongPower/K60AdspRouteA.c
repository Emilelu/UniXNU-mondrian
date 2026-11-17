/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/* Route A acquisition for the K60 ADSP.
 *
 * Reference shape (E:/hackios/UniXNU-zizhan/drivers/PongPower/PongAdsp.cpp:503-521
 * and PongRpmh.cpp:27-48): QMP load_state on, find lcx.lvl/lmx.lvl in the
 * command database, then write one RPMh command per rail into TCS4
 * (0xd00 + 4 * 0x2a0). K60 is the same SM8475 and has the same tcs-config
 * pairs as Zizhan, so the working reference's TCS4 choice is used rather than
 * deriving a slot from the contradictory mainline decode.
 *
 * This file contains no PAS call and no SMC. It writes only the two rail
 * votes and the QMP message AOP expects; every read and write goes through a
 * mapped window supplied by the caller.
 */
#include "K60AdspRouteA.h"
#include "K60PmicRail.h"

#ifdef KERNEL
#include <sys/systm.h>
#else
#include <stdio.h>
#endif

#define QMP_DESC_MAGIC          0x0u
#define QMP_DESC_VERSION        0x4u
#define QMP_DESC_UCORE_LINK     0x0cu
#define QMP_DESC_UCORE_LINK_ACK 0x10u
#define QMP_DESC_UCORE_CH       0x14u
#define QMP_DESC_UCORE_CH_ACK   0x18u
#define QMP_DESC_MCORE_LINK     0x24u
#define QMP_DESC_MCORE_LINK_ACK 0x28u
#define QMP_DESC_MCORE_CH       0x2cu
#define QMP_DESC_MCORE_CH_ACK   0x30u
#define QMP_DESC_MBOX_SIZE      0x34u
#define QMP_DESC_MBOX_OFFSET    0x38u
#define QMP_MAGIC               0x4d41494cu /* "MAIL" */
#define QMP_VERSION             1u
#define QMP_STATE_UP            0xffffu
#define QMP_MSG_BYTES           100u
#define QMP_WORDS               (QMP_MSG_BYTES / 4u)

#define RSC_DRV_CONTROL         0x00u
#define RSC_DRV_IRQ_STATUS      0x04u
#define RSC_DRV_IRQ_CLEAR       0x08u
#define RSC_DRV_CAPS            0x0cu
#define RSC_TCS_BASE            0xd00u
#define RSC_TCS_STRIDE           672u
#define RSC_TCS4                (RSC_TCS_BASE + 4u * RSC_TCS_STRIDE)
#define RSC_TCS3                (RSC_TCS_BASE + 3u * RSC_TCS_STRIDE)
#define RSC_MSGID                0x10108u
#define RSC_IRQ_DONE             (1u << 4)
#define RSC_CMD_DONE             0x10100u
#define RSC_DRV_CONTROL_TCS     (1u << 4)

typedef struct {
    const K60RouteAIo *io;
    volatile uint8_t *aoss;
    volatile uint8_t *ipcc;
    volatile uint8_t *db;
    volatile uint8_t *rsc;
    uint32_t box;
    uint32_t box_bytes;
} Route;

static uint32_t rd32(const volatile uint8_t *base, size_t at)
{
    return *(volatile uint32_t *)(base + at);
}

static void wr32(volatile uint8_t *base, size_t at, uint32_t value)
{
    *(volatile uint32_t *)(base + at) = value;
}

static void fence(void)
{
#if defined(__aarch64__)
    __asm__ volatile("dsb sy" ::: "memory");
#else
    __asm__ volatile("" ::: "memory");
#endif
}

static void spin(void)
{
#if defined(__aarch64__)
    __asm__ volatile("yield" ::: "memory");
#else
    __asm__ volatile("" ::: "memory");
#endif
}

static void log_line(const char *text)
{
    printf("K60ROUTEA: %s%c", text, 10);
}

static int wait_word(const volatile uint8_t *base, size_t at, uint32_t mask,
    uint32_t value, unsigned tries)
{
    for (unsigned i = 0; i < tries; ++i) {
        if ((rd32(base, at) & mask) == value) return 0;
        spin();
    }
    return -1;
}

/* The QMP descriptor lives in the first 0x400 bytes of AOSS. Its message box
 * is a word offset plus a byte length; both are read back and bounds-checked
 * before any word is written. */
static int qmp_open(Route *r)
{
    volatile uint8_t *d = r->aoss;
    const uint32_t box = rd32(d, QMP_DESC_MBOX_OFFSET);
    const uint32_t bytes = rd32(d, QMP_DESC_MBOX_SIZE);

    if (rd32(d, QMP_DESC_MAGIC) != QMP_MAGIC || rd32(d, QMP_DESC_VERSION) != QMP_VERSION)
        return -1;
    if ((box & 3u) || box < 0x3cu || bytes > K60_ROUTE_A_AOSS_BYTES ||
        box > bytes || bytes - box < QMP_MSG_BYTES + 4u)
        return -1;
    r->box = box;
    r->box_bytes = bytes;

    if (rd32(d, QMP_DESC_MCORE_LINK) == QMP_STATE_UP &&
        rd32(d, QMP_DESC_MCORE_LINK_ACK) == QMP_STATE_UP &&
        rd32(d, QMP_DESC_MCORE_CH) == QMP_STATE_UP &&
        rd32(d, QMP_DESC_UCORE_CH) == QMP_STATE_UP &&
        rd32(d, QMP_DESC_MCORE_CH_ACK) == QMP_STATE_UP)
        return 0;

    for (unsigned phase = 0; phase < 4; ++phase) {
        /* Link request, then wait for the AOP's link acknowledgement. */
        if (rd32(d, QMP_DESC_MCORE_LINK) != QMP_STATE_UP) {
            wr32(d, QMP_DESC_UCORE_LINK_ACK, rd32(d, QMP_DESC_UCORE_LINK));
            wr32(d, QMP_DESC_MCORE_LINK, QMP_STATE_UP);
            fence();
            r->io->kick(r->io->context, r->ipcc);
            if (wait_word(d, QMP_DESC_MCORE_LINK_ACK, 0xffffu, QMP_STATE_UP, 100000))
                continue;
        }
        /* Channel request, then the AOP channel acknowledgement. */
        wr32(d, QMP_DESC_MCORE_CH, QMP_STATE_UP);
        fence();
        r->io->kick(r->io->context, r->ipcc);
        if (wait_word(d, QMP_DESC_UCORE_CH, 0xffffu, QMP_STATE_UP, 100000))
            continue;
        wr32(d, QMP_DESC_UCORE_CH_ACK, QMP_STATE_UP);
        fence();
        r->io->kick(r->io->context, r->ipcc);
        if (wait_word(d, QMP_DESC_MCORE_CH_ACK, 0xffffu, QMP_STATE_UP, 100000))
            continue;
        return 0;
    }
    return -1;
}

static int qmp_send_load_state(Route *r)
{
    volatile uint8_t *box = r->aoss + r->box;
    static const char msg[] = "{class: image, res: load_state, name: adsp, val: on}";
    uint32_t words[QMP_WORDS] = { 0 };
    const size_t n = sizeof(msg) - 1u;

    if (n + 1u > QMP_MSG_BYTES) return -1;
    /* The AOSS message RAM is device memory and takes 32-bit accesses only;
     * assemble the text in registers and publish it as whole words. */
    for (size_t i = 0; i < n; ++i)
        words[i / 4u] |= (uint32_t)(uint8_t)msg[i] << (8u * (i % 4u));
    if (wait_word(r->aoss, r->box, 0xffffffffu, 0, 100000)) return -1;
    for (unsigned i = 0; i < QMP_WORDS; ++i)
        wr32(box, 4u + i * 4u, words[i]);
    fence();
    wr32(box, 0, QMP_MSG_BYTES);
    fence();
    r->io->kick(r->io->context, r->ipcc);
    /* qmp_send waits for the AOP to clear the length word, not for a register
     * acknowledgement. Short timeout; a stuck box is a failed acquisition. */
    return wait_word(r->aoss, r->box, 0xffffffffu, 0, 200000);
}

static int find_rail(Route *r, const char *name, K60RpmhResource *res,
    uint32_t *index)
{
    if (k60_cmd_db_find((const uint8_t *)(const void *)r->db, K60_CMD_DB_BYTES,
        name, res) != K60RpmhOk)
        return -1;
    /* Zizhan asks qcom_rpmh_level_index(..., 0xffffffff) for the highest
     * corner. K60's helper is strict (P-191): 0xffffffff is NoLevel, so use
     * the table's last index directly rather than inheriting that mismatch. */
    if (res->level_count == 0)
        return -1;
    *index = res->level_count - 1u;
    return 0;
}

/* Check that the selected command slot is not already owned by another
 * command in this TCS. The reference performs the same conflict check against
 * TCS3 before using TCS4. */
static int tcs_conflict(const Route *r, const K60RscLayout *l, uint32_t tcs,
    uint32_t command_capacity, uint32_t address)
{
    const uint32_t enable = rd32(r->rsc, tcs + l->cmd_enable);
    for (uint32_t i = 0; i < command_capacity && i < 16u; ++i) {
        if ((enable & (1u << i)) &&
            rd32(r->rsc, tcs + (size_t)i * l->cmd_stride + l->cmd_addr) == address)
            return -1;
    }
    return 0;
}

/* One RPMh active-only command into TCS4. This is the exact write sequence
 * used by PongRpmh.cpp:27-48: clear the old command, publish msgid/address/data,
 * set control bits 16 and 24, and wait for the command and TCS status. */
static int vote_tcs4(Route *r, const K60RscLayout *l, uint32_t address,
    uint32_t value, uint32_t command_capacity)
{
    const size_t base = RSC_TCS4;
    const size_t drv_control = RSC_DRV_CONTROL;
    uint32_t progressed = 0;

    if (rd32(r->rsc, RSC_TCS3 + l->status) == 0 &&
        tcs_conflict(r, l, RSC_TCS3, command_capacity, address))
        return -1;
    wr32(r->rsc, drv_control, rd32(r->rsc, drv_control) & ~RSC_DRV_CONTROL_TCS);
    uint32_t control = rd32(r->rsc, base + l->control) & ~(1u << 24);
    wr32(r->rsc, base + l->control, control);
    if (wait_word(r->rsc, base + l->control, 0xffffffffu, control, 1000))
        return -1;
    control &= ~(1u << 16);
    wr32(r->rsc, base + l->control, control);
    if (wait_word(r->rsc, base + l->control, 0xffffffffu, control, 1000))
        return -1;
    wr32(r->rsc, base + l->cmd_enable, 0);
    wr32(r->rsc, RSC_DRV_IRQ_CLEAR, RSC_IRQ_DONE);
    (void)wait_word(r->rsc, RSC_DRV_IRQ_STATUS, RSC_IRQ_DONE, 0, 1000);
    wr32(r->rsc, base + l->cmd_msgid, RSC_MSGID);
    wr32(r->rsc, base + l->cmd_addr, address);
    wr32(r->rsc, base + l->cmd_data, value);
    wr32(r->rsc, base + l->wait_for_cmpl, 1);
    fence();
    wr32(r->rsc, base + l->cmd_enable, 1);
    wr32(r->rsc, base + l->control, 1u << 16);
    if (wait_word(r->rsc, base + l->control, 0xffffffffu, 1u << 16, 1000))
        return -1;
    fence();
    wr32(r->rsc, base + l->control, (1u << 16) | (1u << 24));

    for (unsigned i = 0; i < 200000u; ++i) {
        if (r->io->tick) r->io->tick(r->io->context);
        const uint32_t status = rd32(r->rsc, base + l->cmd_data + 4u);
        const uint32_t idle = rd32(r->rsc, base + l->status);
        if ((status & RSC_CMD_DONE) == RSC_CMD_DONE && idle &&
            (progressed || (rd32(r->rsc, RSC_DRV_IRQ_STATUS) & RSC_IRQ_DONE)))
            break;
        if ((status & RSC_CMD_DONE) != RSC_CMD_DONE || !idle) progressed = 1;
        spin();
        if (i == 200000u - 1u) return -1;
    }
    wr32(r->rsc, base + l->cmd_enable, 0);
    wr32(r->rsc, RSC_DRV_IRQ_CLEAR, RSC_IRQ_DONE);
    wr32(r->rsc, base + l->control,
        rd32(r->rsc, base + l->control) & ~(1u << 24));
    fence();
    return 0;
}

static void release_maps(Route *r)
{
    if (r->aoss) { r->io->unmap(r->io->context, r->aoss, K60_ROUTE_A_AOSS_BYTES); r->aoss = 0; }
    if (r->ipcc) { r->io->unmap(r->io->context, r->ipcc, K60_ROUTE_A_IPCC_BYTES); r->ipcc = 0; }
    if (r->db) { r->io->unmap(r->io->context, r->db, K60_CMD_DB_BYTES); r->db = 0; }
    if (r->rsc) { r->io->unmap(r->io->context, r->rsc, K60_RSC_BYTES); r->rsc = 0; }
}

int k60_adsp_route_a_acquire(const K60RouteAIo *io, K60RouteAResult *out)
{
    Route r = { 0 };
    K60RpmhResource lcx = { 0 }, lmx = { 0 };
    uint32_t lcx_index = 0, lmx_index = 0;
    uint32_t drv, caps, version;

    if (!io || !out || io->version != K60_ROUTE_A_VERSION ||
        io->bytes != sizeof *io || !io->map || !io->unmap || !io->kick)
        return -1;
    for (unsigned i = 0; i < sizeof *out; ++i) ((uint8_t *)out)[i] = 0;
    r.io = io;

    if (io->map(io->context, K60_ROUTE_A_AOSS_PHYS, K60_ROUTE_A_AOSS_BYTES,
        K60_ROUTE_A_MAP_FLAGS, &r.aoss) || !r.aoss) {
        log_line("AOSS map failed");
        goto fail;
    }
    log_line("AOSS mapped");
    if (io->map(io->context, K60_ROUTE_A_IPCC_PHYS, K60_ROUTE_A_IPCC_BYTES,
        K60_ROUTE_A_MAP_FLAGS, &r.ipcc) || !r.ipcc) {
        log_line("IPCC map failed");
        goto fail;
    }
    log_line("IPCC mapped");
    if (qmp_open(&r)) {
        log_line("QMP open failed");
        goto fail;
    }
    out->qmp_open = 1;
    log_line("QMP open ok");
    if (qmp_send_load_state(&r)) {
        log_line("QMP load_state send failed");
        goto fail;
    }
    log_line("QMP load_state ok");

    if (io->map(io->context, K60_CMD_DB_PHYS, K60_CMD_DB_BYTES,
        K60_ROUTE_A_MAP_FLAGS, &r.db) || !r.db) {
        log_line("cmd-db map failed");
        goto fail;
    }
    if (io->map(io->context, K60_RSC_DRV2_PHYS, K60_RSC_BYTES,
        K60_ROUTE_A_MAP_FLAGS, &r.rsc) || !r.rsc) {
        log_line("RSC map failed");
        goto fail;
    }
    log_line("RSC mapped");
    drv = rd32(r.rsc, 0);
    caps = rd32(r.rsc, RSC_DRV_CAPS);
    version = (drv >> 16) & 0xffu;
    /* The proven K60/Zizhan TCS4 vote requires a v2 APSS RSC with at least
     * eight TCS slots and one command slot. v3 and smaller tables would make
     * TCS4 unavailable; never write a slot the firmware did not advertise. */
    if (version != 2u) {
        log_line("RSC version unsupported");
        goto fail;
    }
    {
        K60RscLayout l = k60_rsc_layout(drv);
        if (((caps >> 12) & 0x3fu) < 8u || ((caps >> 27) & 0x1fu) < 1u) {
            log_line("RSC caps incomplete");
            goto fail;
        }
        if (rd32(r.rsc, RSC_TCS4 + l.status) == 0) {
            log_line("TCS4 unavailable");
            goto fail;
        }
        if (find_rail(&r, "lcx.lvl", &lcx, &lcx_index) ||
            find_rail(&r, "lmx.lvl", &lmx, &lmx_index)) {
            log_line("lcx/lmx not found in cmd-db");
            goto fail;
        }
        out->lcx_address = lcx.address; out->lmx_address = lmx.address;
        out->lcx_index = lcx_index; out->lmx_index = lmx_index;
        out->lcx_levels = lcx.level_count; out->lmx_levels = lmx.level_count;
        printf("K60ROUTEA lcx addr=0x%x levels=%u index=%u%c", lcx.address,
            lcx.level_count, lcx_index, 10);
        printf("K60ROUTEA lmx addr=0x%x levels=%u index=%u%c", lmx.address,
            lmx.level_count, lmx_index, 10);
        const uint32_t command_capacity = (caps >> 27) & 0x1fu;
        log_line("voting TCS4");
        if (vote_tcs4(&r, &l, lcx.address, lcx_index, command_capacity) ||
            vote_tcs4(&r, &l, lmx.address, lmx_index, command_capacity)) {
            log_line("TCS4 vote failed");
            goto fail;
        }
    }
    log_line("QMP load_state on and TCS4 lcx/lmx votes complete");
    release_maps(&r);
    return 0;

fail:
    release_maps(&r);
    return -1;
}