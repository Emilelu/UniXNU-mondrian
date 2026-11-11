// SPDX-License-Identifier: BSD-2-Clause-Patent
// Pong/SM8475 UFS transport. Writes are boot-arg gated and limited to the
// declared SHNGROOT windows, including the independent persistent APFS Data.
// Shared queue/protocol code derives
// from Sheng; board addresses and stream ID come from Pong's live DT.
#include <IOKit/IOService.h>
#include "CompletionWait.h"
#include <IOKit/IOBufferMemoryDescriptor.h>
#include <IOKit/IOBSD.h>
#include <IOKit/storage/IOBlockStorageDevice.h>
#include <IOKit/storage/IOMedia.h>
#include <IOKit/IOLib.h>
#include <vm/vm_kern.h>
#include <kern/clock.h>
#include <kern/sched_prim.h>
#include <kern/ast.h>
#include <mach/mach_time.h>
#include <machine/machine_routines.h>
#include <libkern/c++/OSBoolean.h>
#include <libkern/c++/OSDictionary.h>
#include <libkern/c++/OSIterator.h>
#include <libkern/c++/OSNumber.h>
#include <libkern/c++/OSSymbol.h>
#include <libkern/c++/OSString.h>
#include <libkern/OSKextLib.h>
#include <libkern/crypto/sha2.h>
#include <pexpert/pexpert.h>
#include <sys/param.h>
#include <sys/types.h>
#include "../PongProbe.h"

