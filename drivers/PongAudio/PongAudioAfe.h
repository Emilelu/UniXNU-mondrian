/* SPDX-License-Identifier: BSD-2-Clause-Patent
 *
 * Offline encoder for the AFE parameter packets the PRI_TDM speaker path
 * will have to send once the ADSP is up (the PAS1 line). Byte packing only:
 * every function writes a little-endian packet into a caller-supplied
 * buffer and returns its length. No MMIO, no kernel headers, nothing sent.
 *
 * Why this exists. The speaker port cannot make a sound until the DSP is
 * asked, over GLINK, for a bit clock, a TDM group, a TDM port, its slot
 * mapping and DEVICE_START (TDMS.md section 3). Those are field-ordered
 * packed structures; one wrong offset is a silent failure on a board with
 * no serial console. Packing them here, where the host test can read every
 * byte, means the kernel side only moves bytes it already trusts.
 *
 * Layouts are the vendor AudioReach-era ones, from the APSL-2.0 reference
 * (P: hakios.sound.c:349-385, facts only, no code copied) - the same set
 * mainline agrees with where it has an equivalent
 * (M: sound/soc/qcom/qdsp6/q6afe.c:396-417 afe_param_id / param_data_v2,
 * and q6afe.h:180-194 q6afe_tdm_cfg for the field order of the port TDM
 * parameter). Where the two disagree the vendor layout wins, because the
 * DSP in this phone speaks the vendor one; the disagreements are recorded
 * in TDMS.md section 3.
 *
 * Two packet shapes, both carrying the parameters in band
 * (address lsw/msw and mem_map_handle all zero, M: q6afe.c:1076-1085):
 *
 *   service scoped  [GPR 24][svc_cmd_set_param 16][param 12][payload]
 *     opcode AFE_SVC_CMD_SET_PARAM        clocks, groups
 *   port scoped     [GPR 24][port_cmd_set_param_v2 16][param 12][payload]
 *     opcode AFE_PORT_CMD_SET_PARAM_V2    port config, slot mapping
 *   start           [GPR 24][{u16 port, u16 0}]
 *     opcode AFE_PORT_CMD_DEVICE_START
 *
 * The 24-byte GPR header is M: apr.h:79-90 with GPR_PKT_VER 0. The 0504
 * skeleton first carried GPR_VERSION 3, BASIC_RESULT 0x02000002 and
 * GET_SPF_STATE 0x0100100D; all three were corrected in 0504 on
 * 2026-11-15 (PAS1-AUDIO-REQUIREMENTS.md section 1.3). The constants
 * below are what the host test pins.
 *
 * The K60 values (port 0x9020 TERT TDM RX, group 0x9120, 24-bit samples in
 * TDMS.md sections 3 and 4; this file encodes whatever it is given and
 * offers the K60 defaults as named constants, nothing more.
 *
 * Pure: no MMIO, no kernel headers.
 *
 * This header is part of the kernel patch through patches/audio/0003: the
 * AFE selftest in pong_audio.c includes it and calls the encoder. Keep it in
 * the generator NEW_FILES list (AMPS.md section 6).
 */
#ifndef PONG_AUDIO_AFE_H
#define PONG_AUDIO_AFE_H

#include <stddef.h>
#include <stdint.h>
#include <string.h>

/* Speaker-path refusal codes. These are contract, not errno: the values are
 * what pong_audio_status() returns when the PAS1/ADSP path is unavailable.
 * Keep them stable; PAS1-AUDIO-REQUIREMENTS.md section 2 records the names. */
typedef enum {
    PongAudioOk = 0,
    PongAudioErrNoHandoff = -2001,
    PongAudioErrNoLease = -2002,
    PongAudioErrStaleLease = -2003,
    PongAudioErrApmNotReady = -2004,
    PongAudioErrAfeRefused = -2005,
    PongAudioErrBadRequest = -2006,
    PongAudioErrRingFull = -2007,
    PongAudioErrPlayback = -2008
} PongAudioStatus;

static inline const char *
pong_audio_error_name(int status)
{
    switch (status) {
    case PongAudioOk:
        return "PongAudioOk";
    case PongAudioErrNoHandoff:
        return "PongAudioErrNoHandoff";
    case PongAudioErrNoLease:
        return "PongAudioErrNoLease";
    case PongAudioErrStaleLease:
        return "PongAudioErrStaleLease";
    case PongAudioErrApmNotReady:
        return "PongAudioErrApmNotReady";
    case PongAudioErrAfeRefused:
        return "PongAudioErrAfeRefused";
    case PongAudioErrBadRequest:
        return "PongAudioErrBadRequest";
    case PongAudioErrRingFull:
        return "PongAudioErrRingFull";
    case PongAudioErrPlayback:
        return "PongAudioErrPlayback";
    default:
        return "PongAudioErrUnknown";
    }
}

