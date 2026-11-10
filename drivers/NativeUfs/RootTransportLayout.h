// SPDX-License-Identifier: BSD-2-Clause-Patent
// DMA layout. Up to kSlots commands run concurrently, each in its own command slot: a request list entry, a command
// descriptor and a data area (RootCommands.h keeps the geometry of each slot in a table).
//
// STAGE S3: the full 32 slots. Three regions:
//   * region A (cached, allocated first): slots 0..kRegionSlots-1;
//   * a write-combined 4 KiB request-list page: all 32 entries, slot s on entry s. The stream is not cache coherent
//     and an entry is 32 bytes, so two entries share a 64-byte line. A cached list would need entry 2s so that cleaning
//     one entry cannot write a stale copy over the controller's completion of another, which caps a cached list at 16
//     entries. A write-combined (uncached) page needs no cache maintenance at all, so every entry serves;
//   * region B (cached): slots kRegionSlots..kSlots-1, descriptors first then data.
// If the list page or region B cannot be allocated, S3 degrades to region A only, which still gives 16 slots through
// entries 2s (the S2 shape), and then to a single slot.
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
  // S3 target and capabilities.
  kSlotTarget = 32,
  kUseOwnListPage = 1,
  kUseCompletionInterrupt = 1,
  // Region A is what this stage asks for first; the request-list page and region B are separate allocations.
  kDmaBytes = kDmaBytesRegionA,
};
// Region A offsets of slot s < kRegionSlots.
static constexpr uint32_t ufsSlotUcdOffset (unsigned slot) { return slot ? kExtraUcdOffset + (slot - 1) * kUcdStride : kUcdOffset; }
static constexpr uint32_t ufsSlotDataOffset (unsigned slot) { return slot ? kExtraDataOffset + (slot - 1) * kDataMax : kDataOffset; }
// The request list entry of slot s when the list lives in region A (cached, entry 2s) and on its own write-combined
// page (uncached, entry s).
static constexpr uint32_t ufsSlotEntry (unsigned slot) { return 2 * slot; }
static constexpr uint32_t ufsSlotUtrdOffset (unsigned slot) { return 32 * ufsSlotEntry (slot); }
static_assert (ufsSlotUcdOffset (kRegionSlots - 1) + kPrdtOffset + 16 <= kExtraDataOffset, "slot descriptors overlap data");
static_assert (ufsSlotUtrdOffset (kRegionSlots - 1) + 32 <= kUcdOffset, "request list overlaps slot 0's descriptor");
static_assert (kDmaBytesEightSlots <= kDmaBytesRegionA, "eight-slot region must fit inside the sixteen-slot region");
static_assert (32 * kSlots <= 4096, "request list page must hold one entry per slot");
