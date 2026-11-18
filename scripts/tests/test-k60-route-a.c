/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/* Offline host test for the Route A acquisition core. The fake windows model
 * only the bytes this code is allowed to touch: AOSS QMP, IPCC doorbell,
 * command database and the DRV-2 RSC. Every map, read and write is counted. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stddef.h>
#include "K60AdspRouteA.h"
#include "K60PmicRail.h"

#define AOSS_BYTES 0x1000u
#define IPCC_BYTES 0x1000u
#define DB_BYTES 0x20000u
#define RSC_BYTES 0x10000u
#define RSC_TCS4 0x1780u
#define RSC_TCS3 0x14e0u

static unsigned cases;
static const char *scenario;
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL %s:%d: %s: %s\n", __FILE__, __LINE__, scenario, #x); exit(1); } } while (0)

static _Alignas(8) uint32_t aoss[AOSS_BYTES / 4u];
static _Alignas(8) uint32_t ipcc[IPCC_BYTES / 4u];
static _Alignas(8) uint8_t db[DB_BYTES];
static _Alignas(8) uint32_t rsc[RSC_BYTES / 4u];
static unsigned maps, unmaps, kicks, ticks;
static uint64_t map_phys[8];
static unsigned map_flags[8];
static unsigned phase;

static void put16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); }
static void put32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24);
}

static int fake_map(void *ctx, uint64_t physical, size_t bytes, unsigned flags,
    volatile uint8_t **out)
{
    (void)ctx;
    CHECK(out && !*out);
    CHECK(flags == K60_ROUTE_A_MAP_FLAGS);
    CHECK(maps < 8);
    map_phys[maps] = physical;
    map_flags[maps] = flags;
    ++maps;
    if (physical == K60_ROUTE_A_AOSS_PHYS) {
        CHECK(bytes == AOSS_BYTES); *out = (volatile uint8_t *)aoss; return 0;
    }
    if (physical == K60_ROUTE_A_IPCC_PHYS) {
        CHECK(bytes == IPCC_BYTES); *out = (volatile uint8_t *)ipcc; return 0;
    }
    if (physical == K60_CMD_DB_PHYS) {
        CHECK(bytes == DB_BYTES); *out = (volatile uint8_t *)db; return 0;
    }
    if (physical == K60_RSC_DRV2_PHYS) {
        CHECK(bytes == RSC_BYTES); *out = (volatile uint8_t *)rsc; return 0;
    }
    return -1;
}

static void fake_unmap(void *ctx, volatile uint8_t *base, size_t bytes)
{
    (void)ctx;
    CHECK(base != NULL);
    CHECK(bytes == AOSS_BYTES || bytes == IPCC_BYTES || bytes == DB_BYTES || bytes == RSC_BYTES);
    ++unmaps;
}

static void fake_kick(void *ctx, volatile uint8_t *window)
{
    (void)ctx;
    CHECK(window == (volatile uint8_t *)ipcc);
    ++kicks;
    uint32_t *d = aoss;
    /* Complete the three QMP handshake phases, then consume the message. */
    if (d[0x30u / 4u] != 0xffffu) {
        if (d[0x28u / 4u] != 0xffffu) d[0x28u / 4u] = 0xffffu;
        else if (d[0x14u / 4u] != 0xffffu) d[0x14u / 4u] = 0xffffu;
        else d[0x30u / 4u] = 0xffffu;
        return;
    }
    const uint32_t box = d[0x38u / 4u];
    if (d[box / 4u] != 0) d[box / 4u] = 0;
}

static void fake_tick(void *ctx)
{
    (void)ctx;
    ++ticks;
    /* First poll after the command is enabled: status busy; second: done. */
    if (rsc[(RSC_TCS4 + 0x1cu) / 4u] == 1u) {
        if (phase == 0) {
            rsc[(RSC_TCS4 + 0x3cu) / 4u] = 0;
            rsc[(RSC_TCS4 + 0x18u) / 4u] = 0;
            phase = 1;
        } else {
            rsc[(RSC_TCS4 + 0x3cu) / 4u] = 0x10100u;
            rsc[(RSC_TCS4 + 0x18u) / 4u] = 1;
            phase = 0;
        }
    }
}

