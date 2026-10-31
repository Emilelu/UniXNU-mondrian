# Route A-18 交接全文（2026-11-01）

> 本文承接 `HANDOFF-2026-10-31.md`（darwin22 时代）之后的所有工作。
> **阅读顺序**：本文 → `ROUTE-A-18-STATE.md` → `PONG-FEASIBILITY.md` → `HANDOFF-2026-10-31.md`（历史）。

---

## 0. 一句话现状

**darwin22（16.6.1）已经解决掉所有影响启动的内核 panic，但卡在用户态 sig=9 风暴；
现按用户决定整体切换到 darwin24（18.7.10 / 22H374 / xnu-11417）。内核在 Linux 上可完整构建，
已排除三层启动阻断，目前卡在"loader 跳板已执行（屏幕出现绿条）→ 内核进入后静默复位"。**

---

## 1. 为什么离开 darwin22（不要回头重查）

darwin22 已经做到：8 核启动到 launchd、服务链拉起 SpringBoard、`/private/var` 读写挂载、
keybag 通过、watchdogd 禁用、**屏幕出现 iOS 启动进度条**。

**无法解决的那一个**：约 98% 守护进程以 signal 9 异常退出（sig=9 风暴）。已排除：

| 假设 | 补丁 | 结果 |
|---|---|---|
| 无条件 Sandbox 策略拒绝 | `0240` | 风暴未停 |
| 启动约束（LaunchConstraint）拒绝 | `0241`（`k60-no-lc=1`） | 风暴未停 |

用户明确表态："问题依旧 不走16.6.1了"。**该分支已关闭，不要回去。**

---

## 2. 为什么选 pong（Route A-18 的依据）

`UniXNU-pong` 是 **同一颗 SM8475**（A730 GPU / QCA6490 / TFA9873 / Goodix Berlin-D 全在），
darwin24 = iPadOS 18.7.10 / 22H374 / xnu-11417.140.69。

**证据强度的诚实说明**：pong 的 `porting.toml` 有 13 条 `kind="source"`、0 条 host、0 条 device，
`migration-state.json` 里 `image_hashes_used: false`。**也就是说 pong 的 darwin24 从未提供过
可复现的实机证据。** 不要把 pong 的"能跑"当成事实——本项目的 bug 可能就是 pong 自己的 bug。

**架构决策**：不采用 pong 的构建系统（仅 macOS，`build-ipados18.py` 用 `xcrun`，CI 是
`macos-15-intel`）。只采用 pong 的**内核源码与驱动**，送进我们自己的 K60 流水线
（ADT / prelink / payload / bootimg），该流水线已在 16.6.1 上端到端验证过。

---

## 3. 构建环境（全部在 Linux，不需要 macOS）

| 项 | 值 |
|---|---|
| 框架核心 | `/tmp/k60build`，分支 `k60build` |
| 设备仓库 | `~/hackios/UniXNU-mondrian` |
| pong 仓库 | `~/hackios/UniXNU-pong` |
| UEFI 仓库 | `~/hackios/uefi-mondrian` |
| K60 驱动源码 | `/tmp/k60build/pong-driver` |
| 构建树 | `/tmp/k60build/out/route-a18/Pong-iPadOS18-native` |

### 3.1 内核构建（可复现）

```bash
wsl -d Ubuntu-24.04 -- python3 <workspace>/k60-work/route-a18-platform-build.py
```

关键点（踩过的坑，别重犯）：

1. `MACHINE_CONFIGS=PONG`（darwin24 白名单里没有 BCM2837）
2. `PLATFORM=iPhoneOS` 必须显式设置
3. **`LD_KERNEL_ARCHIVES` 会替换默认列表** → 必须显式写 `-L$FAKEROOT/usr/local/lib/kernel -lfirehose_kernel`
4. **make 不追踪命令行变量变化** → 改 `LD_KERNEL_ARCHIVES` 后必须先删
   `build/xnu/ios-obj/DEVELOPMENT_ARM64_PONG/mach.development.pong.unstripped.noctf` 才会重新链接。
   这一条坑过一次：sha256 完全没变，误以为链接成功。
5. PGO 符号需 `LD_KERNEL_LIBS=.../libcc_kext.a`

### 3.2 平台驱动归档（关键：曾经完全缺失）

