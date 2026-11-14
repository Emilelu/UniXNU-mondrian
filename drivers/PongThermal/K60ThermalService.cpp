/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/* Kernel side of the K60 thermal line; see K60ThermalService.h for the object
 * model and docs/research/thermal/06-KEXT-SERVICE.md for the evidence trail.
 *
 * Read-only by construction: the TM window is mapped kIOMapInhibitCache and only
 * read; the SROT window is mapped only to read the version and the enable bit.
 * There is no register write, no interrupt, and no notification post anywhere in
 * this file. */
#include <IOKit/IODeviceTreeSupport.h>
#include <IOKit/IODeviceMemory.h>
#include <IOKit/IOPlatformExpert.h>
#include <IOKit/IOMemoryDescriptor.h>
#include <IOKit/IOKitKeys.h>
#include <libkern/c++/OSBoolean.h>
#include <libkern/c++/OSData.h>
#include <libkern/c++/OSNumber.h>
#include <libkern/c++/OSString.h>
#include <libkern/c++/OSSymbol.h>
#include <pexpert/pexpert.h>

#include "K60ThermalService.h"

OSDefineMetaClassAndStructors(K60ThermalSensor, IOService)
OSDefineMetaClassAndStructors(AppleSMCSensorDispatcherUserClient, IOUserClient)
OSDefineMetaClassAndStructors(AppleSMCSensorDispatcher, IOService)

namespace {

/* MMIO pages are mapped whole: the DT declares 0x1ff bytes per window
 * (mondrian.dts:16439-16455) but a mapping is page granular, so 0x1000 is used.
 * Same choice as the SM8550 reference, ThermalProbe.cpp:83-90. */
constexpr IOByteCount kWindowBytes = 0x1000;
constexpr uint32_t kPollMs = 1000;

/* Published per-sensor property, "K60Temp00" .. "K60Temp31", in the order of
 * k60tsens_sensor_table (tsens0 idx0..15 then tsens1 idx0..15). */
char *sensorKey(unsigned slot)
{
    static char keys[K60TsensSensorCount][12];
    static bool built = false;
    if (!built) {
        for (unsigned i = 0; i < K60TsensSensorCount; ++i) {
            keys[i][0] = 'K'; keys[i][1] = '6'; keys[i][2] = '0'; keys[i][3] = 'T';
            keys[i][4] = 'e'; keys[i][5] = 'm'; keys[i][6] = 'p';
            keys[i][7] = char('0' + (i / 10) % 10);
            keys[i][8] = char('0' + i % 10);
            keys[i][9] = 0;
        }
        built = true;
    }
    return keys[slot];
}

} /* namespace */

/* ---------------------------------------------------------------- sensor --- */

void K60ThermalSensor::setPhysicalWindows(uint64_t tm_physical, uint64_t srot_physical)
{
    tmPhysical = tm_physical;
    srotPhysical = srot_physical;
    /* tsens0 is the lower pair; the board table is ordered tsens0 first. */
    controller = (tm_physical == 0xc265000ull) ? 1u : 0u;
}

/* Two sources, in this order: the physical windows the board DTB declares
 * (mondrian.dts:16440 / :16450), or, when this nub came from a device-tree node,
 * that node's own reg entries. Both end in the same read-only mapping. */
bool K60ThermalSensor::mapWindow(unsigned index, uint64_t physical, IOMemoryMap **out,
                                 const volatile uint32_t **base)
{
    IOMemoryMap *map = nullptr;
    if (physical) {
        IOMemoryDescriptor *descriptor =
            IOMemoryDescriptor::withPhysicalAddress(physical, kWindowBytes, kIODirectionInOut);
        if (!descriptor) {
            IOLog("K60Thermal: window %u at %#llx has no descriptor\n", index,
                  (unsigned long long)physical);
            return false;
        }
        map = descriptor->map(kIOMapAnywhere | kIOMapInhibitCache);
        descriptor->release();
    } else {
        IODeviceMemory *memory = getDeviceMemoryWithIndex(index);
        if (!memory) {
            IOLog("K60Thermal: window %u has no device memory\n", index);
            return false;
        }
        map = memory->map(kIOMapAnywhere | kIOMapInhibitCache);
    }
    if (!map) {
        IOLog("K60Thermal: window %u did not map\n", index);
        return false;
    }
    *out = map;
    *base = reinterpret_cast<const volatile uint32_t *>(map->getVirtualAddress());
    return *base != nullptr;
}

