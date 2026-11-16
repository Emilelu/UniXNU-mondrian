/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
#ifndef K60_PMIC_GLINK_AUDIO_H
#define K60_PMIC_GLINK_AUDIO_H
#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* The audio consumer never sees QcomGlink.h: it only hands callbacks to the
 * battery transport. Values match PongAudioStatus in PongAudioAfe.h. */
typedef struct {
    void (*state)(void *context, bool up);
    void (*receive)(void *context, const uint8_t *data, unsigned bytes);
} K60PmicGlinkAudioClient;

#define K60_PMIC_GLINK_AUDIO_OK             0
#define K60_PMIC_GLINK_AUDIO_NO_TRANSPORT (-2001)
#define K60_PMIC_GLINK_AUDIO_NO_LEASE     (-2002)
#define K60_PMIC_GLINK_AUDIO_STALE_LEASE  (-2003)
#define K60_PMIC_GLINK_AUDIO_REFUSED      (-2004)

/* The send path carries the QcomGlink result values unchanged, so the audio
 * side can retry on AGAIN without including QcomGlink.h. */
#define K60_PMIC_GLINK_AUDIO_AGAIN        (-1)
#define K60_PMIC_GLINK_AUDIO_NOT_OPEN     (-2)
#define K60_PMIC_GLINK_AUDIO_TOO_BIG      (-3)

/* Queues one adsp_apps channel on the shared two-slot transport. The workloop
 * performs the actual registration, so this call is safe from another thread.
 * Returns 0 when the request is queued, or a negative PongAudioStatus value. */
int k60_pmic_glink_attach_audio(const K60PmicGlinkAudioClient *, void *);
int k60_pmic_glink_send_audio(const uint8_t *, unsigned);
bool k60_pmic_glink_audio_ready(void);

#ifdef __cplusplus
}
#endif
#endif
