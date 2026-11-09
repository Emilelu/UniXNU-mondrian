# TWRP 事实澄清（2026-11-09 维护者订正）

## 结论：**TWRP 存在，在设备盘上的 `boot` 分区里**

审计 agent `f656c2c6` 在 `RISKS.md` §R7 里判定「TWRP 不可得，别人进不去」，
**这个判定是基于「构建产物」的搜索，口径错了。**

## 真实情况（维护者原话）

> TWRP 已集成在 boot 镜像里是指**我现在分区中实际存在的 boot**，不是构建出来的那些 boot。
> 每次 fastboot 里面都能 `reboot recovery` 即 TWRP。

也就是说：

| 项 | 状态 |
|---|---|
| 设备 `boot` 分区 | ✅ **已刷入带 TWRP 的 boot** |
| `fastboot reboot recovery` | ✅ **能进 TWRP**（维护者每次都用）|
| 这是不是我们的构建产物 | ❌ **不是**——是第三方 TWRP（历史记录提到「Fuutao 5.10.237」）|
| 在不在公开仓 | ❌ 不在（`TWRP-ENTRY.md:6` 说「不要搜 twrp*.img」）|

## 所以审计的 R7 结论要改成

**原判定（错）**：
> R7（中）TWRP 不可得，而所有写盘步骤都依赖它。级别：C

**正确判定（B 级）**：
> **TWRP 在维护者设备的 boot 分区里，可直接用。**
> 但**别人要复现，必须自己先刷 TWRP**（这是标准操作：从 TWRP 官方或第三方适配版刷入）。
> 这是**前置条件**而非**不可得**。

## 对可复现性分级的影响

**R7 从 C 级降到 B 级**：

| 阶段 | 原判定 | 修正后 |
|---|---|---|
| 刷 TWRP 到 boot | C（不可得）| **B（需人工，但标准操作）** |
| `fastboot reboot recovery` 进 TWRP | C | **B（同上）** |
| 用 TWRP `dd` 写 unixnu 分区 | C | **B（需人工，有 TWRP 就能做）** |

**真正的 C 级依赖反而缩小为**：
- `unixnu` 分区里的 **19.88 GiB Data 窗口内容**（dd 写入的产物，不是流程）
- 手工 dd 的 `/private/var/pong/init`
- 三窗口 SHNGROOT 清单的**内容**

## 修正后「从原厂 K60 到跑 iOS」的完整路径

| 步骤 | 级别 | 说明 |
|---|---|---|
| 1. 刷 TWRP 到 boot 分区 | **B** | 标准操作，第三方 TWRP 镜像 |
| 2. `fastboot reboot recovery` | **B** | 有 TWRP 就行 |
| 3. TWRP 里建 `unixnu` 分区 | **B** | 需文档化尺寸/位置 |
| 4. 构建 boot.img | **A** | `2c9eac9` 已修好环境变量/shim-bin |
| 5. `fastboot boot boot.img` | **A** | 不写盘 |
| 6. TWRP 里 dd 写 Data 窗口 | **C** | **19.88 GiB 内容没有公开产物** |
| 7. 写 `/private/var/pong/init` | **C** | 手工 dd，需 macOS 编译 |
| 8. 写三窗口 SHNGROOT 清单 | **C** | 手写，工具只产两窗口 |

**结论**：流程前置（1-3）是 B 级可复现，**卡点在 6-8 的「盘上内容」**。

## 审计 agent 的技术发现仍然有效（只是结论要改）

它的**实测是对的**：
- 60 个 `boot-*.img` 里 TWRP 命中 0 ✅
- `kernel_size=548,774 + ramdisk_size=201,326,592` 布局里没有第二套 recovery 空间 ✅

**这两个事实说明**：TWRP **不可能**在我们的构建产物里。
但这不等于「TWRP 不可得」——它在**设备盘上的 boot 分区**，是独立刷入的。

## 教训（写进 HARD-RULES）

**HR-11：区分「构建产物」与「设备盘上状态」**

搜索某能力是否存在时，必须明确范围：
- 构建产物（`boot-*.img`、`out/`）→ 决定「别人构建能拿到什么」
- **设备盘上状态**（`/dev/block/by-name/*`）→ 决定「维护者能做什么」

**用构建产物否定设备能力 = 口径错误。**
