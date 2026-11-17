/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* K60 IPA SMMU planner and configuration.
 *
 * Line-by-line C translation of the UFS SMMU takeover template,
 * drivers/NativeUfs/SmmuTakeover.h (BSD-2-Clause-Patent):
 * planUfsSmmuBank(), planUfsSmmu(), configureUfsSmmu() and
 * ufsSmmuAddressBits(), renamed for the IPA stream and expressed with a
 * context pointer instead of a C++ read/write lambda.
 *
 * Source facts: ARM IHI 0062D.c sections 1.6 and 3.7. The Pong
 * qcom,qsmmu-v500 instance exposes 78 owned context banks and 120
 * owned stream-match groups; IPA uses stream 0x5c0 with Iova 0x20000000,
 * a 1 MiB ring and 32 KiB of ArmSmmu4K tables.
 */

#include "K60IpaSmmu.h"

#define K60_IPA_SMMU_IDR0        0x20u
#define K60_IPA_SMMU_IDR1        0x24u
#define K60_IPA_SMMU_IDR2        0x28u
#define K60_IPA_SMMU_SMR(i)      (0x800u + 4u * (i))
#define K60_IPA_SMMU_S2CR(i)     (0xc00u + 4u * (i))
#define K60_IPA_SMMU_SCTLR(p, b) (((p) + (b)) * 4096u)
#define K60_IPA_SMMU_CBAR(bank)  (0x1000u + 4u * (bank))
#define K60_IPA_SMMU_CBA2R(bank) (0x1800u + 4u * (bank))

/* ARM IHI 0062D.c sections 1.6 and 3.7: VA64=0 still rejects inputs above
 * 32 bits with SCTLR.M=0. With VA64=1 the bypass range is bounded by all
 * three hardware widths, not TCR2.PASize (which only limits translation).
 */
static unsigned
k60_ipa_smmu_address_bits(unsigned code)
{
    switch (code) {
    case 0:
        return 32;
    case 1:
        return 36;
    case 2:
        return 40;
    case 3:
        return 42;
    case 4:
        return 44;
    case 5:
        return 48;
    default:
        return 0;
    }
}

static void
k60_ipa_smmu_plan_defaults(K60IpaSmmuPlan *p)
{
    p->slot = 0xffffffffU;
    p->bank = 0;
    p->pages = 0;
    p->smr = 0;
    p->s2cr = 0;
    p->previous_bank = 0xffffffffU;
    p->reuse = 0;
    p->migrate = 0;
    p->error = 0;
}

static int
k60_ipa_smmu_same(const char *left, const char *right)
{
    while (*left != '\0' && *left == *right) {
        ++left;
        ++right;
    }
    return *left == *right;
}

/* Translation of planUfsSmmuBank(): try one context bank, counting down from
 * the top of the owned range with bank_from_top. */
