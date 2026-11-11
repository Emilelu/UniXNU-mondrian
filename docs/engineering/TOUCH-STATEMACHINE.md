# Goodix GT9916R (Berlin-D) 上电→出报告 状态机提取

依据：官方 vendor Linux 驱动 `<workspace>\impl\touch-protocol\refs\`（下称 `brl_hw.c` / `core.c` /`fwupdate.c`），
主线内核 `refs\linux-master\goodix_berlin_core.c`（下称 `mainline`），
以及我们自己的补丁 `<repo>\patches\xnu\zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-touch-console.patch`（下称 `patch`）。
所有行号均为实测。

---

## 0. 一句话答案（先给结论）

**官方在 `brl_send_config()` 之后什么也不做——只有一句 `msleep(100)`（`brl_hw.c:555`）就返回，
调用者随即去注册 IRQ（`core.c:2153→2156→2026`）。没有 reset、没有模式命令、没有 COORD-MODE。**

反过来，官方 Berlin-D **连 config 都不需要下发**：主线驱动 `mainline:728-805` 的整个 probe 只有
上电 + 读版本 + 读 IC_INFO + 注册 IRQ，**零条命令、零字节 config**，注释写明
"只处理已经烧好固件的 multitouch"（`mainline:14-24`）。

所以「能出报告」所需的状态，在 **`brl_power_on()` 结束那一刻就已经达成**（`brl_hw.c:206-258`，
Berlin-D 实际只有 4 步：上电轨 → 释放 reset → `brl_dev_confirm` → 100 ms）。

### ⚠ 但先纠正任务书里的一个前提

任务书假设「`k60_touch_minimal=1` 跳过全部命令」。**实测它没有。** 三个 minimal 运行
（`usblog-20261111-101548 / 115745 / 181651`）的日志逐行相同：

```
goodix: CMD-FIX frame 00 00 05 90 81 16 01 00      ← 发了，进 rawdata
goodix: CMD-FIX ack=80 OK
goodix: CFG-START frame 00 00 04 04 08 00 00 00    ← 发了，进"等 config 数据"
goodix: CFG-START ack=80 OK-config-ready
goodix: CFG download SKIP (minimal path)           ← 只跳了数据
```

对应代码：`patch:4100-4152`（`0x90/0x81`）与 `patch:4164-4195`（`CFG-START`）
**都在 `k60_touch_minimal` 守卫之外**，守卫只包住 4 处（`patch:2866 / 2888 / 4345 / 4487`）。

⇒ **两种路径都从未进入过"官方定义的正常扫描状态"。**
minimal 停在「rawdata 模式 + 等 config 数据」，完整流程停在「config 已写→被硬复位作废」。

而 `reports=` 在**每一次**运行里都是 0（含 minimal），`0x10308` 首字节恒为 `0x00`。
所谓「minimal 时 INT 变低」在约 24 次心跳里只有 0–2 次，且与 `reports` 无关——
**INT 变低不等于出了报告**（见 §4）。

所以真正要解释的不是"完整流程破坏了 minimal 的好状态"，而是：
**两条路径各自缺哪一步，让芯片始终不进扫描。** 答案是 §5 的三条根因。

**最关键的一步（任务书点名要查的那一步）**：`brl_send_config()` 之后官方**没有任何动作**，
既没有 reset 也没有 work-mode 命令（`brl_hw.c:553-559`）。
我们在这之后加了 `CFG-RESET` 硬复位（`patch:4438-4442`）——这一步官方**不存在**，
它把刚写进 `fw_buffer_addr`（RAM，`brl_hw.c:520`）的 config 全部作废。
**这是完整流程特有的、且方向性错误的一步。**

---

## 1. 官方完整启动序列（按时间，逐字）

### 步骤 1 — 上电与复位：`brl_power_on()`

```
函数: goodix_brl_hw.c:206 brl_power_on(cd, on=true)
操作: iovdd(iovdd_gpio 或 regulator) on      :214-222
延时: usleep_range(3000, 3100)               :223
操作: avdd(avdd_gpio 或 regulator) on        :224-232
延时: usleep_range(15000, 15100)             :233
操作: gpio_direction_output(reset_gpio, 1)   ← 释放复位
延时: usleep_range(4000, 4100)               :235
目的: 让芯片 ROM 起来，总线可用
证据: brl_hw.c:213-235
```

### 步骤 2 — 设备握手：`brl_dev_confirm()`

```
函数: goodix_brl_hw.c:75 brl_dev_confirm()
操作: write(0x10000, 8×0xAA); read(0x10000, 8) 比对
重试: 3 次，每次失败 usleep_range(5000,5100)
目的: 确认"总线通了且 ROM 在跑"，不是测试装饰
证据: brl_hw.c:83-96
      memset(tx_buf, DEV_CONFIRM_VAL, sizeof(tx_buf));      :83
      ret = hw_ops->write(cd, BOOTOPTION_ADDR, tx_buf, 8);  :85
      ret = hw_ops->read (cd, BOOTOPTION_ADDR, rx_buf, 8);  :89
