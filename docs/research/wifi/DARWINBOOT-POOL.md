# DarwinBoot pool 对照账本：九张零字节记录与三组 alive 对照（2026-11-16）

状态：**`c2`/`c3` 配方的 pool/体积单轴解释被对照否定，旧样本逐图归因未完成**。
2026-11-15 建这张表是为了记录「DarwinBoot 把整个内核读进 DXE pool，再申请
4.5 GiB 连续窗口」的逐图输入。`c2`/`c3` 的受控干预与 `patches/wifi/0012` 源码链
支持该对照涉及的 UFS SMMU lease 故障（P-215），不自动覆盖 trial、无效测量或独立 bt 样本。
**数值表保留**；同级装载负载不等于逐次 pool 分配、碎片布局或执行路径完全相同。
分析见 [BLOB-RESIDENCY.md](BLOB-RESIDENCY.md) §7（对照适用范围）与 §10（P-215 证据）。

底稿：分支 `feat/wifi-ledger-fold` 的 `96e0a23` / `f9e5d0c`。

## 口径（先于数字读）

- **kernel B / `__TEXT` / `__DATA` / `__DATA_CONST`**：`mtype` 解出
  boot.img ramdisk 槽 `EFI/UniXNU/Payloads/kernel.macho` 后按 `LC_SEGMENT_64`
  读的 vmsize（脚本 `probe-silent6.py`、`probe-c456b.py`，`E:/k60-work/scratch/refmine/`）。
  build-manifest 不存这些数。
- **`pong_wifi`**：镜像字节实测（`scripts/check-arg.py`）与
  build-manifest.json 的 `kernel_args_requested` 两道核对。
- **ADT 窗口**：boot.img ADT `darwinboot-memory-size` 解码（`probe-window3.py`、
  `probe-win2.py`）。
- **series**：build-manifest.json 的 `series` 字段；trial 镜像没有这个键。
- 没测到或不存在的格写 `—`；本文不许估。

## 逐图账本

| 镜像 | kernel B | `__TEXT` | `__DATA` | `__DATA_CONST` | blob | `pong_wifi` | ADT 窗口 | series | 证据目录 |
|---|---|---|---|---|---|---|---|---|---|
| wifi-20261114a | 65,863,680 | 12,877,824 | 1,867,776 | 933,888 | 有（PWF2×2） | 1 | 0x130000000 | 无（trial） | `usblog-20261114-wifi-b` |
| wifi-20261116mhi3 | 65,978,368 | 12,992,512 | 1,867,776 | 933,888 | 有 | 1 | 0x130000000 | 229 `0076aa20902a…` | `usblog-20261115-002804` |
| wifi-20261116mhi4 | 65,978,368 | 12,992,512 | 1,867,776 | 933,888 | 有 | 1 | 0x120000000 | 229 | `usblog-20261115-002243` |
| wifi-20261115z0 | 117,305,344 | 12,992,512 | 53,149,696 | 933,888 | 有 | 0 | 0x120000000 | 224 `34cf51e4…` | `usblog-20261115-135859` |
| wifi-20261116t2 | 117,305,344 | **1,802,240** | 53,149,696 | **12,124,160** | 有（在 `__DATA_CONST`） | 0 | 0x120000000 | 224 `34cf51e4…` | `usblog-20261115-161102` |
| bt-s4b-20261115c | 106,541,056 | 1,720,320 | 52,920,320 | 1,949,696 | 无 | —（kargs `k60bt=1`） | 0x120000000 | 229 `67baff88e1bb` | `usblog-20261115-163144` |
| wifi-20261116c0 | 66,002,944 | 12,992,512 | 1,867,776 | 933,888 | 有（真容器 6 条） | 0 | 0x120000000 | 224 `34cf51e4…` | `usblog-20261115-213221`（测量无效） |
| wifi-20261116c1 | 66,002,944 | 12,992,512 | 1,867,776 | 933,888 | 有（真容器 6 条） | 0 | 0x120000000 | 224 `34cf51e4…` | `usblog-20261115-231707` |
| wifi-20261116c2 | 117,305,344 | **1,802,240** | 53,149,696 | **12,124,160** | 有（`__DATA_CONST`，真容器 6 条） | 0 | 0x120000000 | 224 `34cf51e4…` | `usblog-20261116-000136` |
| wifi-20261116c3（**alive**） | 117,325,824 | **1,802,240** | 53,149,696 | **12,124,160** | 有（`__DATA_CONST`，与 `c2` 逐字节相同） | 0 | 0x120000000 | 226 `d83fb1890e93…` | `usblog-20261116-015128`（221,429 B） |
| wifi-20261116c4/c5/c6（**alive**） | 117,325,824 | **1,802,240** | 53,149,696 | **12,124,160** | 有（同上） | 1（c5 加 `rsc=1`、c6 加 `rsc=2`） | 0x120000000 | 226 `d83fb1890e93…` | `usblog-20261116-072728` / `-075300` / `-081646` |
| adsp-20261115c/d/e（对照，**alive**） | 128,991,232 | 1,720,320 | 76,414,976 | 917,504 | 无 | —（无此参数） | 0x120000000 | 226 `d83fb1890e93…` | `usblog-20261115-213413` / `-220912` / `-223916` |

