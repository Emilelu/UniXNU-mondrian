/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* K60 IPA GSI 3.0 command DMA owner, ported from PongModemIpaDma.h.
 *
 * The register offsets, command opcodes and staged IPA5.1 table geometry are
 * hardware facts taken from the Pong baseband command-DMA owner. All MMIO is
 * routed through K60IpaGsiCallbacks so the host test exercises this exact
 * sequence without mapping anything. The SMMU mapping and GSI IRQ are
 * deliberately left to the kernel glue; see K60IpaGsi.h.
 */

#include "K60IpaGsi.h"

#ifdef K60_HOST_TEST
#include <string.h>
#else
#include <sys/systm.h>
#endif

_Static_assert(K60_IPA_GSI_RING_BYTES == 0x100000u, "1 MiB ring block");
_Static_assert(K60_IPA_GSI_TABLE_BYTES == 0x8000u, "0x8000 table block");
_Static_assert(K60_IPA_GSI_TRE_BYTES * K60_IPA_GSI_TRE_COUNT == 0x1000u,
    "256 16-byte TREs fill one event page");
_Static_assert(K60_IPA_GSI_ENDPOINT_OFFSET == 0x1700u,
    "IPA endpoint 14 lives at 0x1000 + 14 * 0x80");
_Static_assert(K60_IPA_GSI_EVENT_OFFSET + K60_IPA_GSI_EVENT_BYTES <=
    K60_IPA_GSI_EVENT_SHADOW_OFFSET, "event ring precedes its shadow");
_Static_assert(K60_IPA_GSI_PAYLOAD_OFFSET >= K60_IPA_GSI_EVENT_SHADOW_OFFSET + 64u,
    "payload slots follow the event shadow");
_Static_assert(K60_IPA_GSI_HEADER_OFFSET + K60_IPA_GSI_HEADER_BYTES ==
    K60_IPA_GSI_TABLE_OFFSET, "headers precede filter/route tables");
_Static_assert(K60_IPA_GSI_TABLE_OFFSET + K60_IPA_GSI_TABLE_BLOCK_BYTES <=
    K60_IPA_GSI_RING_BYTES, "filter/route tables fit the ring block");

enum {
    K60IpaGsiCmdAllocate = 0,
    K60IpaGsiCmdStart = 1,
    K60IpaGsiCmdReset = 2,
};

typedef struct {
    uint16_t opcode;
    uint8_t bytes;
    uint8_t payload[K60_IPA_GSI_MAX_PAYLOAD];
} K60IpaGsiImmediate;

static uint32_t
k60_ipa_gsi_read_gsi(const K60IpaGsi *gsi, uint32_t offset)
{
    const K60IpaGsiCallbacks *io = &gsi->config.callbacks;

    return io->read_gsi(io->cookie, offset);
}

static void
k60_ipa_gsi_write_gsi(K60IpaGsi *gsi, uint32_t offset, uint32_t value)
{
    const K60IpaGsiCallbacks *io = &gsi->config.callbacks;

    io->write_gsi(io->cookie, offset, value);
}

static uint32_t
k60_ipa_gsi_read_reg(const K60IpaGsi *gsi, uint32_t offset)
{
    const K60IpaGsiCallbacks *io = &gsi->config.callbacks;

    return io->read_reg(io->cookie, offset);
}

static void
k60_ipa_gsi_write_reg(K60IpaGsi *gsi, uint32_t offset, uint32_t value)
{
    const K60IpaGsiCallbacks *io = &gsi->config.callbacks;

    io->write_reg(io->cookie, offset, value);
}

static void
k60_ipa_gsi_sync(K60IpaGsi *gsi, const void *address, size_t bytes,
    int direction)
{
    const K60IpaGsiCallbacks *io = &gsi->config.callbacks;

    if (io->sync != NULL) {
        io->sync(io->cookie, address, bytes, direction);
    }
}

static uint64_t
k60_ipa_gsi_now_ms(const K60IpaGsi *gsi)
{
    const K60IpaGsiCallbacks *io = &gsi->config.callbacks;

    return io->now_ms(io->cookie);
}

static void
k60_ipa_gsi_delay_us(const K60IpaGsi *gsi, uint32_t microseconds)
{
    const K60IpaGsiCallbacks *io = &gsi->config.callbacks;

    io->delay_us(io->cookie, microseconds);
}

static void
k60_ipa_gsi_le16(uint8_t *p, uint16_t value)
{
    p[0] = (uint8_t)value;
    p[1] = (uint8_t)(value >> 8);
}

static void
k60_ipa_gsi_le32(uint8_t *p, uint32_t value)
{
    k60_ipa_gsi_le16(p, (uint16_t)value);
    k60_ipa_gsi_le16(p + 2, (uint16_t)(value >> 16));
}

static void
k60_ipa_gsi_le64(uint8_t *p, uint64_t value)
{
    k60_ipa_gsi_le32(p, (uint32_t)value);
    k60_ipa_gsi_le32(p + 4, (uint32_t)(value >> 32));
}

static uint32_t
k60_ipa_gsi_from32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
        ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static uint64_t
