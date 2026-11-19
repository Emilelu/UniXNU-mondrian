/* SPDX-License-Identifier: BSD-2-Clause-Patent
 * Copyright (c) 2026, UniXNU contributors.
 *
 * Host harness for the K60 GIC SPI ownership code in drivers/ArmCpu/ArmCpu.cpp.
 * The checker splits this file on the extract marker, splices the production
 * fragment in and compiles the result. Part A stands in for the IOKit and
 * distributor helpers the fragment expects; part B exercises the fragment.
 */

#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <thread>
#include <vector>

typedef int IOReturn;
enum {
  kIOReturnSuccess = 0,
  kIOReturnNotReady = 1,
  kIOReturnBadArgument = 2,
  kIOReturnExclusiveAccess = 3,
  kIOReturnNoResources = 4,
  kIOReturnTimeout = 5,
  kIOReturnNotFound = 6,
  kIOReturnNotPermitted = 7,
  kIOReturnBusy = 8,
};

static uint32_t gMemory[0x10000 / 4];
static uintptr_t gExpectedBase;
static unsigned gWrites;
static unsigned gChecks;

volatile uint32_t armcpu_gic_ready = 1;

static void fail(const char *what)
{
  fprintf(stderr, "FAIL %s\n", what);
  exit(1);
}

static void ok(bool condition, const char *what)
{
  gChecks++;
  if (!condition) fail(what);
}

static uint32_t read32(uintptr_t base, unsigned offset)
{
  if (base != gExpectedBase || offset >= sizeof(gMemory)) fail("read32 outside the distributor");
  return gMemory[offset / 4];
}

static void write32(uintptr_t base, unsigned offset, uint32_t value)
{
  if (base != gExpectedBase || offset >= sizeof(gMemory)) fail("write32 outside the distributor");
  gWrites++;
  if (offset >= 0x100 && offset < 0x180) gMemory[offset / 4] |= value;        /* ISENABLER */
  else if (offset >= 0x180 && offset < 0x200) gMemory[offset / 4] &= ~value; /* ICENABLER */
  else if (offset >= 0x280 && offset < 0x300) gMemory[offset / 4] |= value;  /* ISACTIVER */
  else gMemory[offset / 4] = value;
}

static bool waitClear(uintptr_t base, unsigned offset, uint32_t bits)
{
  return !(read32(base, offset) & bits);
}

/* ArmCpu.cpp carries the platform sleep hook beside the SPI owners, so the
   fragment names two sleep types. The model needs them complete, not their
   behaviour. */
struct armcpu_sleep_board {
    void (*prepare)(void);
    int (*should_wake)(uint32_t);
    void (*restore)(void);
    const uint32_t *wake_spis;
    uint32_t wake_spi_count;
    void (*tick)(void);
    uint32_t tick_s;
};
struct armcpu_sleep_stats {
    uint32_t phase, entries, spurious, last_intid, last_reason, cpu_off_failures;
    uint64_t asleep_ticks;
    uint32_t masked, ticks, unarmed;
};

/* @@EXTRACT@@ */

static unsigned gHits;

static void hit(void *context)
{
  (void)context;
  ++gHits;
}

static void reset(void)
{
  for (unsigned i = 0; i < sizeof(gMemory) / 4; i++) gMemory[i] = 0;
  gMemory[1] = 31;                 /* GICD_TYPER: 32 * (31 + 1) = 1024 lines */
  gSpiUsed = 0;
  gSpiRegistering = 0;
  gDist = gExpectedBase;
  gBootAffinity = 0x80000000ULL;
  gWrites = 0;
  gHits = 0;
  armcpu_gic_ready = 1;
}

