/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/* K60 physical battery. All physical GLINK traffic and sample assembly run
 * on one workloop. registerService() is delayed until a coherent hardware
 * sample passes field/units/polarity validation. No Android snapshot, fixed
 * percentage, synthetic battery nub or firmware startup is performed here. */
#include <IOKit/IODeviceTreeSupport.h>
#include <IOKit/IOLib.h>
#include <IOKit/IOPlatformExpert.h>
#include <IOKit/IOWorkLoop.h>
#include <IOKit/IOTimerEventSource.h>
#include <IOKit/pwr_mgt/IOPMPowerSource.h>
#include <libkern/c++/OSBoolean.h>
#include <libkern/c++/OSData.h>
#include <libkern/c++/OSDictionary.h>
#include <libkern/c++/OSNumber.h>
#include <libkern/c++/OSString.h>
#include <libkern/c++/OSSymbol.h>
#include <pexpert/pexpert.h>
#include "K60PmicGlink.h"
#include "K60Battmgr.h"
#include "K60BatteryProtocol.generated.h"

namespace {
constexpr uint32_t kPollMs = 20, kRefreshMs = 5000, kRequestMs = 1000, kChannelMs = 5000;
constexpr unsigned kPropertyNumbers = 24;
uint64_t milliseconds()
{
    clock_sec_t seconds; clock_usec_t fraction;
    clock_get_system_microtime(&seconds, &fraction);
    return uint64_t(seconds) * 1000 + fraction / 1000;
}
uint32_t adapterFamily(uint32_t type)
{
    switch (type) {
    case 1: return kIOPSFamilyCodeUSBHost;
    case 2: return kIOPSFamilyCodeUSBChargingPortDedicated;
    case 3: return kIOPSFamilyCodeUSBChargingPortDownstream;
    case 5: return kIOPSFamilyCodeUSBCTypeC;
    case 6: case 7: case 8: return kIOPSFamilyCodeUSBCPD;
    default: return kIOPSFamilyCodeUSBUnknown;
    }
}
}

class K60Battery : public IOPMPowerSource {
    OSDeclareDefaultStructors(K60Battery)
public:
    bool begin(IOService *, const K60BatteryConfig &, const K60AdspGlinkHandoff &);
    void stop(IOService *) override;
    void free() override;
private:
    IOWorkLoop *loop = nullptr;
    IOTimerEventSource *pollTimer = nullptr, *requestTimer = nullptr, *refreshTimer = nullptr;
    bool pollAdded = false, requestAdded = false, refreshAdded = false;
    bool stopped = false, published = false, up = false;
    uint64_t waitingSince = 0, channelDeadline = 0;
    K60PmicGlink transport;
    K60Battmgr manager = {};
    K60BatterySample lastSample = {};
    struct {const OSSymbol *key = nullptr; uint8_t bits = 32; OSNumber *pending = nullptr;} numbers[kPropertyNumbers];
    const OSSymbol *staleKey = nullptr, *fullKey = nullptr, *sourceKindKey = nullptr, *adapterKey = nullptr;
    OSString *capacityBasis = nullptr;
    const OSSymbol *adapterKeys[4] = {};
    uint32_t adapterValues[4] = {}, adapterMask = UINT32_MAX;
    OSDictionary *pendingAdapter = nullptr;
    const OSSymbol *pendingModel = nullptr;
    uint32_t pendingAdapterValues[4] = {}, pendingAdapterMask = 0;
    bool publishFailed = false;
    bool initProperties();
    void cleanup();
    void stale(const char *);
    void publish(const K60BatterySample &);
    void number(unsigned, uint64_t);
    void pump();
    void updateAdapter(const K60BatterySample &);
    void discardPending();
    static void state(void *, bool);
    static void receive(void *, const uint8_t *, unsigned);
    static void pollAction(OSObject *, IOTimerEventSource *);
    static void requestAction(OSObject *, IOTimerEventSource *);
    static void refreshAction(OSObject *, IOTimerEventSource *);
    static IOReturn shutdownAction(OSObject *, void *, void *, void *, void *);
};
OSDefineMetaClassAndStructors(K60Battery, IOPMPowerSource)