```

> ⚠ **这是 Berlin-D 唯一被官方执行的"初始化写"。**

### 步骤 3 — `brl_reset_after()`：**Berlin-D 直接返回**

```
函数: goodix_brl_hw.c:107 brl_reset_after()
证据: brl_hw.c:114-115
      if (cd->bus->ic_type != IC_TYPE_BERLIN_A)
              return 0;
```

⇒ Berlin-D 上，hold-cpu(0x0002)、clk_sta0(0xD807=0xFF)、clk_sta1(0xD806=0x77)、
trim_D12(0xD006=0x3C)、软复位(0xD808=0xFA) **一条都不执行**（那些在 `:124-199`，属 Berlin-A 专属）。

### 步骤 4 — 100 ms 静置

```
函数: goodix_brl_hw.c:243
操作: msleep(GOODIX_NORMAL_RESET_DELAY_MS)   // = 100，goodix_ts_core.h:56
目的: 等固件完全启动
```

**上电序列到此结束。芯片已经进入"能产生报告"的状态。**
主线驱动同构：`mainline:249-291` 上电 → `:276 dev_confirm` → `:281 msleep(100)` → 直接读版本、
读 IC_INFO、注册中断（`mainline:774-797`）。

### 步骤 5 — 读版本、读 IC_INFO（只读，不改状态）

```
函数: goodix_brl_hw.c:643 brl_read_version()   → 读 0x10014，28 字节 + 校验
函数: goodix_brl_hw.c:892 brl_get_ic_info()     → 读 0x10070，先读 2 字节长度
证据: brl_hw.c:652-658, 901-938
调用顺序: core.c:2106 → 2144
```

### 步骤 6 — 发 config（**条件性**，官方可能整段跳过）

```
函数: core.c:2065 goodix_send_ic_config(cd, CONFIG_TYPE_NORMAL)
关键守卫: core.c:2081-2085
      config_id = goodix_get_file_config_id(cfg->data);
      if (cd->ic_info.version.config_id == config_id) {
              ts_info("config id is equal 0x%x, skiped", config_id);
              return 0;                      ← 相等就一件不发
      }
```

若需要发，走 `brl_send_config()`（`brl_hw.c:493`）：

| 序 | 操作 | 行号 | 等待条件 |
|---|---|---|---|
| 6.1 | `send_cfg_cmd(START=0x04, len=4)` | :511-513 | `ack==0x80` **且** `state==0x80` |
| 6.2 | `write(fw_buffer_addr, cfg, len)`（=0x1205c, 1488B） | :520 | 见 6.1 |
| 6.3 | `read(fw_buffer_addr, tmp, len)` + `memcmp` | :525-535 | 回读必须逐字节相同 |
| 6.4 | `send_cfg_cmd(WRITE=0x05, len=4)` | :537-540 | `ack==0x80` **且** `state==0x80` |
| 6.5 | `send_cfg_cmd(EXIT=0x06, len=4)`（在 `exit:` 标签，**无论成败都发**） | :545-551 | `ack==0x80` **且** `state==0x80` |

### 步骤 7 — `brl_send_config()` 之后：**只有 100 ms**

```
证据: brl_hw.c:553-556
      if (!ret) {
              ts_info("success send config");
              msleep(100);
      }
      kfree(tmp_buf);
      return ret;
