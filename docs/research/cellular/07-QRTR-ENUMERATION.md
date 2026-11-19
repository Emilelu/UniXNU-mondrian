# 07 — QRTR 只读枚举：向 modem 的名字服务发一次 NEW_LOOKUP

本文件记录 L3：在**不重置、不加载、不写任何 modem 分区**的前提下，经 SMEM 上的
GLINK `IPCRTR` 通道向已经在运行的 modem 发一个 QRTR `NEW_LOOKUP`（类型 `0x0a`），
把回来的 `NEW_SERVER` 折叠成表，并用 node 0 的应答判定"modem 的 QMI 名字服务能枚举"。

判据（Lead m03122 原话）：

> 你选的 A（进 L2）我同意，d5a9939 的 12 个 DT 节点我自己合。你继续做 QRTR 枚举的只读部分，
> 判据 NEW_LOOKUP(0x0a) 收 node 0 的 20 字节应答。

## 1. 判据落到代码里是什么

"20 字节应答" = QRTR **control 消息的载荷恰好 20 字节**（5 个 u32：command + 4 个 word），
加 32 字节头后整个数据报 52 字节。名字服务对一次 `NEW_LOOKUP` 的回应是若干条
`NEW_SERVER`（类型 4），每条 52 字节，其中 20 字节载荷是
`{service, instance, node, port}`。

判据被写成三道，全部满足才算过：

| 条件 | 代码位置 |
|---|---|
| 收到 `NEW_SERVER` 且 `header.from_node == 0` | `drivers/PongCellular/K60ModemQrtr.c:117` 起 `k60_qrtr_note()` |
| 该服务的编号 ∈ {21 EFS, 1 WDS, 11 UIM, 3 NAS, 16 PDS} | `drivers/PongCellular/K60ModemQrtr.c:102` `k60_qrtr_wanted()` |
| `state->from_node0 != 0 && state->wanted != 0` | `drivers/PongCellular/K60ModemQrtr.c:173` `k60_qrtr_verdict()` |

这五个服务不是猜的：Android 侧 `qrtr-lookup` 的原始输出
（`docs/research/cellular/01-ANDROID-INVENTORY.md:409-452`）里，36 条 Node = 0 的条目中
就有 `21 Modem embedded file system service`、`1 Wireless Data Service`、
`11 User Identity Module service`、`3 Network Access Service`、
`16 Location service (~ PDS v2)`；该文件的 :454-457 明确把这 36 条当作"modem 已枚举"的证据。
L3 只是用 XNU 自己的传输栈把同一件事再问一遍。

## 2. QRTR 线格式（v1，小端）

头部固定 8 个 u32 = 32 字节（`drivers/PongCellular/K60ModemQrtr.h:20-26`）：

| 偏移 | 字段 | 我们发的值 |
|---|---|---|
| 0x00 | version | `1` |
| 0x04 | type | HELLO=`2`、NEW_LOOKUP=`10 (0x0a)` |
| 0x08 | from_node | `0`（本机 AP） |
| 0x0c | from_port | `0x4000`（`K60_QRTR_FIRST_PORT`） |
| 0x10 | confirm | `0` |
| 0x14 | size | `20`（control 载荷字节数） |
| 0x18 | to_node | `0xffffffff`（广播，`K60_QRTR_BROADCAST_NODE`） |
| 0x1c | to_port | `0xfffffffe`（名字服务，`K60_QRTR_CONTROL_PORT`） |

control 载荷 5 个 u32 = 20 字节：`command` + `words[4]`。
`NEW_LOOKUP` 与 `NEW_SERVER` 都要求 `command == header.type`，否则
`k60_qrtr_note()` 记一次 `malformed` 并丢弃（`K60ModemQrtr.c:148-153`）。
`DEL_SERVER`（类型 5）只表示服务下线，**不计入**判据（`K60ModemQrtr.c:156-158`）。

两种报文长度都是 `32 + 20 = 52` 字节（`K60_QRTR_LOOKUP_BYTES`）。

