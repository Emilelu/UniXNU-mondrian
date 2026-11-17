# ADSP Bring-up Plan V2：QMP load_state、供电观测与后移发布

**Status:** offline plan only. No production source change, no patch, no kernel/image build, no device run, no new boot argument. Every address below is source-derived, not measured on this board. Anything not provable is marked unknown.
**Scope:** the Lead 2026-11-16 22:20 four-part deliverable: vendor QMP/aggre2/bandwidth facts, route C on-device observation checklist, route B call graph including the 0602 battery consumer, and the documentation corrections this survey requires. It does not authorize route A, route B implementation, a rail vote, or a sampler change.

## 0. Pins and boundaries

- Vendor source: Xiaomi K60 Android S [989b27aa8391a2ede9b067b53877c4c3343955fe](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/blob/989b27aa8391a2ede9b067b53877c4c3343955fe/drivers/remoteproc/qcom_q6v5_pas.c), local copy `E:/k60-work/scratch/survey-linux/vendor_q6v5_pas.c`; DT `E:/k60-work/scratch/dtb/mondrian.dts`.
- AOSS message transport: same pin, `drivers/soc/qcom/qcom_aoss.c`; MDT loader: same pin, `drivers/soc/qcom/mdt_loader.c`, local copy `E:/k60-work/scratch/survey-linux/mdt_loader.c`.
- HR-01 still forbids AP TCS writes and `CONTROL_TRIGGER`; the only allowed RSC read is DRV-2 `w[0]` under the four conditions. QMP descriptor reads are a different window and still need the same opt-in boot; this document does not add one.
- Production `resources_cb` remains `K60BoardUnsupported`(-63); the legacy rail gate remains only on `k60_adsp_probe_from_handoff()`; the publish path does not pass it.

## 1. QMP load_state、aggre2、带宽：确切来源、寄存器/命令、各一行日志

| 项 | Vendor 事实（行号） | 在 K60 上是什么 | 一行结果（只读；不投票） |
| --- | --- | --- | --- |
| QMP load_state | `vendor_q6v5_pas.c:374` 在 xo、regulator、AUTH 之前调用 `adsp_toggle_load_state(adsp->qmp, adsp->qmp_name, true)`；消息正文在 `:153-161`：`{class: image, res: load_state, name: adsp, val: on}`；长度 `QMP_MSG_LEN 64`（`:40`） | 不是 MMIO 寄存器。`qmp_send()` 把 64 字节写进 AOSS message RAM：payload 在 `msgram + offset + 4`，长度在 `msgram + offset`，再按 mailbox doorbell（`qcom_aoss.c:239-283`）。AOSS 描述符窗口是 `0xc300000`，大小 `0x400`（DT `:9529-9546`） | 只能读描述符：`K60QMP desc magic=%#x version=%u mcore_link=%#x/%#x mcore_ch=%#x/%#x mbox=%u@%#x` |
| aggre2 clock | `vendor_q6v5_pas.c:382` 在 xo 之后 `clk_prepare_enable(adsp->aggre2_clk)`；但 `cape_adsp_resource:961-973` 的 `has_aggre2_clk=false`，`adsp_init_clock:514-538` 只取 xo；DT `:8711-8730` 的 `clocks` 只有 `<0x20 0>`（xo），无 aggre2 clock | 没有 aggre2 寄存器，也没有对应 clock 对象；`:382` 在 K60 上是空操作（时钟指针为空） | `K60AGGRE2 n/a cape has_aggre2_clk=0 clocks=xo-only` |
| 带宽 | `vendor_q6v5_pas.c:362` → `do_bus_scaling(true):335-351` → `icc_set_bw(adsp->bus_client, 0, UINT_MAX)`；`bus_client` 取自 `:603` 的 `of_icc_get(dev, "rproc_ddr")`。AUTH 前 `:390` → `scm_pas_enable_bw():210-211` → `icc_set_bw(scm_perf_client, 0, UINT_MAX)`；AUTH 后 `:394` → `:235` 归零。`scm_perf_client` 取自 `:598` 的 `of_icc_get(dev, "crypto_ddr")` | K60 DT `:8711-8730` 有 `interconnects = <0x5a 0x2b 0x46 0x200>`、名字 `crypto_ddr`，**没有** `rproc_ddr` 路径，所以 `do_bus_scaling` 走 `IS_ERR` 分支只打印。真正会执行的是 scm 的 crypto_ddr 峰值。目标值是 ICC/BCM/RPMh 投票，AP 侧等价物是 TCS 写（HR-01 禁止），没有可读回的寄存器 | `K60BW crypto_ddr avg=0 peak=UINT_MAX source=vendor:210,:235 rproc_ddr=absent observed=no` |

