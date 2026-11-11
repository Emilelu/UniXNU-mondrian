# UniXNU-mondrian

Redmi K60（代号 **mondrian**，高通 **SM8475**）的 UniXNU 设备支持仓库。

**当前目标：iOS 16.6.1（20G81）/ darwin22 上跑通完整硬件。**

> 本 README 最后更新：2026-11-12。历史路线（darwin24 / iPadOS 18.7.10）已归档到 `chore/archive-darwin24-main-20261103`。

## 八步流程进度

| 硬件 | ① 同型 | ② 官方 | ③ 反编译 | ④ 广域 | ⑤ 方案 | ⑥ 深挖 | ⑦ 核验 | ⑧ 上机 | 当前状态 |
|---|---|---|---|---|---|---|---|---|---|
| **触摸（Goodix GT9916R / BERLIN）** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | **卡在 ⑦ 核验** |
| **GPU（Adreno 730v3 / Metal）** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | 可刷机（⑦ 已核验） |
| CPU | — | — | — | — | — | — | — | ✅ | device-verified（未建八步记录） |
| UFS / 存储 | — | — | — | — | — | — | — | ✅ | device-verified（未建八步记录） |
| 显示 | — | — | — | — | — | — | — | ✅ | device-verified（未建八步记录） |
| 固件 / 启动 | — | — | — | — | — | — | — | ✅ | device-verified（未建八步记录） |
| 电源 | — | — | — | — | — | — | — | ✅ | device-verified（未建八步记录） |
| 诊断 | — | — | — | — | — | — | — | ✅ | device-verified（未建八步记录） |
| WiFi / 蓝牙 / USB | — | — | — | — | — | — | — | — | planned |
| 音频 | — | — | — | — | — | — | — | — | planned |
| 基带 | — | — | — | — | — | — | — | — | planned |
| DSP | — | — | — | — | — | — | — | — | planned |

> ✅ 完成　◐ 部分　❌ 未完成　— 未建立记录
>
> 表格由 `scripts/render-eight-step-table.py` 从 `docs/research/EIGHT-STEPS.toml` 生成，`--check` 可校验 README 是否与数据一致。
> 八步定义见 [`docs/engineering/EIGHT-STEP-SPEC.md`](docs/engineering/EIGHT-STEP-SPEC.md)。

## 分支

| 分支 | 用途 |
|---|---|
| **`main`** | 主线（默认分支），所有可工作的阶段性成果都合到这里 |
| `feat/first-frame-20261107` | 历史里程碑：iOS 16.6.1 用户态首帧（2026-11-07，独立历史线） |
| `chore/archive-darwin24-main-20261103` | 已废弃的 darwin24（iPadOS 18）路线（归档保留） |

> 2026-11-11 清理：删除了已完全合入 `main` 的 `fix/k60-measured-high-window`，
> 以及与之重复的 `archive/first-frame-20261107`、`archive/darwin24-main-20261103`
> 本地别名。远端现存 3 个分支。

提交规范见 `AGENTS.md` 铁律 11：**改动后及时 commit，阶段性成果及时 push**（push 用 Windows 侧 git）。

## 当前状态（2026-11-09）

| 项 | 状态 | 证据 |
|---|---|---|
| Boot chain（UEFI → UniXNU loader → XNU → launchd） | ✅ | `Pong init: exec original /sbin/launchd`，最大 pid 196 |
| UFS / APFS 三窗（OS / SystemOS / Data） | ✅ | `PONG APFS: OS root binding PASS`、`K60DATA mounted ro=0 fstype=apfs` |
| 显示首帧（1440×3200） | ✅ | `K60 DISPLAY: first frame presented (swap 1)` |
| 背光（DCS 0x11/0x29/0x51） | ✅ | `K60 PANEL: bring-up complete` |
| 锁屏 / SpringBoard | ✅ | `Pong UI: 20G81 compatibility library entered SpringBoard` |
| launchd 稳定 | ✅ | `0394` 精选缓存（22 个核心 job）已并入 `0391`，写 `/private/var/pong/xpc/launchd.plist` |
| **实体键（电源/音量）** | 🔄 | 驱动已编译/链接/调用（`bsd_init.o` 有 `U _pong_buttons_init`），`configuration()` 结果不可观测 |
| **触摸** | 🔄 | 协议实测确认是 **BRL**（`0x10000` 读出 `BERLIN 9916R 05.80.02.63`；GTP 寄存器 `0x8140` 等全返回 0，见 P-129）。SPI 全通、config `state=80`、芯片有中断与原始帧，但触点恒为 0。轮询节拍原为 2 ms，按同 SoC PHK110 实测改为 20 ms 待验证 |
| GPU（Adreno 730v3） | 🔄 | 内核全链 `result=0`（42 行）、`CP ready`、`IOAcceleratorES` 已发布；Metal 插件 94,928 B 已部署且属主修为 0，`native Metal entry enabled` 已出现；插件注入 backboardd 仍崩溃（`-[NSURL fileURLWithPath:]`），当前用 `pong_metal=2` 绕开
| WiFi / 蓝牙 / 音频 / 相机 / 传感器 / 电源 | 📋 | 八步调研已完成，实现进行中 |

