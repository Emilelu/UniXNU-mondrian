# 02 · 官方依据（SM8475 / Qualcomm TSENS v2）

本篇回答"凭什么这么做"。官方依据分三层，逐层给可核查引用：

| 层 | 内容 | 状态 |
|---|---|---|
| ① 设备树绑定（DT contract） | `Documentation/devicetree/bindings/thermal/qcom-tsens.yaml` | **已取得**，且第 3 个示例与 K60 tsens0 完全一致 |
| ② 上游内核驱动（寄存器语义） | `drivers/thermal/qcom/tsens.c`、`tsens-v2.c` | **已取得**，含完整寄存器偏移与换算路径 |
| ③ SM8475 SoC 数据手册 / TRM | Qualcomm 内部文档 | **未找到公开版本**（见 §4，不编造章节号） |

本地副本（供复核，均可从下面的 URL 重新下载）：

```
/mnt/e/k60-work/thermal-refs/qcom-tsens.yaml    11884 B / 413 行
/mnt/e/k60-work/thermal-refs/tsens-v2.c          4537 B / 131 行
/mnt/e/k60-work/thermal-refs/tsens.c            34575 B / 1348 行
```

下载源（v6.6 标签，jsdelivr 镜像；raw.githubusercontent 会 429，git.kernel.org 直连失败）：

- binding: <https://cdn.jsdelivr.net/gh/torvalds/linux@v6.6/Documentation/devicetree/bindings/thermal/qcom-tsens.yaml>
- v2 驱动: <https://cdn.jsdelivr.net/gh/torvalds/linux@v6.6/drivers/thermal/qcom/tsens-v2.c>
- 公共驱动: <https://cdn.jsdelivr.net/gh/torvalds/linux@v6.6/drivers/thermal/qcom/tsens.c>
- 上游文档入口: <https://docs.kernel.org/driver-api/thermal/sysfs-api.html>（generic thermal，不涉及 QCOM IP 细节）

---

## 1. 层①：DT 绑定 `qcom-tsens.yaml`

### 1.1 K60 的 compatible 在不在枚举里

`qcom-tsens.yaml:55-68` 的 v2 枚举含 `qcom,sm8450-tsens`（:66）、`qcom,sm8550-tsens`（:67），
**没有 `qcom,sm8475-tsens`**，最后一行是通用 fallback `const: qcom,tsens-v2`（:68）。

K60 的 DT 只写了 `compatible = "qcom,tsens-v2"`（mondrian.dts:16439 / :16449）—— 落在 fallback 上，
合法。上游意义：走 `data_tsens_v2`（`tsens-v2.c:107-116`），即 v2 通用参数，无 SoC 专属 quirks。

### 1.2 **binding 的示例 3 就是本板这个控制器**（关键证据）

`qcom-tsens.yaml:382-396`：

```yaml
# Example 3 (for any platform containing v2 of the TSENS IP):
tsens3: thermal-sensor@c263000 {
    compatible = "qcom,sdm845-tsens", "qcom,tsens-v2";
    reg = <0xc263000 0x1ff>,
          <0xc222000 0x1ff>;
    interrupts = <GIC_SPI 506 IRQ_TYPE_LEVEL_HIGH>,
                 <GIC_SPI 508 IRQ_TYPE_LEVEL_HIGH>;
    interrupt-names = "uplow", "critical";
    #qcom,sensors = <13>;
    #thermal-sensor-cells = <1>;
};
```

对照 K60（mondrian.dts:16438-16446）：TM 地址 `0xc263000`、SROT 地址 `0xc222000`、长度 `0x1ff`、
中断 SPI **506/508**（= DT 的 `0x1fa/0x1fc`）逐项相同，只有 `#qcom,sensors` 是 16 vs 13。
这不是巧合：地址与中断号是 SoC 级的固定布线，绑定文档直接用了同一组数。
→ **"TM 块 + SROT 块"的语义有官方文字依据，不是我们从同族机型猜的。**

### 1.3 required / 可选项对照（K60 是否满足）

