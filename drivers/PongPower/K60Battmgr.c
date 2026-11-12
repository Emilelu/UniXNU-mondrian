/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/* Architecture adapted from ShengBattmgr (BSD-2-Clause-Patent). Wire facts
 * from Xiaomi mondrian-s-oss 989b27aa and actual m81.ko property map.
 * Charging control remains entirely firmware-owned. */
#include "K60Battmgr.h"

#define OP_NOTIFY_ENABLE 4u
#define OP_NOTIFY 7u
#define OP_BATTERY 0x30u
#define OP_USB 0x32u
#define OP_WIRELESS 0x34u
#define TYPE_REQUEST 1u
#define TYPE_NOTIFY 2u
#define FLIGHT_NONE 0u
#define FLIGHT_PROPERTY 1u
#define FLIGHT_SUBSCRIBE 2u
#define BIT(f) (1u << (f))

/* Xiaomi has BATT_CONSTANT_CURRENT at12: temperature13/full18/design17/
 * cycles16/model19. The live module's property map agrees. K60 charge_counter
 * reports1413 for31%/4710mAh: its unit is NOT assumed to be uAh. */
static const struct { uint8_t opcode, property; } fields[K60BmFields] = {
    {OP_BATTERY, 0}, {OP_BATTERY, 2}, {OP_BATTERY, 4}, {OP_BATTERY, 7},
    {OP_BATTERY, 9}, {OP_BATTERY, 13}, {OP_USB, 0}, {OP_USB, 1},
    {OP_USB, 7}, {OP_USB, 4}, {OP_USB, 5}, {OP_WIRELESS, 0},
    {OP_BATTERY, 18}, {OP_BATTERY, 17}, {OP_BATTERY, 16},
    {OP_BATTERY, 20}, {OP_BATTERY, 21}, {OP_BATTERY, 19}
};
static uint32_t le32(const uint8_t *p)
{
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}
static void put32(uint8_t *p, uint32_t n)
{
    p[0] = (uint8_t)n; p[1] = (uint8_t)(n >> 8); p[2] = (uint8_t)(n >> 16); p[3] = (uint8_t)(n >> 24);
}
static void zero(void *p, unsigned bytes)
{
    for (unsigned i = 0; i < bytes; ++i) ((uint8_t *)p)[i] = 0;
}
static void begin_cycle(K60Battmgr *b)
{
    b->cursor = 0; b->fresh = b->completed = 0;
    b->cycle_active = 1; b->refresh_due = b->sample_dirty = 0;
}
void k60_battmgr_init(K60Battmgr *b, int sign, unsigned reply_type, unsigned reply_bytes)
{
    zero(b, sizeof(*b));
    b->charging_current_sign = (int8_t)(sign == 1 || sign == -1 ? sign : 0);
    if ((reply_type == TYPE_REQUEST || reply_type == TYPE_NOTIFY) &&
        (reply_bytes == 12 || reply_bytes == 16 || reply_bytes == 24 || reply_bytes == 28)) {
        b->notify_reply_type = (uint8_t)reply_type;
        b->notify_reply_bytes = (uint16_t)reply_bytes;
    }
}
void k60_battmgr_channel_down(K60Battmgr *b)
{
    b->valid = b->fresh = b->completed = b->last_fresh = b->last_completed = 0;
    b->flight = FLIGHT_NONE; b->cycle_active = b->subscribed = b->subscribe_due = 0;
    b->refresh_due = b->poisoned = b->sample_dirty = 0;
}
void k60_battmgr_channel_up(K60Battmgr *b)
{
    k60_battmgr_channel_down(b);
    b->subscribe_due = b->notify_reply_bytes != 0;
    begin_cycle(b);
}
void k60_battmgr_refresh(K60Battmgr *b)
{
    if (b->poisoned) return;
    if (b->cycle_active || b->flight) b->refresh_due = 1;
    else begin_cycle(b);
}
unsigned k60_battmgr_next(const K60Battmgr *b, uint8_t out[K60_BATTMGR_NOTIFY_BYTES])
{
    if (b->flight || b->poisoned) return 0;
    zero(out, K60_BATTMGR_NOTIFY_BYTES);
    put32(out, K60_BATTMGR_OWNER);
    if (b->subscribe_due) {
        /* Actual Xiaomi/actual module request: type2/op4 + four zero words.
         * A guessed percentage threshold is not the board's request. */
        put32(out + 4, TYPE_NOTIFY); put32(out + 8, OP_NOTIFY_ENABLE);
        return K60_BATTMGR_NOTIFY_BYTES;
    }
    if (!b->cycle_active || b->cursor >= K60BmFields) return 0;
    put32(out + 4, TYPE_REQUEST); put32(out + 8, fields[b->cursor].opcode);
    put32(out + 16, fields[b->cursor].property);
    return K60_BATTMGR_REQUEST_BYTES;
}
void k60_battmgr_sent(K60Battmgr *b)
{
    if (b->flight || b->poisoned) return;
    if (b->subscribe_due) { b->subscribe_due = 0; b->flight = FLIGHT_SUBSCRIBE; }
    else if (b->cycle_active && b->cursor < K60BmFields) b->flight = FLIGHT_PROPERTY;
}
unsigned k60_battmgr_property(const K60Battmgr *b)
{
    return b->flight == FLIGHT_SUBSCRIBE || b->cursor >= K60BmFields ? UINT32_MAX : fields[b->cursor].property;
}
unsigned k60_battmgr_opcode(const K60Battmgr *b)
{
    return b->flight == FLIGHT_SUBSCRIBE ? OP_NOTIFY_ENABLE :
           b->cursor < K60BmFields ? fields[b->cursor].opcode : 0;
}
static int value_valid(unsigned f, int32_t v)
{
    switch (f) {
    case K60BmStatus: return v >= 0 && v <= 4;
    case K60BmPresent: case K60BmUsbOnline: case K60BmWirelessOnline: return v == 0 || v == 1;
    case K60BmCapacity: return v >= 0 && v <= 10000;
    case K60BmVoltage: return v >= 2000000 && v <= 5500000;
    case K60BmCurrent: return v >= -20000000 && v <= 20000000;
    case K60BmTemperature: return v >= -4000 && v <= 9000;
    case K60BmUsbVoltage: return v >= 0 && v <= 30000000;
    case K60BmUsbAdapter: return (v >= 0 && v <= 10) || (v >= 0x80 && v <= 0x84);
    case K60BmUsbMaxCurrent: case K60BmUsbInputLimit: return v >= 0 && v <= 15000000;
    case K60BmFull: case K60BmDesign: return v >= 100000 && v <= 20000000;
    case K60BmCycles: return v >= 0 && v <= 100000;
    case K60BmTimeToFull: case K60BmTimeToEmpty:
        return (v >= 0 && v <= 7 * 24 * 3600) || v == -1;
    default: return 0;
    }
}
static int model_valid(K60Battmgr *b, const uint8_t *data)
{
    unsigned n = 0;
    for (; n < K60_BATTMGR_MODEL_BYTES && data[n]; ++n)
        if (data[n] < 32 || data[n] > 126) return 0;
    if (!n || n == K60_BATTMGR_MODEL_BYTES) return 0;
    static const char debug[] = "Debug_Board";
    unsigned same = n == sizeof(debug) - 1;
    for (unsigned i = 0; same && i < n; ++i) same = data[i] == (uint8_t)debug[i];
    if (same) return 0;
    for (unsigned i = 0; i < n; ++i) b->model[i] = (char)data[i];
    b->model[n] = 0;
    return 1;
}
static int finish_field(K60Battmgr *b)
{
    b->flight = FLIGHT_NONE;
    if (++b->cursor < K60BmFields) return K60BmAnswer;
    b->last_fresh = b->fresh; b->last_completed = b->completed;
    b->cycle_active = 0; b->generations++;
    return K60BmCycleDone;
}
int k60_battmgr_receive(K60Battmgr *b, const uint8_t *data, unsigned bytes)
{
    if (!data || bytes < 12 || le32(data) != K60_BATTMGR_OWNER) {b->ignored++; return K60BmIgnored;}
    const uint32_t type = le32(data + 4), opcode = le32(data + 8);
    if (opcode == OP_NOTIFY) {
        if (type != TYPE_NOTIFY || bytes != 16) {b->ignored++; return K60BmIgnored;}
        const uint32_t property_group = le32(data + 12);
        if (property_group != OP_BATTERY && property_group != OP_USB && property_group != OP_WIRELESS &&
            property_group != 0x50 && property_group != 0x80) {b->ignored++; return K60BmIgnored;}
        b->sample_dirty = 1;
        b->notifications++;
        k60_battmgr_refresh(b);
        return K60BmNotified;
    }
    if (b->poisoned) {b->ignored++; return K60BmIgnored;}
    if (opcode == OP_NOTIFY_ENABLE) {
        /* Until parent captures the exact ack there is no subscription request,
         * therefore no ambiguous response is accepted as subscription success. */
        if (b->flight != FLIGHT_SUBSCRIBE || !b->notify_reply_bytes ||
            bytes != b->notify_reply_bytes || type != b->notify_reply_type) {b->ignored++; return K60BmIgnored;}
        for (unsigned at = 12; at < bytes; at += 4)
            if (le32(data + at)) {b->errors++; b->flight = FLIGHT_NONE; return K60BmAnswer;}
        b->subscribed = 1; b->responses++; b->flight = FLIGHT_NONE;
        return K60BmSubscribed;
    }
    if (type != TYPE_REQUEST || b->flight != FLIGHT_PROPERTY || !b->cycle_active || b->cursor >= K60BmFields ||
        bytes < 16 || opcode != fields[b->cursor].opcode || le32(data + 12) != fields[b->cursor].property) {
        b->ignored++; return K60BmIgnored;
    }
    const unsigned f = b->cursor;
    if (f == K60BmModel && bytes == 16 + K60_BATTMGR_MODEL_BYTES) {
        b->responses++; b->completed |= BIT(f);
        if (model_valid(b, data + 16)) {b->valid |= BIT(f); b->fresh |= BIT(f);}
        else {b->valid &= ~BIT(f); b->errors++;}
        return finish_field(b);
    }
    if (bytes != 24) {b->ignored++; return K60BmIgnored;}
    const int32_t value = (int32_t)le32(data + 16);
    const uint32_t result = le32(data + 20);
    b->responses++; b->completed |= BIT(f); b->last_remote_error = result;
    if (!result && f != K60BmModel && value_valid(f, value)) {
        b->value[f] = value; b->valid |= BIT(f); b->fresh |= BIT(f);
    } else {
        b->valid &= ~BIT(f); b->errors++;
    }
    return finish_field(b);
}
void k60_battmgr_timeout(K60Battmgr *b)
{
    if (b->flight == FLIGHT_NONE) return;
    b->timeouts++; b->poisoned = 1;
    b->valid = b->fresh = b->completed = b->last_fresh = 0;
    b->cycle_active = 0;
}

