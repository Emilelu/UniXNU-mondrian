# UCSI / Type-C 角色判定：主机侧可验证部分

本文只收录**不需要 ADSP 固件字节、不需要上机**就能定论的部分：协议线格式、角色裁决规则、
K60 侧已有的挂载点、以及一份可回归的主机自测。凡是要等 ADSP 起来的，统一列在 §9。

## 0. 一句话结论

Type-C 的 CC 检测与角色裁决**不在 AP 侧寄存器里**，它在 ADSP 的 `msm/adsp/charger_pd` 保护域，
经 `PMIC_RTR_ADSP_APPS` GLINK 通道用 UCSI 上报；而 K60 侧**已经有这条通道的全部基础设施**
（`QcomGlink.c` + `K60PmicGlink.cpp` + `K60Battmgr.c`，目前只跑电池 owner 32778），
所以 UCSI 的接入点不是"新写一条传输"，而是**在已有 receive 回调前加一层 owner 多路复用**
（32778 → 电池，32779 → UCSI）。线格式与角色表已由 `ucsi-host-selftest.c` 在主机上回归通过。

## 1. 证据链总表

| # | 结论 | 证据类别 | 位置 |
| --- | --- | --- | --- |
| 1 | UCSI 挂在 `qcom,pmic_glink` 下，protection domain 是 `msm/adsp/charger_pd` | 同型（固件 DT） | `E:/k60-work/scratch/usb/mondrian.dts:8555-8578` |
| 2 | 随镜像的 DT **没有** ucsi / altmode 子节点 | 实测（构建产物） | `hardware.dtb` sha256 `2d044eaa…f33cd`，反编译 210 行 |
| 3 | GLINK 线格式：owner 32779、type 1、opcode 0x11/0x12/0x13、48 字节 UCSI 缓冲 | 官方（主线 v6.6） | `linux/pmic_glink.h`、`linux/ucsi_glink.c:14-22` |
| 4 | UCSI 数据结构偏移与 CCI 位定义 | 官方（主线 v6.6） | `linux/ucsi.h:21-36`、`:75`、`:99-100`、`:234`、`:260-263` |
| 5 | 角色裁决规则：线上是 host → 设备角色；线上是外设 → 主机角色；无回答 → 设备角色 | 官方（UniXNU 文档） | `UniXNU-upstream/docs/porting/usb.md:100-101` |
| 6 | sheng 的客户端实现（weak_import 五个函数 + 20 ms 定时器 + `ucsi-delay`） | 同型（同 SoC 实机代码） | `UniXNU-sheng/package/ShengBattery.cpp:30-91`、`:241-242` |
| 7 | K60 已有 GLINK 通道与电池 owner 过滤（32778） | 本仓代码 | `drivers/PongPower/K60PmicGlink.cpp:84`、`K60Battmgr.c:149` |
| 8 | 线格式与角色表可在主机上回归 | 本仓自测 | `docs/research/usb/ucsi-host-selftest.c`、`UCSI-SELFTEST-OUTPUT.txt` |

## 2. DT：固件侧有，随镜像侧没有

**固件侧 DT**（`E:/k60-work/scratch/usb/mondrian.dts`，来自 UEFI 的 `sm8475-xiaomi-mondrian.dtb`）：

```
dts:8555  qcom,pmic_glink {
dts:8556      compatible = "qcom,pmic-glink";
dts:8557      qcom,pmic-glink-channel = "PMIC_RTR_ADSP_APPS";
dts:8558      qcom,subsys-name = "lpass";
dts:8559      qcom,protection-domain = "tms/servreg", "msm/adsp/charger_pd";
dts:8560      depends-on-supply = <0x8f>;
dts:8562      qcom,battery_charger { compatible = "qcom,battery-charger"; phandle = <0x335>; };
dts:8567      qcom,ucsi { compatible = "qcom,ucsi-glink"; phandle = <0x336>; };
dts:8572      qcom,altmode { compatible = "qcom,altmode-glink"; #altmode-cells = <0x01>; phandle = <0x337>; };
dts:8555  };
dts:21364   aliases: ucsi    = "/soc/qcom,pmic_glink/qcom,ucsi";
dts:21365   aliases: altmode = "/soc/qcom,pmic_glink/qcom,altmode";
```

