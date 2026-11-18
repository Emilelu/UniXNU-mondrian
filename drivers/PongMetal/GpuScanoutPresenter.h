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
    // One frame: encodes the GPU copy, commits, waits for the GPU. Rows are copied as whole rows of width*4 bytes.
    Result present(const Frame &frame) {
        if (!ready()) return kBadScanout;
        const size_t page = (size_t)getpagesize(), row = (size_t)frame.width * 4;
        if (!frame.base || ((uintptr_t)frame.base & (page - 1)) || !frame.bytes || (frame.bytes & (page - 1)) ||
            frame.width != scanout_.width || frame.height != scanout_.height || frame.stride < row ||
            (size_t)frame.height > frame.bytes / frame.stride || frame.stride * (frame.height - 1) + row > frame.bytes) return kBadFrame;
        /* The compositor hands back the same surface pages frame after frame, and importing them
         * is not cheap: the kernel maps every page into the GPU's context again, which measured
         * 16.8 ms of a 17 ms copy. Keep the last import and reuse it while the pages are the same. */
        if (!(imported_ && importedBase_ == frame.base && importedBytes_ == frame.bytes)) {
            struct timespec before={},after={};clock_gettime(CLOCK_MONOTONIC,&before);
            id<MTLBuffer> fresh = [device_ newBufferWithBytesNoCopy:(void *)frame.base length:frame.bytes options:MTLResourceStorageModeShared deallocator:nil];
            clock_gettime(CLOCK_MONOTONIC,&after);
            lastImportUs_=(uint64_t)(after.tv_sec-before.tv_sec)*1000000u+(uint64_t)(after.tv_nsec-before.tv_nsec)/1000u;
            if (!fresh) return kNoResource;
            /* ARC owns the import: assigning a new buffer to the strong ivar releases the old one. */
            imported_ = fresh;
            importedBase_ = frame.base;
            importedBytes_ = frame.bytes;
            ++imports_;
        } else {
            lastImportUs_=0;
            ++reuses_;
        }
        id<MTLBuffer> source = imported_;
        id<MTLCommandBuffer> commands = [queue_ commandBuffer];
        id<MTLBlitCommandEncoder> blit = commands ? [commands blitCommandEncoder] : nil;
        if (!blit) return kNoResource;
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
                for (uint32_t y = 0; y < frame.height; ++y)
                    [blit copyFromBuffer:source sourceOffset:y * frame.stride toBuffer:target_ destinationOffset:y * scanout_.stride size:row];
            } else {
                id<MTLTexture> texture = [source newTextureWithDescriptor:d offset:0 bytesPerRow:frame.stride];
                if (!texture) {[blit endEncoding]; return kNoResource;}
                [blit copyFromTexture:texture sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0, 0, 0)
                           sourceSize:MTLSizeMake(frame.width, frame.height, 1) toBuffer:target_ destinationOffset:0
                    destinationBytesPerRow:scanout_.stride destinationBytesPerImage:scanout_.stride * frame.height];
            }
        }
        [blit endEncoding];
        [commands commit];
        [commands waitUntilCompleted];
        return commands.status == MTLCommandBufferStatusCompleted ? kOk : kGpuFailed;
    }
private:
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
    id<MTLBuffer> imported_ = nil;   /* the last imported source, reused while the pages are the same */
    const void *importedBase_ = nullptr;
    size_t importedBytes_ = 0;
public:
    /* How often the source import was rebuilt (a new mapping) versus reused (no mapping at all). */
    uint64_t imports() const { return imports_; }
    uint64_t reuses() const { return reuses_; }
    /* How long the last import took, in microseconds: 0 when the previous import was reused. */
    uint64_t importMicroseconds() const { return lastImportUs_; }
private:
    uint64_t imports_ = 0;
    uint64_t reuses_ = 0;
    uint64_t lastImportUs_ = 0;
};

}  // namespace gpupresent
