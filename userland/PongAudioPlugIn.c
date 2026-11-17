// SPDX-License-Identifier: BSD-2-Clause-Patent
//
// K60 output-only AudioServerPlugIn. The plug-in publishes one stereo speaker
// device backed by the PongAudio kernel service. It maps the service control
// page and its 512 KiB output ring with IOConnectMapMemory64, converts the
// host's Float32 IO buffers to 32-bit S24/Q31 words, and advances the shared
// write counter. The kernel service owns the DSP graph and consumes 1024-frame
// periods from the same ring.

#include <CoreAudio/AudioServerPlugIn.h>
#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOKitLib.h>
#include <dlfcn.h>
#include <mach/mach_time.h>
#include <math.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <syslog.h>
#include <unistd.h>

#include "PongAudioServiceAbi.h"

enum {
    kPlugIn = kAudioObjectPlugInObject,
    kDevice = 2,
    kOutStream = 3,
    kInStream = 4,
    kVolume = 5,
    kMute = 6,
};

#define kPlugInBundleID "org.unixnu.k60.audio"
#define kDeviceUID "K60AudioDevice"
#define kModelUID "K60AudioModel"

/* Legacy device-volume selectors from AudioHardware.h; the public ASPL
 * header selected for this build does not include that macOS-only file. */
enum {
    kPongDeviceVolumeScalar = 'volm',
    kPongDeviceVolumeDecibels = 'vold',
    kPongDeviceMute = 'mute',
    kPongDeviceDbRange = 'vdb#',
    kPongDeviceScalarToDb = 'v2db',
    kPongDeviceDbToScalar = 'db2v',
};

static const Float64 kRate = PONG_AUDIO_SERVICE_RATE;

static AudioServerPlugInHostRef gHost;
static pthread_mutex_t gLock = PTHREAD_MUTEX_INITIALIZER;
static atomic_uint gRefs = 1;
static io_connect_t gConnect;
static _Atomic(PongAudioServiceControl *) gControl;
static int32_t *gOut;
static mach_vm_address_t gMapped[2];
static atomic_uint gIoUsers;
static atomic_uint gOutActive = 1;
static _Atomic(Float32) gVolume = 0.25f;
static atomic_uint gMuted;
static Float64 gHostTicksPerFrame;
static uint64_t gZeroOrigin;
static uint64_t gZeroSeed;
static uint64_t gWriteFrames;

static Float32 currentVolume(void) {
    return atomic_load(&gVolume);
}

static uint32_t currentMuted(void) {
    return atomic_load(&gMuted);
}

/* ---- Kernel service ---------------------------------------------------- */

static int physicalReady(void) {
    PongAudioServiceControl *control = atomic_load(&gControl);
    return control && (__atomic_load_n(&control->state, __ATOMIC_ACQUIRE) &
        PongAudioServiceOutputReady);
}

static int ready(void) {
    return physicalReady();
}

static void disconnectService(void) {
    atomic_store(&gControl, NULL);
    gOut = NULL;
    for (unsigned i = 0; i < 2; ++i) {
        if (gMapped[i]) {
            IOConnectUnmapMemory64(gConnect, i, mach_task_self(), gMapped[i]);
            gMapped[i] = 0;
        }
    }
    if (gConnect) {
        IOServiceClose(gConnect);
    }
    gConnect = 0;
}

static int mapType(uint32_t type, void **out, mach_vm_size_t minimum) {
    mach_vm_address_t address = 0;
    mach_vm_size_t size = 0;
    if (IOConnectMapMemory64(gConnect, type, mach_task_self(), &address, &size,
        kIOMapAnywhere) != kIOReturnSuccess) {
        return -1;
    }
    gMapped[type] = address;
    if (size < minimum) {
        return -1;
    }
    *out = (void *)(uintptr_t)address;
    return 0;
}

static int connectService(void) {
    if (atomic_load(&gControl)) {
        return physicalReady() ? 0 : -1;
    }
    io_service_t service = IOServiceGetMatchingService(kIOMainPortDefault,
        IOServiceMatching(PONG_AUDIO_SERVICE_CLASS));
    if (!service) {
        return -1;
    }
    kern_return_t kr = IOServiceOpen(service, mach_task_self(), 0, &gConnect);
    IOObjectRelease(service);
    if (kr != KERN_SUCCESS) {
        gConnect = 0;
        return -1;
    }
    void *control = NULL;
    void *out = NULL;
    if (mapType(PongAudioServiceMemoryControl, &control,
            sizeof(PongAudioServiceControl)) ||
        mapType(PongAudioServiceMemoryOutput, &out,
            PONG_AUDIO_SERVICE_RING_BYTES)) {
        disconnectService();
        return -1;
    }
    PongAudioServiceControl *c = control;
    if (c->magic != PONG_AUDIO_SERVICE_MAGIC ||
        c->version != PONG_AUDIO_SERVICE_VERSION ||
        c->rate != PONG_AUDIO_SERVICE_RATE ||
        c->channels != PONG_AUDIO_SERVICE_CHANNELS ||
        c->frame_bytes != PONG_AUDIO_SERVICE_FRAME_BYTES ||
        c->period_frames != PONG_AUDIO_SERVICE_PERIOD_FRAMES ||
        c->ring_frames != PONG_AUDIO_SERVICE_RING_FRAMES ||
        !(c->state & PongAudioServiceOutputReady)) {
        disconnectService();
        return -1;
    }
    gOut = out;
    atomic_store(&gControl, c);
    syslog(LOG_NOTICE, "PongAudio HAL: K60 stereo service connected");
    return 0;
}

