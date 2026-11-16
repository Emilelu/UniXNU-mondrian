# WiFi series 死因考古（BOOT-DEATH-BISECT）

> 状态：**已结案（2026-11-16）**。死因是 UFS SMMU lease（P-215），**不是**本文 2026-11-15
> 静态二分指向的任何一条体积轴。本文保留静态二分的过程、判据与当时的错误排除，因为它是
> 「六条观测轴是怎么被逐条打掉的」的完整记录；结案证据与调用链以
> [BLOB-RESIDENCY.md](BLOB-RESIDENCY.md) §10 为准。
> 底稿：分支 `feat/wifi-ledger-fold` 的 `96e0a23` / `f9e5d0c`（旧结论保留原样的版本）。
> 任务来源：m04661（Lead 拍板选 C：停止复现 mhi4，改做死因考古）。
> 关联：`docs/research/wifi/LOCAL-VERIFICATION.md` §5.11–§5.20、`docs/plans/WIFI-REBUILD-CHECKLIST.md`。

---

## 0. 结论先行

1. **死因是 UFS SMMU lease（P-215）**：`patches/wifi/0004` 让
   `PongUfsTransport::hostBringUp()` 在 UFS 启动时索取 Apps SMMU lease，而锁只在
   `pong_rpmh_init()` 里 `IOLockAlloc`、唯一调用点 `pong_wifi_start_optional()` 由
   `ArmDTPlatform.cpp:227-228` 在 `registerService()` 之后调——晚于 UFS。于是 lock()
   返回 false ⇒ `transportFailure("Apps SMMU lease unavailable")` ⇒ UFS transport 放弃
   ⇒ 没有根设备 ⇒ 内核在 console worker 起来之前就死 ⇒ **0 字节**。
   `c3`（`patches/wifi/0012` 把分配改成惰性自建，20,480 B、单变量）与 `c2` 同版式、
   同真 PWF2 容器、同窗口、同 `pong_wifi=0`，就进了桌面
   （`usblog-20261116-015128`，console 221,429 B、SpringBoard 133）。
2. **本文 2026-11-15 指向的六条轴全部是观测轴，不是因果轴**：内核体积、`__TEXT` 驻留、
   pool/窗口通道、Data 卷 UUID、`pong_wifi=0` 保护、容器所在段。它们与死因只是**同步
   变化**——都被 `-Wl,-force_load` 一起带进内核。逐条否证见 §6.2 与 BLOB §6 的七格矩阵。
3. **判读顺序是三层，不是两层**：先 diff **构建配置**，再 diff **内核版式**，最后 diff
   **内核字节**。`c0` 是第二层的反例（构建配置打死内核，版式无关）；`c3` 是第三层的
   唯一正例（版式全同，只有 20,480 B 代码不同）。
4. **「0618 MHI 注入」不存在**：patches/xnu 没有 0618 号补丁；MHI 握手日志是
   `patches/wifi/0009` 的构建期注入（k60-wifi `6c99d35`），不改变 XNU 控制流（§4）。
5. **0011 的十级 stage 门与 console 门是纯延迟器**，worker 在
   `k60_usblog_console_up()` 之前不做任何 MMIO（§5）。
6. **series 229 本身不致死**：base-20261113d/f 用的就是同一条 229 行 series
   （`0076aa20…`）且进用户态；六个触摸探针（含无条件 SPMI MMIO 的 `spmi_probe()`）
   也在它们内核里（§3）。
7. **「内核大 ⇒ 死」被两次否证**：`bt-s4b-20261115b`（106.5 MB）进桌面、
   `bt-s4b-20261115c`（同尺寸、只多一个补丁）0 字节；`adsp-20261115c/d/e` 三张
   **128,991,232 B** 全部进桌面（`usblog-20261115-213413` / `-220912` / `-223916`）。
8. **本文 §6.2 把真死因亲手排除过一次**，这是本文最重要的教训：那一行写的是
   「0004 UFS lease……weak 符号为 NULL 直接跳过；只有锁函数存在且返回 false 才
   transportFailure；锁竞争在 console gate 之后的 isolation() 内」，前两句都对，
   第三句错——lease 不是在 `isolation()` 里取的，是在 **UFS 自己的 `hostBringUp()`**
   里取的，那一段早于 console、也早于 wifi worker。静态可达性分析只问了「这段代码
   在 console 之前可不可达」，没问「**别的子系统会不会在 console 之前走进这段代码**」。

口径冲突显式记录：Lead 在 m04661 里说 mhi4 是「224-series」，但 mhi3 与 mhi4 的
build-manifest.json 都记录 `series.count = 229`（`0076aa20…`）。以 manifest 为准；
「224」是 wifi 分支 rebase 后（e0825c6 退役探针）的当前 series 行数，与两张镜像无关。

## 0.1 三层判读顺序

