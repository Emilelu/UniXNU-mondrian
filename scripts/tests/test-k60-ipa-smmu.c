/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Host test for the K60 IPA SMMU planner/configuration.
 *
 * Simulates the ARM SMMUv2 register file of the K60 qcom,qsmmu-v500:
 * IDR0 bit30 with 120 stream-match groups, IDR1 with 78 context banks and
 * 4 KiB page geometry, IDR2 with 48-bit VA64 support in all three fields,
 * one free exact SMR slot and a bypass SCTLR. It checks the plan fields,
 * the exact CBAR/CBA2R/S2CR/SMR writes and their readback, then exercises
 * the refusal paths (missing VA64, oversized DMA, busy context bank,
 * masked conflicting SMR).
 */

#include <stdio.h>
#include <string.h>

#include "K60IpaSmmu.h"

#define SIM_BYTES 0x100000u

typedef struct {
    uint32_t regs[SIM_BYTES / 4u];
    unsigned reads;
    unsigned writes;
    unsigned write_count;
    struct {
        unsigned offset;
        uint32_t value;
    } log[16];
} SimSmmu;

static SimSmmu g_sim;

static uint32_t
sim_read(void *context, unsigned offset)
{
    SimSmmu *sim = context;

    sim->reads++;
    if (offset >= SIM_BYTES || (offset & 3u) != 0) {
        return 0xffffffffu;
    }
    return sim->regs[offset / 4u];
}

static void
sim_write(void *context, unsigned offset, uint32_t value)
{
    SimSmmu *sim = context;

    sim->writes++;
    if (offset >= SIM_BYTES || (offset & 3u) != 0) {
        return;
    }
    sim->regs[offset / 4u] = value;
    if (sim->write_count <
        (unsigned)(sizeof(sim->log) / sizeof(sim->log[0]))) {
        sim->log[sim->write_count].offset = offset;
        sim->log[sim->write_count].value = value;
        sim->write_count++;
    }
}

static uint32_t
sim_reg(const SimSmmu *sim, unsigned offset)
{
    return sim->regs[offset / 4u];
}

static void
sim_set(SimSmmu *sim, unsigned offset, uint32_t value)
{
    sim->regs[offset / 4u] = value;
}

static int
fail(const char *what)
{
    printf("FAIL %s\n", what);
    return 1;
}

/* IDR0 = bit30 | 120 groups; IDR1 = 78 banks, PAGE_SIZE field 0 => 2 pages;
 * IDR2 = VA64 48-bit width in each of the three IDR2 fields (bit12 set).
 * Slots 0..8 and 10..119 hold foreign streams, slot 9 is the only free one.
 */
static void
fixture(SimSmmu *sim)
{
    unsigned i;

    memset(sim, 0, sizeof(*sim));
    sim_set(sim, 0x20u, 0x40000078u);
    sim_set(sim, 0x24u, 0x0000004eu);
    sim_set(sim, 0x28u, 0x00001555u);
    for (i = 0; i < 120u; i++) {
        if (i == 9u) {
            continue;
        }
        sim_set(sim, 0x800u + 4u * i, 0x80000000u | (0x100u + i));
        sim_set(sim, 0xc00u + 4u * i, 0u);
    }
}

static int
expect_error(const char *actual, const char *expected, const char *what)
{
    if (actual == NULL || strcmp(actual, expected) != 0) {
        printf("FAIL %s got=%s\n", what,
            actual != NULL ? actual : "(null)");
        return 0;
    }
    return 1;
}

static int
expect_writes(const SimSmmu *sim, const unsigned *offsets,
    const uint32_t *values, unsigned count, const char *what)
{
    unsigned i;

    if (sim->write_count != count) {
        printf("FAIL %s count=%u want=%u\n", what, sim->write_count, count);
        return 0;
    }
    for (i = 0; i < count; i++) {
        if (sim->log[i].offset != offsets[i] ||
            sim->log[i].value != values[i]) {
            printf("FAIL %s write[%u]=%#x/%#x want=%#x/%#x\n", what, i,
                sim->log[i].offset, sim->log[i].value, offsets[i],
                values[i]);
            return 0;
        }
    }
    return 1;
}