namespace {
#include "RootTransportLayout.h"
#include "RootDiagnostics.h"
#include "TransferPoll.h"
#include "SmmuTakeover.h"
static UfsRootDiagnostics gRootDiagnostic;
struct UfsHost {
  OSSharedPtr<IOMemoryMap> hcMap, smmuMap;
  uintptr_t hc = 0, smmu = 0, cb = 0;
  IOBufferMemoryDescriptor *dma = nullptr;
  uint8_t *virt = nullptr;
  uint64_t phys = 0, blocks = 0;
  uint32_t dmaBytes = 0;          // size of the slot region actually allocated
  IOLock *lock = nullptr;
  bool ready = false, poisoned = false;
  bool writable = false;
  /* Armed just before the Data mount; the first reads say where APFS stops. */
  bool readTrace = false;
  uint32_t readTraceCount = 0;
};
static UfsHost gHost;
static bool gTransportAttempted;
// How many command slots this bring-up enabled (1, 8, 16 or 32) and which request-list form is in use.
extern "C" volatile uint32_t native_ufs_slots = 0;
extern "C" volatile uint32_t native_ufs_list_mode = 0;   // 0 region A (entry 2s), 1 own page, 2 own page + region B
extern "C" volatile uint32_t native_ufs_irq_mode = 0;
extern "C" volatile uint64_t native_ufs_irqs = 0, native_ufs_irq_sleeps = 0;
enum : uint64_t {
  // Pong LUN0 GPT entry "userdata", captured from this phone in recovery.
  kPongUserdataFirst4k = 0x413248ULL,
  kPongUserdataLast4k = 0x75a40eaULL,
  kRootLogicalBlock = 512,
};
struct RootDiskWindow {
  const char *name;
  const char *product;
  const char *signature;
  unsigned signatureOffset;
  uint64_t baseByte;
  uint64_t size;
};
static RootDiskWindow gRootWindows[3];
static unsigned gRootWindowCount;
static uint32_t read32(uintptr_t base, unsigned offset) {
  return *reinterpret_cast<volatile uint32_t *>(base + offset);
}
static void write32(uintptr_t base, unsigned offset, uint32_t value) {
  __asm__ volatile("dsb sy" ::: "memory");
  *reinterpret_cast<volatile uint32_t *>(base + offset) = value;
  __asm__ volatile("dsb sy" ::: "memory");
}
static uintptr_t mapPhys(uint64_t base, uint64_t size, OSSharedPtr<IOMemoryMap> &keep) {
  OSSharedPtr<IOMemoryDescriptor> memory(IOMemoryDescriptor::withPhysicalAddress(base, size, kIODirectionInOut), OSNoRetain);
  if (memory) keep = OSSharedPtr<IOMemoryMap>(memory->map(kIOMapAnywhere | kIOMapInhibitCache), OSNoRetain);
  return keep ? keep->getVirtualAddress() : 0;
}
static IOReturn recordTransport(IOReturn result, uint32_t ocs) {
  gRootDiagnostic.result = static_cast<uint32_t>(result); gRootDiagnostic.ocs = ocs;
  gRootDiagnostic.hcs = read32(gHost.hc, 0x30);
  gRootDiagnostic.hce = read32(gHost.hc, 0x34);
  gRootDiagnostic.doorbell = read32(gHost.hc, 0x58);
  gRootDiagnostic.interrupt = read32(gHost.hc, 0x20);
  gRootDiagnostic.list = uint64_t(read32(gHost.hc, 0x50)) | (uint64_t(read32(gHost.hc, 0x54)) << 32);
  gRootDiagnostic.runStop = read32(gHost.hc, 0x60);
  gRootDiagnostic.ahit = read32(gHost.hc, 0x18);
  for (unsigned i = 0; i < 5; ++i) gRootDiagnostic.uic[i] = read32(gHost.hc, 0x38 + i * 4);
  if (gHost.smmu && gHost.cb) {
    gRootDiagnostic.gfsr = read32(gHost.smmu, 0x48);
    gRootDiagnostic.gsyn = read32(gHost.smmu, 0x54);
    gRootDiagnostic.fsr = read32(gHost.cb, 0x58);
    gRootDiagnostic.fsyn = read32(gHost.cb, 0x68);
    gRootDiagnostic.far = uint64_t(read32(gHost.cb, 0x60)) | (uint64_t(read32(gHost.cb, 0x64)) << 32);
  }
  return result;
}
static void cacheCivac(const void *start, size_t size) {
  uintptr_t end = reinterpret_cast<uintptr_t>(start) + size;
  for (uintptr_t at = reinterpret_cast<uintptr_t>(start) & ~uintptr_t(63); at < end; at += 64)
    __asm__ volatile("dc civac, %0" :: "r"(at) : "memory");
  __asm__ volatile("dsb sy" ::: "memory");
}
static void cacheInvalidate(const void *start, size_t size) {
  __asm__ volatile("dsb sy" ::: "memory");
  uintptr_t end = reinterpret_cast<uintptr_t>(start) + size;
  for (uintptr_t at = reinterpret_cast<uintptr_t>(start); at < end; at += 64)
    __asm__ volatile("dc ivac, %0" :: "r"(at) : "memory");
  __asm__ volatile("dsb sy" ::: "memory");
}
static void hostWrite(unsigned offset, uint32_t value) { write32(gHost.hc, offset, value); }
// The installed Apple SDK declares PE_parse_boot_arg_str only under
// XNU_KERNEL_PRIVATE, which the kext build does not define; the kernel itself
// exports it (pexpert/gen/bootargs.c). Declare it to read a string value such as
// k60_root_partition without PE_parse_boot_argn's numeric conversion.
extern "C" boolean_t PE_parse_boot_arg_str(const char *arg_string, char *arg_ptr, int size);
// The installed Apple SDK ships a truncated kern/sched_prim.h that omits clear_wait (it sits under XNU_KERNEL_PRIVATE in
// the kernel's own header). clear_wait is a normal kernel-internal symbol and this archive is linked statically into the
// kernel, so declaring it here resolves exactly like PE_parse_boot_arg_str above.
extern "C" kern_return_t clear_wait(thread_t thread, wait_result_t result);
#include "RootQueue.h"
#include "RootCommands.h"
#include "RootLayout.h"

// ---- Completion interrupt ------------------------------------------------------------------------------------------
// Same UFSHCI path as the upstream concurrent driver. K60's live DT reports pong,ufs-spi=265, and the ArmCpu SPI
// registration takes the GIC INTID, i.e. 265 + 32 = 297 (kUfsIrq). Both entry points are weakly imported: the K60 kernel
// exports armcpu_spi_attach, while armcpu_spi_mask is not present in this tree, so the interrupt is left unmasked at the
// GIC only if the symbol resolves.
extern "C" IOReturn armcpu_spi_attach (uint32_t, bool, void (*) (void *), void *, uint32_t *, uint64_t *) __attribute__((weak_import));
extern "C" IOReturn armcpu_spi_mask (uint32_t, bool) __attribute__((weak_import));
constexpr uint32_t kUfsIrq = 265 + 32;
static volatile uint32_t gIrqCount = 0;
static bool gIrqMode = false;

static uint32_t hostCompletionCount (unsigned slot) { return __atomic_load_n (&gSlotGen[slot], __ATOMIC_ACQUIRE); }
static bool hostInterruptMode (void) { return gIrqMode && !gHostPanic; }

// Completion wait, ported from UniXNU/ShengUfs CompletionWait.h.
//
// Three modes behind the native-ufs-wait boot argument:
//   Spin (1, default)  one WFE per pause inside the spin budget, then sleep
//                      until the completion interrupt. A WFE ends within about
//                      a microsecond on the counter's event stream, whereas
//                      IODelay(2) blocks on a timer and costs far more.
//   Paced (0)          IODelay(2) per pause, the behaviour we had before.
//   Sleep (2)          sleep from the first pause on.
// Without the interrupt, with interrupts masked, or with preemption disabled,
// the wait cannot sleep and falls back to IODelay.
static uint64_t gSpinTicks = 0;
static uint32_t gSpinTicksUs = ~0U;
static uint32_t gWaitMode = ~0U;   // boot-arg native-ufs-wait, resolved on first wait

// Wait statistics, for the log.
static volatile uint64_t gWaitPauses = 0, gWaitPauseTicks = 0;
static volatile uint64_t gWaitYields = 0, gWaitRange[kUfsWaitRanges] = {};
struct alignas (64) UfsSlotSpin { volatile uint64_t pauses, ticks; };
static UfsSlotSpin gSlotSpin[kSlots];
static volatile uint64_t gSlotDoneAt[kSlots] = {};

static uint32_t hostWaitModeFromBootArgs (void)
{
  static uint32_t resolved = ~0U;
  if (resolved == ~0U) {
    uint32_t mode = kUfsWaitSpin;
    if (PE_parse_boot_argn ("native-ufs-wait", &mode, sizeof (mode)) &&
        mode <= kUfsWaitSleep) {
      resolved = mode;
    } else {
      resolved = kUfsWaitSpin;
    }
  }
  return resolved;
}

static void hostWaitCompletion (unsigned slot, uint32_t seen, uint64_t started)
{
  const uint32_t spinUs = *static_cast<volatile uint32_t *> (&gSpinUs);
  if (spinUs != gSpinTicksUs) {
    nanoseconds_to_absolutetime (uint64_t (spinUs) * 1000, &gSpinTicks);
    gSpinTicksUs = spinUs;
  }
  if (gWaitMode == ~0U) gWaitMode = hostWaitModeFromBootArgs ();
  const uint64_t now = mach_absolute_time ();
  const bool canBlock = preemption_enabled ();
  const bool preemptPending = canBlock && (*ast_pending () & AST_PREEMPTION) != 0;
  const UfsWaitStep step = ufsWaitStep (gWaitMode, hostInterruptMode (), canBlock,
                                       preemptPending, now - started, gSpinTicks);
  if (step == UfsWaitStep::Spin) {
    __builtin_arm_wfe ();
    UfsSlotSpin &spin = gSlotSpin[slot];
    spin.pauses = spin.pauses + 1;
    spin.ticks = spin.ticks + (mach_absolute_time () - now);
    return;
  }
  if (step == UfsWaitStep::Pause) {
    IODelay (2);
    __atomic_fetch_add (&gWaitPauses, 1, __ATOMIC_RELAXED);
    __atomic_fetch_add (&gWaitPauseTicks, mach_absolute_time () - now, __ATOMIC_RELAXED);
    return;
  }
  if (preemptPending && gWaitMode == kUfsWaitSpin && now - started < gSpinTicks) {
    __atomic_fetch_add (&gWaitYields, 1, __ATOMIC_RELAXED);
  }
  __atomic_store_n (&gSlotDoneAt[slot], 0, __ATOMIC_RELAXED);
  assert_wait_timeout ((event_t) (uintptr_t) &gSlotGen[slot], THREAD_UNINT, 1000, NSEC_PER_USEC);
  if (hostCompletionCount (slot) != seen) {
    clear_wait (current_thread (), THREAD_AWAKENED);
    return;
  }
  __atomic_fetch_add (&native_ufs_irq_sleeps, 1, __ATOMIC_RELAXED);
  thread_block (THREAD_CONTINUE_NULL);
}

// Records the completion time of a finished command into the histogram.
static void hostWaitDone (uint64_t started)
{
  uint64_t ns = 0;
  absolutetime_to_nanoseconds (mach_absolute_time () - started, &ns);
  __atomic_fetch_add (&gWaitRange[ufsWaitRange (ns / 1000)], 1, __ATOMIC_RELAXED);
}

static void hostInterrupt (void *)
{
  if (read32 (gHost.hc, 0x20) & 1) {
    write32 (gHost.hc, 0x20, 1);
    __asm__ volatile ("dsb sy" ::: "memory");
  }
  __atomic_add_fetch (&gIrqCount, 1, __ATOMIC_RELEASE);
  __atomic_fetch_add (&native_ufs_irqs, 1, __ATOMIC_RELAXED);
  // Wake exactly the slots whose doorbell bit the controller has cleared.
  uint32_t done = __atomic_load_n (&gOutstanding, __ATOMIC_ACQUIRE) & ~read32 (gHost.hc, 0x58);
  while (done) {
    const unsigned entry = static_cast<unsigned> (__builtin_ctz (done));
    done &= done - 1;
    const int slot = gEntrySlot[entry];
    if (slot < 0) continue;
    // Record when the handler first saw this completion, so the waiter can
    // measure how long it took to be scheduled after the interrupt.
    __atomic_store_n (&gSlotDoneAt[slot], mach_absolute_time (), __ATOMIC_RELAXED);
    __atomic_add_fetch (&gSlotGen[slot], 1, __ATOMIC_RELEASE);
    thread_wakeup ((event_t) (uintptr_t) &gSlotGen[slot]);
  }
}

// Hybrid-polling budget and zero-copy switch, settable from a benchmark. Zero-copy PRDT scatter/gather (hostBuildPrds,
// up to 64 entries of up to 256 KiB, at most 1 MiB per command) is used when the caller's buffer is page aligned and
// every page is reachable through the storage stream; otherwise the slot's 128 KiB data area is used.
extern "C" void native_ufs_set_spin (uint32_t us) { gSpinUs = us; }

// native-ufs-wait selects the completion wait strategy (CompletionWait.h).
// 0 = Paced (IODelay), 1 = Spin (WFE, default), 2 = Sleep.
// A boot argument is read once at first use.
extern "C" void native_ufs_set_wait_mode (uint32_t mode)
{
  if (mode <= kUfsWaitSleep) gWaitMode = mode;
}


// Zero copy (RootCommands.h): a kernel page's physical address, if the storage stream can reach it (gDmaLimit, from the
// SMMU's bypass width and the controller's 64-bit addressing, set at bring-up; 0 until then, so no zero copy).
static uint64_t gDmaLimit = 0;
static uint64_t hostDmaAddress (const void *va)
{
  const uint64_t address = ml_vtophys (reinterpret_cast<vm_offset_t> (va));
  return address && address < gDmaLimit && gDmaLimit - address >= 4096 ? address : 0;
}
extern "C" void native_ufs_set_zero_copy (int on) { gZeroCopy = on != 0; }

// Register the completion interrupt. armcpu_spi_mask is checked only if the kernel exports it.
static void hostEnableInterrupt (void)
{
  if (gIrqMode || !&armcpu_spi_attach) return;
  if (armcpu_spi_attach (kUfsIrq, false, hostInterrupt, nullptr, nullptr, nullptr) != kIOReturnSuccess) {
    IOLog("PONG_UFS: completion interrupt attach failed for INTID %u; polling\n", kUfsIrq);
    return;
  }
  hostWrite (0x24, 1);            // UTRCE: UTRD completion interrupt enable
  if (&armcpu_spi_mask && armcpu_spi_mask (kUfsIrq, false) != kIOReturnSuccess) {
    hostWrite (0x24, 0);
    IOLog("PONG_UFS: completion interrupt unmask failed for INTID %u; polling\n", kUfsIrq);
    return;
  }
  gIrqMode = true;
  native_ufs_irq_mode = 1;
  IOLog("PONG_UFS: completion interrupt on INTID %u (UTRCE), hybrid polling %u us\n", kUfsIrq, gSpinUs);
}

// Can the storage stream reach this physical range? The SMMU is left in bypass (VA64), so the bound is the smallest of the
// three IDR2 address sizes, exactly what the region A check used. Separate allocations (list page, region B) must be
// checked too, since nothing guarantees they land inside region A's range.
static bool hostReachable (uint64_t phys, uint64_t bytes, bool wide)
{
  if (!wide && phys + bytes > 0x100000000ULL) return false;
  if (!gHost.smmu) return false;
  const uint32_t idr2 = read32 (gHost.smmu, 0x28);
  for (unsigned shift = 0; shift <= 8; shift += 4) {
    const unsigned bits = ufsSmmuAddressBits ((idr2 >> shift) & 15);
    if (!bits || phys >= (1ULL << bits) || bytes > (1ULL << bits) - phys) return false;
  }
  return true;
}

// A physically contiguous, page-aligned DMA allocation the storage stream can reach; the caller releases it.
static IOBufferMemoryDescriptor *hostContiguous (uint32_t bytes, IOOptionBits extra, bool wide, uint8_t **virt, uint64_t *phys)
{
  IOBufferMemoryDescriptor *dma = IOBufferMemoryDescriptor::inTaskWithOptions (kernel_task,
    IOOptionBits (kIODirectionInOut) | IOOptionBits (kIOMemoryPhysicallyContiguous) | IOOptionBits (kIOMemoryMapperNone) | extra,
    bytes, 4096);
  if (!dma) return nullptr;
  IOByteCount contiguous = 0;
  *virt = static_cast<uint8_t *> (dma->getBytesNoCopy ());
  *phys = dma->getPhysicalSegment (0, &contiguous, kIOMemoryMapperNone);
  if (!*virt || !*phys || (*phys & 4095) || contiguous < bytes || !hostReachable (*phys, bytes, wide)) {
    dma->release ();
    return nullptr;
  }
  bzero (*virt, bytes);
  cacheCivac (*virt, bytes);
  return dma;
}

// S3 upgrade: move the request list onto its own write-combined page (slot s -> entry s) and, when region A holds all
// kRegionSlots, add region B for slots kRegionSlots..kSlots-1. Any allocation that fails leaves the previous, smaller
// geometry in place: the driver keeps working with fewer slots rather than failing bring-up.
static IOBufferMemoryDescriptor *gListDma = nullptr, *gRegionB = nullptr;
static OSSharedPtr<IOMemoryMap> gListMap;
static void hostSlotsUpgrade (unsigned regionSlots, unsigned entries, bool wide)
{
  if (gListDma || regionSlots < 2 || entries < regionSlots) return;
  uint8_t *listVirt = nullptr;
  uint64_t listPhys = 0;
  IOBufferMemoryDescriptor *list = hostContiguous (4096, IOOptionBits (kIOMapWriteCombineCache), wide, &listVirt, &listPhys);
  if (!list) return;
  // The list page must be reached by the controller through an uncached mapping.
  OSSharedPtr<IOMemoryMap> map (list->createMappingInTask (kernel_task, 0, kIOMapAnywhere | kIOMapWriteCombineCache), OSNoRetain);
  uint8_t *mapped = map ? reinterpret_cast<uint8_t *> (map->getVirtualAddress ()) : nullptr;
  if (!mapped) { list->release (); return; }
  gListDma = list; gListMap = map; gUtrlPhys = listPhys;
  hostSlotGeometryListPage (regionSlots, mapped);
  native_ufs_list_mode = 1;
  unsigned total = regionSlots;
  uint8_t *regionVirt = nullptr;
  uint64_t regionPhys = 0;
  if (regionSlots == kRegionSlots && entries >= kSlots &&
      (gRegionB = hostContiguous (kRegionBBytes, 0, wide, &regionVirt, &regionPhys))) {
    hostSlotGeometryRegionB (kRegionSlots, regionVirt, regionPhys, mapped);
    total = kSlots;
    native_ufs_list_mode = 2;
  }
  hostSlotsInit (total, gHost.lock);
  native_ufs_slots = gSlotCount;
  IOLog("PONG_UFS: request list on write-combined page; %u command slot(s), list mode %u\n", gSlotCount, native_ufs_list_mode);
}

static bool transportFailure(const char *why) {
  gHost.ready = false;
  // No panic, reset, retry or DMA release after a timeout. The controller
  // may still own the allocation. Preserve evidence and let BSD continue.
  char text[2400];
  formatUfsRootDiagnostics(text, sizeof(text), gRootDiagnostic, why, "PONG_UFS TRANSPORT");
  IOLog("%s\nPONG_UFS: no media published; continue boot\n", text);
  PongProbeRecord(4, "ufs-transport", PongProbeFail, why, gRootDiagnostic.result);
  snprintf(text, sizeof(text), "stage=%s op=%x ocs=%x scsi=%x protocol=%u", gRootDiagnostic.stage,
           gRootDiagnostic.opcode, gRootDiagnostic.ocs, gRootDiagnostic.scsi, gRootDiagnostic.protocol);
  PongProbeRecord(5, "ufs-command", PongProbeFail, text, gRootDiagnostic.dma);
  snprintf(text, sizeof(text), "hcs=%x db=%x is=%x fsr=%x syn=%x", gRootDiagnostic.hcs,
           gRootDiagnostic.doorbell, gRootDiagnostic.interrupt, gRootDiagnostic.fsr, gRootDiagnostic.fsyn);
  PongProbeRecord(6, "ufs-hardware", PongProbeFail, text, gRootDiagnostic.far);
  return false;
}

static bool hostBringUp() {
  uint32_t requestWrites = 0;
  gHost.writable = PE_parse_boot_argn("pong_ufs_readwrite", &requestWrites, sizeof(requestWrites)) &&
      requestWrites == 1;
  IOLog("PONG_UFS: storage write path %s by pong_ufs_readwrite boot-arg\n",
        gHost.writable ? "enabled" : "disabled");
  gRootDiagnostic.stage = "controller map";
  gHost.hc = mapPhys(0x01d84000, 0x3000, gHost.hcMap);
  if (!gHost.hc) return transportFailure("controller map");
  gRootDiagnostic.cap = read32(gHost.hc, 0);
  gRootDiagnostic.version = read32(gHost.hc, 8);
  recordTransport(kIOReturnNotReady, 15);
  gRootDiagnostic.stage = "DMA allocation";
  // The concurrent region needs more contiguous DMA memory than the single slot did, and a fragmented kernel map can
  // refuse it. Ask for the full 16-slot region A first, then the eight-slot region, and never fail bring-up over it: the
  // single-slot size is the guaranteed fallback and keeps the driver working exactly as before.
  gHost.lock = IOLockAlloc();
  const bool wide = (gRootDiagnostic.cap & 0x01000000) != 0;
  // Three tiers, widest first: the full region A with region B, an eight-slot region A, and the original single slot.
  // The tier that succeeds fixes how many slots come up; the single slot is the guaranteed fallback.
  const uint32_t sizes[3] = { uint32_t(kDmaBytes), uint32_t(kDmaBytesEightSlots), uint32_t(kDmaBytesOneSlot) };
  for (unsigned attempt = 0; attempt < 3 && !gHost.virt; ++attempt) {
    const uint32_t bytes = sizes[attempt];
    IOBufferMemoryDescriptor *dma = IOBufferMemoryDescriptor::inTaskWithOptions(kernel_task,
      IOOptionBits(kIODirectionInOut) | IOOptionBits(kIOMemoryPhysicallyContiguous) | IOOptionBits(kIOMemoryMapperNone), bytes, 4096);
    if (!dma) continue;
    uint8_t *virt = static_cast<uint8_t *>(dma->getBytesNoCopy());
    IOByteCount contiguous = 0;
    uint64_t phys = dma->getPhysicalSegment(0, &contiguous, kIOMemoryMapperNone);
    gRootDiagnostic.dma = phys; gRootDiagnostic.contiguous = contiguous;
    if (!virt || !phys || (phys & 4095) || contiguous < bytes || (!wide && phys + bytes > 0x100000000ULL)) {
      dma->release();
      continue;
    }
    gHost.dma = dma; gHost.virt = virt; gHost.phys = phys; gHost.dmaBytes = bytes;
  }
  if (!gHost.virt || !gHost.lock) return transportFailure("DMA address/contiguity");
  // What the allocation actually granted decides the slot count: full region A, eight, or the original single slot.
  const unsigned entries = (gRootDiagnostic.cap & 0x1f) + 1;
  unsigned slots;
  if (gHost.dmaBytes >= uint32_t (kDmaBytes)) slots = kRegionSlots;
  else if (gHost.dmaBytes >= uint32_t (kDmaBytesEightSlots)) slots = 8;
  else slots = 1;
  if (slots > entries) slots = entries;
  if (slots > kRegionSlots) slots = kRegionSlots;
  hostSlotGeometryRegionA (slots);
  hostSlotsInit (slots, gHost.lock);
  native_ufs_slots = gSlotCount;
  IOLog("PONG_UFS: %u command slot(s), DMA region %u bytes, controller entries %u\n", gSlotCount, gHost.dmaBytes, entries);
  bzero(gHost.virt, gHost.dmaBytes); cacheCivac(gHost.virt, gHost.dmaBytes);
  gRootDiagnostic.stage = "quiesce firmware queue";
  const char *why = nullptr;
  if (!hostStopQueue(&why)) return transportFailure(why);
  gRootDiagnostic.stage = "SMMU plan";
  gHost.smmu = mapPhys(0x15000000, 0x100000, gHost.smmuMap);
  if (!gHost.smmu) return transportFailure("SMMU map");
  auto read = [](unsigned offset) { return read32(gHost.smmu, offset); };
  UfsSmmuPlan plan = planUfsSmmu(0xe0, gHost.phys, gHost.dmaBytes, read, 78, 120);
  gRootDiagnostic.smmuId1 = read(0x24); gRootDiagnostic.smmuId2 = read(0x28);
  gRootDiagnostic.smmuSlot = plan.slot; gRootDiagnostic.smr = plan.smr; gRootDiagnostic.s2cr = plan.s2cr;
  unsigned rawBanks = gRootDiagnostic.smmuId1 & 255, rawGroups = read(0x20) & 255;
  IOLog("PONG_UFS: SMMU id0=%08x id1=%08x id2=%08x HW banks=%u groups=%u effective banks=%u groups=%u\n",
        read(0x20), gRootDiagnostic.smmuId1, gRootDiagnostic.smmuId2, rawBanks, rawGroups,
        rawBanks < 78 ? rawBanks : 78, rawGroups < 120 ? rawGroups : 120);
  if (plan.error) return transportFailure(plan.error);
  IOLog("PONG_UFS: SID e0 slot=%u firmware-bank=%u target-bank=%u action=%s\n",
        plan.slot, plan.previousBank, plan.bank,
        plan.migrate ? "migrate exact firmware mapping" : plan.reuse ? "reuse bypass" : "install exact mapping");
  gHost.cb = gHost.smmu + (plan.pages + plan.bank) * 4096;
  gRootDiagnostic.stage = "SMMU stream configuration";
  why = configureUfsSmmu(plan, 0xe0, read, [](unsigned offset, uint32_t value) { write32(gHost.smmu, offset, value); });
  gRootDiagnostic.smr = read(0x800 + 4 * plan.slot); gRootDiagnostic.s2cr = read(0xc00 + 4 * plan.slot);
  gRootDiagnostic.cbar = read(0x1000 + 4 * plan.bank); gRootDiagnostic.cba2r = read(0x1800 + 4 * plan.bank);
  gRootDiagnostic.sctlr = read32(gHost.cb, 0);
  if (why) return transportFailure(why);
  {
    // The zero-copy PRDT path may only point at pages the storage stream can reach. The SMMU stays in bypass, so the
    // bound is the smallest of its three IDR2 address sizes (and 32 bits when the controller lacks 64-bit addressing).
    uint64_t limit = wide ? ~0ULL : 0x100000000ULL;
    const uint32_t idr2 = gHost.smmu ? read32(gHost.smmu, 0x28) : 0;
    for (unsigned shift = 0; shift <= 8; shift += 4) {
      const unsigned bits = ufsSmmuAddressBits((idr2 >> shift) & 15);
      const uint64_t width = bits ? (bits >= 64 ? ~0ULL : 1ULL << bits) : 0;
      if (width < limit) limit = width;
    }
    gDmaLimit = limit;
  }
  // The request list form must be final before the controller is told where the list is: hostStartQueue programs
  // UTRLBA from gUtrlPhys, and the geometry decides which entry each slot rings. Best-effort: any allocation that fails
  // leaves the smaller geometry that already works.
  hostSlotsUpgrade (gSlotCount, entries, (gRootDiagnostic.cap & 0x01000000) != 0);
  gRootDiagnostic.stage = "request list start";
  if (!hostStartQueue(&why)) return transportFailure(why);
  gRootDiagnostic.stage = "NOP OUT";
  if (hostNop() != kIOReturnSuccess) return transportFailure("NOP OUT");
  uint32_t power = 0, scsi = 0;
  gRootDiagnostic.stage = "power mode query";
  if (hostQueryRead(3, 2, &power) != kIOReturnSuccess) return transportFailure("power mode query");
  gRootDiagnostic.power = power;
  if ((power & 0xff) != 0x11) {
    gRootDiagnostic.stage = "wake device";
    uint8_t ssu[6] = {0x1b, 0, 0, 0, 0x10, 0};
    if (hostScsi(0xd0, ssu, 6, false, 0, 500000, &scsi) != kIOReturnSuccess) return transportFailure("START STOP UNIT");
    IOSleep(50);
  }
  gRootDiagnostic.stage = "LUN 0 ready";
  for (unsigned attempt = 0; attempt < 20 && !gHost.poisoned; ++attempt) {
    uint8_t tur[6] = {};
    if (hostScsi(0, tur, 6, false, 0, 200000, &scsi) == kIOReturnSuccess) { gHost.ready = true; break; }
    IOSleep(10);
  }
  if (!gHost.ready) return transportFailure("LUN 0 not ready");
  // The LUN answers, so the controller is fully up and every bring-up command (which runs on slot 0) is done: turn on
  // completion interrupts. Best-effort; a failure leaves the polled configuration that already works.
  hostEnableInterrupt ();
  gRootDiagnostic.stage = "READ CAPACITY";
  uint8_t capacity[10] = {0x25};
  if (hostScsi(0, capacity, 10, true, 8, 200000, &scsi) != kIOReturnSuccess) return transportFailure("READ CAPACITY");
  uint32_t last = loadBe32(gHost.virt + kDataOffset), blockSize = loadBe32(gHost.virt + kDataOffset + 4);
  if (!last || last == 0xffffffff || blockSize != 4096) return transportFailure("unsupported LUN geometry");
  gHost.blocks = uint64_t(last) + 1;
  IOLog("PONG_UFS: transport ready LUN=0 block=4096 blocks=%llu; WRITE(10) FUA=%s; writes stay inside declared SHNGROOT windows\n",
        gHost.blocks, gHost.writable ? "enabled" : "disabled");
  return true;
}
}