int k60_battmgr_sample(const K60Battmgr *b, K60BatterySample *s)
{
    const uint32_t battery = BIT(K60BmStatus) | BIT(K60BmPresent) | BIT(K60BmCapacity) |
        BIT(K60BmVoltage) | BIT(K60BmCurrent) | BIT(K60BmTemperature) |
        BIT(K60BmFull) | BIT(K60BmDesign) | BIT(K60BmCycles);
    const uint32_t source = BIT(K60BmUsbOnline) | BIT(K60BmUsbVoltage) | BIT(K60BmWirelessOnline);
    const uint32_t required = battery | source;
    if (!s || b->poisoned || b->sample_dirty ||
        (b->last_fresh & (source | BIT(K60BmPresent))) != (source | BIT(K60BmPresent))) return 0;
    if (!b->value[K60BmPresent]) {
        zero(s, sizeof(*s)); s->valid = b->last_fresh;
        s->external = b->value[K60BmUsbOnline] || b->value[K60BmUsbVoltage] >= 4000000 || b->value[K60BmWirelessOnline];
        return 1;
    }
    if (!b->charging_current_sign || (b->last_fresh & required) != required) return 0;
    /* UNKNOWN status is not a fabricated charging/discharging conclusion. */
    if (!b->value[K60BmStatus]) return 0;
    const uint32_t full = (uint32_t)b->value[K60BmFull], design = (uint32_t)b->value[K60BmDesign];
    if ((uint64_t)full * 2 < design || (uint64_t)full > (uint64_t)design * 3 / 2) return 0;
    zero(s, sizeof(*s));
    s->valid = b->last_fresh; s->present = 1;
    const int usb = b->value[K60BmUsbOnline] != 0 || b->value[K60BmUsbVoltage] >= 4000000;
    s->usb_connected = usb;
    s->external = usb || b->value[K60BmWirelessOnline] != 0;
    const int status = b->value[K60BmStatus];
    s->charging = s->external && status == 1; s->full = s->external && status == 4;
    if (status == 1 && !s->external) return 0;
    s->capacity_hundredths = (uint32_t)b->value[K60BmCapacity];
    s->full_mah = full / 1000; s->design_mah = design / 1000;
    /* mAh is the IOPMPowerSource base contract. This is an explicit conversion
     * from measured SOC/full charge, not an unqualified gauge counter unit. */
    s->current_mah = (uint32_t)(((uint64_t)s->capacity_hundredths * full + 5000000) / 10000000);
    if (s->current_mah > s->full_mah) s->current_mah = s->full_mah;
    s->voltage_mv = (uint32_t)b->value[K60BmVoltage] / 1000;
    s->current_ma = b->charging_current_sign * (b->value[K60BmCurrent] / 1000);
    if ((status == 2 && s->current_ma > 0) || (status == 1 && s->current_ma < 0)) return 0;
    s->temperature_hundredths = b->value[K60BmTemperature]; s->cycles = (uint32_t)b->value[K60BmCycles];
    s->time_remaining_min = -1;
    const unsigned tf = s->external ? K60BmTimeToFull : K60BmTimeToEmpty;
    if ((s->valid & BIT(tf)) && b->value[tf] >= 0 && b->value[tf] != 65535)
        s->time_remaining_min = b->value[tf] / 60;
    if (s->full) s->time_remaining_min = 0;
    if (usb) {
        s->adapter_mv = (uint32_t)b->value[K60BmUsbVoltage] / 1000;
        if (s->valid & BIT(K60BmUsbAdapter)) s->adapter_type = (uint32_t)b->value[K60BmUsbAdapter];
        if (s->valid & BIT(K60BmUsbMaxCurrent)) s->adapter_ma = (uint32_t)b->value[K60BmUsbMaxCurrent] / 1000;
        if ((s->valid & BIT(K60BmUsbInputLimit)) && s->adapter_ma > (uint32_t)b->value[K60BmUsbInputLimit] / 1000)
            s->adapter_ma = (uint32_t)b->value[K60BmUsbInputLimit] / 1000;
    }
    if (s->valid & BIT(K60BmModel))
        for (unsigned i = 0; i < K60_BATTMGR_MODEL_BYTES; ++i) s->model[i] = b->model[i];
    return 1;
}