| binding 要求 | 位置 | K60 DT | 结论 |
|---|---|---|---|
| `compatible` 命中 v2 枚举 | :55-68 | `"qcom,tsens-v2"`（:16439） | ✅ 走 fallback |
| `reg` 两段（TM、SROT） | :80-83；含 tsens-v2 时 required（:290-291） | `<0xc263000 0x1ff 0xc222000 0x1ff>`（:16440） | ✅ 两段齐 |
| `interrupts` + `interrupt-names`，2 项 | :85-92；v2 要求 uplow+critical（:229-263） | `:16442-16443` | ✅ 两中断两名字 |
| `#qcom,sensors` 1..16 | :209-214 | `0x10`（:16441） | ✅ 16 = 上限 |
| `#thermal-sensor-cells` | required（:222-227） | `<1>`（:16444） | ✅ |
| `nvmem-cells` / `calib` 系列 | :93-117（可选，required 列表里**没有**） | 不存在 | ✅ 合法（calibrationless） |
| `clocks` | 全文无此属性 | 不存在 | ✅ 不需要 |
| `additionalProperties: false` | :293 | 节点里没有多余属性 | ✅ |

**这张表就是"我们的 DT 是合规的官方形状"的完整证明**，也是第 5 步（方案）能用上游语义实现的依据。

---

## 2. 层②：上游驱动 —— 寄存器语义与读数路径

### 2.1 v2 IP 的寄存器偏移（`tsens-v2.c:12-27`，全表）

| 偏移 | 宏 | 含义 |
|---|---|---|
| `0x0000` | `SROT_HW_VER_OFF` | 版本：major[31:28] minor[27:16] step[15:0]（`:56-58`） |
| `0x0004` | `SROT_CTRL_OFF` | bit0 = `TSENS_EN`，bit1 = `TSENS_SW_RST`（`:60-61`） |
| `0x0004` | `TM_INT_EN_OFF` | 中断使能 [2:0]（`:66`，注意与 SROT_CTRL 同偏移不同块） |
| `0x0008` | `TM_UPPER_LOWER_INT_STATUS_OFF` | [15:0]=lower 各传感器、[31:16]=upper（`:74,77`） |
| `0x000c / 0x0010` | `..._CLEAR_OFF` / `..._MASK_OFF` | 同上，写 1 清 / 1 屏蔽 |
| `0x0014` | `TM_CRITICAL_INT_STATUS_OFF` | [15:0] critical；bit30 `CC_MON_STATUS`、bit31 `WDOG_BARK_STATUS`（`:80,85,88`） |
| `0x0018 / 0x001c` | `CRITICAL_INT_CLEAR` / `_MASK` | 同上 |
| `0x0020` | `TM_Sn_UPPER_LOWER_THRESHOLD_OFF` | 每传感器 4 字节：[11:0] low、[23:12] up（`:69-70`） |
| `0x0060` | `TM_Sn_CRITICAL_THRESHOLD_OFF` | 每传感器 4 字节：[11:0] critical（`:71`） |
| `0x00a0` | `TM_Sn_STATUS_OFF` | 每传感器 4 字节，见下表（`:94-101`） |
| `0x00e4` | `TM_TRDY_OFF` | bit0：1=ready（`:104`） |
| `0x013c` | `TM_WDOG_LOG_OFF` | [7:0] watchdog bark 计数（`:91`） |

`TM_Sn_STATUS`（每传感器 4 字节）位域 **官方定义**（`tsens-v2.c:94-101`）：

| 位 | 字段 | 用途 |
|---|---|---|
| [11:0] | `LAST_TEMP` | **最近一次温度，unit = 0.1℃，有符号（12 位补码）** |
| [16] | `MIN_STATUS` | 曾低于 MIN 阈值 |
| [17] | `LOWER_STATUS` | 曾低于 lower 阈值 |
| [18] | `UPPER_STATUS` | 曾高于 upper 阈值 |
| [19] | `CRITICAL_STATUS` | 曾高于 critical 阈值 |
| [20] | `MAX_STATUS` | 曾高于 MAX |
| [21] | `VALID` | **1 = LAST_TEMP 有效** |

