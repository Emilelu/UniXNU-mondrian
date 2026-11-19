/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/*
 * Host test for the thermal trip map. It pins the ladder the live device tree
 * declares, the aggregate policy (worst reading wins) and the hand-off to the
 * rail planner: an emergency reading must refuse a raise. No hardware.
 */
#include "K60ThermalMap.h"
#include "K60RailPlan.h"
#include <stdio.h>
#include <string.h>

static unsigned checks;
static unsigned failures;

static void check(const char *name, int got, int want)
{
    checks++;
    if (got != want) {
        failures++;
        printf("FAIL %s: got %d want %d\n", name, got, want);
    }
}

static void check_str(const char *name, const char *got, const char *want)
{
    checks++;
    if (got == 0 || strcmp(got, want) != 0) {
        failures++;
        printf("FAIL %s: got %s want %s\n", name, got ? got : "(null)", want);
    }
}

static const char *const kZoneNames[K60ThermalZoneCount] = {
    "cpu-0", "cpu-1", "cpuss", "gpuss", "ddr", "aoss", "pm8350", "pm8350c",
    "pm8450",
};

static void test_names(void)
{
    int zone;

    for (zone = 0; zone < K60ThermalZoneCount; zone++) {
        check_str("zone name", k60_thermal_zone_name(zone), kZoneNames[zone]);
    }
    for (zone = 0; zone < K60ThermalZoneCount; zone++) {
        const char *name = k60_thermal_zone_name(zone);
        check("zone name is not empty", name != 0 && name[0] != 0, 1);
    }
    check_str("zone name below range", k60_thermal_zone_name(-1), "invalid");
    check_str("zone name at count", k60_thermal_zone_name(K60ThermalZoneCount),
              "invalid");

    check_str("level none", k60_thermal_level_name(K60ThermalLevelNone), "none");
    check_str("level warm", k60_thermal_level_name(K60ThermalLevelWarm), "warm");
    check_str("level junction", k60_thermal_level_name(K60ThermalLevelJunction),
              "junction");
    check_str("level emergency",
              k60_thermal_level_name(K60ThermalLevelEmergency), "emergency");
    check_str("level reset", k60_thermal_level_name(K60ThermalLevelReset), "reset");
    check_str("level shutdown", k60_thermal_level_name(K60ThermalLevelShutdown),
              "shutdown");
    check_str("level below range", k60_thermal_level_name((enum k60_thermal_level)-1),
              "invalid");
    check_str("level at count",
              k60_thermal_level_name((enum k60_thermal_level)K60ThermalLevelCount),
              "invalid");
}

static void test_ladder(void)
{
    check("ladder negative", (int)k60_thermal_level_at(-1), K60ThermalLevelNone);
    check("ladder zero", (int)k60_thermal_level_at(0), K60ThermalLevelNone);
    check("ladder just below warm", (int)k60_thermal_level_at(89999),
          K60ThermalLevelNone);
    check("ladder warm", (int)k60_thermal_level_at(90000), K60ThermalLevelWarm);
    check("ladder just below junction", (int)k60_thermal_level_at(94999),
          K60ThermalLevelWarm);
    check("ladder junction", (int)k60_thermal_level_at(95000),
          K60ThermalLevelJunction);
    check("ladder just below emergency", (int)k60_thermal_level_at(109999),
          K60ThermalLevelJunction);
    check("ladder emergency", (int)k60_thermal_level_at(110000),
          K60ThermalLevelEmergency);
    check("ladder just below reset", (int)k60_thermal_level_at(114999),
          K60ThermalLevelEmergency);
    check("ladder reset", (int)k60_thermal_level_at(115000), K60ThermalLevelReset);
    check("ladder just below shutdown", (int)k60_thermal_level_at(124999),
          K60ThermalLevelReset);
    check("ladder shutdown", (int)k60_thermal_level_at(125000),
          K60ThermalLevelShutdown);
    check("ladder far above shutdown", (int)k60_thermal_level_at(200000),
          K60ThermalLevelShutdown);

    check("zone level below range", k60_thermal_zone_level(-1, 90000), -1);
    check("zone level at count", k60_thermal_zone_level(K60ThermalZoneCount, 90000),
          -1);
}

