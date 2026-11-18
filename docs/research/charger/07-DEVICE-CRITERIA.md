# 07 — ⑧ 真机验收判据（订阅 / 四属性 / Android 同窗口）

> 目的：lease 一落地，Lead 直接飞、直接 grep 判定，不必回来问。
> 边界：**只读判据**——不改驱动、不改内核、不出镜像；boot 动作只在 Lead 手里。
> 取材：格式串逐字抄自源码（P-204，行号对 `feat/charger @ 08b08fd`）；阈值按 Lead 2026-11-15 23:27 的收口口径原样入档。
> 执行顺序钉死：C1 订阅 → C2 四属性 → C3 Android 对照。**C1 不过不读 C2；C2 不过不做 C3。**

## 0. 判据总表

| # | 判据 | 证据行 | 成立条件 | 最少命中 |
| --- | --- | --- | --- | --- |
| C1 | 订阅成立 | `K60Battery.cpp:276`（channel up）+ `:209-214`（sample 行尾 `subscribed=`） | `subscription-ack=1/16`，且随后出现 `subscribed=1` | 1 行 channel up + 1 行 sample |
| C2 | 四属性可读 | `K60Battery.cpp:209-214` | 电压/电流/容量/温度四条各在 §2.2 区间 | 1 行（首帧） |
| C3 | 与 Android 同窗口一致 | 两侧样本配对 | 充电状态一致、时刻差 ≤10 s、四条偏差 ≤ 阈值 | ≥3 对有效样本 |

**启动前置**：同一份 usblog 必须含 `K60Handoff: published authenticated PAS1 epoch=N bytes=104 flags=15`
（`K60HandoffRuntime.cpp:57`，在兄弟树 k60-adsp-handoff / k60-gates / k60-display / k60-lead；本树 k60-charger 只有消费者）。
没有这一行就不要判 C1：Battery 侧必然打 `K60Battery: blocked rc=-4: ...`（`K60Battery.cpp:432`），
记 **INVALID(no lease)** 而不是 FAIL。当前实测 `adsp-20261115e` 正是这个形态
（`K60ADSP owner stage=1 rc=-1000`，`K60AdspOwnerStages.c:71`），缺口是 `K60AdspPlatform.c` 的 21 个 K60OwnerOps
回调实现（已派 adsp 线）。

## 1. C1 订阅成立

### 1.1 证据行（逐字）

channel up（`K60Battery.cpp:276-277`，由 `K60PmicGlink` 的 ready 回调 `state()` 触发）：

```
K60Battery: actual PMIC_RTR_ADSP_APPS channel up; measured sign=%d subscription-ack=%u/%u
```

sample 行尾（`K60Battery.cpp:209-214`，最后一个 `%u` 就是 `manager.subscribed`）：

```
K60Battery: %s sample=%u SOC=%u.%02u%% charge=%u/%umAh design=%umAh cycles=%u voltage=%umV current=%dmA temp=%d.%02uC external=%d charging=%d full=%d subscribed=%u
```

### 1.2 这两行各证明什么（P-204：配置 ≠ 回包）

- `subscription-ack=%u/%u` 打印的是 `manager.notify_reply_type` / `notify_reply_bytes`（`:277` 直接取字段），
  即**配置常量**。它证明生成器把 `(1,16)` 写进内核、`k60_battmgr_init()` 接受了这对值
  （白名单 `K60Battmgr.c:47-56`，只认 `type ∈ {1,2}` 且 `bytes ∈ {12,16,24,28}`；见 `06-SUBSCRIPTION-CONSTANT.md` §1）。
  **它不能证明 ADSP 回过包。**
- `subscribed=1` 才是 ACK 被接受的后果：`K60Battmgr.c:162-171` 要求 `opcode == 4`、`flight == FLIGHT_SUBSCRIBE`、
  `bytes == 16`、`type == 1`，且 `data[12..16)` 逐 4 字节全 0；满足才 `subscribed = 1`。
  任一 4 字节非 0 → `errors++`、`flight = FLIGHT_NONE`，订阅失败但通道保留（继续轮询属性）。
- `subscribed` 没有独立日志行，**只能从 sample 行读**；因此 C1 的“ACK 真的收到”证据依赖至少一帧有效 sample。

### 1.3 通过条件