/* Command, module and parameter ids (P: hakios.sound.c:324-336, identical
 * to M: q6afe.c:28-93). */
#define PONG_AFE_PORT_CMD_DEVICE_START             0x000100e5u
#define PONG_AFE_PORT_CMD_DEVICE_STOP              0x000100e6u
#define PONG_AFE_PORT_CMD_SET_PARAM_V2             0x000100efu
#define PONG_AFE_SVC_CMD_SET_PARAM                 0x000100f3u
#define PONG_AFE_MODULE_AUDIO_DEV_INTERFACE        0x0001020cu
#define PONG_AFE_MODULE_TDM                        0x0001028au
#define PONG_AFE_MODULE_GROUP_DEVICE               0x00010254u
#define PONG_AFE_MODULE_CLOCK_SET                  0x0001028fu
#define PONG_AFE_PARAM_ID_TDM_CONFIG               0x0001029du
#define PONG_AFE_PARAM_ID_PORT_SLOT_MAPPING_CONFIG 0x00010297u
#define PONG_AFE_PARAM_ID_GROUP_DEVICE_ENABLE      0x00010256u
#define PONG_AFE_PARAM_ID_GROUP_DEVICE_TDM_CONFIG  0x0001029eu
#define PONG_AFE_PARAM_ID_CLOCK_SET                0x00010290u

/* PRM: the bit clock is voted through the Audio Process Manager resource
 * manager, not through the AFE clock-set module above (V: audio_prm.c:198-248,
 * audio_prm.h:192-202). The pair above stays only so the legacy layout keeps
 * a test; nothing in the speaker path sends it. */
#define PONG_AFE_GPR_SVC_ASM                    0x7u        /* V: qcom,gpr.h:20 */
#define PONG_AFE_PRM_MODULE_INSTANCE_ID         0x00000002u /* V: audio_prm.h:16 */
#define PONG_AFE_PRM_CMD_REQUEST_HW_RSC         0x0100100fu /* V: audio_prm.h:192 */
#define PONG_AFE_PRM_PARAM_ID_RSC_AUDIO_HW_CLK  0x0800102cu /* V: audio_prm.h:202 */
#define PONG_AFE_APM_CMD_HDR_BYTES              16u         /* V: audio_prm.h:71 */
#define PONG_AFE_APM_MODULE_PARAM_BYTES         16u         /* V: audio_prm.h:110 */
#define PONG_AFE_PRM_MAX_CLOCKS                 1u
#define PONG_AFE_PRM_CLOCK_BYTES                76u         /* 24 + 16 + 16 + 4 + 16 */

/* The K60 speaker port: PRI_TDM_RX_0 and its group (TDMS.md sections 3, 5). */
#define PONG_AFE_PORT_TERT_TDM_RX_0 0x9020u
#define PONG_AFE_GROUP_TERT_TDM_RX  0x9120u
#define PONG_AFE_GROUP_OTHER_PORT   0x9022u
#define PONG_AFE_PORT_INVALID       0xffffu

/* Bit clock id and attribute (V: audio_prm.h:457,570). The rate is rate x
 * slot_width x bus slots, computed by the machine driver from
 * qcom,tdm-max-slots (V: msm_common.c:407-417), which is 8 on this board:
 * 48000 x 32 x 8 = 12.288 MHz. The DT property qcom,msm-cpudai-tdm-clk-rate
 * is not read by the waipio machine driver, so its 1.536 MHz is a dead value. */
#define PONG_AFE_CLOCK_TERT_TDM_IBIT      0x204u
#define PONG_AFE_CLOCK_ATTRIBUTE_NOCOUPLE 4u
#define PONG_AFE_RATE                     48000u
#define PONG_AFE_SLOT_BITS                32u
#define PONG_AFE_SLOTS                    2u
#define PONG_AFE_TDM_MAX_SLOTS            8u   /* V: live FDT qcom,tdm-max-slots */
#define PONG_AFE_TDM_CLK_HZ               (PONG_AFE_RATE * PONG_AFE_SLOT_BITS * PONG_AFE_TDM_MAX_SLOTS)
#define PONG_AFE_MAX_CHANNELS             8u   /* M: q6afe.h:40 */