k60_ipa_gsi_from64(const uint8_t *p)
{
    return (uint64_t)k60_ipa_gsi_from32(p) |
        ((uint64_t)k60_ipa_gsi_from32(p + 4) << 32);
}

static int
k60_ipa_gsi_fail(K60IpaGsi *gsi, int error)
{
    if (gsi->error == K60IpaOk) {
        gsi->error = error;
    }
    return error;
}

int
k60_ipa_gsi_init(K60IpaGsi *gsi, const K60IpaGsiConfig *config)
{
    if (gsi == NULL || config == NULL) {
        return K60IpaBadArgument;
    }
    if (config->callbacks.read_gsi == NULL || config->callbacks.write_gsi == NULL ||
        config->callbacks.read_reg == NULL || config->callbacks.write_reg == NULL ||
        config->callbacks.delay_us == NULL || config->callbacks.now_ms == NULL) {
        return K60IpaBadArgument;
    }
    if (config->ring == NULL || config->ring_size < K60_IPA_GSI_RING_BYTES ||
        config->tables == NULL || config->tables_size < K60_IPA_GSI_TABLE_BYTES) {
        return K60IpaBadArgument;
    }
    if (((uintptr_t)config->ring & (K60_IPA_GSI_RING_ALIGN - 1u)) != 0 ||
        ((uintptr_t)config->tables & (K60_IPA_GSI_PAGE_SIZE - 1u)) != 0) {
        return K60IpaBadArgument;
    }
    if (config->ring_iova == 0 || config->tables_iova == 0 ||
        (config->ring_iova & (K60_IPA_GSI_RING_ALIGN - 1u)) != 0 ||
        (config->tables_iova & (K60_IPA_GSI_PAGE_SIZE - 1u)) != 0) {
        return K60IpaBadArgument;
    }
    if (config->gsi_bytes < K60_GSI_EVENT_BASE + 4u) {
        return K60IpaBadArgument;
    }

    memset(gsi, 0, sizeof(*gsi));
    gsi->config = *config;
    if (gsi->config.gsi_bytes == 0) {
        gsi->config.gsi_bytes = K60_GSI_BYTES;
    }
    memset(gsi->config.ring, 0, K60_IPA_GSI_RING_BYTES);
    memset(gsi->config.tables, 0, K60_IPA_GSI_TABLE_BYTES);
    k60_ipa_gsi_sync(gsi, gsi->config.ring, K60_IPA_GSI_RING_BYTES,
        K60IpaGsiSyncClean);
    k60_ipa_gsi_sync(gsi, gsi->config.tables, K60_IPA_GSI_TABLE_BYTES,
        K60IpaGsiSyncClean);
    gsi->initialized = 1;
    return K60IpaOk;
}

int
k60_ipa_gsi_check_caps(K60IpaGsi *gsi, K60IpaGsiCaps *caps)
{
    uint32_t command_offset;
    uint32_t event_offset;

    if (gsi == NULL || caps == NULL || !gsi->initialized) {
        return K60IpaBadArgument;
    }
    if (gsi->config.gsi_bytes <= K60_GSI_STATUS_OFFSET) {
        return K60IpaBadArgument;
    }
    command_offset = K60_GSI_CHANNEL_BASE +
        K60_GSI_COMMAND_CHANNEL * K60_GSI_CHANNEL_STRIDE;
    event_offset = K60_GSI_EVENT_BASE + K60_GSI_EVENT0 * 0x80u;
    if (gsi->config.gsi_bytes <= command_offset + 4u ||
        gsi->config.gsi_bytes <= event_offset + 4u) {
        return K60IpaBadArgument;
    }

    caps->status = k60_ipa_gsi_read_gsi(gsi, K60_GSI_STATUS_OFFSET);
    caps->channels = k60_ipa_gsi_read_gsi(gsi, K60_GSI_CHANNELS_OFFSET);
    caps->events = k60_ipa_gsi_read_gsi(gsi, K60_GSI_EVENTS_OFFSET);
    caps->command_state =
        (k60_ipa_gsi_read_gsi(gsi, command_offset) >> 20) & 0xfu;
    caps->event_state =
        (k60_ipa_gsi_read_gsi(gsi, event_offset) >> 20) & 0xfu;

    if (caps->status == 0xffffffffu || (caps->status & 1u) != 0) {
        return K60IpaGsiBusy;
    }
    if (caps->channels <= K60_GSI_COMMAND_CHANNEL || caps->events == 0) {
        return K60IpaNotReady;
    }
    if (caps->command_state != 0 || caps->event_state != 0) {
        return K60IpaGsiBusy;
    }
    return K60IpaOk;
}