十二行里九条零字节记录（`c0` 一条测量无效，其余八条保留 silent 采集判定），三组 alive 对照。

九条零字节采集记录都是 `port-not-observed` + `fastboot-return` + console.log 0 字节，判定器
（main 的 `scripts/judge-z0.sh`）都报 `silent` / exit 2。这是采集分类，包含无判别力的 `c0`，
不等于九个有效因果对照。

`c0` 的编译身份与设备 Data UUID 不符，使该格 **没有判别力**（`invalid-measurement`，
P-152/P-209；BLOB-RESIDENCY.md §10.3）；同次 console 为 0 字节，没有可引用的根挂载 panic 行。
`c1` 修正这一行 UUID 后仍然 0 字节（段表与 `c0` 逐项相同），只排除了
**UUID 是 `c0`/`c1` 这组观测的唯一充分解释**，不证明 UUID 无害，也不补出两张图的具体崩点。

## 对照支持什么，以及不能外推什么

1. **`c2`/`c3` 配方不能仅用 pool/体积解释生死**：两者同 117 MB 级版式、同窗口、
   同真 PWF2 容器；`c3` 多 20,480 B 惰性锁代码后进了桌面
   （`usblog-20261116-015128`，console 221,429 B、SpringBoard 133）。这支持 P-215 修复
   在该配方中的因果作用，不等于实测了每次 pool 布局，也不排除任意旧图的窗口分配故障。
2. **单纯总大小阈值不足以解释已观测对照**：`adsp-*` 三张 **128,991,232 B** 内核
   （`__DATA` 76,414,976、span 141,111,296）在同一 4.5 GiB 窗口下全部进桌面；
   `bt-s4b-20261115b`/`c` 同尺寸一活一死。它们提供阈值反例，不替代各自的故障归因。
3. **搬移容器本身不足以救活已测配方**：`t2`/`c2` 把容器搬进 `__DATA_CONST`
   （`__TEXT` 1,802,240）仍 silent；`c3` 同驻留位置 alive。不能把驻留位置写成这些样本
   的唯一生死条件，更不能由此推断每张旧镜像的实际停止位置。

**P-215 的机制与适用范围**：源码链显示 `patches/wifi/0004` 给
`PongUfsTransport::hostBringUp()` 插入 Apps SMMU lease 索取，锁原来只在更晚的
`pong_rpmh_init()` 分配；未就绪时返回 false，可使 UFS transport 放弃根设备。
`c2`/`c3` 的受控对照与 0012 惰性分配修复共同支持这一故障机制
（BLOB-RESIDENCY.md §10.1–§10.2）。**九张 0 字节不是九份同根因证明**。

### 逐图置信边界（与数值账本分开）

“可证”列仅列已有记录或受控干预；“间接”不是该次崩点证据；未知项不以相似尺寸或
series 行数补齐。证据目录按上表逐行对应 `E:/k60-work/evidence/`。

