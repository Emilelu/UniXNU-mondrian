# 移植现状与变更记录

> 本文件收纳 README 里的详细状态表与阶段性变更摘要。
> README 只保留设备身份、八步进度、仓库结构与构建入口。

本轮更新时间：2026-11-16

### 重新审视后的当前结论（2026-11-16）

完整依据与待办见 [重新审视报告](../audits/REASSESSMENT-2026-11-16.md)。本次只核对证据与文档，没有新构建或上机；下方带日期的旧结论是历史记录，发生冲突时以本节为准。

- 已登记的可启动 main 基线是 `baseline-20261116a`；当前 main 为 `1eba4b9` / `snap-r219`，此后提交包含文档与门禁修复，不能把历史镜像当作当前 HEAD 已上机的证明。
- WiFi c7 已读到硬件 SBL/READY，而软件仍为 PBL/POR，超时 `-110`。软件轮询能调用 MHI IRQ handler；`MSI delivered` 打印又在初始化成功后的循环，c7 的失败路径不会执行。现有日志不能证明 MSI 是否到达，也不能把主动推 AMSS 当成已验证根治。c8 暂停，先审重复下载、重入与 READY/M0 转移。
- BT d7 已完成 rampatch，NVM 阶段报 90 s 总预算耗尽、`power=1 result=-60`。不能从没有 `command timeout` 推出每段正常或预算必然不足。d8 是计数观测候选，但实验树的 Bluetooth 仍为 parked，八步 flash 绿色略过了它；先补真实覆盖与实验预测。
- ADSP 复核发现 plan C 的 rail 检查只保护晚期 legacy，早期 publisher 曾可绕过它。owner 分支现已在 `d336fe2` 恢复 `resources_cb` 拒绝；保存的真实回调宿主链轨迹显示 map_smem/alloc/init/mem/load/auth/publish 全为 0（日志与哈希见审计）。这不是功能镜像或 Native 执行验证；继续离线核 rail 采样器，rail-only 与 PAS/handoff 功能图分开验收。
- 全仓同步已结束但结果为 partial：1 更新 / 51 clean / 7 skip / 3 fail / 3 conflict（65 次操作，含重复路径）。恢复出 598 个参考源候选 SHA，其中 525 无台账；新分支审核边界未知，不能称全历史已覆盖。tracker basename 碰撞与 reviewed 水位混淆仍待修。

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
| 蓝牙（QCA6490 / SE20） | 🔄 | 版本查询和 rampatch 下载已观测；d7 在 NVM 阶段总预算超时，完整固件启动、UART.SK、用户态可用性未证；d8 等实际八步覆盖 |
| WiFi（QCA6490） | 🔄 | c7 到硬件 SBL/READY，主机状态未跟进并 -110；MSI、DMA/缓存和状态机原因未定，c8 暂停审查 |
| ADSP / 电池 / 音频 | 🔄 | PAS1/handoff 尚未验证；owner 分支已恢复早期拒绝，保存的宿主轨迹无下游 SMEM/PAS 副作用；功能上机仍暂停 |
| 相机 / 传感器 | 📋 | planned，见 `porting.toml` |

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

- **历史内核证据**：已出现 Adreno 启动终态及 `PONG METAL: real IOAcceleratorES provider published`。这证明对应镜像的初始化/服务发布，不等于完整 Metal 渲染可用。
- **部署证据**：后续 GPU 实验已记录 `K60METAL deploy files=6/6 error=0`；旧的「只有 94,928 B 可执行文件、缺五个依赖」是早期部署状态，不能当作当前结论。
- **尚未验收**：稳定硬件渲染、用户态完整链路和最新源码重编的插件。历史 `pong_metal=1` 实验存在 backboardd 崩溃，`NSURL nil` 字符串本身不构成根因判据；不能据此宣布已修复或必然失败。`pong_metal=2` 基线也不能证明真实 Metal 发布/渲染通过。
- **产物限制**：严格构建使用已有插件 bundle；仅更新插件源码不会自动重编该 bundle。下一次功能验证必须绑定实际插件哈希、镜像身份与对应日志，⑧ 保持未完成。

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

## 六、2026-11-16 变更摘要

### 蓝牙阶梯第一次跑通，读到 QCA6490 的版本寄存器（P-219）