static void fixture(void)
{
    memset(aoss, 0, sizeof aoss);
    memset(ipcc, 0, sizeof ipcc);
    memset(db, 0, sizeof db);
    memset(rsc, 0, sizeof rsc);
    maps = unmaps = kicks = ticks = 0;
    phase = 0;
    memset(map_phys, 0, sizeof map_phys);
    memset(map_flags, 0, sizeof map_flags);

    aoss[0x00 / 4u] = 0x4d41494cu;
    aoss[0x04 / 4u] = 1u;
    aoss[0x34 / 4u] = 0x200u;
    aoss[0x38 / 4u] = 0x100u;

    /* cmd-db: one slave, two 24-byte entries, four levels per rail. */
    put32(db + 4, K60_CMD_DB_MAGIC);
    put16(db + 8, 1);
    put16(db + 8 + 2, 0);
    put16(db + 8 + 4, 0x40);
    put16(db + 8 + 6, 2);
    memcpy(db + 144, "lcx.lvl", 8);
    put32(db + 144 + 16, 0x100);
    put16(db + 144 + 20, 8);
    put16(db + 144 + 22, 0);
    memcpy(db + 168, "lmx.lvl", 8);
    put32(db + 168 + 16, 0x200);
    put16(db + 168 + 20, 8);
    put16(db + 168 + 22, 8);
    const uint16_t levels[4] = { 16, 32, 48, 64 };
    for (unsigned i = 0; i < 4; ++i) {
        put16(db + 208 + i * 2u, levels[i]);
        put16(db + 216 + i * 2u, levels[i]);
    }

    rsc[0] = 0x00020700u;
    rsc[0x0c / 4u] = (8u << 12) | (1u << 27);
    rsc[(RSC_TCS4 + 0x18u) / 4u] = 1;
}

static int contains(const uint8_t *hay, size_t n, const char *needle)
{
    const size_t m = strlen(needle);
    for (size_t i = 0; i + m <= n; ++i)
        if (!memcmp(hay + i, needle, m)) return 1;
    return 0;
}

static K60RouteAResult run(void)
{
    K60RouteAIo io = { K60_ROUTE_A_VERSION, sizeof io, fake_map, fake_unmap,
        fake_kick, fake_tick, NULL };
    K60RouteAResult out;
    const int rc = k60_adsp_route_a_acquire(&io, &out);
    CHECK(rc == 0);
    return out;
}

static void test_success(void)
{
    scenario = "route A acquires QMP and votes both rails through TCS4";
    ++cases;
    fixture();
    K60RouteAResult out = run();
    CHECK(out.qmp_open == 1u);
    CHECK(out.lcx_address == 0x100u && out.lmx_address == 0x200u);
    CHECK(out.lcx_index == 3u && out.lmx_index == 3u);
    CHECK(out.lcx_levels == 4u && out.lmx_levels == 4u);
    CHECK(maps == 4u && unmaps == 4u);
    CHECK(kicks >= 4u && ticks >= 2u);
    CHECK(map_phys[0] == K60_ROUTE_A_AOSS_PHYS && map_phys[1] == K60_ROUTE_A_IPCC_PHYS);
    CHECK(map_phys[2] == K60_CMD_DB_PHYS && map_phys[3] == K60_RSC_DRV2_PHYS);
    CHECK(map_flags[0] == 0x7u && map_flags[1] == 0x7u && map_flags[2] == 0x7u && map_flags[3] == 0x7u);
    CHECK(rsc[(RSC_TCS4 + 0x30u) / 4u] == 0x10108u);
    CHECK(rsc[(RSC_TCS4 + 0x34u) / 4u] == 0x200u);
    CHECK(rsc[(RSC_TCS4 + 0x38u) / 4u] == 3u);
    CHECK(contains((const uint8_t *)aoss, AOSS_BYTES,
        "{class: image, res: load_state, name: adsp, val: on}"));
}

