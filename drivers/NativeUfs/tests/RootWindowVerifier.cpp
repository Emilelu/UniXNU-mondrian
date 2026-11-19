// SPDX-License-Identifier: BSD-2-Clause-Patent
// Host checks for the per-window verifier: full-envelope and header-only paths.
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>
#include "../RootWindowVerifier.h"

extern "C" const struct vr_crypto vr_openssl_crypto;

struct Window {
  char name[32];
  uint64_t offset, size;
};

struct Ops {
  const std::vector<uint8_t> &disk;
  unsigned reads = 0;
  void lock () {}
  void unlock () {}
  void sleep (void *) {}
  void wakeup (void *) {}
  bool readPage (const VrootTable &object, uint64_t page, void *dst) {
    const uint64_t at = (object.firstLba + page) * VR_BLOCK_BYTES;
    if (at + VR_BLOCK_BYTES > disk.size ()) return false;
    std::memcpy (dst, disk.data () + at, VR_BLOCK_BYTES);
    ++reads;
    return true;
  }
  bool sha256 (const void *data, size_t bytes, uint8_t out[32]) {
    return vr_openssl_crypto.sha256 (data, bytes, out) != 0;
  }
};

static std::vector<uint8_t> makeDisk (const std::vector<uint8_t> &table, uint64_t firstLba, uint64_t pages) {
  std::vector<uint8_t> disk ((firstLba + pages) * VR_BLOCK_BYTES, 0xee);
  std::memcpy (disk.data () + firstLba * VR_BLOCK_BYTES, table.data (), table.size ());
  return disk;
}

static std::vector<uint8_t> readFile (const std::string &path) {
  std::ifstream stream (path, std::ios::binary);
  assert (stream);
  return std::vector<uint8_t> (std::istreambuf_iterator<char> (stream), {});
}

