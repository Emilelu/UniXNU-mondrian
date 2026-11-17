/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
#include "K60AdspPlatform.h"
#ifdef KERNEL
#include <sys/systm.h>
#else
#include <stdio.h>
#endif
#define UNAVAILABLE K60_ADSP_OWNER_UNAVAILABLE
static int complete(const K60AdspPlatformServices *s)
{
    return s && s->version==K60_ADSP_PLATFORM_VERSION && s->bytes==sizeof *s &&
        s->available && s->exclusive && s->exclusive_release && s->resources &&
        s->resources_release && s->stopped && s->live && s->map && s->unmap &&
        s->sync && s->lock && s->unlock && s->init_image && s->mem_setup &&
        s->auth_and_reset && s->shutdown && s->delay_us;
}
static void event(const char *name, int rc)
{ printf("K60ADSP platform %s rc=%d%c",name,rc,10); }
static int valid(K60AdspPlatform *p)
{ return p && p->initialized && complete(&p->services); }
static int owned(K60AdspPlatform *p)
{ return valid(p) && p->reserved && p->resources_held && p->cookie && p->epoch &&
    p->services.live(p->service_context,p->cookie,p->epoch)==1; }
static int stopped(K60AdspPlatform *p)
{ return p->services.stopped(p->service_context,p->cookie)==1; }
int k60_adsp_platform_init(K60AdspPlatform *p,const K60AdspPlatformServices *s,
    void *context,const K60AdspReader *reader)
{
    if (!p || p->initialized || (s && !complete(s))) return UNAVAILABLE;
    /* Initialization has no physical effects; a missing carrier stays unavailable.
     * Caller supplies zeroed, disjoint state and persistent services/context. */
    int rc=reader ? k60_adsp_owner_reader_init(&p->reader,reader,p->metadata,sizeof p->metadata) :
        k60_adsp_owner_reader_linked(&p->reader,p->metadata,sizeof p->metadata);
    if (s) p->services=*s;
    p->service_context=context; p->initialized=1;
    return rc; /* install still registers unavailable ops for a carrier failure */
}
static int available(void *ctx,const K60BatteryConfig *c)
{
    K60AdspPlatform *p=ctx;
    return c && valid(p) && !p->locked && p->reader.source.mode &&
        p->services.available(p->service_context,c)==1;
}
static int image_reader(void *ctx,K60OwnerImage *image)
{
    K60AdspPlatform *p=ctx;
    if (!valid(p) || p->locked) return UNAVAILABLE;
    int rc=k60_adsp_owner_image_open(&p->reader,image);
    event("image_reader",rc); return rc;
}
static void image_close(void *ctx,K60OwnerImage *image)
{
    K60AdspPlatform *p=ctx;
    if (!p || p->locked) return;
    k60_adsp_owner_image_close(&p->reader,image); event("image_close",0);
}
static int exclusive(void *ctx,const K60BatteryConfig *c,uint32_t *epoch,void **cookie)
{
    K60AdspPlatform *p=ctx; uint32_t e=0; void *token=0;
    if (!p || p->locked || !epoch || !cookie || !available(p,c) || p->reserved) return UNAVAILABLE;
    int rc=p->services.exclusive(p->service_context,c,&e,&token);
    if (!rc && (!e || !token)) {
        if (token) p->services.exclusive_release(p->service_context,token);
        rc=UNAVAILABLE;
    }
    if (!rc) {p->config=*c;p->cookie=token;p->epoch=e;p->reserved=1;*epoch=e;*cookie=token;}
    event("exclusive",rc); return rc;
}
static void exclusive_release(void *ctx,void *cookie)
{
    K60AdspPlatform *p=ctx;
    if (!valid(p) || !p->reserved || cookie!=p->cookie || p->locked || p->resources_held ||
        p->smem.handle || p->mutex.handle) return;
    p->services.exclusive_release(p->service_context,cookie);
    p->cookie=0;p->epoch=0;p->reserved=0;p->image_initialized=0;
    event("exclusive_release",0);
}
static int resources(void *ctx,void *cookie)
{
    K60AdspPlatform *p=ctx;
    if (!valid(p) || p->locked || !p->reserved || cookie!=p->cookie || p->resources_held) return UNAVAILABLE;
    int rc=p->services.resources(p->service_context,cookie);
    if (!rc) p->resources_held=1;
    event("resources",rc); return rc;
}
static void resources_release(void *ctx,void *cookie)
{
    K60AdspPlatform *p=ctx;
    if (!valid(p) || !p->resources_held || cookie!=p->cookie || p->locked ||
        p->smem.handle || p->mutex.handle) return;
    p->services.resources_release(p->service_context,cookie);p->resources_held=0;
    event("resources_release",0);
}
static int stopped_cb(void *ctx,void *cookie)
{
    K60AdspPlatform *p=ctx;
    return valid(p) && !p->locked && p->reserved && p->cookie==cookie && stopped(p);
}
static int live(void *ctx,void *cookie,uint32_t epoch)
{
    K60AdspPlatform *p=ctx;
    return p && !p->locked && cookie==p->cookie && epoch==p->epoch && owned(p);
}
static void release_map(K60AdspPlatform *p,K60AdspPlatformMapping *m)
{
    if (m->handle || m->base) p->services.unmap(p->service_context,m);
    K60AdspPlatformMapping zero={0};*m=zero;
}
static int mapping_ok(const K60AdspPlatformMapping *m,size_t n,unsigned alignment)
{
    return m->base && m->handle && m->bytes==n && !((uintptr_t)m->base&(alignment-1u)) &&
        n<=UINTPTR_MAX-(uintptr_t)m->base;
}
static int map_smem(void *ctx,const K60BatteryConfig *c,K60Smem *s)
{
    K60AdspPlatform *p=ctx;
    if (!p || p->locked || !s || !c || !owned(p) || !stopped(p) || p->smem.handle || p->mutex.handle ||
        c->smem_base!=p->config.smem_base || c->smem_bytes!=p->config.smem_bytes ||
        c->mutex_base!=p->config.mutex_base || c->smem_bytes>UINT32_MAX) return UNAVAILABLE;
    int rc=p->services.map(p->service_context,c->smem_base,(size_t)c->smem_bytes,K60AdspMapShared,&p->smem);
    if (!rc && !mapping_ok(&p->smem,(size_t)c->smem_bytes,8u)) rc=UNAVAILABLE;
    if (!rc) rc=p->services.map(p->service_context,c->mutex_base,4u,K60AdspMapDevice,&p->mutex);
    if (!rc && !mapping_ok(&p->mutex,4u,4u)) rc=UNAVAILABLE;
    if (rc) {release_map(p,&p->mutex);release_map(p,&p->smem);}
    else {s->base=p->smem.base;s->size=(uint32_t)p->smem.bytes;}
    event("map_smem",rc);return rc;
}
static void unmap_smem(void *ctx,K60Smem *s)
{
    K60AdspPlatform *p=ctx;
    if (!valid(p) || p->locked) return;
    release_map(p,&p->mutex);release_map(p,&p->smem);
    if (s) {s->base=0;s->size=0;} event("unmap_smem",0);
}
static int lock(void *ctx)
{
    K60AdspPlatform *p=ctx;
    if (!p || p->locked || !owned(p) || !p->mutex.handle) return UNAVAILABLE;
    int rc=p->services.lock(p->service_context,&p->mutex);
    if (!rc) p->locked=1;
    return rc; /* never log within a TCSR section */
}
static void unlock(void *ctx)
{
    K60AdspPlatform *p=ctx;
    if (valid(p) && p->locked) {p->services.unlock(p->service_context,&p->mutex);p->locked=0;}
}
static int init_image(void *ctx,const uint8_t *bytes,size_t n)
{
    K60AdspPlatform *p=ctx;
    if (!p || p->locked || !owned(p) || !stopped(p) || p->image_initialized ||
        bytes!=p->metadata || !n || n>sizeof p->metadata) return UNAVAILABLE;
    int rc=p->services.init_image(p->service_context,bytes,n);
    if (!rc) p->image_initialized=1;
    event("init_image",rc);return rc;
}
static int mem_setup(void *ctx,uint64_t base,uint64_t span)
{
    K60AdspPlatform *p=ctx;
    if (!p || p->locked || !owned(p) || !stopped(p) || !p->image_initialized ||
        base!=p->config.adsp_base || !span || span>p->config.adsp_bytes) return UNAVAILABLE;
    int rc=p->services.mem_setup(p->service_context,base,span);event("mem_setup",rc);return rc;
}
static int load(void *ctx,uint64_t dest,const uint8_t *src,uint32_t copy,uint32_t zero)
{
    K60AdspPlatform *p=ctx;uint64_t total=(uint64_t)copy+zero;
    if (!p || p->locked || !owned(p) || !stopped(p) || !p->image_initialized || !total ||
        dest<p->config.adsp_base || total>p->config.adsp_bytes ||
        dest-p->config.adsp_base>p->config.adsp_bytes-total ||
        (copy && (!src || copy>UINTPTR_MAX-(uintptr_t)src))) return UNAVAILABLE;
    int rc=0;uint64_t at=0;
    while (at<total) {
        if (!owned(p) || !stopped(p)) {rc=UNAVAILABLE;break;}
        size_t n=(size_t)(total-at);
        if (n>K60_ADSP_PLATFORM_WINDOW_BYTES) n=K60_ADSP_PLATFORM_WINDOW_BYTES;
        K60AdspPlatformMapping m={0};
        rc=p->services.map(p->service_context,dest+at,n,K60AdspMapFirmware,&m);
        if (!rc && !mapping_ok(&m,n,1u)) rc=UNAVAILABLE;
        if (!rc) {
            for (size_t i=0;i<n;i++) {uint64_t index=at+i;m.base[i]=index<copy?src[(size_t)index]:0;}
            rc=p->services.sync(p->service_context,&m,0,n);
        }
        release_map(p,&m);if (rc) break;at+=n;
    }
    event("load",rc);return rc;
}
static int auth_and_reset(void *ctx)
{
    K60AdspPlatform *p=ctx;
    if (!p || p->locked || !owned(p) || !stopped(p) || !p->image_initialized) return UNAVAILABLE;
    int rc=p->services.auth_and_reset(p->service_context);event("auth_and_reset",rc);return rc;
}
static int shutdown(void *ctx)
{
    K60AdspPlatform *p=ctx;
    if (!valid(p) || p->locked || !p->reserved || !p->resources_held) return UNAVAILABLE;
    int rc=p->services.shutdown(p->service_context);event("shutdown",rc);return rc;
}
static int same_config(const K60BatteryConfig *a,const K60BatteryConfig *b)
{
    return a->smem_base==b->smem_base && a->smem_bytes==b->smem_bytes &&
        a->ipcc_base==b->ipcc_base && a->mutex_base==b->mutex_base &&
        a->adsp_base==b->adsp_base && a->adsp_bytes==b->adsp_bytes &&
        a->remote_pid==b->remote_pid && a->ipcc_client==b->ipcc_client && a->ipcc_signal==b->ipcc_signal &&
        a->desc_item==b->desc_item && a->tx_item==b->tx_item && a->rx_item==b->rx_item &&
        a->smp2p_item==b->smp2p_item && a->protocol==b->protocol &&
        a->charging_current_sign==b->charging_current_sign;
}
static int ready(void *ctx,const K60BatteryConfig *c,const K60Smem *s,uint32_t *bytes,uint32_t *restart)
{
    K60AdspPlatform *p=ctx;
    if (!p || p->locked || !c || !s || !bytes || !restart || !same_config(c,&p->config) || !owned(p) ||
        s->base!=p->smem.base || s->size!=p->smem.bytes) return UNAVAILABLE;
    int rc=K60PublishNotReady;
    for (unsigned i=0;i<1000u;i++) {
        if (!owned(p) || lock(p)) {rc=UNAVAILABLE;break;}
        K60SmemPartition part;uint32_t n=0,r=0;
        rc=k60_smem_partition(s,0,(uint16_t)c->remote_pid,&part);
        if (!rc) rc=k60_handoff_remote_ready(c,s,&part,&n,&r);
        unlock(p);
        if (!rc) {*bytes=n;*restart=r;break;}
        if (i+1u<1000u) p->services.delay_us(p->service_context,1000u);
    }
    event("ready",rc);return rc;
}
static void report(void *ctx,unsigned stage,int rc)
{
    K60AdspPlatform *p=ctx;
    if (!p || p->locked) return;
    printf("K60ADSP platform stage=%u rc=%d ops_complete=%u carrier=%u%c",stage,rc,
        (unsigned)valid(p),(unsigned)(p->reader.source.mode!=0),10);
}
static const K60OwnerOps ops={K60_OWNER_OPS_VERSION,sizeof(K60OwnerOps),
    available,image_reader,image_close,exclusive,exclusive_release,resources,resources_release,
    stopped_cb,live,map_smem,unmap_smem,lock,unlock,init_image,mem_setup,load,auth_and_reset,
    shutdown,ready,report};