| 层 | 问什么 | 手段 | 反例 |
|---|---|---|---|
| 1 构建配置 | defconfig / board.toml / kernel args 有没有把内核打死 | 逐字节扫镜像里的 UUID、args 合规检查（`scripts/check-arg.py`、`scripts/check-defconfig-uuid.py`） | `c0`：defconfig 指名种子 Data UUID ⇒ 根挂载自 panic ⇒ 0 字节（P-152/P-209） |
| 2 内核版式 | 段表 / 驻留位置 / 体积 / 窗口 | `LC_SEGMENT_64` 逐段 + ADT 窗口解码 | `t2`/`c2`：`__TEXT` 只 1,802,240 仍 0 字节 |
| 3 内核字节 | 同样的版式，代码差在哪 | 逐补丁单变量（`c2` → `c3`） | `c3`：只多 20,480 B 就活 |

前两层都只能产出「观测轴」。**只有第三层能产出因果轴**，因为它做的是单变量干预。

## 1. 被编译的源码在哪（静态分析的坐标系）

真正被编译进 mhi3/mhi4 内核的 XNU 源码树是构建产物的物化副本：

```
/opt/k60/trees/k60build/out-wifi/mondrian/ipados-16.6.1-20G81/mondrian/tree/.cache/xnu-work/
```

- `feeds/xnu-c465a9f8` 是未打补丁的干净上游（无 pong_goodix.c），仅作对照。
- 启动顺序锚点（xnu-work/bsd/kern/bsd_init.c）：`:1161 pong_goodix_init();`
  （触摸 bring-up，很早）→ `:1341 k60_usblog_start();`（USB 控制台，晚 180 行）。
  **任何在 :1161 与 :1341 之间发生的 MMIO 都发生在控制台可输出之前。**
- `bsd/conf/files`：`:110 bsd/dev/k60_metal_seeds.c standard`、`:400 pong_input.c standard`、
  `:401 pong_goodix.c standard`——三者无条件编入。
- 控制台就绪判据：`bsd/dev/k60_usblog.c:1595-1598`
  `k60_usblog_console_up(void){ return us >= 4; }`（`us` 为 static volatile int）。

wifi 驱动本体在 k60-wifi 仓 `drivers/PongWifi/`（PongWifiPlatform.cpp / PongWifiNet.cpp /
PongWifiPci.cpp / PongWifiFirmware.cpp / ath11k/PongAth11k.c），由 patches/wifi/0001 引入、
0010 用 `-Wl,-force_load` 链入内核（`build-xnu-4k-baseline.sh:922-926` KERNEL_EXTRA_ARCHIVES
与 `:1143-1147` PLATFORM_ARCHIVES 双路——mondrian 的 `.config` 里
`CONFIG_XNU_SOURCE_CORECRYPT14` 第二行 =y、末行 =n，后者生效，走 PLATFORM_ARCHIVES）。

**这一段坐标系漏掉的东西**（2026-11-16 补）：UFS 驱动不在 wifi 仓里，它在
`drivers/NativeUfs/`；而 `patches/wifi/0004` 会**改这个文件**。所以「wifi 补丁的
影响面」不等于「`drivers/PongWifi/` 的影响面」——它还包括它对别的子系统源码的插入。

## 2. 二分方法与判据

对 series 里每一段（patches/xnu/ 229 行历史 blob + patches/wifi/ 0001–0011）回答两问：

- **Q1 能否编进内核**：补丁是否被 series 列出、目标文件是否 `standard` 登记进 conf/files、
  产物内核里能否找到它的字符串指纹。
- **Q2 有没有 boot 路径副作用**：静态可达性——它的代码在哪个执行上下文里跑
  （SYSINIT / driver start / worker 线程 / 构建期），在 `k60_usblog_console_up()`
  之前是否可达，是否做 MMIO / 改内存布局 / 抢锁。

判为「死因候选」必须同时满足：Q1 成立（真的在内核里）且 Q2 成立（控制台启动前可达、
且能挂死或静默内核）。只满足 Q1 的，一律降级为「共存变量」。

**这两问有一个结构性盲点**（2026-11-16 补，写在这里而不是 §9，因为它决定怎么读 §6）：
Q2 问的是「这段代码自己在 console 之前可不可达」，它默认「这段代码只会在它自己的
上下文里跑」。而 0004 插入 UFS 的代码，跑在 **UFS 的上下文**里——UFS 是根设备，
必然早于 console。补丁自己的上下文（wifi worker）在 console 之后，被插入方的上下文
在 console 之前。所以正确的第三问是：

> **Q3 这段代码会被谁在什么时候调用？被插入的那个调用点，在 console 之前吗？**

Q3 缺失，就是 §6.2 把真死因排除掉的原因。

## 3. 对照证据：series 229 与两个窗口值都有「能起」的样本

### 3.1 series 229 有两个进用户态的样本

