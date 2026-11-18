/* SPDX-License-Identifier: MIT */
#include "NativeAdrenoSubmit.h"
#include "NativeAdrenoABI.h"
#include "AdrenoPM4.h"
#include <kern/clock.h>
#include <IOKit/IOLib.h>

/* Per kernel method: [method][0] calls, [1] calls that returned non-zero, [2] last status,
 * [3] total time in us. The user client credits these after each method returns, so a reader
 * inside NativeAdrenoSubmit sees the last COMPLETED submission, not its own (P-237: name the
 * window). Until 2026-11-19 nothing in the tree read them (P-241). */
extern "C" {extern volatile uint32_t native_adreno_method_stats[20][4];}

/* CP_INDIRECT_BUFFER is opcode 0x3f with a 3-word payload: 64-bit GPU address
 * and IB_SIZE in dwords (bits 0..19), exactly as the pinned adreno_pm4.xml
 * domain states and Linux msm_gem_submit.c converts the userspace byte size. */
enum : uint32_t {SubmitIndirectBuffer=0x3f,SubmitIbWords=3,SubmitMaxJobs=8,
    SubmitMaxBuffers=16,SubmitMaxIbBytes=0xfffffu*4u,
    SubmitAuditBytes=256u*1024u};   /* IB bytes the write-combine audit compares per submission */
extern "C" {volatile uint32_t native_adreno_coherence[8];}
/* The submission (1-based count) at which the write-combine audit found a dirty IB line or failed; 0 = never. */
extern "C" {volatile uint32_t native_adreno_wc_distrusted;}
/* The write-combine audit before each submission while trusted: [0] submissions audited, [1] IB lines compared, [2] dirty lines,
 * [3] stale clean lines, [4] the last audit failure (any failure also ends the trust), [5] pages found back at the default attribute
 * and write-combined again. */
extern "C" {volatile uint32_t native_adreno_wc_audit[6];}
/* Fence waits: [0] calls, [1] timeouts, [2] the fence of the last timed-out wait, [3] the fence value the GPU had written then, [4] the newest fence handed out,
 * [5] the newest completed, [6] waits for a fence no job holds (observeFence path), [7] the last fence refused as never submitted. */