class PongUfsBlock : public IOBlockStorageDevice {
  OSDeclareDefaultStructors(PongUfsBlock)
  // Each in-flight request owns one bounce buffer, so concurrent requests never share a payload. kDataMax-sized so one
  // request reaches the driver as one command instead of a chain of 4 KiB ones.
  static constexpr unsigned kBounces = 4;
  uint8_t *bounces[kBounces] = {};
  uint32_t bounceFree = 0;
  IOLock *windowLock = nullptr;
  bool online = false;
  RootDiskWindow window = {};
public:
  bool init(OSDictionary *properties, const RootDiskWindow &selected);
  bool start(IOService *provider) override;
  void free() override;
  IOReturn doEjectMedia() override { return kIOReturnUnsupported; }
  IOReturn doFormatMedia(UInt64) override { return kIOReturnNotWritable; }
  UInt32 doGetFormatCapacities(UInt64 *, UInt32) const override { return 0; }
  char *getVendorString() override { return const_cast<char *>("Pong"); }
  char *getProductString() override { return const_cast<char *>(window.product); }
  char *getRevisionString() override { return const_cast<char *>("1"); }
  char *getAdditionalDeviceInfoString() override { return const_cast<char *>(window.name); }
  IOReturn reportBlockSize(UInt64 *v) override { *v = kRootLogicalBlock; return kIOReturnSuccess; }
  IOReturn reportMaxValidBlock(UInt64 *v) override { *v = window.size / kRootLogicalBlock - 1; return kIOReturnSuccess; }
  IOReturn reportEjectability(bool *v) override { *v = false; return kIOReturnSuccess; }
  IOReturn reportRemovability(bool *v) override { *v = false; return kIOReturnSuccess; }
  IOReturn reportWriteProtection(bool *v) override {
    *v = !gHost.writable || (window.baseByte & 4095) || (window.size & 4095);
    return kIOReturnSuccess;
  }
  IOReturn reportMediaState(bool *v, bool *changed) override { *v = online && gHost.ready; if (changed) *changed = false; return kIOReturnSuccess; }
  IOReturn doSynchronizeCache() override { return hostSyncCache(); }
  IOReturn doSynchronize(UInt64, UInt64, IOOptionBits) override { return doSynchronizeCache(); }
  IOReturn getWriteCacheState(bool *v) override { *v = false; return kIOReturnSuccess; }
  IOReturn setWriteCacheState(bool) override { return kIOReturnNotWritable; }
  IOReturn doAsyncReadWrite(IOMemoryDescriptor *, UInt64, UInt64, IOStorageAttributes *, IOStorageCompletion *) override;
  // Take/give a bounce buffer from the per-device pool; concurrent callers of doAsyncReadWrite each hold their own.
  uint8_t *takeBounce();
  void giveBounce(uint8_t *buffer);
};
OSDefineMetaClassAndStructors(PongUfsBlock, IOBlockStorageDevice)