| 镜像 | series | board.toml | 内核 | console | 结果 |
|---|---|---|---|---|---|
| base-20261113d | 229 / `0076aa20…` | `de2f2c1b…`（4.75 GiB） | 54,181,888 B | 218,488 B | 进用户态 |
| base-20261113f | 229 / `0076aa20…` | `de2f2c1b…`（4.75 GiB） | 54,181,888 B | 223,923 B | 进用户态 |
| touch-20261114a | 223 / `5a18e929…` | `c349b984…` | 54,181,888 B | 268,137 B | 进 SpringBoard |
| wifi-20261116mhi3 | 229 / `0076aa20…` | `de2f2c1b…` | 65,978,368 B | **0 B** | 死（P-215） |
| wifi-20261116mhi4 | 229 / `0076aa20…` | `c63cd936…`（4.5 GiB） | 65,978,368 B | **0 B** | 死（P-215） |
| wifi-20261116c2 | 224 / `34cf51e4…` | — | 117,305,344 B | **0 B** | 死（P-215） |
| wifi-20261116c3 | 226 / `d83fb189…` | — | 117,325,824 B | 221,429 B | **活**（0012 修好 lease） |

（console 证据：`E:/k60-work/evidence/usblog-20261113-basef2`、`usblog-20261113-basef4`、
`usblog-20261114-150931`、`usblog-20261115-002804`、`usblog-20261115-002243`、
`usblog-20261116-000136`、`usblog-20261116-015128`。）

（口径：上表的 board.toml sha 与窗口值都是 identity seed 落 main **之前**
（`3ea8d71`，2026-11-15 14:40）构建的镜像快照。`3ea8d71` 起 `board.toml`
`[payload."adt"]` 增 `unique_chip_id = "required"`，新构建的 ADT 带
`/chosen/unique-chip-id`，board.toml sha 与 ADT 属性清单都不再等于上表——
`t2` 及以后的窗口/board 参照必须按各自 manifest 重算，不能沿用本表。）

### 3.2 六个触摸探针不是死因

229 series 的 :199-204（历史 blob）启用六个触摸探针补丁，全部只改 `bsd/dev/pong_goodix.c`。
其中 spmi-probe 新增 `spmi_probe()`（xnu-work/bsd/dev/pong_goodix.c:676 定义、
**:1296 无条件调用**，紧挨 :1297 `geni_spi_init()`），对 `0xc400000`（SPMI core, 0x3000）
与 `0xc440000`（SPMI observer, 0x80000）做 `ml_io_map` + 读——这在 `bsd_init.c:1161` 的
`pong_goodix_init()` 里、**早于 :1341 的控制台**执行。

但它不是死因：base-20261113d/f 的内核里同样有这些探针（boot.img 字符串实测
`K60LDO rev=12` ×2 存在），而它们进用户态。**结论：探针的 MMIO 在这块板子上能安全执行。**

### 3.3 窗口键不致死

- 4.75 GiB：base-20261113d/f（54.2 MB 内核，成功）vs mhi3 / wifi-20261115h2（65.9 MB 内核，失败）。
  注意这两个样本内核大小不同，所以「同窗口不同结果」本身不能区分窗口与内核——
  必须借 QEMU 阈值（下表）来判断余量。
- 4.5 GiB：mhi4（失败）；当时没有成功的 4.5 GiB 样本。

注（这一条直接决定「窗口排除」能不能成立）：§5.16 的 QEMU 定量模型
（required RAM ≈ window + kernel + 177 MiB）给出两个不同判决——

| 组合 | QEMU 阈值（最小成功 RAM） | 5120 MiB arena 余量 | 模型判决 | 实测 |
|---|---|---|---|---|
| 4.75 GiB + 54.2 MB（base-20261113d/f） | 5104 MB | 16 MB | 能起 | 进用户态 ✅ 一致 |
| 4.75 GiB + 65.9 MB（a2 / mhi3） | 5116 MB | **4 MB** | 勉强能起 | mhi3 0 字节 ❌ 不一致（但 4 MB 属噪声量级）|
| 4.5 GiB + 65.9 MB（h3q / mhi4） | 4860 MB | 260 MB | 能起 | mhi4 0 字节 ❌ 不一致 |

所以：**mhi3 的 0 字节当时还能用窗口解释（余量 4 MB），mhi4 的不能（余量 260 MB）**。
2026-11-16 的回填：这两张都是 P-215，与窗口无关；4.5 GiB 下 `c3`/`c4`/`c5`/`c6`
（117 MB）与 `adsp` 三张（129 MB）都进了桌面，窗口模型对这块板子已经彻底失去区分力。

---

## 4. 候选一：MHI 注入（Lead 点名「0618」）——排除

**「0618 MHI 注入」不存在**：

