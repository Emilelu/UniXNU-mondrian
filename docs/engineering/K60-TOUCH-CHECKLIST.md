# K60 触摸排障 Checklist —— 严格按 ruby §8 逐条执行

> 参考：`references/ruby-bringup/docs/touch-goodix-9916r.md`
> 依据铁则：HR-27（先抄清单逐条执行）、HR-28（改动须有文档依据）、
>           HR-29（从磁盘恢复状态）、HR-30（已排除假设不重试）
> **未走完本清单前禁止改代码。要改必须先指出第 N 条 FAIL。**

## 当前状态（每轮更新，事实优先于叙述）

| 条 | 项目 | 状态 | 实测值 | 判据（文档原文） |
|---|---|---|---|---|
| 1 | I2C5 SCL/SDA 空闲为 1 | **PASS** | SPMI arbiter ver=0x70000000 apids=768 layout=v7；326 PPID 应答；PPID 0x013->apid 407 与代码注释一致 | §8-1 |
| 2 | 读 LDO3/LDO2 EN/VOUT | **部分** | SPMI 全量 477 外围已扫（P-84 修正）。但 P-85 发现 +0x40/+0x41/+0x46 是 MT6360 偏移，不适用 pm8350c，读数无效。**RPMh 写入已确认成功**（见 P-86/P-87） | 旧值通常 `0x80/0xB0`、`0x80/0x40` |
| 3 | VOUT 回读须 `0x3A/0xD0`，EN 后 `0xC4` | **阻塞** | pm8350c 正确偏移未知，无法回读 | §8-3 |
| 4 | dev_confirm 失败 → 查复位/IOVDD/SPI 线序 | **PASS** | `device confirm OK (0x10000 = 8 x 0xAA)` | §8-4 |
| 5 | 版本失败 → 查 ROM BERLIN/checksum/sensor | **PASS** | `BERLIN / 9916R / 05.80.02.63 / sensor 255` | §8-5 |
| 6 | 帧全 0 → 查 CS/CLK/MISO 与 sync 清零 | **FAIL** | power 修复后 `0x10308` 仍静态：`00 94 b7 56 4b b4 ce be`（CHANGED NO）。SPI 已证通（版本区 28B、IC_INFO、dev_confirm 全 OK），故不是线序问题；疑为扫描引擎未启动或 sync 从未清除 | §8-6 |
| 7 | 有帧无触摸 → 查 event/touch_num/point csum | **阻塞** | 第 6 条未过，无从检查 | §8-7 |
| 8 | 坐标方向 raw/10，无翻转 | 阻塞 | — | §8-8 |

## 关键结论（截至 2026-11-10 17:52）

**第 2、3 条是本轮的主攻方向，也正是 ruby 文档 §3.2 记录的根因：**

> 「只写 enable 位会让 AVDD 欠压，芯片完全不启动；
>   这也是 P1f/P1g 一直读到全 0 的原因。」

**我们的状态与 P1f/P1g 完全同型：**
- dev_confirm OK（第 4 条 PASS）
- 版本 OK（第 5 条 PASS）
- 帧读不到 / 静态垃圾（第 6 条 FAIL）

**这与「AVDD 欠压，ROM 能应答但扫描引擎不工作」的特征完全一致。**

## 第 2 条：读 LDO3/LDO2 EN/VOUT —— 如何执行

ruby 用 MT6360 的 I2C5（SCL GPIO132/SDA GPIO133，slave `0x64`），
CRC8 保护的 SMBus block 访问：

- 写：`START, addr<<1, reg&0x3f, value, crc, dummy0, STOP`
- 读：`START, addr<<1, reg, repeated START, addr<<1|1, value+ACK, crc+NACK, STOP`
- CRC8：poly `0x07`、init `0`、MSB-first，覆盖 `[addr<<1, reg&0x3f, value]`

寄存器：
- LDO3（VMC/IOVDD 1.8V）：EN `0x05` bit6，VOUT `0x09`
- LDO2（VTP/AVDD 3.3V）：EN `0x11` bit6，VOUT `0x15`