`ml_io_map` 的 `io_submap` 只有 8 MiB（`osfmk/arm/io_map.c:65`），而全内核 37 个
`ml_io_map` 调用点已占 7.23 MiB（`scripts/check-io-map-budget.py` 在已应用树上实测）。
蓝牙完整阶梯再要 1 MiB 的 TLMM 窗口（`K60_TLMM_SIZE = 0x00100000`）必然撞穿，
而 `:128` 的 `kmem_alloc` 在 `KMA_NOFAIL` 下不看返回值 —— 于是 `kmem_alloc(... 0x100021):
failed with 3` 变成控制台起来**之前**的 panic，现象是 0 字节日志，和「驱动从未运行」
完全无法区分。

`patches/xnu/0621-k60-io-submap-budget.patch` 把 `IO_MAP_SIZE` 提到 32 MiB（子图只预留
虚拟地址，未 map 的部分不花物理页）。单变量验证 `bt-d5-iomap`（series 233，同一配方只多
这一条）上机 `usblog-20261116-064150`：3,241 行 / 224,863 B / SpringBoard 132 / panic 0，
阶梯完整跑到固件下载 —— `:486 smmu plan sid 0x483 slot 110 bank 72 action install
dma 0x90bc20000`、`:488 dma buffer and smmu bypass ready`、`:493 clocks vote cbcr
core=0x4220`、`:494 full: qbt_boot enter`、**`:707 [bluetooth] QCA controller version
0x12110201`**、`:708 addon: serving 146068 0`、`:724 addon: serving 6442 0`。

当时还记录了 `:1345 marconi-bt: Unable to match bluetooth service in device tree.` 与 `:1346 Not a valid MAC address (all 00s)`，以及 `:186 K60 BT: published local address ee:98:c5:8a:6b:4e`、`:1347 bluetooth: Got local-mac-address`。这些只证明对应身份发布与用户态报错同时存在，不能据此把剩余问题缩成 ADT。后续 d7 在 NVM 阶段返回总预算超时，完整固件启动和 UART.SK 尚未通过；当前判读见文首审计，不沿用早前「内核已全通，只缺用户态节点」结论。

### 固件卷重建：能用，但不可复现（P-216，P-154 关闭）

同一检出、同一 pin、无未提交改动，三次重建固件卷得到三个哈希
（`ce12d145a71e` / `77ad2474a468` / `9f20de15388a`）。根因是 LLD 派生的 CodeView
build-id 不受 `SOURCE_DATE_EPOCH` 影响，而固件卷是压缩的，一个 GUID 变了就重写整个
压缩段——3,145,728 B 里 453,604 B 不同、1,739 个不连续区间。

**同一 payload 只换卷上机**（`fdtest-20261116a`，`boot.img 51d20538…`，证据
`usblog-20261116-025525`）：3384 行 / 230,107 B / SpringBoard 129 / `Early boot complete`
1 次 / `K60DATA mounted` 1 次 / panic 0 / `menu:` 与 `config: no boot entry` 0 次。
⇒ **P-154 关闭**：从当前 pin 重建的卷能找到 payload。FD 的 sha256 从此只当「这一次构建的
标识」，不当身份。新门禁 `scripts/check-firmware-volume.py`（9 例测试）。

### 固件卷的构建依赖一个只存在于本机的 commit（P-217）

`board.toml` 的 `[firmware].patches` 原本是空列表，注释称记录的 pin `6f805f2` 已含全部六个
K60 修复、本机的 `3d2a9fa` 是它的祖先。**两句都不成立**：`git merge-base 3d2a9fa 6f805f2`
返回空；`3d2a9fa` 的父提交 `3c9c7b2` 不在任何远程分支；11 个文件逐文件对比，pin 上只有
`AsmMacroLib.h` 是修好的（且上游用的是另一种修法），其余 10 个是原始状态。`Mu_Basecore`
是嵌套仓，构建读工作树内容而非 gitlink —— 所以本机一直能构建，**干净 clone 会构建出坏的卷**。

修法：工作树切到 `6f805f2`，五个修复改由 `[firmware].patches` 施加
（`Resources/MuPatches/{Auth-Service,Boot-Manager,K60-Exception-Image,Timer,Usb-Bus}.patch`，
均已被 `origin/main` 跟踪、对 pin `git apply --check` 全通过；应用后与 `3d2a9fa` 的 11 个文件
有 10 个逐字节相同）。新门禁 `scripts/check-basecore-pin.py`（10 例测试）钉住三件事：
工作树 HEAD 等于记录的 pin、每个补丁存在且能 apply、故意偏离必须在手册里写明。

