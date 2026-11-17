/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* K60 IPA data path M0 skeleton plus M1 firmware staging.
 *
 * M0 carries the register-map constants and the version decoder so later
 * stages cannot invent a different base address. M1 validates a monolithic
 * ipa_fws image, clears the 64 KiB ipa_fw_region, copies its load segments to
 * their p_paddr offsets and builds the metadata block at the last 8 KiB.
 * k60_ipa_firmware_start() then performs the PAS 15 init/mem-setup/auth-reset
 * sequence and reads the version registers; k60_ipa_probe_from_handoff()
 * supplies the image from IPA/ipa_fws.mbn in the payload FAT.
 */

#include "K60Ipa.h"
#include "K60ModemPas.h"

#ifdef K60_HOST_TEST
#include <stdio.h>
#include <string.h>
#else
#include <pexpert/pexpert.h>
#include <sys/systm.h>
#include "K60Fat.h" /* the kernel copy is pong_fat.h; the host build skips it */
#include "K60PmicRail.h" /* the kernel copy is pong_pmic_rail.h */

/* osfmk/arm/machine_routines.h:703; declared here keeps the include path out
 * of the leaky kernel header set (same choice as K60ModemBoot.c). */
extern vm_offset_t ml_io_map_unmappable(vm_offset_t phys, vm_size_t size,
    uint32_t flags);
extern void delay(int microseconds);
#endif

static int
k60_ipa_blob_read(void *context, uint64_t offset, void *to, size_t length)
{
    const uint8_t *blob = context;

    memcpy(to, blob + offset, length);
    return 0;
}

_Static_assert(K60_IPA_CFG_BASE == 0x03f40000u,
    "IPA register block must be wrapper 0x3e00000 + cfg offset 0x140000");
_Static_assert(K60_GSI_BASE == 0x03e04000u,
    "GSI view must match the live DT gsi-base");
_Static_assert(K60_IPA_VERSION_ADDR == 0x03f40028u,
    "IPA_VERSION must be the IPA register block plus 0x28");
_Static_assert(K60_IPA_IRQ == 654u && K60_GSI_IRQ == 432u,
    "IPA/GSI GIC interrupts must match the live DT");
_Static_assert(K60_IPA_PAS_ID == 15u,
    "IPA firmware uses PAS id 15 on this board");
_Static_assert(K60_IPA_METADATA_BASE + K60_IPA_METADATA_BYTES ==
    K60_IPA_FW_REGION_BASE + K60_IPA_FW_REGION_BYTES,
    "IPA metadata must be the last 8 KiB of the 64 KiB firmware region");

const char k60_ipa_marker[] = "K60IPA M1 staging linked";

K60IpaVersion
k60_ipa_decode_comp_hw_version(uint32_t raw)
{
    K60IpaVersion version;

    version.raw = raw;
    version.major = (raw & 0xf0000000u) >> 28;
    version.minor = (raw & 0x0fff0000u) >> 16;
    version.step = raw & 0x0000ffffu;
    return version;
}

int
k60_ipa_firmware_check(const void *blob, uint64_t size, K60IpaFirmwarePlan *plan)
{
    K60MdtImage image;
    uint32_t load = 0;
    int rc;

    if (!blob || !plan) {
        return K60IpaBadArgument;
    }
    rc = k60_mdt_parse(&image, size, k60_ipa_blob_read, (void *)blob);
    if (rc != K60MdtOk) {
        return K60IpaFirmwareBadImage;
    }
    for (uint32_t i = 0; i < image.count; i++) {
        if (image.segment[i].load) {
            load++;
        }
    }
    plan->span = k60_mdt_span(&image);
    plan->metadata = k60_mdt_metadata_size(&image);
    plan->load_segments = load;
    plan->relocatable = image.relocatable;
    if (image.elf64 || !image.relocatable || image.min_address != 0 ||
        plan->span > K60_IPA_FW_REGION_BYTES ||
        plan->metadata > K60_IPA_METADATA_BYTES) {
        return K60IpaFirmwareLayout;
    }
    return K60IpaOk;
}

