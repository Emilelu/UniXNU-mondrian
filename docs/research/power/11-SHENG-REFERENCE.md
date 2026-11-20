# sheng（UniXNU-sheng）在电源、电池、充电三条线上的位置

> 铁则 12 要求内核层与驱动层的参考来源必须包含 sheng。本文回答三件事：sheng 的补丁里哪几条碰到我们的四条线、我们 36 条契约行里哪几条 sheng 已经解决、以及 `CONFIG_XNU_OWNER_*` 能不能解释 27 侧缺失的行。结论先行：**不能**，原因在第 4 节。

## 1. 引用的是哪一份 sheng

| 检出处 | 状态 | 能不能引用 |
|---|---|---|
| `E:/k60-work/references/UniXNU-sheng` | `bc05635`（main），173 个 `package/` 目录项（170 文件 + 3 子目录，递归 209 个文件），24 条 `patches/xnu-12377/series`；只有一个文件脏（`package/WifiProbe.cpp`） | **是**，本文全部引用的都是这一份 |
| `E:/hackios/UniXNU-sheng` | `a68ee4e`，落后 795、领先 484 | 否。它连 `ShengChargeAuth.c` 都没有，按它查会得到“sheng 没做过充电”这种错误结论 |

两份的差别不是细节：`a68ee4e` 上我们曾记录“充电文件不存在”，而 canonical 检出里该文件就在 `package/ShengChargeAuth.c`。`docs/research/SOURCES.toml` 用 `path = "references/UniXNU-sheng/..."` 直接引用 canonical 检出（现有 5 条 required 记录），`scripts/research-gate.py` 的 `REFERENCE_PREFIXES` 允许 `/mnt/e/k60-work`，这条路径在 WSL 侧可核对；`external:` 不是该门禁认识的写法。

sheng 的板子也是 `ipados-27.0.1-24A446`（`board.toml:9`），所以它是**同一个 OS 目标、不同一块板**：OS 侧经验可以直接借，板级地址不能。

## 2. 24 条 XNU 补丁里，碰电源的只有 3 条

| 补丁 | 行数 | 碰的是什么 | 对我们有没有用 |
|---|---|---|---|
| `zzye-sheng-cpu-idle.patch` | 26 | 在 `osfmk/kern/processor.c` 里加 C 链接的 `uint64_t sheng_cpu_idle_mach(int cpu)`，内部 `cpu_to_processor(cpu)` + `recount_processor_usage(&p->pr_recount, &usage, &idle)`，`PROCESSOR_NULL` 返回 0 | 有：它就是 sheng 的 16 ms 空闲采样的内核半边，见第 5 节 |
| `zzzz-sheng-ipados27-bringup.patch` | 1981 | `sheng_sigp_recover()`：`os_atomic_andnot` 清掉 `SIGPdisabled` 后重发 IPI；外加 `#define IDLE_PROXIMATE_TIMER_WFE 1` 与 cpu_idle 改动 | 有，且是一条现成的坑：注释原文 “an idle core never gets an IPI, so SIGPdisabled left it spinning at full speed — every cluster read busy=100% on the idle desktop” |
| `zzzzzzzzzz-sheng-sigp-reinit-assert.patch` | 12 | `processor_start` 里对 `SIGPdisabled` 断言 | 有：同一个坑的守门版本 |

其余 21 条与电源无关（音频挂载、存储、wifi/bt、appsync、launchd 缓存、trace 等）。`sheng-bootstrap-checkpoints.patch:43-45` 只在 `resume_cluster_powerdown` 前后插 checkpoint；`zzyf-sheng-amp.patch` 与 `zzzzzzzzzzz-sheng-edge-matrix.patch` 只在调度器注释里提到 idle。

**没有一条温控、电池或充电补丁。** sheng 在这三条线上的东西全部在 `package/` 里，作为 kext/用户态代码存在，而不是内核补丁 —— 这一条决定了下表的引用方式。

## 3. 我们 36 条契约行，sheng 解决到哪一步

### 3.1 sheng 已经解决、且不是抄自我们的（可以当第二来源）

