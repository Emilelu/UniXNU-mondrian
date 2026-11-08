# 历史 commit 台账（K60 iOS 移植）

> **用途**：commit 级流水台账（至 2026-11-03 收敛）——回答「这个 sha 是干什么的 / 当时为什么改」。
> **谁该读**：要查某条 commit 的背景时；**不回答**「现在卡哪 / 下一步」（去 INDEX/ISSUES/DECISIONS）。
> **边界**：事件结论以 DECISIONS.md 编号为准（darwin24 停更=第 1 条+D-2026-11-03-14；进度条基线=D-2026-11-03-10/11；ramoops=D-2026-11-04-01；清单几何=I-20261103-11）；本表只做 commit 索引，事件叙述不再扩写。

只读检索产物。范围：作者本人仓库的 git 历史（上游参考仓库单列）。标注「仅 commit 证据」表示结论只来自提交信息本身，未做代码级复核。时间均为提交日期（+08:00）。

## 0. 总览时间线

| 日期 | 阶段 |
|---|---|
| 2026-10-26/27 | K60 UEFI 基线 + 设备仓库基线；ios-sweet-k60 已先行走通 GPU/显示（上游 XTOM0706） |
| 2026-10-28 | 设备仓库迁 format 2；20G81 prelink 打通；内核启动到控制台 |
| 2026-10-29 | UFS 根卷接线（PongUfs）；显示补丁集（1440x3200）；ADT/CPU 拓扑 |
| 2026-10-30 | Data 卷 saga（RAM 盘→UFS 窗口）、trust cache 锁 panic、ramoops/pstore 取证、keybag |
| 2026-10-31 | watchdogd 攻防、sandbox 注册、sig=9 风暴归因受阻 → 用户决定弃 16.6.1；route-a-17（17.7.11）终点 → route-a-18（iPadOS 18/darwin24）开工 |
| 2026-11-01 | darwin24 二十七轮：FDT 假设证伪、prelink 缺口、面包屑定位、CPU 启动顺序 panic；晚间**回退 16.6.1**（恢复 profile/补丁系列/MACHINE_CONFIGS/Darwin22 启动顺序） |
| 2026-11-02 | 4 GiB 高窗口实测定稿（`fix/k60-measured-high-window`），回到用户态 abort 取证 |

## 1. Emilelu/UniXNU（fork，构建核心）

检出：WSL `/tmp/k60build`（`k60build` 分支）、`~/hackios/UniXNU`、`~/smp-core`（detached）、`D:\Android\k60-ios\UniXNU-fork`（旧快照）。
`k60build` 分支主线 25 条（倒序取全部）：

| sha | 日期 | 标题 | 解决什么 |
|---|---|---|---|
| db7177c | 10-31 | k60: give FBSDisplayMode a nonzero preferred scale | SpringBoard display-mode trap：FBSDisplayMode preferred scale 为 0 导致陷阱（对应设备仓 852fd65 的记录） |
| 8bbecce | 10-31 | k60: disable effaceable storage for the keybag | keybag 掉 effaceable 存储 |
| 3aa19a0 | 10-30 | k60: take the Data seed size as a workflow input | Data 种子尺寸参数化 |
| f0521fd | 10-30 | k60: publish /chosen boot-manifest-hash for launchd mount | launchd 挂载校验需要 manifest-hash |
| 5d8ed7f | 10-30 | k60: set /chosen debug-enabled so PE_i_can_has_debugger() is true | 打开调试判定 |
| 79a0e6a | 10-30 | ci: revert to macos-26 | macos-15 排队同样久且缺 Xcode 26 → **回退** 72000fd |
| 72000fd | 10-30 | ci: try macos-15 | macos-26 容量枯竭的尝试（后被 79a0e6a 回退） |
| f372a28 | 10-29 | k60: restore the 33 prelink roots (revert the cluster removal) | **回退** 069fbb0：删掉 Apple 平台簇后 prelink 根缺失，恢复全部 33 roots |
| 7bf70ad | 10-29 | k60: fix the prelink roots list after dropping the Apple platform cluster | 069fbb0 的修补（仍不够，见上） |
| 069fbb0 | 10-29 | k60: keep the Apple Silicon platform cluster out of the prelink | 试图排除 Apple 平台簇（走错的开始） |
| 8a2d786 | 10-29 | k60: cap the ADT CPU count with [payload] cpus | ADT CPU 数受配置 cap |
| 58de14c | 10-29 | ci: upload the payload FAT alongside the native kernel | CI 产物 |
| 1f01eec | 10-29 | k60: drop generic driver build recipes | 驱动归档改由设备基线自持 |
| ade7a38 | 10-29 | k60: compile driver archives against the board machine records | 按板级 machine 记录编归档 |
| 48331ff | 10-29 | k60: include storage-abi headers when building PongUfs | PongUfs 缺 storage-abi 头 |
| f1f974d | 10-29 | k60: ADT whitelist for pong UFS/SMMU windows + cpu-id/max_cpus | ADT 白名单 |
| b37751a | 10-29 | k60: PongUfs catalog repository/revision for GHA module fetch | GHA 模块拉取目录 |
| 2dd28d1 | 10-29 | k60: PongUfs component (SM8475 UFS) wiring | PongUfs 组件接线 |
| 9f59b34 | 10-29 | profile: prelink com.apple.kec.pthread and set security-mode-change-enable | 20G81 profile 完善 |
| fc27d90 | 10-29 | ci: opt-in K60 data seed workflow | Data 种子 CI |
| 43c93c1 | 10-28 | profiles: add the 16.6.1 20G81 OS profile | **16.6.1 路线起点** |
| 9f65d07 | 10-28 | ci: opt-in upload of the native kernel | CI |
| 6d2b4a3 / 3450ca0 | 10-28 | macos Summary 修管 / ci trigger | CI 杂项 |
| ae68700 | 10-26 | docs: refresh device records | 上游同步（UniXNU Docs 署名） |

分支台账（19 个本地分支，全部围绕同一条主线，多数已并入 `k60build`）：`corek60`/`k60rev`（prelink roots 恢复点）、`k60roots`/`k60roots2`（簇排除实验）、`k60cpu`（CPU cap）、`k60dt`（ADT 白名单）、`k60edit`（PongUfs 目录）、`k60c2/c3/c4`（驱动归档编译三步）、`k60push`/`wf154`（CI 上传）、`wf15`/`wf26`（runner 漂移）、`oscfg`（20G81 profile）、`coretc`（/chosen debug-enabled）、`smp-0340`（0340 跳过 AppleARMCPU 校验，**注意：该补丁会破坏 darwin24 路线，设备仓 BRANCHES.md 明记不合入**）、`main`（跟踪上游）。
另：`git log --all --not k60build` 的溢出提交全部来自上游 UniXNU 组织合并进来的分支（署名 rpone / UniXNU Docs / Cursor Agent / Sharky Wang，内容为 GPU/turnip、sheng 设备、文档），非本项目工作。

## 2. Emilelu/UniXNU-mondrian（设备仓库，222 提交）

检出：WSL `~/hackios/UniXNU-mondrian`（`fix/k60-measured-high-window`）+ `~/hackios/work-display/device`（`main`）。工作区现有 ~40 个脏文件（board.toml、dts、series、大量 scripts），属 11-02 内存窗口工作，未提交。

### 2.1 基线（10-27 → 10-28）

| sha | 日期 | 标题 | 解决什么 |
|---|---|---|---|
| 6c45c58 | 10-27 | mondrian: K60 UEFI device support baseline | 设备仓库起点 |
| c25caf3 | 10-28 | mondrian: console-first kernel config and 20G81 prelink | 控制台优先的内核配置 |
| ae1c65d | 10-28 | porting: migrate the K60 device repository to format 2 | porting.toml format 2 迁移 |
| 2245a1c | 10-28 | kernel: port the prelink early security initializer to 8796.141.3 | prelink 早期安全初始化移植到 16.6.1 内核 |
| 673b997 | 10-28 | kernel: leave AppleImage4 unstarted, its start function panics without a manifest | **无 manifest 时 AppleImage4.start() 必 panic** → 不启动 |
| eeccca0 | 10-28 | pong: leave AppleARMPlatform unstarted like AppleImage4 | 同理处理 AppleARMPlatform |
| 702480e | 10-28 | pong: give the Darwin 22 CPU topology a second cluster slot | Darwin22 需要第二个 CPU 簇槽位 |
| caa310e | 10-29 | pong: log duplicate prelink classes instead of panicking | prelink 重复类不再 panic |

### 2.2 UFS 根卷接线（10-29）

| sha | 日期 | 标题 | 解决什么 |
|---|---|---|---|
| 274daaa | 10-29 | mondrian: Phase 2 v1 - UFS root wiring | PongUfs 组件、userdata、dts UFS 节点、native-ufs 参数 |
| e40e548 | 10-29 | k60: name the UFS ADT node ufshc so the driver personality matches | ADT 节点名不匹配则驱动 personality 不命中 |
| 6b232b9 | 10-29 | k60: single-CPU ADT for bring-up (pong parity) | 先单核对齐 pong |
| 0526fcc→36a83f9 | 10-30 | eight CPUs and allow the unsealed read-only root / find SHNGROOT in the unixnu partition instead of Pong's userdata | 8 核；**SHNGROOT 改从 unixnu 分区找**（K60 与 pong 的分区差异） |
| 8d6395b / 3b1a152 / ebbdbf9 / b62e434 | 10-29 | IM4P 解析 / 绑定原始存储构造析构 / prelinked 地址空间推导存储绑定 / kernelcache 传给 prelink_placement | 存储绑定的 prelink 闭环（仅 commit 证据） |
| 1615c68 等 | 10-29 | data seed builder script（hdiutil .cdr 命名 ×3 次重复提交） | Data 种子构建 |