### wifi 家族七张 0 字节镜像的真因（P-215）

`wifi-20261116c3`（`patches/wifi/0012` 让 `pong_smmu_lease_lock()` 惰性自建锁）上机
`usblog-20261116-015128`：221,429 B / 3,202 行 / **SpringBoard 132** / panic 0 /
`:482 K60DATA mounted` / `:972 Early boot complete`。

真因：UFS 的 `hostBringUp()` 取同一把 Apps SMMU 锁，而锁只在 `pong_rpmh_init()` 里分配、
后者由 `pong_wifi_start_optional()` 调用——UFS 更早。锁为 NULL 时 `pong_smmu_lease_lock()`
返回 false，UFS 直接 `transportFailure("Apps SMMU lease unavailable")` 放弃 transport，
没有根设备，内核在 console worker 起来前死掉，日志一个字节都没有。

### series 指纹双命名空间（P-214）

`build-strict.sh` 量的是 series **文件字节**（64 hex），`porting-gate.py` /
`record-boot.py` 量的是 `names+sizes`（16 hex），两者永远不相等，iron-4/hard-33 在 main
上恒红。修法：唯一实现 `scripts/series-fingerprint.py` + manifest 带
`"namespace": "names+sizes"` + 读者拒绝跨命名空间比较。

### 其它

- P-212（把配置打印成证据的日志）、P-213（门禁只读字面量不读变量传播）落账。
- bt 二分八张矩阵全部实飞：`h34`（h3+h4，不带 h1/h2）能起（SB 128），推翻「致命集是
  h3×h4」与「h2 是前置」两条推断；唯一站得住的表述是**全量 0005 四者齐备才 silent**。
- `probe: armed` 与 `[bluetooth] power=` 的缺失是 **h3 单独**造成的可观测性副作用。

## 五、2026-11-15 变更摘要

### 电池入口与 ADSP 发布器曾是死代码（P-208）

`adsp-20261115d`（`pong_handoff_publish=1`）真机 SpringBoard 132、panic 0，却
`K60Handoff:` 命中 0 次。`nm -u IOKitBSDInit.cpo` 显示该 TU 从未引用
`k60_adsp_handoff_publish` / `k60_physical_battery_start`：`-DXNU_K60_PHYSICAL_BATTERY=1`
只挂在 `KernelConfigTables.cpo` 上，`iokit/bsddev/IOKitBSDInit.cpp` 的守卫块整块编译成空，
而 `-force_load` 让符号永远在 kernel 里，所以 P-190 一直假绿。define 已进全局
`EXTRA_CFLAGS`，并新增 P-208 门禁（要求 `IOKitBSDInit.cpo` 引用该符号，仅在
`--kernel` 显式给出时判决）。`baseline-20261115a` 的桩路径（无载体）也已验证通过。

### ADSP 固件载体合入 main（PAS1 解锁的第一步）

- `feat/adsp-carrier`（27 提交）no-ff 合入（`996aac6`）：26 记录 / 23,506,184 B 的
  ADSP 镜像容器经 `0620-k60-adsp-blob.patch` + `osfmk/arm64/k60_adsp_blob.s` 内嵌进
  内核（P-197 的载体 workaround），`build-strict.sh --adsp-blob` 负责生成、校验、
  输入 pin 与 manifest 键。
- 上机验证 `adsp-20261115c`（kernel `402f8cb1…` 128,991,232 B）：真机
  `usblog-20261115-213413` 干净进桌面（SpringBoard 128 行、panic 0）；发布器按设计
  休眠（该图没有 `pong_handoff_publish=1`）。功能图 `adsp-20261115d` 已出
  （30 args / 598 B），等上机窗口。
- 补 `f760086`：无 `--adsp-blob` 的构建写一字节桩 + `len=0`，否则 0620 无条件登记
  的 `.s` 会让内核 make 缺源失败。

### refmine 判决工具合入 main

- `feat/judge-tools` 原基于 `9176f5c`（旧 main），直接合并会删掉 charger 六篇、
  P-205/P-206 与 identity seed 文件；Lead 先 rebase 到 main 再 no-ff 合并
  （`4f56970`）。新增 `scripts/judge-z0.sh`、`scripts/judge-wifi-boot.py`
  与两套测试（11 + 14 例），以及 `docs/wifi` 判决账本修正（P-201 口径）。