int main(void)
{
  gExpectedBase = reinterpret_cast<uintptr_t>(gMemory);

  /* A cold attach enables the line, records the owner and programs the router. */
  reset();
  uint32_t readback = 0;
  uint64_t router = 0;
  ok(armcpu_spi_attach(619, false, hit, &gHits, &readback, &router) == kIOReturnSuccess,
     "619 attaches on a cold distributor");
  ok(gSpiUsed == 1 && gSpi[0].id == 619, "the owner table records 619");
  ok((readback & 3) == 3, "readback reports enabled and unmasked");
  ok(router == 0x80000000ULL, "the router target is the boot affinity");
  ok(gMemory[0x100 / 4 + (619 / 32)] & (1u << (619 % 32)), "GICD_ISENABLER holds the line");
  ok(!(gMemory[0x180 / 4 + (619 / 32)] & (1u << (619 % 32))), "GICD_ICENABLER was written to clear");
  ok(reinterpret_cast<uint8_t *>(gMemory)[0x400 + 619] == 0xa0,
     "the priority byte is 0xa0");
  ok(gMemory[0x6000 / 4 + 2 * 619] == 0x80000000u, "GICD_IROUTER is written low word first");

  /* The edge flag lands in the two-bit config field, shift (n % 16) * 2 + 1. */
  reset();
  ok(armcpu_spi_attach(620, true, hit, &gHits, nullptr, nullptr) == kIOReturnSuccess,
     "620 attaches as an edge source");
  ok((gMemory[(0xc00 + (620 / 16) * 4) / 4] >> ((620 % 16) * 2 + 1)) & 1u,
     "the edge bit is set for 620");
  reset();
  ok(armcpu_spi_attach(620, false, hit, &gHits, nullptr, nullptr) == kIOReturnSuccess,
     "620 attaches as a level source");
  ok(!((gMemory[(0xc00 + (620 / 16) * 4) / 4] >> ((620 % 16) * 2 + 1)) & 1u),
     "the edge bit is clear for a level source");

  /* Duplicate, reserved and out-of-range INTIDs are refused, not aliased. */
  reset();
  ok(armcpu_spi_attach(619, false, hit, &gHits, nullptr, nullptr) == kIOReturnSuccess,
     "the first owner of 619 wins");
  ok(armcpu_spi_attach(619, false, hit, &gHits, nullptr, nullptr) == kIOReturnExclusiveAccess,
     "a second owner of 619 is refused");
  ok(gSpiUsed == 1, "a refused attach does not consume a slot");
  ok(armcpu_spi_attach(27, false, hit, &gHits, nullptr, nullptr) == kIOReturnBadArgument,
     "an SGI/PPI number is refused");
  ok(armcpu_spi_attach(1020, false, hit, &gHits, nullptr, nullptr) == kIOReturnBadArgument,
     "1020 is refused");
  ok(armcpu_spi_attach(1024, false, hit, &gHits, nullptr, nullptr) == kIOReturnBadArgument,
     "a line past GICD_TYPER is refused");
  ok(armcpu_spi_attach(619, false, nullptr, nullptr, nullptr, nullptr) == kIOReturnNotReady,
     "a null handler is refused");

  /* Four slots, then kIOReturnNoResources; the GIC is left as it was. */
  reset();
  for (uint32_t i = 0; i < 4; i++)
    ok(armcpu_spi_attach(600 + i, false, hit, &gHits, nullptr, nullptr) == kIOReturnSuccess,
       "the four published slots fill");
  ok(gSpiUsed == 4, "all four slots are used");
  ok(armcpu_spi_attach(604, false, hit, &gHits, nullptr, nullptr) == kIOReturnNoResources,
     "a fifth owner is refused");
  ok(gSpiUsed == 4, "the refusal does not grow the table");

  /* The distributor must be up before anything is programmed. */
  reset();
  gDist = 0;
  ok(armcpu_spi_attach(619, false, hit, &gHits, nullptr, nullptr) == kIOReturnNotReady,
     "an unmapped distributor is refused");
  reset();
  armcpu_gic_ready = 0;
  ok(armcpu_spi_attach(619, false, hit, &gHits, nullptr, nullptr) == kIOReturnNotReady,
     "an unready GIC is refused");

  /* The registering flag serialises concurrent attaches: no slot is lost and
   * no owner is duplicated. */
  reset();
  const unsigned threads = 8;
  std::vector<IOReturn> results(threads, kIOReturnSuccess);
  std::vector<std::thread> pool;
  for (unsigned i = 0; i < threads; i++)
    pool.emplace_back([i, &results] {
      results[i] = armcpu_spi_attach(700 + i, false, hit, &gHits, nullptr, nullptr);
    });
  for (auto &thread : pool) thread.join();
  unsigned accepted = 0;
  for (unsigned i = 0; i < threads; i++) {
    ok(results[i] == kIOReturnSuccess || results[i] == kIOReturnBusy ||
       results[i] == kIOReturnNoResources,
       "a racing attach returns a defined code");
    if (results[i] == kIOReturnSuccess) accepted++;
  }
  ok(accepted == gSpiUsed, "every success owns exactly one slot");
  for (uint32_t i = 0; i < gSpiUsed; i++)
    for (uint32_t j = i + 1; j < gSpiUsed; j++)
      ok(gSpi[i].id != gSpi[j].id, "no INTID is published twice");

  printf("bluetooth-gic-shared: OK (%u assertion(s), %u write(s))\n", gChecks, gWrites);
  return 0;
}
