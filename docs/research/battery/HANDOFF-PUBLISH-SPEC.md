# 104 字节 `k60-adsp-glink-handoff` 发布规格

> 面向对象：写内核侧「发布者」的 Lead。
> 目标：把「谁在什么时刻、用什么参数、往 `/chosen` 的哪个属性、写哪 104 个字节」写成
> 可以逐字节照抄、可以逐条验收的规格。
> 本文只描述**生产者**。消费者的语义见 `GLINK-HANDOFF.md`，L1 服务层见 `PMIC-GLINK-SERVICE.md`。

---

## 0. 结论摘要

1. **属性名固定为 `k60-adsp-glink-handoff`**，写在 `/chosen`（IODTPlane）上，值是一个
   **恰好 104 字节**的 `OSData`。名字的唯一权威是
   `drivers/PongPower/K60BatteryConfig.h:17`；消费点是
   `drivers/PongPower/K60Battery.cpp:425-429`。
2. **字节内容不要手写**：调用 `drivers/PongPower/K60HandoffBuild.c:33` 的
   `k60_handoff_build()`，它会校验计划、在 SMEM 里分配四个条目、再按
   `K60HandoffBuild.c:67-91` 逐字段写出。手写字段表必然抓不住常量错（P-169 的教训，
   落地测试是 `scripts/tests/test-k60-handoff-build.c:52-76`）。
3. **`plan.required` 必须由调用者填 `K60AdspHandoffRequired`（=15）**。
   `plan_ok()`（`K60HandoffBuild.c:19-31`）只检查 `required != 0`，不检查等于 15；
   而消费者 `K60BatteryConfig.c:68` 要求 `h.flags != K60AdspHandoffRequired` 就返回
   `K60ConfigNoOwnership`。**这是本规格里最容易踩空的一格。**
4. **发布必须在 `k60_physical_battery_start()` 之前完成**。该函数被
   `patches/xnu/0602-k60-physical-battery.patch:23-35` 插在 `IOKitBSDInit()` 里；
   而 `IOKitBSDInit()` 由 `bsd_autoconf()`（`bsd_init.c:1099`）调用，**早于**
   `vfs_mountroot()`（`bsd_init.c:869-870`）。所以「Data mount 之后再发布」在本树行不通，
   必须选一个更早的钩子（见 §7）。
5. **发布成功 ≠ 通道可用**。消费者在 `K60PmicGlink.cpp:57-87` 的 `discover()` 里会拿
   SMEM 里的**真实条目**和 lease 逐项比对，并用 SMP2P 判定远端就绪；任何一项不符就
   `error=-21/-22/-23` 退出。也就是说：**ADSP 必须先跑起来、SMP2P 必须先就绪**，
   发布者不能只写 104 个字节就完事（见 §10）。
6. **`k60_handoff_build()` 自己不持有 TCSR 硬件互斥量**：`K60Smem.c` 里的
   `acquire()`/`release()`（`:17-22`、`:28-33`）只有 `dmb osh` 屏障，没有写
   `0x1f4100c`。调用者必须在调用前后自己持锁（照 `K60PmicGlink.cpp:38-56` 的
   `lockSmem()/unlockSmem()`），否则和 ADSP 侧并发改 SMEM 分配表（见 §9.2）。
7. **失败必须打印一条独立错误行**，不允许静默跳过：`K60Battery.cpp:432` 那条
   `blocked rc=%d` 是消费者侧的兜底，发布者侧必须自己说清是哪一级失败（见 §8）。

---

## 1. 适用范围

| 是 | 否 |
|---|---|
| 生成并发布 104 字节 `k60-adsp-glink-handoff` | pmic_glink 服务层（L1）的报文语义 |
| 在 SMEM 里切出 desc/tx/rx/smp2p 四个条目 | ADSP 固件怎么装进 carveout（那是 PAS1，见 §3 第 1 步） |
| 判定「什么时候可以发布」 | 电池驱动的属性发布逻辑 |
| 失败时的错误行要求 | 路线 A / 路线 B 的选择（那是 `02-GLINK-CONTRACT.md` §6.3） |

---

## 2. 输入：板级配置真值表

