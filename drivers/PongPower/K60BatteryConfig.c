/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
#include "K60BatteryConfig.h"

static uint32_t le32(const uint8_t *p)
{
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}
static uint64_t le64(const uint8_t *p) { return le32(p) | (uint64_t)le32(p + 4) << 32; }
static int fits(uint64_t at, uint64_t bytes, uint64_t size) { return at <= size && bytes <= size - at; }
static int physical_range(uint64_t base, uint64_t bytes)
{
    return bytes && base && base <= UINT64_MAX - bytes;
}
int k60_battery_range_overlaps(uint64_t a, uint64_t n, uint64_t b, uint64_t m)
{
    if (!n || !m) return 0;
    if (a > UINT64_MAX - n || b > UINT64_MAX - m) return 1;
    return a < b + m && b < a + n;
}

int k60_battery_config_parse(const uint8_t *p, size_t bytes, K60BatteryConfig *out)
{
    if (!p || !out || bytes != K60_BATTERY_CONFIG_BYTES || le32(p) != K60_BATTERY_CONFIG_MAGIC ||
        le32(p + 4) != K60_BATTERY_CONFIG_VERSION || le32(p + 8) != bytes || le32(p + 12))
        return K60ConfigBadEncoding;
    K60BatteryConfig c = {0};
    c.smem_base = le64(p + 16); c.smem_bytes = le64(p + 24);
    c.ipcc_base = le64(p + 32); c.mutex_base = le64(p + 40);
    c.adsp_base = le64(p + 48); c.adsp_bytes = le64(p + 56);
    c.remote_pid = le32(p + 64); c.ipcc_client = le32(p + 68); c.ipcc_signal = le32(p + 72);
    c.desc_item = le32(p + 76); c.tx_item = le32(p + 80); c.rx_item = le32(p + 84);
    c.smp2p_item = le32(p + 88); c.protocol = le32(p + 92);
    c.charging_current_sign = (int32_t)le32(p + 96);
    if (le32(p + 100) || le32(p + 104) || le32(p + 108)) return K60ConfigBadEncoding;
    if (!physical_range(c.smem_base, c.smem_bytes) || (c.smem_base & 4095) ||
        c.smem_bytes < 8192 || c.smem_bytes > 16 * 1024 * 1024 || (c.smem_bytes & 4095) ||
        !physical_range(c.adsp_base, c.adsp_bytes) || (c.adsp_base & 4095) || (c.adsp_bytes & 4095) ||
        c.adsp_bytes > 128 * 1024 * 1024 || !physical_range(c.ipcc_base, 4096) || (c.ipcc_base & 4095) ||
        !physical_range(c.mutex_base, 4) || (c.mutex_base & 3) ||
        k60_battery_range_overlaps(c.smem_base, c.smem_bytes, c.adsp_base, c.adsp_bytes))
        return K60ConfigBadResource;
    /* These are the Qualcomm native ADSP edge IDs, not Xiaomi gauge offsets.
     * Reject a board record for another edge/SoC instead of partially matching. */
    if (c.remote_pid != 2 || c.ipcc_client != 3 || c.ipcc_signal != 0 ||
        c.desc_item != 478 || c.tx_item != 479 || c.rx_item != 480 || c.smp2p_item != 443 ||
        c.protocol != K60_BATTERY_PROTOCOL_XIAOMI_MONDRIAN ||
        (c.charging_current_sign != 0 && c.charging_current_sign != 1 && c.charging_current_sign != -1))
        return K60ConfigBadProtocol;
    *out = c;
    return K60ConfigOk;
}

int k60_adsp_handoff_parse(const uint8_t *p, size_t bytes, const K60BatteryConfig *c, K60AdspGlinkHandoff *out)
{
    if (!p || !c || !out || bytes != K60_ADSP_HANDOFF_BYTES || le32(p) != K60_ADSP_HANDOFF_MAGIC ||
        le32(p + 4) != K60_ADSP_HANDOFF_VERSION || le32(p + 8) != bytes || le32(p + 100))
        return K60ConfigBadEncoding;
    K60AdspGlinkHandoff h = {0};
    h.flags = le32(p + 12); h.epoch = le64(p + 16);
    h.smem_base = le64(p + 24); h.smem_bytes = le64(p + 32);
    h.adsp_base = le64(p + 40); h.adsp_bytes = le64(p + 48);
    h.desc_offset = le32(p + 56); h.desc_bytes = le32(p + 60);
    h.tx_offset = le32(p + 64); h.tx_bytes = le32(p + 68);
    h.rx_offset = le32(p + 72); h.rx_bytes = le32(p + 76);
    h.host_tx_head = le32(p + 80); h.host_rx_tail = le32(p + 84);
    h.remote_restart_flag = le32(p + 96);
    if (h.flags != K60AdspHandoffRequired || !h.epoch) return K60ConfigNoOwnership;
    if (h.smem_base != c->smem_base || h.smem_bytes != c->smem_bytes ||
        h.adsp_base != c->adsp_base || h.adsp_bytes != c->adsp_bytes ||
        le32(p + 88) != c->remote_pid || le32(p + 92) != c->smp2p_item)
        return K60ConfigBadResource;
    /* The lease must start a fresh APSS session. Continuing Android's channel
     * IDs/intents or guessing what an old FIFO contained is not a takeover. */
    if (h.host_tx_head || h.host_rx_tail || h.remote_restart_flag > 1) return K60ConfigWrongEpoch;
    const uint64_t usable = c->smem_bytes - 4096;
    if (h.desc_bytes != 32 || (h.desc_offset & 7) || !fits(h.desc_offset, h.desc_bytes, usable) ||
        h.tx_bytes < 256 || h.tx_bytes > 65536 || (h.tx_bytes & 7) || (h.tx_offset & 7) ||
        h.rx_bytes < 256 || h.rx_bytes > 65536 || (h.rx_bytes & 7) || (h.rx_offset & 7) ||
        !fits(h.tx_offset, h.tx_bytes, usable) || !fits(h.rx_offset, h.rx_bytes, usable) ||
        k60_battery_range_overlaps(h.desc_offset, h.desc_bytes, h.tx_offset, h.tx_bytes) ||
        k60_battery_range_overlaps(h.desc_offset, h.desc_bytes, h.rx_offset, h.rx_bytes) ||
        k60_battery_range_overlaps(h.tx_offset, h.tx_bytes, h.rx_offset, h.rx_bytes))
        return K60ConfigBadResource;
    *out = h;
    return K60ConfigOk;
}
