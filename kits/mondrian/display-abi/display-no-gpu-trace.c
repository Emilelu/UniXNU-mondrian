/* SPDX-License-Identifier: MIT */
/* Stage-0 links the display component without the GPU addon. These are the
 * diagnostic hooks the component calls when the addon is absent; weak so the
 * real addon wins the link once it is part of the kernel. */
#include <stdint.h>

__attribute__((weak)) int native_gpu_trace_enabled(void) { return 0; }
__attribute__((weak)) void native_gpu_trace_record(uint32_t event, uint32_t pid,
                                                   const uint64_t *values, uint32_t count)
{ (void)event; (void)pid; (void)values; (void)count; }
__attribute__((weak)) uint32_t native_gpu_trace_snapshot(void *out, uint32_t bytes)
{ (void)out; (void)bytes; return 0; }
__attribute__((weak)) int native_adreno_fences(uint32_t *submitted, uint32_t *retired)
{ (void)submitted; (void)retired; return 0; }
__attribute__((weak)) int native_adreno_fences_detail(uint32_t *a, uint32_t *b, uint32_t *c)
{ (void)a; (void)b; (void)c; return 0; }
