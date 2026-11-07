# K60 移植 — 开工必读索引

> 目的：**避免重复踩坑**。本机已有大量调研文档，很多"新问题"其实早有答案。
> 开工前按顺序读完这 5 份，再动手。

---

## 〇、最新交接（2026-10-30 傍晚，最高优先）

| 顺序 | 文档 | 为什么 |
|---|---|---|
| **★1** | **`HANDOFF-2026-10-30-EVENING.md`** | **当前交接全文**：`/private/var` 已只读挂上；读写挂载卡死待查；11 条新踩坑；精确下一步 |
| **★2** | `PROGRESS-2026-10-30-PM.md` | 信任缓存打通后的完整推进记录 + pong 对标（含内存盘路线为何废弃）|
| 3 | `HANDOFF-2026-10-30.md` | 上一棒交接（trust cache / userspace 入口阶段）|

> ⚠️ **冲突时以 EVENING 为准**。旧文档中「Data 无可用卷」「用内存盘 seed 提供 /private/var」等结论已被实测取代。

---

## 一、必读（按顺序）

| # | 文档 | 为什么必读 |
|---|---|---|
| 0 | **官方 docs** `~/hackios/UniXNU-docs/docs/` | UniXNU 上游完整文档（576 文件）。**遇到问题先查这里**，尤其 `concepts/`、`porting/`、`drivers/`、`devices/sirius.md`（已完成的参考设备）|
| 1 | `deliverables/delta2/14-UFS-CONSTANTS-DIFF.md` | **UFS 驱动里所有硬编码/硬校验的逐条清单**（file:line 全注），分「必须改 / 可沿用 / 待实测」三类。今天踩的 `geometry changed` 就在这里写着 |
| 2 | `deliverables/delta2/13-DT-DIFF-K60-VS-PONG.md` | K60 vs Pong 的**设备树逐属性 diff**，ADT 必改点清单 |
| 3 | `deliverables/gamma2/01-UFS-APFS-HFSX-ROOT-K60.md` | UFS/APFS/HFSX 根的硬件事实与结论（22 KB，最全）|
| 4 | `deliverables/delta2/01-PRELINK-PAYLOAD-K60.md` | prelink + payload 架构（34 KB，最全）|
| 5 | `FIRST-BOOT-PLAYBOOK.md` | 启动序列判读、失败签名、迭代闭环 |

### 官方 docs 重点篇目

| 文档 | 用途 |
|---|---|
| `docs/concepts/security.md` | AMFI / 根卷认证（当前卡点相关）|
| `docs/porting/log-capture.md` | 日志捕获（panic 读取）|
| `docs/concepts/prelink.md` | prelink 机制 |
| `docs/concepts/boot-chain.md` | 启动链全貌 |
| `docs/porting/dual-system-partition.md` | 双系统分区（我们在用）|
| `docs/porting/bring-up.md` | bring-up 标准流程 |
| `docs/drivers/arm-cpu.md` | ArmCpu 驱动（8 核相关）|
| `docs/drivers/arm-dt-platform.md` | ArmDTPlatform（平台专家）|
| `docs/devices/sirius.md` | 已完成的参考设备（含 root 认证经验）|
| `docs/devices/mondrian.md` | **我们自己的设备页**（官方生成）|

> 官方 docs 更新方式：
> ```bash
> cd ~/hackios/UniXNU-docs && git fetch --depth 1 origin main && git checkout -q FETCH_HEAD
> ```

## 二、按域查阅

### 存储 / 根文件系统
- `deliverables/gamma2/01-UFS-APFS-HFSX-ROOT-K60.md` — UFS/APFS/HFSX 全貌
- `deliverables/delta2/14-UFS-CONSTANTS-DIFF.md` — 硬编码清单
- `deliverables/delta2/02-DUALSYSTEM-READONLY-CHECKLIST.md` — 双系统只读核对
- `deliverables/beta2/01-DUAL-SYSTEM-PREFLIGHT.md` — 双系统前置

### 显示
- `deliverables/display-k60/K60-DISPLAY-A1.md` — 四要素与首帧判据
- `deliverables/K60-120HZ-PLAN.md` — **120Hz 完整时序参数**（从 dtbo 提取）
- `deliverables/delta2/11-BOOT51-FD-CONTENTS.md` — UEFI FD 内容

