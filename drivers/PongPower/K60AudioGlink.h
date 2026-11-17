/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
#ifndef K60_AUDIO_GLINK_H
#define K60_AUDIO_GLINK_H
#include <stdbool.h>
#include <stdint.h>
#include "K60PmicGlinkAudio.h"
#include "QcomGlink.h"

#ifdef __cplusplus
extern "C" {
#endif

#define K60_AUDIO_GLINK_NAME "adsp_apps"
#define K60_AUDIO_GLINK_INTENT_BYTES 512u
#define K60_AUDIO_GLINK_INTENT_COUNT 20u
#define K60_AUDIO_GLINK_SEND_MAX 560u /* one maximum GPR packet */

typedef struct {
    QcomGlink *transport;
    QcomGlinkChannel *channel;
    K60PmicGlinkAudioClient client;
    void *context;
    uint8_t storage[K60_AUDIO_GLINK_INTENT_BYTES * K60_AUDIO_GLINK_INTENT_COUNT];
    uint8_t pending[K60_AUDIO_GLINK_SEND_MAX];
    unsigned pending_bytes;
    bool pending_valid;
    bool requested;
    bool attached;
    int error;
} K60AudioGlink;

void k60_audio_glink_init(K60AudioGlink *, QcomGlink *);
int k60_audio_glink_request(K60AudioGlink *, const K60PmicGlinkAudioClient *, void *);
int k60_audio_glink_service(K60AudioGlink *);
int k60_audio_glink_send(K60AudioGlink *, const uint8_t *, unsigned);
bool k60_audio_glink_ready(const K60AudioGlink *);
void k60_audio_glink_stop(K60AudioGlink *);

#ifdef __cplusplus
}
#endif
#endif
