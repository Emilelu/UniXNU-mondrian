// SPDX-License-Identifier: BSD-2-Clause-Patent
//
// The K60 audio service the userland HAL opens after pong_audio_start(). It
// owns the control page and playback ring, and pumps one 1024-frame period at
// a time into pong_audio_submit(). The period pump deliberately refuses to
// start until the AFE six-step has set pong_audio_status() == PongAudioOk; this keeps a
// HAL from believing audio is running while the DSP graph is still closed.

#include <IOKit/IOService.h>
#include <IOKit/IOUserClient.h>
#include <IOKit/IOBufferMemoryDescriptor.h>
#include <IOKit/IOPlatformExpert.h>
#include <IOKit/IOLib.h>
#include <IOKit/IOMemoryDescriptor.h>
#include <IOKit/IOWorkLoop.h>
#include <IOKit/IOTimerEventSource.h>
#include <kern/clock.h>
#include <kern/task.h>

#include "PongAudioServiceAbi.h"
#include "../PongAudio/PongAudioRing.h"

extern "C" int pong_audio_submit(const void *frames, uint32_t frame_count);
extern "C" int pong_audio_status(void);
extern "C" vm_offset_t phystokv(uint64_t pa);
extern "C" uint64_t pmap_find_pa(void *pmap, uint64_t va);
extern "C" struct pmap *get_task_pmap(task_t task);

extern "C" {
volatile int32_t k60_audio_service[8];
}

#define PONG_AUDIO_SERVICE_PERIOD_US \
	((PONG_AUDIO_SERVICE_PERIOD_FRAMES * 1000000u) / PONG_AUDIO_SERVICE_RATE)
#define PONG_AUDIO_SERVICE_PERIOD_BYTES \
	(PONG_AUDIO_SERVICE_PERIOD_FRAMES * PONG_AUDIO_SERVICE_FRAME_BYTES)

static uint64_t
pong_audio_ticks_per_frame(void)
{
	mach_timebase_info_data_t tb;
	clock_timebase_info(&tb);
	return ((1000000000ull << 32) / PONG_AUDIO_SERVICE_RATE) *
	    tb.denom / tb.numer;
}

/* CoreAudio loads its host frequency from the dyld shared cache and assumes
 * 24 MHz. K60's architectural counter is 19.2 MHz, so rewrite just that
 * double after resolving it in the caller's pmap. This follows the clock
 * handoff required by porting/power; without it the audio server's IO cycle
 * runs 25 percent long. */
static IOReturn
pong_audio_set_host_clock(task_t task, uint64_t address)
{
	const uint64_t apple = 0x4176e36000000000ull;

	if (task != current_task() || (address & 7) ||
	    address < 0x180000000ull || address >= 0x400000000ull) {
		return kIOReturnBadArgument;
	}
	IOMemoryDescriptor *memory = IOMemoryDescriptor::withAddressRange(
	    address, 8, kIODirectionOut, task);
	if (!memory) {
		return kIOReturnNoMemory;
	}
	IOReturn result = memory->prepare();
	if (result != kIOReturnSuccess) {
		memory->release();
		return result;
	}
	uint64_t seen = 0;
	if (copyin(address, &seen, 8)) {
		result = kIOReturnNotReadable;
	} else {
		const uint64_t pa = pmap_find_pa(get_task_pmap(task), address);
		result = kIOReturnNoResources;
		if (pa) {
			mach_timebase_info_data_t tb;
			clock_timebase_info(&tb);
			const uint64_t hz = 1000000000ull * tb.denom / tb.numer;
			const unsigned top = 63 - (unsigned)__builtin_clzll(hz);
			if (top <= 52) {
				const uint64_t bits = (uint64_t)(1023 + top) << 52 |
				    ((hz << (52 - top)) & ((1ull << 52) - 1));
				volatile uint64_t *value =
				    reinterpret_cast<volatile uint64_t *>(phystokv(pa));
				result = kIOReturnUnsupported;
				if (*value == seen && (seen == apple || seen == bits)) {
					*value = bits;
					__asm__ volatile("dsb sy" ::: "memory");
					result = kIOReturnSuccess;
					IOLog("PongAudioService: CoreAudio host clock=%llu Hz\n", hz);
				}
			}
		}
	}
	memory->complete();
	memory->release();
	return result;
}