bool K60Battery::initProperties()
{
    if (!properties || properties->ensureCapacity(48) < 48) return false;
    /* Property objects are immutable after setPSProperty. Allocate only for
     * changed values; reusing two OSNumbers still mutates retained snapshots
     * two cycles later. No per-poll or unchanged-field allocation. */
    const char *keys[kPropertyNumbers] = {
        kIOPMPSCurrentCapacityKey, kIOPMPSMaxCapacityKey, kIOPMPSVoltageKey, kIOPMPSAmperageKey,
        kIOPMPSCycleCountKey, kIOPMPSTimeRemainingKey, "InstantAmperage", kIOPMPSBatteryTemperatureKey,
        "NominalChargeCapacity", "DesignCapacity", "K60CapacityHundredths", "K60BatterySampleSequence",
        "K60BatterySampleUptimeMS", "K60BatteryValidFields", "K60BatteryResponses", "K60BatteryNotifications",
        "K60BatteryTimeouts", "K60BatteryErrors", "K60BatteryIgnored", "K60GlinkEpoch",
        "K60GlinkReceived", "K60GlinkTransmitted", "K60UsbOnline", "K60WirelessOnline"
    };
    for (unsigned i = 0; i < kPropertyNumbers; ++i) {
        numbers[i].key = OSSymbol::withCString(keys[i]);
        numbers[i].bits = i == 12 || i == 19 ? 64 : 32;
        if (!numbers[i].key) return false;
    }
    staleKey = OSSymbol::withCString("K60BatteryStale");
    fullKey = OSSymbol::withCString(kIOPMFullyChargedKey);
    sourceKindKey = OSSymbol::withCString("K60CurrentCapacityBasis");
    adapterKey = OSSymbol::withCString(kIOPMPSAdapterDetailsKey);
    capacityBasis = OSString::withCString("measured SOC times measured full charge (mAh)");
    if (!staleKey || !fullKey || !sourceKindKey || !adapterKey || !capacityBasis) return false;
    const char *keysForAdapter[] = {kIOPMPSAdapterDetailsFamilyKey, kIOPMPSAdapterDetailsVoltage,
        kIOPMPSAdapterDetailsAmperageKey, kIOPMPSAdapterDetailsWattsKey};
    for (unsigned i = 0; i < 4; ++i) {
        adapterKeys[i] = OSSymbol::withCString(keysForAdapter[i]);
        if (!adapterKeys[i]) return false;
    }
    return true;
}
void K60Battery::number(unsigned index, uint64_t value)
{
    auto &entry = numbers[index];
    OSNumber *old = OSDynamicCast(OSNumber, getPSProperty(entry.key));
    if (entry.bits == 32) value &= UINT32_MAX;
    if (old && old->unsigned64BitValue() == value) return;
    OSNumber *updated = OSNumber::withNumber(value, entry.bits);
    if (!updated) {publishFailed = true; return;}
    entry.pending = updated;
}
void K60Battery::discardPending()
{
    for (auto &entry : numbers) OSSafeReleaseNULL(entry.pending);
    OSSafeReleaseNULL(pendingAdapter); OSSafeReleaseNULL(pendingModel);
}
void K60Battery::stale(const char *why)
{
    if (!published) return;
    if (getPSProperty(staleKey) == kOSBooleanTrue) {updateStatus(); return;}
    setPSProperty(staleKey, kOSBooleanTrue);
    updateStatus();
    IOLog("K60Battery: hardware sample unavailable (%s); preserving last measured values as stale\n", why);
}
void K60Battery::publish(const K60BatterySample &s)
{
    publishFailed = false;
    if (!s.present) {
        if (!published) return;
        updateAdapter(s);
        if (publishFailed) {discardPending(); stale("property allocation failed"); return;}
        if (pendingAdapter) {
            setPSProperty(adapterKey, pendingAdapter); adapterMask = pendingAdapterMask;
            for (unsigned i = 0; i < 4; ++i) adapterValues[i] = pendingAdapterValues[i];
        }
        discardPending();
        setBatteryInstalled(false); setExternalConnected(s.external);
        setExternalChargeCapable(s.external); setIsCharging(false);
        setAtWarnLevel(false); setAtCriticalLevel(false);
        setPSProperty(fullKey, kOSBooleanFalse); setPSProperty(staleKey, kOSBooleanTrue);
        updateStatus();
        IOLog("K60Battery: measured battery absent; last pack measurements are unavailable\n");
        return;
    }
    number(0, s.current_mah); number(1, s.full_mah); number(2, s.voltage_mv);
    number(3, uint32_t(s.current_ma)); number(4, s.cycles);
    number(5, uint32_t(s.time_remaining_min < 0 ? 0xffff : s.time_remaining_min));
    number(6, uint32_t(s.current_ma)); number(7, uint32_t(s.temperature_hundredths));
    number(8, s.full_mah); number(9, s.design_mah); number(10, s.capacity_hundredths);
    number(11, manager.generations); number(12, milliseconds()); number(13, s.valid);
    number(14, manager.responses); number(15, manager.notifications); number(16, manager.timeouts);
    number(17, manager.errors); number(18, manager.ignored); number(19, transport.epoch());
    number(20, transport.received()); number(21, transport.transmitted());
    number(22, manager.value[K60BmUsbOnline]); number(23, manager.value[K60BmWirelessOnline]);
    if (s.model[0]) {
        OSSymbol *old = model();
        if (!old || strcmp(old->getCStringNoCopy(), s.model)) {
            pendingModel = OSSymbol::withCString(s.model);
            if (!pendingModel) publishFailed = true;
        }
    }
    updateAdapter(s);
    if (publishFailed) {discardPending(); stale("property allocation failed"); return;}
    /* All changed immutable objects exist before a single visible property
     * changes. Allocation failure preserves the previous coherent sample. */
    for (auto &entry : numbers) {
        if (entry.pending) setPSProperty(entry.key, entry.pending);
    }
    if (pendingAdapter) {
        setPSProperty(adapterKey, pendingAdapter);
        adapterMask = pendingAdapterMask;
        for (unsigned i = 0; i < 4; ++i) adapterValues[i] = pendingAdapterValues[i];
    }
    if (pendingModel) setModel(const_cast<OSSymbol *>(pendingModel));
    discardPending();
    setBatteryInstalled(s.present); setExternalConnected(s.external);
    setExternalChargeCapable(s.external); setIsCharging(s.charging);
    setAtWarnLevel(s.present && !s.external && s.capacity_hundredths <= 1000);
    setAtCriticalLevel(s.present && !s.external && s.capacity_hundredths <= 200);
    setPSProperty(staleKey, kOSBooleanFalse);
    setPSProperty(fullKey, s.full ? kOSBooleanTrue : kOSBooleanFalse);
    setPSProperty(sourceKindKey, capacityBasis);
    const bool first = !published;
    /* All initial properties must enter the IORegistry before a client can
     * discover the service. updateStatus copies the power-source dictionary. */
    updateStatus();
    if (settingsChangedSinceUpdate) return; /* registry copy failed: do not expose partial initial properties */
    if (first) {published = true; registerService();}
    if (first || s.external != lastSample.external || s.charging != lastSample.charging || s.full != lastSample.full ||
        s.capacity_hundredths != lastSample.capacity_hundredths) {
        IOLog("K60Battery: %s sample=%u SOC=%u.%02u%% charge=%u/%umAh design=%umAh cycles=%u voltage=%umV current=%dmA temp=%d.%02uC external=%d charging=%d full=%d subscribed=%u\n",
            first ? "physical source published" : "physical source updated", manager.generations,
            s.capacity_hundredths / 100, s.capacity_hundredths % 100, s.current_mah, s.full_mah, s.design_mah,
            s.cycles, s.voltage_mv, s.current_ma, s.temperature_hundredths / 100,
            unsigned(s.temperature_hundredths < 0 ? -s.temperature_hundredths : s.temperature_hundredths) % 100,
            s.external, s.charging, s.full, manager.subscribed);
    }
    lastSample = s;
}