bool K60ThermalSensor::start(IOService *provider)
{
    if (!IOService::start(provider)) return false;

    /* ADT path: a nub created from scripts/make-pong-adt.py carries the two
     * absolute bases as properties instead of reg entries, because the arm-io
     * ranges window (0x17000000 + 0x02000000) does not cover 0xc263000.
     * Device-tree properties live on the nub, so read the provider first. */
    IOService *node = provider ? provider : this;
    if (!tmPhysical) {
        OSData *tm = OSDynamicCast(OSData, node->getProperty("pong,tsens-tm-base"));
        OSData *srot = OSDynamicCast(OSData, node->getProperty("pong,tsens-srot-base"));
        if (tm && srot && tm->getLength() == sizeof(uint64_t) && srot->getLength() == sizeof(uint64_t)) {
            setPhysicalWindows(*(const uint64_t *)tm->getBytesNoCopy(),
                               *(const uint64_t *)srot->getBytesNoCopy());
        }
    }

    /* The DT gives reg = <TM 0x1ff, SROT 0x1ff>; index 0 is the TM window and
     * index 1 the SROT window (mondrian.dts:16439-16455). */
    if (!mapWindow(0, tmPhysical, &tmMap, &tm)) { stop(provider); return false; }
    if (!mapWindow(1, srotPhysical, &srotMap, &srot)) { stop(provider); return false; }

    /* Which controller this nub is. A DT-matched nub learns it from its node
     * name; a nub created by k60_thermal_start already set it from the base. */
    OSString *name = OSDynamicCast(OSString, node->getProperty("name"));
    if (name) controller = name->isEqualTo("thermal-sensor@c265000") ? 1u : 0u;

    loop = IOWorkLoop::workLoop();
    if (!loop) { stop(provider); return false; }
    timer = IOTimerEventSource::timerEventSource(this, &K60ThermalSensor::timerFired);
    if (!timer || loop->addEventSource(timer) != kIOReturnSuccess) { stop(provider); return false; }

    /* First sample before publishing, so a consumer never reads an empty node. */
    sampleOnce();
    if (!publishProperties()) { stop(provider); return false; }
    published = true;

    /* One second, matching thermalmonitord's own polling interval
     * (ThermalLevel.h:6-25: the dispatcher helper polls every 1.0 s). */
    timer->setTimeoutMS(kPollMs);
    registerService();
    IOLog("K60Thermal: tsens%u mapped, %u sensors, version %u.%u.%u\n",
          controller, (unsigned)K60TsensSensorsPerController,
          (unsigned)K60TSENS_VER_MAJOR(srot ? srot[K60TSENS_SROT_HW_VER / 4] : 0),
          (unsigned)K60TSENS_VER_MINOR(srot ? srot[K60TSENS_SROT_HW_VER / 4] : 0),
          (unsigned)K60TSENS_VER_STEP(srot ? srot[K60TSENS_SROT_HW_VER / 4] : 0));
    return true;
}

void K60ThermalSensor::stop(IOService *provider)
{
    if (timer) {
        timer->cancelTimeout();
        if (loop) loop->removeEventSource(timer);
        timer->release();
        timer = nullptr;
    }
    if (loop) { loop->release(); loop = nullptr; }
    if (tmMap) { tmMap->release(); tmMap = nullptr; }
    if (srotMap) { srotMap->release(); srotMap = nullptr; }
    tm = nullptr;
    srot = nullptr;
    IOService::stop(provider);
}

void K60ThermalSensor::free()
{
    if (timer) { timer->release(); timer = nullptr; }
    if (loop) { loop->release(); loop = nullptr; }
    if (tmMap) { tmMap->release(); tmMap = nullptr; }
    if (srotMap) { srotMap->release(); srotMap = nullptr; }
    IOService::free();
}

