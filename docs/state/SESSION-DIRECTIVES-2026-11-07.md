# 会话指令与事实总账（2026-11-07）

> 用途：把用户在本会话中下达的**全部指令、纠正、事实结论**固化。上下文压缩后以本文件为准。
> 维护规则：用户新增/纠正一条 → 本文件追加一节；不允许只存在于对话里。

## 0. 铁则（已写入各仓 `AGENTS.md`，此处为摘要）

1. **非临时文件不许放 `/tmp`。** 补丁、`series`、构建脚本、笔记、被结果引用的产物 → 仓库或 `E:\k60-work`。
2. **源码必须先纳入 git 并 push，再进入下一步。** 只在临时 worktree 里的工作等于没做。
3. **遇到问题先查 `UniXNU-pong` 的解决方案，禁止在没调研该仓库的情况下瞎猜瞎搞。** 方案必须给出 `文件:行号`，或明确声明"没找到先行实现"。

## 1. 找文件的协议（用户 2026-11-07 明确）

> "所有你认为遗漏的文件都可以在 `D:\Android`、E 盘、F 盘以及 WSL 内各种地方找；如果找不到才是真的被清掉了。"

**顺序**：
1. `D:\Android`（含 `D:\Android\k60-ios`、`deliverables/`、`config/`、`archive/`）
2. `E:`（`E:\hackios`、`E:\k60-work`、`E:\k60-archive`）
3. `F:`（`F:\k60-archive`，含 `dtb/`）
4. WSL 内部（`/tmp`、`/opt`、`/home`）

**血泪教训（本会话三次误判"文件丢了"）**：
- 用 **MSYS 的 `/tmp`** 去看 **WSL 的 `/tmp`** → 误判 `k60build`/`usb-cdc-mainline`/IPSW 全丢。**MSYS `/tmp` ≠ WSL `/tmp`**；查 WSL 必须 `wsl -u root -e bash -c ...`。
- 误判 dtbo 丢失 → 实际在 `F:/k60-archive/dtb/`（65 个文件，含 `dtbo_a_fdt15.dtb` 752,562 B、`dtbo_a_fdt19.dtb` 509,088 B）。
- 误判 IPSW 分量丢失 → 实际在 `E:/hackios/UniXNU/out/ipsw/20G81/`：`096-57366-083.dmg`(4,250,815,697 B=OS 窗口)、`096-56782-083.dmg`(2,665,480,192 B=裸 APFS SystemOS)、`kernelcache.decompressed`(48,644,096 B)，合计 6.5 GB。

**结论**：宣布"文件丢失"之前，必须在上述四个位置都搜过，并记录搜索命令与结果。

## 2. 参照对象：pong 的 **ios16 分支**（不是 main）

- `UniXNU-pong` = **Nothing Phone (2)，SM8475**，iOS 16.6.1 / 20G81 —— 与我们同 SoC、同 OS 版本；README 明确写「**曾进入 iOS 主界面**」。
- 读取方式：`git -C E:/hackios/UniXNU-pong show FETCH_HEAD:<路径>`（`ios16` 已 fetch 为 `FETCH_HEAD`）。
- pong 的 **main 分支是 iPadOS 18（22H374）**，方案不同（App cryptex 装进 OS：`install_app_cryptex()`）；**ios16 分支才是我们的同款**（`source_path` 对 App cryptex 返回 `None`，注释就是 `no matching 20G81 App cryptex in this port yet`）。

## 3. 三层对比结论（机械 diff，均已实测）

| 层 | 结果 |
|---|---|
| `userland/` | **14/14 文件与 pong16 完全相同**；`build.py` 字节一致（558 行，`prepare()` 394、`apply()` 449） |
| `drivers/` | **156 文件清单零差异**；`PongAdreno` 103 文件同码；4 个文件内容不同（`DarwinBoot.c`、`NativeUfs.cpp`、`PongUfsTransport.cpp`、`RootLayout.h`） |
| 内核补丁 | pong16 有 **103** 个，我们仓库**全部都有**；我们另有 52 个自有；`series` 原 129 条 |
| `scripts/` | pong 42 个一个不缺，另有 36 个自有，12 个同名内容不同 |
| `board.toml` | pong 54 行、**无 `[userdata]`/`[windows]`**（内存/窗口在 ADT 生成器与 UEFI 侧）；我们 162 行、`[userdata]` 31-35、`windows` 35 |