void K60Battery::updateAdapter(const K60BatterySample &s)
{
    /* Optional failed adapter properties remain absent, never zero-watt facts.
     * A changed dictionary/number is new: previously retained snapshots stay
     * immutable, and unchanged adapter state requires no allocation. */
    const uint32_t fields[] = {1u << K60BmUsbAdapter, 1u << K60BmUsbVoltage,
        (1u << K60BmUsbMaxCurrent) | (1u << K60BmUsbInputLimit),
        (1u << K60BmUsbVoltage) | (1u << K60BmUsbMaxCurrent) | (1u << K60BmUsbInputLimit)};
    const uint32_t values[] = {s.usb_connected ? adapterFamily(s.adapter_type) : kIOPSFamilyCodeDisconnected,
        s.adapter_mv, s.adapter_ma, uint32_t(uint64_t(s.adapter_mv) * s.adapter_ma / 1000000)};
    uint32_t mask = 0;
    if (!s.external) mask = 1;
    else if (s.usb_connected)
        for (unsigned i = 0; i < 4; ++i) if ((s.valid & fields[i]) == fields[i]) mask |= 1u << i;
    bool changed = mask != adapterMask;
    for (unsigned i = 0; i < 4; ++i) if ((mask & (1u << i)) && values[i] != adapterValues[i]) changed = true;
    if (!changed) return;
    OSDictionary *details = OSDictionary::withCapacity(4);
    if (!details) {publishFailed = true; return;}
    for (unsigned i = 0; i < 4; ++i) {
        if (!(mask & (1u << i))) continue;
        OSNumber *value = OSNumber::withNumber(uint64_t(values[i]), 32);
        if (!value || !details->setObject(adapterKeys[i], value)) publishFailed = true;
        if (value) value->release();
    }
    if (!publishFailed) {
        pendingAdapter = details;
        pendingAdapterMask = mask;
        for (unsigned i = 0; i < 4; ++i) pendingAdapterValues[i] = values[i];
    }
    if (publishFailed) details->release();
}
void K60Battery::pump()
{
    if (stopped || !up || manager.flight || manager.poisoned) return;
    uint8_t bytes[K60_BATTMGR_NOTIFY_BYTES];
    const unsigned length = k60_battmgr_next(&manager, bytes);
    if (!length) return;
    const int rc = transport.send(bytes, length);
    if (rc == QcomGlinkAgain) {
        if (!waitingSince) waitingSince = milliseconds();
        return;
    }
    waitingSince = 0;
    if (rc != QcomGlinkOk) {stale("GLINK send refused"); return;}
    k60_battmgr_sent(&manager);
    requestTimer->setTimeoutMS(kRequestMs);
}
void K60Battery::state(void *owner, bool ready)
{
    auto self = static_cast<K60Battery *>(owner);
    self->up = ready;
    self->waitingSince = 0;
    self->requestTimer->cancelTimeout();
    if (ready) {
        self->channelDeadline = 0;
        k60_battmgr_channel_up(&self->manager);
        IOLog("K60Battery: actual PMIC_RTR_ADSP_APPS channel up; measured sign=%d subscription-ack=%u/%u\n",
            int(self->manager.charging_current_sign), self->manager.notify_reply_type, self->manager.notify_reply_bytes);
    } else {
        k60_battmgr_channel_down(&self->manager);
        self->stale("PMIC channel down");
        if (!self->stopped) self->channelDeadline = milliseconds() + kChannelMs;
    }
}
void K60Battery::receive(void *owner, const uint8_t *data, unsigned bytes)
{
    auto self = static_cast<K60Battery *>(owner);
    if (self->stopped || !self->up) return;
    const int rc = k60_battmgr_receive(&self->manager, data, bytes);
    if (rc == K60BmAnswer || rc == K60BmCycleDone || rc == K60BmSubscribed) self->requestTimer->cancelTimeout();
    if (rc == K60BmCycleDone) {
        K60BatterySample sample;
        if (k60_battmgr_sample(&self->manager, &sample)) self->publish(sample);
        else {
            self->stale("incomplete/unqualified sample");
            IOLog("K60Battery: no publication sample=%u fresh=%x errors=%u sign=%d raw-current=%d raw-temp=%d\n",
                self->manager.generations, self->manager.last_fresh, self->manager.errors,
                int(self->manager.charging_current_sign), self->manager.value[K60BmCurrent], self->manager.value[K60BmTemperature]);
        }
        if (self->manager.refresh_due) k60_battmgr_refresh(&self->manager);
    }
    /* Do not send from inside GLINK's receive callback. RX_DONE must be put
     * into its FIFO first; the poll timer calls pump after native poll returns. */
}
void K60Battery::pollAction(OSObject *owner, IOTimerEventSource *timer)
{
    auto self = OSDynamicCast(K60Battery, owner);
    if (!self || self->stopped) return;
    if (self->transport.poll() < 0 || !self->transport.alive()) {
        self->stale("platform lease invalidated");
        self->refreshTimer->cancelTimeout(); self->requestTimer->cancelTimeout();
        IOLog("K60Battery: physical transport stopped error=%d; no DSP/FIFO reset\n", self->transport.lastError());
        return;
    }
    if (self->channelDeadline && milliseconds() >= self->channelDeadline) {
        self->stale("GLINK handshake timed out");
        self->transport.close();
        self->refreshTimer->cancelTimeout(); self->requestTimer->cancelTimeout();
        IOLog("K60Battery: GLINK epoch never became ready; platform owner must supply a new authenticated session\n");
        return;
    }
    self->pump();
    if (self->waitingSince && milliseconds() - self->waitingSince >= kRequestMs) {
        self->stale("GLINK FIFO/intent backpressure");
        self->channelDeadline = milliseconds() + kChannelMs;
        if (!self->transport.reopen()) {self->transport.close(); return;}
    }
    timer->setTimeoutMS(kPollMs);
}
void K60Battery::requestAction(OSObject *owner, IOTimerEventSource *)
{
    auto self = OSDynamicCast(K60Battery, owner);
    if (!self || self->stopped || !self->manager.flight) return;
    IOLog("K60Battery: physical PMIC request timeout op=%x property=%u; quarantining old channel\n",
        k60_battmgr_opcode(&self->manager), k60_battmgr_property(&self->manager));
    k60_battmgr_timeout(&self->manager);
    self->stale("PMIC response timed out");
    self->channelDeadline = milliseconds() + kChannelMs;
    if (!self->transport.reopen()) self->transport.close();
}
void K60Battery::refreshAction(OSObject *owner, IOTimerEventSource *timer)
{
    auto self = OSDynamicCast(K60Battery, owner);
    if (!self || self->stopped || !self->transport.alive()) return;
    if (self->up) {k60_battmgr_refresh(&self->manager); self->pump();}
    timer->setTimeoutMS(kRefreshMs);
}
bool K60Battery::begin(IOService *provider, const K60BatteryConfig &config, const K60AdspGlinkHandoff &handoff)
{
    if (!IOPMPowerSource::start(provider)) return false;
    k60_battmgr_init(&manager, config.charging_current_sign,
        K60_BATTERY_NOTIFY_REPLY_TYPE, K60_BATTERY_NOTIFY_REPLY_BYTES);
    if (!initProperties()) return false;
    loop = IOWorkLoop::workLoop();
    pollTimer = IOTimerEventSource::timerEventSource(kIOTimerEventSourceOptionsPriorityWorkLoop, this, pollAction);
    requestTimer = IOTimerEventSource::timerEventSource(kIOTimerEventSourceOptionsPriorityWorkLoop, this, requestAction);
    refreshTimer = IOTimerEventSource::timerEventSource(kIOTimerEventSourceOptionsPriorityWorkLoop, this, refreshAction);
    if (!loop || !pollTimer || !requestTimer || !refreshTimer) return false;
    if (loop->addEventSource(pollTimer) != kIOReturnSuccess) return false;
    pollAdded = true;
    if (loop->addEventSource(requestTimer) != kIOReturnSuccess) return false;
    requestAdded = true;
    if (loop->addEventSource(refreshTimer) != kIOReturnSuccess) return false;
    refreshAdded = true;
    const K60PmicGlink::Client callbacks = {state, receive};
    if (!transport.open(config, handoff, callbacks, this)) {
        IOLog("K60Battery: physical transport initialization rejected error=%d; no publication\n", transport.lastError());
        return false;
    }
    channelDeadline = milliseconds() + kChannelMs;
    pollTimer->setTimeoutMS(kPollMs); refreshTimer->setTimeoutMS(kRefreshMs);
    return true;
}
IOReturn K60Battery::shutdownAction(OSObject *owner, void *, void *, void *, void *)
{
    auto self = OSDynamicCast(K60Battery, owner);
    if (!self) return kIOReturnBadArgument;
    self->stopped = true;
    if (self->pollTimer) self->pollTimer->cancelTimeout();
    if (self->requestTimer) self->requestTimer->cancelTimeout();
    if (self->refreshTimer) self->refreshTimer->cancelTimeout();
    self->transport.close();
    return kIOReturnSuccess;
}
void K60Battery::cleanup()
{
    /* runAction owns the same gate as every timer/GLINK callback. Cancellation
     * alone does not serialize with an action already running on the loop. */
    if (loop) loop->runAction(shutdownAction, this);
    else shutdownAction(this, nullptr, nullptr, nullptr, nullptr);
    if (loop) {
        if (refreshAdded) {loop->removeEventSource(refreshTimer); refreshAdded = false;}
        if (requestAdded) {loop->removeEventSource(requestTimer); requestAdded = false;}
        if (pollAdded) {loop->removeEventSource(pollTimer); pollAdded = false;}
    }
    OSSafeReleaseNULL(refreshTimer); OSSafeReleaseNULL(requestTimer); OSSafeReleaseNULL(pollTimer); OSSafeReleaseNULL(loop);
}
void K60Battery::stop(IOService *provider)
{
    cleanup();
    IOPMPowerSource::stop(provider);
}
void K60Battery::free()
{
    cleanup();
    discardPending();
    for (auto &entry : numbers) {
        OSSafeReleaseNULL(entry.key);
    }
    for (auto &key : adapterKeys) OSSafeReleaseNULL(key);
    OSSafeReleaseNULL(capacityBasis);
    OSSafeReleaseNULL(staleKey); OSSafeReleaseNULL(fullKey); OSSafeReleaseNULL(sourceKindKey);
    OSSafeReleaseNULL(adapterKey);
    IOPMPowerSource::free();
}

