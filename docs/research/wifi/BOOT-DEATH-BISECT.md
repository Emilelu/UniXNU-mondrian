# WiFi series 死因考古（BOOT-DEATH-BISECT）

> 状态：**静态判定稿（2026-11-15）**。本文档只做「能否编进内核 + 有没有 boot 路径副作用」的
> 静态二分，**不构建、不上机**。上机判据在 §7，实验建议在 §8。
> 任务来源：m04661（Lead 拍板选 C：停止复现 mhi4，改做死因考古）。
> 关联：`docs/research/wifi/LOCAL-VERIFICATION.md` §5.11–§5.20、`docs/plans/WIFI-REBUILD-CHECKLIST.md`。

---

## 0. 结论先行

1. **「0618 MHI 注入」不存在**。patches/xnu/ 没有 0618 号补丁；MHI 握手日志是
   patches/wifi/0009 里的构建期注入（k60-wifi commit `6c99d35`），不改变 XNU 控制流，
   只在 worker 内、console gate 之后的路径输出。**排除为死因**（§4）。
2. **0011 的十级 stage 门与 console 门是纯延迟器**：worker 在 `k60_usblog_console_up()`
   之前不做任何 MMIO，缺省（mhi3/mhi4 的 payload_args 没有 `k60_wifi_stage`）全跑。
   静态上它把风险推迟到控制台起来之后，**不可能是 0 字节的根因**（§5）。
3. **series 229 本身不致死**：base-20261113d / base-20261113f 两张已进用户态的镜像
   （console 218,488 / 223,923 B）用的就是同一条 229 行 series
   (`0076aa20902ad3029628352093ab8c074f8a2db77e2079b840a32bd1658dcfdd`)，
   连同六个触摸探针（含无条件 SPMI MMIO 的 `spmi_probe()`）也在它们内核里（§3）。
4. **窗口在 mhi4 上被排除；mhi3 的余量很薄**：同一个 4.75 GiB 窗口（`de2f2c1b…`）下，
   base-20261113d/f（54.2 MB 内核，模型阈值 5104 MiB，余量 16 MB）进用户态、
   mhi3（65.9 MB 内核，阈值 5116 MiB，余量只剩 4 MB）0 字节；而 mhi4（4.5 GiB，
   阈值约 4860 MiB，余量约 260 MB）**仍然 0 字节**。QEMU 模型对 mhi3 的判决是
   「勉强能起」、对 mhi4 是「余量充足能起」，两张却都死了 ⇒ 窗口可以解释 mhi3 的
   临界余量（4 MB 在真实板子上就是噪声量级），但**解释不了 mhi4**，后者才是
   「窗口无关」的硬证据（§3.3）。
5. **排除法后剩余的唯一实质差异**：wifi 线镜像 = base 线 + PongWifi 驱动被
   `-Wl,-force_load` 链入（含 11.19 MB 固件进 `__TEXT,__const`）+ `pong_wifi=1` +
   内核 65,978,368 B（比 base 的 54,181,888 大 11.8 MB）（§6）。
6. **最大证据缺口**：65.9 MB 内核 + `pong_wifi=0` 的干净对照 `wifi-20261116a2`
   **从未上机**；其 0 字节-vs-进用户态的分界至今没有数据（§6.3、§8）。

口径冲突显式记录：Lead 在 m04661 里说 mhi4 是「224-series」，但 mhi3 与 mhi4 的
build-manifest.json 都记录 `series.count = 229`（`0076aa20…`）。以 manifest 为准；
「224」是 wifi 分支 rebase 后（e0825c6 退役探针）的当前 series 行数，与两张镜像无关。

---

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
`CONFIG_XNU_SOURCE_CORECRYPTO14` 第二行 =y、末行 =n，后者生效，走 PLATFORM_ARCHIVES）。

## 2. 二分方法与判据

对 series 里每一段（patches/xnu/ 229 行历史 blob + patches/wifi/ 0001–0011）回答两问：

- **Q1 能否编进内核**：补丁是否被 series 列出、目标文件是否 `standard` 登记进 conf/files、
  产物内核里能否找到它的字符串指纹。
- **Q2 有没有 boot 路径副作用**：静态可达性——它的代码在哪个执行上下文里跑
  （SYSINIT / driver start / worker 线程 / 构建期），在 `k60_usblog_console_up()`
  之前是否可达，是否做 MMIO / 改内存布局 / 抢锁。

