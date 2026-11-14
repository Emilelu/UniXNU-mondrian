# 按键 ④ 广域参考（Reuse first）

> 状态：✅ 已完成（2026-11-14）。证据等级：官方目录 + 源码比对 + 真机日志。
> 规范依据：`docs/engineering/EIGHT-STEP-SPEC.md:96-140`（④ 五条必做顺序）。
> 结论先说：**官方没有可复用的按键组件，K60 只能自建；但有 3 个同族实现可交叉，且它们的寄存器语义与 K60 完全同构。**

## [catalog_checked] UniXNU/components.toml 逐个比对（29 个）

规范写 25 个，实际文件 `E:/hackios/UniXNU/components.toml` 有 **29** 个 `[[component]]`（`grep '^id = '` 计数）。逐个回答"有没有能直接用的"：

| # | 组件 | 功能 | 对按键可用？ | 理由 |
|---|---|---|---|---|
| 1 | ArmCpu | ARM generic interrupt controller and timer | **部分可用（已用）** | K60 若走中断路径，`armcpu_spi_attach(32+481,…)` 就是它提供的 SPI 挂载接口（`ButtonProbe.cpp:137` 调用点）。当前轮询实现不依赖它 |
| 2 | ArmDTPlatform | Device-tree platform expert | **可用（已用）** | 发布 `/arm-io/pong-buttons` 的 DT nub；日志 `ArmDTPlatform: published DT nub pong-buttons` |
| 3 | ArmVirtPlatform | QEMU virt platform expert | 不可用 | 虚拟平台专用 |
| 4 | DarwinBoot | UEFI XNU loader | 间接相关 | 传 boot-arg `pong_buttons=1`；不含按键逻辑 |
| 5 | Adreno740 | A740 kernel GPU driver | 不可用 | GPU |
| 6 | AdrenoMetal | Metal frontend | 不可用 | GPU |
| 7 | ShengUfs | SM8550 UFS transport | 不可用 | 存储 |
| 8 | **ShengHidInput** | **sheng touch input through IOHIDDevice** | **不可直接用** | 唯一的输入层组件，但 `hardware=["sheng touch event source"]`、`verified_devices=["sheng"]`、`dependencies=["ShengNovatekTouch"]`、`source_files=["NativeHidInput.cpp"]`（`components.toml:143-161`）—— 它只把 **sheng 的 NT36532 触摸** 包成 IOHIDDevice，没有 PMIC 按键的采集路径。K60 的按键在 `bsd/dev/pong_buttons.c` 里自己读 SPMI，与它无耦合 |
| 9 | ShengNovatekTouch | NT36532 touch protocol | 不可用 | 触摸芯片协议 |
| 10 | QcomGeniSpi | Qualcomm GENI SPI controller | 不可用 | 按键走 SPMI，不走 GENI SPI（SPMI 仲裁器在 0xC400000，GENI SE 在别处） |
| 11 | GopFramebuffer | GOP framebuffer | 不可用 | 显示 |
| 12 | SoftwareAES | software AES | 不可用 | 加密 |
| 13 | AppleKeyStoreState | key store state | 不可用 | 与"按键"无关（AppleKeyStore 是密钥库） |
| 14 | RamBlock | RAM block device | 不可用 | 存储 |
| 15 | VirtioMmioBlock | virtio block | 不可用 | 存储 |
| 16 | VirtioMmioConsole | virtio console | 不可用 | 控制台 |
| 17 | XnuPrelink | kit | 不可用 | 预链接 |
| 18 | AdrenoPM4 | kit | 不可用 | GPU |
| 19 | AdrenoFirmware | kit | 不可用 | GPU |
| 20 | ArmSmmu4K | kit | 不可用 | SMMU |
| 21 | AirNir | kit | 不可用 | 网络 |
| 22 | VerifiedRoot | kit | 不可用 | 根卷 |
| 23 | Sm8550Platform | SM8550 GPU platform ops | 不可用 | GPU 平台 |
| 24 | Ath12kWifi | Wi-Fi | 不可用 | 网络 |
| 25 | QcaBluetooth | 蓝牙 | 不可用 | 蓝牙 |
| 26 | QcomDwc3 | USB3 DRD | 不可用 | USB |
| 27 | ShengPreflight | 预检 | 不可用 | 打包 |
| 28 | PongUfs | SM8475/pong UFS + SHNGROOT | 不可用 | 存储 |
| 29 | QcomBaseband | 基带 | 不可用 | 基带 |