| 样本/组 | 可证 | 间接支持 | 未知/不可断言 |
|---|---|---|---|
| wifi-20261114a | trial、无 series 键、0 字节及上表镜像数值 | 带真容器的早期 silent 样本 | 完整 series/归档来源及该次调用路径未核；不能归为已证 lease |
| mhi3 | series 229 `0076aa20902a…`、0 字节、4.75 GiB | 已读 0004/锁实现与该类风险相容 | 逐图归档与实际停止路径未闭环，无同次 lease 失败日志 |
| mhi4 | series 229、0 字节、4.5 GiB，与 mhi3 同段表 | 窗口变化没有消除 silent | 同上；窗口对照不证明此图 lease 或 pool 失败 |
| z0 | series 224 `34cf51e4…`、`pong_wifi=0`、0 字节 | worker 开关未消除这次 silent；与 P-215 风险相容 | 未由逐图归档/调用路径证明实际崩点 |
| t2 | 真实容器在 `__DATA_CONST`、0 字节、上表 series | 与 c2 同段表节表，搬移未救活 | 同版式不是同一执行轨迹；逐图 lease 归因仍间接 |
| bt-s4b-20261115c | 无 wifi blob、series 229 `67baff88e1bb`、0 字节；b 同尺寸 alive | 总大小不能单独解释 bt 对照 | 独立 bt 故障；未核实 wifi 归档/lease 调用路径，不纳入 P-215 已证范围 |
| c0 | 身份不符、0 字节、该格 invalid-measurement | 身份检查是必要前置 | 无同次 panic 行，具体崩点与 lease 是否先触发未知 |
| c1 | UUID 修正、与 c0 同段表，仍 0 字节 | 排除 UUID 是唯一充分解释；P-215 是候选机制 | 不证明 UUID 无害；无同次根挂载或 lease 失败行 |
| c2 | 0 字节；与 c3 受控干预及源码链共同支持 P-215 | t2 的版式复现 | 不补造该次 panic/lease 输出，也不扩展到其它旧图 |
| c3 | 0012 干预后 alive，真容器与 c2 逐字节相同 | 支持该配方中的修复效果 | 不保证所有带 0012 的镜像必活 |
| c4/c5/c6 | 该配方开 worker/只读探针/投票后均 alive | P-215 修复后可进入后续 MHI 阶段 | 不证明其它配方无 early-boot 缺陷；c6 MHI 故障另查 |
| adsp-20261115c/d/e | 129 MB 级、无 blob、三张 alive | 已观测阈值反例 | 不判定任一 silent 镜像的故障机制 |

## 每行一句（不引申）

1. **wifi-20261114a**：65.9 MB 级最早的一张，blob 在 `__TEXT`，`pong_wifi=1`，
   4.75 GiB 窗口；trial 镜像，manifest 没有 series 键。silent。
2. **mhi3**：66 MB 级正式镜像，4.75 GiB 窗口。silent。
3. **mhi4**：与 mhi3 同尺寸同段表，窗口 4.5 GiB。silent。
4. **z0**：117 MB 版式，`pong_wifi=0`，4.5 GiB 窗口，series 224。silent。
5. **t2**：117 MB 版式，blob 容器移入 `__DATA_CONST`（`__TEXT` 1,802,240），
   `pong_wifi=0`，4.5 GiB 窗口，series 224。silent。
6. **bt-s4b-20261115c**：106.5 MB、无 wifi blob、kargs `k60bt=1`、4.5 GiB 窗口、
   series 229。silent；同尺寸同 blob 只差一个补丁的 bt-s4b-20261115b 同日 alive
   （`usblog-20261115-140927`，213,434 B；见 BLOB-RESIDENCY.md §2）。
7. **c0**：正式 C 格（66 MB、blob 在 `__TEXT`、`pong_wifi=0`、无 GPU addon、
   无 battery），4.5 GiB 窗口，series 224。**这张的 silent 没有判别力**：boot.img
   实测唯一带种子 Data UUID（`6DCCF70A-…` ×1、`1BCD69FF-…` ×0；其余 52 张
   wifi/bt 图相反）；只能判身份不符使格无判别力，未观察到具体 panic。
8. **c1**：`c0` 只改该 UUID 一行，段表逐项相同，仍然 0 字节 ⇒ 有效 silent 记录，
   只排除 UUID 是这组失败的唯一充分解释。
