/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/*
 * K60Backlight.cpp - the OS facing half of the K60 brightness service.
 *
 * K60 has no backlight IC: brightness is the panel's DSI DCS 0x51 online DBV,
 * already implemented by pong_panel_set_brightness() in PongDsiPanel.cpp:247.
 * What was missing is a service CoreBrightness can talk to. This file is the
 * structure of UniXNU-sheng/package/AppleARMBacklight.cpp with the hardware
 * layer removed: no I2C engines, no GENI state machine, no interrupts, because
 * the transport is the DSI command FIFO that already works.
 *
 * Contract (docs/zh/porting/display.md:80-114, AppleARMBacklight.cpp:350-448):
 *   CoreBrightness/backboardd looks for a service with backlight-control = true,
 *   reads min/max from IODisplayParameters.brightness, and sends
 *   {brightness, FadePeriod (16.16 seconds)} through setProperties. iPadOS 27
 *   sends brightness-nits (signed 16.16) instead and ramps by itself.
 *
 * Two traps from the reference implementation, both avoided here:
 *   int-229 the class cannot be named AppleARMBacklight (the prelinked kernel
 *          already carries that class; a duplicate name panics on registration),
 *          so it is K60Backlight and impersonates the metaclass instead.
 *   int-236 publishing backlight-control without IOObjectConformsTo(service,
 *          "AppleARMBacklight") makes CoreBrightness skip the libEDR server and
 *          QuartzCore blocks with the display lock held: the screen stops
 *          updating. backlight-control is therefore only published when the
 *          impersonation succeeded (same rule as AppleARMBacklight.cpp:360).
 *
 * Counting follows the reference layout; see docs/research/display/
 * BRIGHTNESS-PLAN.md section 5 for the index table.
 */
#include <IOKit/IOService.h>
#include <IOKit/IOLib.h>
#include <IOKit/IOWorkLoop.h>
#include <IOKit/IOTimerEventSource.h>
#include <IOKit/IOPlatformExpert.h>
#include <kern/clock.h>
#include <libkern/c++/OSData.h>
#include <libkern/c++/OSDictionary.h>
#include <libkern/c++/OSNumber.h>
#include <libkern/c++/OSSymbol.h>
#include <libkern/libkern.h>
#include <pexpert/pexpert.h>

#include "K60BacklightCodec.h"

/* Same archive: PongDsiPanel.o is linked in through this reference, which is why
 * this service lives in drivers/PongAdreno rather than in the xnu tree. */
extern "C" int pong_panel_set_brightness(uint32_t level);
extern "C" uint32_t pong_panel_brightness(void);

/* [0] stage (1 attached, 2 work loop ready, 3 published, 4 published as
 * AppleARMBacklight, negative: the step that failed), [1] brightness requests,
 * [2] last level written, [3] level read back, [4] DBV read back, [5] failed
 * writes, [6]..[12] GENI/interrupt slots that K60 does not have (-1),
 * [13] timeouts (-1: counted inside PongDsiPanel.cpp), [14] attach tries,
 * [15] completed writes. */
extern "C" {volatile int32_t native_backlight_stats[16];}
/* [0] last level asked for, [1] its fade in milliseconds, [2] request timer
 * runs, [3] fades begun from a request, [4] [5] interrupts (unused, -1). */
extern "C" {volatile int32_t native_backlight_request[6];}

namespace {
/* The newest request, goal << 16 | milliseconds, bit 63 set while the work loop
 * has not taken it yet. */
volatile uint64_t gRequest;

bool bootArg(const char *name, uint32_t &value)
{
    uint32_t parsed = value;
    if (!PE_parse_boot_argn(name, &parsed, sizeof(parsed))) return false;
    value = parsed;
    return true;
}
}