这六项必须来自板级配置（`K60BatteryConfig`），不能由发布者另填一套。权威生成器是
`scripts/build-k60-physical-battery.py:105-110` 的 `board_config()`，它从 ADT 读、
并且 `:103` 硬断言 `ipcc 大小 == 4096 && smem 大小 == 0x200000 && adsp 大小 == 0x3100000`。

| 字段 | 真值 | 证据 |
|---|---|---|
| `smem_base` | `0x80900000` | `dts/mondrian.dts:120-123` `smem_region@80900000` |
| `smem_bytes` | `0x200000`（2 MiB） | 同上；`build-k60-physical-battery.py:103` 断言 |
| `adsp_base` | `0x9fd00000` | `dts/mondrian.dts:152-155` `adsp_region@9fd00000` |
| `adsp_bytes` | `0x3100000`（49 MiB） | 同上 |
| `ipcc_base` | `0xed18000`（4096 B） | `dts/mondrian.dts:142-150` `mailbox@ed18000` |
| `mutex_base` | `0x1f4100c` | `dts/mondrian.dts:125-140`：`syscon@1f40000` + `0x1000` + hwlock `3`×4 |
| `remote_pid` | `2` | `dts/mondrian.dts:163-176` `qcom,remote-pid = <2>` |
| `ipcc_client` / `ipcc_signal` | `3` / `0` | `dts/mondrian.dts:165` `mboxes = <&ipcc 0x03 0x00>` |
| `desc_item` / `tx_item` / `rx_item` | `478` / `479` / `480` | `build-k60-physical-battery.py:109` |
| `smp2p_item` | `443`（= `0x1bb`） | `dts/mondrian.dts:179-187` `qcom,smem = <0x1bb 0x1ad>` |
| `protocol` | `1` | `K60BatteryConfig.h` `K60_BATTERY_PROTOCOL_XIAOMI_MONDRIAN` |
| `charging_current_sign` | `0/1/-1` | `K60BatteryConfig.c:48` 只接受这三个值 |

这些值同时被 `K60BatteryConfig.c:45-49` 的**硬编码门**再校验一遍
（`remote_pid==2 && ipcc_client==3 && ipcc_signal==0 && desc_item==478 && tx_item==479 && rx_item==480 && smp2p_item==443 && protocol==1`）。
发布者不要复制这些常量，直接复用解析好的 `K60BatteryConfig`。

---

## 3. 调用序列

发布者应当是一个**单一编排函数**（建议名 `k60_adsp_handoff_publish()`），
返回 `0` 或负错误码。六步，顺序不能换：

| # | 动作 | 现有实现 | 失败含义 |
|---|---|---|---|
| 1 | 装载并释放 ADSP 固件（PAS1 auth + reset + 逐段 INIT_IMAGE + MEM_SETUP） | `K60AdspBoot.c:178` `k60_adsp_probe_from_handoff()` → `k60_adsp_bring_up()` | ADSP 没起来，后面全废 |
| 2 | 等 SMP2P 条目 `"slave-kernel"` 的 `state & 2` 置位、`state & 1` 清零 | 判定逻辑现成在 `K60PmicGlink.cpp:88-109` `remoteReady()` | 远端未就绪 |
| 3 | 拿 TCSR 互斥量（`mutex_base`，写 `1` 表示 APSS owner） | 现成在 `K60PmicGlink.cpp:38-56` | 拿不到锁 = 不能改 SMEM |
| 4 | `k60_smem_partition(&smem, 0, 2, &part)` 定位分区 | `K60Smem.c:49-71` | `K60SmemNoTable`/`NoPartition` |
| 5 | `k60_handoff_build(&smem, &part, &plan, blob)` | `K60HandoffBuild.c:33` | `-8` 计划非法 / `-6` 已存在 / `-7` 无空间 |
| 6 | 把 `blob`（104 B）作为 `OSData` 挂到 `/chosen` 的 `k60-adsp-glink-handoff` | 本规格要新增 | 属性已存在则拒绝二次发布 |

第 3 步的锁必须覆盖第 4–5 步，第 5 步返回后再 `unlock`（照 `K60PmicGlink.cpp:59-65`
的 `lockSmem() … unlockSmem()` 包住 `k60_smem_partition` + `k60_smem_find` 的写法）。

