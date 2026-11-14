/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Host test for the board DTS thermal ladder: builds the pure arithmetic of
 * drivers/PongThermal/K60ThermalZones.c against the passive trips of the board DTB and
 * checks the table, the hysteresis, the unreadable-sensor rule and the closest-zone scan.
 * Build: cc -std=c11 -O1 -Wall -Wextra -Werror -I drivers/PongThermal \
 *        scripts/tests/test-k60-thermal-zones.c -o build/thermal/test-zones */
#include <stdio.h>
#include <string.h>
#include "../../drivers/PongThermal/K60ThermalKernel.h"
/* The ladder reuses the trip arithmetic of the five-domain level, so the host build
 * compiles that translation unit in. Both are pure C with no kernel headers. */
#include "../../drivers/PongThermal/K60ThermalLevel.c"
#include "../../drivers/PongThermal/K60ThermalZones.c"

static unsigned gFailures;
static unsigned gChecks;

#define CHECK(cond, what)                                                    \
    do {                                                                     \
        ++gChecks;                                                           \
        if (!(cond)) {                                                       \
            ++gFailures;                                                     \
            printf("FAIL %s:%d %s\n", __FILE__, __LINE__, what);             \
        }                                                                    \
    } while (0)

static void test_table(void)
{
    CHECK(K60TzZones == 32, "one zone per sampled sensor");
    for (unsigned slot = 0; slot < K60TzZones; ++slot) {
        const K60TzZone *zone = k60tz_zone(slot);

        CHECK(zone != (const K60TzZone *)0, "every slot has a zone");
        if (zone == (const K60TzZone *)0) {
            continue;
        }
        CHECK(zone->tiers == 2u || zone->tiers == 3u, "a zone has two or three passive trips");
        CHECK(zone->tiers <= K60TzTiers, "tiers fits the row");
        for (unsigned t = 0; t < zone->tiers; ++t) {
            CHECK(zone->trips[t].milli_c > 0, "a used trip has a temperature");
            CHECK(zone->trips[t].hysteresis_mc > 0, "a used trip has the DT hysteresis");
            if (t > 0) {
                CHECK(zone->trips[t].milli_c > zone->trips[t - 1].milli_c, "trips ascend");
            }
        }
        CHECK(k60tz_name(slot)[0] != '?', "every slot has a name");
        CHECK(strcmp(k60tz_name(slot), pong_thermal_sensors[slot].name) == 0,
              "the zone name is the sensor name");
    }
    CHECK(k60tz_zone(K60TzZones) == (const K60TzZone *)0, "no zone past the last slot");
    CHECK(strcmp(k60tz_name(K60TzZones), "?") == 0, "no name past the last slot");

    /* Spot rows against the DTS: aoss-0 has the reset-monitor and thermal-engine trips
     * only (:7121, :7115); the big cluster adds the emergency trip at 110 C (:7238);
     * gpuss-0 has the 95 C junction trip (:7600); ddr has 90 C (:8008) and its row is
     * not in DTS order, so this checks the sort; mdmss-0 keeps only its two passive
     * trips (:8068, :8048) and not the active 102/105 C pair (:8054, :8061). */
    CHECK(k60tz_zone(0)->tiers == 2 && k60tz_zone(0)->trips[0].milli_c == 115000 &&
          k60tz_zone(0)->trips[1].milli_c == 125000, "aoss-0 is 115/125 C");
    CHECK(k60tz_zone(5)->tiers == 3 && k60tz_zone(5)->trips[0].milli_c == 110000 &&
          k60tz_zone(5)->trips[0].hysteresis_mc == 10000, "cpu-1-0 starts at 110 C / 10 C");
    CHECK(k60tz_zone(14)->tiers == 3 && k60tz_zone(14)->trips[0].milli_c == 95000,
          "gpuss-0 starts at 95 C");
    CHECK(k60tz_zone(25)->tiers == 3 && k60tz_zone(25)->trips[0].milli_c == 90000 &&
          k60tz_zone(25)->trips[1].milli_c == 115000, "ddr starts at 90 C and is sorted");
    CHECK(k60tz_zone(26)->tiers == 2 && k60tz_zone(26)->trips[1].milli_c == 125000,
          "mdmss-0 keeps the passive trips only");
    for (unsigned slot = 0; slot < K60TzZones; ++slot) {
        CHECK(strcmp(k60tz_name(slot), "mx-pe") != 0, "mx-pe is not a temperature zone");
        CHECK(strcmp(k60tz_name(slot), "isense_trim") != 0, "isense_trim is not a temperature zone");
    }
}

