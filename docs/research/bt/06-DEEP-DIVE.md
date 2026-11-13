# 06 — Deep dive: the staged QCA6490 Bluetooth code, line by line

Status: reviewed 2026-11-13. Scope: what is already in `main` under
`patches/xnu/0500`-`0502b` (the `bsd/dev/qbt_k60.c` backend plus the vendored QcaBluetooth
core), read against (a) the locked mainline GENI sources, (b) the official QcaBluetooth
component and (c) the K60 vendor `btpower.c`/`hci_qca.c`. This is the ⑥ deep dive of
`docs/research/EIGHT-STEPS.toml`; it does not build or run anything.

The file under review is `bsd/dev/qbt_k60.c` **as created by `patches/xnu/0500`**:
1249 lines, sha256 `8451c8706ecf75a79fba49ba7e3bda769ee73fcac5f357a46c9d484df3878748`.
Line numbers below are for that exact extract. It is **not** the older copy in
`/mnt/e/k60-work/impl/bt/bsd/dev/qbt_k60.c` (sha256 `9b506121…`), which predates the stage
gating added before `main` was frozen at `f119a80`.

Reference copies used for every claim: `docs/research/bt/evidence/linux-geni-se-v6.6.h`,
`linux-qcom-geni-se-v6.6.c`, `linux-qcom_geni_serial-v6.6.c`, `clk-rcg2.c`, `clk-branch.h`,
`k60-android-btpower.c`, `k60-android-hci_qca.c`, plus the official component at
`E:/hackios/QcaBluetooth/src/qbt_geni.c` / `src/qbt_geni_regs.h` and
`docs/porting/bluetooth.md`.

## 0. Verdict

The backend is structurally faithful: every register offset, bit and buffer-geometry rule that
I could check against a local source **matches** (§2, V1–V11). One deviation still blocks S2, one
blocked S1 and is now fixed in the probe, and one was resolved offline on 2026-11-14:

| id | deviation | reach |
|----|-----------|-------|
| **F1** | GENI DMA address is the *virtual* pointer; SMMU stream 0x483 is neither bypassed nor configured | blocks S2 — **fix plan settled** (§F1: reuse the `k60_usblog.c` planner + `kmem_alloc_contig` pattern, inside `patches/bt/`) |
| **F2** | `G_MANUAL_RFR` (0x2ac) is written with a value the component never uses | **resolved**: it is `0x80000001` in the official sheng backend (`BluetoothProbe.cpp:202`), decoded = manual RFR + RTS ready |
| **F3** | `k60_stop_engine()` polls offset 0xe40, which exists in no GENI header | blocks S2 (decided by the S1 `rsvd_e40` read) |
| **F11** | the SE20 RCG root is never enabled (`CMD_ROOT_EN`/`CMD_ROOT_OFF` missing) | blocked S1; probe rungs s6/s7 now perform the enable, S2 needs the same code in the real path |

Consequence: do **not** go to S2 (first real power-on) until S1 has returned the `rsvd_e40` read that
decides F3 and the RCG rungs that decide F11. F1's fix is already designed and needs no device data;
F2 needs no work at all.

## 1. What `main` already carries

| patch | contents | state |
|-------|----------|-------|
| `0500-k60-bt-qbt-new-files.patch` | 156,632 B, creates `bsd/dev/qbt_k60.c` (1249 lines) + `bsd/dev/qbt/{qbt.h,qbt_geni.h,qbt_transport.h,qbt_internal.h,qbt_geni_regs.h,qbt_core.c,qbt_geni.c,qbt_transport.c,qbt_linux.c,qbt_linux.h,btqca.c,btqca.h}` + Linux shims | never booted with `k60bt=1` |
| `0501` | `bsd/conf/files` + `Makefile.arm64` INCFLAGS | compiled |
| `0502` | `bsd_init.c` call under `ARM64_BOARD_CONFIG_PONG` | compiled |
| `0502b` | weak `armcpu_spi_attach`/`armcpu_spi_mask`/`native_gpu_addon_stage` | stubs |
| series | `patches/xnu/series:201-204` = 0500, 0502b, 0501, 0502 | applied in every image since 209-patch boot |