## 3. 传输：SMEM + GLINK + IPCC

全部参数来自活 Android DT（`docs/research/cellular/02-DT-TRUTH.md:145-171`：
`qcom,remote-pid = <1>`、`mboxes = <&ipcc 2 0>`、`qcom,glink-channels = "IPCRTR"`、
`qcom,intents = (0x800,5) (0x2000,3) (0x4400,2)`；节点本体见 `dts/mondrian.dts:250-283`）：

| 常量 | 值 | 依据 |
|---|---|---|
| `K60_MODEM_SMEM_BASE` | `0x80900000` | DT `qcom,smem`，2 MiB（`02-DT-TRUTH.md:184-200` 区域表） |
| `K60_MODEM_IPCC_BASE` | `0x0ed18000` | DT `mailbox@ed18000`；`mboxes = <&ipcc 2 0>` ⇒ client 2，signal 0。上游 `v6.6/arch/arm64/boot/dts/qcom/sm8450.dtsi:3176-3183` 同址（`qcom,sm8450-ipcc`，GIC SPI 229 = DT 的 `0xe5`）；门铃字由 `drivers/mailbox/qcom-ipcc.c:17-25,152-153` 定义为 `client<<16 | signal` 写入 `0x0c`，与本实现一致。参考实现 `hakios.mpss.c:616` 的 `0x00408000` 是 SM8250 时代的 IPCC 实例，**不适用本板** |
| GLINK descriptor / ours / theirs | SMEM item `478 / 479 / 480` | 参考实现 `E:/k60-work/references/phk110-port/drivers/modem/hakios.mpss.c:2563-2565` |
| GLINK descriptor 布局 | `+0` our tail、`+4` our head、`+8` their tail、`+12` their head、`+16` reserve | 参考实现 `hakios.mpss.c:~2567-2571`（`GLINK_OUR_TAIL/OUR_HEAD/THEIR_TAIL/THEIR_HEAD/RESERVE`）；与本实现 `K60ModemLink.c:1049-1053` 的 `tx=[desc0,desc1]`、`rx=[desc2,desc3]` 逐字段一致 |
| modem SMP2P | SMEM item `435` | 同文件 `:324-325`（`ITEM_SMP2P_OURS 428` / `ITEM_SMP2P_THEIRS 435`） |
| SMEM 分区 | host0=0 ↔ host1=1 | `k60_smem_partition(&smem, 0, 1, ...)`（`K60ModemLink.c:183`） |

实现在 `drivers/PongCellular/K60ModemLink.c`：

1. `k60_modem_qrtr_probe()`（:153）只由 `pong_modem >= 2` 触发；
2. `ml_io_map_unmappable()` 映射 2 MiB SMEM 与 4 KiB IPCC（:170-178）；
3. `k60_smem_partition(0,1)` + `k60_smem_find()` 取 478/479/480/435 的偏移与长度（:183-193）；
4. `k60_qrtr_modem_ready()`（:112）读 SMP2P 435：校验 `magic == 0x504d5324`、
   `(words[1] & 0xff) == 1`、`words[2] == 1`、`20 + valid*20 <= bytes`，并找 16 字节名
   `slave-kernel` 要求 `(state & 2) && !(state & 1)`（modem 已 ready、未 stop）；
5. 几何检查：descriptor 32 字节、两个队列各 ≥ 1024 字节（:1145-1149）；
6. **活 FIFO 不 reset**：载具路径（`k60_modem_transport_prepare()`，:844）先跑 435 的
   `k60_modem_transport_stale()`（:1002，打印
   `K60MODEM stale check: modem still owns smp2p entries=%u, refusing reset`），
   再只清 AP 自己拥有的两个字 —— `desc[1]`（our head）与 `desc[2]`（their tail），
   与参考实现 `glink_reset` 清 `+4/+8` 完全一致；`desc[0]/desc[3]` 属于远端，永不写。
   走 probe 的兜底 adopt 仍保留 `desc[1]!=0 || desc[2]!=0` 的旧 gate（:1158，
   打印 `K60MODEM qrtr: glink fifo not fresh (...), not adopted`）；352d7f30 删掉的是
   `k60_modem_glink_start()` 里那份重复 gate，不是兜底。
   铁则不变：**永不 reset 活着的 FIFO**（`drivers/PongPower/QcomGlink.h:2-4`、
   `K60PmicGlink.cpp:77-78`）；