class PongAudio : public IOService {
	OSDeclareDefaultStructors(PongAudio)
private:
	IOBufferMemoryDescriptor *fControlMemory = nullptr;
	IOBufferMemoryDescriptor *fOutputMemory = nullptr;
	PongAudioServiceControl *fControl = nullptr;
	uint8_t *fOutput = nullptr;
	IOWorkLoop *fWorkLoop = nullptr;
	IOTimerEventSource *fTimer = nullptr;
	uint8_t fPeriodScratch[PONG_AUDIO_SERVICE_PERIOD_BYTES];
	bool fTimerStarted = false;

	bool allocateBuffers();
	void releaseBuffers();
	void timerFired();
	IOReturn startTimer();
	void stopTimer();

public:
	bool startAudio();
	void stop(IOService *provider) override;

	IOBufferMemoryDescriptor *memoryForType(uint32_t type);
	IOReturn startOutput();
	IOReturn stopOutput();
	IOReturn request(uint32_t selector);
	IOReturn setHostClock(task_t task, uint64_t address);
};

OSDefineMetaClassAndStructors(PongAudio, IOService)

bool
PongAudio::allocateBuffers()
{
	fControlMemory = IOBufferMemoryDescriptor::inTaskWithOptions(kernel_task,
	    kIODirectionInOut | kIOMemoryKernelUserShared,
	    sizeof(PongAudioServiceControl), 4096);
	fOutputMemory = IOBufferMemoryDescriptor::inTaskWithOptions(kernel_task,
	    kIODirectionInOut | kIOMemoryKernelUserShared,
	    PONG_AUDIO_SERVICE_RING_BYTES, 4096);
	if (!fControlMemory || !fOutputMemory) {
		return false;
	}
	fControl = (PongAudioServiceControl *)fControlMemory->getBytesNoCopy();
	fOutput = (uint8_t *)fOutputMemory->getBytesNoCopy();
	if (!fControl || !fOutput) {
		return false;
	}
	for (size_t i = 0; i < sizeof(*fControl); i++) {
		((uint8_t *)fControl)[i] = 0;
	}
	for (size_t i = 0; i < PONG_AUDIO_SERVICE_RING_BYTES; i++) {
		fOutput[i] = 0;
	}
	fControl->magic = PONG_AUDIO_SERVICE_MAGIC;
	fControl->version = PONG_AUDIO_SERVICE_VERSION;
	fControl->rate = PONG_AUDIO_SERVICE_RATE;
	fControl->channels = PONG_AUDIO_SERVICE_CHANNELS;
	fControl->frame_bytes = PONG_AUDIO_SERVICE_FRAME_BYTES;
	fControl->period_frames = PONG_AUDIO_SERVICE_PERIOD_FRAMES;
	fControl->ring_frames = PONG_AUDIO_SERVICE_RING_FRAMES;
	fControl->lead_frames = PONG_AUDIO_SERVICE_LEAD_FRAMES;
	fControl->state = PongAudioServiceOutputReady;
	fControl->out_late = 0;
	fControl->out_write = 0;
	fControl->out_read = 0;
	fControl->out_seq = 0;
	fControl->reserved0 = 0;
	fControl->ticks_per_frame_q32 = pong_audio_ticks_per_frame();
	fControl->out_anchor_host = mach_absolute_time();
	fControl->out_frames = 0;
	return true;
}

void
PongAudio::releaseBuffers()
{
	stopTimer();
	if (fControlMemory) {
		fControlMemory->release();
		fControlMemory = nullptr;
	}
	if (fOutputMemory) {
		fOutputMemory->release();
		fOutputMemory = nullptr;
	}
	fControl = nullptr;
	fOutput = nullptr;
}

bool
PongAudio::startAudio()
{
	if (!allocateBuffers()) {
		releaseBuffers();
		return false;
	}
	// iOS's audio server is sandboxed against unknown user clients; the kernel
	// lets these processes open this service.
	setProperty("NativeSandboxGrantProcess", "audiomxd,mediaserverd");
	setProperty("IOUserClientClass", "PongAudioUserClient");
	registerService();
	return true;
}

void
PongAudio::stop(IOService *provider)
{
	stopOutput();
	releaseBuffers();
	IOService::stop(provider);
}

IOBufferMemoryDescriptor *
PongAudio::memoryForType(uint32_t type)
{
	IOBufferMemoryDescriptor *memory = nullptr;
	if (type == PongAudioServiceMemoryControl) {
		memory = fControlMemory;
	} else if (type == PongAudioServiceMemoryOutput) {
		memory = fOutputMemory;
	}
	if (memory) {
		memory->retain();
	}
	return memory;
}