int
main(void)
{
    K60IpaSmmuPlan plan;
    const char *error = NULL;
    unsigned offsets[8];
    uint32_t values[8];
    unsigned i;
    int rc;

    /* 1. Exact IPA setup: one free exact SMR slot, top owned context bank. */
    fixture(&g_sim);
    rc = k60_ipa_smmu_plan(&plan, 0x5c0u, 0x20000000ull, 0x100000ull,
        sim_read, &g_sim, 78u, 120u);
    if (rc != K60IpaSmmuOk || plan.error != NULL ||
        plan.slot != 9u || plan.bank != 77u || plan.pages != 2u ||
        plan.smr != 0u || plan.s2cr != 0u ||
        plan.previous_bank != 0xffffffffu || plan.reuse || plan.migrate) {
        return fail("baseline plan");
    }
    error = (const char *)0x1;
    rc = k60_ipa_smmu_configure(&plan, 0x5c0u, sim_read, sim_write, &g_sim,
        &error);
    if (rc != K60IpaSmmuOk || error != NULL) {
        return fail("baseline configure");
    }
    if (sim_reg(&g_sim, 0x1000u + 4u * 77u) != 0x10000u ||
        sim_reg(&g_sim, 0x1800u + 4u * 77u) != 1u ||
        sim_reg(&g_sim, 0xc00u + 4u * 9u) != 77u ||
        sim_reg(&g_sim, 0x800u + 4u * 9u) != 0x800005c0u ||
        sim_reg(&g_sim, (2u + 77u) * 4096u) != 0u) {
        return fail("baseline registers");
    }
    offsets[0] = (2u + 77u) * 4096u;
    values[0] = 0u;
    offsets[1] = 0x1800u + 4u * 77u;
    values[1] = 1u;
    offsets[2] = 0x1000u + 4u * 77u;
    values[2] = 0x10000u;
    offsets[3] = 0xc00u + 4u * 9u;
    values[3] = 77u;
    offsets[4] = 0x800u + 4u * 9u;
    values[4] = 0x800005c0u;
    if (!expect_writes(&g_sim, offsets, values, 5u, "baseline writes")) {
        return 1;
    }

    /* 2. Exact firmware mapping on a foreign bank migrates without touching
     * the already-correct SMR. */
    fixture(&g_sim);
    sim_set(&g_sim, 0x800u + 4u * 4u, 0x800005c0u);
    sim_set(&g_sim, 0xc00u + 4u * 4u, 3u);
    rc = k60_ipa_smmu_plan(&plan, 0x5c0u, 0x20000000ull, 0x100000ull,
        sim_read, &g_sim, 78u, 120u);
    if (rc != K60IpaSmmuOk || plan.error != NULL || plan.slot != 4u ||
        plan.bank != 77u || plan.reuse != 0 || plan.migrate != 1 ||
        plan.previous_bank != 3u || plan.smr != 0x800005c0u ||
        plan.s2cr != 3u) {
        return fail("migrate plan");
    }
    error = NULL;
    rc = k60_ipa_smmu_configure(&plan, 0x5c0u, sim_read, sim_write, &g_sim,
        &error);
    if (rc != K60IpaSmmuOk || error != NULL ||
        sim_reg(&g_sim, 0x800u + 4u * 4u) != 0x800005c0u ||
        sim_reg(&g_sim, 0xc00u + 4u * 4u) != 77u) {
        return fail("migrate configure");
    }
    offsets[0] = (2u + 77u) * 4096u;
    values[0] = 0u;
    offsets[1] = 0x1800u + 4u * 77u;
    values[1] = 1u;
    offsets[2] = 0x1000u + 4u * 77u;
    values[2] = 0x10000u;
    offsets[3] = 0xc00u + 4u * 4u;
    values[3] = 77u;
    if (!expect_writes(&g_sim, offsets, values, 4u, "migrate writes")) {
        return 1;
    }

    /* 3. Exact mapping already on our bank reuses the bypass context with
     * no register writes at all. */
    fixture(&g_sim);
    sim_set(&g_sim, 0x800u + 4u * 2u, 0x800005c0u);
    sim_set(&g_sim, 0xc00u + 4u * 2u, 77u);
    sim_set(&g_sim, (2u + 77u) * 4096u, 0u);
    sim_set(&g_sim, 0x1000u + 4u * 77u, 0x10000u);
    sim_set(&g_sim, 0x1800u + 4u * 77u, 1u);
    rc = k60_ipa_smmu_plan(&plan, 0x5c0u, 0x20000000ull, 0x100000ull,
        sim_read, &g_sim, 78u, 120u);
    if (rc != K60IpaSmmuOk || plan.error != NULL || plan.slot != 2u ||
        plan.bank != 77u || plan.reuse != 1 || plan.migrate != 0 ||
        plan.previous_bank != 77u || plan.smr != 0x800005c0u ||
        plan.s2cr != 77u) {
        return fail("reuse plan");
    }
    error = NULL;
    rc = k60_ipa_smmu_configure(&plan, 0x5c0u, sim_read, sim_write, &g_sim,
        &error);
    if (rc != K60IpaSmmuOk || error != NULL || g_sim.write_count != 0u) {
        return fail("reuse configure");
    }

    /* 4. Missing VA64 support is refused before any register is considered. */
    fixture(&g_sim);
    sim_set(&g_sim, 0x28u, 0x00000055u);
    rc = k60_ipa_smmu_plan(&plan, 0x5c0u, 0x20000000ull, 0x100000ull,
        sim_read, &g_sim, 78u, 120u);
    if (rc != K60IpaSmmuUnsupported ||
        !expect_error(plan.error, "SMMU AArch64 stage 1 unsupported",
            "VA64 error")) {
        return fail("VA64 status");
    }

    /* 5. DMA that does not fit the 48-bit hardware width is refused. */
    fixture(&g_sim);
    rc = k60_ipa_smmu_plan(&plan, 0x5c0u, 1ull << 48, 0x1000u,
        sim_read, &g_sim, 78u, 120u);
    if (rc != K60IpaSmmuUnsupported ||
        !expect_error(plan.error, "DMA exceeds SMMU address width",
            "DMA error")) {
        return fail("DMA status");
    }

    /* 6. A foreign EE0 stream already mapped into every candidate context
     * bank refuses the reservation and leaves the first error visible. */
    fixture(&g_sim);
    for (i = 0; i < 8u; i++) {
        sim_set(&g_sim, 0x800u + 4u * i, 0x80000000u | (0x400u + i));
        sim_set(&g_sim, 0xc00u + 4u * i, 70u + i);
    }
    rc = k60_ipa_smmu_plan(&plan, 0x5c0u, 0x20000000ull, 0x100000ull,
        sim_read, &g_sim, 78u, 120u);
    if (rc != K60IpaSmmuUnsupported ||
        !expect_error(plan.error, "reserved context bank already used",
            "busy context error")) {
        return fail("busy context status");
    }

    /* 7. Every candidate context bank with SCTLR.M set refuses. */
    fixture(&g_sim);
    for (i = 70u; i <= 77u; i++) {
        sim_set(&g_sim, (2u + i) * 4096u, 1u);
    }
    rc = k60_ipa_smmu_plan(&plan, 0x5c0u, 0x20000000ull, 0x100000ull,
        sim_read, &g_sim, 78u, 120u);
    if (rc != K60IpaSmmuUnsupported ||
        !expect_error(plan.error, "reserved context bank not bypass",
            "busy SCTLR error")) {
        return fail("busy SCTLR status");
    }

    /* 8. Retry loop: only the top bank is busy, so bank 76 is selected. */
    fixture(&g_sim);
    sim_set(&g_sim, (2u + 77u) * 4096u, 1u);
    rc = k60_ipa_smmu_plan(&plan, 0x5c0u, 0x20000000ull, 0x100000ull,
        sim_read, &g_sim, 78u, 120u);
    if (rc != K60IpaSmmuOk || plan.error != NULL || plan.bank != 76u ||
        plan.slot != 9u || plan.pages != 2u) {
        return fail("retry plan");
    }
    error = NULL;
    rc = k60_ipa_smmu_configure(&plan, 0x5c0u, sim_read, sim_write, &g_sim,
        &error);
    if (rc != K60IpaSmmuOk || error != NULL ||
        sim_reg(&g_sim, 0x1000u + 4u * 76u) != 0x10000u ||
        sim_reg(&g_sim, 0x1800u + 4u * 76u) != 1u ||
        sim_reg(&g_sim, 0xc00u + 4u * 9u) != 76u ||
        sim_reg(&g_sim, 0x800u + 4u * 9u) != 0x800005c0u) {
        return fail("retry configure");
    }

    /* 9. A masked SID that matches is an unconditional refusal. */
    fixture(&g_sim);
    sim_set(&g_sim, 0x800u, 0x80000000u | (1u << 16) | 0x5c0u);
    sim_set(&g_sim, 0xc00u, 0u);
    rc = k60_ipa_smmu_plan(&plan, 0x5c0u, 0x20000000ull, 0x100000ull,
        sim_read, &g_sim, 78u, 120u);
    if (rc != K60IpaSmmuUnsupported ||
        !expect_error(plan.error, "conflicting IPA stream mapping",
            "masked SMR error")) {
        return fail("masked SMR status");
    }

    printf("K60 IPA SMMU PASS id0=%#x id1=%#x id2=%#x groups=120 banks=78 "
        "pages=2 slot=9 bank=77 smr=%#x s2cr=%u cbar=%#x cba2r=%u\n",
        0x40000078u, 0x0000004eu, 0x00001555u, 0x800005c0u, 77u,
        0x10000u, 1u);
    return 0;
}
