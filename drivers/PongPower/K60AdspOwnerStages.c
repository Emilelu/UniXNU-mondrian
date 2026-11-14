/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
#include "K60AdspOwnerStages.h"
#ifdef KERNEL
#include <sys/systm.h>
#else
#include <stdio.h>
#endif
static void clear_lease(K60OwnerSession *s)
{ K60AdspOwnerLease zero = {0}; s->lease = zero; }
static int result(K60OwnerSession *s, unsigned stage, int rc)
{
    printf("K60ADSP owner stage=%d rc=%d\n", (int)stage, rc);
    if (s) { s->detail = rc; if (s->ops.report) s->ops.report(s->context, stage, rc); }
    return rc;
}
static int complete_ops(const K60OwnerOps *o)
{
    return o && o->version == K60_OWNER_OPS_VERSION && o->bytes == sizeof *o &&
        o->available && o->image_reader && o->image_close && o->exclusive &&
        o->exclusive_release && o->resources && o->resources_release && o->stopped &&
        o->live && o->map_smem && o->unmap_smem && o->lock && o->unlock &&
        o->init_image && o->mem_setup && o->load && o->auth_and_reset &&
        o->shutdown && o->ready && o->report;
}
static int config_ok(const K60BatteryConfig *c)
{
    return c && c->smem_base == UINT64_C(0x80900000) && c->smem_bytes == 0x200000u &&
        c->adsp_base == UINT64_C(0x9fd00000) && c->adsp_bytes == 0x3100000u &&
        c->mutex_base == 0x1f4100cu && c->ipcc_base == 0xed18000u &&
        c->remote_pid == 2u && c->ipcc_client == 3u && !c->ipcc_signal &&
        c->desc_item == 478u && c->tx_item == 479u && c->rx_item == 480u &&
        c->smp2p_item == 443u && c->protocol == 1u;
}
static int live(K60OwnerSession *s)
{ return s->reserved && s->resources_held && s->epoch &&
    s->ops.live(s->context, s->cookie, s->epoch) == 1; }
