// SPDX-License-Identifier: BSD-2-Clause-Patent
// Host checks for policy selection and header-only table authentication.
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>
#include "../RootPolicyTable.h"

extern "C" const struct vr_crypto vr_openssl_crypto;

struct Window {
  char name[32];
  uint64_t offset, size;
};

struct Ops {
  const std::vector<uint8_t> &table;
  uint64_t firstLba;
  unsigned reads = 0;
  bool read4k (uint64_t lba, uint32_t blocks, void *dst) {
    if (blocks != 1 || lba != firstLba) return false;
    std::memset (dst, 0, VR_BLOCK_BYTES);
    std::memcpy (dst, table.data (), table.size ());
    ++reads;
    return true;
  }
};

static std::vector<uint8_t> readFile (const std::string &path) {
  std::ifstream stream (path, std::ios::binary);
  assert (stream);
  return std::vector<uint8_t> (std::istreambuf_iterator<char> (stream), {});
}

int main (int argc, char **argv) {
  assert (argc == 2);
  const std::string dir = argv[1];
  const auto image = readFile (dir + "/image.bin");
  const auto manifest = readFile (dir + "/manifest.bin");
  const auto header = readFile (dir + "/manifest.header.bin");
  const auto key = readFile (dir + "/trusted-key.bin");
  const auto otherKey = readFile (dir + "/other-key.bin");
  const auto table = readFile (dir + "/table.bin");
  assert (key.size () == VR_KEY_BYTES && otherKey.size () == VR_KEY_BYTES);
  assert (header.size () == VR_HEADER_BYTES + VR_SIGNATURE_BYTES);
  assert (manifest.size () == header.size () + table.size ());

  const uint64_t imageBytes = image.size ();
  const uint64_t tableBytes = table.size ();
  NativeVerifiedBlockPolicy one[1] = {{manifest.data (), manifest.size ()}};
  NativeVerifiedBlockPolicy headerOnly[1] = {{header.data (), header.size ()}};
  NativeVerifiedBlockPolicy duplicate[2] = {{manifest.data (), manifest.size ()}, {header.data (), header.size ()}};

  RootPolicySelection selection {};
  assert (!rootPolicySelect (nullptr, 1, imageBytes, &selection));
  assert (!rootPolicySelect (one, 0, imageBytes, &selection));
  assert (!rootPolicySelect (duplicate, 2, imageBytes, &selection));
  assert (!rootPolicySelect (one, 1, imageBytes + 1, &selection));
  assert (rootPolicySelect (one, 1, imageBytes, &selection));
  assert (!selection.headerOnly && selection.manifestBytes == manifest.size () && !selection.tableBytes);
  RootPolicySelection cached {};
  assert (rootPolicySelect (headerOnly, 1, imageBytes, &cached));
  assert (cached.headerOnly && cached.tableBytes == tableBytes);

  Window windows[2] = {};
  std::strcpy (windows[0].name, "OS");
  windows[0].offset = 0;
  windows[0].size = imageBytes;
  std::strcpy (windows[1].name, "OS.vroot");
  windows[1].offset = 4096;
  windows[1].size = tableBytes;
  const uint64_t firstLba = 2 * 4096 / 4096 + 1;  // userdataFirst = 2, table offset 4096

  // A full envelope carries the table in the boot image; no table object is read.
  {
    std::vector<uint8_t> unused;
    Ops ops {unused, ~uint64_t (0)};
    struct vr_view view {};
    assert (rootPolicyOpen (selection, windows, 2, 2, "OS", key.data (), &vr_openssl_crypto,
                             ops, nullptr, 0, &view) == VR_OK);
    assert (view.image_bytes == imageBytes && view.hashes == manifest.data () + header.size ());
    assert (!ops.reads);
    for (uint64_t block = 0; block < view.block_count; ++block) {
      const uint64_t at = block * VR_BLOCK_BYTES;
      const uint64_t length = imageBytes - at < VR_BLOCK_BYTES ? imageBytes - at : VR_BLOCK_BYTES;
      assert (vr_verify_block (&view, block, image.data () + at, static_cast<size_t> (length), &vr_openssl_crypto) == VR_OK);
    }
  }

  // A header-only policy reads and authenticates "<window>.vroot" from LUN 0.
  {
    std::vector<uint8_t> loaded (tableBytes);
    Ops ops {table, firstLba};
    struct vr_view view {};
    assert (rootPolicyOpen (cached, windows, 2, 2, "OS", key.data (), &vr_openssl_crypto,
                             ops, loaded.data (), loaded.size (), &view) == VR_OK);
    assert (ops.reads == 1 && view.hashes == loaded.data ());
    for (uint64_t block = 0; block < view.block_count; ++block) {
      const uint64_t at = block * VR_BLOCK_BYTES;
      const uint64_t length = imageBytes - at < VR_BLOCK_BYTES ? imageBytes - at : VR_BLOCK_BYTES;
      assert (vr_verify_block (&view, block, image.data () + at, static_cast<size_t> (length), &vr_openssl_crypto) == VR_OK);
    }
    loaded[0] ^= 0x80;
    assert (vr_verify_block (&view, 0, image.data (), 4096, &vr_openssl_crypto) == VR_BLOCK);
  }

  // Wrong anchor, wrong table, missing window and a truncated header are refused.
  {
    std::vector<uint8_t> loaded (tableBytes);
    Ops ops {table, firstLba};
    struct vr_view view {};
    assert (rootPolicyOpen (cached, windows, 2, 2, "OS", otherKey.data (), &vr_openssl_crypto,
                             ops, loaded.data (), loaded.size (), &view) == VR_KEY);
    assert (rootPolicyOpen (cached, windows, 2, 2, "SystemOS", key.data (), &vr_openssl_crypto,
                             ops, loaded.data (), loaded.size (), &view) == VR_FORMAT);
    windows[1].size = tableBytes - 1;
    assert (rootPolicyOpen (cached, windows, 2, 2, "OS", key.data (), &vr_openssl_crypto,
                             ops, loaded.data (), loaded.size (), &view) == VR_FORMAT);
    windows[1].size = tableBytes;
    std::vector<uint8_t> badTable = table;
    badTable[0] ^= 1;
    Ops badOps {badTable, firstLba};
    assert (rootPolicyOpen (cached, windows, 2, 2, "OS", key.data (), &vr_openssl_crypto,
                             badOps, loaded.data (), loaded.size (), &view) == VR_HASH_TABLE);
    assert (vr_open_header (header.data (), header.size () - 1, key.data (), 1,
                            &vr_openssl_crypto, &view) == VR_FORMAT);
    assert (vr_open_header (header.data (), header.size (), key.data (), 8,
                            &vr_openssl_crypto, &view) == VR_FORMAT);
  }

  // A signed header mutation is not accepted; the signature covers the metadata.
  {
    std::vector<uint8_t> changed = header;
    changed[40] ^= 1;
    NativeVerifiedBlockPolicy bad[1] = {{changed.data (), changed.size ()}};
    RootPolicySelection badSelection {};
    assert (rootPolicySelect (bad, 1, imageBytes, &badSelection));
    std::vector<uint8_t> loaded (tableBytes);
    Ops ops {table, firstLba};
    struct vr_view view {};
    assert (rootPolicyOpen (badSelection, windows, 2, 2, "OS", key.data (), &vr_openssl_crypto,
                             ops, loaded.data (), loaded.size (), &view) == VR_SIGNATURE);
  }

  std::puts ("PASS: policy selection and header-only table authentication");
  return 0;
}
