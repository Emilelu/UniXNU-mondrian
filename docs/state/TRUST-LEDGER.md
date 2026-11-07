# 可信度台账（TRUST LEDGER）

> 目的：本仓库的历史调研文档**不能默认正确**。任何决定实现的数值，必须先在本表登记
> 「出处 / 冲突 / 复算方式 / 状态」，否则只能写"未核实"。
> 状态取值：`已实测`（有设备输出或 SHA256）、`可复算`（有可重跑的本地命令）、
> `未核实`（引用的源已不在盘上或只有推断）、`已证伪`（有反证）。
> 建立于 2026-11-07，触发原因：`plans/K60-120HZ-PLAN.md` 的面板数据取自通用参考面板（见 §2）。

## 1. 已经证伪 / 互相矛盾的

| # | 断言 | 出处 A | 出处 B（反证） | 状态 |
|---|---|---|---|---|
| T1 | DRAM 12 GiB @`0x80000000`，`swinfo.fingerprint=mondrian:12` 可作 SKU 证据 | `D:/Android/k60-ios/AGENT-COORDINATION.md:1778,1792,1782` | `docs/audits/MEASURED-HIGH-WINDOW-2026-11-02.md:39-57` 原文："A hand-authored DTS containing base=0x80000000,size=12 GiB is **NOT** hardware measurement. Neither is swinfo.fingerprint=mondrian:12 a reliable SKU proof." | **冲突未解** |
| T2 | K60 面板 = `sharp_qhd_plus_dsc_cmd`，无 120Hz 档，切档用 DCS `0xC6` | `D:/Android/k60-ios/deliverables/K60-120HZ-PLAN.md` §2/§3 | `deliverables/ZCODE-RESEARCH-REPORT.md:396`（U6-C5）：那是通用参考面板；真机 `m11a_42_02_0a` | **已证伪** |
| T3 | K60 触摸是 sweet 那套 I2C `0x5d` / SE `0xa84000` | （我此前的推断，源自 sweet NOTES） | `AGENT-COORDINATION.md:1379`：K60 = GENI SPI `spi@990000` CS0 15 MHz；**明确写"不要抄 sweet 的 GT9896 常量"** | **已证伪** |
| T4 | 按 pong 的 glob 字母序全量应用 155 个补丁即可"与 pong 完全一致" | `UniXNU-pong` `scripts/build-xnu-4k-baseline.sh:71` | `docs/audits/PONG16-DIFF-AUDIT.md` §5：实测 111 clean / 14 fuzz / **30 FAIL**，真实脚本第 1 个补丁就 exit 1（`0210` 的目标文件由第 115 位的 `ui-foundation` 创建） | **已证伪** |
| T5 | sweet 的 19 个 cryptex hard-link 是解决 launchd 崩溃的正解 | `ios-sweet-k60/NOTES.md:139` | 架构不同：sweet 单卷可写 HFS+；我们/pong 三窗口 + 只读 OS 卷，正解是 `apply()` 移走 stock jobs（`userland/build.py:449-471`） | **已证伪（架构不适用）** |

### 1.1 文件可用性误判（2026-11-07 核对后纠正）

| # | 断言 | 出处 A | 出处 B（反证） | 状态 |
|---|---|---|---|---|
| C1 | K60 raw dtbo 已不在盘上，无法解析 `dtbo_a_fdt15/fdt19` | `docs/plans/K60-TOUCH-PARAMS.md` §1.1（只搜 D/E 盘，未搜 F 盘） | `docs/state/SESSION-DIRECTIVES-2026-11-07.md` §1：`F:/k60-archive/dtb/` 有 65 个文件，含 `dtbo_a_fdt15.dtb` 752,562 B、`dtbo_a_fdt19.dtb` 509,088 B | **已证伪（可用性误判）** |
| C2 | IPSW 分量本地已丢，重建前必须重新下载 | `docs/state/STATE-2026-11-07.md` §10 旧标题 | `docs/state/SESSION-DIRECTIVES-2026-11-07.md` §1：`E:/hackios/UniXNU/out/ipsw/20G81/` 有 `096-57366-083.dmg` 4,250,815,697 B、`096-56782-083.dmg` 2,665,480,192 B、`kernelcache.decompressed` 48,644,096 B（合计约 6.5 GB） | **已证伪（可用性误判）** |

## 2. 需要复算才能用的

