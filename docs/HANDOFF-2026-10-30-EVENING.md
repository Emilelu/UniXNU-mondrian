# K60 iOS 移植 · 交接文档（HANDOFF-2026-10-30-EVENING）

> 交接时间：2026-10-30 18:20 (UTC+8)
> 上一棒：`HANDOFF-2026-10-30.md`（userspace 入口 / trust cache 阶段）
> 交接原因：转交下一 agent 继续推进 `/private/var` 可写 与 userspace 服务链。

---

## 〇、一句话现状

**XNU 已启动到 launchd，`/private/var` 第一次真正挂上了（来自真实 UFS Data 窗口，只读）。**
当前唯一硬阻塞：**APFS 读写挂载会在空间扫描后卡死**，所以 keybag 写不进去。
下一步是确认 UFS 写路径，或换成 Apple 原生相容的 APFS 容器。

---

## 一、立即要做的下一步（唯一动作）

d8b9e4 之前最后一次改动（`aa7a1f1`）已**提交但未编译**，内核还是旧的。所以第一件事是：

```bash
# 1) 重编内核（会把 UFS 写路径的 K60UFS write# 标记编进去）
wsl -d Ubuntu-24.04 -- bash /mnt/d/Android/k60-ios/local-kernel-build12.sh

# 2) 出「读写探测」payload（带 pong_data_mount=1 + pong_data_rw=1）
wsl -d Ubuntu-24.04 -- bash /mnt/d/Android/k60-ios/handoff-ufsdata-rw-payload.sh

# 3) 上机（只 boot，绝不 flash；设备可能停在屏幕，脚本会自动切 fastboot）
wsl -d Ubuntu-24.04 -- bash /mnt/d/Android/k60-ios/handoff-boot-image.sh /mnt/d/Android/k60-ios/boot-ufsdata-rw.img
```

**判据（屏幕最后一行）**：

| 看到什么 | 结论 | 下一步 |
|---|---|---|
| `K60UFS write#0 blk=... hcs=0 hcsfatal=0 ready=1 poison=0` 后卡住 | UFS **写命令本身卡死** | 查 `hostWrite4kLocked` / SCSI WRITE(10) |
| `write#0` 里 `hcs` 非 0 或 `poison=1` | 命令未完成就判 busy，host 被永久 poison | 修 `hostIdle()` 的完成等待 |
| `write#0 -> result=<非0>` | 写返回错误 | 看 result 码定位（NotReady/IOError）|
| 出现多条 `write#N -> result=0` 后卡在别处 | UFS 写没问题，是 **APFS RW 阶段**卡住 | 换 APFS 容器（见 §4.3）|

**若 `mounted ro=0` 真的出现**（即读写挂载成功）→ 立刻跑 `pong_software_keybag` 相关验证，keybag 应能写。

---

## 二、硬约束（违反会变砖）

- **只 `fastboot boot`，绝不 `fastboot flash`**
- 允许写 `unixnu` 分区（SHNGROOT 所在，Data 窗口已写入此分区，符合红线）
- 禁止碰 `persist` / `modemst*` / Android `userdata` / `boot` / `vbmeta`
- 手机 serial `6033dbec`
- **无串口**；**长按重启不是温重启 → DRAM 掉电 → ramoops 日志必然丢失**（重要，见 §5.1）

---

## 三、仓库与产物

| 位置 | 作用 | 状态 |
|---|---|---|
| WSL `~/hackios/UniXNU-mondrian` | device 仓 | **HEAD `aa7a1f1`（detached）**，已 push 到 origin/main |
| WSL `/tmp/k60build` | core 仓（构建树） | `5d8ed7f` |
| WSL `~/hackios/uefi-mondrian` | UEFI 固件 | — |
| `/mnt/d/Android/k60-ios/refs/UniXNU-pong` | pong 参考仓 | 分支 `latest`，commit `64ddf28` |
| Win `D:\Android\k60-ios` | 脚本/镜像/文档 | — |

GitHub：core `Emilelu/UniXNU`（`k60`）· device `Emilelu/UniXNU-mondrian`（`main`）

---

## 四、本轮解决的阻塞（按顺序，全部有实测证据）

### 4.1 trust cache 之后到 launchd 的整条链

