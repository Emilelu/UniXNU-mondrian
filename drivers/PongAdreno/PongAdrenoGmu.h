/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#ifndef PONG_ADRENO_GMU_H
#define PONG_ADRENO_GMU_H
#include <stddef.h>
#include <stdint.h>
#include "PongAdrenoHfi.h"
#include "PongAdrenoPower.h"
#ifdef __cplusplus
extern "C" {
#endif

/* SM8475/Pong only. These are hardware TCM/buffer extents, not CPU page
 * granules: all backing memory and translations still use native 4 KiB.
 */
enum {PongGpuCore,PongGpuGmu,PongGpuRscc,PongGpuPdc,PongGpuCxMisc,
      PongGpuClock,PongGpuSmmu,PongGpuAo,PongGpuWindowCount};
typedef struct {uint64_t physical;size_t bytes;} PongGpuWindow;
extern const PongGpuWindow PongAdrenoWindows[PongGpuWindowCount];
enum {PongAdrenoChipId=0x07030002,PongAdrenoGmemBytes=0x200000,
      PongAdrenoGpuSid=0,PongAdrenoLpacSid=1,PongAdrenoSecureSid=2,
      PongAdrenoGmuSid=5,PongAdrenoGmuStreamMask=0x400};
/* Device-tree and Mesa profile facts; not an advertised ready GPU device.
 * Mesa names this exact Adreno730v3 revision FD725/A7XX Gen1, so a compiler
 * must keep chip_id intact instead of selecting generic FD730 or A740.
 */
enum {PongAdrenoGpuIrq=332,PongAdrenoHfiIrq=336,PongAdrenoGmuIrq=337,
      PongAdrenoContextBanks=21,PongAdrenoStreamSlots=24,
      PongAdrenoHighestBankBit=16,PongAdrenoTileWidth=64,PongAdrenoTileHeight=32,
      PongAdrenoGmuTimerLow=0x16220,PongAdrenoGmuTimerHigh=0x16224,
      PongAdrenoCxGdscr=0x9108,PongAdrenoCxHwControl=0x953c,
      PongAdrenoGxGdscr=0x905c,PongAdrenoSmmuClockVote=0x7000};
typedef enum {PongGpuSuccess,PongGpuArgument,PongGpuPrerequisite,PongGpuFirmware,
    PongGpuIo,PongGpuBusy,PongGpuTimeout,PongGpuPoisoned} PongGpuStatus;
typedef struct {
    void *cookie;
    /* All callbacks return0 on success, nonzero on failure. */
    /* These must check real power/clocks, owned native4K translations and
     * exclusive ownership, not set a software flag to bypass prerequisites. */
    int (*platform_ready)(void *);
    int (*read32)(void *,unsigned window,size_t byte_offset,uint32_t *);
    int (*write32)(void *,unsigned window,size_t byte_offset,uint32_t);
    int (*barrier)(void *);
    int (*publish)(void *,void *owned_cpu,size_t bytes);
    int (*now_us)(void *,uint64_t *);
    int (*wait_us)(void *,unsigned);
} PongGpuOps;
typedef struct {volatile uint32_t *cpu;size_t bytes;uint32_t iova;} PongGpuMemory;
typedef struct {
    uint32_t chip_id;
    const uint8_t *firmware;size_t firmware_bytes;
    PongGpuMemory cache,dummy,hfi,log;
} PongGpuGmuConfig;
typedef struct {
    PongGpuOps io;PongAdrenoHfi hfi;
    unsigned attempted,poisoned,fw_ready,hfi_ready,power_attempted,power_started,gpu_held;
    /* The two indices the startup vote used (GX level and DDR level). Kept so a later
     * GX_BW_PERF_VOTE can raise the GPU level without rebuilding the tables, which need
     * the power inputs that are only available during startup. */
    unsigned perf_gpu_index,perf_bus_index,perf_votes;
} PongGpuGmuDevice;
typedef struct {
    unsigned phase,writes,fw_ready,hfi_ready,resources_must_retain;
    uint32_t last_register,last_value;
    uint32_t core_version,hfi_version;
} PongGpuGmuResult;

/* A real, one-shot loader for an ALREADY owned/powered/mapped Pong GMU.
 * It programs Pong's RSC/PDC, uploads its firmware into real cache/TCM,
 * starts CM3, then waits for fresh firmware/HFI readiness. It does NOT
 * establish regulator votes, SMMU mappings, ZAP authorization, CP execution
 * or a Metal device. There is no IOKit personality/automatic boot entry.
 * Failure after a write attempts reset, poisons the device and retains DMA
 * backing. Only a later hardware quiesce can authorize release.
 */
PongGpuStatus PongAdrenoGmuStart(PongGpuGmuDevice *,const PongGpuGmuConfig *,PongGpuGmuResult *);
typedef struct {
    unsigned phase,published,acknowledged,polls,resources_must_retain;
    uint32_t command,header,firmware_error;
    PongAdrenoHfiStatus transport;
} PongGpuPowerResult;
/* Exact gen7-4-0 cold-start handshake after actual GMU/HFI readiness:
 * PERF -> BW -> CORE_FW_START -> default blocking GX/BW vote. This differs
 * from Sheng's extra START message. ACD/BCL/IFPC are left disabled until
 * their AOP/power prerequisites exist; no A740 feature table is reused.
 * Only actual matching ACKs advance state. Elapsed time and poll counts
 * are bounded, and an uncertain attempt poisons/retains the session.
 * Success is GMU power protocol startup, not CP execution or acceleration.
 */
PongGpuStatus PongAdrenoGmuStartPower(PongGpuGmuDevice *,const PongPowerInputs *,PongGpuPowerResult *);
/* Vendor gen7_gpu_boot: fresh OOB_GPU acknowledgement followed by START10.
 * Keep OOB held while this port has no idle/slumber/resume owner. */
PongGpuStatus PongAdrenoGmuHoldGpu(PongGpuGmuDevice *,PongGpuPowerResult *);
/* Runtime GPU DCVS, after the power handshake: the CX GMU busy counter (19.2 MHz
 * ticks while the GPU is busy) and the HFI GX_BW_PERF_VOTE (id 30) that the
 * start vote already uses. Ported from UniXNU-zizhan's PongAdrenoGmu.c, itself
 * from Linux a6xx_hw_init/gen7_start. Only a DCVS owner calls these; a refused
 * vote leaves the HFI request pending, so the caller must stop voting.
 */
PongGpuStatus PongAdrenoGmuEnableBusyCounter(PongGpuGmuDevice *);
PongGpuStatus PongAdrenoGmuBusyTicks(PongGpuGmuDevice *,uint64_t *ticks);
PongGpuStatus PongAdrenoGmuSetLevel(PongGpuGmuDevice *,unsigned gpu_index,
    unsigned bus_index,uint32_t *firmware_error);
/* Another GPU level on the running GMU -- the same GX_BW_PERF_VOTE (HFI 30) the startup
 * vote uses, exactly as Linux's a6xx_gmu_set_freq does for a non-legacy GMU. Valid only
 * after the GX is up (PongAdrenoGmuHoldGpu succeeded). The DDR level is not changed: this
 * raises the GPU's own level and leaves the bandwidth vote as startup set it. */
PongGpuStatus PongAdrenoGmuVotePerf(PongGpuGmuDevice *,unsigned gpu_index,PongGpuPowerResult *);
#ifdef __cplusplus
}
#endif
#endif