static void test_zone_level(void)
{
    uint8_t after = 99;

    /* cpu-1-0: 110/10, 115/5, 125/1. */
    CHECK(k60tz_zone_level(0, 109999, 5, &after) == 0 && after == 0, "below 110 C is level 0");
    CHECK(k60tz_zone_level(0, 110000, 5, &after) == 1 && after == 1, "110 C is level 1");
    CHECK(k60tz_zone_level(1, 100000, 5, &after) == 1, "110 C holds at exactly 110-10 C");
    CHECK(k60tz_zone_level(1, 99999, 5, &after) == 0 && after == 0, "below 110-10 C releases");
    CHECK(k60tz_zone_level(0, 115000, 5, &after) == 2 && after == 2, "115 C is level 2");
    CHECK(k60tz_zone_level(2, 125000, 5, &after) == 3 && after == 3, "125 C is level 3");
    CHECK(k60tz_zone_level(3, 124000, 5, &after) == 3, "124 C holds level 3 (125-1)");
    CHECK(k60tz_zone_level(3, 123999, 5, &after) == 2, "below 125-1 C drops to level 2");

    /* A two-trip zone stops at 2 even above its top trip. */
    CHECK(k60tz_zone_level(0, 115000, 0, &after) == 1, "aoss-0 115 C is level 1");
    CHECK(k60tz_zone_level(0, 125000, 0, &after) == 2 && after == 2, "aoss-0 tops out at level 2");
    CHECK(k60tz_zone_level(2, 140000, 0, &after) == 2, "a second trip is the ceiling");

    CHECK(k60tz_zone_level(1, K60TL_NO_READING, 5, &after) == 0 && after == 0,
          "no reading is level 0 and forgets the trips");
    CHECK(k60tz_zone_level(0, 120000, K60TzZones, &after) == 0 && after == 0,
          "an out-of-range slot is level 0");
    CHECK(k60tz_zone_level(0, 115000, 5, (uint8_t *)0) == 2, "the counted state is optional");
}

static void test_step(void)
{
    int32_t milli_c[K60TzZones];
    K60TzState state;

    for (unsigned slot = 0; slot < K60TzZones; ++slot) {
        milli_c[slot] = K60TL_NO_READING;
    }
    memset(&state, 0, sizeof(state));
    CHECK(k60tz_step(&state, milli_c) == 0, "no readings is level 0");

    milli_c[7] = 111000;
    CHECK(k60tz_step(&state, milli_c) == 1, "one zone at 111 C is level 1");
    milli_c[7] = 126000;
    CHECK(k60tz_step(&state, milli_c) == 3 && state.crossed[7] == 3, "one zone at 126 C is level 3");
    milli_c[7] = 123000;
    CHECK(k60tz_step(&state, milli_c) == 2 && state.crossed[7] == 2, "123 C drops it to level 2");

    /* The board level is the worst zone, not the worst average. */
    milli_c[7] = 111000;
    milli_c[0] = 126000;
    CHECK(k60tz_step((K60TzState *)0, milli_c) == 2, "aoss-0 tops out at 2 while cpu-1-2 is at 1");
    milli_c[25] = 90000;
    CHECK(k60tz_step((K60TzState *)0, milli_c) == 2, "ddr at exactly 90 C is level 1");
    milli_c[25] = 125000;
    CHECK(k60tz_step((K60TzState *)0, milli_c) == 3, "ddr at 125 C is level 3");
    CHECK(k60tz_step((K60TzState *)0, (const int32_t *)0) == 0, "no array is level 0");
}

static void test_closest(void)
{
    int32_t milli_c[K60TzZones];
    struct K60TzClosest closest;

    for (unsigned slot = 0; slot < K60TzZones; ++slot) {
        milli_c[slot] = 45000;
    }
    CHECK(k60tz_closest(milli_c, &closest) == 0, "a reading exists");
    CHECK(closest.slot == 25 && closest.level == 0 && closest.margin_mc == 45000,
          "ddr at 45 C is the closest zone, 45 C below its 90 C trip");
    CHECK(closest.next_tier == 0, "the next tier is the first one");

    milli_c[25] = 91000;
    CHECK(k60tz_closest(milli_c, &closest) == 0 && closest.slot == 25 &&
          closest.level == 1 && closest.margin_mc == 24000,
          "ddr at 91 C is level 1 and 24 C below its 115 C trip");

    milli_c[8] = 130000;
    CHECK(k60tz_closest(milli_c, &closest) == 0 && closest.slot == 8 &&
          closest.margin_mc == -1 && closest.level == 3,
          "a zone past its last trip wins the scan");

    for (unsigned slot = 0; slot < K60TzZones; ++slot) {
        milli_c[slot] = K60TL_NO_READING;
    }
    CHECK(k60tz_closest(milli_c, &closest) == -1, "no readings means no closest zone");
    CHECK(k60tz_closest(milli_c, (struct K60TzClosest *)0) == -1, "a missing output is rejected");
}

int main(void)
{
    test_table();
    test_zone_level();
    test_step();
    test_closest();
    if (gFailures != 0) {
        printf("TESTS FAILED %u of %u\n", gFailures, gChecks);
        return 1;
    }
    printf("TESTS OK %u\n", gChecks);
    return 0;
}
