# APPEX-REGISTRATION —— 桌面小组件 `.appex` 零 spawn 的离线取证（收窄版）

> **范围**：只读 OS 窗 `os.raw` 与既有 usblog 日志；**不上机、不申请窗口、不改内核**。
> 结论按 **事实 / 推断 / 未知** 三级标注：事实=盘上文件或日志原文；推断=有 strings 或 plist 支撑但未在设备上验证；未知=离线不可判定，留给将来上机的第一件事。
> 本文件是 `WALLPAPER-CHAIN.md` §4 F5 的展开，不改变壁纸线判据（`RESEARCH.md` §0 六步）。

## 0. 结论卡

- **事实**：素材全在——OS 窗有 597 个 `.appex` 目录、`ChronoCore.framework/Support/chronod`(65,184 B)、`ChronoKit.framework` 齐全；设备日志里 chronod 被拉起并活到资源记账。
- **事实**：缺的是**注册数据**——OS 窗 `.csstore` 0 命中，`private/var/db/lsd` 与 `private/var/installd` 目录存在但为空；设备日志里 `installd`/`pkd` **从未 exec**（`^KE .*(installd|pkd)` 0 命中，只有 `lsd`、`SpringBoard`），扩展发现流程跑完结果为空。
- **事实**：四个相关 daemon 的 job **全是 Adaptive、无 `RunAtLoad`**（`com.apple.mobile.installd`、`com.apple.lsd`、`com.apple.pluginkit.pkd`、`com.apple.mobile_installation_proxy`）；镜像里**连 `launchctl` 都没有**（OS 窗无 `bin/launchctl`）⇒ 「上机后手动 kickstart 一下」这种最便宜的触发方式在这张镜像上不存在。
- **推断**：`installd` 自带完整的「从盘上状态 reconcile → 交 LaunchServices 注册」路径（`MILaunchServicesOperationManager` + `MIDiskImageManager` 的 mount point 扫描，§4），所以**只要它作为 launchd job 被启动一次**，大概率不需要额外的请求体就能把系统 app 注册进 LS。
- **未知**：`Discovering all extensions` 的打印者不在 OS 窗任何二进制里（§5），在 dyld 共享缓存中；`com.apple.lsd.rebuild` 与 `com.apple.mobile.installd` 的 XPC 请求体格式未公开；`installd` 启动后是否会因容器/沙盒/entitlement 失败也未知。
- **结论**：F5 的正确形态不是「播种数据库」（不可行），而是「**让 launchd 把 `com.apple.mobile.installd` 启起来，并保证它能拿到 Data 侧容器目录**」。这是唯一还站得住的落点；仍不在本线最小修复内。

## 1. 症状与日志事实

| 观测 | 原文 | 出处 |
| --- | --- | --- |
| widget 扩展零 spawn | `appex\|Extensions/\|WidgetKit` 全文 **0 命中**；`KE` 126 条无任何 `.appex` 路径 | `usblog-20261115-003207/console.log` |
| 发现流程空跑 | `Discovering all extensions` + `Discovery completed`，中间/前后**无计数、无插件名** | 同上 `:2798-2799`；a 日志 `:2750-2751` |
| 不是本次回归 | 该两行自 2026-11-07 起每次启动都在（`bootcap-20261107-121353/console.log:2896-2897` 及此后各次） | 历次 usblog |
| 只有 lsd 在跑 | `^KE .* (installd\|pkd\|pkreporter)` 0 命中，`KE` 里能看到的注册相关进程只有 `lsd` | `usblog-20261115-003207` |
| chronod 正常 | `KE 107 109 xpcproxy …/chronod`（`:1230`）→ `K60RV 4 chronod[109] mem=4864`（`:2364`），健康启动无 `KX!` | 同上 |
| 宿主在 | `System/Library/CoreServices/SpringBoard.app/SpringBoard` 112,528 B（薄壳，主体在 dyld 缓存） | OS 窗 |

## 2. 链上角色盘点（全部来自 OS 窗，事实）