| # | 阻塞 | 根因 | 修复 | commit |
|---|---|---|---|---|
| 1 | CoreTrust 拒 launchd（`unsuitable CT policy 0`）| TC 未注入 | payload 带 `--trust-cache`（20G81 束 `344ae644…`）| `8b82eb3` |
| 2 | TC 装载时 `data abort` @ `__PLK_TEXT_EXEC` | `trust_cache_runtime_init()` 因 `img4if==NULL` 提前 return，`trust_cache_rt` 全零 → AMFI `loadModule` 撞 NULL `mutableRT` | 照常初始化运行时，img4 传 NULL，只挡动态加载 | `df99f2e` |
| 3 | 模块 1（System TC）被当 engineering 跳过 | `MASTER.arm64.pong` 缺 `CONFIG_SECOND_STATIC_TRUST_CACHE` | 新增补丁打开 | `df99f2e` |
| 4 | owner 挂载块从不执行（`K60CACHE` 从不出现）| 补丁 hunk 被 rebase 进 `if (scratch_result != KERN_SUCCESS) { panic(); }` 里，且重复声明 `init_envp` 遮蔽外层 | 移出失败分支、删重复声明 | `4ffd2ad` |
| 5 | bootstrap 轮链接失败（`native_pong_ufs_volume_device` 等未定义）| bootstrap 轮故意跳过驱动 archive | 给驱动入口加 **weak 定义**（返回 0 的桩）| `a3cef50` |
| 6 | `mount[3]` 退出 66（`failed to get boot manifest hash`）| `/chosen/boot-manifest-hash` 不存在 | ADT 注入 48 字节 `boot-manifest-hash` | `b8b0…`（profile.toml）|
| 7 | dyld 找不到 libSystem（`no dyld cache`）| 缓存真名是 **`dyld_shared_cache_arm64`**（不是 arm64e）；union 挂载后可见 | 探针确认 p1=0 | `e3a9540` |
| 8 | 每次改配置被构建脚本冲掉 | `local-kernel-build12.sh` 开头 `git reset --hard origin/main` | **改配置必须先 commit+push** | — |
| 9 | `kern_exec.o` 编译失败（无任何 clang 诊断）| `EXPORT_HDRS/libsa` 目录缺失 + 我手工环境不全 | 建目录；用完整构建而非手工 make | — |
| 10 | `MiniIOSurface.cpp` 类型错误 | `IOPlatformExpert*` 不能隐式转 `IOService*` | 显式 `static_cast` | `e8f417a` |

### 4.2 `/private/var` 从无到有（本轮核心成果）

**曾经的死路**：内存盘（NativeRamBlock + 32 MiB APFS seed）
- 现象：`K60DATA mount enter path=/private/var dev=/dev/disk1s1` 后**永久卡死**
- 卡点在 `mount()` 内部；APFS 已发布该卷（说明种子/UUID 都对）
- pong **不用这条路**

**正确路线（对齐 pong）**：真实 UFS Data 窗口
- unixnu 32 GiB，SHNGROOT 原有 OS(4.75 GiB) + SystemOS(2.48 GiB)，**尾部余 24.7 GiB**
- 新增 Data 窗口：**offset `7,780,433,920`（7420 MiB）、size `35,651,584`**
- 镜像：用 `tools/make-gpt-data-image.py` 把 32 MiB 裸 APFS 包进 **GPT**（PongUfs 要求 Data 窗口 offset 512 处是 `EFI PART`，裸 APFS 会被拒）
- 安装：`install-k60-ufs-data.py`（recovery ADB，先 dd 数据再写 4 KiB 目录，支持 `--dry-run`）
- **实测验证**：manifest count=3、Data @7,780,433,920、`EFI PART` ✓、`NXSB` ✓、manifest sha256 ✓

**重要坑**：
- 窗口可写性由 boot-arg **`pong_ufs_readwrite=1`** 决定（`PongUfsTransport` 所有写都过这个门），**没有它连 Data 窗口都是只读**
- Data 窗口签名要求 `EFI PART@512`；SystemOS 是裸 APFS（`NXSB@32`）
- 驱动窗口表被 **`#if XNU_PONG_UFS_DATA`** 包着，该宏由 defconfig 里 `CONFIG_XNU_OWNER_DATA_UFS=y` **精确行**推导
- 构建脚本强制：`DATA_UFS=1` 必须 `NATIVE_RAM_BLOCK=0` + `NATIVE_UFS=1` + `DATA_MOUNT=1`

