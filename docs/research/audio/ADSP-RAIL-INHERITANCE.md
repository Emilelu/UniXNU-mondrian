# ADSP LCX/LMX 供电继承：四个问题的取证（round 33，2026-11-16）

Lead 2026-11-16 08:08 的裁定：HR-01 **不放松**，但 `K60AdspBoard.c` 的 `resources_cb` 把两种
完全不同的情况合并成了一个返回值 `K60BoardUnsupported`(-63)——「轨已被 ABL/Android 投过、XNU 只是继承」
和「轨读回来是 0 / 不存在」在日志里长得一模一样，于是「DSP 起不来」永远无法区分是没电还是我们拒绝投票。
这与 P-190/P-204 同型：**用一个常量代替了本可测量的东西**。

这份文档的**第一步是只取证、不改代码**：按 Lead 的四个问题给出可核对的答案，并额外记录一条
决定实现位置的时序事实（第四节末尾）。第二步走过两版：Lead 2026-11-16 09:45 选的 B
（先记录、后查表）在 13:50 被他本人撤回——**读者结构上早于写者**，`resources()` 永远查到空账本，
fail-closed 因此变成永远为假的条件；改版 C：`resources()` 只声明继承哪两条轨，四元组回读与三态
判定挪进 `k60_adsp_bring_up()` 的第一步、即 `AUTH_AND_RESET` 之前。现状见第六节，
真机读数填入第五节的实测骨架。

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

三条出路，**Lead 2026-11-16 09:45 先选 B，13:50 撤回并改选 C**：

- **A. 把发布点移到 Data 挂载之后**：在 0614 那个已经过门的调用点之后（`native_owner_data_stage = 3`
  附近）再触发发布。代价：0619 的 early-owner `startup_claim(1)` 语义、电池消费者的时序都要重新论证，
  且要改 `patches/xnu/0619`。未采用。
- **B（已撤回）. `resources()` 先查账本、`k60_rail_probe()` 后记录**：把四元组记进 `static` 账本，
  `resources()` 只查表并三态判定。听上去是 fail-closed，量一遍时序却是反的：`resources()` 在
  `IOKitBSDInit()` 里跑，账本的写者 `k60_rail_probe()` 在 kern_exec 的 Data 挂载之后才跑，
  **读者结构上早于写者**，于是查表永远查到空账本——这道门看着像检查，实际只把功能关死。
  撤回理由即此；不是实现 bug，是位置选错。
- **C（已落地）. `resources()` 只声明，回读放到不可逆操作之前**：`resources()` 不读寄存器、不查账本，
  只按设备树的 `cx-supply` / `mx-supply` 声明继承 `lcx.lvl` / `lmx.lvl` 并返回成功；真正的四元组回读
  放进 `k60_adsp_bring_up()` 的第一步（`k60_adsp_plan()` 与 `k60_adsp_auth_and_reset()` 之前）——
  这里本来就在 Data 挂载之后，HR-01 的时机条件自然成立，而 `AUTH_AND_RESET` 是唯一不可逆的一步，
  检查贴着它放才有意义。仍复用 `pong_rail_probe=1`，只读、单次、不轮询。

## 五、实测（真机，待填）

Lead 2026-11-16 13:50 起飞的探针镜像只带 `pong_rail_probe=1`：基线 29 项 575 B + 17 B = 592 B
≤ 607 B，**没有** `pong_handoff_publish=1`（再加就 615 B，且这一轮只验证只读回读本身）。
所以这一版验证的是 `k60_rail_probe()` 这条只读通道，不是发布路径。

期望日志（按出现顺序；`rail_print()` 每轨一行）：

```txt
K60RAIL cmd-db magic=0xc0330db version=1
K60RAIL lcx id=... tcs=... addr=... level=... (arc index, not mV) complete=1 valid=1
K60RAIL lmx id=... tcs=... addr=... level=... (arc index, not mV) complete=1 valid=1
```

如果日志里只有 `K60ADSP: rails not measured` 而没有四元组，说明这条路径没有跑到
（`k60_rail_probe()` 在 Data 挂载之后、`pong_rail_probe=1` 门内），不是账本坏了。