7. `qcom_glink_channel(&k60_qrtr_link, "IPCRTR", 0x4400, 4, intents, &callbacks, NULL, 1)`
   （:1063-1065、:1175-1177）：`open_now = 1`，AP 作为 initiator 先发 OPEN；
   参考实现相反（固定本地 id 1，等 modem 发 OPEN 再答 `GLINK_OPEN_ACK`，
   `hakios.mpss.c:2625` 注释 "The one channel we answer when the modem opens it"）。
   本机先开是 Pong 的路径；B 飞行要看 `K60MODEM glink: IPCRTR opened as initiator`
   之后是否收到 OPEN_ACK/OPEN —— 这是传输层第一处待验证偏差。

### 3.1 intent 数量为什么是 0x4400 × 4

DT 要求三组：`0x800×5`、`0x2000×3`、`0x4400×2`。`QcomGlink` 每个通道只支持**一组**
intent（本机最多 4 个），所以取最大尺寸 `0x4400` 与最大数量 4，覆盖 DT 的第三组并留余量；
更小的两档报文也能装进大缓冲。这是"够用"而不是"完全等价"，已记录在 `K60ModemLink.c:44-48`。

参考实现通告的是 DT 的完整三组（`hakios.mpss.c:2622`：`intents = { {0x800,5}, {0x2000,3}, {0x4400,2} }`）。
本机只发一组是 `QcomGlink` 的每通道单组限制，但总量并不缩水：4×0x4400 = 68 KiB，
与 DT 的 5×0x800 + 3×0x2000 + 2×0x4400 同为 68 KiB。若 B 飞行在 intent 协商阶段出现异常，
先读 `K60MODEM glink` 的日志，再考虑把 `QcomGlink` 扩成多组；这一条与第 7 条的 open 方向
一起，是传输层相对参考实现的两处已知偏差。

`QCOM_GLINK_MAX_CHANNELS = 1` 是**每实例**上限：modem 用自己的 `QcomGlink` 实例，
只开一条 `IPCRTR`，因此不需要改 `PongPower` 的头文件，也不会碰 PMIC 线的实例。

## 4. 门控与顺序（默认完全静默）

`drivers/PongCellular/K60ModemBoot.c`：

```c
if (!PE_parse_boot_argn("pong_modem", &enabled, sizeof(enabled)) ||
    enabled == 0) {
        return 0;                       /* 普通启动：不打印、不映射、不发 SMC */
}
printf("K60MODEM probe begin\n");
if (enabled >= 2) {                     /* 先QRTR，再PAS：reset 会掩盖已在跑的名字服务 */
        extern int k60_modem_qrtr_probe(void);
        (void)k60_modem_qrtr_probe();
}
```

| `pong_modem` | 行为 |
|---|---|
| 未设置 / `0` | 完全静默：不打印一行、不映射任何 MMIO、不发 SMC |
| `1` | 只走 L2 的 PAS 序列（auth_reset → init_image → mem_setup） |
| `>=2` | 先做本节描述的 QRTR 只读枚举，再走 PAS |

顺序的理由写在 `K60ModemBoot.c:115-117`：PAS 的 `AUTH_AND_RESET` 会把 modem 复位，
先枚举才能看到"Android 热切过来时 modem 本来就在跑"的真实状态。

## 5. 日志契约（全部以 `K60MODEM` 开头）

成功路径（`pong_modem=2`，且 FIFO 是 fresh epoch、modem 打开通道）：