**挂载顺序坑**：必须先 union（SystemOS@`/`）再挂 Data；反过来 union 会把 `/private/var` 遮住，自检会误报 `novar`。

### 4.3 当前卡点：APFS 读写挂载

实测序列：
```
K60DATA attempt enter
K60DATA UFS window dev=... path=/dev/disk3s1 bytes=...
K60DATA RO mount enter path=/private/var dev=/dev/disk3s1
disk3 scan took 0.xxxx s (no trim)          ← 只读时走完并成功
K60DATA mount returned error=0 result=0 rw=0
K60DATA mounted ro=1 fstype=apfs            ← 里程碑
```
读写（`pong_data_rw=1`）时：`disk3 scan` 之后**卡死**。

**两个已定位的可疑点**（都在驱动里，源码已加标记待编译）：

```cpp
// PongUfsTransport.cpp doAsyncReadWrite
if (result == kIOReturnSuccess && write && !hostIdle()) result = kIOReturnNotReady;
else if (write) result = hostWrite4kLocked(...);
```
```cpp
// RootCommands.h hostIdle()
if (read32(gHost.hc, 0x58) != 0) {        // HCS 有未完成命令
  gHost.poisoned = true; gHost.ready = false;   // 永久 poison
  return false;
}
```
- 写返回 `NotReady` 时 APFS 会**无限重试** → 表现为挂死（不 panic，因为 `transportFailure` 只 IOLog）
- 也就是：读正常、第一次写失败 → host 被 poison → 之后全 NotReady → 死循环

**另一个候选原因**：种子是 **macOS 26 的 hdiutil** 造的 APFS，版本比 iOS 16.6.1 的 `apfs-2142` 新。
只读不需要日志/空间事务，读写要 → 卡住。pong 用的是 Apple 原厂 iPadOS 18 模板，天然相容。

> 注意：iOS 16.6.1 的 IPSW **没有**「原厂 Data 模板」组件（Data 是设备上现场格式化的）。
> pong 说的「原厂模板」实质 = OS 里的 `private/var` 内容 + 本机 hdiutil 格式化成 APFS，与我们的种子同源。

---

## 五、取证手段（重要，别再踩）

### 5.1 ramoops 在本机不可用

- ramoops 映射**是成功的**：`ro_base=0xfffffff035600000 sig=43474244 ro_size=17494`
  （`sig=43474244` = Linux `PERSISTENT_RAM_SIG`「CGBD」，`ro_size` 是已镜像字节数）
- 但 **长按电源重启不是温重启**，DRAM 掉电 → 内容清零 → 进 TWRP/Android 读 `/sys/fs/pstore` **永远为空**
- `PE_k60_reset_now()`（panic 后 PSCI SYSTEM_RESET）**也没生效**（panic 停在屏上），所以拿不到留存日志
- 结论：**屏幕是唯一可靠日志**。要留日志，得先修好温重启，或把关键状态用 `panic()` 打到屏幕上

### 5.2 屏幕取证的正确姿势
- 关键状态一律用 `panic("K60...")` 输出（panic 永远在最后、不会被刷走）
- 普通 `printf` 会被后续输出冲掉，只适合定位「卡死点」（最后一行即卡点）
- 已内置的判据前缀：`K60CACHE`（union/缓存）、`K60SELF`（Data 挂载+ramoops 自检）、`K60DATA`（Data 步骤）、`K60UFS write#`（写路径）

---

## 六、构建配方（本地 WSL，不用 GHA）

```bash
# 内核（改 defconfig / 补丁后必须走这个，它会先 defconfig 再 build）
wsl -d Ubuntu-24.04 -- bash /mnt/d/Android/k60-ios/local-kernel-build12.sh
```

依赖已封装：`HOST_CC`/`MIGCC`/`MIGCOM`/`CC` + `dwarfdump`/`c++filt` shim + `PONG_NATIVE_DRIVER_SOURCE`。
`PONG_NATIVE_DRIVER_SOURCE` 让 UFS/RamBlock 驱动随内核一起编。

**产物**：`/tmp/k60build/out/mondrian/ipados-16.6.1-20G81/mondrian/kernel/kernel.macho`

**payload/启动镜像**（含 AppleARMCPU 校验补丁，**必须打**，否则 8 核 ADT 会 panic）：