static int
k60_ipa_gsi_owned_events(K60IpaGsi *gsi, uint32_t events)
{
    uint32_t value;

    /* Native gsi_register_device arms the EE-local interrupt types before
     * ALLOCATE. A polled owner still has to arm and acknowledge its actual
     * sources; masking the GIC line is not a substitute for configuring the
     * GSI completion engine. Never clear foreign rings. */
    k60_ipa_gsi_write_gsi(gsi, 0x25220u, 1u);
    value = k60_ipa_gsi_read_gsi(gsi, 0x25088u);
    k60_ipa_gsi_write_gsi(gsi, 0x25088u, value | 0x4cu);
    value = k60_ipa_gsi_read_gsi(gsi, 0x25204u);
    k60_ipa_gsi_write_gsi(gsi, 0x25204u, value | 1u);
    value = k60_ipa_gsi_read_gsi(gsi, 0x25210u);
    k60_ipa_gsi_write_gsi(gsi, 0x25210u, value | 0xeu);
    value = k60_ipa_gsi_read_gsi(gsi, 0x250acu);
    k60_ipa_gsi_write_gsi(gsi, 0x250acu, value | events);

    if (k60_ipa_gsi_read_gsi(gsi, 0x25220u) != 1u ||
        (k60_ipa_gsi_read_gsi(gsi, 0x25088u) & 0x4cu) != 0x4cu ||
        (k60_ipa_gsi_read_gsi(gsi, 0x25204u) & 1u) == 0 ||
        (k60_ipa_gsi_read_gsi(gsi, 0x25210u) & 0xeu) != 0xeu ||
        (k60_ipa_gsi_read_gsi(gsi, 0x250acu) & events) != events) {
        return k60_ipa_gsi_fail(gsi, K60IpaGsiIoError);
    }
    return K60IpaOk;
}

static int
k60_ipa_gsi_command(K60IpaGsi *gsi, int event, uint32_t id, uint32_t opcode,
    uint32_t expected)
{
    uint32_t offset;
    uint32_t source;
    uint32_t mask;
    uint32_t clear;
    uint32_t bit;
    uint32_t old_mask;
    uint32_t old_type;
    uint32_t type;
    uint32_t actual = 0;
    uint64_t end;
    int done = 0;

    if (gsi == NULL || id >= 32u || opcode > 0xffu) {
        return K60IpaGsiInvalid;
    }
    offset = event != 0 ? K60_GSI_EVENT_BASE + id * 0x80u :
        K60_GSI_CHANNEL_BASE + id * K60_GSI_CHANNEL_STRIDE;
    if (opcode == K60IpaGsiCmdAllocate &&
        ((k60_ipa_gsi_read_gsi(gsi, offset) >> 20) & 0xfu) != 0) {
        return k60_ipa_gsi_fail(gsi, K60IpaGsiBusy);
    }
    /* Mirror the native command-control acknowledgement even though this
     * owner polls. Clear and mask only this allocated resource; stale
     * mailbox bits must not survive ALLOCATE -> START. */
    source = event != 0 ? 0x2509cu : 0x25090u;
    mask = event != 0 ? 0x250a0u : 0x25094u;
    clear = event != 0 ? 0x250a4u : 0x25098u;
    bit = 1u << id;
    old_mask = k60_ipa_gsi_read_gsi(gsi, mask);
    old_type = k60_ipa_gsi_read_gsi(gsi, 0x25088u);
    type = event != 0 ? 2u : 1u;
    k60_ipa_gsi_write_gsi(gsi, clear, bit);
    k60_ipa_gsi_write_gsi(gsi, mask, old_mask | bit);
    k60_ipa_gsi_write_gsi(gsi, 0x25088u, old_type | type);
    k60_ipa_gsi_write_gsi(gsi, event != 0 ? 0x25010u : 0x25008u,
        id | (opcode << 24));

    end = k60_ipa_gsi_now_ms(gsi) + 50u;
    do {
        actual = (k60_ipa_gsi_read_gsi(gsi, offset) >> 20) & 0xfu;
        if (actual == expected) {
            if (event == 0) {
                gsi->channel_state = actual;
            }
            done = 1;
            break;
        }
        if (actual == 15u) {
            break;
        }
        k60_ipa_gsi_delay_us(gsi, 10u);
    } while (k60_ipa_gsi_now_ms(gsi) < end);

    if ((k60_ipa_gsi_read_gsi(gsi, source) & bit) != 0) {
        k60_ipa_gsi_write_gsi(gsi, clear, bit);
    }
    k60_ipa_gsi_write_gsi(gsi, mask, old_mask);
    k60_ipa_gsi_write_gsi(gsi, 0x25088u, old_type);
    if (!done) {
        return k60_ipa_gsi_fail(gsi,
            actual == 15u ? K60IpaGsiIoError : K60IpaGsiTimeout);
    }
    return K60IpaOk;
}

