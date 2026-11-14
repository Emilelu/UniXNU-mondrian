# QRTR 判决日志样例（上机对号入座）

> **这些样例是从源码的 printf 格式串推出来的，不是实测。**
> 出处逐条标在每段末尾。真实上机时数字会不同（服务条数、port、polls），
> 但**行文、顺序、字段名**不会变——格式串就是契约。

## 0. 先记三条读法

1. **默认完全静默**：内核命令行没有 `pong_modem` 或等于 0 时，一行都不会打印
   （`K60ModemBoot.c:109-112` 在 `printf` 之前就 return）。看不到任何 `K60MODEM` 行
   **不是失败**，是没开门。
2. **`verdict` 只有两种取值**：`ok` 或 `no reply`（`K60ModemLink.c:263` 的三元表达式）。
   所以日志里是 `verdict ok …` 或 `verdict no reply …`，没有单独的 `verdict no`。
3. **有些失败分支没有 verdict 行**：`glink fifo not fresh`（`:211-213`）与
   `modem not ready`（`:198-200`）都在打印 verdict 之前就 return 了。
   上机若只看到这些行而没有 verdict 行，那是**设计好的早退**，不是日志被截断。

## 1. 用例 A：没开门（预期中的最常见形态）

```text
（无输出）
```

门控：内核命令行无 `pong_modem`，或 `pong_modem=0`。
判读：正常。这一轮什么都没碰——carveout 没映射、SMEM 没读、SMC 没发。
出处：`K60ModemBoot.c:109-112`（`!PE_parse_boot_argn(...) || enabled == 0` → return 0）。

## 2. 用例 B：`pong_modem=1`，carveout 里没有镜像

```text
K60MODEM probe begin
K60MODEM carrier absent: no modem image staged at 0x8bc00000
K60MODEM pas skipped, nothing was handed to the secure monitor
```

判读：**这是 L2 第一次上机最可能的正确结果**。头部 16 字节不匹配 `modem.b01` 的签名
（`0e c0 00 58 / 00 c0 00 58` ×3），所以拒绝发 SMC。三行之后就结束，没有 plan/copy/PAS 行。
出处：`K60ModemBoot.c:113`、`:134-136`、签名比对在 `K60ModemPas.h` 的 `k60_modem_carrier_ok()`。

## 3. 用例 C：`pong_modem=1`，签名命中但窗口映射失败

```text
K60MODEM probe begin
K60MODEM cannot map the carveout head 0x8bc00000
```

判读：`ml_io_map_unmappable()` 返回 0。两行即止，没有 PAS 行。
出处：`K60ModemBoot.c:124-131`。

## 4. 用例 D：`pong_modem=1`，签名命中且 PAS 全程成功

```text
K60MODEM probe begin
K60MODEM carrier present at 0x8bc00000
K60MODEM plan rows=30 copied=109060761 zeroed=211012967 base=0x8bc00000 window=0x13200000
K60MODEM copy skipped: image already staged at 0x8bc00000
K60MODEM auth_reset ok
K60MODEM init_image ok segments=27
K60MODEM mem_setup ok base=0x8bc00000 span=0x13200000
```

判读：七行全出即 PAS 序列走完。四个数字是**固定值**（`pong_modem_table.h` 生成时算定）：
`rows=30`、`copied=109060761`、`zeroed=211012967`；`segments=27` 是 30 段里去掉 3 个纯 bss 段
（b14/b21/b30）后的可认证段数。**这三个数字对不上就说明段表与固件不一致，先别信后面的结论。**
出处：`K60ModemBoot.c:48`、`:61`、`:70`、`:87`、`:95`。

## 5. 用例 E：`pong_modem=1`，PAS 中途失败（每步一行，带返回值）

### E1 `AUTH_AND_RESET` 被拒

```text
K60MODEM probe begin
K60MODEM carrier present at 0x8bc00000
K60MODEM plan rows=30 copied=109060761 zeroed=211012967 base=0x8bc00000 window=0x13200000
K60MODEM copy skipped: image already staged at 0x8bc00000
K60MODEM scm cmd=0x5 rc=-1 x0=0x2 x1=0x0
K60MODEM auth_reset failed rc=-1
```

