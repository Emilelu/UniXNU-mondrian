# 移植现状与变更记录

> 本文件收纳 README 里的详细状态表与阶段性变更摘要。
> README 只保留设备身份、八步进度、仓库结构与构建入口。

本轮更新时间：2026-11-14

---

> 本文件里的 SHA 是**已完成工作的取用记录**，每条都带取用日期。
> 待办与计划里不写死上游 SHA（★37 / HR-72）——上游每小时都在推进，
> 写死的 SHA 第二天就过时。查最新状态用 `scripts/track-upstream-branches.py`。


### 可刷镜像（2026-11-14 15:09，真机验证）

```
/mnt/e/k60-work/artifacts/touch-20261114a/boot.img
201,887,744 B
sha256 0b2003f45603449b28194e29def3302d84f1de508895581c0cd0417dcf9d88e9
kernel c78a5cc93c3ec6e24de34a4a31e1b7639607fb45c2b024cb78b32753b8451b09
```

这一版同时带 GPU addon（Metal 插件 51,278,451 B）、iOS `buttons` 节点与
触摸坐标使能。上机日志 `E:\k60-work\evidence\usblog-20261114-150931\console.log`：
3,870 行、SpringBoard 254、八条真实触点、四条 HID 派发、无 panic 标记。
`MAIN-BASELINE.toml` 记在 `0143b46` 条目下；此后到 `143f3ff` 只改文档、
门禁与测试脚本，内核输入逐字节不变。

包含当天全部改动：

| 改动 | 日志判据 |
|---|---|
| 触摸 boot-option 握手 | `device confirm OK` / `FAILED` |
| 触摸 SPI 模式选择 | `SPI mode select failed` |
| 触摸 config 请求检测 | `chip requested a config` |
| 触摸 config 下载 | `CFG-DL wrote=N/1488 bad=0` |
| 触摸坐标使能 | `RAW-OFF ack=80` 后必须出现 `COORD-ON ack=80` |
| 实体键逐条件诊断 | `Pong keys: missing <prop>` |
| GPU 八条发布诊断 | `accelerator not published` / `publish skipped` |
| UFS 三模式等待 | `native-ufs-wait` |
| GPU 启动开关 | `pong_adreno_start=1` |
| GPU Metal 开关 | `pong_metal=1` |
| 音频 DT 节点 | `pong-audio`（九个待实测项写 0）|

> 上面这张表是 2026-11-12 那一版的判据。当前（2026-11-14）镜像为
> `touch-20261114a`，内核 `c78a5cc9…`，223 个补丁，判据以
> [`docs/research/touch/08-on-device.md`](../research/touch/08-on-device.md) 第 7 轮为准。

**此前的最新镜像是 `boot-v15-20261108.img`（2026-11-11），不含以上任何一项。**

## 一、硬件状态明细

| 项 | 状态 | 证据 |
|---|---|---|
| Boot chain（UEFI → UniXNU loader → XNU → launchd） | ✅ | `Pong init: exec original /sbin/launchd`，最大 pid 196 |
| UFS / APFS 三窗（OS / SystemOS / Data） | ✅ | `PONG APFS: OS root binding PASS`、`K60DATA mounted ro=0 fstype=apfs` |
| 显示首帧（1440×3200） | ✅ | `K60 DISPLAY: first frame presented (swap 1)` |
| 背光（DCS 0x11/0x29/0x51） | ✅ | `K60 PANEL: bring-up complete` |
| 锁屏 / SpringBoard | ✅ | `Pong UI: 20G81 compatibility library entered SpringBoard` |
| launchd 稳定 | ✅ | `0394` 精选缓存（22 个核心 job）已并入 `0391`，写 `/private/var/pong/xpc/launchd.plist` |
| 实体键（电源/音量） | ✅ | 三键真机可用（`Pong keys: arbiter v7 … power=1 up=1 down=1`），16 条按下/释放事件覆盖三键，逐条件诊断已消除「结果不可观测」缺口（P-142） |
| 触摸 | ✅ | 单指已真机验证，见下方「触摸」专节 |
| GPU（Adreno 730v3） | 🔄 | 见下方「GPU」专节 |
| WiFi / 蓝牙 / 音频 / 相机 / 传感器 | 📋 | planned，见 `porting.toml` |

### 触摸

- **协议**：BRL。`0x10000` 稳定读出 `BERLIN 9916R 05.80.02.63`；GTP 寄存器
  `0x8140` / `0x8047` / `0x804E` / `0x814E` 全部返回 0（2026-11-11 实测，
  见 P-129）。
- **2026-11-14 结论：单指触摸已通过真机验证。** 镜像 `touch-20261114a`
  （`boot.img` `0b2003f4…`、内核 `c78a5cc9…`）启动后 `goodix: COORD-ON ack=80`，
  随后八条 `goodix: type=1 finger=0 raw=… normalized=…` 与四条
  `Pong touch HID: type=1|3` 派发；日志 268,137 B / SpringBoard 254 行 /
  无 panic 标记，用户在场确认屏幕响应。证据
  `E:\k60-work\evidence\usblog-20261114-150931\console.log`，记录见
  [`docs/research/touch/08-on-device.md`](../research/touch/08-on-device.md) 第 7 轮。
- **真因**：旧代码只发 `0x90/0x00`（关 raw 帧），从未发本机 Android
  `goodix_htc_enable(false)` 的第二条 `0x91/0x01`（坐标上报使能）；且配置完成
  只看 `ack[1]`、不等 `reply[0] == 0x80`，没写完的配置看起来已完成。
