/* SPDX-License-Identifier: MIT */
/* Sheng's actual Metal blit presenter, using Pong's scoped frame transport.
 * No readback checks, test draws, physical-address API or fabricated fence. */
#pragma once
#include <pthread.h>
#include <time.h>
#include "../PongAdreno/PongScanoutWire.h"
#include "GpuScanoutPresenter.h"
namespace pongscanout {
using Open=kern_return_t(*)(unsigned,mach_port_t,unsigned,unsigned *);
using Call=kern_return_t(*)(unsigned,unsigned,const void *,size_t,void *,size_t *);
using Map=kern_return_t(*)(unsigned,unsigned,mach_port_t,uint64_t *,uint64_t *,unsigned);
struct Context {unsigned connection;Call call;gpupresent::Presenter *presenter;};
static void *serve(void *opaque)
{
    auto *context=static_cast<Context *>(opaque);unsigned copies=0,refusals=0;
    /* The porting guide's frame-path table splits the render server's own
     * share into "wait for the offer", "encode and copy", and "retire". Keep
     * the last frame's three numbers so the rate line names the stage that
     * costs the frame instead of blaming the whole driver. */
    uint64_t lastWait=0,lastCopy=0,lastDone=0;
    pthread_set_qos_class_self_np(QOS_CLASS_USER_INTERACTIVE,0);
    for(;;) {
        @autoreleasepool {
            PongScanoutWaitInfo wait{500};PongScanoutFrame frame{};size_t bytes=sizeof(frame);
            struct timespec t0={},t1={},t2={};clock_gettime(CLOCK_MONOTONIC,&t0);
            auto status=context->call(context->connection,PongScanoutWait,&wait,sizeof(wait),&frame,&bytes);
            clock_gettime(CLOCK_MONOTONIC,&t1);
            if(unsigned(status)==0xe00002d6)continue;
            if(status || bytes!=sizeof(frame) || frame.reserved || frame.format!=PongScanoutBgra) {
                report("scanout frame wait stopped",status?:-1);return nullptr;
            }
            auto result=context->presenter->present({reinterpret_cast<void *>(frame.address),size_t(frame.bytes),
                size_t(frame.stride),frame.width,frame.height});
            clock_gettime(CLOCK_MONOTONIC,&t2);
            lastWait=uint64_t(t1.tv_sec-t0.tv_sec)*1000000000ull+uint64_t(t1.tv_nsec-t0.tv_nsec);
            lastCopy=uint64_t(t2.tv_sec-t1.tv_sec)*1000000000ull+uint64_t(t2.tv_nsec-t1.tv_nsec);
            // Presenter returns kOk only after waitUntilCompleted reports the
            // real command buffer completed. Errors never retire as success.
            const bool notSubmitted=result!=gpupresent::kOk && result!=gpupresent::kGpuFailed;
            PongScanoutDone done{frame.sequence,result==gpupresent::kOk?0u:
                (notSubmitted?uint32_t(PongScanoutNotSubmitted):0xe00002bcu),0};bytes=0;
            status=context->call(context->connection,PongScanoutComplete,&done,sizeof(done),nullptr,&bytes);
            {
                struct timespec t3={};clock_gettime(CLOCK_MONOTONIC,&t3);
                lastDone=uint64_t(t3.tv_sec-t2.tv_sec)*1000000000ull+uint64_t(t3.tv_nsec-t2.tv_nsec);
            }
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
            if(!(copies%60)) {
                struct timespec now={};clock_gettime(CLOCK_MONOTONIC,&now);
                char rate[320];snprintf(rate,sizeof(rate),
                    "scanout frames=%u at %lld.%03lld s; last frame: wait=%llu us copy=%llu us done=%llu us; imports=%llu reuses=%llu import=%llu us",
                    copies,(long long)now.tv_sec,(long long)(now.tv_nsec/1000000),
                    lastWait/1000,lastCopy/1000,lastDone/1000,
                    (unsigned long long)context->presenter->imports(),(unsigned long long)context->presenter->reuses(),
                    (unsigned long long)context->presenter->importMicroseconds());
                report(rate,0);
            }
        }
    }
}
static void start(void *iokit,unsigned service,id<MTLDevice> device)
{
    char args[4096];size_t argsLength=sizeof(args)-1;
    if(!sysctlbyname("kern.bootargs",args,&argsLength,nullptr,0)) {
        args[argsLength<sizeof(args)?argsLength:sizeof(args)-1]=0;
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
    if(!presenter->ready()) {
        // The import can own pinned memory even when creation fails. Keep its
        // connection/backing for teardown rather than silently recycle it.
        report("GPU scanout import unavailable; CPU fallback requires retired DMA",-1);return;
    }
    auto *context=new Context{connection,call,presenter};pthread_t thread;
    pthread_attr_t attr;pthread_attr_init(&attr);pthread_attr_setdetachstate(&attr,PTHREAD_CREATE_DETACHED);
    pthread_attr_setstacksize(&attr,1024*1024);
    int result=pthread_create(&thread,&attr,serve,context);pthread_attr_destroy(&attr);
    report(result?"scanout worker creation failed":"real GPU scanout worker ready",result);
}
}
