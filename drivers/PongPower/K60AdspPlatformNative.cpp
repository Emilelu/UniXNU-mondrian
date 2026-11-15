/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/* Native IOKit primitives for the K60 PAS1 platform contract. SCM register,
 * resume/busy and cache-maintenance patterns adapted from pong-power
 * PongAdsp.cpp / PongPlatformResources.* at
 * c117a6700968c944528570326c8d709e29bd373f (BSD-2-Clause-Patent).
 * Board resource/reset ownership is deliberately supplied separately. */
#include <IOKit/IOLib.h>
#include <IOKit/IOMemoryDescriptor.h>
#include <IOKit/IOBufferMemoryDescriptor.h>
#include <kern/task.h>
#include "K60AdspPlatform.h"
#include "K60AdspPas.h"

extern "C" { extern unsigned long gPhysBase, gPhysSize; }
namespace {
constexpr int unavailable = K60_ADSP_OWNER_UNAVAILABLE;
constexpr uint64_t physicalLimit = UINT64_C(1) << 36;
constexpr uint64_t mappingPage = 4096;
constexpr int64_t interrupted = 1, busy = -12;
constexpr unsigned busyAttempts = 20, resumeLimit = 100000;
struct Native {
    K60AdspPlatformOwnership board;
    const K60AdspPlatformOwnership *source;
    void *boardContext;
    K60BatteryConfig config;
    void *cookie;
    uint32_t epoch;
    IOBufferMemoryDescriptor *metadata;
    bool prepared, reserved, resources, imageInitialized;
    bool authAttempted, shutdownComplete;
    unsigned poisoned, scmRetained, tcsrHeld;
    IOMemoryMap *lockedMap;
};
Native native;
unsigned ownershipInstallation;

bool installed()
{ return __atomic_load_n(&ownershipInstallation, __ATOMIC_ACQUIRE) == 2u; }
bool healthy(const Native *n)
{ return n == &native && installed() && !__atomic_load_n(&n->poisoned, __ATOMIC_ACQUIRE); }
void poison(Native *n)
{ __atomic_store_n(&n->poisoned, 1u, __ATOMIC_RELEASE); }
bool extent(uint64_t base, uint64_t bytes)
{ return bytes && base && base < physicalLimit && bytes <= physicalLimit - base; }
bool overlapsRam(uint64_t base, uint64_t bytes)
{
    const uint64_t ramBase = gPhysBase, ramBytes = gPhysSize;
    /* An unknown/overflowed XNU RAM extent cannot prove a safe carveout. */
    if (!ramBytes || ramBytes > UINT64_MAX - ramBase) return true;
    return base < ramBase + ramBytes && ramBase < base + bytes;
}
bool validConfig(const K60BatteryConfig *c)
{
    return c && extent(c->smem_base, c->smem_bytes) &&
        extent(c->adsp_base, c->adsp_bytes) && extent(c->mutex_base, 4) &&
        !(c->smem_base & 7u) && !(c->mutex_base & 3u) &&
        !(c->adsp_base & (mappingPage - 1)) &&
        !(c->adsp_bytes & (mappingPage - 1)) && c->smem_bytes <= SIZE_MAX &&
        !(c->smem_base < c->adsp_base + c->adsp_bytes &&
          c->adsp_base < c->smem_base + c->smem_bytes) &&
        !overlapsRam(c->smem_base, c->smem_bytes) &&
        !overlapsRam(c->adsp_base, c->adsp_bytes);
}
bool owned(Native *n)
{
    return healthy(n) && n->reserved && n->cookie && n->epoch &&
        n->board.live(n->boardContext, n->cookie, n->epoch) == 1;
}
bool stopped(Native *n)
{
    return healthy(n) && n->reserved && n->cookie &&
        n->board.stopped(n->boardContext, n->cookie) == 1;
}
void freeMetadata(Native *n)
{
    if (!n->metadata) return;
    if (n->prepared) (void)n->metadata->complete();
    n->metadata->release(); n->metadata = nullptr; n->prepared = false;
}
int available(void *context, const K60BatteryConfig *c)
{
    auto n = static_cast<Native *>(context);
    return healthy(n) && validConfig(c) && n->board.available(n->boardContext, c) == 1;
}
int exclusive(void *context, const K60BatteryConfig *c, uint32_t *epoch, void **cookie)
{
    auto n = static_cast<Native *>(context);
    if (!epoch || !cookie) return unavailable;
    *epoch = 0; *cookie = nullptr;
    if (!available(n, c) || n->reserved || n->metadata) return unavailable;
    uint32_t e = 0; void *token = nullptr;
    int rc = n->board.exclusive(n->boardContext, c, &e, &token);
    if (rc) return rc; /* Board failures must roll back internally. */
    n->reserved = true; n->cookie = token; n->epoch = e; n->config = *c;
    if (!e || !token) {
        /* A malformed successful lease cannot establish safe rollback. */
        poison(n); return unavailable;
    }
    *epoch = e; *cookie = token; return 0;
}
void exclusiveRelease(void *context, void *cookie)
{
    auto n = static_cast<Native *>(context);
    if (!healthy(n) || !n->reserved || cookie != n->cookie || n->resources ||
        n->tcsrHeld || n->scmRetained) return;
    /* Owner abort already proved terminal stopped state. The board exclusion
     * holds that proof through this release, including after dropping votes. */
    freeMetadata(n);
    n->board.exclusive_release(n->boardContext, cookie);
    n->cookie = nullptr; n->epoch = 0; n->reserved = false;
    n->imageInitialized = false;
    n->authAttempted = false; n->shutdownComplete = false;
}
int resources(void *context, void *cookie)
{
    auto n = static_cast<Native *>(context);
    if (!healthy(n) || !n->reserved || cookie != n->cookie || n->resources) return unavailable;
    int rc = n->board.resources(n->boardContext, cookie);
    if (!rc) n->resources = true;
    return rc;
}
void resourcesRelease(void *context, void *cookie)
{
    auto n = static_cast<Native *>(context);
    if (!healthy(n) || !n->resources || cookie != n->cookie || n->tcsrHeld || n->scmRetained) return;
    /* No second mutable stopped query: valid void releases cannot fail after
     * the owner's final proof under its retained exclusion. */
    n->board.resources_release(n->boardContext, cookie); n->resources = false;
}
int isStopped(void *context, void *cookie)
{
    auto n = static_cast<Native *>(context);
    return healthy(n) && n->reserved && cookie == n->cookie &&
        !n->tcsrHeld && !n->scmRetained &&
        (!n->authAttempted || n->shutdownComplete) && owned(n) && stopped(n);
}
int live(void *context, void *cookie, uint32_t epoch)
{
    auto n = static_cast<Native *>(context);
    return owned(n) && n->resources && cookie == n->cookie && epoch == n->epoch;
}

bool mappingValid(const K60AdspPlatformMapping *m)
{
    if (!m || !m->handle || !m->base || !m->bytes ||
        m->bytes > UINTPTR_MAX - reinterpret_cast<uintptr_t>(m->base)) return false;
    auto map = static_cast<IOMemoryMap *>(m->handle);
    const uintptr_t start = map->getVirtualAddress(), requested = reinterpret_cast<uintptr_t>(m->base);
    const uint64_t length = map->getLength();
    return start && requested >= start && requested - start <= length &&
        m->bytes <= length - (requested - start);
}
int mapMemory(void *context, uint64_t physical, size_t bytes, unsigned kind, K60AdspPlatformMapping *out)
{
    auto n = static_cast<Native *>(context);
    if (!out || out->handle || out->base || out->bytes) return unavailable;
    if (!owned(n) || !n->resources || !extent(physical, bytes)) return unavailable;
    IOOptionBits cache = kIOMapInhibitCache;
    if (kind == K60AdspMapShared) {
        if (!stopped(n) || physical != n->config.smem_base || bytes != n->config.smem_bytes) return unavailable;
    } else if (kind == K60AdspMapDevice) {
        if (!stopped(n) || physical != n->config.mutex_base || bytes != 4u) return unavailable;
    } else if (kind == K60AdspMapFirmware) {
        if (!stopped(n) || !n->imageInitialized || bytes > K60_ADSP_PLATFORM_WINDOW_BYTES ||
            physical < n->config.adsp_base || bytes > n->config.adsp_bytes ||
            physical - n->config.adsp_base > n->config.adsp_bytes - bytes) return unavailable;
        cache = kIOMapWriteCombineCache;
    } else return unavailable;
    /* Mapping the containing page is essential for K60's TCSR +0x00c register
     * and for unaligned firmware segments. Return the exact requested extent. */
    const uint64_t aligned = physical & ~(mappingPage - 1);
    const size_t offset = static_cast<size_t>(physical - aligned);
    if (bytes > SIZE_MAX - offset || bytes + offset > SIZE_MAX - (mappingPage - 1)) return unavailable;
    const size_t length = (bytes + offset + mappingPage - 1) & ~size_t(mappingPage - 1);
    if (!extent(aligned, length)) return unavailable;
    auto memory = IOMemoryDescriptor::withPhysicalAddress(aligned, length, kIODirectionInOut);
    if (!memory) return unavailable;
    IOMemoryMap *map = memory->map(kIOMapAnywhere | cache); memory->release();
    if (!map) return unavailable;
    const uintptr_t base = map->getVirtualAddress();
    if (!base || map->getLength() < length || length > UINTPTR_MAX - base) {
        map->release(); return unavailable;
    }
    out->base = reinterpret_cast<volatile uint8_t *>(base + offset);
    out->bytes = bytes; out->handle = map; return 0;
}
void unmapMemory(void *context, K60AdspPlatformMapping *m)
{
    auto n = static_cast<Native *>(context);
    if (n != &native || !m || (n->tcsrHeld && m->handle == n->lockedMap)) return;
    /* Firmware windows are disposable even on a load error; persistent SMEM
     * mappings are retained by the C owner whenever its session is Poisoned. */
    if (m->handle) static_cast<IOMemoryMap *>(m->handle)->release();
    *m = {};
}
int cleanToPoc(const void *start, size_t bytes)
{
    const uintptr_t address = reinterpret_cast<uintptr_t>(start);
    if (!start || !bytes || bytes > UINTPTR_MAX - address) return unavailable;
    uint64_t ctr;
    __asm__ volatile("mrs %0, ctr_el0" : "=r"(ctr));
    const uintptr_t line = uintptr_t(4) << ((ctr >> 16) & 15);
    const uintptr_t end = address + bytes;
    for (uintptr_t at = address & ~(line - 1); at < end;) {
        __asm__ volatile("dc cvac, %0" :: "r"(at) : "memory");
        if (end - at <= line) break;
        at += line;
    }
    __asm__ volatile("dsb sy" ::: "memory"); return 0;
}
int syncMemory(void *context, const K60AdspPlatformMapping *m, size_t offset, size_t bytes)
{
    auto n = static_cast<Native *>(context);
    if (!healthy(n) || !mappingValid(m) || offset > m->bytes || bytes > m->bytes - offset) return unavailable;
    if (!bytes) { __asm__ volatile("dsb sy" ::: "memory"); return 0; }
    return cleanToPoc(reinterpret_cast<const void *>(reinterpret_cast<uintptr_t>(m->base) + offset), bytes);
}
int lockMemory(void *context, const K60AdspPlatformMapping *m)
{
    auto n = static_cast<Native *>(context);
    if (!owned(n) || !n->resources || !mappingValid(m) || m->bytes != 4 ||
        (reinterpret_cast<uintptr_t>(m->base) & 3u) ||
        !__sync_bool_compare_and_swap(&n->tcsrHeld, 0u, 1u)) return unavailable;
    n->lockedMap = static_cast<IOMemoryMap *>(m->handle);
    auto word = reinterpret_cast<volatile uint32_t *>(m->base);
    for (unsigned tries = 0; tries < 100; ++tries) {
        *word = 1; /* TCSR APSS hardware owner ID; not a software CAS. */
        __asm__ volatile("dsb sy" ::: "memory");
        if (*word == 1) { __asm__ volatile("dmb osh" ::: "memory"); return 0; }
        IODelay(10);
    }
    n->lockedMap = nullptr; __atomic_store_n(&n->tcsrHeld, 0u, __ATOMIC_RELEASE);
    return unavailable;
}
void unlockMemory(void *context, const K60AdspPlatformMapping *m)
{
    auto n = static_cast<Native *>(context);
    if (n != &native || !n->tcsrHeld || !mappingValid(m) || m->bytes != 4 || m->handle != n->lockedMap) return;
    auto word = reinterpret_cast<volatile uint32_t *>(m->base);
    __asm__ volatile("dmb osh" ::: "memory");
    if (*word == 1) *word = 0;
    else poison(n); /* Lost hardware ownership is not a successful release. */
    __asm__ volatile("dsb sy" ::: "memory");
    n->lockedMap = nullptr; __atomic_store_n(&n->tcsrHeld, 0u, __ATOMIC_RELEASE);
}

struct ScmResult { uint64_t status, payload, session; };
ScmResult smc(uint64_t function, uint32_t arginfo, uint64_t a, uint64_t b, uint64_t c, uint64_t session)
{
    register uint64_t x0 __asm__("x0") = function;
    register uint64_t x1 __asm__("x1") = arginfo;
    register uint64_t x2 __asm__("x2") = a;
    register uint64_t x3 __asm__("x3") = b;
    register uint64_t x4 __asm__("x4") = c;
    register uint64_t x5 __asm__("x5") = 0;
    register uint64_t x6 __asm__("x6") = session;
    register uint64_t x7 __asm__("x7") = 0;
    __asm__ volatile("smc #0"
        : "+r"(x0), "+r"(x1), "+r"(x2), "+r"(x3), "+r"(x4), "+r"(x5), "+r"(x6), "+r"(x7)
        :: "x8", "x9", "x10", "x11", "x12", "x13", "x14", "x15", "x16", "x17", "cc", "memory");
    return {x0, x1, x6};
}
int scm(Native *n, uint32_t command, uint32_t arginfo, uint64_t a, uint64_t b, uint64_t c)
{
    if (!owned(n) || !n->resources || n->tcsrHeld || n->scmRetained) return unavailable;
    if (n->board.scm_lock(n->boardContext) != 0) return unavailable;
    n->scmRetained = 1;
    if (!owned(n)) {
        n->scmRetained = 0; n->board.scm_unlock(n->boardContext); return unavailable;
    }
    ScmResult result = {UINT64_MAX, 0, 0};
    for (unsigned attempt = 0; attempt < busyAttempts; ++attempt) {
        uint64_t function = k60_scm_fn(K60_SCM_SVC_PIL, command), session = 0;
        unsigned resumed = 0;
        for (;;) {
            result = smc(function, arginfo, a, b, c, session);
            if (static_cast<int64_t>(result.status) != interrupted) break;
            if (resumed == resumeLimit) {
                /* The secure session is still suspended. Retain the board's
                 * global lock, coherent metadata, and all owner resources.
                 * No further SMC or stopped/live proof is allowed this boot. */
                poison(n); return unavailable;
            }
            ++resumed; function = static_cast<uint64_t>(interrupted); session = result.session;
        }
        if (static_cast<int64_t>(result.status) > 0) {
            /* WAITQ_SLEEP (2) and unknown positive responses are not
             * terminal errors. Without the secure IRQ/wait-context owner we
             * cannot resume or ACK them safely: retain exactly as suspended. */
            poison(n); return unavailable;
        }
        if (static_cast<int64_t>(result.status) != busy) break;
        IOSleep(30); /* At most twenty attempts, including twenty busy pauses. */
    }
    n->scmRetained = 0; n->board.scm_unlock(n->boardContext);
    return k60_scm_ok(result.status, result.payload) ? 0 : unavailable;
}
int initImage(void *context, const uint8_t *metadata, size_t bytes)
{
    auto n = static_cast<Native *>(context);
    if (!owned(n) || !n->resources || !stopped(n) || n->tcsrHeld || n->metadata ||
        !metadata || !bytes || bytes > K60_ADSP_PLATFORM_METADATA_BYTES ||
        bytes > UINTPTR_MAX - reinterpret_cast<uintptr_t>(metadata)) return unavailable;
    /* PAS metadata must stay noncacheable while secure XPU protection changes.
     * The SDK explicitly supports inhibited-cache IOBuffer allocations. */
    n->metadata = IOBufferMemoryDescriptor::inTaskWithOptions(kernel_task,
        IOOptionBits(kIODirectionInOut) | IOOptionBits(kIOMemoryHostPhysicallyContiguous) |
        IOOptionBits(kIOMapInhibitCache), K60_ADSP_PLATFORM_METADATA_BYTES, mappingPage);
    if (!n->metadata) return unavailable;
    n->prepared = n->metadata->prepare() == kIOReturnSuccess;
    if (!n->prepared) { freeMetadata(n); return unavailable; }
    IOByteCount span = 0;
    const uint64_t physical = n->metadata->getPhysicalSegment(0, &span, kIOMemoryMapperNone);
    auto cpu = static_cast<uint8_t *>(n->metadata->getBytesNoCopy());
    if (!cpu || n->metadata->getLength() < K60_ADSP_PLATFORM_METADATA_BYTES ||
        !extent(physical, K60_ADSP_PLATFORM_METADATA_BYTES) || (physical & (mappingPage - 1)) ||
        span < K60_ADSP_PLATFORM_METADATA_BYTES) { freeMetadata(n); return unavailable; }
    /* Copy before PAS sees the physical extent; clear all remaining reserved
     * bytes so this coherent allocation never exposes stale host memory. */
    for (size_t i = 0; i < K60_ADSP_PLATFORM_METADATA_BYTES; ++i) cpu[i] = i < bytes ? metadata[i] : 0;
    if (cleanToPoc(cpu, K60_ADSP_PLATFORM_METADATA_BYTES)) { freeMetadata(n); return unavailable; }
    int rc = scm(n, K60_SCM_PAS_INIT_IMAGE, k60_scm_args(2, K60_SCM_VAL, K60_SCM_RW, 0),
        K60_PAS_ADSP, physical, 0);
    if (!rc) n->imageInitialized = true;
    /* Even a terminal PAS error retains the descriptor until safe owner release. */
    return rc;
}
int memSetup(void *context, uint64_t base, uint64_t bytes)
{
    auto n = static_cast<Native *>(context);
    if (!owned(n) || !stopped(n) || !n->imageInitialized || base != n->config.adsp_base ||
        !extent(base, bytes) || bytes > n->config.adsp_bytes) return unavailable;
    return scm(n, K60_SCM_PAS_MEM_SETUP, k60_scm_args(3, 0, 0, 0), K60_PAS_ADSP, base, bytes);
}
int authAndReset(void *context)
{
    auto n = static_cast<Native *>(context);
    if (!owned(n) || !stopped(n) || !n->imageInitialized || n->authAttempted) return unavailable;
    n->authAttempted = true; n->shutdownComplete = false;
    return scm(n, K60_SCM_PAS_AUTH_AND_RESET, k60_scm_args(1, 0, 0, 0), K60_PAS_ADSP, 0, 0);
}
int shutdown(void *context)
{
    auto n = static_cast<Native *>(context);
    if (!owned(n) || !n->resources || n->tcsrHeld || n->scmRetained) return unavailable;
    int rc = scm(n, K60_SCM_PAS_SHUTDOWN, k60_scm_args(1, 0, 0, 0), K60_PAS_ADSP, 0, 0);
    if (!rc) n->shutdownComplete = true;
    /* A zero PAS result never creates the independent board stopped proof. */
    return rc;
}
void delay(void *context, unsigned microseconds)
{ if (context == &native && microseconds) IODelay(microseconds); }
const K60AdspPlatformServices services = {
    K60_ADSP_PLATFORM_VERSION, sizeof(K60AdspPlatformServices), available, exclusive,
    exclusiveRelease, resources, resourcesRelease, isStopped, live, mapMemory,
    unmapMemory, syncMemory, lockMemory, unlockMemory, initImage, memSetup,
    authAndReset, shutdown, delay
};
bool complete(const K60AdspPlatformOwnership *o)
{
    return o && o->version == K60_ADSP_PLATFORM_VERSION && o->bytes == sizeof(*o) &&
        o->available && o->exclusive && o->exclusive_release && o->resources &&
        o->resources_release && o->stopped && o->live && o->scm_lock && o->scm_unlock;
}
} // namespace

extern "C" int k60_adsp_platform_ownership_install(const K60AdspPlatformOwnership *o, void *context)
{
    if (!complete(o)) return unavailable;
    if (installed()) return native.source == o && native.boardContext == context ? 1 : unavailable;
    if (!__sync_bool_compare_and_swap(&ownershipInstallation, 0u, 1u)) return unavailable;
    native.board = *o; native.boardContext = context; native.source = o;
    __atomic_store_n(&ownershipInstallation, 2u, __ATOMIC_RELEASE); return 0;
}
extern "C" const K60AdspPlatformServices *k60_adsp_platform_native_services(void)
{ return &services; }
extern "C" void *k60_adsp_platform_native_context(void)
{
    IOLog("K60ADSP native board_ownership=%u\n", installed() ? 1u : 0u);
    return &native;
}