**结论**：29 个组件里**没有任何按键 / PON / PMIC GPIO 组件**。唯一输入层组件 `ShengHidInput` 绑定 sheng 触摸，不能吃 PMIC 键 → **K60 自建不违反「有官方组件却造轮子」的 FAIL 条件**。

## [repositories_checked] unixnu.com/zh/drivers/repositories

页面 `https://unixnu.com/zh/drivers/repositories`（抓取 2026-11-14 11:38，HTTP 200）列出 **28 个官方驱动 + 12 个社区驱动 + 9 个设备分支**（规范写 27/12/9，页面实际 28）。

**官方驱动 28 项**：Adreno740、AdrenoMetal、ShengUfs、**ShengHidInput**、RamBlock、GopFramebuffer、QcomGeniSpi、QcomBaseband、SoftwareAES、AppleKeyStoreState、VirtioMmioBlock、VirtioMmioConsole、ShengNovatekTouch、XnuPrelink、Ath12kWifi、QcaBluetooth、QcomDwc3、ArmCpu、ArmDTPlatform、ArmVirtPlatform、ArmSmmu4K、AirNir、AdrenoPM4、AdrenoFirmware、Sm8550Platform（= UniXNU-sm8550-common）、DarwinBoot、VerifiedRoot、ShengPreflight。
→ 属输入层的只有 **ShengHidInput** 一项，理由同上表第 8 行。**没有 PMIC PON/GPIO 按键驱动**。

**社区驱动 12 项**：NativeMsdc、NativeAdreno-myron、NativeUfs-myron、NativeAdreno-fuxi、NativeUfs-alioth、unixnu-nativeufs、unixnu-nativemobiledisplay、unixnu-nativeramblock、NativeEmmc、NativeDwc3、unixnu-nativefocaltechtouch、Adreno830。
→ 全部是存储/显示/USB/触摸，**无按键**。

**设备分支 9 项**：Sony Xperia 1 II、小米平板 7、Nothing Phone (3a)、一加 6T、小米 13 Pro、一加 5、QEMU virt、Benesse TAB-A04-BR3、Unisoc 设备。
→ 官方设备分支里**没有 SM8475 机型**，也没有任何按键驱动条目。

## [same_soc] 同 SoC 兄弟（SM8475）

