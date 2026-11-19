/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
#include "K60ThermalMap.h"

typedef struct {
    const char *name;
    unsigned cpu;
    unsigned gpu;
} ZoneRow;

static const ZoneRow kZones[K60ThermalZoneCount] = {
    { "cpu-0", 1, 0 },
    { "cpu-1", 1, 0 },
    { "cpuss", 1, 0 },
    { "gpuss", 0, 1 },
    { "ddr", 0, 0 },
    { "aoss", 0, 0 },
    { "pm8350", 0, 0 },
    { "pm8350c", 0, 0 },
    { "pm8450", 0, 0 },
};

static const char *const kLevelNames[K60ThermalLevelCount] = {
    "none", "warm", "junction", "emergency", "reset", "shutdown",
};

const char *k60_thermal_zone_name(int zone)
{
    if (zone < 0 || zone >= K60ThermalZoneCount) {
        return "invalid";
    }
    return kZones[zone].name;
}

const char *k60_thermal_level_name(enum k60_thermal_level level)
{
    if ((int)level < 0 || (int)level >= K60ThermalLevelCount) {
        return "invalid";
    }
    return kLevelNames[level];
}

enum k60_thermal_level k60_thermal_level_at(int32_t millideg)
{
    if (millideg >= K60_THERMAL_TRIP_SHUTDOWN) {
        return K60ThermalLevelShutdown;
    }
    if (millideg >= K60_THERMAL_TRIP_RESET) {
        return K60ThermalLevelReset;
    }
    if (millideg >= K60_THERMAL_TRIP_EMERGENCY) {
        return K60ThermalLevelEmergency;
    }
    if (millideg >= K60_THERMAL_TRIP_JUNCTION) {
        return K60ThermalLevelJunction;
    }
    if (millideg >= K60_THERMAL_TRIP_WARM) {
        return K60ThermalLevelWarm;
    }
    return K60ThermalLevelNone;
}

int k60_thermal_zone_level(int zone, int32_t millideg)
{
    if (zone < 0 || zone >= K60ThermalZoneCount) {
        return -1;
    }
    return (int)k60_thermal_level_at(millideg);
}

int k60_thermal_advise(const K60ThermalReading *readings, unsigned count,
                       K60ThermalAdvisory *out)
{
    unsigned i;
    int worst_zone = -1;
    int32_t worst_deg = 0;
    enum k60_thermal_level worst = K60ThermalLevelNone;

    if (out == 0) {
        return -1;
    }
    if (count > K60_THERMAL_MAX_READINGS) {
        return -3;
    }
    if (count != 0 && readings == 0) {
        return -2;
    }
    for (i = 0; i < count; i++) {
        enum k60_thermal_level level;
        int zone = readings[i].zone;
        int32_t deg = readings[i].millideg;

        if (zone < 0 || zone >= K60ThermalZoneCount) {
            return -4;
        }
        level = k60_thermal_level_at(deg);
        if ((int)level > (int)worst ||
            ((int)level == (int)worst && level != K60ThermalLevelNone &&
             (deg > worst_deg || (deg == worst_deg && zone < worst_zone)))) {
            worst = level;
            worst_zone = zone;
            worst_deg = deg;
        }
    }

    out->level = worst;
    out->zone = worst == K60ThermalLevelNone ? -1 : worst_zone;
    out->millideg = worst == K60ThermalLevelNone ? 0 : worst_deg;
    out->allow_raise = (int)worst < (int)K60ThermalLevelEmergency;
    out->throttle_cpu = ((int)worst >= (int)K60ThermalLevelEmergency) ||
                        ((int)worst >= (int)K60ThermalLevelJunction && worst_zone >= 0 &&
                         kZones[worst_zone].cpu);
    out->throttle_gpu = ((int)worst >= (int)K60ThermalLevelEmergency) ||
                        ((int)worst >= (int)K60ThermalLevelJunction && worst_zone >= 0 &&
                         kZones[worst_zone].gpu);
    return 0;
}