```

**没有 `brl_reset()`。没有 `brl_dev_confirm()`。没有 `0x90/0x00`。没有任何模式命令。**

调用链随后是 `core.c:2153 goodix_send_ic_config(...)` → `core.c:2156 goodix_ts_stage2_init(cd)`
→ `core.c:2026 goodix_ts_irq_setup(cd)` → 注册中断，开始收报告。

### 步骤 8 — 中断注册与报告读取（运行态）

```
函数: core.c:1291 goodix_ts_irq_setup()
操作: gpio_to_irq(irq_gpio) → devm_request_threaded_irq(..., ts_bdata->irq_flags | IRQF_ONESHOT, ...)
证据: core.c:1297-1309
读法: brl_hw.c:1169 brl_event_handler()
      pre_read_len = IRQ_EVENT_HEAD_LEN(8) + BYTES_PER_POINT(8)*2 + 2 = 26   :1179-1180
      read(touch_data_addr, pre_buf, 26)                                     :1181
      if (pre_buf[0] == 0x00) return -EINVAL;   ← 只在有报告时才继续          :1188
      checksum_cmp(pre_buf, 8, U8_LE)                                        :1193
      if (event_status & GOODIX_TOUCH_EVENT /*0x80*/) → touch_handler         :1199-1202
清标志: brl_hw.c:1226 brl_after_event_handler()
      write(touch_data_addr, &0, 1)                                          :1234
```

---

## 2. 与我们的实现逐项对照

| # | 步骤 | 官方 | 我们（patch 行号） | 差异 |
|---|---|---|---|---|
| 1 | 上电轨 | iovdd 3ms → avdd 15ms（`brl_hw.c:213-233`） | 同序（`patch:2440` 附近已按此实现） | 一致 |
| 2 | 释放 reset + 4ms | `brl_hw.c:234-235` | 一致 | 一致 |
| 3 | `dev_confirm` 写 8×0xAA @0x10000 | **必做**（`brl_hw.c:236`） | minimal 跳过（`patch:2866-2870`），完整流程做（`:2869`） | minimal 少做（实测仍能读回，非根因） |
| 4 | `brl_reset_after` | **Berlin-D 直接 return**（`brl_hw.c:114-115`） | 未实现 | 一致（本来就不该做） |
| 5 | 100 ms 静置 | `brl_hw.c:243` | `sleep_ms(100)`（`patch:2871`） | 一致 |
| 6 | `0xC900 = 0x01` + 回读校验 | **Berlin-A 专属**，D 上被 `ic_type != IC_TYPE_BERLIN_A` 拦掉（`brl_hw.c:59-61`） | **每次启动都写**，minimal 才跳过（`patch:2888-2911`，实测 `rb=01` 通过） | ★ 我们在 D 上写了一个官方明令 D 不用的寄存器 |
| 7 | `0x90/0x81`（进 rawdata） | **只在容值测试路径**（`brl_hw.c:1313`，由 inspect 触发），**且必定配 `0x90/0x00` 退出**（`:1348-1351`） | **每次启动无条件发**（`patch:4100-4152`，**在 minimal 守卫之外**；三个 minimal 日志均有 `CMD-FIX ack=80`） | ★★ **两条路径都发了**，把测试模式入口当成启动步骤 |
| 8 | `CFG-START(0x04)` | 条件性（`core.c:2082` config_id 相等就跳过） | **无条件发**（`patch:4164-4195`，**minimal 也发**，日志 `CFG-START ack=80 OK-config-ready`） | ★★ 两条路径都发了；且少了 config_id 相等跳过 |
| 9 | 等 config 命令完成 | `ack==0x80` **且** `state==0x80`（`brl_hw.c:461` `cmd_ack.state == target_status`） | **只查 `ack[1]`**（`patch:4144 / 4189 / 4397 / 4410 / 4500`） | ★★ **从不检查 state 字段** |
| 10 | config 数据写 `fw_buffer_addr` | `:520` | `k60_fw_buffer_addr`（`patch:4363`），已实测 `bad=0` | 一致（地址已修正） |
| 11 | 回读 memcmp | `:525-535` | 每 64B 回读比对（`patch:4367-4375`） | 一致 |
| 12 | `CFG-WRITE(0x05)` | `:539`，等 `ack+state` | `patch:4383-4398`，只等 ack | 差 state |
| 13 | `CFG-EXIT(0x06)` | `:547`，等 `ack+state`，之后 `msleep(100)` | `patch:4400-4412`，等 ack 后 `sleep_ms(100)` | 差 state |
| 14 | **config 之后复位** | **官方不复位** | **我们硬复位 gpio20 低 2ms→高→100ms**（`patch:4438-4442`） | ★★ **凭空多出的一步** |
| 15 | 复位后重新握手 | 上电路径上 reset 释放后紧接 `dev_confirm`（`brl_hw.c:234-241`）；但 `brl_reset()` 本身不跑它（`:310-323`） | **复位后只重写 0xC900，不跑 dev_confirm**（`patch:4444-4456`） | 次要风险，见 §3.2 标注 |
| 16 | `0x90/0x00`（回坐标模式） | 只在容值测试退出时发（`brl_hw.c:1348`） | 完整流程发（`patch:4492-4501`），minimal 跳过（`:4487`） | 我们"补发"的这一步本身是对的，但它救不回第 14/15 步 |
| 17 | 注册 IRQ | `core.c:2026 / 1304` | 轮询（不注册中断） | 见 §4 |

---

## 3. 我们缺的东西（按重要性排序）

### ★★★ 3.1 缺「固件 config 应用完成」这个**状态**：`cmd_ack.state == 0x80`

官方对命令缓冲**读两个字段**：`ack`（字节 1，命令帧是否被接收）和 `state`（字节 0，固件是否处理完）。
`state` 只在 `wait_cmd_status()` 里读，而**只被 config 三阶段用**——这正是我们从未实现的那个判据。

```
官方: goodix_brl_hw.c:450 wait_cmd_status()
      ret = hw_ops->read(cd, misc->cmd_addr, cmd_ack.buf, sizeof(cmd_ack));   :459
      if (!ret && cmd_ack.state == target_status) {                            :461
              ts_debug("status check pass");
              return 0;
      }
      msleep(20);                                                              :466
      ...重试 CONFIG_CMD_WAIT_RETRY = 20 次（:448）→ 最长 400 ms
