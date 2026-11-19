# iOS 27 电源移植清单（版本无关部分）

状态：**iOS16 平台睡眠暂停在“完整恢复未过”；本文件把可跨版本复用的电源策略、硬件事实、测试与移植顺序固定下来，iOS27 上按此重做，不逐行回放 8796 的 XNU 补丁。** 目标树为
`E:/hackios/xnekom-ios27`（`feat/ios27`），目标内核 XNU 12377.121.6 / Darwin 26，4 KiB 页、arm64e；板级仍是 K60（mondrian，SM8475），只是在构建/预链接层以 iPhone 16 Pro Max（iPhone17,2 / D94AP）的 iOS 27.0.1 24A446 档位作为身份与 fixture。

## 1. 为什么现在切换

- iOS16（8796，16 KiB 页）上已经把等待路径推进到 `IOCPUSleepKernel`：w9 完成 prepare/restore 和 timer PPI 27 唤醒，随后在 secondary 状态上 panic；w10 把 secondary 提前置 Stopped 后仍然在 `processor_start` 阶段硬挂，console 停止、只能手动复位。
- 这不是策略问题，而是 8796 的 `IOCPUSleepKernel`/ArmCpu 语义与我们的 vendored 驱动之间的耦合。继续在同一棵 8796 树上试错会反复消耗设备，而且这些行级补丁本来就不能直接用于 12377。
- 版本无关的部分已经稳定：八个纯 C 规划模块（含温控跳变点地图）、八套 host 断言、现场 EPSS/GPU/PMIC 事实、板级参数与文档。iOS27 先搬这些，再接内核。

## 2. 复用矩阵