static void *awaitService(void *unused) {
    (void)unused;
    usleep(100000);
    for (unsigned i = 0; i < 300; i++) {
        pthread_mutex_lock(&gLock);
        int connected = connectService() == 0;
        pthread_mutex_unlock(&gLock);
        if (connected) {
            AudioObjectPropertyAddress changed[2] = {
                {kAudioPlugInPropertyDeviceList, kAudioObjectPropertyScopeGlobal,
                    kAudioObjectPropertyElementMaster},
                {kAudioObjectPropertyOwnedObjects, kAudioObjectPropertyScopeGlobal,
                    kAudioObjectPropertyElementMaster},
            };
            OSStatus result = gHost ? gHost->PropertiesChanged(gHost, kPlugIn, 2,
                changed) : kAudioHardwareNotRunningError;
            if (!result || i < 3 || !(i % 100)) {
                syslog(result ? LOG_ERR : LOG_NOTICE,
                    "PongAudio HAL: device discovery notification result=%d",
                    (int)result);
            }
            if (!result) {
                return NULL;
            }
        }
        usleep(100000);
    }
    syslog(LOG_ERR, "PongAudio HAL: no physical output ready within 30 seconds");
    return NULL;
}

static kern_return_t call(uint32_t selector) {
    return gConnect ? IOConnectCallScalarMethod(gConnect, selector, NULL, 0,
        NULL, NULL) : KERN_FAILURE;
}

/* CoreAudio loads its host frequency from the dyld shared cache and assumes
 * 24 MHz. K60's architectural counter is 19.2 MHz, so resolve the constant
 * from AudioGetHostClockFrequency's instruction pair and let the service
 * rewrite that double. Without this the audio server's IO cycle runs 25
 * percent long, as porting/power requires us to correct at service start. */
static void setHostClock(void) {
    uintptr_t symbol = (uintptr_t)dlsym(RTLD_DEFAULT,
        "AudioGetHostClockFrequency") & ((((uintptr_t)1) << 47) - 1);
    if (!symbol || !gConnect) {
        return;
    }
    const uint32_t *code = (const uint32_t *)symbol;
    uint32_t adrp = code[0], ldr = code[1];
    if ((adrp & 0x9f000000u) != 0x90000000u ||
        (ldr & 0xffc00000u) != 0xfd400000u ||
        ((ldr >> 5) & 31) != (adrp & 31)) {
        return;
    }
    int64_t pages = (int64_t)(((adrp >> 5) & 0x7ffffu) << 2 |
        ((adrp >> 29) & 3));
    if (pages & (1 << 20)) {
        pages -= 1 << 21;
    }
    uint64_t address = (symbol & ~(uintptr_t)0xfff) +
        (uint64_t)(pages * 4096) + ((ldr >> 10) & 0xfff) * 8;
    kern_return_t r = IOConnectCallScalarMethod(gConnect,
        PongAudioServiceSetHostClock, &address, 1, NULL, NULL);
    syslog(r ? LOG_ERR : LOG_NOTICE,
        "PongAudio HAL: host clock adjustment result=%x", r);
}

/* ---- Helpers ----------------------------------------------------------- */

static AudioStreamBasicDescription format(UInt32 channels) {
    AudioStreamBasicDescription f = {0};
    f.mSampleRate = kRate;
    f.mFormatID = kAudioFormatLinearPCM;
    f.mFormatFlags = kAudioFormatFlagIsFloat | kAudioFormatFlagsNativeEndian |
        kAudioFormatFlagIsPacked;
    f.mBytesPerPacket = 4 * channels;
    f.mFramesPerPacket = 1;
    f.mBytesPerFrame = 4 * channels;
    f.mChannelsPerFrame = channels;
    f.mBitsPerChannel = 32;
    return f;
}

#define REPLY(type, value) do { \
    if (inDataSize < sizeof(type)) return kAudioHardwareBadPropertySizeError; \
    *(type *)outData = (value); \
    *outDataSize = sizeof(type); \
    return 0; \
} while (0)
#define REPLY_STR(text) REPLY(CFStringRef, CFSTR(text))

static UInt32 latencyFrames(void) {
    PongAudioServiceControl *control = atomic_load(&gControl);
    return control ? control->lead_frames : PONG_AUDIO_SERVICE_LEAD_FRAMES;
}

static Float32 toDb(Float32 scalar) {
    return scalar <= 0.0001f ? -96.0f : 20.0f * log10f(scalar);
}

/* ---- IUnknown ---------------------------------------------------------- */

static HRESULT QueryInterface(void *self, REFIID uuid, LPVOID *out);
static ULONG AddRef(void *self) {
    (void)self;
    return atomic_fetch_add(&gRefs, 1) + 1;
}
static ULONG Release(void *self) {
    (void)self;
    UInt32 r = atomic_load(&gRefs);
    if (r) {
        r = atomic_fetch_sub(&gRefs, 1) - 1;
    }
    return r;
}

static OSStatus Initialize(AudioServerPlugInDriverRef d,
    AudioServerPlugInHostRef host) {
    (void)d;
    gHost = host;
    pthread_mutex_lock(&gLock);
    const int alreadyConnected = atomic_load(&gControl) != NULL;
    const int connected = connectService() == 0;
    if (connected && alreadyConnected) {
        setHostClock();
    }
    pthread_mutex_unlock(&gLock);
    syslog(LOG_NOTICE, "PongAudio HAL: AudioServerPlugIn initialized");
    pthread_t worker;
    int created = pthread_create(&worker, NULL, awaitService, NULL);
    if (!created) {
        pthread_detach(worker);
    } else {
        syslog(LOG_ERR, "PongAudio HAL: discovery worker unavailable result=%d",
            created);
    }
    return 0;
}
static OSStatus CreateDevice(AudioServerPlugInDriverRef d, CFDictionaryRef desc,
    const AudioServerPlugInClientInfo *c, AudioObjectID *o) {
    (void)d; (void)desc; (void)c; (void)o;
    return kAudioHardwareUnsupportedOperationError;
}
static OSStatus DestroyDevice(AudioServerPlugInDriverRef d, AudioObjectID o) {
    (void)d; (void)o;
    return kAudioHardwareUnsupportedOperationError;
}
static OSStatus AddDeviceClient(AudioServerPlugInDriverRef d, AudioObjectID o,
    const AudioServerPlugInClientInfo *c) {
    (void)d; (void)o; (void)c;
    return 0;
}
static OSStatus RemoveDeviceClient(AudioServerPlugInDriverRef d, AudioObjectID o,
    const AudioServerPlugInClientInfo *c) {
    (void)d; (void)o; (void)c;
    return 0;
}
static OSStatus PerformDeviceConfigurationChange(AudioServerPlugInDriverRef d,
    AudioObjectID o, UInt64 a, void *i) {
    (void)d; (void)o; (void)a; (void)i;
    return 0;
}
static OSStatus AbortDeviceConfigurationChange(AudioServerPlugInDriverRef d,
    AudioObjectID o, UInt64 a, void *i) {
    (void)d; (void)o; (void)a; (void)i;
    return 0;
}

