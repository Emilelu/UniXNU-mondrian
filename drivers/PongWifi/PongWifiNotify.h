/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#ifndef PONG_WIFI_NOTIFY_H
#define PONG_WIFI_NOTIFY_H
#include <stdint.h>
#include <stdbool.h>

/* Protected by the network driver's lock. Producers never deliver socket
 * or ifnet events from the cooperative firmware dispatcher. */
struct pong_wifi_notification {
    uint32_t kind;
    int32_t result, rssi;
    uint32_t keyed;
};
#define PONG_WIFI_NOTIFY_CAPACITY 32
struct pong_wifi_notification_queue {
    struct pong_wifi_notification entries[PONG_WIFI_NOTIFY_CAPACITY];
    unsigned first, count;
};
static inline bool pong_wifi_notification_push(struct pong_wifi_notification_queue *q,
                                              struct pong_wifi_notification event)
{
    if (q->count == PONG_WIFI_NOTIFY_CAPACITY) return false;
    q->entries[(q->first + q->count) % PONG_WIFI_NOTIFY_CAPACITY] = event;
    ++q->count;
    return true;
}
static inline bool pong_wifi_notification_pop(struct pong_wifi_notification_queue *q,
                                             struct pong_wifi_notification *event)
{
    if (!q->count) return false;
    *event = q->entries[q->first];
    q->first = (q->first + 1) % PONG_WIFI_NOTIFY_CAPACITY;
    --q->count;
    return true;
}
static inline void pong_wifi_notification_reset(struct pong_wifi_notification_queue *q)
{
    q->first = q->count = 0;
}
#endif
