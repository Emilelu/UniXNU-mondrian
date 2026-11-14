/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
#ifndef K60_ADSP_OWNER_H
#define K60_ADSP_OWNER_H
#include "K60BatteryConfig.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Platform/audio owner API, deliberately NOT implemented by a raw PAS probe.
 * acquire must prepare fresh host FIFOs while PAS1 is stopped, authenticate and
 * start PAS1, retain power/XO/interconnect votes, and exclude every other GLINK
 * worker/reset path. The token and epoch bind this exact board/config, item
 * geometry and current boot. Ownership is pinned until explicit abort; no
 * reset/restart, GLINK activity, vote release or token expiry is allowed in
 * unlocked intervals. On successful publication it stays retained indefinitely.
 * revalidate must be nonblocking/read-only; abort must quiesce the provider on
 * failure. Success transfers GLINK only, never drops the resource votes.
 * The default compiled provider returns UNAVAILABLE before physical mapping.
 * Replacing it requires an audited implementation of this entire contract. */
typedef struct {
    uint32_t version, bytes, flags, epoch;
    void *token;
} K60AdspOwnerLease;
#define K60_ADSP_OWNER_VERSION 1u
#define K60_ADSP_OWNER_UNAVAILABLE (-1000)
int k60_adsp_owner_acquire(const K60BatteryConfig *, K60AdspOwnerLease *);
int k60_adsp_owner_revalidate(const K60AdspOwnerLease *);
void k60_adsp_owner_abort(const K60AdspOwnerLease *);
/* The early attempt supersedes the unsafe late diagnostic loader, even on error. */
int k60_adsp_handoff_owner_active(void);
/* Shared atomic arbitration: 1=early handoff, 2=late diagnostic. No release. */
int k60_adsp_startup_claim(unsigned owner);
int k60_adsp_handoff_publish(void);
#ifdef __cplusplus
}
#endif
#endif