int
k60_ipa_firmware_stage(const void *blob, uint64_t size, void *region,
    uint64_t region_size, void *metadata, uint64_t metadata_size,
    K60IpaFirmwarePlan *plan)
{
    K60MdtImage image;
    K60IpaFirmwarePlan local;
    int rc;

    if (!blob || !region || !metadata) {
        return K60IpaBadArgument;
    }
    rc = k60_ipa_firmware_check(blob, size, &local);
    if (rc != K60IpaOk) {
        return rc;
    }
    if (region_size < local.span) {
        return K60IpaFirmwareTooLarge;
    }
    if (metadata_size < local.metadata) {
        return K60IpaFirmwareTooLarge;
    }
    rc = k60_mdt_parse(&image, size, k60_ipa_blob_read, (void *)blob);
    if (rc != K60MdtOk) {
        return K60IpaFirmwareBadImage;
    }
    memset(region, 0, (size_t)region_size);
    for (uint32_t i = 0; i < image.count; i++) {
        const K60MdtSegment *s = &image.segment[i];
        uint64_t offset;

        if (!s->load) {
            continue;
        }
        rc = k60_mdt_place(&image, i, K60_IPA_FW_REGION_BASE, region_size,
            &offset);
        if (rc != K60MdtOk) {
            return K60IpaFirmwareLayout;
        }
        memcpy((uint8_t *)region + offset,
            (const uint8_t *)blob + s->file_offset, (size_t)s->file_size);
        if (s->memory_size > s->file_size) {
            memset((uint8_t *)region + offset + s->file_size, 0,
                (size_t)(s->memory_size - s->file_size));
        }
    }
    rc = k60_mdt_metadata(&image, k60_ipa_blob_read, (void *)blob,
        metadata, metadata_size);
    if (rc != K60MdtOk) {
        return K60IpaFirmwareLayout;
    }
    if (plan) {
        *plan = local;
    }
    return K60IpaOk;
}

static uint32_t
k60_ipa_reg_read(const void *registers, size_t at)
{
    return *(const volatile uint32_t *)((const uint8_t *)registers + at);
}

static void
k60_ipa_reg_write(void *registers, size_t at, uint32_t value)
{
    *(volatile uint32_t *)((uint8_t *)registers + at) = value;
#ifndef K60_HOST_TEST
    __asm__ volatile("dsb sy" ::: "memory");
#endif
}

/* Pong's ipaResourcesPrepare sequence, kept as pure register access so both
 * the kernel and the host test exercise the same field encodings. */
int
k60_ipa_resources_prepare(void *registers, size_t bytes)
{
    static const uint8_t src[5][6][2] = {
        {{7, 12}, {0, 0}, {0, 0}, {0, 0}, {1, 63}, {0, 63}},
        {{21, 21}, {0, 0}, {0, 0}, {0, 0}, {10, 10}, {0, 0}},
        {{33, 33}, {0, 0}, {0, 0}, {0, 0}, {20, 20}, {0, 0}},
        {{0, 63}, {0, 0}, {0, 63}, {0, 63}, {1, 63}, {0, 63}},
        {{38, 38}, {0, 0}, {0, 0}, {0, 0}, {16, 16}, {0, 0}}
    };
    static const uint8_t dst[3][8][2] = {
        {{6, 6}, {5, 5}, {0, 0}, {0, 0}, {0, 0}, {0, 0}, {39, 39}, {0, 0}},
        {{0, 3}, {0, 3}, {0, 0}, {0, 0}, {0, 0}, {0, 0}, {0, 0}, {0, 0}},
        {{0, 63}, {0, 63}, {0, 0}, {0, 0}, {0, 0}, {0, 0}, {0, 0}, {0, 0}}
    };
    uint32_t comp, qsb_writes, qsb_reads, timestamp, gran, divider;
    int ready = 1;

    if (registers == NULL || bytes < 0x6a8u) {
        return K60IpaBadArgument;
    }
    if (k60_ipa_reg_read(registers, K60_IPA_VERSION_REG) == 0 ||
        k60_ipa_reg_read(registers, K60_IPA_VERSION_REG) == 0xffffffffu) {
        return K60IpaNotReady;
    }
    comp = k60_ipa_reg_read(registers, 0x2cu) | 0x180u;
    k60_ipa_reg_write(registers, 0x2cu, comp);
    qsb_writes = k60_ipa_reg_read(registers, 0x54u) & ~0xffu;
    qsb_reads = k60_ipa_reg_read(registers, 0x58u) & ~0xffff00ffu;
    k60_ipa_reg_write(registers, 0x54u, qsb_writes);
    k60_ipa_reg_write(registers, 0x58u, qsb_reads);
    timestamp = (k60_ipa_reg_read(registers, 0x4acu) & ~0x1f1f9fu) |
        14u | 0x80u | (14u << 8) | (24u << 16);
    k60_ipa_reg_write(registers, 0x4acu, timestamp);
    gran = (k60_ipa_reg_read(registers, 0x4b4u) & ~0xfffu) |
        3u | (4u << 3) | (5u << 6) | (5u << 9);
    k60_ipa_reg_write(registers, 0x4b4u, gran);
    divider = k60_ipa_reg_read(registers, 0x4b0u);
    if ((divider & (1u << 31)) != 0) {
        k60_ipa_reg_write(registers, 0x4b0u, divider & ~(1u << 31));
    }
    k60_ipa_reg_write(registers, 0x4b0u, divider | (1u << 31));
    if (k60_ipa_reg_read(registers, 0x2cu) != comp ||
        k60_ipa_reg_read(registers, 0x54u) != qsb_writes ||
        k60_ipa_reg_read(registers, 0x58u) != qsb_reads ||
        k60_ipa_reg_read(registers, 0x4acu) != timestamp ||
        k60_ipa_reg_read(registers, 0x4b4u) != gran ||
        (k60_ipa_reg_read(registers, 0x4b0u) & (1u << 31)) == 0) {
        return K60IpaNotReady;
    }
    for (unsigned direction = 0; direction < 2 && ready; direction++) {
        const unsigned types = direction ? 3u : 5u;
        const unsigned pairs = direction ? 4u : 3u;
        for (unsigned t = 0; t < types && ready; t++) {
            for (unsigned pair = 0; pair < pairs; pair++) {
                const uint8_t *x = direction ? dst[t][pair * 2] : src[t][pair * 2];
                const uint8_t *y = direction ? dst[t][pair * 2 + 1] : src[t][pair * 2 + 1];
                const size_t offset = (direction ? 0x600u : 0x500u) +
                    t * 0x20u + pair * 4u;
                const uint32_t fields = (uint32_t)x[0] | ((uint32_t)x[1] << 8) |
                    ((uint32_t)y[0] << 16) | ((uint32_t)y[1] << 24);
                const uint32_t value = (k60_ipa_reg_read(registers, offset) &
                    ~0x3f3f3f3fu) | fields;
                k60_ipa_reg_write(registers, offset, value);
                if (k60_ipa_reg_read(registers, offset) != value) {
                    ready = 0;
                    break;
                }
            }
        }
    }
    if (ready) {
        const uint32_t config = (k60_ipa_reg_read(registers, 0x6a0u) &
            ~0x3f1ff171u) | 0x41u;
        k60_ipa_reg_write(registers, 0x6a0u, config);
        ready = k60_ipa_reg_read(registers, 0x6a0u) == config;
        if (ready) {
            const uint32_t ext = (k60_ipa_reg_read(registers, 0x6a4u) &
                ~0x70u) | 0x10u;
            k60_ipa_reg_write(registers, 0x6a4u, ext);
            ready = k60_ipa_reg_read(registers, 0x6a4u) == ext;
        }
    }
    return ready ? K60IpaOk : K60IpaNotReady;
}