| # | 项目 | 位置 / commit | 按键实现 | 与 K60 的关系 | 可复用内容 |
|---|---|---|---|---|---|
| 1 | **UniXNU-pong**（Nothing Phone (1) / pong / SM8475） | `E:/k60-work/references/UniXNU-pong/patches/xnu-ipados18/0001-pong-darwin24.patch`（`bsd/dev/pong_buttons.c` 246 行，diff 起 :117） | **中断版**：PDC pin1 → SPI 481，`armPeripheral` 8 步使能 + `acknowledge_key_irq` + 去抖 64 ms；`enable_irqs()` 里 `armcpu_spi_attach(32+481,false,key_irq,…)` 最多重试 120×100 ms | 同 SoC、同 PMIC 族、同 DT 属性名 | **K60 当前实现就是它的轮询降级版**（去掉中断，保留寄存器语义）。DT 节点 `dts/pong.dts:63-68` 与 K60 `scripts/make-pong-adt.py:240` 完全同值 |
| 2 | **UniXNU-zizhan**（zizhan / SM8475） | `E:/hackios/UniXNU-zizhan`（HEAD `034a0b0`） | 无独立驱动，复用 pong 的 `pong_buttons.c`；`dts/zizhan.dts:53-60` 的 `pong-buttons` 节点与 K60 **逐属性同值**（`core-base 0xc400000`/`cnfg-base 0xc42d000`/`observer-base 0xc440000`/`ee 0`/`pon-ppid 0x13`/`volume-up-ppid 0x18d`） | 同 SoC 同 PMIC 布局 | ① 证明这组 DT 常量在同 SoC 上是稳定的；② `patches/xnu-ipados18/0010-pong-power-key-reset.patch` 的**长按 3 s 复位钩子**（`pong_button_reset_hook`、`reset_ms=3000`、`pong_button_reset` boot-arg）是 K60 缺的能力，可移植；③ `userland/touch.c:374-428` 的 buttons_thread 与 K60 `userland/touch.c:364-397` 同构 |
| 3 | **phk110-port / UniXNU-udon**（一加 Ace 2 / PHK110 / SM8475） | `E:/k60-work/references/phk110-port/drivers/input/hakios.buttons.c`（615 行）、`docs/phk110/waves/wave12-touch-buttons.md`（417 行） | **轮询版 60 Hz**：PMK8350 PON(0x013) 位 0x80/0x40 + PM7325 GPIO6(0x18d) 低有效；仲裁器 v5/v7 双布局；无中断 | 同 SoC、同 PMIC 外设 id | ① **真机取证范式**：wave12 记录三键 press/release（t=265 s 时 30,006 次总线读仅 2 失败，读 5–6 µs）；② `buttons_map=1` 换序机制说明"RESIN/GPIO6 谁是音量加因机而异"；③ `REG_RT_STATUS 0x10`/`INT_SET_TYPE 0x11`/`POLARITY_LOW 0x13` 常量与 K60 一致 |
| 4 | **ios-sweet-k60**（同一台 K60 / mondrian，社区分支） | `E:/k60-work/references/ios-sweet-k60/xnu/patches/0251-k60-keys-pon-gpio.patch`（39,249 B，`bsd/sys/k60_keys.h` 150 行 + `bsd/dev/k60_keys.c` 715 行）、`0101-k60-spmi-arbiter-addresses.patch`（1,496 B） | 轮询 25 ms，PON 走 `sweet_spmi_read()` 共用电锁，GPIO 自发 `EXT_READL` | **同机型**（不是同 SoC 而是同一台机器） | ① `0101` 把 sweet 的 `0xc40a000/0xc440000/0xe600000` 纠正为 K60 的 `0xc42d000/0xc400000/0xc440000` —— 与 K60 现有常量一致，是**独立第三源**；② `0251:172-174` 的 `K60_KEYS_PON_RT 0x1310`、`PWR_BIT 7`、`RES_BIT 6`（注释明确标"推断"）与 UEFI boot40 实测一致；③ usage 0x30/0xe9/0xea 与 K60 相同；④ 它的 NOTES.md 明确写「0251 离线完成，**未上机**」→ 只能当旁证，不能当实测 |
| 5 | **UniXNU-sm8475-common** | `E:/hackios/UniXNU-sm8475-common` | 无 | 同 SoC 公共库 | grep `buttons|pwrkey|pon_hlos|spmi-pmic-arb|gpio-keys` **零命中** → SM8475 公共层不含按键 |
| 6 | **UniXNU-liuqin**（小米平板 6 Pro） | `E:/hackios/UniXNU-liuqin` | 无驱动 | 非同 SoC，仅参考 ADT | `scripts/make-liuqin-adt.py:176-179` 的 `/buttons` 节点写法（`compatible/device_type = buttons`、`button-names hold/voldown/volup`、`home-button-type 2`）—— K60 缺这个节点 |
| 7 | **zizhan 上游（qiumochen/UniXNU-zizhan，社区 device_main）** | 本地**无检出**（`/e/k60-work/references` 与 `/e/hackios` 都没有） | **未取得** | — | ④ 的规范提到 zizhan 作为同 SoC 源，但社区仓未 clone；已用 `E:/hackios/UniXNU-zizhan`（官方设备分支）替代，不影响结论 |
| 8 | **d22ap / taro**（规范点名的另两个 SM8475 代号） | 本地无检出，官方设备分支页也没有 | **未取得** | — | 如实记为缺口；SM8475 侧的结论已由 pong / zizhan / phk110 / sweet-k60 四个源覆盖 |

## [same_chip] 同外设芯片（PMK8350 PON + PM8350 GPIO）

