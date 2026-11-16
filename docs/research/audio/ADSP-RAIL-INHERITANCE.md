# ADSP LCX/LMX 供电继承：四个问题的取证（round 33，2026-11-16）

Lead 2026-11-16 08:08 的裁定：HR-01 **不放松**，但 `K60AdspBoard.c` 的 `resources_cb` 把两种
完全不同的情况合并成了一个返回值 `K60BoardUnsupported`(-63)——「轨已被 ABL/Android 投过、XNU 只是继承」
和「轨读回来是 0 / 不存在」在日志里长得一模一样，于是「DSP 起不来」永远无法区分是没电还是我们拒绝投票。
这与 P-190/P-204 同型：**用一个常量代替了本可测量的东西**。

这份文档的**第一步是只取证、不改代码**：按 Lead 的四个问题给出可核对的答案，并额外记录一条
决定实现位置的时序事实（第四节末尾）。Lead 2026-11-16 09:45 在两条出路中选了 B 之后，
**第二步（`resources_cb` 三态化 + 轨账本）已经落地**，现状见第五节。

## 一、问题 1：ADSP 在这块板上需要哪几条轨，resource id 是什么

### 1.1 设备树原文（本板，官方 FDT）

`sm8475-xiaomi-mondrian.dtb` 的 ADSP 节点（原文见 `docs/research/audio/VENDOR-ADSP-NODE.md:17-63`）：

```dts
remoteproc-adsp@03000000 {
        compatible = "qcom,cape-adsp-pas";
        cx-supply = <0x93>;
        cx-uV-uA = <0x180 0x00>;
        mx-supply = <0x94>;
        mx-uV-uA = <0x180 0x00>;
        reg-names = "cx\0mx";
        clocks = <0x20 0x00>;
        clock-names = "xo";
        qcom,qmp = <0x8c>;
        interconnects = <0x5a 0x2b 0x46 0x200>;
        interconnect-names = "crypto_ddr";
}
```

两个 phandle 解到（`E:/k60-work/scratch/dtb/mondrian.dts`）：

| phandle | 节点 | resource-name | 稳压器子节点 | 行 |
| --- | --- | --- | --- | --- |
| `0x93` | `rpmh-regulator-lcxlvl` | `lcx.lvl` | `regulator-pm8350-l8-level`（`pm8350_l8_level`） | `:5333-5345` |
| `0x94` | `rpmh-regulator-lmxlvl` | `lmx.lvl` | `regulator-pm8450-l1-level`（`pm8450_l1_level`） | `:6113-6125` |

别名表把这两条钉成 **LPI**（低功耗岛，即 ADSP 所在电源域）的 CX/MX：

```
:21177  VDD_LPI_CX_LEVEL = "/soc/rsc@17a00000/rpmh-regulator-lcxlvl/regulator-pm8350-l8-level"
:21288  VDD_LPI_MX_LEVEL = "/soc/rsc@17a00000/rpmh-regulator-lmxlvl/regulator-pm8450-l1-level"
```

### 1.2 与 Pong 的关系：同一对轨，不同 PMIC

Pong 的 `E:/k60-work/references/pong-power/PongAdsp.cpp:565-572` 按名字取的就是这两条：

```cpp
if (!readCmdDb(db) || qcom_cmd_db_find(db, sizeof db, "lcx.lvl", &gLcx) ||
    qcom_cmd_db_find(db, sizeof db, "lmx.lvl", &gLmx) ||
    qcom_rpmh_level_index(&gLcx, 0xffffffffu, &lcx) ||
    qcom_rpmh_level_index(&gLmx, 0xffffffffu, &lmx)) { ... }
if ((rc = vote(lcx, lmx))) { fail(StRails, rc); ... }
```

**结论 1**：K60 的 ADSP CX/MX **就是** `lcx.lvl` / `lmx.lvl` 这一对，与 Pong 同名同源；
差别在 PMIC 侧的具体器件（K60 = pm8350 l8 / pm8450 l1）。所以「抄 Pong 的轨名」是对的，
「抄 Pong 的地址或电平」是错的——地址必须从**本板** cmd-db 现取。

### 1.3 resource id：本板尚未测量

