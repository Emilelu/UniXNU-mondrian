/* SPDX-License-Identifier: MIT */
/* Sheng's actual Metal blit presenter, using Pong's scoped frame transport.
 * Optional bounded RGB cadence observations do not alter rendering or fences. */
#pragma once
#include <pthread.h>
#include "../PongAdreno/PongScanoutWire.h"
#include "GpuScanoutPresenter.h"
namespace pongscanout {
using Open=kern_return_t(*)(unsigned,mach_port_t,unsigned,unsigned *);
using Call=kern_return_t(*)(unsigned,unsigned,const void *,size_t,void *,size_t *);
using Map=kern_return_t(*)(unsigned,unsigned,mach_port_t,uint64_t *,uint64_t *,unsigned);
struct Context {unsigned connection;Call call;gpupresent::Presenter *presenter;gpupresent::Scanout scanout;bool probe;};
static bool sampleRgb(const gpupresent::Frame &frame,uint32_t out[256])
{
    if(!frame.base || ((uintptr_t)frame.base&3) || !frame.width || !frame.height ||
       frame.stride<size_t(frame.width)*4 || (frame.stride&3) || frame.height>frame.bytes/frame.stride)return false;
    const auto *base=static_cast<const volatile uint32_t *>(frame.base);
    for(unsigned i=0;i<256;++i) {
        const size_t x=(uint64_t(i%16)*2+1)*frame.width/32;
        const size_t y=(uint64_t(i/16)*2+1)*frame.height/32;
        out[i]=base[(y*frame.stride)/4+x]&0x00ffffffu;
    }
    return true;
}
static void *serve(void *opaque)
{
    auto *context=static_cast<Context *>(opaque);unsigned copies=0,refusals=0;
    uint32_t before[256],source[256],target[256],lastSource[256],lastTarget[256];
    bool previous=false;unsigned samples=0,sourceChanges=0,targetChanges=0,mismatches=0,mutations=0;
    uint64_t started=0,window=0,last=0,cost=0,maxCost=0,maxGap=0;
    auto now=[](){return clock_gettime_nsec_np(CLOCK_UPTIME_RAW)/1000;};
    pthread_set_qos_class_self_np(QOS_CLASS_USER_INTERACTIVE,0);
    for(;;) {
        @autoreleasepool {
            PongScanoutWaitInfo wait{500};PongScanoutFrame frame{};size_t bytes=sizeof(frame);
            auto status=context->call(context->connection,PongScanoutWait,&wait,sizeof(wait),&frame,&bytes);
            if(unsigned(status)==0xe00002d6)continue;
            if(status || bytes!=sizeof(frame) || frame.reserved || frame.format!=PongScanoutBgra) {
                report("scanout frame wait stopped",status?:-1);return nullptr;
            }
            const uint64_t began=now();
            if(!started)started=window=began;
            const gpupresent::Frame input{reinterpret_cast<void *>(frame.address),size_t(frame.bytes),
                size_t(frame.stride),frame.width,frame.height};
            const bool probing=context->probe && began-started<120000000 && sampleRgb(input,before);
            auto result=context->presenter->present({reinterpret_cast<void *>(frame.address),size_t(frame.bytes),
                size_t(frame.stride),frame.width,frame.height});
            const uint64_t ended=now();
            if(probing && result==gpupresent::kOk && sampleRgb(input,source) &&
               sampleRgb({context->scanout.base,context->scanout.bytes,context->scanout.stride,
                   context->scanout.width,context->scanout.height},target)) {
                ++samples;
                mutations+=memcmp(before,source,sizeof(source))!=0;
                mismatches+=memcmp(source,target,sizeof(source))!=0;
                if(previous) {
                    sourceChanges+=memcmp(source,lastSource,sizeof(source))!=0;
                    targetChanges+=memcmp(target,lastTarget,sizeof(target))!=0;
                    const uint64_t gap=began-last;if(gap>maxGap)maxGap=gap;
                }
                memcpy(lastSource,source,sizeof(source));memcpy(lastTarget,target,sizeof(target));previous=true;last=began;
                const uint64_t took=ended-began;cost+=took;if(took>maxCost)maxCost=took;
                if(ended-window>=5000000) {
                    char text[240];snprintf(text,sizeof(text),
                        "RGB seq=%llu ms=%llu n=%u src=%u dst=%u mismatch=%u mutate=%u copy_us=%llu max=%llu gap=%llu",
                        (unsigned long long)frame.sequence,(unsigned long long)((ended-window)/1000),samples,
                        sourceChanges,targetChanges,mismatches,mutations,(unsigned long long)(cost/samples),
                        (unsigned long long)maxCost,(unsigned long long)maxGap);
                    report(text,0);window=ended;samples=sourceChanges=targetChanges=mismatches=mutations=0;cost=maxCost=maxGap=0;
                }
            }
            // Presenter returns kOk only after waitUntilCompleted reports the
            // real command buffer completed. Errors never retire as success.
            const bool notSubmitted=result!=gpupresent::kOk && result!=gpupresent::kGpuFailed;
            PongScanoutDone done{frame.sequence,result==gpupresent::kOk?0u:
                (notSubmitted?uint32_t(PongScanoutNotSubmitted):0xe00002bcu),0};bytes=0;
            status=context->call(context->connection,PongScanoutComplete,&done,sizeof(done),nullptr,&bytes);
            if(status || result==gpupresent::kGpuFailed) {
                report("GPU scanout copy failed; mappings retained",status?:int(result));return nullptr;
            }
            if(notSubmitted) {
                report("scanout copy not submitted; CPU fallback available",int(result));
                // Retry a transient resource refusal, then leave the kernel's
                // CPU path active instead of repeatedly stalling each frame.
                if(++refusals>=3)return nullptr;
                continue;
            }
            refusals=0;
            if(copies++<3)report("actual GPU scanout copy completed",0);
        }
    }
}
static void start(void *iokit,unsigned service,id<MTLDevice> device)
{
    bool probe=false;
    char args[4096];size_t argsLength=sizeof(args)-1;
    if(!sysctlbyname("kern.bootargs",args,&argsLength,nullptr,0)) {
        args[argsLength<sizeof(args)?argsLength:sizeof(args)-1]=0;
        const char probeKey[]="gprobe=1";
        const char *found=args;
        while((found=strstr(found,probeKey))) {
            const char after=found[sizeof(probeKey)-1];
            if((found==args || found[-1]==' ' || found[-1]=='\t') && (!after || after==' ' || after=='\t'))probe=true;
            found+=sizeof(probeKey)-1;
        }
        const char key[]="pong_gpu_scanout=0";
        const char *option=args;
        while((option=strstr(option,key))) {
            const char after=option[sizeof(key)-1];
            if((option==args || option[-1]==' ' || option[-1]=='\t') &&
               (!after || after==' ' || after=='\t')) {
                report("GPU scanout disabled by boot policy; CPU display active",0);return;
            }
            option+=sizeof(key)-1;
        }
    }
    auto open=(Open)dlsym(iokit,"IOServiceOpen");auto call=(Call)dlsym(iokit,"IOConnectCallStructMethod");
    auto map=(Map)dlsym(iokit,"IOConnectMapMemory64");
    auto close=(kern_return_t(*)(unsigned))dlsym(iokit,"IOServiceClose");
    if(!open || !call || !map || !close)return;
    unsigned connection=0;auto status=open(service,mach_task_self(),0x4148,&connection);
    if(status){report("scanout connection unavailable; CPU display remains available",status);return;}
    PongScanoutModeInfo mode{};size_t size=sizeof(mode);
    status=call(connection,PongScanoutMode,nullptr,0,&mode,&size);
    if(status || size!=sizeof(mode) || mode.version!=1 || mode.format!=PongScanoutBgra ||
       !mode.width || !mode.height || mode.width>16384 || mode.height>16384 ||
       mode.stride<mode.width*4 || mode.bytes<mode.stride*mode.height) {
        close(connection);report("scanout mode refused",status?:-1);return;
    }
    uint64_t address=0,length=0;
    status=map(connection,PongScanoutMemory,mach_task_self(),&address,&length,1);
    if(status || !address || length<mode.bytes){close(connection);report("scanout mapping refused",status?:-1);return;}
    auto *presenter=new gpupresent::Presenter(device,{reinterpret_cast<void *>(address),size_t(mode.bytes),
        size_t(mode.stride),uint32_t(mode.width),uint32_t(mode.height)});
    presenter->sink(reportFrame);
    if(!presenter->ready()) {
        // The import can own pinned memory even when creation fails. Keep its
        // connection/backing for teardown rather than silently recycle it.
        report("GPU scanout import unavailable; CPU fallback requires retired DMA",-1);return;
    }
    auto *context=new Context{connection,call,presenter,{reinterpret_cast<void *>(address),size_t(mode.bytes),
        size_t(mode.stride),uint32_t(mode.width),uint32_t(mode.height)},probe};pthread_t thread;
    pthread_attr_t attr;pthread_attr_init(&attr);pthread_attr_setdetachstate(&attr,PTHREAD_CREATE_DETACHED);
    pthread_attr_setstacksize(&attr,1024*1024);
    int result=pthread_create(&thread,&attr,serve,context);pthread_attr_destroy(&attr);
    report(result?"scanout worker creation failed":"real GPU scanout worker ready",result);
}
}