```
K60MODEM probe begin
K60MODEM qrtr: glink desc=0x.../32 ours=0x.../4096 theirs=0x.../4096
K60MODEM qrtr: channel up
K60MODEM qrtr: service 21 (0x15) instance 1 node 0 port 21
...
K60MODEM qrtr: sent hello and new_lookup (0x0a) from port 0x4000
K60MODEM qrtr: verdict ok services=36 node0=36 wanted=5 malformed=0 polls=N
```

失败/边界路径（都带步骤名与返回值，不做无提示的跳过）：

| 打印 | 含义 |
|---|---|
| `K60MODEM qrtr: smem map failed at %#x` / `ipcc map failed at %#x` | 映射失败 |
| `K60MODEM qrtr: no modem smem partition rc=%d` / `smem item %u missing rc=%d` | SMEM 表缺失 |
| `K60MODEM qrtr: modem not ready (smp2p items=%u state=%#x)` | SMP2P 未就绪 |
| `K60MODEM qrtr: glink geometry wrong desc=%u ours=%u theirs=%u` | FIFO 几何不对 |
| `K60MODEM qrtr: glink fifo not fresh (...), not adopted` | FIFO 有历史数据，拒绝接管（**不 reset**） |
| `K60MODEM qrtr: no channel slot for IPCRTR` | 通道槽位不足 |
| `K60MODEM qrtr: glink poll rc=%d at %u` | 轮询错误 |
| `K60MODEM qrtr: verdict no reply services=%u node0=%u wanted=%u malformed=%u polls=%u` | 一秒内没有应答 |

`channel up/down` 的回调也会打印（`K60ModemLink.c:82`），便于确认对端有没有真的把通道打开。

**首次上机最可能看到的不是成功路径**：如果 Android 侧 modem 已经通过它自己的 GLINK 栈
在用这条通道，FIFO 的 `our_head/their_tail` 不会双零，本实现会打印 `not fresh` 并退出——
这是设计行为（宁可不枚举，也不 reset 活 FIFO）。这正是为什么 L3 的镜像必须在
`pong_modem=2` 下由 Lead 上机确认，而不是本线自己 boot。

## 6. 离线验证

1. **纯 codec 宿主测试** `scripts/tests/test-k60-modem-qrtr.c`（6 组）：
   `check_lookup`（52 字节、字段全对）、`check_hello`、`check_parse_and_verdict`
   （构造 node 0 的 NEW_SERVER 21 应答 → verdict=1；node 1 的同样应答 → verdict=0）、
   `check_services_and_array`（表容量与重复计数）、`check_malformed`（短包/命令不匹配）、
   `check_node_filter`。
   运行：`gcc -O1 -Wall -Wextra -Werror -Idrivers/PongCellular -o ... scripts/tests/test-k60-modem-qrtr.c drivers/PongCellular/K60ModemQrtr.c`，
   输出 `TESTS OK 6 groups (lookup, hello, verdict, services, malformed, node)`。
2. **补丁一致性** `scripts/tests/test-k60-modem-image.py`：把 `0622-k60-modem-qrtr.patch`
   内嵌的五份源码（`pong_modem_qrtr.h/.c`、`qcom_glink.h/.c`、`pong_modem_link.c`）
   与仓库文件逐项比对（include 名归一化 + GLINK 副本按 `k60m_glink_` 改名后比对），
   防止"内核编译的副本"与"测试的副本"漂移。
3. **构建期内核**（tag `cellular-l3-20261115a`，exit 0；上一版 `cellular-l3-20261114d` 因命令行
   缺 `pong_modem=2` 已作废）：kernel.macho
   `2841d160f3cb474861d858c39bf0be74bf929499b31e4b1526678dc9f29e0e03` 105,504,768 B，
   `strings | grep -c K60MODEM` = 33（其中 `K60MODEM qrtr` 16 条、`k60m_glink` 16 条），
   `bsd/DEVELOPMENT/` 下有 `pong_modem_qrtr.o`、`pong_modem_link.o`、`qcom_glink.o`，
   `bsd/conf/files:408-413` 是六条 standard。完整清单见 `docs/research/EIGHT-STEPS.toml`
   的 `[hardware.cellular.step.verify]` 的 artifact_check。