**K60 必须做同样的事，但走 SM8475 的 PMIC 路径。**
已知（`docs/OPS-TWRP-DD.md:171-173`，Android 实机）：
```
regulator.27 name=pm8350c_l2  state=enabled  uV=1800000   ← 触摸 IOVDD
regulator.29 name=pm8350c_l3  state=disabled uV=2700000   ← 疑似 AVDD，Android 也是 disabled
regulator.43 name=pm8350c_l12 state=enabled  uV=1800000
```

**关键疑点：`pm8350c_l3` 在 Android 上也是 `disabled`，
说明 K60 的 AVDD 可能不来自 PMIC，而是 GPIO 负载开关（我们用的 GPIO71）。**
**那 GPIO71 到底输出了多少伏？从未测量。**

## 下一步（严格按清单顺序）

1. **先做第 1 条**：确认 I2C/SPMI 通信本身可用（否则第 2 条无从读）
2. **再做第 2、3 条**：用 RPMh 的读命令（不是写）回读 ldoc2 实际电压
3. 第 2、3 条 PASS 之前，不再碰帧解析

## 已排除假设（HR-30 登记，不要重试）

| 假设 | 实测反证 | 日志 |
|---|---|---|
| `0x10308` 可写（用于清 sync） | 写入 accepted 但回读 `unchanged`，200ms 后仍 `static` | `usblog-20261110-164538` |
| `0x10400` 是格式化帧 | `[3..7]` 固定 `e8 08 e8 08 01`，值域 `0x26fe..0x2719` 是直流偏置+噪声 | `usblog-20261110-174720` |
| GENI SE4 FIFO 可用 | `status 0, sent 13, received 0` | 多轮 |
| `pm8350c` ppid = `0x2c2` | SPMI 上找不到 | `usblog-20261110-143619` |
| TLMM 窗口 0x20000 够用 | gpio71 cfg 读回 0（越界） | `usblog-20261110-151747` |


---

## 2026-11-10 19:13 电源突破（内核 9ea06001 / 镜像 6ac1d7b1 / usblog-20261110-191312）

```
goodix: RPMh caps=0x800c8104 count=8 ncpt=16 ver=0x20700 tcs4_idle=1
goodix: rails written iovdd=0x42c00 avdd=0x40f00 (ldoc3)
goodix: rails on (ldoc2=0x42c00, AVDD gpio71=1)     <- 不再超时
K60S19: bitbang dev_confirm -> OK
K60S19: bitbang goodix_probe -> OK (SPI by GPIO path)
```

**三项修正确认生效：**
1. P-82 TLMM 窗口 0x80000 -> gpio71 cfg=0x280 output enable
2. P-86 TCS 槽位 slot0 -> ACTIVE TCS4 (0xd00+4*0x2a0)
3. P-87 完成判据 IRQ_STATUS -> CMD_STATUS(&0x10100)==0x10100 && idle

**仍未解决：** 帧区 0x10308 静态（`CHANGED NO`），`int=0` 仅在 1200 次轮询中出现 3 次。

**下一个假设（待验证）：** Goodix BerlinD 需要显式"扫描使能"命令，
vendor `goodix_core.ko` 在 `0x1728c` / `0x172b8` 处加载立即数 `0xc900`，
需反汇编该上下文确定完整命令帧，不能凭猜。

---

## 2026-11-10 19:50 诚实评估：已开通但无 report 生成

### 已确认成立的事实（有日志证据）

| # | 项 | 证据 |
|---|---|---|
| 1 | TLMM 窗口已修 | P-82，gpio71 cfg=0x280 out_en=1 |
| 2 | RPMh 电源真通 | P-86/P-87，TCS4+CMD_STATUS，无超时 |
| 3 | SPI bit-bang 可用 | dev_confirm OK、goodix_probe OK |
| 4 | 0xc900=0x01 握手 OK | rb=01，芯片确认 SPI 模式 |
| 5 | **0x10400+ 是活热力图** | `0x10420-0x10760` 每帧 CHANGED，值域 0x2600-0x2a00 |
| 6 | **0x10308 是静态垃圾** | 200+ 轮从未变化，00 94 b7 56 ... |