/* GPR wire constants (M: apr.h:96-108). */
#define PONG_AFE_GPR_VERSION            0x0u
#define PONG_AFE_GPR_HEADER_BYTES       24u
#define PONG_AFE_GPR_HEADER_WORDS       6u   /* 24 bytes / 4 */
#define PONG_AFE_GPR_DOMAIN_ADSP        2u
#define PONG_AFE_GPR_DOMAIN_APPS        3u
#define PONG_AFE_GPR_BASIC_RSP_RESULT   0x02001005u
#define PONG_AFE_GPR_BASIC_EVT_ACCEPTED 0x02001006u
#define PONG_AFE_GPR_APM_GET_SPF_STATE 0x01001021u  /* M: audioreach.h:38 */
#define PONG_AFE_GPR_APM_SPF_STATE     0x02001007u  /* M: audioreach.h:39 */
#define PONG_AFE_GPR_PORT_APM          1u           /* M: apr.h:105, the APM module instance */
#define PONG_AFE_GPR_SVC_AFE           4u           /* V: qcom,gpr.h:17, the AFE service */
#define PONG_AFE_GPR_PORT_CLIENT       0x2001u      /* P: PongAudio.cpp:36 Port */

/* Envelope sizes, all packed (M: q6afe.c:396-417). */
#define PONG_AFE_SVC_HDR_BYTES   16u  /* payload_size, addr lsw, addr msw, handle */
#define PONG_AFE_PORT_HDR_BYTES  16u  /* port, payload_size, addr lsw, addr msw, handle */
#define PONG_AFE_PARAM_BYTES     12u  /* module, param, size, reserved */

/* Payload sizes (P: hakios.sound.c:349-385, all packed). */
#define PONG_AFE_CLOCK_SET_BYTES     20u
#define PONG_AFE_GROUP_TDM_BYTES     44u
#define PONG_AFE_GROUP_ENABLE_BYTES  4u
#define PONG_AFE_TDM_BYTES           36u
#define PONG_AFE_SLOT_MAPPING_BYTES  28u
#define PONG_AFE_DEVICE_START_BYTES  4u

/* Little-endian field writers: the byte order of every multi-byte field
 * below is decided here and nowhere else. */
static inline void
pong_afe_put16(uint8_t *p, uint16_t v)
{
    p[0] = (uint8_t)(v & 0xffu);
    p[1] = (uint8_t)((v >> 8) & 0xffu);
}

static inline void
pong_afe_put32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)(v & 0xffu);
    p[1] = (uint8_t)((v >> 8) & 0xffu);
    p[2] = (uint8_t)((v >> 16) & 0xffu);
    p[3] = (uint8_t)((v >> 24) & 0xffu);
}

/* The 24-byte GPR header (M: apr.h:79-90, audioreach.c:229-266):
 *   word0 = version | header_word_size << 4 | packet_size << 8
 *   word1 = dest_domain | src_domain << 8
 *   word2 = src_port, word3 = dest_port, word4 = token, word5 = opcode
 * packet_bytes is the whole packet including this header. Returns 24, or 0
 * if the buffer cannot hold it. */
static inline size_t
pong_afe_gpr_hdr(uint8_t *buf, size_t bytes, uint32_t opcode, uint32_t token,
    uint16_t src_port, uint16_t dest_port, size_t packet_bytes)
{
    if (buf == NULL || bytes < PONG_AFE_GPR_HEADER_BYTES ||
        packet_bytes > 0x00ffffffu) {
        return 0;
    }
    pong_afe_put32(buf + 0,
        PONG_AFE_GPR_VERSION |
            ((uint32_t)PONG_AFE_GPR_HEADER_WORDS << 4) |
            ((uint32_t)packet_bytes << 8));
    pong_afe_put32(buf + 4,
        PONG_AFE_GPR_DOMAIN_ADSP |
            ((uint32_t)PONG_AFE_GPR_DOMAIN_APPS << 8));
    pong_afe_put32(buf + 8, src_port);
    pong_afe_put32(buf + 12, dest_port);
    pong_afe_put32(buf + 16, token);
    pong_afe_put32(buf + 20, opcode);
    return PONG_AFE_GPR_HEADER_BYTES;
}

/* The first packet an audio client sends: GET_SPF_STATE from its own GPR
 * port (0x2001 on Pong) to the APM module instance (port 1), 24 bytes of
 * header and no payload (P: PongAudio.cpp:107, ShengGpr.c:63). */
static inline size_t
pong_afe_gpr_spf_state_query(uint8_t *buf, size_t bytes, uint32_t token)
{
    return pong_afe_gpr_hdr(buf, bytes, PONG_AFE_GPR_APM_GET_SPF_STATE,
        token, PONG_AFE_GPR_PORT_CLIENT, PONG_AFE_GPR_PORT_APM,
        PONG_AFE_GPR_HEADER_BYTES);
}

/* struct afe_param (P: hakios.sound.c:349-352), packed 12 bytes:
 * module, param, payload size, reserved. */
