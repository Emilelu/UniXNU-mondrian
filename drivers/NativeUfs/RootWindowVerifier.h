// SPDX-License-Identifier: BSD-2-Clause-Patent
#pragma once
// Per-window verified-root state: a full signed envelope keeps its whole table, a header-only
// policy keeps only page hashes and fills a bounded page cache on demand. The adapter is
// host-testable: the caller owns every buffer and supplies the transport through Ops.
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#if defined(__APPLE__)
#include <libkern/crypto/sha2.h>
#else
#ifndef OPENSSL_SUPPRESS_DEPRECATED
#define OPENSSL_SUPPRESS_DEPRECATED
#endif
#include <openssl/sha.h>
#endif
#include "verified_root.h"
#include "VerifiedTableCache.h"
#include "RootPolicyTable.h"

struct RootWindowVerifier {
  struct vr_view view;
  VrootTable table;
  VrootTableCache cache;
  bool ready;
};

// All buffers are caller-owned and must outlive the verifier. They are only used for a
// header-only policy; a full envelope ignores them.
struct RootWindowVerifierMemory {
  uint8_t *header;             // VR_BLOCK_BYTES bytes: signed header + key share one page
  size_t headerBytes;
  uint8_t *pageHashes;         // ceil(tableBytes / 4096) * 32
  size_t pageHashBytes;
  uint32_t *where;             // one entry per table page
  size_t whereCount;
  uint8_t *scratch;            // VR_BLOCK_BYTES, used only while the table is hashed at set-up
  size_t scratchBytes;
  VrootCacheEntry *entries;
  uint8_t *cachePages;         // cacheCount * VR_BLOCK_BYTES
  uint32_t cacheCount;
};

static inline uint64_t rootWindowTableBytes (const struct vr_view &view)
{
  return view.block_count * 32;
}

static inline uint64_t rootWindowTablePages (uint64_t tableBytes)
{
  return (tableBytes + VR_BLOCK_BYTES - 1) / VR_BLOCK_BYTES;
}

// Authenticate the policy, then (header-only) read the table object once, hash it page by page
// into the caller's arrays and check the whole digest against the signed header. The table
// object itself is released: later block checks go through the cache.
template <typename Ops, typename Window>
static bool rootWindowVerifierConfigure (RootWindowVerifier &verifier, const RootWindowVerifierMemory &memory,
                                         const RootPolicySelection &selection, const Window *windows,
                                         uint32_t windowCount, uint64_t userdataFirst, const char *window,
                                         const uint8_t key[VR_KEY_BYTES], const struct vr_crypto *crypto, Ops &ops)
{
  verifier = {};
  if (!selection.manifest || !crypto || !key) return false;

  if (!selection.headerOnly) {
    const int status = vr_open (selection.manifest, selection.manifestBytes, key, 1, crypto, &verifier.view);
    if (status != VR_OK || verifier.view.image_bytes != selection.imageBytes) {
      verifier = {};
      return false;
    }
    verifier.ready = true;
    return true;
  }

  if (!memory.header || memory.headerBytes < VR_BLOCK_BYTES || !memory.pageHashes ||
      !memory.where || !memory.scratch || memory.scratchBytes < VR_BLOCK_BYTES ||
      !memory.entries || !memory.cachePages || !memory.cacheCount) return false;

  memcpy (memory.header, selection.manifest, VR_HEADER_BYTES + VR_SIGNATURE_BYTES);
  memcpy (memory.header + VR_BLOCK_BYTES - VR_KEY_BYTES, key, VR_KEY_BYTES);
  int status = vr_open_header (memory.header, VR_HEADER_BYTES + VR_SIGNATURE_BYTES, key, 1, crypto, &verifier.view);
  if (status != VR_OK || verifier.view.image_bytes != selection.imageBytes) {
    verifier = {};
    return false;
  }
  const uint64_t tableBytes = rootWindowTableBytes (verifier.view);
  if (tableBytes != selection.tableBytes) {
    verifier = {};
    return false;
  }
  const uint64_t pages = rootWindowTablePages (tableBytes);
  if (memory.pageHashBytes < pages * 32 || memory.whereCount < pages) {
    verifier = {};
    return false;
  }

  uint64_t lba = 0;
  if (!rootPolicyTableLba (windows, windowCount, userdataFirst, window, tableBytes, &lba)) {
    verifier = {};
    return false;
  }

  VrootTable readTable = {};
  readTable.firstLba = lba;
  SHA256_CTX whole;
  SHA256_Init (&whole);
  for (uint64_t page = 0; page < pages; ++page) {
    if (!ops.readPage (readTable, page, memory.scratch)) {
      verifier = {};
      return false;
    }
    const uint64_t left = tableBytes - page * VR_BLOCK_BYTES;
    const size_t take = left < VR_BLOCK_BYTES ? static_cast<size_t> (left) : VR_BLOCK_BYTES;
    SHA256_Update (&whole, memory.scratch, take);
    if (!crypto->sha256 (memory.scratch, take, memory.pageHashes + page * 32)) {
      verifier = {};
      return false;
    }
  }
  uint8_t digest[32];
  SHA256_Final (digest, &whole);
  if (memcmp (digest, memory.header + 88, 32)) {
    verifier = {};
    return false;
  }

  memset (memory.where, 0, pages * sizeof (uint32_t));
  memset (memory.entries, 0, memory.cacheCount * sizeof (VrootCacheEntry));
  verifier.table.pageHashes = memory.pageHashes;
  verifier.table.where = memory.where;
  verifier.table.tableBytes = tableBytes;
  verifier.table.pages = pages;
  verifier.table.firstLba = lba;
  verifier.cache.pages = memory.cachePages;
  verifier.cache.entries = memory.entries;
  verifier.cache.count = memory.cacheCount;
  verifier.ready = true;
  return true;
}

// Verify one image block. A full envelope checks its in-memory table; a header-only policy
// fetches the block's table entry through the page cache.
template <typename Ops>
static int rootWindowVerifierVerify (RootWindowVerifier &verifier, Ops &ops, uint64_t block,
                                     const void *data, size_t length, const struct vr_crypto *crypto)
{
  if (!verifier.ready) return VR_BLOCK;
  if (!verifier.view.hashes)
    return vrootVerifyBlock (verifier.cache, ops, verifier.table, verifier.view, block, data, length, crypto);
  return vr_verify_block (&verifier.view, block, data, length, crypto);
}

template <typename Ops>
static void rootWindowVerifierDrop (RootWindowVerifier &verifier, Ops &ops)
{
  if (verifier.ready && !verifier.view.hashes) vrootTableDrop (verifier.cache, ops, verifier.table);
  verifier = {};
}