- DT 里 `qcom,rpmh-arc-regulator` 的 `regulator-min-microvolt = <0x10>`、
  `regulator-max-microvolt = <0xffff>`、`qcom,init-voltage-level = <0x10>`（`:5340-5342`、`:6120-6122`）
  是**档位索引**（ARC corner），不是毫伏。初值 16（0x10）。
- 本板**从未**在运行时读到过 `lcx.lvl` / `lmx.lvl` 的 cmd-db 记录：全证据库
  `grep -rh K60RAIL E:/k60-work/evidence` 只有三行（cmd-db magic、ldoc2=0x42c00、DRV-2 布局），
  没有 ADSP 轨；仓库里除 `scripts/tests/test-k60-pmic-rail.c:70,97` 的合成夹具外没有任何 ADSP 轨名。
- ⚠ `E:/k60-work/references/UniXNU-sheng/package/tests/qcom_adsp_host.c:450` 里的
  `0x30010` / `0x30020` 是**参考实现的宿主夹具值**，不是本板测量值，**不得**写进内核常量。

## 二、问题 2：已投票的状态能不能只读地读出来，从哪个寄存器/TCS 槽

能，有两条**互不相同**的只读来源，必须都读才有意义：

| 来源 | 读什么 | 证明什么 | HR-01 |
| --- | --- | --- | --- |
| cmd-db `0x80860000` | 按资源名取 `address` + 电平表 | 这条轨的**命令地址**（后续所有比较的基准） | 普通内存，安全，无限制 |
| DRV-2 `0x17a20000` + TCS 槽 | `cmd_addr` / `cmd_data` / `status` / `idle` / `cmd_enable` | **已保留的请求本身**（谁投了、投到几档） | 仅四条件同时满足时（见第四节） |

### 2.1 cmd-db：已实现、已上机

`drivers/PongPower/K60PmicRail.c:273-388` 的 `k60_rail_probe()` 是**目前唯一被批准的**受限只读实现
（`docs/ops/HARD-RULES.md:101-104`）。它 `ml_io_map_unmappable(0x80860000, 0x20000, 0x7)` 后打印
`K60RAIL cmd-db magic=%#x version=%u`、按名查表并打印 `K60RAIL ldoc2 address=%#x levels=%u ...`，
然后映射 DRV-2 并打印布局。第二步之后它在**同一次**读取里按 `cmd_addr` 命中反推 TCS 槽并读出 `cmd_data` 档位（`k60_rail_measure()` `:175`），把 lcx/lmx 四元组写进静态账本（`k60_rail_ledger_store()` `:226`）。**它只读 DRV-2 的布局字段与 TCS 槽里的命令/数据字，从不写任何寄存器。**

### 2.2 DRV-2 + TCS 槽：本仓库族里已有的只读先例

`E:/hackios/k60-wifi/patches/wifi/0003-drivers-PongWifi-k60-rsc-gate.patch:28-39` 在投票前做了一次
**纯只读**探测，用的正是同一套偏移：

```cpp
bool readable=rsc.open(0x17a20000,0x10000);
constexpr unsigned tcs4=0xd00+4*0x2a0;
id=rsc.r(0); caps=rsc.r(0xc); idle=rsc.r(tcs4+0x18); st=rsc.r(tcs4+0x3c);
const unsigned count=(caps>>12)&63,ncpt=(caps>>27)&31;
if(!readable||caps==0xffffffffu||id==0xffffffffu||((id>>16)&255)>=3||count<8||ncpt<1||!idle) fail;
```

判据含义（同 `docs/research/REFERENCE-INDEX.md:176` 与本板实测
`K60RAIL rsc drv_id=0x20700 version=2 stride=672 cmd=20 ctrl=0x14 enable=0x1c msgid=0x30 addr=0x34 data=0x38`）：
`drv_id` 主版本 2 → v2 布局；`count>=8`、`ncpt>=1` 是 TCS 数组与每槽命令数的下限；`idle` 表示该槽空闲。

### 2.3 ⚠ TCS 槽号：本板有两个互相矛盾的说法，不要猜