class K60Backlight final : public IOService
{
    OSDeclareDefaultStructors(K60Backlight)

public:
    bool startService(void);
    void stop(IOService *provider) override;
    void free(void) override;
    IOReturn setProperties(OSObject *properties) override;

private:
    IOWorkLoop *loop = nullptr;
    IOTimerEventSource *requestTimer = nullptr;
    IOTimerEventSource *fadeTimer = nullptr;
    bool requestAdded = false, fadeAdded = false;
    bool published = false, stopped = false, impersonated = false;
    bool invert = false;
    uint32_t level = 0, from = 0, to = 0, periodMs = 0;
    uint64_t start = 0;

    static const OSMetaClass *gAppleClass;

    static const OSMetaClass *appleMetaClass(const OSMetaClassBase *);
    bool impersonate(void);
    void publish(uint32_t value);
    void publishCalibration(void);
    void publishFirst(void);
    void beginFade(uint32_t goal, uint32_t milliseconds);
    bool writeLevel(uint32_t value);
    static void requestAction(OSObject *owner, IOTimerEventSource *timer);
    static void fadeAction(OSObject *owner, IOTimerEventSource *timer);
    static IOReturn beginAction(OSObject *owner, void *, void *, void *, void *);
};

OSDefineMetaClassAndStructors(K60Backlight, IOService)

const OSMetaClass *K60Backlight::gAppleClass = nullptr;

/* The metaclass the sandbox and IOObjectConformsTo are asked about once the
 * instance's vtable slot 7 points here (see impersonate). A member so it can
 * reach the private gAppleClass, exactly as the reference implementation does. */
const OSMetaClass *K60Backlight::appleMetaClass(const OSMetaClassBase *)
{
    return gAppleClass;
}

bool K60Backlight::impersonate(void)
{
    enum {kSlots = 320, kGetMetaClass = 7};
    const OSSymbol *name = OSSymbol::withCString("AppleARMBacklight");
    gAppleClass = name ? OSMetaClass::getMetaClassWithName(name) : nullptr;
    OSSafeReleaseNULL(name);
    if (!gAppleClass) return false;
#if __has_feature(ptrauth_calls)
    /* arm64e signs vtable entries, so a copied vtable would not authenticate;
     * that build would need the hand written getMetaClass() of the reference
     * implementation. This kernel is built for arm64 (build-xnu-4k-baseline.sh
     * ARCH_STRING_FOR_CURRENT_MACHINE_CONFIG=arm64), so refuse rather than
     * pretend: without impersonation the service simply does not claim
     * backlight-control (int-236 stays avoided). */
    return false;
#else
    uintptr_t *copy = static_cast<uintptr_t *>(IOMalloc(kSlots * sizeof(uintptr_t)));
    if (!copy) return false;
    memcpy(copy, *reinterpret_cast<uintptr_t **>(this), kSlots * sizeof(uintptr_t));
    copy[kGetMetaClass] = reinterpret_cast<uintptr_t>(&appleMetaClass);
    __asm__ volatile("dmb ish" ::: "memory");
    *reinterpret_cast<uintptr_t **>(this) = copy;
    return true;
#endif
}

void K60Backlight::publish(uint32_t value)
{
    OSDictionary *brightness = OSDictionary::withCapacity(3);
    OSDictionary *milliNits = OSDictionary::withCapacity(3);
    OSDictionary *parameters = OSDictionary::withCapacity(2);
    OSNumber *min = OSNumber::withNumber(0ULL, 32);
    OSNumber *max = OSNumber::withNumber((uint64_t)k60backlight::kMaxLevel, 32);
    OSNumber *cur = OSNumber::withNumber((uint64_t)value, 32);
    OSNumber *nitsMin = OSNumber::withNumber((uint64_t)k60backlight::kMinNits * 1000, 32);
    OSNumber *nitsMax = OSNumber::withNumber((uint64_t)k60backlight::kMaxNits * 1000, 32);
    OSNumber *nitsCur = OSNumber::withNumber((uint64_t)k60backlight::milliNitsFromLevel(value), 32);
    if (!brightness || !milliNits || !parameters || !min || !max || !cur ||
        !nitsMin || !nitsMax || !nitsCur) goto done;
    brightness->setObject("min", min);
    brightness->setObject("max", max);
    brightness->setObject("value", cur);
    milliNits->setObject("min", nitsMin);
    milliNits->setObject("max", nitsMax);
    milliNits->setObject("value", nitsCur);
    parameters->setObject("brightness", brightness);
    parameters->setObject("BrightnessMilliNits", milliNits);
    setProperty("IODisplayParameters", parameters);
done:
    OSSafeReleaseNULL(nitsCur);
    OSSafeReleaseNULL(nitsMax);
    OSSafeReleaseNULL(nitsMin);
    OSSafeReleaseNULL(cur);
    OSSafeReleaseNULL(max);
    OSSafeReleaseNULL(min);
    OSSafeReleaseNULL(parameters);
    OSSafeReleaseNULL(milliNits);
    OSSafeReleaseNULL(brightness);
}