### 2.3 显示（10-29）

| sha | 日期 | 作者 | 标题 |
|---|---|---|---|
| 3de020b | 10-29 | A2 display | k60: display bring-up patch set for the 1440x3200 panel |
| 10e50a8/fef75ea | 10-29 | A5 | k60: countdown on the payload menu so first boot runs unattended（重复提交 ×2） |
| b8df9fc | 10-30 | XTOM0706 | k60: pin the current display scale in the board overlay（协作方提交引入） |
| acb5c2d | 10-30 | mzyxsl | k60: fix the board inputs the payload, lock and prelink steps read（协作方提交引入） |

### 2.4 Data 卷 saga（10-30，按序）

`d91dfe8` 启用 RAM-block Data 卷让 launchd 能挂 /private/var → `a8d4121` scratch 挂载 opt-in+全步 trace → `c3ef534` 改从真实 UFS Data 窗口挂载 → `33b832c` 删掉内存 scratch 盘 → `e548891` 为隔离卡死把 Data 窗口只读挂载 → `94ec2f9` union 之后挂 Data、默认只读 → `aa7a1f1` trace 首次 UFS 写找读写挂载卡点 → `655c1f8` Data 探针以 panic 收尾让结果不被滚屏冲掉 → `c62fcdd`→`19f8892` mkdir 结果从 panic 改回单行摘要 → `8bfa0dd` 强制 MNT_CPROTECT → `0f7d0f1` **回退** → `044af77` 再次强制 → `a6ff16b` **最终放弃 MNT_CPROTECT：真正的门是缺 key store** → `e2c4bf0` Data 挂载后建运行时目录 → `5af93db` 信任挂载结果而非被覆盖 vnode → `261f6ee` Data 卷查找指向再生成种子 → `c134e3f` 按请求尺寸校验种子。
涉及文件（仅 commit 证据）：kern_exec 挂载链、0239 目录补丁、seed 构建脚本。

### 2.5 trust cache / 签名（10-30）

`b424011` 启用 XNU_TRUST_CACHE_RUNTIME（**startup.c 真正读的是这个开关名**）→ `8327c1d` img4 未注册则推迟 runtime → `94fc4c7` 查询先答 not-found → `7aeed61` 随 sealed 卷带 20G81 trust-cache 包 → `1b9619b` 对 unsealed 用户态关签名强制 → `7b072c3` 给 non-sleepable RW lock panic 记名 → `f4b2dac` PPL trust cache 锁保持可睡眠 → `7a66e6b` 开 native trust cache 初始化 runtime 锁 → `132e55b` 锁修好前只留开关 → `8b82eb3` [payload] 注册 trust cache 白名单 → `df99f2e` 无 img4 初始化 trust cache runtime。

### 2.6 SystemOS union / owner cache（10-30）

`99b3cf3` owner cache 启动路径支持 SystemOS union 挂载 → `0586183` owner cache 挂载补全 Data 链 → `03c0357` 给 launchd 可写 Data → `4ffd2ad` owner cache 挂载不再只在 scratch 失败时跑 → `15780cd` 无法服务 dyld 时带 owner cache 状态 panic → `14a5aa6` init exec 旁报挂载状态 → `e3a9540` 探测 union root 上 dyld shared cache 布局 → `48d641c`→`ece7de8` offline-owner-systemos-mount.patch 的位置调整→**删除（被 systemos 挂载取代）**。

### 2.7 取证基础设施（10-30）

`d2c5e49` panic 发布到 Android pstore pmsg 区并复位 → `a024d02` debug=0x144 使 PE_i_can_has_debugger() 为真 → `469ab81`/`4594e82`/`c0eb3ea`/`7ec4333`/`aa8c08f` ramoops 补丁单 TU 化与接入 kern_exec 系列 → `5b5c03d` 报告 /private/var 缺失原因并证明 ramoops 镜像可用 → `de71f85` 资源监控缺失时压制其监视 → `ce509e2` 选软件 keybag 启动。
（后续 11-02 交接确认：**ramoops 实机不可用**，重启 DRAM 掉电；最终取证靠「屏幕不滚动 + 拍照」。）

### 2.8 watchdog / keybag / 崩溃风暴（10-31，署名 k60-ios 除注明外）

`1644482` 发布 IOWatchdog 并停 dump cores → `8c7f13b` watchdog 挪进 key store TU → `a0552d4` 挪进显示服务入口 → `34b26cb` 控制台报 watchdog 状态 → `82ff14e` **最终方案：通过 launchd policy 禁用 watchdogd**。
`4f283cd` 应答 MobileKeyBag 存包的选择子 → `ce1dd20` Data 挂载后写明文 plist 系统 keybag → `f8cfe47` key store 调用计数。
`7cfce0c`（Emilelu）**无条件注册 Sandbox 策略，退役 AMFI 替身** → `c9d49c0` 把 sig=9 风暴归因到未注册的 minimac 策略（文档）→ `8598c97`/`99eeba9` k60-no-lc=1 跳过启动约束（重复提交 ×2）。
→ **结果：风暴未停**（11-02 交接 §3.3 判定「26%→15% 的数字无效，屏幕在滚」）。

### 2.9 用户态停滞与显示收口（10-31）

`a24242a` 用户态停滞分析与新探针（文档）→ `6e92110` 0236 扩成 managed-memory + 面板报告 → `6d05ecf` 面板帧缓冲问题与 boot-arg 门控 cap（文档）→ `26c0780` 链接 PongAdreno、accel/ramoops 桥、IOMFB selector 回退 → `bea4d90` 平台归档链接修复 + 控制台字号缩放溢出修复 → `4918a1e` 观察已提交 exit reasons 而不改终止策略 → `0f6a15a` 发布 /chosen 身份（K60 参考移植所需）→ `e1e2b05` 0234-0236 入系列 → `852fd65` SpringBoard display-mode trap 与 scale 修复（文档，对应核心仓 db7177c）→ `7f57666` 显示缩放修复实测与进度条停滞（文档）→ `68df29e`/`6d4586b` 10-31 交接（进度条停滞、工具链缺口）。

### 2.10 route-a-17（17.7.11）与 route-a-18（iPadOS 18/darwin24）（10-31 → 11-01 上午）

| sha | 日期 | 标题 | 解决什么 |
|---|---|---|---|
| e5f23c4 | 10-31 | route-a: minimal series = the 62 patches that apply to xnu-10063 | 17.7.11（xnu-10063）最小补丁集 |
| 7ea7ce5 | 10-31 | route-a: add the core public-entitlements-header patch | entitlements 头 |
| 6e94f41 | 10-31 | route-a-17 final state: 0242 shim, BCM2837 machine, 17.7.11 profile | **17.7.11 终点**（后被 route-a-18 吸收） |
| 3e23d1d | 10-31 | route-a-18: first darwin24 kernel on Linux | darwin24 内核首次在 Linux 构建 |
| e24207d | 10-31 | route-a-18: darwin24 payload and boot image through the K60 pipeline | 走 K60 已验证流水线 |
| b38621f | 10-31 | route-a-18: darwin24 prelink data from the real 22H374 kernelcache | 真实 22H374 prelink 数据 |
| 1c674d4 | 10-31 | route-a-18: give the darwin24 kernel a K60 ramoops console | ramoops 控制台 |
| 31f68da | 10-31 | route-a-18: link the K60 platform layer into the darwin24 kernel | K60 平台层链接 |
| 449a204 | 11-01 | docs: route-a-18 handover, full state after 27 rounds | **二十七轮交接** |
| 61d39e2 | 11-01 | readme: announce the darwin22 -> darwin24 route change | 正式宣布路线切换 |
| 1659829 | 11-01 | docs(route-a-18): FDT 假设证伪，改记 prelink 缺口 | **FDT 假设证伪** |
| 353438b | 11-01 | docs(route-a-18): 状态表改为 prelink 缺口 + 面包屑方案 | 面包屑方案立项 |
| 74c0ec8 | 11-01 | xnu(darwin24): 0244 早期启动面包屑 | 8 槽写 0xA73FF000；文件 `patches/xnu-ipados18/0244-k60-breadcrumbs.patch` |
| 818694a / 934647b / 6463182 / 979939c | 11-01 | build/scripts: 幂等应用 0244、darwin24 内核构建+ADT+bootimg 校验、镜像校验、darwin24 prelink（5 root + 3 library-only） | 工具链 |
| a86eb84 / c326dfd | 11-01 | scripts: 面包屑块映射 PTE 静态模型 / ramoops 读回加面包屑页 | 面包屑读回 |
| e636e44 | 11-01 | xnu(darwin24): 面包屑改画帧缓冲 + arm_vm_init 内 6 个阶段 | 面包屑可视化 |
| ea64a62 | 11-01 | xnu(darwin24): 0245 PONG 簇数 1 -> 3 | 簇拓扑 |
| cc384bb | 11-01 | xnu(darwin24): 0246 把 0214 字号缩放移植到 darwin24 | 补丁移植 |
| 6cdcc21 | 11-01 | dts: CPU reg 改为真实 MPIDR（0x0-0x3 / 0x100-0x102 / 0x200） | **DTS 用真实 MPIDR** |
| d2af811 | 11-01 | fix(armcpu): start the processors the Darwin 24 way | Darwin24 启动顺序（针对 cpu_common.c:586 assert panic） |
| 3f0e785 | 11-01 | fix(smp): let the firmware pick, and let a woken core wait for its turn | SMP 让步 |
| 8d80731 | 11-01 | docs(route-a-18): the CPU start order and what the panic said | panic 全文归档（bc6 首次可读 panic） |
| 5033446 / e492683 | 11-01 | docs(route-a-18): 两条硬规则 + 上游 26/27 不迁移结论 / 记录上游 ipados27 SHA 与不迁移理由 | **26/27 不迁移三理由**（证据作废、补丁套不上、arm64e 零证据） |
| 556298e | 11-01 | Merge the darwin24 route into main | darwin24 并入 main |