## 4. 窗口模型（`unixnu` 分区）——不能整分区 flash

```
/dev/block/by-name/unixnu      真 GPT 分区，LBA 53342976..61731583（32 GiB，4 KiB 扇区）
├─ [0, 4096)   SHNGROOT 目录（自定义头）
│     "SHNGROOT" + <IIQ: version,count,total> + 128 B/条 <32sQQII: name,offset,len,blockBytes,flags>
├─ OS 窗口       GPT+APFS 磁盘镜像（512 处 "EFI PART"）
├─ SystemOS 窗口 同上
└─ Data 窗口     内核 K60DATA 直接映射（`/dev/disk5s1`，bytes=0x4f8200000）
```

- 来源：`scripts/install-k60-ufs-data.py:22-28`（常量）、`:104-120`（解析）、`:60-64`（要求窗口是 GPT）。
- **写入方式**：`dd if=... of=/dev/block/by-name/unixnu bs=4096 seek=$((53342976+OS_offset/4096)) count=$((OS_len/4096)) conv=notrunc,fsync`；**SHNGROOT 不动**（我们的记录格式无 sha256）。
- pong16 的写入脚本同样要求 **recovery ADB + 分区未挂载**（`scripts/install-pong-ufs-data.py:4-6,55-57,71`）。

## 5. 本地 APFS 能力：只有"读"

- `tools/apfs/apfs.py`（1242 行）+ `dmg.py`：纯 Python、**0 个写函数**；`open_image()` 嗅探 DMG/GPT/裸容器；命令只有 `info/ls/tree/cat/stat`。
- `read-data-volume.py` 的 `DevImage`：`adb exec-out dd if=/dev/block/sda bs=4096 skip=<blk> count=1`，带重试/缓存，越界拒绝。
- **TWRP 里没有 APFS 读写工具**（用户确认）。
- 因此 OS 窗口的正确改法是 **macOS（GitHub Actions `macos-*`）跑 `userland/build.py prepare` + `apply`**（`hdiutil attach`），产出 `pong-ios1661-system.cdr`，再 recovery adb dd 写入窗口。

## 6. 触摸（K60 = Goodix on GENI SPI）

**权威参数**（`D:/Android/k60-ios/AGENT-COORDINATION.md:1379`，设备 adb 6033dbec 实测）：
- 总线：**GENI SPI `spi@990000`（=SE4）、CS0、15 MHz**
- 引脚：**IRQ = GPIO 21、RESET = GPIO 20、AVDD = GPIO 71**
- 固件：`goodix_firmware_m11a`
- 坐标：**10× 面板 = 14400 × 32000**（面板 1440×3200）

**与 pong 驱动断言的关系**（`patches/xnu/zzzz…-pong-touch-console.patch`）：
- DT 节点：`/arm-io/pong-touch`；属性 9 个：`spi-base/tlmm-base/gcc-base/rsc-base/cmd-db-base/gpio-offset/pins[6]/max-x/max-y`（`:58-62`）
- 断言：`se_phys==0x990000`、`tlmm_phys==0xf000000`、`gcc_phys==0x100000`、`rsc_phys==0x17a20000`、`cmd_db_phys==0x80860000`、`gpio_offset==0x100000`、`pins=16,17,18,19,21,20`、`max_x==1080`、`max_y==2412`（`:63-65`）
- `PIN_INT=pins[4]=21`、`PIN_RESET=pins[5]=20`（`:109-110`）；GENI **SE4**（`GCC_QUP0_SE4_DFSR = gcc+0x274f8`，`:294`）
- **相同项**：`spi-base 0x990000`、INT 21、RESET 20、SE4 ✅
- **必须改**：`max_x/max_y` → 14400/32000；`avdd` → GPIO71（对应 `pins[0..3]` 语义待核）；固件名 `goodix_firmware_m11a`
- **未核实**：`rsc-base 0x17a20000` 对 K60 是否可用（K60 曾 **RSC `0x17a00000` 访问死**，见 `docs/ROUTE-A-18-DELTAS.md:13-15`）；`cmd-db/gcc` 是否 SM8475 常量