/* The slider table and calibration points iPadOS 27 asks for. The panel's
 * luminance has not been measured, so these set the slider's scale, not an
 * absolute brightness (same disclosure as the reference implementation). */
void K60Backlight::publishCalibration(void)
{
    const int32_t table[3] = {(int32_t)(k60backlight::kMinNits << 16),
                              (int32_t)(k60backlight::kMidNits << 16),
                              (int32_t)(k60backlight::kMaxNits << 16)};
    if (OSData *marketing = OSData::withBytes(table, sizeof(table))) {
        setProperty("backlight-marketing-table", marketing);
        marketing->release();
    }
    if (OSData *lmax = OSData::withBytes(&table[2], sizeof(table[2]))) {
        setProperty("LmaxProduct", lmax);
        lmax->release();
    }
    if (OSNumber *number = OSNumber::withNumber((uint64_t)k60backlight::kMinNits, 32)) {
        setProperty("LminProduct", number);
        number->release();
    }
    if (OSNumber *number = OSNumber::withNumber((uint64_t)k60backlight::kMidNits, 32)) {
        setProperty("LmidProduct", number);
        number->release();
    }
    OSDictionary *calibration = OSDictionary::withCapacity(6);
    if (!calibration) return;
    const struct {const char *key; uint32_t nits;} fields[] = {
        {"lMinProduct", k60backlight::kMinNits}, {"lMidProduct", k60backlight::kMidNits},
        {"lMaxProduct", k60backlight::kMaxNits}, {"lMinPanel", k60backlight::kMinNits},
        {"lMidPanel", k60backlight::kMidNits}, {"lMaxPanel", k60backlight::kMaxNits}};
    for (const auto &field : fields) {
        if (OSNumber *number = OSNumber::withNumber((uint64_t)field.nits << 16, 32)) {
            calibration->setObject(field.key, number);
            number->release();
        }
    }
    setProperty("backlight-calibration-parameters", calibration);
    calibration->release();
}

/* One DCS 0x51 write. The panel has no read back command, so the value reported
 * as read back is the one this service last wrote successfully
 * (PongDsiPanel.cpp:255), not a measurement. */
bool K60Backlight::writeLevel(uint32_t value)
{
    const uint32_t dbv = k60backlight::applyInvert(k60backlight::dbvFromLevel(value), invert);
    if (pong_panel_set_brightness(dbv)) {
        __atomic_fetch_add(&native_backlight_stats[5], 1, __ATOMIC_RELAXED);
        return false;
    }
    __atomic_fetch_add(&native_backlight_stats[15], 1, __ATOMIC_RELAXED);
    native_backlight_stats[2] = (int32_t)value;
    const uint32_t written = pong_panel_brightness();
    native_backlight_stats[4] = (int32_t)written;
    native_backlight_stats[3] = (int32_t)k60backlight::levelFromDbv(written);
    return true;
}

void K60Backlight::beginFade(uint32_t goal, uint32_t milliseconds)
{
    if (!fadeTimer) return;
    fadeTimer->cancelTimeout();
    from = level;
    to = k60backlight::clampLevel((int64_t)goal);
    periodMs = milliseconds;
    clock_get_uptime(&start);
    fadeAction(this, fadeTimer);
}