**随镜像走的 DT** 是 4024 B 的 `hardware.dtb`
（`/opt/k60/trees/lead-out/mondrian/ipados-16.6.1-20G81/mondrian/device-tree/hardware.dtb`，
sha256 `2d044eaa08b7e58c0510a33da795c960085e13d6943cd4c25e0e050e0bfa33cd`，与
`usb-20261114g` manifest 的 `dtb` 一致）。反编译只有 210 行，`:201-207` 是

```
pmic-glink {
    compatible = "qcom,pmic-glink";
    qcom,pmic-glink-channel = "PMIC_RTR_ADSP_APPS";
    battery-charger { compatible = "qcom,battery-charger"; };
};
```

即**没有 `qcom,ucsi`、没有 `qcom,altmode`、也没有 ssphy/hsphy/dwc3**。
仓库源 `dts/mondrian.dts:189-197` 同样是这个最小形态。

> 这一条不是缺陷，而是主线模型的正常形态：主线 `pmic_glink.c` 把 UCSI / altmode / power-supply
> 建成 **auxiliary device**（`linux/pmic_glink.c:131` `pmic_glink_add_aux_device`，
> `:272` `ucsi_aux`、`:277` `altmode_aux`、`:282` `ps_aux`），**不读 DT 子节点**。
> 下游 DT 里的 `qcom,ucsi` 子节点是给下游 `ucsi_glink` 驱动匹配用的。
> 因此：走"代码里按 owner 注册客户端"这条主线模型，DT 不需要改；走"DT 驱动"模型才需要加节点，
> 那属于 `dts/`（不在本线写作用域，片段见 §10）。

## 3. 主线协议（v6.6）

### 3.1 承载层

```c
/* linux/pmic_glink.h */
#define PMIC_GLINK_OWNER_BATTMGR  32778
#define PMIC_GLINK_OWNER_USBC     32779
#define PMIC_GLINK_OWNER_USBC_PAN 32780
#define PMIC_GLINK_REQ_RESP 1
#define PMIC_GLINK_NOTIFY   2
struct pmic_glink_hdr { __le32 owner; __le32 type; __le32 opcode; };  /* 12 B */
```

`pmic_glink.c` 按 **owner id** 多路复用：`devm_pmic_glink_register_client()` 里
`client->id = id`（`:84`）、挂进 `pg->clients`（`:90`），收到消息时按 `hdr->owner` 找客户端。
这正是 K60 侧要复刻的那一层（见 §6）。

### 3.2 UCSI 承载

```c
/* linux/ucsi_glink.c */
#define UCSI_BUF_SIZE            48
#define UC_UCSI_READ_BUF_REQ     0x11
#define UC_UCSI_WRITE_BUF_REQ    0x12
#define UC_UCSI_USBC_NOTIFY_IND  0x13
```

| 消息 | 长度 | 结构 |
| --- | --- | --- |
| `read_buf_req` | 12 B | 只有 hdr（owner=32779, type=1, opcode=0x11） |
| `read_buf_resp` | 64 B | hdr + `u8 buf[48]` + `u32 ret_code` |
| `write_buf_req` | 64 B | hdr + `u8 buf[48]` + `u32 reserved` |
| `write_buf_resp` | 16 B | hdr + `u32 ret_code` |
| `notify_ind` | 24 B | hdr + `u32 notification` + `u32 receiver` + `u32 reserved` |

读路径（`ucsi_glink.c:76-94`）：发 READ_BUF_REQ → 等 `read_ack`（**5 s 超时**，
超时打 `timeout waiting for UCSI read response`）→ `memcpy(val, &read_buf[offset], val_len)`。
写路径（`:113-119`）同构。通知（`:209-232`）：读 `UCSI_CCI` →
`con_num = UCSI_CCI_CONNECTOR(cci)` → 非零则 `ucsi_connector_change()`。

