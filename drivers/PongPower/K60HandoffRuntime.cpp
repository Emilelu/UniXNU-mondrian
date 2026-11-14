/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
#include <IOKit/IOLib.h>
#include <IOKit/IODeviceTreeSupport.h>
#include <IOKit/IORegistryEntry.h>
#include <libkern/c++/OSData.h>
#include "K60AdspOwnerStages.h"
extern "C" { extern unsigned long gPhysBase, gPhysSize; }
namespace {
struct Context { IORegistryEntry *chosen; OSData *data; K60BatteryConfig config; };
int root(void *p) { return static_cast<Context *>(p)->chosen != nullptr; }
int exists(void *p) { return static_cast<Context *>(p)->chosen->getProperty(K60_ADSP_HANDOFF_PROPERTY) != nullptr; }
IOReturn store(OSObject *,void *arg,void *,void *,void *) {
    auto c=static_cast<Context *>(arg);
    if (exists(c)) return kIOReturnExclusiveAccess;
    return c->chosen->setProperty(K60_ADSP_HANDOFF_PROPERTY,c->data)?kIOReturnSuccess:kIOReturnError;
}
int commit(void *p,const uint8_t *blob,size_t bytes) {
    auto c=static_cast<Context *>(p); K60AdspGlinkHandoff parsed;
    if (bytes!=K60_ADSP_HANDOFF_BYTES ||
        !c->data->appendBytes(blob,bytes) || c->data->getLength()!=bytes ||
        k60_adsp_handoff_parse(static_cast<const uint8_t *>(c->data->getBytesNoCopy()),bytes,&c->config,&parsed))
        return K60PublishPropertyFailed;
    /* Atomic no-clobber registry commit, with all TCSR locks released. */
    IOReturn rc=c->chosen->runPropertyAction(store,nullptr,c);
    return rc==kIOReturnSuccess?0:rc==kIOReturnExclusiveAccess?K60PublishExists:K60PublishPropertyFailed;
}
}
extern "C" int k60_adsp_handoff_publish(void) {
    if (!k60_adsp_startup_claim(1u)) return K60PublishExists;
    Context c={}; K60AdspOwnerLease lease={};
    if (k60_battery_config_parse(K60BatteryBoardConfig,K60BatteryBoardConfigBytes,&c.config))
        return K60PublishInvalid;
    /* Reject XNU RAM overlap before the installed provider first has effects. */
    if (k60_battery_range_overlaps(c.config.smem_base,c.config.smem_bytes,gPhysBase,gPhysSize) ||
        k60_battery_range_overlaps(c.config.adsp_base,c.config.adsp_bytes,gPhysBase,gPhysSize) ||
        k60_battery_range_overlaps(c.config.mutex_base,4,gPhysBase,gPhysSize) ||
        k60_battery_range_overlaps(c.config.ipcc_base,4096,gPhysBase,gPhysSize)) return K60PublishInvalid;
    c.chosen=IORegistryEntry::fromPath("/chosen",gIODTPlane);
    if (!c.chosen) return K60PublishNotReady;
    if (exists(&c)) {c.chosen->release();return K60PublishExists;}
    c.data=OSData::withCapacity(K60_ADSP_HANDOFF_BYTES);
    if (!c.data) {c.chosen->release();return K60PublishPropertyFailed;}
    /* No backend/image_reader installed => -1000 before SMEM/TCSR mapping.
     * Stages 1-4 own preparation, PAS, discovery, build and self-parse. */
    int rc=k60_adsp_owner_acquire(&c.config,&lease);
    if (rc || k60_adsp_owner_revalidate(&lease)) {
        IOLog("K60Handoff: PAS1 bring-up/retained ownership failed rc=%d; no lease published%c",rc,10);
        if (lease.token) k60_adsp_owner_abort(&lease);
        rc=K60PublishPasFailed;
    } else {
        const K60OwnerPublishOps ops={root,exists,commit};
        rc=k60_adsp_owner_publish(&lease,&ops,&c);
        if (rc) k60_adsp_owner_abort(&lease);
        else IOLog("K60Handoff: published authenticated PAS1 epoch=%u bytes=104 flags=15%c",lease.epoch,10);
    }
    c.data->release();c.chosen->release();return rc;
}
