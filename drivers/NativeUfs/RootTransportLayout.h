// SPDX-License-Identifier: BSD-2-Clause-Patent
// DMA layout. Up to kSlots commands can run concurrently, each in its own command slot: a request list entry, a command
// descriptor and a data area (RootCommands.h keeps the geometry of each slot in a table).
//
// STAGE S1 (this file): geometry only. The constants and the slot offset helpers are introduced so S2/S3 can size their
// allocations from them, but kDmaBytes deliberately stays kDmaBytesOneSlot and no caller enumerates slots yet, so the
// driver still runs exactly one command at a time. Nothing outside this header changes in S1.
//
// Region A (one contiguous, cached allocation) holds slots 0..kRegionSlots-1: slot 0 keeps the original layout (its
// descriptor at kUcdOffset, data at kDataOffset), the others follow. Offset 0 of region A holds the request list
// (UTRLBA) unless the list has a page of its own. The stream is not cache coherent and request list entries are
// 32 bytes, so two entries share a 64-byte line: with the list in region A, slot s uses entry 2s (the CPU's clean of
// one entry must not write a stale copy over the controller's completion of another). A list page mapped
// write-combined (not cached, as Linux's coherent DMA memory on this stream) lets slot s use entry s, so all 32
// entries serve; region B then holds slots kRegionSlots..kSlots-1 with descriptors first and data after.
enum : uint32_t {
  kUcdOffset = 4096,
  kRspOffset = 512,
  kPrdtOffset = 1024,
  kDataOffset = 8192,
  kDataMax = 131072,
  kSlots = 32,
  kRegionSlots = 16,
  kUcdStride = 2048,
  kExtraUcdOffset = kDataOffset + kDataMax,
  kExtraDataOffset = (kExtraUcdOffset + (kRegionSlots - 1) * kUcdStride + 4095) & ~4095U,
  // Bytes of the full 16-slot region A, of an 8-slot region A, and of the original single slot.
  kDmaBytesRegionA = kExtraDataOffset + (kRegionSlots - 1) * kDataMax,
  kDmaBytesOneSlot = kDataOffset + kDataMax,
  kDmaBytesEightSlots = kExtraDataOffset + 7 * kDataMax,
  kRegionBDataOffset = kRegionSlots * kUcdStride,
  kRegionBBytes = kRegionBDataOffset + kRegionSlots * kDataMax,
  // S1 runs one slot, so the allocation stays the original single-slot size.
  kDmaBytes = kDmaBytesOneSlot,
};
// Region A offsets of slot s < kRegionSlots.
static constexpr uint32_t ufsSlotUcdOffset (unsigned slot) { return slot ? kExtraUcdOffset + (slot - 1) * kUcdStride : kUcdOffset; }
static constexpr uint32_t ufsSlotDataOffset (unsigned slot) { return slot ? kExtraDataOffset + (slot - 1) * kDataMax : kDataOffset; }
// The request list entry of slot s with the list in region A.
static constexpr uint32_t ufsSlotEntry (unsigned slot) { return 2 * slot; }
static constexpr uint32_t ufsSlotUtrdOffset (unsigned slot) { return 32 * ufsSlotEntry (slot); }
static_assert (ufsSlotUcdOffset (kRegionSlots - 1) + kPrdtOffset + 16 <= kExtraDataOffset, "slot descriptors overlap data");
static_assert (ufsSlotUtrdOffset (kRegionSlots - 1) + 32 <= kUcdOffset, "request list overlaps slot 0's descriptor");
static_assert (kDmaBytesEightSlots <= kDmaBytesRegionA, "eight-slot region must fit inside the sixteen-slot region");