### 2.11 回退 16.6.1（11-01 晚，**本台账最重要的回退链**）

| sha | 标题 | 含义 |
|---|---|---|
| b4198de | fix(board): point the repository back at the 16.6.1 profile | board 指回 16.6.1 |
| 1963891 | fix(series): restore the 16.6.1 patch set the storm was observed on | 恢复风暴发生时的 16.6.1 补丁系列 |
| dcb901b | fix(build): restore MACHINE_CONFIGS=PONG and pass the driver source through | 恢复 PONG 机器配置 |
| 0979d04 | fix(build): put the driver project's c++filt wrapper first on PATH | 构建修复 |
| 48abe35 | fix(armcpu): restore the Darwin 22 start order the 16.6.1 kernel links | **恢复 Darwin22 启动顺序**（当前 HEAD 所在提交） |

原因（仅 commit + 文档证据）：darwin24 卡在「loader 跳板执行（绿条）→ 内核进入后静默复位」；pong 的 darwin24 从未提供可复现实机证据（ROUTE-A-18-HANDOFF §2 自述「本项目的 bug 可能就是 pong 自己的 bug」）；27 轮后决定回到证据最完整的 16.6.1。

### 2.12 维护与文档（穿插）

`d6b6456` fork 决策记录 + 公共 fork 审计；`9595de1` 引入 fork 离线记录检查器；`52b7048` 设备文档 workflow 改手动；`0971b17`/`6dc9a7b` **Data ENOSPC 归因与 2 GiB Data 安装**（unixnu 剩余空间未用的实证）；`350d1c5` 分支台账（46 个 dev* 退役）；`a44d6ec` 上游生态与 iOS 16→27 阶梯；`1e611e7` 用归因式批处理规则替代「一次一个变量」。

## 3. Emilelu/uefi-mondrian（25 提交，全录）

| sha | 日期 | 标题 | 解决什么 |
|---|---|---|---|
| f92c387 | 10-27 | mondrianPkg init | 起点 |
| 78b6c1c / afcf934 / c774389 | 10-27 | 区名对齐 pong 惯例（splash→Display Reserved、xbl_dtlog→DT BLOB、SMEM/HYP/AOP 等） | 帧缓冲/IORT/内存图命名 |
| 1691b74 / 3520c3b / 07b7bd3 / aac7008 / c576cc5→c318b43→17e4166 | 10-27 | EnvDxe 断言死循环 → debug 构建容忍 → 移出 FV → APRIORI 排序 → 开源 RamPartitionDxe（SMEM item 15 提供 EFI_RAMPARTITION_PROTOCOL） | **EnvDxe 构造 ASSERT 卡 DXE 调度** |
| 367e8af | 10-27 | K60 minimal DXE: 只留开源骨架（丢掉整套 vendor 驱动栈） | 闭源栈不可构建 |
| 7d27120 | 10-27 | K60: BDS AfterConsole 自动启动 UniXNU app；加 RamDiskDxe；降 fb 日志刷屏 | 启动链 |
| f4cbb97 / 28d45ed | 10-27 | K60ButtonsDxe v7 arbiter 布局 → v3 自动识别 v5/v7/v2 | 按键 |
| 587c515 | 10-27 | mondrian: K60 UEFI bring-up baseline | 基线 |
| 43e245e | 10-28 | repo hygiene | Mu 补丁清单、死文件、gitignore |
| 4be99ad | 10-29 | reserve the ABL fastboot staging window | 保留 ABL fastboot 暂存窗 |
| 86dd47b | 10-29 | make a clean clone buildable | 干净克隆可构建 |
| 1a5006e | 10-29 | vendored: import pong UniXNUPkg + DarwinBootPkg, retire out-of-tree loader | vendor 化，退役树外 loader |
| eb47698 | 10-29 | drop the keypad idle auto-reset | 键盘空闲自动复位误触 |
| f679172 | 10-29 | docs: .fd rebuilds are not byte-identical | 构建非字节可复现的备忘 |
| e06211d | 10-31 | ci: build UEFI images on demand only | CI |
| （脏） | 11-02 | MemoryMapLib.c（XNU High Arena）、BootArgs.h（Darwin22）、Mu_Basecore 指针 | **4 GiB 高窗口工作，未提交** |

## 4. ios-sweet-k60（fork 自 XTOM0706；参考 + 协作，84 提交精选）

作者本人提交仅 4 条：`8c47846`（10-29，touch 接线 /k60-touch、ID 回读、rpmh 映射序修复）、`18d019b`/`91d5b3b`/`3fbaa5e`（CI runner 探测）。
上游（XTOM0706 / XTOM.汤姆 / miyu）关键弧：

- **GPU/GMU**（10-27）：`c931e70` 真实 HFI 队列表 → `19bc209` 固件缓存镜像过新上下文点亮 CM3 → `02b7d26` stage-1 上下文 → `ba4ecd1` RSCC/PDC 预序列 → `d1966be` 先唤醒 GPU RSC 再碰 RSCC、修 PDC/CX_MISC 窗口 → `6d0299f` 映射整个 16 MB GMU 缓存窗（0205）→ `5b438f8` **改为只映射固件写的窗口（0207）** → `6a4babb` GMU 冷启动对齐 SM8550 参考。
- **显示画布**（10-27/28）：`0ec402d` 把面板呈现为 iPhone X 1125x2436（0209）→ `c03653c` 画布覆盖改 opt-in（0211）→ `0814108` 画布宽高改 4 字节 data（0212）→ `2a89ddf` digitizer 1440x3200→1125x2436 映射（0214）→ `e7c1531` 报 1170x2532 画布让 UIKit 找到出厂位图（0217）→ `fdf570c` 发布显示模式、CoreAnimation 原生驱动（0218）→ `d11a3c0` **记录如何到达锁屏、触摸卡在哪**（关键文档）。
- **触摸**（10-28/31）：`12860b0` 触摸分阶段 bring-up → `2f07bed` pong Goodix-over-GENI-SPI 栈移植（0240-0243）→ `524598b` SE4 时钟与 QUPv3 root → `98d9698` SM8450 GCC 投票位 → `d92f36d` bit-bang SPI 兜底 → `0eea76c` **fifo 接口开关是 0x2008 不是 0x64**。
- **按键/RPMh**（10-31/11-01）：`c4a00a1` PON periph 0x13 电源键/音量减 + pm8350 GPIO6 音量加；`a5dda36` 按 QcomRpmh 重写 RPMh 投票（布局自适应 + ARC 等级索引）。
- **11-01 文档**：GPU 现状清单、iOS 26/27 评估、自签/越狱可行性、pandora（SM8850）拆解清单、相机可行性。

## 5. 其余作者仓库

- **UniXNU-sm8475-common**（3 提交）：`bff96bc` SM8475 共享平台支持 → `70f2026` CPU 节点按 unit address 命名 → `d0c90f1` 每个 CPU 节点打 Darwin 簇标签（10-28）。
- **PongUfs**：feed 缓存内仅见 `c959284`（10-29）vendor PongProbe.h 同目录引用。
- **work-display/pw**（5 提交，无远端）：`47e6b74` baseline → `b2374ba` 0210 原生画布 → `20534d7` 0211 显示启动 → `403186b` 0212 空加速器 → `6f5d6dc` 0213 首帧（10-29，署名 A2 display）。
- **UniXNU-pong**（参考，Chengdong-Yu）：本地多出 `e5f03fd`/`3d5ea22` 两条 **stash 记录**（10-31，"WIP/index on main: ab74f07 Mark UFS and APFS support available"），是作者在上游工作区暂存过的痕迹（仅 commit 证据）。上游本体为 iPadOS18/Darwin24 格式 2 移植（`f62243e` 等）。

## 6. 上游锚点（feeds 固定版本）

| feed | 版本 | 用途 |
|---|---|---|
| xnu-c465a9f8 | xnu-8796.141.3 | **16.6.1 主线内核基线**（xnu-work 的 origin） |
| xnu-b7545ced | xnu-10063.141.1 | 17.7.11 路线基线 |
| xnu-11417 | xnu-11417.140.69 | iPadOS18/darwin24 路线基线（route-a18 xnu-work 的 origin） |
| libdispatch-* | libdispatch-1325.120.2 | 用户态库参考 |
| mu_basecore | microsoft/mu_basecore | UEFI 框架 |
| corecrypto-2023 | ONLYA/corecrypto-2023 | NativeAES 闭环节源码构建（对应 `dda77e9`） |