static int take(K60OwnerSession *s)
{
    if (s->locked || s->ops.lock(s->context)) return K60_ADSP_OWNER_UNAVAILABLE;
    s->locked = 1; return 0;
}
static void drop(K60OwnerSession *s)
{ if (s->locked) { s->locked = 0; s->ops.unlock(s->context); } }
static void abort_locked(K60OwnerSession *s)
{
    if (!s || s->phase == K60OwnerPublished || s->phase == K60OwnerPoisoned ||
        s->phase == K60OwnerFailed) return;
    drop(s); clear_lease(s);
    /* AUTH failure is uncertain too: shutdown AND prove stopped before dropping
     * votes/exclusion/mappings. A poisoned session retains all recovery state. */
    if (s->reserved && ((s->auth_attempted && s->ops.shutdown(s->context)) ||
        s->ops.stopped(s->context, s->cookie) != 1)) {
        s->phase = K60OwnerPoisoned; return;
    }
    if (s->mapped) { s->ops.unmap_smem(s->context, &s->smem); s->mapped = 0; }
    if (s->image_open) { s->ops.image_close(s->context, &s->image); s->image_open = 0; }
    if (s->resources_held) { s->ops.resources_release(s->context, s->cookie); s->resources_held = 0; }
    if (s->reserved) { s->ops.exclusive_release(s->context, s->cookie); s->reserved = 0; }
    s->evidence = 0; s->phase = K60OwnerFailed;
}
static int fail(K60OwnerSession *s, unsigned stage, int rc)
{ abort_locked(s); return result(s, stage, rc); }
static int claim_locked(K60OwnerSession *s, const K60BatteryConfig *c,
    const K60OwnerOps *o, void *context)
{
    if (!s) return K60_ADSP_OWNER_UNAVAILABLE;
    if (s->phase != K60OwnerEmpty) return result(s, 1, K60_ADSP_OWNER_UNAVAILABLE);
    if (!config_ok(c) || !complete_ops(o)) {
        printf("K60ADSP owner stage=1 rc=%d%c", K60_ADSP_OWNER_UNAVAILABLE, 10);
        if (o && o->report) o->report(context, 1, K60_ADSP_OWNER_UNAVAILABLE);
        return K60_ADSP_OWNER_UNAVAILABLE;
    }
    s->ops = *o; s->config = *c; s->context = context; clear_lease(s);
    /* PAS/backend/carrier not ready: absolutely no SMEM/TCSR map or lock. */
    if (s->ops.available(context, &s->config) != 1) return fail(s, 1, K60_ADSP_OWNER_UNAVAILABLE);
    int rc = s->ops.image_reader(context, &s->image);
    if (rc) return fail(s, 1, K60_ADSP_OWNER_UNAVAILABLE);
    s->image_open = 1;
    if (!s->image.handle || !s->image.mdt || !s->image.metadata)
        return fail(s, 1, K60_ADSP_OWNER_UNAVAILABLE);
    rc = k60_adsp_mdt_prepare(s->image.mdt, s->image.bytes, c->adsp_base, c->adsp_bytes,
        s->image.piece, s->image.context, s->image.metadata, s->image.metadata_capacity, &s->image_plan);
    if (rc) return fail(s, 1, K60_ADSP_OWNER_UNAVAILABLE);
    rc = s->ops.exclusive(context, &s->config, &s->epoch, &s->cookie);
    if (rc) return fail(s, 1, K60_ADSP_OWNER_UNAVAILABLE);
    s->reserved = 1;
    if (!s->epoch || !s->cookie) return fail(s, 1, K60_ADSP_OWNER_UNAVAILABLE);
    if (s->ops.resources(context, s->cookie)) return fail(s, 1, K60_ADSP_OWNER_UNAVAILABLE);
    s->resources_held = 1; s->evidence = K60AdspResourcesHeld | K60AdspGlinkExclusive;
    /* Never force-stop or overwrite a running/unknown PAS1 just to obtain FIFOs. */
    if (!live(s) || s->ops.stopped(context, s->cookie) != 1)
        return fail(s, 1, K60_ADSP_OWNER_UNAVAILABLE);
    if (s->ops.map_smem(context, &s->config, &s->smem)) return fail(s, 1, K60_ADSP_OWNER_UNAVAILABLE);
    s->mapped = 1;
    if (!s->smem.base || ((uintptr_t)s->smem.base & 7u) ||
        s->smem.size != s->config.smem_bytes || take(s))
        return fail(s, 1, K60_ADSP_OWNER_UNAVAILABLE);
    /* A probe proves that the mutex is obtainable, not that PAS is authenticated. */
    drop(s); s->phase = K60OwnerClaimed; s->completed |= 1u;
    return result(s, 1, 0);
}
static int prepare_pas1_locked(K60OwnerSession *s)
{
    if (!s || s->phase != K60OwnerClaimed) return s ? result(s, 2, K60_ADSP_OWNER_UNAVAILABLE) : K60_ADSP_OWNER_UNAVAILABLE;
    if (!live(s) || s->ops.stopped(s->context, s->cookie) != 1)
        return fail(s, 2, K60_ADSP_OWNER_UNAVAILABLE);
    int rc = take(s);
    if (rc) return fail(s, 2, rc);
    K60SmemPartition part;
    rc = k60_smem_partition(&s->smem, 0, 2, &part);
    const uint16_t ids[3] = {478, 479, 480};
    const uint32_t sizes[3] = {32, 4096, 4096};
    /* Refuse existing host items, even all-zero ones. Never allocate SMP2P 443.
     * Partial allocator failure is not rolled back or treated as a fresh retry. */
    for (unsigned i = 0; !rc && i < 3; ++i) {
        uint32_t at, n; int found = k60_smem_find(&s->smem, &part, ids[i], &at, &n);
        if (found != K60SmemMissing) rc = found ? found : K60SmemExists;
    }
    for (unsigned i = 0; !rc && i < 3; ++i) {
        uint32_t at, n; rc = k60_smem_alloc(&s->smem, &part, ids[i], sizes[i], &at, &n);
        if (!rc && n != sizes[i]) rc = K60SmemCorrupt;
    }
    drop(s);
    if (rc) return fail(s, 2, K60_ADSP_OWNER_UNAVAILABLE);
    s->evidence |= K60AdspFreshHostFifos; s->completed |= 4u; s->phase = K60OwnerPrepared;
    return result(s, 2, 0);
}
static int auth_and_start_locked(K60OwnerSession *s)
{
    if (!s || s->phase != K60OwnerPrepared) return s ? result(s, 3, K60_ADSP_OWNER_UNAVAILABLE) : K60_ADSP_OWNER_UNAVAILABLE;
    if (!live(s) || s->ops.stopped(s->context, s->cookie) != 1)
        return fail(s, 3, K60_ADSP_OWNER_UNAVAILABLE);
    K60AdspMdtPlan *p = &s->image_plan;
    /* INIT prefix+hash once, reloc MEM_SETUP, COPY+BSS+CACHE, then AUTH.
     * The legacy K60AdspBoot copy->AUTH->INIT(payload)->MEM order is NOT reused. */
    int rc = s->ops.init_image(s->context, s->image.metadata, (size_t)p->prefix_bytes + p->hash_bytes);
    if (!rc && p->relocatable) rc = s->ops.mem_setup(s->context, p->region_base, p->span);
    for (uint32_t i = 0; !rc && i < p->count; ++i) {
        const K60AdspMdtSegment *seg = &p->segment[i];
        const uint8_t *bytes = 0; size_t n = 0;
        if (!live(s) || s->ops.stopped(s->context, s->cookie) != 1) { rc = K60_ADSP_OWNER_UNAVAILABLE; break; }
        if (seg->copy_bytes && seg->source_is_piece) {
            if (!s->image.piece || s->image.piece(s->image.context, seg->index, &bytes, &n) ||
                !bytes || n != seg->copy_bytes) { rc = K60_ADSP_OWNER_UNAVAILABLE; break; }
        } else if (seg->copy_bytes) bytes = s->image.mdt + seg->file_offset;
        rc = s->ops.load(s->context, seg->destination, bytes, seg->copy_bytes, seg->zero_bytes);
    }
    if (rc) return fail(s, 3, K60_ADSP_OWNER_UNAVAILABLE);
    if (!live(s) || s->ops.stopped(s->context, s->cookie) != 1)
        return fail(s, 3, K60_ADSP_OWNER_UNAVAILABLE);
    s->auth_attempted = 1;
    if (s->ops.auth_and_reset(s->context) || !live(s))
        return fail(s, 3, K60_ADSP_OWNER_UNAVAILABLE);
    s->evidence |= K60AdspAuthenticated; s->completed |= 8u; s->phase = K60OwnerStarted;
    /* No lease is returned until build+self-parse and all four facts succeed. */
    return result(s, 3, 0);
}
static int plan_matches(const K60OwnerSession *s, const K60HandoffPlan *p)
{
    const K60BatteryConfig *c = &s->config;
    return p && p->required == 15u && p->epoch == s->epoch && p->epoch &&
        p->smem_base == c->smem_base && p->smem_bytes == c->smem_bytes &&
        p->adsp_base == c->adsp_base && p->adsp_bytes == c->adsp_bytes &&
        p->desc_item == 478 && p->tx_item == 479 && p->rx_item == 480 &&
        p->smp2p_item == 443 && p->remote_pid == 2 && p->desc_bytes == 32 &&
        p->tx_bytes == 4096 && p->rx_bytes == 4096 && !p->host_tx_head && !p->host_rx_tail &&
        p->smp2p_bytes >= 20 && p->smp2p_bytes <= 340 && p->remote_restart_flag <= 1;
}
static int build_handoff_locked(K60OwnerSession *s, const K60HandoffPlan *p)
{
    if (!s || s->phase != K60OwnerStarted) return s ? result(s, 4, K60PublishBuildFailed) : K60PublishBuildFailed;
    if (!plan_matches(s, p) || s->evidence != 15u) return fail(s, 4, K60PublishBuildFailed);
    if (!live(s)) return fail(s, 4, K60PublishPasFailed);
    uint32_t n = 0, restart = 0;
    if (s->ops.ready(s->context, &s->config, &s->smem, &n, &restart) ||
        n != p->smp2p_bytes || restart != p->remote_restart_flag) return fail(s, 4, K60PublishNotReady);
    if (take(s)) return fail(s, 4, K60PublishLockFailed);
    K60SmemPartition part; uint32_t off[3] = {0}, bytes[3] = {0}, live_n = 0, live_restart = 0;
    int rc = k60_smem_partition(&s->smem, 0, 2, &part), code = K60PublishPartitionFailed;
    if (!rc) {
        code = K60PublishNotReady;
        rc = k60_handoff_remote_ready(&s->config, &s->smem, &part, &live_n, &live_restart);
        if (!rc && (live_n != n || live_restart != restart)) rc = -1;
    }
    const uint16_t ids[3] = {478, 479, 480}; const uint32_t sizes[3] = {32,4096,4096};
    code = rc ? code : K60PublishBuildFailed;
    for (unsigned i = 0; !rc && i < 3; ++i) {
        rc = k60_smem_find(&s->smem, &part, ids[i], &off[i], &bytes[i]);
        if (!rc && bytes[i] != sizes[i]) rc = -1;
    }
    if (!rc) for (unsigned i = 0; i < 32; ++i) if (s->smem.base[off[0] + i]) { rc = -1; code = K60PublishDirtyDescriptor; break; }
    drop(s);
    if (rc) return fail(s, 4, code);
    if (!live(s)) return fail(s, 4, K60PublishPasFailed);
    if (take(s)) return fail(s, 4, K60PublishLockFailed);
    K60AdspGlinkHandoff parsed;
    /* Final TCSR window: only existing-only serialization + self-parse. */
    rc = k60_handoff_build_existing(&s->smem, &part, p, s->blob);
    if (!rc) rc = k60_adsp_handoff_parse(s->blob, sizeof s->blob, &s->config, &parsed);
    drop(s);
    if (rc || parsed.epoch != s->epoch || parsed.flags != 15u ||
        parsed.desc_offset != off[0] || parsed.tx_offset != off[1] || parsed.rx_offset != off[2] ||
        parsed.desc_bytes != 32u || parsed.tx_bytes != 4096u || parsed.rx_bytes != 4096u ||
        parsed.remote_restart_flag != restart) return fail(s, 4, K60PublishBuildFailed);
    if (!live(s)) return fail(s, 4, K60PublishPasFailed);
    /* Internal completed bit1 means build/self-parse; public bit1 remains
     * ResourcesHeld. Never derive public ownership flags from a stage number. */
    s->completed |= 2u; s->restart = restart; s->smp2p_bytes = n; s->phase = K60OwnerBuilt;
    s->lease.version = K60_ADSP_OWNER_VERSION; s->lease.bytes = sizeof s->lease;
    s->lease.flags = s->evidence; s->lease.epoch = s->epoch; s->lease.token = s;
    return result(s, 4, 0);
}
static int publish_locked(K60OwnerSession *s, const K60OwnerPublishOps *o, void *context)
{
    if (!s || s->phase != K60OwnerBuilt || !o || !o->root_ready || !o->exists || !o->commit)
        return s ? result(s, 5, s->phase == K60OwnerPublished ? K60PublishExists : K60PublishInvalid) : K60PublishInvalid;
    if (o->root_ready(context) != 1) return fail(s, 5, K60PublishNotReady);
    if (o->exists(context)) return fail(s, 5, K60PublishExists);
    if (!live(s) || s->lease.flags != 15u || s->lease.epoch != s->epoch) return fail(s, 5, K60PublishPasFailed);
    uint32_t n = 0, restart = 0; K60AdspGlinkHandoff parsed;
    if (s->ops.ready(s->context, &s->config, &s->smem, &n, &restart) ||
        n != s->smp2p_bytes || restart != s->restart) return fail(s, 5, K60PublishNotReady);
    if (k60_adsp_handoff_parse(s->blob, sizeof s->blob, &s->config, &parsed) ||
        parsed.epoch != s->epoch || !live(s)) return fail(s, 5, K60PublishBuildFailed);
    int rc = o->commit(context, s->blob, sizeof s->blob);
    if (rc) return fail(s, 5, rc == K60PublishExists ? rc : K60PublishPropertyFailed);
    /* Commit is terminal. No abort, vote release or exclusive release thereafter. */
    s->completed |= 16u; s->phase = K60OwnerPublished; return result(s, 5, 0);
}