static int
k60_ipa_gsi_submit_batch(K60IpaGsi *gsi, const K60IpaGsiImmediate *commands,
    uint32_t count)
{
    uint32_t i;

    if (gsi == NULL || commands == NULL) {
        return K60IpaBadArgument;
    }
    if (gsi->pending) {
        return K60IpaGsiBusy;
    }
    if (count == 0 || count > K60_IPA_GSI_MAX_BATCH) {
        return K60IpaBadArgument;
    }
    if (gsi->stage < 4u) {
        return K60IpaNotReady;
    }
    if (gsi->error != K60IpaOk) {
        return gsi->error;
    }

    for (i = 0; i < count; i++) {
        uint32_t index = (gsi->producer + i) & (K60_IPA_GSI_TRE_COUNT - 1u);
        uint8_t *payload = gsi->config.ring + K60_IPA_GSI_PAYLOAD_OFFSET +
            index * K60_IPA_GSI_PAYLOAD_BYTES;
        uint8_t *tre = gsi->config.ring + index * K60_IPA_GSI_TRE_BYTES;

        if (commands[i].bytes == 0 ||
            commands[i].bytes > K60_IPA_GSI_MAX_PAYLOAD) {
            return k60_ipa_gsi_fail(gsi, K60IpaGsiInvalid);
        }
        memset(payload, 0, K60_IPA_GSI_PAYLOAD_BYTES);
        memcpy(payload, commands[i].payload, commands[i].bytes);
        memset(tre, 0, K60_IPA_GSI_TRE_BYTES);
        k60_ipa_gsi_le64(tre, gsi->config.ring_iova +
            K60_IPA_GSI_PAYLOAD_OFFSET + index * K60_IPA_GSI_PAYLOAD_BYTES);
        k60_ipa_gsi_le16(tre + 8, commands[i].opcode);
        k60_ipa_gsi_le32(tre + 12, (3u << 16) |
            (i + 1u == count ? 0x600u : 1u));
        k60_ipa_gsi_sync(gsi, payload, K60_IPA_GSI_PAYLOAD_BYTES,
            K60IpaGsiSyncClean);
        k60_ipa_gsi_sync(gsi, tre, K60_IPA_GSI_TRE_BYTES,
            K60IpaGsiSyncClean);
    }
    gsi->last_tre = (gsi->producer + count - 1u) &
        (K60_IPA_GSI_TRE_COUNT - 1u);
    gsi->producer = (gsi->producer + count) &
        (K60_IPA_GSI_TRE_COUNT - 1u);
    gsi->pending = 1;
    gsi->deadline_ms = k60_ipa_gsi_now_ms(gsi) + 1000u;
    k60_ipa_gsi_write_gsi(gsi, 0x24000u + 12u * 8u + 4u, 0u);
    k60_ipa_gsi_write_gsi(gsi, 0x24000u + 12u * 8u,
        (uint32_t)(gsi->config.ring_iova +
            (uint64_t)gsi->producer * K60_IPA_GSI_TRE_BYTES));
    return K60IpaOk;
}

int
k60_ipa_gsi_submit(K60IpaGsi *gsi, uint32_t opcode, const void *payload,
    size_t payload_bytes)
{
    K60IpaGsiImmediate command;

    if (gsi == NULL || payload == NULL || payload_bytes == 0 ||
        payload_bytes > K60_IPA_GSI_MAX_PAYLOAD) {
        return K60IpaBadArgument;
    }
    memset(&command, 0, sizeof(command));
    command.opcode = (uint16_t)opcode;
    command.bytes = (uint8_t)payload_bytes;
    memcpy(command.payload, payload, payload_bytes);
    return k60_ipa_gsi_submit_batch(gsi, &command, 1u);
}

static int
k60_ipa_gsi_poll_owned_events(K60IpaGsi *gsi, uint32_t events)
{
    uint32_t global;
    uint32_t general;
    uint32_t pending;

    global = k60_ipa_gsi_read_gsi(gsi, 0x25200u);
    general = k60_ipa_gsi_read_gsi(gsi, 0x2520cu);
    if ((global & 1u) != 0 || (general & 0xeu) != 0) {
        gsi->failure_regs[5] = k60_ipa_gsi_read_gsi(gsi, 0x25240u);
        gsi->failure_regs[6] = global;
        return k60_ipa_gsi_fail(gsi, K60IpaGsiIoError);
    }
    pending = k60_ipa_gsi_read_gsi(gsi, 0x250a8u) & events;
    if (pending != 0) {
        k60_ipa_gsi_write_gsi(gsi, 0x250b0u, pending);
    }
    return K60IpaOk;
}