### 3.1 `K60HandoffPlan` 的 13 个字段怎么填

`K60HandoffBuild.h:20-31`：

```c
typedef struct {
    uint32_t required;      /* 填 K60AdspHandoffRequired (=15) —— 见 §9.1 */
    uint32_t epoch;         /* 非 0，本次会话唯一 —— 见 §9.4 */
    uint64_t smem_base;     /* 板级配置 smem_base */
    uint32_t smem_bytes;    /* 板级配置 smem_bytes */
    uint64_t adsp_base;     /* 板级配置 adsp_base */
    uint32_t adsp_bytes;    /* 板级配置 adsp_bytes */
    uint16_t desc_item, tx_item, rx_item, smp2p_item;  /* 478/479/480/443 */
    uint16_t remote_pid;    /* 2 */
    uint32_t desc_bytes, tx_bytes, rx_bytes, smp2p_bytes;
    uint32_t host_tx_head, host_rx_tail, remote_restart_flag;
} K60HandoffPlan;
```

| 字段 | 取值 | 约束来源 |
|---|---|---|
| `required` | `15` | `K60HandoffBuild.c:29` 只查 `!=0`；`K60BatteryConfig.c:68` 要求 `==15` |
| `epoch` | 本次启动的唯一非 0 值，**不得跨启动复用** | `K60HandoffBuild.c:22`；`K60BatteryConfig.c:68` |
| `smem_base` / `smem_bytes` | `0x80900000` / `0x200000` | `K60HandoffBuild.c:22`（≥8192）；`K60BatteryConfig.c:69`（必须等于板级配置） |
| `adsp_base` / `adsp_bytes` | `0x9fd00000` / `0x3100000` | `K60HandoffBuild.c:23`；`K60BatteryConfig.c:69` |
| 四个 `*_item` | `478/479/480/443`，两两不同且非 0 | `K60HandoffBuild.c:50-55` |
| `desc_bytes` | **必须 32** | `K60HandoffBuild.c:24`；`K60BatteryConfig.c:77` |
| `tx_bytes` / `rx_bytes` | 建议 `4096`；合法域 256–65536 且 8 对齐 | `K60HandoffBuild.c:15` `ring_ok()`；`K60BatteryConfig.c:78-79` |
| `smp2p_bytes` | 20–340；建议直接取 SMEM 里 443 条目的实际大小 | `K60HandoffBuild.c:26`；`K60PmicGlink.cpp:70` |
| `host_tx_head` / `host_rx_tail` | **必须 0** | `K60HandoffBuild.c:28`；`K60BatteryConfig.c:75` |
| `remote_restart_flag` | `≤1`，且必须等于 SMP2P 里的重启位 | `K60HandoffBuild.c:29`；`K60PmicGlink.cpp:95` |

`tx_bytes=rx_bytes=4096` 的理由：`.ko` 单帧最大 220 B（`wls_debug_store`），
0x41 分片帧 144 B，0x30 收 144 B；4096 有 18 倍余量，且和
`scripts/tests/test-k60-handoff-build.c:37` 的已验证取值一致。
注意 AP 侧 GLINK intent 是 `256 B × 4`（`K60PmicGlink.cpp:84`），环大小与 intent 大小无关。

---

## 4. 104 字节真值表

逐字节来源是 `K60HandoffBuild.c:67-91`，**这张表就是代码，不是推导**：