- patches/xnu/（229 历史 blob 与现行 224）都没有 0618 号补丁。wifi 线 06xx 段是
  0600 / 0602 / 0610-k60-metal-seeds / 0611–0616；全树 grep `0618` 只命中
  0503-k60-audio-aw882xx.patch:108 的 `GENI_M_IRQ_CLEAR 0x0618u`（音频寄存器值，无关）。
- MHI 握手日志的真实出处：k60-wifi commit `6c99d35`
  「feat(wifi): log the MHI handshake the console could not see」（2026-11-14 20:44），
  只改两个文件：patches/wifi/0009-scripts-k60-wifi-build.patch（+82）与
  scripts/build-k60-ath11k.py（+78）。手段是把 ath11k/mhi 源码里的 dev_dbg 改成 info、
  加符号链接（init.c/main.c/pm.c/boot.c/internal.h）——**纯构建期注入，XNU 控制流零改动**。
  产物在 `/opt/k60/trees/k60build/wifi/ath11k-mhiboot/`（mhi_boot.o、mhi_pm.o、
  ath11k_mhi.o、libPongAth11k.a 等）。

静态判定：

- Q1 成立：mhi4 kernel `Pong MHI` 格式串 11 处（实测），日志确实进了内核。
- Q2 不成立：这些日志的输出点全部在 worker 线程内、console gate 之后
  （`nw_wifi_start` 路径，PongWifiPlatform.cpp:675 之后）。worker 早在
  `pong_wifi_start_optional()` 里由 `PE_parse_boot_argn("pong_wifi")` 把守，
  而它被调用的唯一位置是 ArmDTPlatform.cpp:228（registerService 之后）。
  控制台 0 字节意味着死亡发生在 `bsd_init.c:1341` 之前——MHI 日志路径在那时
  根本没开始执行。

**排除**。但记录一条观察：worker 的日志走 IOLog，若控制台从未起来，日志同样丢失；
`6c99d35` 的初衷（console 看不到 MHI 握手）与本次 0 字节是两个独立问题。
（2026-11-16 回填：这条排除是对的——0009 只改构建脚本，不改任何 XNU 或驱动控制流。）

## 5. 候选二：0011 十级 stage 门——排除（且它恰是反死因的）

patches/wifi/0011-drivers-PongWifi-k60-bringup-stages.patch（141 行，wifi 线独有，
main 上不存在）给 PongWifiPlatform.cpp 加了两道门：

- **console 门**（:123-124 补丁原文；落地 PongWifiPlatform.cpp:655-656）：
  `for(;c<240&&!k60_usblog_console_up();c++)IOSleep(500);`
  等不到 120 秒就 `fail("console never came up; WiFi skipped before any MMIO")` 退出。
- **stage 门**：`stageOpen(n,what)` 十级（1 TLMM pinmux → 2 SPMI/PMIC → 3 cmd-db →
  4 RPMh/RSC → 5 GCC GDSC → 6 PARF/DBI/PHY → 7 82 项 PHY 表 → 8 PERST/LTSSM →
  9 APPSSMMU SID → 10 PARF MSI0），boot-arg `k60_wifi_stage=N` 挡 N+1 之后；
  缺省全跑。supplies() 拆成 2/3/4 三档（rail 数组上限 8）。

静态判定：

- Q1 成立：mhi4 kernel `held back by k60_wifi_stage` ×1、`k60_wifi_stage` ×2（实测）。
- Q2 不成立，方向相反：worker 的第一个动作就是等控制台（240×500 ms），
  **在控制台起来之前不做任何 MMIO**（0011 之前的行为——直接 MMIO——才是
  wifi-20261114b 0 字节的解释，见 LOCAL-VERIFICATION §5.1）。worker 是
  `kernel_thread_start` 起的独立线程，不阻塞主 boot 路径；
  `pong_wifi_start_optional()` 本体只做两次 `IOLockAlloc`（pong_rpmh_init, :727-731）
  + 一次 `PE_parse_boot_argn` + 一次 `kernel_thread_start`，无 MMIO。
- mhi3/mhi4 的 payload_args 30 项里**没有** `k60_wifi_stage`/`k60_wifi_rsc`
  → 门缺省全跑，不存在「门挡住了 MMIO 导致设备没起来」的静默失败路径会反噬内核。

**排除**。唯一理论风险是 `IOSleep` 在极早期被调用（worker 可能赶在 bsd_init:1341
之前被 ArmDTPlatform.cpp:228 调度），但 `IOSleep` 只让出 CPU，不做 MMIO，
不写控制台；最坏情况是 worker 先睡 500 ms 再查一次 `us >= 4`——静态上无害。

（2026-11-16 回填：这条排除也是对的。但注意它旁边那句话——「`pong_wifi_start_optional()`
本体只做两次 IOLockAlloc + 一次 PE_parse_boot_argn + 一次 kernel_thread_start，
无 MMIO」——正是死因的另一半：那两次 `IOLockAlloc` 里有 `smmuLeaseLock`，
而它是 UFS 需要的东西，却被安排在 UFS 之后才分配。）