static uint32_t
k60_ipa_gsi_word(void *gsi, size_t at)
{
    return *(const volatile uint32_t *)((const uint8_t *)gsi + at);
}

int
k60_ipa_gsi_check(void *gsi, size_t bytes, K60IpaGsiCaps *caps)
{
    size_t command = K60_GSI_CHANNEL_BASE +
        K60_GSI_COMMAND_CHANNEL * K60_GSI_CHANNEL_STRIDE;
    size_t event = K60_GSI_EVENT_BASE + K60_GSI_EVENT0 * 0x80u;

    if (gsi == NULL || caps == NULL || bytes <= K60_GSI_STATUS_OFFSET) {
        return K60IpaBadArgument;
    }
    if (bytes <= command + 4u || bytes <= event + 4u) {
        return K60IpaBadArgument;
    }
    caps->status = k60_ipa_gsi_word(gsi, K60_GSI_STATUS_OFFSET);
    caps->channels = k60_ipa_gsi_word(gsi, K60_GSI_CHANNELS_OFFSET);
    caps->events = k60_ipa_gsi_word(gsi, K60_GSI_EVENTS_OFFSET);
    caps->command_state = (k60_ipa_gsi_word(gsi, command) >> 20) & 0xfu;
    caps->event_state = (k60_ipa_gsi_word(gsi, event) >> 20) & 0xfu;
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

#ifndef K60_HOST_TEST
static int
k60_ipa_scm_call(uint32_t fn, uint32_t arginfo, uint64_t a, uint64_t b,
    uint64_t c, uint64_t *rx0, uint64_t *rx1)
{
    register uint64_t x0 __asm__("x0") = fn;
    register uint64_t x1 __asm__("x1") = arginfo;
    register uint64_t x2 __asm__("x2") = a;
    register uint64_t x3 __asm__("x3") = b;
    register uint64_t x4 __asm__("x4") = c;
    register uint64_t x5 __asm__("x5") = 0;
    register uint64_t x6 __asm__("x6") = 0;
    register uint64_t x7 __asm__("x7") = 0;

    __asm__ volatile("smc #0"
        : "+r"(x0), "+r"(x1), "+r"(x2), "+r"(x3)
        : "r"(x4), "r"(x5), "r"(x6), "r"(x7)
        : "memory");

    *rx0 = x0;
    *rx1 = x1;
    return k60_modem_scm_ok(x0, x1) ? K60IpaOk : K60IpaPasDenied;
}

static int
k60_ipa_pas_call(uint32_t cmd, uint32_t arginfo, uint64_t a, uint64_t b,
    uint64_t c)
{
    uint64_t x0 = 0, x1 = 0;
    int rc = k60_ipa_scm_call(k60_modem_scm_fn(K60M_SCM_SVC_PIL, cmd),
        arginfo, a, b, c, &x0, &x1);

    if (rc != K60IpaOk) {
        printf("K60IPA scm cmd=%#x rc=%d x0=%#llx x1=%#llx\n", cmd, rc,
            (unsigned long long)x0, (unsigned long long)x1);
    }
    return rc;
}

#define K60_IPA_CMD_DB_PHYS   0x80860000u
#define K60_IPA_CMD_DB_BYTES  0x00020000u
#define K60_IPA_RSC_DRV2_PHYS 0x17a20000u
#define K60_IPA_RSC_BYTES     0x00010000u
#define K60_IPA_RSC_TCS_BASE  0x00000d00u
#define K60_IPA_RSC_TCS_STRIDE 672u
#define K60_IPA_RSC_TCS4      (K60_IPA_RSC_TCS_BASE + 4u * K60_IPA_RSC_TCS_STRIDE)
#define K60_IPA_RSC_TCS3      (K60_IPA_RSC_TCS_BASE + 3u * K60_IPA_RSC_TCS_STRIDE)
#define K60_IPA_RSC_MSGID     0x00010108u
#define K60_IPA_RSC_IRQ_DONE  (1u << 4)
#define K60_IPA_RSC_CMD_DONE  0x00010100u
#define K60_IPA_RSC_CTRL_TCS  (1u << 4)

static uint16_t
k60_ipa_le16(const uint8_t *p)
{
    return (uint16_t)(p[0] | (uint16_t)p[1] << 8);
}

static uint32_t
k60_ipa_le32(const uint8_t *p)
{
    return (uint32_t)k60_ipa_le16(p) | (uint32_t)k60_ipa_le16(p + 2) << 16;
}

static uint32_t
k60_ipa_rd32(const volatile uint8_t *base, size_t at)
{
    return *(const volatile uint32_t *)(base + at);
}

static void
k60_ipa_wr32(volatile uint8_t *base, size_t at, uint32_t value)
{
    *(volatile uint32_t *)(base + at) = value;
    __asm__ volatile("dsb oshst" ::: "memory");
}

static void
k60_ipa_fence(void)
{
    __asm__ volatile("dsb sy" ::: "memory");
}

static void
k60_ipa_spin(void)
{
    __asm__ volatile("yield" ::: "memory");
}

static int
k60_ipa_wait_word(const volatile uint8_t *base, size_t at, uint32_t mask,
    uint32_t value, unsigned tries)
{
    for (unsigned i = 0; i < tries; i++) {
        if ((k60_ipa_rd32(base, at) & mask) == value) {
            return 0;
        }
        delay(10);
    }
    return -1;
}

/* Find the IP0 BCM record in the AOP command DB and read its eight-byte aux
 * record. The first aux word is kHz per vote unit; Pong's ipaClockPrepare and
 * NothingOSS clk-rpmh use the same record, not an ARC level table. */
static int
k60_ipa_find_ip0(const uint8_t *db, uint32_t *address, uint32_t *unit_khz)
{
    static const char id[8] = { 'I', 'P', '0', 0, 0, 0, 0, 0 };

    if (db == NULL || address == NULL || unit_khz == NULL) {
        return -1;
    }
    if (k60_ipa_le32(db + 4) != 0x0c0330dbu) {
        return -1;
    }
    for (unsigned s = 0; s < 8; s++) {
        const uint8_t *slave = db + 8 + 16 * s;
        uint32_t head, data, count;

        if (k60_ipa_le16(slave) == 0) {
            break;
        }
        head = 144u + k60_ipa_le16(slave + 2);
        data = 144u + k60_ipa_le16(slave + 4);
        count = k60_ipa_le16(slave + 6);
        if (head > K60_IPA_CMD_DB_BYTES ||
            count > (K60_IPA_CMD_DB_BYTES - head) / 24u) {
            break;
        }
        for (uint32_t n = 0; n < count; n++) {
            const uint8_t *entry = db + head + 24 * n;
            uint32_t bytes, at, i;
            int same = 1;

            for (i = 0; i < 8; i++) {
                if (entry[i] != (uint8_t)id[i]) {
                    same = 0;
                    break;
                }
            }
            if (!same) {
                continue;
            }
            bytes = k60_ipa_le16(entry + 20);
            at = data + k60_ipa_le16(entry + 22);
            if (bytes < 4 || at > K60_IPA_CMD_DB_BYTES ||
                bytes > K60_IPA_CMD_DB_BYTES - at) {
                return -1;
            }
            *address = k60_ipa_le32(entry + 16);
            *unit_khz = k60_ipa_le32(db + at);
            return 0;
        }
    }
    return -1;
}

static int
k60_ipa_tcs_conflict(const volatile uint8_t *rsc, const K60RscLayout *l,
    uint32_t tcs, uint32_t capacity, uint32_t address)
{
    uint32_t enable = k60_ipa_rd32(rsc, tcs + l->cmd_enable);

    for (uint32_t i = 0; i < capacity && i < 16u; i++) {
        if ((enable & (1u << i)) != 0 &&
            k60_ipa_rd32(rsc, tcs + (size_t)i * l->cmd_stride + l->cmd_addr) == address) {
            return -1;
        }
    }
    return 0;
}

/* Same active-only TCS4 sequence as K60ModemLink's rail vote, repeated here
 * because that helper is file-static and IPA must vote IP0 before PAS 15. */
static int
k60_ipa_vote_tcs4(volatile uint8_t *rsc, const K60RscLayout *l,
    uint32_t address, uint32_t value, uint32_t capacity)
{
    const size_t base = K60_IPA_RSC_TCS4;
    uint32_t control, progressed = 0;
    int rc = -1;

    if (k60_ipa_rd32(rsc, K60_IPA_RSC_TCS3 + l->status) == 0 &&
        k60_ipa_tcs_conflict(rsc, l, K60_IPA_RSC_TCS3, capacity, address)) {
        return -1;
    }
    k60_ipa_wr32(rsc, K60_IPA_RSC_TCS_BASE,
        k60_ipa_rd32(rsc, K60_IPA_RSC_TCS_BASE) & ~K60_IPA_RSC_CTRL_TCS);
    control = k60_ipa_rd32(rsc, base + l->control) & ~(1u << 24);
    k60_ipa_wr32(rsc, base + l->control, control);
    if (k60_ipa_wait_word(rsc, base + l->control, 0xffffffffu, control, 1000)) {
        return -1;
    }
    control &= ~(1u << 16);
    k60_ipa_wr32(rsc, base + l->control, control);
    if (k60_ipa_wait_word(rsc, base + l->control, 0xffffffffu, control, 1000)) {
        return -1;
    }
    k60_ipa_wr32(rsc, base + l->cmd_enable, 0);
    k60_ipa_wr32(rsc, K60_IPA_RSC_TCS_BASE + l->irq_clear, K60_IPA_RSC_IRQ_DONE);
    if (k60_ipa_wait_word(rsc, K60_IPA_RSC_TCS_BASE + l->irq_status,
        K60_IPA_RSC_IRQ_DONE, 0, 1000)) {
        return -1;
    }
    k60_ipa_wr32(rsc, base + l->cmd_msgid, K60_IPA_RSC_MSGID);
    k60_ipa_wr32(rsc, base + l->cmd_addr, address);
    k60_ipa_wr32(rsc, base + l->cmd_data, value);
    k60_ipa_wr32(rsc, base + l->wait_for_cmpl, 1);
    k60_ipa_fence();
    k60_ipa_wr32(rsc, base + l->cmd_enable, 1);
    if (k60_ipa_rd32(rsc, base + l->cmd_addr) != address ||
        k60_ipa_rd32(rsc, base + l->cmd_data) != value) {
        goto cleanup;
    }
    k60_ipa_wr32(rsc, base + l->control, 1u << 16);
    k60_ipa_fence();
    if (k60_ipa_wait_word(rsc, base + l->control, 0xffffffffu, 1u << 16, 1000)) {
        goto cleanup;
    }
    k60_ipa_fence();
    k60_ipa_wr32(rsc, base + l->control, (1u << 16) | (1u << 24));
    for (unsigned i = 0; i < 200000u; i++) {
        const uint32_t status = k60_ipa_rd32(rsc, base + l->cmd_data + 4u);
        const uint32_t idle = k60_ipa_rd32(rsc, base + l->status);

        if ((status & K60_IPA_RSC_CMD_DONE) == K60_IPA_RSC_CMD_DONE && idle &&
            k60_ipa_rd32(rsc, base + l->cmd_enable) == 1u &&
            k60_ipa_rd32(rsc, base + l->cmd_addr) == address &&
            k60_ipa_rd32(rsc, base + l->cmd_data) == value &&
            (progressed || (k60_ipa_rd32(rsc, K60_IPA_RSC_TCS_BASE + l->irq_status) &
            K60_IPA_RSC_IRQ_DONE))) {
            rc = 0;
            break;
        }
        if ((status & K60_IPA_RSC_CMD_DONE) != K60_IPA_RSC_CMD_DONE || !idle) {
            progressed = 1;
        }
        if ((i & 0x0fu) == 0) {
            delay(10);
        } else {
            k60_ipa_spin();
        }
    }
cleanup:
    k60_ipa_wr32(rsc, base + l->cmd_enable, 0);
    k60_ipa_wr32(rsc, K60_IPA_RSC_TCS_BASE + l->irq_clear, K60_IPA_RSC_IRQ_DONE);
    control = k60_ipa_rd32(rsc, base + l->control) & ~(1u << 24);
    k60_ipa_wr32(rsc, base + l->control, control);
    if (k60_ipa_wait_word(rsc, base + l->control, 0xffffffffu, control, 1000)) {
        return -1;
    }
    k60_ipa_fence();
    return rc;
}

/* Vote IP0 at the native IPA5.x boot corner (SVS2, 120 MHz). The BCM value
 * uses commit/valid bits 30/29 and the frequency in aux units in bits 13:0. */
static int
k60_ipa_clock_vote(void)
{
    volatile uint8_t *db = NULL, *rsc = NULL;
    uint32_t drv, caps, version, capacity, address = 0, unit_khz = 0;
    uint32_t units, vote;
    K60RscLayout layout;
    int rc = K60IpaClockFailed;

    db = (volatile uint8_t *)(uintptr_t)ml_io_map_unmappable(
        (vm_offset_t)K60_IPA_CMD_DB_PHYS, (vm_size_t)K60_IPA_CMD_DB_BYTES, 0x7);
    rsc = (volatile uint8_t *)(uintptr_t)ml_io_map_unmappable(
        (vm_offset_t)K60_IPA_RSC_DRV2_PHYS, (vm_size_t)K60_IPA_RSC_BYTES, 0x7);
    if (db == NULL || rsc == NULL) {
        printf("K60IPA IP0 clock map failed db=%p rsc=%p\n", (void *)db, (void *)rsc);
        return K60IpaClockFailed;
    }
    drv = k60_ipa_rd32(rsc, 0);
    caps = k60_ipa_rd32(rsc, 0x0cu);
    version = (drv >> 16) & 0xffu;
    layout = k60_rsc_layout(drv);
    capacity = (caps >> 27) & 0x1fu;
    if (version != 2u || ((caps >> 12) & 0x3fu) < 8u || capacity < 1u) {
        printf("K60IPA IP0 clock RSC unsupported drv=%#x caps=%#x\n", drv, caps);
        return K60IpaClockFailed;
    }
    if (k60_ipa_rd32(rsc, K60_IPA_RSC_TCS4 + layout.status) == 0) {
        printf("K60IPA IP0 clock TCS4 unavailable\n");
        return K60IpaClockFailed;
    }
    if (k60_ipa_find_ip0((const uint8_t *)db, &address, &unit_khz) != 0 ||
        address == 0 || unit_khz == 0 || unit_khz > 120000u) {
        printf("K60IPA IP0 clock record missing address=%#x unit=%u\n", address, unit_khz);
        return K60IpaClockFailed;
    }
    units = (120000u + unit_khz - 1u) / unit_khz;
    if (units == 0 || units > 0x3fffu) {
        printf("K60IPA IP0 clock vote overflow unit=%u units=%u\n", unit_khz, units);
        return K60IpaClockFailed;
    }
    vote = (1u << 30) | (1u << 29) | units;
    if (k60_ipa_vote_tcs4(rsc, &layout, address, vote, capacity) != 0) {
        printf("K60IPA IP0 clock vote failed address=%#x vote=%#x\n", address, vote);
        return K60IpaClockFailed;
    }
    printf("K60IPA IP0 clock address=%#x unit_khz=%u vote=%#x ok\n",
        address, unit_khz, vote);
    rc = K60IpaOk;
    return rc;
}

/* md0 carries the payload FAT.  memdev hands us the page numbers through
 * k60_ipa_note_window(); convert them exactly the way k60_adsp_md_window()
 * does, because mdevadd() keeps a kernel VA page number for a vmd entry. */
static uint64_t k60_ipa_md_base;
static uint64_t k60_ipa_md_size;

void
k60_ipa_note_window(uint64_t base, uint64_t size)
{
    k60_ipa_md_base = base;
    k60_ipa_md_size = size;
    printf("K60IPA md0 window noted %#llx..%#llx\n",
        (unsigned long long)base, (unsigned long long)(base + size));
}

static int
k60_ipa_md_window(uint64_t *base, uint64_t *size)
{
    if (k60_ipa_md_size != 0) {
        const uint64_t va_pages = 0xfffffff000000000ULL >> 12;

        *base = (k60_ipa_md_base - va_pages) << 12;
        *size = k60_ipa_md_size << 12;
        return 0;
    }
    printf("K60IPA md0 was never registered\n");
    return -1;
}

int
k60_ipa_firmware_start(const void *blob, uint64_t size)
{
    K60IpaFirmwarePlan plan;
    vm_offset_t firmware, metadata, gsi_map;
    int rc;

    if (!blob) {
        return K60IpaBadArgument;
    }
    rc = k60_ipa_clock_vote();
    if (rc != K60IpaOk) {
        printf("K60IPA IP0 clock unavailable rc=%d\n", rc);
        return rc;
    }
    rc = k60_ipa_firmware_check(blob, size, &plan);
    if (rc != K60IpaOk) {
        printf("K60IPA firmware check failed rc=%d size=%llu\n", rc,
            (unsigned long long)size);
        return rc;
    }
    printf("K60IPA firmware plan span=%#llx metadata=%#llx loads=%u\n",
        (unsigned long long)plan.span, (unsigned long long)plan.metadata,
        plan.load_segments);
    /* The TZ-owned GSI global block must not be overwritten. A set EE0 bit
     * before PAS means another manager already owns the block; Pong checks
     * the same status before its signed firmware load. */
    gsi_map = ml_io_map_unmappable((vm_offset_t)K60_GSI_BASE,
        (vm_size_t)K60_GSI_BYTES, 0x7);
    if (gsi_map == 0) {
        printf("K60IPA cannot map GSI view %#x\n", K60_GSI_BASE);
        return K60IpaMapFailed;
    }
    {
        K60IpaGsiCaps caps;

        rc = k60_ipa_gsi_check((void *)(uintptr_t)gsi_map, K60_GSI_BYTES,
            &caps);
        printf("K60IPA pre-PAS GSI status=%#x channels=%u events=%u cmd=%u ev0=%u\n",
            caps.status, caps.channels, caps.events, caps.command_state,
            caps.event_state);
        if (rc != K60IpaOk) {
            printf("K60IPA GSI not available for IPA rc=%d\n", rc);
            return rc;
        }
    }
    /* Both IPA regions are DDR carveouts, not device memory: use the same
     * VM_WIMG_DEFAULT flag K60ModemBoot and K60AdspBoot use. */
    firmware = ml_io_map_unmappable((vm_offset_t)K60_IPA_FW_REGION_BASE,
        (vm_size_t)K60_IPA_FW_REGION_BYTES, 0x2);
    if (firmware == 0) {
        printf("K60IPA cannot map firmware region %#x\n",
            K60_IPA_FW_REGION_BASE);
        return K60IpaMapFailed;
    }
    metadata = ml_io_map_unmappable((vm_offset_t)K60_IPA_METADATA_BASE,
        (vm_size_t)K60_IPA_METADATA_BYTES, 0x2);
    if (metadata == 0) {
        printf("K60IPA cannot map metadata region %#x\n",
            K60_IPA_METADATA_BASE);
        return K60IpaMapFailed;
    }
    rc = k60_ipa_firmware_stage(blob, size, (void *)firmware,
        K60_IPA_FW_REGION_BYTES, (void *)metadata, K60_IPA_METADATA_BYTES,
        &plan);
    if (rc != K60IpaOk) {
        printf("K60IPA firmware stage failed rc=%d\n", rc);
        return rc;
    }
    printf("K60IPA firmware staged at %#x metadata=%#x\n",
        K60_IPA_FW_REGION_BASE, K60_IPA_METADATA_BASE);
    rc = k60_ipa_pas_call(K60M_SCM_PAS_INIT_IMAGE,
        k60_modem_scm_args(2, K60M_SCM_VAL, K60M_SCM_RW, 0),
        K60_IPA_PAS_ID, K60_IPA_METADATA_BASE, 0);
    if (rc != K60IpaOk) {
        printf("K60IPA init_image failed rc=%d\n", rc);
        return rc;
    }
    printf("K60IPA init_image ok\n");
    rc = k60_ipa_pas_call(K60M_SCM_PAS_MEM_SETUP,
        k60_modem_scm_args(3, 0, 0, 0), K60_IPA_PAS_ID,
        K60_IPA_FW_REGION_BASE, plan.span);
    if (rc != K60IpaOk) {
        printf("K60IPA mem_setup failed rc=%d\n", rc);
        return rc;
    }
    printf("K60IPA mem_setup ok base=%#x span=%#llx\n",
        K60_IPA_FW_REGION_BASE, (unsigned long long)plan.span);
    rc = k60_ipa_pas_call(K60M_SCM_PAS_AUTH_AND_RESET,
        k60_modem_scm_args(1, 0, 0, 0), K60_IPA_PAS_ID, 0, 0);
    if (rc != K60IpaOk) {
        printf("K60IPA auth_and_reset failed rc=%d\n", rc);
        return rc;
    }
    printf("K60IPA auth_and_reset ok\n");
    {
        uint32_t status = *(volatile uint32_t *)(gsi_map + 0x25000);
        uint32_t channels = *(volatile uint32_t *)(gsi_map + 0x25040) & 0xffu;
        uint32_t events = *(volatile uint32_t *)(gsi_map + 0x25050) & 0xffu;

        printf("K60IPA post-PAS GSI status=%#x channels=%u events=%u\n",
            status, channels, events);
        if ((status & 1u) == 0) {
            printf("K60IPA GSI EE0 not enabled after auth\n");
        }
    }
    {
        volatile uint8_t *cfg = (volatile uint8_t *)(uintptr_t)
            ml_io_map_unmappable((vm_offset_t)K60_IPA_CFG_BASE, 0x1000, 0x7);
        uint32_t version, comp;

        if (cfg == NULL) {
            printf("K60IPA cannot map cfg page %#x\n", K60_IPA_CFG_BASE);
            return K60IpaMapFailed;
        }
        version = *(volatile uint32_t *)(cfg + K60_IPA_VERSION_REG);
        comp = *(volatile uint32_t *)(cfg + K60_IPA_COMP_HW_VERSION_REG);
        printf("K60IPA version=%#x comp=%#x\n", version, comp);
        if (version == 0 || version == 0xffffffffu) {
            printf("K60IPA IPAREADY not set\n");
            return K60IpaNotReady;
        }
        rc = k60_ipa_resources_prepare((void *)(uintptr_t)cfg, 0x1000);
        printf("K60IPA resources ready=%d\n", rc == K60IpaOk);
        if (rc != K60IpaOk) {
            return rc;
        }
    }
    return K60IpaOk;
}
#else /* K60_HOST_TEST */
int
k60_ipa_firmware_start(const void *blob, uint64_t size)
{
    (void)blob;
    (void)size;
    return K60IpaNotReady;
}
#endif /* K60_HOST_TEST */

#ifndef K60_HOST_TEST
int
k60_ipa_probe_from_handoff(void)
{
    K60FatVolume volume;
    uint64_t base = 0, size = 0;
    uint32_t offset = 0, length = 0;
    vm_offset_t ram;
    int enabled = 0;

    if (!PE_parse_boot_argn("pong_ipa", &enabled, sizeof(enabled)) ||
        enabled == 0) {
        return 0;
    }
    printf("K60IPA probe begin\n");
    if (k60_ipa_md_window(&base, &size) != 0) {
        return -1;
    }
    ram = ml_io_map_unmappable((vm_offset_t)base, (vm_size_t)size, 0x2);
    if (ram == 0) {
        printf("K60IPA cannot map the payload FAT %#llx\n",
            (unsigned long long)base);
        return -1;
    }
    if (k60_fat_open((const void *)(uintptr_t)ram, (size_t)size,
        &volume) != 0) {
        printf("K60IPA payload FAT open failed\n");
        return -1;
    }
    if (k60_fat_find((const void *)(uintptr_t)ram, &volume, "IPA",
        "ipa_fws.mbn", &offset, &length) != 0) {
        printf("K60IPA IPA/ipa_fws.mbn missing\n");
        return -1;
    }
    printf("K60IPA firmware file length=%u\n", length);
    return k60_ipa_firmware_start((const uint8_t *)(uintptr_t)ram + offset,
        length);
}
#else /* K60_HOST_TEST */
int
k60_ipa_probe_from_handoff(void)
{
    return K60IpaNotReady;
}
#endif /* K60_HOST_TEST */

int
k60_ipa_probe(void)
{
    printf("K60IPA probe: cfg=0x%x gsi=0x%x irq=%u/%u state=not-ready\n",
        K60_IPA_CFG_BASE, K60_GSI_BASE, K60_IPA_IRQ, K60_GSI_IRQ);
    return K60IpaNotReady;
}