static inline void
pong_afe_param(uint8_t *p, uint32_t module_id, uint32_t param_id,
    uint16_t payload_bytes)
{
    pong_afe_put32(p + 0, module_id);
    pong_afe_put32(p + 4, param_id);
    pong_afe_put16(p + 8, payload_bytes);
    pong_afe_put16(p + 10, 0u);
}

/* Layout of the two packets, in bytes from the start of the packet. */
#define PONG_AFE_OFF_SVC_PAYLOAD_SIZE 24u
#define PONG_AFE_OFF_PORT_ID          24u
#define PONG_AFE_OFF_PORT_PAYLOAD_SIZE 26u
#define PONG_AFE_OFF_PARAM            40u
#define PONG_AFE_OFF_PAYLOAD          52u

/* Service-scoped parameter: clocks and groups (P: afe_service_param
 * :386-402). In band, address and handle zero. Returns the packet length,
 * or 0 if the buffer is too small. */
static inline size_t
pong_afe_svc_set_param(uint8_t *buf, size_t bytes, uint32_t module_id,
    uint32_t param_id, const uint8_t *payload, size_t payload_bytes,
    uint32_t token)
{
    size_t total = PONG_AFE_GPR_HEADER_BYTES + PONG_AFE_SVC_HDR_BYTES +
        PONG_AFE_PARAM_BYTES + payload_bytes;

    if (buf == NULL || (payload == NULL && payload_bytes != 0u) ||
        payload_bytes > 0xffffu || bytes < total) {
        return 0;
    }
    if (pong_afe_gpr_hdr(buf, bytes, PONG_AFE_SVC_CMD_SET_PARAM, token,
            PONG_AFE_GPR_PORT_CLIENT, PONG_AFE_GPR_SVC_AFE, total) == 0u) {
        return 0;
    }
    pong_afe_put32(buf + PONG_AFE_OFF_SVC_PAYLOAD_SIZE,
        (uint32_t)(PONG_AFE_PARAM_BYTES + payload_bytes));
    pong_afe_put32(buf + 28, 0u);  /* payload_address_lsw */
    pong_afe_put32(buf + 32, 0u);  /* payload_address_msw */
    pong_afe_put32(buf + 36, 0u);  /* mem_map_handle */
    pong_afe_param(buf + PONG_AFE_OFF_PARAM, module_id, param_id,
        (uint16_t)payload_bytes);
    for (size_t i = 0; i < payload_bytes; ++i) {
        buf[PONG_AFE_OFF_PAYLOAD + i] = payload[i];
    }
    return total;
}

/* Port-scoped parameter: the port id goes in the first two bytes and the
 * payload size in the next two (P: afe_port_param :404-420, the same
 * 16-byte shape as M: q6afe.c:411-417 afe_port_cmd_set_param_v2). The packet
 * travels from our client port to the AFE service, like the PRM vote travels
 * from ASM to the PRM instance: a zero destination reached no service at all
 * and the DSP answered GPR_IBASIC_RSP_RESULT status 1 (aj console 549). */
static inline size_t
pong_afe_port_set_param(uint8_t *buf, size_t bytes, uint16_t port_id,
    uint32_t module_id, uint32_t param_id, const uint8_t *payload,
    size_t payload_bytes, uint32_t token)
{
    size_t total = PONG_AFE_GPR_HEADER_BYTES + PONG_AFE_PORT_HDR_BYTES +
        PONG_AFE_PARAM_BYTES + payload_bytes;

    if (buf == NULL || (payload == NULL && payload_bytes != 0u) ||
        payload_bytes > 0xffffu || bytes < total) {
        return 0;
    }
    if (pong_afe_gpr_hdr(buf, bytes, PONG_AFE_PORT_CMD_SET_PARAM_V2, token,
            PONG_AFE_GPR_PORT_CLIENT, PONG_AFE_GPR_SVC_AFE, total) == 0u) {
        return 0;
    }
    pong_afe_put16(buf + PONG_AFE_OFF_PORT_ID, port_id);
    pong_afe_put16(buf + PONG_AFE_OFF_PORT_PAYLOAD_SIZE,
        (uint16_t)(PONG_AFE_PARAM_BYTES + payload_bytes));
    pong_afe_put32(buf + 28, 0u);  /* payload_address_lsw */
    pong_afe_put32(buf + 32, 0u);  /* payload_address_msw */
    pong_afe_put32(buf + 36, 0u);  /* mem_map_handle */
    pong_afe_param(buf + PONG_AFE_OFF_PARAM, module_id, param_id,
        (uint16_t)payload_bytes);
    for (size_t i = 0; i < payload_bytes; ++i) {
        buf[PONG_AFE_OFF_PAYLOAD + i] = payload[i];
    }
    return total;
}

