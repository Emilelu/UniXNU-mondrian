// SPDX-License-Identifier: MIT
// GPU presentation: the GPU copies a finished BGRA frame (the compositor's IOSurface pages) into the firmware scanout memory. Both are
// imported without a copy (newBufferWithBytesNoCopy: pinned by the kernel and mapped into the GPU's 4 KiB context), the copy is a blit on
// the GPU's queue, and the call returns after the GPU retired it. No CPU touches a pixel; there is no staging copy and no software fallback
// here. Used through the public Metal API, on any device (the native frontend on the tablet, the Mac's device for the host check).
//
// Bounded stage timing: import / encode / wait are reported separately so a frame budget overrun is attributed by measurement rather than
// guessed. Timing never changes the copy, the queue or the completion contract.
#pragma once
#import <Metal/Metal.h>
#include <unistd.h>
#include <stdint.h>
#include <string.h>
#include <time.h>
#include <stdio.h>

namespace gpupresent {

struct Scanout {
    void *base;       // writable mapping of the firmware framebuffer (page aligned)
    size_t bytes;     // whole extent, a multiple of the page size
    size_t stride;    // bytes per row
    uint32_t width, height;
};

struct Frame {
    const void *base; // page-aligned mapping of the surface pages
    size_t bytes;     // allocation size, a multiple of the page size
    size_t stride;
    uint32_t width, height;
};

enum Result { kOk = 0, kBadFrame, kBadScanout, kNoResource, kGpuFailed };

class Presenter {
public:
    // Set by the host so stage timings use the same bounded diagnostic channel as the rest of the scanout worker.
    using Sink = void (*)(const char *text, int status);
    void sink(Sink handler) { sink_ = handler; }
    Presenter(id<MTLDevice> device, const Scanout &scanout) : device_(device), scanout_(scanout) {
        queue_ = [device newCommandQueue];
        if (!validScanout() || !queue_) return;
        target_ = [device newBufferWithBytesNoCopy:scanout.base length:scanout.bytes options:MTLResourceStorageModeShared deallocator:nil];
    }
    bool ready() const { return target_ != nil; }
    // One frame: encodes the GPU copy, commits, waits for the GPU. Rows are copied as whole rows of width*4 bytes.
    Result present(const Frame &frame) {
        stageStart = stageNow();
        if (!ready()) return kBadScanout;
        const size_t page = (size_t)getpagesize(), row = (size_t)frame.width * 4;
        if (!frame.base || ((uintptr_t)frame.base & (page - 1)) || !frame.bytes || (frame.bytes & (page - 1)) ||
            frame.width != scanout_.width || frame.height != scanout_.height || frame.stride < row ||
            (size_t)frame.height > frame.bytes / frame.stride || frame.stride * (frame.height - 1) + row > frame.bytes) return kBadFrame;
        id<MTLBuffer> source = [device_ newBufferWithBytesNoCopy:(void *)frame.base length:frame.bytes options:MTLResourceStorageModeShared deallocator:nil];
        if (!source) return kNoResource;
        const uint64_t imported = stageNow();
        id<MTLCommandBuffer> commands = [queue_ commandBuffer];
        id<MTLBlitCommandEncoder> blit = commands ? [commands blitCommandEncoder] : nil;
        if (!blit) return kNoResource;
        bool rowByRow = false;
        if (frame.stride == scanout_.stride) {
            // Equal pitch: the rows are one contiguous run.
            [blit copyFromBuffer:source sourceOffset:0 toBuffer:target_ destinationOffset:0 size:frame.stride * (frame.height - 1) + row];
        } else {
            // A linear texture over the surface pages reads them with the surface's pitch and writes the scanout's pitch.
            MTLTextureDescriptor *d = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatBGRA8Unorm width:frame.width
                                                                                       height:frame.height mipmapped:NO];
            d.storageMode = MTLStorageModeShared;
            d.usage = MTLTextureUsageShaderRead;
            if (frame.stride % [device_ minimumLinearTextureAlignmentForPixelFormat:MTLPixelFormatBGRA8Unorm]) {
                rowByRow = true;
                for (uint32_t y = 0; y < frame.height; ++y)
                    [blit copyFromBuffer:source sourceOffset:y * frame.stride toBuffer:target_ destinationOffset:y * scanout_.stride size:row];
            } else {
                // A linear texture is created per frame: the source import only lives for this offer/complete
                // window, so a texture kept across frames could read recycled pages. The 3-8 ms it costs in the
                // translated runtime requires a kernel-side lifetime guarantee, not a cache here.
                id<MTLTexture> texture = [source newTextureWithDescriptor:d offset:0 bytesPerRow:frame.stride];
                if (!texture) {[blit endEncoding]; return kNoResource;}
                [blit copyFromTexture:texture sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0, 0, 0)
                           sourceSize:MTLSizeMake(frame.width, frame.height, 1) toBuffer:target_ destinationOffset:0
                    destinationBytesPerRow:scanout_.stride destinationBytesPerImage:scanout_.stride * frame.height];
            }
        }
        [blit endEncoding];
        const uint64_t encoded = stageNow();
        [commands commit];
        const uint64_t committed = stageNow();
        [commands waitUntilCompleted];
        const uint64_t finished = stageNow();
        reportTiming(imported, encoded, committed, finished, rowByRow, frame);
        return commands.status == MTLCommandBufferStatusCompleted ? kOk : kGpuFailed;
    }
private:
    static uint64_t stageNow() { return clock_gettime_nsec_np(CLOCK_UPTIME_RAW) / 1000; }
    // Bounded: the first 8 frames plus one every 120, so a capture always has attribution without flooding the console.
    void reportTiming(uint64_t imported, uint64_t encoded, uint64_t committed, uint64_t finished, bool rowByRow, const Frame &frame) {
        static uint64_t frames;
        const uint64_t index = frames++;
        if (index >= 8 && (index % 120)) return;
        char text[240];
        snprintf(text, sizeof(text), "present #%llu import=%lluus encode=%lluus commit=%lluus wait=%lluus total=%lluus rows=%u copy=%s",
            (unsigned long long)index, (unsigned long long)(imported - stageStart), (unsigned long long)(encoded - imported),
            (unsigned long long)(committed - encoded), (unsigned long long)(finished - committed),
            (unsigned long long)(finished - stageStart), rowByRow ? frame.height : 1u,
            rowByRow ? "row" : (frame.stride == scanout_.stride ? "linear" : "texture"));
        if (sink_) sink_(text, 0);
        else fprintf(stderr, "GPU %s\n", text);
    }
    uint64_t stageStart = stageNow();
    Sink sink_ = nullptr;
    bool validScanout() const {
        const size_t page = (size_t)getpagesize();
        return scanout_.base && !((uintptr_t)scanout_.base & (page - 1)) && scanout_.bytes && !(scanout_.bytes & (page - 1)) &&
               scanout_.width && scanout_.height && scanout_.stride >= (size_t)scanout_.width * 4 &&
               scanout_.stride * scanout_.height <= scanout_.bytes;
    }
    id<MTLDevice> device_;
    Scanout scanout_;
    id<MTLCommandQueue> queue_;
    id<MTLBuffer> target_;
};

}  // namespace gpupresent