### 平台身份种子（identity seed）落地并真机验证

- `board.toml` 的 `[payload."adt"]` 增加 `"unique_chip_id" = "required"`；
  `build-strict.sh` 默认 `UNIXNU_UNIQUE_CHIP_ID=4B36305400000001` 并转发
  `--unique-chip-id`（`3ea8d71` / `dafa502` / `2f9f991`）。
- 离线 payload 验证：`unique-chip-id` 5 处、`chip-id` 9 处（此前 0）。
- `seed-20261115a`（kernel `a07e9565…`、boot.img `1fc1169e…`）真机：
  `usblog-20261115-155741`，247,731 B / SpringBoard 183 / 无 panic /
  `no platform identity` 0 命中 → `3ea8d71` 记 `state="booted"`（`3e59ba5`）。

### 上机窗口（2026-11-15）

- `wifi-20261116t2`（固件挪 `__DATA,__const`）：port-not-observed → 固件驻留
  假设否证，wifi 只剩 DarwinBoot pool/窗口通道方向。
- `bt-s4c-20261115c`（负向，空 blob）：进桌面，`addon: no GpuAddon property`
  判据命中、`K60 BT: published local address ee:98:c5:8a:6b:4e`（identity 生效）；
  新崩溃族 C：backboardd `getBytes:range:`（根因 = `0509` 三属性发成 OSString，
  已立项 `docs/research/display/BACKBOARD-CRASH-FAMILIES.md`）。
- `bt-s4b-20261115c`（正向，带 blob）：port-not-observed → 唯一变量 =
  `patches/bt/0005` 与 blob 的组合，bt 线四 hunk 二分图（h1–h4）已备齐待飞。
- `usb-20261115c`（mode-2）：boot-and-echo 全流程 PASS（COM5 9.5 s、
  sent=64 received=64）；`usb-20261115d`（mode-1）：265,561 B / SB 133 /
  五条 `K60BEACON` 自发信标，主机侧 MI_00=COM6、MI_02=vendor 无驱动（预期）。
  P1+P2 合体经真机验证，usb 线收工。
- `thermal-20261115b`（bias=85000）：22 passed / 0 failed、tsens zone 发布
  `Thermal_Level_Warning=3`；cooling 终局排序 ddr 停核 > cpufreq-cdev（EPSS 只读）。

### 流程与门禁

- P-203：`git worktree prune` 在 linked worktree 里跑会清掉主仓 `.git/worktrees/`
  下全部管理目录（19 棵全挂、不可逆）——guard 拒 shared-metadata 动词 +
  `scripts/repair-worktrees.py` 通用修复器（29 例宿主测试）。
- P-204：判据不能建立在「某个串出现 N 次」上（一天三次同形错误），判据必须
  自证、指向具体对象、格式串从源码抄。
- P-205 加强（`2152c6e`）：`check-readme.py` 新增第五条对账——两份 README 的
  八步表块必须等于 `render-eight-step-table.py` 从 EIGHT-STEPS.toml 现场渲染的
  结果。从此「合并一个新增 `[hardware.*]` 行的分支而没重生成八步图」会在
  check-rules 直接红（自测 10 例）。
- `feat/charger` 11 提交 no-ff 合入 main（`fd6adeb`）：订阅 ACK 按 ADSP 固件
  opcode-4 handler 钉死 (type=1, 16 B)，`build-k60-physical-battery.py` 产出
  `MEASURED_NOTIFY_REPLY=(1,16)` 且抓包只能确认不能覆盖；GLINK 契约与
  `K60Battmgr` 白名单对齐；104 字节 handoff 发布规范落库。八步表新增充电行
- P-206（`c97a4cf`）：`check-build-env.py` 不再写死 `mondrian` board 目录——从
  out 树按 mtime 推导（wifi 线的 `mondrian_wifi` 首次构建死在
  `Availability.h` file not found 而门禁一直验旧树假绿）；`FAKEROOT_FILES`
  2→5（三个 Availability 头 + 两个 firehose 文件）。
  （①–⑦ ✅、⑧ 待上机），真机验证排在 ADSP PAS1 之后。
- P-205 + ★36 第 7 条：README 的日期、编号、门禁点名必须与 STATUS /
  HARD-RULES / PITFALLS / build-strict.sh 可对账，新门禁 `scripts/check-readme.py`。

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

## GPU / Metal 历史样本（2026-11-13；后续证据以文首现状为准）

