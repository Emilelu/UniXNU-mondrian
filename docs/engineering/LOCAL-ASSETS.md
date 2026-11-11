# 本地资源总索引（HR-39 强制维护）

> 用途：调试任何硬件前先查这里，避免重复发现已有文件/反复踩坑。
> 规则：发现关键文件 10 分钟内没定位 → 已反复发生 200+ 轮事故 → 随时补。

## 1. 官方驱动源码（touch-protocol 参考，最重要）

| 资源 | 路径 | 用途 |
|------|------|------|
| goodix_brl_hw.c | `impl/touch-protocol/refs/goodix_brl_hw.c` (1474行) | **config 下载三阶段协议** + 复位 + SPI模式 |
| goodix_brl_spi.c | `impl/touch-protocol/refs/goodix_brl_spi.c` | SPI 帧构造（0xF0/0xF1）|
| goodix_cfg_bin.c | `impl/touch-protocol/refs/goodix_cfg_bin.c` | config bin 解析（已整篇读）|
| goodix_ts_core.c | `impl/touch-protocol/refs/goodix_ts_core.c` (2470行) | 核心/ioctl/event |
| goodix_ts_core.h | `impl/touch-protocol/refs/goodix_ts_core.h` | goodix_ts_cmd/misc 结构 |
| goodix_ts_inspect.c | `impl/touch-protocol/refs/goodix_ts_inspect.c` (83KB) | INSPECT 数据兜底 |
| goodix_brl_fwupdate.c | `impl/touch-protocol/refs/goodix_brl_fwupdate.c` (35KB) | 固件更新 |
| gt9916r-windows/ | `impl/touch-protocol/refs/gt9916r-windows/` | Windows 驱动 |
| official-goodix/ | `impl/touch-protocol/refs/official-goodix/` | 官方参考 |

## 2. 固件 / config bin

| 资源 | 路径 | 大小 | 用途 |
|------|------|------|------|
| goodix_cfg_group_m11a.bin | `scratch/goodix-fw/` | 1627B | **GT9916R config（写回芯片用）** |
| goodix_firmware_m11a.bin | `scratch/goodix-fw/` | 223744B | GT9916R 固件 |
| goodix_cfg_bin.c | `impl/touch-protocol/refs/goodix_cfg_bin.c` | 9KB | config 解析 |

## 3. 反汇编产物

| 资源 | 路径 | 用途 |
|------|------|------|
| goodix_core.ko | `scratch/goodix_core.ko` (98KB) | vendor 反汇编（brl_select_spi_mode 等）|

## 4. 各硬件参考仓库（references/）

| 仓库 | 路径 | status | 说明 |
|------|------|--------|------|
| ruby-ios-bringup | `references/ruby-bringup/` | device-verified | **GT9916R 触摸（K60同款）** |
| ios-sweet | `references/ios-sweet/` | — | 旧实现 |
| UniXNU-ruby | `references/UniXNU-ruby/` | catalog | — |
| UniXNU-zizhan | `hackios/UniXNU-zizhan/` | device-verified | 同 SOC SM8475（但触摸是ST FTS非Goodix）|
| UniXNU-mondrian | `hackios/UniXNU-mondrian/` | 当前工作仓 | — |

## 5. 现有诊断/脚本

| 资源 | 路径 | 用途 |
|------|------|------|
| goodixcfg.sh | `scratch/goodixcfg.sh` | 导出当前 pong_goodix.c configuration |
| K60-TOUCH-CHECKLIST.md | `docs/` | 触摸进度 |
| RUBY-TOUCH-REFERENCE.md | `docs/` | ruby 触摸参考分析 |

## 6. 关键硬件技术文档（docs/）

| 资源 | 用途 |
|------|------|
| HARD-RULES.md | 铁则（39 条，含 all-hardware）|
| PITFALLS.md | 已排除假设（P-83~P-87 等）|
| LOCAL-ASSETS.md | 本索引 |
| HANDOFF.md | 交接记录 |

## 维护规则（HR-39）
- 每次大任务开始前更新本文件
- 发现本地已有但之前漏查的关键文件 → 立刻补入 + 记坑到 PITFALLS


## 7. 外部 fork 参考（yibiya）

| 资源 | 路径 | 说明 |
|------|------|------|
| yibiya-unNIXNU-mondrian | `references/yibiya-upstream` | 浅克隆 depth=50，HEAD 522c6ea，分支 upstream-fix |
| 采纳分析 | `docs/YIBIYA-PICK.md` | 40 个 commit 的采纳/不采纳判断与理由 |
| 已导入脚本 | `scripts/pack-boot-jobs.py`, `scripts/data2g-*.sh`, `scripts/diagnostics/rf*.py` | launchd 档案、Data 2GiB、资源叉诊断 |
| 已导入补丁 | `patches/xnu/0403-k60-pid26-slide.patch` | shared-region 起始地址诊断 |

**更新方式**（定时任务每日两次自动执行）：
```bash
cd <repo> && git fetch yibiya upstream-fix --depth 60
git log --oneline -20 yibiya/upstream-fix
```
