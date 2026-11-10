# UniXNU-mondrian

Redmi K60（代号 **mondrian**，高通 **SM8475**）的 UniXNU 设备支持仓库。

**当前目标：iOS 16.6.1（20G81）/ darwin22 上跑通完整硬件。**

> 本 README 最后更新：2026-11-09。历史路线（darwin24 / iPadOS 18.7.10）已归档到 `archive/darwin24-main-20261103` 分支，不再维护。

## 分支

| 分支 | 用途 |
|---|---|
| **`main`** | 主线（默认分支），所有可工作的阶段性成果都合到这里 |
| `archive/first-frame-20261107` | 历史里程碑：iOS 16.6.1 用户态首帧 |
| `archive/darwin24-main-20261103` | 已废弃的 darwin24（iPadOS 18）路线 |

提交规范见 `AGENTS.md` 铁律 11：**改动后及时 commit，阶段性成果及时 push**（push 用 Windows 侧 git）。

## 当前状态（2026-11-09）

| 项 | 状态 | 证据 |
|---|---|---|
| Boot chain（UEFI → UniXNU loader → XNU → launchd） | ✅ | 启动日志 |
| UFS / APFS 三窗（OS / SystemOS / Data） | ✅ | `PONG APFS: OS root binding PASS`、`K60DATA mounted ro=0 fstype=apfs` |
| 显示首帧（1440×3200） | ✅ | `K60 DISPLAY: first frame presented (swap 1)` |
| 背光（DCS 0x11/0x29/0x51） | ✅ | `K60 PANEL: bring-up complete` |
| 锁屏 / SpringBoard | ✅ | `Pong UI: 20G81 compatibility library entered SpringBoard` |
| launchd 稳定 | ✅ | 禁用 8 个 App-cryptex job 后不再 `initproc exited` |
| **实体键（电源/音量）** | 🔄 | 驱动已编译/链接/调用（`bsd_init.o` 有 `U _pong_buttons_init`），`configuration()` 结果不可观测 |
| **触摸** | 🔄 | 时钟已修（QUP0 **SE1** 偏移 + HWCG 清除）；GENI SE FIFO 模式仍被拒；固件已从真机提取（`goodix_firmware_m11a.bin` 223,744 B，sha `1e647510…`） |
| GPU（Adreno 730v3 scanout） | ❌ | 三补丁已 rebase（sha `cba010e4`/`77a95ade`/`8bc95a66`），卡在 `libPongAdrenoPlatform.a` 的 `-force_load` 作用域 |
| WiFi / 蓝牙 / 音频 / 相机 / 传感器 / 电源 | 📋 | 八步调研已完成，实现进行中 |

详细状态与缺口矩阵见 [`E:\k60-work\docs\PORTING-PIPELINE.md`](file:///E:/k60-work/docs/PORTING-PIPELINE.md)。

## 结构

| 路径 | 内容 |
|---|---|
| `board.toml` | `schema_version = 2` 设备配置与组件选择 |
| `porting.toml` | 14 个子系统的输入、发现、证据与完成判据 |
| `feeds.toml` | 固定的 SoC 源 |
| `configs/mondrian_defconfig` | 设备内核设置 |
| `dts/mondrian.dts` | 内存、CPU、外设（含 `unixnu,adt-name` 导出的触摸/按键节点） |
| `patches/xnu/` | 设备补丁（16.6.1 系列，见 `patches/xnu/series`） |
| `scripts/` | 设备构建与检查工具 |
| `drivers/` | PongAdreno / NativeUfs / NativeRamBlock / ArmCpu / ArmDTPlatform / PongMetal |

## 四层仓库

| 层 | 仓库 | 内容 |
|---|---|---|
| 框架 | [UniXNU/UniXNU](https://github.com/UniXNU/UniXNU)（`main`） | `unixnu` 命令、共享脚本、profiles、组件目录 |
| SoC | UniXNU-sm8475-common | `soc.toml`、`configs/sm8475.config`、`dts/sm8475.dtsi` |
| 设备 | 本仓库 | `board.toml`、`dts/mondrian.dts`、`patches/xnu/` |
| 固件 | uefi-mondrian | EDK2 / Mu-Silicium 构建树 |

## 构建

```bash
# 内核（Linux/WSL）
tr -d '\r' < E:/k60-work/scratch/buildv15.sh > /tmp/b.sh && bash /tmp/b.sh
# 产物
#   /opt/k60/trees/k60build/out-baseline/mondrian/ipados-16.6.1-20G81/mondrian/kernel/kernel.macho
# 打包 boot 镜像
tr -d '\r' < E:/k60-work/scratch/packv15.sh > /tmp/p.sh && bash /tmp/p.sh
#   → E:/k60-work/usb-a-stage/out/boot-v15-20261108.img
```

**路径铁则（重要）**：构建读取的是 `/tmp/usb-cdc-mainline/device`（= `/opt/k60/trees/usb-cdc-mainline/device`，同一 inode）。
`/mnt/e/hackios/UniXNU-mondrian` 是**另一份 git 副本**。改补丁前必须 `ls -li` 对比 inode、`sha256sum` 比对两侧一致后才可构建。
详见 `AGENTS.md` 铁律 12。

## 作业纪律

1. **八步流水线**（铁则 10）：同型研究 → 官方文档 → 反编译+真机数据 → 广域验证 → 方案 → 深挖 → 核验 → 真机。**缺一步不得上机**。
2. **调研驱动**（铁则 5）：任何上机/改代码前必须有已落盘的调研文档。
3. **坑必记录**（铁则 1）：`E:\k60-work\docs\PITFALLS.md`（P-NN）+ `PITFALLS-FROM-HISTORY.md`。
4. **先查 Pong 仓库**（铁则 8）：`Chengdong-Yu/UniXNU-pong` 的 `main`/`ios16` 分支与 `drivers/*` 子模块。
5. **路径核对**（铁则 12）：见上。

## 相关文档

- 项目总闸：`D:\Android\AGENTS.md`（铁律 1–12）
- 文档入口：`E:\k60-work\docs\INDEX.md`
- 现状页：`E:\k60-work\docs\HANDOFF.md`
- 八步矩阵：`E:\k60-work\docs\PORTING-PIPELINE.md`
- 坑台账：`E:\k60-work\docs\PITFALLS.md`

## 数据安全

- bring-up 全程只用 `fastboot boot`（RAM 临时引导），**不 flash 任何分区**。
- XNU 的 root/Data 使用独立 `unixnu` 分区：SHNGROOT 里的 OS/SystemOS 窗口 + 尾部 Data 窗口，不写安卓 `userdata`。
- **绝对禁止** `fastboot flash persist` / `flash all`（TEE 密钥永久损坏）。

## 许可

设备级代码采用 BSD-2-Clause-Patent。导入组件保留各自 SPDX 标记与原始许可证。