> 以下是该次镜像的观察及当时假设，不代表所有后续镜像。后续已有六文件部署成功记录，也有 `pong_metal=1` 的 backboardd 失败；不能由一次发布成功推断崩溃已根治，不能由当时缺文件推断今天仍缺。

三条来自 `E:\k60-work\evidence\usblog-20261113-055021\console.log`：

```
616: PONG METAL: real IOAcceleratorES provider published for20G81 discovery
618: PONG METAL: NativeAdreno complete runtime publication status=0x0
622: PONG ADRENO: startup COMPLETE; hardware armed result=0 a=0x40000007 b=0x20010000
712: Pong init: native Metal entry enabled for backboardd
1557: Pong UI: optional camera-filter GPU prewarm skipped (software-only platform)
```

1. **该样本在 `pong_metal=1` 时发布 provider 并出现 `Early boot complete`。** 这只能修正「永远不能发布/启动」的绝对表述，不能证明所有 backboardd 崩溃都由旧 Data/libSystem 问题造成；后续失败仍需逐镜像核验。
2. **`pong_metal=2` 时那段发布代码根本不会执行**，所以"看不到 Metal"曾长期被误读
   为失败；实际是 `PongAdrenoNativeGlue.cpp:43-49` 只在 `metal==1` 时调用
   `PongAdrenoPublishMetalAccelerator()`。
3. **该样本用户态仍判定为 software-only**（第 1557 行）。当时文件部署不全是候选原因，尚不能排除内核/接口路径：
   日志里 `K60METALPLUGIN deploy bytes=94928` 只有 bundle 的**可执行文件**，
   缺 `Info.plist`、`PongAdrenoMetal.publish`、`PongAdrenoMetal.clients`，
   以及 `PongMetalBridge.dylib`、`libvulkan_freedreno.dylib`。`PongMetalPlugin.mm:191-200`
   要求 `.publish` 内容为 `1`、属主 uid 0、组与其他位不可写，否则
   `selectedClient()` 会返回 false；这是需要验证的部署前置条件，不能单独证明 software-only 的全部原因。

缺失清单与体积：`Info.plist` 695 B、`PongAdrenoMetal.publish` 2 B、
`PongAdrenoMetal.clients` 数十字节（这三项极小，可用内核 blob 方式部署）；
`PongMetalBridge.dylib` ≈33 MB、`libvulkan_freedreno.dylib` ≈18 MB（必须走
文件系统，不可能做成 C 数组）。

## 2026-11-18 GPU 逐行搬运实测：比纹理慢 14.6 ms，`submit` 与搬运形状无关

- `gpu-stride-20261118`（`usblog-20261118-181618`，295,620 B）判 **FAIL**，唯一失败项是 S6：
  逐行搬运下 `submit` 中位数 11,483 µs，未达 ≤6,000 µs。
- 与 `gpu-import-scope2` 逐项对照：`encode` 389 → 15,040 µs、`copy` 23.0 → 37.6 ms，
  而 `submit` 11,478 → 11,483 µs。**删掉每帧纹理让每帧慢 14.6 ms**，纹理路径已恢复；
  3,200 条命令各要 ~4.7 µs 编码，是真正的成本所在（P-235）。
- `submit` 在两种完全不同的搬运形状下只差 5 µs，加上 45 样本的 `r(submit,gpu)=0.007`，
  判定它是翻译层每次提交的固定 CPU 开销；下一步进 `commit_now`/`submit_batch` 打点，
  不再在外层调搬运形状。
- 帧率 7.04 fps（669 帧 / 95 s），与 `present()` 的单帧 23–37 ms 同量级；
  距 120 fps（≤8.3 ms/帧）还差一个数量级。

## 2026-11-18 GPU 帧路径：成本被定位到 `presenter->present()`，采样节奏教训记入 P-233

两次上机都是 Lead 自己飞的，只 `fastboot boot`，没有写过分区。

**第一飞 `gpu-stages-20261118`（证据 `usblog-20261118-135714`）** 把官方文档
`/zh/porting/gpu` 的七阶段拆成两段可读计时：内核侧 `PONG SCANOUT: frame=N prepare=…
offer_and_copy=… total=…`、渲染线程侧 `last frame: wait=… copy=… done=…`。实测
`prepare` 4–12 µs、`offer_and_copy` 13,296–37,320 µs、`copy` 16,813–19,833 µs、`done` 38–55 µs
⇒ 成本全在 `presenter->present()`（F6），锁页与 offer 交接都被排除。18.4 MB / 16.8 ms ≈ 1.1 GB/s，
远低于 A730 blit 的预期带宽。