| 资产 | 当前位置/状态 | iOS27 动作 |
| --- | --- | --- |
| `K60CpuFreqPlan`（EPSS 档位、governor、boost 窗口） | `drivers/PongPower/K60CpuFreqPlan.c`，host 203 项（含 DCVS_CTRL 回归与限频上限夹取） | **直接复用**；先跑 host，再接 iOS27 的 `processor_info`/EPSS 映射 |
| PDMEM perf-lock 投票（`0x17d09804/8/c`） | `K60CpuFreqPlan`/探针已接入，host 203，未上机 | **直接复用**；iOS27 先确认 ADT 的 `qcom,perf-lock-support` 与 PDMEM 窗 |
| L3 follow（mode 10，`0x17d90000` + `0x90`） | `K60CpuFreqPlan`/探针已接入，host 203，未上机 | **直接复用**；iOS27 先确认 L3 窗口与 `0x90` 投票语义 |
| 限频上限（`0x30c`=REG_INTR_STATUS，bit2=GT_IRQ_STATUS + `0x20` 低字节） | `K60CpuFreqPlan`/探针已接入，mode 1 只读打印 limits/cap，voteDomain 也按 cap 重建 LUT，host 203，未上机 | **直接复用**；iOS27 先确认 12377 的 EPSS 窗口仍暴露 `0x30c` 与相同 bit |
| `K60GpuFreqPlan`（13 档 OPP、HFI id 30 的 level+bus index、50% 目标、prewake） | `drivers/PongPower/K60GpuFreqPlan.c`，host 140 项 | **直接复用策略**；HFI/GMU 寄存器访问按 iOS27 的 Adreno 组件重接 |
| `K60BoostPlan`（触摸 1 s、4 窗 2 帧、300 ms/60%、fence 1 ms） | `drivers/PongPower/K60BoostPlan.c`，host 40 项 | **直接复用**；输入改为 iOS27 的触摸/帧通知 |
| `K60SleepPlan`（TLMM 掩码、PON 位、wake-after、背光/触摸时序） | `drivers/PongPower/K60SleepPlan.c`，host 73 项 | **直接复用**；板级 hook 只替换 IOKit/ArmCpu 接线 |
| `K60PowerVotePlan`（16 资源×32 owner） | `drivers/PongPower/K60PowerVotePlan.c`，host 58 项 | **直接复用**；消费者等外设驱动 |
| `K60RailPlan`（稳压器→互连→频率→回读、温控门、回滚） | `drivers/PongPower/K60RailPlan.c`，host 134 项（conformance 套件，含回滚） | **直接复用**；接真实 regulator/interconnect 消费者前保持纯规划 |
| `K60ThermalMap`（跳变点→等级→`allow_raise`/降档建议） | `drivers/PongPower/K60ThermalMap.c`，host 125 项 | **直接复用**；读数来源按 12377 的 tsens 节点名重接，策略不变 |
| `K60ChargeAuth`（充电认证握手状态机） | `drivers/PongPower/K60ChargeAuth.c`，host 99 项（HMAC 向量另 5 项） | **直接复用**；只依赖 `K60ChargeCrypto` 回调与 PMIC 属性名，27 侧换属性号与 `read_random` 接线即可，协议本身不变 |
| `test-k60-power-conformance.c` + `run-k60-power-host.sh` | 十套件 1915 项 | **直接复用**；作为 iOS27 的第一道门 |
| 跨版本搬运清单 `docs/research/power/CARRY.toml` + `scripts/check-power-carry.py` | 八个模块 16 个文件 872 项断言钉住哈希；`--target` 逐文件比对目标树的副本 | **直接复用**；iOS27 分支合并后跑 `python3 scripts/check-power-carry.py --target E:/hackios/xnekom-ios27`——2026-11-20 实测六个 `SAME`、`K60ThermalMap` 三个 `MISS`（该树停在温控提交之前）。清单同时钉住三个 console 判读器（handoff 33 / sleep 28 / mode1 14 例，夹具必须仍打印这个数）：同日实测 `judge-k60-mode1-console` 两个文件 `SAME`，`judge-k60-handoff-console` 与 `judge-k60-sleep-console` 的脚本与夹具都 `MISS` |
| iOS27 搬运前置检查 `scripts/check-ios27-power-preflight.py` | 一次读两棵树（本线 + `--tree`/`K60_IOS27_TREE` 指定的 27 检出），给出五类判定：tree、八个模块逐文件哈希、`sleep-report-guard`、`builder-route`、三个判读器是否已并入；18 项测试，退出 0/1/2 | **直接复用**；2026-11-20 对 `xnekom-ios27@ee910a78` 实测 **3 个阻塞**：`K60ThermalMap` 三文件缺、`0629-k60-sleep-trace.patch:7` 的 report 被 `#if defined(PONG)` 包住、`judge-k60-handoff-console.py`/`judge-k60-sleep-console.py` 未并入。同日这一行的 `0629` 已把门控改成驱动级宏 `K60_PLATFORM_SLEEP_REPORT`（补丁对 `xnu-8796` 的 `IOCPU.cpp` 能干净应用），门禁同时报警“提到 report 却没有这个宏”的形状；`builder-route` 已通过（该树 `board.toml` 已走 `build-xnu-generic.sh`） |
| mode-1 只读 A 判据 | `scripts/judge-k60-mode1-console.py`，14 cases；检查 capture、late read 三域 enable、L3 15 行、无写行与 SpringBoard | **直接复用**；iOS27 改 header/寄存器名后重跑 |
| 平台睡眠判据（catalog ArmCpu 路线） | `scripts/judge-k60-sleep-console.py`，28 checks：ENABLE/ENTER/PREPARE/HALT/RESUME/REPORT/WAKE/NO-PANIC，并把 resume panic 与“唤醒后硬挂”分开 | **直接复用**；iOS27 用 catalog ArmCpu 重做睡眠后，判据不变，只换行文本；`0629` 的门控已从 `defined(PONG)` 改成 `K60_PLATFORM_SLEEP_REPORT`（2026-11-20），否则 27 框上两份 report 会被预处理器删掉 |
| 只读 A 的现成镜像（iOS16） | image w11 离线构建于 2026-11-19 21:55，未上机：`E:/k60-work/artifacts/power-conformance-20261119w11/boot.img` 201,887,744 B sha256 `6db4e6b7…`，kernel `069e7075…`，参数 30 项 601 B（`k60_cpufreq=1`，无 `applog=1`） | 等 slot 即可飞 A；iOS27 用同一判据重判 |
| 现场事实：EPSS 三窗口 0x17d91000/2000/3000、L3 0x17d90000、4/3/1 核域 | `docs/research/power/01-EPSS-PROBE.md` | 复用；用 iOS27 的 ADT/FDT 复核地址与域映射 |
| 现场事实：GPU 13 档 900–220 MHz、HFI 升序、GMU XO 19.2 MHz | `docs/research/power/04-GPU-FREQUENCY.md` | 复用；HFI 版本/命令号按 iOS27 固件复核 |
| 现场事实：PMK8350 PON 0x13 IRQ 7 → SPI 481/INTID 513；TLMM 0x0f000000、汇总 SPI 208 | `docs/research/power/02-PLATFORM-SLEEP.md` §3 | 复用地址；PON 路由仍需驱动配置 |
| 板级参数 `platform-sleep`、`platform-sleep-wake-after`、`pong_*_dcvs` | `docs/engineering/BOOT-ARGS.md` | 保留命名；按 iOS27 的 boot-arg 解析点接入 |
| vendored `drivers/ArmCpu` + `0623/0624/0625` | iOS16 专用 | **不要逐行搬**；改用官方 catalog ArmCpu + sheng 的 xnu-12377 补丁 |
| `K60PlatformSleep.cpp` | timer-only 板级 hook，iOS16 API | **适配**：换成 catalog `armcpu_sleep_register` 的板级回调与 iOS27 的 IOPMrootDomain 通知 |
| ADSP/电池/充电认证 | 独立线（charge-auth 分支、battery §4） | 不在本清单；iOS27 另立 ADSP 端口 |