Function map in the reviewed file (useful for citations): `k60_read32/k60_write32` 313/316,
`k60_map` 328, pin helpers 350–364, RX-wake arm/disarm 376/388, UART pin mux 400/407, GIC mask
419, `k60_gcc_set_se_rate` 435, `k60_gcc_wait_halt` 468, `k60_serial_clock` 481, GENI
read/write 522/526, DMA sync 531, `k60_irq_mask` 552, `k60_geni_receive` 576,
`k60_uart_flow` 597, `k60_geni_source_hz` 605, `k60_qup_sampling` 622, `k60_stop_engine`
628, `k60_prepare_engine` 651, `k60_quiesce` 676, `k60_pump` 701, `k60_wait_until` 721,
`k60_clock` 740, `k60_uart_speed` 777, firmware reader 857, `k60_firmware_get` 914,
`k60_log` 966, `k60_platform` table 975, `k60_bt_power_on` 1007, `k60_bt_power_off` 1103,
IRQ handlers 1140/1146, `k60_bt_local_address` weak default 269, `k60_worker` 1137,
`qbt_k60_start` 1217.

## 2. Verified against a local source (no action)

| id | what | K60 line | reference |
|----|------|----------|-----------|
| V1 | wrapper hardware version read from **wrapper** base + 0x4 | 622–623 | `linux-qcom-geni-se-v6.6.c:196-202` (`wrapper->base + QUP_HW_VER_REG`), `:114` = 0x4 |
| V2 | oversampling 16 when version ≥ `0x20050000`, else 32 | 623–625 | `linux-qcom_geni_serial-v6.6.c:1225-1230` |
| V3 | engine abort = write 2 to 0x604/0x634 | 632–633 | geni-se.h M/S_GENI_CMD_ABORT = BIT(1) |
| V4 | IRQ clear = 0xffffffff to 0x618, 0x648, 0xc44, 0xd44 | 642–645 | `geni_se_irq_clear()` (`linux-qcom-geni-se-v6.6.c:239-246`) writes exactly these four |
| V5 | TX/RX DMA FSM reset at 0xc58/0xd58 | 637–638 | geni-se.h `SE_DMA_TX_FSM_RST`/`SE_DMA_RX_FSM_RST` |
| V6 | busy predicate = `status & 0x1001` | 631,635 | geni-se.h M_GENI_CMD_ACTIVE BIT(0) \| S_GENI_CMD_ACTIVE BIT(12) |
| V7 | TX 4096 B at +0, RX 4×2048 B at +4096; every buffer 64-byte aligned and disjoint | 651–660 | `qbt_geni.c` `valid_buffer()` requires `!(address & 63)` and non-overlap; geometry = sheng `BluetoothProbe.cpp:311-313` |
| V8 | baud pairs are exact: 7,372,800 Hz / 115200 / 16 = div 4; 48,000,000 Hz / 3,000,000 / 16 = div 1; 0 % error | 605–620 | `qbt_geni.c` `qbt_geni_set_rate()` (div ≤ 4095, error ≤ 1 %) and `tests/geni.c:57-58` |
| V9 | TX clean-to-PoC, RX invalidate-after-device, `ctr_el0` line size | 531–550 | sheng `BluetoothProbe.cpp:85-99` |
| V10 | 5 GCC votes CORE/S_AHB/M_AHB/CORE_2X/SE20 and the 5 halt registers | 96–124, 490–503 | vendor `k60-android-gcc-waipio.c:2248-2272`, vote/halt bit layout; CBCR_CLK_OFF = BIT(31) (`clk-branch.h:42`) |
| V11 | halt wait returns immediately when HWCG_EN BIT(1) is set | 468–480 | matches `clk_branch_in_hwcg_mode()` early return (see F5 for the caveat) |