判为「死因候选」必须同时满足：Q1 成立（真的在内核里）且 Q2 成立（控制台启动前可达、
且能挂死或静默内核）。只满足 Q1 的，一律降级为「共存变量」。

## 3. 对照证据：series 229 与两个窗口值都有「能起」的样本

### 3.1 series 229 有两个进用户态的样本

| 镜像 | series | board.toml | 内核 | console | 结果 |
|---|---|---|---|---|---|
| base-20261113d | 229 / `0076aa20…` | `de2f2c1b…`（4.75 GiB） | 54,181,888 B | 218,488 B | 进用户态 |
| base-20261113f | 229 / `0076aa20…` | `de2f2c1b…` | 54,181,888 B | 223,923 B | 进用户态 |
| touch-20261114a | 223 / `5a18e929…` | `c349b984…` | 54,181,888 B | 268,137 B | 进 SpringBoard |
| wifi-20261116mhi3 | 229 / `0076aa20…` | `de2f2c1b…` | 65,978,368 B | **0 B** | 死 |
| wifi-20261116mhi4 | 229 / `0076aa20…` | `c63cd936…`（4.5 GiB） | 65,978,368 B | **0 B** | 死 |

（console 证据：`E:/k60-work/evidence/usblog-20261113-basef2`、`usblog-20261113-basef4`、
`usblog-20261114-150931`、`usblog-20261115-002804`、`usblog-20261115-002243`。）

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
- 4.5 GiB：mhi4（失败）；成功的 4.5 GiB 样本目前没有。

注（这一条直接决定「窗口排除」能不能成立）：§5.16 的 QEMU 定量模型
（required RAM ≈ window + kernel + 177 MiB）给出两个不同判决——

| 组合 | QEMU 阈值（最小成功 RAM） | 5120 MiB arena 余量 | 模型判决 | 实测 |
|---|---|---|---|---|
| 4.75 GiB + 54.2 MB（z0 / base-20261113d/f） | 5104 MB | 16 MB | 能起 | 进用户态 ✅ 一致 |
| 4.75 GiB + 65.9 MB（a2 / mhi3） | 5116 MB | **4 MB** | 勉强能起 | mhi3 0 字节 ❌ 不一致（但 4 MB 属噪声量级）|
| 4.5 GiB + 65.9 MB（h3q / mhi4） | 4860 MB | 260 MB | 能起 | mhi4 0 字节 ❌ 不一致 |

所以：**mhi3 的 0 字节仍可用窗口解释（余量 4 MB），mhi4 的不能（余量 260 MB）**。
「两张都死 ⇒ 窗口无关」只在 mhi4 这一张上成立；mhi3 与 mhi4 很可能死因不同。
要把 mhi3 也钉死，需要的对照是「4.75 GiB + 65.9 MB + `pong_wifi=0`」——那正是
`wifi-20261116a2`，从未上机（§6.3）。

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
   __TEXT vmsize 12,992,512 vs 1,720,320（+11.27 MB，即固件）、
   __TEXT_EXEC 8,765,440 vs 8,355,840（+409,600）、__DATA_CONST 933,888 vs 917,504、
   __LINKEDIT 6,668,288 vs 6,569,984；PRELINK/PLK 各段逐字节同值。
   内核 VM 跨度（Kernel.Base→End）：mhi4 0x15AC000 = 22.7 MB，baseline 10.7 MB——
   这个跨度直接进 DarwinBoot 的 `ArgsAddress = ALIGN_VALUE(Address + Kernel.End -
   Kernel.Base, SIZE_16KB)`（DarwinBoot.c:609）。

### 6.2 已被逐一排除的共存变量