void K60ThermalSensor::timerFired(OSObject *owner, IOTimerEventSource *sender)
{
    K60ThermalSensor *self = OSDynamicCast(K60ThermalSensor, owner);
    if (!self) return;
    self->sampleOnce();
    self->publishProperties();
    sender->setTimeoutMS(kPollMs);
}

void K60ThermalSensor::sampleOnce()
{
    if (!tm) { ++failedReads; return; }
    K60TsensReading readings[K60TsensSensorsPerController];
    int valid = k60tsens_read_controller(tm, readings);
    if (valid < 0) { ++failedReads; return; }
    ++samples;
    for (unsigned i = 0; i < K60TsensSensorsPerController; ++i) {
        if (!readings[i].valid) { ++failedReads; continue; }
        OSNumber *value = OSNumber::withNumber((uint64_t)(int64_t)readings[i].milli_c, 32);
        if (!value) continue;
        setProperty(sensorKey(controller * K60TsensSensorsPerController + i), value);
        value->release();
    }
    setProperty(K60PROP_SAMPLES, (uint64_t)samples, 32);
    setProperty(K60PROP_FAILED, (uint64_t)failedReads, 32);
}

bool K60ThermalSensor::publishProperties()
{
    if (!srot || !tm) return false;
    const uint32_t version = srot[K60TSENS_SROT_HW_VER / 4];
    const uint32_t ctrl = srot[K60TSENS_SROT_CTRL / 4];
    setProperty(K60PROP_VERSION, (uint64_t)version, 32);
    setProperty(K60PROP_CTRL, (uint64_t)ctrl, 32);
    setProperty(K60PROP_BASE, (uint64_t)(uintptr_t)tm, 64);
    return true;
}

void K60ThermalSensor::sampleDomains(int32_t domain_milli_c[K60TlInputs])
{
    if (!tm) return;

    K60TsensReading readings[K60TsensSensorsPerController];
    if (k60tsens_read_controller(tm, readings) < 0) return;
    /* Fold this controller's 16 sensors into the five pressure domains. A domain
     * takes the hottest valid reading among its sensors; the mapping is
     * k60tl_input_of_sensor() so that both controllers agree on the split. */
    for (unsigned i = 0; i < K60TsensSensorsPerController; ++i) {
        if (!readings[i].valid) continue;
        unsigned slot = controller * K60TsensSensorsPerController + i;
        unsigned domain = k60tl_input_of_sensor(slot);
        if (domain >= K60TlInputs) continue;
        if (domain_milli_c[domain] == K60TL_NO_READING || readings[i].milli_c > domain_milli_c[domain])
            domain_milli_c[domain] = readings[i].milli_c;
    }
}

/* ------------------------------------------------------------ dispatcher --- */

bool AppleSMCSensorDispatcher::start(IOService *provider)
{
    return IOService::start(provider);
}

bool AppleSMCSensorDispatcher::publish(K60ThermalSensor *first, K60ThermalSensor *second)
{
    if (!first) return false;
    attached[0] = first;
    attached[1] = second;
    /* thermalmonitord looks the nub up by class name and then instantiates the
     * user client named here (reference: ThermalLevel.cpp:47-70). */
    setProperty(kIOUserClientClassKey, "AppleSMCSensorDispatcherUserClient");
    registerService();
    IOLog("K60Thermal: dispatcher published\n");
    return true;
}

unsigned AppleSMCSensorDispatcher::level(int32_t domain_milli_c[K60TlInputs])
{
    for (unsigned i = 0; i < K60TlInputs; ++i) domain_milli_c[i] = K60TL_NO_READING;
    for (unsigned i = 0; i < 2; ++i) {
        if (attached[i]) attached[i]->sampleDomains(domain_milli_c);
    }
    /* One shared hysteresis state: both controllers update the same five inputs. */
    lastLevel = k60tl_step(&levelState, domain_milli_c);
    if (attached[0]) attached[0]->setProperty(K60PROP_LEVEL, (uint64_t)lastLevel, 32);
    return lastLevel;
}

