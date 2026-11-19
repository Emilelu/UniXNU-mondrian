/* SPDX-License-Identifier: MIT */
/* Sheng's actual Metal blit presenter, using Pong's scoped frame transport.
 * No readback checks, test draws, physical-address API or fabricated fence. */
#pragma once
#include <pthread.h>
#include <time.h>
#include "../PongAdreno/PongScanoutWire.h"
#include "GpuScanoutPresenter.h"
#include "PongScanoutTiming.h"
namespace pongscanout {
using Open=kern_return_t(*)(unsigned,mach_port_t,unsigned,unsigned *);
using Call=kern_return_t(*)(unsigned,unsigned,const void *,size_t,void *,size_t *);
using Map=kern_return_t(*)(unsigned,unsigned,mach_port_t,uint64_t *,uint64_t *,unsigned);
struct Context {unsigned connection;Call call;gpupresent::Presenter *presenter;bool blitProbe;unsigned bench;};
/* A span is only meaningful when both ends were actually read: a zeroed timespec is
 * what a failed clock_gettime leaves behind, and treating that as a real stamp would
 * report a stage that never ran. */
static inline uint64_t span(const struct timespec &from,const struct timespec &to)
{
    return stamped(from) && stamped(to) ? elapsedUs(from,to) : 0;
}
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
            lastWait=span(t0,t1);
            /* One line per flight, only after the first successful copy: name the primitive and
             * both pitches. Reporting on a refused first frame would print stale or zero shape
             * data and the next retry would produce a second line. */
            if(!copies && result==gpupresent::kOk) {
                char path[192];
                snprintf(path,sizeof(path),"scanout copy %s source=%zu scanout=%zu rows=%u",
                         context->presenter->copyShape(),context->presenter->sourceStride(),
                         context->presenter->scanoutStride(),context->presenter->rows());
                report(path,0);
                /* The control the 2026-11-19 flight could not provide: the same bytes copied
                 * into a device buffer and back into the framebuffer. Runs once, only when the
                 * boot argument asked, and only after a real copy just succeeded, so a zero can
                 * only mean the control copy itself failed. */
                if(context->blitProbe && context->presenter->runBlitProbe(
                       {reinterpret_cast<void *>(frame.address),size_t(frame.bytes),
                        size_t(frame.stride),frame.width,frame.height})) {
                    char control[256];
                    snprintf(control,sizeof(control),
                        "scanout blit control bytes=%zu src-to-device=%llu us device-to-scanout=%llu us",
                        context->presenter->probeBytes(),
                        (unsigned long long)context->presenter->probeSourceToDeviceUs(),
                        (unsigned long long)context->presenter->probeDeviceToScanoutUs());
                    report(control,0);
                
                /* A bounded repeat of the same copy, so the blit can be measured without
                 * waiting for something on the device to animate. Every flight before this
                 * one came back with four frames and no steady sample because the screen was
                 * static, which is a property of the screen and not of the copy. Off unless
                 * gbench=N asked, and it runs inside the same offer, before the kernel
                 * retires the mapping, so the pages are the ones the client really gave us. */
                if(context->bench) {
                    for(unsigned n=1;n<=context->bench;n++) {
                        const auto repeat=context->presenter->present(
                            {reinterpret_cast<void *>(frame.address),size_t(frame.bytes),
                             size_t(frame.stride),frame.width,frame.height});
                        const uint64_t imported=context->presenter->importMicroseconds();
                        const uint64_t encoded=context->presenter->encodeMicroseconds();
                        const uint64_t submitted=context->presenter->submitMicroseconds();
                        const uint64_t waited=context->presenter->waitMicroseconds();
                        char line[256];
                        snprintf(line,sizeof(line),
                                 "scanout bench n=%u/%u import=%llu us encode=%llu us submit=%llu us"
                                 " gpu=%llu us sum=%llu us status=0x%x",
                                 n,context->bench,
                                 (unsigned long long)imported,(unsigned long long)encoded,
                                 (unsigned long long)submitted,(unsigned long long)waited,
                                 (unsigned long long)(imported+encoded+submitted+waited),
                                 unsigned(repeat));
                        report(line,0);
                        if(repeat!=gpupresent::kOk)break;
                        struct timespec pause={0,2000000};
                        nanosleep(&pause,nullptr);
                    }
                }
} else if(context->blitProbe) {
                    report("scanout blit control could not run",0);
                }
            }
            lastCopy=span(t1,t2);
            // Presenter returns kOk only after waitUntilCompleted reports the
            // real command buffer completed. Errors never retire as success.
            const bool notSubmitted=result!=gpupresent::kOk && result!=gpupresent::kGpuFailed;
            PongScanoutDone done{frame.sequence,result==gpupresent::kOk?0u:
                (notSubmitted?uint32_t(PongScanoutNotSubmitted):0xe00002bcu),0};bytes=0;
            status=context->call(context->connection,PongScanoutComplete,&done,sizeof(done),nullptr,&bytes);
            {
                struct timespec t3={};clock_gettime(CLOCK_MONOTONIC,&t3);
                lastDone=span(t2,t3);
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
            /* The flight is 240 s long. A 60-frame cadence needs 0.25 fps just to
             * produce one sample, and the 2026-11-18 16:19 flight presented 22
             * frames in 55 s, so no stage line ever appeared and the card could
             * not be judged. Sample the first few frames, then every tenth. */
            if(copies<=8 || !(copies%10)) {
                struct timespec now={};clock_gettime(CLOCK_MONOTONIC,&now);
                /* `sum` is the four stages this side owns, so the flight can compare it
                 * against the kernel's outer `copy` number without doing arithmetic on
                 * numbers that were printed from different samples. `imports` must equal
                 * `frames`: the presenter imports the source once per presented frame and
                 * keeps nothing across frames (PongAdrenoScanout.cpp releases the mapping
                 * as soon as the copy retires, so a cached import would be a dangling one). */
                const uint64_t imported=context->presenter->importMicroseconds();
                const uint64_t encoded=context->presenter->encodeMicroseconds();
                const uint64_t submitted=context->presenter->submitMicroseconds();
                const uint64_t waited=context->presenter->waitMicroseconds();
                /* Every span below is printed in microseconds. The three outer spans used to be
                 * divided by 1000 while still carrying the "us" label, which made a 48 ms frame
                 * read as a 48 us copy and turned P-234 into a false "the copy is free" verdict. */
                char rate[512];snprintf(rate,sizeof(rate),
                    "scanout frames=%u at %llu.%03llu s; last frame: wait=%llu us copy=%llu us done=%llu us; imports=%llu import=%llu us encode=%llu us submit=%llu us gpu=%llu us sum=%llu us",
                    copies,(unsigned long long)absoluteUs(now)/1000000ull,(unsigned long long)(absoluteUs(now)%1000000ull)/1000ull,
                    (unsigned long long)lastWait,(unsigned long long)lastCopy,(unsigned long long)lastDone,
                    (unsigned long long)context->presenter->imports(),
                    (unsigned long long)imported,(unsigned long long)encoded,(unsigned long long)submitted,
                    (unsigned long long)waited,(unsigned long long)(imported+encoded+submitted+waited));
                report(rate,0);
            }
        }
    }
}
static void start(void *iokit,unsigned service,id<MTLDevice> device)
{
    char args[4096];size_t argsLength=sizeof(args)-1;
    /* The control copies the same 18.4 MB two more ways, once, after the first real copy
     * succeeds - roughly 25 ms on one frame.
     *
     * OFF BY DEFAULT since 2026-11-19 (P-244). The control answered its question in
     * usblog-20261119-070345: 1,993 us into a device buffer and 1,835 us into the firmware
     * frame buffer, so the target was never the slow part and there is nothing left to measure
     * here. That same flight ended with a CP/SMMU fault after the mapped set grew to 951
     * objects and 557 MB; the probe's extra full-frame write is not proven innocent, and it
     * also shears one visible frame because it copies at the source pitch. A flight that wants
     * it back sets `pong_gpu_blit_probe=1` on the boot line (the line is at 596 of 607 bytes,
     * so this costs a decision, not a default). */
    bool blitProbe=false;
    unsigned bench=0;
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
        const char probeKey[]="pong_gpu_blit_probe=1";
        option=args;
        while((option=strstr(option,probeKey))) {
            const char after=option[sizeof(probeKey)-1];
            if((option==args || option[-1]==' ' || option[-1]=='\t') &&
               (!after || after==' ' || after=='\t')) { blitProbe=true;break; }
            option+=sizeof(probeKey)-1;
        }
        /* Asking for a level vote implies asking to measure it, so `gperf` also runs a bounded
         * bench: three flights came back with four frames because the screen was static, and a
         * measurement that depends on whether something happens to animate is not a
         * measurement. `gbench=` overrides the count for a future flight that has room for it
         * on the boot line; the count is capped so a typo cannot loop forever. */
        const char perfKey[]="gperf=";
        option=args;
        while((option=strstr(option,perfKey))) {
            if((option==args || option[-1]==' ' || option[-1]=='\t') &&
               option[sizeof(perfKey)-1]>='0' && option[sizeof(perfKey)-1]<='9') { bench=24;break; }
            option+=sizeof(perfKey)-1;
        }
        const char benchKey[]="gbench=";
        option=args;
        while((option=strstr(option,benchKey))) {
            if(option!=args && option[-1]!=' ' && option[-1]!='\t') {option+=sizeof(benchKey)-1;continue;}
            const char *digits=option+sizeof(benchKey)-1;
            if(*digits>='0' && *digits<='9') {
                unsigned value=0,count=0;
                while(*digits>='0' && *digits<='9' && ++count<=6) value=value*10+unsigned(*digits++-'0');
                const char after=*digits;
                if(!after || after==' ' || after=='\t') {
                    bench=value>120?120:value;
                    break;
                }
            }
            option+=sizeof(benchKey)-1;
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
    auto *context=new Context{connection,call,presenter,blitProbe,bench};pthread_t thread;
    pthread_attr_t attr;pthread_attr_init(&attr);pthread_attr_setdetachstate(&attr,PTHREAD_CREATE_DETACHED);
    pthread_attr_setstacksize(&attr,1024*1024);
    int result=pthread_create(&thread,&attr,serve,context);pthread_attr_destroy(&attr);
    report(result?"scanout worker creation failed":"real GPU scanout worker ready",result);
}
}
