/* Host test for the K60 IPA GSI3.0 command DMA owner (M2).
 *
 * The test simulates the GSI and IPA register windows as byte arrays and
 * drives the same k60_ipa_gsi_* code the kernel uses. It checks the Pong
 * sequence: busy-EE0 refusal, owned event sources, ring context pointers,
 * one 16-byte TRE with a 32-byte payload slot, the command doorbell, both
 * accepted completion statuses (1 and 2), and stop/cleanup.
 */

#include <stdio.h>
#include <string.h>

#include "K60IpaGsi.h"

static uint8_t g_gsi[K60_GSI_BYTES] __attribute__((aligned(K60_IPA_GSI_PAGE_SIZE)));
static uint8_t g_regs[0x20000] __attribute__((aligned(K60_IPA_GSI_PAGE_SIZE)));
static uint8_t g_ring[K60_IPA_GSI_RING_BYTES] __attribute__((aligned(K60_IPA_GSI_RING_ALIGN)));
static uint8_t g_tables[K60_IPA_GSI_TABLE_BYTES] __attribute__((aligned(K60_IPA_GSI_PAGE_SIZE)));

typedef struct {
    uint64_t now_ms;
    unsigned delay_calls;
} Sim;

static uint32_t
get32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
        ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static uint64_t
get64(const uint8_t *p)
{
    return (uint64_t)get32(p) | ((uint64_t)get32(p + 4) << 32);
}

static uint16_t
get16(const uint8_t *p)
{
    return (uint16_t)((uint16_t)p[0] | ((uint16_t)p[1] << 8));
}

static uint32_t
sim_read32(uint8_t *base, size_t size, uint32_t offset)
{
    if ((size_t)offset + 4u > size) {
        return 0xffffffffu;
    }
    return *(volatile uint32_t *)(base + offset);
}

static void
sim_write32(uint8_t *base, size_t size, uint32_t offset, uint32_t value)
{
    if ((size_t)offset + 4u <= size) {
        *(volatile uint32_t *)(base + offset) = value;
    }
}

static void
sim_set_state(uint32_t offset, uint32_t opcode)
{
    uint32_t value = sim_read32(g_gsi, sizeof(g_gsi), offset);

    value &= ~(0xfu << 20);
    if (opcode == 0u) {
        value |= 1u << 20;
    } else if (opcode == 1u) {
        value |= 2u << 20;
    }
    sim_write32(g_gsi, sizeof(g_gsi), offset, value);
}

static uint32_t
sim_read_gsi(void *cookie, uint32_t offset)
{
    (void)cookie;
    return sim_read32(g_gsi, sizeof(g_gsi), offset);
}

static void
sim_write_gsi(void *cookie, uint32_t offset, uint32_t value)
{
    (void)cookie;
    sim_write32(g_gsi, sizeof(g_gsi), offset, value);
    if (offset == 0x25008u) {
        sim_set_state(K60_GSI_CHANNEL_BASE + (value & 0xffu) *
            K60_GSI_CHANNEL_STRIDE, (value >> 24) & 0xffu);
    } else if (offset == 0x25010u) {
        sim_set_state(K60_GSI_EVENT_BASE + (value & 0xffu) * 0x80u,
            (value >> 24) & 0xffu);
    }
}

static uint32_t
sim_read_reg(void *cookie, uint32_t offset)
{
    (void)cookie;
    return sim_read32(g_regs, sizeof(g_regs), offset);
}

static void
sim_write_reg(void *cookie, uint32_t offset, uint32_t value)
{
    (void)cookie;
    sim_write32(g_regs, sizeof(g_regs), offset, value);
}

static uint64_t
sim_now_ms(void *cookie)
{
    return ((Sim *)cookie)->now_ms;
}

static void
sim_delay_us(void *cookie, uint32_t microseconds)
{
    Sim *sim = cookie;

    sim->delay_calls++;
    if (microseconds >= 1000u) {
        sim->now_ms += microseconds / 1000u;
    } else if (microseconds != 0u) {
        sim->now_ms += 1u;
    }
}

static void
sim_sync(void *cookie, const void *address, size_t bytes, int direction)
{
    (void)cookie;
    (void)address;
    (void)bytes;
    (void)direction;
}