int main (int argc, char **argv) {
  assert (argc == 3);
  const std::string dir = argv[1];
  const std::string largeDir = argv[2];
  const auto image = readFile (dir + "/image.bin");
  const auto manifest = readFile (dir + "/manifest.bin");
  const auto header = readFile (dir + "/manifest.header.bin");
  const auto key = readFile (dir + "/trusted-key.bin");
  const auto table = readFile (dir + "/table.bin");
  assert (key.size () == VR_KEY_BYTES);
  assert (header.size () == VR_HEADER_BYTES + VR_SIGNATURE_BYTES);
  const uint64_t imageBytes = image.size ();
  const uint64_t tableBytes = table.size ();
  assert (rootWindowTablePages (0) == 0);
  assert (rootWindowTablePages (1) == 1);
  assert (rootWindowTablePages (VR_BLOCK_BYTES) == 1);
  assert (rootWindowTablePages (UINT64_MAX) == UINT64_MAX / VR_BLOCK_BYTES + 1);
  const uint64_t tablePages = (tableBytes + VR_BLOCK_BYTES - 1) / VR_BLOCK_BYTES;
  const uint64_t tableLba = (2 * VR_BLOCK_BYTES + 4096) / VR_BLOCK_BYTES;
  const auto disk = makeDisk (table, tableLba, tablePages);

  Window windows[2] = {};
  std::strcpy (windows[0].name, "OS");
  windows[0].offset = 0;
  windows[0].size = imageBytes;
  std::strcpy (windows[1].name, "OS.vroot");
  windows[1].offset = 4096;
  windows[1].size = tableBytes;
  constexpr uint64_t userdataFirst = 2;

  NativeVerifiedBlockPolicy full[1] = {{manifest.data (), manifest.size ()}};
  NativeVerifiedBlockPolicy cached[1] = {{header.data (), header.size ()}};
  RootPolicySelection fullSelection {}, cachedSelection {};
  assert (rootPolicySelect (full, 1, imageBytes, &fullSelection));
  assert (rootPolicySelect (cached, 1, imageBytes, &cachedSelection));

  // A full envelope verifies from the table embedded in the signed object.
  {
    RootWindowVerifier verifier {};
    RootWindowVerifierMemory memory {};
    std::vector<uint8_t> unused;
    Ops ops {unused};
    assert (rootWindowVerifierConfigure (verifier, memory, fullSelection, windows, 2, userdataFirst,
                                         "OS", key.data (), &vr_openssl_crypto, ops));
    assert (verifier.ready && verifier.view.hashes == manifest.data () + header.size ());
    for (uint64_t block = 0; block < verifier.view.block_count; ++block) {
      const uint64_t at = block * VR_BLOCK_BYTES;
      const size_t length = static_cast<size_t> (imageBytes - at < VR_BLOCK_BYTES ? imageBytes - at : VR_BLOCK_BYTES);
      assert (rootWindowVerifierVerify (verifier, ops, block, image.data () + at, length, &vr_openssl_crypto) == VR_OK);
    }
    assert (rootWindowVerifierVerify (verifier, ops, 0, image.data (), 1, &vr_openssl_crypto) == VR_BLOCK);
    rootWindowVerifierDrop (verifier, ops);
    assert (!verifier.ready);
    assert (ops.reads == 0);
  }

  // A header-only policy reads the table once, keeps only page hashes and serves blocks from the cache.
  {
    std::vector<uint8_t> headerStorage (VR_BLOCK_BYTES);
    std::vector<uint8_t> pageHashes (tablePages * 32);
    std::vector<uint32_t> where (tablePages);
    std::vector<uint8_t> scratch (VR_BLOCK_BYTES);
    std::vector<VrootCacheEntry> entries (2);
    std::vector<uint8_t> cachePages (2 * VR_BLOCK_BYTES);
    RootWindowVerifierMemory memory {headerStorage.data (), headerStorage.size (), pageHashes.data (),
                                     pageHashes.size (), where.data (), where.size (), scratch.data (),
                                     scratch.size (), entries.data (), cachePages.data (), 2};
    RootWindowVerifier verifier {};
    Ops ops {disk};
    assert (rootWindowVerifierConfigure (verifier, memory, cachedSelection, windows, 2, userdataFirst,
                                         "OS", key.data (), &vr_openssl_crypto, ops));
    assert (verifier.ready && !verifier.view.hashes);
    assert (ops.reads == tablePages);
    assert (verifier.cache.stats.misses == 0);
    for (uint64_t block = 0; block < verifier.view.block_count; ++block) {
      const uint64_t at = block * VR_BLOCK_BYTES;
      const size_t length = static_cast<size_t> (imageBytes - at < VR_BLOCK_BYTES ? imageBytes - at : VR_BLOCK_BYTES);
      assert (rootWindowVerifierVerify (verifier, ops, block, image.data () + at, length, &vr_openssl_crypto) == VR_OK);
    }
    assert (verifier.cache.stats.misses == 1 && verifier.cache.stats.hits == 3 && verifier.cache.stats.reads == 1);
    std::vector<uint8_t> bad = image;
    bad[VR_BLOCK_BYTES] ^= 1;
    assert (rootWindowVerifierVerify (verifier, ops, 1, bad.data () + VR_BLOCK_BYTES, VR_BLOCK_BYTES,
                                      &vr_openssl_crypto) == VR_BLOCK);
    rootWindowVerifierDrop (verifier, ops);
    assert (!verifier.ready);
  }

  // A header-only policy with a corrupted table object is refused before any block is served.
  {
    std::vector<uint8_t> headerStorage (VR_BLOCK_BYTES);
    std::vector<uint8_t> pageHashes (tablePages * 32);
    std::vector<uint32_t> where (tablePages);
    std::vector<uint8_t> scratch (VR_BLOCK_BYTES);
    std::vector<VrootCacheEntry> entries (2);
    std::vector<uint8_t> cachePages (2 * VR_BLOCK_BYTES);
    RootWindowVerifierMemory memory {headerStorage.data (), headerStorage.size (), pageHashes.data (),
                                     pageHashes.size (), where.data (), where.size (), scratch.data (),
                                     scratch.size (), entries.data (), cachePages.data (), 2};
    std::vector<uint8_t> badTable = table;
    badTable[0] ^= 1;
    const auto badDisk = makeDisk (badTable, tableLba, tablePages);
    RootWindowVerifier verifier {};
    Ops ops {badDisk};
    assert (!rootWindowVerifierConfigure (verifier, memory, cachedSelection, windows, 2, userdataFirst,
                                          "OS", key.data (), &vr_openssl_crypto, ops));
    assert (!verifier.ready);
  }

  // Missing or undersized cache memory is refused rather than silently bypassing verification.
  {
    RootWindowVerifier verifier {};
    RootWindowVerifierMemory memory {};
    Ops ops {disk};
    assert (!rootWindowVerifierConfigure (verifier, memory, cachedSelection, windows, 2, userdataFirst,
                                          "OS", key.data (), &vr_openssl_crypto, ops));
  }

  // A header-only policy whose table spans two pages: page 0 holds 128 entries,
  // page 1 holds the two-entry tail. The tail page must hash only its table bytes.
  {
    const auto largeImage = readFile (largeDir + "/image.bin");
    const auto largeManifest = readFile (largeDir + "/manifest.bin");
    const auto largeHeader = readFile (largeDir + "/manifest.header.bin");
    const auto largeTable = readFile (largeDir + "/table.bin");
    assert (largeHeader.size () == VR_HEADER_BYTES + VR_SIGNATURE_BYTES);
    assert (largeImage.size () == 130 * VR_BLOCK_BYTES);
    assert (largeTable.size () == 130 * 32);
    const uint64_t largeTablePages = (largeTable.size () + VR_BLOCK_BYTES - 1) / VR_BLOCK_BYTES;
    assert (largeTablePages == 2);
    const uint64_t largeTableLba = (2 * VR_BLOCK_BYTES + 4096) / VR_BLOCK_BYTES;
    const auto largeDisk = makeDisk (largeTable, largeTableLba, largeTablePages);

    Window largeWindows[2] = {};
    std::strcpy (largeWindows[0].name, "OS");
    largeWindows[0].offset = 0;
    largeWindows[0].size = largeImage.size ();
    std::strcpy (largeWindows[1].name, "OS.vroot");
    largeWindows[1].offset = 4096;
    largeWindows[1].size = largeTable.size ();

    NativeVerifiedBlockPolicy largeCached[1] = {{largeHeader.data (), largeHeader.size ()}};
    RootPolicySelection largeSelection {};
    assert (rootPolicySelect (largeCached, 1, largeImage.size (), &largeSelection));

    std::vector<uint8_t> headerStorage (VR_BLOCK_BYTES);
    std::vector<uint8_t> pageHashes (largeTablePages * 32);
    std::vector<uint32_t> where (largeTablePages);
    std::vector<uint8_t> scratch (VR_BLOCK_BYTES);
    std::vector<VrootCacheEntry> entries (2);
    std::vector<uint8_t> cachePages (2 * VR_BLOCK_BYTES);
    RootWindowVerifierMemory memory {headerStorage.data (), headerStorage.size (), pageHashes.data (),
                                     pageHashes.size (), where.data (), where.size (), scratch.data (),
                                     scratch.size (), entries.data (), cachePages.data (), 2};
    RootWindowVerifier verifier {};
    Ops ops {largeDisk};
    assert (rootWindowVerifierConfigure (verifier, memory, largeSelection, largeWindows, 2, 2,
                                         "OS", key.data (), &vr_openssl_crypto, ops));
    assert (verifier.ready && !verifier.view.hashes);
    assert (ops.reads == 2);
    assert (verifier.cache.stats.misses == 0);
    assert (rootWindowVerifierVerify (verifier, ops, 0, largeImage.data (), VR_BLOCK_BYTES,
                                      &vr_openssl_crypto) == VR_OK);
    assert (rootWindowVerifierVerify (verifier, ops, 129, largeImage.data () + 129 * VR_BLOCK_BYTES,
                                      VR_BLOCK_BYTES, &vr_openssl_crypto) == VR_OK);
    assert (verifier.cache.stats.misses == 2 && verifier.cache.stats.hits == 0);
    assert (rootWindowVerifierVerify (verifier, ops, 0, largeImage.data (), VR_BLOCK_BYTES,
                                      &vr_openssl_crypto) == VR_OK);
    assert (verifier.cache.stats.hits == 1);
    rootWindowVerifierDrop (verifier, ops);
    assert (!verifier.ready);
  }

  std::puts ("PASS: per-window verified-root verifier");
  return 0;
}