| offset | 宽度 | 值 | 写入行 |
|---|---|---|---|
| `+0` | u32 | `0x4842364b`（`K60_HANDOFF_MAGIC`，ASCII "K6BH"） | `K60HandoffBuild.c:67` |
| `+4` | u32 | `1`（`K60_HANDOFF_VERSION`） | `:68` |
| `+8` | u32 | `104`（`K60_HANDOFF_BYTES`，必须等于实际长度） | `:69` |
| `+12` | u32 | `plan->required` = **15** | `:70` |
| `+16` | u32 | `plan->epoch` 低 32 位 | `:71` |
| `+20` | u32 | `0`（epoch 高半） | `:72` |
| `+24` | u64 | `plan->smem_base` | `:73` |
| `+32` | u32 | `plan->smem_bytes` | `:74` |
| `+36` | u32 | `0` | `:75` |
| `+40` | u64 | `plan->adsp_base` | `:76` |
| `+48` | u32 | `plan->adsp_bytes` | `:77` |
| `+52` | u32 | `0` | `:78` |
| `+56` | u32 | `offsets[0]`（desc 条目在 SMEM 内的偏移） | `:79` |
| `+60` | u32 | `plan->desc_bytes` = 32 | `:80` |
| `+64` | u32 | `offsets[1]`（tx 环偏移） | `:81` |
| `+68` | u32 | `plan->tx_bytes` | `:82` |
| `+72` | u32 | `offsets[2]`（rx 环偏移） | `:83` |
| `+76` | u32 | `plan->rx_bytes` | `:84` |
| `+80` | u32 | `plan->host_tx_head` = 0 | `:85` |
| `+84` | u32 | `plan->host_rx_tail` = 0 | `:86` |
| `+88` | u32 | `plan->remote_pid` = 2 | `:87` |
| `+92` | u32 | `plan->smp2p_item` = 443 | `:88` |
| `+96` | u32 | `plan->remote_restart_flag` | `:89` |
| `+100` | u32 | `0`（保留，消费者要求必须为 0） | `:90` |

关于 `offsets[0..2]`：`k60_smem_alloc()` 返回的是**已经加过分区偏移和条目头**的绝对偏移
（`K60Smem.c:148` `*offset = p->offset + at + ENTRY;`），所以直接写进 `+56/+64/+72`
就是消费者要的值，**不要再加 `smem_base`，也不要再减 `PART_HEADER`**。

---

## 5. 逐字段对上消费者的读取顺序

消费者是 `drivers/PongPower/K60BatteryConfig.c:54-87` 的 `k60_adsp_handoff_parse()`。
下表左边是它实际读的位置，右边是 §4 的写入位置——**必须一一对上**（P-169 就是因为
自造字段表和这里错位才出的问题）。

| 消费者读取（行号） | 字段 | 对应 §4 偏移 | 门禁 |
|---|---|---|---|
| `K60BatteryConfig.c:56` `le32(p)` | magic | `+0` | `!= 0x4842364b` → `BadEncoding` |
| `:56` `le32(p+4)` | version | `+4` | `!= 1` → `BadEncoding` |
| `:56` `le32(p+8)` | bytes | `+8` | `!= 实际长度` → `BadEncoding` |
| `:57` `le32(p+100)` | reserved | `+100` | 非 0 → `BadEncoding` |
| `:60` `le32(p+12)` | flags | `+12` | `:68` `!= 15` → `NoOwnership` |
| `:60` `le64(p+16)` | epoch | `+16..+23` | `:68` `== 0` → `NoOwnership` |
| `:61` `le64(p+24)` | smem_base | `+24` | `:69` 必须 == 板级配置 |
| `:61` `le64(p+32)` | smem_bytes | `+32` | 同上 |
| `:62` `le64(p+40)` | adsp_base | `+40` | 同上 |
| `:62` `le64(p+48)` | adsp_bytes | `+48` | 同上 |
| `:63` `le32(p+56)` | desc_offset | `+56` | `:77` 8 对齐 + `fits` |
| `:63` `le32(p+60)` | desc_bytes | `+60` | `:77` 必须 == 32 |
| `:64` `le32(p+64)` | tx_offset | `+64` | `:78` 8 对齐 + `fits` |
| `:64` `le32(p+68)` | tx_bytes | `+68` | `:78` 256–65536 且 8 对齐 |
| `:65` `le32(p+72)` | rx_offset | `+72` | `:79` 8 对齐 + `fits` |
| `:65` `le32(p+76)` | rx_bytes | `+76` | `:79` 256–65536 且 8 对齐 |
| `:66` `le32(p+80)` | host_tx_head | `+80` | `:75` 必须 0 |
| `:66` `le32(p+84)` | host_rx_tail | `+84` | `:75` 必须 0 |
| `:67` `le32(p+96)` | remote_restart_flag | `+96` | `:75` `>1` → `WrongEpoch` |
| **`:71` `le32(p+88)`** | remote_pid | `+88` | 必须 == `c->remote_pid`（2） |
| **`:71` `le32(p+92)`** | smp2p_item | `+92` | 必须 == `c->smp2p_item`（443） |

