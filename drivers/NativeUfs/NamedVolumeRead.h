// SPDX-License-Identifier: BSD-2-Clause-Patent
#pragma once
// Read-only lookup of a GPT partition by name, for the storage service that has
// to fetch the modem's EFS images. The GPT facts come from LUN 0's primary
// header at 4096-byte sectors, exactly as RootLayout.h reads them; this file
// holds only the parts that can be wrong on paper so the host test can run
// them without a device.
#include <stddef.h>
#include <stdint.h>

static constexpr unsigned kNativeVolumeNameMax = 36;
static constexpr uint32_t kNativeVolumeEntryBytes = 128;
static constexpr unsigned kNativeVolumeNameOffset = 56;

// A GPT entry is unused when its type GUID is all zero.
static inline bool nativeVolumeEntryUsed (const uint8_t *entry)
{
  uint8_t used = 0;
  for (unsigned i = 0; i < 16; ++i) used |= entry[i];
  return used != 0;
}

// The name is 36 UTF-16LE code units, not a C string: a full-length name has no
// terminator left inside the field.
static inline bool nativeVolumeNameMatches (const uint8_t *entry, const char *name)
{
  if (entry == nullptr || name == nullptr || name[0] == '\0') return false;
  unsigned length = 0;
  while (name[length] && length <= kNativeVolumeNameMax) ++length;
  if (length == 0 || length > kNativeVolumeNameMax) return false;
  for (unsigned c = 0; c < length; ++c) {
    const uint8_t high = entry[kNativeVolumeNameOffset + 2 * c + 1];
    if (entry[kNativeVolumeNameOffset + 2 * c] != static_cast<uint8_t> (name[c]) || high != 0) return false;
  }
  if (length < kNativeVolumeNameMax) {
    if (entry[kNativeVolumeNameOffset + 2 * length] != 0) return false;
    if (entry[kNativeVolumeNameOffset + 2 * length + 1] != 0) return false;
  }
  return true;
}

// Turns a byte range inside one partition into whole sectors to read plus the
// offset of the first wanted byte inside the first sector. Refuses a zero
// length, a range that leaves the partition, and any arithmetic that would
// wrap.
static inline bool nativeVolumePlan (uint64_t firstLba, uint64_t lastLba,
  uint32_t sectorBytes, uint64_t offset, size_t length,
  uint64_t *firstSector, uint32_t *skip, uint32_t *sectors)
{
  if (sectorBytes == 0 || length == 0) return false;
  if (lastLba < firstLba) return false;
  const uint64_t capacity = (lastLba - firstLba + 1) * static_cast<uint64_t> (sectorBytes);
  if (offset > capacity) return false;
  if (static_cast<uint64_t> (length) > capacity - offset) return false;
  const uint64_t skipBytes = offset % sectorBytes;
  const uint64_t wanted = skipBytes + static_cast<uint64_t> (length);
  const uint64_t count = (wanted + sectorBytes - 1) / sectorBytes;
  if (count == 0 || count > 0xffffffffULL) return false;
  if (firstSector != nullptr) *firstSector = firstLba + offset / sectorBytes;
  if (skip != nullptr) *skip = static_cast<uint32_t> (skipBytes);
  if (sectors != nullptr) *sectors = static_cast<uint32_t> (count);
  return true;
}

// The K60 publishes six UFS LUNs, and the modem EFS partitions (modemst1,
// modemst2, fsg, fsc) do not live on the LUN that carries unixnu/userdata:
// on the device they are sdf3..sdf6 while unixnu is sda38. The lookup therefore
// has to try every LUN and accept only one claimant. 8 covers the six the
// firmware exposes with two spare slots.
static constexpr unsigned kNativeVolumeLunCount = 8;

// Pick the LUN that reported the name. found[i] is non-zero for a hit.
// Returns 1 with *lun set; 0 when nothing matched or two LUNs claimed the name.
static inline int nativeVolumeUniqueLun (const uint8_t *found, unsigned count,
  unsigned *lun)
{
  if (found == nullptr) return 0;
  unsigned hits = 0, pick = 0;
  for (unsigned i = 0; i < count; ++i) {
    if (!found[i]) continue;
    pick = i;
    if (++hits > 1) return 0;
  }
  if (hits != 1) return 0;
  if (lun != nullptr) *lun = pick;
  return 1;
}