### 触摸
- `deliverables/gamma2/02-GOODIX-TOUCH-K60.md` — 硬件事实（SE4/GPIO/坐标/供电）
- `deliverables/delta2/15-TOUCH-DIFF.md` — ADT `pong-touch` 节点逐属性 diff
- `deliverables/A1-touch/HANDOFF.md` — 交接全文（含寄存器判据、已知坑）
- `ios-sweet-k60/drivers/k60-goodix-touch/README.md` — 上机步骤

### GPU
- `deliverables/gamma2/03-ADRENO730-GPU-K60.md` — GPU/GMU/SMMU/ZAP 硬件事实
- `deliverables/delta2/16-GPU-DIFF.md` — PongAdreno 常量层复核（结论：零改动）
- `smp/K60-SMP-MULTICORE.md` — 含 GMU M3 交付说明

### CPU / SMP
- `smp/K60-SMP-MULTICORE.md` — 8 核开启条件、启动顺序、验收判据
- `deliverables/delta2/17-PMIC-CLOCK-DIFF.md` — PMIC/时钟/电源域依赖面

### 启动链 / 构建
- `deliverables/delta2/08-BOOT-IMAGE-PIPELINE.md` — boot.img 生成
- `deliverables/delta2/10-FIRST-BOOT-RUNBOOK.md` — 首启 runbook
- `deliverables/delta2/20-GHA-WORKFLOW-REVIEW.md` — GHA 工作流
- `deliverables/beta2/02-XNU-TOOLCHAIN-PREFLIGHT.md` — 工具链

### 排障
- `deliverables/delta2/21-FAILURE-MODE-MATRIX.md` — **失败模式矩阵**（先查这个）
- `deliverables/delta2/12-EARLY-BOOT-EVIDENCE-PLAN.md` — 早期启动取证
- `deliverables/delta2/19-ANDROID-READONLY-COLLECTION.md` — 从 Android 侧只读取证

### 历史与规划
- `K60-MONDRIAN-PORTING-PLAN.md` — 总体移植计划
- `K60-RESEARCH-INPUTS.md` — 调研输入汇总
- `K60-IOS-STATUS.md` — 状态快照
- `deliverables/delta2/03-NEXT-PHASE-STEPS.md` — 下一阶段
- `AGENT-COORDINATION.md` — 全部实测日志与决策（append-only，最长）

## 三、已知"文档没覆盖"的缺口

| 缺口 | 说明 | 状态 |
|---|---|---|
| **根卷认证链** | `zzzzzzzzz-pong-development-root-policy.patch` 的 `pong_allow_unauthenticated_root` 还有隐藏条件 `PE_i_can_has_debugger()`，文档未记载 | 已修（`68504b3` 去掉该条件）|
| **launchd 之后的 userspace** | AMFI / trust cache / sandbox 服务链，无文档 | 待调研（已交 ZCode，见 `deliverables/ZCODE-RESEARCH-TASK.md`）|
| **WiFi / 音频 / 蓝牙** | 完全未覆盖 | 未开工 |
| **120Hz 实施细节** | 参数已提取，但 PLL 是否可配未验证 | `K60-120HZ-PLAN.md` §6 风险 |

## 四、今天实战验证过的结论（可放心引用）

```
ArmCpu: CPU registered, install interrupt controller
cache: 8 CPU(s), 64 bytes CPU cache line size          ← 8 核已验证
K60 DISPLAY: panel 1440x3200 DSC video mode, 60 Hz     ← 显示出帧
apfs_module_start: Load com.apple.filesystems.apfs     ← APFS 加载
PONG_UFS: transport ready LUN=0 block=4096 blocks=61731840   ← UFS 传输层通
panic: rootvp not authenticated @bsd_init.c:1087       ← 当前卡点（已放宽门，待验证）
```

## 五、协作约定

见 `COLLABORATION-RULES.md`：
- 新变动立即通知相关方
- 长程任务拆给子 agent，一个领域一个 owner，禁止两人同做
- 派发 GHA 必须带 `pre_build`（见 R4）
- 每步 append 到 `AGENT-COORDINATION.md`

---

## 六、踩坑记录（实测，2026-10-29 夜）

> 每条都是**花了时间才定位到**的，写下来避免重复。

### 6.1 UFS 驱动：两处硬编码来自 Pong，K60 必须改

| 位置 | Pong 值 | K60 实际 | 症状 |
|---|---|---|---|
| `RootLayout.h` 的分区名 | `"userdata"` | **`"unixnu"`** | 找不到分区 → 无 IOMedia |
| `PongUfsTransport.cpp:48-49` 的 LBA | `0x413248 / 0x75a40ea` | **53342976 / 61731583** | `Pong userdata geometry changed` |