| 角色 | 二进制（OS 窗大小） | launchd job（类型 / 身份） | Mach service | 盘上产物 / 职责 |
| --- | --- | --- | --- | --- |
| `installd` | `usr/libexec/installd` 608,880 B | `com.apple.mobile.installd`（Adaptive；`UserName`/`GroupName` `_installd`；`EnablePressuredExit`/`EnableTransactions`） | `com.apple.mobile.installd` | MobileInstallation 记录 + 向 LS 注册（journal + reconcile，§4） |
| `lsd`（用户域） | `usr/libexec/lsd` 57,424 B | `com.apple.lsd`（Adaptive；`UserName mobile`；`ThrottleInterval 1`；`PublishesEvents com.apple.launchservices.LSObserver`） | 13 个：`advertisingidentifiers diagnostics extensions icons installation mapdb modifydb open openurl personaobserver plugin rebuild xpc` | LaunchServices 数据库（`.csstore`）与 map；**已在跑** |
| `lsd`（系统域） | 同一二进制 | `com.apple.lsd.system`（`ProgramArguments [lsd, systemSessionDaemon, runAsRoot]`；`LimitLoadToSessionType System`；`Disabled = {#IfFeatureFlagDisabled: LaunchServices/system_session_lsd, #Then: True}`） | `com.apple.lsd.system.{modifydb,rebuild,mapdb}` | 系统会话的 LS 写路径；**默认被 feature flag 关掉** |
| `pkd` | `usr/libexec/pkd` 229,504 B | `com.apple.pluginkit.pkd`（Adaptive） | `com.apple.pluginkit.pkd` | PlugInKit 数据库（`PKDatabase`）；有数据之后的扩展拉起者 |
| `pkreporter` | `usr/libexec/pkreporter` | `com.apple.pluginkit.pkreporter`（唯一 `StartCalendarInterval`：周六 06:10） | — | 统计上报 |
| `mobile_installation_proxy` | `usr/libexec/mobile_installation_proxy` 112,112 B | `com.apple.mobile.installation_proxy`（Adaptive；`UserName mobile`） | `com.apple.mobile.installation_proxy` | lockdown 侧的安装转发器，**不是首启注册的触发者**（§4） |
| `misagent` | `usr/libexec/misagent` | `com.apple.misagent`（Adaptive；`mobile`） | `com.apple.misagent` | provisioning profile 代理 |
| SpringBoard | `…/SpringBoard.app/SpringBoard` 112,528 B | `com.apple.SpringBoard`（LaunchEvents） | — | 扩展宿主；`PlugIns/` 下只有 `SpringBoardDiagnosticExtension.appex` |
| `chronod` | `ChronoCore.framework/Support/chronod` 65,184 B | `com.apple.chronod` | — | 小组件时间线服务（已起来） |

LaunchDaemons 共 477 个 plist。`.appex` 目录 **597** 个（`7z l` 按 `\.appex$` 统计；旧文里的 603 是含文件级命中的口径）。

## 3. 缺的不是二进制，是三个数据对象 + 一个触发者

1. **MobileInstallation 记录**：OS 窗 `private/var/installd` 存在但为空（系统卷只带目录骨架）。
2. **LaunchServices 数据库**：`private/var/db/lsd` 存在但为空；全 OS 窗 `.csstore` 0 命中。`lsd` 自己的 entitlement 串说明契约：`com.apple.private.coreservices.canmaplsdatabase`、`com.apple.private.coreservices.canforcedatabasegc`、`com.apple.springboard.launchapplications`；`installd` 侧对应 `com.apple.private.coreservices.can-register-install-results`。
3. **PlugInKit 数据库**：`pkd` 的 `PKDatabase` 由 LS 的扩展注册喂数据；LS 为空时它无事可做。
4. **触发者**：四个 job 全 Adaptive、无 `RunAtLoad`；OS 窗无 `bin/launchctl` ⇒ 首启时必须有「第一个 XPC 请求」把 `com.apple.mobile.installd` 叫起来，而这张镜像没有任何东西会发它。

> 注：`private/var` 在 OS 窗只是系统卷自带的骨架，真实 Data 内容由我们的 varpack/init `mkdir` 生成；所以「Data 侧没有 X」这句只能从 varpack 与设备日志断言，不能从 `os.raw` 推断（`RESEARCH.md` §2 同源注意）。

## 4. 每个 daemon 的 strings 说了什么（事实层，可直接引用）