static int
k60_ipa_gsi_completion(K60IpaGsi *gsi)
{
    uint64_t pointer;
    uint64_t base;
    uint32_t index;
    uint32_t visited = 0;
    int done = 0;

    if (k60_ipa_gsi_poll_owned_events(gsi, 1u) != K60IpaOk) {
        return gsi->error;
    }
    /* The firmware writes the owned event shadow when it generates an
     * event. MMIO context snapshots alone are not enough for the GSI3.0
     * producer pointer. */
    k60_ipa_gsi_sync(gsi, gsi->config.ring + K60_IPA_GSI_EVENT_SHADOW_OFFSET,
        64u, K60IpaGsiSyncInvalidate);
    pointer = k60_ipa_gsi_from64(gsi->config.ring +
        K60_IPA_GSI_EVENT_SHADOW_OFFSET);
    base = gsi->config.ring_iova + K60_IPA_GSI_EVENT_OFFSET;
    if (pointer < base || pointer >= base + K60_IPA_GSI_EVENT_BYTES ||
        ((pointer - base) & (K60_IPA_GSI_TRE_BYTES - 1u)) != 0) {
        return k60_ipa_gsi_fail(gsi, K60IpaGsiIoError);
    }
    index = (uint32_t)((pointer - base) / K60_IPA_GSI_TRE_BYTES);
    while (gsi->event_read != index && visited++ < K60_IPA_GSI_TRE_COUNT) {
        const uint8_t *event = gsi->config.ring + K60_IPA_GSI_EVENT_OFFSET +
            gsi->event_read * K60_IPA_GSI_TRE_BYTES;
        uint64_t tre;
        uint32_t event_status;

        /* Event pages were cleaned before GSI took ownership; the CPU
         * never writes them after that handoff, so invalidate only. */
        k60_ipa_gsi_sync(gsi, event, K60_IPA_GSI_TRE_BYTES,
            K60IpaGsiSyncInvalidate);
        tre = k60_ipa_gsi_from64(event);
        event_status = event[11];
        gsi->last_event = event_status;
        if (event[15] != K60_GSI_COMMAND_CHANNEL ||
            tre < gsi->config.ring_iova ||
            tre >= gsi->config.ring_iova + K60_IPA_GSI_EVENT_BYTES ||
            ((tre - gsi->config.ring_iova) & (K60_IPA_GSI_TRE_BYTES - 1u)) != 0) {
            return k60_ipa_gsi_fail(gsi, K60IpaGsiIoError);
        }
        if (event_status != 1u && event_status != 2u) {
            return k60_ipa_gsi_fail(gsi, K60IpaGsiIoError);
        }
        if ((uint32_t)((tre - gsi->config.ring_iova) /
            K60_IPA_GSI_TRE_BYTES) == gsi->last_tre) {
            done = 1;
        }
        gsi->event_read = (gsi->event_read + 1u) &
            (K60_IPA_GSI_TRE_COUNT - 1u);
    }
    if (visited != 0) {
        k60_ipa_gsi_write_gsi(gsi, 0x24804u, 0u);
        k60_ipa_gsi_write_gsi(gsi, 0x24800u,
            (uint32_t)(base + ((gsi->event_read + K60_IPA_GSI_TRE_COUNT - 1u) &
            (K60_IPA_GSI_TRE_COUNT - 1u)) * K60_IPA_GSI_TRE_BYTES));
    }
    if (done) {
        gsi->pending = 0;
        gsi->completed_commands++;
        return K60IpaOk;
    }
    if (k60_ipa_gsi_now_ms(gsi) >= gsi->deadline_ms) {
        uint32_t channel = K60_GSI_CHANNEL_BASE +
            K60_GSI_COMMAND_CHANNEL * K60_GSI_CHANNEL_STRIDE;

        gsi->failure_regs[0] = k60_ipa_gsi_read_gsi(gsi, channel + 16u);
        gsi->failure_regs[1] = k60_ipa_gsi_read_gsi(gsi, channel + 24u);
        gsi->failure_regs[2] = k60_ipa_gsi_read_gsi(gsi, channel + 0x40u);
        gsi->failure_regs[3] = k60_ipa_gsi_read_gsi(gsi, channel + 0x44u);
        gsi->failure_regs[4] = k60_ipa_gsi_read_gsi(gsi, channel + 0x48u);
        gsi->failure_regs[7] = k60_ipa_gsi_read_gsi(gsi, 0x1c000u + 16u);
        return k60_ipa_gsi_fail(gsi, K60IpaGsiTimeout);
    }
    return K60IpaNotReady;
}

static int
k60_ipa_gsi_init_headers(K60IpaGsi *gsi)
{
    static const uint32_t guarded[] = {
        0x1288u, 0x1308u, 0x1388u, 0x1408u, 0x1488u, 0x1528u,
        0x15c8u, 0x1668u, 0x1708u, 0x1b40u, 0x3898u, 0x4ee8u,
    };
    K60IpaGsiImmediate header;
    uint32_t geometry;
    uint32_t i;
    uint32_t back;

    geometry = k60_ipa_gsi_read_reg(gsi, 0x40u);
    gsi->restricted = (geometry >> 16) * 8u;
    gsi->sram_bytes = (geometry & 0xffffu) * 8u;
    /* Cold boot, before INIT_DRIVER transfers SRAM ownership to MPSS.
     * Native ipa_setup_apps_pipes starts with HDR_INIT_LOCAL; there is no
     * invented HPS pipeline-clear wait before the tables exist. */
    if (gsi->sram_bytes < 0x5000u ||
        gsi->restricted > 0xffffu - 0x5000u) {
        return k60_ipa_gsi_fail(gsi, K60IpaGsiNoDevice);
    }
    /* Match _ipa_init_sram_v3 on IPA5.1: two 4-byte canaries immediately
     * before each shared table/header/context, modem memory and PDN region.
     * Do not write the uC shared area at 0x1000. */
    for (i = 0; i < sizeof(guarded) / sizeof(guarded[0]); i++) {
        for (back = 4u; back <= 8u; back += 4u) {
            uint32_t address = 0x10000u + gsi->restricted + guarded[i] - back;

            k60_ipa_gsi_write_reg(gsi, address, 0xdeadbeefu);
            if (k60_ipa_gsi_read_reg(gsi, address) != 0xdeadbeefu) {
                return k60_ipa_gsi_fail(gsi, K60IpaGsiIoError);
            }
        }
    }

    memset(gsi->config.ring + K60_IPA_GSI_HEADER_OFFSET, 0,
        K60_IPA_GSI_HEADER_BYTES);
    k60_ipa_gsi_sync(gsi, gsi->config.ring + K60_IPA_GSI_HEADER_OFFSET,
        K60_IPA_GSI_HEADER_BYTES, K60IpaGsiSyncClean);
    memset(&header, 0, sizeof(header));
    header.opcode = 9u;
    header.bytes = 16u;
    k60_ipa_gsi_le64(header.payload, gsi->config.ring_iova +
        K60_IPA_GSI_HEADER_OFFSET);
    k60_ipa_gsi_le32(header.payload + 8, 0x420u |
        ((gsi->restricted + 0x1708u) << 12));
    if (k60_ipa_gsi_submit_batch(gsi, &header, 1u) != K60IpaOk) {
        return gsi->error;
    }
    gsi->stage = 5u;
    return K60IpaOk;
}