### 2.1 搬运前置检查（2026-11-20）

搬运清单只回答“八个模块的字节还在不在”。27 线另外踩过的三类坑不会让哈希变化，却会让一次
27 飞行毫无结论，所以它们也进同一个检查：

```sh
K60_IOS27_TREE=E:/hackios/xnekom-ios27 python3 scripts/check-ios27-power-preflight.py
```

- **sleep-report-guard**：`patches/xnu/0629-k60-sleep-trace.patch:7` 与 `:61` 把两条 report
  调用包在 `#if defined(PONG)` 里。27 线的机器 profile 不是 PONG（Lead 裁定：27 线不引入 PONG），
  于是 report 静默消失、`judge-k60-sleep-console.py` 的 REPORT 判据永远 FAIL。2026-11-20 已按
  Lead 裁定改成驱动级宏 `K60_PLATFORM_SLEEP_REPORT`（默认 1，`-D…=0` 关闭）：补丁开头定义一次，
  两处 `#if K60_PLATFORM_SLEEP_REPORT` 只管调用。本门禁同时拦两种形状——旧的 `defined(PONG)`
  是阻塞项，完全没有宏只算警告（"以后再套一个 #if 会再删一次"）。
- **builder-route**：调 27 树自己的 `scripts/pick-xnu-builder.sh board.toml`，要求它选
  `build-xnu-generic.sh`。选到 16.6.1 的 `build-xnu-4k-baseline.sh` 就意味着 `MACHINE_CONFIGS=PONG`，
  而 12377 源码没有 `pexpert/pexpert/arm64/PONG.h`，`make installhdrs` 直接停在
  `Unsupported CURRENT_MACHINE_CONFIG PONG`（bt 线 2026-11-20 的 CI 诊断）。该树实测已通过。
- **judges**：判读器是脚本，必须真的在 27 树里存在，否则飞行没有判据。只在本线存在时算阻塞，
  两边都没有时只算警告（还没写的东西不该阻塞别人）。

### 2.2 本分支的成果怎么交到 27 检出（2026-11-20 实测）