| 脚本 | 用途 |
|---|---|
| `handoff-ufsdata-payload.sh` | 只读 Data（`pong_data_mount=1`）→ `boot-ufsdata.img` |
| `handoff-ufsdata-rw-payload.sh` | **读写 Data**（`pong_data_mount=1 pong_data_rw=1`）→ `boot-ufsdata-rw.img` |
| `handoff-boot-image.sh <img>` | 自动切 fastboot 并 boot（内部做 wslpath 转换）|

> ⚠️ `unixnu bootimg` 内置校验对 v4 镜像会**误报**（它比较 v4 恒为 0 的 `page_size` 字段）。
> 用 `handoff-verify-bootimg.sh` 自己做 v4 布局校验。

---

## 七、当前代码状态（关键位置）

### 7.1 内核侧（`patches/xnu/offline-owner-systemos-mount.patch`）

`load_init_program()` 里的顺序与开关：

```
[1] union SystemOS @ "/"          ← 必须先做
[2] if (pong_data_mount==1)
      native_owner_data_prepare()
        ├─ UFS 查找（DATA_UFS=y 时）: k60_ufs_data_volume_device(UUID,...) → /dev/disk3s1
        ├─ pong_data_rw==1 ? flags=0 : flags=MNT_RDONLY
        └─ mount("apfs", "/private/var", dev)
[3] if (pong_data_mount==1 && !mounted) panic("K60SELF novar ...")
```

### 7.2 驱动侧（`drivers/NativeUfs/PongUfsTransport.cpp`）

- 已加 **`K60UFS write#N`** 有限次标记（8 次上限），**尚未编译进内核**
- 窗口表：`{OS, EFI PART@512}`、`{SystemOS, NXB@32}`、`#if XNU_PONG_UFS_DATA {Data, EFI PART@512}`
- 写门控：`gHost.writable`（= `pong_ufs_readwrite`）+ 窗口 4096 对齐

### 7.3 defconfig 现值

```
CONFIG_XNU_NATIVE_RAM_BLOCK=n     ← 内存盘已弃用
CONFIG_XNU_NATIVE_UFS=y
CONFIG_XNU_OWNER_DATA_MOUNT=y
CONFIG_XNU_OWNER_DATA_UFS=y       ← 走 UFS Data 窗口
CONFIG_XNU_OWNER_DATA_VOLUME_UUID="6DCCF70A-6FD6-403E-ACED-95313CD7CBB8"
```

### 7.4 boot args 现值（`board.toml`）

```
-v native-ufs=1 pong_allow_unauthenticated_root=1 debug=0x144
cs_enforcement_disable=1 pong_software_keybag=1 disable_exc_resource=1
pong_ufs_readwrite=1
```
（测试时额外用 `--kernel-arg` 加 `pong_data_mount=1` / `pong_data_rw=1`）

---

## 八、与 pong 参考仓的对标（`64ddf28`）

| 项 | pong | 我们 |
|---|---|---|
| OS | ipados-18.7.10 / **Darwin 24** | ipados-16.6.1 / **Darwin 22** |
| 组件 | `PongPlatform24` 单一聚合 | ArmDTPlatform/ArmCpu/XnuPrelink/PongUfs 分散 |
| Data | 真实 UFS 窗口 8 GiB（`952D79E9-…`，offset 12,231,639,040）| **真实 UFS 窗口 32 MiB**（`6DCCF70A-…`，offset 7,780,433,920）✅ 已对齐思路 |
| init | 自研 `/pong/init` + `libpong-ui18.dylib` | 原生 launchd |
| 结果 | services34 进桌面 | launchd 跑到 watchdogd |

**pong 的关键经验（可直接借用）**：
- 「三个卷 UUID 统一配置化」——我们踩过同一个坑（`576A2203` vs `6DCCF70A`）
- keybag 目录由**用户态 init 创建**（`/private/var/keybags` 0700、`/private/var/logs` 0755），内核只负责挂载
- 官方设备页：pong 12 部分全 implemented；我们只有「配置」+「镜像组装」
- 补丁覆盖度：pong 103 个 patch 我们**一个不缺**，另有 22 个未入 series

---

## 九、已知但未处理的次生问题