/* API gate spans commit AND the terminal state transition. An abort racing a
 * commit cannot shut down a newly published owner. No waiting while TCSR held. */
static int enter(K60OwnerSession *s)
{ return s && __sync_bool_compare_and_swap(&s->operation_busy, 0u, 1u); }
static int leave(K60OwnerSession *s, int rc)
{ __atomic_store_n(&s->operation_busy, 0u, __ATOMIC_RELEASE); return rc; }
int k60_owner_claim(K60OwnerSession *s, const K60BatteryConfig *c, const K60OwnerOps *o, void *x)
{ if (!enter(s)) return K60_ADSP_OWNER_UNAVAILABLE; return leave(s, claim_locked(s,c,o,x)); }
int k60_owner_prepare_pas1(K60OwnerSession *s)
{ if (!enter(s)) return K60_ADSP_OWNER_UNAVAILABLE; return leave(s, prepare_pas1_locked(s)); }
int k60_owner_auth_and_start(K60OwnerSession *s)
{ if (!enter(s)) return K60_ADSP_OWNER_UNAVAILABLE; return leave(s, auth_and_start_locked(s)); }
int k60_owner_build_handoff(K60OwnerSession *s, const K60HandoffPlan *p)
{ if (!enter(s)) return K60_ADSP_OWNER_UNAVAILABLE; return leave(s, build_handoff_locked(s,p)); }
int k60_owner_publish(K60OwnerSession *s, const K60OwnerPublishOps *o, void *x)
{ if (!enter(s)) return K60_ADSP_OWNER_UNAVAILABLE; return leave(s, publish_locked(s,o,x)); }
void k60_owner_abort(K60OwnerSession *s)
{ if (enter(s)) { abort_locked(s); (void)leave(s,0); } }
