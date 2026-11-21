// SYNTHETIC FIXTURE. Not the real header. Four lines of it, so that
// check-gpu27-flip-asserts.py has something to compare with the draft.
#pragma once
#include <stddef.h>

struct PongScanoutFrame {
    uint64_t sequence, address, bytes, stride;
    uint32_t width, height, format, token, evict, target;
};

static_assert(sizeof(PongScanoutFrame)==56,"v2 frame");
static_assert(offsetof(PongScanoutFrame,token)==44,"v2 token sits where reserved was");
static_assert(offsetof(PongScanoutFrame,evict)==48,"v2 evict");
static_assert(offsetof(PongScanoutFrame,target)==52,"v2 target");