- `docs/research/touch/POWER-RPMH-LDOC2.md:33`：「**本板 TCS 编号 3（不是 4）**，yibiya 实测；
  DT 在 Android 上是 active0..2/sleep3..4，不要按 DT 推」。
- `docs/research/REFERENCE-INDEX.md:883-886` §14.5：Pong 用 `0xd00+4*0x2a0`（槽 4），
  而 live FDT 说 `qcom,drv-id=<2>`——两者不冲突（drv-id 选 DRV，槽号选 DRV 内的 TCS），但混抄会算错地址。

这两条说的是**不同外设**（触摸 IOVDD vs Pong 的通用投票）。ADSP 的 LCX/LMX 由谁、在哪个槽投的，
**本板没有测量**。所以实现时**不得写死槽号**：应按 `tcs = 0xd00 + slot*0x2a0` 遍历，
用「`cmd_addr` 是否等于 cmd-db 给出的资源地址」来**认出**是哪个槽，而不是先假定槽号再验证。

## 三、问题 3：什么算「证明已继承」

每条轨必须给出**四元组实测值**，缺一不算：

| 元素 | 含义 | 来源 |
| --- | --- | --- |
| resource id | cmd-db 里的 `address`（如 ldoc2 的 `0x42c00`） | cmd-db 按名查表 |
| TCS slot | 实际承载该请求的槽（0..n） | 由 `cmd_addr` 命中反推 |
| addr | 该槽 `cmd_addr` 寄存器回读值 | `base+0x34` |
| data/level | 该槽 `cmd_data` 回读值，**必须非 0** | `base+0x38` |

**三条硬性排除**（都是本仓库已经付过代价的误判）：

1. **「caps 看着合理」不算证明**。caps 只说明 RSC 块可访问（`REFERENCE-INDEX.md:865-866` 明说：
   这张表只证明「RSC 这个块能读写」，**不证明**那几条轨的投票参数对）。
2. **「RPMh ACK」不算证明**。`POWER-RPMH-LDOC2.md:101-113`：ACK 只代表请求被接受，不代表 PMIC 输出；
   yibiya 的做法是再读 PMIC observer（SID2 C200，APID 181）的 ready/enable/valid。
   未投票实测 `ready=0 enable=0 program=1800 valid=0 mode=7 status=3`，Android 侧 `ready=1 enable=1 valid=1800`。
   **`AVDD GPIO71 IO=3` 明确不是供电证明。**
3. **aux 字节不是电平表**。`POWER-RPMH-LDOC2.md:35-42`：ldoc2 的 aux 是 4 个身份字节 `01 2a 00 00`，
   被当成 u16 数组解析就会得出 `levels=1 l0=10753`（= 0x2a01 误读）这种「没有 1800 档」的错误结论。
   校验方式：`le16(aux)==0x2a01` 且后两字节为 0。

**判定规则（第二步实现的判据）**：
- 每条轨都拿到非 0 的 data/level，且 addr 与 cmd-db 的 address 一致 → `K60BoardOk`，并打印四元组；
- 任一条缺失 / 为 0 / addr 不匹配 → 仍然 `K60BoardUnsupported`，但**日志必须点名是哪条轨、读到了什么**；
- ARC 轨（lcx/lmx）的 data 是**档位索引**（初值 0x10=16），不是毫伏——
  不能用 `k60_rpmh_level_index()` 的毫伏语义去解释它。

## 四、问题 4：时机与门控

必须逐条满足 `docs/ops/HARD-RULES.md:52-58` 的四条件，且**复用现有约束，不加新开关**：

1. **时机**：`k60_data_mounted == 1` 之后（`bsd/kern/kern_exec.c:7896` 置位）。早期启动访问仍会死。
2. **显式开启**：复用 `pong_rail_probe=1`（`patches/xnu/0614-k60-adsp-call-site.patch:8-20` 的调用点
   已经是 `if (PE_parse_boot_argn("pong_rail_probe", &pong_rail_probe, sizeof(pong_rail_probe)) && pong_rail_probe != 0)`）。
   理由：启动参数预算只剩 32 B（基线 575 B / 607 B），**不新增参数**。