const K60OwnerOps *k60_adsp_platform_ops(void) {return &ops;}
#ifndef KERNEL
#if defined(__APPLE__)
#define OPTIONAL __attribute__((weak_import))
#else
#define OPTIONAL __attribute__((weak))
#endif
extern const K60AdspPlatformServices *k60_adsp_platform_native_services(void) OPTIONAL;
extern void *k60_adsp_platform_native_context(void) OPTIONAL;
#endif
static K60AdspPlatform platform;
static unsigned installation;
int k60_adsp_platform_install(void)
{
    if (__atomic_load_n(&installation,__ATOMIC_ACQUIRE)==2u) return 1;
    if (!__sync_bool_compare_and_swap(&installation,0u,1u)) return UNAVAILABLE;
    const K60AdspPlatformServices *s=0;void *ctx=0;
#ifdef KERNEL
    s=k60_adsp_platform_native_services();ctx=k60_adsp_platform_native_context();
#else
    if (k60_adsp_platform_native_services && k60_adsp_platform_native_context) {
        s=k60_adsp_platform_native_services();ctx=k60_adsp_platform_native_context();
    }
#endif
    int carrier=k60_adsp_platform_init(&platform,s,ctx,0);
    int rc=platform.initialized?k60_adsp_owner_install(&ops,&platform):UNAVAILABLE;
    __atomic_store_n(&installation,rc?3u:2u,__ATOMIC_RELEASE);
    printf("K60ADSP platform install rc=%d carrier_rc=%d ops_complete=%u%c",rc,carrier,(unsigned)valid(&platform),10);
    return rc;
}