注意最后两行：`remote_pid` 和 `smp2p_item` **不在** `K60AdspGlinkHandoff` 结构体里
（`K60BatteryConfig.h:48-54` 没有这两个字段），消费者是在 `:71` 直接读原始字节做比对的。
所以「结构体里没有」不等于「不用写」——它们是必填项。

---

## 6. 发布动作

| 项 | 值 |
|---|---|
| 节点 | `/chosen`，`gIODTPlane` |
| 属性名 | `k60-adsp-glink-handoff`（`K60BatteryConfig.h:17` `K60_ADSP_HANDOFF_PROPERTY`） |
| 值类型 | `OSData`，长度 **恰好 104** |
| 读取方 | `K60Battery.cpp:425-426` `IORegistryEntry::fromPath("/chosen", gIODTPlane)` + `getProperty(...)` |
| 二次发布 | **拒绝**。已有同名属性时打印错误并返回非 0，不覆盖 |

现有可抄的先例：`patches/wifi/0001-drivers-PongWifi-vendor-zizhan-087416a.patch:1907`
`auto chosen=IORegistryEntry::fromPath("/chosen",gIODTPlane); if(chosen){chosen->setProperty("mac-address-wifi0",st.mac,6); chosen->release();}`。

验收断言（发布后立刻自检，不要等消费者报错）：

```
length == 104
le32(blob+0)  == 0x4842364b
le32(blob+4)  == 1
le32(blob+8)  == 104
le32(blob+12) == 15
le32(blob+100)== 0
```

这五条正好是 `K60BatteryConfig.c:56-58` 的第一道门。最省事的做法是发布前直接调一次
`k60_adsp_handoff_parse(blob, 104, &config, &handoff)`，要求返回 `K60ConfigOk`——
自产自检，和 `scripts/tests/test-k60-handoff-build.c:118-134` 的做法一致。

---

## 7. 时机：必须早于 `IOKitBSDInit()` 里的电池启动

### 7.1 现有插入点

| 钩子 | 位置 | 调什么 |
|---|---|---|
| `bsd_autoconf()` | `bsd_init.c:1082-1100`：`kminit()` → pseudo_inits → `return IOKitBSDInit();`（`:1099`） | — |
| `IOKitBSDInit()` | `patches/xnu/0602-k60-physical-battery.patch:23-35`，紧跟 `IOService::publishResource("IOBSD")` | `k60_physical_battery_start()`（消费者） |
| `bsd_init()` | `bsd_init.c:869-870` `vfs_mountroot()`，`:1028-1033` `mountroot_post_hook()` | — |
| `kern_exec.c` | `patches/xnu/0614-k60-adsp-call-site.patch:6-13`，`k60_data_mounted = 1` 之后 | `k60_adsp_probe_from_handoff()`（ADSP 装载） |

调用顺序是 `bsd_autoconf()` → `IOKitBSDInit()` → … → `vfs_mountroot()` → … → Data mount → `kern_exec`。
所以：

- **消费者（`k60_physical_battery_start`）比 `kern_exec` 里的 ADSP 装载早得多**；
- 也就是说，现在的 0614 插入点对电池线来说**太晚**，它只服务音频线；
- 若照现状开机，电池会在 ADSP 还没装载时就跑，即使 `/chosen` 里有 blob，
  `discover()` 的 `remoteReady()` 也必然失败（`K60PmicGlink.cpp:73` `error=-22`）。

### 7.2 要求的顺序

```
bsd_autoconf()
  └─ kminit()
  └─ pseudo_inits
  └─ k60_adsp_handoff_publish()          ← 新增：装载 ADSP + 等 SMP2P + 分配 + 发布
  └─ IOKitBSDInit()
        └─ publishResource("IOBSD")
        └─ k60_physical_battery_start()  ← 现有消费者，此时 blob 已就位、ADSP 已就绪
```