### 仍未解决

| 项 | 状态 |
|---|---|
| **格式化 report 未生成** | 0x10308 静态，reports=0 |
| **INT (gpio21) 触摸时不拉低** | POLL hb int=1 恒定，仅 reset 时 int=0×2 |

### 核心矛盾

Goodix BerlinD 固件在检测到触摸时，会**自己**把 report 写到
`0x10308`（ruby §5.3 如此，MTK 上就是这么通的）。
但 K60 上 `0x10308` 完全静态。

**两个可能：**
1. **report-enable 寄存器从未写**（0xc900 只是 SPI 模式，还要单独使能 report 输出）
2. **INT 极性/引脚不对**，或触摸根本没到达芯片（热力图变化是电源噪声）

### 下一决定性测试（不再猜）

**热力图峰值跟踪**：在轮询里持续跟踪 `0x10400` 区的最大值位置，
让用户手指触摸屏幕：
- 若峰值位置随手指移动 → 触摸物理上到达芯片，只是 report 没生成 → 查 report-enable
- 若峰值不动或 max 只是缓慢漂移 → 触摸未到达芯片 → 查 INT 引脚/极性/同步序列

**这个测试直接区分"芯片没感应到" vs "感应到了但没上报"，是最省时间的一步。**


---

## 2026-11-10 20:10 决定性突破：找到 config 下载完整协议（官方 brl_hw.c）

### 已确认芯片
```
goodix: chip "BERLIN", firmware "9916R" 05.80.02.63, sensor 255
```
**K60 触摸就是 GT9916R BerlinD（同 ruby），协议层应适用 ruby/官方驱动。**

### 本地已找到完整官方驱动源码
`<workspace>/impl/touch-protocol/refs/`
- goodix_brl_hw.c (1474 行)  ← 硬件+config下载
- goodix_brl_fwupdate.c (35KB) ← 固件更新
- goodix_ts_core.c (61KB)
- goodix_cfg_bin.c (9KB, 已整篇读)
- + 本机 config/firmware bin!
  `<workspace>/scratch/goodix-fw/goodix_cfg_group_m11a.bin` (1627B)
  `<workspace>/scratch/goodix-fw/goodix_firmware_m11a.bin` (223744B)

### 🎯 config 下载三阶段协议（brl_hw.c:493-560 已完整读）
```c
#define CONFIG_CMD_START  0x04
#define CONFIG_CMD_WRITE  0x05
#define CONFIG_CMD_EXIT   0x06
#define CONFIG_CMD_STATUS_PASS  0x80
#define CONFIG_CND_LEN    4        // cmd 缓冲 4 字节

1. send_cmd(CONFIG_CMD_START=0x04) -> wait 状态 0x80 (20x20ms)
2. write(fw_buffer_addr, cfg, len)      // cfg 来自 config bin 的实际数据段
3. read(fw_buffer_addr, tmp) 读回比较   // 校验
4. send_cmd(CONFIG_CMD_WRITE=0x05) -> 通知固件
5. send_cmd(CONFIG_CMD_EXIT=0x06) -> 结束
6. msleep(100)
```

### 之前核心误判（HR-30 更正）
**以为 config 在芯片里出厂就有（ruby §7「版本/config 相等时不下载」）。
实际 brl_send_config 证明 config 必须主动下载回芯片，
否则 AFE 用默认配置无法校准 -> 正是 node=72 恒满 / 无 report / 无 INT 的特征。**

### 已知/缺
- command_address = 0x10174 (已有)
- cfg 数据 = goodix_cfg_group_m11a.bin 的解析后数据段 (待从 goodix_cfg_bin.c 取出)
- **fw_buffer_addr = 缺**（从 cd->ic_info.misc.fw_buffer_addr 读，需查 brl_read/read in goodix_ts_core）

### 下一步（决定性，非盲改）
1. 从 goodix_ts_core.c 的 brl_read 看 misc 结构读 fw_buffer_addr
2. 从 config bin 解析出实际 cfg 数据段（长度 < fw_buffer_max_len）
3. 实现 brl_send_config 三阶段下载（bit-bang SPI 已有 write/read）
4. 下载后应产生 report —— 那才是真正触摸打通

