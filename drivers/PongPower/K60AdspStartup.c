/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Copyright (c) 2026, UniXNU contributors. */
/* Shared early/late startup exclusion. Never clear uncertain ownership. */
static unsigned startup_owner;
int k60_adsp_startup_claim(unsigned owner)
{
    return (owner == 1u || owner == 2u) &&
        __sync_bool_compare_and_swap(&startup_owner, 0u, owner);
}
int k60_adsp_handoff_owner_active(void)
{
    return __atomic_load_n(&startup_owner, __ATOMIC_ACQUIRE) == 1u;
}