### 3.3 UCSI 数据结构

```c
/* linux/ucsi.h:21-25 */
#define UCSI_VERSION     0
#define UCSI_CCI         4
#define UCSI_CONTROL     8
#define UCSI_MESSAGE_IN  16
#define UCSI_MESSAGE_OUT 32
/* :28-36 */
#define UCSI_CCI_CONNECTOR(_c_) (((_c_) & GENMASK(7, 1)) >> 1)
#define UCSI_CCI_LENGTH(_c_)    (((_c_) & GENMASK(15, 8)) >> 8)
#define UCSI_CCI_BUSY             BIT(28)
#define UCSI_CCI_ACK_COMPLETE     BIT(29)
#define UCSI_CCI_ERROR            BIT(30)
#define UCSI_CCI_COMMAND_COMPLETE BIT(31)
```

命令字：`UCSI_ACK_CC_CI = 0x04`（`:75`）、`UCSI_SET_NOTIFICATION_ENABLE = 0x05`、
`UCSI_GET_CONNECTOR_STATUS = 0x12`、`UCSI_PPM_RESET = 0x01`。
ACK 位：`UCSI_ACK_CONNECTOR_CHANGE = BIT(16)`、`UCSI_ACK_COMMAND_COMPLETE = BIT(17)`（`:99-100`）。

> **一个曾经踩过的坑（写在这里防回归）**：控制字是 64 位，但 ACK/notify 掩码就在**低 32 位**，
> 不再左移 16。主线 `ucsi.c:43` 是 `ctrl = UCSI_ACK_CC_CI;`（裸值），
> `:1031-1032` 是 `c = UCSI_SET_NOTIFICATION_ENABLE | con->ucsi->ntfy;`。
> 第一版自测多移了一次 `<<16`，被往返断言抓住。

### 3.4 连接器状态与伙伴类型

`struct ucsi_connector_status`（`ucsi.h:234`）里 `flags` 字段：
`UCSI_CONSTAT_PARTNER_TYPE((f) & GENMASK(15,13) >> 13)`（`:260`），取值
1=DFP、2=UFP、3=CABLE、4=CABLE_AND_UFP、5=DEBUG、6=AUDIO（`:261-263`）。

## 4. 角色裁决规则

官方文档原句（`UniXNU-upstream/docs/porting/usb.md:100-101`）：

> A host on the cable selects the device role and a peripheral selects the host role. With
> no answer from either source, the device role runs.

落到 K60：

| 线上伙伴（PARTNER_TYPE） | 含义 | K60 角色 | 依据 |
| --- | --- | --- | --- |
| DFP (1) | 对端是主机 | **device** | usb.md:100-101 |
| UFP (2) | 对端是外设（U 盘/键盘） | **host** | usb.md:100-101 |
| CABLE_AND_UFP (4) | 带电源的线 + 外设 | **host** | 同上（仍是对端外设） |
| DEBUG (5) | 调试配件 | **device** | 同上（不选 host 的安全默认） |
| AUDIO (6) | 音频转接 | **device** | 同上 |
| CABLE (3) / 未连接 | 无回答 | **device**（默认） | usb.md:101 "no answer … device role runs" |

这条表被 `ucsi-host-selftest.c` 的 `role_from_connector_status()`（`:128-143`）固化，
第 4 组与第 6 组断言覆盖全部七种输入。

## 5. sheng 的客户端（同 SoC 实机代码）

`UniXNU-sheng/package/ShengBattery.cpp` 是唯一能看到"官方 USB 栈怎么被喂角色"的实机实现：