IOReturn
PongAudio::startTimer()
{
	if (!fWorkLoop) {
		fWorkLoop = IOWorkLoop::workLoop();
		if (!fWorkLoop) {
			return kIOReturnNoResources;
		}
	}
	if (!fTimer) {
		fTimer = IOTimerEventSource::timerEventSource(this,
		    OSMemberFunctionCast(IOTimerEventSource::Action, this,
		    &PongAudio::timerFired));
		if (!fTimer || fWorkLoop->addEventSource(fTimer) != kIOReturnSuccess) {
			if (fTimer) {
				fTimer->release();
				fTimer = nullptr;
			}
			return kIOReturnNoResources;
		}
	}
	fTimerStarted = true;
	return fTimer->setTimeoutUS(PONG_AUDIO_SERVICE_PERIOD_US);
}

void
PongAudio::stopTimer()
{
	fTimerStarted = false;
	if (fTimer) {
		fTimer->cancelTimeout();
	}
}

IOReturn
PongAudio::startOutput()
{
	if (!fControl || !fOutput) {
		return kIOReturnNotReady;
	}
	if (pong_audio_status() != 0) {
		fControl->state = PongAudioServiceOutputReady;
		return kIOReturnNotReady;
	}
	fControl->out_read = fControl->out_write;
	fControl->out_late = 0;
	const uint32_t seq = __atomic_load_n(&fControl->out_seq, __ATOMIC_RELAXED);
	__atomic_store_n(&fControl->out_seq, seq + 1, __ATOMIC_RELAXED);
	fControl->ticks_per_frame_q32 = pong_audio_ticks_per_frame();
	fControl->out_anchor_host = mach_absolute_time();
	fControl->out_frames = 0;
	__atomic_store_n(&fControl->out_seq, seq + 2, __ATOMIC_RELEASE);
	fControl->state = PongAudioServiceOutputReady |
	    PongAudioServiceOutputRunning;
	const IOReturn result = startTimer();
	if (result != kIOReturnSuccess) {
		fControl->state = PongAudioServiceOutputReady;
		return result;
	}
	return kIOReturnSuccess;
}

IOReturn
PongAudio::stopOutput()
{
	if (!fControl) {
		return kIOReturnSuccess;
	}
	stopTimer();
	fControl->state = PongAudioServiceOutputReady;
	return kIOReturnSuccess;
}

IOReturn
PongAudio::request(uint32_t selector)
{
	switch (selector) {
	case PongAudioServiceStartOutput:
		return startOutput();
	case PongAudioServiceStopOutput:
		return stopOutput();
	default:
		return kIOReturnUnsupported;
	}
}

IOReturn
PongAudio::setHostClock(task_t task, uint64_t address)
{
	return pong_audio_set_host_clock(task, address);
}

void
PongAudio::timerFired()
{
	if (!fControl || !fOutput ||
	    (fControl->state & PongAudioServiceOutputRunning) == 0) {
		return;
	}
	const uint64_t write = __atomic_load_n(&fControl->out_write,
	    __ATOMIC_ACQUIRE);
	const uint64_t read = __atomic_load_n(&fControl->out_read,
	    __ATOMIC_RELAXED);
	if (write - read >= PONG_AUDIO_SERVICE_PERIOD_FRAMES) {
		const uint32_t index = (uint32_t)(read %
		    PONG_AUDIO_SERVICE_RING_FRAMES);
		uint32_t first = PONG_AUDIO_SERVICE_PERIOD_FRAMES;
		if (index + first > PONG_AUDIO_SERVICE_RING_FRAMES) {
			first = PONG_AUDIO_SERVICE_RING_FRAMES - index;
		}
		for (uint32_t i = 0; i < first; i++) {
			for (uint32_t b = 0; b < PONG_AUDIO_SERVICE_FRAME_BYTES; b++) {
				fPeriodScratch[i * PONG_AUDIO_SERVICE_FRAME_BYTES + b] =
				    fOutput[(index + i) * PONG_AUDIO_SERVICE_FRAME_BYTES + b];
			}
		}
		for (uint32_t i = first; i < PONG_AUDIO_SERVICE_PERIOD_FRAMES; i++) {
			for (uint32_t b = 0; b < PONG_AUDIO_SERVICE_FRAME_BYTES; b++) {
				fPeriodScratch[i * PONG_AUDIO_SERVICE_FRAME_BYTES + b] =
				    fOutput[(i - first) * PONG_AUDIO_SERVICE_FRAME_BYTES + b];
			}
		}
		const int rc = pong_audio_submit(fPeriodScratch,
		    PONG_AUDIO_SERVICE_PERIOD_FRAMES);
		if (rc == 0) {
			__atomic_store_n(&fControl->out_read,
			    read + PONG_AUDIO_SERVICE_PERIOD_FRAMES, __ATOMIC_RELEASE);
			__atomic_fetch_add(&fControl->out_frames,
			    PONG_AUDIO_SERVICE_PERIOD_FRAMES, __ATOMIC_RELEASE);
		} else {
			fControl->out_late++;
		}
	}
	if (fTimerStarted) {
		fTimer->setTimeoutUS(PONG_AUDIO_SERVICE_PERIOD_US);
	}
}

