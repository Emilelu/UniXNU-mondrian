# 移植现状与变更记录

> 本文件收纳 README 里的详细状态表与阶段性变更摘要。
> README 只保留设备身份、八步进度、仓库结构与构建入口。

本轮更新时间：2026-11-12

---

> 本文件里的 SHA 是**已完成工作的取用记录**，每条都带取用日期。
> 待办与计划里不写死上游 SHA（★37 / HR-72）——上游每小时都在推进，
> 写死的 SHA 第二天就过时。查最新状态用 `scripts/track-upstream-branches.py`。

## 一、硬件状态明细

| 项 | 状态 | 证据 |
|---|---|---|
| Boot chain（UEFI → UniXNU loader → XNU → launchd） | ✅ | `Pong init: exec original /sbin/launchd`，最大 pid 196 |
| UFS / APFS 三窗（OS / SystemOS / Data） | ✅ | `PONG APFS: OS root binding PASS`、`K60DATA mounted ro=0 fstype=apfs` |
| 显示首帧（1440×3200） | ✅ | `K60 DISPLAY: first frame presented (swap 1)` |
| 背光（DCS 0x11/0x29/0x51） | ✅ | `K60 PANEL: bring-up complete` |
| 锁屏 / SpringBoard | ✅ | `Pong UI: 20G81 compatibility library entered SpringBoard` |
| launchd 稳定 | ✅ | `0394` 精选缓存（22 个核心 job）已并入 `0391`，写 `/private/var/pong/xpc/launchd.plist` |
| 实体键（电源/音量） | 🔄 | 驱动已编译/链接/调用（`bsd_init.o` 有 `_pong_buttons_init`），`configuration()` 结果不可观测 |
| 触摸 | 🔄 | 见下方「触摸」专节 |
| GPU（Adreno 730v3） | 🔄 | 见下方「GPU」专节 |
| WiFi / 蓝牙 / 音频 / 相机 / 传感器 | 📋 | planned，见 `porting.toml` |

### 触摸

- **协议**：BRL。`0x10000` 稳定读出 `BERLIN 9916R 05.80.02.63`；GTP 寄存器
  `0x8140` / `0x8047` / `0x804E` / `0x814E` 全部返回 0（2026-11-11 实测，
  见 P-129）。
- **当前卡点**：SPI 全通、config `state=80`、芯片有中断与原始帧，
  但触点计数恒为 0。
- **2026-11-12 变更**：触摸驱动整体换成 yibiya `fix/touch-gpu-bringup`
  分支的干净实现（47,040 B / 1,039 行，替换原有的 239,781 B / 5,452 行
  诊断版）。新实现使用真实触摸坐标范围 `14400×32000`、显式
  `bitbang-pins` 角色元组、`k60_touch_se=5 k60_touch_rcg=1`。
- **未验证**：⑧ 上机。

### GPU

- **内核侧**：Adreno 全链 42 行 `result=0`（parent ARC、CX clocks、
  GMU firmware/HFI、GMU power handshake、GMU native4K context、
  CP ready、CP/user-client startup）。
- **Metal 插件**：94,928 B，已写入
  `/private/var/pong/PongAdrenoMetal.bundle/`，属主 uid=0。
- **当前卡点**：`pong_metal=1` 时 backboardd 崩溃
  （`-[NSURL fileURLWithPath:]` nil）；`pong_metal=2` 时系统稳定
  但 `IOAcceleratorES` 发布 0 次、`native Metal entry` 0 次、帧率 0。
- **未验证**：⑧ 上机。

---

## 二、2026-11-11 变更摘要

### 从 `yibiya/fix/ui-startup-blob` 移植

此前上游镜像的 refspec 只跟踪 `upstream-fix` 单分支，其它分支从未下载。
修复 refspec 后发现该分支含 319 个 `main` 没有的提交。

| 修复 | 提交 | 取用日期 | 解决的问题 |
|---|---|---|---|
| `userland/ui_compat.c` | `f291b52` | 2026-11-11 | `CFPreferencesSetAppValue` 在 `__attribute__((constructor))` 里调用会阻塞主线程 → backboardd 崩溃。移到 `present_home()`（主队列运行时）。 |
| `patches/xnu/0394` | `5198a67` | 2026-11-11 | 原 launchd 服务缓存引用本移植不带的 App-cryptex 程序（`webbookmarksd`），launchd SIGSEGV → 内核 panic `initproc exited`。改为 22 个核心 job 的精选缓存。 |
| `patches/xnu/0340` | `c6e555c` | 2026-11-11 | UI 库换成上游的 95,856 B 版本（含上述修复）。 |

