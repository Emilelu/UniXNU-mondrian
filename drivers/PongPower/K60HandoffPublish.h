/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
#ifndef K60_HANDOFF_PUBLISH_H
#define K60_HANDOFF_PUBLISH_H
#include "K60BatteryConfig.h"
#include "K60HandoffBuild.h"
#ifdef __cplusplus
extern "C" {
#endif
enum { K60PublishOk=0, K60PublishInvalid=-40, K60PublishExists=-41,
    K60PublishPasFailed=-42, K60PublishNotReady=-43, K60PublishLockFailed=-44,
    K60PublishPartitionFailed=-45, K60PublishDirtyDescriptor=-46,
    K60PublishBuildFailed=-47, K60PublishPropertyFailed=-48 };
/* pas must return zero ONLY for authenticated PAS1 with resources retained and
 * exclusive GLINK ownership. A disabled/skipped probe is NOT success. The
 * publisher never converts an enable argument into an ownership assertion. */
typedef struct {
    int (*exists)(void *);
    int (*pas)(void *);
    int (*ready)(void *, const K60BatteryConfig *, const K60Smem *, uint32_t *, uint32_t *);
    int (*lock)(void *);
    void (*unlock)(void *);
    int (*publish)(void *, const uint8_t *, size_t);
} K60HandoffPublishOps;
typedef struct { int stage, detail; uint32_t epoch; } K60HandoffPublishResult;
/* Read-only live SMP2P check; caller owns any required discovery mutex. */
int k60_handoff_remote_ready(const K60BatteryConfig *, const K60Smem *,
    const K60SmemPartition *, uint32_t *, uint32_t *);
int k60_handoff_publish(const K60BatteryConfig *, const K60Smem *, uint32_t,
    const K60HandoffPublishOps *, void *, K60HandoffPublishResult *);
#ifdef __cplusplus
}
#endif
#endif