| 事实 | 实测值 | 判读 |
| --- | --- | --- |
| lcx resource id | `<!-- MEASURED: lcx resource id -->` | 必须等于 cmd-db 条目 `lcx.lvl` 的 address |
| lcx TCS 槽 | `<!-- MEASURED: lcx tcs slot -->` | 由 `cmd_addr` 命中反推，**不是写死的槽号** |
| lcx addr 回读 | `<!-- MEASURED: lcx cmd_addr -->` | 必须等于 resource id；不等即「测得但无效」 |
| lcx level 回读 | `<!-- MEASURED: lcx cmd_data -->` | ARC 档位索引，**不是 mV**；DT `qcom,init-voltage-level = <0x10>`，不得过 `k60_rpmh_level_index()` |
| lmx resource id | `<!-- MEASURED: lmx resource id -->` | 必须等于 cmd-db 条目 `lmx.lvl` 的 address |
| lmx TCS 槽 | `<!-- MEASURED: lmx tcs slot -->` | 同上；若与 lcx 同槽，先怀疑读错 |
| lmx addr 回读 | `<!-- MEASURED: lmx cmd_addr -->` | 必须等于 resource id |
| lmx level 回读 | `<!-- MEASURED: lmx cmd_data -->` | 同上；非零才算继承成立 |
| 结论 | `<!-- MEASURED: verdict -->` | 两轨完整、有效、非零 = 继承成立；否则点名轨与字段 |

（`<!-- MEASURED: ... -->` 是占位符；收到 console.log 后逐项填写，缺一项就留空并注明原因。）

## 六、现状与两版第二步

**第一步（本文取证）时的状态**：`drivers/PongPower/K60AdspBoard.c` 的 `resources_cb` 在 lease + 排除 +
停机三项通过后**无条件** `return K60BoardUnsupported`，于是 owner 在 stage 1 就失败
（`adsp-20261115e` 的 `stage=1 rc=-1000`），PAS1 不运行。

**第二步 B（09:45 落地，13:50 撤回）**：`k60_rail_probe()` 记账、`resources()` 查表并三态判定。
主机侧当时已验证（rail 37 例 + board 8 场景），但时序上读者早于写者，见 4.1 的撤回理由；
这一段只作为历史记录，代码已不在该形态。

**第二步 C（13:50 之后落地，主机侧已验证）**：

- **声明**：`K60AdspBoard.c:243` 的 `resources_cb` 不读寄存器、也不查账本；lease + 排除 + 停机三项
  通过后打印 `K60ADSP: rails declared lcx=lcx.lvl lmx=lmx.lvl (inherited, not yet read)`，
  置 `b->resources = 1`、`b->last_rc = K60BoardOk` 并返回 `K60BoardOk`。措辞里的 `not yet read`
  是判据的一部分：这一行**不能**被读成「已继承」。
- **回读**：`K60PmicRail.c:389` 的 `k60_rail_inherit()` 在 `k60_adsp_bring_up()` 的第一步调用
  （`k60_adsp_plan()` 与 `k60_adsp_auth_and_reset()` 之前，见 `patches/xnu/0613-k60-adsp-pas.patch:208`），
  一次、只读、同一 `pong_rail_probe` 门控；`k60_rail_verdict()`（`:260`）三态：
  完整且有效 → 打印 `K60ADSP: rails inherited lcx=<id>@<tcs> level=<n> lmx=<id>@<tcs> level=<n> (arc index, not mV)` 并返回 0；
  没有记录 → `rails not measured: pong_rail_probe is off …; refusing AUTH_AND_RESET`；
  不完整 → `rail not inherited <rail>: <field> missing; refusing AUTH_AND_RESET`；
  完整但无效 → `rail measured but invalid <rail> (<why>); refusing AUTH_AND_RESET`。
  后三种都返回 `-63`，只有第一种继续走 PAS1。
- **没有改变的部分**：成功路径仍然一个寄存器都没写；`resources_release_cb` 的「nothing was ever voted」
  注释与语义不变；HR-01 四条件（Data 挂载后、`pong_rail_probe=1`、只读、单次不轮询）原样成立；
  `0602`/`0614`/`0619` 的时序一行未动；没有新增启动参数。
- **门禁**：`test-k60-pmic-rail.c` 49 例（含 `k60_rail_verdict()` 全部分支），
  `test-k60-adsp-board.c` 8 场景（第 8 个 `scenario_resources_declares` 证明无账本也返回成功、
  仍受 lease 约束）；板级测试的链接**故意不含 `K60PmicRail.c`**，依赖回潮会直接链接失败。
