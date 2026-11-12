/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/* Qualcomm PMIC GLINK codec for the measured K60/Xiaomi battery-charger
 * protocol. Property numbers are checked against the live vendor module;
 * no SM8550 gauge extensions, charger writes, cached/fixed readings. */
#ifndef K60_BATTMGR_H
#define K60_BATTMGR_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
#define K60_BATTMGR_OWNER 32778u
#define K60_BATTMGR_REQUEST_BYTES 24u
#define K60_BATTMGR_NOTIFY_BYTES 28u
#define K60_BATTMGR_MODEL_BYTES 128u

enum K60BatteryField {
    K60BmStatus, K60BmPresent, K60BmCapacity, K60BmVoltage, K60BmCurrent,
    K60BmTemperature, K60BmUsbOnline, K60BmUsbVoltage, K60BmUsbAdapter,
    K60BmUsbMaxCurrent, K60BmUsbInputLimit, K60BmWirelessOnline,
    K60BmFull, K60BmDesign, K60BmCycles, K60BmTimeToFull, K60BmTimeToEmpty,
    K60BmModel, K60BmFields
};
enum K60BatteryResponse {
    K60BmIgnored = 0, K60BmAnswer = 1, K60BmCycleDone = 2,
    K60BmNotified = 3, K60BmSubscribed = 4
};

typedef struct {
    int32_t value[K60BmFields];
    uint32_t valid, fresh, completed, last_fresh, last_completed;
    uint32_t generations, responses, notifications, errors, timeouts, ignored;
    uint32_t last_remote_error;
    uint16_t notify_reply_bytes;
    uint8_t notify_reply_type;
    int8_t charging_current_sign;
    uint8_t cursor, flight, cycle_active, subscribe_due, subscribed, refresh_due;
    uint8_t poisoned, sample_dirty;
    char model[K60_BATTMGR_MODEL_BYTES];
} K60Battmgr;

typedef struct {
    uint32_t valid;
    int present, external, charging, full, usb_connected;
    uint32_t capacity_hundredths, current_mah, full_mah, design_mah, cycles;
    uint32_t voltage_mv, adapter_mv, adapter_ma, adapter_type;
    int32_t current_ma, temperature_hundredths;
    int time_remaining_min;
    char model[K60_BATTMGR_MODEL_BYTES];
} K60BatterySample;

/* sign: +1 wire charging-positive, -1 discharge-positive, 0 unqualified.
 * reply type/length must be measured, not inferred from Linux's loose ACK.
 * A zero reply length disables subscription; real polling remains available. */
void k60_battmgr_init(K60Battmgr *, int sign, unsigned reply_type, unsigned reply_bytes);
void k60_battmgr_channel_up(K60Battmgr *);
void k60_battmgr_channel_down(K60Battmgr *);
void k60_battmgr_refresh(K60Battmgr *);
/* Returns one request without marking it sent. Caller retries FIFO backpressure
 * and calls sent only after the actual GLINK FIFO write succeeds. */
unsigned k60_battmgr_next(const K60Battmgr *, uint8_t out[K60_BATTMGR_NOTIFY_BYTES]);
void k60_battmgr_sent(K60Battmgr *);
int k60_battmgr_receive(K60Battmgr *, const uint8_t *, unsigned);
/* No transaction ID exists on this protocol. An unanswered sent request poisons
 * its channel epoch. Owner must CLOSE/ACK/OPEN before making another request,
 * so a late reply can never satisfy the same property in a subsequent cycle. */
void k60_battmgr_timeout(K60Battmgr *);
int k60_battmgr_sample(const K60Battmgr *, K60BatterySample *);
unsigned k60_battmgr_property(const K60Battmgr *);
unsigned k60_battmgr_opcode(const K60Battmgr *);
#ifdef __cplusplus
}
#endif
#endif