9. **c2**：`t2` 的段表节表复现，0 字节；结合 c3 干预判该配方，而不是单凭驻留位置归因。
10. **c3**（alive）：与 `c2` 同版式、同容器、同窗口、同 `pong_wifi=0`，只多
    20,480 B 惰性锁代码 ⇒ 该配方的 P-215 受控修复证据，不是旧图共因证明。
11. **c4/c5/c6**（alive）：`c3` + `pong_wifi=1`（`c5` 加 `rsc=1`、`c6` 加 `rsc=2`），
    段表与 `c3` 逐项相同 ⇒ 这些配方未被 worker 开关与投票阻止进入桌面。
    `c6` 停在 MHI 的 `-110`（`device in READY state` 之后），属另一类故障（有日志）。
12. **adsp-20261115c/d/e**（alive）：129 MB、无 blob、同 4.5 GiB 窗口 ⇒ 阈值模型的反证。

## 附：历史拒飞清单与已知代码前置

> 保留的是当时拒绝重复实验的决策与版式，不是“所有同类都会撞同一 lease”的定理。
> 当时的“缺 0012”须逐图核实补丁、归档与调用路径；上面的间接/未知列不能被清单覆盖。
> 已确认走 0004 UFS 索取与旧锁实现的候选，重建前应具备 0012 或等价生命周期修复并验证。
> 本页不授权重建或上机，c8 继续 HOLD。

mhi5d = 117 MB + blob（`__TEXT`）+ `pong_wifi=1` + 4.5 GiB + series 224
（与 mhi5 同尺寸同段表，payload `96ea535f…`）。它是 0012 之前的产物：

1. **66 MB + blob + `pong_wifi=1`**：mhi3 / mhi4 已飞 silent ⇒ 当时拒绝无新变量重复飞行。
2. **117 MB + blob（`__TEXT`）+ `pong_wifi=0`**：z0 已飞 silent ⇒ 同上，不以版式认定崩点。
3. **117 MB + blob（`__DATA_CONST`）+ `pong_wifi=0`**：t2 / c2 已飞 silent ⇒ 当时拒飞；
   搬移不足以救活这两次记录，c2 的 P-215 依据另见受控对照。
4. **mhi5d 自身**：1、2 的交集版式 ⇒ 保留当时拒飞，不把未飞镜像当成同次故障证明。
5. **106.5 MB bt 版式**（无 wifi，`k60bt=1`，只差一个补丁的同尺寸对）：
   b alive / c silent 已飞完 ⇒ 当时拒绝无新变量的重复飞行，不据此归为同一故障。
6. **66 MB + blob（`__TEXT`）+ `pong_wifi=0`**：`c1` 已飞 silent ⇒ 当时拒绝原样重飞；
   UUID 改正未救活，不补 lease 失败日志。
7. **117 MB + blob（`__DATA_CONST`）+ `pong_wifi=0` 的第二次复现**：`c2` 与 `t2`
   逐项相同、已飞 silent ⇒ 保留当时拒飞决策，不作为逐图归因。

**旧计划中的 tiny B 格**（54.8 MB、4×23 B 占位头、`pong_wifi=1`，`t1c` 从未飞）
原本用于拆分真 blob 与驱动代码存在。它不是已证 silent，更不是新的飞行许可。
若未来重新立项，须先核对实际 series/归档/0004 调用路径与锁生命周期；
确认走该故障路径时，0012 或等价修复是已知代码前置。不能写“否则只会复现 lease”。

**本页的后续边界**：pool 通道的结论不替代 MHI 因果分析。`c7` 的
`usblog-20261116-122546:608,610,612,618,620,628,632` 只记录到硬件 SBL/READY、主机请求 M0、
software ee=PBL/pm_state=POR，抓取未见 EE 处理或完整镜像 BHIE 发起；原因待验，不作死锁定论。
共享 rp 不变不证设备未写或 DMA 正常，软件 IRQ 不证 GIC；BHI 已发同文件 512 KiB 前缀。
c8 目前暂停，先审重复下载、重入及 READY→M0 协议；以后分 BHIE 返回、硬件 EE/M0、host
事件处理、QMI/ath11k、netdev/扫描/关联/数据独立验收，不能用 exec_env 1→2 单值结 Wi-Fi 通。
见 [BLOB-RESIDENCY.md](BLOB-RESIDENCY.md) §11.4–§11.8。
