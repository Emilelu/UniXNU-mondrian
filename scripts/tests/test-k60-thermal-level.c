/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Host test for the thermal pressure level: builds the pure arithmetic of
 * drivers/PongThermal/K60ThermalLevel.c against the trip points of the board DTB and
 * checks the hysteresis, the unreadable-sensor rule and the domain table.
 * Build: cc -std=c11 -O1 -Wall -Wextra -I drivers/PongThermal \
 *        scripts/tests/test-k60-thermal-level.c -o build/thermal/test-level */
#include <stdio.h>
#include <string.h>
#include "../../drivers/PongThermal/K60ThermalLevel.c"

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

static void test_tables(void)
{
    CHECK(k60tl_trips(K60TlCpuLittle) == k60tl_trips(K60TlCpuBig),
          "both CPU clusters share one trip table");
    for (unsigned i = 0; i < K60TlInputs; ++i) {
        const K60TlTrip *t = k60tl_trips(i);
        CHECK(t != (const K60TlTrip *)0, "every input has trips");
        for (unsigned k = 1; k < K60TlTrips; ++k) {
            CHECK(t[k].milli_c > t[k - 1].milli_c, "trips ascend");
        }
        CHECK(t[K60TlTrips - 1].milli_c == 125000, "board-wide trip is 125 C");
        CHECK(k60tl_input_name(i)[0] != '?', "input has a name");
    }
    CHECK(k60tl_trips(K60TlInputs) == (const K60TlTrip *)0, "no trips past the last input");
    CHECK(strcmp(k60tl_level_name(K60TlTrapping), "trapping") == 0, "level 3 is trapping");

    /* The numbers IOPMrootDomain understands: IOPM.h:764 normal 0, :765 danger 5,
     * :768 warning 100, :769 trap 110. Only 100 and 110 move thermalWarningState
     * (IOPMrootDomain.cpp:8133-8134), which is why heavy and trapping carry them. */
    CHECK(k60tl_platform_value(K60TlNominal) == 0u, "nominal publishes as normal 0");
    CHECK(k60tl_platform_value(K60TlModerate) == 5u, "moderate publishes as danger 5");
    CHECK(k60tl_platform_value(K60TlHeavy) == 100u, "heavy publishes as warning 100");
    CHECK(k60tl_platform_value(K60TlTrapping) == 110u, "trapping publishes as trap 110");
    CHECK(k60tl_platform_value(K60TlSleeping) == 110u, "sleeping shares the trap value");
    CHECK(k60tl_platform_value(9u) == 0u, "an out-of-range level publishes as nominal");
    CHECK(strcmp(k60tl_level_name(9), "?") == 0, "level out of range has no name");

    /* The DT numbers themselves: 110/10, 115/5, 125/1 for CPU; 95/5 for GPU and NPU;
     * 90/5 for DDR (docs/research/thermal/05-PRESSURE-LEVEL.md §2). */
    CHECK(k60tl_trips(K60TlCpuLittle)[0].milli_c == 110000 &&
          k60tl_trips(K60TlCpuLittle)[0].hysteresis_mc == 10000, "cpu trip 1 = 110 C / 10 C");
    CHECK(k60tl_trips(K60TlGpu)[0].milli_c == 95000 &&
          k60tl_trips(K60TlGpu)[0].hysteresis_mc == 5000, "gpu trip 1 = 95 C / 5 C");
    CHECK(k60tl_trips(K60TlNpu)[0].milli_c == 95000, "npu trip 1 = 95 C");
    CHECK(k60tl_trips(K60TlDdr)[0].milli_c == 90000 &&
          k60tl_trips(K60TlDdr)[0].hysteresis_mc == 5000, "ddr trip 1 = 90 C / 5 C");
}

static void test_input_level(void)
{
    const K60TlTrip *cpu = k60tl_trips(K60TlCpuBig);
    unsigned after = 99;

    CHECK(k60tl_input_level(0, 109999, cpu, K60TlTrips, &after) == 0 && after == 0,
          "below 110 C is nominal");
    CHECK(k60tl_input_level(0, 110000, cpu, K60TlTrips, &after) == 1 && after == 1,
          "110 C crosses the first trip exactly");
    CHECK(k60tl_input_level(1, 110000, cpu, K60TlTrips, &after) == 1,
          "110 C keeps the crossed trip (hysteresis holds it)");
    CHECK(k60tl_input_level(1, 100001, cpu, K60TlTrips, &after) == 1,
          "just above 110-10 C still holds");
    CHECK(k60tl_input_level(1, 100000, cpu, K60TlTrips, &after) == 1,
          "at exactly 110-10 C the trip is still crossed (release is strictly below)");
    CHECK(k60tl_input_level(1, 99999, cpu, K60TlTrips, &after) == 0 && after == 0,
          "below 110-10 C releases the trip");
    CHECK(k60tl_input_level(0, 114999, cpu, K60TlTrips, &after) == 1,
          "just below 115 C is still level 1");
    CHECK(k60tl_input_level(0, 115000, cpu, K60TlTrips, &after) == 2,
          "115 C is level 2");
    CHECK(k60tl_input_level(2, 125000, cpu, K60TlTrips, &after) == 3 && after == 3,
          "125 C is level 3");
    CHECK(k60tl_input_level(3, 124000, cpu, K60TlTrips, &after) == 3,
          "124 C holds level 3 (125-1)");
    CHECK(k60tl_input_level(3, 123999, cpu, K60TlTrips, &after) == 2,
          "below 125-1 C drops to level 2");

    CHECK(k60tl_input_level(2, K60TL_NO_READING, cpu, K60TlTrips, &after) == 0 && after == 0,
          "no reading is nominal and forgets the trips");
    CHECK(k60tl_input_level(0, 130000, (const K60TlTrip *)0, K60TlTrips, &after) == 0,
          "no table is nominal");
    CHECK(k60tl_input_level(0, 130000, cpu, 0, &after) == 0, "no trips is nominal");
}