3. **只读**：只读 TCS 的 `cmd_addr`/`cmd_data`/`status`/`idle`/`cmd_enable`，
   **不写任何 TCS 寄存器、不设 `CONTROL_TRIGGER`**。
4. **单次**：一次启动最多一次，不轮询。

### 4.1 决定性时序事实：`resources()` 跑在 Data 挂载**之前**

`k60_adsp_handoff_publish()` 是 `resources()` 的唯一生产者路径，而它的唯一调用点在
`patches/xnu/0619-k60-adsp-glink-handoff.patch:320-338`：插在 `IOKitBSDInit()` 里
`IOService::publishResource("IOBSD")` **之前**，由 `pong_handoff_publish=1` 打开。

而 Data 挂载发生在更晚的线程里：

```
bsd/kern/bsd_init.c:909        bsd_autoconf();          ← 内含 IOKitBSDInit()（:1321）
bsd/kern/bsd_init.c:1264       bsdinit_task()           ← :1295 load_init_program(p)
bsd/kern/kern_sig.c:3420       if (!bsd_init_done) { bsd_init_done = 1; bsdinit_task(); }
bsd/kern/kern_exec.c:8563      native_owner_data_prepare(p, scratch)
bsd/kern/kern_exec.c:7896      k60_data_mounted = 1;    ← 四条件的「时机」在这里才成立
```

**结论**：`k60_adsp_handoff_publish()` → `k60_adsp_platform_install()` → `k60_adsp_owner_acquire()`
→ `resources()` 全都在 IOKitBSDInit 里跑完，**结构上早于 `k60_data_mounted=1`**。
所以 `resources_cb` **不可能自己**在 HR-01 允许的时机做那次 TCS 读取。

两条合法出路（**Lead 2026-11-16 09:45 选了 B**：A 会把电池消费者等待的时刻往后推、并重新论证
`startup_claim(1)` 语义；B 只是把这次读从 `resources()` 挪进已有的 `k60_rail_probe()`，不动物时序、仍然 fail-closed）：

- **A. 把发布点移到 Data 挂载之后**：在 0614 那个已经过门的调用点之后（`native_owner_data_stage = 3`
  附近）再触发发布。代价：0619 的 early-owner `startup_claim(1)` 语义、电池消费者的时序都要重新论证，
  且要改 `patches/xnu/0619`（本轮禁改 patches/）。
- **B. `resources()` 不自己读，只消费已记录的证据**：在 0614 的 `pong_rail_probe` 单次读取里
  顺带把 lcx/lmx 四元组记录下来（与现有 `k60_rail_probe()` 同一函数、同一次、同一门控），
  `resources()` 只检查「是否已有该记录」，没有就仍然 fail-closed 并打印缺哪条轨。
  代价：一次启动里 `pong_handoff_publish=1` 与 `pong_rail_probe=1` 必须同时给，
  否则记录不存在——但那本来就是「默认关、显式开」的语义。

## 五、现状与第二步

**第一步（本文）时的状态**：`drivers/PongPower/K60AdspBoard.c` 的 `resources_cb` 在 lease + 排除 +
停机三项通过后**无条件** `return K60BoardUnsupported`，于是 owner 在 stage 1 就失败
（`adsp-20261115e` 的 `stage=1 rc=-1000`），PAS1 不运行。

**第二步（2026-11-16，Lead 09:45 选 route B 后已落地，主机侧已验证）**：

- **记录**：`drivers/PongPower/K60PmicRail.c` 在既有的 `k60_rail_probe()` 里、与 DRV-2 只读探测
  **同一次、同一门控**中增加测量：按 `cmd_addr` 命中反推 TCS 槽（**不写死槽号**），读出 `cmd_data`
  的 ARC 档位，把四元组（resource id / TCS 槽 / addr 回读 / level 回读）写进
  `k60_rail_ledger_store()` 的 `static K60RailLedger`。账本自带 `magic` / `drv_id` / `recorded` /
  `gate`，每条轨自带 `complete` / `valid` / `missing` / `why`：缺任何一项即整条轨「未取得」，
  **不允许半条记录**。打印行 `K60RAIL lcx id=… tcs=… addr=… level=… (arc index, not mV) complete=…
  valid=…`。