/* ---- Properties -------------------------------------------------------- */

static Boolean HasProperty(AudioServerPlugInDriverRef d, AudioObjectID o,
    pid_t pid, const AudioObjectPropertyAddress *a);
static OSStatus GetPropertyDataSize(AudioServerPlugInDriverRef d,
    AudioObjectID o, pid_t pid, const AudioObjectPropertyAddress *a,
    UInt32 qs, const void *q, UInt32 *size);
static OSStatus GetPropertyData(AudioServerPlugInDriverRef d, AudioObjectID o,
    pid_t pid, const AudioObjectPropertyAddress *a, UInt32 qs, const void *q,
    UInt32 inDataSize, UInt32 *outDataSize, void *outData);

static bool deviceGainProperty(AudioObjectID o,
    const AudioObjectPropertyAddress *a) {
    return o == kDevice && a->mScope == kAudioObjectPropertyScopeOutput &&
        a->mElement <= 2 &&
        (a->mSelector == kPongDeviceVolumeScalar ||
         a->mSelector == kPongDeviceVolumeDecibels ||
         a->mSelector == kPongDeviceMute);
}

static void gainChanged(void) {
    if (!gHost) {
        return;
    }
    AudioObjectPropertyAddress control[2] = {
        {kAudioLevelControlPropertyScalarValue, kAudioObjectPropertyScopeGlobal, 0},
        {kAudioLevelControlPropertyDecibelValue, kAudioObjectPropertyScopeGlobal, 0},
    };
    AudioObjectPropertyAddress device[3] = {
        {kPongDeviceVolumeScalar, kAudioObjectPropertyScopeOutput, 0},
        {kPongDeviceVolumeDecibels, kAudioObjectPropertyScopeOutput, 0},
        {kPongDeviceMute, kAudioObjectPropertyScopeOutput, 0},
    };
    gHost->PropertiesChanged(gHost, kVolume, 2, control);
    const AudioObjectPropertyAddress mute = {
        kAudioBooleanControlPropertyValue, kAudioObjectPropertyScopeGlobal, 0};
    gHost->PropertiesChanged(gHost, kMute, 1, &mute);
    gHost->PropertiesChanged(gHost, kDevice, 3, device);
}

static OSStatus IsPropertySettable(AudioServerPlugInDriverRef d, AudioObjectID o,
    pid_t pid, const AudioObjectPropertyAddress *a, Boolean *out) {
    (void)d; (void)pid;
    *out = (o == kVolume &&
            (a->mSelector == kAudioLevelControlPropertyScalarValue ||
             a->mSelector == kAudioLevelControlPropertyDecibelValue)) ||
        (o == kMute && a->mSelector == kAudioBooleanControlPropertyValue) ||
        (o == kOutStream &&
         (a->mSelector == kAudioStreamPropertyVirtualFormat ||
          a->mSelector == kAudioStreamPropertyPhysicalFormat ||
          a->mSelector == kAudioStreamPropertyIsActive)) ||
        (o == kDevice && a->mSelector == kAudioDevicePropertyNominalSampleRate) ||
        deviceGainProperty(o, a);
    return HasProperty(d, o, pid, a) ? 0 : kAudioHardwareUnknownPropertyError;
}

