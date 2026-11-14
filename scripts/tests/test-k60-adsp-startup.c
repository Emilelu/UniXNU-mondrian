/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#include <stdlib.h>
#include <stdio.h>
int k60_adsp_startup_claim(unsigned);
int k60_adsp_handoff_owner_active(void);
int main(int argc,char **argv)
{
    unsigned first=argc>1?(unsigned)atoi(argv[1]):1u;
    if(k60_adsp_startup_claim(0) || k60_adsp_startup_claim(3) ||
       !k60_adsp_startup_claim(first) || k60_adsp_startup_claim(first) ||
       k60_adsp_startup_claim(first==1?2:1) ||
       k60_adsp_handoff_owner_active()!=(first==1)) return 1;
    printf("TESTS OK startup owner %u excludes repeated/competing attempts\n",first);
    return 0;
}