1. ≥1 行 `... channel up; measured sign=±1 subscription-ack=1/16`；同一 epoch 内重复出现时每次都必须 `1/16`。
2. 该行之后 ≤10 s 内出现首帧 sample，且行尾 `subscribed=1`（`kRefreshMs = 5000`，`K60Battery.cpp:25`，一轮刷新 5 s）。

`sign` 必须 `+1` 或 `-1`；`0` 表示极性未定，`k60_battmgr_sample()` 会直接返回 0（`K60Battmgr.c:216`），
后面 C2 必然打不出 sample 行。

### 1.4 失败形态（照 grep，逐字）

| 观察到的行 | 出处 | 含义 / 下一步 |
| --- | --- | --- |
| `subscription-ack=0/0` | `K60Battery.cpp:276` | 常量没进内核（生成器没跑 / 还是旧镜像）：订阅静默关闭，只剩属性轮询 |
| `subscribed=0` 且 `errors=` 递增 | `:209-214`、`:295-297` | ACK 被拒：type/bytes/result 不符（`K60Battmgr.c:162-171`）；核对 06 的取值是否被别处覆盖 |
| `no publication sample=%u fresh=%x errors=%u sign=%d raw-current=%d raw-temp=%d` | `:295-297` | 本轮不完整/不合格；`sign=0` 或 raw 值直接指出是哪条字段没到 |
| `blocked rc=-4: no authenticated exclusive PAS1/SMEM/GLINK platform handoff; ...` | `:432` | lease 没发布 → INVALID(no lease)，先修 ⑧ 前置 |
| `physical transport initialization rejected error=%d; no publication` | `:366` | `transport.open()` 失败：desc/tx/rx 与 handoff 不符 |
| `GLINK epoch never became ready; platform owner must supply a new authenticated session` | `:318` | 握手超时（`kChannelMs = 5000`，`:25`） |
| `physical PMIC request timeout op=%x property=%u; quarantining old channel` | `:333-334` | 无回包 → `poisoned=1`（`K60Battmgr.c:194-200`），必须重开 channel |
| `physical transport stopped error=%d; no DSP/FIFO reset` | `:311` | lease 失效 / 被回收 |
| `hardware sample unavailable (<why>); preserving last measured values as stale` | `:141` | 有旧值但本轮作废；`why` 取值见 §2.4 |

**正向前置行**（出现即可继续）：
`K60Battery: adopting authenticated PAS1 GLINK epoch=%llu desc=%x tx=%x/%x rx=%x/%x (no FIFO reset)`（`K60PmicGlink.cpp:128-129`）。

## 2. C2 四属性可读（各自下限）

### 2.1 sample 行字段映射（`K60Battery.cpp:209-214` → `K60BatterySample`）

| 位置 | 格式 | 来源（`K60Battmgr.c` 行） | 说明 |
| --- | --- | --- | --- |
| 1 | `%s` | `:210` | `physical source published`（首帧）/ `physical source updated` |
| 2 | `sample=%u` | `manager.generations`（`:144`） | 完整轮次计数（一轮 18 字段） |
| 3-4 | `SOC=%u.%02u%%` | `capacity_hundredths / 100`、`% 100`（`:229`） | 0.01 % 分辨率 |
| 5-7 | `charge=%u/%umAh`、`design=%umAh` | `current_mah` / `full_mah` / `design_mah`（`:230`、`:233`） | `current_mah` 由 SOC×full 换算，不是电量计原始计数 |
| 8 | `cycles=%u` | `:238` | |
| 9 | `voltage=%umV` | `voltage_mv = value / 1000`（`:235`） | wire 单位 µV |
| 10 | `current=%dmA` | `current_ma = sign × value / 1000`（`:236`） | 符号见 `K60Battmgr.h:52`：+1 = wire 充电正 |
| 11-12 | `temp=%d.%02uC` | `temperature_hundredths`（`:238`、`:212-213`） | 整数部分 `%d`、小数取绝对值 `%02u`；负温显示成 `-3.05` |
| 13-15 | `external=%d charging=%d full=%d` | `:223-228` | 充电状态机：`status==1` 充电、`==4` 满 |
| 16 | `subscribed=%u` | `manager.subscribed` | C1 的证据位 |

