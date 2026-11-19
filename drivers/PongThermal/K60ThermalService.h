/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/* Kernel side of the K60 thermal line.
 *
 * Two objects live here:
 *   K60ThermalSensor          matches the board DT nodes thermal-sensor@c263000
 *                             and @c265000, maps the TM window read-only, samples
 *                             the 16 status words of its controller and republishes
 *                             them as registry properties.
 *   AppleSMCSensorDispatcher  the nub thermalmonitord looks up by class name. It
 *                             exposes selectors 0..3 of the AppleSMCSensorDispatcher
 *                             user client (count / keys / values / write) and answers
 *                             the pressure level computed by K60ThermalLevel.c.
 *
 * Nothing here writes a tsens register, takes a tsens interrupt, or posts a
 * notification: the pressure notification is thermalmonitord's job, it is the
 * consumer of these selectors. See docs/research/thermal/06-KEXT-SERVICE.md. */
#ifndef K60_THERMAL_SERVICE_H
#define K60_THERMAL_SERVICE_H

#include <IOKit/IOService.h>
#include <IOKit/IOUserClient.h>
#include <IOKit/IOLib.h>
#include <IOKit/IOWorkLoop.h>
#include <IOKit/IOTimerEventSource.h>
#include <libkern/c++/OSDictionary.h>

#include "K60Tsens.h"
#include "K60ThermalLevel.h"

/* Same contract as the SM8550 reference (ThermalLevel.h:31-41): thermalmonitord
 * of macOS 27.3 polls once a second, selector 0 for the key count, 1 for 15 key
 * codes, 2 for 15 values, and it matches the service by this class name. */
enum {
    kK60SmcSelCount  = 0,
    kK60SmcSelKeys   = 1,
    kK60SmcSelValues = 2,
    kK60SmcSelWrite  = 3,
    kK60SmcSelectors = 4,
    kK60SmcSlots     = 15,
    kK60SmcArrayBytes = kK60SmcSlots * 4,
    kK60SmcWriteBytes = 88,
    kK60SmcKeys       = 1,
};

#define K60SMC_KEY_MTPL 0x6d54504cu /* 'mTPL' */
#define K60SMC_ENTITLEMENT "com.apple.private.smcsensor.user-access"

/* Registry property names, one per published reading. Kept short so that
 * "ioreg -l | grep K60T" stays readable in a boot log. */
#define K60PROP_VERSION "K60TsensVersion"
#define K60PROP_CTRL    "K60TsensCtrl"
#define K60PROP_LEVEL   "K60ThermalLevel"
#define K60PROP_SAMPLES "K60ThermalSamples"
#define K60PROP_FAILED  "K60ThermalFailedReads"
#define K60PROP_BASE    "K60TsensBase"

class K60ThermalSensor : public IOService {
    OSDeclareDefaultStructors(K60ThermalSensor)
public:
    bool start(IOService *provider) override;
    void stop(IOService *provider) override;
    void free() override;
    /* Fold this controller's valid readings into the caller's five-domain array,
     * raising an entry only when this controller is hotter. K60TL_NO_READING in
     * an entry means "no reading yet". Safe with no hardware mapped. */
    void sampleDomains(int32_t domain_milli_c[K60TlInputs]);
    /* Physical windows to map when this service is created by k60_thermal_start
     * rather than matched against a device-tree nub. The ADT has no tsens node
     * yet (06-KEXT-SERVICE.md §5), and both bases are in the board DTB
     * (mondrian.dts:16440 / :16450), so they are cited constants, not guesses. */
    void setPhysicalWindows(uint64_t tm_physical, uint64_t srot_physical);

private:
    IOWorkLoop *loop = nullptr;
    IOTimerEventSource *timer = nullptr;
    IOMemoryMap *tmMap = nullptr;
    IOMemoryMap *srotMap = nullptr;
    const volatile uint32_t *tm = nullptr;
    const volatile uint32_t *srot = nullptr;
    uint32_t controller = 0;
    uint32_t samples = 0, failedReads = 0;
    uint64_t tmPhysical = 0, srotPhysical = 0;
    bool published = false;
    bool mapWindow(unsigned index, uint64_t physical, IOMemoryMap **out,
                   const volatile uint32_t **base);
    bool publishProperties();
    void sampleOnce();
    static void timerFired(OSObject *owner, IOTimerEventSource *sender);
};

class AppleSMCSensorDispatcher;

class AppleSMCSensorDispatcherUserClient : public IOUserClient {
    OSDeclareDefaultStructors(AppleSMCSensorDispatcherUserClient)
public:
    bool initWithTask(task_t owningTask, void *securityToken, UInt32 type) override;
    bool start(IOService *provider) override;
    IOReturn clientClose() override;
    IOReturn externalMethod(uint32_t selector, IOExternalMethodArguments *arguments,
                            IOExternalMethodDispatch *dispatch, OSObject *target, void *reference) override;
    /* Public: the selector dispatch table is a file-scope constant
     * (same layout as ThermalLevel.cpp:160-166). */
    static IOReturn sCount(OSObject *target, void *reference, IOExternalMethodArguments *arguments);
    static IOReturn sKeys(OSObject *target, void *reference, IOExternalMethodArguments *arguments);
    static IOReturn sValues(OSObject *target, void *reference, IOExternalMethodArguments *arguments);
    static IOReturn sWrite(OSObject *target, void *reference, IOExternalMethodArguments *arguments);
private:
    AppleSMCSensorDispatcher *dispatcher = nullptr;
    uint64_t counts = 0, refusals = 0, writes = 0;
};

class AppleSMCSensorDispatcher : public IOService {
    OSDeclareDefaultStructors(AppleSMCSensorDispatcher)
public:
    bool start(IOService *provider) override;
    /* Both controllers feed the level: GPU sits on tsens0 idx14/15, the little
     * cluster, NPU and DDR on tsens1 idx1..9, so a single controller would leave
     * half the domains permanently without a reading. */
    bool publish(K60ThermalSensor *first, K60ThermalSensor *second);
    unsigned level(int32_t domain_milli_c[K60TlInputs]);
    K60ThermalSensor *sensor() const { return attached[0]; }
private:
    K60ThermalSensor *attached[2] = { nullptr, nullptr };
    K60TlState levelState = {};
    unsigned lastLevel = 0;
};

#endif /* K60_THERMAL_SERVICE_H */