/* DEVICE_START: {u16 port_id, u16 reserved} as the packet payload
 * (P: afe_on :461-465, M: q6afe.c:385-388). Returns 28. */
static inline size_t
pong_afe_device_start(uint8_t *buf, size_t bytes, uint16_t port_id, uint32_t token)
{
    size_t total = PONG_AFE_GPR_HEADER_BYTES + PONG_AFE_DEVICE_START_BYTES;

    if (buf == NULL || bytes < total) {
        return 0;
    }
    if (pong_afe_gpr_hdr(buf, bytes, PONG_AFE_PORT_CMD_DEVICE_START, token,
            PONG_AFE_GPR_PORT_CLIENT, PONG_AFE_GPR_SVC_AFE, total) == 0u) {
        return 0;
    }
    pong_afe_put16(buf + 24, port_id);
    pong_afe_put16(buf + 26, 0u);
    return total;
}

/* --- the five parameter payloads ------------------------------------- */

/* struct afe_clock_set (P: :355-358, packed 20 bytes):
 *   version, id, hz  (u32 each), attribute, root (u16 each), enable (u32)
 * The K60 sample is {1, 0x204, 48000*32*2, 4, 0, on}: TERT TDM IBIT. */
static inline size_t
pong_afe_clock_set(uint8_t *out, size_t bytes, uint16_t clock_id,
    uint32_t hz, uint16_t attribute, uint32_t enable)
{
    if (out == NULL || bytes < PONG_AFE_CLOCK_SET_BYTES) {
        return 0;
    }
    pong_afe_put32(out + 0, 1u);           /* version */
    pong_afe_put32(out + 4, clock_id);
    pong_afe_put32(out + 8, hz);
    pong_afe_put16(out + 12, attribute);
    pong_afe_put16(out + 14, 0u);          /* root */
    pong_afe_put32(out + 16, enable);
    return PONG_AFE_CLOCK_SET_BYTES;
}

/* A PRM clock request (V: audio_prm.c:198-248), one GPR message carrying an
 * APM command header, one module parameter header, the clock count and one
 * clock tuple:
 *   [GPR 24][apm_cmd_header 16][apm_module_param_data 16][count 4][cfg 16]
 * The AudioReach command header orders the four words as address lsw, address
 * msw, mem_map_handle, payload_size (V: audio_prm.h:86-116, P: cmd_header);
 * the AFE envelope above puts payload_size first, this one puts it last.
 * payload_size counts everything after the command header (36) and param_size
 * everything after the parameter header (20). src_port is the ASM service,
 * dest_port the PRM instance, and both addresses stay zero because the
 * payload is in band. */
static inline size_t
pong_afe_prm_clock_request(uint8_t *out, size_t bytes, uint16_t clock_id,
    uint32_t hz, uint32_t attribute, uint32_t token)
{
    size_t n;

    if (out == NULL || bytes < PONG_AFE_PRM_CLOCK_BYTES) {
        return 0;
    }
    n = pong_afe_gpr_hdr(out, bytes, PONG_AFE_PRM_CMD_REQUEST_HW_RSC, token,
        PONG_AFE_GPR_SVC_ASM, PONG_AFE_PRM_MODULE_INSTANCE_ID,
        PONG_AFE_PRM_CLOCK_BYTES);
    if (n == 0) {
        return 0;
    }
    pong_afe_put32(out + 24, 0u);    /* payload_address_lsw */
    pong_afe_put32(out + 28, 0u);    /* payload_address_msw */
    pong_afe_put32(out + 32, 0u);    /* mem_map_handle */
    pong_afe_put32(out + 36, 36u);   /* payload_size */
    pong_afe_put32(out + 40, PONG_AFE_PRM_MODULE_INSTANCE_ID);
    pong_afe_put32(out + 44, PONG_AFE_PRM_PARAM_ID_RSC_AUDIO_HW_CLK);
    pong_afe_put32(out + 48, 20u);   /* param_size */
    pong_afe_put32(out + 52, 0u);    /* error_code */
    pong_afe_put32(out + 56, PONG_AFE_PRM_MAX_CLOCKS);
    pong_afe_put32(out + 60, clock_id);
    pong_afe_put32(out + 64, hz);
    pong_afe_put32(out + 68, attribute);
    pong_afe_put32(out + 72, 0u);    /* clock_root */
    return PONG_AFE_PRM_CLOCK_BYTES;
}

/* struct afe_group_tdm (P: :360-366, packed 44 bytes):
 *   version (u32), group, reserved (u16), ports[8] (u16),
 *   channels, rate, bits (u32), slots, slot_bits (u16), slot_mask (u32)
 * The K60 group lists 0x9020 only (the DT says group-num-ports = 1);
 * 0x9022 is the vendor's unused second port. */