```

`send_cfg_cmd()` 对 **START / WRITE / EXIT 三条命令每一条**都调用它：

```
官方: goodix_brl_hw.c:484-489
      ret = cd->hw_ops->send_cmd(cd, cfg_cmd);
      ...
      ret = wait_cmd_status(cd, CONFIG_CMD_STATUS_PASS /*0x80*/, CONFIG_CMD_WAIT_RETRY);
```

而 `brl_send_cmd()` 自己的成功判据是**另一个字段**：

```
官方: goodix_brl_hw.c:398
      if (cmd_ack.ack == CMD_ACK_OK)  { msleep(40); return 0; }
```

⇒ 官方是**两段式**：先 `ack==0x80`（命令帧被接收，`:398`），再 `state==0x80`（固件处理完毕，`:461`）。
我们的 `patch` 在 5 处（`:4144/4189/4397/4410/4500`）**只做了第一段**。

**为什么这会导致无报告**：`CFG-EXIT` 之后，我们从来没观测到固件是否真的离开"接收 config"状态。
日志里 `CFG-EXIT ack=80 OK-config-applied`（`usblog-20261111-130708/console.log:759`）这句
"OK-config-applied" 是我们自己 `patch:4411` 打印的字符串，它只证明 ack 字节是 0x80，
**不证明 config 已应用**。
若固件始终没到 `state==0x80`，它就停在"等 config / 处理 config"的分支里，不会去组报告帧。

> 这正是任务书要求的「不是一个命令，而是一个状态」。

### ★★★ 3.2 凭空多出的 `CFG-RESET` 硬复位（官方从不做）

```
我们: patch:4438-4442
      printf("goodix: CFG-RESET assert reset (gpio%d)\n", PIN_RESET);
      gpio_set(PIN_RESET, false);
      sleep_ms(2);
      gpio_set(PIN_RESET, true);
      sleep_ms(100);