## 6. 排除法之后剩下什么

### 6.1 wifi 镜像与能起镜像的完整差集

以 base-20261113f（能起，229 series，4.75 GiB）为基线，mhi3/mhi4（死，同 series、
同窗口、同 args 基础集）的差集只有三项：

1. **PongWifi 被 force_load 链入**：`PongWifi` 字符串 29 处、`Pong MHI` 11 处
   （base 是 0 / 0）。固件 11,189,974 B 以 `.incbin` 进 `__TEXT,__const`
   （PongWifiFirmware.s：`.section __TEXT,__const / .p2align 12 / .globl
   _pong_wifi_firmware / .incbin …`）。
2. **命令行多了 `pong_wifi=1`**（第 30 项；其余 29 项与 base/touch 完全一致）。
3. **内核 65,978,368 B vs 54,181,888 B（+11.8 MB）**。段级差异：
   `__TEXT` vmsize 12,992,512 vs 1,720,320（+11.27 MB，即固件）、
   `__TEXT_EXEC` 8,765,440 vs 8,355,840（+409,600）、`__DATA_CONST` 933,888 vs 917,504、
   `__LINKEDIT` 6,668,288 vs 6,569,984；PRELINK/PLK 各段逐字节同值。

**第四项当时没看见**（2026-11-16 补）：`patches/wifi/0004` 改了
`drivers/NativeUfs/PongUfsTransport.cpp`——一个**不属于 wifi 驱动**的文件。
它在差集里不显形，因为它不产生新的字符串指纹（那几行是调用，不是格式串），
内核里 `PongUfs` 串数在两边都一样。

### 6.2 已被逐一排除的共存变量

| 变量 | 证据 | 判定 |
|---|---|---|
| 六个触摸探针（含 spmi_probe 无条件 MMIO） | base-20261113d/f 内核含 `K60LDO rev=12` ×2 且进用户态 | 排除 |
| 0610 metal-seeds（k60_metal_seeds.c，99 行） | 无 SYSINIT、无 boot 路径 MMIO，static int + done 守卫；mhi4/base 内核都有 `k60_metal` ×14 | 排除 |
| 0615 md-window（memdev.c:707 k60_adsp_note_window） | 只记账，无 MMIO | 排除 |
| **0004 UFS lease（weak_import pong_smmu_lease_lock）** | 当时写「weak 符号为 NULL 直接跳过；只有锁函数存在且返回 false 才 transportFailure；锁竞争在 console gate 之后的 isolation() 内」 | **错——这就是死因（P-215）** |
| 元类重复（PongWifiNet.cpp:733-784 六个无条件 OSDefineMetaClassAndStructors） | 命中 K60 soft patch（patches/xnu/zzzz…-pong-duplicate-class-soft.patch，series :85）→ 只打日志并跳过第二个注册，不 panic；能进 launchd 的 boot-ab2.img 就有 2 行 duplicate 日志 | 排除 |
| IONetworkStack 首次引入 | 实例化只发生在 worker 内 coldLink → pong_wifi_net_prepare()（PongWifiNet.cpp:860）之后，即 console gate 之后 | 排除 |
| 0003 RSC 探针 | 只在 worker 内 stage 4 路径执行 | 排除 |

0004 那一行错在哪，写清楚（这是本文唯一需要背下来的教训）：

- 「weak 符号为 NULL 直接跳过」——对。但 `pong_smmu_lease_lock` 这个符号**存在**，
  因为 0001 定义了它。
- 「只有锁函数存在且返回 false 才 transportFailure」——也对，而且这正是实际发生的。
- 「锁竞争在 console gate 之后的 isolation() 内」——错。`isolation()` 是 wifi 侧
  的调用点；0004 插进 UFS 的那个调用点在 `hostBringUp()`，UFS 是根设备，
  在 console 之前几百行就跑完了。

### 6.3 剩余嫌疑与缺失的一格数据（已作废，保留原样）

> **2026-11-16 01:51 作废声明**：本节三条线索全部不是死因。`c3`（`c2` + 惰性锁
> 20,480 B）带同样的 blob、同样的 117 MB 版式进了桌面（`usblog-20261116-015128`），
> 真因是 UFS SMMU lease（P-215，BLOB-RESIDENCY.md §10.2）。本节保留原样，
> 作为「当时为什么把死因指向体积」的记录。

排除后，死因必须从 §6.1 的三项里产生。三条静态线索：

1. **`pong_wifi=1` 启动的 worker 本体**：0011 之后的 worker 在控制台起来之前
   理论上无害（只有 IOSleep），但 `kernel_thread_start` 抢占 + `IOLockAlloc`
   的时机（registerService 之后立刻）无法用字符串证据进一步排除或证实。