> 未提交工作树的改动现状见 `E:\k60-work\HANDOFF-2026-11-02.md` §4/§8（kern_exit.c STR/corpse、MiniIOMobileFramebuffer 压缩等），不属于任何 commit，本台账不重复展开。

## 7. 里程碑 tag 登记（2026-11-03，分支收敛后形态）

> 分支收敛（D-2026-11-03-17）后，里程碑一律以 annotated tag 锚定，不再保留同名分支。
> 各仓分支只剩 `main`（+ mondrian 的 `archive/darwin24-main-20261103`、fork 的 `k60`/`k60build`）。

| tag | 仓库 | → commit | 里程碑 |
|---|---|---|---|
| `v0.0.9-premain-8598c97` | UniXNU-mondrian | `8598c97` | main 切换前锚（darwin24 时代远端 main 尖端） |
| `v0.1.0-progressbar` | UniXNU-mondrian | `66a603f` | M1 进度条+backboardd 首帧（内核树，126 提交重放） |
| `v0.1.0-progressbar-device` | UniXNU-mondrian | `48abe35` | M1 设备配置锚（board/dts/series 提交态） |
| `v0.1.1-ios16-main-merged` | UniXNU-mondrian | `3c1bea3` | 设备线合入 iOS16 main（merge = `c39ff29`） |
| `v0.2.0-darwin24-archive` | UniXNU-mondrian | `10d1be3` | darwin24 45 提交归档（iOS18 起点） |
| `v0.1.0-progressbar-core` | UniXNU（fork） | `db7177c` | M1 编排侧锚（FBSDisplayMode scale 修复） |
| `v0.1.0-high-window-fd` | uefi-mondrian | `e06211d` | 4 GiB 高窗口 FD 基线 |
| `v0.1.1-fd-darwin22` | uefi-mondrian | `6244582` | FD：Darwin22 boot_args + 实测高窗 arena |

被删除分支的 sha 对照（恢复用）：`progress-bar-20261102`=v0.1.0-progressbar；`baseline/progressbar-device-20261102`=v0.1.0-progressbar-device；`ios16-main-20261103`=main；`fix/k60-measured-high-window`(mondrian)=v0.1.1-ios16-main-merged；`a5-timeout`=`fef75ea`（已判吸收删除，diff 存档 `docs/archive/a5-timeout-fef75ea.diff`）；`baseline/progressbar-core-20261102`=v0.1.0-progressbar-core；`baseline/high-window-fd-20261102`=v0.1.0-high-window-fd；`fix/k60-measured-high-window`(uefi)=v0.1.1-fd-darwin22。

### 7.0 里程碑推进过程记录（收敛前，2026-11-03 早些时候）

判据：首次出进度条/backboardd 首帧、Data 扩容完成、首次进 launchd、内存阶梯通过等重大进展点。
凡有提交可锚定的进展点已打 annotated tag 并建基线分支（均已推送 GitHub）；无提交的进展点仅台账登记。

| # | 里程碑 | 日期 | 仓库 | tag | 基线分支 | 锚定 commit | 镜像/boot/payload sha | 达成能力 | 已知缺陷 | 验证 |
|---|---|---|---|---|---|---|---|---|---|---|
| M1 | 进度条 + backboardd 首帧（内核侧） | 11-02 20:03 | UniXNU-mondrian | `v0.1.0-progressbar` | `progress-bar-20261102` | `66a603f`（重定根后；代码尖端 `e4778db`） | boot `302a001b48fc…`；payload `0854bb38…`；kernel `65fbe51e…`；kcdata 版 `6153c2aa…`/`64ae6488…` | K60DATA rw 挂载、launchd 加载、backboardd 首帧 1440x3200 | xpcproxy spawn EACCES（site=1）、守护进程 sig=6/5、未进 SpringBoard、USB 日志未通 | ✅ 屏摄核实（11-02/11-03 多轮） |
| M1b | 同上（核心编排侧） | 10-31 | UniXNU（fork） | `v0.1.0-progressbar-core` | `baseline/progressbar-core-20261102` | `db7177c` | 同上镜像 | FBSDisplayMode preferred scale 非零修复（进度条渲染关键） | main 落后 org 556 | ✅ 同上 |
| M1c | 同上（固件侧） | 10-31 | uefi-mondrian | `v0.1.0-high-window-fd` | `baseline/high-window-fd-20261102` | `e06211d` | FD 打入 `302a001b…` | 4 GiB 高窗口 FD | 出货 FD 依赖未提交改动（BootArgs.h/MemoryMapLib.c/Mu_Basecore） | ✅ 同上 |
| M1d | 同上（设备仓侧） | 11-01/11-02 | UniXNU-mondrian | —（分支即锚） | `baseline/progressbar-device-20261102` | `48abe35` | — | 设备配置基线（board.toml/DTS/series 提交态） | 真实构建态 = 48abe35 + 未提交工作区（55 文件） | ✅（以上机镜像反推） |
| M2 | kcdata STR 诊断版 | 11-02 22:xx | 内核树中间态（无独立提交） | — | — | — | boot `6153c2aa…`；kernel `64ae6488…` | STR 自杀（sig=6）/被杀（sig=5）分类生效 | — | ✅ IMG_0180.JPG |
| M3 | 内存 4.5 GiB 通过 | 11-03 00:5x | uefi 工作区（改动未提交） | — | — | 无提交 | 镜像随 4g-quiet 轮次（后被重打包覆盖） | `mem=4608` 三数一致 | 后被 4.75 GiB 取代 | ✅ 屏摄 `mem=4608` |
| M4 | P1 argfix 进 launchd | 11-03 | 配置改动（无提交） | — | — | 无提交 | boot `310c25a8…` | 越过 vnode_rele_ext panic，进 launchd | — | ✅ 屏摄 |
| M5 | 内存 4.75 GiB 通过 | 11-03 | uefi 工作区（未提交） | — | — | 无提交 | `e5171421c6c6…` 轮标注未上机；通过轮 sha 未完整登记 | 按能进 XNU 判定通过 | 5 GiB 失败（加载器对齐缺口 128 KiB） | ✅ 屏摄（进 XNU） |
| M6 | Data 20 GiB 窗口写入 | 11-03 09-10 时 | 无 git 提交（分区内容） | — | — | — | 窗口镜像 `data-window-20354.img`，窗级 sha `adbbf0ddc4bb…` | 20354 MiB 窗口写入 + 全窗回读校验一致 | — | ✅ sha256 全窗回读 |
| M7 | 0305 探针定位 site=1 | 11-03 10:47 | 内核树现行态（= M1 归档分支） | （同 M1） | `progress-bar-20261102` | `e4778db`（代码尖端） | boot `bb0498dd…` | `execerr=13 where=spawn site=1` 定位到 spawn 属性段 | — | ✅ 屏摄 |

