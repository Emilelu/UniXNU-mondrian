// SPDX-License-Identifier: MIT
/* The scanout stage timing arithmetic, in one place and testable on the host.

 * Why this is a separate header: the frame report has to attribute a slow frame
 * to a stage the porting guide names (commit, submit, GPU complete), and the
 * first attempt at that arithmetic was wrong in two ways that both produced
 * plausible-looking numbers instead of an error:
 *
 *   1. `(uint64_t)(b.tv_nsec - a.tv_nsec)` when the difference is negative. Any
 *      span that crosses a whole second has b.tv_nsec < a.tv_nsec, so the cast
 *      turned ~17 ms into ~1.8e13 us. The report looked fine; the criterion
 *      comparing it against the outer `copy` number could never pass.
 *   2. Dividing the two fields separately. floor(seconds) + floor(nanoseconds)
 *      rounds a cross-second sub-microsecond span wrong by 1 us, which is small
 *      but means a test cannot pin the exact behaviour.
 *
 * Borrow from the seconds field before dividing, and keep the function free of
 * Metal/Darwin headers so `scripts/tests/test-scanout-timing.py` can compile and
 * execute it with the host compiler instead of only matching its text. */
#pragma once
#include <cstdint>
#include <ctime>

namespace pongscanout {

/* 0 means "the clock was not read". Callers pass a zeroed timespec only when they
 * want to skip a stage, so validity is separate from the elapsed value. */
inline bool stamped(const struct timespec &value)
{
    return value.tv_sec != 0 || value.tv_nsec != 0;
}

/* Microseconds elapsed from `from` to `to` on a monotonic clock. A negative span
 * (clock went backwards, or the caller swapped the arguments) reports 0 rather
 * than wrapping into a huge positive number. */
inline uint64_t elapsedUs(const struct timespec &from, const struct timespec &to)
{
    int64_t seconds = (int64_t)to.tv_sec - (int64_t)from.tv_sec;
    int64_t nanoseconds = (int64_t)to.tv_nsec - (int64_t)from.tv_nsec;
    if (nanoseconds < 0) {
        nanoseconds += 1000000000LL;
        seconds -= 1;
    }
    if (seconds < 0) return 0;
    return (uint64_t)seconds * 1000000ULL + (uint64_t)nanoseconds / 1000ULL;
}

/* Absolute monotonic time in microseconds, for a rate line that has to survive
 * the report's own formatting. */
inline uint64_t absoluteUs(const struct timespec &value)
{
    return (uint64_t)value.tv_sec * 1000000ULL + (uint64_t)value.tv_nsec / 1000ULL;
}

}  // namespace pongscanout