### 2.2 温度换算：官方一行代码

`tsens.c:318` 注释 "Return sign-extended temperature in mCelsius"，`:328` 函数 `tsens_hw_to_mC()`，
关键的 `:346-347`：

```c
/* deciCelsius -> milliCelsius along with sign extension */
return sign_extend32(temp, resolution) * 100;
```

`resolution` = 11（LAST_TEMP 的 [11:0]，即符号位是 bit11）。所以：

```
temperature_mC = sign_extend_12(raw & 0xfff) * 100
temperature_C  = sign_extend_12(raw & 0xfff) / 10.0
```

**这是"不需要标定系数"的官方文字依据**：v2 的 status 字里就是 0.1℃ 单位的温度，不是 ADC code。
（"adc=0" 见 `tsens-v2.c:35`；只有 adc=1 的老 IP 才走 `degc_to_code()/code_to_degc()`，`tsens.c:290-315`。）

### 2.3 标定属性缺失时会发生什么：calibrationless

`tsens.c:131-152`（`tsens_read_calibration()`）在 DT 没有 nvmem 时走 default 分支：

```c
dev_dbg(priv->dev, "calibrationless mode\n");   /* :147 */
...
p1[i] = 500;                                   /* :149 */
p2[i] = 780;                                   /* :150 */
```

`p1/p2` 只喂给 `compute_intercept_slope()`（`:258-288`）算 slope/offset，而 slope/offset 只用于
`tsens_mC_to_hw()` 编程硬件阈值（`:1222-1225`）—— **读数路径完全不使用它们**。
→ K60 缺 `nvmem-cells` 是合法且常见的配置；它只意味着"如果我们自己写 trip 阈值，阈值精度只能用默认
标定点"，而本阶段我们**不写任何阈值**，所以无影响。

### 2.4 读数路径（要照抄的部分）

`tsens.c:750-779 get_temp_tsens_valid()`：

1. 轮询 `VALID` 位（每次间隔 1us，超时 20ms）；注释 `:763-767` 说明 VALID 在 6 个 AHB 周期（≈360ns）
   内会为 0 —— 即"读到 VALID=0 是正常的短暂状态，必须重试"。
2. `VALID=1` 后再读 `LAST_TEMP`，避免读到半更新的值。
3. 返回值再经 `tsens_hw_to_mC()` 换算。

### 2.5 初始化：硬件使能由固件负责（对我们最重要的一条）

`tsens.c:890-981 init_common()`：

- `:901-916`：DT 有 2 个 resource（本板就是）→ `priv->tm_offset = 0`，SROT 单独 `devm_ioremap_resource`；
  老 DT 只给一个连续 2K 块时 `tm_offset = 0x1000`（`:919`）。
- `:950-962`：版本 > VER_0_1 时从 **SROT** 块读版本字段（`SROT_HW_VER`）。
- `:970-979`：**只有 VER_0 才由驱动写 `TSENS_EN=1`**；v2 只读，若为 0 直接
  `dev_err("device not enabled")` + `-ENODEV`。

推论（明确标注为推论，需上机验证）：在 K60 上，TSENS 的使能是 XBL/固件做的，XNU 侧不该也无法打开它。
如果 `0xc222000+0x4` 的 bit0 读为 0，说明"这块 IP 没被固件启动"，读数不可信 —— 这就是 01 篇 §10 的
第 1 条 prediction。

### 2.6 v2 IP 的能力参数（`tsens-v2.c:31-39`）

| 参数 | 值 | 意义 |
|---|---|---|
| `ver_major` | `VER_2_X` | 版本族 |
| `crit_int` | 1 | 有独立 critical 中断 |
| `combo_int` | 0 | 不用组合中断 |
| `adc` | **0** | **不做 ADC 换算**（读数即温度，见 §2.2） |
| `srot_split` | 1 | **SROT 与 TM 分离**（要求 DT 两段 reg） |
| `max_sensors` | 16 | 单控制器上限 |
| `trip_min/max_temp` | `-40000` / `120000` | m°C，编程阈值时的合法区间 |