> 注：M1 内核归档分支的根为自包含根 `cad1c22`（树与 apple-oss `1b191cb` 逐字节一致；因浅克隆父指针悬空，
> GitHub 连通性检查拒收，故 commit-tree 重建无父根后重放 126 提交）。重放脚本与提交信息底稿存
> `E:\k60-work\git\`（`replay-baseline.sh`、`msg-*.txt`）。

### 7.1 darwin24 归档分支（2026-11-03，经用户决定）

- 分支 `archive/darwin24-main-20261103`（= 本地 `main` 尖端 `10d1be3`）与 annotated tag
  `v0.2.0-darwin24-archive` 已推送至 `UniXNU-mondrian` origin；**远端 `main` 未推、未动**（仍 `8598c97`，
  落后本地 main 45 提交）。
- 这 45 个提交 = darwin24/iPadOS18 归档线（构建链 17、文档/交接 12、route-a-17 终点 3、调研/规范 6、
  payload 探针 2、合并与台账 5），**与 iOS16/20G81 主线（`progress-bar-20261102`）互不混入**；
  对当前修复仅 `9807d4b`/`58746fc` 两条 payload 探针提交有借鉴价值，其余 43 条无直接帮助。
- 敏感面：凭据零命中；设备序列号 `6033dbec` 在远端已有公开记录、非新暴露；`deepseek-harness`
  绝对路径为新暴露（无凭据性质）。详见 `E:\k60-work\git\main45-report.txt`。
- **后续路线**：该归档分支即为将来 iOS 18（Darwin 24）重启的起点；路线决策（iOS18 排到 iOS16 基本可用之后）
  见 `DECISIONS.md` D-2026-11-03-14（含 persona 差异提醒）。

### 7.2 待定补丁草稿（mondrian 工作区，未入 series、未提交）

2026-11-03 用户决定：以下补丁文件保持 untracked、**不移动路径**（移动可能影响构建脚本的路径匹配），
登记用途与启用条件；启用时先补入 `patches/xnu/series` 再提交。

| 补丁文件 | 作用（自文件名/头部推断） | 为何未入 series | 何时可能用到 |
|---|---|---|---|
| `patches/xnu/zzyb-native-cryptex-os-view.patch`（174 行） | native cryptex OS 视图（疑为 dyld shared cache / cryptex 挂载视图探针） | 当前排查焦点在 spawn EACCES（site=1），不涉及 cryptex | 用户态推进到 dyld/cache 阶段后 |
| `patches/xnu/zzyc-owner-skip-launch-constraints.patch`（31 行） | owner 侧跳过启动约束（与已入系列的 0241 同族，疑为 owner-cache 路径变体） | 0241 已在系列内承担 skip-launch-constraints；zzyc 是未启用的备选实现 | 0241 被证明不足/冲突时 |
| `patches/xnu/zzzz…-k60-quiet-watch.patch`（22 行） | quiet-watch 观测（与已入系列的 quiet-wakes 同族） | quiet-wakes 已入系列覆盖 wake 观测；watch 为更细粒度变体，暂不需要 | 需要 watchdog 粒度观测时 |

## 2026-11-04 init-v7probe 写入 + 上机

- **写入**：四闸门全绿（11:28:44）。Gate1 备份 init-v6（sha `1533CC58C3E04132D101D6783DA14AC3CD84771380BF91B84AB5688A298305EA`，目录 `E:\k60-work\rollback\pong-init-20261104-112844`）；Gate2 dd `bs=4096 seek=2501111 count=9 conv=notrunc,fsync`；Gate3 整段回读 sha `CEF43EBB5A0AC4CC9466E4BC901910F9E9391BC9F89A35CD050B46CE2299F699`；Gate3b 裸前缀 sha `A00DA80E44415708FC415251357EAF2BC8C9E27C2E912EFD501D577254CA5CB1`（== init-v7probe）。
- **boot**：`fastboot boot E:\k60-work\candidates\4g-quiet\boot-ios16-4g-quiet-v5.img`（201,883,648 B，sha256 `310F7BC17EDF6EAFAAFF35824F60CEE735073DAC3E36A7140FBE102DD5F29792`，与 v6 上机同一份，含 XNU 内核 + `pong_init_path` 钩子），下发时刻 2026-11-04 11:30:05。
- **看点**（等屏摄）：`enter configure_ui_library` / `UI compatibility library absent; SKIP` / `exec original 20G81 launchd`；零换行 shim 下最后停在哪个字符串就是死点。

## 2026-11-04 init-v9alias 写入 + 上机

- **写入**：四闸门全绿（12:15:17）。Gate1 备份 init-v7probe（段 sha `CEF43EBB5A0AC4CC9466E4BC901910F9E9391BC9F89A35CD050B46CE2299F699`，目录 `E:\k60-work\rollback\pong-init-20261104-121517`）；Gate2 dd `bs=4096 seek=2501111 count=9 conv=notrunc,fsync`；Gate3 整段回读 sha `D398900E07662545B92F21825D4E30F6E237941893FA112774D34AE020229D6D`；Gate3b 裸前缀 sha `78DCEE4C412FC712DEB790C24D910C76F6D918010D96DF6D1662C06903DAED87`（== init-v9alias）。
- **boot**：`fastboot boot E:\k60-work\candidates\4g-quiet\boot-ios16-4g-quiet-v5.img`（201,883,648 B，sha256 `310F7BC17EDF6EAFAAFF35824F60CEE735073DAC3E36A7140FBE102DD5F29792`，与上机同一份），Sending OKAY 4.522s / Booting OKAY 0.150s / Total 4.906s，下发时刻 2026-11-04 12:16:10。
- **看点**：v9alias 第 5 条守卫——若生效打出 `Pong init: wallpaper alias SKIP (no source)`，随后 `UI compatibility library absent; SKIP` 与 `exec original 20G81 launchd`；若仍定住，TWRP 拉 `/private/var/pong/status.txt` 按 token 表翻译（最后 token = 死点；止 `B4x`=守卫内 stat 挂；止 `B4b`=进 mount 前）。

## 2026-11-04 init-v10guard 构建（未写设备、未 boot）

- **背景**：v9alias 上机早停被定性为 trace 观察者效应（I-20261104-05 拍板：status.txt 零痕迹，早停不可作为 mount 反证）；方向 = 撤观测变量、守卫保留并扩到 target-first，单独验第 5 条 mount（判读规则落 GAP-AUDIT）。
- **源**：`init.c.v10guard-mondrian-src`（sha `399cb8d9…`）——v9alias 删全部 trace helper（`g_trace_fd`/`trace_open`/`tr`）与 16 处 `tr()` 调用（A0-A4/B0/B1/B4a/B4b/B4e/B4s/B4x/B4y/C1/D1/D2/E1）；守卫改为 **target 首选判据**：`stat("/Library/Wallpaper")!=0` → `wallpaper alias SKIP (no target)`，`stat("/private/var/pong/Wallpaper")!=0` → `wallpaper alias SKIP (no source)`，任一缺失即整体 skip 不进 mount；greeting 改 `[v10guard]`；不新增任何文件写操作。
- **产物**：`init-v10guard` 34,880 B，sha256 `db7e4eee780fd357b93f52d740f3e980afde86449299457468ebf75d00b98865`（≤36,864 extent 断言过）。四版并列：v6 34,872/`25d23885…`、v7probe 34,880/`a00da80e…`、v9alias 34,880/`78dcee4c…`、v10guard 34,880/`db7e4eee…`。
- **编译（WSL）**：`/opt/unixnu-linux/llvm/bin/clang -target arm64-apple-darwin22 --ld-path=/opt/unixnu-linux/CommandLineTools/usr/bin/ld -Os -static -nostdlib -ffreestanding -fno-stack-protector -fno-stack-check -fno-builtin -I libmini -Wl,-e,_start -Wl,-pagezero_size,0x100000000 -Wl,-sectcreate,__TEXT,__entitlements,init-entitlements.plist -Wl,-x -Wl,-adhoc_codesign libmini/start.S libmini/mini.c init.c -o init-v10guard`。
- **工具链复算注记**：同命令重建 v9alias 与交付件逐字节比对——34,880 B 等长、otool 全节一致、symtab 69 符号一致；差异仅 16 随机 UUID 字节 + 96 ad-hoc 签名字节 + **10 个语义等价指令字节**（4× movi 零化编码 `0x6F↔0x4F`、1× 独立指令顺序交换）。此为编译器惯用法指纹：本机 clang-24 与历史构建（疑 mac 通道；对照 `/tmp/init-v3/init-v2-repro` 与 init-v2 的 8 B 差同族）不可字节复现，功能等价成立。`__data` 段随 `g_trace_fd` 移除消失（`__DATA` nsects 4→3）。
- **二进制证据（全过）**：trace 字符串（`/private/var/pong/status.txt`、`trace open failed`、`trace write failed`）0 命中；17 个 token 字面量在 `__cstring` 0 命中；守卫串 `(no target)`/`(no source)` 各 1 命中、`wallpaper aliases SKIP (stock view unavailable)` 1 命中（两调用点共用去重字面量）；greeting `[v10guard]` 1 命中、`[v9alias]`/`[v8trace]` 0 命中。
- **离线核实**：Data 窗（`data-window-20354.work.pristine-backup.img`，apfs 列目录）`/pong` 仅 `init`——`/private/var/pong/Wallpaper`、`stock-wallpaper` 均不存在（实测，与 GAP-AUDIT 互证）；OS 窗 `/Library/Wallpaper` 本地无镜像**离线不可核**（文档级：ios16 上游 init.c 同 5 条 views、build.py 不播种 Wallpaper，设计预期 stock 有该目录）——守卫 target-first 覆盖两种情形。
- **写盘脚本**：`E:\k60-work\usb-a-stage\scripts\write-pong-init-v10guard.ps1`（四闸门全继承；Gate1 锚定 v9alias 现值双断言：裸 sha `78DCEE4C…` + 段 sha `D398900E…`）。设备回 TWRP 后先 `-BackupOnly`，Gate2 起等放行。

## 2026-11-04 init-v10guard 写入 + 上机

- **写入**：四闸门全绿（13:55:02）。Gate0 state=recovery（TWRP）；Gate1 三值全等（device/host/expected 段 sha 均 `D398900E07662545B92F21825D4E30F6E237941893FA112774D34AE020229D6D`，双断言过），备份目录 `E:\k60-work\rollback\pong-init-20261104-135502`（`-BackupOnly` 预演备份 `…-135448` 同值在先）；Gate2 dd `bs=4096 seek=2501111 count=9 conv=notrunc,fsync`；Gate3 整段回读 sha `ED6C3BF17A7CD6E869802BCBCBC42A03C863A46799904EAAEF2339DA20BAF6E1`；Gate3b 裸前缀 sha `DB7E4EEE780FD357B93F52D740F3E980AFDE86449299457468EBF75D00B98865`（== init-v10guard）；Gate4 登记 WRITE-RESULT.json。
- **boot**：镜像先核 sha（`310F7BC17EDF6EAFAAFF35824F60CEE735073DAC3E36A7140FBE102DD5F29792`，201,883,648 B，**非 USB panic 版**），`adb reboot bootloader` → fastboot 在线（6033dbec）→ `fastboot boot E:\k60-work\candidates\4g-quiet\boot-ios16-4g-quiet-v5.img`；fastboot 原始返回 Sending OKAY 4.522s / Booting OKAY 0.150s / Total 4.785s，**下发时刻 2026-11-04 13:56:03**。只 boot，未 flash。
- **看点（判读规则见 GAP-AUDIT「判读规则（v10guard）」）**：① 4 条 SKIP 后打 `Pong init: wallpaper aliases SKIP (stock view unavailable)` 并继续到 `UI compatibility library absent; SKIP` → `exec original 20G81 launchd` ⇒ 第 5 条按守卫安全跳过、mount 死锁方向收束；② **4 条 SKIP 后仍定住** ⇒ 死点在第 5 条或其内核侧（`bindfs` 在本版 XNU 可能无可用路径），立刻切内核方向、不再加用户态探针；③ 守卫串 `(no target)`/`(no source)` 仅 stock-wallpaper plist 存在但源/目标缺失时出现（当前 Data 实测皆缺，预期走分支①）；④ 完全无 Pong init 输出 → 按 I-20261104-02 核 init 现址（LBA 2501111，裸 sha 应为 `db7e4eee…`）。**等屏摄。**

## 2026-11-04 Data 卷实读取证：写盘能力三重证实 +「hang」叙事大翻转（I-20261104-06）

- **动作（只读，设备 Android root adb）**：dd 拉容器头 128 MiB（skip=2494976 count=32768，sha `a1ce6709…`）与尾区 334 MiB（skip=7623424 count=81664，含现行 omap 根块 5128782——容器扩容后 omap 在高块，sha `73324ee1…`）；双 sha 校验一致；稀疏装配（21,340,618,752 B）+ 读护栏解析（83 次块读全在证据区内）。sidecar：`E:\k60-work\evidence\data-live-20261104\SIDECAR.json`。
- **目录项裁决**：`/pong` = { `init`, `status.txt` }；`/pong/init` 36864 B sha `ed6c3bf1…`（== Gate3 段值）/ 前 34880 B `db7e4eee…`（== v10guard）；**`/pong/status.txt` 39 B = token 全链 `A0 A1 A2 B0 B1 B4a B4e B4s C1 D1 D2 E1`（sha `b823e52c…`）——v9alias 跑完整个 init 并 exec 了 launchd**；`/cores`(1775)、`CoreDuet/Knowledge`、`IdentityServices/PDS`(uid 501)、timezone 双链接均为 init 所建且跨重启持久；`/codes`、`/containers`（uid 0，基线无，待归因——疑似 launchd 痕迹）。
- **结论**：用户 A/B/C 框架判定 = **A（修正判据版）写盘可用**；`.pong-write-check` 缺席系 unlink 设计使然。I-20261104-03/04/05 三条据此关闭移已解决区；坑 41（trace 观察者效应）更正作废、新增坑 43（自报成功≠落盘）/44（屏上最后行≠进程死点，console 静默死亡）/45（扫描未覆盖≠不存在）/46（raw 覆写不更新 inode.size，上限 35160 B）。
- **新前线**：console 静默死亡根因（CONSOLE 排水器升主线）+ launchd 进度归因；屏摄证据降级为辅助，盘痕迹升为唯一可信通道。

## 2026-11-04 launchd 活性 T1/T2 + console 链路走读（I-20261104-07）

- **T1/T2（任务 A）**：T2 快照（间隔 ~50 min，设备在 Android，未重启）与 T1 两区 sha 逐字节一致 ⇒ 窗口内卷静态（Android 不写 sda38）。**mtime 归因**：`/codes`、`/containers/{Bundle,Data,Shared,Temp}`、`/installd`、`/keybags`、`/db/com.apple.xpc.launchd` 均为 **epoch+35/36s**（时钟未校准段，早于 status.txt 的 44s）⇒ **launchd 起到 installd 层**；`/cores`、`CoreDuet`、`IdentityServices`、timezone 链接为 11-03 20:31:40（v5 镜像打包 epoch，历轮 init 所建）。
- **console 链路（任务 B，源码走读 progress-bar 树）**：`cnwrite`(cons.c:76)→`kmstart`/`kmoutput`(km.c:299/:347)→`kmputc`(:272 **G1**:275)→`console_write`(serial_console.c:517，**ramoops :520 在一切显示门之前**)→`_cnputs`(:269 **G3**:274)→`vcputc_options`(video_console.c:1239 **G4**:1241)→帧缓冲。三道断点候选：①**渲染到面板不再扫描的内存**（映射/滚动错乱，video_console.c:2956-2967、gc_scroll_up:1114，最吻合）；②disableConsoleOutput/gc_enabled 被关（:362/:2800，但 ARM 无 disable/release op 调用者，触发源待查）；③console_io_allowed arm64 panic 分支（serial_console.c:161-175，解释重启回 Android）。排除：vcputc_lock 死锁、ramoops 写阻塞（均与 E1 矛盾）。**区分实验**：内核 sysctl 导出环形区（accessor 现成 arm_init.c:175-191）或 drainer 落 `/private/var/pong/dbc.log`；屏死点后环尾有内核新行 ⇒ 显示侧死坐实。init 用户态读环**不可行**（无 phys 通道）。
- **文档**：ISSUES 新增 I-20261104-07；HANDOFF「不要重复尝试」补「再往 init 里加用户态探针」；SIDECAR 补 T2 段。

## 2026-11-04 里程碑定稿：pong 用户态适配已越过关键一步（mtime/内容归因）

- **追加取证（只读）**：补拉中部 4 MiB（skip=6590976 count=1024，sha `9e46916a…`；容器块 4096000-4097023，含 plist 数据块 4096025），小文件内容全部解析成功（plistlib 解 XML/bplist00）。
- **里程碑证据链（全部盘侧实测，不是推断）**：init（`status.txt` token 全链 `A0…E1`）→ launchd（`disabled.plist={'com.apple.watchdogd': True}`）→ installd 级骨架（`/codes`、`/containers/{Bundle,Data/System,Shared/SystemGroup,Temp}`、`/installd/Library`，epoch+35s，非 init 可造）→ cfprefsd（`.GlobalPreferences.plist` en_US/en）→ **SpringBoard**（`com.apple.springboard.plist={'BKNoWatchdogs':1,'FBLaunchWatchdogExceptions':{purplebuddy:100}}`）→ **设置助理跑完全部步骤**（`com.apple.purplebuddy.plist={'SetupDone':1,'SetupFinishedAllSteps':1,'SetupVersion':11}`）。`systembag.kb={'KeyBagKeys':b'SWEET'}` 占位，判移植侧 stub 写。**〔更正：同日复核（见下条）剔除 `.GlobalPreferences.plist`（种子自带，sha 与基线相同），其余各项经基线对照确认为运行时新写。〕**
- **口径变更（用户拍板）**：当前唯一卡点 = **观测通道**（console 静默死亡 I-20261104-07 + 无日志出口），不是用户态适配；下一步第一动作 = **USB 通道上机验证**；显示侧另开平行线不占关键路径；init 禁改（35,160 B 上限，余量 280 B）。
- **产物**：`references/BOOT-PROGRESS-MARKERS.md`（launchd 之后进度的盘侧证据清单，L0-L6 分层 + 判读纪律 + 取证流程速查）；HANDOFF/INDEX 状态段更新；ISSUES I-20261104-07 补「分工」分节。

## 2026-11-04 里程碑证据「种子自带」排除复核（用户要求，只读）

- **方法**：同一对照脚本分别解析基线镜像（`data-window-20354.work.pristine-backup.img`，xid=7 代）与 live 卷，9 个路径逐项比对存在性/内容 sha16/mtime；seed 侧查 `var.skel`、ios16 build.py、build-ipados18.py 生产者。
- **结果**：`/keybags/systembag.kb`、`…/Preferences/com.apple.{purplebuddy,springboard}.plist`、`/db/com.apple.xpc.launchd/disabled.plist` 基线**均无** ⇒ **运行时新写**（c=epoch+36s、m=epoch+39s）；`/mobile/Library/Preferences/.GlobalPreferences.plist` 基线已有且 **sha 相同（`633dfefd…`）= 种子自带，剔除出证据**；`/private/var/db/` 系四路径两版均无（无法判定，live 对应物在 Preferences 与 com.apple.xpc.launchd 下，已分别判定）。seed 侧：var.skel 只有 keybags 目录条目（:114）；ios16 build.py 无生产者；ipados18 虽播种同名 SetupDone 形态但非本窗构建管线，且 live 内容缺 `ForceNoBuddy` 键（与上游播种形态不符）→ 指向真实运行时 Setup 完成。
- **结论**：**部分成立**——里程碑除 `.GlobalPreferences.plist` 外全部成立。HANDOFF/INDEX/BOOT-PROGRESS-MARKERS 同步改口（剔除项明标）；sidecar 增「baseline_vs_live」节。

## 2026-11-04 显示交接链路查清（静态，新现场事实吸收）

- **新现场事实（用户确认）**：屏停在最后一帧控制台文字（非黑非白），无苹果标无进度条——内核控制台仍持帧缓冲；与盘侧「系统在跑」互洽（显示没交出去）。
- **机制（实测级）**：iOS 用户态画面（IOSurface→`IOMobileFramebufferUserClient`→swap）的**唯一交接点**在 [MiniIOMobileFramebuffer.cpp:1008-1012](file:///E:/k60-work/git/progress-bar-20261102/iokit/Kernel/MiniIOMobileFramebuffer.cpp#L1008-L1012)（`fGraphics=true` + `PE_initialize_console(NULL, kPEGraphicsMode)` + drawLayer）；`k60_textonly` 定义于同文件 :138（默认 0），在 :999-1007 以 `continue` 跳过每个 UI 帧 ⇒ 交接永不发生、内核文本独占面板。在役 cmdline 实证含 `-v … k60_textonly=1`（`candidates/4g-quiet/extracted/unixnu.toml:12`）；「无苹果标/进度条」另因 `-v` 文本路径下 vc_progress 本就不画（pexpert/arm/pe_init.c:542-558）。
- **判定**：**A（k60_textonly 是用户态画面唯一拦路点）成立（实测级）**；**B（iOS 侧显示驱动缺失）不成立（实测级）**——MiniIOMobileFramebuffer start() :390-483 起线程/发布 UserClient，MiniIOSurface.cpp:2050 启动，软件合成本地绘制、不依赖 GPU。剩余不确定（推断级）：SpringBoard/backboardd 是否真在提交 swap 帧（零成本旁证：屏摄 5s 摘要区是否已有帧计数）。
- **实验设计（不上机）**：仅 `k60_textonly=1→0`、其余 boot-arg 逐字不变，新 boot.img 只 `fastboot boot`。判据：① 切到图形 UI（Hello/Setup 完成画面，**非苹果标**）⇒ A 成立；② graphics 但全黑 ⇒ 交接发生但无帧提交（查 backboardd/WindowServer）；③ 仍停文字帧 ⇒ 交接未触发（开 `fbtrace=N`）。回退：只 boot，无持久影响。
- **文档**：ISSUES I-20261104-07 增「显示交接」分节；HANDOFF 下一步加第二列（显示交接实验，排 USB 之后）。

## 2026-11-04 gfx 实验（k60_textonly=1→0 cmdline 补丁）制作 + 上机

- **制作（不重编内核）**：`boot-ios16-4g-quiet-v5.img`（201,883,648 B / `310F7BC1…29792`）为基底，cmdline 在 ramdisk 窗内 unixnu.toml 的 args 行（@0x349B499，319 B）；`k60_textonly=1` 全镜像**唯一**命中 @55162233，**等长单字符替换**（`1`→`0`，0x31→0x30 @0x349B586）——**无长度变化，header 各字段（magic/ksz@8=548774/rsz@12=192MiB）、kernel 段、全零 trailer 均不动**（用户警告的「长度牵动 header 字段」本案不触发；格式按 splice 既有模型：4 KiB header + kernel 4 KiB 对齐 + 192 MiB ramdisk 窗 + 4 KiB trailer）。
- **硬校验（全过）**：① 字节级 diff 全镜像**恰好 1 字节**（@0x349B586）；② extract-cmdline 重提取 + 逐 token diff：**唯一差异 = `k60_textonly=1→0`**；③ 新镜像 201,883,648 B，sha256 **`65d8f2950a9f64995b99e42f58e4647483cf09beafdda123da8db6d35950e576`**；④ header 前 4096 B sha 相同、kernel 段 sha 相同（`6f34b220…`，证明未重编）、trailer 全零相同。
- **上机（只 boot，未 flash）**：`adb reboot bootloader` → fastboot 在线（6033dbec）→ `fastboot boot boot-ios16-4g-quiet-v5-gfx.img`；原始返回 Sending OKAY 4.538s / Booting OKAY 0.152s / Total 4.820s，**下发时刻 2026-11-04 15:41:02**。
- **看点（三判据，等屏摄）**：① 屏从文字切到图形 UI（Hello/Setup 完成画面——非苹果标）⇒ 交接成功（`k60_textonly` 唯一拦路点定案）；② graphics 但全黑 ⇒ 交接完成但无帧提交（查 backboardd/WindowServer 存活，非驱动问题）；③ 仍停文字帧 ⇒ 交接未触发（开 `fbtrace=N` 查 UserClient/swap 路径）。

## 2026-11-04 gfx 判读落地（判据 3）+ 盘侧 GUI 进程取证（T3）

- **判读（用户回报）**：gfx 镜像上机屏仍停 Pong init 文字帧 ⇒ **判据 3：交接未触发，没有任何进程提交过第一帧**（`fGraphics` 未置位）。
- **T3 取证（只读，Android；xid 15→16，sidecar `evidence/data-live-20261104/SIDECAR.json` T3 段）**：崩溃证据**全空**（DiagnosticLogs/cores/log/asl/diagnostics/uuidtext 全 0 项或不存在）；`/mobile/Library/Caches` 空；`/containers/*` 骨架在但内容全空；**`disabled.plist`/`purplebuddy.plist`/`springboard.plist` mtime epoch+39s→45s 被同内容重写**（新 checkpoint，数据块 4096025→4096029-31，内容逐键相同）。
- **判定 = ② 有启动痕迹但无崩溃记录**：SpringBoard/purplebuddy/launchd 在 gfx boot 内活着并重持久化状态，但**零崩溃报告、零帧提交** ⇒ 进程活着但没提交帧。**不是显示驱动问题**（驱动存在，前 A/B 判定）。下一步：查 swap 调用方（backboardd/WindowServer 的 IOMobileFramebuffer 打开/提交路径），候选通道 `fbtrace=N` 或内核日志出口（drainer/USB）。
- **文档**：ISSUES I-20261104-07 补判读结果与取证；HANDOFF §4 第二列改「交接未触发 → 查 GUI 进程」。

## 2026-11-04 晚 0301–0305 诊断补丁提交主线（本地）

- **commit**：`1c0f468ef5d74b763605b552e2be683dacdd939a`（`feat(series): add k60 diag probes 0301-0305`），分支 `fix/k60-measured-high-window`（本地 HEAD `3c1bea3` → `1c0f468`）。**已推送（2026-11-04 晚，用户单条批准）**：`git push origin fix/k60-measured-high-window`——远端原无同名分支，`[new branch]` 创建；远端尖端经 `ls-remote` 复核 == `1c0f468`；相对远端 `main`（`c39ff29`，未触碰）新增 commit 恰 1 条；无 force。
- **内容**：`patches/xnu/0301-0305`（沙盒直方图/execerr kxp/K60HB 心跳/kxq rate 与 site tags，共 5 文件 611 行）+ `series` 5 行——即 v5/v6/v9 镜像实际携带但从未提交、只存于 `/tmp/usb-a-stage/device` 工作树的诊断面（坑表 #42 发现的漂移源）。
- **方式**：plumbing（临时 index + commit-tree + update-ref），**刻意不碰工作树**（其上正跑着 console-export/init 两路脏改动）；提交后把工作树 series 补 5 行 + 补 5 个补丁文件 + 混合 reset 索引——工作树残差恢复为他方原有的 `+0243` 单行。
- **验证**：`git show --stat`（6 文件 616 插入）；同字节内容已经 2026-11-04 第三轮全量内核构建编译通过（0 error，kernel.macho `7cd756d5…`）；「HEAD+0301-0305 无 0300」形态未单独编译（0300 与 0301–0305 文件面不相交：`bsd/dev/k60_usblog.c`/`conf/files`/`arm_init.c`/`bsd_init.c` vs `kern_exec/kern_exit/kern_minimac`），理论风险已排除故未花一轮全量构建。

## 2026-11-04 晚 B 决策提交 + F1(cdc3) 重建

- **B 决策提交**：`d881352fa8100ee8f5dcd33455046d53d2128695`（`chore(config): adopt the B decision, drop the trust-cache path`），分支 `fix/k60-measured-high-window`（HEAD `1c0f468` → `d881352`）；内容 = defconfig 双 `y→n` + `board.toml trust_cache_sha256=[]`（**环 1–3**，与 `diffs/v4-baseline-config.patch` 原文逐字一致）。**已推送 fork**（`1c0f468..d881352` 快进，`ls-remote` 复核一致，main `c39ff29` 未碰）。
- **环 4（miniamfi 回退 pong 原文）**：经核实 `libkern/amfi/miniamfi.c:136` 在**当前树内已是 pong 原文**（`mini_tc_loadModule` 返回 `kTCReturnUnsupported`），载体 `diffs/v4-baseline-miniamfi-revert.patch` 为 0 字节空文件——无内容可提交，四环由此闭环。
- **F1(cdc3) 重建**（cdc2 clone + B 输入，其余不动）：内核 `dafb3c1510b344cf90ea466e3afede6c723b86aaf9e842f2f032a58e04f08413`（`trust_cache_init` 命中 **0** = v5 同指纹）；payload 不传 `--trust-cache`（`kernel.macho.trustcache` sidecar 命中 **0**）；`boot-usb-cdc3-20261104.img`（201,883,648 B，sha `43a383b67c154d12fa9d910c3dc6b15653fb177a9c938cd8500c23e27a8a9fb7`）；cmdline 闸门 PASS（v5 + 仅 `k60_usblog=2`）；`K60 USBLOG`×49、`K60HB`×1 在位。**只构建未上机**，等窗口。

## 2026-11-05 console-export 0306 上机 PASS（通道打通）

- **动作**：用户批准后 `fastboot -s 6033dbec boot boot-console-0306-20261105.img`（sha `56953b8c…`，201,883,648 B）；Sending OKAY 4.525s / Booting OKAY 0.150s；**未 flash/erase/GPT、未写任何分区**。XNU 退出后设备回 **TWRP recovery**（root 可读块设备）。
- **盘侧判读（实测，APFS OwnerData xid=19，按需只读解析）**：`/pong/console.log` inode 249、root:wheel、mode 0644、**size 24,715 B**（首轮同路径 0 B）。首行 `===== K60LOG boot epoch=1793709100 ring_total=24006 dropped=0 =====`，其后为真实内核输出：`K60 USBLOG: GDSC usb30_prim …`、`K60CONSOLE: font scale 3`、`Darwin Kernel Version 22.6.0: Thu Nov  5 11:41:56 CST 2026; emilelu:ios-obj/DEVELOPMENT_ARM64_PONG`（= 本轮构建），尾部 `Pong init: exec original /sbin/launchd` / `KE 2 1 init /sbin/launchd`。→ **PASS：sysctl 导出通道打通**（I-20261105-01 关闭）。
- **取证优化（本轮起强制）**：改用 `tools/apfs-device-read.py` 按需取块（本次 81 块≈324 KiB），产出 `DEVICE-READ.json` + `console.log.txt`(24,715 B) + `REPORT.md`，**不再落 21 GB 全量容器镜像**（坑 #61）。同时删除 E 盘与精确镜像只差 95 B 的重复全量件 19.9 GB，E 可用 62.95→82.82 GB。
- **遗留**：① `console.log` 权限仍 0644，应 0600；② marker/配额(16/64 MiB)/500 MiB floor/fsync/轮转/STOP 持久语义未加固，init 仅剩 248 B（34,912/35,160）需先做尺寸实验；③ `dropped=0` 仅本轮观测；④ USB reader 同源改动待 USB 线恢复后验证。

## 2026-11-05 console-export 修复 0306（root-only cursor + 统一 ring snapshot）

- **触发**：首轮盘侧判读（I-20261105-01）定位 0243 OID 为 RD-only、init 传 `newp` cursor，被 `kern_newsysctl.c:1709-1714` 前门拒绝；同时发现 writer/reader 无 generation，0243/USB/`kern_exec` 三个 reader 各自双读，无法证明一致性。
- **环境先决**：宿主 WSL2 曾不可用（I-20261105-02 / 坑 #58），用户授权后启用 `Microsoft-Hyper-V-Hypervisor`+`HypervisorPlatform` 并重启，`HypervisorPresent=True`，工具链与两构建树恢复。
- **实现（新增 `0306-k60-console-snapshot.patch`，16,001 B，sha `03db2b5a61c7de09918789ebff357efc40e3c3531531c77d085d33ced66b8e6a`）**：
  1. `osfmk/arm/arm_init.c` + `osfmk/arm64/pong_ramoops_console.h`：新增 `pong_ramoops_seq`；writer 在 busy 成功后用 odd/even sequence 包住一次写入，metadata 改原子发布，payload 保持 volatile byte stores + PoC clean + `dsb sy`；新增 `pong_ramoops_snapshot()`，读取侧 bounded（8 次）非阻塞；物理 12 B DBGC header 不变。
  2. `bsd/dev/k60_console_export.c`：OID 改为 `CTLTYPE_OPAQUE|CTLFLAG_RD|CTLFLAG_WR|CTLFLAG_LOCKED`（**无** `CTLFLAG_ANYBODY`）；handler 对每次请求（含无 newp 的读）用 `kauth_cred_proc_ref`+`kauth_cred_getuid` 做实 root 校验，只接受严格 8 B cursor；改用共享 snapshot；加 `sizeof==56` 与关键 `offsetof` 的 `_Static_assert`；不稳定快照返回 `EBUSY`（不返回 EAGAIN，避免 `userland_sysctl` 无界重试）。
  3. `bsd/dev/k60_usblog.c`：USB reader 改用同一 snapshot API，保留独立游标与首次 64 KiB 回放。
  4. `bsd/kern/kern_exec.c`：**未改**（init 前诊断仍走已原子化的 debug getters）。
- **构建**：新 out 目录 `/tmp/usb-cdc-mainline/out3`（不复用 out2 脏树）。首跑失败于 fakeroot 缺 `Availability.h`（坑 #35 复现，用 out2 fakeroot 头集补齐）；再跑失败于 `arm_init.c` 未引 errno（坑 #60）；补 `#include <sys/errno.h>` 后 **0 error**，`kernel: prelink` 成功。
- **产物（实测，已外置 `E:\k60-work\deliverables\console-export-0306-20261105\`）**：
  - `kernel-0306.macho` 53,813,248 B sha `7a944a0ae08e69cb33b931d549403d0b107e3b77e4859f814833c33140eeac55`
  - `payload-0306.img` 201,326,592 B sha `b6c08c5859a97d8089bc1168bee41379c397f9bbd7e96893fdb2064bef302eb1`
  - `boot-console-0306-20261105.img` 201,883,648 B sha `56953b8ce189211e4366ed42159c77ae740346df9dc7a725f0cd78d92931b609`
- **离线闸门（全过）**：`trust_cache_init`=**0**（B 决策未回退）；`pong_ramoops_snapshot`=1、`K60 console ring export`=1 在位；cmdline 18 token 与 11-04 baseline **同集合**（仅既有的 `k60_console_export=1`、`k60_usblog=2`）；内核 `error:`=0。
- **未做**：未写设备、未 boot、未改 init（仍为 v11drain 34,912 B）；未提交 git（工作树仍含他方会话脏改动）。上机须按新短单另行批准。

## 2026-11-05 console-export + init-v11drain 首轮上机（只 boot，盘侧未打通）

- **写入闸门（实测）**：设备 6033dbec，目标 `/dev/block/sda38`（unixnu）；写前完整 extent 备份 `E:\k60-work\rollback\pong-init-20261105-011015\prewrite-device-backup.bin`，LBA 2501111..2501119、9×4096=36,864 B，sha `ED6C3BF17A7CD6E869802BCBCBC42A03C863A46799904EAAEF2339DA20BAF6E1`，时间 2026-11-05 01:10 Asia/Shanghai。写前复读与备份相同；旧 init 34,880 B 前缀 sha `DB7E4EEE…B98865`。v11drain 34,912 B，sha `12B9DF42CB76C2FFE21A1326215ABE2021AD02CE332B9215E7C2B0FE1AC26B94`；extent 右侧零填充后 sha `ECEB785EA615906EB59A351062BA04F82472F0EAEA8EE6ECA99940E5E0B03FFD`。写后整 extent 与 34,912 B bare-prefix 双回读匹配；结果 `WRITE-RESULT.json`。
- **boot（实测）**：镜像 `E:\k60-work\usb-a-stage\out\boot-usb-console-export-20261104.img`，201,883,648 B，sha `A246507B371D2AB06CE059A8892227B2F5BF3DD14796C6FE69A83A89D74C3C8E`；命令仅 `fastboot -s 6033dbec boot <image>`，Sending OKAY 4.533s / Booting OKAY 0.152s / total 4.823s；未执行 flash/erase/GPT。用户明确报告屏幕 `Pong init: var: stat root`；该屏显不作为进程停点证据。
- **盘侧判据（实测）**：只读抓取 sda38 Data 窗中完整 OwnerData APFS 容器，anchor LBA 2494976，bs=4096，skip=2494976，count=5210112。adb 原始流 21,340,618,847 B，sha `35E496AB4C7C0137C43057A7C93C34D23172A216A4FBC6B7C3E16576452CB975`；多出 95 B 为 toybox dd 诊断尾部，原始流保留。按预期容器长度生成解析副本 21,340,618,752 B，sha `257AEC0B8B44DDDEB2DC7C077B2B994066A6077C30CDADB210AC22FEB610DED0`，offset 32 锚点 NXSB。APFS OwnerData xid=18；metadata checksum 7 checked / 0 bad。`/pong/console.log` inode 249 size=0 B；`/pong/status.txt` 39 B；无 `.1/.2/.3`。完整侧车 `E:\k60-work\evidence\console-drain-20261105\SIDECAR.json`。
- **判定（文档+实测）**：上一轮无 console.log inode，本轮新 inode + mode root:wheel 0644，结合 init 源码只能由 fork 后 drainer 创建，证明 init 已越过 `var: stat root`、完成 Data write-check 并 fork，drainer 到达 mkdir/open；0 B 且无 `K60LOG boot epoch` 表明首个 sysctl pull/响应头校验未到 marker。**源码接口缺陷已确认，运行时 errno 未实读**：0243 OID 是 `CTLTYPE_OPAQUE|CTLFLAG_RD|CTLFLAG_LOCKED`，drainer 以 8 B cursor 作为 sysctl `newp`；实际 `bsd/kern/kern_newsysctl.c:1709-1714` 对这种请求在 handler 前返回 EPERM，handler 不会被调用；init 只将 errno 2 (`ENOENT`) 视为旧内核静默退出，其他错误报 unreadable 后退出。该源码路径与本轮盘侧 0 B 文件吻合，但具体 errno 不是设备回读值。详见 ISSUES I-20261105-01、PITFALLS #57。
- **后续**：不再 boot、不回滚。本轮结束于明确失败判据。修复前先审查 OID `CTLFLAG_WR` 的安全边界，或设计不依赖 `newp` 的读取游标 ABI；补全研审、构建、自检和新短验证单，必须再次取得用户批准才可设备操作。