class PongAudioUserClient : public IOUserClient {
	OSDeclareDefaultStructors(PongAudioUserClient)
private:
	task_t fOwner = nullptr;
	PongAudio *fProvider = nullptr;

public:
	bool initWithTask(task_t task, void *security, UInt32 type,
	    OSDictionary *properties) override;
	bool start(IOService *provider) override;
	IOReturn clientClose() override;
	IOReturn clientMemoryForType(UInt32 type, IOOptionBits *options,
	    IOMemoryDescriptor **memory) override;
	IOReturn externalMethod(uint32_t selector, IOExternalMethodArguments *args,
	    IOExternalMethodDispatch *dispatch, OSObject *target,
	    void *reference) override;
};

OSDefineMetaClassAndStructors(PongAudioUserClient, IOUserClient)

bool
PongAudioUserClient::initWithTask(task_t task, void *security, UInt32 type,
    OSDictionary *properties)
{
	if (!IOUserClient::initWithTask(task, security, type, properties)) {
		return false;
	}
	fOwner = task;
	return true;
}

bool
PongAudioUserClient::start(IOService *provider)
{
	fProvider = OSDynamicCast(PongAudio, provider);
	if (!fProvider || !IOUserClient::start(provider)) {
		return false;
	}
	k60_audio_service[1] = k60_audio_service[1] + 1;
	return true;
}

IOReturn
PongAudioUserClient::clientClose()
{
	if (fProvider) {
		fProvider->stopOutput();
	}
	k60_audio_service[2] = k60_audio_service[2] + 1;
	terminate();
	return kIOReturnSuccess;
}

IOReturn
PongAudioUserClient::clientMemoryForType(UInt32 type, IOOptionBits *options,
    IOMemoryDescriptor **memory)
{
	if (!fProvider || !options || !memory) {
		return kIOReturnBadArgument;
	}
	IOBufferMemoryDescriptor *m = fProvider->memoryForType(type);
	if (!m) {
		return kIOReturnBadArgument;
	}
	*options = 0;
	*memory = m; /* the caller consumes the reference */
	k60_audio_service[5] = k60_audio_service[5] + 1;
	return kIOReturnSuccess;
}

IOReturn
PongAudioUserClient::externalMethod(uint32_t selector,
    IOExternalMethodArguments *args, IOExternalMethodDispatch *dispatch,
    OSObject *target, void *reference)
{
	if (selector == PongAudioServiceSetHostClock) {
		if (!args || args->scalarInputCount != 1 || args->structureInputSize ||
		    args->scalarOutputCount || args->structureOutputSize) {
			return kIOReturnBadArgument;
		}
		if (!fProvider) {
			return kIOReturnNotReady;
		}
		const IOReturn result = fProvider->setHostClock(fOwner,
		    args->scalarInput[0]);
		if (result != kIOReturnSuccess) {
			k60_audio_service[4] = k60_audio_service[4] + 1;
		}
		return result;
	}
	if (!args || args->scalarInputCount || args->structureInputSize ||
	    args->scalarOutputCount || args->structureOutputSize) {
		return kIOReturnBadArgument;
	}
	if (!fProvider) {
		return kIOReturnNotReady;
	}
	k60_audio_service[3] = k60_audio_service[3] + 1;
	const IOReturn result = fProvider->request(selector);
	if (result != kIOReturnSuccess) {
		k60_audio_service[4] = k60_audio_service[4] + 1;
	}
	return result;
}

extern "C" void
pong_audio_service_start(void)
{
	PongAudio *audio = OSTypeAlloc(PongAudio);
	if (!audio || !audio->init() || !audio->attach(IOService::getPlatform())) {
		if (audio) {
			audio->release();
		}
		k60_audio_service[0] = -1;
		return;
	}
	if (!audio->start(IOService::getPlatform()) || !audio->startAudio()) {
		k60_audio_service[0] = -2;
		audio->detach(IOService::getPlatform());
		audio->release();
		return;
	}
	k60_audio_service[0] = 1;
	audio->release(); /* the platform's attachment keeps it */
}