```bash
wsl -d Ubuntu-24.04 -- python3 <workspace>/k60-work/build-k60-platform-archives.py
```
产出 `build/armdt-platform/libArmDTPlatform.a`（27,808 B）与 `build/armcpu/libArmCpu.a`（34,600 B）。

**这两份必须用 `-Wl,-force_load` 链进内核**，否则 `PE_init` 找不到 `IODTPlatformExpert`，
内核没有控制台、loader 报 `0 staged kext(s)`。16.6.1 能显示控制台正是因为它链了这两份。

### 3.3 UEFI FD 构建

```bash
cd ~/hackios/uefi-mondrian && python3 ./build_uefi.py -d mondrian -r DEBUG -c
```

- **不需要 `nasm` / `iasl`**（曾误判为阻塞，实际 AARCH64 平台构建不需要）
- 结尾 `The Device DTB is Missing in "Resources/DTBs"!` 是**无害**的构建后步骤失败，
  硬件 DTB 由 `bootimg` 单独提供
- 产物：`Build/mondrianPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd`

### 3.4 打包与校验

```bash
cd /tmp/k60build
./unixnu bootimg -D ~/hackios/UniXNU-mondrian --uefi ~/hackios/uefi-mondrian \
  --fd ~/hackios/uefi-mondrian/Build/mondrianPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd \
  --dtb <OUT>/device-tree/hardware.dtb \
  --ramdisk <OUT>/payload/payload.img \
  -o /mnt/d/Android/k60-ios/<name>.img
```

`bootimg` 返回 rc=1 且提示 `boot image header does not match the requested parameters`
是**已知误报**，必须用独立哈希校验，见 §5。

---

## 4. 已排除的三层阻断（重要，避免重复劳动）

### 4.1 入口点 — 已排除

darwin24 内核 `LC_UNIXTHREAD` PC = `0xFFFFFFF0074C04A0`，文件偏移 `0x4bc4a0`。
入口字 `140006EF 00000000 00000000 00000000`，`B +0x1bbc` 跳到真实代码
`D510109F D5034FDF AA0003F4 D2800015`。

**我们 darwin22（能启动）的入口字完全一样**；Apple 22H374 只是用 `D503201F`(NOP) 填充、
分支偏移不同，落点同样是 `D510109F...`。→ 入口不是问题。

### 4.2 `boot_args` 结构体（xnu 源码侧）— 已排除

`pexpert/pexpert/arm64/boot.h` 的 `struct boot_args`（13 字段）与 `struct Boot_Video`（6 字段）
在 xnu-8796 与 xnu-11417 **完全相同**。→ 内核侧结构体没变。

### 4.3 `start.s:756` 的 `bne .` 自旋 — 已排除

```asm
MOV64   x0, SCTLR_EL1_DEFAULT
MSR_SCTLR_EL1_X0        // PONG 是 NO_MONITOR=1 → KTRR 关闭 → 仅 msr，不改 x0
isb     sy
MOV64   x1, SCTLR_EL1_DEFAULT
cmp     x0, x1          // 常量与自己比较 → 永远相等
bne     .
```
→ 永远不跳转，不是死循环点。（`start.s:568` 的 `bne .` 由 `tbz w1,#0x1f` 保护，
非 kext 内核会跳过，也不是。）

---

## 5. boot 镜像真实布局（校验时必须知道）

```
偏移 0        ANDROID! 头 (page 4096, kernel_size 548935)
偏移 4096     gzip(UEFI FD)  547,073 B   ← 内含 112 B BootShim 前缀，ARMd 在 +56
偏移 551169   hardware.dtb     1,862 B   （追加在内核区末尾）
偏移 557056   payload.img  201,326,592 B
总计          201,887,744 B
```

校验方法（`verify-shim-fd.py` 已实现）：解 gzip → 去掉前 112 字节 → 必须等于 FD 的 sha256。

---

## 6. ★ Route A-18 的第 2 个根因：`boot_args` ABI（已修复并验证）

**这是最容易被忽略、也最致命的一处。** `uefi-mondrian` 里的
`Platforms/Xiaomi/DarwinBootPkg/Driver/BootArgs.h` 是**我们自己**在 16.6.1 时代改写的
Darwin 22 版本，注释里就写着：

