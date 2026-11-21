# 平台预算：`ml_io_map` 还有没有共享子图；T0SZ / SIGP 能不能原样搬

> 官方锚点：<https://unixnu.com/zh/porting/platform#source-map>（`E:/hackios/UniXNU/docs/zh/porting/platform.md:10-19`，ArmCpu 的 timer/GIC 初始化）与 <https://unixnu.com/zh/porting/platform#block-and-os-services>（`:69-80`，块设备与 OS 服务的映射输入）。
> 本文回答 Lead 的三个具体问题：① 12377 重写 `osfmk/arm/io_map.c` 之后 `ml_io_map` 是否仍是全局共享子图；② 按调用点的字节预算；③ T0SZ 与 SIGP 补丁逐行能不能搬。

## 0. 结论

1. **不是共享子图了。** 12377 的 `osfmk/arm/io_map.c` 里没有 `IO_MAP_SIZE`，也没有 `io_submap`；每次 `ml_io_map()` 都各自 `kmem_alloc(kernel_map, …)`（`io_map.c:112`）。16 系列 `0621` 把 `IO_MAP_SIZE` 从 8 MiB 抬到 32 MiB 的那个补丁，在 27 上**没有对应物、也不需要**。
2. **因此没有「平台线额度」可分给 GPU/USB 线。** 每条调用换的是 `kernel_map` 的 VA 和 `KMA_IO|KMA_PERMANENT` 的映射，互不挤占。GPU/USB 线不需要向本线申请配额；它们要自己保证窗口大小合理、失败可诊断。
3. **27 stage-0 的 `ml_io_map` 预算 ≈ 3.04 MiB**，且几乎全部来自 BT 补丁的 5 个窗口；XNU 自身的三处调用在本板 ADT 上都是 0 字节（属性不存在）。
4. **T0SZ：可以搬，但要整组搬**（6 个文件 + 2 处汇编），并且 `pmap.c` 里失败的那 1 个 hunk 属于 GPU 线（`native_pmap_user_mappings`），必须剥离或由 GPU 线提供。
5. **SIGP：可以原样搬**（`cpu_common.c` 3/3、`cpu.c` 6/6、assert 守卫 12 行单独一个补丁），2026-11-21 对 pristine `E:/hackios/xnu-12377` 全部 `git apply --check` 通过。

## 1. `ml_io_map`：12377 已把共享子图换成 `kernel_map`

### 1.1 现状（构建基线 `osfmk/arm/io_map.c`，117 行）

`io_map()` 先算 `start_offset = phys_addr - trunc_page(phys_addr)`、`alloc_size = round_page(size + start_offset)`，然后分两条路：

- `startup_phase < STARTUP_SUB_KMEM`：从 `virtual_space_start` 抢 VA（`virtual_space_start += round_page(size)`），`assert(flags == VM_WIMG_WCOMB || flags == VM_WIMG_IO)`，再用 `pmap_map_bd` / `pmap_map_bd_with_options` 直接建映射；
- 否则：`kma_flags_t kmaflags = KMA_NOFAIL | KMA_PAGEABLE | KMA_IO;`，`!unmappable` 时再加 `KMA_PERMANENT`，然后 `kmem_alloc(kernel_map, &start, alloc_size, kmaflags, VM_KERN_MEMORY_IOKIT)`（`:112`）并 `pmap_map`。

`ml_io_map_unmappable()` 的唯一差别是不加 `KMA_PERMANENT`（`machine_routines.c:1861`）。`ml_io_unmap()` 走 `pmap_remove` + `kmem_free`（`machine_routines.c:~1890`）。

**判据**：整个文件没有 `IO_MAP_SIZE`、没有 `io_submap`、没有 `io_range`。16 系列的 `0621` 正是把这三样加进 `osfmk/arm/io_map.c` 并把 `IO_MAP_SIZE` 从 `8ul << 20` 改成 `32ul << 20`——**那是 16 系列的私有结构，12377 没有**。

### 1.2 16 系列的证据只对 16 系列有效

`0621` 的注释（P-219）说「every `ml_io_map()` caller shares this one submap，K60 驱动窗口之和已超 8 MiB」；`E:/hackios/k60-gates/docs/research/bt/HANDOFF.md:698-730` 记录 d4 那次 `kmem_alloc(... 1048576 ...): failed with 3 @vm_kern.c:178`，d5 抬到 32 MiB 后起飞。这两条在 27 上不能当约束引用：27 的 `io_map()` 不向任何固定池取内存，`kmem_alloc` 失败只会在内核 VA 真正耗尽时出现。

### 1.3 按调用点的字节预算（27 stage-0）