/* ------------------------------------------------------------ user client --- */

bool AppleSMCSensorDispatcherUserClient::initWithTask(task_t owningTask, void *securityToken, UInt32 type)
{
    if (copyClientEntitlement(owningTask, K60SMC_ENTITLEMENT) != kOSBooleanTrue) {
        ++refusals;
        return false;
    }
    return IOUserClient::initWithTask(owningTask, securityToken, type);
}

bool AppleSMCSensorDispatcherUserClient::start(IOService *provider)
{
    if (!IOUserClient::start(provider)) return false;
    dispatcher = OSDynamicCast(AppleSMCSensorDispatcher, provider);
    if (!dispatcher) return false;
    setProperty(kIOUserClientDefaultLockingKey, kOSBooleanTrue);
    return true;
}

IOReturn AppleSMCSensorDispatcherUserClient::clientClose()
{
    terminate();
    return kIOReturnSuccess;
}

/* The four selector handlers are public because the dispatch table below is a
 * file-scope constant (same layout as ThermalLevel.cpp:160-166). */
IOReturn AppleSMCSensorDispatcherUserClient::sCount(OSObject *, void *, IOExternalMethodArguments *arguments)
{
    if (!arguments->scalarOutput || arguments->scalarOutputCount < 1) return kIOReturnBadArgument;
    arguments->scalarOutput[0] = kK60SmcKeys;
    return kIOReturnSuccess;
}

IOReturn AppleSMCSensorDispatcherUserClient::sKeys(OSObject *, void *, IOExternalMethodArguments *arguments)
{
    uint32_t *out = static_cast<uint32_t *>(arguments->structureOutput);
    if (!out) return kIOReturnBadArgument;
    for (unsigned i = 0; i < kK60SmcSlots; ++i) out[i] = 0;
    out[0] = K60SMC_KEY_MTPL;
    return kIOReturnSuccess;
}

IOReturn AppleSMCSensorDispatcherUserClient::sValues(OSObject *target, void *, IOExternalMethodArguments *arguments)
{
    AppleSMCSensorDispatcherUserClient *self = OSDynamicCast(AppleSMCSensorDispatcherUserClient, target);
    if (!self) return kIOReturnBadArgument;
    uint32_t *out = static_cast<uint32_t *>(arguments->structureOutput);
    if (!out) return kIOReturnBadArgument;

    int32_t domains[K60TlInputs];
    const unsigned level = self->dispatcher ? self->dispatcher->level(domains) : 0;
    for (unsigned i = 0; i < kK60SmcSlots; ++i) out[i] = 0;
    /* Slot order is the key order of sKeys; the pressure level is the only key
     * this board reports. Foundation maps 1,2 -> Fair, 3 -> Serious, 4 -> Critical. */
    out[0] = level;
    ++self->counts;
    return kIOReturnSuccess;
}

IOReturn AppleSMCSensorDispatcherUserClient::sWrite(OSObject *target, void *, IOExternalMethodArguments *arguments)
{
    AppleSMCSensorDispatcherUserClient *self = OSDynamicCast(AppleSMCSensorDispatcherUserClient, target);
    if (!self) return kIOReturnBadArgument;
    if (!arguments->structureInput || arguments->structureInputSize < kK60SmcWriteBytes) return kIOReturnBadArgument;
    /* The write selector only feeds the usage counters of the reference; there is
     * no writable thermal state on this board, so it is accepted and ignored. */
    ++self->writes;
    return kIOReturnSuccess;
}

static const IOExternalMethodDispatch kK60SmcMethods[kK60SmcSelectors] = {
    { &AppleSMCSensorDispatcherUserClient::sCount,  0, 0, 1, 0 },
    { &AppleSMCSensorDispatcherUserClient::sKeys,   0, 0, 0, kK60SmcArrayBytes },
    { &AppleSMCSensorDispatcherUserClient::sValues, 0, 0, 0, kK60SmcArrayBytes },
    { &AppleSMCSensorDispatcherUserClient::sWrite,  0, kK60SmcWriteBytes, 0, 0 },
};