static int
k60_ipa_gsi_init_contexts(K60IpaGsi *gsi)
{
    static const uint32_t offsets[] = { 0x1b40u, 0x3898u, 0x2868u, 0x4ee8u };
    static const uint32_t sizes[] = { 0xd20u, 0xd48u, 0xa48u, 0x118u };
    K60IpaGsiImmediate commands[4];
    uint32_t i;

    memset(commands, 0, sizeof(commands));
    for (i = 0; i < 4u; i++) {
        commands[i].opcode = 0x13u;
        commands[i].bytes = 16u;
        k60_ipa_gsi_le16(commands[i].payload + 2, (uint16_t)sizes[i]);
        k60_ipa_gsi_le16(commands[i].payload + 4,
            (uint16_t)(gsi->restricted + offsets[i]));
        k60_ipa_gsi_le64(commands[i].payload + 8, gsi->config.ring_iova +
            K60_IPA_GSI_HEADER_OFFSET);
    }
    if (k60_ipa_gsi_submit_batch(gsi, commands, 4u) != K60IpaOk) {
        return gsi->error;
    }
    gsi->stage = 7u;
    return K60IpaOk;
}

static int
k60_ipa_gsi_init_tables(K60IpaGsi *gsi)
{
    static const uint32_t opcodes[] = { 3u, 4u, 7u, 8u };
    static const uint32_t hash[] = { 0x1288u, 0x1388u, 0x1488u, 0x15c8u };
    static const uint32_t plain[] = { 0x1308u, 0x1408u, 0x1528u, 0x1668u };
    const uint64_t empty_table = (K60_IPA_GSI_TABLE_BLOCK_BYTES / 8u) * 128u + 1u;
    uint8_t *filter;
    uint8_t *route;
    uint64_t bitmap;
    K60IpaGsiImmediate commands[4];
    uint32_t i;

    /* NothingOSS ipahal_{rt,flt}_generate_empty_img uses local SRAM on
     * IPA5.1. Local encoding is (byte_offset / 8) * 128 + 1. */
    filter = gsi->config.ring + K60_IPA_GSI_TABLE_OFFSET + 0x100u;
    route = gsi->config.ring + K60_IPA_GSI_TABLE_OFFSET + 0x200u;
    memset(gsi->config.ring + K60_IPA_GSI_TABLE_OFFSET, 0,
        K60_IPA_GSI_TABLE_BLOCK_BYTES);
    bitmap = (1ull << 1) | (1ull << 2) | (1ull << 5) | (1ull << 6) |
        (1ull << 7) | (1ull << 10) | (1ull << 12) | (1ull << 15);
    k60_ipa_gsi_le64(filter, bitmap);
    for (i = 0; i < 8u; i++) {
        k60_ipa_gsi_le64(filter + 8u + i * 8u, empty_table);
    }
    for (i = 0; i < 19u; i++) {
        k60_ipa_gsi_le64(route + i * 8u, empty_table);
    }
    k60_ipa_gsi_sync(gsi, gsi->config.ring + K60_IPA_GSI_TABLE_OFFSET,
        K60_IPA_GSI_TABLE_BLOCK_BYTES, K60IpaGsiSyncClean);

    memset(commands, 0, sizeof(commands));
    for (i = 0; i < 4u; i++) {
        uint32_t size = i < 2u ? 72u : 152u;
        uint64_t address = gsi->config.ring_iova + K60_IPA_GSI_TABLE_OFFSET +
            (i < 2u ? 0x100u : 0x200u);
        uint64_t fields;

        commands[i].opcode = (uint16_t)opcodes[i];
        commands[i].bytes = 24u;
        k60_ipa_gsi_le64(commands[i].payload, address);
        fields = (uint64_t)size |
            ((uint64_t)(gsi->restricted + hash[i]) << 12) |
            ((uint64_t)size << 28) |
            ((uint64_t)(gsi->restricted + plain[i]) << 40);
        k60_ipa_gsi_le64(commands[i].payload + 8, fields);
        k60_ipa_gsi_le64(commands[i].payload + 16, address);
    }
    if (k60_ipa_gsi_submit_batch(gsi, commands, 4u) != K60IpaOk) {
        return gsi->error;
    }
    gsi->stage = 9u;
    return K60IpaOk;
}