void K60Backlight::fadeAction(OSObject *owner, IOTimerEventSource *sender)
{
    K60Backlight *self = static_cast<K60Backlight *>(owner);   /* see impersonate() */
    if (!self || self->stopped) return;
    uint64_t now = 0, elapsedNs = 0;
    clock_get_uptime(&now);
    absolutetime_to_nanoseconds(now - self->start, &elapsedNs);
    const uint32_t elapsedMs = elapsedNs > 0xffffffffull ? 0xffffffffu : (uint32_t)(elapsedNs / 1000000ull);
    const uint32_t next = k60backlight::fadeLevel(self->from, self->to, elapsedMs, self->periodMs);
    if (next != self->level) {
        self->writeLevel(next);
        self->level = next;
    }
    if (next != self->to) sender->setTimeoutMS(k60backlight::kStepMs);
}

void K60Backlight::requestAction(OSObject *owner, IOTimerEventSource *sender)
{
    (void)sender;
    K60Backlight *self = static_cast<K60Backlight *>(owner);
    if (!self || self->stopped) return;
    __atomic_fetch_add(&native_backlight_request[2], 1, __ATOMIC_RELAXED);
    const uint64_t request = __atomic_exchange_n(&gRequest, 0ull, __ATOMIC_ACQUIRE);
    if (!(request >> 63)) return;
    __atomic_fetch_add(&native_backlight_request[3], 1, __ATOMIC_RELAXED);
    self->beginFade((uint32_t)(request >> 16) & 0xffff, (uint32_t)request & 0xffff);
}

/* The reference waits for both engines to answer a level read first; here the
 * panel is already lit by bring-up, so the published value is whatever DBV the
 * panel was left at (0xff, PongDsiPanel.cpp:236). */
void K60Backlight::publishFirst(void)
{
    published = true;
    level = from = to = k60backlight::levelFromDbv(pong_panel_brightness());
    native_backlight_stats[2] = (int32_t)level;
    native_backlight_stats[3] = (int32_t)level;
    native_backlight_stats[4] = (int32_t)pong_panel_brightness();
    /* int-236: only claim backlight-control when the conformance query will
     * answer AppleARMBacklight. k60_backlight_control=0 is the escape hatch. */
    uint32_t control = 1;
    bootArg("k60_backlight_control", control);
    if (control && impersonate()) {
        impersonated = true;
        setProperty("NativeSandboxGrantProcess", "backboardd");
        setProperty("backlight-control", true);
    }
    publishCalibration();
    publish(level);
    registerService();
    native_backlight_stats[0] = impersonated ? 4 : 3;
    IOLog("K60 BACKLIGHT: published level %u dbv 0x%x control %d%s\n", level,
          pong_panel_brightness(), (int)impersonated,
          impersonated ? "" : " (no AppleARMBacklight conformance)");
}

IOReturn K60Backlight::setProperties(OSObject *properties)
{
    OSDictionary *dictionary = OSDynamicCast(OSDictionary, properties);
    if (!dictionary) return kIOReturnBadArgument;
    uint32_t goal;
    uint32_t milliseconds = 0;
    if (OSNumber *nits = OSDynamicCast(OSNumber, dictionary->getObject("brightness-nits"))) {
        /* iPadOS 27: signed 16.16 nits, ramped by the caller. */
        goal = k60backlight::levelFromNits((int32_t)nits->unsigned32BitValue());
    } else if (OSNumber *brightness = OSDynamicCast(OSNumber, dictionary->getObject("brightness"))) {
        OSNumber *fadePeriod = OSDynamicCast(OSNumber, dictionary->getObject("FadePeriod"));
        goal = k60backlight::clampLevel((int64_t)(int32_t)brightness->unsigned32BitValue());
        if (fadePeriod)
            milliseconds = k60backlight::fadeMsFromFixed((uint64_t)fadePeriod->unsigned32BitValue());
    } else {
        return kIOReturnSuccess;
    }
    __atomic_fetch_add(&native_backlight_stats[1], 1, __ATOMIC_RELAXED);
    native_backlight_request[0] = (int32_t)goal;
    native_backlight_request[1] = (int32_t)milliseconds;
    /* Hand the request to the work loop instead of blocking backboardd's
     * brightness thread here (int-277/int-278 in the reference). */
    __atomic_store_n(&gRequest,
                     (1ull << 63) | ((uint64_t)goal << 16) | (uint64_t)(milliseconds & 0xffff),
                     __ATOMIC_RELEASE);
    if (requestTimer) requestTimer->setTimeoutUS(1);
    publish(goal);
    return kIOReturnSuccess;
}