static inline size_t
pong_afe_group_tdm(uint8_t *out, size_t bytes, uint16_t group,
    const uint16_t *ports, uint32_t channels, uint32_t rate, uint32_t bits,
    uint16_t slots, uint16_t slot_bits, uint32_t slot_mask)
{
    if (out == NULL || bytes < PONG_AFE_GROUP_TDM_BYTES) {
        return 0;
    }
    pong_afe_put32(out + 0, 1u);           /* version */
    pong_afe_put16(out + 4, group);
    pong_afe_put16(out + 6, 0u);           /* reserved */
    for (unsigned i = 0; i < PONG_AFE_MAX_CHANNELS; ++i) {
        pong_afe_put16(out + 8u + i * 2u,
            ports != NULL ? ports[i] : PONG_AFE_PORT_INVALID);
    }
    pong_afe_put32(out + 24, channels);
    pong_afe_put32(out + 28, rate);
    pong_afe_put32(out + 32, bits);
    pong_afe_put16(out + 36, slots);
    pong_afe_put16(out + 38, slot_bits);
    pong_afe_put32(out + 40, slot_mask);
    return PONG_AFE_GROUP_TDM_BYTES;
}

/* struct afe_group_enable (P: :368-370, packed 4 bytes): group, enable. */
static inline size_t
pong_afe_group_enable(uint8_t *out, size_t bytes, uint16_t group, uint16_t enable)
{
    if (out == NULL || bytes < PONG_AFE_GROUP_ENABLE_BYTES) {
        return 0;
    }
    pong_afe_put16(out + 0, group);
    pong_afe_put16(out + 2, enable);
    return PONG_AFE_GROUP_ENABLE_BYTES;
}

/* struct afe_tdm (P: :372-378, packed 36 bytes):
 *   version, channels, rate, bits (u32), then data_format, sync_mode,
 *   sync_source, slots, data_out, invert_sync, data_delay, slot_bits
 *   (u16 each), then slot_mask (u32).
 * Field order is the same as M: q6afe.h:180-194; the vendor file starts
 * with a version word where mainline starts with the channel count. */
static inline size_t
pong_afe_tdm(uint8_t *out, size_t bytes, uint32_t channels, uint32_t rate,
    uint32_t bits, uint16_t data_format, uint16_t sync_mode,
    uint16_t sync_source, uint16_t slots, uint16_t data_out,
    uint16_t invert_sync, uint16_t data_delay, uint16_t slot_bits,
    uint32_t slot_mask)
{
    if (out == NULL || bytes < PONG_AFE_TDM_BYTES) {
        return 0;
    }
    pong_afe_put32(out + 0, 1u);           /* version */
    pong_afe_put32(out + 4, channels);
    pong_afe_put32(out + 8, rate);
    pong_afe_put32(out + 12, bits);
    pong_afe_put16(out + 16, data_format);
    pong_afe_put16(out + 18, sync_mode);
    pong_afe_put16(out + 20, sync_source);
    pong_afe_put16(out + 22, slots);
    pong_afe_put16(out + 24, data_out);
    pong_afe_put16(out + 26, invert_sync);
    pong_afe_put16(out + 28, data_delay);
    pong_afe_put16(out + 30, slot_bits);
    pong_afe_put32(out + 32, slot_mask);
    return PONG_AFE_TDM_BYTES;
}

/* struct afe_slot_mapping (P: :380-385, packed 28 bytes):
 *   version (u32), channels, bits (u16), align (u32), offsets[8] (u16)
 * offsets are byte offsets inside a frame: {0, 4} for two 32-bit slots. */
static inline size_t
pong_afe_slot_mapping(uint8_t *out, size_t bytes, uint16_t channels,
    uint16_t bits, uint32_t align, const uint16_t *offsets)
{
    if (out == NULL || bytes < PONG_AFE_SLOT_MAPPING_BYTES) {
        return 0;
    }
    pong_afe_put32(out + 0, 1u);           /* version */
    pong_afe_put16(out + 4, channels);
    pong_afe_put16(out + 6, bits);
    pong_afe_put32(out + 8, align);
    for (unsigned i = 0; i < PONG_AFE_MAX_CHANNELS; ++i) {
        pong_afe_put16(out + 12u + i * 2u,
            offsets != NULL ? offsets[i] : PONG_AFE_PORT_INVALID);
    }
    return PONG_AFE_SLOT_MAPPING_BYTES;
}

/* --- the amplifier write stream ------------------------------------- */

/* One AW88261 register write on the wire is three bytes: register, then the
 * value big-endian (M: aw88261.c regmap write through the 16-bit bus). The
 * replay pass in PongAudioAmp.c sends exactly this, so the profile can be
 * turned into bytes here and compared pair for pair.
 * pairs is the flat {register, value} array PongAudioAmpProfile.h holds.
 * Returns 3 * pairs_count, or 0 if the buffer is too small. */
