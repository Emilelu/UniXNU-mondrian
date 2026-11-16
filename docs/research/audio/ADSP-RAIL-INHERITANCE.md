# ADSP LCX/LMX 供电继承：四个问题的取证（round 33，2026-11-16）

**当前裁决：Lead 2026-11-16 15:03 选择 (iii)，恢复 handoff 资源拒绝。**
[`resources_cb`](../../../drivers/PongPower/K60AdspBoard.c#L243) 在 lease/排他/stopped 检查后仍须返回
`K60BoardUnsupported`(-63)，不置 `resources=1`，打印
`K60ADSP: rails not verified for handoff; no PAS/SMEM mutation`，先于下游 map/SMEM 分配/SCM/copy/AUTH/发布。
HR-01 **不放松**；未知供电不是轨关闭，也不能被声明成 `K60AdspResourcesHeld`。

**历史（已被本裁决取代）**：08:08 的要求是区分未测量与测得请求，不是授权把未知改报成功。
B（09:45 采用、13:50 撤回）让早期 `resources()` 查晚期探针的账本，读者结构上早于写者。
C（13:50 采用、15:03 撤回）让 `resources()` 声明成功、仅在 legacy `k60_adsp_bring_up()` 检查；
但生产 owner stages 不经过 legacy 门，且在 AUTH 前已有 SMEM/PAS/copy 副作用。
现状与调用链见第六节。撤回 `de8cf52` 可出功能实验图的批准；`adsp-20261116a` 构建被门禁拒绝，
**没有 boot.img、未上机**。本轮不开 `pong_adsp`/`pong_handoff_publish`；只读探针须先离线审计，
由 Lead 另行决定是否构建或 boot rail-only，不能预写继承或 PAS/handoff 成功。

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

可以取得资源地址与某位置保留的请求这两类**不同**的原始事实，但二者不足以证明当前供电：

| 来源 | 读什么 | 证明什么 | HR-01 |
| --- | --- | --- | --- |
| cmd-db `0x80860000` | 按资源名取 `address` + 电平表 | 这条轨的**命令地址**（后续所有比较的基准） | 普通内存，安全，无限制 |
| DRV-2 `0x17a20000` + TCS 槽 | `cmd_addr` / `cmd_data` / status / enable / msgid 原始值，含 slot+command index | **该位置留有的请求**；不证明投票来源、AOP 当前聚合状态或轨有效 | 仅四条件同时满足，且布局先审计（见第四节） |

### 2.1 cmd-db：已实现、已上机

历史 railh 只验证过受限只读探针的 cmd-db magic、ldoc2 和 DRV-2 布局三行，
没有 ADSP LCX/LMX 请求实测。后加的
[`k60_rail_measure()`](../../../drivers/PongPower/K60PmicRail.c#L175) 与 ledger 不因这个先例而已上机或已审计。
它们只读、不写 TCS，但现实现固定 5 槽、每槽只看首个 command；是否覆盖可访问槽与全部 command、
status/enable/msgid 解释、以及唯一入口的单次 attempted 语义，均待离线核验（第六节）。

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

历史先例把下列布局打印解释为 v2（同
[`REFERENCE-INDEX.md:176`](../REFERENCE-INDEX.md#L176)）：
`K60RAIL rsc drv_id=0x20700 version=2 stride=672 cmd=20 ctrl=0x14 enable=0x1c msgid=0x30 addr=0x34 data=0x38`。
这不是 ADSP 采样器的审计结论：实际 caps 可访问 slot 数、每槽 command 数、cmd_stride，
`TCS_STATUS(+0x18)` 与 `CMD_STATUS(+0x3c)`、bit0 是否可命名 idle、enable/msgid 语义仍须可靠来源确认。

### 2.3 ⚠ TCS 槽号：本板有两个互相矛盾的说法，不要猜

- `docs/research/touch/POWER-RPMH-LDOC2.md:33`：「**本板 TCS 编号 3（不是 4）**，yibiya 实测；
  DT 在 Android 上是 active0..2/sleep3..4，不要按 DT 推」。
- `docs/research/REFERENCE-INDEX.md:883-886` §14.5：Pong 用 `0xd00+4*0x2a0`（槽 4），
  而 live FDT 说 `qcom,drv-id=<2>`——两者不冲突（drv-id 选 DRV，槽号选 DRV 内的 TCS），但混抄会算错地址。

这两条说的是**不同外设**（触摸 IOVDD vs Pong 的通用投票）。ADSP 的 LCX/LMX 由谁、在哪个槽投的，
**本板没有测量**。所以实现时**不得写死槽号**，也不能固定只扫 5 槽或每槽首 command
就宣称覆盖完整。先确认 caps/布局，再记录 slot+command index 并按 `cmd_addr` 匹配资源地址；
未确认的布局列为阻塞，不猜、不扩大到其它 DRV，没扫到不等于没投票。

## 三、问题 3：请求记录不等于「证明已继承」

旧 B/C 用四元组判「已继承」的规则已被 15:03 裁决否定。下表仅列原始请求记录，
还必须保留 command index 与原始状态/enable/msgid；不能把它们升级为供电有效证明：

| 元素 | 含义 | 来源 |
| --- | --- | --- |
| resource id | cmd-db 里的 `address`（如 ldoc2 的 `0x42c00`） | cmd-db 按名查表 |
| TCS slot + command index | 实际观察到请求的位置（覆盖范围先审计） | 由 `cmd_addr` 命中反推，不假定每槽只一个 command |
| addr | 该 command 的 `cmd_addr` 原始回读 | 槽基址、command stride 与偏移须核验 |
| data/level | 该 command 的 `cmd_data` 原始回读，保留 0 与非 0 | 非零只证明此处留有请求，不证明轨有效 |

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

**当前判读边界**：
- 匹配地址且有非零 data 只能称 **recorded/request observed**；不能返回成功来授予 ResourcesHeld。
- 缺记录、零值或扫描范围不全须逐项报告，不能推导「无票」或「轨关闭」。
- `K60RailVerdictInherited`、`valid=1` 是旧实现命名，证据强度不足；legacy 检查虽保留，不能据此授权 SCM。
- ARC 轨（lcx/lmx）的 data 仍是**档位索引**（DT 初值 0x10=16），不是毫伏；
  不能用 `k60_rpmh_level_index()` 的毫伏语义解释。真正供电证据须按官方 ARC/AOP 聚合状态语义验证。

## 四、问题 4：时机与门控

必须逐条满足 `docs/ops/HARD-RULES.md:52-58` 的四条件，且**复用现有约束，不加新开关**：

1. **时机**：`k60_data_mounted == 1` 之后（`bsd/kern/kern_exec.c:7896` 置位）。早期启动访问仍会死。
2. **显式开启**：复用 `pong_rail_probe=1`（`patches/xnu/0614-k60-adsp-call-site.patch:8-20` 的调用点
   已经是 `if (PE_parse_boot_argn("pong_rail_probe", &pong_rail_probe, sizeof(pong_rail_probe)) && pong_rail_probe != 0)`）。
   **不新增参数**；完整参数与字节数须从真实候选镜像量，旧 575/592/593 B 估算不作本轮证据。
3. **只读**：只读审计后的 DRV-2 cmd-db/TCS 原始字段，
   **不写任何 TCS 寄存器、不设 `CONTROL_TRIGGER`、不扩大到其它 DRV**。
4. **单次**：一次启动最多一次尝试，失败同样消耗；唯一采样入口前置 attempted，
   probe/inherit 复用结果，已有 ledger 不得重新 map/read。现实现尚未证明满足这一点，
   也不能只凭调用点注释声称四条件已由入口保证。

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

三条出路的裁决历史（当前只有 (iii) 恢复拒绝获准）：

- **A，未采用**：把 owner/publish 移到 Data 挂载之后。将来的设计必须同时重审 early
  `startup_claim(1)` 与晚期 owner 的所有权边界，以及电池消费者 attempted 先置位的顺序；
  先提交调用图、阶段表、host trace，不在本轮改 `0614`/`0602`/`0619` 时序。
- **B，09:45 采用、13:50 撤回**：晚期探针写账本、早期 `resources()` 查账本，
  读者早于写者。host 的合成账本不能证明这条生产时序可达。保守拒绝本身是安全边界，
  不能为让功能继续而把未知改报成功。
- **C，13:50 采用、15:03 撤回**：`resources()` 只声明并返回成功；legacy
  `k60_adsp_bring_up()` 才查轨。真实 owner stages 不经过它；AUTH 也不是第一处副作用。
  C 的 host 通过记录只能描述旧实现，不能证明 handoff 受保护。

## 五、实测状态与未来记录表

**2026-11-16 ADSP 轨实测仍为空。** 原“Lead 13:50 起飞、参数 592 B”的叙述错误且已撤回：
`adsp-20261116a` 被门禁拒绝，无 boot.img、未上机；592/593 B 等手算值不是镜像实测。
旧 railh 只有 cmd-db magic、ldoc2、DRV-2 布局三行，不含 LCX/LMX。

以下仅是离线审计完成、Lead 另行批准 rail-only 后的原始记录表，**不是本轮起飞授权**。
不带 `pong_adsp`/`pong_handoff_publish`；不把旧 `complete=1 valid=1` 或
`rails inherited` 日志当供电证明。每条记录须能追溯完整 console、镜像、参数真实字节数与代码 revision。

| 事实 | 实测值 | 判读边界 |
| --- | --- | --- |
| lcx/lmx cmd-db resource id | 未测 | 按名取得 command address；不是 rail-on 状态 |
| DRV-2 caps / 可访问 slots / commands / stride | 未测、布局待审计 | 记录可靠来源与覆盖范围，不固定 5 槽或仅首 command |
| lcx slot + command index / addr / data | 未测 | 原始值；ARC data 为档位索引而非 mV |
| lmx slot + command index / addr / data | 未测 | 同上；同槽不同 command 并不自动无效 |
| TCS_STATUS / CMD_STATUS / enable / msgid | 未测、语义待审计 | 分开记录，不把 CMD_STATUS bit0 擅称 idle |
| attempted / ledger reuse / 失败注入 trace | 待离线证明 | 成功或失败均只尝试一次，已有账本不再 map/read |
| 请求观察与实际供电结论 | 无供电结论 | 非零只证明某位置留有请求；缺记录不证明无票或轨关闭 |

## 六、当前拒绝与已撤回实现

**当前 (iii)，15:03**：`resources_cb` 在 lease/排他/stopped 校验通过后仍返回
`K60BoardUnsupported`(-63)，不置 `b->resources=1`；固定拒绝日志为
`K60ADSP: rails not verified for handoff; no PAS/SMEM mutation`。
owner 返回 `K60_ADSP_OWNER_UNAVAILABLE`，不得设置 `K60AdspResourcesHeld` 或发布 lease。
这恢复的是生产链最早可执行的安全门，不是证明电源关闭。legacy `k60_rail_inherit()` 保留，
但其名字与旧 verdict 不能授权 PAS/SCM；本轮不开功能参数、不出功能图。

**已撤回历史**：B 的 rail37 + board8、C 的 rail49 + board8 是各自旧合成 helper/回调行为的
host 结果；C 曾打印 `rails declared ... (inherited, not yet read)` 并置资源标志，其
`scenario_resources_declares` 的成功目标与六行成功链均已撤销，不能作当前验收或下一次起飞依据。
旧代码保留的 `Inherited`/`valid=1` 命名也不表示证据已升级。

**本轮 host 边界**（完整 runner exit0，未上机）：

- board 仍 **8 场景**，第 8 场景验证有合法 lease、stopped 证据时资源仍拒绝且不置标志；
  场景 6 的安装门只模拟 native C++ 注册协议，不等于生产 owner integration。
- 真正下游门禁在 [test-k60-owner-claim.c](../../../scripts/tests/test-k60-owner-claim.c) 的新增场景：
  真实 board callbacks + production `k60_adsp_owner_install/acquire/publish`，owner-claim **18 场景**
  （原 17 + 此 1）。链接 `--wrap=k60_smem_alloc` 直接计数，夹具构造完成后清零。
  断言 `map_smem=0 alloc=0 init=0 mem=0 load=0 auth=0 publish=0`、无 TCSR 锁、
  无 resources release、输出 lease 全零、SMEM 字节不变，并拒绝重试。
  board 排他所需的一个只读 SMEM map/unmap 是预期的，不能误写成“所有 map=0”。
- P-223 注册命令须同时执行 rail helper、board8、owner-claim18；rail49 的通过仅证明旧 helper
  分支，不解决采样覆盖、状态语义或单次入口。完整 runner 日志 `E:/k60-work/artifacts/adsp-board-20261116/refusal/host-tests.log` 共 1458 行、55737 B，SHA256 `e1457b20f26c27c77fb4d72b0170f74e896bd850cd284c146fe199cde29da89c`；第 27 行是七项下游计数全零的拒绝轨迹。

### 6.1 决定性缺口：发布路径不经过 `k60_adsp_bring_up()`

生产调用链是 `k60_adsp_handoff_publish()` → runtime 安装 board/platform →
`k60_adsp_owner_acquire()` → owner stages；不经过 legacy `k60_adsp_bring_up()`。
[OwnerStages:90–95](../../../drivers/PongPower/K60AdspOwnerStages.c#L90) 在 resources 返回 0 后立即
置 `resources_held` / `K60AdspResourcesHeld` 并取得 `map_smem`；
[:109–124](../../../drivers/PongPower/K60AdspOwnerStages.c#L109) 为 host FIFO 分配 478/479/480；
[:138–156](../../../drivers/PongPower/K60AdspOwnerStages.c#L138) 执行 INIT_IMAGE → MEM_SETUP →
COPY/BSS → AUTH_AND_RESET。故只把门贴在 AUTH 前已太晚，C 的 legacy 门也完全覆盖不到这条链。

### 6.2 采样器仍有的阻塞

`K60_RAIL_SLOTS=5`、每槽首 command、`cmd_stride` 未用于全 command 覆盖、status/enable/msgid
解释均须按可靠布局来源审计。`k60_rail_probe()` 在检查 ledger 前已 map/read；`rail_pass()`
失败又不记录 attempted，所以现代码不能证明失败也只尝试一次或 probe/inherit 无重复硬件读取。
必须在唯一采样入口执行四条件与 attempted 门；先补离线正反例，不在本轮修改采样器或扩大访问。
即使未来记录完整，TCS 请求仍不是 AOP 当前聚合或 PMIC/ARC 生效状态。

## 七、证据索引

| 事实 | 出处 |
| --- | --- |
| ADSP 节点的 cx/mx/xo/qmp/interconnect | `docs/research/audio/VENDOR-ADSP-NODE.md:17-63`；DTB `remoteproc-adsp@03000000` |
| lcx.lvl / lmx.lvl 节点与 PMIC 子节点 | `E:/k60-work/scratch/dtb/mondrian.dts:5333-5345`、`:6113-6125`；别名 `:21177-21179`、`:21288-21290` |
| Pong 按名取 lcx/lmx 并取最高档投票 | `E:/k60-work/references/pong-power/PongAdsp.cpp:225-231`、`:565-572` |
| 历史受限只读先例（不是新增采样器批准） | `drivers/PongPower/K60PmicRail.c:437-540`（`k60_rail_probe()`）；`docs/ops/HARD-RULES.md:101-104` |
| 旧 helper 与当前资源拒绝 | `drivers/PongPower/K60PmicRail.c:260-434`（verdict:260、record_pass:335、pass:357、inherit:389，待审计）；`drivers/PongPower/K60AdspBoard.c:241`（返回 -63）；`docs/engineering/PITFALLS.md` P-223 |
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