int
k60_ipa_gsi_start(K60IpaGsi *gsi)
{
    K60IpaGsiCaps caps;
    uint64_t event_iova;
    uint64_t channel_iova;
    uint32_t endpoint;
    uint32_t channel;
    uint32_t value;
    uint32_t offset;
    int rc;

    if (gsi == NULL || !gsi->initialized) {
        return K60IpaBadArgument;
    }
    if (gsi->stage != 0u) {
        return K60IpaGsiBusy;
    }
    gsi->stage = 1u;
    gsi->error = K60IpaOk;

    rc = k60_ipa_gsi_check_caps(gsi, &caps);
    if (rc != K60IpaOk) {
        return k60_ipa_gsi_fail(gsi, rc);
    }
    gsi->caps = caps;
    gsi->channels = caps.channels;
    gsi->events = caps.events;
    gsi->event_state = caps.event_state;

    rc = k60_ipa_gsi_owned_events(gsi, 1u);
    if (rc != K60IpaOk) {
        return rc;
    }
    /* Event0 and command channel 12 are real EE0 allocations; context
     * fields follow GSI3.0, with ERINDEX in CNTXT1 rather than older CNTXT0. */
    rc = k60_ipa_gsi_command(gsi, 1, K60_GSI_EVENT0, K60IpaGsiCmdAllocate, 1u);
    if (rc != K60IpaOk) {
        return rc;
    }

    event_iova = gsi->config.ring_iova + K60_IPA_GSI_EVENT_OFFSET;
    k60_ipa_gsi_write_gsi(gsi, K60_GSI_EVENT_BASE,
        (16u << 24) | (1u << 7) | 2u);
    k60_ipa_gsi_write_gsi(gsi, K60_GSI_EVENT_BASE + 4u, 4096u);
    k60_ipa_gsi_write_gsi(gsi, K60_GSI_EVENT_BASE + 8u,
        (uint32_t)event_iova);
    k60_ipa_gsi_write_gsi(gsi, K60_GSI_EVENT_BASE + 12u,
        (uint32_t)(event_iova >> 32));
    for (offset = 32u; offset <= 52u; offset += 4u) {
        k60_ipa_gsi_write_gsi(gsi, K60_GSI_EVENT_BASE + offset, 0u);
    }
    /* Original ipa_dp.c: non-NAPI command ring count 1, 16 cycles of the
     * 32 kHz moderation clock. Zero/zero moderation is not the Pong policy. */
    k60_ipa_gsi_write_gsi(gsi, K60_GSI_EVENT_BASE + 32u, (1u << 16) | 16u);
    k60_ipa_gsi_le64(gsi->config.ring + K60_IPA_GSI_EVENT_SHADOW_OFFSET,
        event_iova);
    k60_ipa_gsi_sync(gsi, gsi->config.ring + K60_IPA_GSI_EVENT_SHADOW_OFFSET,
        64u, K60IpaGsiSyncClean);
    k60_ipa_gsi_write_gsi(gsi, K60_GSI_EVENT_BASE + 48u,
        (uint32_t)(gsi->config.ring_iova + K60_IPA_GSI_EVENT_SHADOW_OFFSET));
    k60_ipa_gsi_write_gsi(gsi, K60_GSI_EVENT_BASE + 52u,
        (uint32_t)((gsi->config.ring_iova + K60_IPA_GSI_EVENT_SHADOW_OFFSET) >> 32));
    value = k60_ipa_gsi_read_gsi(gsi, K60_GSI_EVENT_BASE + 4u);
    if (value != 4096u ||
        k60_ipa_gsi_read_gsi(gsi, K60_GSI_EVENT_BASE + 8u) !=
        (uint32_t)event_iova) {
        return k60_ipa_gsi_fail(gsi, K60IpaGsiIoError);
    }
    k60_ipa_gsi_write_gsi(gsi, 0x24804u, 0u);
    k60_ipa_gsi_write_gsi(gsi, 0x24800u,
        (uint32_t)(event_iova + K60_IPA_GSI_EVENT_BYTES -
        K60_IPA_GSI_TRE_BYTES));

    rc = k60_ipa_gsi_command(gsi, 0, K60_GSI_COMMAND_CHANNEL,
        K60IpaGsiCmdAllocate, 1u);
    if (rc != K60IpaOk) {
        return rc;
    }
    channel = K60_GSI_CHANNEL_BASE +
        K60_GSI_COMMAND_CHANNEL * K60_GSI_CHANNEL_STRIDE;
    channel_iova = gsi->config.ring_iova;
    k60_ipa_gsi_write_gsi(gsi, channel, (16u << 24) | (1u << 7) | 2u);
    k60_ipa_gsi_write_gsi(gsi, channel + 4u, 4096u);
    k60_ipa_gsi_write_gsi(gsi, channel + 8u, (uint32_t)channel_iova);
    k60_ipa_gsi_write_gsi(gsi, channel + 12u, (uint32_t)(channel_iova >> 32));
    /* GSI3.0 moved QOS from the older +0x5c to +0x48; +0x5c is scratch4.
     * bit24 makes the doorbell address-valued, and low_weight=15 matches
     * the command channel's native policy. */
    value = (1u << 24) | (1u << 10) | (24u << 16) | 15u;
    k60_ipa_gsi_write_gsi(gsi, channel + 0x48u, value);
    for (offset = 0x4cu; offset <= 0x70u; offset += 4u) {
        k60_ipa_gsi_write_gsi(gsi, channel + offset, 0u);
    }
    if (k60_ipa_gsi_read_gsi(gsi, channel + 0x48u) != value ||
        k60_ipa_gsi_read_gsi(gsi, channel + 4u) != 4096u ||
        k60_ipa_gsi_read_gsi(gsi, channel + 8u) != (uint32_t)channel_iova) {
        return k60_ipa_gsi_fail(gsi, K60IpaGsiIoError);
    }
    gsi->stage = 3u;

    /* Prepare the real IPA command endpoint 14 in DMA-only mode to LAN
     * consumer 16; no WAN/RX channel is started or published here. */
    endpoint = K60_IPA_GSI_ENDPOINT_OFFSET;
    k60_ipa_gsi_write_reg(gsi, endpoint + 8u, 0u);
    k60_ipa_gsi_write_reg(gsi, endpoint + 12u, 0u);
    k60_ipa_gsi_write_reg(gsi, endpoint + 16u, 0u);
    k60_ipa_gsi_write_reg(gsi, endpoint + 20u, 0u);
    k60_ipa_gsi_write_reg(gsi, endpoint + 32u, 3u | (16u << 4));
    k60_ipa_gsi_write_reg(gsi, endpoint + 36u, 0u);
    k60_ipa_gsi_write_reg(gsi, endpoint + 52u, 0u);
    k60_ipa_gsi_write_reg(gsi, endpoint + 56u, 0u);
    k60_ipa_gsi_write_reg(gsi, endpoint + 60u, 0u);
    k60_ipa_gsi_write_reg(gsi, endpoint + 64u, 0u);
    if (k60_ipa_gsi_read_reg(gsi, endpoint + 32u) != (3u | (16u << 4))) {
        return k60_ipa_gsi_fail(gsi, K60IpaGsiIoError);
    }
    k60_ipa_gsi_write_gsi(gsi, 0x25220u, 1u);
    rc = k60_ipa_gsi_command(gsi, 0, K60_GSI_COMMAND_CHANNEL,
        K60IpaGsiCmdStart, 2u);
    if (rc != K60IpaOk) {
        return rc;
    }
    gsi->stage = 4u;
    return k60_ipa_gsi_init_headers(gsi);
}