**只在状态变化时打印**（`K60Battery.cpp:207-208`：`first || external/charging/full/capacity 变化`）。
稳态插着充电器时一锅只出一行——**不要因为只有一行就判失败**，要判的是这一行的四条属性对不对。
需要多行时靠插拔 USB（翻转 `external`）或 SOC 跨 1 %（翻 `capacity_hundredths`）触发。

### 2.2 通过区间（⑧ 验收窗口；与代码层强制范围分开）

| 属性 | 行内字段 | ⑧ 通过区间 | 代码层已强制（`K60Battmgr.c:106-124`，不过就丢字段） | 理由 |
| --- | --- | --- | --- | --- |
| 电压 | `voltage=%u` | **3300–5000 mV** | 2 000 000–5 500 000 µV（`:112`） | 3.3 V = 锂电空载下限；>5 V 说明 USB/PD 电压串进电芯模型 |
| 电流 | `current=%d` | **\|I\| 100–6000 mA** | −20 000 000–20 000 000 µA（`:113`） | <100 mA 在 ADC 噪声内不可判；6 A = 65 W 电芯能力上界 |
| 容量 | `SOC=%u.%02u` | **1.00–100.00 %**（100–10000） | 0–10000（`:111`） | 0 与“未初始化”不可分；`status==0` 还会被 `K60Battmgr.c:218` 直接拒帧 |
| 温度 | `temp=%d.%02u` | **0.0–60.0 °C**（0–6000） | −4000–9000（`:114`） | 0.00 与传感器未就绪不可分；60 °C 接近充电保护 |

补充（不单独判，但出现即说明字段矛盾）：

- `charge=<current>/<full>` 必须 `current ≤ full`（`:234` 有截断，但极端值说明 SOC 与 full 不自洽）；
- `full×2 ≥ design ≥ full×2/3`（`:220` 的样本合格条件，不符直接不出 sample）；
- 充电时 `charging=1` 与 `external=1` 必须同时成立（`:227-228`）。

### 2.3 命中次数

- **最低 1 行**（首帧 `physical source published`），四条属性全部落在 §2.2 区间即 C2 通过。
- **理想 ≥3 行**（同一份 usblog），用于看符号与温漂；只有插拔或 SOC 跨 1 % 才会多出行，凑不满不是失败。
- 每行都要 `external/charging` 与当次操作一致；`subscribed=1` 至少出现在首帧。

### 2.4 失败形态

| 行 | 出处 | 含义 |
| --- | --- | --- |
| `hardware sample unavailable (incomplete/unqualified sample)` | `:141` + `:294` | `k60_battmgr_sample()` 返回 0：某字段未 valid，或 `poisoned/sample_dirty` |
| `no publication sample=%u fresh=%x errors=%u sign=%d raw-current=%d raw-temp=%d` | `:295-297` | 同上，且直接给出 `last_fresh` 位图与 raw 值——先看 `raw-current` / `raw-temp` 是否为 0 |
| `measured battery absent; last pack measurements are unavailable` | `:160` | `present == 0`（`K60Battmgr.c:211-215`）：电池没认到，只剩 adapter 属性 |
| `hardware sample unavailable (platform lease invalidated)` | `:309` | lease 失效 |
| `hardware sample unavailable (GLINK FIFO/intent backpressure)` | `:323` | 发送侧背压（`QcomGlinkAgain`，`:258-261`） |
| `hardware sample unavailable (PMIC response timed out)` | `:336` | 超时后被 quarantine |
| `hardware sample unavailable (GLINK send refused)` | `:263` | send 非 `QcomGlinkOk` |
| `hardware sample unavailable (property allocation failed)` | `:149`、`:181` | 不可变属性对象分配失败，旧样本保持 |
| `source setup rejected; no power-source publication` | `:441` | `begin()` 失败（transport / timer 初始化） |
| `captured board config invalid rc=%d; no hardware access/publication` | `:424` | 板级配置解析失败 |

## 3. C3 与 Android 侧同窗口对比

### 3.1 Android 侧取值（两条通道任选一条，证据里注明用了哪条）

```
adb shell dumpsys battery            # level / voltage(mV) / temperature(0.1 °C) / status
adb shell cat /sys/class/power_supply/battery/{capacity,voltage_now,current_now,temp,status}
```

sysfs 单位换算：`voltage_now` µV ÷1000 → mV；`current_now` µA ÷1000 → mA；`temp` 0.1 °C ÷10 → °C；`capacity` 直接是 %。
`status`：2 = Charging，3 = Discharging，4 = Not charging，5 = Full。