IOReturn AppleSMCSensorDispatcherUserClient::externalMethod(uint32_t selector,
        IOExternalMethodArguments *arguments, IOExternalMethodDispatch *dispatch,
        OSObject *target, void *reference)
{
    if (selector >= kK60SmcSelectors) return kIOReturnUnsupported;
    return IOUserClient::externalMethod(selector, arguments,
        const_cast<IOExternalMethodDispatch *>(&kK60SmcMethods[selector]),
        target ? target : this, reference);
}

/* ---------------------------------------------------------------- entry --- */

/* Called from the platform expert once the DT nubs exist. Weak so that a build
 * without the platform hook still links (P-190: verify the symbol, not the name). */
/* Bases from the board DTB, /soc/thermal-sensor@c263000 and @c265000:
 * reg = <0xc263000 0x1ff 0xc222000 0x1ff> and <0xc265000 0x1ff 0xc223000 0x1ff>
 * (mondrian.dts:16440 / :16450). TM first, SROT second. */
static const struct {
    uint64_t tm;
    uint64_t srot;
} kK60TsensWindows[K60TsensControllers] = {
    { 0xc263000ull, 0xc222000ull },
    { 0xc265000ull, 0xc223000ull },
};

/* Attach one controller. The sensor is created here, not matched against a
 * device-tree node: the ADT this kernel boots from has no tsens child under
 * /arm-io (scripts/make-pong-adt.py:235-248), so the Info.plist personalities
 * cannot fire yet. The bases are the DTB's own, and the mapping is read-only. */
static K60ThermalSensor *k60_thermal_sensor(IOService *platform, unsigned controller)
{
    K60ThermalSensor *sensor = OSTypeAlloc(K60ThermalSensor);
    if (!sensor) return nullptr;
    sensor->setPhysicalWindows(kK60TsensWindows[controller].tm, kK60TsensWindows[controller].srot);
    if (!sensor->init()) { sensor->release(); return nullptr; }
    if (!sensor->attach(platform)) { sensor->release(); return nullptr; }
    if (!sensor->start(platform)) {
        sensor->detach(platform);
        sensor->release();
        return nullptr;
    }
    /* start() took the registry reference; the creator keeps its own. */
    return sensor;
}

extern "C" int k60_thermal_start(void)
{
    char arg[16];
    if (PE_parse_boot_argn("k60-thermal", arg, sizeof(arg))) {
        if (arg[0] == '0') { IOLog("K60Thermal: disabled by boot arg\n"); return 0; }
    }

    IOService *platform = IOService::getPlatform();
    if (!platform) return -1;

    K60ThermalSensor *sensors[K60TsensControllers] = { nullptr, nullptr };
    for (unsigned i = 0; i < K60TsensControllers; ++i) {
        sensors[i] = k60_thermal_sensor(platform, i);
        if (!sensors[i]) {
            IOLog("K60Thermal: tsens%u did not start; no dispatcher published\n", i);
            for (unsigned j = 0; j < i; ++j) {
                sensors[j]->stop(platform);
                sensors[j]->detach(platform);
                sensors[j]->release();
            }
            return -2;
        }
    }

    /* Attach the dispatcher under the platform expert, as the reference does
     * (ThermalLevel.cpp:178-225): the nub must be reachable from the root so that
     * a user client can be opened against it. */
    AppleSMCSensorDispatcher *dispatcher = OSTypeAlloc(AppleSMCSensorDispatcher);
    if (!dispatcher) return -3;
    if (!dispatcher->init()) { dispatcher->release(); return -4; }
    if (!dispatcher->attach(platform)) { dispatcher->release(); return -5; }
    if (!dispatcher->start(platform)) {
        dispatcher->detach(platform);
        dispatcher->release();
        return -6;
    }
    if (!dispatcher->publish(sensors[0], sensors[1])) { dispatcher->release(); return -7; }
    dispatcher->release();
    IOLog("K60Thermal: service started, 2 controllers, %u sensors\n",
          (unsigned)K60TsensSensorCount);
    return 1;
}