判读：`cmd=0x5` = `K60M_SCM_PAS_AUTH_AND_RESET`；`rc=-1` = `K60ModemPasDenied`；
`x0=0x2` 是 SCM 的拒绝码（具体含义按 secure monitor 侧定义，本线不猜）。
`x1=0` 说明第二寄存器干净。序列到此为止，**后面的行不会出现**。

### E2 某一段 `INIT_IMAGE` 被拒

```text
K60MODEM auth_reset ok
K60MODEM scm cmd=0x1 rc=-1 x0=0x2 x1=0x0
K60MODEM init_image failed seg=7 addr=0x8bf40000 bytes=1441792 rc=-1
```

判读：`cmd=0x1` = `INIT_IMAGE`；`seg` 是**表内下标**（0 起），`addr` 是该段物理地址，
`bytes` 是 `p_filesz`。用 `seg` 号去 `pong_modem_table.h` 数第几行，就能说出是哪一段被拒。

### E3 `MEM_SETUP` 被拒

```text
K60MODEM init_image ok segments=27
K60MODEM scm cmd=0x2 rc=-1 x0=0x2 x1=0x0
K60MODEM mem_setup failed rc=-1
```

判读：`cmd=0x2` = `MEM_SETUP`。走到这里说明 27 段全部认证通过，只剩最后一步。
出处：`K60ModemPas.c:52-56` 的失败行，`K60ModemBoot.c:67`、`:81`、`:92`。

## 6. 用例 F：`pong_modem=2`，GLINK FIFO 不是新 epoch（本线预判的首选结果）

```text
K60MODEM probe begin
K60MODEM qrtr: glink desc=0x0/32 ours=0x0/0 theirs=0x0/0
K60MODEM qrtr: glink fifo not fresh (our_head=1048576 their_tail=0), not adopted
```

判读：**没有 verdict 行，这是对的。** `our_head` 非 0 表示 Android 那一轮已经用过这对队列，
本线拒绝 reset 活 FIFO，直接放弃。`desc=0x0/32` 表示描述符在 SMEM 偏移 0、32 字节，
`ours=0x0/0` 与 `theirs=0x0/0` 表示两个队列的偏移/长度读出来是 0 —— 说明 SMEM 里
这两个 item 还没被 modem 初始化（冷启动且 modem 没跑），或者 modem 用的是另一套 item。
出处：`K60ModemLink.c:195-196`、`:211-213`。

## 7. 用例 G：`pong_modem=2`，SMP2P 说 modem 没就绪

```text
K60MODEM probe begin
K60MODEM qrtr: glink desc=0x12000/32 ours=0x12020/4096 theirs=0x13020/4096
K60MODEM qrtr: modem not ready (smp2p items=6 state=0x1)
```

判读：`items=6` 是 SMP2P 块里有效条目数，`state=0x1` 是 `slave-kernel` 那个条目的状态字。
`0x1` 是 fatal 位（`state & 1`）⇒ 未就绪；`0x2` 才是 ready 位。**同样没有 verdict 行。**
出处：`K60ModemLink.c:197-200`，判据在 `:146`（`(state & 2) != 0 && (state & 1) == 0`）。

## 8. 用例 H：`pong_modem=2`，通道通了但一秒内没有应答

```text
K60MODEM probe begin
K60MODEM qrtr: glink desc=0x12000/32 ours=0x12020/4096 theirs=0x13020/4096
K60MODEM qrtr: waiting for the modem to open IPCRTR
K60MODEM qrtr: channel up
K60MODEM qrtr: sent hello and new_lookup (0x0a) from port 0x4000
K60MODEM qrtr: verdict no reply services=0 node0=0 wanted=0 malformed=0 polls=500
```

判读：通道被 modem 打开、包发出去了、但一个 NEW_SERVER 都没回。
`polls=500` 说明轮询跑满（500 × 2 ms ≈ 1 秒）。这条**是失败**，但不是 GLink 失败——
是名字服务没回，下一步查 QRTR 头里的 `from_node` 是否被 modem 当成别的节点。
出处：`K60ModemLink.c:82`、`:234`、`:254-255`、`:262-265`。