extern "C" void k60_physical_battery_start(void)
{
    static unsigned attempted;
    unsigned enabled = 1;
    PE_parse_boot_argn("k60_battery", &enabled, sizeof(enabled));
    if (!enabled || __atomic_exchange_n(&attempted, 1u, __ATOMIC_ACQ_REL)) return;
    K60BatteryConfig config;
    const int rc = k60_battery_config_parse(K60BatteryBoardConfig, K60BatteryBoardConfigBytes, &config);
    if (rc) {IOLog("K60Battery: captured board config invalid rc=%d; no hardware access/publication\n", rc); return;}
    IORegistryEntry *chosen = IORegistryEntry::fromPath("/chosen", gIODTPlane);
    OSData *record = chosen ? OSDynamicCast(OSData, chosen->getProperty(K60_ADSP_HANDOFF_PROPERTY)) : nullptr;
    K60AdspGlinkHandoff handoff;
    const int lease = record ? k60_adsp_handoff_parse(static_cast<const uint8_t *>(record->getBytesNoCopy()),
        record->getLength(), &config, &handoff) : K60ConfigNoOwnership;
    if (chosen) chosen->release();
    if (lease) {
        IOLog("K60Battery: blocked rc=%d: no authenticated exclusive PAS1/SMEM/GLINK platform handoff; no MMIO, FIFO writes or power-source publication\n", lease);
        return;
    }
    IOService *provider = IOService::getPlatform();
    K60Battery *battery = new K60Battery;
    bool attached = false;
    if (provider && battery && battery->init()) attached = battery->attach(provider);
    if (!attached || !battery->begin(provider, config, handoff)) {
        if (battery) {if (attached) battery->stop(provider); if (attached) battery->detach(provider); battery->release();}
        IOLog("K60Battery: source setup rejected; no power-source publication\n");
        return;
    }
    /* The builtin service retains its one owner reference for the epoch.
     * Timers only exist after the hardware lease is verified. */
}
