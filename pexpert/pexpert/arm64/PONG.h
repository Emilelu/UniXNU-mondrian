// SPDX-License-Identifier: BSD-2-Clause-Patent
#ifndef _PEXPERT_ARM64_PONG_H
#define _PEXPERT_ARM64_PONG_H

// Nothing Phone (2), SM8475: firmware PSCI and the native GICv3 CPU provider.
#define PONG 1
#define GENERIC_PSCI_SMP 1
#define NO_MONITOR 1
#define NO_ECORE 1
#define ARM_ARCH_TIMER 1
#define __ARM_ARCH__ 8
#define __ARM_VMSA__ 8
#define __ARM_VFP__ 4
#define __ARM_COHERENT_CACHE__ 1
#define __ARM_DEBUG__ 7
#define __ARM64_PMAP_SUBPAGE_L1__ 1

/* SM8475 sets PSTATE.PAN on exception entry; copyio must lift it around
 * user memory access, unlike the original BCM2837/A53 target. */
/* Development-only compatibility mode: use the generic no-PAN uaccess
 * implementation and preserve PAN=0 across exception entry. All three
 * pieces (copyio, initial PSTATE and SCTLR.SPAN) must agree. */
#if defined(XNU_PONG_LEGACY_UACCESS) && XNU_PONG_LEGACY_UACCESS && \
    (DEVELOPMENT || DEBUG) && !SECURE_KERNEL
#define PONG_LEGACY_UACCESS 1
#else
#define PONG_LEGACY_UACCESS 0
#endif
#if defined(XNU_NATIVE_PAN) && XNU_NATIVE_PAN && !PONG_LEGACY_UACCESS
#define __ARM_PAN_AVAILABLE__ 1
#endif

// No PI3_UART, BCM2837 GPIO/timer routing, or fixed Raspberry Pi panic buffer.
#endif