---

## 2026-11-10 21:05 里程碑：固件命令通路打通（ack=0x80 OK）

**内核 66abb3f2 / 镜像 9900cc30 / usblog-20261110-210508**

```
goodix: CMD-FIX frame 00 00 05 90 81 16 01 00
goodix: CMD-FIX ack=80 OK      ← 固件接受命令！
```

### 证明的事
1. 命令帧格式正确：`[state=00][ack=00][len=05][cmd=90][d0=81][cs低=16][cs高=01]`
2. 校验和算法正确：官方 `goodix_ts_utils.c:36-60`
   - `checksum = sum(&buf[2], len-2)`，`buf[5]=低, buf[6]=高`
   - 之前 ack=0x04 CHECKSUM-ERR（f[6] 应为 01 而非 00）
3. 固件服务循环活着、能响应命令
4. bit-bang SPI 写/读全部正确

### 关键结论
- 之前所有「0x10308 静态 / int 不拉低」都是因为**没走对命令协议**
- 固件不是死了，是我们在等错误的东西
- `0x10400` = fw_buffer（可写 RAM），不是热力图

### 下一步（GBP)
1. 读坐标命令：`GOODIX_CMD_COORD = 0`（brl_hw.c:1359）
2. config 下载：`brl_send_config` 三阶段（brl_hw.c:493，需分块因 fwmax=16）
3. 触摸 report 应发生在 config 下载 + 扫描使能后

### 已解决 vs 待解决
| 项 | 状态 |
|---|---|
| 电源（P-82/86/87）| ✅ |
| SPI bit-bang | ✅ |
| 命令通路（ack=0x80）| ✅ 本里程碑 |
| 读坐标 | 待做：cmd=0 |
| config 下载 | 待做：分块三阶段 |
| 触摸 report | 待上述完成 |

---

## 2026-11-11 00:13 决定性诊断：芯片根本没在扫描（verdict=chip-static）

**内核 385c7d5d / 镜像 b1b88195 / usblog-20261111-001337**

### IC_INFO 走查验证通过

```
goodix: ICINFO len=193 off=49
goodix: ICINFO vendor+138=+140: 14400 x 32000   <- 我们 1440x3200 的 10 倍，符合 GT9916 亚像素约定
goodix: ICINFO ours+52=+54: 1440 x 3200
goodix: ICINFO cmd=0x10174 touch=0x10308 alt=0x10400
```

**结论：五张 16-bit 列表走完后 off=49 正确，`touch_address=0x10308` 是公式算出的
正确地址**（不是 ruby 文档抄来的，是我们自己按 vendor 公式算的）。

校验方法来自 PHK110 真机可用的 Goodix 驱动
（`Seanding1998/hakios-xnu-kernel` @ phk110-port，`drivers/input/hakios.goodix.c:713-745`）：
它用 `max_x = le16(info+offset+122+16)` / `max_y = le16(info+offset+122+18)`
作为走查是否正确的判据。我们得到 14400/32000，是面板 1440x3200 的正好 10 倍。

### 三区采样结果：只有 0x10400 在动

```
SCAN touch  0x10308 changed=0/12   0094b756 4bb4ceba
SCAN frame  0x30084 changed=0/12   19461305 4553efc0
SCAN fwbuf  0x10400 changed=12/12  801900e8 08e80801
SCAN int=1 verdict=chip-static
```

| 区域 | 变化 | 含义 |
|---|---|---|
| `0x10308` touch_data_addr | **0/12** | 无触摸报告 |
| `0x30084` frame_data_addr | **0/12** | **无原始帧数据** |
| `0x10400` fw_buffer_addr | 12/12 | 只是诊断计数器（byte1 递增，`08e80801` 恒定）|

**`0x30084` 也静态 = 芯片连原始热力图都不产生 = 扫描引擎完全没启动。**

### 关键对照：真机可用的驱动不下载 config

