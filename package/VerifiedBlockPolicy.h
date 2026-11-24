// SPDX-License-Identifier: BSD-2-Clause-Patent
// Source-storage build view: the package defines these objects itself, so the
// declarations must not be const (the driver-local header keeps the 16-line view).
#ifndef NATIVE_VERIFIED_BLOCK_POLICY_H
#define NATIVE_VERIFIED_BLOCK_POLICY_H
#include <stdint.h>
struct NativeVerifiedBlockPolicy {
  const uint8_t *manifest;
  uint64_t manifestBytes;
};
static_assert(sizeof(NativeVerifiedBlockPolicy) == 16 && alignof(NativeVerifiedBlockPolicy) == 8);
extern "C" {
extern NativeVerifiedBlockPolicy verified_root_policies[];
extern uint64_t verified_root_policy_count;
}
#endif