- **教训登记**：`docs/engineering/PITFALLS.md` P-223（fail-closed 的位置必须在不可逆操作之前）。
- **真机判据（C 完整链，两次启动才齐）**：本轮探针给 `pong_rail_probe=1` 拿四元组；
  下一次给 `pong_handoff_publish=1` 时，成功链为 `board ownership init ok` →
  `board ownership installed rc=0` → `platform installed rc=0` → `K60ADSP: rails declared …` →
  继续 PAS1；legacy `pong_adsp` 路径才会打印 `K60ADSP: rails inherited …`。

### 6.1 一个必须报告的时序事实：发布路径不经过 `k60_adsp_bring_up()`

C 的 fail-closed 贴在 `AUTH_AND_RESET` 前面，但**只有 legacy `pong_adsp` 路径经过 `bring_up()`**：

- 发布路径：`k60_adsp_owner_acquire()`（`K60HandoffRuntime.cpp:72`）→ `K60AdspOwnerStages.c:156`
  的 `auth_and_reset` → `K60AdspPlatformNative.cpp:336-342` 的 SCM `PAS_AUTH_AND_RESET`，
  全程在 `IOKitBSDInit()` 里，**早于 Data 挂载**。
- legacy 路径：`k60_adsp_probe_from_handoff()` → `k60_adsp_bring_up()`，在 kern_exec 的
  `k60_data_mounted = 1` 之后，rail gate 有效。

也就是说：C 让 legacy 路径真正 fail-closed 在不可逆操作之前；发布路径在 `resources()` 时只能
声明（那一刻读不到），它的四元组证据只能来自同一启动里更晚的 `k60_rail_probe()`。这一条随本轮
汇报提交给 Lead；在裁定前不擅自改 `0619`/`0602`/`0614` 的时序。

## 七、证据索引

| 事实 | 出处 |
| --- | --- |
| ADSP 节点的 cx/mx/xo/qmp/interconnect | `docs/research/audio/VENDOR-ADSP-NODE.md:17-63`；DTB `remoteproc-adsp@03000000` |
| lcx.lvl / lmx.lvl 节点与 PMIC 子节点 | `E:/k60-work/scratch/dtb/mondrian.dts:5333-5345`、`:6113-6125`；别名 `:21177-21179`、`:21288-21290` |
| Pong 按名取 lcx/lmx 并取最高档投票 | `E:/k60-work/references/pong-power/PongAdsp.cpp:225-231`、`:565-572` |
| 唯一被批准的只读实现 | `drivers/PongPower/K60PmicRail.c:437-540`（`k60_rail_probe()`）；`docs/ops/HARD-RULES.md:101-104` |
| 四元组回读与三态判定 | `drivers/PongPower/K60PmicRail.c:260-434`（verdict:260、record_pass:335、pass:357、inherit:389）；`drivers/PongPower/K60AdspBoard.c:243-262`（只声明）；`docs/engineering/PITFALLS.md` P-223 |
| 回读调用点（`AUTH_AND_RESET` 之前） | `patches/xnu/0613-k60-adsp-pas.patch:208`（`k60_adsp_bring_up()` 第一步） |
| 发布路径不经过 `bring_up()` | `K60HandoffRuntime.cpp:72`；`K60AdspOwnerStages.c:156`；`K60AdspPlatformNative.cpp:336-342` |
| 只读 TCS 槽先例（wifi gate） | `E:/hackios/k60-wifi/patches/wifi/0003-drivers-PongWifi-k60-rsc-gate.patch:28-39` |
| DRV-2 可读可写、drv-0/drv-3 禁碰 | `docs/research/REFERENCE-INDEX.md:836-866`（582 boot 审计） |
| v2 布局与 TCS 偏移/步长 | `docs/research/touch/POWER-RPMH-LDOC2.md:44-64` |
| ACK ≠ 供电；observer 判据 | `docs/research/touch/POWER-RPMH-LDOC2.md:101-113` |
| aux 身份字节陷阱 | `docs/research/touch/POWER-RPMH-LDOC2.md:35-42` |
| 四条件原文 | `docs/ops/HARD-RULES.md:44-58` |
| 发布点在 IOKitBSDInit、早于 Data 挂载 | `patches/xnu/0619-k60-adsp-glink-handoff.patch:320-338`；`bsd/kern/bsd_init.c:909,1264,1321`；`bsd/kern/kern_sig.c:3420`；`bsd/kern/kern_exec.c:7896,8563` |
| 本板 K60RAIL 实测（仅三行，无 ADSP 轨） | `E:/k60-work/evidence/usblog-20261114-railh/console.log:477-479` |
