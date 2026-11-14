/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
#include <IOKit/IOLib.h>
#include <IOKit/IOPlatformExpert.h>
#include <IOKit/IODeviceTreeSupport.h>
#include <IOKit/IORegistryEntry.h>
#include <libkern/c++/OSData.h>
#include <libkern/c++/OSSharedPtr.h>
#include <kern/clock.h>
#include "K60AdspOwner.h"
#include "K60HandoffPublish.h"
extern "C" {
extern unsigned long gPhysBase, gPhysSize;
}
namespace {
struct Context {
    IORegistryEntry *chosen;
    OSData *data;
    IOMemoryMap *smemMap, *mutexMap;
    volatile uint32_t *mutex;
    K60BatteryConfig config;
    K60AdspOwnerLease lease;
    K60Smem smem;
};
uint64_t nowUs() {
    clock_sec_t sec; clock_usec_t usec;
    clock_get_system_microtime(&sec,&usec);
    return uint64_t(sec)*1000000u+usec;
}
IOMemoryMap *map(uint64_t base,size_t bytes) {
    OSSharedPtr<IOMemoryDescriptor> d(IOMemoryDescriptor::withPhysicalAddress(base,bytes,kIODirectionInOut),OSNoRetain);
    return d ? d->map(kIOMapAnywhere|kIOMapInhibitCache) : nullptr;
}
int exists(void *p) {return static_cast<Context *>(p)->chosen->getProperty(K60_ADSP_HANDOFF_PROPERTY)!=nullptr;}
int pas(void *p) {
    auto c=static_cast<Context *>(p);
    return k60_adsp_owner_revalidate(&c->lease);
}
int lock(void *p) {
    auto c=static_cast<Context *>(p); const uint64_t began=nowUs();
    do {
        *c->mutex=1; __asm__ volatile("dsb sy" ::: "memory");
        if (*c->mutex==1) {__asm__ volatile("dmb osh" ::: "memory");return 0;}
        IODelay(10);
    } while(nowUs()-began<1000u);
    return -1;
}
void unlock(void *p) {
    auto c=static_cast<Context *>(p); __asm__ volatile("dmb osh" ::: "memory");
    if (*c->mutex==1) *c->mutex=0;
    __asm__ volatile("dsb sy" ::: "memory");
}
int ready(void *p,const K60BatteryConfig *config,const K60Smem *smem,uint32_t *bytes,uint32_t *restart) {
    const uint64_t began=nowUs();
    do {
        if (k60_adsp_owner_revalidate(&static_cast<Context *>(p)->lease)) return -1;
        if (!lock(p)) {
            K60SmemPartition part;
            int rc=k60_smem_partition(smem,0,uint16_t(config->remote_pid),&part);
            if (!rc) rc=k60_handoff_remote_ready(config,smem,&part,bytes,restart);
            unlock(p);
            if (!rc) return 0;
            if (rc==K60SmemNoTable || rc==K60SmemNoPartition || rc==K60SmemBadPartition || rc==K60SmemCorrupt) return rc;
        }
        IOSleep(20);
    } while(nowUs()-began<2000000u);
    return -1;
}
IOReturn store(OSObject *,void *arg,void *,void *,void *) {
    auto c=static_cast<Context *>(arg);
    if (c->chosen->getProperty(K60_ADSP_HANDOFF_PROPERTY)) return kIOReturnExclusiveAccess;
    return c->chosen->setProperty(K60_ADSP_HANDOFF_PROPERTY,c->data)?kIOReturnSuccess:kIOReturnError;
}
int publish(void *p,const uint8_t *blob,size_t bytes) {
    auto c=static_cast<Context *>(p); uint32_t n=0,restart=0;
    if (bytes!=K60_ADSP_HANDOFF_BYTES || k60_adsp_owner_revalidate(&c->lease)) return -1;
    /* A second bounded discovery prevents publishing a known-stale restart.
     * Neither this nor the consumer can prevent a future DSP crash. */
    if (ready(p,&c->config,&c->smem,&n,&restart) || restart!=(uint32_t(blob[96])|uint32_t(blob[97])<<8|uint32_t(blob[98])<<16|uint32_t(blob[99])<<24)) return -1;
    if (!c->data->appendBytes(blob,bytes) || c->data->getLength()!=bytes) return -1;
    K60AdspGlinkHandoff parsed;
    if (k60_adsp_handoff_parse(static_cast<const uint8_t *>(c->data->getBytesNoCopy()),bytes,&c->config,&parsed)) return -1;
    return c->chosen->runPropertyAction(store,nullptr,c)==kIOReturnSuccess?0:-1;
}
void report(const K60HandoffPublishResult &r) {
    switch(r.stage) {
    case K60PublishOk: IOLog("K60Handoff: published authenticated PAS1 epoch=%u bytes=104 flags=15 (no live FIFO writes)\n",r.epoch);break;
    case K60PublishExists: IOLog("K60Handoff: /chosen already carries k60-adsp-glink-handoff; refusing to overwrite\n");break;
    case K60PublishPasFailed: IOLog("K60Handoff: PAS1 ownership revalidation failed rc=%d; no lease published\n",r.detail);break;
    case K60PublishNotReady: IOLog("K60Handoff: SMP2P slave-kernel not ready within 2000 ms or epoch changed rc=%d; no lease published\n",r.detail);break;
    case K60PublishLockFailed: IOLog("K60Handoff: TCSR mutex timeout; refusing SMEM access\n");break;
    case K60PublishPartitionFailed: IOLog("K60Handoff: SMEM table/partition unavailable rc=%d\n",r.detail);break;
    case K60PublishDirtyDescriptor: IOLog("K60Handoff: descriptor is not an exact fresh 32-byte record rc=%d; not published\n",r.detail);break;
    default: IOLog("K60Handoff: build/self-check/publication failed stage=%d rc=%d; not published\n",r.stage,r.detail);break;
    }
}
}
extern "C" int k60_adsp_handoff_publish(void) {
    if (!k60_adsp_startup_claim(1u)) {IOLog("K60Handoff: duplicate startup attempt refused\n");return K60PublishExists;}
    Context c={}; int rc=K60PublishInvalid;
    if (k60_battery_config_parse(K60BatteryBoardConfig,K60BatteryBoardConfigBytes,&c.config)) {IOLog("K60Handoff: board config rejected; no lease published\n");return rc;}
    /* A future provider may prepare FIFO memory during acquire. Reject XNU
     * RAM overlap before invoking it, not after its first side effect. */
    if (k60_battery_range_overlaps(c.config.smem_base,c.config.smem_bytes,gPhysBase,gPhysSize) || k60_battery_range_overlaps(c.config.adsp_base,c.config.adsp_bytes,gPhysBase,gPhysSize) || k60_battery_range_overlaps(c.config.mutex_base,4,gPhysBase,gPhysSize) || k60_battery_range_overlaps(c.config.ipcc_base,4096,gPhysBase,gPhysSize)) {IOLog("K60Handoff: board resources overlap XNU RAM; no provider invoked\n");return rc;}
    c.chosen=IORegistryEntry::fromPath("/chosen",gIODTPlane);
    if (!c.chosen) {IOLog("K60Handoff: /chosen unavailable; no lease published\n");return rc;}
    if (exists(&c)) {IOLog("K60Handoff: /chosen already carries k60-adsp-glink-handoff; refusing to overwrite\n");c.chosen->release();return K60PublishExists;}
    c.data=OSData::withCapacity(K60_ADSP_HANDOFF_BYTES);
    if (!c.data) {IOLog("K60Handoff: OSData allocation failed; no lease published\n");c.chosen->release();return K60PublishPropertyFailed;}
    /* There is no audited provider in main. Do not equate the disabled legacy
     * probe's zero return value with authentication or held resource votes. */
    rc=k60_adsp_owner_acquire(&c.config,&c.lease);
    if (rc || c.lease.version!=K60_ADSP_OWNER_VERSION || c.lease.bytes!=sizeof c.lease || c.lease.flags!=K60AdspHandoffRequired || !c.lease.epoch || !c.lease.token || k60_adsp_owner_revalidate(&c.lease)) {
        IOLog("K60Handoff: PAS1 bring-up/retained ownership failed rc=%d; no lease published\n",rc);
        if (c.lease.token) k60_adsp_owner_abort(&c.lease);
        c.data->release();c.chosen->release();return K60PublishPasFailed;
    }
    {
        c.smemMap=map(c.config.smem_base,size_t(c.config.smem_bytes));c.mutexMap=map(c.config.mutex_base,4);
        if (!c.smemMap || !c.mutexMap) {IOLog("K60Handoff: SMEM/TCSR mapping failed; no lease published\n");rc=K60PublishInvalid;}
        else {
            c.smem={reinterpret_cast<volatile uint8_t *>(c.smemMap->getVirtualAddress()),uint32_t(c.config.smem_bytes)};
            c.mutex=reinterpret_cast<volatile uint32_t *>(c.mutexMap->getVirtualAddress());
            const K60HandoffPublishOps ops={exists,pas,ready,lock,unlock,publish};
            K60HandoffPublishResult result={};
            rc=k60_handoff_publish(&c.config,&c.smem,c.lease.epoch,&ops,&c,&result);report(result);
        }
    }
    if (rc) {IOLog("K60Handoff: session not published rc=%d; owner abort required\n",rc);k60_adsp_owner_abort(&c.lease);}
    if(c.mutexMap)c.mutexMap->release();if(c.smemMap)c.smemMap->release();
    c.data->release();c.chosen->release();return rc;
}