即：**新增一个补丁（建议编号 0617），把 `k60_adsp_handoff_publish()` 插在
`bsd_autoconf()` 的 `return IOKitBSDInit();` 之前**（`bsd_init.c:1099` 上面一行）。
不要插在 `kern_exec`，那里的时机对电池线无效。

### 7.3 为什么不能只「提前发布、稍后装载」

`k60_adsp_handoff_parse()` 只做字节校验，不看 SMP2P，所以「早发布」本身能通过解析。
但紧接着 `k60_physical_battery_start()` 就会 `new K60Battery` → `begin()` →
`transport.open()` → `discover()`，那里要求 `remoteReady()`。
所以发布和 ADSP 就绪**必须在同一个函数里按顺序完成**，不能拆成两个时间点。

---

## 8. 失败处理：每一级一条独立错误行

不允许静默返回。消费者侧的 `K60Battery.cpp:432` 只会在「blob 缺失/非法」时说一句
`blocked rc=%d`，它无法区分是 PAS1 没起、还是 SMEM 没表、还是分配没空间。

| 失败级 | 返回 | 必须打印（建议措辞） |
|---|---|---|
| 第 1 步 PAS1 装载 | `-1` | `K60Handoff: PAS1 bring-up failed; no lease published` |
| 第 2 步 SMP2P 未就绪（超时） | `-2` | `K60Handoff: SMP2P slave-kernel not ready after %u ms; no lease published` |
| 第 3 步 拿不到 TCSR 互斥量 | `-3` | `K60Handoff: TCSR mutex timeout; refusing to touch the SMEM allocator` |
| 第 4 步 无 SMEM 表/无分区 | `K60SmemNoTable`/`NoPartition` | `K60Handoff: SMEM table/partition unavailable rc=%d` |
| 第 5 步 `k60_handoff_build` 失败 | 其返回值 | `K60Handoff: build failed rc=%d (plan rejected / no space / duplicate item)` |
| 第 6 步 属性已存在 | `-4` | `K60Handoff: /chosen already carries k60-adsp-glink-handoff; refusing to overwrite` |
| 第 6 步 自检失败 | `-5` | `K60Handoff: self-check rejected the blob rc=%d; not published` |

这七条是**可 grep 的验收点**：开机日志里出现哪一条，就直接指向哪一级。

---

## 9. 六个必须避开的坑

### 9.1 `required` 填 15，不是「非 0 就行」

`K60HandoffBuild.c:29` 的条件是 `p->required == 0u` 才拒绝。填 `1`、`3`、`7` 都能过
`plan_ok()`，但消费者 `K60BatteryConfig.c:68` 要求 `h.flags != K60AdspHandoffRequired`，
而 `K60AdspHandoffRequired` 是 `15u`（`K60BatteryConfig.h:31-37` 四个位全置）。
表现是：发布成功、开机日志无异常、电池永远 `blocked rc=-4`。
**落地测试**：`scripts/tests/test-k60-handoff-build.c:56` 已经断言 `{12, 0xfu, ...}`。

### 9.2 `k60_handoff_build()` 不持锁

`K60Smem.c:17-22` 的 `acquire()` 和 `:28-33` 的 `release()` 只有 `dmb osh`，**没有**写
`0x1f4100c`。而 `K60PmicGlink.cpp:38-49` 的 `lockSmem()` 才是真正的 TCSR 互斥量
（`*mutex = 1` + `dsb sy` + `dmb osh`，1000 µs 超时）。
SMEM 分配表是 APSS 与 ADSP 共享的，发布者必须自己持锁包住整个 `k60_handoff_build()`。

### 9.3 `K60SmemExists` 回落要检查内容，不能默认「已就绪」

`K60HandoffBuild.c:59-63`：`k60_smem_alloc` 返回 `K60SmemExists` 时会回落到
`k60_smem_find` 直接复用已有条目。这对 `smp2p_item=443` 是**正确**的（443 是 Android/ADSP
本来就建的条目），但对 `desc/tx/rx = 478/479/480` 有风险：如果上一次 Android 启动留下的
环还在，就会复用旧环，而 `host_tx_head`/`host_rx_tail` 已经被写成 0 了。
消费者随后在 `K60PmicGlink.cpp:78` 检查 `desc[1] != lease.host_tx_head`（即 `desc[1] != 0`），
不符就 `error=-23`。

