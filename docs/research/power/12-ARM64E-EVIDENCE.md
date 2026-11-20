# arm64e 五条硬性要求的离线证据（2026-11-20）

本文只做离线核对：没有构建，没有上机。判据是 `docs/zh/porting/arm64e.md:16-22` 的五条要求，
数字是本仓已经记下来的那一次捕获。结论：**五条没有一条完整闭合**——第 1 条有一个核的原始值、
按页面的成对规则已经满足，但另外七个核没读、镜像没有哈希；第 5 条只有构建常量；第 2、3、4 条是空的。

## 1. 五条要求的现状

| # | 要求（`arm64e.md:16-22`） | 等级 | 现有依据 | 还缺什么 |
| --- | --- | --- | --- | --- |
| 1 | 每个启用的 CPU 实现 FEAT_PAuth，地址密钥与通用密钥都在 | 单核原始值 | `docs/engineering/IOS27.md:252` 的 F0 捕获：`ISAR1=0x0010011101211052, ISAR2=0`；解码见 §2（APA=5、API=0、GPA=1、GPI=0） | 其余 7 核各一次读数；带镜像哈希的复跑（P0） |
| 2 | XNU 在 EL1 写五组密钥寄存器不陷入 | 未测 | 只有代码路径：`native-pac-keys.patch` 的 `PAC_INIT_KEY_STATE`（§3.4） | P1 |
| 3 | PAC 指令在 EL1 和 EL0 不陷入，每核 PACIA 改指针、AUTIA 还原 | 未测；只有 sheng 的机制旁证 | §3.5 | P2 |
| 4 | SoC 仓库列在官方 SoC 支持页 | 未满足（行政项） | `soc-support.md:126-134` 只把 SM8550 当示例；`arm64e.md:29-31` 的受支持设备表只有 sheng | P3，排在 P0-P2 之后 |
| 5 | 原生 4 KiB 一级翻译 | 构建常量成立，运行期未测 | `porting.toml` 的 granules 证据；`scripts/check-ios27-granules.sh:35-40` | 运行期 TCR_EL1 的 TG0/TG1（P4） |

等级只有三档：单核原始值、构建常量、未测。没有“大概”“应该”。

## 2. 第 1 条：那串数字说了什么

2026-11-18 的 F0 捕获记在 `docs/engineering/IOS27.md:245-255`：原始值是
`ISAR1=0x0010011101211052`、`ISAR2=0`，探针随后打印 `RESULT no FEAT_PAuth`。
`porting.toml` 的 limits 只留了 `ISAR1 APA=0b0101` 一句，没有原值。字段偏移以
`E:/hackios/xnu-12377/osfmk/arm64/proc_reg.h:3139-3167` 为准（GPA=24、GPI=28、FCMA=16、
JSCVT=12、API=8、APA=4）：

| 字段 | 位 | 本值 | 说明 |
| --- | --- | --- | --- |
| APA | [7:4] | 0b0101 | 地址组：FPACCOMBINE（PAuth + FPAC） |
| API | [11:8] | 0b0000 | 地址组第二种编码为 0 |
| GPA | [27:24] | 0b0001 | 通用组非零 |
| GPI | [31:28] | 0b0000 | 通用组第二种编码为 0 |

页面第 1 条是**成对**规则，不是四个字段都要非零：地址组 `APA` **或** `API` 非零
（ISAR2 的 `APA3` 是另一条路），通用组 `GPA` **或** `GPI` 非零（`GPA3` 同理）。
本值 `(APA|API)=5`、`(GPA|GPI)=1`，两组都非零，所以**被读到的那一个核**满足第 1 条。
`ISAR2=0` 只说明 APA3/GPA3 那条路不存在，不影响结论。

两处解码错误要一起改掉：

- `0b0101` 不是“PAuth + EPAC + PAuth2”。同一个半字节只能有一个编码：APA 与 API 共用
  ARM 的一张表（`proc_reg.h:3159-3167` 只给 API 建了枚举，APA 只有掩码），其中
  `1=PAuth、3=PAuth2、4=FPAC、5=FPACCOMBINE`，EPAC 是 `0b0010`。所以 `0b0101` 是
  FPACCOMBINE——PAuth 与 FPAC 合并，既不是 EPAC，也不是三者相加；旧稿把三个编码叠在
  一个值上，任何 ISA 编码都不这么写。
- `API=0` 不是“通用密钥指令（PACGA）不在”。页面的配对是 `(APA|API)` 对 `(GPA|GPI)`，
  API 属于**地址组**；通用组由 `GPA=1` 满足。把 API 说成 PACGA 会把它挪进通用组，
  于是“API=0 所以通用密钥缺失”看起来成立，实际两组都不缺。

探针的判词条件 `apa && api && gpa && gpi` 有两处错：要求 API 非零（页面允许它为 0），
以及把 GPA/GPI 读成 `[15:12]/[19:16]`——那是 JSCVT/FCMA。那次捕获的 GPA/GPI 行
因此不是测量值，只有 ISAR1 原值可用；原值按 §2 解出 GPA=1、GPI=0（与 `IOS27.md:253`
录的数值一致，但探针当时读的不是这两个字段）。`RESULT no FEAT_PAuth` 是判词 bug，
**只能引原始数字，不能引那行判词**。修复补丁见 §3.3。

