# 按键 ② 官方驱动文档与配套文件

> 状态：✅ 已完成（2026-11-14）。证据等级：文档 + 官方源码。来源：`https://unixnu.com/zh/porting/input`（本地副本 `UniXNU-docs/docs/zh/porting/input.md`，抓取 2026-11-14 11:20 返回 200）、`https://unixnu.com/zh/drivers/repositories`、`https://unixnu.com/zh/reference/components`、`UniXNU/components.toml`。

## 已收集

| # | 文档/页面 | 内容 | 本地副本 | 抓取时间 |
|---|---|---|---|---|
| 1 | `/zh/porting/input` §4「适配实体按键」 | 六条硬要求 + 预期结果（见下表） | `UniXNU-docs/docs/zh/porting/input.md:70-79` | 2026-11-14 11:20（HTTP 200） |
| 2 | `/zh/porting/input` §源码与接口 | 按键事件归到 `NativeHidInput.cpp, ButtonProbe.cpp` 一行 | `input.md:9`、:19（表行，钉 commit） | 2026-11-14 11:20 |
| 3 | `/zh/porting/drivers` 覆盖表第 4 行 | 「触控与实体按键」→ 需要检查的实现：QcomGeniSpi、ShengNovatekTouch、ShengHidInput、**ButtonProbe** | `UniXNU-docs/docs/zh/porting/drivers.md:39` | 2026-11-14 11:22 |
| 4 | 官方参考实现 `ButtonProbe.cpp` | 221 行，SPMI 仲裁器 + PDC + HID consumer 的完整按键实现 | `references/UniXNU-sheng/package/ButtonProbe.cpp`（官方页钉 commit `516a7804`，本地 checkout HEAD `11080685`） | 2026-11-14 11:25 |
| 5 | 官方 SPMI 辅助接口 `BootResetCore.h` | 仲裁器常量与 `br_read8/br_write8` 封装（文档点名「SPMI 控制器变化时适配」） | `references/UniXNU-sheng/package/BootResetCore.h` | 2026-11-14 11:28 |
| 6 | `/zh/guide/mobilegestalt` | `/buttons` 节点的 `button-names`、`home-button-type` 要求与 ADT 写法 | `UniXNU-docs/docs/zh/guide/mobilegestalt.md:26-27,42,77-78` | 2026-11-14 11:30 |
| 7 | `/zh/porting/device-tree` §product 与 buttons | `/buttons` 由 MobileGestalt 与平台代码读取 | `UniXNU-docs/docs/zh/porting/device-tree.md:94,221,223` | 2026-11-14 11:31 |
| 8 | `/zh/guide/boot` 启动菜单按键表 | 上/下移动、Enter 启动、任意键停倒计时、Cancel | `UniXNU-docs/docs/zh/guide/boot.md:57,60,62-64` | 2026-11-14 11:33 |
| 9 | `/zh/reference/components` + `components.toml` | 29 个官方组件里唯一输入层组件是 ShengHidInput | `UniXNU/components.toml:143-161` | 2026-11-14 11:35 |

## 官方要求逐条（`input.md` §4，原文见 :70-79）

| # | 官方原文要点 | 对 K60 的落地 | 证据 |
|---|---|---|---|
| 1 | 「参考源码索引中的 `ButtonProbe.cpp` 实现中断采样和 HID 按键事件」 | 参考其寄存器序列，但 K60 先走 16 ms 轮询（见 ③ 与 ⑤） | `input.md:72`；`ButtonProbe.cpp:89`（`buttonsIrq`）、:178（`buttonsThread`） |
| 2 | 「映射目标 GPIO 或 PMIC 输入、极性、所有权、中断路由和应答操作」 | 五个量全部有本机来源：PMK8350 PON(0x013) + PM8350 GPIO6(0x18D)、低有效、EE0 所有权、SPI481、PDC pin1 | `docs/research/buttons/03-REVERSE.md` 的 live FDT 表 |
| 3 | 「仅访问当前执行环境拥有的 PMIC 外设」 | 读通道前校验 `cnfg+4*apid & 7 == 0`；不写任何 PMIC 配置寄存器 | `patches/xnu/zzzz…-pong-physical-keys.patch:252-260`（type/subtype/owner 校验） |
| 4 | 「SPMI 控制器变化时适配 `BootResetCore.h` 辅助接口」 | 用同一套 v7 布局：map `core+0x2000+4*apid`、obs `0x20*apid`、chnls `0x1000*apid` | `BootResetCore.h` 的 `BR_APID_MAP 0x2000` / `BR_OBS_APID_STRIDE 0x20` / `BR_CHNL_APID_STRIDE 0x1000` |
| 5 | 「把按下/释放状态接入 HID consumer 报告」 | 内核投 `PONG_BUTTON_DOWN/UP` 到 `/dev/pong-buttons`，用户态发 consumer page 0x0c 的 0x30/0xe9/0xea | `userland/touch.c:382-397`；`patches/…-pong-physical-keys.patch:235` |
| 6 | 「预期结果：每次按下和释放产生正确报告，包括长按和同时按键，中断活动保持有界」 | 已实测：170 条 `key=… down=… sent=1`，含长按与同时按；无中断风暴（轮询模式） | `usblog-20261108-213652/console.log:1266,2424+`；见 ③ |