- **`installd` 的注册路径是自洽的**（不是「等人喂一条 install 请求」）：
  `+[MILaunchServicesOperationManager _reconcileOperations:unregisterMountPoints:registerMountPoints:restartUniqueOperations:]`、
  `-[MIJournal reconcile]`、`+[MILaunchServicesOperationManager instanceForSystemSharedContent]`、
  `-[MIDiskImageManager registerContentsAtMountPoint:completion:]`、`-[MIDiskImageManager _onQueue_registerDiscoveredAppEntries:onMountPoint:completion:]_block_invoke_2`、
  `-[MIInstallationJournalEntry performLaunchServicesRegistrationWithError:]`。
  ⇒ 启动时它会 `_initializeMountInfoFromStorage`、按 mount point 扫盘上的 app、建 journal entry、再交 LS 注册。**没有「扫 `.appex`」入口**——appex 是 LS 注册 app 时的附带信息，pkd/ExtensionKit 再从 LS 读。
- **重试有计数上限**：`_shouldContinueAfterCheckingAttemptCountInDir:` 对应串 `%s: Discovered %ld previous reconcile attempts; declaring defeat`。⇒ 反复失败会把计数烧掉；**不要用「discovery 出现次数」当判据**（P-204 同形）。
- **`lsd`**：`RebuildMapsForLaunchServices` 选择器 + `com.apple.lsd.rebuild`/`com.apple.lsd.system.rebuild` 服务存在 ⇒ 存在「让 lsd 重建 LS 映射」的入口；但请求体格式未公开（§5）。
- **`pkd`**：`Launching extension %@(%@) for host %d`、`PKDatabase`、`NSExtensionDiscoveryFilter`、`no XPCService for plug-in; database returned %@`、entitlement `com.apple.runningboard.launch_extensions`、`com.apple.private.xpc.domain-extension.proxy` ⇒ pkd 只是「有数据之后按 host 拉起」的执行者，**不负责发现**。
- **`mobile_installation_proxy`**：依赖 `InstallCoordination`/`MobileInstallation`/`liblockdown`/`UserManagement`，检查 `com.apple.private.InstallCoordination.allowed`，拒绝串 `Policy prohibits install`、`Installing system apps from the host is prohibited.`、`Path supplied to install, %@, is not in an allowed location` ⇒ 它是「外部主机装 app」的转发器，**首启注册不靠它**。

## 5. 离线能走到哪、走不到哪（证据边界）

**能**：盘上文件与 plist；`installd`/`pkd`/`lsd`/`mobile_installation_proxy` 的 strings 与部分符号（这几个是 OS 窗里的真实二进制，可反汇编）。

**不能**：
- **dyld 共享缓存不在 `os.raw`**（全列表 `com.apple.dyld` 0 命中），但设备上可读（`K60DYLD path=/System/Library/Caches/com.apple.dyld rc=0`、`dyld_shared_cache_arm64 rc=0`、`arm64e rc=2`、`/usr/lib/dyld rc=0`，a 日志 `:485-492`）⇒ `FrontBoard`/`FrontBoardServices`/`LaunchServices`/`MobileCoreServices` 与 SpringBoard 主体**不可离线反汇编**。
- **`Discovering all extensions` 的打印者无法离线定位**：该串在 `pkd`/`lsd`/`installd`/`pluginkit`/`SpringBoard`/`mobile_installation_proxy` 六个二进制里 **全部 0 命中** ⇒ 在缓存里。
- **XPC 协议**：`com.apple.lsd.rebuild` 与 `com.apple.mobile.installd` 的请求体序列化格式没有盘上证据；`installd` 只留 selector 名（`-[MIClientConnection checkCapabilities:withOptions:completion:]` 等），没有 wire format。
- **`os.raw` 的 `private/var` 是骨架**（§3 注）。

## 6. 候选与取舍（全部离线设计，未实施）

### C1（唯一现实路径，形态已收窄）— 让 launchd 启一次 `com.apple.mobile.installd`