4. **改名原因**（本轮新增，链接期才发现）：`configs/mondrian_defconfig:78` 的
   `CONFIG_XNU_K60_PHYSICAL_BATTERY=y` 让 build-strict 用 `-Wl,-force_load` 把
   `libK60PhysicalBattery.a` 整块链进内核，而该归档里已经有 `QcomGlink.o`；0622 的
   私有副本若仍叫 `qcom_glink_*` 就会撞 8 个全局符号（`_qcom_glink_adopt/_channel/
   _poll/_reopen/_send/_stop/_rx_avail/_tx_avail`）。修法与 P-190 的 `K60Smem` 同形：
   内核副本改用 `k60m_glink_` 前缀，`drivers/PongPower/QcomGlink.{c,h}` 一字不动。

## 7. 边界（L3 明确不做的事）

- **不写** modem 分区、EFS/NV、`modemst1/2`、`fsg/fsc`；只写 GLINK ring 本身（那是传输）。
- **不 reset** modem、不对 FIFO 做任何 head/tail 写；`AUTH_AND_RESET` 只在 `pong_modem>=1` 且
  QRTR 枚举之后才可能发生。
- **不发 QMI 请求**：本层只做名字服务（control 端口）的 HELLO + NEW_LOOKUP，
  没有 QMI client 分配、没有 CTL 服务交互、没有 QMAP/IPA 数据面（`dts/mondrian.dts:295-334` 的
  IPA 节点完全没碰；DT 的 `pas-ids = <0x0f>` 与 modem 的 4 互不相干）。
- **不自行 boot**：镜像交 Lead，由 Lead 在用户同意后执行。

## 8. 下一步（L4 候选）

1. `pong_modem=2` 上机确认 `verdict ok`，或确认 `glink fifo not fresh` 的实际形态；
2. QMI client 分配（CTL 服务 0，`QMI_CTL_REQ` 0x0020 等）与第一条 `QMI_GET_VERSION`；
3. `rmtfs`（EFS 请求的搬运工）与 `modemst1/2` 只读挂载；
4. 电话/短信需要 iOS profile（现为 `ipados-16.6.1-20G81`），属另一条线，不在本线范围。

## 9. 相关文件

| 文件 | 作用 |
|---|---|
| `drivers/PongCellular/K60ModemQrtr.h` / `.c` | 纯 codec：编码 HELLO/NEW_LOOKUP、解析 NEW_SERVER、判据 |
| `drivers/PongCellular/K60ModemLink.c` | SMEM/IPCC/GLINK 传输与轮询 |
| `drivers/PongPower/QcomGlink.h` / `.c` | 被复制进内核的 GLINK 实现（原 PMIC 线，本线只读复用） |
| `patches/xnu/0622-k60-modem-qrtr.patch` | 把上述 5 个源文件落进 `bsd/dev/` |
| `scripts/append-conffiles.py` | 注册 `pong_modem_qrtr.c`、`pong_modem_link.c`、`qcom_glink.c` |
| `scripts/tests/test-k60-modem-qrtr.c` | 6 组宿主测试 |
| `scripts/tests/test-k60-modem-qrtr.c` | 6 组宿主测试 |

## 10. 实机结论与外部参考复核（2026-11-19）

### 10.1 硬件已经把“枚举”这条路探到底

k35 起 QcomBaseband 组件真的链进内核（22/22 服务发布，S6 PASS），此后每一次 B 形态飞行都在同一处收尾：