补充要求（不在 §4 但在同一体系内）：

| 要求 | 出处 | K60 现状 |
|---|---|---|
| `/buttons` 节点提供 `button-names`（`hold`/`voldown`/`volup`，无 Home 键则省略 `menu`）与 `home-button-type=2` | `mobilegestalt.md:26-27`、`device-tree.md:223` | ✅ 已落地：`board.toml:268-276` 的 `[adt.buttons.*]`（main `174fb69`）经 `devicetree.py:388-390` 发射 `/device-tree/buttons`，重生成实测 `button-names=hold\0voldown\0volup\0`、`home-button-type=0x2`（14,660 B / 23 节点 ADT，`board.toml` 已含 `5cd8924` 的 pong-buttons 段）。`scripts/make-pong-adt.py:240` 在 `schema_version = 2` 下仍是死代码（`payload.py:231-236`），改它无效 |
| 启动菜单的按键语义（上下/Enter/任意键） | `boot.md:57-64` | 由 UEFI Keypad 链提供（`K60KeypadDeviceLib`），不是内核侧 |
| 官方参考实现用 boot arg 开关（sheng 是 `sheng-buttons=1`，页面写 `buttons=1`） | `input.md:77`；`ButtonProbe.cpp:214` `sheng_buttons_probe()` | K60 用 `pong_buttons=1`（默认开），见 `board.toml` 默认 boot-arg |

## 官方参考实现 `ButtonProbe.cpp` 关键行（221 行）

| 行 | 内容 | 对 K60 的意义 |
|---|---|---|
| :26 | `kCore 0xc400000 / kObsrvr 0xc440000 / kChnls 0xc500000 / kIntr 0xc4c0000 / kCnfg 0xc42d000 / kPdc 0xb220000` | 六个窗口地址与 K60 live FDT 完全一致 |
| :27 | `kPonPpid 0x013 / kGpioPpid 0x18d` | 与 K60 DT 的 `pon-ppid`/`volume-up-ppid` 同值 |
| :28 | `kPowerBit 1u<<7 / kResinBit 1u<<6 / kGpioBit 1u<<0` | 与 K60 的 RT_STS 位（7/6/0）一致 |
| :29-31 | `kAccEnable 0x100 / kIrqStatus 0x104 / kIrqClear 0x108`；`kRtSts 0x10 / kSetType 0x11 / kPolHigh 0x12 / kPolLow 0x13 / kLatchedClr 0x14 / kEnSet 0x15`；`kPdcPin 1 / kSpi 481` | K60 当前只用 0x10 读状态，中断路径未启用 |
| :33 | `kReportPower 1u<<1 / kReportVolumeUp 1u<<2 / kReportVolumeDown 1u<<3`（report 2） | K60 改为 consumer page 的 usage 0x30/0xe9/0xea（HID 键盘事件），报告描述符不同 |
| :55 | `int findApid(uint32_t ppid)`：`map = core+0x2000+4*i`，bits19:8=PPID，bit24=IRQ owner，owner `cnfg+4*i & 7 == ee` | K60 的 `find_channel()` 同构（`patches/…:200-210` 附近） |
| :68 | `int armPeripheral(int apid, uint8_t bits)`：8 步序列（读 SET_TYPE/POL_HIGH/POL_LOW → 写 type|bits、high|bits、low|bits、LATCHED_CLR=bits、EN_SET=bits → ACC_ENABLE=1），失败重试 4 次 × `IOSleep(25)` | K60 轮询版**不启用中断**，因此不写这些寄存器（只读原则） |
| :89 | `void buttonsIrq(void *)`：遍历 intr 窗口 word 找 pending，只清非本 EE 的 arbiter 状态 | 若将来上中断，需照此避免读别人的寄存器 |
| :126 | `uint32_t pressed()`：PON 0x10 bit7→power、bit6→vol-down；GPIO 0x10 `!(gpio & bit0)`→vol-up | 与 K60 `look()` 的判据完全一致 |
| :137 | `bool setup()`：map core 0x3000/cnfg 0x4000/intr 0x1000/pdc 0x2000；version ∈ [0x70000000,0x80000000)；apid 数 = `core[4]&0x7ff` ≤1024；obs `0x20*apids`、chnls `0x1000*apids`；PDC pin1 cfg 写 `(1<<3)|4`；`armcpu_spi_attach(32+481,false,…)` 失败每 250 ms 重试 240 次 | K60 的 `configuration()` 做了同样的版本/通道数校验（`patches/…:246-249`），但**没有**映射 intr/pdc，也不 attach SPI |
| :178 | `void buttonsThread(void *, wait_result_t)`：setup 后死循环，`pressed()` 与 last 比较，变化则回调，然后 `assert_wait(gEvents)` | K60 用 16 ms `assert_wait_deadline` 轮询（`patches/…:269+`） |
| :198/:214 | `native_buttons_set_sink(sink,ctx)`；`sheng_buttons_probe()` 读 boot arg `buttons` 必须 =1 | K60 的开关是 `pong_buttons`（默认 1） |