**要求**：发布者在 `k60_handoff_build()` 返回后，对 `desc_offset` 处的 32 字节做一次
全零检查；非零则打印 §8 第 5 级的错误并**不发布**（宁可这一轮没有电池，也不要假装接管）。

### 9.4 `epoch` 必须每次启动都不同

`K60HandoffBuild.c:22` 只要非 0；消费者 `K60BatteryConfig.c:68` 只要非 0。
但语义上它是「本次会话」的标识：`K60PmicGlink.cpp:128` 会把它打进日志，
`K60BatterySmoke.c:94` 要求 `epoch > 0`，`K60Battery.cpp:318` 在通道超时时提示
「platform owner must supply a new authenticated session」。
建议取值：`(uint32_t)clock_get_system_microtime()` 之类的启动时刻秒数，
或 UEFI 传进来的 boot counter。**不要用常量**，否则跨启动无法区分新旧会话。

### 9.5 `remote_restart_flag` 必须和 SMP2P 里的位一致

消费者 `K60PmicGlink.cpp:95`：`(remoteState[4] & 1) != lease.remote_restart_flag` 就
`error=-22`。所以发布者**必须**在发布前读一次 SMP2P 条目（`smem + smp2p_offset` 处的
`remoteState[4] & 1`），把同一个值填进 `plan.remote_restart_flag`。
随便填 0 或 1 会有一半概率开机失败——这是最隐蔽的一格。

### 9.6 `+88/+92` 不是「结构体字段」，但必须写对

见 §5 最后两行。`K60AdspGlinkHandoff`（`K60BatteryConfig.h:48-54`）里没有
`remote_pid`/`smp2p_item`，容易误以为不用写。实际是 `K60BatteryConfig.c:71` 直接读原始字节
和板级配置比对。好消息是 `k60_handoff_build()` 已经替你写了（`:87-88`），
只要 `plan.remote_pid` 和 `plan.smp2p_item` 填的是板级真值就不会错。

---

## 10. 发布成功 ≠ 通道可用：`discover()` 的第二次校验

`K60PmicGlink.cpp:57-87` 在 `open()` 里做的是「拿 SMEM 真实条目去验 lease」，逐条：

| 行 | 检查 | 失败码 |
|---|---|---|
| `:59` | `lockSmem()` 拿到 TCSR 互斥量 | `-20` |
| `:60` | `k60_smem_partition(&smem, 0, remote_pid, &part)` | SMEM 错误码 |
| `:61-64` | 四个 item 逐个 `k60_smem_find` | SMEM 错误码 |
| `:67-70` | `offsets[0..2]/sizes[0..2]` 必须**逐项等于** lease 的 `desc/tx/rx`；smp2p 偏移 4 对齐、大小 20–340 | `-21` |
| `:71-73` | `remoteReady()`：magic `0x504d5324`、`(state[1]&255)==1`、`state[2]==remote_pid`、条目名 `"slave-kernel"`、`state&2 && !(state&1)` | `-22` |
| `:78` | `desc[1] == lease.host_tx_head` 且 `desc[2] == lease.host_rx_tail`（都应为 0） | `-23` |
| `:84` | `qcom_glink_channel(&native, "PMIC_RTR_ADSP_APPS", 256, 4, …)` 建通道 | `-24` |

`:67-70` 的逐项相等是关键：**lease 里的三个偏移必须是 SMEM 里真实条目的偏移**，
不能是「自己算出来的地址」。`k60_smem_alloc` 返回的偏移天然满足这一点，
手写偏移必然对不上。

---

## 11. 未决问题

1. **SMEM 分区表本身从哪来。** `k60_smem_partition()`（`K60Smem.c:49-71`）要求
   `smem_base + smem_bytes - 4096` 处有 `TOC_MAGIC 0x434f5424`、版本 1、条目数组。
   这张表由 bootloader（或 Android 内核首次启动）写入；本仓库没有任何代码创建它。
   若 K60 冷启动时 SMEM 是空的，第 4 步会直接 `K60SmemNoTable`。
   **需要真机取证**：从 UEFI 或内核早期 dump `0x80900000 + 0x1ff000` 的 32 字节。