#define PONG_AFE_AMP_WRITE_BYTES 3u
static inline size_t
pong_afe_amp_write(uint8_t *out, size_t bytes, uint16_t reg, uint16_t value)
{
    if (out == NULL || bytes < PONG_AFE_AMP_WRITE_BYTES) {
        return 0;
    }
    out[0] = (uint8_t)(reg & 0xffu);
    out[1] = (uint8_t)((value >> 8) & 0xffu);
    out[2] = (uint8_t)(value & 0xffu);
    return PONG_AFE_AMP_WRITE_BYTES;
}

static inline size_t
pong_afe_amp_stream(uint8_t *out, size_t bytes, const uint16_t *pairs,
    size_t pairs_count)
{
    size_t need = pairs_count * PONG_AFE_AMP_WRITE_BYTES;

    if (out == NULL || pairs == NULL || bytes < need) {
        return 0;
    }
    for (size_t i = 0; i < pairs_count; ++i) {
        (void)pong_afe_amp_write(out + i * PONG_AFE_AMP_WRITE_BYTES,
            PONG_AFE_AMP_WRITE_BYTES, pairs[i * 2u], pairs[i * 2u + 1u]);
    }
    return need;
}

/* --- the order the DSP expects --------------------------------------- */

/* P: afe_on :432-468. Clock first (the port cannot be configured without a
 * running bit clock), then the group, then the port, then start. Each step
 * is a separate packet; the kernel side sends them in this order and stops
 * at the first failure. */
typedef enum {
    PongAfeStepClock = 0,
    PongAfeStepGroupTdm,
    PongAfeStepGroupEnable,
    PongAfeStepPortTdm,
    PongAfeStepSlotMapping,
    PongAfeStepDeviceStart,
    PongAfeStepCount
} PongAfeStep;

/* 1 = port scoped packet (AFE_PORT_CMD_SET_PARAM_V2 with the port id),
 * 0 = service scoped (AFE_SVC_CMD_SET_PARAM), -1 = out of range. */
static inline int
pong_afe_step_port_scoped(unsigned step)
{
    switch (step) {
    case PongAfeStepClock:
    case PongAfeStepGroupTdm:
    case PongAfeStepGroupEnable:
        return 0;
    case PongAfeStepPortTdm:
    case PongAfeStepSlotMapping:
        return 1;
    case PongAfeStepDeviceStart:
        return 0;
    default:
        return -1;
    }
}

/* Module and parameter id of a step; returns 0 on success, -1 out of range. */
static inline int
pong_afe_step_ids(unsigned step, uint32_t *module_id, uint32_t *param_id)
{
    switch (step) {
    case PongAfeStepClock:
        *module_id = PONG_AFE_PRM_MODULE_INSTANCE_ID;
        *param_id = PONG_AFE_PRM_PARAM_ID_RSC_AUDIO_HW_CLK;
        return 0;
    case PongAfeStepGroupTdm:
        *module_id = PONG_AFE_MODULE_GROUP_DEVICE;
        *param_id = PONG_AFE_PARAM_ID_GROUP_DEVICE_TDM_CONFIG;
        return 0;
    case PongAfeStepGroupEnable:
        *module_id = PONG_AFE_MODULE_GROUP_DEVICE;
        *param_id = PONG_AFE_PARAM_ID_GROUP_DEVICE_ENABLE;
        return 0;
    case PongAfeStepPortTdm:
        *module_id = PONG_AFE_MODULE_AUDIO_DEV_INTERFACE;
        *param_id = PONG_AFE_PARAM_ID_TDM_CONFIG;
        return 0;
    case PongAfeStepSlotMapping:
        *module_id = PONG_AFE_MODULE_TDM;
        *param_id = PONG_AFE_PARAM_ID_PORT_SLOT_MAPPING_CONFIG;
        return 0;
    default:
        return -1;
    }
}

/* Opcode of a step; 0 out of range. */
static inline uint32_t
pong_afe_step_opcode(unsigned step)
{
    if (step == PongAfeStepClock) {
        return PONG_AFE_PRM_CMD_REQUEST_HW_RSC;
    }
    if (step == PongAfeStepDeviceStart) {
        return PONG_AFE_PORT_CMD_DEVICE_START;
    }
    if (pong_afe_step_port_scoped(step) == 1) {
        return PONG_AFE_PORT_CMD_SET_PARAM_V2;
    }
    if (pong_afe_step_port_scoped(step) == 0 && step != PongAfeStepDeviceStart) {
        return PONG_AFE_SVC_CMD_SET_PARAM;
    }
    return 0u;
}