static OSStatus SetPropertyData(AudioServerPlugInDriverRef d, AudioObjectID o,
    pid_t pid, const AudioObjectPropertyAddress *a, UInt32 qs, const void *q,
    UInt32 size, const void *data) {
    (void)d; (void)pid; (void)qs; (void)q;
    if ((deviceGainProperty(o, a) && a->mSelector == kPongDeviceMute) ||
        (o == kMute && a->mSelector == kAudioBooleanControlPropertyValue)) {
        if (size != sizeof(UInt32)) {
            return kAudioHardwareBadPropertySizeError;
        }
        UInt32 muted = *(const UInt32 *)data;
        if (muted > 1) {
            return kAudioHardwareIllegalOperationError;
        }
        atomic_store(&gMuted, muted);
        gainChanged();
        return 0;
    }
    if (o == kVolume || deviceGainProperty(o, a)) {
        if (size != sizeof(Float32)) {
            return kAudioHardwareBadPropertySizeError;
        }
        Float32 v = *(const Float32 *)data;
        if (a->mSelector == kAudioLevelControlPropertyDecibelValue ||
            a->mSelector == kPongDeviceVolumeDecibels) {
            v = v <= -96.0f ? 0.0f : powf(10.0f, v / 20.0f);
        } else if (a->mSelector != kAudioLevelControlPropertyScalarValue &&
            a->mSelector != kPongDeviceVolumeScalar) {
            return kAudioHardwareUnknownPropertyError;
        }
        if (!isfinite(v)) {
            return kAudioHardwareIllegalOperationError;
        }
        v = v < 0 ? 0 : v > 1 ? 1 : v;
        atomic_store(&gVolume, v);
        gainChanged();
        return 0;
    }
    if (o == kOutStream && a->mSelector == kAudioStreamPropertyIsActive) {
        if (size != sizeof(UInt32)) {
            return kAudioHardwareBadPropertySizeError;
        }
        const UInt32 active = *(const UInt32 *)data;
        if (active > 1) {
            return kAudioHardwareIllegalOperationError;
        }
        if (atomic_exchange(&gOutActive, active) != active && gHost) {
            gHost->PropertiesChanged(gHost, kOutStream, 1, a);
        }
        return 0;
    }
    if (o == kOutStream && (a->mSelector == kAudioStreamPropertyVirtualFormat ||
        a->mSelector == kAudioStreamPropertyPhysicalFormat)) {
        if (size != sizeof(AudioStreamBasicDescription)) {
            return kAudioHardwareBadPropertySizeError;
        }
        const AudioStreamBasicDescription *f = data;
        const AudioStreamBasicDescription expected = format(2);
        return f->mSampleRate == expected.mSampleRate &&
            f->mFormatID == expected.mFormatID &&
            f->mFormatFlags == expected.mFormatFlags &&
            f->mBytesPerPacket == expected.mBytesPerPacket &&
            f->mFramesPerPacket == 1 &&
            f->mBytesPerFrame == expected.mBytesPerFrame &&
            f->mChannelsPerFrame == 2 &&
            f->mBitsPerChannel == 32 ? 0 : kAudioDeviceUnsupportedFormatError;
    }
    if (o == kDevice && a->mSelector == kAudioDevicePropertyNominalSampleRate) {
        return size >= sizeof(Float64) && *(const Float64 *)data == kRate ?
            0 : kAudioDeviceUnsupportedFormatError;
    }
    return kAudioHardwareUnknownPropertyError;
}

static Boolean HasProperty(AudioServerPlugInDriverRef d, AudioObjectID o,
    pid_t pid, const AudioObjectPropertyAddress *a) {
    UInt32 size = 0;
    return GetPropertyDataSize(d, o, pid, a, 0, NULL, &size) == 0;
}

static OSStatus GetPropertyDataSize(AudioServerPlugInDriverRef d,
    AudioObjectID o, pid_t pid, const AudioObjectPropertyAddress *a,
    UInt32 qs, const void *q, UInt32 *size) {
    UInt8 scratch[1024] = {0};
    UInt32 written = 0;
    OSStatus r = GetPropertyData(d, o, pid, a, qs, q, sizeof scratch,
        &written, scratch);
    if (r == 0) {
        *size = written;
    }
    return r;
}

static UInt32 objects(AudioObjectID o, AudioObjectPropertyScope scope,
    AudioObjectID *list) {
    UInt32 n = 0;
    if (o == kPlugIn && ready()) {
        list[n++] = kDevice;
    } else if (o == kDevice) {
        if (scope != kAudioObjectPropertyScopeInput) {
            list[n++] = kOutStream;
            list[n++] = kVolume;
            list[n++] = kMute;
        }
    }
    return n;
}