bool K60Backlight::startService(void)
{
    native_backlight_stats[0] = 1;
    for (int i = 6; i <= 12; ++i) native_backlight_stats[i] = -1;
    native_backlight_stats[13] = -1;
    native_backlight_stats[14] = 1;
    native_backlight_request[4] = -1;
    native_backlight_request[5] = -1;
    uint32_t invertArg = 0;
    invert = bootArg("k60_backlight_invert", invertArg) && invertArg != 0;
    loop = IOWorkLoop::workLoop();
    requestTimer = IOTimerEventSource::timerEventSource(this, requestAction);
    fadeTimer = IOTimerEventSource::timerEventSource(this, fadeAction);
    if (!loop || !requestTimer || !fadeTimer) return false;
    if (loop->addEventSource(requestTimer) != kIOReturnSuccess) return false;
    requestAdded = true;
    if (loop->addEventSource(fadeTimer) != kIOReturnSuccess) return false;
    fadeAdded = true;
    native_backlight_stats[0] = 2;
    /* Publish from the work loop so the first setProperties cannot race the
     * IORegistry publication. */
    loop->runAction(beginAction, this);
    return true;
}

IOReturn K60Backlight::beginAction(OSObject *owner, void *, void *, void *, void *)
{
    K60Backlight *self = static_cast<K60Backlight *>(owner);   /* see impersonate() */
    if (!self || self->published) return kIOReturnSuccess;
    self->publishFirst();
    return kIOReturnSuccess;
}

void K60Backlight::stop(IOService *provider)
{
    stopped = true;
    if (fadeTimer) fadeTimer->cancelTimeout();
    if (requestTimer) requestTimer->cancelTimeout();
    if (loop) {
        if (fadeAdded) {loop->removeEventSource(fadeTimer); fadeAdded = false;}
        if (requestAdded) {loop->removeEventSource(requestTimer); requestAdded = false;}
    }
    OSSafeReleaseNULL(fadeTimer);
    OSSafeReleaseNULL(requestTimer);
    OSSafeReleaseNULL(loop);
    IOService::stop(provider);
}

void K60Backlight::free(void)
{
    OSSafeReleaseNULL(fadeTimer);
    OSSafeReleaseNULL(requestTimer);
    OSSafeReleaseNULL(loop);
    IOService::free();
}

/* Entry point, called from pong_scanout_initialize() once the panel is out of
 * sleep (same archive, so PongDsiPanel.o is already linked in). */
extern "C" void k60_backlight_start(void)
{
    static unsigned attempted;
    uint32_t enabled = 1;
    bootArg("k60_backlight", enabled);
    if (!enabled || __atomic_exchange_n(&attempted, 1u, __ATOMIC_ACQ_REL)) return;
    IOService *provider = IOService::getPlatform();
    K60Backlight *service = new K60Backlight;
    bool attached = false;
    if (provider && service && service->init()) attached = service->attach(provider);
    if (!attached || !service->startService()) {
        if (service) {
            if (attached) service->stop(provider);
            if (attached) service->detach(provider);
            service->release();
        }
        native_backlight_stats[0] = -1;
        IOLog("K60 BACKLIGHT: service setup rejected; brightness stays at bring-up value\n");
        return;
    }
    /* The service retains its own owner reference for the epoch; there is no
     * unload path, matching the reference implementation. */
}