| # | 断言 | 出处 | 复算方式 | 状态 |
|---|---|---|---|---|
| T6 | `/memory/reg` 六段（`0x80000000/0x6a000000`、`0xf4600000/0xba00000`、`0x800000000/0x37500000`、`0x900000000/0x180000000`、`0x840000000/0xc0000000`、`0x837b00000/0x1e00000`） | `docs/audits/MEASURED-HIGH-WINDOW-2026-11-02.md:41-51` | 设备在 Android/recovery：`adb shell od -A x -t x8 /sys/firmware/devicetree/base/memory/reg` | 未核实（设备当前在 fastboot） |
| T7 | K60 触摸 9 个 DT 属性：`spi-base=0x990000`、`pins[4]=21`(INT)、`pins[5]=20`(RESET)、`max=14400/32000`、`avdd=GPIO71`、固件 `goodix_firmware_m11a` | `AGENT-COORDINATION.md:1379`；pong 断言见 `patches/xnu/zzzz…-pong-touch-console.patch:63-65` | 上机后用 `k60touchid=1` 判据行 `K60 TOUCH: ID: abi=berlin chip="…"` 与 `goodix: touch report at 0x…` 复核 | 部分已实测（spi/pins 与 pong 同值），`avdd/pins[0..3]` 未核实 |
| T8 | `rsc-base=0x17a20000` 对 K60 可用 | pong 断言同文件 `:64` | 先只读探针（等价 sweet `0248`），**未探针前禁止发起 TCS 写**；K60 曾出现 RSC `0x17a00000` 访问死（`docs/reference/ROUTE-A-18-DELTAS.md:13-15`） | 未核实 |
| T9 | K60 真面板 = `qcom,mdss_dsi_m11a_42_02_0a_dsc_cmd`（**不是** `sharp_qhd_plus_dsc_cmd`） | `ZCODE-RESEARCH-REPORT.md:384/:396` | **已用二进制 grep 复核**：`F:/k60-archive/dtb/dtbo_a_fdt19.dtb` 命中 `m11a_42_02_0a` 4 次、`dtbo_a_fdt15.dtb` 命中 0 次（fdt15 只有通用 `sharp_qhd_plus_dsc`） | **已实测** |
| T11 | 面板三档 60/90/120，切档 DCS `0x2F`（`0x02/0x01/0x00`），三档 phy-timings 与 clockrate `0x47868C00` 相同 | `ZCODE-RESEARCH-REPORT.md:384` | 需从 `fdt19` 的 `m11a` 节点解析 timing@0/1/2 逐字节复核（dtbo 已在 `F:/k60-archive/dtb/`，可复算） | 可复算 |
| T10 | prelink `roots` 与 `slide` 的取值 | `profiles/os/ipados-16.6.1-20G81/profile.toml`（`slide=0`） | 用 `D:/Android/k60-ios/config/kc20g81-components.json`（1418 行 load/exec 表）复算，并对首轮 prelink 报告做比对 | 可复算 |

## 3. 已被今天设备日志证实的（可作为基线）

| # | 事实 | 证据 |
|---|---|---|
| E1 | SpringBoard 已进主循环、无崩溃循环 | 0460/0461 日志 `[SpringBoard] _checkIn returned` → `UIApplication _run entered` → `main queue reached locked=0 screen=0 dim=1` |
| E2 | launchd（PID 1）后期 SIGSEGV，紧接 `access(/System/Cryptexes/App/usr/libexec/webbookmarksd, X_OK) failed errno 2` | `KX! … launchd sig=11 ns=2 code=0xb` + `initproc exited` |
| E3 | 设备 OS 窗口是 stock 镜像，未跑过 `apply()` | `Pong init: exec original /sbin/launchd`（非 `launchd.ios`）、无 `pong/stock-config`、四个 boot view SKIP |
| E4 | `userland/build.py` 与 pong ios16 字节一致；`apply()` 在 `:449` | `docs/audits/PONG16-DIFF-AUDIT.md` §3 |
| E5 | AKS 35/101 与 no-ext-resolver 在本树已具备 | `iokit/Kernel/MiniAppleKeyStore.cpp` switch 内含 `kAKSGetExtendedState`/`kAKSAssertConsume`；`config/MASTER.arm64.pong` 的 FILESYS_BASE 不含 `config_ext_resolver` |

## 4. 使用规则

1. 引用任何历史文档的数值前，先在本表找到对应行；状态不是 `已实测`/`可复算` 的，**必须重算或标注未核实**。
2. 新增断言 = 新增一行，写清出处与复算命令。
3. 出现反证时把状态改为 `已证伪`，保留两边出处，不删旧行。