static OSStatus propertyData(AudioServerPlugInDriverRef d, AudioObjectID o,
    pid_t pid, const AudioObjectPropertyAddress *a, UInt32 qs, const void *q,
    UInt32 inDataSize, UInt32 *outDataSize, void *outData) {
    (void)d; (void)pid;
    if (o == kInStream) {
        return kAudioHardwareBadObjectError;
    }
    const AudioObjectPropertySelector s = a->mSelector;
    if (o >= kPlugIn && o <= kMute &&
        (s == kAudioObjectPropertyCustomPropertyInfoList ||
         (o == kPlugIn && (s == kAudioPlugInPropertyBoxList ||
          s == kAudioPlugInPropertyClockDeviceList)) ||
         (o == kOutStream && s == 'taps'))) {
        *outDataSize = 0;
        return 0;
    }
    switch (o) {
    case kPlugIn:
        switch (s) {
        case kAudioObjectPropertyBaseClass: REPLY(AudioClassID, kAudioObjectClassID);
        case kAudioObjectPropertyClass: REPLY(AudioClassID, kAudioPlugInClassID);
        case kAudioObjectPropertyOwner: REPLY(AudioObjectID, kAudioObjectUnknown);
        case kAudioObjectPropertyManufacturer: REPLY_STR("UniXNU");
        case kAudioObjectPropertyName: REPLY_STR("K60 Audio");
        case kAudioPlugInPropertyBundleID: REPLY_STR(kPlugInBundleID);
        case kAudioObjectPropertyOwnedObjects:
        case kAudioPlugInPropertyDeviceList: {
            if (!ready() || inDataSize < sizeof(AudioObjectID)) {
                *outDataSize = 0;
                return 0;
            }
            ((AudioObjectID *)outData)[0] = kDevice;
            *outDataSize = sizeof(AudioObjectID);
            return 0;
        }
        case kAudioPlugInPropertyTranslateUIDToDevice: {
            CFStringRef uid = q && qs >= sizeof(CFStringRef) ?
                *(const CFStringRef *)q : NULL;
            REPLY(AudioObjectID, ready() && uid &&
                CFStringCompare(uid, CFSTR(kDeviceUID), 0) == kCFCompareEqualTo ?
                kDevice : kAudioObjectUnknown);
        }
        case kAudioPlugInPropertyResourceBundle: REPLY_STR("");
        default: return kAudioHardwareUnknownPropertyError;
        }
    case kDevice:
        switch (s) {
        case kPongDeviceDbRange:
            if (a->mScope != kAudioObjectPropertyScopeOutput || a->mElement > 2) {
                return kAudioHardwareUnknownPropertyError;
            }
            REPLY(AudioValueRange, ((AudioValueRange){-96.0, 0.0}));
        case kPongDeviceScalarToDb: case kPongDeviceDbToScalar: {
            if (a->mScope != kAudioObjectPropertyScopeOutput || a->mElement > 2) {
                return kAudioHardwareUnknownPropertyError;
            }
            if (inDataSize < sizeof(Float32)) {
                return kAudioHardwareBadPropertySizeError;
            }
            Float32 value = *(Float32 *)outData;
            if (!isfinite(value)) {
                return kAudioHardwareIllegalOperationError;
            }
            if (s == kPongDeviceScalarToDb) {
                value = toDb(value < 0 ? 0 : value > 1 ? 1 : value);
            } else {
                value = value <= -96 ? 0 : value >= 0 ? 1 :
                    powf(10.0f, value / 20.0f);
            }
            REPLY(Float32, value);
        }
        case kPongDeviceVolumeScalar:
            if (!deviceGainProperty(o, a)) {
                return kAudioHardwareUnknownPropertyError;
            }
            REPLY(Float32, currentVolume());
        case kPongDeviceVolumeDecibels:
            if (!deviceGainProperty(o, a)) {
                return kAudioHardwareUnknownPropertyError;
            }
            REPLY(Float32, toDb(currentVolume()));
        case kPongDeviceMute:
            if (!deviceGainProperty(o, a)) {
                return kAudioHardwareUnknownPropertyError;
            }
            REPLY(UInt32, currentMuted());
        case kAudioObjectPropertyBaseClass: REPLY(AudioClassID, kAudioObjectClassID);
        case kAudioObjectPropertyClass: REPLY(AudioClassID, kAudioDeviceClassID);
        case kAudioObjectPropertyOwner: REPLY(AudioObjectID, kPlugIn);
        case kAudioObjectPropertyName: REPLY_STR("K60 Stereo Speakers");
        case kAudioObjectPropertyManufacturer: REPLY_STR("UniXNU");
        case kAudioDevicePropertyDeviceUID: REPLY_STR(kDeviceUID);
        case kAudioDevicePropertyModelUID: REPLY_STR(kModelUID);
        case kAudioObjectPropertyModelName: REPLY_STR("K60 Stereo Speaker");
        case kAudioObjectPropertySerialNumber: REPLY_STR("K60-SM8475");
        case kAudioObjectPropertyFirmwareVersion: REPLY_STR("1.0");
        case kAudioObjectPropertyIdentify: REPLY(UInt32, 0);
        case kAudioObjectPropertyElementName: REPLY_STR("");
        case kAudioDevicePropertyConfigurationApplication: REPLY_STR("com.apple.Preferences");
        case 'accs': REPLY(UInt32, 0);
        case 'auto': REPLY(UInt32, 0);
        case kAudioDevicePropertyTransportType: REPLY(UInt32, kAudioDeviceTransportTypeBuiltIn);
        case kAudioDevicePropertyRelatedDevices: REPLY(AudioObjectID, kDevice);
        case kAudioDevicePropertyClockDomain: REPLY(UInt32, 0);
        case kAudioDevicePropertyDeviceIsAlive: REPLY(UInt32, ready());
        case kAudioDevicePropertyDeviceIsRunning: REPLY(UInt32, gIoUsers > 0);
        case 'siso': REPLY(UInt32, 0);
        case 'drte': REPLY(UInt32, 0);
        case kAudioDevicePropertyDeviceCanBeDefaultDevice:
            REPLY(UInt32, ready() && a->mScope != kAudioObjectPropertyScopeInput);
        case kAudioDevicePropertyDeviceCanBeDefaultSystemDevice:
            REPLY(UInt32, ready() && a->mScope != kAudioObjectPropertyScopeInput);
        case kAudioDevicePropertyLatency: REPLY(UInt32, latencyFrames());
        case kAudioDevicePropertySafetyOffset:
            REPLY(UInt32, latencyFrames() + 2 * PONG_AUDIO_SERVICE_PERIOD_FRAMES);
        case kAudioDevicePropertyNominalSampleRate: REPLY(Float64, kRate);
        case kAudioDevicePropertyAvailableNominalSampleRates:
            REPLY(AudioValueRange, ((AudioValueRange){kRate, kRate}));
        case kAudioDevicePropertyIsHidden: REPLY(UInt32, 0);
        case kAudioDevicePropertyZeroTimeStampPeriod:
            REPLY(UInt32, PONG_AUDIO_SERVICE_RING_FRAMES);
        case kAudioDevicePropertyClockIsStable: REPLY(UInt32, 1);
        case kAudioDevicePropertyClockAlgorithm: REPLY(UInt32, kAudioDeviceClockAlgorithmRaw);
        case kAudioDevicePropertyPreferredChannelsForStereo: {
            if (a->mScope == kAudioObjectPropertyScopeInput) {
                *outDataSize = 0;
                return 0;
            }
            if (inDataSize < 2 * sizeof(UInt32)) {
                return kAudioHardwareBadPropertySizeError;
            }
            UInt32 *channels = outData;
            channels[0] = 1;
            channels[1] = 2;
            *outDataSize = 2 * sizeof(UInt32);
            return 0;
        }
        case kAudioDevicePropertyPreferredChannelLayout: {
            const UInt32 channels = a->mScope == kAudioObjectPropertyScopeInput ? 0 : 2;
            const UInt32 bytes = (UInt32)(offsetof(AudioChannelLayout,
                mChannelDescriptions) + channels * sizeof(AudioChannelDescription));
            if (inDataSize < bytes) {
                return kAudioHardwareBadPropertySizeError;
            }
            AudioChannelLayout *layout = outData;
            memset(layout, 0, bytes);
            layout->mChannelLayoutTag = kAudioChannelLayoutTag_UseChannelDescriptions;
            layout->mNumberChannelDescriptions = channels;
            if (channels) {
                layout->mChannelDescriptions[0].mChannelLabel = kAudioChannelLabel_Left;
                layout->mChannelDescriptions[1].mChannelLabel = kAudioChannelLabel_Right;
            }
            *outDataSize = bytes;
            return 0;
        }
        case kAudioObjectPropertyOwnedObjects:
        case kAudioDevicePropertyStreams:
        case kAudioObjectPropertyControlList: {
            AudioObjectID list[3];
            UInt32 n = objects(kDevice, a->mScope, list);
            UInt32 out = 0;
            for (UInt32 i = 0; i < n; ++i) {
                if (s == kAudioObjectPropertyOwnedObjects && q && qs) {
                    if (qs % sizeof(AudioClassID)) {
                        return kAudioHardwareBadPropertySizeError;
                    }
                    const AudioClassID child = list[i] == kVolume ?
                        kAudioVolumeControlClassID : list[i] == kMute ?
                        kAudioMuteControlClassID : kAudioStreamClassID;
                    const AudioClassID base = list[i] == kVolume ?
                        kAudioLevelControlClassID : list[i] == kMute ?
                        kAudioBooleanControlClassID : kAudioObjectClassID;
                    bool accepted = false;
                    for (UInt32 k = 0; k < qs / sizeof(AudioClassID); k++) {
                        AudioClassID wanted = ((const AudioClassID *)q)[k];
                        if (wanted == child || wanted == base ||
                            wanted == kAudioObjectClassID ||
                            ((list[i] == kVolume || list[i] == kMute) &&
                             wanted == kAudioControlClassID)) {
                            accepted = true;
                        }
                    }
                    if (!accepted) {
                        continue;
                    }
                }
                if (s == kAudioDevicePropertyStreams && list[i] != kOutStream) {
                    continue;
                }
                if (s == kAudioObjectPropertyControlList && list[i] == kOutStream) {
                    continue;
                }
                if ((out + 1) * sizeof(AudioObjectID) > inDataSize) {
                    break;
                }
                ((AudioObjectID *)outData)[out++] = list[i];
            }
            *outDataSize = out * (UInt32)sizeof(AudioObjectID);
            return 0;
        }
        default: return kAudioHardwareUnknownPropertyError;
        }
    case kOutStream:
    case kInStream: {
        const UInt32 channels = o == kOutStream ? 2 : 1;
        switch (s) {
        case kAudioObjectPropertyBaseClass: REPLY(AudioClassID, kAudioObjectClassID);
        case kAudioObjectPropertyClass: REPLY(AudioClassID, kAudioStreamClassID);
        case kAudioObjectPropertyOwner: REPLY(AudioObjectID, kDevice);
        case kAudioObjectPropertyName:
            if (o == kOutStream) {
                REPLY_STR("K60 Speaker Output");
            }
            REPLY_STR("Microphone");
        case kAudioObjectPropertyOwnedObjects: *outDataSize = 0; return 0;
        case kAudioStreamPropertyIsActive: REPLY(UInt32, atomic_load(&gOutActive));
        case kAudioStreamPropertyDirection: REPLY(UInt32, o == kInStream);
        case kAudioStreamPropertyTerminalType:
            REPLY(UInt32, o == kOutStream ? kAudioStreamTerminalTypeSpeaker :
                kAudioStreamTerminalTypeMicrophone);
        case kAudioStreamPropertyStartingChannel: REPLY(UInt32, 1);
        case kAudioStreamPropertyLatency: REPLY(UInt32, 0);
        case kAudioStreamPropertyVirtualFormat:
        case kAudioStreamPropertyPhysicalFormat: REPLY(AudioStreamBasicDescription, format(channels));
        case kAudioStreamPropertyAvailableVirtualFormats:
        case kAudioStreamPropertyAvailablePhysicalFormats: {
            AudioStreamRangedDescription r = {format(channels), {kRate, kRate}};
            REPLY(AudioStreamRangedDescription, r);
        }
        default: return kAudioHardwareUnknownPropertyError;
        }
    }
    case kVolume:
        switch (s) {
        case kAudioObjectPropertyName: REPLY_STR("K60 Speaker Volume");
        case kAudioObjectPropertyBaseClass: REPLY(AudioClassID, kAudioLevelControlClassID);
        case kAudioObjectPropertyClass: REPLY(AudioClassID, kAudioVolumeControlClassID);
        case kAudioObjectPropertyOwner: REPLY(AudioObjectID, kDevice);
        case kAudioObjectPropertyOwnedObjects: *outDataSize = 0; return 0;
        case kAudioControlPropertyScope: REPLY(AudioObjectPropertyScope, kAudioObjectPropertyScopeOutput);
        case kAudioControlPropertyElement: REPLY(AudioObjectPropertyElement, kAudioObjectPropertyElementMaster);
        case kAudioLevelControlPropertyScalarValue: REPLY(Float32, currentVolume());
        case kAudioLevelControlPropertyDecibelValue: REPLY(Float32, toDb(currentVolume()));
        case kAudioLevelControlPropertyDecibelRange: REPLY(AudioValueRange, ((AudioValueRange){-96.0, 0.0}));
        case kAudioLevelControlPropertyConvertScalarToDecibels:
            if (inDataSize < sizeof(Float32)) {
                return kAudioHardwareBadPropertySizeError;
            }
            *(Float32 *)outData = toDb(*(Float32 *)outData);
            *outDataSize = sizeof(Float32);
            return 0;
        case kAudioLevelControlPropertyConvertDecibelsToScalar:
            if (inDataSize < sizeof(Float32)) {
                return kAudioHardwareBadPropertySizeError;
            }
            *(Float32 *)outData = *(Float32 *)outData <= -96.0f ? 0.0f :
                powf(10.0f, *(Float32 *)outData / 20.0f);
            *outDataSize = sizeof(Float32);
            return 0;
        default: return kAudioHardwareUnknownPropertyError;
        }
    case kMute:
        switch (s) {
        case kAudioObjectPropertyName: REPLY_STR("K60 Speaker Mute");
        case kAudioObjectPropertyBaseClass: REPLY(AudioClassID, kAudioBooleanControlClassID);
        case kAudioObjectPropertyClass: REPLY(AudioClassID, kAudioMuteControlClassID);
        case kAudioObjectPropertyOwner: REPLY(AudioObjectID, kDevice);
        case kAudioObjectPropertyOwnedObjects: *outDataSize = 0; return 0;
        case kAudioControlPropertyScope: REPLY(AudioObjectPropertyScope, kAudioObjectPropertyScopeOutput);
        case kAudioControlPropertyElement: REPLY(AudioObjectPropertyElement, kAudioObjectPropertyElementMaster);
        case kAudioBooleanControlPropertyValue: REPLY(UInt32, currentMuted());
        default: return kAudioHardwareUnknownPropertyError;
        }
    default:
        return kAudioHardwareBadObjectError;
    }
}

