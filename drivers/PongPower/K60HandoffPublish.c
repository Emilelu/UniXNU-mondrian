/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
#include "K60HandoffPublish.h"
static uint32_t rd(const K60Smem *s, uint32_t at)
{ return *(volatile uint32_t *)(s->base + at); }
static void acquire(void)
{
#if defined(__aarch64__) && defined(KERNEL)
    __asm__ volatile("dmb osh" ::: "memory");
#endif
}
int k60_handoff_remote_ready(const K60BatteryConfig *c, const K60Smem *s,
    const K60SmemPartition *p, uint32_t *bytes, uint32_t *restart)
{
    uint32_t off, n;
    if (!c || !s || !p || !bytes || !restart ||
        k60_smem_find(s,p,(uint16_t)c->smp2p_item,&off,&n) ||
        (off & 3u) || n < 20u || n > 340u) return K60PublishNotReady;
    if (rd(s,off)!=0x504d5324u || (rd(s,off+4)&255u)!=1u ||
        rd(s,off+8)!=c->remote_pid) return K60PublishNotReady;
    const uint32_t count=rd(s,off+12), total=count&65535u, valid=count>>16;
    acquire();
    if (total>16u || valid>total || 20u+valid*20u>n) return K60PublishNotReady;
    static const uint8_t name[16]="slave-kernel";
    for (uint32_t i=0;i<valid;i++) {
        unsigned j=0;
        for (;j<16;j++) if (s->base[off+20u+i*20u+j]!=name[j]) break;
        if (j==16) {
            const uint32_t state=rd(s,off+36u+i*20u);
            if (!(state&2u) || (state&1u)) return K60PublishNotReady;
            *bytes=n; *restart=rd(s,off+16)&1u; acquire(); return 0;
        }
    }
    return K60PublishNotReady;
}
static int finish(K60HandoffPublishResult *r,int stage,int detail)
{ if (r) { r->stage=stage; r->detail=detail; } return stage; }
int k60_handoff_publish(const K60BatteryConfig *c,const K60Smem *s,uint32_t epoch,
    const K60HandoffPublishOps *o,void *ctx,K60HandoffPublishResult *r)
{
    uint8_t blob[K60_ADSP_HANDOFF_BYTES];
    uint32_t n=0,restart=0,off=0,bytes=0,live_n=0,live_restart=0;
    K60SmemPartition part;
    K60AdspGlinkHandoff parsed;
    int rc,stage;
    if (r) { r->stage=K60PublishInvalid; r->detail=0; r->epoch=epoch; }
    if (!c || !s || !s->base || !epoch || !o || !o->exists || !o->pas ||
        !o->ready || !o->lock || !o->unlock || !o->publish ||
        c->smem_bytes!=s->size || c->smem_bytes>0xffffffffu ||
        c->adsp_bytes>0xffffffffu || c->remote_pid!=2 || c->protocol!=1 ||
        c->desc_item!=478 || c->tx_item!=479 || c->rx_item!=480 || c->smp2p_item!=443)
        return finish(r,K60PublishInvalid,0);
    if (o->exists(ctx)) return finish(r,K60PublishExists,0);
    rc=o->pas(ctx); if (rc) return finish(r,K60PublishPasFailed,rc);
    rc=o->ready(ctx,c,s,&n,&restart);
    if (rc || n<20u || n>340u || restart>1u) return finish(r,K60PublishNotReady,rc);
    rc=o->lock(ctx); if (rc) return finish(r,K60PublishLockFailed,rc);
    stage=K60PublishPartitionFailed;
    rc=k60_smem_partition(s,0,(uint16_t)c->remote_pid,&part);
    if (rc) goto unlock;
    /* Recheck readiness and epoch under the allocation mutex. Never allocate
     * item 443 to manufacture readiness and never reset an existing ring. */
    stage=K60PublishNotReady;
    rc=k60_handoff_remote_ready(c,s,&part,&live_n,&live_restart);
    if (rc || live_n!=n || live_restart!=restart) { if (!rc) rc=-1; goto unlock; }
    rc=k60_smem_find(s,&part,(uint16_t)c->desc_item,&off,&bytes);
    stage=K60PublishDirtyDescriptor;
    if (!rc) {
        if (bytes!=32u) {rc=-1; goto unlock;}
        for (uint32_t i=0;i<32u;i++) if (s->base[off+i]) {rc=-1; goto unlock;}
    } else if (rc!=K60SmemMissing) goto unlock;
    K60HandoffPlan plan={K60AdspHandoffRequired,epoch,c->smem_base,(uint32_t)c->smem_bytes,
        c->adsp_base,(uint32_t)c->adsp_bytes,(uint16_t)c->desc_item,(uint16_t)c->tx_item,
        (uint16_t)c->rx_item,(uint16_t)c->smp2p_item,(uint16_t)c->remote_pid,
        32u,4096u,4096u,n,0,0,restart};
    stage=K60PublishBuildFailed;
    /* FIFO preparation belongs to the stopped-DSP PAS owner, not this live
     * publication path. Missing items are a dependency failure, never allocation. */
    rc=k60_handoff_build_existing(s,&part,&plan,blob);
    if (!rc) rc=k60_adsp_handoff_parse(blob,sizeof blob,c,&parsed);
    /* Consumer demands exact item sizes; reject a previously allocated larger
     * ring rather than publish a lease the consumer cannot adopt. */
    const uint16_t ids[3]={(uint16_t)c->desc_item,(uint16_t)c->tx_item,(uint16_t)c->rx_item};
    const uint32_t want[3]={32u,4096u,4096u};
    for (unsigned i=0;!rc && i<3;i++) {
        rc=k60_smem_find(s,&part,ids[i],&off,&bytes);
        if (!rc && bytes!=want[i]) rc=-1;
    }
unlock:
    o->unlock(ctx);
    if (rc) return finish(r,stage,rc);
    /* The property callback also rejects a duplicate; no OSData while locked. */
    rc=o->publish(ctx,blob,sizeof blob);
    return finish(r,rc?K60PublishPropertyFailed:K60PublishOk,rc);
}
