// SPDX-License-Identifier: BSD-2-Clause-Patent
#pragma once
// Policy selection and table authentication for NativeUfs.
// The window parameter is duck-typed: it must provide name[32], offset and size.
#include <string.h>
#include "verified_root.h"
#include "VerifiedBlockPolicy.h"

struct RootPolicySelection {
  const uint8_t *manifest;
  uint64_t manifestBytes;
  uint64_t imageBytes;
  uint64_t tableBytes;      // header-only policies only; zero for a full envelope
  bool headerOnly;
};

static uint64_t rootPolicyLe64 (const uint8_t *p)
{
  return uint64_t (p[0]) | (uint64_t (p[1]) << 8) | (uint64_t (p[2]) << 16) |
         (uint64_t (p[3]) << 24) | (uint64_t (p[4]) << 32) | (uint64_t (p[5]) << 40) |
         (uint64_t (p[6]) << 48) | (uint64_t (p[7]) << 56);
}

// Pick the one policy whose signed image size is the window capacity. Two matches are refused:
// publishing one of two possible roots is worse than refusing to publish either.
static bool rootPolicySelect (const NativeVerifiedBlockPolicy *policies, uint64_t count,
                              uint64_t imageBytes, RootPolicySelection *out)
{
  if (!policies || !count || count > 16 || !out || !imageBytes) return false;
  const uint8_t *manifest = nullptr;
  uint64_t manifestBytes = 0;
  for (uint64_t index = 0; index < count; ++index) {
    const NativeVerifiedBlockPolicy &policy = policies[index];
    if (!policy.manifest || policy.manifestBytes < VR_HEADER_BYTES + VR_SIGNATURE_BYTES) return false;
    if (rootPolicyLe64 (policy.manifest + 24) != imageBytes) continue;
    if (manifest) return false;
    manifest = policy.manifest;
    manifestBytes = policy.manifestBytes;
  }
  if (!manifest) return false;
  const bool headerOnly = manifestBytes == VR_HEADER_BYTES + VR_SIGNATURE_BYTES;
  uint64_t tableBytes = 0;
  if (headerOnly) {
    const uint64_t blocks = rootPolicyLe64 (manifest + 32);
    if (!blocks || blocks > (UINT64_MAX - VR_HEADER_BYTES - VR_SIGNATURE_BYTES) / 32) return false;
    tableBytes = blocks * 32;
  }
  *out = {manifest, manifestBytes, imageBytes, tableBytes, headerOnly};
  return true;
}

// The hash table of a header-only policy is the LUN 0 object "<window>.vroot", whose size is exact
// (not rounded) and whose offset is 4 KiB aligned relative to the userdata partition.
// Window is duck-typed: it must provide name[32], offset and size (RootLayout::RootWindow does).
template <typename Window>
static bool rootPolicyTableLba (const Window *windows, uint32_t count, uint64_t userdataFirst,
                                const char *window, uint64_t tableBytes, uint64_t *lba)
{
  if (!windows || !window || !lba || !tableBytes || userdataFirst > UINT64_MAX / VR_BLOCK_BYTES) return false;
  char name[32];
  const size_t windowLength = strlen (window);
  if (!windowLength || windowLength + 7 > sizeof (name)) return false;
  memcpy (name, window, windowLength);
  memcpy (name + windowLength, ".vroot", 7);
  for (uint32_t index = 0; index < count; ++index) {
    const Window &object = windows[index];
    if (strcmp (object.name, name)) continue;
    if (object.size != tableBytes || !object.offset || (object.offset & 4095) ||
        object.offset > UINT64_MAX - userdataFirst * 4096ULL) return false;
    const uint64_t absolute = userdataFirst * 4096ULL + object.offset;
    if (absolute & 4095) return false;
    *lba = absolute / 4096ULL;
    return true;
  }
  return false;
}

// Read exactly tableBytes from consecutive 4 KiB blocks into a caller-owned buffer.
template <typename Ops>
static bool rootPolicyReadTable (Ops &ops, uint64_t firstLba, uint8_t *table, uint64_t tableBytes)
{
  if (!table || !tableBytes) return false;
  for (uint64_t done = 0; done < tableBytes; done += VR_BLOCK_BYTES) {
    uint8_t page[VR_BLOCK_BYTES];
    if (!ops.read4k (firstLba + done / VR_BLOCK_BYTES, 1, page)) return false;
    const uint64_t take = tableBytes - done < VR_BLOCK_BYTES ? tableBytes - done : VR_BLOCK_BYTES;
    memcpy (table + done, page, static_cast<size_t> (take));
  }
  return true;
}

// Authenticate a policy and, for a header-only policy, read and authenticate its table object.
// On success view->hashes points into \`table\`, which must stay alive as long as the view is used.
template <typename Ops, typename Window>
static int rootPolicyOpen (const RootPolicySelection &selection, const Window *windows, uint32_t windowCount,
                           uint64_t userdataFirst, const char *window,
                           const uint8_t key[VR_KEY_BYTES], const struct vr_crypto *crypto, Ops &ops,
                           uint8_t *table, uint64_t tableCapacity, struct vr_view *view)
{
  if (!view) return VR_FORMAT;
  *view = {};
  if (!selection.manifest || !crypto || !key) return VR_FORMAT;
  if (!selection.headerOnly) {
    const int status = vr_open (selection.manifest, selection.manifestBytes, key, 1, crypto, view);
    if (status != VR_OK) return status;
    if (view->image_bytes != selection.imageBytes) { *view = {}; return VR_FORMAT; }
    return VR_OK;
  }
  int status = vr_open_header (selection.manifest, selection.manifestBytes, key, 1, crypto, view);
  if (status != VR_OK) return status;
  if (view->image_bytes != selection.imageBytes || view->block_count > UINT64_MAX / 32) {
    *view = {};
    return VR_FORMAT;
  }
  const uint64_t tableBytes = view->block_count * 32;
  if (tableBytes != selection.tableBytes || !table || tableCapacity < tableBytes) {
    *view = {};
    return VR_FORMAT;
  }
  uint64_t lba = 0;
  if (!rootPolicyTableLba (windows, windowCount, userdataFirst, window, tableBytes, &lba) ||
      !rootPolicyReadTable (ops, lba, table, tableBytes)) {
    *view = {};
    return VR_FORMAT;
  }
  uint8_t digest[32];
  if (!crypto->sha256 (table, static_cast<size_t> (tableBytes), digest) ||
      memcmp (digest, selection.manifest + 88, 32)) {
    *view = {};
    return VR_HASH_TABLE;
  }
  view->hashes = table;
  return VR_OK;
}