## 9. 用例 I：`pong_modem=2`，成功枚举（判据达成）

```text
K60MODEM probe begin
K60MODEM qrtr: glink desc=0x12000/32 ours=0x12020/4096 theirs=0x13020/4096
K60MODEM qrtr: waiting for the modem to open IPCRTR
K60MODEM qrtr: channel up
K60MODEM qrtr: sent hello and new_lookup (0x0a) from port 0x4000
K60MODEM qrtr: service 21 (0x15) instance 0 node 0 port 21
K60MODEM qrtr: service 3 (0x3) instance 0 node 0 port 77
K60MODEM qrtr: service 11 (0xb) instance 0 node 0 port 80
K60MODEM qrtr: service 1 (0x1) instance 0 node 0 port 82
K60MODEM qrtr: service 4097 (0x1001) instance 1 node 0 port 28
K60MODEM qrtr: service 16 (0x10) instance 0 node 0 port 111
K60MODEM qrtr: verdict ok services=37 node0=37 wanted=5 malformed=0 polls=93
```

判读：判据行 `verdict ok` + `wanted=5`。要点：

- `services` 是收到的 NEW_SERVER 条数（含同号多 instance），`node0` 是其中 `from_node == 0` 的条数。
- `wanted` 只数 `{1, 3, 11, 16, 21}`（`K60ModemQrtr.c:104-113`）；`4097` 会被打印但**不计入**。
- `polls=93` 说明收满后提前退出（`K60ModemLink.c:257-259`：`services != 0 && i > 60` 才 break）。
- port 值随 modem 复位变化，**比对时不作判据**（见 `08-QRTR-SERVICES.md` §3 末段）。

## 10. 用例 J：`pong_modem=2`，回包格式不对（malformed）

```text
K60MODEM qrtr: service 21 (0x15) instance 0 node 0 port 21
K60MODEM qrtr: verdict ok services=3 node0=3 wanted=1 malformed=2 polls=120
```

判读：`malformed=2` 表示有两条包在 `k60_qrtr_note()` 里被拒（`header.size != 20` 或
`control.command != header.type`）。**verdict 仍可能是 ok**，因为判据只看 wanted。
malformed 非 0 时要回头核 32 字节头的字段顺序，或先跑宿主测试 `test-k60-modem-qrtr.c` 复核 codec。
出处：`K60ModemQrtr.c:139-151`。

## 11. `pong_modem=2` 的完整行序（把上面几段拼起来）

```text
K60MODEM probe begin                    ← Boot.c:113
K60MODEM qrtr: …（QRTR 全段，可能早退）   ← Link.c，见用例 F/G/H/I/J
K60MODEM carrier absent … / carrier present …
K60MODEM plan rows=…
K60MODEM copy skipped: …
K60MODEM auth_reset ok
K60MODEM init_image ok segments=27
K60MODEM mem_setup ok base=… span=…
```

**顺序是硬的**：QRTR 段一定在 `carrier` 之前（`K60ModemBoot.c:118-122` 在映射 carveout 之前调用），
这是设计选择——PAS 的 `AUTH_AND_RESET` 会把 modem 复位，先枚举才能看到 Android 留下的现场。

## 12. 抓日志与自查命令

```sh
# 只留本线的行
grep 'K60MODEM' <console.log>
# 判决行
grep 'K60MODEM qrtr: verdict' <console.log>
# 服务条数与判决里的 services 对账
grep -c 'K60MODEM qrtr: service ' <console.log>
# 五个判据号各命中几次，加起来应等于 wanted
grep -E 'service (21|1|11|3|16) ' <console.log> | wc -l
```

## 13. 与 08 的对应

| 08 §7 的结论行 | 本篇样例 |
| --- | --- |
| `verdict ok` 且 `wanted >= 3` | 用例 I |
| `verdict ok` 但 `wanted == 0` | 用例 I 去掉五个判据行（服务号换成别的） |
| `verdict no reply`、`services > 0`、`node0 == 0` | 用例 I 的 `node0=0` 变体 |
| `verdict no reply`、`services == 0` | 用例 H |
| `malformed > 0` | 用例 J |
| 没有 verdict 行 | 用例 F（not fresh）或 G（modem not ready） |
