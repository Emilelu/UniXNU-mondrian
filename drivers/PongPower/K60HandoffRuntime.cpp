/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
#include <IOKit/IOLib.h>
#include <IOKit/IODeviceTreeSupport.h>
#include <IOKit/IORegistryEntry.h>
#include <libkern/c++/OSData.h>
#include "K60AdspOwnerStages.h"
#include "K60AdspPlatform.h"
#include "K60AdspBoard.h"
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
/* The board ownership service this boot installs. File scope so the lease and
 * its read-only SMEM window outlive this call for the whole boot; the ownership
 * table handed to the platform points at this object, so the address is stable. */
static K60AdspBoard board;

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
    /* Install only after RAM/registry preflight, board ownership first: native
     * available() reads exactly 1 only once our own board service is installed,
     * so the platform would otherwise stay unavailable before SMEM/TCSR. Each
     * step logs its own line, so a device run separates "not installed" from
     * "install failed". */
    int board_init=k60_adsp_board_init(&board,k60_adsp_board_platform_io());
    if (board_init!=K60BoardOk) {
        IOLog("K60Handoff: board ownership init failed rc=%d; nothing installed%c",board_init,10);
        c.data->release();c.chosen->release();
        return K60PublishNotReady;
    }
    IOLog("K60Handoff: board ownership init ok rc=0%c",10);
    int ownership=k60_adsp_platform_ownership_install(k60_adsp_board_ownership(&board),&board);
    if (ownership!=0 && ownership!=1) {
        IOLog("K60Handoff: board ownership install failed rc=%d; platform not installed%c",ownership,10);
        c.data->release();c.chosen->release();
        return K60PublishNotReady;
    }
    IOLog("K60Handoff: board ownership installed rc=%d%c",ownership,10);
    int installed=k60_adsp_platform_install();
    IOLog("K60Handoff: platform installed rc=%d%c",installed,10);
    int rc=installed<0?installed:k60_adsp_owner_acquire(&c.config,&lease);
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