static void test_zone_ladder(void)
{
    int zone;

    for (zone = 0; zone < K60ThermalZoneCount; zone++) {
        check("zone none", k60_thermal_zone_level(zone, 0), K60ThermalLevelNone);
    }
    for (zone = 0; zone < K60ThermalZoneCount; zone++) {
        check("zone warm", k60_thermal_zone_level(zone, 90000),
              K60ThermalLevelWarm);
    }
    for (zone = 0; zone < K60ThermalZoneCount; zone++) {
        check("zone emergency", k60_thermal_zone_level(zone, 110000),
              K60ThermalLevelEmergency);
    }
}

static void test_errors(void)
{
    K60ThermalReading one = { K60ThermalZoneCpu0, 90000 };
    K60ThermalReading many[K60_THERMAL_MAX_READINGS + 1];
    K60ThermalAdvisory adv;
    unsigned i;

    check("null advisory", k60_thermal_advise(&one, 1, 0), -1);
    check("null readings with a count", k60_thermal_advise(0, 1, &adv), -2);
    check("null readings with no count is empty",
          k60_thermal_advise(0, 0, &adv), 0);
    check("null readings with a count leaves the advisory alone",
          k60_thermal_advise(0, 2, &adv), -2);

    for (i = 0; i < K60_THERMAL_MAX_READINGS + 1; i++) {
        many[i].zone = K60ThermalZoneCpu0;
        many[i].millideg = 90000;
    }
    check("too many readings", k60_thermal_advise(many,
              K60_THERMAL_MAX_READINGS + 1, &adv), -3);
    check("exactly the maximum readings",
          k60_thermal_advise(many, K60_THERMAL_MAX_READINGS, &adv), 0);
    check("maximum readings level", (int)adv.level, K60ThermalLevelWarm);

    many[0].zone = K60ThermalZoneCount;
    check("unknown zone in the input", k60_thermal_advise(many, 1, &adv), -4);
    many[0].zone = -1;
    check("negative zone in the input", k60_thermal_advise(many, 1, &adv), -4);
}

