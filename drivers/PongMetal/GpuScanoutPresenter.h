// SPDX-License-Identifier: MIT
// GPU presentation: the GPU copies a finished BGRA frame (the compositor's IOSurface pages) into the firmware scanout memory. Both are
// imported without a copy (newBufferWithBytesNoCopy: pinned by the kernel and mapped into the GPU's 4 KiB context), the copy is a blit on
// the GPU's queue, and the call returns after the GPU retired it. No CPU touches a pixel; there is no staging copy and no software fallback
// here. Used through the public Metal API, on any device (the native frontend on the tablet, the Mac's device for the host check).
#pragma once
#import <Metal/Metal.h>
#include <unistd.h>
#include <stdint.h>
#include <string.h>
#include "PongScanoutTiming.h"

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
    Presenter(id<MTLDevice> device, const Scanout &scanout) : device_(device), scanout_(scanout) {
        queue_ = [device newCommandQueue];
        if (!validScanout() || !queue_) return;
        target_ = [device newBufferWithBytesNoCopy:scanout.base length:scanout.bytes options:MTLResourceStorageModeShared deallocator:nil];
    }
    bool ready() const { return target_ != nil; }
    // One frame: imports the source pages, encodes the GPU copy, commits, waits for the GPU. Rows are copied as whole rows of width*4 bytes.
    Result present(const Frame &frame) {
        if (!ready()) return kBadScanout;
        const size_t page = (size_t)getpagesize(), row = (size_t)frame.width * 4;
        if (!frame.base || ((uintptr_t)frame.base & (page - 1)) || !frame.bytes || (frame.bytes & (page - 1)) ||
            frame.width != scanout_.width || frame.height != scanout_.height || frame.stride < row ||
            (size_t)frame.height > frame.bytes / frame.stride || frame.stride * (frame.height - 1) + row > frame.bytes) return kBadFrame;
        /* Import the source pages for THIS frame and drop the import when this call returns.
         * A previous version kept the last import and reused it when the address and length
         * matched. That is not safe: the kernel releases the frame's IOMemoryMap in
         * PongAdrenoScanout.cpp right after the copy retires, so a cached import would point
         * at a mapping that is already gone, and the GPU would read pages nobody owns. There
         * is no way to prove the same virtual address means the same live pages, so the
         * import is measured instead of cached: `imports` must equal the number of frames,
         * and `import=` is the share of the frame that the mapping itself costs. */
        struct timespec i0 = {}, i1 = {};
        clock_gettime(CLOCK_MONOTONIC, &i0);
        id<MTLBuffer> source = [device_ newBufferWithBytesNoCopy:(void *)frame.base length:frame.bytes
                                                         options:MTLResourceStorageModeShared deallocator:nil];
        clock_gettime(CLOCK_MONOTONIC, &i1);
        lastImportUs_ = pongscanout::elapsedUs(i0, i1);
        ++imports_;
        if (!source) return kNoResource;
        /* The official porting guide splits a frame into commit, submit and GPU complete. Measure
         * all three so a 16.8 ms copy can be attributed instead of guessed. */
        struct timespec e0 = {}, e1 = {}, e2 = {}, e3 = {};
        clock_gettime(CLOCK_MONOTONIC, &e0);
        id<MTLCommandBuffer> commands = [queue_ commandBuffer];
        id<MTLBlitCommandEncoder> blit = commands ? [commands blitCommandEncoder] : nil;
        if (!blit) return kNoResource;
        /* Three shapes are possible and the report names the one that ran. A 2026-11-18 flight
         * replaced the linear texture with 3,200 copy commands: `encode` went from 389 us to
         * 15,040 us (+14.6 ms) while `submit` stayed at 11.5 ms to within 5 us, so removing the
         * per-frame image made each frame slower and the commit cost was never the image. The
         * texture is therefore kept for a pitch change, with the row loop only as the fallback a
         * stride the device cannot express as a linear texture forces. */
        const bool singleRun = frame.stride == scanout_.stride;
        const char *shape = "single run";
        if (singleRun) {
            // Equal pitch: the rows are one contiguous run.
            [blit copyFromBuffer:source sourceOffset:0 toBuffer:target_ destinationOffset:0 size:frame.stride * (frame.height - 1) + row];
        } else {
            /* A single pitched buffer copy would be the obvious answer - one command carrying
             * sourceBytesPerRow and destinationBytesPerRow - and Vulkan has no such call, so it
             * would be emulated as an image round trip anyway, which is what the texture below
             * already is. It is also not reachable from here: NBBlitEncoder implements
             * copyFromBuffer:toBuffer: and the texture paths only, so the selector would raise
             * and take backboardd with it. The 1.9 ms the 2026-11-19 control measured was an
             * UNPITCHED copy; the only ways to get it are to remove the pitch change (own the
             * scanout buffer at the surface's pitch, which needs DPU programming to scan out) or
             * to stop copying at all. Recorded in P-243 so nobody re-adds this branch.
             * A linear texture over the surface pages reads them with the surface's pitch and writes the scanout's pitch.
            MTLTextureDescriptor *d = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatBGRA8Unorm width:frame.width
                                                                                       height:frame.height mipmapped:NO];
            d.storageMode = MTLStorageModeShared;
            d.usage = MTLTextureUsageShaderRead;
            if (frame.stride % [device_ minimumLinearTextureAlignmentForPixelFormat:MTLPixelFormatBGRA8Unorm]) {
                shape = "per row";
                for (uint32_t y = 0; y < frame.height; ++y)
                    [blit copyFromBuffer:source sourceOffset:size_t(y) * frame.stride toBuffer:target_
                         destinationOffset:size_t(y) * scanout_.stride size:row];
            } else {
                shape = "texture untile";
                id<MTLTexture> texture = [source newTextureWithDescriptor:d offset:0 bytesPerRow:frame.stride];
                if (!texture) {[blit endEncoding]; return kNoResource;}
                [blit copyFromTexture:texture sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0, 0, 0)
                           sourceSize:MTLSizeMake(frame.width, frame.height, 1) toBuffer:target_ destinationOffset:0
                    destinationBytesPerRow:scanout_.stride destinationBytesPerImage:scanout_.stride * frame.height];
            }
        }
        lastShape_ = shape;
        lastSourceStride_ = frame.stride;
        lastRows_ = frame.height;
        [blit endEncoding];
        clock_gettime(CLOCK_MONOTONIC, &e1);
        [commands commit];
        clock_gettime(CLOCK_MONOTONIC, &e2);
        [commands waitUntilCompleted];
        clock_gettime(CLOCK_MONOTONIC, &e3);
        lastEncodeUs_ = pongscanout::elapsedUs(e0, e1);
        lastSubmitUs_ = pongscanout::elapsedUs(e1, e2);
        lastWaitUs_ = pongscanout::elapsedUs(e2, e3);
        return commands.status == MTLCommandBufferStatusCompleted ? kOk : kGpuFailed;
    }
    /* A control for the 2026-11-19 finding: a commit that carries nothing but the scanout
     * blit takes 5.3-22.8 ms, and the same figure comes from the kernel side, the client
     * side and the compositor. That leaves three candidates - the destination (the firmware
     * framebuffer), Turnip's copy implementation, or the bandwidth itself - and nothing
     * measured so far separates them. This probe copies the same bytes two more ways in one
     * flight: the surface pages into a device buffer the GPU allocated, and that device buffer
     * into the firmware framebuffer. Same call shape, same byte count, different destination.
     * If the device-buffer copy is fast and the framebuffer copy is slow, the destination is
     * the cost; if both are slow, the copy implementation is. It runs at most once, only when
     * pong_gpu_blit_probe=1 asked for it, and never on the frame path. */
    bool runBlitProbe(const Frame &frame) {
        if (probeRan_ || !ready() || !frame.base || !frame.bytes) return false;
        probeRan_ = true;
        /* Both copies move the same byte count, and it must fit the smaller of the two
         * extents. The first version used the source extent, frame.stride*(h-1)+row, which
         * with a 5888 source pitch and a 5760 scanout pitch is 18,841,472 bytes against an
         * 18,432,000 byte framebuffer - so the guard refused the whole control and the first
         * flight reported nothing. The size difference this control exists to explain is
         * exactly what stopped it, so the count is clamped here instead of guarded later. */
        const size_t bytes = frame.bytes < scanout_.bytes ? frame.bytes : scanout_.bytes;
        if (!bytes) return false;
        probe_ = [device_ newBufferWithLength:scanout_.bytes options:MTLResourceStorageModeShared];
        if (!probe_) return false;
        id<MTLBuffer> source = [device_ newBufferWithBytesNoCopy:(void *)frame.base length:frame.bytes
                                                        options:MTLResourceStorageModeShared deallocator:nil];
        if (!source) return false;
        probeBytes_ = bytes;
        probeSourceToDeviceUs_ = timedCopy(source, probe_, bytes);
        probeDeviceToScanoutUs_ = timedCopy(probe_, target_, bytes);
        return probeSourceToDeviceUs_ != 0;
    }
    bool probeRan() const { return probeRan_; }
    size_t probeBytes() const { return probeBytes_; }
    uint64_t probeSourceToDeviceUs() const { return probeSourceToDeviceUs_; }
    uint64_t probeDeviceToScanoutUs() const { return probeDeviceToScanoutUs_; }
    /* How many times the source pages were imported: one per presented frame, so a
     * flight can prove no import survived into the next frame. */
    uint64_t imports() const { return imports_; }
    /* How long the last import took, in microseconds. */
    uint64_t importMicroseconds() const { return lastImportUs_; }
    uint64_t encodeMicroseconds() const { return lastEncodeUs_; }
    uint64_t submitMicroseconds() const { return lastSubmitUs_; }
    uint64_t waitMicroseconds() const { return lastWaitUs_; }
    /* Which copy shape the last frame used: one contiguous run, a linear texture that reads the
     * surface pitch and writes the scanout pitch, or the row loop that a stride the device cannot
     * express as a linear texture forces. The shape was silent for two flights and hid a 14.6 ms
     * regression, so it is named in the report. */
    const char *copyShape() const { return lastShape_; }
    size_t sourceStride() const { return lastSourceStride_; }
    size_t scanoutStride() const { return scanout_.stride; }
    uint32_t rows() const { return lastRows_; }
private:
    /* Commit one identical-shape copy and return the GPU time, in microseconds, from commit
     * to complete. A zero return means the copy failed, which the report prints as a zero. */
    uint64_t timedCopy(id<MTLBuffer> from, id<MTLBuffer> to, size_t bytes) {
        id<MTLCommandBuffer> commands = [queue_ commandBuffer];
        id<MTLBlitCommandEncoder> blit = commands ? [commands blitCommandEncoder] : nil;
        if (!blit) return 0;
        [blit copyFromBuffer:from sourceOffset:0 toBuffer:to destinationOffset:0 size:bytes];
        [blit endEncoding];
        struct timespec a = {}, b = {};
        clock_gettime(CLOCK_MONOTONIC, &a);
        [commands commit];
        [commands waitUntilCompleted];
        clock_gettime(CLOCK_MONOTONIC, &b);
        return commands.status == MTLCommandBufferStatusCompleted ? pongscanout::elapsedUs(a, b) : 0;
    }
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
    uint64_t imports_ = 0;
    uint64_t lastImportUs_ = 0;
    uint64_t lastEncodeUs_ = 0;
    uint64_t lastSubmitUs_ = 0;
    uint64_t lastWaitUs_ = 0;
    const char *lastShape_ = "none";
    size_t lastSourceStride_ = 0;
    uint32_t lastRows_ = 0;
    id<MTLBuffer> probe_ = nil;
    bool probeRan_ = false;
    size_t probeBytes_ = 0;
    uint64_t probeSourceToDeviceUs_ = 0;
    uint64_t probeDeviceToScanoutUs_ = 0;
};

}  // namespace gpupresent