**同日修掉三个问题**（`38b44bed`）：①`_k60Us()` 的跨整秒负数强转会把 17 ms 算成小时级，
换成带借位的 `PongScanoutTiming.h` 并用 `test-scanout-timing.py` 真编译执行 11 例；
②`report()` 的 256 字节缓冲把整行尾部连同换行一起截掉，改成 768 字节且强制换行；
③跨帧复用导入会让 GPU 读已 `release` 的映射（`PongAdrenoScanout.cpp:195-196` 每帧释放），
缓存整体删除，改为每帧在 `present()` 内导入一次（`test-presenter-import-scope.py` 13 例钉住）。

**第二飞 `gpu-import-scope-20261118`（`boot.img 111851fa…`，证据 `usblog-20261118-161936`）**
抓取完整（231,325 B / 3,400 行）、`K60KEXC` 0、`actual GPU scanout copy completed` 2 次，
但**一条阶段样本都没有**：报告行每 60 帧一条，而这次玩家态只有
`MiniIOMobileFramebuffer: 22 frames in 54713 ms`。判据与采样节奏没有一起设计 ⇒ **P-233**。
采样改为「前 8 帧每帧一条、之后每 10 帧一条」，`FLIGHT-CARD-20261118k.md` 是按新节奏写的卡，
镜像 `gpu-import-scope2-20261118`（`boot.img f67c4983…`）已构建、`verify-boot-image: OK`、
卡片门禁 ✅ —— **等设备回到 fastboot 才能飞**。

当前里程碑：首帧（软件合成）已成立、Metal 出帧（`c>0`）已成立、**帧率仍只有 0.4–7.8 fps**，
120 fps 与跟手远未达成。下一步按 k 卡的 F6/F7 分支决定：`gpu` 占 `sum` 的 0.8 以上 ⇒ 转
Turnip 渲染模式（本机被 `PongMetalPlugin.mm:136` 强制 `TU_DEBUG=sysmem,nocb`，官方默认 `gmem,nocb`）；
`encode`+`submit` 占 0.6 以上 ⇒ 转命令提交的批量/复用。

**第三飞 `gpu-import-scope2-20261118`（`boot.img f67c4983…`，证据 `usblog-20261118-171507`）** 判决 PASS：
54 条阶段样本，S1–S8 全过（`K60KEXC` 0、backboardd 崩 0、中位 `copy` 23.0 ms、`imports==frames` 54/54）。
归因第一次是**量出来的**而不是推的：45 条稳态样本里 `import` 0.2 %、`encode` 1.9 %、
**`submit` 49.6 %、`gpu` 45.9 %**，`sum` 与 `copy` 中位只差 +1.8 %。

两个结论由此而定：

1. **删掉跨帧导入缓存没有代价**（每帧重导入中位 54 µs）——那条缓存本来只是为了性能，现在理由彻底消失。
2. **`commit` 不是等 GPU**：`pearson r(submit, gpu) = 0.007`、`r(submit, 上一帧 gpu) = 0.088`，
   极差 0.05–4.99 也说明它不跟随 GPU。所以 8–11 ms 的 `submit` 是翻译层里的 CPU 工作。

同一飞暴露一个测量缺陷并记为 **P-234**：`wait/copy/done` 打印时除以 1000 却仍标 `us`，
外层看起来比内层小一千倍；若照字面读会得到「copy 已经免费」的反向结论。

下一张 `gpu-stride-20261118`（卡 `FLIGHT-CARD-20261118l.md`）只回答一个问题：
这条拷贝是整段一次还是逐行 3200 次？它同时删掉线性纹理分支——那条分支会让翻译层每帧
建一个 Vulkan image 并分配内存，正是「CPU 侧 per-frame 开销」最可能的形状。
若本来就已是整段，则纹理分支从来不是成本，下一步转去翻译层内部测量 `commit_now`。

当前里程碑：首帧（软件合成）已成立、Metal 出帧（`c>0`）已成立、**帧率仍只有 3.1 fps**（样本区间
469 帧 / 150 s），而 `present()` 只占 23 ms（理论上限 43 fps）⇒ 帧路径之外还有别的瓶颈，
120 fps 与跟手远未达成。