static OSStatus GetPropertyData(AudioServerPlugInDriverRef d, AudioObjectID o,
    pid_t pid, const AudioObjectPropertyAddress *a, UInt32 qs, const void *q,
    UInt32 size, UInt32 *written, void *data) {
    OSStatus r = propertyData(d, o, pid, a, qs, q, size, written, data);
    if (r) {
        static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
        static struct {
            AudioObjectID object;
            UInt32 selector, scope;
            OSStatus error;
        } seen[48];
        static unsigned count;
        pthread_mutex_lock(&lock);
        unsigned i = 0;
        for (; i < count; i++) {
            if (seen[i].object == o && seen[i].selector == a->mSelector &&
                seen[i].scope == a->mScope && seen[i].error == r) {
                break;
            }
        }
        if (i == count && count < 48) {
            seen[count].object = o;
            seen[count].selector = a->mSelector;
            seen[count].scope = a->mScope;
            seen[count++].error = r;
            UInt32 s = a->mSelector;
            syslog(LOG_NOTICE,
                "PongAudio HAL: property object=%u selector=%c%c%c%c scope=%x error=%d",
                o, (char)(s >> 24), (char)(s >> 16), (char)(s >> 8), (char)s,
                a->mScope, (int)r);
        }
        pthread_mutex_unlock(&lock);
    }
    return r;
}