真值锚点（`docs/engineering/ANDROID-HW-TRUTH.md:68-77`，2026-11-15 实测）：capacity 100、temp 358（35.8 °C）、
status Charging、current_now 836 mA、voltage_now 4 333 mV、USB CDP online。

**第三条通道：Android 自己的 dmesg**（没有 root/adb 取 sysfs 时用）。判据器直接吃这份 dmesg，
匹配行是充电器驱动打的电池帧（`/mnt/e/k60-work/evidence/wifi-trial/dmesg-android-20261114.txt` 实测 117 行）：

```
[ 6380.688186] BATTERY_CHG: handle_message: [ADSP] fg_update_status:: ssoc:100, rsoc:99,
    raw_soc:9806, vbat:4332, ibat:350, temp:286, ffc:0, rm:4412, bf:4499, bc:3, ...
[ 6380.100000] BATTERY_CHG: xm_charger_debug_info_print_work: usb_present: 1
```

单位与 sysfs **不同**：`vbat` 已是 mV、`ibat` 已是 mA、`temp` 是 0.1 °C、`ssoc` 是 %。两个字段缺失，
必须显式说明而不是猜：① dmesg 不打印电池 `status`，充电状态改用 `usb_present`（供电有无）代替，
电流符号因此不校验；② dmesg 只有 `[ 6380.688186]` 这种相对秒，没有 wall clock，配对窗口按 dmesg
相对秒圈定（`--window-start 6380 --window-end 6420`），不是 epoch 秒。`--android` 按内容自动识别两种输入。

### 3.2 配对规则（任一不满足 → 该对作废，不是判据失败）

1. **同一供电来源**：两侧都记下供电（主机 USB 口 / 充电头 / 无线），不同则作废。
2. **充电状态一致**：Android `status ∈ {2,5}` ↔ XNU `charging=1` 或 `full=1`；Android `{3,4}` ↔ XNU `charging=0 且 full=0`。
3. **时刻差 ≤10 s**：Android 侧记 `date +%s`，XNU 侧用采到该行的时间；无时间戳就用同一 usblog 的采集窗口，超窗即作废。
4. **电流窗口**：只在 XNU `|current| ≥ 100 mA` 的稳态窗口比电流；否则电流项跳过，其余三条照比。

### 3.3 阈值（Lead 口径，原样）

| 属性 | 阈值 | 备注 |
| --- | --- | --- |
| 电压 | **±60 mV** | 逐对比较 |
| 电流 | **±150 mA** | 仅 `\|I\| ≥ 100 mA` 稳态；先按充电状态归一化符号 |
| 容量 | **±3 个百分点（pp）** | 两侧都按 % 比（XNU 用 `SOC=%u.%02u`） |
| 温度 | **±3 °C** | Android 0.1 °C ÷10 后比 |

符号约定：XNU `current_ma` 已按 `charging_current_sign` 归一化，`K60Battmgr.h:52` 记 **+1 = wire 充电正、-1 = wire 放电正**；PMIC-GLINK 参考实现 `ShengBattmgr.c:228` 的 `-V(BmCurrent)/1000` 表明其固件按放电正汇报，故 K60 默认 **-1**。
充电时两侧应同号为正；**符号方向不一致直接 FAIL**（比数值超差更早暴露 sign 常量错）。

### 3.4 命中次数

- **≥3 对有效样本**（三次 boot，或一次 boot 内三次插拔翻转状态）。
- 任一对四条全在阈值内才算一对；30 min 内凑不满 3 对 → 判 **INVALID(样本不足)**，不判 FAIL。
- 任一对超阈值 → 该对作废并记一行越界明细；连续 3 对同向越界（例如电压恒低 200 mV）→ **FAIL(systematic)**。

### 3.5 失败形态

| 现象 | 判定 | 处理 |
| --- | --- | --- |
| 只有 1–2 对 | INVALID | 补样本 |
| 充电状态在窗口内翻转 | 该对作废 | 选稳态窗口重取 |
| 电压差 >60 mV 且两侧电流 ≈0 | 该对作废 | 空载/刚插拔，等 30 s 重取 |
| 容量差 >3 pp 且温度差 <1 °C | 该对作废 | 采样不同步（充电中 SOC 会爬），重取；持续则 FAIL |
| 充电时两侧电流符号相反 | **FAIL** | `charging_current_sign` 常量或 ADSP 极性错 |
| 温度差 >3 °C 但 `\|ΔI\| < 100 mA` | 该对作废 | 低电流下温升判据不成立 |