详细状态与缺口矩阵见 [`E:\k60-work\docs\PORTING-PIPELINE.md`](file:///E:/k60-work/docs/PORTING-PIPELINE.md)。


## 2026-11-11 变更摘要

### 从上游 `yibiya/fix/ui-startup-blob` 移植（该分支 2026-11-11 新建）

此前该镜像的 refspec 只跟踪 `upstream-fix` 单分支，其它 5 个分支从未被下载。
修复 refspec 后才发现这条分支含 319 个 `main` 没有的提交。

| 修复 | 提交 | 解决的问题 |
|---|---|---|
| `userland/ui_compat.c` | `f291b52` | `CFPreferencesSetAppValue` 在 `__attribute__((constructor))` 里调用会阻塞主线程 → backboardd 崩溃。移到 `present_home()`（主队列运行时）。 |
| `patches/xnu/0394` | `5198a67` | 原 launchd 服务缓存引用本移植不带的 App-cryptex 程序（`webbookmarksd`），launchd SIGSEGV → 内核 panic `initproc exited`。改为 22 个核心 job 的精选缓存。 |
| `patches/xnu/0340` | `c6e555c` | UI 库换成上游的 95,856 B 版本（含上述修复）。 |

`0394` 的调用点已并入 `0391`（两者抢同一处 `kern_exec.c` 锚点，独立应用会冲突）。

### 触摸协议：一次被实测推翻的纠错

`docs/ANDROID-HW-TRUTH.md` 曾据模块名 `goodix_ts` 推断 K60 走 **GTP 协议**。
2026-11-11 的实测推翻了它：

```
同一启动 usblog-20261111-233246
第 710 行: goodix: chip "BERLIN", firmware "9916R" 05.80.02.63   ← BRL 0x10000 OK
第 805 行: GTP 0x8140 id=.... fw=0000                            ← GTP 全 0
第 807 行: GTP 0x804E status=0
第 808 行: GTP 0x814E buffer_status=0 points=0
```

探针在 `resume sequence done` 之后执行，芯片当时处于工作状态，GTP 仍全 0
→ **BRL 才是正确协议**。`goodix_ts` 只是模块名，Goodix 的 Berlin 系列
在 vendor 内核里也用它加载（内部走 `goodix_brl_hw.c`）。

真正的线索来自同 SoC 的兄弟移植（`Seanding1998/hakios-xnu-kernel`，
一加 Ace 2 / PHK110 / **SM8475**）：`docs/phk110/waves/wave12c-electrical.md`
记录该 SoC 上的触摸控制器**每 CS 帧只吐一个响应块，块按 ~20 ms 节拍重新武装**，
微秒级续读会踩进未武装窗口读回错位填充。我们的轮询循环
（`if (!int_now || ++idle >= 1)` + `sleep_ms(2)`，条件恒真）每 2 ms 无条件读，
比该节拍快 10 倍——这解释了 `0x10308` 为什么跨几十次读取永远返回同一串字节。
轮询已改为 20 ms 节拍待验证。详见 P-129。

### 其他

- **goodix resume**：来自从未入 series 的 `pong-goodix-resume.patch`，
  reset + probe + 清除 report 字节，唤醒 Android 遗留的 sleep/gesture 状态。
- **Metal 插件部署**：94,928 B，用 2026-11-11 源码在 Mac 上重编并签名，
  通过 `0340` 的同一机制写入 `/private/var/pong/PongAdrenoMetal.bundle/`。
- **工具链**：新增 `scripts/track-upstream-branches.py`（上游全分支追踪，
  含 zizhan 等参考仓库）；`gate.py` 新增 `[P]` 协议断言与 `[Q]` 补丁结构校验。

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
