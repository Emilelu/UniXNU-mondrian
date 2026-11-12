/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
#ifndef K60_BATTERY_CONFIG_H
#define K60_BATTERY_CONFIG_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

#define K60_BATTERY_CONFIG_MAGIC 0x4342364bu /* K6BC, little endian */
#define K60_BATTERY_CONFIG_VERSION 1u
#define K60_BATTERY_CONFIG_BYTES 112u
#define K60_ADSP_HANDOFF_MAGIC 0x4842364bu   /* K6BH, little endian */
#define K60_ADSP_HANDOFF_VERSION 1u
#define K60_ADSP_HANDOFF_BYTES 104u
#define K60_ADSP_HANDOFF_PROPERTY "k60-adsp-glink-handoff"
#define K60_BATTERY_PROTOCOL_XIAOMI_MONDRIAN 1u

/* A real platform/loader PAS1 owner, not a boot argument, supplies this lease.
 * It must initialize the APSS FIFOs while ADSP is stopped, authenticate PAS1,
 * retain its power/XO/interconnect requirements and relinquish GLINK completely.
 * Neither the battery driver nor this parser authenticates or resets a DSP. */
/* K6BH record offsets (all little endian, no native struct padding):
 * 0 magic,4 version,8 bytes,12 flags;16 epoch(u64);
 * 24 SMEM base(u64),32 SMEM bytes(u64),40 ADSP base(u64),48 ADSP bytes(u64);
 * 56/60 descriptor offset/bytes,64/68 TX offset/bytes,72/76 RX offset/bytes;
 * 80 APSS TX head(0),84 APSS RX tail(0),88 remote PID(2),92 SMP2P item(443),
 * 96 captured remote restart flag,100 reserved(0). Only the genuine platform
 * PAS1 owner may emit this lease; a config builder must never synthesize it. */
enum {
    K60AdspAuthenticated = 1u << 0,
    K60AdspResourcesHeld = 1u << 1,
    K60AdspGlinkExclusive = 1u << 2,
    K60AdspFreshHostFifos = 1u << 3,
    K60AdspHandoffRequired = 15u
};

typedef struct {
    uint64_t smem_base, smem_bytes, ipcc_base, mutex_base;
    uint64_t adsp_base, adsp_bytes;
    uint32_t remote_pid, ipcc_client, ipcc_signal;
    uint32_t desc_item, tx_item, rx_item, smp2p_item;
    uint32_t protocol;
    int32_t charging_current_sign; /* 0 until actual charging/discharging wire pair qualifies +/-1 */
} K60BatteryConfig;

typedef struct {
    uint32_t flags;
    uint64_t epoch;
    uint64_t smem_base, smem_bytes, adsp_base, adsp_bytes;
    uint32_t desc_offset, desc_bytes, tx_offset, tx_bytes, rx_offset, rx_bytes;
    uint32_t host_tx_head, host_rx_tail, remote_restart_flag;
} K60AdspGlinkHandoff;

enum {
    K60ConfigOk = 0,
    K60ConfigBadEncoding = -1,
    K60ConfigBadResource = -2,
    K60ConfigBadProtocol = -3,
    K60ConfigNoOwnership = -4,
    K60ConfigWrongEpoch = -5
};

/* Versioned byte records have no compiler-layout/padding dependency. Config is
 * generated only from the captured live FDT and checked vendor module. Handoff
 * is separately supplied by the authenticated platform owner through /chosen. */
int k60_battery_config_parse(const uint8_t *, size_t, K60BatteryConfig *);
int k60_adsp_handoff_parse(const uint8_t *, size_t, const K60BatteryConfig *, K60AdspGlinkHandoff *);
int k60_battery_range_overlaps(uint64_t, uint64_t, uint64_t, uint64_t);

extern const uint8_t K60BatteryBoardConfig[K60_BATTERY_CONFIG_BYTES];
extern const size_t K60BatteryBoardConfigBytes;

#ifdef __cplusplus
}
#endif
#endif