1. **不要 exec 二进制、要起 job**：`installd` 的 Mach service 由 launchd 在 job 启动时注册；直接 `fork+exec /usr/libexec/installd` 不能替代（`MIClientConnection` 走 bootstrap 名字）。
2. **触发手段盘点**：
   - (a) **init 侧最小 XPC 客户端**发一条请求到 `com.apple.mobile.installd`（launchd 收到 demand 即启动 job）——需要先离线解出消息体；`fork/execve` 在 libmini 里有，XPC 客户端没有，得自写 ~几百行 stub。**推荐**。
   - (b) **内核侧让 launchd 启动指定 job**：要碰 launchd 内部状态，重且脆，只在 (a) 走不通时考虑。
   - (c) **改 boot-jobs 策展集加 `RunAtLoad`**：策展集 bindfs 到 `/System/Library/LaunchDaemons` 在密封根 EPERM（P-27，`boot view … result=-1 errno=1`）⇒ **这条路本身就不通**，除非 P-27 先解决。
   - (d) **改 OS 窗 plist 重新封装 SystemOS 卷**：等于重签密封系统卷，工作量与风险都超出本线。
3. **同时要补的 Data 侧**：`installd` 以 `_installd` 身份跑，需要 `/private/var/installd/Library/…` 可写；现有 init 只建了 `installd`、`installd/Library`、`installd/Library/Caches` 三层（a 日志 `:479`），journal/instance 目录是否够用**未知**，需在 C1 上机时观察它的失败串。
4. **判据**：见 §7。

### C2（备选）— 触发 `com.apple.lsd.rebuild`

用户域 `lsd` 已在跑，`com.apple.lsd.rebuild` 服务在。但两个问题：① 请求体格式未知；② 即使 rebuild 成功，`lsd` 只重建它「认为已安装」的 app 的映射，没有 MobileInstallation 记录时可能仍空。⇒ 作为 C1 的补充（C1 起不来时的观测手段），不作首选。

### C3（不做）— 静态播种 `.csstore` / MobileInstallation plist

格式未公开、含 bundle 指纹与 UUID、跨版本不稳定；且一旦写错会把后续真实注册卡死（`_reconcileOperations` 的 attempt 计数）。维持「不做」。

### C4（当前状态）— 接受无小组件

本线已 closure 结案；小组件不影响壁纸判据。

## 7. 若将来上机的判据（一次启动内）

1. `KE … /usr/libexec/installd`（或 `KE … pkd`）出现；
2. `Discovering all extensions` 之后出现**非零计数或具体插件名**（当前是紧接着 `Discovery completed`）；
3. 至少一条 `.appex` 路径的 `KE` 行（例：`…/AppStoreWidgetsExtension.appex`）；
4. chronod 侧出现 widget 扩展的拉起/check-in。

**反例判读**：`installd` 起来但立刻 `KX!` 退出 ⇒ 读退出码与它的日志，问题在容器/沙盒/entitlement，不在注册链。**不要**用 `Discovering` 出现次数当判据（P-204）。

## 8. 归属与交接

- 需要新立项：C1 的最小 XPC stub 落 `userland/`（init 侧），若要 (b) 则落 `patches/xnu`；都要多轮上机，且与本线（壁纸）无耦合。
- 本文件只做离线收窄；**不申请上机窗口**，worktree 保留待用。
- 相关：`WALLPAPER-CHAIN.md` §2.6（日志取证）、§4 F5（方案与判据）；`RESEARCH.md` §5（症状表）；P-27（bindfs EPERM）、P-198（补丁互顶）、P-204（计数≠语义）、P-205（resid 语义）。

## 9. 证据索引

| 材料 | 位置 / 命令 |
| --- | --- |
| OS 窗全量列表 | `/tmp/oslist.txt`（282,397 行；文件 16.23 GiB） |
| 抽取单个二进制 | `7z e -y /opt/k60/osroot/os.raw 'usr/libexec/installd'` |
| strings | `strings -a installd \| grep -iE '/private/var\|reconcil\|LaunchServices'` |
| plist 全量 | `7z l … 'System/Library/LaunchDaemons/*.plist'`（477 个）；关键四份：installd / lsd / lsd.system / pkd |
| a 日志 discovery | `usblog-20261115-132805/console.log:2750-2751` |
| `-003207` discovery | `:2798-2799`；KE 行 `:1230`；`K60RV` `:2364` |
| dyld 缓存可读性 | a 日志 `:485-492`（`K60DYLD … rc=0`） |
| appex 目录数 | `grep -c '\.appex$' /tmp/oslist.txt` = 597 |