27 检出 `E:/hackios/xnekom-ios27` 的 `origin` 是 **xNekom 的 fork**，而且 fetch refspec 只有
`+refs/heads/feat/ios27:refs/remotes/origin/feat/ios27`——本线的 `feat/power-ios27-carry` 在那里
既不在 `origin/*` 里，也不会被 `git fetch origin` 拉到。要么临时加一个指向
`https://github.com/Emilelu/UniXNU-mondrian.git` 的 remote，要么按文件搬：

```sh
# 只取到 FETCH_HEAD，不留引用
git fetch https://github.com/Emilelu/UniXNU-mondrian.git feat/power-ios27-carry
python3 scripts/check-power-carry.py --target E:/hackios/xnekom-ios27   # 列出缺哪些文件
```

实测（2026-11-20，本线 HEAD `4023fd52`，27 线 `feat/xnu27-psci-target` `f902a778`）：

- `git merge-tree --write-tree` 合成无冲突（树 `a321fd2e`），但**整支合并不等于正确**：本分支带
  iOS16 的 profile、`board.toml`、`AGENTS.md` 与 16.6.1 的补丁序列，27 线要的是文件级搬运。
- 逐文件搬运以 `docs/research/power/CARRY.toml` 为准：八个纯 C 模块 + 三个上机判读器，各自带
  `.c/.h`、测试文件与用例数；`check-power-carry.py --target` 会按哈希说 SAME/DRIFT/MISS。
- 只想先要温控那一块时，三个提交（`d1ddea39`、`92c56173`、`9554ab7e`）的合并 diff 在 27 树上
  `git apply --check` 通过，可以直接 cherry-pick，不必整支合并。
- 拿不到分支时还有一个不看 git 的通道：
  `python3 scripts/make-power-carry-bundle.py` 按 `CARRY.toml` 把 8 个模块、3 个判读器、它们的测试
  与三份文档复制成 `build/power-carry-bundle/`（路径与仓库一致，附 `MANIFEST.sha256` 与 README）。
  在目标树里 `cp -a build/power-carry-bundle/. .` 之后再跑 `check-power-carry.py --target .`，
  每个文件应报 SAME。该工具本身由 `scripts/tests/test-power-carry.py` 覆盖（建包、逐文件哈希、
  把包当 target 通过、改一个字节必须被拒）。

## 3. iOS27 参考实现

- 官方组件：`UniXNU/ArmCpu`（catalog 路径 `drivers/ArmCpu`，当前 HEAD `73c2360` 已有 `ArmCpuSleep.h` 与 platform sleep；catalog 记录的 `93a5030` 早于该功能，取 HEAD 并记录 revision）。
- sheng 的 12377 补丁：`E:/hackios/UniXNU-sheng` 分支 `feat/platform-sleep-wake`，commit `927a458`，
  `patches/xnu-12377/sheng-platform-sleep.patch`（99 行）。它做四件事：
  1. 在 `osfmk/arm64/cpu.c` 声明并调用 `arm64_platform_sleep_hook`；
  2. 启动核 `arm64_platform_sleep_hook(TRUE); arm_init_cpu(cpu_data_ptr, 0);`（12377 的 `arm_init_cpu` 是**两个参数**）；
  3. secondary 在 `arm64_prepare_for_sleep(true)` 前调用 hook(FALSE)；
  4. `IOPMrootDomain` 在 `platform-sleep=1` 且 hook 已安装时清 `gSleepDisabledFlag`。
- 该补丁还带 cpu_common 的自 IPI 恢复（`sheng_sigp_recover`）；我们的 8796 树没有这个符号，12377 上要按 sheng 的原样接，不要删。
- 我们 iOS16 的 `0624`（boot-complete 事件 helper，绕过 `clientEntitled`）在 12377 上**不需要**：sheng 的路径在 `IOPMrootDomain` 里清 `gSleepDisabledFlag`，睡眠入口由正常电源事件驱动。若 12377 仍拒绝 `sleepSystem`，先查 `systemBooting`/`userDisabledAllSleep`/`pmPowerStateQueue`，不要搬 0624。