| # | 来源 | 关键事实 | 与 K60 一致？ |
|---|---|---|---|
| 1 | mainline `drivers/spmi/spmi-pmic-arb.c`（v7 布局） | map 表 `core+0x2000+4*apid`（bits19:8 PPID、bit24 IRQ owner）、obs `0x8000*ee+0x20*apid`、chnls `0x1000*apid` | ✅ K60 日志 `arbiter v7 channels=768` 与 UEFI `apid_count 758` 都落在 v7 |
| 2 | mainline `drivers/input/misc/pm8941-pwrkey.c` | PON `INT_RT_STS(0x10)` 位号 = 该键的 IRQ 号 | ✅ K60 pwrkey=IRQ7→bit7、resin=IRQ6→bit6（UEFI boot40 实测 `pon rtsts=0x10`） |
| 3 | mainline `drivers/pinctrl/qcom/pinctrl-spmi-gpio.c` | `MODE_CTL 0x40`、`DIG_PULL_CTL 0x42`、`DIG_IN_CTL 0x43`、`EN_CTL 0x46`；subtype 0x10..0x13 同布局 | ✅ K60 厂商 `vendor/pinctrl-spmi-gpio.c:33,41-44,50-56` 同值；K60 回读校验用同一组偏移 |
| 4 | **官方 `ButtonProbe.cpp`（sheng / PMK8550 + PM8550）** | `kPonPpid 0x013`、`kGpioPpid 0x18d`、`kPowerBit 1<<7`、`kResinBit 1<<6`、`kGpioBit 1<<0` | ✅ 与 K60 **逐项相同**（PMK8550/PM8550 与 PMK8350/PM8350 的 PON/GPIO 布局同族） |
| 5 | PHK110 的 PMK8350 + PM7325 | PON 位 0x80/0x40；GPIO6 低有效；APID 407/434 | ✅ 位与 APID 相同，**仅 RESIN/GPIO6 的键位分配相反** |
| 6 | sweet 板（POCO X5 Pro / SM6375） | PON 读 `0x0810`（`pon_pbs` 页）、音量加读 PM6150L SID4 `0xc1` | ❌ **不适用**：K60 的 `0x0810` 落在 `pon_pbs@800` 而 APPS 只能读 `pon_hlos@1300`；K60 音量加在 PM8350 而非 PM6150L |

## [cross_check] 多来源交叉（≥2 独立来源一致）

| 参数 | 来源 A | 来源 B | 来源 C | 一致？ |
|---|---|---|---|---|
| 仲裁器窗口 `core 0xc400000 / cnfg 0xc42d000 / observer 0xc440000` | live FDT 无此三者（不是 DT 属性）→ 由 **K60 日志** `PMIC windows mapped` 与 `arbiter v7` 反证 | **sweet-k60 `0101` 补丁**（从 live FDT 的 `reg` 读出 `<0xc42d000 0x4000 0xc400000 0x3000 0xc500000 0x400000 0xc440000 0x80000 0xc4c0000 0x10000>`） | **官方 `ButtonProbe.cpp:26`** 的 `kCore/kCnfg/kObsrvr` | ✅ 三源一致 |
| PON PPID `0x013`（SID0） | live FDT `:9852` `interrupts=<0x00 0x13 0x07 0x03>` | 官方 `ButtonProbe.cpp:27` `kPonPpid 0x013` | UEFI `K60KeypadDeviceLib.c:26,78` `PPID_PON 0x013` | ✅ 三源一致 |
| 音量加 PPID `0x18D`（SID1 GPIO6） | live FDT `:10338` `pinctrl@8800` + `:32483` `gpios=<0x57b 0x06 0x01>` | 官方 `ButtonProbe.cpp:27` `kGpioPpid 0x18d` | UEFI `:27,79` `PPID_GPIO 0x18D` | ✅ 三源一致 |
| 电源键位 = RT_STS bit7 | live FDT `:9852` `interrupts=<… 0x07 …>`（IRQ7） | UEFI `:28,33` "Power = PON INT_RT_STS bit7" + "boot40 ground truth pon rtsts=0x10" | 官方 `ButtonProbe.cpp:28` `kPowerBit 1u<<7` | ✅ 三源一致（**推翻了 K60ButtonsDxe v3 的 bit0 假设**） |
| 音量减 = RT_STS bit6 | live FDT `:9858` `interrupts=<… 0x06 …>` | UEFI `:29` "VolDn = bit6 (resin IRQ6)" | 官方 `ButtonProbe.cpp:28` `kResinBit 1u<<6` | ✅ 三源一致 |
| 音量加 = GPIO6 低有效 | live FDT `:32483` `gpios=<0x57b 0x06 0x01>`（第三项 1 = ACTIVE_LOW）+ `:10358-10364` `bias-pull-up` | UEFI `:30` "VolUp = pm8350 gpio6 RT_STS bit0, ACTIVE LOW"；`:33` `gpio rtsts=0x01` | 官方 `ButtonProbe.cpp:126` `!(gpio & bit0)` | ✅ 三源一致 |
| HID usage `0x30/0xe9/0xea`（consumer page 0x0c） | K60 `userland/touch.c:66-69` | 官方 `ButtonProbe.cpp` 用 report 2 位域（**不同形式**，但同样是 consumer page） | sweet-k60 `0251` `K60_KEY_USAGE_*` 0x30/0xe9/0xea | ◐ 形式不同（位域 vs usage），语义一致 |
| 真机可用 | K60 `usblog-20261108-180257:229`（三键 usable=1） | K60 `usblog-20261108-213652:2424+`（170 条 HID 事件） | PHK110 wave12（同族 PMIC 三键真机） | ✅ 一致 |

