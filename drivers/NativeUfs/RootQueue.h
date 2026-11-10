// SPDX-License-Identifier: BSD-2-Clause-Patent
// Root queue takeover; shared with the host fault-injection harness.
//
// STAGE S3: the request list is a page of its own (gUtrlPhys, a write-combined 4 KiB allocation) instead of region A's
// offset 0, so all 32 entries serve (slot s on entry s) and no cache maintenance touches the list. Until the page exists
// gUtrlPhys is 0 and the list address stays region A, which is exactly what S1/S2 did.
static uint64_t gUtrlPhys = 0;

static bool hostWaitRegister (unsigned offset, uint32_t mask, uint32_t value)
{
  uint64_t deadline;
  clock_interval_to_deadline (100, kMillisecondScale, &deadline);
  unsigned polls = 0;
  do {
    if ((read32 (gHost.hc, offset) & mask) == value) return true;
    IODelay (10);
  } while (++polls < 10000 && mach_absolute_time () < deadline);
  return false;
}

static bool hostStopQueue (const char **why)
{
  // Confirm the firmware has no active transfer/task before changing its
  // request list or the storage stream's SMMU routing.
  if (!(read32 (gHost.hc, 0x34) & 1) || (read32 (gHost.hc, 0x30) & 0x0f) != 0x0f) {
    recordTransport (kIOReturnNotReady, 15);
    *why = "controller not ready for takeover";
    return false;
  }
  if (read32 (gHost.hc, 0x58) || read32 (gHost.hc, 0x78)) {
    recordTransport (kIOReturnBusy, 15);
    *why = "firmware request outstanding";
    return false;
  }
  if (read32 (gHost.hc, 0x20) & kUfsFatalStatus) {
    recordTransport (kIOReturnIOError, 15);
    *why = "firmware controller error";
    return false;
  }
  hostWrite (0x24, 0);
  hostWrite (0x60, 0);
  if (!hostWaitRegister (0x60, 1, 0)) {
    recordTransport (kIOReturnTimeout, 15);
    *why = "request list stop";
    return false;
  }
  return true;
}

static bool hostStartQueue (const char **why)
{
  // S3: our own write-combined list page when it was allocated, else region A's offset 0 as before.
  const uint64_t base = gUtrlPhys ? gUtrlPhys : gHost.phys;
  hostWrite (0x50, static_cast<uint32_t> (base));
  hostWrite (0x54, static_cast<uint32_t> (base >> 32));
  if (read32 (gHost.hc, 0x50) != uint32_t (base) || read32 (gHost.hc, 0x54) != uint32_t (base >> 32)) {
    recordTransport (kIOReturnIOError, 15);
    *why = "request list address";
    return false;
  }
  gRootDiagnostic.isBefore = read32 (gHost.hc, 0x20);
  hostWrite (0x20, gRootDiagnostic.isBefore);
  hostWrite (0x60, 1);
  if (!hostWaitRegister (0x60, 1, 1) || !hostWaitRegister (0x30, 3, 3)) {
    recordTransport (kIOReturnTimeout, 15);
    *why = "request list ready";
    return false;
  }
  return true;
}