## 4. 移植顺序

1. **基线**：在 `feat/ios27` 上先构建不带电源新代码的镜像，确认 bsd_init、SpringBoard、USB console 都成立；记录 boot.img/kernel/payload 与 console。
2. **策略先行**：把八个纯 C 模块和 host 套件原样带过去，先跑 `bash scripts/tests/run-k60-power-host.sh`；十套件数字必须与 iOS16 一致（1915），再跑 `python3 scripts/check-power-carry.py --target <iOS27 树>` 确认八个模块逐文件一致，并确认新增的 `scripts/check-power-portability.py` 通过（八模块无 IOKit/XNU 依赖，freestanding C11 可编译）。这一步不需要设备。
3. **组件替换**：用 catalog ArmCpu 替换 vendored `drivers/ArmCpu`；确认 `armcpu_sleep_register`、stats、board 回调的结构体大小与 iOS16 版本一致（56 B/48 B），不一致就按 12377 头文件改板级。
4. **XNU 补丁**：把 sheng 的 12377 补丁按当前 12377 源树重放；只保留 hook、`arm_init_cpu(cpu_data_ptr, 0)`、secondary hook、IOPMrootDomain 清标志、sigp 恢复。不要带 0623/0624/0625。
5. **板级 hook**：先 timer-only（无 PON），`platform-sleep=1` + `platform-sleep-wake-after=5`；prepare/restore 只累加计数，不在关中断上下文打印；唤醒后在安全上下文打一条 report。
6. **唤醒链**：确认 `IOCPUSleepKernel` 的 secondary 恢复路径与 catalog ArmCpu 的 `haltCPU`/`processor_sleep` 语义一致；如果 12377 仍在启动核上调用 `haltCPU`，按 sheng/ArmCpu 的 `processor_exit` 语义处理，不要重复 w10 的“状态置 Stopped 后仍等 `processor_start`”死路。
7. **PON 电源键**：再接 SPI 481/INTID 513 的路由、锁存清除与按键吞掉；先做“按电源键唤醒”单测，再谈合盖/背光/触摸。
8. **策略接线**：CPU EPSS → GPU DCVS → boost/触摸/帧 → 外设投票；每接一条都保留默认关闭开关。

## 5. 验收判据

| 门 | 通过条件 |
| --- | --- |
| host | 十套件 1915 项全过；`check-power-portability.py` 报告 7 模块 freestanding C11 通过；`K60_POWER_SANITIZE=1` 的 ASan/UBSan 重跑通过；新增 iOS27 适配代码另有断言 |
| 静态 | kernel.macho 有 `_armcpu_sleep_register`、`_arm64_platform_sleep_hook`、板级 register/report 符号；无 `0624` 的 `k60_platform_sleep_boot_complete` |
| 默认启动 | `platform-sleep=0` 到 SpringBoard，无 prepare/restore；300 s autoreset 正常 |
| timer 睡眠 | `platform-sleep=1 platform-sleep-wake-after=5`：prepare=1、restore=1、last_intid=27、last_reason=timer，且 `IOCPUSleepKernel` 打印退出/`wake cpus done`，系统继续运行 |
| 电源键 | 按电源键唤醒，唤醒源为 PON，不是 timer；按键释放被吞掉，屏幕/触摸恢复 |
| 回归 | 连续两次睡眠/唤醒不 panic、不硬挂；CPU/GPU 频率与触摸在唤醒后恢复 |

## 6. 已知陷阱