XNU 自身的 `ml_io_map` 调用全部由 ADT 属性驱动，本板 ADT 不提供这些属性 → 0 字节：

| 调用点 | 条件 | 本板 |
|---|---|---|
| `osfmk/arm64/machine_routines.c:1371-1385` `ml_map_cpu_pio()` | 每个 CPU 有 `cpu_IMPL_pa`/`coresight_pa`/`UTTDBG_pa`，每个簇有 `acc_IMPL_pa` | 无 → 0 |
| `osfmk/arm64/cpu.c:1310` | ADT 有 `stram` 节点与 `reg` | 无 → 0 |
| `osfmk/arm64/cpu.c:289` | topology 给 `cpu_regmap_paddr`，`CORESIGHT_SIZE` = `0x1000`（`osfmk/arm64/proc_reg.h:3049`） | 无 → 0 |

驱动侧（`ml_io_map` / `ml_io_map_unmappable`）：

| 调用点 | 窗口 | 字节 | 27 stage-0 |
|---|---|---|---|
| `patches/xnu-12377/0500-k60-bt-qbt-new-files.patch:1017-1021` | GCC `0x001F4200`（`:107`）、UART `0x4000`（`:75`）、QUP `0x2000`（`:78`）、TLMM `0x00100000`（`:97`）、GIC DIST `0x00010000`（`:101`） | 2,048,512 + 16,384 + 8,192 + 1,048,576 + 65,536 = **3,187,200 B（3.04 MiB）**；按 4 KiB 页对齐后 3,190,784 B | 在（series 里有 0500） |
| `drivers/PongThermal/pong_thermal.c:286-289` | `PONG_THERMAL_WINDOW 0x1000`（`:41`）× 2 窗口 × `PONG_THERMAL_CONTROLLERS 2`（`K60ThermalKernel.h:23`） | 16,384 B | 否（`board.toml:14` 不含 PongThermal） |
| `drivers/PongPower/K60PmicRail.c:361,368` | `K60_CMD_DB_BYTES 0x20000`、`K60_RSC_BYTES 0x10000`（`K60PmicRail.h:28,30`） | 196,608 B | 否（不含 PongPower） |
| `drivers/PongPower/K60AdspBoard.c:376` | 调用方给 `bytes` | 可变 | 否（不含 PongPower） |

**stage-0 合计：3,187,200 B ≈ 3.04 MiB**（页对齐后 3,190,784 B）。将来把 PongPower 拉进来会再加 ≥ 0.19 MiB 常驻。

### 1.4 对 GPU / USB 线的回答

- **不存在需要分配的池**，所以「开额度」这个动作在 27 上不成立。GPU/USB 线直接 `ml_io_map` 自己的窗口即可，不会因为 BT 先映射了 3 MiB 而失败。
- **仍然共享的是 `kernel_map` 的 VA 与页表**。`KMA_PERMANENT` 的映射永不回收（这是 `ml_io_map` 与 `ml_io_map_unmappable` 的唯一区别），因此 GPU/UFS 这种长期窗口用哪个变体是有意的选择，不是顺手。
- **失败形态变了**：16 系列是「子图用完 → `kmem_alloc` 返回 3」，27 是「kernel_map 真没 VA → `KMA_NOFAIL` 在 `vm_kern.c` 里等/失败」。诊断时看 `startup_phase` 与 `kernel_map` 的 `vm_map` 统计，不要再去 grep `IO_MAP_SIZE`。
- **唯一还要盯的是 bootstrap 分支**：`startup_phase < STARTUP_SUB_KMEM` 时从 `virtual_space_start` 抢地址且 `assert(flags == WCOMB || IO)`。本板早期没有这类调用（ADT 无属性），但若将来把 GPU/UFS 的映射提前到 VM 起来之前，flag 必须显式给 `VM_WIMG_IO` 或 `VM_WIMG_WCOMB`，否则是 assert 而不是失败返回。

### 1.5 门禁 `check-io-map-budget.py` 在 27 上是假绿（需要 gates 仓改，不在本线树里改）

实测（2026-11-21，对本线 27 构建基线）：

```sh
python3 scripts/check-io-map-budget.py --tree /e/hackios/UniXNU/out/mondrian/ios-27.0.1-24A446/mondrian_ios27/tree/.cache/xnu-work
# submap 8388608 = 0x800000 (8388608 bytes) from default
# 2 call site(s), 2 unresolved; resolved total 0x0 (0.00 MiB)
# ✅ io_submap budget: every ml_io_map window fits
```

这条 ✅ 什么也没证明。机理写在 `scripts/check-io-map-budget.py` 里：