int
k60_ipa_gsi_poll(K60IpaGsi *gsi)
{
    uint32_t expected;
    int rc;

    if (gsi == NULL || !gsi->initialized) {
        return K60IpaBadArgument;
    }
    if (gsi->error != K60IpaOk) {
        return gsi->error;
    }
    if (gsi->stage < 4u || !gsi->pending) {
        return K60IpaOk;
    }
    rc = k60_ipa_gsi_completion(gsi);
    if (rc != K60IpaOk) {
        return rc;
    }
    if (gsi->stage == 5u) {
        gsi->stage = 6u;
        return k60_ipa_gsi_init_contexts(gsi);
    }
    if (gsi->stage == 7u) {
        gsi->stage = 8u;
        expected = gsi->restricted + 0x1b40u;
        k60_ipa_gsi_write_reg(gsi, 0x478u, expected);
        if (k60_ipa_gsi_read_reg(gsi, 0x478u) != expected) {
            return k60_ipa_gsi_fail(gsi, K60IpaGsiIoError);
        }
        return k60_ipa_gsi_init_tables(gsi);
    }
    if (gsi->stage == 9u) {
        gsi->stage = 10u;
    }
    return K60IpaOk;
}

int
k60_ipa_gsi_stop(K60IpaGsi *gsi)
{
    int rc = K60IpaOk;

    if (gsi == NULL || !gsi->initialized) {
        return K60IpaBadArgument;
    }
    if (gsi->stage >= 4u && gsi->error == K60IpaOk) {
        rc = k60_ipa_gsi_command(gsi, 0, K60_GSI_COMMAND_CHANNEL,
            K60IpaGsiCmdReset, 0u);
    }
    gsi->pending = 0;
    gsi->stage = 0u;
    gsi->producer = 0u;
    gsi->event_read = 0u;
    gsi->last_tre = 0u;
    gsi->last_event = 0u;
    gsi->deadline_ms = 0u;
    gsi->error = K60IpaOk;
    return rc;
}