2. **DarwinBoot 装载 65.9 MB 内核的窗口数学**（§5.16）：65.9 MB 在 4.75 GiB 窗口
   下模型阈值为 5116 MiB，5120 MiB arena 只剩 4 MB 余量。**这一项对 mhi4（4.5 GiB，
   余量 260 MiB）本应更宽松，但它也死了**——
   除非死亡根本不在窗口申请这一步，而在更早的 `ReadFile(Root, KernelPath,
   SIZE_128MB, …)`（DarwinBoot.c:558）把 65.9 MB 吃进 DXE pool 之后、
   UEFI 自身就已经不稳定。字符串证据无法区分这两者。
3. **固件 .incbin 11.19 MB 进 __TEXT,__const**：让内核跨越某个 UEFI/加载器的
   尺寸阈值。

**关键缺口**：干净的对照 `wifi-20261116a2`（65.9 MB 内核、pong_wifi=0、args 30 项
587 B 合规）**从未上机**。它的两个兄弟：
- wifi-20261115a（pong_wifi=0 但 `epoch=1 debug=1`）0 字节——**无效对照**，
  `check-image-args.py:52-56` 明文禁止这两项（debug=1 = DB_HALT 静默停机；epoch=1 破坏时钟基线）；
- wifi-20261115h2（pong_wifi=1 + k60_wifi_rsc=2，合规）0 字节——真驱动样本。

即：**「65.9 MB + pong_wifi=0 + 合规参数」的格子当时是空的**。

### 6.4 a2 的证据等级（P-201）

`wifi-20261116a2` 就是上面那一格的填充物，但它自己的 `build-manifest.json` 写着
`"note": "trial build outside build-strict.sh (flash gate blocked by the touch line)"`，
键只有 `tag` / `note` / `components` / `kernel_args` 四个——**没有 `series`、`repo`、
`frozen`、`gates`**。所以它与同队列镜像（mhi3/mhi4，series 229 / `0076aa20…` 全记）
不是同一等级的证据：**构建输入指纹不可复核**，只能核「这张镜像里到底有什么」。

这条教训已按 [docs/engineering/PITFALLS.md](../../engineering/PITFALLS.md) 的 **P-201**
（「绕过 build-strict.sh 造的对照镜像，证据等级自动降一级」，main `1d10955`）落号；
判定器与对账脚本看到没有 `series` 键的 manifest，把结论降级成「结构性观察」，
不许当作「变量已隔离」的证据。

a2 仍然可用的部分（实测，可直接当判据）：`boot.img` sha256 `0a1c2ec0…`、
payload kernel `e273b649…` 65,978,368 B、args 30 项 587 B（`pong_wifi=0`、
`debug=0x140`、`epoch=1793709100`）、`Pong MHI` 0 处（mhi4 是 11 处）、
`PongWifi` 22 处（mhi4 也是 22 处：force_load 在、体积相同）。
（2026-11-16 回填：a2 现在只剩史料价值——它的那一格已被 `c1` 正式填过，
结论是 silent 且有效。）

---

## 7. 上机判据：只判「有没有进用户态」，不再用于归因

本节只给判据，不执行。每张镜像约 2 分钟，中间必须回到 fastboot 再飞下一张
（`bash scripts/k60-device.sh boot <image>`）。

| 判据 | 观察 | 当时的结论 | 2026-11-16 的结局 |
|---|---|---|---|
| C1 66 MB + `pong_wifi=0` 出 200 KB 以上 console | `K60 USBLOG st=` / `K60PREV none` | 驱动活体是死因 | 载体换成 `c1` 后落在 C2 列（0 字节），本列无证据 |
| C2 同上但仍是 0 字节 | `capture.json` 的 `portSeen=false`、`bytes=0` | 内核体积/固件 residency 是死因 | `c1`（`usblog-20261115-231707`）与 `c2`（`usblog-20261116-000136`）都落这一列——但**这一列的归因是错的**，`c3` 推翻了它 |
| C3 出现 `PongWifi: console up after N ms; starting cold link` 之后才死 | 该行之后断流 | 死在 worker 的 MMIO 段 | 未出现（死亡早于 console） |
| C4 出现 `PongWifi: stage N (…) held back` 且后续正常 | 门生效、boot 继续 | 门机制健康 | 未出现（同上） |

**C1/C2 两列都不是死因所在**：死因是 UFS SMMU lease（P-215），它在 UFS 侧、在
console worker 之前，两列都没覆盖到。本表此后只用于判「镜像有没有走到用户态」，
不再用于归因。

**判据可执行化**：C1–C4 由 `scripts/judge-wifi-boot.py` 判定。输入一份
`console.log` 或整个含 `capture.json` 的采集目录，输出四态
`alive` / `driver-dead` / `silent` / `unknown`（退出码 0/1/2/3），并直接打印下一步。
判定行自身带 `[exit N]`：管道（`| head`、`| tee`）会把 `$?` 换成最后一段的状态，
而 `silent` 曾因此被读成 exit 0；要机器读就取裸调用的 `$?`，或在 bash 里取
`${PIPESTATUS[0]}`，过滤过输出时以行内的 `[exit N]` 为准：