`0394` 的调用点已并入 `0391`——两者抢同一处 `kern_exec.c` 锚点，
独立应用会冲突。

### 触摸协议：一次被实测推翻的纠错

`docs/engineering/ANDROID-HW-TRUTH.md` 曾据模块名 `goodix_ts` 推断
K60 走 GTP 协议。2026-11-11 的实测推翻了它：

```
同一启动 usblog-20261111-233246
第 710 行: goodix: chip "BERLIN", firmware "9916R" 05.80.02.63   ← BRL 0x10000 OK
第 805 行: GTP 0x8140 id=.... fw=0000                            ← GTP 全 0
第 807 行: GTP 0x804E status=0
第 808 行: GTP 0x814E buffer_status=0 points=0
```

探针在 `resume sequence done` 之后执行，芯片当时处于工作状态，
GTP 仍全 0 → **BRL 才是正确协议**。`goodix_ts` 只是模块名，
Goodix 的 Berlin 系列在 vendor 内核里也用它加载（内部走 `goodix_brl_hw.c`）。

真正的线索来自同 SoC 兄弟移植（`Seanding1998/hakios-xnu-kernel`，
一加 Ace 2 / PHK110 / SM8475）：`docs/phk110/waves/wave12c-electrical.md`
记录该 SoC 上的触摸控制器**每 CS 帧只吐一个响应块，块按 ~20 ms 节拍
重新武装**，微秒级续读会踩进未武装窗口读回错位填充。

### 其他

- **goodix resume**：来自从未入 series 的 `pong-goodix-resume.patch`，
  reset + probe + 清除 report 字节，唤醒 Android 遗留的 sleep/gesture 状态。
- **Metal 插件部署**：94,928 B，用 2026-11-11 源码在 Mac 上重编并签名，
  通过 `0340` 的同一机制写入 `/private/var/pong/PongAdrenoMetal.bundle/`。
- **工具链**：`scripts/track-upstream-branches.py`（上游全分支追踪）、
  `scripts/research-gate.py`（研究完整性）、`scripts/eight-step-gate.py`
  （八步流程）、`scripts/porting-gate.py`（porting.toml schema）。

---

## 三、2026-11-12 变更摘要

### 触摸/GPU 驱动取自 `yibiya/fix/touch-gpu-bringup`

| 提交 | 取用日期 | 内容 |
|---|---|---|
| `2994f1f` | 2026-11-12 | `fix(input): supply actual K60 touch metadata` |
| `6565837` | 2026-11-12 | `fix(gpu): use monitor access for K60 RSC` |
| `4eb8395` | 2026-11-12 | `fix(gpu): map only consumed GCC pages` |
| `c80e0e1` | 2026-11-12 | `fix(input): adapt real Goodix and HID to K60`（触摸驱动重写）|

### 流程与门禁

- `docs/engineering/EIGHT-STEP-SPEC.md`：八步流程完整定义
  （目的 / 必做 / 证据格式 / 通过条件 / 反模式）。
- `docs/research/EIGHT-STEPS.toml`：逐硬件的八步证据。
- `docs/research/SOURCES.toml`：研究完整性清单。
- `CREDITS.md`：贡献者与外部来源。

---

## 四、相关文档

| 文档 | 内容 |
|---|---|
| `docs/engineering/EIGHT-STEP-SPEC.md` | 八步流程规范 |
| `docs/engineering/HARD-RULES.md` | 铁则 ★1–★35 |
| `docs/engineering/PITFALLS.md` | 坑记录 P-01–P-130 |
| `docs/engineering/ANDROID-HW-TRUTH.md` | Android 实机硬件真值 |
| `docs/engineering/TOUCH-STATEMACHINE.md` | 官方 Goodix 驱动状态机 |
| `docs/engineering/K60-TOUCH-CHECKLIST.md` | 触摸八步核对清单 |
| `porting.toml` | 14 个子系统的记录（官网设备页数据源）|
| `CREDITS.md` | 贡献者与来源 |