/* ---- IO ---------------------------------------------------------------- */

static OSStatus StartIO(AudioServerPlugInDriverRef d, AudioObjectID o,
    UInt32 client) {
    (void)d; (void)client;
    if (o != kDevice) {
        return kAudioHardwareBadObjectError;
    }
    pthread_mutex_lock(&gLock);
    OSStatus r = 0;
    if (atomic_load(&gIoUsers) == 0) {
        if (connectService()) {
            r = kAudioHardwareNotRunningError;
        } else if (call(PongAudioServiceStartOutput) != KERN_SUCCESS) {
            r = kAudioHardwareNotRunningError;
        } else {
            setHostClock();
            PongAudioServiceControl *control = atomic_load(&gControl);
            unsigned i;
            for (i = 0; i < 200 && ready() &&
                 !(control->state & PongAudioServiceOutputRunning); i++) {
                usleep(10000);
            }
            if (!ready() || !(control->state & PongAudioServiceOutputRunning)) {
                call(PongAudioServiceStopOutput);
                r = kAudioHardwareNotRunningError;
            } else {
                gWriteFrames = __atomic_load_n(&control->out_write, __ATOMIC_ACQUIRE);
                const uint64_t host = mach_absolute_time();
                const uint64_t anchor = __atomic_load_n(
                    &control->out_anchor_host, __ATOMIC_ACQUIRE);
                gZeroOrigin = host > anchor && gHostTicksPerFrame > 0 ?
                    (uint64_t)((Float64)(host - anchor) / gHostTicksPerFrame) : 0;
                gZeroSeed++;
            }
        }
    }
    if (!r) {
        atomic_fetch_add(&gIoUsers, 1);
    }
    pthread_mutex_unlock(&gLock);
    syslog(r ? LOG_ERR : LOG_NOTICE, "PongAudio HAL: StartIO result=%d", (int)r);
    return r;
}

static OSStatus StopIO(AudioServerPlugInDriverRef d, AudioObjectID o,
    UInt32 client) {
    (void)d; (void)client;
    if (o != kDevice) {
        return kAudioHardwareBadObjectError;
    }
    pthread_mutex_lock(&gLock);
    UInt32 users = atomic_load(&gIoUsers);
    if (users && atomic_fetch_sub(&gIoUsers, 1) == 1) {
        (void)call(PongAudioServiceStopOutput);
    }
    pthread_mutex_unlock(&gLock);
    return 0;
}

static OSStatus GetZeroTimeStamp(AudioServerPlugInDriverRef d, AudioObjectID o,
    UInt32 client, Float64 *sampleTime, UInt64 *hostTime, UInt64 *seed) {
    (void)d; (void)o; (void)client;
    if (!ready()) {
        return kAudioHardwareNotRunningError;
    }
    PongAudioServiceControl *control = atomic_load(&gControl);
    if (!control || gHostTicksPerFrame <= 0) {
        return kAudioHardwareNotRunningError;
    }
    uint32_t seq = 0;
    uint64_t anchor = 0;
    bool stable = false;
    for (unsigned attempt = 0; attempt < 128; attempt++) {
        seq = __atomic_load_n(&control->out_seq, __ATOMIC_ACQUIRE);
        if (seq & 1) {
            continue;
        }
        anchor = __atomic_load_n(&control->out_anchor_host, __ATOMIC_RELAXED);
        __atomic_thread_fence(__ATOMIC_ACQUIRE);
        if (seq == __atomic_load_n(&control->out_seq, __ATOMIC_RELAXED)) {
            stable = true;
            break;
        }
    }
    if (!stable) {
        return kAudioHardwareNotRunningError;
    }
    const uint64_t now = mach_absolute_time();
    const Float64 period = gHostTicksPerFrame *
        PONG_AUDIO_SERVICE_RING_FRAMES;
    const uint64_t origin = anchor +
        (uint64_t)((Float64)gZeroOrigin * gHostTicksPerFrame);
    const uint64_t wraps = now > origin ?
        (uint64_t)((Float64)(now - origin) / period) : 0;
    *sampleTime = (Float64)(gZeroOrigin +
        wraps * PONG_AUDIO_SERVICE_RING_FRAMES);
    *hostTime = origin + (uint64_t)((Float64)wraps * period);
    *seed = 1 + seq / 2 + gZeroSeed;
    return 0;
}