static void test_step(void)
{
    int32_t mc[K60TlInputs] = {40000, 42000, 38000, 39000, 41000};
    K60TlState state;

    memset(&state, 0, sizeof state);
    CHECK(k60tl_step(&state, mc) == K60TlNominal, "cool board is nominal");
    CHECK(k60tl_step((K60TlState *)0, mc) == K60TlNominal, "stateless query works");

    mc[K60TlGpu] = 95000;                       /* GPU is the hot one */
    CHECK(k60tl_step(&state, mc) == K60TlModerate, "GPU at 95 C is moderate");
    CHECK(state.crossed[K60TlGpu] == 1, "GPU trip remembered");

    mc[K60TlGpu] = K60TL_NO_READING;            /* GPU unreadable now */
    CHECK(k60tl_step(&state, mc) == K60TlNominal, "unreadable GPU cannot hold the level");
    CHECK(state.crossed[K60TlGpu] == 0, "unreadable GPU forgets its trip");

    mc[K60TlGpu] = 38000;
    mc[K60TlCpuBig] = 110000;                   /* big cluster hot instead */
    CHECK(k60tl_step(&state, mc) == K60TlModerate, "big cluster at 110 C is moderate");
    mc[K60TlCpuBig] = 115000;
    CHECK(k60tl_step(&state, mc) == K60TlHeavy, "big cluster at 115 C is heavy");
    mc[K60TlDdr] = 90000;
    CHECK(k60tl_step(&state, mc) == K60TlHeavy, "a second domain at its first trip cannot raise it");
    mc[K60TlDdr] = 125000;
    CHECK(k60tl_step(&state, mc) == K60TlTrapping, "DDR at 125 C is trapping");

    /* The highest input wins, and each input keeps its own hysteresis state. */
    mc[K60TlDdr] = 120000;
    mc[K60TlCpuBig] = 114000;
    CHECK(k60tl_step(&state, mc) == K60TlHeavy, "both hold their levels through hysteresis");
    CHECK(state.crossed[K60TlDdr] == 2 && state.crossed[K60TlCpuBig] == 2,
          "per-input state kept");
    CHECK(k60tl_step((K60TlState *)0, (const int32_t *)0) == K60TlNominal,
          "no readings at all is nominal");
}

static void test_sensor_map(void)
{
    /* tsens0 idx 0..4 are aoss/cpuss (unused), 5..13 the big cluster, 14/15 the GPU. */
    CHECK(k60tl_input_of_sensor(0) == K60TlNoInput, "aoss-0 unused");
    CHECK(k60tl_input_of_sensor(5) == K60TlCpuBig, "tsens0 idx 5 = cpu-1-0");
    CHECK(k60tl_input_of_sensor(13) == K60TlCpuBig, "tsens0 idx 13 = cpu-1-8");
    CHECK(k60tl_input_of_sensor(14) == K60TlGpu && k60tl_input_of_sensor(15) == K60TlGpu,
          "tsens0 idx 14/15 = gpuss");
    CHECK(k60tl_input_of_sensor(16) == K60TlNoInput, "tsens1 idx 0 = aoss-1");
    CHECK(k60tl_input_of_sensor(17) == K60TlCpuLittle, "tsens1 idx 1 = cpu-0-0");
    CHECK(k60tl_input_of_sensor(20) == K60TlCpuLittle, "tsens1 idx 4 = cpu-0-3");
    CHECK(k60tl_input_of_sensor(21) == K60TlNpu && k60tl_input_of_sensor(23) == K60TlNpu,
          "tsens1 idx 5..7 = nspss");
    CHECK(k60tl_input_of_sensor(24) == K60TlNoInput, "tsens1 idx 8 = video");
    CHECK(k60tl_input_of_sensor(25) == K60TlDdr, "tsens1 idx 9 = ddr");
    CHECK(k60tl_input_of_sensor(26) == K60TlNoInput, "tsens1 idx 10 = mdmss-0");
    CHECK(k60tl_input_of_sensor(32) == K60TlNoInput, "index past the table is unused");
}

int main(void)
{
    test_tables();
    test_input_level();
    test_step();
    test_sensor_map();
    if (gFailures != 0) {
        printf("TESTS FAILED %u of %u\n", gFailures, gChecks);
        return 1;
    }
    printf("TESTS OK %u\n", gChecks);
    return 0;
}