**结论：** 三件里只有 QMP 描述符可以只读观测；aggre2 在 K60 根本不存在；带宽只能把 vendor 意图打印出来，不能读回生效值。QMP 的 `load_state` 是消息写 + mailbox，不是“读一个寄存器再比较”。所以路线 C 不允许发送 `load_state`，也不允许用它的结果推断轨已开。
QMP 描述符偏移（全部 u32）：`+0x0` magic（`0x4d41494c`）、`+0x4` version（1）、`+0x24`/`+0x28` mcore link state/ack、`+0x2c`/`+0x30` mcore channel state/ack、`+0x34`/`+0x38` mcore mailbox size/offset；ucore 对应 `+0xc/+0x10/+0x14/+0x18/+0x1c/+0x20`。`QMP_STATE_UP=0xffff`。

## 2. 路线 C 的上机最小观测清单

前置条件（缺一不算路线 C）：只使用已有 `pong_rail_probe=1`，不新增 boot-arg；在 `k60_data_mounted==1` 之后；只读；单次；不写 TCS、不写 QMP、不发送任何 mailbox 消息。

| # | 打印行（建议名） | 读什么 | 预期与判别 |
| --- | --- | --- | --- |
| 1 | `K60RAIL cmd-db magic=... version=...`（已有） | cmd-db 头 `0x80860000+4/+8` | magic 必须 `0x0c0330db`；不是则 cmd-db 本身不对，后面所有 rail 行都无意义 |
| 2 | `K60RAIL lcx ...` / `K60RAIL lmx ...`（已有） | DRV-2 TCS 槽，按 cmd_addr 匹配 lcx.lvl/lmx.lvl | 每行给出 resource id、tcs 槽、cmd_addr、cmd_data、complete/valid；`cmd_data` 是 ARC level index，不是 mV |
| 3 | `K60QMP desc ...`（新增，同一次 probe 内） | `0xc300000+0x0/0x4/0x24..0x38`，8 个 u32 | magic=`0x4d41494c`、version=1、link/channel 的 state 与 ack 相等且为 up（`0xffff`）才算 AOSS 通信就绪 |
| 4 | `K60AGGRE2 n/a ...`（静态行） | 无 | 只是把“K60 无此 clock”说清楚，不参与成功判据 |
| 5 | `K60BW crypto_ddr ...`（静态行） | 无 | 只是把 vendor 的 0/UINT_MAX 意图与“不可读回”说清楚，不参与成功判据 |

现有 `k60_rail_measure()` 只按 `K60RscLayout` 读三项：`status`、`cmd_addr`、`cmd_data`；v2 相对 TCS 基址是 `+0x18`、`+0x34`、`+0x38`（v3 的偏移必须由 `k60_rsc_layout()` 选择，不能手抄）。QMP 只增加描述符的 8 个 u32 读，不增加 TCS 槽/命令扫描范围。

**轨的三种结果（A-C）与 QMP 独立判定（D）：**

