/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* K60 IPA SMMU stream planner and configuration.
 *
 * C port of drivers/NativeUfs/SmmuTakeover.h (BSD-2-Clause-Patent):
 * planUfsSmmuBank -> k60_ipa_smmu_bank(), planUfsSmmu -> k60_ipa_smmu_plan(),
 * configureUfsSmmu -> k60_ipa_smmu_configure(), ufsSmmuAddressBits ->
 * k60_ipa_smmu_address_bits().
 *
 * The register model is ARM SMMUv2 (IHI 0062D.c sections 1.6 and 3.7) as
 * exposed by the K60 qcom,qsmmu-v500 instance: IDR0/IDR1/IDR2 at
 * 0x20/0x24/0x28, SMR at 0x800 + 4*i, S2CR at 0xc00 + 4*i, SCTLR at
 * (pages + bank) * 4096, CBAR at 0x1000 + 4*bank, CBA2R at 0x1800 + 4*bank.
 *
 * IPA stream 0x5c0 uses Iova 0x20000000, a 1 MiB ring and 32 KiB of
 * ArmSmmu4K tables with ownedBanks 78 and ownedGroups 120. Planning is
 * read-only; the caller must quiesce the IPA queue, own the SMMU mapping
 * and keep an MMIO barrier in the write callback before calling configure.
 */

#ifndef K60_IPA_SMMU_H
#define K60_IPA_SMMU_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Register accessors: offset is a byte offset in the owned SMMU mapping.
 * The read callback returns the 32-bit register value. The write callback
 * must complete an MMIO barrier before it returns.
 */
typedef uint32_t (*K60IpaSmmuRead)(void *context, unsigned offset);
typedef void (*K60IpaSmmuWrite)(void *context, unsigned offset, uint32_t value);

typedef struct {
    unsigned slot;
    unsigned bank;
    unsigned pages;
    uint32_t smr;
    uint32_t s2cr;
    unsigned previous_bank;
    int reuse;
    int migrate;
    const char *error;
} K60IpaSmmuPlan;

enum {
    K60IpaSmmuOk = 0,
    K60IpaSmmuBadArgument = -1,
    K60IpaSmmuUnsupported = -2,
    K60IpaSmmuReadback = -3
};

/* Plan a context bank and stream-match slot for one IPA stream. Returns 0 on
 * success; on refusal returns K60IpaSmmuUnsupported and leaves plan->error
 * pointing at a static reason string. plan must not be NULL. */
int k60_ipa_smmu_plan(K60IpaSmmuPlan *plan, uint16_t stream, uint64_t dma,
    uint64_t bytes, K60IpaSmmuRead read, void *context,
    unsigned owned_banks, unsigned owned_groups);

/* Program a successful plan. Returns 0 after every readback matches; on
 * failure returns K60IpaSmmuReadback and sets *error to a static string.
 * The caller must quiesce the IPA queue and own the SMMU mapping first. */
int k60_ipa_smmu_configure(const K60IpaSmmuPlan *plan, uint16_t stream,
    K60IpaSmmuRead read, K60IpaSmmuWrite write, void *context,
    const char **error);

#ifdef __cplusplus
}
#endif

#endif /* K60_IPA_SMMU_H */