## 官方 SPMI 辅助接口 `BootResetCore.h`

| 常量 | 值 | 含义 |
|---|---|---|
| `BR_VERSION_V7_MIN` | `0x70000000u` | v7 起始版本（K60 实测 = 0x70000000，见 ③） |
| `BR_VERSION_V8_MIN` | `0x80000000u` | v8 起始 |
| `BR_APID_MAP` | `0x2000` | `core + 0x2000 + 4*apid`：bits 19:8 = PPID，bit 24 = IRQ owner |
| `BR_CNFG_OWNER` | `0x00` | `cnfg + 4*apid`：bits 2:0 = 允许写该 APID 的 EE |
| `BR_OBS_EE_STRIDE` / `BR_OBS_APID_STRIDE` | `0x8000` / `0x20` | observer 读通道 = `0x8000*EE + 0x20*APID` |
| `BR_CHNL_APID_STRIDE` | `0x1000` | 读写通道 = `0x1000*APID` |

函数：`br_find`、`br_read8(obs, a, apid, byte_addr, *value)`、`br_write8(chn, apid, byte_addr, value)`、`br_set_bootloader(...)`。

## 官方组件/仓库结论（② 视角，④ 详版见 `04-WIDE.md`）

- `UniXNU/components.toml` 29 个组件中**没有**任何按键 / PON / PMIC GPIO 组件。唯一输入层组件 `ShengHidInput`（`components.toml:143-161`）是 sheng 触摸的 IOHIDDevice 发布层（`hardware=["sheng touch event source"]`、`verified_devices=["sheng"]`、`dependencies=["ShengNovatekTouch"]`），不能消费 PMIC 键。
- 官方驱动仓库页 28 项里输入层同样只有 `ShengHidInput`；官方**没有** PMIC 按键驱动可复用，因此 K60 自建 `bsd/dev/pong_buttons.c` 不违反「有官方组件却造轮子」的反模式。

## K60 与官方参考实现的差异（必须保留）

| 项 | 官方 `ButtonProbe.cpp`（sheng / SM8550） | K60（mondrian / SM8475） | 依据 |
|---|---|---|---|
| 中断 | PDC pin1 → SPI 481，真中断 + 只应答 | 16 ms 轮询，未映射 PDC/intr 窗口 | 上机日志只有轮询路径；上中断需要写 PMIC 中断寄存器，与只读原则冲突 |
| HID 形式 | 自建 report 2 位域（`IOHIDUserDevice`） | consumer page 的键盘事件 0x30/0xe9/0xea | `userland/touch.c:382-397` |
| boot arg | `buttons=1`（页面）/ `sheng-buttons=1`（源码） | `pong_buttons=1`，默认开 | `board.toml` 默认 boot-arg |
| 音量加来源 | PM8550 GPIO6（SID1） | PM8350 GPIO6（SID1），低有效 | 见 ③ live FDT |

## ADT 里 `/arm-io/pong-buttons` 的来源（2026-11-14 结案）

**已闭合**：`[adt.arm-io.pong-buttons.*]` 已由 Lead 落进 `board.toml:267-280`（main `5cd8924` "fix(adt): own the pong-buttons node instead of a build-copy edit"），仓库自此自洽。用仓库 `board.toml` 直接跑 `unixnu.devicetree.generate()` 重生成 ADT 得 **14,660 B / 23 节点**，`/device-tree/arm-io/pong-buttons` 六属性齐全（core-base `0xc400000` / cnfg-base `0xc42d000` / observer-base `0xc440000` / ee `0x0` / pon-ppid `0x13` / volume-up-ppid `0x18d`），`/device-tree/buttons` 同时存在。