PHK110 的 `drivers/input/hakios.goodix.c` L603-902 全段只有 5 处 SPI 调用：
- `:699` 读版本
- `:713/:717` 读 IC_INFO
- `:774/:778` 命令缓冲（仅 touch_rate=480 时用）
- `:866/:872` 读报告
- `:875` 写 0 清 sync

**零 config 下载、零扫描使能命令、零 sleep/doze，而真机可用。**

而且它的主循环（`:1516-1548`）**不依赖 INT 线**：
`idle_looks = 16000 / poll_us`，线恒高也每 16 ms 无条件读一次。
所以「INT 恒为 1」不是独立症状，只是「没有待读报告」的结果。

### 下一步（按依据排序）

1. **走裸路径**：power_on → reset → 0xc900 握手 → 直接读 0x10308，
   **跳过 config 下载和 dev_confirm 的 0xAA 写入**。
   假设：这两步中的某一步把芯片留在了测试状态。
2. 若裸路径仍静态：反汇编 vendor `goodix_core.ko`，找真正的扫描启动序列。
3. 加「INT 恒高也每 16 ms 读一次」的逃生阀（他们的做法，零风险）。

---

## 2026-11-11 01:31 GPU scanout 已接通

```
PONG SCANOUT: actual framebuffer handoff available sequence=0 status=0x0
PONG ADRENO: 22 步初始化全过（42 条 result=0）
```

`pong_gpu_scanout=1` 加入 boot-args 后，framebuffer handoff 成功。
boot-args 当前 595/600（上限 600，硬限 608 见 HR-45）。

**完整 GPU 开关组合：**
```
pong_adreno_start=1   驱动主开关（PongAdrenoPlatform.cpp:392）
pong_metal=1          Metal 桥（PongAdrenoClient.cpp:202）
pong_gpu_scanout=1    扫描输出（PongAdrenoScanout.cpp:44）
```

---

## 2026-11-11 01:45 GPU/Metal：dock 模糊消失的根因已定位

### 现象
用户反馈：dock 栏模糊效果没有，是纯色的。

### 根因（三层，全部有代码依据）

**第一层：Metal 插件从未被调用**

日志里只有：
```
PONG METAL: real IOAcceleratorES provider published for20G81 discovery
PONG METAL: NativeAdreno complete runtime publication status=0x0
```
但**没有** `real device returned to stock20G81 discovery`，也没有 `runtime refused device`
—— 说明 `- [PongAdrenoMetalDevice initWithAcceleratorPort:]` 从未被调用。

**第二层：系统找不到插件 bundle**

`drivers/PongAdreno/PongAdrenoAccelerator.cpp:44-45` 已正确设置：
```c
service->setProperty("MetalPluginName","PongAdrenoMetal");
service->setProperty("MetalPluginClassName","PongAdrenoMetalDevice");
```
系统据此去找 `/System/Library/Extensions/PongAdrenoMetal.bundle`。
**该 bundle 不在设备上，也没有挂载机制生效** → 系统无从加载。

**第三层：即使 bundle 在，还需要两个 root 拥有的种子文件**

`drivers/PongMetal/PongMetalPlugin.mm:170-199 selectedClient()`：
```c
for(const char *directory: {"/System/Library/Extensions", "/private/var/pong"}) {
    // publish：普通文件 + st_uid==0 + (st_mode & 022)==0 + 内容首字符 '1'
    if(lstat(marker,&st) || !S_ISREG(st.st_mode) || st.st_uid || (st.st_mode&022)) continue;
    const bool publish=fgetc(file)=='1'; if(!publish) return false;
    // clients：同样权限 + 当前进程名必须在列表里
    while(fgets(line,...)) if(!strcmp(line,process)) { selected=true; break; }
    return selected;
}
return false;
```
`initWithAcceleratorPort` 里：`if(!self || !port || !selectedClient()) return nil;`
**缺任一条件 → 返回 nil → 系统退回软件渲染 → dock 模糊变纯色。**

`scripts/build-pong-metal-plugin.py:40-41` 会生成这两个文件，
`clients` 列表是：
```
backboardd, SpringBoard, CollectionsPoster, WidgetRenderer_Default,
PosterBoard, Weather, WeatherPoster, GradientPosterExtension
```

