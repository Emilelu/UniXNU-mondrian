// SPDX-License-Identifier: BSD-2-Clause-Patent
// Host checks for the verified-root read path: RootWindowRead's window reader
// must verify every 4096-byte block through RootWindowVerifier before copying.
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>
using IOReturn = uint32_t;
constexpr IOReturn kIOReturnSuccess = 0, kIOReturnBadArgument = 1, kIOReturnIOError = 2,
                    kIOReturnNotPrivileged = 3;
constexpr uint64_t kDataMax = 131072;
#include "../RootWindowVerifier.h"
#include "../RootWindowRead.h"

extern "C" const struct vr_crypto vr_openssl_crypto;

struct Window {
  char name[32];
  uint64_t offset, size;
};

struct CacheOps {
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

struct ReadOps {
  RootWindowVerifier &verifier;
  CacheOps &cache;
  const std::vector<uint8_t> &disk;
  std::vector<uint8_t> &output;
  unsigned reads = 0, verifies = 0;
  void lock () {}
  void unlock () {}
  IOReturn read (uint64_t lba, uint32_t blocks, void *dst) {
    const uint64_t at = lba * VR_BLOCK_BYTES;
    if (at + uint64_t (blocks) * VR_BLOCK_BYTES > disk.size ()) return kIOReturnIOError;
    std::memcpy (dst, disk.data () + at, uint64_t (blocks) * VR_BLOCK_BYTES);
    ++reads;
    return kIOReturnSuccess;
  }
  IOReturn verify (uint64_t index, const void *data, size_t length) {
    ++verifies;
    const int status = rootWindowVerifierVerify (verifier, cache, index, data, length, &vr_openssl_crypto);
    return status == VR_OK ? kIOReturnSuccess : kIOReturnNotPrivileged;
  }
  uint64_t copy (uint64_t offset, const void *data, uint64_t length) {
    if (offset + length > output.size ()) return 0;
    std::memcpy (output.data () + offset, data, length);
    return length;
  }
};

static std::vector<uint8_t> readFile (const std::string &path) {
  std::ifstream stream (path, std::ios::binary);
  assert (stream);
  return std::vector<uint8_t> (std::istreambuf_iterator<char> (stream), {});
}

static std::vector<uint8_t> makeDisk (const std::vector<uint8_t> &table, uint64_t firstLba, uint64_t pages) {
  std::vector<uint8_t> disk ((firstLba + pages) * VR_BLOCK_BYTES, 0xee);
  std::memcpy (disk.data () + firstLba * VR_BLOCK_BYTES, table.data (), table.size ());
  return disk;
}

static std::vector<uint8_t> padToBlocks (const std::vector<uint8_t> &image) {
  std::vector<uint8_t> disk (((image.size () + VR_BLOCK_BYTES - 1) / VR_BLOCK_BYTES) * VR_BLOCK_BYTES, 0xee);
  std::memcpy (disk.data (), image.data (), image.size ());
  return disk;
}

int main (int argc, char **argv) {
  assert (argc == 2);
  const std::string dir = argv[1];
  const auto image = readFile (dir + "/image.bin");
  const auto manifest = readFile (dir + "/manifest.bin");
  const auto header = readFile (dir + "/manifest.header.bin");
  const auto key = readFile (dir + "/trusted-key.bin");
  const auto table = readFile (dir + "/table.bin");
  assert (key.size () == VR_KEY_BYTES);
  assert (header.size () == VR_HEADER_BYTES + VR_SIGNATURE_BYTES);
  assert (image.size () % 512 == 0);
  const auto imageDisk = padToBlocks (image);
  const uint64_t imageBytes = image.size ();
  const uint64_t tableBytes = table.size ();
  const uint64_t tablePages = (tableBytes + VR_BLOCK_BYTES - 1) / VR_BLOCK_BYTES;
  const uint64_t tableLba = (2 * VR_BLOCK_BYTES + 4096) / VR_BLOCK_BYTES;
  const auto tableDisk = makeDisk (table, tableLba, tablePages);

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

  // A full envelope verifies each window block before copying.
  {
    RootWindowVerifier verifier {};
    RootWindowVerifierMemory memory {};
    CacheOps cache {tableDisk};
    assert (rootWindowVerifierConfigure (verifier, memory, fullSelection, windows, 2, userdataFirst,
                                         "OS", key.data (), &vr_openssl_crypto, cache));
    std::vector<uint8_t> output (imageBytes, 0xa5);
    ReadOps ops {verifier, cache, imageDisk, output};
    std::vector<uint8_t> bounce (kDataMax);
    const UfsWindowResult result = ufsReadWindow (ops, 0, imageBytes, 0, imageBytes / 512, bounce.data ());
    assert (result.status == kIOReturnSuccess && result.done == imageBytes);
    assert (ops.verifies == (imageBytes + VR_BLOCK_BYTES - 1) / VR_BLOCK_BYTES);
    assert (!std::memcmp (output.data (), image.data (), imageBytes));

    std::vector<uint8_t> bad = imageDisk;
    bad[VR_BLOCK_BYTES] ^= 1;
    std::vector<uint8_t> refused (imageBytes, 0xa5);
    ReadOps badOps {verifier, cache, bad, refused};
    const UfsWindowResult badResult = ufsReadWindow (badOps, 0, imageBytes, 0, imageBytes / 512, bounce.data ());
    assert (badResult.status == kIOReturnNotPrivileged && badResult.done == 0);
    assert (refused[VR_BLOCK_BYTES] == 0xa5);
    rootWindowVerifierDrop (verifier, cache);
  }

  // A header-only policy reads table entries through the cache and verifies
  // every window block before copying it.
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
    CacheOps cache {tableDisk};
    assert (rootWindowVerifierConfigure (verifier, memory, cachedSelection, windows, 2, userdataFirst,
                                         "OS", key.data (), &vr_openssl_crypto, cache));
    assert (verifier.ready && !verifier.view.hashes);
    std::vector<uint8_t> output (imageBytes, 0xa5);
    ReadOps ops {verifier, cache, imageDisk, output};
    std::vector<uint8_t> bounce (kDataMax);
    const UfsWindowResult result = ufsReadWindow (ops, 0, imageBytes, 0, imageBytes / 512, bounce.data ());
    assert (result.status == kIOReturnSuccess && result.done == imageBytes);
    assert (ops.verifies == (imageBytes + VR_BLOCK_BYTES - 1) / VR_BLOCK_BYTES);
    assert (!std::memcmp (output.data (), image.data (), imageBytes));
    assert (cache.reads >= tablePages);
    rootWindowVerifierDrop (verifier, cache);
  }

  std::puts ("PASS: verified window read verifies every block before copy");
  return 0;
}