static OSStatus WillDoIOOperation(AudioServerPlugInDriverRef d, AudioObjectID o,
    UInt32 client, UInt32 op, Boolean *will, Boolean *inPlace) {
    (void)d; (void)o; (void)client;
    *will = op == kAudioServerPlugInIOOperationWriteMix;
    *inPlace = true;
    return 0;
}
static OSStatus BeginIOOperation(AudioServerPlugInDriverRef d, AudioObjectID o,
    UInt32 client, UInt32 op, UInt32 frames,
    const AudioServerPlugInIOCycleInfo *info) {
    (void)d; (void)o; (void)client; (void)op; (void)frames; (void)info;
    return 0;
}

static inline int32_t toS24(Float32 v) {
    if (!isfinite(v)) {
        v = 0;
    }
    if (v > 1.0f) {
        v = 1.0f;
    } else if (v < -1.0f) {
        v = -1.0f;
    }
    return (int32_t)(v * 2147483520.0f);
}

static OSStatus DoIOOperation(AudioServerPlugInDriverRef d, AudioObjectID o,
    AudioObjectID stream, UInt32 client, UInt32 op, UInt32 frames,
    const AudioServerPlugInIOCycleInfo *info, void *main, void *secondary) {
    (void)d; (void)o; (void)client; (void)info; (void)secondary;
    if (!ready()) {
        return kAudioHardwareNotRunningError;
    }
    if (op != kAudioServerPlugInIOOperationWriteMix || stream != kOutStream ||
        !main) {
        return 0;
    }
    PongAudioServiceControl *control = atomic_load(&gControl);
    const uint64_t read = __atomic_load_n(&control->out_read, __ATOMIC_ACQUIRE);
    if (gWriteFrames + frames < read ||
        gWriteFrames + frames - read > PONG_AUDIO_SERVICE_RING_FRAMES) {
        return 0;
    }
    const Float32 *src = main;
    const Float32 gain = currentMuted() ? 0.0f : currentVolume();
    const Boolean active = atomic_load(&gOutActive);
    uint32_t position = (uint32_t)(gWriteFrames % PONG_AUDIO_SERVICE_RING_FRAMES);
    for (UInt32 i = 0; i < frames; ++i) {
        int32_t *dst = gOut + 2 * (size_t)position;
        dst[0] = active ? toS24(src[2 * i] * gain) : 0;
        dst[1] = active ? toS24(src[2 * i + 1] * gain) : 0;
        position++;
        if (position == PONG_AUDIO_SERVICE_RING_FRAMES) {
            position = 0;
        }
    }
    gWriteFrames += frames;
    __atomic_store_n(&control->out_write, gWriteFrames, __ATOMIC_RELEASE);
    return 0;
}

static OSStatus EndIOOperation(AudioServerPlugInDriverRef d, AudioObjectID o,
    UInt32 client, UInt32 op, UInt32 frames,
    const AudioServerPlugInIOCycleInfo *info) {
    (void)d; (void)o; (void)client; (void)op; (void)frames; (void)info;
    return 0;
}

static AudioServerPlugInDriverInterface gInterface = {
    NULL, QueryInterface, AddRef, Release, Initialize, CreateDevice,
    DestroyDevice, AddDeviceClient, RemoveDeviceClient,
    PerformDeviceConfigurationChange, AbortDeviceConfigurationChange,
    HasProperty, IsPropertySettable, GetPropertyDataSize, GetPropertyData,
    SetPropertyData, StartIO, StopIO, GetZeroTimeStamp, WillDoIOOperation,
    BeginIOOperation, DoIOOperation, EndIOOperation,
};
static AudioServerPlugInDriverInterface *gInterfacePtr = &gInterface;

static HRESULT QueryInterface(void *self, REFIID uuid, LPVOID *out) {
    if (!out) {
        return E_POINTER;
    }
    *out = NULL;
    CFUUIDRef requested = CFUUIDCreateFromUUIDBytes(NULL, uuid);
    if (!requested) {
        return E_NOINTERFACE;
    }
    HRESULT r = E_NOINTERFACE;
    if (CFEqual(requested, IUnknownUUID) ||
        CFEqual(requested, kAudioServerPlugInDriverInterfaceUUID)) {
        AddRef(self);
        *out = &gInterfacePtr;
        r = S_OK;
    }
    CFRelease(requested);
    return r;
}

__attribute__((visibility("default")))
void *PongAudio_Create(CFAllocatorRef allocator, CFUUIDRef type) {
    (void)allocator;
    if (!type || !CFEqual(type, kAudioServerPlugInTypeUUID)) {
        return NULL;
    }
    if (!gHostTicksPerFrame) {
        mach_timebase_info_data_t tb;
        mach_timebase_info(&tb);
        gHostTicksPerFrame = 1e9 * (Float64)tb.denom /
            ((Float64)PONG_AUDIO_SERVICE_RATE * (Float64)tb.numer);
    }
    pthread_mutex_lock(&gLock);
    (void)connectService();
    pthread_mutex_unlock(&gLock);
    syslog(LOG_NOTICE, "PongAudio HAL: AudioServerPlugIn factory accepted");
    return &gInterfacePtr;
}
