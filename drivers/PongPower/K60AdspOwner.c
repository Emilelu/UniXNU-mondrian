/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
#include "K60AdspOwnerStages.h"
#ifdef KERNEL
#include <sys/systm.h>
#else
#include <stdio.h>
#endif
/* Persistent state outlives the runtime stack. No retry and no success release. */
static K60OwnerSession owner;
static K60OwnerOps platform;
static void *platform_context;
static unsigned configured; /* 0 absent, 1 installing, 2 installed, 3 attempted */
static int install_locked(const K60OwnerOps *ops, void *context)
{
    if (!ops || ops->version != K60_OWNER_OPS_VERSION || ops->bytes != sizeof *ops ||
        !ops->image_reader || !__sync_bool_compare_and_swap(&configured, 0u, 1u))
        return K60_ADSP_OWNER_UNAVAILABLE;
    platform = *ops; platform_context = context;
    __atomic_store_n(&configured, 2u, __ATOMIC_RELEASE); return 0;
}
static int acquire_locked(const K60BatteryConfig *config, K60AdspOwnerLease *lease)
{
    if (lease) { K60AdspOwnerLease zero = {0}; *lease = zero; }
    if (!config || !lease || !__sync_bool_compare_and_swap(&configured, 2u, 3u)) {
        printf("K60ADSP owner stage=1 rc=%d%c", K60_ADSP_OWNER_UNAVAILABLE, 10);
        return K60_ADSP_OWNER_UNAVAILABLE;
    }
    int rc = k60_owner_claim(&owner, config, &platform, platform_context);
    if (!rc) rc = k60_owner_prepare_pas1(&owner);
    if (!rc) rc = k60_owner_auth_and_start(&owner);
    if (!rc) {
        uint32_t n = 0, restart = 0;
        rc = owner.ops.ready(owner.context, &owner.config, &owner.smem, &n, &restart);
        if (!rc) {
            K60HandoffPlan plan = {15u,owner.epoch,owner.config.smem_base,(uint32_t)owner.config.smem_bytes,
                owner.config.adsp_base,(uint32_t)owner.config.adsp_bytes,478,479,480,443,2,
                32,16384,16384,n,0,0,restart};
            rc = k60_owner_build_handoff(&owner, &plan);
        } else {
            k60_owner_abort(&owner);
            printf("K60ADSP owner stage=4 rc=%d%c", K60PublishNotReady, 10);
            owner.ops.report(owner.context, 4, K60PublishNotReady); rc = K60PublishNotReady;
        }
    }
    if (rc) return rc;
    *lease = owner.lease; return 0;
}
static int same_lease(const K60AdspOwnerLease *lease)
{
    return lease && lease->token == &owner && lease->version == K60_ADSP_OWNER_VERSION &&
        lease->bytes == sizeof *lease && lease->flags == 15u && lease->epoch == owner.epoch &&
        owner.epoch && owner.lease.token == &owner && owner.lease.flags == 15u &&
        (owner.phase == K60OwnerBuilt || owner.phase == K60OwnerPublished);
}
static int revalidate_locked(const K60AdspOwnerLease *lease)
{
    if (!same_lease(lease) || !owner.reserved || !owner.resources_held ||
        owner.ops.live(owner.context, owner.cookie, owner.epoch) != 1)
        return K60_ADSP_OWNER_UNAVAILABLE;
    return 0;
}
static void abort_locked(const K60AdspOwnerLease *lease)
{
    if (same_lease(lease)) k60_owner_abort(&owner);
}
static int publish_locked(const K60AdspOwnerLease *lease, const K60OwnerPublishOps *ops, void *context)
{
    if (!same_lease(lease)) {
        printf("K60ADSP owner stage=5 rc=%d%c", K60PublishPasFailed, 10);
        return K60PublishPasFailed;
    }
    return k60_owner_publish(&owner, ops, context);
}

/* Serialize reads of token/phase as well as writes. Callback reentry refuses
 * rather than blocking; never release ownership during an in-flight commit. */
static unsigned api_busy;
static int api_enter(void) { return __sync_bool_compare_and_swap(&api_busy,0u,1u); }
static int api_leave(int rc) { __atomic_store_n(&api_busy,0u,__ATOMIC_RELEASE); return rc; }
int k60_adsp_owner_install(const K60OwnerOps *o, void *x)
{ if (!api_enter()) return K60_ADSP_OWNER_UNAVAILABLE; return api_leave(install_locked(o,x)); }
int k60_adsp_owner_acquire(const K60BatteryConfig *c, K60AdspOwnerLease *l)
{
    if (!api_enter()) { if (l) {K60AdspOwnerLease z={0};*l=z;} return K60_ADSP_OWNER_UNAVAILABLE; }
    return api_leave(acquire_locked(c,l));
}
int k60_adsp_owner_revalidate(const K60AdspOwnerLease *l)
{ if (!api_enter()) return K60_ADSP_OWNER_UNAVAILABLE; return api_leave(revalidate_locked(l)); }
void k60_adsp_owner_abort(const K60AdspOwnerLease *l)
{ if (api_enter()) {abort_locked(l);(void)api_leave(0);} }
int k60_adsp_owner_publish(const K60AdspOwnerLease *l, const K60OwnerPublishOps *o, void *x)
{ if (!api_enter()) return K60_ADSP_OWNER_UNAVAILABLE; return api_leave(publish_locked(l,o,x)); }