---

## 3. 官方依据能支持什么、不能支持什么

**支持（本阶段就要用）**：

- 只要 TM 块可映射、`TSENS_EN=1`、`VALID=1`，就能用一个 32 位 load 得到 0.1℃ 精度的温度；
- 32 个传感器的编号由 DT 的 `thermal-sensors = <&tsensN idx>` 决定（01 篇 §3）；
- 纯只读访问不会破坏硬件状态（我们不写 `CLEAR`/`MASK`/`THRESHOLD`，也不碰 `SW_RST`）。

**不支持（本阶段不做，也不许假装能做）**：

- ❌ 写 trip 阈值/中断：那需要 `THRESHOLD` 寄存器编程 + 标定（本板 calibrationless，阈值精度无保证），
  且中断要到 GIC/XNU 侧接（我们连 GIC 驱动都没有），见 03 篇"不可复用"。
- ❌ 用 QFPROM/efuse 自己算标定：v2 + adc=0 的读数路径不需要它；编造系数会引入误差。
- ❌ 用 thermal-engine 的 125℃ trip 做保护：那是用户态守护进程策略，XNU 侧没有对应物。

---

## 4. 层③：SM8475 数据手册 —— 未找到公开章节（不要编号）

我实际查过的范围：

1. 本仓库全部文档：`grep -iE 'sm8475.{0,40}(trm|manual|datasheet)' docs/**/*.md` → **零命中**。
2. 上游内核树：binding 的 compatible 枚举里没有 `qcom,sm8475-tsens`（`qcom-tsens.yaml:55-68`），
   也没有任何 sm8475 专属 tsens 文档。
3. 公开网络：Qualcomm SM8475 的 TRM/数据手册不公开发行（需 NDA），kernel.org/git.kernel.org 上只有
   驱动与绑定，没有寄存器手册。

**结论：不存在可引用的"SM8475 数据手册第 X 章"。** 本篇不写章节号，也不假装有。
替代依据是层①+层②：绑定规定了 DT 契约，驱动规定了寄存器语义，两者合起来对"只读温度"这件事是
完备的、可枚举的、可复核的 —— 且 §1.2 已证明绑定示例用的就是本板同一组地址/中断。

若将来需要层③（例如要写阈值、要读 CC_MON/WDOG 细节），才必须找高通内部文档；那是另一条取证路径，
必须先登记 blocker，不能用"同族机型推测"替代。

---

## 5. 引用清单（可直接点击复核）

- <https://cdn.jsdelivr.net/gh/torvalds/linux@v6.6/Documentation/devicetree/bindings/thermal/qcom-tsens.yaml>
  → `:55-68` compatible、`:80-83` 两段 reg、`:85-92` 中断、`:93-117` nvmem 可选、`:209-214` sensors 上限 16、
  `:222-227` required、`:229-263` v2 强制两中断、`:290-291` 强制 reg、`:293` additionalProperties、
  `:382-396` **示例 3 = 本板控制器**。
- <https://cdn.jsdelivr.net/gh/torvalds/linux@v6.6/drivers/thermal/qcom/tsens-v2.c>
  → `:12-27` 偏移表、`:31-39` 能力参数、`:53-105` 位域定义、`:94-101` STATUS 位域、`:107-116` ops。
- <https://cdn.jsdelivr.net/gh/torvalds/linux@v6.6/drivers/thermal/qcom/tsens.c>
  → `:131-152` calibrationless、`:290-315` ADC 换算（不适用）、`:318-348` `tsens_hw_to_mC()`、
  `:750-779` `get_temp_tsens_valid()`、`:890-981` `init_common()`（两段 reg / 版本 / TSENS_EN）、
  `:1222-1225` 阈值编程（本阶段不用）。
- 板级事实引用见 `01-SAME-HARDWARE.md`（`mondrian.dts` 行号）。
