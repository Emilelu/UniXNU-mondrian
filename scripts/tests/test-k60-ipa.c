/* Host test for the K60 IPA M0 skeleton: constants, version decode, inert probe. */

#include <stdio.h>
#include "K60Ipa.h"

_Static_assert(K60_IPA_CFG_BASE == 0x03f40000u, "cfg base");
_Static_assert(K60_GSI_BASE == 0x03e04000u, "gsi base");
_Static_assert(K60_IPA_VERSION_ADDR == 0x03f40028u, "version register");
_Static_assert(K60_IPA_IRQ == 654u, "ipa irq");
_Static_assert(K60_GSI_IRQ == 432u, "gsi irq");

int
main(void)
{
    const K60IpaVersion v = k60_ipa_decode_comp_hw_version(0x51000002u);

    if (v.major != 5u || v.minor != 0x100u || v.step != 2u) {
        printf("FAIL version decode %u.%u.%u\n", v.major, v.minor, v.step);
        return 1;
    }
    if (k60_ipa_probe() != K60IpaNotReady) {
        printf("FAIL M0 probe must stay inert\n");
        return 1;
    }
    if (k60_ipa_marker[0] == '\0') {
        printf("FAIL marker missing\n");
        return 1;
    }
    printf("K60 IPA M0 PASS version=%u.%u.%u cfg=%#x gsi=%#x\n",
        v.major, v.minor, v.step, K60_IPA_CFG_BASE, K60_GSI_BASE);
    return 0;
}