> Handing a Darwin 22 kernel a Darwin 24 layout puts BootFlags and MemorySizeActual
> 0x1a0 bytes past where the kernel reads them, which is an immediate fault on handoff.

| 字段 | Darwin 22（旧，错） | Darwin 24（现在） |
|---|---|---|
| `DARWIN_BOOT_LINE_LENGTH` | 608 | **1024** |
| `BootFlags` 偏移 | `0x2d0` | **`0x470`** |
| `MemorySizeActual` 偏移 | `0x2d8` | **`0x478`** |
| `sizeof` | `0x2e0` | **`0x480`** |

已改并**双重验证**：
- 编译期 `STATIC_ASSERT` 全过
- `DarwinBoot.obj` 内含 `0x480 ×3`、`1024 ×11`；FD 内 `0x2e0` 出现 **0 次**
- FD sha256：`a8a6f79c1d7705d96922c523c63c1cee24988788d29bfc97529e1cdbc67e4d4d`

同批修正：`DarwinBoot.c` 两处打印从 "Darwin 22 ABI" 改为 "Darwin 24 ABI"（只是字符串，
但屏幕上看到 "Darwin 22" 会误导诊断）。

**顺带确认的事实**：`Entry.S` 与 pong 的 `DarwinBoot24` **sha256 完全一致**；
`DarwinBoot.c` 与 pong 的差异只有我们加的 QR 调试行、前缀标签、ABI 字符串。
→ **除 `BootArgs.h` 外，我们的 loader 本来就是 pong 的 DarwinBoot24。**

---

## 7. 当前卡点（下一任从这里开始）

最后一次上机（`boot-darwin24-abi24.img`）现象：

```
… entry words 140006EF 00000000 00000000 00000000
HANDOFF EXIT RETURN 00000000000000803518
owned trampoline pa 0xC84F8000 (196 bytes)
Exiting boot services…
SecurityLock::LockType: SOFTWARE_LOCK … LockCapsuleInterface
```
**+ 屏幕上方出现绿条**（用户确认）。

### 绿条意味着什么

绿条由 `Entry.S` 的 `DarwinEnter` 绘制，位置在关 MMU **之前**：

```asm
mrs x4, sctlr_el1
bic x4, x4, #1        // MMU OFF
bic x4, x4, #4        // D-cache OFF
bic x4, x4, #0x1000   // I-cache OFF
msr sctlr_el1, x4
tlbi vmalle1
dsb sy
isb
br x1                 // 跳到内核入口的物理地址
```

→ **跳板确实执行了并跳进了内核**（PA `0xC74C04A0`）。阶段从"没进去"推进到"进去了、内核瞬死"。

`HANDOFF EXIT RETURN 0x803518` 是 `ExitBootServices` 的返回码，bit63=0 → `EFI_ERROR` 为假
→ `Enter()` 确实被调用，之后 `CpuDeadLoop()`，然后板子复位。

### 已知的观测盲区（这是最大障碍）

- pong 的驱动栈里**只有 5 个驱动**：`ArmCpu` `ArmDTPlatform` `NativeRamBlock` `NativeUfs` `PongAdreno`
  ——**没有任何视频控制台驱动**
- `pong_display` / `pong_software_ui` 在整个驱动树中**没有读者**（它们是用户态标志，不是控制台开关）
- ramoops 控制台（K60 基址 `0xA7000000`）的 `pong_ramoops_console_init()` 在
  `arm_init()` 里 **`arm_vm_init()` 之后**才跑

→ **`arm_vm_init` 之前/之中的任何死亡都是完全静默的。** 必须先解决"看得见"的问题。

### 尚未排除的最新线索（建议优先查这个）

打包给内核的 FDT **是原始 `hardware.dtb`（1862 B，14 个节点）**，不是
`devicetree.generate()` 生成的 ADT（14,620 B）。

- `unixnu bootimg` 的 `--dtb` 只做 `patch_dtb()`（按 `board.toml [[bootimg.dtb_node]]` 加节点），
  **不会调用 `devicetree.generate()`**（已 grep 确认 `scripts/unixnu/` 内无此调用）
- 该 DTB 只有：`/`、`/cpus`、`/cpus/cpu@0..7`、`/psci`、`/interrupt-controller@17100000`、
  `/memory@80000000`、`/ufs@1d84000`