```sh
python3 scripts/judge-wifi-boot.py E:/k60-work/evidence/usblog-20261116-xxxxxx
```

自测 `python3 scripts/tests/test-judge-wifi-boot.py`（11 例：两份真静默
`usblog-20261115-002243`（mhi4）/ `usblog-20261115-002804`（mhi3）、两份真进用户态
`usblog-20261115-003922`（thermal-20261114f）与 `usblog-20261115-012913`
（bt-s4a-20261114f，旧载体族），另加 worker 断流、worker 失败串、stage 门被挡、
无标识控制台、纯 fastboot 噪声、空文件六个合成样本，以及一例「消费者丢掉退出码
仍能从行内 `[exit N]` 读到」。每个用例都断言退出码本身，因为退出码是判定器进
自动流水线时的全部 API）。

**工具落位**：三件工具（`scripts/judge-wifi-boot.py`、`scripts/judge-z0.sh`、
`scripts/check-arg.py`）与两份自测已合入 main（合并 `4f56970`，登记 `3e6f110`，
tag `snap-r198`）；本节与 BLOB-RESIDENCY.md 的引用一律写 main 上的 `scripts/`
路径。

**引用纪律**：贴判定结果时写 **usblog 目录名**，镜像只作附注。证据目录与镜像
不是一一命名——`usblog-20261115-012913` 对应的是 `bt-s4a-20261114f`，而 bt 线
现在跑的是 s4b/s4c 受控对照对；只写「bt 健康镜像」过几轮就对不上号了。镜像名
从同目录 `boot.json` 的 `image` 字段取，不要凭记忆补。

**测试纪律**（P-202「绿得没有区分力」的同类）：判定器的测试必须跑真样本，且
真样本缺失时不能静默降级成 SKIP 还报绿。这套测试原先写死 WSL 路径
`/mnt/e/k60-work/evidence`，在宿主 MSYS 侧跑时四份真日志全部 SKIP，输出照样是
`TESTS OK`——门禁在，但已经没有区分力。现在路径按 `K60_EVIDENCE` → `/mnt/e` →
`E:/` 三段探测，WSL 与 MSYS 两侧都是 `11 cases (0 failure(s), 0 skipped)`；
任何一个真样本找不到就应当显式 SKIP 并在汇总行报出 skip 数，而不是假装通过。

**MHI 阶段不在本表**：silent 结案之后，`c4`–`c7` 的失败模式是**有日志的 `-110`**，
它已经不是「死因考古」而是「功能没起来」。`c7`（`usblog-20261116-122546`）把这条也
钉住了：设备 `exec_env=1`（SBL）、事件环为空、`amss entries` 打印 0 次 ⇒
`mhi_download_amss_image()` 从未被调用，**设备在 SBL 等 AMSS、主机在等 EE 事件**，
是死锁不是超时。判据只剩一条：`c8` 推完 AMSS 后 `exec_env` 是否从 1 变 2。
详见 [BLOB-RESIDENCY.md](BLOB-RESIDENCY.md) §11 与
[C7-READING-GUIDE.md](C7-READING-GUIDE.md) §5。

## 8. 不建议的做法

- **不要再靠 QEMU 推手机结论**。§5.16 的 QEMU 模型对「4.75 GiB + 65.9 MB」成立，
  但它预测 mhi4（4.5 GiB）应当更容易通过，实测却 0 字节。模型与实测已经分叉，
  继续用 QEMU 定量只会放大偏差。
- **不要再拿 mhi3/mhi4 当窗口对照组**。两者都带 `pong_wifi=1` + 同一内核，
  窗口是唯一变量但两个取值都失败——这对样本无法区分「窗口」与「驱动」。
- **不要用 wifi-20261115a 当 `pong_wifi=0` 证据**。它的 `debug=1`（DB_HALT，
  任何 debug trap 静默停机）与 `epoch=1`（重置时钟基线）本身就能造成 0 字节，
  `scripts/check-image-args.py:52-56` 已把它判为非法镜像。
- **不要用「字符串指纹在不在」判一条补丁的影响面**（2026-11-16 新增）。0004 改的是
  UFS 的调用点，它不产生任何新格式串，所以在差集里完全隐形。判影响面要看
  `git show` 的文件列表，不看内核里的字符串。
- **不要把「当时唯一的观测轴」写成「死因」**（2026-11-16 新增）。观测轴表格的结论列
  只能写「这是目前唯一还分得开生死的观测轴」，并附一行推翻条件。

## 9. 局限与证据

**局限**

1. 本文档 2026-11-15 的版本全部是静态判定：没有新增构建、没有新增上机。所有「排除」
   都建立在「该代码在 `k60_usblog_console_up()` 之前不可达」或「同代码在能起的镜像里
   也存在」两条静态论证上，不是运行时证明。**这次静态排除错了两次**：一次把真死因
   （0004 lease）排除，一次把体积当成死因。