## 4. 判定与证据归档

- **PASS** = C1 ∧ C2 ∧ C3 全部成立；**FAIL** = 任一出现系统性/符号失败；**INVALID** = 前置缺失或样本不足。

**判据可执行化**：C1–C3 由 `scripts/judge-battery.py` 判定。输入一份
`console.log`（或整个 usblog 目录，自动找 `console.log`），每条判据单独一行
`C1 订阅成立 : PASS (命中 1 次, 证据 :3, :4)`，末行固定
`TOTAL: n PASS / n FAIL / n INVALID`（没有 TOTAL 行等于没跑过）。

```
python3 scripts/judge-battery.py --log E:/k60-work/evidence/usblog-20261116-xxxxxx
python3 scripts/judge-battery.py --log <usblog-dir> --android android-samples.tsv \
    --window-start 1763000000 --window-end 1763001800
python3 scripts/judge-battery.py --log <usblog-dir> --android dmesg-android.txt \
    --window-start 6380 --window-end 6420
```

**顺序不可颠倒**：C3 只在 C1/C2 都 PASS 时才评估，否则 `INVALID` 并写明
「先判有没有，再判差多少」——对着一条从未订阅成功的日志算差值，会得到一组
自信的、凭空来的数字。C3 通过时除了 PASS 还打一行最大实测差值
（`|ΔV|/±60mV、|ΔSOC|/±3pp、|ΔT|/±3C、|ΔI|/±150mA`），失败时每个越界对给出
`:行号 ΔV=…mV/±60mV` 形状的明细；没有两侧同时 ≥100 mA 的窗口时明确写「|ΔI| 未比」。
`--android` 两种输入按内容自动识别（§3.1 的转写 TSV 与 Android dmesg）。

自测 `python3 scripts/tests/test-judge-battery.py`（20 例：lease 未发布的 INVALID、
`subscribed=0` 的 FAIL、只有首帧不判失败、电压越界、`temp=0.00C` 视为未就绪、
`subscription-ack=0/0` 与 `2/24` 两种常量形态、C3 四种结局、C3 被 C1 拦住、
dmesg 通道 PASS 与供电不一致 FAIL、两侧都有稳态负载时才比电流）。两个离线限制写在
脚本 docstring 里：IOLog 行没有时间戳，所以 C1 的 ≤10 s 窗口只能按行序判；
C3 的配对时刻只能靠 `--window-start/--window-end` 圈定。
- 最小证据集：① 一份完整 usblog（含 handoff 行、channel up 行、全部 sample 行）；② Android 侧命令原文 + 时间戳；③ 下表填好的对照表。

grep 模板：

```
grep -nE 'K60Handoff: published authenticated|K60ADSP owner stage=|K60Battery: actual PMIC_RTR_ADSP_APPS|K60Battery: .* sample=|K60Battery: (blocked|no publication|physical transport|GLINK epoch|hardware sample|measured battery|source setup|captured board config)' usblog-*.txt
```

对照表模板：

| # | 时刻（两侧） | XNU V/mV I/mA SOC/% T/°C charging | Android V/mV I/mA level/% T/°C status | ΔV/ΔI/ΔSOC/ΔT | 判定 |
| --- | --- | --- | --- | --- | --- |
| 1 | | | | | |

## 5. 阈值与前置的入档说明

- 阈值来自 Lead 2026-11-15 23:27 的收口（电压 ±60 mV / 电流 ±150 mA 且仅 `|I| ≥ 100 mA` / 容量 ±3 pp /
  温度 ±3 °C / 两侧采样间隔 ≤10 s 且充电状态一致），本文件原样收录；改动需同步 reply md 并在 commit message 写明。
- C1 的 `(1,16)` 来自 `docs/research/charger/06-SUBSCRIPTION-CONSTANT.md` §0（ADSP handler `0x60155910` 逐指令）。
- ⑧ 的 device 段仍为 `done=false`；本文件只是判据，不改变 `EIGHT-STEPS.toml` 的状态。