- **缺 `/chosen`、`/arm-io`、`/defaults`、`/options`** —— 而这四个正是
  `ArmDTPlatform.cpp` 头注释里声明 `configure()` 必需的东西：
  > `/chosen` with a CHRP NVRAM proxy (nvram-bank-size, nvram-proxy-data)
  > `/options`, `/cpus`, `/arm-io` and `/defaults` … absent inputs make configure() fail
- payload 里 `adt_sha256 = 78f8ecd0528185818164eb8c93588fc5ba3ae4a25f29ee56be293e4d18b73bd0`
  但 `payload/adt.bin`、`device-tree/adt.bin` **都不存在**

`adt-generate2.py` 已能生成 14,620 B 的 ADT（注意：该 blob 头部 magic 是 `0x06000000`，
是**容器格式**，内部才嵌 FDT；`adt-walk.py` 假设裸 FDT 会报 `not an FDT`，需要先修）。

---

## 8. 下一步建议（按优先级）

1. **先解决可观测性**，不要再盲刷：
   - 在 `start.s` 的 `_start` 里加**不依赖 MMU 的面包屑**：`mov x20, x0` 之后、
     开 MMU 之前各画一条色条到 framebuffer（`x20` 是 boot_args PA，`Video[]` 在 +0x28，
     `v_rowBytes` 在 +0x38）。XNU 的 bootstrap 页表含 **V=P 块映射**，所以开 MMU 之后
     用 PA 写 framebuffer 仍然有效。
   - 或在 `arm_init()` 最开头、`arm_vm_init()` 之前，直接往 PA `0xA7000000` 写标记字，
     之后从 Android root 用 `dd if=/dev/mem` 读回（设备已在 Android 时零成本）。
2. **核对 FDT**：确认内核实际需要的是 `hardware.dtb` 还是生成的 ADT；若是后者，
   需要把 ADT 送进 `bootimg`（或让 `bootimg` 调用 `devicetree.generate()`）。
3. 若内核已越过 `arm_vm_init` → 读 ramoops carveout，看 `PONG DIAGNOSTIC v92` 是否出现。
4. 再往后：22H374 trust cache 转换（仍用 20G81 的 `344ae644…`）、DarwinBoot24 UEFI 若需要。

---

## 9. 硬约束（违反会变砖）

- **只 `fastboot boot`，绝不 `fastboot flash boot`**（boot 分区属 Android，会毁双系统）
- **绝不 `fastboot flash persist`**（TEE 会 `deleteAllKeys`，密钥永久失效）
- 允许写 `unixnu` 分区；禁止碰 `persist` / `modemst*` / Android `userdata`
- 设备串号 `6033dbec`
- 一次只改一个变量，并说明改动量
- 提交按文件拆分，**绝不 `git add -A`**；`mac-build/` 保持未跟踪
- 每个 push 的仓库，README 要及时跟进更新

---

## 10. 关键产物清单（截至 2026-11-01）

| 产物 | 大小 | sha256 |
|---|---|---|
| darwin24 内核 `mach.development.pong.unstripped.noctf` | 20,872,376 | `2f485593b3f7c2d35657f14d5e2e5804ca434fbf56df6f275c0802bf32a7e5cd` |
| payload.img | 201,326,592 | `632cb82961ab2ecd82c1e36a97a284ecd9ceec3e012078867450cb670ea20728` |
| UEFI FD（ABI 修复 + 标签） | 3,145,728 | `a8a6f79c1d7705d96922c523c63c1cee24988788d29bfc97529e1cdbc67e4d4d` |
| `boot-darwin24-abi24.img`（**已刷，出绿条**） | 201,887,744 | `c249c547e6999a2722b5884733bda98af9c0d5a719ab575e4e921465df8c338a` |
| `boot-darwin24-abi24b.img`（已构建，未刷） | 201,887,744 | `6796e1479e5c5cd83fa37998b573d394e6b2b7a44ff2083353a153b9d04b35e0` |
| `libArmDTPlatform.a` | 27,808 | — |
| `libArmCpu.a` | 34,600 | — |
| 22H374 kernelcache（解压后） | 48,562,204 | `7f730f49240b76ca4b5938b152479cba1b729ac4c188e233e73665394f04ba43` |

设备仓库已提交：`3e23d1d`、`e24207d`、`b38621f`、`1c674d4`、`31f68da`（分支 `route-a-18`）。