- **A. 两轨都 complete/valid 且 level 非 0，QMP 描述符正常**：ABL 已把两轨留在可继承状态，且 AOSS 活着；这是路线 C 唯一正结果。路线 A（loader 投票）更没有必要；但路线 B 仍要单独设计，因为 `resources()` 在发布路径上仍早于 Data，不能读。
- **B. 两轨 complete 但 level==0、或 tcs 不 idle、或其中一轨只有 request record**：轨没有真正继承；QMP 正常也不改变这一点。路线 C 不能靠 QMP 修，路线 B 只改发布时机也不投票；要么 loader/ABL（路线 A），要么另找可授权的投票路径。先把槽号和 `cmd_data` 原值贴出来，不要用 `k60_rpmh_level_index()` 把 ARC index 当 mV。
- **C. 打印 `rails not measured` 或完全没有第 2 行**：这不是轨结论，是代码路径没到。依次核对：`pong_rail_probe` 门是否真命中（`0614` 的 `PE_parse_boot_argn`）、`k60_rail_probe()` 是否在 `k60_data_mounted=1` 之后被调用、`k60_cmd_db_find("lcx.lvl")`/`"lmx.lvl"` 是否返回 0、`rail_measure` 是否找到槽。把“没测到”与“测到无效”分开记录。
- **D. QMP magic 不是 `0x4d41494c`、version 不是 1、或 link/channel 未 up**：AOSS 未初始化或描述符不对；此时 `load_state` 消息也发不出去，任何依赖 QMP 的 PAS 启动都会独立失败。QMP 没有“开/关”位，D 只判 AOSS 通信是否就绪；不要把它写成轨的结论。

槽号说明：DT `rsc@17a00000` 的 `qcom,tcs-config=<02 03 00 02 01 02 03 00 04 01>`（`mondrian.dts:5119-5129`）按 vendor 绑定解码是 ACTIVE=槽 0-2、SLEEP=3-4、WAKE=5-6、CONTROL=0、FAST=7。Pong 参考实现硬编码的“槽 4”在 K60 是 SLEEP 槽，不能照抄（`K60PmicRail.c:167-173` 的注释把参考槽 4 当成可照抄对象；它声称“本板用 TCS3”也没有来源）。如果观测到的 request record 落在 3/4，只能说明 SLEEP 组里有请求，不能据此声称 ACTIVE 轨已开。

## 3. 路线 B 的调用图、阶段表与 0602 电池消费者

**现在的调用图（发布路径）：**

- 唯一发布点：`patches/xnu/0619-k60-adsp-glink-handoff.patch:331-336`，在 `IOKitBSDInit` 里、`IOService::publishResource("IOBSD")`（`:338`）之前，门是 `pong_handoff_publish==1`。内部顺序：`k60_adsp_handoff_publish()`（`K60HandoffRuntime.cpp:36`）→ `k60_adsp_startup_claim(1)`（`:37`）→ 配置/范围检查（`:39-45`）→ `/chosen`（`:46`）→ `exists()`（`:48`）→ board init（`:56`）→ ownership install（`:63`）→ platform install（`:70`）→ `k60_adsp_owner_acquire`（`:72`）→ `owner_publish`（`:78`）。
- 属性写入：`K60HandoffRuntime.cpp:18` 的 `setProperty`，经 `:26-28` 的 `runPropertyAction` 原子 no-clobber 提交。
- 属性读取点（全部）：producer 侧 `exists()`（`K60HandoffRuntime.cpp:14`，在 `:48` 调用）只做 no-clobber 预检；consumer 侧 `drivers/PongPower/K60Battery.cpp:426` 的 `getProperty(K60_ADSP_HANDOFF_PROPERTY)` 是唯一真实消费，由 `patches/xnu/0602-k60-physical-battery.patch:33-35` 在 `publishResource("IOBSD")` 之后调用 `k60_physical_battery_start()`（`K60Battery.cpp:416`）进入。grep 没有其它读点。`:418` 的 `static attempted` 与 `:421` 的原子交换意味着**一次失败后本轮不再尝试**。
- 现在的后期路径：`0619` 的 kern_exec hunk（`:341-355`）在 Data 挂载后先 `k60_adsp_startup_claim(2)`，再 `k60_adsp_probe_from_handoff()`（进入 legacy `k60_adsp_bring_up()`），再 `pong_rail_probe`（`:356`），最后 `native_owner_data_stage=3`。发布路径不经过这个 legacy bring-up，所以发布路径的 AUTH 早已在 Data 之前发生。