这次捕获还有三个限制：

1. 镜像没有记录哈希（`IOS27.md:247-249`），`porting.toml` 的 limits 还写明“no capture
   from this branch's build”，所以它是一次观察，不是可复现测量。
2. 只读了 ID 寄存器，没有密钥寄存器与 PACIA/AUTIA 的步骤，第 2、3 条仍是空白。
3. 只读了一个核。ID 寄存器按 PE 实现，异构核不保证相同；页面要求“每个启用的 CPU”，
   8 个核要有 8 行（MPIDR + 两个原值）。

## 3. 为什么现有日志补不上第 2、3、5 条

### 3.1 16.6.1 那条线不是 arm64e，但它确实是 4 KiB

`ipados-16.6.1-20G81` 的 profile 没有 `[os] arch`（`E:/hackios/UniXNU/profiles/os/ipados-16.6.1-20G81/profile.toml:1-9`），
按 `arm64e.md:40` 走 `profiles/arch/arm64`，内核是 8796。

页大小要说清：8796 上游是 16 KiB；本仓 16.6.1 的 series 自 2026-11-08（`6dcb7da0`）起用
`patches/xnu/series:19-21` 的三个 `native-4k-*` 补丁把它改成 4 KiB（`IOS27.md:73-83`），
`boot-proven-20261113` 与 2026-11-14 的触摸启动都在其后，所以那条线的 SpringBoard 启动
是 4 KiB stage-1 的板上运行。`08-IOS27-POWER-PORT.md:8` 的“16 KiB”是上游基线，不是那次构建。

它证明的是“这颗 SoC 与启动链能做 4 KiB 翻译”；不证明 12377/arm64e 的 pmap 与运行期 TCR。

### 3.2 arm64e 内核只构建过

F1 的内核与 F2 的预链接文件都构建出来了，尺寸与哈希记在 `porting.toml` 的 findings 里，
本文不重复；`mapping_complete=False`（384 个未映射符号）与 `loadable=False` 也在那里。
“内核是 arm64e”与“板子跑过 arm64e”是两件事，后者没有记录。

### 3.3 探针与它的修复补丁

探针本体在 `ios-mondrian` 的 `shim/pac.c`，那个检出不在本机；本仓可引的是
`patches/ios-mondrian/pac-probe-arm64e-gate.patch`（`IOS27.md:270-276`）：它同时改
`shim/pac.c` 与 `docs/PAC_PROBE.md`，判词从 `apa && api && gpa && gpi` 改成
`apa || apa3`，GPA/GPI 改读 `[27:24]/[31:28]`，只在 `ISAR1.API` 非零时才写 `APGA`
（patch:87-111）。

补丁自己的注释仍写着“0b0101 here is PAuth + EPAC + PAuth2”（patch:101-103），
与 §2 的更正冲突：复跑前按 §2 读，不要按那句注释读。镜像哈希仍未记录，
`porting.toml` 的 next_action 只有 `shim/out/shim-boot.img` 这个名字。

### 3.4 第 2 条只有代码路径，没有测量

arm64e profile 的 series 含 `native-pac-keys.patch`
（`E:/hackios/UniXNU/profiles/arch/arm64e/patches/xnu/series`）。它在 `BCM2837.h` 里按
`__arm64e__` 定义 `HAS_APPLE_PAC`/`HAS_NATIVE_PAC`，在 `PAC_INIT_KEY_STATE` 里从
`CNTPCT_EL0` 用 splitmix64 生成 **10 个密钥字**（IA/IB/DA/DB/GA 各 Lo/Hi），第一个 CPU
生成后存进 `native_pac_keys`，后续 CPU 直接装载——所以**每个 CPU 的密钥相同**；
`ml_enable_user_jop_key` 变成返回 0 的空操作（内核与所有进程共用一组，和 `arm64e.md:52-54` 一致）。

这条路径说明“XNU 打算怎么写”，不说明“写进去没有陷入”。要测两件事：`msr APIAKeyLo_EL1`
不产生 `EC=0x18`；`HAS_APPLE_PAC` 让 `SCTLR_EL1_DEFAULT` 带上 `SCTLR_PAC_KEYS_ENABLED`
（`proc_reg.h:624,733-737,754-759`）之后，四个使能位真的变成 1。

XNU 判定 FPAC 用的是 **API** 字段，不是 APA：`commpage.c:509-517` 按 `API >= 3/4/5`
置 `gARM_FEAT_PAuth2`/`FPAC`/`FPACCOMBINE`。本核 API=0，所以内核把地址组当成
“无 FPAC”处理。P2 若看到 `ESR_EC_PAC_FAIL`，那是地址组有 FPAC 而内核特征位没开；
记录即可，不改判据。

### 3.5 sheng 是跨 SoC 的机制证据

sheng 是同一代 12377 内核的板级参考（`docs/research/SOURCES.toml:264-268`）。能引的有三处：

