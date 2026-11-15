/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
#ifndef K60_ADSP_OWNER_STAGES_H
#define K60_ADSP_OWNER_STAGES_H
#include "K60AdspOwner.h"
#include "K60AdspMdt.h"
#include "K60HandoffPublish.h"
#ifdef __cplusplus
extern "C" {
#endif
/* A reader pins immutable host buffers until image_close, including every .bNN.
 * It performs no SMEM/TCSR mapping. Lead supplies the carrier; NULL is unavailable. */
typedef struct {
    const uint8_t *mdt;
    size_t bytes;
    K60AdspMdtPiece piece;
    void *context, *handle;
    uint8_t *metadata; size_t metadata_capacity;
} K60OwnerImage;
typedef int (*k60_owner_image_reader)(void *, K60OwnerImage *);
/* All callbacks return 0 on success except available/stopped/live which return
 * exactly 1 for proven readiness/stopped/retained ownership. Failed acquisitions
 * must be transactional. available is side-effect-free and covers SCM readiness,
 * votes/reset/exclusion backends AND carrier availability, not DSP running state.
 * No default raw SMC fallback: secure callbacks own serialization, interrupted
 * resume/busy handling, coherent metadata and bounded hardware transactions. */
typedef struct {
    uint32_t version, bytes;
    int (*available)(void *, const K60BatteryConfig *);
    k60_owner_image_reader image_reader;
    void (*image_close)(void *, K60OwnerImage *);
    int (*exclusive)(void *, const K60BatteryConfig *, uint32_t *, void **);
    void (*exclusive_release)(void *, void *);
    int (*resources)(void *, void *);
    void (*resources_release)(void *, void *);
    int (*stopped)(void *, void *);
    int (*live)(void *, void *, uint32_t);
    /* Returned base must be 8-byte aligned; no physical access before available. */
    int (*map_smem)(void *, const K60BatteryConfig *, K60Smem *);
    void (*unmap_smem)(void *, K60Smem *);
    int (*lock)(void *);
    void (*unlock)(void *);
    int (*init_image)(void *, const uint8_t *, size_t);
    int (*mem_setup)(void *, uint64_t, uint64_t);
    /* Copy/zero/sync one validated segment at its relocated destination. */
    int (*load)(void *, uint64_t, const uint8_t *, uint32_t, uint32_t);
    int (*auth_and_reset)(void *);
    int (*shutdown)(void *);
    /* Bounded wait/discovery: owns short TCSR itself; sleeps only unlocked. */
    int (*ready)(void *, const K60BatteryConfig *, const K60Smem *, uint32_t *, uint32_t *);
    /* Observer called only with TCSR released, after the core emits the stage log. */
    void (*report)(void *, unsigned, int);
} K60OwnerOps;
#define K60_OWNER_OPS_VERSION 1u
enum { K60OwnerEmpty, K60OwnerClaimed, K60OwnerPrepared, K60OwnerStarted,
       K60OwnerBuilt, K60OwnerPublished, K60OwnerFailed, K60OwnerPoisoned };
typedef struct {
    K60BatteryConfig config;
    K60OwnerOps ops; void *context, *cookie;
    K60OwnerImage image; K60AdspMdtPlan image_plan;
    K60Smem smem;
    K60AdspOwnerLease lease;
    uint8_t blob[K60_HANDOFF_BYTES];
    uint32_t epoch, phase, evidence, completed, restart, smp2p_bytes;
    unsigned image_open, reserved, resources_held, mapped, locked, auth_attempted;
    int detail;
    unsigned operation_busy; /* nonblocking API serialization, not TCSR */
} K60OwnerSession;
/* Zero-initialize once. Do not copy/reset a live session. Only these APIs may
 * mutate its state; stage entry is atomically serialized and busy callers fail.
 * Session/config/ops/reader buffers must be disjoint and have persistent lifetime.
 * One software exclusive lease spans stages 2-4 AND stage-5 commit. Short TCSR
 * sections serialize stopped allocation/discovery. The final serialization section
 * performs only build_existing+self-parse: no PAS/owner callback, sleep or logging.
 * Missing PAS/backend/carrier readiness returns before SMEM/TCSR mappings (-42 at
 * runtime). Running PAS1 is refused before SMEM mapping; no forced takeover.
 * On published success there is NO release path; abort applies only to failures. */
int k60_owner_claim(K60OwnerSession *, const K60BatteryConfig *, const K60OwnerOps *, void *);
int k60_owner_prepare_pas1(K60OwnerSession *);
int k60_owner_auth_and_start(K60OwnerSession *);
int k60_owner_build_handoff(K60OwnerSession *, const K60HandoffPlan *);
typedef struct {
    int (*root_ready)(void *); /* /chosen registry root, not mounted rootfs */
    int (*exists)(void *);
    /* Atomic no-clobber commit; returns K60PublishExists on a duplicate race. */
    int (*commit)(void *, const uint8_t *, size_t);
} K60OwnerPublishOps;
int k60_owner_publish(K60OwnerSession *, const K60OwnerPublishOps *, void *);
void k60_owner_abort(K60OwnerSession *);
/* Install once, before first attempt; full production backend required. NULL
 * image reader is rejected. This is the carrier/platform integration seam. */
int k60_adsp_owner_install(const K60OwnerOps *, void *);
int k60_adsp_owner_publish(const K60AdspOwnerLease *, const K60OwnerPublishOps *, void *);
#ifdef __cplusplus
}
#endif
#endif