Also verified: RX wake (GPIO79) is armed as a plain TLMM GPIO interrupt with the status bit read
from `GPIO_CFG(n)[3] & 1` and disabled by clearing `[2]` — same 0x1000-per-pin layout as the
vendor driver (`k60-android-btpower.c`) and `phk110-port/drivers/bluetooth/hakios.bt.c:20-31`.
`k60_clock(false)` only gates after `qbt_geni_quiesce()` has successed and after the RX wake
source is armed, which is exactly the `clock` contract in `include/qbt.h`.

## 3. Deviations

### F1 — GENI DMA uses the virtual address (blocks S2)

```c
/* 0500:1025-1028 */
/* TODO: replace with a physically contiguous allocation and map the
 * QUPV3_2 SMMU stream (FDT iommus = <&apps_smmu 0x483 0>).
 * The skeleton assumes a 1:1 PA here; if the SMMU is translating,
 * this address is wrong and GENI DMA will fault. */
k60.dma_pa = (uint64_t)(uintptr_t)k60.dma_base;
```

`IOMallocData()` returns a kernel virtual pointer with no contiguity guarantee, and
`k60_prepare_engine()` hands `k60.dma_pa + offset` to the component, which programs it straight
into `G_TX_PTR_L/H` and `G_RX_PTR_L/H`. The wrapper node in the live FDT declares
`iommus = <0x5b 0x483 0>; qcom,iommu-dma-addr-pool = <0x40000000 0x10000000>; qcom,iommu-dma =
"fastmap"; dma-coherent` (`mondrian.dts:10707-10720`), and the official path explicitly sets up a
32 KiB DMA area with `smmu_plan_bypass`/`smmu_configure_bypass` under `AppsSmmuLock` before it
touches the engine (`docs/porting/bluetooth.md:45-62`, step 1). On K60 nothing does that, and
nothing proves the pages are contiguous either.

Severity: blocking. If the SMMU translates, the very first `G_RX_DMA_LEN` write faults; if it
does not, non-contiguous pages corrupt RX silently. Fix belongs to S2 (`patches/bt/`).