/* The six packets with the K60 values, in one call. This is the only place
 * that combines a payload builder with its envelope: the kernel sequence
 * sends exactly these bytes and the host test pins every length, opcode and
 * selected field. Max packet: group TDM = 24 + 16 + 12 + 44 = 96 bytes. */
#define PONG_AFE_STEP_PACKET_MAX 96u

static inline size_t
pong_afe_step_packet(uint8_t *out, size_t bytes, unsigned step, uint32_t token)
{
    uint8_t payload[PONG_AFE_GROUP_TDM_BYTES];
    uint16_t ports[PONG_AFE_MAX_CHANNELS];
    uint16_t offsets[PONG_AFE_MAX_CHANNELS];
    size_t n;

    if (out == NULL || step >= (unsigned)PongAfeStepCount) {
        return 0u;
    }
    if (step == (unsigned)PongAfeStepClock) {
        return pong_afe_prm_clock_request(out, bytes,
            PONG_AFE_CLOCK_TERT_TDM_IBIT, PONG_AFE_TDM_CLK_HZ,
            PONG_AFE_CLOCK_ATTRIBUTE_NOCOUPLE, token);
    }
    memset(payload, 0, sizeof(payload));
    if (step == (unsigned)PongAfeStepGroupTdm) {
        for (unsigned i = 0; i < PONG_AFE_MAX_CHANNELS; ++i) {
            ports[i] = PONG_AFE_PORT_INVALID;
        }
        ports[0] = PONG_AFE_PORT_TERT_TDM_RX_0;
        ports[1] = PONG_AFE_GROUP_OTHER_PORT;
        n = pong_afe_group_tdm(payload, sizeof(payload),
            PONG_AFE_GROUP_TERT_TDM_RX, ports, PONG_AFE_SLOTS, PONG_AFE_RATE,
            PONG_AFE_SLOT_BITS, (uint16_t)PONG_AFE_SLOTS,
            (uint16_t)PONG_AFE_SLOT_BITS, 3u);
        if (n == 0u) {
            return 0u;
        }
        return pong_afe_svc_set_param(out, bytes, PONG_AFE_MODULE_GROUP_DEVICE,
            PONG_AFE_PARAM_ID_GROUP_DEVICE_TDM_CONFIG, payload, n, token);
    }
    if (step == (unsigned)PongAfeStepGroupEnable) {
        n = pong_afe_group_enable(payload, sizeof(payload),
            PONG_AFE_GROUP_TERT_TDM_RX, 1u);
        if (n == 0u) {
            return 0u;
        }
        return pong_afe_svc_set_param(out, bytes, PONG_AFE_MODULE_GROUP_DEVICE,
            PONG_AFE_PARAM_ID_GROUP_DEVICE_ENABLE, payload, n, token);
    }
    if (step == (unsigned)PongAfeStepPortTdm) {
        n = pong_afe_tdm(payload, sizeof(payload), PONG_AFE_SLOTS, PONG_AFE_RATE,
            PONG_AFE_SLOT_BITS, 0u, 0u, 1u, (uint16_t)PONG_AFE_SLOTS, 0u, 1u,
            1u, (uint16_t)PONG_AFE_SLOT_BITS, 3u);
        if (n == 0u) {
            return 0u;
        }
        return pong_afe_port_set_param(out, bytes, PONG_AFE_PORT_TERT_TDM_RX_0,
            PONG_AFE_MODULE_AUDIO_DEV_INTERFACE, PONG_AFE_PARAM_ID_TDM_CONFIG,
            payload, n, token);
    }
    if (step == (unsigned)PongAfeStepSlotMapping) {
        for (unsigned i = 0; i < PONG_AFE_MAX_CHANNELS; ++i) {
            offsets[i] = PONG_AFE_PORT_INVALID;
        }
        offsets[0] = 0u;
        offsets[1] = 4u;
        n = pong_afe_slot_mapping(payload, sizeof(payload),
            (uint16_t)PONG_AFE_SLOTS, (uint16_t)PONG_AFE_SLOT_BITS, 0u, offsets);
        if (n == 0u) {
            return 0u;
        }
        return pong_afe_port_set_param(out, bytes, PONG_AFE_PORT_TERT_TDM_RX_0,
            PONG_AFE_MODULE_TDM, PONG_AFE_PARAM_ID_PORT_SLOT_MAPPING_CONFIG,
            payload, n, token);
    }
    if (step == (unsigned)PongAfeStepDeviceStart) {
        return pong_afe_device_start(out, bytes, PONG_AFE_PORT_TERT_TDM_RX_0,
            token);
    }
    return 0u;
}

#endif /* PONG_AUDIO_AFE_H */