static void
sim_reset(Sim *sim)
{
    memset(g_gsi, 0, sizeof(g_gsi));
    memset(g_regs, 0, sizeof(g_regs));
    memset(g_ring, 0, sizeof(g_ring));
    memset(g_tables, 0, sizeof(g_tables));
    sim->now_ms = 1000u;
    sim->delay_calls = 0u;
    /* restricted = 0x100 * 8 = 0x800; SRAM = 0x0c00 * 8 = 0x6000. */
    sim_write32(g_regs, sizeof(g_regs), 0x40u, 0x01000c00u);
    sim_write32(g_gsi, sizeof(g_gsi), K60_GSI_CHANNELS_OFFSET, 64u);
    sim_write32(g_gsi, sizeof(g_gsi), K60_GSI_EVENTS_OFFSET, 16u);
}

static void
make_config(K60IpaGsiConfig *config, Sim *sim)
{
    memset(config, 0, sizeof(*config));
    config->callbacks.read_gsi = sim_read_gsi;
    config->callbacks.write_gsi = sim_write_gsi;
    config->callbacks.read_reg = sim_read_reg;
    config->callbacks.write_reg = sim_write_reg;
    config->callbacks.delay_us = sim_delay_us;
    config->callbacks.now_ms = sim_now_ms;
    config->callbacks.sync = sim_sync;
    config->callbacks.cookie = sim;
    config->ring = g_ring;
    config->ring_size = sizeof(g_ring);
    config->ring_iova = 0x20000000ull;
    config->tables = g_tables;
    config->tables_size = sizeof(g_tables);
    config->tables_iova = 0x20080000ull;
    config->gsi_bytes = K60_GSI_BYTES;
}

static void
sim_complete_event(K60IpaGsi *gsi, uint32_t status)
{
    uint8_t *event = g_ring + K60_IPA_GSI_EVENT_OFFSET +
        (gsi->event_read & (K60_IPA_GSI_TRE_COUNT - 1u)) *
        K60_IPA_GSI_TRE_BYTES;
    uint8_t *shadow = g_ring + K60_IPA_GSI_EVENT_SHADOW_OFFSET;
    uint64_t base = gsi->config.ring_iova + K60_IPA_GSI_EVENT_OFFSET;
    uint64_t tre = gsi->config.ring_iova +
        (uint64_t)gsi->last_tre * K60_IPA_GSI_TRE_BYTES;
    uint64_t pointer = base + (uint64_t)((gsi->event_read + 1u) &
        (K60_IPA_GSI_TRE_COUNT - 1u)) * K60_IPA_GSI_TRE_BYTES;
    unsigned i;

    memset(event, 0, K60_IPA_GSI_TRE_BYTES);
    for (i = 0; i < 8u; i++) {
        event[i] = (uint8_t)(tre >> (8u * i));
    }
    event[11] = (uint8_t)status;
    event[15] = (uint8_t)K60_GSI_COMMAND_CHANNEL;
    for (i = 0; i < 8u; i++) {
        shadow[i] = (uint8_t)(pointer >> (8u * i));
    }
}

static int
fail(const char *message)
{
    printf("FAIL %s\n", message);
    return 1;
}