// If an expected APFS volume is absent, list only IOMedia objects beneath the
// selected UFS window. This keeps the failure report specific to the
// SystemOS image and reveals whether the UUID, the volume, or its ancestry is
// the mismatch.
static unsigned native_pong_log_ufs_window_media(const char *windowKey) {
  OSDictionary *matching = IOService::serviceMatching("IOMedia");
  OSIterator *iterator = matching ? IOService::getMatchingServices(matching) : nullptr;
  OSSafeReleaseNULL(matching);
  if (!iterator) {
    IOLog("PONG APFS: window media enumeration unavailable window=%s\n", windowKey);
    return 0;
  }

  unsigned candidates = 0;
  while (OSObject *object = iterator->getNextObject()) {
    IOService *media = OSDynamicCast(IOService, object);
    if (!media) continue;

    bool targetWindow = false;
    bool readOnlyWindow = false;
    bool writableWindow = false;
    unsigned depth = 0;
    for (IOService *provider = media; provider && depth < 64;
         provider = provider->getProvider(), ++depth) {
      PongUfsBlock *block = OSDynamicCast(PongUfsBlock, provider);
      if (!block) continue;
      targetWindow = block->getProperty(windowKey) == kOSBooleanTrue;
      readOnlyWindow = block->getProperty("PongReadOnly") == kOSBooleanTrue;
      writableWindow = block->getProperty("PongWritable") == kOSBooleanTrue;
      break;
    }
    if (!targetWindow) continue;

    ++candidates;
    OSString *uuid = OSDynamicCast(OSString, media->getProperty("UUID"));
    OSString *name = OSDynamicCast(OSString, media->getProperty(kIOBSDNameKey));
    IOLog("PONG APFS: window media uuid=%s bsd=%s readonly=%d writable=%d depth=%u\n",
          uuid ? uuid->getCStringNoCopy() : "?",
          name ? name->getCStringNoCopy() : "?", readOnlyWindow, writableWindow, depth);
  }
  iterator->release();
  IOLog("PONG APFS: window media count=%u window=%s\n", candidates, windowKey);
  return candidates;
}