static K60IpaSmmuPlan
k60_ipa_smmu_bank(uint16_t stream, uint64_t dma, uint64_t bytes,
    K60IpaSmmuRead read, void *context, unsigned owned_banks,
    unsigned owned_groups, unsigned bank_from_top)
{
    K60IpaSmmuPlan p;
    uint32_t idr0;
    uint32_t idr1;
    uint32_t idr2;
    unsigned count;
    unsigned banks;
    unsigned matches;
    unsigned shift;
    unsigned i;

    k60_ipa_smmu_plan_defaults(&p);
    idr0 = read(context, K60_IPA_SMMU_IDR0);
    idr2 = read(context, K60_IPA_SMMU_IDR2);
    count = idr0 & 255u;
    if (!(idr0 & (1U << 30)) || !(idr2 & (1U << 12))) {
        p.error = "SMMU AArch64 stage 1 unsupported";
        return p;
    }
    for (shift = 0; shift <= 8u; shift += 4u) {
        unsigned bits = k60_ipa_smmu_address_bits((idr2 >> shift) & 15u);

        if (!bits || !bytes || dma >= (1ULL << bits) ||
            bytes > (1ULL << bits) - dma) {
            p.error = "DMA exceeds SMMU address width";
            return p;
        }
    }
    idr1 = read(context, K60_IPA_SMMU_IDR1);
    banks = idr1 & 255u;
    /* DT and ID registers are independent upper bounds. Firmware can expose
     * fewer resources than the Android DT describes (Pong ID1.NUMCB=75,
     * DT limit=78). Intersect the bounds; never expand the hardware range. */
    if (!owned_banks || !owned_groups || !banks || !count) {
        p.error = "empty SMMU ownership/capability range";
        return p;
    }
    if (banks > owned_banks) {
        banks = owned_banks;
    }
    if (count > owned_groups) {
        count = owned_groups;
    }
    p.pages = 1U << (((idr1 >> 28) & 7u) + 1u);
    if ((idr1 >> 31) || !count || p.pages > 128 || banks < 2 || banks > 128 ||
        (p.pages + banks) * 4096u > 0x100000u) {
        p.error = "unsupported SMMU geometry";
        return p;
    }
    if (count > 128) {
        p.error = "unsupported stream-match group count";
        return p;
    }
    if (bank_from_top >= banks - 1) {
        p.error = "no free context bank";
        return p;
    }
    p.bank = banks - 1 - bank_from_top;
    matches = 0;
    for (i = 0; i < count; ++i) {
        uint32_t smr = read(context, K60_IPA_SMMU_SMR(i));
        uint32_t s2cr;
        uint32_t mask;
        unsigned mapped_bank;
        int match;
        int translate;
        int our_bank;

        if (!(smr & 0x80000000U)) {
            if (!p.reuse && !p.migrate) {
                p.slot = i;
            }
            continue;
        }
        s2cr = read(context, K60_IPA_SMMU_S2CR(i));
        mask = (smr >> 16) & 0x7fffu;
        match = ((smr ^ stream) & 0xffffu & ~mask) == 0;
        translate = ((s2cr >> 16) & 3u) == 0;
        mapped_bank = s2cr & 255u;
        our_bank = translate && mapped_bank == p.bank;
        if (match) {
            ++matches;
            /* A single exact firmware mapping for the IPA SID is the handoff
             * to migrate after the queue is stopped. Never accept a masked
             * mapping, a non-translation type, or a context bank outside the
             * owned range. */
            if (matches > 1 || mask || !translate || mapped_bank >= banks) {
                p.slot = i;
                p.smr = smr;
                p.s2cr = s2cr;
                p.error = "conflicting IPA stream mapping";
                return p;
            }
            p.reuse = our_bank;
            p.migrate = !our_bank;
            p.previous_bank = mapped_bank;
            p.slot = i;
            p.smr = smr;
            p.s2cr = s2cr;
        } else if (our_bank) {
            p.slot = i;
            p.smr = smr;
            p.s2cr = s2cr;
            p.error = "reserved context bank already used";
            return p;
        }
    }
    {
        uint32_t sctlr = read(context, K60_IPA_SMMU_SCTLR(p.pages, p.bank));

        if ((sctlr & 1u) || (p.reuse &&
            (sctlr || read(context, K60_IPA_SMMU_CBAR(p.bank)) != 0x10000u ||
             (read(context, K60_IPA_SMMU_CBA2R(p.bank)) & ~1u)))) {
            p.error = "reserved context bank not bypass";
            return p;
        }
    }
    if (p.slot == 0xffffffffU) {
        p.error = "no free stream-match group";
    }
    return p;
}

static int
k60_ipa_smmu_retryable(const char *error)
{
    return k60_ipa_smmu_same(error, "reserved context bank already used") ||
        k60_ipa_smmu_same(error, "reserved context bank not bypass");
}

/* Translation of planUfsSmmu(): bounded warm-reset fallback over
 * bankFromTop 1..7, intersected with the owned ranges above. Keep exact SID
 * matching, firmware migration and VA64 checks. */