2. **ADSP 固件载体。** `k60_adsp_probe_from_handoff()` 需要 FAT ramdisk 里的
   `adsp.b00..b25 + adsp.mdt`（`K60AdspBoot.c:213` `k60_fat_open`），而
   `docs/engineering/BOOT-ARGS.md:278-280` 记录 `memdev` 的 `vmd0` 是固件虚拟地址、
   XNU 读不到。这条不解决，§3 第 1 步就过不去。
3. **SMP2P 就绪要等多久。** `K60AdspBoot.c:228` 返回时只表示固件已装、PAS 已释放，
   不表示 ADSP 已初始化完 pmic_glink。需要真机测一个上界（建议先按 2 s 轮询、20 ms 间隔）。
4. **`remote_restart_flag` 的来源语义。** 现在只知道它必须等于 `remoteState[4] & 1`，
   不知道 ADSP 什么时候会翻这一位（重启后由谁清）。建议第一次实现就按「发布前现读」处理。
5. **`tx_bytes`/`rx_bytes` 的真实值。** 4096 是能满足约束的最小合理值，但没有和
   Android 原厂的环大小对齐过；若真机出现 GLINK 环满/背压，优先怀疑这里偏小。

---

## 12. 复现命令

```bash
cd /mnt/e/hackios/k60-charger

# 1) 104 字节写入顺序（真值表来源）
sed -n '67,91p' drivers/PongPower/K60HandoffBuild.c

# 2) 计划校验（注意 required 只查非 0）
sed -n '19,31p' drivers/PongPower/K60HandoffBuild.c

# 3) 消费者读取顺序
sed -n '54,87p' drivers/PongPower/K60BatteryConfig.c

# 4) 发布时机：bsd_autoconf → IOKitBSDInit → vfs_mountroot
grep -n "bsd_autoconf\|IOKitBSDInit\|vfs_mountroot" bsd_init.c

# 5) 现有两个插入点
sed -n '20,40p' patches/xnu/0602-k60-physical-battery.patch
sed -n '1,20p' patches/xnu/0614-k60-adsp-call-site.patch

# 6) 全仓仍无生产者（应为空，除测试与 patch）
grep -rn "k60_handoff_build(" --include=*.c --include=*.cpp drivers/ bsd/ iokit/

# 7) 第二次校验（发布成功后仍可能失败的地方）
sed -n '57,87p' drivers/PongPower/K60PmicGlink.cpp

# 8) 主机侧落地测试（逐字段断言 + 喂给真实 parse），期望输出 "TESTS OK 10"
cc -I drivers/PongPower -DK60_HOST_TEST -o /tmp/t scripts/tests/test-k60-handoff-build.c \
   drivers/PongPower/K60BatteryConfig.c && /tmp/t
```

---

## 13. 与其他文档的关系

| 文档 | 关系 |
|---|---|
| `GLINK-HANDOFF.md` | 104 字节**消费者**契约（逐字段校验）。本文是它的**生产者**对偶。注意它 §80-101 说的「没有 SMEM 分配器 / 没有 PAS1 装载器」已过时：`K60Smem.c:113`、`K60AdspPas.c`、`K60AdspBoot.c` 都在树里。 |
| `PMIC-GLINK-SERVICE.md` | L1 服务层契约（pmic_glink 报文语义）。本文只到 L0。 |
| `docs/research/charger/02-GLINK-CONTRACT.md` | `.ko` 期望的通道名/opcode/prop map；它的 §6.2 已把「104 B 覆盖什么、不覆盖什么」列成表。 |
| `docs/engineering/BATTERY-INTEGRATION.md` | 构建与宏链路的接入步骤（`-DXNU_K60_PHYSICAL_BATTERY`、`-force_load libK60PhysicalBattery.a`）。 |
| `docs/engineering/BOOT-ARGS.md` | `k60_battery`（默认 1）与 `pong_adsp`（默认 0）两个开关的语义。 |