```cpp
// :30  注释原文
// The USB-C owner (32779) shares this channel: QcomDwc3 asks what is on the cable over UCSI.
// :31-34  weak_import
uint32_t qcom_ucsi_start(uint8_t *);
uint32_t qcom_ucsi_receive(const uint8_t *, uint32_t, uint8_t *);
uint32_t qcom_ucsi_tick(uint8_t *);
bool     qcom_ucsi_polling(void);
// :36
uint32_t sheng_adsp_send(ShengAdspChannel *, const void *, uint32_t);
// :81-82
void ucsiSend(unsigned n) {
    if (n) sheng_adsp_send(channel, ucsiOut, n);
    if (qcom_ucsi_polling && qcom_ucsi_polling()) ucsiTimer->setTimeoutMS(20);
}
// 收到消息时（首 4 字节就是 pmic_glink_hdr.owner 的小端值）
if (qcom_ucsi_receive && length >= 4 && (data[0] | data[1]<<8 | data[2]<<16 | (uint32_t)data[3]<<24) == 32779u)
    self->ucsiSend(qcom_ucsi_receive(data, length, self->ucsiOut));
```

三个可移植的设计点：

1. **首条命令是 `PPM_RESET`**，且被 `ucsi-delay`（秒，上限 600，`:75`、`:241-242`）延迟——
   因为 ADSP 侧 PPM 就绪晚于 AP 侧驱动。
2. **按需 20 ms 定时器**：`qcom_ucsi_polling()` 为真才起，而不是常驻轮询。
3. **owner 判定在 4 字节处**，与主线 `pmic_glink_hdr` 完全一致——这就是 §6 多路复用的依据。

## 6. K60 侧的接入点（本轮最关键的新结论）

K60 仓库**已经有完整的 GLINK 客户端**，只是只为电池服务：

| 文件 | 事实 |
| --- | --- |
| `drivers/PongPower/QcomGlink.h:17` | `#define QCOM_GLINK_MAX_CHANNELS 1u` —— 只有一个通道槽 |
| `drivers/PongPower/QcomGlink.h:86` | `int qcom_glink_adopt(QcomGlink *, QcomGlinkFifo tx, QcomGlinkFifo rx, void (*kick)(void *), void *) ` |
| `drivers/PongPower/QcomGlink.h:89-90` | `qcom_glink_channel(g, name, intent_size, intent_count, storage, client, ctx, open_now)` |
| `drivers/PongPower/QcomGlink.h:93/95` | `qcom_glink_poll()` / `qcom_glink_send()` |
| `drivers/PongPower/K60PmicGlink.cpp:84` | `channel = qcom_glink_channel(&native, "PMIC_RTR_ADSP_APPS", 256, 4, intents, &callbacks, this, 1);` |
| `drivers/PongPower/K60PmicGlink.cpp:60/64` | `k60_smem_partition(...)` / `k60_smem_find(..., ids[i], ...)` 定位 desc/tx/rx |
| `drivers/PongPower/K60Battmgr.c:149` | `if (!data || bytes < 12 || le32(data) != K60_BATTMGR_OWNER) { b->ignored++; return K60BmIgnored; }` |
| `drivers/PongPower/K60Battmgr.h:12` | `#define K60_BATTMGR_OWNER 32778u` |

也就是说：**32779 的 UCSI 消息现在会走同一条 GLINK 通道、同一个 receive 回调，
然后在 `K60Battmgr.c:149` 被当作"不是我的 owner"静默丢弃。**
接入 UCSI 不需要新的传输层，只需要在 `K60Battery::receive()`（`K60Battery.cpp:284-289`）
调用 `k60_battmgr_receive()` **之前**按 `le32(data)` 分流：

```c
switch (le32(data)) {
case 32778: k60_battmgr_receive(&manager, data, bytes); break;   /* 电池，现状不变 */
case 32779: k60_ucsi_receive(&ucsi, data, bytes);      break;   /* 新增 */
default:    /* 未注册 owner：计数，不猜 */ break;
}
```

这与主线 `pmic_glink.c` 的 client-list 语义同构（`:84` `client->id`、`:90` `list_add`），
只是 K60 侧用 `switch` 而不是链表——通道只有一条（`QCOM_GLINK_MAX_CHANNELS 1`），
多开一条通道反而是错的方向。