static void test_policy(void)
{
    K60ThermalReading cpu_warm = { K60ThermalZoneCpu1, 96000 };
    K60ThermalReading gpu_warm = { K60ThermalZoneGpuss, 96000 };
    K60ThermalReading cpu_hot = { K60ThermalZoneCpu0, 111000 };
    K60ThermalReading pmic_warm = { K60ThermalZonePm8350, 91000 };
    K60ThermalReading ddr_hot = { K60ThermalZoneDdr, 115000 };
    K60ThermalReading two[2];
    K60ThermalAdvisory adv;

    check("empty input succeeds", k60_thermal_advise(0, 0, &adv), 0);
    check("empty input level", (int)adv.level, K60ThermalLevelNone);
    check("empty input zone", adv.zone, -1);
    check("empty input degrees", (int)adv.millideg, 0);
    check("empty input allows a raise", adv.allow_raise, 1);
    check("empty input throttles nothing", adv.throttle_cpu + adv.throttle_gpu, 0);

    check("cpu junction is admitted", k60_thermal_advise(&cpu_warm, 1, &adv), 0);
    check("cpu junction level", (int)adv.level, K60ThermalLevelJunction);
    check("cpu junction throttles the cpu", adv.throttle_cpu, 1);
    check("cpu junction spares the gpu", adv.throttle_gpu, 0);
    check("cpu junction still allows a raise", adv.allow_raise, 1);

    check("gpu junction is admitted", k60_thermal_advise(&gpu_warm, 1, &adv), 0);
    check("gpu junction level", (int)adv.level, K60ThermalLevelJunction);
    check("gpu junction throttles the gpu", adv.throttle_gpu, 1);
    check("gpu junction spares the cpu", adv.throttle_cpu, 0);

    check("cpu emergency is admitted", k60_thermal_advise(&cpu_hot, 1, &adv), 0);
    check("cpu emergency level", (int)adv.level, K60ThermalLevelEmergency);
    check("cpu emergency refuses a raise", adv.allow_raise, 0);
    check("cpu emergency throttles the cpu", adv.throttle_cpu, 1);
    check("cpu emergency throttles the gpu too", adv.throttle_gpu, 1);
    check("cpu emergency keeps its zone", adv.zone, K60ThermalZoneCpu0);
    check("cpu emergency keeps its reading", (int)adv.millideg, 111000);

    check("pmic warm is admitted", k60_thermal_advise(&pmic_warm, 1, &adv), 0);
    check("pmic warm level", (int)adv.level, K60ThermalLevelWarm);
    check("pmic warm allows a raise", adv.allow_raise, 1);
    check("pmic warm throttles the cpu", adv.throttle_cpu, 0);
    check("pmic warm throttles the gpu", adv.throttle_gpu, 0);

    check("ddr reset is admitted", k60_thermal_advise(&ddr_hot, 1, &adv), 0);
    check("ddr reset level", (int)adv.level, K60ThermalLevelReset);
    check("ddr reset refuses a raise", adv.allow_raise, 0);
    check("ddr reset throttles the cpu", adv.throttle_cpu, 1);
    check("ddr reset throttles the gpu", adv.throttle_gpu, 1);

    two[0] = cpu_warm;
    two[1] = gpu_warm;
    check("two zones are admitted", k60_thermal_advise(two, 2, &adv), 0);
    check("two zones keep a junction level", (int)adv.level,
          K60ThermalLevelJunction);
    check("equal readings prefer the lower zone index", adv.zone,
          K60ThermalZoneCpu1);
    two[0].zone = K60ThermalZoneCpu1;
    two[0].millideg = 96000;
    two[1].zone = K60ThermalZoneCpu0;
    two[1].millideg = 96000;
    check("a tie prefers the lower zone index", k60_thermal_advise(two, 2, &adv), 0);
    check("a tie picks cpu-0", adv.zone, K60ThermalZoneCpu0);
    two[0].millideg = 97000;
    check("a higher temperature wins the tie", k60_thermal_advise(two, 2, &adv), 0);
    check("the hotter reading is named", (int)adv.millideg, 97000);
    check("the hotter zone is named", adv.zone, K60ThermalZoneCpu1);
}

static void test_rail_handoff(void)
{
    K60RailState state;
    K60RailPoint from = { 1000000, 800000, 0 };
    K60RailPoint target = { 1500000, 900000, 0 };
    K60RailStep steps[8];
    K60ThermalReading hot = { K60ThermalZoneCpu1, 111000 };
    K60ThermalReading warm = { K60ThermalZoneCpu1, 96000 };
    K60ThermalAdvisory adv;
    unsigned count = 0;

    memset(&state, 0, sizeof state);
    k60_rail_reset(&state, &from);
    check("hot advisory", k60_thermal_advise(&hot, 1, &adv), 0);
    check("emergency refuses the rail raise",
          k60_rail_plan(&state, &target, adv.allow_raise, steps, 8, &count), -2);
    check("the refused plan has no steps", (int)count, 0);
    check("warm advisory", k60_thermal_advise(&warm, 1, &adv), 0);
    check("junction admits the rail raise",
          k60_rail_plan(&state, &target, adv.allow_raise, steps, 8, &count), 0);
    check("the admitted plan has steps", count > 0, 1);
}

int main(void)
{
    test_names();
    test_ladder();
    test_zone_ladder();
    test_errors();
    test_policy();
    test_rail_handoff();

    printf("thermal-map: %u checks, %u failures\n", checks, failures);
    if (failures != 0) {
        return 1;
    }
    printf("TESTS OK %u checks\n", checks);
    return 0;
}
