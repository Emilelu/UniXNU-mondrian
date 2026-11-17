/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
#include "K60AudioGlink.h"

static void
audio_state(void *owner, QcomGlinkChannel *channel, int up)
{
    K60AudioGlink *link = (K60AudioGlink *)owner;
    (void)channel;
    if (link && link->client.state) link->client.state(link->context, up != 0);
}

static void
audio_receive(void *owner, QcomGlinkChannel *channel, const uint8_t *data, uint32_t bytes)
{
    K60AudioGlink *link = (K60AudioGlink *)owner;
    (void)channel;
    if (link && link->client.receive) link->client.receive(link->context, data, bytes);
}

void
k60_audio_glink_init(K60AudioGlink *link, QcomGlink *transport)
{
    if (!link) return;
    link->transport = transport;
    link->channel = 0;
    link->client.state = 0;
    link->client.receive = 0;
    link->context = 0;
    link->pending_bytes = 0;
    link->pending_valid = false;
    link->requested = false;
    link->attached = false;
    link->error = 0;
}

int
k60_audio_glink_request(K60AudioGlink *link, const K60PmicGlinkAudioClient *client, void *context)
{
    if (!link) return K60_PMIC_GLINK_AUDIO_REFUSED;
    if (!link->transport) return K60_PMIC_GLINK_AUDIO_NO_TRANSPORT;
    if (link->transport->broken) return K60_PMIC_GLINK_AUDIO_STALE_LEASE;
    if (!client || !client->state || !client->receive || !context)
        return K60_PMIC_GLINK_AUDIO_REFUSED;
    if (link->attached) return K60_PMIC_GLINK_AUDIO_OK;
    link->client = *client;
    link->context = context;
    __atomic_store_n(&link->requested, true, __ATOMIC_RELEASE);
    return K60_PMIC_GLINK_AUDIO_OK;
}

static int
audio_flush_pending(K60AudioGlink *link)
{
    if (!link->pending_valid) return K60_PMIC_GLINK_AUDIO_OK;
    if (!link->transport) return K60_PMIC_GLINK_AUDIO_NO_TRANSPORT;
    if (link->transport->broken) {
        link->pending_valid = false;
        link->pending_bytes = 0;
        return K60_PMIC_GLINK_AUDIO_STALE_LEASE;
    }
    if (!__atomic_load_n(&link->attached, __ATOMIC_ACQUIRE) || !link->channel)
        return K60_PMIC_GLINK_AUDIO_OK; /* keep the packet until the slot is up */
    const int rc = qcom_glink_send(link->transport, link->channel,
        link->pending, link->pending_bytes);
    if (rc == QcomGlinkOk) {
        link->pending_valid = false;
        link->pending_bytes = 0;
        return K60_PMIC_GLINK_AUDIO_OK;
    }
    if (rc == QcomGlinkAgain || rc == QcomGlinkNotOpen)
        return K60_PMIC_GLINK_AUDIO_OK; /* keep the packet for the next poll */
    link->pending_valid = false;
    link->pending_bytes = 0;
    link->error = rc;
    return rc;
}

int
k60_audio_glink_service(K60AudioGlink *link)
{
    if (!link) return K60_PMIC_GLINK_AUDIO_REFUSED;
    if (__atomic_exchange_n(&link->requested, false, __ATOMIC_ACQUIRE)) {
        if (!link->transport) return K60_PMIC_GLINK_AUDIO_NO_TRANSPORT;
        if (link->transport->broken) return K60_PMIC_GLINK_AUDIO_STALE_LEASE;
        if (!link->attached) {
            const QcomGlinkClient callbacks = {audio_state, audio_receive};
            link->channel = qcom_glink_channel(link->transport, K60_AUDIO_GLINK_NAME,
                K60_AUDIO_GLINK_INTENT_BYTES, K60_AUDIO_GLINK_INTENT_COUNT,
                link->storage, &callbacks, link, 1);
            if (!link->channel) {
                link->error = K60_PMIC_GLINK_AUDIO_REFUSED;
                return link->error;
            }
            link->attached = true;
            link->error = 0;
        }
    }
    return audio_flush_pending(link);
}

int
k60_audio_glink_send(K60AudioGlink *link, const uint8_t *data, unsigned bytes)
{
    if (!link) return K60_PMIC_GLINK_AUDIO_REFUSED;
    if (!link->transport) return K60_PMIC_GLINK_AUDIO_NO_TRANSPORT;
    if (link->transport->broken) return K60_PMIC_GLINK_AUDIO_STALE_LEASE;
    if (!data || bytes == 0) return K60_PMIC_GLINK_AUDIO_REFUSED;
    if (bytes > K60_AUDIO_GLINK_SEND_MAX) return K60_PMIC_GLINK_AUDIO_TOO_BIG;
    if (!__atomic_load_n(&link->attached, __ATOMIC_ACQUIRE) || !link->channel)
        return K60_PMIC_GLINK_AUDIO_NO_LEASE;
    if (link->pending_valid) return K60_PMIC_GLINK_AUDIO_REFUSED;
    const int rc = qcom_glink_send(link->transport, link->channel, data, bytes);
    if (rc == QcomGlinkOk) return K60_PMIC_GLINK_AUDIO_OK;
    if (rc == QcomGlinkAgain || rc == QcomGlinkNotOpen) {
        for (unsigned i = 0; i < bytes; i++) link->pending[i] = data[i];
        link->pending_bytes = bytes;
        link->pending_valid = true;
        return K60_PMIC_GLINK_AUDIO_OK; /* queued; service() retries */
    }
    return rc;
}

bool
k60_audio_glink_ready(const K60AudioGlink *link)
{
    if (!link || !__atomic_load_n(&link->attached, __ATOMIC_ACQUIRE)) return false;
    return link->channel && link->channel->up && link->transport && !link->transport->broken;
}

void
k60_audio_glink_stop(K60AudioGlink *link)
{
    if (!link) return;
    __atomic_store_n(&link->requested, false, __ATOMIC_RELEASE);
    link->pending_valid = false;
    link->pending_bytes = 0;
    link->attached = false;
    link->channel = 0;
    link->error = 0;
}