**阶段表（路线 B 的目标：把发布点移到 Data 之后；早 claim 保留，后期不 re-claim，legacy 路径排除）：**

| 阶段 | 当前位置 | 现在做什么 | 路线 B 后 | 受影响 |
| --- | --- | --- | --- | --- |
| 1 早发布 | `IOKitBSDInit`，Data 前 | `k60_adsp_handoff_publish()`：claim(1) + 安装 + acquire + AUTH + 发布属性 | 移到 Data 后；claim(1) 保留（仍是本轮唯一 owner） | 发布前任何人读属性都读不到 |
| 2 `publishResource("IOBSD")` | `0619:338` | 发布 IOKit 资源 | 不变 | 与 ADSP 无关 |
| 3 电池启动 | `0602:33-35`，在阶段 2 之后、Data 之前 | `k60_physical_battery_start()` 读 `:426` 属性；缺失 → `:431-433` 打印 blocked → `attempted=1` 永久消耗 | 调用点仍在 Data 前；属性更不可能存在 | **唯一读点失效，整轮无电池服务**；`attempted` 阻止重试 |
| 4 后期 probe | `kern_exec`，Data 后（`0614`/0619） | claim(2) 被排除；legacy bring-up 若未 claim(1) 才跑；`pong_rail_probe` 单次 | 不变；`pong_rail_probe` 仍只做观测 | 路线 B 的 `resources()` 可以在 Data 后合法读到真值（仍需 `pong_rail_probe=1` 单次） |
| 5 电池后续 | `K60Battery.cpp:435-443` | 拿到 lease 才 attach/begin；否则无 power source | 若阶段 3 已失败，不会再有第二次 | 需要“单次晚通知/延迟启动”；不能改动 0602 时序来绕过 |

**Host trace 必须覆盖的顺序（设计约束，不是实测）：**

1. 早发布：`K60Handoff: board ownership init ok rc=0` → `ownership installed rc=...` → `platform installed rc=...`（`K60HandoffRuntime.cpp:62,69,71`），随后才是 `published authenticated ...`（`:81`）或 `PAS1 bring-up/retained ownership failed ...`（`:74`）。
2. `publishResource("IOBSD")` 之后：`0602` 调电池启动；路线 B 下应在 `K60Battery.cpp:432` 看到 `blocked rc=...`，而不是 attach/begin。
3. Data 挂载后：`0619` 的 `K60PAS legacy startup excluded by earlier ADSP owner/attempt`，证明 claim(2) 没重入；随后是 `K60RAIL ...`、`K60QMP ...`。
4. 任何 `K60ADSP: rails not verified for handoff; no PAS/SMEM mutation`（`K60AdspBoard.c:253`）都必须出现在任何 PAS/SMEM 日志之前。
5. 该 trace 只证明调用顺序；它不证明轨有效、带宽生效或 QMP 消息能发出去。

**结论：** 路线 B 的结构性代价不在 ADSP 本身，而在 0602 电池消费者：它比新的发布点早，且 `attempted` 一次性。可行的后续设计只有两类——(a) 让 0602 的启动在 Data 后/发布后发生（改 0602 时序，当前未授权）；(b) 保留 0602 调用，但让 `K60Battery` 注册一次“属性出现”通知并在那时启动（改生产 C，当前未授权）。在两者之一经 Lead 批准前，不能把路线 B 说成可上机方案。无论哪种，都必须：不重新 claim(1)、不启用 legacy claim(2)、失败则本轮无服务且不重试、只在属性校验通过后 attach。