> 注意：`K60PmicGlink` 的 `open()` 需要 `K60AdspGlinkHandoff` lease（104 字节），
> 而仓库里**没有生产者**（`docs/research/battery/GLINK-HANDOFF.md:14`：
> `grep -rn 'k60-adsp-glink-handoff' drivers/ patches/` 只有消费点）。
> 所以 §6 的分流点可以在主机上写好、审完，但**运行时仍要等 PAS1/ADSP**。

**共享通道提示（2026-11-14，Lead 确认）：** 这条 `PMIC_RTR_ADSP_APPS` GLINK 通道
是**多条线共用**的——owner 32778（`PMIC_GLINK_OWNER_BATTMGR`）是电池/charger 线，
owner 32779（`PMIC_GLINK_OWNER_USBC`）才是 UCSI（主线 `pmic_glink.h:11-13`）。
charger/ADSP 线在 `K60Battmgr.c:149` 之后加自己的处理时，**不要把非 32778 的消息
继续静默丢弃**——32779 分支是 UCSI 线的入口，`default` 分支只计数。
分流实现见上面 `switch (le32(data))` 代码块；改 `receive()` 前先与两条线对齐。

## 7. 主机侧自测（可回归）

`docs/research/usb/ucsi-host-selftest.c`（287 行，C11，零依赖，不接触设备）：

```sh
cc -std=c11 -Wall -Wextra -o /tmp/ucsi-host-selftest docs/research/usb/ucsi-host-selftest.c
/tmp/ucsi-host-selftest
```

输出存档在 `docs/research/usb/UCSI-SELFTEST-OUTPUT.txt`，当前 `RESULT: PASS (0 failures)`，
六组共 40+ 断言：

| 组 | 覆盖 |
| --- | --- |
| 1 消息布局 | hdr 12 / read_req 12 / read_resp 64 / write_req 64 / write_resp 16 / notify_ind 24 |
| 2 SET_NOTIFICATION_ENABLE | 控制字 `0x0000000048010005`（cmd 0x05 + bit16/27/30，无 connector 字段） |
| 3 NOTIFY_IND → CCI | 通知类型 0x13、CCI 的 COMMAND_COMPLETE、connector 由 bits 7:1 解出 |
| 4 角色判定表 | §4 的七种输入全覆盖 |
| 5 ACK_CC_CI | 0x04 + BIT(16) + BIT(17) |
| 6 全往返 | PPM 收写 → 读回 flags → 角色（host on cable → device / peripheral → host） |

它同时是 §3.3 那个 `<<16` 坑的回归网。

## 8. 与"上机可验证"的边界

| 事项 | 现在能否定论 | 依据 |
| --- | --- | --- |
| UCSI 线格式、消息长度、owner、opcode | ✅ 能 | 主线源码 + 自测 |
| 角色裁决规则 | ✅ 能 | 官方 usb.md:100-101 |
| K60 侧接入点（owner 分流位置） | ✅ 能 | 本仓 `K60Battmgr.c:149` / `K60PmicGlink.cpp:84` |
| DT 是否需要加 `qcom,ucsi` 子节点 | ✅ 能（走主线模型不需要） | 主线 `pmic_glink.c:131/272/277` |
| PPM 实际支持的连接器数量、CAM、PDO | ❌ 不能 | 需要 PPM 在线（ADSP） |
| UCSI 首条命令的合适延迟 | ❌ 不能 | sheng 用 boot arg `ucsi-delay` 现场调，K60 无实测 |
| 角色切换后 DWC3 core soft reset 的时序 | ❌ 不能 | 官方只写"每次换角色做一次 core soft reset"，无寄存器级证据 |

## 9. 阻塞与未决

1. **ADSP 不在线**：`usblog-20261114-usb-hb2/console.log` 里 `adsp|glink` 命中 **0 次**；
   现有 0612/0613/0614 三个 ADSP 补丁只到 PAS 的 SMC 封装与调用点
   （`0613-k60-adsp-pas.patch:59-66` 声明 `k60_adsp_auth_and_reset` 等，`:120` 打 `K60PAS cmd=… rc=…`），
   尚未见到任何 `K60PAS` 输出。⇒ UCSI 的运行时验证排在 PAS1 之后。