// Development APFS handoff: resolve a unique APFS IOMedia by its observed
// volume UUID and prove that it descends from the matching SHNGROOT UFS window.
// This is device ancestry, not cryptographic image authentication.
extern "C" int native_pong_ufs_volume_device(const char *uuid, int kind,
                                               dev_t *device, char *path, size_t pathSize) {
  if (!uuid || strlen(uuid) != 36 || !device || !path || pathSize < 8 || kind<0 || kind>2) return 0;
  const char *windowName=kind==2?"Data":kind==1?"SystemOS":"OS";
  const char *windowKey=kind==2?"PongDataWindow":kind==1?"PongSystemOSWindow":"PongRootWindow";
  *device = NODEV;
  path[0] = 0;

  OSDictionary *matching = IOService::serviceMatching("IOMedia");
  OSDictionary *properties = OSDictionary::withCapacity(1);
  OSString *wanted = OSString::withCString(uuid);
  if (!matching || !properties || !wanted) {
    OSSafeReleaseNULL(wanted);
    OSSafeReleaseNULL(properties);
    OSSafeReleaseNULL(matching);
    return 0;
  }
  bool ready = properties->setObject("UUID", wanted) &&
      matching->setObject("IOPropertyMatch", properties);
  wanted->release();
  properties->release();
  OSIterator *iterator = nullptr;
  if (ready && kind) {
    IOLog("PONG APFS: wait for %s UUID %.36s, timeout=5s\n", windowName,uuid);
    auto published = IOService::waitForMatchingService(matching, 5ULL * 1000000000ULL);
    if (published) {
      IOLog("PONG APFS: %s UUID appeared; rechecking IOMedia\n",windowName);
      iterator = IOService::getMatchingServices(matching);
    } else {
      IOLog("PONG APFS: %s UUID wait timed out\n",windowName);
    }
  } else if (ready) {
    iterator = IOService::getMatchingServices(matching);
  }
  matching->release();
  if (!iterator) {
    IOLog("PONG APFS: UUID lookup unavailable uuid=%.36s window=%s\n", uuid,
          windowName);
    if (kind) native_pong_log_ufs_window_media(windowKey);
    return 0;
  }

  unsigned matches = 0;
  bool accepted = false;
  dev_t selected = NODEV;
  char selectedPath[64] = {};
  while (OSObject *object = iterator->getNextObject()) {
    IOService *media = OSDynamicCast(IOService, object);
    if (!media) continue;
    ++matches;
    if (matches != 1) { accepted = false; break; }
    OSString *identity = OSDynamicCast(OSString, media->getProperty("UUID"));
    OSString *name = OSDynamicCast(OSString, media->getProperty(kIOBSDNameKey));
    OSNumber *major = OSDynamicCast(OSNumber, media->getProperty(kIOBSDMajorKey));
    OSNumber *minor = OSDynamicCast(OSNumber, media->getProperty(kIOBSDMinorKey));
    if (!identity || strcmp(identity->getCStringNoCopy(), uuid) || !name || !major || !minor ||
        !name->getLength() || name->getLength() >= sizeof(selectedPath) - 6 ||
        name->getLength() >= pathSize - 6 || major->unsigned64BitValue() > 255 ||
        minor->unsigned64BitValue() > 0xffffff) {
      IOLog("PONG APFS: UUID candidate malformed uuid=%.36s identity=%d bsd=%d major=%d minor=%d\n",
            uuid, identity != nullptr, name != nullptr, major != nullptr, minor != nullptr);
      continue;
    }

    bool validWindow = false;
    bool foundUfsWindow = false;
    unsigned depth = 0;
    for (IOService *provider = media; provider && depth < 64;
         provider = provider->getProvider(), ++depth) {
      PongUfsBlock *block = OSDynamicCast(PongUfsBlock, provider);
      if (!block) continue;
      foundUfsWindow = true;
      validWindow = block->getProperty(windowKey) == kOSBooleanTrue &&
          block->getProperty("PongUfsWindow") == kOSBooleanTrue;
      if(kind==2) {
        validWindow=validWindow && block->getProperty("PongWritable")==kOSBooleanTrue &&
            media->getProperty(kIOMediaWritableKey)==kOSBooleanTrue;
      }
      break;
    }
    if (!validWindow) {
      IOLog("PONG APFS: UUID candidate rejected uuid=%.36s bsd=%s ufs-window=%d depth=%u window=%s\n",
            uuid, name->getCStringNoCopy(), foundUfsWindow, depth,
            windowName);
      continue;
    }

    selected = static_cast<dev_t>(makedev(major->unsigned32BitValue(), minor->unsigned32BitValue()));
    snprintf(selectedPath, sizeof(selectedPath), "/dev/%s", name->getCStringNoCopy());
    accepted = true;
  }
  iterator->release();
  if (!accepted || matches != 1) {
    IOLog("PONG APFS: UUID lookup miss wanted=%.36s matches=%u accepted=%d window=%s\n",
          uuid, matches, accepted, windowName);
    if (kind) native_pong_log_ufs_window_media(windowKey);
    return 0;
  }
  *device = selected;
  strlcpy(path, selectedPath, pathSize);
  IOLog("PONG APFS: UUID %.36s bound to %s UFS window %s\n", uuid,
        windowName, selectedPath);
  return 1;
}