**Fix plan (settled 2026-11-14 from this tree's own working code, no new evidence needed):**
`bsd/dev/k60_usblog.c` already carries a working apps_smmu bypass planner and already allocates
DMA correctly — `smmu_plan_bank()` / `smmu_plan()` / `smmu_configure()` / `smmu_usb_bypass()`
(`patches/xnu/0300-k60-usblog-ep0.patch:288-523`, a 1:1 C port of `drivers/NativeUfs/SmmuTakeover.h`),
with the allocation pattern

```c
/* 0300:1236-1246 */
if (kmem_alloc_contig(kernel_map, &ud.dma, UD_SIZE, PAGE_MASK, 0, 0,
    KMA_DATA | KMA_ZERO | KMA_PERMANENT, VM_KERN_MEMORY_IOKIT) != KERN_SUCCESS) { … }
ppnum_t pn = pmap_find_phys(kernel_pmap, (addr64_t)ud.dma);
ud.dma_pa = ptoa_64(pn);
```

That path is proven on this board: the CDC console it feeds is the same console every boot log in
`/mnt/e/k60-work/evidence/` comes from, and its SMMU dump prints a live `sCR0 0x00200406`
(`console.log:246`). BT's stream is 0x483 (FDT `iommus = <0x5b 0x483 0>`, `mondrian.dts:10715`), so S2
must call the same planner with `stream = 0x483`. The helpers are `static` inside `k60_usblog.c`, so
the two options are (a) lift them into a shared `bsd/dev/k60_smmu.c` and add it to `bsd/conf/files`
(**Lead scope** — the build file list is outside this line), or (b) duplicate them inside
`qbt_k60.c` (**inside this line's write scope**, `patches/bt/`, no build-list change). (b) is the
low-risk default and is what S2 will do. S1 cannot decide this — but S1's `fifo_if_disabled`/protocol
reads prove the engine is reachable, which is the precondition for trying.

### F2 — `G_MANUAL_RFR` written with an unexplained value (**resolved 2026-11-14**)

```c
/* 0500:764-766 */
/* Leave RTS ready so the controller's 0xFD wake indication reaches GPIO79. */
k60_uart_write(NULL, 0x2ac, 0x80000001u);
```

0x2ac is `G_MANUAL_RFR` (`qbt_geni_regs.h:30`). The component only ever writes two values to it:

```c
/* qbt_geni.c:18-21 — ready/flow ? 0 : G_RFR_OFF */
wr(g, G_MANUAL_RFR, ready && g->flow ? 0 : G_RFR_OFF);   /* G_RFR_OFF = 0x80000002, regs.h:80 */
```

so 0 is "ready" and `0x80000002` is "manual, not ready". `0x80000001` is a third state that
appears in neither source.

**RESOLVED 2026-11-14 — the value is the official board backend's own write, not an invention:**

```cpp
// UniXNU-sheng/package/BluetoothProbe.cpp:201-202  (sheng = SM8550/WCN7850, boots on iPadOS 27)
/* Leave RTS ready so the controller can send its IBS wake indication. */
uwr(nullptr,0x2ac,0x80000001u);
```

The comment and the call site are identical to 0500's, so 0500 copied it from a backend that is
proven on hardware. Decoded against Linux's own field names (`qcom_geni_serial.c:64-66`:
`UART_MANUAL_RFR_EN` BIT(31), `UART_RFR_NOT_READY` BIT(1), `UART_RFR_READY` BIT(0)), the value is
"manual RFR enabled, RTS asserted (ready)" — which is exactly what the gated-clock state wants: RTS
stays ready so the controller may start sending, its first byte is the 0xFD wake indication, and the
falling edge on GPIO79 wakes the host. The component's `G_RFR_OFF = 0x80000002` is "enabled, not
ready" and is only used while the component itself is running. **Severity downgraded blocking →
verified (A-level, official same-chip backend).** S1's 0x2ac read stays in the probe as a record.

### F3 — `k60_stop_engine()` polls an undefined offset (blocks S2)

```c
/* 0500:631, 639 */
if ((k60_uart_read(NULL, 0x40) & 0x1001u) || (k60_uart_read(NULL, 0xe40) & 3u)) { ... abort ... }
for (i = 0; i < 1000 && (k60_uart_read(NULL, 0xe40) & 3u); i++) IODelay(1);
if (i == 1000) return -ETIMEDOUT;
```

0xe40 is not defined in `linux-geni-se-v6.6.h` (which jumps from `SE_HW_PARAM_0/1` 0xe24/0xe28
to the end) and not in `qbt_geni_regs.h` either. Linux waits for the FSM resets on completely
different registers: `TX_RESET_DONE` BIT(3) of `SE_DMA_TX_IRQ_STAT` 0xc40 and `RX_RESET_DONE`
BIT(3) of `SE_DMA_RX_IRQ_STAT` 0xd40. If 0xe40 reads non-zero on K60 (reserved/unimplemented
registers commonly do), `k60_stop_engine()` takes the abort branch, runs the abort poll, then
**always** returns `-ETIMEDOUT` from the second loop — `k60_bt_power_on()` fails and the earlier
stage would print `power=1 result=-110`. That failure mode is indistinguishable from a real
power/clock bug, so it must be excluded before S2.

### F4 — SE20 RCG divider width and duty are unverified (medium)

```c
/* 0500:441-465 */
const uint32_t mask = 0x1fu | (7u << 8) | (3u << 12) | (1u << 20);
uint32_t value = pre_div | (src_cfg << 8) | (1u << 20);
if (m && n && m != n) value |= (2u << 12);         /* CFG_MODE_DUAL_EDGE */
uint32_t d_val = r->n;                              /* not the descriptor's d */
...
k60_write32(&k60.gcc, base + 0xc, (~n_minus_m) & 0xffff);
k60_write32(&k60.gcc, base + 0x10, (~d_val) & 0xffff);
```

What matches Linux: M/N/D are written **before** CFG, N = `~(n-m)`, D = `~d`, D clamped to
`[m, 2(n-m)]`, DUAL_EDGE only when `mnd && n && m != n`, then a full CFG write, then
`CMD_UPDATE` BIT(0) with a poll for clear (`clk-rcg2.c:295-350`, update path
`:111-135`). What does not: Linux clamps the frequency descriptor's own `d` and writes its
complement, whereas K60 starts from `d = n` (forced 50 % duty — harmless for UART but not what
the descriptor says); and the CFG field mask `0x1f | 7<<8 | 3<<12 | 1<<20` assumes a 3-bit
divider at bits 10:8. A grep for `CFG_SRC_DIV_SHIFT`/`CFG_SRC_DIV_MASK` in our evidence copy of
`clk-rcg.h` returns **zero hits**, so the divider width is still unverified from local evidence.
Action: confirm from `clk-rcg.h` at a known tag / the SM8450 clock driver, and prefer
`update_bits`-style read-modify-write (K60 already reads `cfg` first and masks, which is
equivalent). Not a blocker: a wrong divider only produces the div already proven by the
`kern.qbt` baud log.

### F5 — halt wait proves less than it looks (informational)

`k60_gcc_wait_halt()` succeeds when `HWCG_EN` BIT(1) is set, before reading `CBCR_CLK_OFF`
BIT(31). That mirrors `clk_branch_in_hwcg_mode()`, so it is *correct* — but it explicitly does
not prove the branch is running. The `clocks vote cbcr core=… se=…` print at `0500:494-503`
is therefore the real evidence, and S1 already captures it. When reading S1 logs, treat
`se=0x80000000` (off) vs `se=0x0` (running) as the signal, not the absence of an error.

### F6 — clock-off path does not prove the SE drained (medium)

`0500:505-513` drops the 5 vote bits and polls nothing (`IODelay(10)`), citing the vendor's
`BRANCH_HALT_VOTED` 10 µs convention (`clk-branch.c:69-73`). Since this only runs after a
successful `qbt_geni_quiesce()`, the risk is small, but S2 should poll SE20 `CBCR_CLK_OFF`
BIT(31) before returning and should never gate while `status & 0x1001` is set.

### F7 — firmware search list contains paths that will never exist on iOS (low)

`0500:861-868` tries `/private/var/ngpu/firmware/qca` first (the official staging root), then
`/vendor/firmware/qca`, `/vendor/firmware`, `/firmware/image`, `/modem/image/qca6490`. On iOS
the last four do not exist; they are dev fallbacks and harmless, but the failure message must not
be read as "firmware missing on the device" — only the first root matters for acceptance.

### F8 — power-off order details (low)

`0500:1103-1128`: `qbt_shutdown` runs before the engine is quiesced, BT_EN is dropped, then
`k60_stop_engine()` only if `clocked`, then `k60_serial_clock(false)` unconditionally (so a
never-clocked boot also drops the vote bits — writes a 0 into an otherwise untouched register,
harmless), and the 32 KiB DMA block is never freed (deliberate: the worker may power-cycle).
No change needed before S1/S2; note it for the S6 cleanup.

### F9 — `stop_engine()` mutates the component's state directly (low)

`0500:646-649` sets `k60.geni.state = QBT_GENI_OFF` and clears `rx_busy`/`tx_busy` by hand.
Correct while the core is not running (power-on path), wrong if ever called with a live
transport; keep it power-path-only.

### F10 — worker timing constants are arbitrary (low)

`0500:1188-1191` uses 1 s health ticks and a 500 ms service-close delay; neither is traceable to
a source. They only affect log cadence and when the UART.SK channel is torn down, not
correctness.

### F11 — the SE20 RCG root is never enabled (blocks S1, new 2026-11-14)

```c
/* 0500:435-466, k60_gcc_set_se_rate() — the whole enable tail */
k60_write32(&k60.gcc, base + 0x8, m);
k60_write32(&k60.gcc, base + 0xc, (~n_minus_m) & 0xffff);
k60_write32(&k60.gcc, base + 0x10, (~d_val) & 0xffff);
k60_write32(&k60.gcc, base + 0x4, (cfg & ~mask) | value);
k60_write32(&k60.gcc, base, 1u);              /* CMD_UPDATE only */
```

Linux `clk_rcg2_is_enabled()` (`clk-rcg2.c:64-75`) defines "RCG on" as `(cmd & CMD_ROOT_OFF) == 0`,
and `clk_rcg2_set_force_enable()` (`:981-1002`) turns a root on by writing `CMD_ROOT_EN` BIT(1)
and polling that predicate for up to 500 µs. `update_config()` (`:111-135`) only *latches* a
config. 0500 does the latch and nothing else: it never sets `CMD_ROOT_EN` and never checks
`CMD_ROOT_OFF`, so the SE20 root clock can still be gated at the moment the first SE register is
read. Bit definitions: `CMD_UPDATE` BIT(0), `CMD_ROOT_EN` BIT(1), `CMD_ROOT_OFF` BIT(31)
(`clk-rcg2.c:24-31`); the register is `K60_GCC_WRAP2_SE20_CMD_RCGR` 0x2e618 (`0500:122`), which the
vendor table confirms as `gcc_qupv3_wrap2_s5_clk_src.cmd_rcgr` with `enable_safe_config = true`
and `HW_CLK_CTRL_MODE` (`k60-android-gcc-waipio.c:1370-1387`).

Why this is a real candidate for the S1a zero-byte death: the touch line's healthy boot does the
full sequence before it maps the SE — `CMD_ROOT_EN` → wait `ROOT_OFF` clear → write CFG →
`ROOT_EN|UPDATE` → wait `UPDATE|ROOT_OFF` → CBCR readiness loop → *then* `ml_io_map`
(`patches/xnu/zzzz…-pong-touch-console.patch:307-339`), and its console shows the SE4 identity
reads succeeding (`console.log:661-663`). K60's BT path skips all of that.

Severity: blocking for S1 (it may be the hang) and mandatory for S2. The S1c probe therefore
adds three read/write rungs that isolate it: s5 reads CMD/CFG/DFSR and decodes `ROOT_OFF` /
`ROOT_EN` / `UPDATE`; s6 sets `ROOT_EN` and polls `ROOT_OFF`; s7 writes CFG and latches
`ROOT_EN|UPDATE`. Rung A3 (step=5) alone answers "was the root off before we touched anything?".

### F12 — no CBCR readiness poll before the first SE access (medium, new 2026-11-14)

The touch line waits for each branch's CBCR to report running (`cbcr_running(v) = !(v & CLK_OFF) || (v & HWCG)`,
2000 × 10 µs, `…-pong-touch-console.patch:253-260,342-358`) before it maps the SE. 0500 polls the
five halt registers *before* the RCG is configured (`0500:481-513`), so a branch that was merely
idle-and-hw-gated passes, and nothing re-checks after `k60_gcc_set_se_rate()`. Cheap fix in S2:
repeat the five halt reads after the rate write and log them (the probe's s4 already establishes
the baseline values).