- `E:/k60-work/references/UniXNU-sheng/patches/xnu-12377/zzzz-sheng-ipados27-bringup.patch:1621-1635`：
  `signPointer()` 的 `ptrauth_key_asia`/`asda` 分支调用 `pmap_sign_user_ptr(...)`，并打印
  `sheng-sign: unsignedAddr=... key=... a_key=... result=...`——27 内核在非 Apple SoC 上确实走签名路径。
- `hal/ShengAudioPlugIn.c:9-11` 在 `__has_feature(ptrauth_calls)` 下包含 `<ptrauth.h>`，
  `:92` 用 `ptrauth_strip(signed_symbol, ptrauth_key_function_pointer)` 取函数地址。
- `board.toml:72` 的 `audio_target = "arm64e-apple-ios27.0"`，`:246` 修的是
  `dyld_shared_cache_arm64e.03` 的 text fixup。

sheng 是 SM8550、跑 macOS 27.3 arm64e（`porting.toml` 的 findings），与本板（SM8475、
iOS 27.0.1）不是同一颗 SoC、也不是同一个 OS 产品。它证明“同一代 12377 arm64e 内核会在
非 Apple SoC 上执行签名路径”，**不能**证明 SM8475 的 EL1 能写五组密钥寄存器，也不能替代
每核 PACIA/AUTIA。它是机制旁证，不是本板测量。

## 4. 探针判据

P0–P4 的完整判据（寄存器读写名、期望值/不变式、可区分的失败形状、能证明/不能证明、八核普查与
“Census, not sample”）在 `docs/research/charger/ARM64E-PROBE.md`。这里不再复制判据：两处各写一套
期望值，改一处就会留一处旧的。§1–§3 的捕获、限制与 sheng 旁证仍以本文为准。
## 5. 对电源线意味着什么

1. **任何契约行都不得声称“本板支持 PAC”。** `docs/research/power/HW-CONTRACTS.toml` 的
   `adsp-smc-clobber`（P-255）是唯一相关的因果链：SMCCC 1.x 允许 monitor 破坏 x4–x17，
   只读输入在 asm 之后被当成原值，跨一次 SMC 的活跃值可能留在寄存器里；27 线若先做 PAS
   再写密钥寄存器，写进去的可能是陈旧字。这是“PAC 可能被电源线代码弄坏”的机制说明，
   不是“PAC 已验证”。
2. 电源线现有的 EL1 材料（`K60AdspPas.c` 的 `smc #0`、0629 的睡眠/恢复打印、ArmCpu 的
   PSCI bring-up）只证明 EL1 能执行 SMC/睡眠/bring-up，不碰密钥寄存器，也不执行 PACIA/AUTIA。
3. 顺序：先 P0/P1/P2，再谈 27 线的 PAC 结论；4 KiB 属于 P4。

## 6. 复现与引用

```sh
grep -n 'APA=0b0101' porting.toml                # limits 里的那一句
grep -n 'TCR_EL1_BOOT' porting.toml              # host 侧 4 KiB 常量
sh scripts/check-ios27-granules.sh ../UniXNU/out/mondrian/ios-27.0.1-24A446/mondrian_ios27/tree
```

页面：`E:/hackios/UniXNU/docs/zh/porting/arm64e.md:16-25`（要求、HCR 说明、入档要求）、
`:27-31`（受支持设备）、`:40`（缺省 arch）、`:52-54`（密钥共用与四个使能位）；
`E:/hackios/UniXNU/docs/zh/porting/soc-support.md:126-134`（SM8550 示例）。

本仓：`porting.toml` 的 `ios27-arm64e`（procedure/limits/next_action/evidence）、
`feeds.toml:7-14`、`board.toml:332,368,378`、`patches/xnu/series:19-21`、
`docs/engineering/IOS27.md:73-83`（16 线的 4 KiB）与 `:245-276`（F0 捕获、读数争议、补丁位置）、
`patches/ios-mondrian/pac-probe-arm64e-gate.patch`、`docs/engineering/PITFALLS.md`（P-255、P-274）。

内核：`E:/hackios/xnu-12377/osfmk/arm64/proc_reg.h:610-624`（SCTLR 使能位与 RES1）、
`:3139-3167`（ISAR1 偏移与 API 枚举）；`osfmk/arm/commpage/commpage.c:509-517`（FPAC 特征位
取自 API）；`osfmk/arm64/platform_tests.c:2050-2071`（两种认证失败形状的断言）。

arm64e profile：`E:/hackios/UniXNU/profiles/arch/arm64e/patches/xnu/series` 与
`E:/hackios/UniXNU/patches/xnu-12377/native-pac-keys.patch`（十个密钥字、`HAS_NATIVE_PAC`）。

sheng：`E:/k60-work/references/UniXNU-sheng`（`patches/xnu-12377/zzzz-sheng-ipados27-bringup.patch`、
`hal/ShengAudioPlugIn.c`、`board.toml`；同一 OS 目标、不同 SoC）。

`IOS27.md` 的同一段已按本文更正：只保留捕获原文与限制，不再给出
“0b0101 = EPAC + PAuth2、API = 通用密钥”的旧读法。
