/* Default provider must never mint PAS ownership. */
#include <stdio.h>
#include <string.h>
#include "../../drivers/PongPower/K60AdspOwner.h"
int main(void)
{
    K60AdspOwnerLease lease, zero={0};
    memset(&lease,0xff,sizeof lease);
    if (k60_adsp_owner_acquire(0,&lease)!=K60_ADSP_OWNER_UNAVAILABLE ||
        memcmp(&lease,&zero,sizeof lease) ||
        k60_adsp_owner_acquire(0,0)!=K60_ADSP_OWNER_UNAVAILABLE ||
        k60_adsp_owner_revalidate(&lease)!=K60_ADSP_OWNER_UNAVAILABLE) return 1;
    k60_adsp_owner_abort(&lease);
    puts("TESTS OK: absent owner never grants flags/token/epoch"); return 0;
}
