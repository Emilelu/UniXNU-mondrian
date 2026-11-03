/*
 * K60 bring-up: an empty IOAcceleratorES.
 *
 * CoreAnimation asks IOKit for an IOAcceleratorES before it composes anything
 * (backboardd polls IOServiceMatching("IOAcceleratorES")); with no such service
 * every composed frame stays blank even when the framebuffer itself works. The
 * real accelerator on this board is the Adreno backend, which publishes its own
 * IOAcceleratorES provider once IOGPUFamily is prelinked and started. Until then
 * this stub owns the name: it answers every user-client call with success and
 * zeroed outputs, advertises no MetalPluginName, and so lets the software path
 * (MiniIOMobileFramebuffer) put the first frames on the panel.
 *
 * Built only when the native accelerator is not part of the link
 * (XNU_K60_ACCEL_STUB=1, the default). Boot-arg accel_stub=0 disables it at run
 * time; the build script drops it when PongAdreno is linked.
 */
#include <pexpert/arm64/board_config.h>

#if !defined(XNU_K60_ACCEL_STUB)
#define XNU_K60_ACCEL_STUB 1
#endif

#if defined(PONG) && (DEVELOPMENT || DEBUG) && !SECURE_KERNEL && XNU_K60_ACCEL_STUB

#include <IOKit/IOLib.h>
#include <IOKit/IOService.h>
#include <IOKit/IOUserClient.h>
#include <IOKit/IOKitKeys.h>
#include <libkern/c++/OSBoolean.h>
#include <pexpert/pexpert.h>
#include <sys/proc.h>
#include <sys/systm.h>

class K60AcceleratorUserClient : public IOUserClient
{
	OSDeclareDefaultStructors(K60AcceleratorUserClient);

public:
	IOReturn clientClose(void) APPLE_KEXT_OVERRIDE;
	IOReturn externalMethod(uint32_t selector, IOExternalMethodArguments * args,
	    IOExternalMethodDispatch * dispatch, OSObject * target, void * reference) APPLE_KEXT_OVERRIDE;
};

OSDefineMetaClassAndStructors(K60AcceleratorUserClient, IOUserClient);

static uint32_t gK60AccelCalls;

IOReturn
K60AcceleratorUserClient::clientClose(void)
{
	terminate();
	return kIOReturnSuccess;
}

IOReturn
K60AcceleratorUserClient::externalMethod(uint32_t selector, IOExternalMethodArguments * args,
    __unused IOExternalMethodDispatch * dispatch, __unused OSObject * target, __unused void * reference)
{
	for (uint32_t i = 0; i < args->scalarOutputCount && i < 16; i++) {
		args->scalarOutput[i] = 0;
	}
	if (args->structureOutput != NULL && args->structureOutputSize > 0) {
		bzero(args->structureOutput, args->structureOutputSize);
	}
	if (gK60AccelCalls < 24) {
		char name[32] = "?";

		proc_selfname(name, sizeof(name));
		gK60AccelCalls++;
		IOLog("K60 ACCEL: %s selector %u (%u in, %u out) answered by the empty accelerator\n",
		    name, selector, args->scalarInputCount, args->scalarOutputCount);
	}
	return kIOReturnSuccess;
}

class IOAcceleratorES : public IOService
{
	OSDeclareDefaultStructors(IOAcceleratorES);

public:
	bool start(IOService * provider) APPLE_KEXT_OVERRIDE;
};

OSDefineMetaClassAndStructors(IOAcceleratorES, IOService);

bool
IOAcceleratorES::start(IOService * provider)
{
	if (!IOService::start(provider)) {
		return false;
	}
	setProperty(kIOUserClientClassKey, "K60AcceleratorUserClient");
	setProperty("IOAcceleratorStub", kOSBooleanTrue);
	registerService();
	IOLog("K60 ACCEL: empty IOAcceleratorES published (no backend)\n");
	return true;
}

void
MiniAcceleratorPublishStub(IOService * provider)
{
	static bool published;
	uint32_t enabled = 1;

	if (published || provider == NULL) {
		return;
	}
	PE_parse_boot_argn("accel_stub", &enabled, sizeof(enabled));
	if (enabled == 0) {
		IOLog("K60 ACCEL: the empty IOAcceleratorES is disabled (accel_stub=0)\n");
		return;
	}
	IOAcceleratorES * accel = OSTypeAlloc(IOAcceleratorES);

	if (accel == NULL || !accel->init()) {
		OSSafeReleaseNULL(accel);
		return;
	}
	if (!accel->attach(provider) || !accel->start(provider)) {
		accel->detach(provider);
		accel->release();
		return;
	}
	published = true;
}
#endif /* PONG && DEVELOPMENT && !SECURE_KERNEL && XNU_K60_ACCEL_STUB */