int
k60_ipa_smmu_plan(K60IpaSmmuPlan *plan, uint16_t stream, uint64_t dma,
    uint64_t bytes, K60IpaSmmuRead read, void *context,
    unsigned owned_banks, unsigned owned_groups)
{
    K60IpaSmmuPlan first;
    unsigned attempt;

    if (!plan || !read) {
        if (plan) {
            k60_ipa_smmu_plan_defaults(plan);
            plan->error = "SMMU missing plan or read callback";
        }
        return K60IpaSmmuBadArgument;
    }
    first = k60_ipa_smmu_bank(stream, dma, bytes, read, context,
        owned_banks, owned_groups, 0);
    if (!first.error) {
        *plan = first;
        return K60IpaSmmuOk;
    }
    /* An inexact/masked SID is still an unconditional refusal; the planner
     * already migrates an exact mapping from another bank. */
    if (!k60_ipa_smmu_retryable(first.error)) {
        *plan = first;
        return K60IpaSmmuUnsupported;
    }
    for (attempt = 1; attempt < 8u; ++attempt) {
        K60IpaSmmuPlan next = k60_ipa_smmu_bank(stream, dma, bytes, read,
            context, owned_banks, owned_groups, attempt);

        if (!next.error) {
            *plan = next;
            return K60IpaSmmuOk;
        }
        if (!k60_ipa_smmu_retryable(next.error)) {
            break;
        }
    }
    *plan = first;
    return K60IpaSmmuUnsupported;
}

/* Translation of configureUfsSmmu(). The caller must first quiesce the IPA
 * queue. The planner refuses other streams sharing this bank and enabled
 * translation; no live context is disabled here. The write callback must
 * complete an MMIO barrier before it returns. */
int
k60_ipa_smmu_configure(const K60IpaSmmuPlan *plan, uint16_t stream,
    K60IpaSmmuRead read, K60IpaSmmuWrite write, void *context,
    const char **error)
{
    unsigned cb;

    if (!plan || !read || !write || !error) {
        if (error) {
            *error = "SMMU missing configure argument";
        }
        return K60IpaSmmuBadArgument;
    }
    *error = 0;
    if (plan->error) {
        *error = plan->error;
        return K60IpaSmmuUnsupported;
    }
    cb = K60_IPA_SMMU_SCTLR(plan->pages, plan->bank);
    if (!plan->reuse) {
        write(context, cb, 0);
    }
    if (read(context, cb) != 0) {
        *error = "SMMU bypass disable readback";
        return K60IpaSmmuReadback;
    }
    /* Set VA64 before exposing a newly allocated stream. Repair an exclusive
     * existing 32-bit bypass too; do not silently reuse the faulty state. */
    if (read(context, K60_IPA_SMMU_CBA2R(plan->bank)) != 1u) {
        write(context, K60_IPA_SMMU_CBA2R(plan->bank), 1u);
    }
    if (!plan->reuse) {
        write(context, K60_IPA_SMMU_CBAR(plan->bank), 0x10000u);
    }
    if (read(context, K60_IPA_SMMU_CBA2R(plan->bank)) != 1u ||
        read(context, K60_IPA_SMMU_CBAR(plan->bank)) != 0x10000u ||
        read(context, cb) != 0) {
        *error = "SMMU VA64 bypass readback";
        return K60IpaSmmuReadback;
    }
    if (!plan->reuse) {
        /* For a firmware handoff the SMR is already the exact IPA SID.
         * Configure the new bank first, then atomically change only this
         * slot's S2CR. */
        write(context, K60_IPA_SMMU_S2CR(plan->slot), plan->bank);
        if (read(context, K60_IPA_SMMU_S2CR(plan->slot)) != plan->bank) {
            *error = "SMMU stream context readback";
            return K60IpaSmmuReadback;
        }
        if (!plan->migrate) {
            write(context, K60_IPA_SMMU_SMR(plan->slot),
                0x80000000u | stream);
        }
    }
    if (read(context, K60_IPA_SMMU_SMR(plan->slot)) !=
            (0x80000000u | stream) ||
        read(context, K60_IPA_SMMU_S2CR(plan->slot)) != plan->bank) {
        *error = "SMMU stream mapping readback";
        return K60IpaSmmuReadback;
    }
    return K60IpaSmmuOk;
}