extern "C" {volatile uint32_t native_adreno_fence_wait[8];}
/* The IBs of the last submissions: [slot] fence, iova low/high, bytes, then the first 28 dwords of the first IB (read as the kernel maps it). */
extern "C" {volatile uint32_t native_adreno_ib_log[4][4+28];volatile uint32_t native_adreno_ib_log_count;}
IOReturn NativeAdrenoSubmit::poison()
{
    poisoned_=true;return kIOReturnIOError;
}
NativeAdrenoSubmit::Job *NativeAdrenoSubmit::find(uint32_t fence)
{
    if(fence)for(auto &job:jobs_)if(job.active && job.fence==fence)return &job;
    return nullptr;
}
NativeAdrenoSubmit::Job *NativeAdrenoSubmit::free()
{
    for(auto &job:jobs_)if(!job.active)return &job;
    return nullptr;
}
IOReturn NativeAdrenoSubmit::attach(NativeAdrenoVm *vm,NativeAdrenoRing *ring)
{
    if(attached_ || poisoned_ || vm_ || ring_)return kIOReturnBusy;
    if(!vm || !ring || vm->poisoned() || ring->poisoned())return kIOReturnBadArgument;
    vm_=vm;ring_=ring;attached_=true;stats_={};
    return kIOReturnSuccess;
}
IOReturn NativeAdrenoSubmit::release(Job &job)
{
    IOReturn status=kIOReturnSuccess;
    for(size_t i=0;i<job.count;++i) {
        IOReturn retired=vm_->retireJobAfterCompletion(job.handles[i]);
        if(retired)status=retired;else ++stats_.references_retired;
    }
    if(status)return poison();
    if(vm_->acquireImported())return poison();
    job={};return kIOReturnSuccess;
}
IOReturn NativeAdrenoSubmit::detach()
{
    if(poisoned_ || outstanding())return kIOReturnBusy;
    if(!attached_)return kIOReturnNotReady;
    attached_=false;vm_=nullptr;ring_=nullptr;return kIOReturnSuccess;
}
bool NativeAdrenoSubmit::queueOutstanding(uint32_t queue) const
{
    return rangeOutstanding(queue,1);
}
bool NativeAdrenoSubmit::rangeOutstanding(uint32_t first,uint32_t count) const
{
    for(const auto &job:jobs_)if(job.active && job.queue-first<count)return true;
    return false;
}
size_t NativeAdrenoSubmit::outstanding() const
{
    size_t count=0;for(const auto &job:jobs_)if(job.active)++count;return count;
}
IOReturn NativeAdrenoSubmit::submit(const NativeAdrenoSubmitBuffer *buffers,size_t count,
    uint32_t queue,uint32_t *fence)
{
    if(!fence)return kIOReturnBadArgument;*fence=0;
    if(!attached_ || poisoned_)return kIOReturnNotReady;
    if(!buffers || !count || count>SubmitMaxBuffers)return kIOReturnBadArgument;
    /* Every buffer is validated against the live VM before any reference. */
    uint64_t handles[SubmitMaxBuffers];size_t handle_count=0;
    uint32_t words[SubmitMaxBuffers*(1+SubmitIbWords)];size_t word_count=0;
    for(size_t i=0;i<count;++i) {
        const NativeAdrenoSubmitBuffer &buffer=buffers[i];
        if(!buffer.handle || !buffer.bytes || (buffer.bytes&3) || buffer.bytes>SubmitMaxIbBytes)
            return kIOReturnBadArgument;
        uint64_t iova=0;size_t bytes=0;unsigned permissions=0;
        IOReturn status=vm_->describe(buffer.handle,&iova,&bytes,&permissions);
        if(status)return status;
        if(!(permissions&ArmSmmu4KRead) || buffer.iova<iova ||
            buffer.iova-iova>bytes || buffer.bytes>bytes-(buffer.iova-iova))return kIOReturnBadArgument;
        uint32_t header=0;
        if(AdrenoPM4Type7(SubmitIndirectBuffer,SubmitIbWords,&header)!=AdrenoPM4Success)
            return poison();
        words[word_count++]=header;
        words[word_count++]=(uint32_t)buffer.iova;
        words[word_count++]=(uint32_t)(buffer.iova>>32);
        words[word_count++]=(uint32_t)(buffer.bytes/4);
        bool known=false;
        for(size_t j=0;j<handle_count;++j)if(handles[j]==buffer.handle) {known=true;break;}
        if(!known)handles[handle_count++]=buffer.handle;
    }
    IOReturn swept=retireCompleted();
    if(swept)return swept;
    Job *job=free();
    if(!job)return kIOReturnBusy;
    for(size_t i=0;i<handle_count;++i) {
        IOReturn status=vm_->holdJob(handles[i]);
        if(status) {
            while(i) {vm_->retireJobAfterCompletion(handles[--i]);++stats_.references_retired;}
            return status;
        }
        ++stats_.references_held;
    }
    uint32_t value=0;
    /* int-070: the first IB word as the kernel's cacheable alias and DRAM see it before any maintenance, then DRAM after the CPU
     * caches over every mapped BO are cleaned and invalidated. The board shows the last submission's record on a stall. */
    uint32_t cached=~0u,before=~0u,ignored=0,after=~0u;
    /* Write-combined stores this CPU made before the call (the client's command words) complete before anything below. */
    __asm__ volatile("dsb sy":::"memory");
    /* int-098/099: with write-combined user BOs and no maintenance the CP stopped at the end of the first IB, as in int-065..069 when an
     * IB sat in a CPU cache. While write-combined BOs are trusted, every line of this submission's IBs is compared as a CPU cache and
     * DRAM hold it (bounded). A dirty line means a client view still caches its BOs: maintain every BO from now on, this submission
     * included (the audit already wrote the IB lines back; the rest of the BOs may hold more). */
    if(vm_->writeCombinedTrusted()) {
        /* int-100: the dirty IB page was back at XNU's default (cacheable) attribute. Write-combine every such page again first; the
         * pmap writes its lines back on the way, so the audit below should then find none. */
        uint32_t reset=0;
        IOReturn audited=vm_->reassertWriteCombined(&reset);
        native_adreno_wc_audit[5]=native_adreno_wc_audit[5]+reset;
        uint32_t lines=0,dirty=0,stale=0;size_t budget=SubmitAuditBytes;
        /* The re-assertion above is the correction and runs every time; the audit only detects, and found no dirty line in int-141's
         * 133798, so after the first 16 submissions it compares every eighth one's IBs (it cost about 2 ms each). */
        ++audit_tick_;
        const bool audit_now=audit_tick_<=16 || (audit_tick_&7)==1;
        if(!audit_now)budget=0;
        for(size_t i=0;i<count && budget && !audited;++i) {   /* a failed re-assertion skips the audit and ends the trust */
            const size_t bytes=buffers[i].bytes<budget?(size_t)buffers[i].bytes:budget;
            audited=vm_->auditRange(buffers[i].iova,bytes,&lines,&dirty,&stale);budget-=bytes;
        }
        if(audit_now && audited!=kIOReturnUnsupported) {   /* no board hook (host): nothing to compare */
            native_adreno_wc_audit[0]=native_adreno_wc_audit[0]+1;
            native_adreno_wc_audit[1]=native_adreno_wc_audit[1]+lines;
            native_adreno_wc_audit[2]=native_adreno_wc_audit[2]+dirty;
            native_adreno_wc_audit[3]=native_adreno_wc_audit[3]+stale;
            if(audited)native_adreno_wc_audit[4]=audited;
        }
        if(dirty || (audited && audited!=kIOReturnUnsupported)) {
            /* One line per boot, emitted exactly when trust ends: from here on publishMapped() also
             * maintains every write-combined BO, which is the difference between a cheap submission and
             * the 10 ms pass the probe measures. Without this line a flight cannot tell "distrusted from
             * the start" from "lost trust at frame N", and those have different causes. */
            IOLog("PONG WC: distrust latched submit=%u audit=%u lines=%u dirty=%u stale=%u status=0x%x resets=%u\n",
                (unsigned)(++audit_tick_),(unsigned)native_adreno_wc_audit[0],(unsigned)native_adreno_wc_audit[1],
                (unsigned)native_adreno_wc_audit[2],(unsigned)native_adreno_wc_audit[3],(unsigned)audited,
                (unsigned)reset);
            vm_->distrustWriteCombined();
            native_adreno_wc_distrusted=native_adreno_coherence[0]+1;
        }
    }
    (void)vm_->sampleWord(buffers[0].iova,&cached,&before);
    const uint64_t publish_began=mach_absolute_time();
    IOReturn status=vm_->publishMapped();
    const uint64_t publish_ticks=mach_absolute_time()-publish_began;
    if(!status) {
        /* Probe (2026-11-18): publishMapped() maintains every mapped BO, so the cost should follow the mapped set and not the
         * submission. This records the submission's own referenced bytes next to the time the pass took, so a flight shows whether
         * the two are proportional and whether the pass is the 10.2-11.5 ms that no copy shape moved. */
        static uint32_t probed;
        if(!(++probed&31)) {
            uint64_t referenced=0,nanoseconds=0;
            for(size_t i=0;i<count;++i)referenced+=buffers[i].bytes;
            absolutetime_to_nanoseconds(publish_ticks,&nanoseconds);
            /* The userspace side of a submission is inside [MTLCommandBuffer commit], and the
             * coherence work that used to dominate it is now skipped, yet that call still takes
             * about 3.0 ms of a 12.6 ms present(). This prints the KMD's own view of the same
             * submit (native_adreno_method_stats[5] = NativeAdrenoMethodSubmit, cumulative total
             * microseconds in slot 3) so one flight separates "the kernel is slow" from "the
             * translator is slow": if sub_us is close to the userspace number the time is spent
             * here, if it is microseconds the time is upstream of us. The counters existed with
             * no reader since 2026-11-18 (P-241's family). */
            /* Window: this runs INSIDE NativeAdrenoSubmit, so the counter for the current
             * method has not been credited yet. The number printed is therefore the last
             * COMPLETED submit, which is the previous frame's - labelled prevsub for that
             * reason (P-237: always name the window). With one submit per frame it describes
             * the same work within a frame interval. */
            IOLog("PONG SUB: sample n=%u buffers=%u referenced=%llu publish=%llu us prevsub_count=%u prevsub_total=%u us\n",
                (unsigned)probed,(unsigned)count,referenced,nanoseconds/1000,
                (unsigned)native_adreno_method_stats[NativeAdrenoMethodSubmit][0],
                (unsigned)native_adreno_method_stats[NativeAdrenoMethodSubmit][3]);
        }
        (void)vm_->sampleWord(buffers[0].iova,&ignored,&after);
        native_adreno_coherence[0]=native_adreno_coherence[0]+1;
        native_adreno_coherence[1]=cached;native_adreno_coherence[2]=before;native_adreno_coherence[3]=after;
        if(cached!=before || before!=after) {
            if(!native_adreno_coherence[4]) {
                native_adreno_coherence[5]=cached;native_adreno_coherence[6]=before;native_adreno_coherence[7]=after;
            }
            native_adreno_coherence[4]=native_adreno_coherence[4]+1;
        }
        status=vm_->invalidateTlb();
    }
    if(status) {
        for(size_t i=0;i<handle_count;++i) {vm_->retireJobAfterCompletion(handles[i]);++stats_.references_retired;}
        return status;
    }
    {
        const uint32_t slot=native_adreno_ib_log_count&3;uint32_t head[28];
        (void)vm_->peekWords(buffers[0].iova,head,28);
        native_adreno_ib_log[slot][0]=ring_->lastSubmitted()+1;native_adreno_ib_log[slot][1]=(uint32_t)buffers[0].iova;
        native_adreno_ib_log[slot][2]=(uint32_t)(buffers[0].iova>>32);native_adreno_ib_log[slot][3]=(uint32_t)buffers[0].bytes;
        for(unsigned i=0;i<28;++i)native_adreno_ib_log[slot][4+i]=head[i];
        native_adreno_ib_log_count=native_adreno_ib_log_count+1;
    }
    status=ring_->submitFramed(words,word_count,&value);
    if(status) {
        /* A poisoned ring may already have consumed the WPTR write, so the
         * referenced buffers cannot be retired here. */
        if(ring_->poisoned()) {
            *job=Job{};++stats_.poisoned_jobs;
            for(size_t i=0;i<handle_count;++i)job->handles[i]=handles[i];
            job->count=handle_count;job->queue=queue;job->active=true;
            return poison();
        }
        while(handle_count) {vm_->retireJobAfterCompletion(handles[--handle_count]);++stats_.references_retired;}
        return status;
    }
    for(size_t i=0;i<handle_count;++i)job->handles[i]=handles[i];
    job->count=handle_count;job->fence=value;job->queue=queue;job->active=true;
    ++stats_.submissions;
    if(outstanding()>stats_.peak_jobs)stats_.peak_jobs=outstanding();
    *fence=value;
    return kIOReturnSuccess;
}
IOReturn NativeAdrenoSubmit::observeFence(uint32_t fence,const NativeAdrenoRingClock *clock,
    uint32_t timeout_us)
{
    if(!attached_ || poisoned_)return kIOReturnNotReady;
    if(!fence)return kIOReturnBadArgument;
    const NativeAdrenoRingFence result=ring_->observeFence(fence,clock,timeout_us,nullptr);
    if(result==NativeAdrenoRingFencePoisoned)return poison();
    if(result==NativeAdrenoRingFenceArgument)return kIOReturnBadArgument;
    if(result==NativeAdrenoRingFenceTimeout)return kIOReturnTimeout;
    return kIOReturnSuccess;
}
IOReturn NativeAdrenoSubmit::wait(uint32_t fence,const NativeAdrenoRingClock *clock,
    uint32_t timeout_us)
{
    if(!attached_ || poisoned_)return kIOReturnNotReady;
    Job *job=find(fence);
    uint32_t observed=0;
    native_adreno_fence_wait[0]=native_adreno_fence_wait[0]+1;
    if(!job) {
        native_adreno_fence_wait[6]=native_adreno_fence_wait[6]+1;
        const NativeAdrenoRingFence passed=ring_->observeFence(fence,clock,timeout_us,&observed);
        if(passed==NativeAdrenoRingFencePoisoned)return poison();
        if(passed==NativeAdrenoRingFenceArgument) {native_adreno_fence_wait[7]=fence;return kIOReturnBadArgument;}
        if(passed==NativeAdrenoRingFenceTimeout) {
            ++stats_.timeouts;
            native_adreno_fence_wait[1]=native_adreno_fence_wait[1]+1;native_adreno_fence_wait[2]=fence;native_adreno_fence_wait[3]=observed;
            native_adreno_fence_wait[4]=ring_->lastSubmitted();native_adreno_fence_wait[5]=ring_->completedFence();
            return kIOReturnTimeout;
        }
        return kIOReturnSuccess;
    }
    const NativeAdrenoRingFence result=ring_->wait(fence,clock,timeout_us,&observed);
    if(result==NativeAdrenoRingFencePoisoned)return poison();
    if(result==NativeAdrenoRingFenceArgument) {native_adreno_fence_wait[7]=fence;return kIOReturnBadArgument;}
    if(result==NativeAdrenoRingFenceTimeout) {
        ++stats_.timeouts;
        native_adreno_fence_wait[1]=native_adreno_fence_wait[1]+1;native_adreno_fence_wait[2]=fence;native_adreno_fence_wait[3]=observed;
        native_adreno_fence_wait[4]=ring_->lastSubmitted();native_adreno_fence_wait[5]=ring_->completedFence();
        return kIOReturnTimeout;
    }
    IOReturn status=release(*job);
    if(status)return status;
    ++stats_.completed;
    return kIOReturnSuccess;
}
IOReturn NativeAdrenoSubmit::waitAll(const NativeAdrenoRingClock *clock,uint32_t timeout_us)
{
    if(!attached_ || poisoned_)return kIOReturnNotReady;
    while(outstanding()) {
        Job *oldest=nullptr;
        for(auto &job:jobs_)if(job.active && (!oldest || job.fence-oldest->fence>0x80000000u))oldest=&job;
        const IOReturn status=wait(oldest->fence,clock,timeout_us);
        if(status)return status;
    }
    return kIOReturnSuccess;
}
IOReturn NativeAdrenoSubmit::waitRange(uint32_t first,uint32_t count,const NativeAdrenoRingClock *clock,uint32_t timeout_us)
{
    if(!attached_ || poisoned_)return kIOReturnNotReady;
    while(rangeOutstanding(first,count)) {
        Job *oldest=nullptr;
        for(auto &job:jobs_)if(job.active && job.queue-first<count && (!oldest || job.fence-oldest->fence>0x80000000u))oldest=&job;
        const IOReturn status=wait(oldest->fence,clock,timeout_us);
        if(status)return status;
    }
    return kIOReturnSuccess;
}
IOReturn NativeAdrenoSubmit::retireCompleted()
{
    if(!attached_ || poisoned_)return kIOReturnNotReady;
    for(auto &job:jobs_) {
        if(!job.active)continue;
        const NativeAdrenoRingFence state=ring_->observeFence(job.fence,nullptr,0,nullptr);
        if(state==NativeAdrenoRingFencePoisoned)return poison();
        if(state!=NativeAdrenoRingFenceComplete)continue;
        const IOReturn status=release(job);
        if(status)return status;
        ++stats_.completed;
    }
    return kIOReturnSuccess;
}