| 问题 | 说明 | 优先级 |
|---|---|---|
| `/private/var` 只读 | keybag 写不进 → MKB FATAL | **最高** |
| `watchdogd` SIGTRAP 退出 | `namespace 2 subcode 0x5`（信号退出，**不是**资源监控）| 中 |
| `disable_exc_resource=1` 无效 | 因为该 panic 走的是 `OS_REASON_SIGNAL`，与资源监控无关 | 低 |
| ramoops 日志拿不到 | 长按重启不是温重启；`PE_k60_reset_now()` 未生效 | 中（取证）|
| 22 个补丁未入 series | `pong-touch-console`、`pong-physical-keys`、`pong-ufs-data` 等 | 低 |
| GPU 空壳 | `K60 ACCEL: empty IOAcceleratorES`，SpringBoard 需要真 GPU | 后期 |

---

## 十、工程陷阱清单（本轮新增，务必读）

1. **PowerShell 会吃掉 `$VAR`、`|`、`[0-9]`** → 凡含变量/管道/方括号，**必须写 `.sh` 再 `wsl bash xxx.sh`**
2. **Windows 的 `adb.exe` / `fastboot.exe` 不认 WSL 路径** → 传文件/镜像前用 `wslpath -w` 转换
3. **构建脚本开头会 `git reset --hard origin/main`** → 改 defconfig/board.toml/驱动后**必须先 commit+push**
4. **`unixnu build payload` 的 `--trust-cache` 白名单读 `[payload]`，不是 `[payload."adt"]`**
5. **`board.toml` 的 `data_ramdisk` 键不被读取** → 只有 CLI `--data-ramdisk FILE` 有效
6. **`panic()` 是 noreturn** → 之后的代码会被当死代码优化掉，曾因此长期掩盖链接问题
7. **Mach-O 里 weak *声明* 仍是强引用** → 未定义符号要用 weak **定义**（返回 0 的桩）
8. **改 CFLAGS 不会触发 make 重编** → 必要时删掉对应 `.o`（但别删 `mach.*.unstripped`，它会连带破坏 `EXPORT_HDRS`）
9. **头文件里放函数定义会被多 TU 包含** → 用 `static inline`，或把实现放进单个 `.c`
10. **同一个 `.o` 的 `CFLAGS_ADD` 只能有一行** → 第二行会**替换**第一行，静默丢掉所有 `XNU_OWNER_*` 开关
11. **`set -u` 下变量必须先定义再使用** → 我加 `-DXNU_PONG_RAMOOPS_CONSOLE` 时踩过（用到行在定义行之前）

---

## 十一、关键文件速查

| 用途 | 路径 |
|---|---|
| 本轮进展详录 | `D:\Android\k60-ios\PROGRESS-2026-10-30-PM.md` |
| 上一棒交接 | `D:\Android\k60-ios\HANDOFF-2026-10-30.md` |
| 开工必读索引（9 条踩坑）| `D:\Android\k60-ios\READING-INDEX.md` |
| 10 章 149 条调研 | `D:\Android\k60-ios\deliverables\ZCODE-RESEARCH-REPORT.md` |
| 构建（内核）| `local-kernel-build12.sh` |
| payload（只读 / 读写）| `handoff-ufsdata-payload.sh` / `handoff-ufsdata-rw-payload.sh` |
| 上机 | `handoff-boot-image.sh` |
| boot.img 独立校验 | `handoff-verify-bootimg.sh` |
| Data 镜像生成（GPT 包裹）| `tools/make-gpt-data-image.py`（仓内副本 `scripts/make-k60-gpt-data-image.py`）|
| Data 窗口安装（含 dry-run）| `install-k60-ufs-data.py`（仓内副本 `scripts/install-k60-ufs-data.py`）|
| 进 recovery 等 adb | `handoff-enter-recovery.sh` |
| 设备状态速查 | `handoff-state-final.sh` |
| pong 参考仓 | `D:\Android\k60-ios\refs\UniXNU-pong`（分支 `latest`）|
| pong 服务迭代史（**强烈推荐读**）| `refs/UniXNU-pong/migration/ipados18/services.md` |

---

## 十二、汇报格式要求

每次上机后给出：
1. **改动**（commit hash + 一句话）
2. **屏幕原文**（最后几行 / panic 全文；OCR 错误请标注）
3. **判据对照**（本次预期 vs 实际）
4. **下一步**（若失败，明确「停在哪一行判据」）

**没有实测不写「已修复」。**