**禁止**：抄 sweet 的 GT9896 常量（`0x5d`、SE `0xa84000`）——那是 Redmi Note 10 Pro（SM7150）。
**sweet 的 K60 触摸补丁（0240-0252）是失败记录**，作者自述触摸未修好；只作"踩过什么"的证据（尤其 `0246-skip-rpmh`、`0248-rsc-address-probe`、`0252-先 ml_io_map 再读 TCS`）。

## 7. 120Hz

- **真面板 = `qcom,mdss_dsi_m11a_42_02_0a_dsc_cmd`**（`F:/k60-archive/dtb/dtbo_a_fdt19.dtb` 二进制 grep 命中 4 次；`dtbo_a_fdt15.dtb` 命中 0 次）。
- `K60-120HZ-PLAN.md` 的面板数据取自 **通用参考面板 `sharp_qhd_plus_dsc_cmd`（fdt15）** → **已证伪，禁止使用其 `0xC6` 切档序列**（依据 `D:/Android/k60-ios/deliverables/ZCODE-RESEARCH-REPORT.md:396` U6-C5）。
- 真面板 **三档 60/90/120**：`timing@0`=60Hz（DCS `0x2F=0x02`）、`timing@1`=90Hz（`0x2F=0x01`）、`timing@2`=120Hz（`0x2F=0x00`）；三档 **phy-timings 与 clockrate `0x47868C00`(1.2 GHz) 逐字节相同**（`ZCODE:384` U6-C4）。
- 内核侧 `fb_hz=N`(1..240) 只改 **CoreAnimation 节拍**（TimingElements/vsync/present，`MiniIOMobileFramebuffer.cpp:158/327/879/1172`），**不改面板扫描率**。
- **真 120Hz 需要新增 DSI host/PHY/PLL 驱动——当前完全缺失**；前置是 GPU scanout 生效。
- 验收分级：S 级（mfb 5 秒行/`reportFrameTimes`）只证明"CA 以为 120"；**H 级必须读 INTF 帧计数 ≈120.2/s**；V 级 Dock 滑动无 33/33/17 抖动。

## 8. GPU

- 驱动与我们**同码**（`drivers/PongAdreno` 103 文件、`NativeMetal`/`PongMetal`/`ArmSmmu4K` 全同）。
- 我们主动关掉了 GPU：`patches/xnu/0231-k60-accel-stub-adreno-gate.patch` 把 `MiniAcceleratorPublishStub(provider)` 包进 `#if XNU_K60_ACCEL_STUB` → 只发布 stub，走软件 framebuffer。
- 按 pong 开启需要：去掉该门 + 启用 `pong-gpu-scanout`、`pong-gpu-only-display`、`pong-source-row-pitch`、`pong-union-lower-directory`、`zzy-native-gpu-addon-mount`、`offline-native-gpu-broker`（均属"有文件未启用"）。
- 判据日志：`PONG SCANOUT: actual framebuffer handoff available`、`GPU frame completed`；决定性实验：`pong_gpu_only=1` 下屏幕仍刷新且无 `PONG GPU ONLY: no completed GPU frame`。

## 9. 内存（用户目标：12 GB 全部可用）

- pong 的模型（`scripts/make-pong-adt.py:23,110,155-156`）：`DRAM_BASE = 0x80000000`；`--dram-size` 写入 `chosen.dram-size`（给 XNU 看的总量）；另有 **`darwinboot-memory-size`**（UEFI 实际交给 XNU 的 arena），由 `scripts/pong_adt_contract.py:136` 校验。**两者独立**。
- 我们现状：`board.toml:98 dram_size = "0x140000000"`（5 GiB）、`:162 owned_memory_size = "0x130000000"`（4.75 GiB）；`dts/mondrian.dts:29-32` 只有一段 `memory@900000000 { reg = <0x9 0 0x1 0x40000000> }`（5 GiB）。
- 真机 `/memory/reg` 六段（`docs/MEASURED-HIGH-WINDOW-2026-11-02.md:41-51`）：`0x80000000/0x6a000000`、`0xf4600000/0xba00000`、`0x800000000/0x37500000`、`0x900000000/0x180000000`、`0x840000000/0xc0000000`、`0x837b00000/0x1e00000`；**`[0x100000000,0x800000000)` 是空洞，无 RAM**。
- 该文档明确否掉两件事：手写 `base=0x80000000,size=12 GiB` **不是**硬件实测；`swinfo.fingerprint=mondrian:12` **不是**可靠 SKU 证据。**它与 `AGENT-COORDINATION.md:1778/1792` 的"12 GiB 硬件实测"说法冲突——冲突未解（见 TRUST-LEDGER T1）**。
- 达到 12 GB 的路径（按该文档）：①修回被截断的 `Platforms/Xiaomi/mondrianPkg/Library/MemoryMapLib/MemoryMapLib.c`（恢复全部低内存描述符，`git HEAD e06211de`）；②**只加一个 arena** `[0x900000000,0xa40000000)`（5 GiB）做首个实验；③验证 XNU 能看到后再逐级放大；④不要盲目照搬 pong 的 HYP 保留区；⑤`dram-size` 与 `darwinboot-memory-size` 必须分别设置，不能只改一个。