**关键**：`delta2/14-UFS-CONSTANTS-DIFF.md` 早就写了这两条，但当时没查。

### 6.2 IOKit personality 的 `IONameMatch` 必须等于 ADT 节点名

`ios16-native-ufs-personality.patch` 注册的是 `IONameMatch = ufshc`，
而 board DTS 的 `unixnu,adt-name` 写的是 `"ufs"` → **永不匹配**，驱动不 probe。

**教训**：改 personality 或改 `unixnu,adt-name` 时，两边必须同步。
当前值：`unixnu,adt-name = "ufshc"`（device main `e40e548`）。

### 6.3 `boot.img` ≠ `payload.img`（这个坑最贵）

| 文件 | 是什么 | 怎么用 |
|---|---|---|
| `payload.img` | 192 MiB **FAT32**，头 `eb 58 90` | 是 **ramdisk**，不能直接 `fastboot boot` |
| `boot.img` | Android boot v4，头 `ANDROID!` | kernel = BootShim+UEFI FD+DTB，ramdisk = payload |

直接 `fastboot boot payload.img` 会让 fastboot 把 FAT 当 kernel 打包 → ABL 复位 → **开机 logo 循环**。

生成：`unixnu bootimg --uefi <uefi> --fd <SILICIUM_UEFI.fd> --dtb <dtb> --ramdisk payload.img -o boot.img`

### 6.4 `boot.img` v4 的 ramdisk 偏移不是 `4096 + kernel_size`

v4 布局：`header(page 4096)` → `kernel(按 page 对齐)` → `ramdisk`。
正确算法：
```python
kernel_off = 4096
ramdisk_off = kernel_off + ((kernel_size + 4095) // 4096) * 4096
```

### 6.5 根卷认证还有隐藏条件 `PE_i_can_has_debugger()`

`zzzzzzzzz-pong-development-root-policy.patch` 的放行条件：
```c
pong_development_root = (boot_arg == 1) &&
    PE_i_can_has_debugger(NULL) &&          // ← 文档没写，实测过不去
    (vfs_flags(...) & MNT_RDONLY);
```
即使传 `pong_allow_unauthenticated_root=1`，panic 仍在，且**不打印** `PONG DEVELOPMENT` 那行。

修法（已做）：`68504b3` 去掉 debugger 条件；`a024d02` 加 `debug=0x144` 双保险。

### 6.6 二进制 patch panic **不可行**（已分析，别重试）

`rootvp not authenticated after mounting` 的字符串只有 1 个引用点（`0x9f6c50`），
但它调用的是 `printf`（`0x9a65ac`），不是 panic。
屏幕报的 `caller 0xfffffff0079fac18` 是 `panic()` **内部**格式化代码的返回地址
（`BL 0x971c94` 的返回点），不是调用点。

→ 无法据此定位 `if (autherr && ...)` 的条件分支。**只能重编内核。**

### 6.7 macOS runner 容量是硬瓶颈

`macos-26` 与 `macos-15` 都会出现：
```
The job was not acquired by Runner of type hosted even after multiple attempts
```
（15 分钟后 job 被 cancelled，`steps=0`，无日志）

**对策**：排队期间做离线工作（本地生成 ADT、离线打 kext 补丁、重出 boot.img），
不要空等。离线链路见 `mk-offline-full.sh`。

### 6.8 离线迭代链路（把 8 分钟 CI 降到 1 分钟）

```bash
# 完整离线：重生成 ADT + 改 boot-args + 打 AppleARMCPU 补丁 + 出 boot.img
bash mk-offline-full.sh <base-payload.img> <out-boot.img> [cpus]
```
依赖：
- `/tmp/corek60` — core k60 分支 checkout（有 `[payload] cpus` 支持）
- `/tmp/adtgen` — device 仓 checkout（含 `ufshc` dts）
- `smp/patch_armcpu_validate.py` — AppleARMCPU 校验补丁工具
- `hardware.dtb` — 由 `dtc` 从 dts 编译（`rebuild-dtb.sh`）

### 6.9 只读的 GPT 分区内容可以验证（不用刷机）

```bash
adb shell "su -c 'dd if=/dev/block/by-name/unixnu bs=8 count=1'"   # → SHNGROOT
adb shell "su -c 'blockdev --getsize64 /dev/block/by-name/unixnu'" # → 34359738368 (32 GiB)
```
已验证：魔数 `SHNGROOT`、version 1、count 2、image_bytes 7,763,656,704。