- **查表**：`resources_cb` 变成三态——记录完整且有效 → `K60BoardOk` 并打印
  `K60ADSP: rails inherited lcx=<id>@<tcs> level=<n> lmx=<id>@<tcs> level=<n> (arc index, not mV; drv_id=…)`；
  没有记录 → `-63` 并打印「pong_rail_probe 还没跑」；有记录但不完整/无效 → 同样 `-63`，
  但措辞不同并点名轨与字段（`not obtained: <field> missing` 与 `measured but invalid: <why>`）。
- **没有改变的部分**：成功路径**仍然一个寄存器都没写**，`resources_release_cb` 的
  「nothing was ever voted」注释与语义保持不变；HR-01 的四项条件（Data 挂载后、`pong_rail_probe=1`、
  只读、单次不轮询）原样成立；`0602`/`0614`/`0619` 的时序一行未动。
- **门禁**：`scripts/tests/test-k60-pmic-rail.c` 37 例（含未测量、缺字段、level=0、槽不 idle、
  窗口过短、NULL 参数），`scripts/tests/test-k60-adsp-board.c` 第 8 个场景
  `scenario_rails_three_state` 走完三种状态，两者都已接进 `scripts/tests/run-k60-handoff-host.sh`。
- **教训登记**：`docs/engineering/PITFALLS.md` P-197 与 `docs/engineering/RULES.toml` 的 `P-197`。
- **真机判据**（Lead 飞）：`pong_handoff_publish=1 pong_rail_probe=1` 同时给，成功链为
  `board ownership init ok` → `board ownership installed rc=0` → `platform installed rc=0` →
  `K60ADSP: rails inherited …` → K60PAS 三阶段 → `K60Handoff: published authenticated PAS1
  epoch=N bytes=104 flags=15`；失败必须能读出是哪条轨、缺哪个字段。

## 六、证据索引

| 事实 | 出处 |
| --- | --- |
| ADSP 节点的 cx/mx/xo/qmp/interconnect | `docs/research/audio/VENDOR-ADSP-NODE.md:17-63`；DTB `remoteproc-adsp@03000000` |
| lcx.lvl / lmx.lvl 节点与 PMIC 子节点 | `E:/k60-work/scratch/dtb/mondrian.dts:5333-5345`、`:6113-6125`；别名 `:21177-21179`、`:21288-21290` |
| Pong 按名取 lcx/lmx 并取最高档投票 | `E:/k60-work/references/pong-power/PongAdsp.cpp:225-231`、`:565-572` |
| 唯一被批准的只读实现 | `drivers/PongPower/K60PmicRail.c:273-388`；`docs/ops/HARD-RULES.md:101-104` |
| 四元组账本（记录/查表） | `drivers/PongPower/K60PmicRail.c:155-262`；`drivers/PongPower/K60AdspBoard.c:247-299`；`docs/engineering/PITFALLS.md` P-197 |
| 只读 TCS 槽先例（wifi gate） | `E:/hackios/k60-wifi/patches/wifi/0003-drivers-PongWifi-k60-rsc-gate.patch:28-39` |
| DRV-2 可读可写、drv-0/drv-3 禁碰 | `docs/research/REFERENCE-INDEX.md:836-866`（582 boot 审计） |
| v2 布局与 TCS 偏移/步长 | `docs/research/touch/POWER-RPMH-LDOC2.md:44-64` |
| ACK ≠ 供电；observer 判据 | `docs/research/touch/POWER-RPMH-LDOC2.md:101-113` |
| aux 身份字节陷阱 | `docs/research/touch/POWER-RPMH-LDOC2.md:35-42` |
| 四条件原文 | `docs/ops/HARD-RULES.md:44-58` |
| 发布点在 IOKitBSDInit、早于 Data 挂载 | `patches/xnu/0619-k60-adsp-glink-handoff.patch:320-338`；`bsd/kern/bsd_init.c:909,1264,1321`；`bsd/kern/kern_sig.c:3420`；`bsd/kern/kern_exec.c:7896,8563` |
| 本板 K60RAIL 实测（仅三行，无 ADSP 轨） | `E:/k60-work/evidence/usblog-20261114-railh/console.log:477-479` |