2. 字符串证据来自 boot.img / kernel.macho 的 `grep -a`，只能证明「符号/格式串在
   内核里」，不能证明「该路径执行过」。
3. `pong_wifi_start_optional()` 的调用时机（ArmDTPlatform.cpp:228，registerService
   之后）与 `kernel_thread_start` 的实际调度点之间存在竞态窗口，静态无法消除。
4. 本文档不覆盖 UEFI 侧（`uefi-mondrian`）的行为差异；0 字节既可能来自内核死，
   也可能来自 UEFI 从未交接。区分手段见 §7 的 C1/C2。
5. 六触摸探针的「不是死因」结论只覆盖 base-20261113d/f 这一对样本；
   若探针与 wifi 驱动有交互（例如 SPMI 仲裁器状态被探针改动），静态无法排除。
6. 死因结论（P-215）来自**一次**单变量干预（`c2` → `c3`），不是重复实验；
   `c4`/`c5`/`c6` 是同版式的三次独立复现，但它们都带 0012，所以复现的是
   「修好之后能起」，不是「没有 0012 就会死」的第二次验证。

**证据清单**

| 事实 | 证据路径 |
|---|---|
| mhi3/mhi4 都 0 字节 | `E:/k60-work/evidence/usblog-20261115-002804/{console.log,capture.json}`、`…/usblog-20261115-002243/` |
| base-20261113d/f 进用户态 | `E:/k60-work/evidence/usblog-20261113-basef2/console.log`（218,488 B）、`…-basef4/console.log`（223,923 B） |
| touch-20261114a 进 SpringBoard | `E:/k60-work/evidence/usblog-20261114-150931/console.log`（268,137 B） |
| `c2` 0 字节 / `c3` 进桌面（单变量对） | `E:/k60-work/evidence/usblog-20261116-000136/`（0 B）、`…/usblog-20261116-015128/`（221,429 B） |
| `c4`/`c5`/`c6` 都进桌面 | `usblog-20261116-072728`（221,888 B）、`-075300`（221,969 B）、`-081646`（221,551 B） |
| wifi-20261115a 非法参数 | `E:/k60-work/artifacts/wifi-20261115a/build-manifest.json`（`epoch=1 debug=1`）+ `scripts/check-image-args.py:52-56` |
| wifi-20261115h2 合规但 0 字节 | `E:/k60-work/artifacts/wifi-20261115h2/build-manifest.json`（`pong_wifi=1 k60_wifi_rsc=2 debug=0x140 epoch=1793709100`，602 B） |
| wifi-20261116a2 从未上机 | evidence 全库按 imageSha256 join 零命中；其 args 30 项 587 B |
| series 229 全量 | `git show backup/pre-rebase-aad0e6d:patches/xnu/series`（229 行，sha256 `0076aa20…`） |
| 当前 wifi 分支 series 已退役探针 | `/mnt/e/hackios/k60-wifi/patches/xnu/series` = 224 行 `34cf51e4…`（e0825c6 retire the six one-off probe patches） |
| MHI 日志注入出处 | k60-wifi `6c99d35`；产物 `/opt/k60/trees/k60build/wifi/ath11k-mhiboot/` |
| 内核段表与尺寸 | `build-manifest.json` 的 `components.kernel_built`；扫描脚本 `E:/k60-work/scratch/refmine/probe-family.py` |
| 固件 .incbin | `/opt/k60/trees/k60build/wifi/native-mhiboot/PongWifiFirmware.s`（215 B）+ `PongWifiFirmware.bin`（11,189,974 B） |
| 重复类日志无害实证 | `E:/k60-work/evidence/usblog-20261112-203710/console.log:125,134`（boot-ab2.img 进 launchd） |
| 窗口 QEMU 定量模型 | k60-wifi `docs/research/wifi/LOCAL-VERIFICATION.md` §5.16 |
| 死因代码 | `drivers/NativeUfs/PongUfsTransport.cpp:29,143,174-181,602`；`drivers/PongWifi/PongWifiPlatform.cpp:152,716-718,729`；P-215 正文 `docs/engineering/PITFALLS.md:5337` 起 |
| 修法 | `patches/wifi/0012-drivers-PongWifi-lease-lock-lazy-init.patch`（20,480 B） |

**口径冲突记录**：Lead 在 m04661 称 mhi4 为「224-series」，但
`wifi-20261116mhi4/build-manifest.json` 记录 `series.count = 229`、
`series.sha256 = 0076aa20…`；mhi3 同。224 是 wifi 分支 rebase 后
（`e0825c6` 退役六个探针）的当前行数，与两张已构建镜像无关。本文档一律以
manifest 为准，并在正文 §0 复述该冲突。
