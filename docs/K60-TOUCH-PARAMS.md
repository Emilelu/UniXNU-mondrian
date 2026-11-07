# K60 触摸参数表（pong 驱动 + K60 实测值）

> 目的：把 pong 的 Goodix-over-GENI-SPI 驱动接到 K60 上所需的全部参数一次列清。
> 口径：pong 的断言来自 `patches/xnu/zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-touch-console.patch`；
> K60 的实测值来自 `D:/Android/k60-ios/AGENT-COORDINATION.md:1379,1778,1792`（设备 adb 6033dbec 实测）。

## 1. pong 驱动的硬依赖（原文）

```
:58   SecureDTLookupEntry(NULL, "/arm-io/pong-touch", &entry)     ← DT 节点路径
:59-62 property: spi-base / tlmm-base / gcc-base / rsc-base / cmd-db-base / gpio-offset / pins[6] / max-x / max-y
:63-65 断言: se_phys==0x990000 && tlmm_phys==0xf000000 && gcc_phys==0x100000 &&
             rsc_phys==0x17a20000 && cmd_db_phys==0x80860000 && gpio_offset==0x100000 &&
             pins=16,17,18,19,21,20 && max_x==1080 && max_y==2412
:109-110 PIN_INT=pins[4]=21   PIN_RESET=pins[5]=20
:294     GENI SE4（GCC_QUP0_SE4_DFSR = gcc + 0x274f8）
```

## 2. K60 实测值 vs pong（逐项）

| 属性 | pong 断言 | K60 | 依据 | 结论 |
|---|---|---|---|---|
| `spi-base` | `0x990000` | `spi@990000`（GENI SPI，CS0，15 MHz） | AGENT-COORDINATION:1379 | ✅ **相同** |
| `pins[4]`（INT） | `21` | GPIO 21 | 同上 | ✅ **相同** |
| `pins[5]`（RESET） | `20` | GPIO 20 | 同上 | ✅ **相同** |
| `max-x` / `max-y` | `1080` / `2412` | **`14400` / `32000`**（10× 面板；live FDT `goodix,panel-max-x=0x3840`=14400、`panel-max-y=0x7d00`=32000） | AGENT-COORDINATION:1379 | ❌ **必须改** |
| `avdd` | pins[0..3] 之一（未核实） | **GPIO 71** | AGENT-COORDINATION:1379 | ❌ 需核对 pins[0..3] 语义 |
| 固件 | pong 自带 | **`goodix_firmware_m11a`** | 同上 | ❌ 文件名/加载路径不同 |
| `tlmm-base` + `gpio-offset` | `0xf000000` + `0x100000` = TLMM `0x0f100000` | TLMM 基址 `0x0f100000` | sweet `NOTES.md`（K60 PON/GPIO 段）+ SM8475 SoC 常量 | ✅ 等价，**待实机核** |
| `gcc-base` | `0x100000` | SM8475 GCC = `0x00100000` | SoC 常量 | ⚠️ 待实机核 |
| `cmd-db-base` | `0x80860000` | 同（SM8475 cmd-db） | SoC 常量 | ⚠️ 待实机核 |
| `rsc-base` | `0x17a20000` | **未核实**；K60 曾出现 **RSC 块 `0x17a00000` 访问死**（`docs/ROUTE-A-18-DELTAS.md:13-15`） | 失败记录 | ⚠️ **必须先探针，不能直接写** |
| 总线 | GENI SE4 SPI | GENI SPI @0x00990000（=SE4），CS0，15 MHz | AGENT-COORDINATION:1379 | ✅ **相同** |
| 坐标换算 | 直接像素 | IC 0.1 mm → 面板 1440×3200 | 同上 | 需按 pong 的 `max_x` 逻辑换算 |

## 3. sweet 的 K60 触摸补丁 = 失败记录（不要当解法）

`sweet/xnu/patches/0240..0252` 只提供"踩过什么"，作者自述触摸仍未修好：

| 补丁 | 它做了什么 / 失败点 |
|---|---|
| `0240-k60-touch-pins-rpmh` | 从 pong 的 `bsd/dev/pong_goodix.c`（899 行）拆出；pm8350c LDO2 的 RPMh 投票（command DB + RSC TCS） |
| `0241-k60-touch-geni-spi` | QUPv3 SE4 @0x00990000、reg 0x4000、GIC SPI 605；"K60 与 pong 的 SPI 控制器完全一致" |
| `0242-k60-touch-goodix` | Berlin 与 GT9xx 两套 ABI 都实现，靠探针定夺；**型号从未在硬件上确认** |
| `0243-k60-touch-hid-thread` | HID 上报线程，分级 boot-arg，默认只到第 2 步 |
| `0244 / 0252` | rpmh 槽探针；**0252 修正：必须先 `ml_io_map()` 再读 TCS**（0244 在映射前读 0xd00 导致首票访问未映射地址） |
| `0246` | RSC 不安全时跳过 IOVDD 投票（`k60touchstage=2`） |
| `0248` | RSC 地址探测（现象级，**未定因**） |
| `0251` | `k60touchid=1` 机器可读 ID 回读，判据 `K60 TOUCH: ID: abi=berlin chip="911"` |

**结论**：RPMh/RSC 是这条路上唯一真正的坑，且 K60 侧尚未定因；其余（GENI/引脚/HID）与 pong 一致。

## 4. 首次上机的安全顺序（只读优先）

1. 启用 `pong-touch-console`（先按 `docs/GPU-ENABLE-PLAN.md` 确认 series 顺序），把断言里 `max_x/max_y` 改成 14400/32000，**并把 rsc 相关路径暂时禁用**（等价 sweet 的 `0246`）。
2. 只跑到"读芯片 ID / 固件版本 + 找 touch report 地址"：pong 的判据行是
   `goodix: chip "…", firmware "…"`（`:716`）与 `goodix: touch report at 0x…, coordinates up to …`（`:746`）。
3. 确认 `rsc-base` 可读之后，再开 TCS/RPMh 投票；否则会重演 `0x17a00000` 访问死。
4. 最后才启用 HID 上报线程。

## 5. 未核实（上机前必须闭合）

- `pins[0..3]` 的语义（pong=16,17,18,19）与 K60 `avdd=71` 的对应关系；
- `rsc-base` 的真实基址（`0x17a20000` 是否适用于 K60）与可读性；
- `cmd-db-base` / `gcc-base` 是否真是 SM8475 SoC 常量；
- 触摸 IC 的确切型号（Berlin 家族确定，GT9916 只是 DT compatible 的板级假设；`goodix_firmware_m11a` 文件本体未拿到）。