| 我们的契约行 | sheng 的位置 | 值 |
|---|---|---|
| `adsp-owner` / `adsp-request-bytes` / `adsp-notify-bytes` | `package/ShengBattmgr.h:16` / `:27` / `:28` | `SHENG_BATTMGR_OWNER 32778u`、`SHENG_BATTMGR_REQUEST_BYTES 24u`、`SHENG_BATTMGR_ENABLE_BYTES 28u` |
| `battery-owner-usbc-neighbour` | `package/ShengBattery.cpp:33` | 注释写明 32779（USB-C 端口管理器）共用同一条通道，这与 sheng `ea15446` 的路由实现一致 |
| `thermal-trip-warm` / `-junction` / `-emergency` | `package/ThermalLevel.h:65`（`{90000, 2000}, {95000, 2000}, {110000, 1000}`）、`package/ThermalProbe.cpp:27`（“mainline trip points: CPU 90/95/110 (passive/passive/critical), GPU 85/90/110”） | 三档数值与我们相同；但 sheng 的列表属于它的 CPU/GPU 输入组，我们的 junction 行是 gpuss-0 zone——数值同、域不同 |

这三组已经写进 `docs/research/power/HW-CONTRACTS.toml` 的 `second` 字段，由 `scripts/check-hw-contracts.py` 逐行重开核对。

### 3.2 sheng 帮不上的，以及为什么

| 契约行 | 为什么 sheng 不能作证 |
|---|---|
| `thermal-trip-reset` 115000 / `thermal-trip-shutdown` 125000 | sheng 全仓 0 处 115000、0 处 125000；它的梯子止于 110 ℃ critical。这两档是厂商 FDT 额外挂的 zone，只能靠本机 DTB |
| `adsp-carveout` 0x9fd00000 / `adsp-load-base` 0x86300000 | sheng 是另一块板：`package/AdspProbe.cpp:54` 写着 `kAdspBase = 0x9ea00000, kAdspSize = 0x4680000`。板级 carveout 不可移植，我们的值来自本机 FDT 与 `adsp.b00` 的 ELF 入口 |
| `power-pdmem-vote-magic` 0x17d09804 / `-offset` 0x804 | sheng 全仓 0 处 pdmem / 0x17d09；它根本不走 PDMEM 投票，而是直写 EPSS 寄存器（`package/CpuFreqProbe.cpp:76` `kDomainBase[3] = {0x17d91000, 0x17d92000, 0x17d93000}`、`:78` `kL3Base = 0x17d90000`、`perf_state 0x320`、`EPSS_REG_L3_VOTE 0x90`）。这是两种实现路线，不是同一事实的两个拷贝 |
| `handoff-*`（PAS1 租约） | sheng 有 PAS id 1（`package/AdspProbe.cpp:55` `kPasAdsp = 1`），但按单实例加载 adsp.mbn，没有跨实例租约与握手；这部分是我们自己的设计 |
| `adsp-config-*`（`K60_BATTERY_CONFIG`） | sheng 没有该结构 |

### 3.3 sheng 是出处而不是旁证的三行

`charger-wire-opcodes`（owner 32778 / Get 0x50 / Set 0x51）、`charger-diagnostic-properties`（18 个属性号 0x17,0x19,0x16,0x32,…）、`charger-request-bytes`（52 字节）都能在 `package/ShengChargeAuth.c:5`、`:7-10` 与 `ShengChargeAuth.h:9` 找到，而且枚举与 18 个数值与我们的 `drivers/PongPower/K60ChargeAuth.c:8`、`:10-13` 相同（数组名不同：`ChargeDiagnosticCount` vs `K60ChargeDiagnosticCount`）。

正因为同源（我们的文件是那份文件的移植），它**不能**算独立第二来源：我们的文件是那份文件的移植。把它写成 `second` 等于自己给自己作证。这三行因此在 `HW-CONTRACTS.toml` 里保持 `second_unavailable`，`tried` 的第一条就写明“canonical 检出里有这一行，但它就是我们的移植来源”，`why` 说清能定这件事的是一个独立的 `xiaomi-mipps-auth` 检出。

这条区分本身就是结论：**同一份文本出现在两个仓库里，只有在两边独立产生时才叫第二个来源**；否则它证明的是“我们抄对了”，而不是“协议是这样”。

## 4. `CONFIG_XNU_OWNER_*` 解释不了 27 侧缺失的行

Lead 问的是：sheng 开了 8 个 `CONFIG_XNU_OWNER_*`，我们 27 侧那些 `missing` 行是不是就因为这些开关没开？答案是**不是**，三条证据：

