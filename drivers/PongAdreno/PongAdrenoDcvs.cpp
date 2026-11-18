/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* K60 runtime GPU DCVS: the official section 5 loop (GMU XO busy counter, 50 %
 * target, HFI bandwidth vote). The level decision is K60GpuFreqPlan.c, which
 * the host test covers; this file only reads the counter, keeps time, applies
 * the idle/wake floor and votes. Structure, the 16 ms cadence, the 85 % top
 * threshold and the 50 ms wake boost come from UniXNU-zizhan
 * drivers/PongAdreno/PongAdrenoPlatform.cpp:396-545 (BSD-2-Clause-Patent),
 * itself from UniXNU-sheng package/GpuPowerProbe.cpp and Linux
 * msm_gpu_devfreq/simple_ondemand. No touch boost: K60 has no touch activity
 * source yet, so pong_gpu_dcvs_touch_ms is not implemented.
 */
#include <IOKit/IOLib.h>
#include <kern/clock.h>
#include <kern/thread.h>
#include <pexpert/pexpert.h>
#include "PongAdrenoGmu.h"
#include "PongAdrenoPower.h"
#include "K60GpuFreqPlan.h"

extern "C" PongGpuGmuDevice *pong_adreno_gmu_device(void);
extern "C" void pong_ramoops_diagnostic_write(const char *,int);

namespace {
constexpr unsigned kWindowMs=16;
constexpr unsigned kReportMs=10000;
/* 19.2 MHz XO: one tick is 625/12 ns (52.083 ns). */
constexpr uint64_t kTickNsNumerator=625,kTickNsDenominator=12;
static volatile unsigned sStarted;

static void report(const char *phase,unsigned result,uint64_t a=0,uint64_t b=0)
{
    char text[240];int n=snprintf(text,sizeof(text),
        "PONG ADRENO: %s result=%u a=0x%llx b=0x%llx\n",phase,result,a,b);
    if(n>0){IOLog("%s",text);pong_ramoops_diagnostic_write(text,n<(int)sizeof(text)?n:(int)sizeof(text)-1);}
}
static void dcvs(void *,wait_result_t)
{
    PongGpuGmuDevice *gmu=pong_adreno_gmu_device();
    if(!gmu){report("SKIP DCVS no GMU device",1);return;}
    unsigned top=K60_GPU_MAX_LEVELS,floor=1,boost_ms=50;
    (void)PE_parse_boot_argn("pong_gpu_max_level",&top,sizeof(top));
    (void)PE_parse_boot_argn("pong_gpu_dcvs_min",&floor,sizeof(floor));
    (void)PE_parse_boot_argn("pong_gpu_dcvs_boost_ms",&boost_ms,sizeof(boost_ms));
    if(top<1 || top>K60_GPU_MAX_LEVELS)top=K60_GPU_MAX_LEVELS;
    if(floor<1)floor=1;
    if(floor>top)floor=top;
    /* PongAdrenoPowerLevels is descending Android order; K60 tables ascend. */
    uint32_t khz[K60_GPU_MAX_LEVELS];
    for(unsigned i=0;i<K60_GPU_MAX_LEVELS;i++)khz[i]=PongAdrenoPowerLevels[i].hz/1000u;
    K60GpuTable table={};
    if(k60_gpu_build_table(khz,K60_GPU_MAX_LEVELS,&table)!=K60_GPU_MAX_LEVELS)
        {report("SKIP DCVS table",2);return;}
    table.count=top;
    if(PongAdrenoGmuEnableBusyCounter(gmu)){report("SKIP DCVS busy counter",3);return;}
    uint64_t busy=0;
    if(PongAdrenoGmuBusyTicks(gmu,&busy)){report("SKIP DCVS first sample",4);return;}
    K60GpuDcvs dcvs={};
    K60GpuGovernor gov={};
    k60_gpu_dcvs_reset(&dcvs,&gov,floor,top);
    uint64_t last_busy=busy,last=0,report_at=0,win_busy=0,win_us=0;
    absolutetime_to_nanoseconds(mach_absolute_time(),&last);
    report("DCVS started",0,(uint64_t(top)<<32)|floor,dcvs.level);
    for(;;) {
        IOSleep(kWindowMs);
        uint64_t now_ticks=0;
        if(PongAdrenoGmuBusyTicks(gmu,&now_ticks)){report("STOP DCVS busy read",5);break;}
        uint64_t at=0,ns=0;
        absolutetime_to_nanoseconds(mach_absolute_time(),&at);
        if(at<=last)continue;
        ns=at-last;last=at;
        uint64_t delta=now_ticks-last_busy;last_busy=now_ticks;
        uint64_t busy_ns=delta*kTickNsNumerator/kTickNsDenominator;
        if(busy_ns>ns)busy_ns=ns;
        unsigned want=0;
        if(k60_gpu_dcvs_window(&dcvs,&gov,&table,delta,ns,at,boost_ms,
            K60_GPU_WAKE_MIN_KHZ,&want)<0)
            {report("STOP DCVS governor",6);break;}
        if(want!=dcvs.level) {
            uint32_t error=0;
            const auto status=PongAdrenoGmuSetLevel(gmu,want,
                PongAdrenoPowerLevels[K60_GPU_MAX_LEVELS-want].bus,&error);
            if(k60_gpu_dcvs_voted(&dcvs,&gov,want,status==PongGpuSuccess)) {
                report("STOP DCVS votes refused",dcvs.refused,
                    (uint64_t(status)<<32)|want,dcvs.level);
                break;
            }
        }
        win_busy+=busy_ns/1000ull;win_us+=ns/1000ull;
        if(!report_at)report_at=at+uint64_t(kReportMs)*1000000ull;
        if(at>=report_at) {
            const unsigned average=win_us?unsigned(win_busy*1000ull/(win_us?win_us:1)):0;
            report("DCVS window",dcvs.level,(uint64_t(average)<<32)|dcvs.wakes,
                dcvs.changes);
            report_at=at+uint64_t(kReportMs)*1000000ull;win_busy=win_us=0;
        }
    }
    thread_terminate(current_thread());
    thread_block(THREAD_CONTINUE_NULL);
}
}
extern "C" int pong_adreno_dcvs_start(void)
{
    unsigned requested=0;
    if(!PE_parse_boot_argn("pong_gpu_dcvs",&requested,sizeof(requested)) || requested!=1)return 0;
    if(__atomic_exchange_n(&sStarted,1,__ATOMIC_ACQ_REL))return 0;
    thread_t thread=THREAD_NULL;
    const auto status=kernel_thread_start(dcvs,nullptr,&thread);
    if(status!=KERN_SUCCESS){report("FAIL DCVS thread",static_cast<unsigned>(status));return 1;}
    thread_deallocate(thread);
    return 0;
}