```

官方 `brl_send_config()` 之后**只有 `msleep(100)`**（`brl_hw.c:555`），全程没有 reset。
我们把它从 `fwupdate.c:924`（`goodix_update_finish()`，那是**烧 flash 固件**路径的收尾，
不是下 config 的收尾）搬了过来——`goodix_send_ic_config()` 走的是 `brl_send_config()`
（`core.c:2088`），**根本不经过 `goodix_update_finish()`**。

两个后果：
1. **RAM 里的 config 被丢弃（确定）**。`brl_send_config` 写的是 `fw_buffer_addr = 0x1205c`（`:520`），
   那是芯片 RAM。硬复位后固件重新从 flash 载入 config，我们刚写的 1488 字节全部作废。
2. **复位后我们写 `0xC900`（官方在 D 上明令不碰，`brl_hw.c:59-61`），芯片因此处于
   一个官方从未定义过的状态。** 官方 `brl_reset()`（`:310-323`）复位后只做
   `return brl_select_spi_mode(cd);`（`:322`，在 D 上被 `:59-61` 拦成 no-op），
   **也不跑 `dev_confirm`**——所以"复位后必须握手"不是官方规则，本项不作主要论据。
   「推测」：复位后芯片停在 ROM 未握手，是 `int` 恒高的一种可能；但**第 1 点已足够解释无报告**。

⇒ 复位后芯片处于一个**官方从未定义过**的状态，且刚写好的 config 已作废。

### ★ 3.3 在 Berlin-D 上写 `0xC900 = 0x01`

```
官方: goodix_brl_hw.c:52-61
      static int brl_select_spi_mode(struct goodix_ts_core *cd)
      {
              if (cd->bus->bus_type == GOODIX_BUS_TYPE_I2C ||
                              cd->bus->ic_type != IC_TYPE_BERLIN_A)
                      return 0;                      ← D 直接不写
```

`0xC900` 是 **berlin_A SPI mode** 寄存器（`brl_hw.c:19-21`）。D 上它从未被官方写过。
我们写了并"验证成功"（日志 `0xc900 SPI-enable write/verify -> OK (rb=01)`），
但回读等于写入值只证明那个地址可读写，**不证明它是 SPI 模式寄存器**——在 D 上它可能是别的功能。
`brl_reset_after()` 里真正的 D 侧初始化（clk_sta / D12 trim）反而被 `:114-115` 整段跳过，
我们也没实现。

### ★★★ 3.4 开机就发 `0x90/0x81` 进 rawdata，且**minimal 路径也没跳过**

官方只在容值/裸数据测试里发这条（`brl_hw.c:1313`，由 `goodix_ts_inspect.c:1419-1429`
的 `goodix_cap_test_prepare()` 调用），**并且 `brl_send_cmd` 无论成败都在 `exit:` 补一条
`0x90/0x00` 回坐标模式**：

```
官方: goodix_brl_hw.c:1347-1351
exit:
      temp_cmd.cmd = 0x90;
      temp_cmd.data[0] = 0;
      temp_cmd.len = 5;
      brl_send_cmd(cd, &temp_cmd);
      /* enable irq & esd */  brl_irq_enbale(cd,true); goodix_ts_blocking_notify(NOTIFY_ESD_ON,NULL);  :1353-1354
```

**代码实证**：`patch:4100-4152` 这段（`0x90/0x81`）没有任何 `k60_touch_minimal` 判断；
`k60_touch_minimal` 只出现在 4 处（`patch:2866 / 2888 / 4345 / 4487`）。
三个 minimal 运行日志里都有：

```
usblog-20261111-101548:758  goodix: CMD-FIX frame 00 00 05 90 81 16 01 00
usblog-20261111-115745:758  goodix: CMD-FIX frame 00 00 05 90 81 16 01 00
usblog-20261111-181651:738  goodix: CMD-FIX frame 00 00 05 90 81 16 01 00
```

而三者的 `COORD-MODE` 次数 = **0**（minimal 守卫 `patch:4487` 把 `0x90/0x00` 跳掉了）。

⇒ **minimal 路径的实际状态是：「进了 rawdata，没有出来」，外加「发了 CFG-START，没有数据」。
它不是"跳过全部命令"的干净状态，所以它证明不了"命令无害"。**

这也直接解释了为什么 minimal 的 `reports` 仍然是 0 —— 它从头到尾没在坐标模式上运行过。

### 3.5 少了 `config_id` 相等则整段跳过

```
官方: core.c:2081-2085
      config_id = goodix_get_file_config_id(cfg->data);
      if (cd->ic_info.version.config_id == config_id) { ...; return 0; }
```

我们无条件下发。我们的 config 包 `goodix_cfg_group_m11a.bin` 里 `cfg_id = 0x640fdf7d`
（offset 139+30，实测），而芯片 IC_INFO 的 `version.config_id` 在同一结构里我们没打印过，
所以**连"该不该发"都没判断**。

### 3.6 命令帧只写 8 字节，官方写 16

```
官方: brl_hw.c:382   hw_ops->write(cd, misc->cmd_addr, cmd->buf, sizeof(*cmd));   // =16
我们: patch:4133     goodix_write(command_address, f, sizeof(f));                  // f 是 uint8_t f[8]
```

`struct goodix_ts_cmd` 是 `state,ack,len,cmd,data[10]` 共 16 字节（`core.h:311-324`），
`cmd_max_len` 我们实测打印为 16（日志 `MISC cmd=0x10174 cmax=16`）。写 8 字节时
`data[2..9]` 保留的是上一次的内容。校验和只覆盖 `buf[2..4]`（`utils.c:42-53` 被 `brl_hw.c:376`
以 `&buf[2], len-2` 调用），所以内容上够用，但与官方帧长不一致。

### 3.7 ACK 后的静置时间不同

```
官方: brl_hw.c:399   msleep(40);   // 命令成功后固定等 40 ms
我们: patch:4133-4142 轮询 15 次 × 20 ms，一旦读到非 0/0xff 就 break
```

官方在 `send_cmd` 成功后**无条件等 40 ms** 才继续；我们是"读到即走"。对 config 这类
需要固件真正动作的命令，这个差别会放大 §3.1 的问题。

---

## 4. INT 处理对照

### 官方

| 项 | 官方实现 | 证据 |
|---|---|---|
| 触发类型 | 由 DT `irq-flags` 决定，`devm_request_threaded_irq(..., irq_flags \| IRQF_ONESHOT, ...)` | `core.c:1304-1309` |
| 形态 | **threaded + ONESHOT**（上半部传 `NULL`） | `core.c:1305-1307` |
| 处理函数第一步 | 置 `ts_esd->irq_status = true`、`irq_trig_cnt++`，再跑外部模块 `irq_event` | `core.c:1249-1262` |
| 真正的读 | `hw_ops->event_handler()` → `brl_event_handler()`，**先读 26 字节**（8 头 + 2 触点 + 2 校验） | `core.c:1266`；`brl_hw.c:1179-1182` |
| 读前的判定 | `if (pre_buf[0] == 0x00) return -EINVAL;` —— **首字节为 0 就是没报告，直接退出** | `brl_hw.c:1188-1191` |
| 必清寄存器 | **有**。读完必须 `write(touch_data_addr, 0, 1)`，否则不再产生下一次中断 | `brl_hw.c:1226-1236` |
| 清的前提 | `if (cd->tools_ctrl_sync) return 0;` —— 工具占着同步标志时不清 | `brl_hw.c:1232-1233` |

> **「必须清某个寄存器否则不再中断」的机制确实存在**：就是往 `touch_data_addr` 首字节写 0。
> 主线驱动一模一样：`mainline:599 regmap_write(cd->regmap, cd->touch_data_addr, 0);`

### 我们

- DT `irq-gpio=21, flags=0x2008` = `IRQF_ONESHOT(0x2000) | IRQ_TYPE_LEVEL_LOW(0x8)`，
  与官方 `irq_flags | IRQF_ONESHOT` 语义一致（`core.c:1307`）。
- 我们不注册中断，用轮询读电平 + 每 16 ms 盲读一次（继承 `hakios.goodix.c:1490,1525`）。
  这条路在 PHK110 真机上可行，**不是故障点**。
- 清标志我们做了（`patch:2931 goodix_write(touch_address, &zero, 1)`，日志
  `FRAME clear write -> accepted`）。**但注意**：日志紧接着 `FRAME after ... (unchanged)`、
  `FRAME +200ms ... (static)` —— 写完 0 之后首字节**仍是 `00 94 b7 56 ...`**，
  说明这个"清"从未真正生效（那不是报告区应有的响应方式）。

- **关键观测**：`POLL hb int=...` 心跳里 `int` 是电平采样，不是"有没有报告"。
  `usblog-20261111-181651`（minimal）24 次心跳里 2 次 `int=0`（行 2739、2938），
  而 `reports=0` 全程不变 —— **INT 变低并不等于出了报告**。
  `usblog-20261111-130708`（完整流程）19 次心跳全 `int=1`。

| 运行 | 路径 | 心跳数 | int=0 次数 | reports | CFG 数据 | CFG-WRITE | CFG-RESET | COORD-MODE | 0xC900 | CMD-FIX(0x81) |
|---|---|---|---|---|---|---|---|---|---|---|
| `101548` | minimal | 17 | 0 | 0 | SKIP | 无 | 无 | 无 | 无 | **有** |
| `115745` | minimal | 13 | 1 | 0 | SKIP | 无 | 无 | 无 | 无 | **有** |
| `181651` | minimal | 24 | 2 | 0 | SKIP | 无 | 无 | 无 | 无 | **有** |
| `011925` | 完整 | 17 | 1 | 0 | sent | 有 | 有 | 无 | 有 | 有 |
| `001337` | 完整 | 23 | 0 | 0 | sent | 有 | 有 | 无 | 有 | 有 |
| `130708` | 完整 | 19 | 0 | 0 | sent | 有 | 有 | 有 | 有 | 有 |
| `191415` | 完整 | 24 | 0 | 0 | sent | 有 | 有 | 有 | 有 | 有 |

**两个必须看清的事实：**

1. **「minimal 时 INT 变低」并没有伴随报告。** 三个 minimal 运行 `reports` 全为 0，
   `int=0` 只在 17/13/24 次心跳里出现 0–2 次。`0x10308` 首字节始终 `0x00`。
   ⇒ `int` 电平**不是**"有没有报告"的判据，`brl_hw.c:1188` 的首字节判据才是。
2. **minimal 与完整流程都没有在"坐标模式"下真正运行过。** minimal 缺 `0x90/0x00`（`patch:4487` 跳过），
   完整流程做了 `CFG-RESET`（`patch:4438`）。

所以"minimal 能中断、完整流程不能"这个对比，**其前提不成立**：两者都不能。
差别只是 minimal 少了 config 写入与硬复位，所以它的失败发生在更早的 `0x90/0x81` 那一步。

> `int=0` 的正确解读：它是「芯片把 INT 拉低过」的电平采样，可能来自上电/复位后的瞬态、
> 也可能来自 rawdata 模式下的帧同步，但都不是 `event & 0x80` 的坐标报告。
> 「推测」：`0x90/0x81` 之后芯片在 rawdata 帧周期里会短暂拉低 INT，这解释了 `int=0` 的零星出现。

---

## 5. 最可能的根因（三条，均有原文证据）

### 根因 1（两条路径共有）：启动就 `0x90/0x81` 进 rawdata，而 minimal 从不回坐标模式

- 官方只把 `0x90/0x81` 当**测试模式入口**用，且 `exit:` 无条件补 `0x90/0x00`（`brl_hw.c:1348-1351`）。
- 我们 `patch:4100-4152` 在启动路径无条件发 `0x90/0x81`（**无 minimal 守卫**）。
- minimal 的 `0x90/0x00` 被 `patch:4487` 跳掉 → 三个 minimal 日志 `CMD-FIX ack=80` 且 `COORD-MODE=0`。
- 完整流程虽然发了 `0x90/0x00`（`patch:4492`），但在此之前先做了 `CFG-RESET` 硬复位。
- **这条同时解释了两个现象**：minimal 为什么 `reports=0`，以及完整流程为什么也没有报告。
- 硬证据：`brl_hw.c:1313`（唯一的 `0x81` 调用点）+ `:1348-1351`（强制配对退出）+ `patch:4487`（唯一跳过点）。

### 根因 2（完整流程独有）：config 之后做了一次官方从不做的硬复位，作废刚写进 RAM 的 config

- 官方 `brl_send_config()` 之后的全部动作 = `msleep(100)`（`brl_hw.c:553-556`）。
- 我们 `patch:4438-4442` 硬复位、`:4444-4456` 只补 `0xC900`（D 上官方不碰的寄存器，`brl_hw.c:59-61`）。
- config 写在 `0x1205c`（**RAM**，`brl_hw.c:520`），硬复位后固件从 flash 重载，1488 字节全废。
  这是硬事实。
- 附带的次要风险：复位后我们没有 `dev_confirm`。「推测」芯片可能停在 ROM。
- 数据旁证：跑过 `CFG-RESET` 的 `130708 / 191415` 两次 `int` 全程为高（完整表见 §4）；样本少，仅旁证。

### 根因 3（完整流程独有）：只查 `ack` 不查 `state`，`CFG-EXIT` 的"已应用"从未被证实

- 官方 `wait_cmd_status()` 读 `cmd_ack.state == 0x80`（`brl_hw.c:461`），START/WRITE/EXIT 后各等一次，
  最长 400 ms（`:448,466`）。
- 我们 5 处判据全是 `ack[1] == 0x80`（`patch:4144/4189/4397/4410/4500`）。
- 后果：无法确认固件是否离开了"接收/处理 config"分支。与 `0x10308` 首字节恒 `0x00`
  （`brl_hw.c:1188` 正是官方"无报告"判据）吻合。

### 排除项（有证据，不必再查）

| 说法 | 排除依据 |
|---|---|
| "必须下发 config 才会扫描" | 主线 `mainline:728-805` 零命令零 config 即可工作；`mainline:14-24` 明言只处理已烧好固件的 multitouch |
| "minimal 跳过全部命令、所以命令无害" | **前提错误**：三个 minimal 运行都有 `CMD-FIX 0x90/0x81 ack=80` 与 `CFG-START ack=80`（`usblog:101548/758-761`、`115745/758-761`、`181651/738-741`），因为 `patch:4100-4152`、`patch:4164-4195` 不在 minimal 守卫内 |
| "`dev_confirm` 有害" | minimal 跳过它仍能读版本/IC_INFO 并出现 `int=0`；且官方把它列为上电必做（`brl_hw.c:236`） |
| "config 地址写错" | 已在 `patch:4363` 用 `fw_buffer_addr`；日志 `CFG-DL wrote=1488/1488 bad=0` |
| "config 内容不对" | 本地 `goodix_cfg_group_m11a.bin` 按 `goodix_cfg_bin.c:45-98` 解析：`pkg_len=1609`，`head=56+65=121`，body 起点 `18+121=139`、长 1488，与 `patch:4215` 的 `k60_cfg[1488]` **逐字节同源**；body 内嵌 `goodix_config_head` 面板名 `NM`、`fw_pid=9916R`、`fw_vid=05 80 02 63`、`cfg_id=0x640fdf7d`、`cfg_len=1424`、`cfg_num=66`、校验和 `0x08d3` 自校验通过 |
| "misc 偏移错" | 已由 head=8/point=8 交叉命中（本任务不复核） |
| "INT 处理方式错" | 官方 DT 电平低触发（`core.c:1307`），轮询电平等价；`hakios.goodix.c:1525` 真机可用 |

---

## 6. 修复顺序（按根因，不动其它代码）

按「先让芯片进入官方定义的扫描状态」排序，前三条是**状态**层面的，不做完它们，
后面调什么都不会出报告。

1. **把 `0x90/0x81` 从启动路径彻底删掉**（`patch:4100-4152`）。启动时官方从不让芯片进 rawdata；
   依据 `brl_hw.c:1313`（唯一调用点在容值测试）+ `:1348-1351`（强制配对退出）。
   删掉后 minimal 与完整流程都会回到"上电即在坐标模式"的官方初始态。
2. **删掉 `CFG-RESET` 硬复位整段**（`patch:4432-4456`）。官方 config 后只有 `msleep(100)`（`brl_hw.c:553-556`）；
   这段会把刚写进 `0x1205c`（RAM，`:520`）的 1488 字节 config 全部作废。
3. **把 5 处 ack 判据改成两段式**：先 `ack==0x80`（`brl_hw.c:398`），再轮询 `state==0x80`
   （`brl_hw.c:450-472`，最多 20 次 × 20 ms = 400 ms，`:448`）。
   这是唯一能证明「固件已应用 config」的官方判据。
4. **`0xC900` 在 Berlin-D 上不要写**（`patch:2888-2911`），依据 `brl_hw.c:59-61`。
5. **加 `config_id` 相等则整段跳过**（`core.c:2081-2085`）：先打印 `ic_info.version.config_id`
   （`goodix_ic_info_version` 第 5 字节起 u32，`core.h:146-158`）与本地 `0x640fdf7d` 比对。
6. 命令帧写满 16 字节（`brl_hw.c:382` vs `patch:4133` 的 8 字节）。
7. 若要贴近官方时序，把 ack 后的"读到即走"改成官方那样固定 `msleep(40)`（`brl_hw.c:399`）。

> 验证只看一个判据：**`0x10308` 首字节是否出现非 `0x00`**。
> 那就是官方自己的"有报告"判据（`brl_hw.c:1188`）。不要再用 INT 电平当成功标志——§4 已证明它不可靠。
