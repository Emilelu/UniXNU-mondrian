// SYNTHETIC FIXTURE. Not the real header. Four lines of it, so that
// check-gpu27-flip-asserts.py has something to compare with the draft.
#pragma once
#include <stddef.h>

struct PongScanoutFrame {
    uint64_t sequence, address, bytes, stride;
    uint32_t width, height, format, token, evict, target;
};