- `io_map_size()`（`:71-79`）在 `osfmk/arm/io_map.c` 里找不到 `IO_MAP_SIZE` 时**不报错**，退回 `DEFAULT_SUBMAP = 8 << 20`（`:33`），并在输出里标 `from default`；
- `call_sites()`（`:83`）只扫 `bsd/dev/*.c`，尺寸必须写成字面量或同文件 `#define`（`:101-105`），所以 BT 窗口的宏尺寸一律算 `unresolved`，`resolved total 0x0`；
- 于是一个「没有子图、窗口尺寸也没算出来」的树，得到的是「every window fits」。这在 16 系列是对的（P-219 的真问题），在 12377 之后是过期模型。

建议（gates 仓归 Lead）：`IO_MAP_SIZE` 缺席时不要打 ✅，改打印「12377 之后 `io_map()` 每次 `kmem_alloc(kernel_map)`，本门禁不适用（P-219 已封存）」并按 skip 退出；BT 窗口的尺寸读 `patches/xnu-12377/0500-*.patch` 的宏，而不是 `bsd/dev/*.c` 里的 `#define`。

## 2. T0SZ：整组可搬，但有一处属于 GPU 线

### 2.1 前提条件在 27 构建上成立

sheng 的 T0SZ 分支(`prop_reg.h`)条件是：

```c
#if defined(BCM2837) && !defined(__ARM_16K_PG__) && defined(__arm64e__)
#define T0SZ_USER 17ULL
#else
#define T0SZ_USER T0SZ_BOOT
#endif
```

三个条件在 27 的构建记录里都能核到：

- `BCM2837`：构建基线 `pexpert/pexpert/arm64/board_config.h:307-315` 有 `#ifdef ARM64_BOARD_CONFIG_BCM2837 / #include <pexpert/arm64/BCM2837.h>`，而 `BCM2837.h:11` 就是 `#define BCM2837`；编译参数里确有 `-D ARM64_BOARD_CONFIG_BCM2837`。pristine `E:/hackios/xnu-12377` 的 `board_config.h` **没有** BCM2837 分支，`BCM2837.h` 也不存在——这层是构建树/构建驱动加上去的。
- `arm64e`：编译参数 `-arch arm64e`、`--target=arm64e-apple-ios17.0.0`。
- `!__ARM_16K_PG__`：本板是 4 KiB 页（`configs/mondrian_ios27_defconfig` 注释「arch profile 带 4 KiB tables 和 PAC」），16K 宏未定义。

→ 在 27 构建上 `T0SZ_USER = 17`，即用户 VA 47 位（`64 - 17`）。若哪天把 `ARM64_BOARD_CONFIG_BCM2837` 去掉换成别的 board 头，这条 `#if` 会整体退化成 `T0SZ_USER == T0SZ_BOOT`，补丁变成 no-op 而**不会报错**——这是搬它时要写进注释的风险点。

### 2.2 逐 hunk 判断（对 pristine `E:/hackios/xnu-12377` 执行 `git apply --check`，`2026-11-21`）

| 目标文件 | 补丁内行 | 内容 | apply | 判断 |
|---|---|---|---|---|
| `osfmk/arm64/proc_reg.h` | `:1195-1230` | `T0SZ_USER` 三条件、`TCR_EPD0_DISABLE`、`TCR_EL1_KVA_ENTRY` | 3/3 | **原样搬** |
| `osfmk/arm/pmap/pmap_pt_geometry.h` | `:1075-1082` | `pmap_get_pt_attr()` 按 `PMAP_TYPE_KERNEL` 选 attr | 1/1 | **原样搬** |
| `osfmk/arm/pmap/pmap.c` | `:842-884`、`:893`、`:933-938`、`:946-948`、`:971-972` | `pmap_pt_attr_4k_user`、`native_user_pt_attr`、`pmap_user_tcr`/`pmap_apply_user_tcr`、`kernel_pmap->type`、切换/清除 TTBR0 时应用、`pmap_user_va_bits` | 9/10 | **搬 9 个**；失败的那 1 个（`@@ -15301,3 +15370,76 @@`）是 `native_pmap_user_mappings()`，**属于 GPU 线**，剥离或由 GPU 线提供 |
| `osfmk/arm/arm_init.c` | `:779-783` | `set_tcr(TCR_EL1_KVA_ENTRY); flush_core_tlb();` 放在 `arm_slide_rebase_and_sign_image()` 之前 | 1/1 | **原样搬** |
| `osfmk/arm64/start.s` | `:1293-1300` | `arm_init_tramp` 里 `MOV64 x1,TCR_EL1_KVA_ENTRY; MSR_TCR_EL1_X1; isb sy; tlbi vmalle1; dsb ish; isb sy` | 1/1 | **原样搬** |
| `osfmk/arm64/sleh.c` | `:1256` | PAC 故障掩码用 `64 - T0SZ_USER` | 2/3 | **搬 2 个**；失败的是纯注释 hunk（`sleh_irq` 的 per-interrupt sampling 关闭说明），手工带过即可，不改逻辑 |
| `osfmk/arm64/arm_vm_init.c` | `:1093-1096` | TTBR0 失效后应用 user TCR | 0/1 pristine；1/1 构建基线 | **依赖基线**：构建树的上下文多一个 `#endif`，搬之前先对齐这段 |