- **不要在关中断/console suspended 上下文 IOLog**：iOS16 的 K60 USB log 会把它当 panic（w8 的 `Console I/O from interrupt-disabled context`）。只累加计数，唤醒后在 `console_resume` 之后打印。
- **secondary 状态**：w9 的 `Spurious wakeup of cpu 1` 是 secondary 在 CPU_OFF 前没有置 Stopped；w10 置了 Stopped 仍在 `processor_start` 处硬挂，说明状态位不是充分条件。iOS27 先读 catalog ArmCpu 的 `haltCPU` 实现，按它的 `processor_exit`/`processor_sleep` 语义接。
- **启动核 haltCPU**：iOS16 的 `IOCPUSleepKernel` 对每个 target 都调 `haltCPU`，包括启动核；我们的旧实现因此在启动核上进了 `ml_arm_sleep` 并等待其他核。iOS27 要确认 12377 的调用点，不能假设 8796 的行为。
- **EPSS `DCVS_CTRL` 是固件所有**：sheng 最新 `origin/main c8f92b2` 的 `package/CpuFreqProbe.cpp:132-142` 从不写 `0xb0`，只在 bit0 已为 1 时写每核 `perf_state +4×i` 行。我们的 mode 9 主动置 bit0，image t/u 都未枚举串口；iOS27 的 governor 必须只读 bit0、绝不置/清它；PDMEM perf-lock 投票（`0x17d09804/8/c`）是我们的新假设，尚未上机，若仍无效才接受 d1/d2 由 EPSS 独占。
- **catalog ArmCpu 的 haltCPU 只写状态**：`E:/hackios/ArmCpu/ArmCpu.cpp:1227-1233` 的注释说明它等 `processor_sleep()` 从目标核自己的上下文把核带下去（`cpu_sleep → quiesceCPU`），`haltCPU()` 只 `setCPUState(kIOCPUStateStopped)`。8796 的 generic `IOCPUSleepKernel` 没有 `processor_sleep`，只有 `haltCPU`；我们把 `haltCPU` 改成 `processor_exit_reason` 来补偿，w9 的 Spurious wakeup 和 w10 的 `processor_start` 硬挂就是这条错配。iOS27 先确认 12377 是否有 `processor_sleep`；没有就按 sheng 补丁/AppleARMSMP 的调用点改，不要只改 `haltCPU`。
- **两个参数**：12377 的 `arm_init_cpu(cpu_data_ptr, 0)` 与 8796 的一个参数不同；补丁重放时按 12377 签名。
- **4 KiB**：策略模块不关心页大小，但 ADSP/GPU/共享内存的缓冲区、DMA 与 prelink 都按 4 KiB 重算；不要把 16 KiB 的常量带过去。
- **iPhone17,2 是身份**：它只提供 iOS27 profile/kernelcache/prelink fixture（cupid 已用它到 bsd_init），不是把系统移植到 iPhone 16 Pro Max 硬件；K60 的 UFS/显示/触摸/PMIC 仍按本板事实。
- **0625 是 bring-up 调试**：K60TRACE 仍在 iOS16 的 series 里；iOS27 不搬，iOS16 发布前也应移除或标注。

## 7. 证据

- iOS16 w9：`E:/k60-work/evidence/power-conformance-sleep-w9-20261119-1311`（boot.img `0fc5a223…`、kernel `d87590f6…`、payload `2800c16a…`）。
- iOS16 w10：`E:/k60-work/evidence/power-conformance-sleep-w10-20261119-1328`（boot.img `4399eea5…`、kernel `20a0aac9…`、payload `0e686049…`；console 有 resumed/report，无 wake cpus done）。
- iOS16 默认启动：`E:/k60-work/evidence/power-conformance-sleep-z-20261119-1013`（image z，SpringBoard）。
- iOS27 目标事实：`E:/hackios/xnekom-ios27/docs/engineering/IOS27.md`。
- sheng 12377 补丁：`E:/hackios/UniXNU-sheng` `feat/platform-sleep-wake` `927a458`。

## 8. 边界

本清单只覆盖 §5 的电源策略与平台睡眠移植，不覆盖 ADSP/音频（§2/§3）、电池/充电认证（§4）、温控与显示/触摸驱动。iOS27 的 bsd_init 之前，不要在这条线上改 K60 的硬件驱动；先把纯策略、host 门和 12377 的 hook 准备好。