| 飞行 | 窗口 | 看到什么 |
|---|---|---|
| k36 | 10 s | 只有两条 NEW_SERVER：`66 (0x42) instance 46081 port 2`、`43 (0x2b) instance 4610 port 1` |
| k37 | 60 s | 两条广播 `NEW_LOOKUP`（全量 + service 2）零应答，服务数不变 |
| k38 | 60 s | 直接向 Android 记录的 DMS 固定端口 96 发 `GetRevision`，仍然零应答 |
| k39 | 240 s | 8 次交替 lookup + 8 次固定端口请求，服务数始终 2；240 s 循环被 300 s autoreset 截断 |
| k41 | 240 s | 把 IPCRTR 的 open 提前到 glink fifo 出现后 24 ms（比 smp2p ready 早 5 秒），服务仍是 2 |
| k42 | 240 s | modem 一开始给足 30 个接收缓冲，随后在 35–45 秒**不再读环、不再回 RX_DONE** |
| k43 | 240 s | mode 0（不发 lookup、不碰固定端口）复现同一停摆 ⇒ 与那两类请求无关 |

### 10.2 为什么“问服务”在这块板上注定问不到

`01-ANDROID-INVENTORY.md` §5.5 的 strace 显示：Android 上 `qrtr-lookup` 发出的 `0x0a NEW_LOOKUP` 由 **AP 自己的 qrtr_ns**（内核里的名称服务，逐条重放它收到的 NEW_SERVER 表）回答，modem 没有回答 lookup 的义务。
而 modem 的 QMI 服务是开机时**主动注册**的广播：它注册时我们这条 IPCRTR 通道还不存在（要等 AUTH_AND_RESET 之后 glink fifo 才出现），广播就丢了。k41 把 open 提前到 fifo 出现后 24 ms 也没赶上，说明注册发生得更早，甚至可能在 modem 固件 init 阶段、glink 通道建立之前。

因此“忠实枚举”需要的是**AP 侧常驻的 QRTR 名称服务 + 常驻 worker**（Pong 的形态：`PongModemQrtr.cpp:108` 的 worker 一直 poll，`:245` 注明所有 GLINK 调用都在同一个 owner 线程），而不是一次 boot 窗口里的探针。
备选是绕开枚举、直接按 Android 记录的固定端口表连（DMS 96、EFS 21、WDS 82、NAS 77、UIM 80）——
快，但换固件就可能错，只能作为兜底。

### 10.3 外部参考复核（2026-11-19）

用户指定转向三份更新的参考：`kmu1757/UniXNU-t970`、`qiumochen/UniXNU-zizhan`（用户态仍参考 sheng）。

| 仓库 | 是什么 | 对基带的意义 |
|---|---|---|
| `qiumochen/UniXNU-zizhan` | 小米 MIX Fold 2（**SM8475，与本板同 SoC**），Pong 派生 | 它的 `porting.toml` cellular 区写着 “No cellular implementation or device verification has been performed in this repository”，下一步也只是“盘点 modem 传输”——**同 SoC 的兄弟也没有做过基带**，抄不到枚举实现 |
| `kmu1757/UniXNU-t970` | 三星 Tab S7+ / S20+（SM8250），Pong 派生、代码更新 | 驱动走 submodule；没有 `QcomGlink`，也没有 cellular 实现，价值在 GPU/用户态与构建组织 |
| `UniXNU/UniXNU-sheng` | 小米平板 6S Pro（SM8550），官方维护 | 用户态参考（`migration/ipados18`、`kits/`），与基带无关 |

唯一直接相关的一条：zizhan 的 `drivers/PongPower/QcomGlink.c`（455 行，与我们 525 行的实现同源但更早重写）
在 INTENT 分支里**对每一对 (size, id) 一律入表，不校验 id 是否为 0**；表满时驱逐“空闲且更小”的槽位并
`dropped++`，而不是判定流损坏（注释引用 `UniXNU-sheng 552b674`）。这与我们 0622 里那条
`if (!size)` 的 delta 结论一致：**id 0 是合法的缓冲编号，不是坏帧**——k35 的硬件日志（w2=0x80、w3=0）
正是这个形态。