## 4. Deliberately absent (dependencies, not defects)

| item | why absent | owner |
|------|-----------|-------|
| PMIC rail voter (S10/S11/S12, PM8350C S1, PMR735A L7) | RSC must never be read; cold boot returns `-EOPNOTSUPP` (`0500:1009-1014`) | UEFI/bootloader voter, or a future RSC-safe path |
| board-local BT address | weak `k60_bt_local_address()` (`0500:269,275`); `qbt_boot` rejects all-zero | board integration (`dts/mondrian.dts` ADT node) |
| DT node for the controller | `dts/mondrian.dts` has no `bluetooth` node; properties would be dead (P-147 class) | Lead (handoff in `RESEARCH.md` §9) |
| BlueTool / Type0 staging | needs the iOS-SDK toolchain + 20G81 `bluetoothd` hash | LAN Mac, S5 |
| SMMU stream 0x483 | see F1 | S2 |

## 5. What this changes for S1

The probe has been rewritten twice since the first draft; the current artefact is **S1c**:
`patches/bt/0001-k60-bt-readonly-probe.patch` = `patches/xnu/0507-k60-bt-readonly-probe.patch`
(13,001 B / 280 lines, sha256 `05dd342b83d3d035e05495280d9bee9d40624f9732240b7323146964e7b8b2e1`,
`git apply --check` OK, `clang -fsyntax-only` clean). It delays `k60bt_delay` (default 20 s, cap
120 s) so the CDC console is alive, prints a mark before every access (36 marks), and splits the
work into nine `k60bt_step` rungs:

| step | what it does | decides |
|------|--------------|---------|
| s1 | map GCC / UART / wrapper only, zero MMIO | plumbing (boot args, worker, delay, marks, console drain) |
| s2 | GPLL0 vote + lock poll | PLL path |
| s3 | QUPV3_2 vote 0x62010, read-back | vote register accepted |
| s4 | read the five halt registers | branch CBCR baseline (F5) |
| s5 | **read-only** SE20 RCG: CMD 0x2e618, CFG +0x4, DFSR +0x14, decode ROOT_OFF/ROOT_EN/UPDATE | **F11** — was the root gated before we touched anything |
| s6 | set `CMD_ROOT_EN`, poll `ROOT_OFF` clear (500 × 1 µs) | **F11** — does the root come on at all |
| s7 | write CFG = `(cfg &amp; ~0x371f)` + `BIT(20)` + `1`, then latch `ROOT_EN` and `UPDATE`, poll | **F11** — first writes to the RCG |
| s8 | SE identity: 0x040, 0x064, 0x068, 0x2ac, wrapper 0x004 | GENI reachability + **F2** |
| s9 | 0xc40, 0xd40, 0xe40, 0x040 again | **F3** and the S2 reset-done baseline |

Rung ladder on device (same image, stop where the board dies): A1 `k60bt_step=1`, A2 `=4`,
A3 `=5`, A4 `=7`, A5 `=9`; if A4 dies, B = `=6` proves s7's CFG write is the killer. The verdict
table and the exact boot commands live in `S1-PROBE-SPEC.md` §4/§5; the register provenance is
§3 there and §2 here.