以下三行是**历史取证**，解释 11-14 那次上机镜像为什么能通按键（该镜像的节点来自本地未提交改动，已不再是当前依赖）：

| # | 核查对象 | 结果 |
|---|---|---|
| 1 | 构建产物 `usb-20261114b/boot.img`（201,887,744 B，sha256 `EF0E905F…`）里的 `KERNEL~1ADT` | 15,736 B，sha256 `18a514e7…`，与 `build-manifest.json` 的 `components.adt` 一致；24 节点，`/device-tree/arm-io/pong-buttons` 有 core-base/cnfg-base/observer-base/ee/pon-ppid/volume-up-ppid，**无 compatible**，**无 `/device-tree/buttons`** |
| 2 | 被构建的 board 仓 `E:/hackios/k60-usb`（HEAD `9ce7d2c`，构建提交 `0b00bc79`） | `board.toml` 只有 4 个 adt 段（:235 `pong-touch.string`、:238 `.u64`、:243 `.u32`、:249 `.bytes`），`grep pong-buttons` 零命中；`dts/mondrian.dts` 只有 :55 `unixnu,adt-name="pong-audio"`、:87 `"ufshc"` |
| 3 | 框架 OS profile：WSL `/opt/k60/trees/k60build/profiles/os/ipados-16.6.1-20G81/profile.toml:149-158` | **命中**：`["adt"."arm-io"."pong-buttons"]` + `.u64` 三个基址 + `.u32` ee/pon-ppid/volume-up-ppid，**没有 `.string compatible`** —— 与第 1 行 ADT 缺 compatible 完全吻合。该文件 `git status` 为 ` M`（未提交），`git show HEAD:…` 零命中；上游 `E:/hackios/UniXNU/profiles/os/` 的四个 profile 也零命中 |

合并顺序决定了它能生效：`scripts/unixnu/profiles.py` 的 `load()` 按 arch → soc → **os profile** → `board.toml` 依次 `merge()`，后者覆盖前者。所以 11-14 镜像按键能通，靠的是这处**本地未提交的 profile 改动**，不是任何仓库里的提交。

该本地改动当时的后果是：干净重建会退回 `Pong keys: DT node /arm-io/pong-buttons not found`。`5cd8924` 把这六行搬进 `board.toml` 后，该缺口关闭（`devicetree.py` 会 merge `[adt.arm-io.*]`，board 覆盖 profile，取值相同无副作用）。`dts/` 侧曾被删过一次：`10649b3`（"fix(adt): let each of the three sources own its own fields"，在 HEAD 祖先链上）把该节点从 DTS 移除，理由是「Configured arm-io child duplicates an exported hardware node」——profile 已带全部六个属性。

## 缺口

- ✅ K60 的 ADT **已有** `/buttons` 节点（2026-11-14 复核，原缺口已闭合）：`board.toml:268-276` 的 `[adt.buttons.string/.strings/.u32]` 由 main `174fb69` 落盘。
  - 发射链：`board.toml:1` 是 `schema_version = 2`，ADT 由 `scripts/unixnu/devicetree.py` 的 `generate()` 生成，`/buttons` 只在 `[adt].buttons` 存在时发射（`devicetree.py:388-390`）；`scripts/make-pong-adt.py:240` 属 schema_version 1 的遗留工具，**本机不会被调用**，改它是死代码（`payload.py:231-236`）。
  - 实测：用 `unixnu.devicetree.generate()` 重生成 ADT 得 14,660 B / 23 节点（`board.toml` 含 `5cd8924` 的 pong-buttons 段），`/device-tree/buttons` 带 `compatible=buttons`、`device_type=buttons`、`button-names=686f6c6400766f6c646f776e00766f6c757000`（`hold\0voldown\0volup\0`）、`home-button-type=0x2`。
  - 取值照抄 yibiya `board.toml:256-264`；`opposed-power-vol-buttons` 在 `UniXNU-docs` 里 grep 不到、yibiya 也无先例，**不写入**。
- ◐ 官方参考实现的中断路径（PDC + SPI 481 + `armPeripheral`）只读了源码，**未在 K60 上验证**；K60 当前走轮询，中断是可选增强。
- ◐ 官方页写的 boot arg 名是 `buttons=1`，源码读的是 `sheng-buttons=1`；两者不一致是板级命名差异，K60 用 `pong_buttons`，不冲突但需在 ⑦ 里如实记录。
- ❌ 官方无 PMK8350/PM8350 的公开寄存器手册（Qualcomm NDA）；寄存器语义只能以 mainline `spmi-pmic-arb.c`、`pinctrl-spmi-gpio.c`、`pm8941-pwrkey.c` 与官方 `ButtonProbe.cpp` 三处交叉为依据（见 ③）。