| 变量 | 证据 | 判定 |
|---|---|---|
| 六个触摸探针（含 spmi_probe 无条件 MMIO） | base-20261113d/f 内核含 `K60LDO rev=12` ×2 且进用户态 | 排除 |
| 0610 metal-seeds（k60_metal_seeds.c，99 行） | 无 SYSINIT、无 boot 路径 MMIO，static int + done 守卫；mhi4/base 内核都有 `k60_metal` ×14 | 排除 |
| 0615 md-window（memdev.c:707 k60_adsp_note_window） | 只记账，无 MMIO | 排除 |
| 0004 UFS lease（weak_import pong_smmu_lease_lock） | weak 符号为 NULL 直接跳过；只有锁函数存在且返回 false 才 transportFailure；锁竞争在 console gate 之后的 isolation() 内 | 排除 |
| 元类重复（PongWifiNet.cpp:733-784 六个无条件 OSDefineMetaClassAndStructors） | 命中 K60 soft patch（patches/xnu/zzzz…-pong-duplicate-class-soft.patch，series :85）→ 只打日志并跳过第二个注册，不 panic；能进 launchd 的 boot-ab2.img 就有 2 行 duplicate 日志 | 排除 |
| IONetworkStack 首次引入 | 实例化只发生在 worker 内 coldLink → pong_wifi_net_prepare()（PongWifiNet.cpp:860）之后，即 console gate 之后 | 排除 |
| 0003 RSC 探针 | 只在 worker 内 stage 4 路径执行 | 排除 |

### 6.3 剩余嫌疑与缺失的一格数据

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
   尺寸阈值。z0（54.2 MB）在 QEMU 里 5104 MB 成功、a2（65.9 MB）要 5116 MB——
   在 5120 MB 的手机 arena 上，任何额外的 DXE 分配都可能把 65.9 MB 推过线。

**关键缺口**：干净的对照 `wifi-20261116a2`（65.9 MB 内核、pong_wifi=0、args 30 项
587 B 合规 `debug=0x140`/`epoch=1793709100`）**从未上机**——evidence 全库按
imageSha256 join 零命中。它的两个兄弟：
- wifi-20261115a（pong_wifi=0 但 `epoch=1 debug=1`）0 字节——**无效对照**，
  `check-image-args.py:52-56` 明文禁止这两项（debug=1 = DB_HALT 静默停机；epoch=1 破坏时钟基线）；
- wifi-20261115h2（pong_wifi=1 + k60_wifi_rsc=2，合规）0 字节——真驱动样本。

即：**「65.9 MB + pong_wifi=0 + 合规参数」的格子是空的**。补上它，才能把
「驱动活体（worker/锁/元类）」与「内核体积/固件 residency」这两类残余假设分开。

---

## 7. 上机判据（如果 Lead 决定再飞）

本节只给判据，不执行。每张镜像约 2 分钟，中间必须回到 fastboot 再飞下一张
（`bash scripts/k60-device.sh boot <image>`）。

| 判据 | 观察 | 结论 |
|---|---|---|
| C1 65.9 MB + `pong_wifi=0`（`wifi-20261116a2`）出 200 KB 以上 console | 控制台出现 `K60 USBLOG st=` / `K60PREV none` | **驱动活体是死因**：体积不是；下一步只在 worker 前置动作里找 |
| C2 同上但仍是 0 字节 | `capture.json` 的 `portSeen=false`、`bytes=0` | **内核体积/固件 residency 是死因**：与 `pong_wifi` 无关，回到 §5.16 的 arena 模型，改窗口或裁固件 |
| C3 出现 `PongWifi: console up after N ms; starting cold link` 之后才死 | 该行之后断流 | 死在 worker 的 MMIO 段（stage 1–10），可按 `k60_wifi_stage` 逐级二分 |
| C4 出现 `PongWifi: stage N (…) held back` 且后续正常 | 门生效、boot 继续 | 说明门机制本身健康，可用于后续分级上机 |

注意 §5.16 的窗口数学对「4.75 GiB + 65.9 MB」给出的是**余量仅 4 MB**的临界判决
（阈值 5116 MiB vs arena 5120 MiB）；a2 就是 4.75 GiB（`wifi-20261116a2w/a2q/a2r`
才是改窗口的三张），所以 C1/C2 用的是同一窗口、只差 `pong_wifi`。
也正因为余量只有 4 MB，C2 若成立仍需再用 4.5 GiB 版本复核一次（`a2q`），
才能把「体积」与「窗口」彻底分开——这正是 §6.3 缺失的那一格。

## 8. 不建议的做法

- **不要再靠 QEMU 推手机结论**。§5.16 的 QEMU 模型对「4.75 GiB + 65.9 MB」成立，
  但它预测 mhi4（4.5 GiB）应当更容易通过，实测却 0 字节。模型与实测已经分叉，
  继续用 QEMU 定量只会放大偏差。
- **不要再拿 mhi3/mhi4 当窗口对照组**。两者都带 `pong_wifi=1` + 同一内核，
  窗口是唯一变量但两个取值都失败——这对样本无法区分「窗口」与「驱动」。
