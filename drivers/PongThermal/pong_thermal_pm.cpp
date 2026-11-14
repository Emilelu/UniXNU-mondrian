/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/* Pong SM8475 thermal pressure level: the publisher.
 *
 * This file is the master copy. patches/xnu/0617-k60-thermal-tsens.patch carries
 * it into the XNU tree verbatim as bsd/dev/pong_thermal_pm.cpp;
 * scripts/check-thermal-kernel-patch.py fails when the two copies differ.
 *
 * What it does: hands the board's pressure level (nominal / moderate / heavy /
 * trapping, computed by bsd/dev/pong_thermal_level.c) to the one thermal entry
 * point this kernel already has, IOPMrootDomain::systemPowerEventOccurred, under
 * the key kIOPMThermalLevelWarningKey. It installs no actuator and programs no
 * clock: docs/research/thermal/TRIP-DESIGN.md section 3.5 is the decision record.
 *
 * Why this is C++: systemPowerEventOccurred takes an OSSymbol and an OSObject,
 * which only exist in C++. bsd/conf/files had no .cpp before this file; the
 * build system has always supported it (makedefs/MakeInc.rule:423-428 turns
 * .cpp into .cpo, bsd/conf/Makefile.template:72 has the %CXXFILES hook).
 *
 * The call is made from the thermal worker thread, not from the PM work loop.
 * That is the supported shape: IOPMrootDomain::setThermalState re-dispatches
 * itself through gIOPMWorkLoop->runAction when it is called outside the gate
 * (iokit/Kernel/IOPMrootDomain.cpp:8119-8136), and the property update takes
 * featuresDictLock (:8154-8156). What has not been shown on hardware is that a
 * non-Apple kext-side caller is harmless; docs/research/thermal/08-KERNEL-DRIVER.md
 * section 7.4 keeps that as an open question for the first boot. */
#include <pexpert/arm64/board_config.h>

#if defined(PONG)

#include <IOKit/IOService.h>
#include <IOKit/pwr_mgt/IOPM.h>
#include <IOKit/pwr_mgt/RootDomain.h>
#include <libkern/c++/OSNumber.h>
#include <libkern/c++/OSSymbol.h>
#include <sys/pong_thermal_level.h>
#include <sys/systm.h>

/* The event key, created once. Every IOPMrootDomain key in the tree is made this
 * way and never released (iokit/Kernel/IOPMrootDomain.cpp:1535-1538). */
static const OSSymbol *pong_thermal_pm_key;

/* What was last accepted by the root domain, so an unchanged level costs nothing. */
static unsigned int pong_thermal_pm_last_level;
static int pong_thermal_pm_have_last;

/* The level-to-value table lives in bsd/dev/pong_thermal_level.c (k60tl_platform_value),
 * where scripts/tests/test-k60-thermal-level.c can check it on the host against
 * iokit/IOKit/pwr_mgt/IOPM.h:763-772. Only the two platform values, 100 and 110, move
 * IOPMrootDomain::thermalWarningState (iokit/Kernel/IOPMrootDomain.cpp:8133-8134); the
 * others are recorded in the "Power Status" dictionary and broadcast (:8172-8188). */

/* Called once per sampling round by the worker in bsd/dev/pong_thermal.c.
 *
 * Before IOKit has started there is no root domain: bsd_init calls
 * pong_thermal_init (bsd/kern/bsd_init.c:1166-1167) long before IOKitBSDInit
 * (:1325), so the first rounds return here and the first successful call is the
 * moment the publisher goes live. A missing root domain is not an error. */
extern "C" void
pong_thermal_pm_publish(unsigned int level)
{
	IOPMrootDomain *root;
	OSNumber *number;
	uint32_t value;

	if (pong_thermal_pm_have_last && level == pong_thermal_pm_last_level) {
		return;
	}
	root = IOService::getPMRootDomain();
	if (root == NULL) {
		return;
	}
	if (!pong_thermal_pm_key) {
		pong_thermal_pm_key = OSSymbol::withCStringNoCopy(kIOPMThermalLevelWarningKey);
		if (!pong_thermal_pm_key) {
			return;
		}
	}
	value = (uint32_t)k60tl_platform_value(level);
	/* withNumber hands back a retained object; the root domain keeps its own
	 * reference in the "Power Status" dictionary (:8172), so this one is dropped
	 * right after the call, as overload one does (:8103-8116). */
	number = OSNumber::withNumber((unsigned long long)value, 32);
	if (number == NULL) {
		return;
	}
	(void)root->systemPowerEventOccurred(pong_thermal_pm_key, (OSObject *)number);
	number->release();
	pong_thermal_pm_last_level = level;
	pong_thermal_pm_have_last = 1;
	printf("PongThermal: level %s (%u) published as %s=%u\n",
	    k60tl_level_name(level), level, kIOPMThermalLevelWarningKey, value);
}

#endif /* PONG */