### 挂载补丁存在但不兼容

`patches/xnu/zzy-native-gpu-addon-mount.patch` 正是做这件事：
- 把 owner 提供的 Metal bundle 以 MNT_RDONLY|MNT_UNION 挂到 `/System/Library/Extensions`
- 需要 boot-arg `sheng-gpu-addon=1`
- **但该补丁不在 SERIES-FINAL.txt 里**（而 P-90：改仓库 series 无效，必须改 SERIES-FINAL.txt）

尝试加入后构建失败：
```
error: patch failed: bsd/kern/kern_exec.c:7193
patches applied: 197
```
**它的上下文基于旧的 kern_exec.c，与当前补丁栈（0394/0398 等同样改 kern_exec.c）不兼容。**

### 两种修复路径

**A. 重新生成 addon 补丁**（对当前 kern_exec.c 重做 diff）
**B. 把挂载逻辑并入我们已控制的 0398 补丁**
   （0398-k60-pong-runtime-directories.patch 已经在改 kern_exec.c 的
   `native_owner_data_prepare`，在同一处加 `/System/Library/Extensions` 的
   bindfs union 挂载最自然）

**B 更稳**，因为 0398 已经在正确的位置、且我们完全控制它。

### 还需要的前置条件

1. `/private/var/pong/PongAdrenoMetal.bundle/` 必须存在于 Data 卷
   （由 `scripts/build-pong-metal-plugin.py` 在 Mac 上产出，需要 xcrun + Xcode）
2. `/private/var/pong/PongAdrenoMetal.publish` 内容 `1`、root 拥有、mode 不加 group/other 写位
3. `/private/var/pong/PongAdrenoMetal.clients` 含至少 `backboardd`
4. boot-arg `sheng-gpu-addon=1`

---

## 2026-11-11 01:50 GPU/Metal：部署链路摸清，剩余是工程问题

### 已验证存在且有效

```
<workspace>/impl/gpu-mac-build/out/metal-plugin/
├── PongAdrenoMetal.bundle/
│   ├── Info.plist                  695 B    NSPrincipalClass = PongAdrenoMetalDevice ✓
│   ├── PongAdrenoMetal             94,896 B Mach-O arm64 dylib ✓
│   ├── PongMetalBridge.dylib       33 MB
│   └── libvulkan_freedreno.dylib   18 MB
├── PongAdrenoMetal.publish         "1\n" ✓
└── PongAdrenoMetal.clients         backboardd/SpringBoard/... ✓
```

Mac 上同一份产物也在 `~/k60-build/out/metal-plugin/`。

### 现有部署机制不适用

`0340-k60-uilib-deploy.patch` 用**内核内嵌 C 数组**部署
`libpong-ui.dylib`（629 KB 补丁 ≈ 100 KB 二进制）：
```c
static const unsigned char k60_uilib_blob[] = { ... };
vnode_open("/private/var/pong/libpong-ui.dylib", O_CREAT|O_WRONLY|O_TRUNC, 0644, 0, &vp, ctx);
vn_rdwr(UIO_WRITE, vp, (caddr_t)k60_uilib_blob, sizeof(k60_uilib_blob), ...);
```
**Metal bundle 总计 51 MB，做成 C 数组约 300 MB 补丁文本，不可行。**

### 三条可行路径（按工程量排序）

**① 把 bundle 直接写进 Data 卷镜像（最简单）**
- Data 卷（`/dev/disk4s1`）是我们自己构建/写入的
- 把 `PongAdrenoMetal.bundle/` 和两个种子文件在离线阶段放进
  `private/var/pong/` 目录树
- 优点：一次性、不走内核、无大小限制
- 缺点：需要找到 Data 卷镜像的构建/写入脚本

**② 分块内核部署（中等）**
- 复用 0340 的模式，但只内嵌 `PongAdrenoMetal`（94 KB）+ Info.plist
- 两个大 dylib 单独处理（它们可以留在 Data 卷的普通路径，
  通过 dylib 的 `@rpath` 解析）