- **尚未验收**：两点同时按下的触点 ID 稳定性与独立 release、屏幕边缘手势、
  手指移动时的持续帧率、息屏 `tap-to-wake`；`0x10308` 头长度取自 `misc+48`
  仍是推断（保留模块只证明 `misc+44` 与 `misc+50`）。
- **2026-11-12 变更**：触摸驱动整体换成 yibiya `fix/touch-gpu-bringup`
  分支的干净实现（47,040 B / 1,039 行，替换原有的 239,781 B / 5,452 行
  诊断版）。新实现使用真实触摸坐标范围 `14400×32000`、显式
  `bitbang-pins` 角色元组、`k60_touch_se=5 k60_touch_rcg=1`。

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

## GPU / Metal：种子已就位，插件无人加载（2026-11-13 06:16 实测）

`K60SEED` 三行证明内核侧投递成功，且权限与判据完全吻合：

```
K60SEED /private/var/pong/PongAdrenoMetal.publish          bytes=2   resid=0 error=0 uid=0 mode=0x81a4
K60SEED /private/var/pong/PongAdrenoMetal.clients          bytes=122 resid=0 error=0 uid=0 mode=0x81a4
K60SEED /private/var/pong/PongAdrenoMetal.bundle/Info.plist bytes=555 resid=0 error=0 uid=0 mode=0x81ed
```

`0x81a4` = 0644、`0x81ed` = 0755、`uid=0`，满足 `PongMetalPlugin.mm:191-200` 的
`S_ISREG` / `st_uid == 0` / `(st_mode & 022) == 0` 三个条件。

同一次启动里 `PONG METAL: … publication status=0x0`，说明 `IOAcceleratorES` 也发布了。

**但 UI 依旧判定软件路径**，而且原因是可定位的：`userland/ui_compat.c:510` 只有在
`MTLCreateSystemDefaultDevice()` 返回 nil 时才打印
`optional camera-filter GPU prewarm skipped (software-only platform)`——
所以那不是“策略选择”，是**这个进程里确实没有 Metal 设备**。

同一份日志里 `DYLD_INSERT`、`PongMetal`、`libpong` 三个词零命中，
`NativeAdrenoPublish.cpp` 的 MetalPluginName 读取者计数也没有输出，
说明 `PongAdrenoMetal.bundle` 虽然被 0340 部署到 `/private/var/pong/`，
**却从来没有任何进程 dlopen 过它**。Apple 的 Metal 装载器只认
`/System/Library/Extensions/<MetalPluginName>.bundle`，而我们根卷是密封的（P-27），
所以“把 bundle 放对位置”这条路本身不成立。

结论：剩下的不是权限问题，也不是 GPU 硬件问题，而是**装载路径**问题——
必须由用户态自己在调用 `MTLCreateSystemDefaultDevice()` 之前
`dlopen("/private/var/pong/PongAdrenoMetal.bundle/PongAdrenoMetal", RTLD_NOW|RTLD_GLOBAL)`，
让 ObjC 类先注册进进程，再让 Metal 去匹配 IOAcceleratorES。

## GPU / Metal 现状（2026-11-13 实测，修正旧结论）

三条来自 `E:\k60-work\evidence\usblog-20261113-055021\console.log`：

```
616: PONG METAL: real IOAcceleratorES provider published for20G81 discovery
618: PONG METAL: NativeAdreno complete runtime publication status=0x0
622: PONG ADRENO: startup COMPLETE; hardware armed result=0 a=0x40000007 b=0x20010000
712: Pong init: native Metal entry enabled for backboardd
1557: Pong UI: optional camera-filter GPU prewarm skipped (software-only platform)
```

1. **`pong_metal=1` 不再导致 backboardd 崩溃。** 本文件早前记的
   "`pong_metal=1` → backboardd crash `-[NSURL fileURLWithPath:]` nil，只有
   `pong_metal=2` 稳定" 已失效：那次崩溃发生在 Data 卷与 `libSystem` 还加载失败的
   时期，与取值只是时间上的巧合。取 `=1` 现在能发布 provider、能进
   `Early boot complete`。
2. **`pong_metal=2` 时那段发布代码根本不会执行**，所以"看不到 Metal"曾长期被误读
   为失败；实际是 `PongAdrenoNativeGlue.cpp:43-49` 只在 `metal==1` 时调用
   `PongAdrenoPublishMetalAccelerator()`。
3. **用户态仍判定为 software-only**（第 1557 行）。原因在文件部署，不在内核：
   日志里 `K60METALPLUGIN deploy bytes=94928` 只有 bundle 的**可执行文件**，
   缺 `Info.plist`、`PongAdrenoMetal.publish`、`PongAdrenoMetal.clients`，
   以及 `PongMetalBridge.dylib`、`libvulkan_freedreno.dylib`。`PongMetalPlugin.mm:191-200`
   要求 `.publish` 内容为 `1`、属主 uid 0、组与其他位不可写，否则
   `selectedClient()` 直接返回 false——这正是 software-only 的来源。

缺失清单与体积：`Info.plist` 695 B、`PongAdrenoMetal.publish` 2 B、
`PongAdrenoMetal.clients` 数十字节（这三项极小，可用内核 blob 方式部署）；
`PongMetalBridge.dylib` ≈33 MB、`libvulkan_freedreno.dylib` ≈18 MB（必须走
文件系统，不可能做成 C 数组）。
