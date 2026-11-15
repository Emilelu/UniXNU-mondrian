/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Publisher contract: real SMEM allocator/parser, fake PAS/lock/registry. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../../drivers/PongPower/K60HandoffPublish.h"

#define TOTAL 32768u
#define PART 256u
static union { uint64_t align; uint8_t bytes[TOTAL]; } memory;
static char order[32];
static unsigned used, acquired, released, publications;
static int pas_rc, ready_rc, lock_rc, publish_rc, duplicate;
static uint8_t published[K60_ADSP_HANDOFF_BYTES];
static uint32_t initial_up;
static void event(char c) { order[used++] = c; order[used] = 0; }
static uint32_t get32(const uint8_t *p) { return p[0] | (uint32_t)p[1]<<8 | (uint32_t)p[2]<<16 | (uint32_t)p[3]<<24; }
static void put32(uint32_t at, uint32_t value) { memcpy(memory.bytes + at, &value, 4); }
static int exists(void *p) { (void)p; return duplicate; }
static int pas(void *p) { (void)p; event('P'); return pas_rc; }
static int ready(void *p, const K60BatteryConfig *c, const K60Smem *s, uint32_t *bytes, uint32_t *restart)
{ (void)p; (void)c; (void)s; event('R'); *bytes=40; *restart=0; return ready_rc; }
static int lock(void *p)
{ (void)p; event('L'); if (lock_rc) return lock_rc; acquired++; return 0; }
static void unlock(void *p)
{ (void)p; event('U'); released++; }
static int publish(void *p, const uint8_t *data, size_t bytes)
{
    (void)p; event('W');
    if (acquired != released || bytes != sizeof published) return -99;
    memcpy(published, data, bytes); publications++;
    return publish_rc;
}
static const K60HandoffPublishOps ops = {exists, pas, ready, lock, unlock, publish};
static K60BatteryConfig cfg;
static K60Smem smem;
static K60HandoffPublishResult result;
static void setup(void)
{
    memset(&memory,0,sizeof memory); memset(&cfg,0,sizeof cfg); memset(&result,0,sizeof result);
    memset(published,0,sizeof published); memset(order,0,sizeof order);
    used=acquired=released=publications=0; pas_rc=ready_rc=lock_rc=publish_rc=duplicate=0;
    cfg.smem_base=0x80900000; cfg.smem_bytes=TOTAL; cfg.adsp_base=0x9fd00000; cfg.adsp_bytes=0x3100000;
    cfg.remote_pid=2; cfg.ipcc_client=3; cfg.desc_item=478; cfg.tx_item=479; cfg.rx_item=480;
    cfg.smp2p_item=443; cfg.protocol=1;
    smem.base=memory.bytes; smem.size=TOTAL;
    put32(TOTAL-4096,0x434f5424); put32(TOTAL-4092,1); put32(TOTAL-4088,1);
    put32(TOTAL-4064,PART); put32(TOTAL-4060,0x6000); put32(TOTAL-4052,2u<<16); put32(TOTAL-4048,8);
    put32(PART,0x54525024); put32(PART+4,2u<<16); put32(PART+8,0x6000);
    put32(PART+12,32); put32(PART+16,0x6000);
    /* A remote-created SMP2P item, not a readiness record invented by publisher. */
    K60SmemPartition part; uint32_t offset, bytes;
    if (k60_smem_partition(&smem,0,2,&part) || k60_smem_alloc(&smem,&part,443,40,&offset,&bytes)) {
        fputs("fixture failure\n",stderr); exit(2);
    }
    put32(offset,0x504d5324); put32(offset+4,1); put32(offset+8,2); put32(offset+12,0x10001);
    memcpy(memory.bytes+offset+20,"slave-kernel",12); put32(offset+36,2);
    /* The genuine PAS owner prepares these while ADSP is stopped. */
    const uint16_t ids[3]={478,479,480}; const uint32_t sizes[3]={32,4096,4096};
    for (unsigned i=0;i<3;i++)
        if (k60_smem_alloc(&smem,&part,ids[i],sizes[i],&offset,&bytes)) puts("fixture rings failure");
    initial_up=get32(memory.bytes+PART+12);
}
static unsigned checks, failures;
#define CHECK(x) do { checks++; if (!(x)) { failures++; printf("FAIL line %u: %s\n",__LINE__,#x); } } while(0)
static int run(void) { return k60_handoff_publish(&cfg,&smem,1794654001u,&ops,0,&result); }
int main(void)
{
    K60AdspGlinkHandoff parsed;
    setup(); CHECK(run()==0); CHECK(strcmp(order,"PRLUW")==0); CHECK(acquired==1 && released==1);
    CHECK(publications==1); CHECK(get32(published+12)==15); CHECK(get32(published+88)==2);
    CHECK(get32(published+92)==443); CHECK(k60_adsp_handoff_parse(published,sizeof published,&cfg,&parsed)==0);
    CHECK(parsed.desc_bytes==32 && parsed.tx_bytes==4096 && parsed.rx_bytes==4096);
    CHECK(get32(memory.bytes+PART+12)==initial_up);
    setup(); pas_rc=-17; CHECK(run()==K60PublishPasFailed); CHECK(strcmp(order,"P")==0);
    CHECK(publications==0 && acquired==0 && get32(memory.bytes+PART+12)==initial_up);
    setup(); ready_rc=-1; CHECK(run()==K60PublishNotReady); CHECK(strcmp(order,"PR")==0); CHECK(acquired==0 && publications==0);
    setup(); lock_rc=-1; CHECK(run()==K60PublishLockFailed); CHECK(strcmp(order,"PRL")==0); CHECK(released==0 && publications==0);
    setup(); put32(TOTAL-4096,0); CHECK(run()==K60PublishPartitionFailed); CHECK(strcmp(order,"PRLU")==0); CHECK(acquired==released && publications==0);
    setup(); duplicate=1; CHECK(run()==K60PublishExists); CHECK(order[0]==0 && publications==0);
    setup(); CHECK(k60_handoff_publish(&cfg,&smem,0,&ops,0,&result)==K60PublishInvalid); CHECK(order[0]==0);
    setup(); publish_rc=-1; CHECK(run()==K60PublishPropertyFailed); CHECK(acquired==released && publications==1);
    setup(); { K60SmemPartition part; uint32_t off, bytes; CHECK(k60_smem_partition(&smem,0,2,&part)==0);
      CHECK(k60_smem_find(&smem,&part,478,&off,&bytes)==0); put32(off,1);
      CHECK(run()==K60PublishDirtyDescriptor); CHECK(strcmp(order,"PRLU")==0); CHECK(publications==0 && acquired==released); }
    /* A missing provider-prepared TX item must not cause live allocation. */
    setup(); { K60SmemPartition part; uint32_t off, bytes;
      CHECK(k60_smem_partition(&smem,0,2,&part)==0);
      CHECK(k60_smem_find(&smem,&part,479,&off,&bytes)==0);
      memory.bytes[off-14]=0xe7; memory.bytes[off-13]=0x03; /* id 999, same valid entry */
      CHECK(run()==K60PublishBuildFailed); CHECK(publications==0 && acquired==released);
      CHECK(get32(memory.bytes+PART+12)==initial_up); }
    /* Exercise real SMP2P readiness, not only the fake wait callback. */
    setup(); { K60SmemPartition part; uint32_t off,n,got,epoch;
      CHECK(k60_smem_partition(&smem,0,2,&part)==0);
      CHECK(k60_smem_find(&smem,&part,443,&off,&n)==0);
      CHECK(k60_handoff_remote_ready(&cfg,&smem,&part,&got,&epoch)==0 && got==40 && epoch==0);
      put32(off+36,0); CHECK(k60_handoff_remote_ready(&cfg,&smem,&part,&got,&epoch)!=0);
      put32(off+36,1); CHECK(k60_handoff_remote_ready(&cfg,&smem,&part,&got,&epoch)!=0);
      put32(off+36,3); CHECK(k60_handoff_remote_ready(&cfg,&smem,&part,&got,&epoch)!=0);
      put32(off+36,2); put32(off+8,3); CHECK(k60_handoff_remote_ready(&cfg,&smem,&part,&got,&epoch)!=0);
      put32(off+8,2); put32(off+12,0x20001); CHECK(k60_handoff_remote_ready(&cfg,&smem,&part,&got,&epoch)!=0);
      put32(off+12,0x10001); put32(off,0); CHECK(k60_handoff_remote_ready(&cfg,&smem,&part,&got,&epoch)!=0); }
    setup(); { uint8_t before[TOTAL]; memcpy(before,memory.bytes,TOTAL);
      CHECK(run()==0); CHECK(memcmp(before,memory.bytes,TOTAL)==0); }
    printf("TESTS %s %u checks (%u failures)\n",failures?"FAILED":"OK",checks,failures);
    return failures!=0;
}
