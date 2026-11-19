/* Host test for drivers/PongThermal/K60Tsens.c - pure decode logic plus the MMIO
 * readers driven from a fake TM window. Build and run:
 *   cc -std=c11 -O1 -Wall -Wextra -I drivers/PongThermal \
 *      -o build/tsenstest scripts/tests/test-k60-thermal-tsens.c && ./build/tsenstest
 */
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include "../../drivers/PongThermal/K60Tsens.c"

static uint32_t tm[0x200u / 4u];

/* status word for a temperature in milli-Celsius with VALID set */
static uint32_t st(int32_t mc)
{
    int32_t deci = mc / 100;
    return ((uint32_t)deci & K60TSENS_STATUS_TEMP_MASK) | K60TSENS_STATUS_VALID;
}

int main(void)
{
    int fails = 0;
    K60TsensReading r;
    K60TsensReading all[K60TsensSensorsPerController];
    const K60TsensSensor *tab;
    uint32_t n = 0, major = 0, minor = 0, step = 0, i;
    int seen0 = 0, seen1 = 0;

    /* 1. plain conversion: deci-Celsius * 100 */
    if (k60tsens_status_to_mc(st(54900)) != 54900) { printf("FAIL to_mc 54900\n"); fails++; }
    if (k60tsens_status_to_mc(st(0)) != 0) { printf("FAIL to_mc 0\n"); fails++; }

    /* 2. negative temperatures survive sign extension of the 12-bit field */
    if (k60tsens_status_to_mc(st(-40000)) != -40000) { printf("FAIL to_mc -40000\n"); fails++; }
    if (k60tsens_status_to_mc(st(-1000)) != -1000) { printf("FAIL to_mc -1000\n"); fails++; }

    /* 3. flag bits 16..20 */
    if (k60tsens_status_flags(K60TSENS_STATUS_MIN | K60TSENS_STATUS_UPPER) != 0x05u) {
        printf("FAIL flags\n"); fails++;
    }

    /* 4. decode: valid reading */
    if (k60tsens_decode(st(65300), &r) != K60TsensOk || r.valid != 1 || r.milli_c != 65300) {
        printf("FAIL decode valid\n"); fails++;
    }

    /* 5. decode: VALID clear -> no reading, and milli_c is not left uninitialised */
    if (k60tsens_decode(0x00000225u, &r) != K60TsensNoValid || r.valid != 0 || r.milli_c != 0) {
        printf("FAIL decode no-valid\n"); fails++;
    }

    /* 6. decode: outside -40..160 C is rejected even with VALID set */
    if (k60tsens_decode(st(160100), &r) != K60TsensOutOfRange || r.valid != 0) {
        printf("FAIL decode 160.1\n"); fails++;
    }
    if (k60tsens_decode(st(-40100), &r) != K60TsensOutOfRange || r.valid != 0) {
        printf("FAIL decode -40.1\n"); fails++;
    }
    if (k60tsens_decode(st(160000), &r) != K60TsensOk) { printf("FAIL decode 160.0\n"); fails++; }
    if (k60tsens_decode(st(-40000), &r) != K60TsensOk) { printf("FAIL decode -40.0\n"); fails++; }

    /* 7. bad argument */
    if (k60tsens_decode(st(5000), 0) != K60TsensBadArg) { printf("FAIL decode null\n"); fails++; }

    /* 8. SROT_HW_VER field split (tsens-v2.c:56-58) */
    if (k60tsens_decode_hw_ver(0x20030007u, &major, &minor, &step) != K60TsensOk ||
        major != 2 || minor != 3 || step != 7) { printf("FAIL hw_ver\n"); fails++; }
    if (k60tsens_decode_hw_ver(0, &major, &minor, 0) != K60TsensBadArg) {
        printf("FAIL hw_ver null\n"); fails++;
    }

    /* 9. TSENS_EN is read, never written */
    if (!k60tsens_ctrl_enabled(0x1u) || k60tsens_ctrl_enabled(0x0u) ||
        k60tsens_ctrl_enabled(0xfffffffeu)) { printf("FAIL ctrl\n"); fails++; }

    /* 10. MMIO read from a fake TM window: 0xa0 + 4n word index */
    memset(tm, 0, sizeof tm);
    for (i = 0; i < K60TsensSensorsPerController; i++) {
        tm[(0xa0u + 4u * i) / 4u] = st(40000 + (int32_t)i * 100);
    }
    if (k60tsens_read(tm, 0, &r) != K60TsensOk || r.milli_c != 40000) { printf("FAIL read s0\n"); fails++; }
    if (k60tsens_read(tm, 15, &r) != K60TsensOk || r.milli_c != 41500) { printf("FAIL read s15\n"); fails++; }
    if (k60tsens_read(tm, 16, &r) != K60TsensBadArg) { printf("FAIL read s16\n"); fails++; }
    if (k60tsens_read(0, 0, &r) != K60TsensBadArg) { printf("FAIL read null\n"); fails++; }
    if (k60tsens_read_controller(tm, all) != 16) { printf("FAIL read_controller\n"); fails++; }

    /* 11. one dead sensor lowers the valid count but does not poison the others */
    tm[(0xa0u + 4u * 7u) / 4u] = 0x00000225u;   /* VALID clear */
    if (k60tsens_read_controller(tm, all) != 15) { printf("FAIL read_controller 15\n"); fails++; }
    if (all[6].valid != 1 || all[7].valid != 0 || all[8].valid != 1) { printf("FAIL mixed\n"); fails++; }

    /* 12. TM_TRDY bit 0 */
    tm[0xe4u / 4u] = 1u;
    if (k60tsens_trdy(tm) != 1) { printf("FAIL trdy\n"); fails++; }
    tm[0xe4u / 4u] = 0u;
    if (k60tsens_trdy(tm) != 0) { printf("FAIL trdy 0\n"); fails++; }

    /* 13. the board table: 32 entries, 16 per controller, contiguous indices */
    tab = k60tsens_sensor_table(&n);
    if (n != 32u || tab == 0) { printf("FAIL table count\n"); fails++; }
    for (i = 0; i < n; i++) {
        if (tab[i].controller > 1u || tab[i].index > 15u) { printf("FAIL table entry %u\n", i); fails++; }
        if (tab[i].controller == 0u) { seen0++; } else { seen1++; }
    }
    if (seen0 != 16 || seen1 != 16) { printf("FAIL table split %d/%d\n", seen0, seen1); fails++; }
    if (strcmp(k60tsens_sensor_name(0, 0), "aoss-0") != 0) { printf("FAIL name tsens0[0]\n"); fails++; }
    if (strcmp(k60tsens_sensor_name(0, 14), "gpuss-0") != 0) { printf("FAIL name tsens0[14]\n"); fails++; }
    if (strcmp(k60tsens_sensor_name(1, 9), "ddr") != 0) { printf("FAIL name tsens1[9]\n"); fails++; }
    if (strcmp(k60tsens_sensor_name(1, 15), "camera-1") != 0) { printf("FAIL name tsens1[15]\n"); fails++; }
    if (k60tsens_sensor_name(1, 16) != 0 || k60tsens_sensor_name(2, 0) != 0) {
        printf("FAIL name out of range\n"); fails++;
    }
    /* zone ids are the live Android numbering 24..55, in table order */
    for (i = 0; i < n; i++) {
        if (tab[i].zone != 24u + i) { printf("FAIL zone %u\n", i); fails++; }
    }

    printf(fails ? "TESTS FAILED %d\n" : "TESTS OK %d\n", fails ? fails : 16);
    return fails != 0;
}