- 注意 `PongMetalBridge.dylib` 和 `libvulkan_freedreno.dylib` 是运行时依赖，
  `PongAdrenoMetal` 的 `@loader_path` 需要它们在同一 bundle 目录

**③ 运行时从 UFS 读取并写入（最复杂）**
- init 阶段从某个 UFS 分区读 bundle 写进 Data
- 需要额外的源位置

### 挂载步骤（三条路径都要做）

1. `/System/Library/Extensions/PongAdrenoMetal.bundle` 必须可见
   → bindfs MNT_RDONLY|MNT_UNION 从 `/private/var/pong/PongAdrenoMetal.bundle`
2. 两个种子文件在 `/private/var/pong/`：
   - `PongAdrenoMetal.publish` 内容 `1`、**uid=0**、mode 不加 group/other 写位（如 0644）
   - `PongAdrenoMetal.clients` 同样权限，含 `backboardd`
3. boot-arg `sheng-gpu-addon=1`（已在 packv15.sh 里）

### 挂载补丁需要重新生成

`patches/xnu/zzy-native-gpu-addon-mount.patch` 做的是步骤 1，
**但它的上下文基于旧 `kern_exec.c`，与当前补丁栈不兼容**：
```
error: patch failed: bsd/kern/kern_exec.c:7193
```

**建议把这部分逻辑并进 `0398-k60-pong-runtime-directories.patch`** ——
0398 已经在改 `native_owner_data_prepare`（创建 `/private/var/pong/*` 目录），
在同一个函数里加 bindfs union 挂载最自然，也避免再引入一个易冲突的独立补丁。

### P-90 教训

改 `patches/xnu/series` 无效，构建时会被
`scratch/SERIES-FINAL.txt` 覆盖（`buildv15.sh:12`）。

## 2026-11-11 18:20 状态订正：芯片在扫描，报告地址未找到

### 已经确证的事实

| 判据 | 结论 | 证据 |
|---|---|---|
| SPI 双向 | ✅ 通 | `device confirm OK (0x10000 = 8 x 0xAA)` |
| 芯片身份 | ✅ 正确 | `chip "BERLIN", firmware "9916R" 05.80.02.63, sensor 255` |
| **扫描引擎** | ✅ **运行中** | 完整抓包里 **INT 变低 2 次**（`int=0`），只可能由真实触摸引起 |
| `misc` packed 解码 | ✅ 字段对 | `fwbuf=0x1205c/4200 frame=0x10400 touch=0x10308`，`head=8 point=8` |
| config 下载 | ✅ 到官方地址 | `CFG-DL start, 1488 bytes -> fwbuf 0x1205c (max 4200)` / `bad=0` |
| **报告地址** | ❌ **找错了** | `0x10308` 每次读出同一串 8 字节，末字节跨启动 +2 = 计数器 |

### 为什么"reports=0"不代表芯片没工作

`goodix_poll()` 第一句：
```c
if (!goodix_read(touch_address, report, first) || report[0] == 0) return;
```
`report[0] == 0` 就返回，不计数。报告区如果不是 `0x10308`，
就永远读到首字节 0，`reports` 永远 0，**即使 INT 正常变低**。

### 下一步：触摸差分扫描

不再从结构体偏移推地址，改为**扫描并打印"值发生变化的地址"**：
空闲时固件更新的是计数器/状态，手指触摸时变化的是报告区，
两者命中的字节不同，报告区会自己暴露。

已在 `zzzz...-pong-touch-console.patch` 加入 `k60_touchmap_scan()`，
每心跳采样 `0x10000/0x10200/0x10400/0x30000` 各 16 个 16 字节步进的地址，
只打印变化的字节。

### dev_confirm 是否污染芯片（待定）

PHK110 真机可用的版本不做 `dev_confirm`（往 `0x10000` 写 8×0xAA）。
`k60_touch_minimal=1` 可以跳过它，用于对照。当前这版就是 minimal，
INT 仍能变低，说明 **`dev_confirm` 不是阻碍扫描的原因**。