## 复用决策（Reuse first 的实际结论）

| 候选 | 能否直接用 | 决策 |
|---|---|---|
| 官方组件（29 个） | ❌ 无按键组件 | 自建 `bsd/dev/pong_buttons.c`，**但 HID 发布层照官方 `ButtonProbe.cpp` 的 consumer page 语义** |
| 官方 `ButtonProbe.cpp` | ◐ 架构可借，代码不能直接编 | 借：寄存器语义、`findApid` 规则、`pressed()` 判据、SPI481/PDC 常量；不借：report 2 位域、boot-arg 名 |
| pong 的 `pong_buttons.c`（246 行中断版） | ✅ 已复用（降级为轮询） | 当前 K60 实现即其轮询子集；中断版留作可选增强 |
| zizhan 的 `pong-buttons` DT 节点 | ✅ 已复用（逐属性同值） | 交叉验证 DT 常量正确 |
| zizhan 的长按 3 s 复位钩子 | ◐ 可移植 | **建议**：K60 没有从运行中的 iOS 回到 fastboot 的按键通路，这是真缺口（超出本线写作用域，报 Lead） |
| phk110 的 `hakios.buttons.c` | ◐ 不可直接编（HakiOS 框架），但可借 | 借：真机取证方法（每分钟汇总总线读次数/失败数）、`buttons_map` 换序思路 |
| sweet-k60 的 `k60_keys.c`（同机型） | ❌ 不可用 | 它依赖 sweet 的 `sweet_spmi_read()` 电锁与 sweet UFS 初始化顺序；且 NOTES 自述**未上机**。只作常量旁证 |
| sweet 板 `sweet_keys.c` | ❌ 明确不适用 | PON `0x0810`（PBS 页）与 PM6150L `0xc1` 在 K60 上都是错的（见 ③ 缺口） |

## 缺口

- ❌ **官方无按键组件**（29 个组件 + 28 个官方驱动 + 12 社区 + 9 设备分支全部核对完毕）：这是事实结论，不是遗漏。
- ❌ `d22ap` / `taro` 两个规范点名的 SM8475 代号本地无检出，社区 `qiumochen/UniXNU-zizhan` 也未 clone —— 但 SM8475 侧已有 4 个源（pong / zizhan / phk110 / sweet-k60），结论不受影响。
- ◐ 官方 `ButtonProbe.cpp` 的**中断路径**（PDC pin1 + SPI 481 + `armPeripheral` 8 步）只在 sheng（SM8550）上验证过，K60 未验证；K60 现走轮询，中断是可选增强。
- ◐ K60 **没有** zizhan 那样的长按电源键复位钩子，运行中的 iOS 无法靠按键回到 fastboot。属能力缺口，不在本线写作用域（`patches/xnu/` 由触摸线持有），报 Lead。
- ❌ K60 的 ADT 缺 `/buttons` 节点（见 ② 与 ③），pong/zizhan/liuqin 都有 —— 修法在 `scripts/make-pong-adt.py`，不在本线写作用域。