Reads at s8/s9 are pure loads; they cannot hang the machine any more than the identity reads.
What is new is that the ladder now separates "GENI is unreachable" from "the RCG root was never
turned on" — the touch line proves the latter is a real failure mode on this SoC.

## 6. How to reproduce this review

```bash
# extract the file exactly as 0500 creates it
cd /mnt/e/hackios/k60-bt
git apply --numstat patches/xnu/0500-k60-bt-qbt-new-files.patch | head
# the extract used here:
sha256sum /mnt/e/k60-work/scratch/bt-0500/qbt_k60.c
# -> 8451c8706ecf75a79fba49ba7e3bda769ee73fcac5f357a46c9d484df3878748  (1249 lines)
```

Cross-check lines against `docs/research/bt/evidence/linux-geni-se-v6.6.h` (register map),
`linux-qcom-geni-se-v6.6.c` (`geni_se_irq_clear` 239-246, `geni_se_get_qup_hw_version` 196-202),
`clk-rcg2.c` (MND 288-350), `E:/hackios/QcaBluetooth/src/qbt_geni.c` (prepare/set_rate/rfr).

## 7. Sources

- `patches/xnu/0500-k60-bt-qbt-new-files.patch` (main, f119a80) — code under review.
- `docs/research/bt/evidence/linux-geni-se-v6.6.h`, `linux-qcom-geni-se-v6.6.c`,
  `linux-qcom_geni_serial-v6.6.c`, `clk-rcg2.c`, `clk-branch.h`, `clk-branch.c` — Linux GENI/clk.
- `E:/hackios/QcaBluetooth/src/qbt_geni.c`, `src/qbt_geni_regs.h`, `include/qbt.h` — component contract.
- `E:/hackios/UniXNU/docs/porting/bluetooth.md:45-62` — official power/DMA sequence.
- `E:/k60-work/scratch/bt/mondrian.dts:10707-10720` — wrapper SMMU binding, live FDT.
- Vendor `k60-android-btpower.c`, `k60-android-hci_qca.c`, `k60-android-gcc-waipio.c` — K60 measured/vendor behaviour.
