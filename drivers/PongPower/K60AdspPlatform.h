/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
#ifndef K60_ADSP_PLATFORM_H
#define K60_ADSP_PLATFORM_H
#include "K60AdspImageReader.h"
#ifdef __cplusplus
extern "C" {
#endif
#define K60_ADSP_PLATFORM_VERSION 1u
#define K60_ADSP_PLATFORM_METADATA_BYTES 65536u
#define K60_ADSP_PLATFORM_WINDOW_BYTES 262144u
enum { K60AdspMapShared, K60AdspMapDevice, K60AdspMapFirmware };
typedef struct {
    volatile uint8_t *base;
    size_t bytes;
    void *handle;
} K60AdspPlatformMapping;
/* Persistent board services. These are facts/leases, never inferred from a boot
 * argument, startup CAS, successful SHUTDOWN, or a discovered RPMh address.
 * Failed acquire callbacks must roll back internally; successful releases cannot
 * fail. available/live/stopped are read-only and return exactly 1 for proof.
 * exclusive excludes reset/restart and competing GLINK/PAS owners until its
 * exclusive_release, including after resources_release; no callback may reenter.
 * live proves the retained token independently of resource acquisition. stopped
 * independently proves stopped state, stable under that exclusion until an
 * explicit owner PAS/start action. resources retains power/XO/interconnect.
 * scm_lock covers ALL SCM clients and the entire resumed/busy transaction. */
typedef struct {
    uint32_t version, bytes;
    int (*available)(void *, const K60BatteryConfig *);
    int (*exclusive)(void *, const K60BatteryConfig *, uint32_t *, void **);
    void (*exclusive_release)(void *, void *);
    int (*resources)(void *, void *);
    void (*resources_release)(void *, void *);
    int (*stopped)(void *, void *);
    int (*live)(void *, void *, uint32_t);
    int (*scm_lock)(void *);
    void (*scm_unlock)(void *);
} K60AdspPlatformOwnership;
/* map failure leaves no mapping; sync completes writes to the point of coherency
 * before return. Firmware mappings are bounded, normal/write-combine memory,
 * never device memory. PAS init owns a coherent physically contiguous metadata
 * buffer until safe exclusive release, including terminal preAUTH errors; a PAS
 * failure may be uncertain. Native implements
 * serialization/resume/busy/metadata, tests inject explicit fake services. */
typedef struct {
    uint32_t version, bytes;
    int (*available)(void *, const K60BatteryConfig *);
    int (*exclusive)(void *, const K60BatteryConfig *, uint32_t *, void **);
    void (*exclusive_release)(void *, void *);
    int (*resources)(void *, void *);
    void (*resources_release)(void *, void *);
    int (*stopped)(void *, void *);
    int (*live)(void *, void *, uint32_t);
    int (*map)(void *, uint64_t, size_t, unsigned, K60AdspPlatformMapping *);
    void (*unmap)(void *, K60AdspPlatformMapping *);
    int (*sync)(void *, const K60AdspPlatformMapping *, size_t, size_t);
    int (*lock)(void *, const K60AdspPlatformMapping *);
    void (*unlock)(void *, const K60AdspPlatformMapping *);
    int (*init_image)(void *, const uint8_t *, size_t);
    int (*mem_setup)(void *, uint64_t, uint64_t);
    int (*auth_and_reset)(void *);
    int (*shutdown)(void *);
    void (*delay_us)(void *, unsigned);
} K60AdspPlatformServices;
typedef struct {
    K60AdspPlatformServices services;
    void *service_context;
    K60BatteryConfig config;
    K60AdspOwnerReader reader;
    uint8_t metadata[K60_ADSP_PLATFORM_METADATA_BYTES];
    K60AdspPlatformMapping smem, mutex;
    void *cookie;
    uint32_t epoch;
    unsigned initialized, reserved, resources_held, locked, image_initialized;
} K60AdspPlatform;
/* Initialize once before use, then retain state/services/context indefinitely
 * after Published/Poisoned. No reset API. NULL services is a valid unavailable
 * production state. Explicit reader is a host/mapped-FAT injection; NULL selects
 * the real linked carrier with absence-only legacy fallback. */
int k60_adsp_platform_init(K60AdspPlatform *, const K60AdspPlatformServices *, void *, const K60AdspReader *);
const K60OwnerOps *k60_adsp_platform_ops(void);
int k60_adsp_platform_install(void); /* 0 installed, 1 own prior install, -1000 failure */
/* Native services exist, but their available remains 0 until this board ownership
 * service is installed. No default success and no raw K60AdspPas fallback. */
int k60_adsp_platform_ownership_install(const K60AdspPlatformOwnership *, void *);
const K60AdspPlatformServices *k60_adsp_platform_native_services(void);
void *k60_adsp_platform_native_context(void);
#ifdef __cplusplus
}
#endif
#endif