extern "C" int native_pong_ufs_data_volume_device(const char *uuid,dev_t *device,
    char *path,size_t pathSize,uint64_t *bytes) {
  if(!bytes)return 0;
  *bytes=0;
  if(!native_pong_ufs_volume_device(uuid,2,device,path,pathSize))return 0;
  for(unsigned i=0;i<gRootWindowCount;++i)if(!strcmp(gRootWindows[i].name,"Data")) {
    *bytes=gRootWindows[i].size;
    gHost.readTrace = true;
    gHost.readTraceCount = 0;
    IOLog("K60RD trace armed for Data mount\n");
    return 1;
  }
  return 0;
}

bool PongUfsBlock::init(OSDictionary *properties, const RootDiskWindow &selected) {
  if (!selected.name || !selected.product || !selected.signature || !selected.size ||
      (selected.baseByte & 4095) || (selected.size & 511) ||
      !IOBlockStorageDevice::init(properties)) return false;
  window = selected;
  return true;
}
bool PongUfsBlock::start(IOService *provider) {
  windowLock = IOLockAlloc();
  for (unsigned k = 0; k < kBounces; ++k) {
    bounces[k] = static_cast<uint8_t *>(IOMallocAligned(kDataMax, 4096));
    if (!bounces[k]) return false;
    bounceFree |= 1U << k;
  }
  if (!windowLock || !gHost.ready || !window.size || !IOBlockStorageDevice::start(provider)) return false;
  gRootDiagnostic.stage = "first root read";
  uint8_t *probe = takeBounce();
  const IOReturn first = hostRead4k(0, window.baseByte / 4096, 1, probe);
  const bool matched = first == kIOReturnSuccess &&
      !memcmp(probe + window.signatureOffset, window.signature, strlen(window.signature));
  giveBounce(probe);
  if (first != kIOReturnSuccess) return transportFailure("first root read");
  if (!matched) return transportFailure("SHNGROOT window signature mismatch");
  gRootDiagnostic.first = kPongUserdataFirst4k;
  gRootDiagnostic.last = kPongUserdataLast4k;
  gRootDiagnostic.windowBytes = window.size;
  const bool writableWindow = gHost.writable && !(window.baseByte & 4095) && !(window.size & 4095);
  IOLog("PONG_UFS: SHNGROOT %s first read complete signature=1 base=%llx bytes=%llx; publish 512-byte %s disk\n",
        window.name, window.baseByte, window.size, writableWindow ? "read-write" : "read-only");
  setProperty("PongReadOnly", !writableWindow);
  setProperty("PongWritable", writableWindow);
  setProperty("PongUfsWindow", true);
  setProperty("PongRootWindow", !strcmp(window.name, "OS"));
  setProperty("PongSystemOSWindow", !strcmp(window.name, "SystemOS"));
  setProperty("PongDataWindow", !strcmp(window.name, "Data"));
  setProperty("Physical Interconnect", "UFS");
  online = true; registerService();
  char detail[96];
  snprintf(detail, sizeof(detail), "SHNGROOT %s disk published", window.name);
  PongProbeRecord(4, "ufs-transport", PongProbePass, detail, window.size);
  return true;
}
uint8_t *PongUfsBlock::takeBounce() {
  IOLockLock(windowLock);
  while (!bounceFree) IOLockSleep(windowLock, &bounceFree, THREAD_UNINT);
  const unsigned k = static_cast<unsigned>(__builtin_ctz(bounceFree));
  bounceFree &= ~(1U << k);
  IOLockUnlock(windowLock);
  return bounces[k];
}
void PongUfsBlock::giveBounce(uint8_t *buffer) {
  IOLockLock(windowLock);
  for (unsigned k = 0; k < kBounces; ++k) if (bounces[k] == buffer) bounceFree |= 1U << k;
  IOLockWakeup(windowLock, &bounceFree, true);
  IOLockUnlock(windowLock);
}
void PongUfsBlock::free() {
  for (unsigned k = 0; k < kBounces; ++k) if (bounces[k]) { IOFreeAligned(bounces[k], kDataMax); bounces[k] = nullptr; }
  bounceFree = 0;
  if (windowLock) { IOLockFree(windowLock); windowLock = nullptr; }
  IOBlockStorageDevice::free();
}
IOReturn PongUfsBlock::doAsyncReadWrite(IOMemoryDescriptor *buffer, UInt64 block, UInt64 count,
                                      IOStorageAttributes *, IOStorageCompletion *completion) {
  const uint64_t rootBlocks = window.size / kRootLogicalBlock;
  const bool write = buffer && buffer->getDirection() == kIODirectionOut;
  // Entry trace: the deeper K60UFS write#N line sits after the writable gate, so
  // a rejected write used to leave no trace at all. Log the first eight calls
  // before any gate so "APFS never wrote" and "the gate refused" stay distinct.
  static uint32_t k60WriteCalls;
  const bool k60TraceCall = write && k60WriteCalls < 8;
  if (k60TraceCall) {
    IOLog("K60UFS wcall#%u blk=%llu cnt=%llu len=%llu writable=%d align=%u/%u online=%d ready=%d\n",
          k60WriteCalls, (unsigned long long)block, (unsigned long long)count,
          (unsigned long long)(buffer ? buffer->getLength() : 0),
          gHost.writable ? 1 : 0, (unsigned)(window.baseByte & 4095),
          (unsigned)(window.size & 4095), online ? 1 : 0, gHost.ready ? 1 : 0);
    k60WriteCalls++;
  }
  if (!buffer || !completion || !completion->action || !count || block >= rootBlocks ||
      count > rootBlocks - block || count > UINT64_MAX / kRootLogicalBlock ||
      buffer->getLength() < count * kRootLogicalBlock ||
      (buffer->getDirection() != kIODirectionIn && !write))
    return kIOReturnBadArgument;
  if (write && (!gHost.writable || (window.baseByte & 4095) || (window.size & 4095))) {
    if (k60TraceCall) {
      IOLog("K60UFS wcall#%u rejected NotWritable writable=%d base=%llu size=%llu\n",
            k60WriteCalls - 1, gHost.writable ? 1 : 0,
            (unsigned long long)window.baseByte, (unsigned long long)window.size);
    }
    return kIOReturnNotWritable;
  }
  if (!online || !gHost.ready) return kIOReturnNotReady;
  if (!write && gHost.readTrace && gHost.readTraceCount < 48) {
    IOLog("K60RD #%u blk=%llu cnt=%llu\n", gHost.readTraceCount,
          (unsigned long long)block, (unsigned long long)count);
    gHost.readTraceCount++;
  }
  static uint32_t k60WriteTrace;
  const bool k60TraceWrite = write && k60WriteTrace < 8;
  if (k60TraceWrite) {
    IOLog("K60UFS write#%u blk=%llu cnt=%llu hcs=%x hcsfatal=%x ready=%d poison=%d\n",
          k60WriteTrace, (unsigned long long)block, (unsigned long long)count,
          read32(gHost.hc, 0x58), read32(gHost.hc, 0x20), gHost.ready ? 1 : 0,
          gHost.poisoned ? 1 : 0);
  }
  uint64_t done = 0, bytes = count * kRootLogicalBlock;
  IOReturn result = kIOReturnSuccess;
  // No global lock: every iteration takes its own command slot and its own bounce buffer, so concurrent requests run
  // in parallel on different slots (S2: up to eight).
  uint8_t *bounce = takeBounce();
  while (done < bytes) {
    const uint64_t absolute = window.baseByte + block * kRootLogicalBlock + done;
    const uint32_t inside = static_cast<uint32_t>(absolute & 4095);
    uint64_t wanted = bytes - done;
    if (wanted > kDataMax - inside) wanted = kDataMax - inside;
    uint32_t physicalBlocks = static_cast<uint32_t>((inside + wanted + 4095) / 4096);
    uint64_t available = uint64_t(physicalBlocks) * 4096 - inside;
    uint64_t take = wanted < available ? wanted : available;
    if (write) {
      uint64_t writeStart = absolute & ~UINT64_C(4095);
      uint64_t writeEnd = writeStart + uint64_t(physicalBlocks) * 4096;
      uint64_t windowEnd = window.baseByte + window.size;
      if (writeStart < window.baseByte || writeEnd < writeStart || writeEnd > windowEnd) {
        result = kIOReturnNotWritable;
        break;
      }
    }
    if (!gHost.ready || gHost.poisoned) {
      result = kIOReturnNotReady;
      break;
    }
    // The bounce buffer is private to this request; the command slot is taken inside hostRead4k/hostWrite4k.
    // Full physical-block writes need no read of the old contents.
    if (!write || inside || take != uint64_t(physicalBlocks) * 4096)
      result = hostRead4k(0, absolute / 4096, physicalBlocks, bounce);
    if (result == kIOReturnSuccess) {
      uint8_t *data = bounce + inside;
      uint64_t copied = write ? buffer->readBytes(done, data, take) : buffer->writeBytes(done, data, take);
      if (copied != take) result = kIOReturnUnderrun;
      else if (write) result = hostWrite4k(0, absolute / 4096, physicalBlocks, bounce, true);
    }
    if (result != kIOReturnSuccess) break;
    done += take;
  }
  if (k60TraceWrite) {
    k60WriteTrace++;
    IOLog("K60UFS write#%u -> result=%x done=%llu ready=%d poison=%d\n",
          k60WriteTrace - 1, result, (unsigned long long)done,
          gHost.ready ? 1 : 0, gHost.poisoned ? 1 : 0);
  }
  giveBounce(bounce);
  if (result != kIOReturnSuccess && result != kIOReturnNotWritable)
    transportFailure(write ? "block write failed" : "block read failed");
  completion->action(completion->target, completion->parameter, result, done);
  return kIOReturnSuccess;
}
extern "C" bool pong_ufs_transport_start(IOService *provider) {
  if (gTransportAttempted) {
    IOLog("PONG_UFS: transport attempt already completed; skip duplicate match\n");
    return false;
  }
  gTransportAttempted = true;
  // A built-in transport has no separate kext dependency record. Explicitly
  // start the genuine family and its personalities before using its classes.
  OSReturn loaded = OSKextLoadKextWithIdentifier("com.apple.iokit.IOStorageFamily");
  if (loaded != kOSReturnSuccess) {
    gRootDiagnostic.result = static_cast<uint32_t>(loaded);
    return transportFailure("IOStorageFamily load/start failed");
  }
  loaded = OSKextLoadKextWithIdentifier("com.apple.filesystems.apfs");
  if (loaded != kOSReturnSuccess) {
    gRootDiagnostic.result = static_cast<uint32_t>(loaded);
    return transportFailure("APFS load/start failed");
  }
  // Original prelinked storage metadata must be initialized before allocation.
  OSSharedPtr<const OSSymbol> name(OSSymbol::withCStringNoCopy("IOBlockStorageDevice"), OSNoRetain);
  const OSMetaClass *meta = name ? OSMetaClass::getMetaClassWithName(name.get()) : nullptr;
  if (meta != &IOBlockStorageDevice::gMetaClass)
    return transportFailure("original storage metaclass not registered");
  if (meta->getClassSize() != sizeof(IOBlockStorageDevice) || meta->getSuperClass() != &IOService::gMetaClass)
    return transportFailure("original storage class/parent ABI mismatch");
  if (!hostBringUp()) return false;
  RootLayout layout;
  const char *why = nullptr;
  if (!findRootLayout(&layout, &why)) return transportFailure(why);
  // The geometry is read from the board's own GPT instead of a captured Pong
  // constant: the K60 dual-system layout puts SHNGROOT in a dedicated "unixnu"
  // partition whose first/last LBA differ from Pong's userdata. Only the sanity
  // check against the device capacity remains.
  if (layout.userdataFirst >= layout.userdataLast || layout.userdataLast >= gHost.blocks)
    return transportFailure("root partition geometry outside the device");
  if (layout.manifestStatus) return transportFailure("invalid SHNGROOT manifest/hash/bounds");
  static const struct { const char *name, *product, *signature; unsigned offset; } wanted[] = {
    {"OS", "iOS 16 OS root", "EFI PART", 512},
    {"SystemOS", "iOS 16 SystemOS", "NXSB", 32},
#if XNU_PONG_UFS_DATA
    {"Data", "iOS 16 persistent Data", "EFI PART", 512},
#endif
  };
  gRootWindowCount = 0;
  for (const auto &item : wanted) {
    bool found = false;
    for (uint32_t index = 0; index < layout.windows; ++index) {
      if (strcmp(layout.window[index].name, item.name)) continue;
      if (gRootWindowCount >= 3) return transportFailure("too many SHNGROOT disks");
      gRootWindows[gRootWindowCount++] = {item.name, item.product, item.signature, item.offset,
        layout.userdataFirst * 4096ULL + layout.window[index].offset, layout.window[index].size};
      found = true;
      break;
    }
    if (!found) return transportFailure("required SHNGROOT window missing");
  }
  for (unsigned index = 0; index < gRootWindowCount; ++index) {
    OSSharedPtr<PongUfsBlock> block(new PongUfsBlock, OSNoRetain);
    if (!block || !block->init(nullptr, gRootWindows[index]) || !block->attach(provider))
      return transportFailure("block allocation/attachment");
    if (!block->start(provider)) { block->detach(provider); return transportFailure("block start"); }
  }
  return true;
}