2. **GLINK lease 无生产者**（`docs/research/battery/GLINK-HANDOFF.md:14`、`:80-99`）：
   即使 PAS1 起来，还缺 SMEM 分配器与 lease 发布，这是电池/音频/UCSI 三条线共用的前置。
3. **`ucsi-delay` 等价物未定**：sheng 有 boot arg，K60 要么沿用（需 `board.toml` 改动，
   不在本线写作用域），要么在驱动里做有界重试。
4. **altmode 完全未碰**：`qcom,altmode-glink`（phandle 0x337）与 DisplayPort 交替模式相关，
   依赖 QMP 的 DP 侧，本轮只登记不实现。

## 10. 需要 Lead 合并的片段（不在本线写作用域）

只有一件事需要改 `dts/`，而且**只有当**我们选择"DT 驱动"而不是"owner 注册"模型时才需要：

```diff
--- a/dts/mondrian.dts
+++ b/dts/mondrian.dts
@@ pmic_glink: pmic-glink {
     battery_charger: battery-charger {
         compatible = "qcom,battery-charger";
     };
+
+    ucsi: ucsi {
+        compatible = "qcom,ucsi-glink";
+    };
+
+    altmode: altmode {
+        compatible = "qcom,altmode-glink";
+        #altmode-cells = <1>;
+    };
 };
```

推荐**不合并**：本线实现走 owner 注册（§6），与主线 `pmic_glink.c` 同构，不需要 DT 参与。

## 11. 复现命令

```sh
# 自测
cc -std=c11 -Wall -Wextra -o /tmp/ucsi-host-selftest docs/research/usb/ucsi-host-selftest.c && /tmp/ucsi-host-selftest

# 随镜像 DT 有没有 ucsi 节点
dtc -I dtb -O dts /opt/k60/trees/lead-out/mondrian/ipados-16.6.1-20G81/mondrian/device-tree/hardware.dtb \
  | grep -nE 'ucsi|pmic-glink|battery'

# 固件 DT 的 UCSI 节点
grep -n 'qcom,ucsi\|qcom,altmode\|ucsi = ' /mnt/e/k60-work/scratch/usb/mondrian.dts

# K60 侧 owner 过滤点
grep -n 'K60_BATTMGR_OWNER\|qcom_glink_channel' drivers/PongPower/K60Battmgr.c drivers/PongPower/K60PmicGlink.cpp
```

## 12. 证据索引

| 文件 | 用途 |
| --- | --- |
| `docs/research/usb/ucsi-host-selftest.c` | 线格式与角色表的主机回归（287 行） |
| `docs/research/usb/UCSI-SELFTEST-OUTPUT.txt` | 最近一次输出，`RESULT: PASS (0 failures)` |
| `E:/k60-work/scratch/usb/linux/pmic_glink.h` | owner id / hdr / msg type（主线 v6.6） |
| `E:/k60-work/scratch/usb/linux/pmic_glink.c` | owner 多路复用模型（`:84`、`:90`、`:131`、`:272/277/282`） |
| `E:/k60-work/scratch/usb/linux/ucsi_glink.c` | 0x11/0x12/0x13 与 48 字节缓冲（`:14-22`、`:76-94`、`:209-232`） |
| `E:/k60-work/scratch/usb/linux/ucsi.h` | 偏移、CCI 位、命令、伙伴类型 |
| `E:/k60-work/references/UniXNU-upstream/docs/porting/usb.md` | 角色裁决官方表述（`:90-101`） |
| `E:/k60-work/references/UniXNU-sheng/package/ShengBattery.cpp` | 同 SoC 实机客户端（`:30-91`） |
| `E:/k60-work/references/UniXNU-sheng/package/BootLog.c` | `[usb ucsi] state/status/cci/changes` 遥测格式（`:304`、`:1944`） |
| `docs/research/battery/GLINK-HANDOFF.md` | lease 契约与"无生产者"事实 |
| `E:/k60-work/scratch/usb/mondrian.dts` | 固件侧 UCSI/altmode 节点（`:8555-8578`） |
