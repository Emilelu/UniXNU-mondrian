/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/* Port of UniXNU-sheng package/ShengChargeAuth.h (BSD-2-Clause-Patent).
 * Xiaomi's PMIC GLINK authentication protocol, as used by sm8550-mainline
 * 87ac0f2347eb and xiaomi-mipps-auth 9176efbdf276. The firmware owns PD/PPS
 * contracts, charge pumps, current limits and thermal regulation. */
#ifndef K60_CHARGE_AUTH_H
#define K60_CHARGE_AUTH_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

#define K60_CHARGE_REQUEST_BYTES 52u
enum {
    K60ChargeIdle, K60ChargeGaugeCheck, K60ChargeGaugeChallenge, K60ChargeGaugeDigest,
    K60ChargeGaugeMark, K60ChargeAdapterCheck, K60ChargeHostRole, K60ChargeVdmWrite,
    K60ChargeVdmState, K60ChargeVdmDigest, K60ChargeAdapterId, K60ChargeVerified,
    K60ChargeReverse, K60ChargeCompensation, K60ChargePdMark, K60ChargeDiagnostics,
    K60ChargeDone, K60ChargeFailed
};
enum {
    K60ChargeAdapterSvid, K60ChargePdo2, K60ChargeAdapterIdValue, K60ChargeApdoMax,
    K60ChargePowerMax, K60ChargeFastMode, K60ChargeQuickType, K60ChargePpsPtf,
    K60ChargePump1Ok, K60ChargePump2Ok, K60ChargePump1Current, K60ChargePump2Current,
    K60ChargePumpVoltage, K60ChargePumpBatteryVoltage, K60ChargeGaugeFast,
    K60ChargeVdmVersion, K60ChargeVdmVoltage, K60ChargeVdmTemperature,
    K60ChargeDiagnosticCount
};
typedef struct {
    void (*random)(void *, uint32_t);
    void (*hmac)(const uint8_t *, uint32_t, const uint8_t *, uint32_t, uint8_t[32]);
} K60ChargeCrypto;
typedef struct {
    K60ChargeCrypto crypto;
    uint32_t state, pending, opcode, property, pending_bytes;
    uint64_t due_ms, deadline_ms;
    uint32_t generation, reads, writes, errors, timeouts, ignored, retries;
    uint32_t gauge_verified, adapter_verified, diagnostic_valid;
    int32_t diagnostic[K60ChargeDiagnosticCount];
    int32_t result, last_result, host_ready;
    uint8_t online, enabled, gauges, slave, tries, seed_index, vdm_command,
        diagnostic_cursor, diagnostic_due, cancelled;
    uint8_t challenge[32], expected[32];
} K60ChargeAuth;

void k60_charge_auth_init(K60ChargeAuth *, const K60ChargeCrypto *);
/* K60 is a single-cell pack. A dual-gauge board opts in to the slave check. */
void k60_charge_auth_set_gauges(K60ChargeAuth *, unsigned count);
/* Retire an attachment. An outstanding exchange keeps its queue slot until its
 * reply or timeout, so the reply cannot advance a replacement attachment. */
void k60_charge_auth_reconnect(K60ChargeAuth *, uint64_t now_ms);
/* Called after a battery refresh. Authentication runs once per PD attachment. */
void k60_charge_auth_observe(K60ChargeAuth *, int online, int usb_type, uint64_t now_ms);
/* All requests share the battery manager's serialized GLINK queue. */
uint32_t k60_charge_auth_next(K60ChargeAuth *, uint64_t now_ms,
    uint8_t out[K60_CHARGE_REQUEST_BYTES]);
int k60_charge_auth_receive(K60ChargeAuth *, const uint8_t *, uint32_t, uint64_t now_ms);
void k60_charge_auth_timeout(K60ChargeAuth *, uint64_t now_ms);
uint32_t k60_charge_auth_wait_ms(const K60ChargeAuth *, uint64_t now_ms);

#ifdef __cplusplus
}
#endif
#endif