static void test_bad_qmp(void)
{
    scenario = "a bad QMP descriptor is refused before cmd-db or RSC";
    ++cases;
    fixture();
    aoss[0] = 0;
    K60RouteAIo io = { K60_ROUTE_A_VERSION, sizeof io, fake_map, fake_unmap,
        fake_kick, fake_tick, NULL };
    K60RouteAResult out;
    CHECK(k60_adsp_route_a_acquire(&io, &out) != 0);
    CHECK(maps == 2u && unmaps == 2u);
}

static void test_missing_lmx(void)
{
    scenario = "a missing lmx.lvl is a failed acquisition, not a partial vote";
    ++cases;
    fixture();
    memset(db + 168, 0, 8);
    K60RouteAIo io = { K60_ROUTE_A_VERSION, sizeof io, fake_map, fake_unmap,
        fake_kick, fake_tick, NULL };
    K60RouteAResult out;
    CHECK(k60_adsp_route_a_acquire(&io, &out) != 0);
    CHECK(maps == 4u && unmaps == 4u);
}

static void test_tcs_conflict(void)
{
    scenario = "a TCS3 command with the same address blocks TCS4";
    ++cases;
    fixture();
    rsc[(RSC_TCS3 + 0x1cu) / 4u] = 1u;
    rsc[(RSC_TCS3 + 0x34u) / 4u] = 0x100u;
    K60RouteAIo io = { K60_ROUTE_A_VERSION, sizeof io, fake_map, fake_unmap,
        fake_kick, fake_tick, NULL };
    K60RouteAResult out;
    CHECK(k60_adsp_route_a_acquire(&io, &out) != 0);
}

static void test_tcs_unavailable(void)
{
    scenario = "a zero TCS4 status word is refused";
    ++cases;
    fixture();
    rsc[(RSC_TCS4 + 0x18u) / 4u] = 0;
    K60RouteAIo io = { K60_ROUTE_A_VERSION, sizeof io, fake_map, fake_unmap,
        fake_kick, fake_tick, NULL };
    K60RouteAResult out;
    CHECK(k60_adsp_route_a_acquire(&io, &out) != 0);
}

static void test_rsc_version_three(void)
{
    scenario = "a v3 RSC is refused before TCS4 is written";
    ++cases;
    fixture();
    rsc[0] = 0x00030700u;
    K60RouteAIo io = { K60_ROUTE_A_VERSION, sizeof io, fake_map, fake_unmap,
        fake_kick, fake_tick, NULL };
    K60RouteAResult out;
    CHECK(k60_adsp_route_a_acquire(&io, &out) != 0);
}

static void test_rsc_count_short(void)
{
    scenario = "an APSS RSC with fewer than eight TCS slots is refused";
    ++cases;
    fixture();
    rsc[0x0c / 4u] = (7u << 12) | (1u << 27);
    K60RouteAIo io = { K60_ROUTE_A_VERSION, sizeof io, fake_map, fake_unmap,
        fake_kick, fake_tick, NULL };
    K60RouteAResult out;
    CHECK(k60_adsp_route_a_acquire(&io, &out) != 0);
}

static void test_conflict_uses_command_capacity(void)
{
    scenario = "TCS3 conflict scan stops at ncpt, not at the TCS count";
    ++cases;
    fixture();
    rsc[0x0c / 4u] = (8u << 12) | (2u << 27);
    rsc[(RSC_TCS3 + 0x1c) / 4u] = 1u << 3;
    rsc[(RSC_TCS3 + 0x34u + 20u * 3u) / 4u] = 0x100u;
    K60RouteAIo io = { K60_ROUTE_A_VERSION, sizeof io, fake_map, fake_unmap,
        fake_kick, fake_tick, NULL };
    K60RouteAResult out;
    CHECK(k60_adsp_route_a_acquire(&io, &out) == 0);
}

int main(void)
{
    test_success();
    test_bad_qmp();
    test_missing_lmx();
    test_tcs_conflict();
    test_tcs_unavailable();
    test_rsc_version_three();
    test_rsc_count_short();
    test_conflict_uses_command_capacity();
    printf("TESTS OK route-a: %u scenarios\n", cases);
    return 0;
}