/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/* Darwin userspace, read-only: k60-battery-smoke [samples]
 * Queries the real K60Battery IORegistry object and watches live sequence/
 * notification updates. No Android/sysfs source, battery writes or shim. */
#include <CoreFoundation/CoreFoundation.h>
#include <dlfcn.h>
#include <mach/mach.h>
#include <mach/mach_time.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

typedef uint32_t IOObject;
static CFMutableDictionaryRef (*matching)(const char *);
static kern_return_t (*services)(mach_port_t, CFDictionaryRef, IOObject *);
static IOObject (*next)(IOObject);
static kern_return_t (*release_object)(IOObject);
static kern_return_t (*properties)(IOObject, CFMutableDictionaryRef *, CFAllocatorRef, uint32_t);

static int number(CFDictionaryRef d, CFStringRef key, int64_t *out)
{
    CFTypeRef value = CFDictionaryGetValue(d, key);
    return value && CFGetTypeID(value) == CFNumberGetTypeID() &&
        CFNumberGetValue((CFNumberRef)value, kCFNumberSInt64Type, out);
}
static int flag(CFDictionaryRef d, CFStringRef key, int *out)
{
    CFTypeRef value = CFDictionaryGetValue(d, key);
    if (!value || CFGetTypeID(value) != CFBooleanGetTypeID()) return 0;
    *out = CFBooleanGetValue((CFBooleanRef)value);
    return 1;
}
static uint64_t uptime_ms(void)
{
    mach_timebase_info_data_t t;
    if (mach_timebase_info(&t) != KERN_SUCCESS || !t.denom) return 0;
    const uint64_t now = mach_absolute_time();
    return (now / t.denom * t.numer + (now % t.denom) * t.numer / t.denom) / 1000000;
}
int main(int argc, char **argv)
{
    unsigned samples = 6;
    if (argc > 2) {fprintf(stderr, "usage: %s [samples]\n", argv[0]); return 1;}
    if (argc == 2) {
        char *end;
        unsigned long n = strtoul(argv[1], &end, 10);
        if (!argv[1][0] || *end || n < 2 || n > 120) {fprintf(stderr, "samples must be2..120\n"); return 1;}
        samples = (unsigned)n;
    }
    void *kit = dlopen("/System/Library/Frameworks/IOKit.framework/IOKit", RTLD_NOW | RTLD_LOCAL);
    if (!kit) {fprintf(stderr, "IOKit unavailable: %s\n", dlerror()); return 1;}
    matching = (CFMutableDictionaryRef (*)(const char *))dlsym(kit, "IOServiceMatching");
    services = (kern_return_t (*)(mach_port_t, CFDictionaryRef, IOObject *))dlsym(kit, "IOServiceGetMatchingServices");
    next = (IOObject (*)(IOObject))dlsym(kit, "IOIteratorNext");
    release_object = (kern_return_t (*)(IOObject))dlsym(kit, "IOObjectRelease");
    properties = (kern_return_t (*)(IOObject, CFMutableDictionaryRef *, CFAllocatorRef, uint32_t))
        dlsym(kit, "IORegistryEntryCreateCFProperties");
    if (!matching || !services || !next || !release_object || !properties) {
        fprintf(stderr, "required real IOKit registry APIs are absent\n"); dlclose(kit); return 1;
    }
    CFMutableDictionaryRef query = matching("K60Battery");
    IOObject iterator = 0, source = 0;
    if (!query) {dlclose(kit); return 1;}
    if (services(0, query, &iterator) != KERN_SUCCESS || !iterator) {
        fprintf(stderr, "registry lookup failed\n"); dlclose(kit); return 1;
    } /* Matching dictionary consumed by IOServiceGetMatchingServices. */
    source = next(iterator);
    IOObject duplicate = next(iterator);
    release_object(iterator);
    if (duplicate) {release_object(duplicate); if (source) release_object(source); dlclose(kit); return 1;}
    if (!source) {
        fprintf(stderr, "NO PHYSICAL SOURCE: check K60Battery blocked/PAS1 handoff/current qualification log; not a battery pass\n");
        dlclose(kit); return 2;
    }
    int result = 0, advanced = 0;
    int64_t first_sequence = -1;
    for (unsigned sample = 0; sample < samples; ++sample) {
        CFMutableDictionaryRef d = NULL;
        if (properties(source, &d, kCFAllocatorDefault, 0) != KERN_SUCCESS || !d) {result = 1; break;}
        int present, stale, external, charging, full;
        int64_t sequence, stamp, epoch, capacity, maximum, voltage, amperage, temperature, cycles, responses;
        const int complete = flag(d, CFSTR("BatteryInstalled"), &present) &&
            flag(d, CFSTR("K60BatteryStale"), &stale) && flag(d, CFSTR("ExternalConnected"), &external) &&
            flag(d, CFSTR("IsCharging"), &charging) && flag(d, CFSTR("FullyCharged"), &full) &&
            number(d, CFSTR("K60BatterySampleSequence"), &sequence) && number(d, CFSTR("K60BatterySampleUptimeMS"), &stamp) &&
            number(d, CFSTR("K60GlinkEpoch"), &epoch) && number(d, CFSTR("CurrentCapacity"), &capacity) &&
            number(d, CFSTR("MaxCapacity"), &maximum) && number(d, CFSTR("Voltage"), &voltage) &&
            number(d, CFSTR("Amperage"), &amperage) && number(d, CFSTR("Temperature"), &temperature) &&
            number(d, CFSTR("CycleCount"), &cycles) && number(d, CFSTR("K60BatteryResponses"), &responses);
        if (!complete) {fprintf(stderr, "incomplete physical registry sample\n"); CFRelease(d); result = 1; break;}
        const uint64_t now = uptime_ms();
        if (!present || stale || epoch <= 0 || sequence <= 0 || responses <= 0 || capacity < 0 || maximum <= 0 ||
            capacity > maximum || voltage < 2000 || voltage > 5500 || cycles < 0 ||
            stamp < 0 || !now || now < (uint64_t)stamp || now - (uint64_t)stamp > 15000) {
            fprintf(stderr, "invalid/stale hardware sample: present=%d stale=%d sequence=%lld epoch=%lld\n",
                present, stale, (long long)sequence, (long long)epoch);
            CFRelease(d); result = 1; break;
        }
        if (first_sequence < 0) first_sequence = sequence;
        if (sequence > first_sequence) advanced = 1;
        printf("sample=%lld stamp=%lldms physical-epoch=%lld current=%lld/%lldmAh voltage=%lldmV amperage=%dmA temp=%d/100C cycles=%lld external=%d charging=%d full=%d responses=%lld\n",
            (long long)sequence, (long long)stamp, (long long)epoch, (long long)capacity, (long long)maximum,
            (long long)voltage, (int32_t)amperage, (int32_t)temperature, (long long)cycles,
            external, charging, full, (long long)responses);
        fflush(stdout);
        if (sample == 0) {
            CFDataRef xml = CFPropertyListCreateData(kCFAllocatorDefault, d, kCFPropertyListXMLFormat_v1_0, 0, NULL);
            if (xml) {fwrite(CFDataGetBytePtr(xml), 1, (size_t)CFDataGetLength(xml), stdout); CFRelease(xml);}
        }
        CFRelease(d);
        if (sample + 1 < samples) sleep(5);
    }
    if (!advanced) {fprintf(stderr, "hardware refresh sequence did not advance\n"); result = 1;}
    release_object(source); dlclose(kit);
    return result;
}
