// SPDX-License-Identifier: BSD-2-Clause-Patent
// Host test for the read-only named-volume lookup: the GPT name comparison and
// the byte-range plan, including the three refusals the transport must honour.
#include <stdio.h>
#include <string.h>
#include "../../drivers/NativeUfs/NamedVolumeRead.h"

static int failures = 0;

static void check (bool ok, const char *what)
{
  if (!ok) { printf ("FAIL %s\n", what); ++failures; }
}

static void name (uint8_t *entry, const char *text)
{
  memset (entry, 0, kNativeVolumeEntryBytes);
  entry[0] = 1;                             // used: a non-zero type GUID
  for (unsigned i = 0; text[i]; ++i) {
    entry[kNativeVolumeNameOffset + 2 * i] = static_cast<uint8_t> (text[i]);
    entry[kNativeVolumeNameOffset + 2 * i + 1] = 0;
  }
}

int main (void)
{
  uint8_t entry[kNativeVolumeEntryBytes];
  uint8_t unused[kNativeVolumeEntryBytes];
  uint64_t sector = 0;
  uint32_t skip = 0, sectors = 0;

  name (entry, "modemst1");
  check (nativeVolumeNameMatches (entry, "modemst1"), "the name matches itself");
  check (!nativeVolumeNameMatches (entry, "modemst2"), "a different name does not match");
  check (!nativeVolumeNameMatches (entry, "modemst"), "a prefix does not match");
  check (!nativeVolumeNameMatches (entry, "modemst1x"), "a longer name does not match");
  check (!nativeVolumeNameMatches (entry, ""), "an empty name never matches");
  check (!nativeVolumeNameMatches (entry, nullptr), "a null name never matches");
  check (!nativeVolumeNameMatches (nullptr, "modemst1"), "a null entry never matches");

  memset (unused, 0, sizeof unused);
  check (!nativeVolumeEntryUsed (unused), "an all-zero type guid is unused");
  check (nativeVolumeEntryUsed (entry), "a named entry is used");

  char longName[kNativeVolumeNameMax + 2];
  memset (longName, 'a', sizeof longName);
  longName[sizeof longName - 1] = 0;
  check (!nativeVolumeNameMatches (entry, longName), "a name past 36 units is refused");

  name (entry, "modemst1");
  entry[kNativeVolumeNameOffset + 2 * 36 - 1] = 0;
  check (nativeVolumeNameMatches (entry, "modemst1"), "the terminator stays mandatory");

  // Partition at LBA 0x1000..0x10ff, 4096-byte sectors, so 1 MiB.
  check (nativeVolumePlan (0x1000, 0x10ff, 4096, 0, 4096, &sector, &skip, &sectors),
    "the first sector is readable");
  check (sector == 0x1000 && skip == 0 && sectors == 1, "the first sector plans exactly");
  check (nativeVolumePlan (0x1000, 0x10ff, 4096, 0x1800, 512, &sector, &skip, &sectors),
    "an unaligned range is readable");
  check (sector == 0x1001 && skip == 0x800 && sectors == 1, "an unaligned range plans the covering sector");
  check (nativeVolumePlan (0x1000, 0x10ff, 4096, 0x100000 - 512, 512, &sector, &skip, &sectors),
    "the last block is readable");
  check (sector == 0x10ff && skip == 0xe00, "the last block plans the final sector");

  check (!nativeVolumePlan (0x1000, 0x10ff, 4096, 0, 0, &sector, &skip, &sectors),
    "a zero length is refused");
  check (!nativeVolumePlan (0x1000, 0x10ff, 4096, 0x100000, 512, &sector, &skip, &sectors),
    "a range past the partition is refused");
  check (!nativeVolumePlan (0x1000, 0x10ff, 4096, 0x100000 - 512, 1024, &sector, &skip, &sectors),
    "a range that runs over the end is refused");
  check (nativeVolumePlan (0x1000, 0x10ff, 4096, 0, 4096, nullptr, nullptr, nullptr),
    "null outputs are still planned");
  check (!nativeVolumePlan (0x10ff, 0x1000, 4096, 0, 512, &sector, &skip, &sectors),
    "an inverted partition is refused");
  check (!nativeVolumePlan (0x1000, 0x10ff, 0, 0, 512, &sector, &skip, &sectors),
    "a zero sector size is refused");

  if (failures) { printf ("K60 NAMED VOLUME FAIL %d checks\n", failures); return 1; }
  printf ("K60 NAMED VOLUME PASS names, unused slots, plans, refusals\n");
  return 0;
}