1. **开关的语义与电源无关。** 它们是根策略与存储挂载开关：`XNU_OWNER_ROOT_AUDIT` / `ROOT_TRUST`（`UniXNU` 的 `concepts/security.md:14` 把它们归在“根策略”）、`CACHE_MOUNT` / `CACHE_STARTUP` / `DATA_MOUNT` / `BOOT_MANIFEST` / `UNION_SYSTEMOS` 加一个卷 UUID（`DATA_VOLUME_UUID`）。`NATIVE_RAM_BLOCK` 不是 OWNER 开关；`DATA_UFS` 与 cache 卷 UUID 是我们自己的开关。
2. **读它们的是构建脚本，不是电源代码。** `drivers/` 下 grep `XNU_OWNER` 仍是 0 处命中；实际读这些开关的是 `scripts/build-xnu-4k-baseline.sh:124`（决定 `offline-owner-systemos-mount.patch` 是否入列）、`:602`/`:611`（把 ROOT_AUDIT/ROOT_TRUST 传给 `bsd_init.o` 的 `-D`）与 `scripts/build-pong-ufs-probe-macos.py:48`（读 `CONFIG_XNU_OWNER_DATA_UFS`）。没有一处决定电池或温控 archive 是否编译。
3. **数字上也不是这个形状。** `sheng_ipados27_defconfig` 22 行、8 个 owner 开关；我们 `configs/mondrian_defconfig` 84 行、13 行 owner 开关；而 `configs/mondrian_ios27_defconfig` 26 行、**0 个** owner 开关、**0 个** K60 开关（`NATIVE_UFS` / `ADRENO` / `LEGACY_DISPLAY` 全为 n）。

真正的原因是第 3 条的后半句：27 侧 stage 0 停在 `bsd_init`（`configs/mondrian_ios27_defconfig:17-19` 写着这是有意的），它**根本没有链进**电池与温度那两个 archive —— 没有 `CONFIG_XNU_K60_PHYSICAL_BATTERY`（我们 16.6.1 的 `mondrian_defconfig:84` 是 y），也没有 `CONFIG_XNU_PONG_THERMAL`（`configs/mondrian_defconfig:69` 是 n）。

所以 `unchecked` 的 10 行（5 行 `K60ThermalMap.h`、5 行 `K60ChargeAuth.*`）是“27 还没走到电池阶段”，不是“开关没开所以读不到”。这两句话的差别决定下一步：前者要等 27 自己出 stage 1，后者今天就能补一个 defconfig。

## 5. 顺手带回来的一条工程结论：idle 采样两条路

同一个 16 ms 空闲采样，两边取数的方式不同：

| | sheng | 我们 |
|---|---|---|
| 取数 | 内核补丁加 `sheng_cpu_idle_mach()`，内部 `recount_processor_usage()` | `processor_info(processor_array[cpu], PROCESSOR_CPU_LOAD_INFO, …)`（`drivers/PongPower/K60CpuFreqProbe.cpp:637`） |
| 为什么这样 | 板级 kext 看不到 `struct processor`，只能让内核暴露一个函数 | 走 Mach 既有接口，不需要改内核 |

sheng 的 bringup 补丁把这条路的一个假象写得很清楚：一个空闲核不会收到 IPI，所以 `SIGPdisabled` 会让它**满速自旋**，于是“每个 cluster 在空闲桌面上都读出 busy=100%”。我们走 `processor_info` 不受这一条直接影响，但它给了一个判读准则：**读数是 100% 忙时，先怀疑采样口径，再怀疑负载**。这条写进了 `docs/research/power/01-EPSS-PROBE.md` 的 mode 5 一节（“空闲口径的判读准则”）。

## 6. 这份东西怎么用

- 写内核层或驱动层的新参考时，先在这里查 sheng 有没有对应实现；没有就明写“sheng 无”，不要写成“参考过 sheng”。
- 板级地址（carveout、PMP、PDMEM 窗口）永远以本机 FDT / 固件为准，sheng 是另一块板。
- `charger-wire-*` 三行的 `second_unavailable` 是**有意保持**的：sheng 的同一份文本是我们的出处，不是旁证。
- 27 侧离开 stage 0 时，`CONFIG_XNU_K60_PHYSICAL_BATTERY` 与 `CONFIG_XNU_PONG_THERMAL` 要和那 10 行文件一起过去；这两件事在 `docs/research/power/27-WORKORDER.md` 里是同一批工作。
