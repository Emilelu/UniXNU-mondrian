/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
#include "K60AdspOwner.h"
/* Explicit absent provider. Replace this archive member only when the PAS1
 * owner contract is implemented and independently verified. No weak imports,
 * physical mappings, firmware load or synthetic ownership are permitted here. */
int k60_adsp_owner_acquire(const K60BatteryConfig *config, K60AdspOwnerLease *lease)
{
    (void)config;
    if (lease) { K60AdspOwnerLease empty = {0}; *lease = empty; }
    return K60_ADSP_OWNER_UNAVAILABLE;
}
int k60_adsp_owner_revalidate(const K60AdspOwnerLease *lease)
{
    (void)lease; return K60_ADSP_OWNER_UNAVAILABLE;
}
void k60_adsp_owner_abort(const K60AdspOwnerLease *lease)
{
    (void)lease; /* No resources were acquired by this implementation. */
}