## 4. 文档修正清单

| 文件:行 | 现在写的 | 应对 |
| --- | --- | --- |
| `docs/research/audio/ADSP-PAS1.md:31` | `PAS_INIT_IMAGE ... pas=1, phys=<每段物理地址>` | 错。`INIT_IMAGE` 只调一次，第二个参数是 5404 B metadata（884 B header prefix + 4520 B hash）的物理地址；不是每段 paddr。依据 `mdt_loader.c:238-251`、`K60AdspOwnerStages.c:138`、`K60AdspPlatformNative.cpp:323-324` |
| `ADSP-PAS1.md:32` | `PAS_MEM_SETUP ... base=0x86300000` | 错。基址是板级 region `0x9fd00000`，span `0x3100000`；0x86300000 是链接基址。依据 `K60AdspOwnerStages.c:138-139`、`mdt_loader.c:253-260` |
| `ADSP-PAS1.md:36` | “`INIT_IMAGE` 需要逐段地址……必须先有段的 (paddr, bytes) 列表” | 错。INIT_IMAGE 一次 metadata；逐段的是 COPY/BSS，不是 SCM INIT_IMAGE |
| `ADSP-PAS1.md:40` | “载入基址 0x86300000” | 混淆链接基址与物理 region；应写“链接基址 0x86300000，重定位后物理装载到 0x9fd00000..0xa2e00000” |
| `docs/research/battery/HANDOFF-PUBLISH-SPEC.md:87` | “逐段 INIT_IMAGE + MEM_SETUP” | 同一错误；改成一次 metadata INIT_IMAGE + 一次 region MEM_SETUP + 逐段 COPY/BSS |
| `drivers/PongPower/K60PmicRail.c:167-173` | “this board votes touch through TCS3 while the reference implementation writes slot 4” | 不能照抄：DT `tcs-config` 解出 ACTIVE=0-2、SLEEP=3-4；Pong 的槽 4 在 K60 是 SLEEP；“本板用 TCS3”无来源。只改注释，不改采样语义 |
| `docs/research/audio/VENDOR-ADSP-NODE.md:178,184` | 把 0x86300000 当作装载基址 | 标明它是链接基址；物理装载基址见上 |
| `docs/research/audio/GAP-ANALYSIS.md:117` | “SCM PAS_INIT_IMAGE→MEM_SETUP→分段 load” | 顺序对，但补“INIT_IMAGE 一次 metadata”以免读者重犯 `ADSP-PAS1` 的错 |
| `patches/xnu/0613-k60-adsp-pas.patch:243,252` | legacy `k60_adsp_bring_up` 仍逐段 `k60_adsp_init_image(s->paddr)`，再 `mem_setup(0x86300000, 0x3100000)` | 与 vendor/生产 owner 不一致；这是 legacy 路径的代码事实，本文件只登记，不在本轮修改 |

**引用规则：** 任何引用 `ADSP-*.md` 的 SCM 参数都必须回到 `mdt_loader.c`、`K60AdspOwnerStages.c`、`K60AdspPlatformNative.cpp` 三者之一核对；`ADSP-PAS1.md` 当前不能作为 SCM 参数的一手来源。

## 未覆盖 / 未证明

- 没有上机，因此 QMP 描述符是否在 K60 上可读、rail 四元组是否真值，全部未知；本文件只给读点与判别。
- 没有 TCS 写权限，因此“带宽是否生效”“两轨是否足够让 AUTH 成功”都无法离线证明；别家的顺序不等于 K60 的结果。
- 路线 B 的 `resources()` 读取实现、晚通知/延迟电池启动、以及 0619 时序是否改动，都未获授权；需要下一次 Lead 裁决。
- 本文件不改变 production `resources_cb`(-63)、HR-01、0619/0602/0614、默认 boot args 或 porting 验证状态。