- **不要用 wifi-20261115a 当 `pong_wifi=0` 证据**。它的 `debug=1`（DB_HALT，
  任何 debug trap 静默停机）与 `epoch=1`（重置时钟基线）本身就能造成 0 字节，
  `scripts/check-image-args.py:52-56` 已把它判为非法镜像。

## 9. 局限与证据

**局限**

1. 本文档全部是静态判定：没有新增构建、没有新增上机。所有「排除」都建立在
   「该代码在 `k60_usblog_console_up()` 之前不可达」或「同代码在能起的镜像里
   也存在」两条静态论证上，不是运行时证明。
2. 字符串证据来自 boot.img / kernel.macho 的 `grep -a`，只能证明「符号/格式串在
   内核里」，不能证明「该路径执行过」。
3. `pong_wifi_start_optional()` 的调用时机（ArmDTPlatform.cpp:228，registerService
   之后）与 `kernel_thread_start` 的实际调度点之间存在竞态窗口，静态无法消除。
4. 本文档不覆盖 UEFI 侧（`uefi-mondrian`）的行为差异；0 字节既可能来自内核死，
   也可能来自 UEFI 从未交接。区分手段见 §7 的 C1/C2。
5. 六触摸探针的「不是死因」结论只覆盖 base-20261113d/f 这一对样本；
   若探针与 wifi 驱动有交互（例如 SPMI 仲裁器状态被探针改动），静态无法排除。

**证据清单**

| 事实 | 证据路径 |
|---|---|
| mhi3/mhi4 都 0 字节 | `E:/k60-work/evidence/usblog-20261115-002804/{console.log,capture.json}`、`…/usblog-20261115-002243/` |
| base-20261113d/f 进用户态 | `E:/k60-work/evidence/usblog-20261113-basef2/console.log`（218,488 B）、`…-basef4/console.log`（223,923 B） |
| touch-20261114a 进 SpringBoard | `E:/k60-work/evidence/usblog-20261114-150931/console.log`（268,137 B） |
| wifi-20261115a 非法参数 | `E:/k60-work/artifacts/wifi-20261115a/build-manifest.json`（`epoch=1 debug=1`）+ `scripts/check-image-args.py:52-56` |
| wifi-20261115h2 合规但 0 字节 | `E:/k60-work/artifacts/wifi-20261115h2/build-manifest.json`（`pong_wifi=1 k60_wifi_rsc=2 debug=0x140 epoch=1793709100`，602 B） |
| wifi-20261116a2 从未上机 | evidence 全库按 imageSha256 join 零命中；其 args 30 项 587 B（`pong_wifi=0`，`debug=0x140`，`epoch=1793709100`） |
| series 229 全量 | `git show backup/pre-rebase-aad0e6d:patches/xnu/series`（229 行，sha256 `0076aa20…`） |
| 当前 wifi 分支 series 已退役探针 | `/mnt/e/hackios/k60-wifi/patches/xnu/series` = 224 行 `34cf51e4…`（e0825c6 retire the six one-off probe patches） |
| MHI 日志注入出处 | k60-wifi `6c99d35`；产物 `/opt/k60/trees/k60build/wifi/ath11k-mhiboot/` |
| 内核段表与尺寸 | `/opt/k60/trees/k60build/out-wifi/…/.cache/xnu-work` 产物；`build-manifest.json` 的 `components.kernel_built` |
| 固件 .incbin | `/opt/k60/trees/k60build/wifi/native-mhiboot/PongWifiFirmware.s`（215 B）+ `PongWifiFirmware.bin`（11,189,974 B） |
| 重复类日志无害实证 | `E:/k60-work/evidence/usblog-20261112-203710/console.log:125,134`（boot-ab2.img 进 launchd） |
| 窗口 QEMU 定量模型 | k60-wifi `docs/research/wifi/LOCAL-VERIFICATION.md` §5.16 |

**口径冲突记录**：Lead 在 m04661 称 mhi4 为「224-series」，但
`wifi-20261116mhi4/build-manifest.json` 记录 `series.count = 229`、
`series.sha256 = 0076aa20…`；mhi3 同。224 是 wifi 分支 rebase 后
（`e0825c6` 退役六个探针）的当前行数，与两张已构建镜像无关。本文档一律以
manifest 为准，并在正文 §0 复述该冲突。