int
main(void)
{
    K60IpaGsi gsi;
    K60IpaGsiConfig config;
    K60IpaGsiCaps caps;
    Sim sim;
    uint32_t channel;
    uint32_t doorbell;
    uint32_t index;
    uint32_t value;
    uint8_t payload[24];
    unsigned i;

    _Static_assert(K60_IPA_GSI_RING_BYTES == 0x100000u, "ring size");
    _Static_assert(K60_IPA_GSI_TABLE_BYTES == 0x8000u, "table size");
    _Static_assert(K60_IPA_GSI_ENDPOINT_OFFSET == 0x1700u, "endpoint offset");

    if (k60_ipa_gsi_init(NULL, NULL) != K60IpaBadArgument) {
        return fail("null init");
    }

    /* 1. A GSI EE0 already enabled by TZ or another owner must be refused. */
    sim_reset(&sim);
    make_config(&config, &sim);
    sim_write32(g_gsi, sizeof(g_gsi), K60_GSI_STATUS_OFFSET, 1u);
    if (k60_ipa_gsi_init(&gsi, &config) != K60IpaOk) {
        return fail("init busy case");
    }
    if (k60_ipa_gsi_start(&gsi) != K60IpaGsiBusy) {
        return fail("busy EE0 not refused");
    }
    if (gsi.error != K60IpaGsiBusy) {
        return fail("busy EE0 error code");
    }

    /* 2. Normal start: ownership, ring contexts, endpoint, first HDR_INIT. */
    sim_reset(&sim);
    make_config(&config, &sim);
    if (k60_ipa_gsi_init(&gsi, &config) != K60IpaOk) {
        return fail("init");
    }
    if (k60_ipa_gsi_check_caps(&gsi, &caps) != K60IpaOk ||
        caps.channels != 64u || caps.events != 16u) {
        return fail("capability read");
    }
    if (k60_ipa_gsi_start(&gsi) != K60IpaOk) {
        return fail("start");
    }
    if (gsi.stage != 5u || !gsi.pending) {
        return fail("start stage");
    }
    value = sim_read32(g_gsi, sizeof(g_gsi), 0x25220u);
    if (value != 1u ||
        (sim_read32(g_gsi, sizeof(g_gsi), 0x25088u) & 0x4cu) != 0x4cu ||
        (sim_read32(g_gsi, sizeof(g_gsi), 0x25204u) & 1u) == 0 ||
        (sim_read32(g_gsi, sizeof(g_gsi), 0x25210u) & 0xeu) != 0xeu ||
        (sim_read32(g_gsi, sizeof(g_gsi), 0x250acu) & 1u) == 0) {
        return fail("owned event sources");
    }
    if (sim_read32(g_gsi, sizeof(g_gsi), K60_GSI_EVENT_BASE) != 0x10000082u ||
        sim_read32(g_gsi, sizeof(g_gsi), K60_GSI_EVENT_BASE + 4u) != 4096u ||
        get32(g_gsi + K60_GSI_EVENT_BASE + 8u) != 0x20010000u ||
        get32(g_gsi + K60_GSI_EVENT_BASE + 48u) != 0x20018000u ||
        sim_read32(g_gsi, sizeof(g_gsi), 0x24800u) != 0x20010ff0u) {
        return fail("event ring context");
    }
    channel = K60_GSI_CHANNEL_BASE +
        K60_GSI_COMMAND_CHANNEL * K60_GSI_CHANNEL_STRIDE;
    value = sim_read32(g_gsi, sizeof(g_gsi), channel);
    if ((value & ~0x00f00000u) != 0x10000082u ||
        ((value >> 20) & 0xfu) != 2u ||
        sim_read32(g_gsi, sizeof(g_gsi), channel + 4u) != 4096u ||
        get32(g_gsi + channel + 8u) != 0x20000000u ||
        sim_read32(g_gsi, sizeof(g_gsi), channel + 0x48u) != 0x0118040fu) {
        return fail("command ring context");
    }
    if (sim_read32(g_regs, sizeof(g_regs), K60_IPA_GSI_ENDPOINT_OFFSET + 32u) != 0x103u) {
        return fail("endpoint mode");
    }
    if (get64(g_ring) != 0x20020000ull || get16(g_ring + 8) != 9u ||
        get32(g_ring + 12) != 0x00030600u ||
        get64(g_ring + K60_IPA_GSI_PAYLOAD_OFFSET) != 0x20030000ull ||
        get32(g_ring + K60_IPA_GSI_PAYLOAD_OFFSET + 8u) != 0x01f08420u) {
        return fail("header TRE/payload");
    }

    /* 3. Complete HDR_INIT with status 1; contexts are then submitted. */
    sim_complete_event(&gsi, 1u);
    if (k60_ipa_gsi_poll(&gsi) != K60IpaOk || gsi.stage != 7u || !gsi.pending) {
        return fail("header completion");
    }
    if (get64(g_ring + 1u * K60_IPA_GSI_TRE_BYTES) != 0x20020020ull ||
        get16(g_ring + 1u * K60_IPA_GSI_TRE_BYTES + 8u) != 0x13u ||
        get16(g_ring + K60_IPA_GSI_PAYLOAD_OFFSET + 32u + 2u) != 0x0d20u ||
        get16(g_ring + K60_IPA_GSI_PAYLOAD_OFFSET + 32u + 4u) != 0x2340u) {
        return fail("context command encoding");
    }

    /* 4. Complete contexts with status 2; tables are then submitted. */
    sim_complete_event(&gsi, 2u);
    if (k60_ipa_gsi_poll(&gsi) != K60IpaOk || gsi.stage != 9u || !gsi.pending) {
        return fail("context completion");
    }
    if (sim_read32(g_regs, sizeof(g_regs), 0x478u) != 0x2340u) {
        return fail("local context readback");
    }
    if (get64(g_ring + K60_IPA_GSI_TABLE_OFFSET + 0x100u) != 0x94e6ull ||
        get64(g_ring + K60_IPA_GSI_TABLE_OFFSET + 0x108u) != 0x10001ull ||
        get64(g_ring + K60_IPA_GSI_TABLE_OFFSET + 0x200u) != 0x10001ull) {
        return fail("filter/route tables");
    }

    /* 5. Complete tables; init reaches stage 10. */
    sim_complete_event(&gsi, 1u);
    if (k60_ipa_gsi_poll(&gsi) != K60IpaOk || gsi.stage != 10u || gsi.pending) {
        return fail("table completion");
    }

    /* 6. Public submit: one TRE of 16 bytes and one 32-byte payload slot. */
    for (i = 0; i < sizeof(payload); i++) {
        payload[i] = (uint8_t)(0x30u + i);
    }
    if (k60_ipa_gsi_submit(&gsi, 0x34u, payload, sizeof(payload)) != K60IpaOk) {
        return fail("submit");
    }
    index = gsi.last_tre;
    if (get64(g_ring + index * K60_IPA_GSI_TRE_BYTES) !=
        (0x20000000ull + K60_IPA_GSI_PAYLOAD_OFFSET +
        (uint64_t)index * K60_IPA_GSI_PAYLOAD_BYTES) ||
        get16(g_ring + index * K60_IPA_GSI_TRE_BYTES + 8u) != 0x34u ||
        get32(g_ring + index * K60_IPA_GSI_TRE_BYTES + 12u) != 0x00030600u) {
        return fail("submit TRE");
    }
    if (memcmp(g_ring + K60_IPA_GSI_PAYLOAD_OFFSET +
            (uint64_t)index * K60_IPA_GSI_PAYLOAD_BYTES, payload,
            sizeof(payload)) != 0) {
        return fail("submit payload");
    }
    for (i = 24u; i < K60_IPA_GSI_PAYLOAD_BYTES; i++) {
        if (g_ring[K60_IPA_GSI_PAYLOAD_OFFSET +
            (uint64_t)index * K60_IPA_GSI_PAYLOAD_BYTES + i] != 0u) {
            return fail("payload padding");
        }
    }
    doorbell = sim_read32(g_gsi, sizeof(g_gsi), 0x24000u + 12u * 8u);
    if (doorbell != (uint32_t)(0x20000000ull +
        (uint64_t)gsi.producer * K60_IPA_GSI_TRE_BYTES)) {
        return fail("command doorbell");
    }

    /* 7. Status 2 is also a valid command completion. */
    sim_complete_event(&gsi, 2u);
    if (k60_ipa_gsi_poll(&gsi) != K60IpaOk || gsi.pending ||
        gsi.completed_commands != 4u) {
        return fail("status 2 completion");
    }

    /* 8. Stop resets command channel 12 and clears local state. */
    if (k60_ipa_gsi_stop(&gsi) != K60IpaOk) {
        return fail("stop");
    }
    if (gsi.stage != 0u || gsi.pending || gsi.error != K60IpaOk ||
        ((sim_read32(g_gsi, sizeof(g_gsi), channel) >> 20) & 0xfu) != 0u) {
        return fail("stop cleanup");
    }
    if (k60_ipa_gsi_stop(&gsi) != K60IpaOk) {
        return fail("stop idempotent");
    }

    printf("K60 IPA GSI DMA PASS\n");
    return 0;
}
