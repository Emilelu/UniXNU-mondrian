/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
#include "K60HandoffBuild.h"

#define BAD_PLAN (-8)

static void le32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24);
}
static void le64(uint8_t *p, uint64_t v)
{
    le32(p, (uint32_t)v); le32(p + 4, (uint32_t)(v >> 32));
}
static int ring_ok(uint32_t bytes) { return bytes >= 256u && bytes <= 65536u && (bytes & 7u) == 0u; }

/* Every field is validated before the first allocation, so a rejected plan
 * never leaves a half-written partition behind. */
static int plan_ok(const K60HandoffPlan *p)
{
    if (!p) return 0;
    if (!p->epoch || !p->smem_base || !p->smem_bytes || p->smem_bytes < 8192u) return 0;
    if (!p->adsp_base || !p->adsp_bytes) return 0;
    if (p->desc_bytes != 32u) return 0;
    if (!ring_ok(p->tx_bytes) || !ring_ok(p->rx_bytes)) return 0;
    if (p->smp2p_bytes < 20u || p->smp2p_bytes > 340u) return 0;
    if (!p->remote_pid || p->remote_pid > 255u) return 0;
    if (p->host_tx_head || p->host_rx_tail) return 0;
    if (p->remote_restart_flag > 1u || p->required == 0u) return 0;
    return 1;
}

int k60_handoff_build(const K60Smem *smem, const K60SmemPartition *part,
                      const K60HandoffPlan *plan, uint8_t out[K60_HANDOFF_BYTES])
{
    const uint16_t items[4] = {plan->desc_item, plan->tx_item, plan->rx_item, plan->smp2p_item};
    uint32_t sizes[4];
    uint32_t offsets[4] = {};
    uint32_t lengths[4] = {};
    unsigned i;
    int rc;

    if (!smem || !part || !out || !plan_ok(plan)) return BAD_PLAN;

    sizes[0] = plan->desc_bytes;
    sizes[1] = plan->tx_bytes;
    sizes[2] = plan->rx_bytes;
    sizes[3] = plan->smp2p_bytes;

    for (i = 0; i < 4; ++i) {
        unsigned j;
        if (items[i] == 0u) return BAD_PLAN;
        for (j = 0; j < i; ++j)
            if (items[i] == items[j]) return BAD_PLAN;
    }

    for (i = 0; i < 4; ++i) {
        rc = k60_smem_alloc(smem, part, items[i], sizes[i], &offsets[i], &lengths[i]);
        if (rc == K60SmemExists) {
            if (k60_smem_find(smem, part, items[i], &offsets[i], &lengths[i]) != K60SmemOk) return rc;
        } else if (rc) {
            return rc;
        }
        if (lengths[i] < sizes[i]) return K60SmemCorrupt;
    }

    le32(out + 0, K60_HANDOFF_MAGIC);
    le32(out + 4, K60_HANDOFF_VERSION);
    le32(out + 8, K60_HANDOFF_BYTES);
    le32(out + 12, plan->required);
    le32(out + 16, plan->epoch);
    le32(out + 20, 0);
    le64(out + 24, plan->smem_base);
    le32(out + 32, plan->smem_bytes);
    le32(out + 36, 0);
    le64(out + 40, plan->adsp_base);
    le32(out + 48, plan->adsp_bytes);
    le32(out + 52, 0);
    le32(out + 56, offsets[0]);
    le32(out + 60, plan->desc_bytes);
    le32(out + 64, offsets[1]);
    le32(out + 68, plan->tx_bytes);
    le32(out + 72, offsets[2]);
    le32(out + 76, plan->rx_bytes);
    le32(out + 80, plan->host_tx_head);
    le32(out + 84, plan->host_rx_tail);
    le32(out + 88, plan->remote_pid);
    le32(out + 92, plan->smp2p_item);
    le32(out + 96, plan->remote_restart_flag);
    le32(out + 100, 0);
    return 0;
}