## 10. 实体键：UEFI 与 iOS 的关系

- UEFI 侧驱动：`uefi-mondrian/Binaries/<device>/QcomPkg/Drivers/{ButtonsDxe,SPMDxe→SPMIDxe,PmicDxeLa}`（408 个相关文件）。
- **硬件同源**（PMIC PON 的 KPDPWR/RESIN + PMIC GPIO），**代码无关**（DXE 协议栈 vs XNU 直接 MMIO）。
- UEFI 驱动是**参数证据源**：K60 PON 在 `periph 0x13`；音量加在 `pm8350@1 pinctrl@8800` 的 **GPIO6 = 0x8d00**、第三项 `1` = ACTIVE_LOW（sweet `NOTES.md` 记录）。
- iOS 侧按 pong 的 `pong-physical-keys.patch` 结构 + 上述参数实现。

## 11. 内核补丁：不能按 pong 的字母序全量应用

`docs/PONG16-DIFF-AUDIT.md`（commit `6005f7c`，482 行）实测：
- 按 pong 字母序应用我们 155 个 → **111 clean / 14 fuzz / 30 FAIL**；真实脚本**第 1 个补丁就 exit 1**（`0210` 的目标文件由第 115 位的 `ui-foundation` 创建）。
- 依赖链：`0211/0212/0213/0231/0233/0235` 同因；`0243` 依赖 `ramoops-minimal`(94)；`0240/0301` 依赖 `userland-abi`(98)。
- 显示同函数重叠：`0210:37` vs `pong-gpu-scanout:14`（都改 `IOMobileFramebuffer::start`）；`0213:14` vs `pong-gpu-only-display:28`（都改 `publishModes`）；`0211:5` vs `gpu-only-display:3`（都改 `native_pong_ui_services_start`）。
- 挂载区重叠：`0302:108/117` vs `pong-ufs-data:56`；`0303:88`/`0239:3` vs `zzyb:165`；`writable:41` vs `zzy:88` —— 全在 `native_owner_data_prepare()`，爆炸半径是 root/Data 挂载。
- **结论**：保留 format-2 `series`；pong 新补丁只能**追加在创建者之后**或 `series` 末尾；启用 GPU 补丁前先重做 `0210/0213/0211`。

## 12. 今天已恢复/已入库的东西

- WSL `/tmp/usb-cdc-mainline/device/patches/xnu/` 里 **0384–0390 全部存在**（含 `0390-k60-cryptex-app-access.patch`）。
- 已复制到 `E:/hackios/UniXNU-mondrian/patches/xnu/` 并补进 `series`：**0384 pid_hibernate、0385 AKS 93/34、0386 exec 探针守卫、0387 panic args、0388 n4k cache I/O、0389 KXPC**。
- **0390 不启用**：它是"对 `/System/Cryptexes/App` 的 access 假成功"，属自创路线，Pong 没有此做法（铁则 3）。
- 构建环境（WSL 侧）**仍然完整**：`/opt/unixnu-linux`、`/tmp/k60build`、`/tmp/usb-cdc-mainline`。

## 13. 文档可信度纪律

- 所有决定实现的数值必须先在 `docs/TRUST-LEDGER.md` 登记（出处/冲突/复算方式/状态）。
- 状态只有 `已实测`、`可复算`、`未核实`、`已证伪`；引用未经复算的只能写"未核实"。
- 已证伪/冲突项（截至本文件）：T1 内存 12 GiB 之争、T2 PLAN 面板数据、T3 sweet 触摸常量、T4 pong 字母序全量应用、T5 sweet cryptex hard-link 架构；C1 dtbo、C2 IPSW、C3 真面板。