**结论**：T0SZ 不能按「一个 patch 打进去」处理。要么把 6 个文件按上表拼成一个 27 专用补丁（剥掉 `pmap.c` 的 GPU hunk），要么先接受 `pmap.c` 9/10 的部分应用再人工补。两处汇编（`arm_init.c:779-783`、`start.s:1293-1300`）是 `T0SZ_USER != T0SZ_BOOT` 的落点，缺一条都会让用户 pmap 与 TTBR1 的描述符层级不一致。

### 2.3 为什么需要它（一句话，供 commit message）

arm64e 用户代码把 PAC 放在 bit 46 以上，libobjc 用 43 位掩码剥 isa；4 KiB 内核默认的 `T0SZ_BOOT` 给出的用户范围装不下这些，所以用户 pmap 用 4 级表 + 47 位范围，TTBR1 保持 `T1SZ_BOOT`。`TCR_EPD0_DISABLE` 是在切换 TTBR0 时先停走表再改 TCR，避免中间态被硬件走。

## 3. SIGP：原样可搬

| 目标文件 | 内容 | apply | 判断 |
|---|---|---|---|
| `osfmk/arm/cpu_common.c` | `sheng_sigp_recovered` 计数、`sheng_sigp_recover(target_cpu)`（要求 `cpu_flags & (InitState|StartedState)`，然后 `os_atomic_andnot(&target->cpu_signal, SIGPdisabled, acq_rel)`）、两个 `cpu_signal_internal` 重试环里调用 | 3/3 | **原样搬** |
| `osfmk/arm64/cpu.c` | `cpu_idle` 用 `sheng_sigp_recover()` 清 SIGP（代替 `idle_disallowed`），两个计数 | 6/6 | **原样搬** |
| 单独补丁 `zzzzzzzzzz-sheng-sigp-reinit-assert.patch`（12 行） | 在 `assert3u(getCpuDatap()->cpu_signal, ==, SIGPdisabled)` 前加 `else if (os_atomic_load(&sheng_sigp_recovered, relaxed) == 0)` | 通过 | **原样搬**（必须与上面两个同批，否则 assert 会打死） |

**机理**：SMP 下副核在 `cpu_idle` 里被投递 SIGP 后进入 WFI，但 `SIGPdisabled` 位可能留在 `cpu_signal` 里；下一次 `cpu_signal` 认为「已经投递过」直接返回，唤醒丢失，表现为调度停摆/UFS 根挂不上。`sheng_sigp_recover()` 在重试环里把这一位清掉并计数。

## 4. 复现

```sh
# 1) 共享子图是否还在（应为空）
grep -n "IO_MAP_SIZE\|io_submap" <build-tree>/osfmk/arm/io_map.c

# 2) 补丁可应用性（对 pristine 12377）
cd E:/hackios/xnu-12377
git apply --check E:/hackios/k60-gates/patches/xnu-12377/0532-k60-cpu-start-completion.patch
git apply --check E:/hackios/k60-gates/patches/xnu-12377/0540-k60-psci-smp.patch
git apply --check E:/hackios/k60-gates/patches/xnu-12377/0541-k60-virtual-timer-guard.patch

# 3) sheng 补丁逐 hunk（脚本见 E:/k60-work/scratch/platform27/hunkcheck.py）
HUNKREPO=E:/hackios/xnu-12377 python3 E:/k60-work/scratch/platform27/hunkcheck.py <patch> proc_reg.h pmap.c pmap_pt_geometry.h arm_init.c start.s sleh.c arm_vm_init.c cpu_common.c cpu.c
```

## 5. 仍未定的

- 27 上 `ml_io_map` 的 bootstrap 分支是否会被提前调用（GPU/UFS 若在 VM 之前映射）——目前 stage-0 没有这种调用，`unknown`，定它的证据是 F3/F4 的映射时序日志。
- `pmap.c` 那个 GPU hunk 由哪条线提供（k60-gates 现有 `patches/xnu-12377/` 里没有 `native_pmap_user_mappings` 的实现），需要 Lead 指派。
