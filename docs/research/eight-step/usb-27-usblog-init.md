# 27 的 k60_usblog=2 初始化路径与 16.6.1 的差异（只读核实）

日期：2026-11-24。对象是 **当前** 27 树（2026-11-24 00:50 落入 0547/0548/0549，12:20–12:21 重建），
不是 2026-11-21 的 `652237c6` 构建。**不构建、不上机。**

参考产物：

- 内核 `/opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/kernel/kernel.macho`
  93,143,040 B，sha256 `7a5a603ef4e2010645ab091361e1cd97009fac089578d3d8147831013f66b981`
- `payload/payload.json`：`kernel_sha256` 同上；`kernel_args` 含 `k60_usblog=2 k60_console_export=1`
- 源 `.../tree/.cache/xnu-work/bsd/dev/k60_usblog.c` 1,338 行 / 44,702 B
- 编译产物 `.../DEVELOPMENT_ARM64_BCM2837/bsd/DEVELOPMENT/k60_usblog.o` 72,288 B（2026-11-24 12:20）

## 1. 结论

1. **参数链路存在，且确实编进 27 内核。** `k60_usblog=2` 由 `bsd/dev/k60_usblog.c:167` 的
   `PE_parse_boot_argn("k60_usblog", &enabled, sizeof(enabled))` 解析；早期探针调用在
   `osfmk/arm/arm_init.c:726-727`，worker 起点在 `bsd/kern/bsd_init.c:1340-1341`。
   `_k60_usblog_init/_k60_usblog_mode/_k60_usblog_start/_k60_usblog_reset_to_fastboot` 四个符号
   都在新内核的 65,581 个定义符号里，`strings | grep -c "K60 USBLOG"` = 51。
2. **27 的 gadget 是 0300 基线，缺 0307 的四处 DMA/描述符修复。** 27 源与 16.6.1 终版源
   （1,944 行 / 66,512 B），18 hunks（删 596 行 / 插 32 行）；0307 的四个 hunk（`patches/xnu/0307-k60-usblog-dma-coherency.patch:3,17,30,56`）
   在 27 一个都没有。16.6.1 的 0307 注释写下了不修时的实测症状：CPU 读 stale 事件
   （`console-font1.log: 8x "event 0x00000000", ev=8 cfg=0`），SETUP 完成被丢，主机
   GET_DESCRIPTOR 失败（Windows `VID_0000&PID_0002` Code 43）。⇒ 27 的第一次枚举
   **预期会复现 0307 之前的失败**。
3. **`k60_console_export=1` 在 27 是空转。** `bsd/dev/k60_console_export.c:37` 全文受
   `#if defined(PONG) && defined(XNU_PONG_RAMOOPS_CONSOLE) && XNU_PONG_RAMOOPS_CONSOLE` 包裹，
   27 的 `k60_console_export.o.json`（279 参数）没有 `-DPONG`、没有 `-DXNU_PONG_RAMOOPS_CONSOLE`；
   对象只有 **336 B**（唯一符号 `ltmp0`），内核里 `_k60_console_export_sysctl` 不存在
   （`strings | grep -c k60_console_export` = 0）。这不影响 USB CDC 的 drain：ramoops 的写者仍在
   `osfmk/console/serial_console.c:608,613,699`，`ud_console()` 直接读 `pong_ramoops_debug_base()`。
   因此 `k60_console_export=1` 目前只是无害的无效参数，不是通道的一部分。

## 2. 27 的调用链（file:line）

| 阶段 | 位置 | 代码 / 条件 | 失败或证据 |
| --- | --- | --- | --- |
| 编译登记 | `bsd/conf/files:634-637` | `bsd/dev/k60_usblog.c`、`k60_console_export.c`、`k60_usblog_reset.c`、`k60_adreno_grant.cpp` 四条 | 补丁 `xnu-patches.list:106-108` = 0547/0548/0549 |
| boot-arg | `bsd/dev/k60_usblog.c:162-171` | `PE_parse_boot_argn("k60_usblog", …)` :167；0 = inert，1 = read-only probe，2 = CDC console | payload args 里确有 `k60_usblog=2` |
| 早期探针 | `osfmk/arm/arm_init.c:726-727` → `k60_usblog.c:262-270` → `:206-256` | 在 `pong_ramoops_console_init()` 之后调用；probe 只读 GCC `GDSCR 0x49004` bit31 + 7 个 CBCR（0x49018/0x49020/0x49024/0x49084/0x49088/0x9c00c/0x9c010），再读 DWC3 与 eUSB2 0x88e3000 的 +0x1a0/+0x210/+0x240/+0x254 | 时钟不全：`K60 USBLOG: controller unpowered or unclocked; DWC3 not read` |
| worker 起点 | `bsd/kern/bsd_init.c:1340-1341` → `k60_usblog.c:1325-1338` | `k60_usblog_start()` 在 `result == KERN_SUCCESS` 块内（:1334 起），`kernel_thread_start(ud_worker, …)` | `k60_usblog_mode < 2` 时直接返回 |
| worker 顺序 | `k60_usblog.c:1147-1322` | `us = 2` → 2 s 心跳 `ud_hb` → `smmu_dump_state()` → 等 UFS SMMU stream 0xe0 最多 180×500 ms → GCC gate → map DWC3 → GSNPSID → GCTL.PRTCAPDIR → `DCTL &= ~RUN_STOP` 等 `DSTS.DEVCTRLHLT`（250×1 ms）→ 清 DEVTEN/DALEPENA → `kmem_alloc_contig(0x8000)` → `pmap_find_phys` → `smmu_usb_bypass` → `DCTL=CSFTRST`（500×1 ms）→ GUSB2PHYCFG/DCFG → 事件环 → 端点 → VBUS → `DCTL |= RUN_STOP` | 见 §3 每条的打印；60 s 无活动：`no USB activity 60 s after RUN_STOP; PHY rails or VBUS path suspect` |
| 控制器枚举门 1 | `k60_usblog.c` 同函数 | `(GSNPSID & 0xffff0000) ∈ {0x55330000,0x55340000,0x33310000}`；K60 的 GSNPSID 实测 `0x33313130`（16.6.1 `RESEARCH.md:56`） | 否则 `unexpected GSNPSID 0x%08x; gadget not started` |
| 控制器枚举门 2 | 同上 | `((GCTL >> 12) & 3) == 2`（device mode） | 否则 `GCTL.PRTCAPDIR not device` |
| 控制器枚举门 3 | 同上 | `DSTS.DEVCTRLHLT` 在 250 ms 内清 | 否则 `DWC3 did not halt`（同一段） |
| 端点复位 | `k60_usblog.c:760-777` | `ud_reset_endpoints()`：`DEPSTARTCFG`、`ud_endpoint(0,0,64)`、`ud_endpoint(1,0,64)`、`DALEPENA = 0x3`、`ud_start_setup()` | `K60 USBLOG: endpoint 0 setup failed` |
| EP0 状态机 | `k60_usblog.c:1038-1106`（`ud_event`） | XferComplete：`EP0_SETUP` → `ud_sync(UD_SETUP,8)` → `ud_setup()`；`EP0_DATA` → `WAIT_STATUS3`；`EP0_STATUS` → `ud_start_setup()`；`XferNotReady(status=2)` → STATUS2/3 | 状态卡住时无 `setup` 打印 |
| EP0 请求处理 | `k60_usblog.c:848-977`（`ud_setup`） | GET_DESCRIPTOR(1/2/3/6)、SET_ADDRESS、SET_CONFIGURATION、GET/SET_LINE_CODING、SET_CONTROL_LINE_STATE、SEND_BREAK、CLEAR_FEATURE；`SET_CONFIGURATION` 时 `ud_endpoint(2,2,packet)`（bulk OUT）、`ud_endpoint(3,2,packet)`（bulk IN）、`ud_endpoint(5,3,16)`（中断 IN），`DALEPENA |= 0x2c` | `K60 USBLOG: setup %02x %02x %04x len %u`；`configured (1)`；`DTR 1` |
| 描述符 | `k60_usblog.c:779-795` + `:802-819` | 设备：`18,1,0x00,0x02,2,0,0,64,0x09,0x12,0x01,0x00,0x00,0x01,1,2,3,1` ⇒ VID `0x1209` PID `0x0001`；配置：2 接口，IF0 CDC-ACM comm（EP 0x82 中断 IN 16 B），IF1 CDC data（EP 0x81 bulk IN 64、EP 0x01 bulk OUT 64）；`ud_configuration()` 按 speed 改 maxpacket | 主机侧看到 `1209:0001`；Windows 若按 class 绑定则看 subclass（见 §3） |
| console drain | `k60_usblog.c:978-1037`（`ud_console`） | 仅 `configured && dtr`；保持 bulk OUT 排空；ring header 双读 seqlock（magic `0x43474244`）；首次回放最后 64 KiB；每次 ≤1024 B，整包时 `--length` 造短包；`ud_start(3, UD_TXDATA, …)` | 出字内容应含 worker 前面的所有 `K60 USBLOG` 行 |

## 3. 与 16.6.1 的差异（按对枚举的影响排序）

| # | 差异 | 16.6.1 证据 | 27 现状 | 影响 |
| --- | --- | --- | --- | --- |
| D1 | 0307-1：ep0 IN TRB 偏移 | `patches/xnu/0307-k60-usblog-dma-coherency.patch:3`；16.6.1 源 `:926` `UD_TRB_IN 0x10c0`、`:930` `UD_TRB_RX 0x3040`（各自独占 64 B cache line） | 27 `:600` 仍是 `0x1010`、`:604` 仍是 `0x3020`（与 `UD_TRB_OUT 0x1000` 同线） | 一次 clean 可能覆盖相邻 TRB；配合 D3 造成事件/传输互相踩 |
| D2 | 0307-2：设备描述符 class/subclass | patch `:17`；16.6.1 `:1112` = `18, 1, 0x00, 0x02, 2, 2, 0, 64` | 27 `:779-782` = `2, 0, 0` | Linux/macOS 不变；Windows 不按 `USB\Class_02&SubClass_02` 绑 usbser.sys，需要手动驱动 |
| D3 | 0307-3：事件环读前 invalidate | patch `:30`；16.6.1 `:1552-1560` 的注释与原句 `ud_sync(UD_EVT, UD_EVT_SIZE)` | 27 `ud_events()` `:1108-1146` 直接从 `ud.dma + UD_EVT` 读，无 `ud_sync(UD_EVT, …)` | **枚举主因**：stale 事件全读成 `0x00000000` → SETUP 完成丢失 → GET_DESCRIPTOR 失败 |
| D4 | 0307-4：DMA 分配后 clean | patch `:56`；16.6.1 `:1770` `flush_dcache64((addr64_t)ud.dma_pa, UD_SIZE, TRUE)` | 27 `:1233` `ud.dma_pa = ptoa_64(pn)` 与 `:1236` `smmu_usb_bypass` 之间没有 flush | `KMA_ZERO` 留下的 dirty lines 回写覆盖控制器写入的 event/SETUP 数据 |
| D5 | 0308 的 restart reason recorder | 16.6.1 `:147-473`（IMEM `0x146AA000` + SPMI `0xC400000/0xC42D000/0xC440000/0xC500000`） | 27 明确丢弃：`k60_usblog_reset.c:2-11` 头注释「minus its reason recorder (decision A, 2026-11-22)」 | 不影响枚举；只影响重启后 ABL 能否回到 fastboot。该决定有书面依据，不列为缺陷 |
| D6 | 0334b 自动复位 | 16.6.1 `:1595-...` 的 `k60_autoreset_*` 段 | 27 `k60_usblog_reset.c:47-105` 完整移植（0550），`k60_autoreset`/`k60_autoreset_idle` 参数保留 | 不影响枚举 |
| D7 | 0341 `k60_usblog_console_up` | 16.6.1 `:1592-1597`；调用者 `osfmk/arm64/sleh.c:764-765`（只在 USB console running 时打印 probe） | 27 没有该函数，也没有 `us >= 4` 的导出判定（`us` 仍是文件内 static） | 不影响枚举；只影响 sleh 的诊断打印 |
| D8 | 0306/0308 的 ring snapshot | 16.6.1 `ud_console` 用 `pong_ramoops_snapshot()` 取一致快照 + quiet-loop 检测 panic | 27 改成直接读 ring + seqlock `D-2026-11-04-02`（见 `ud_console` 注释） | 不改变枚举；并发写时丢字节策略不同 |
| D9 | 0336/0339 panic report | 16.6.1 `k60_panic_report`/`k60_panic_reset_to_fastboot` | 27 没有 | 不影响枚举 |

**不属于差异的部分**：EP0 状态机（`ud_setup` 的请求表）、CDC-ACM 接口布局、`ud_console` 的 drain
语义、`ud_worker` 的 SMMU/CSFTRST/QSCRATCH 顺序，27 与 16.6.1 同源，只差 0307 与上表的诊断面。
27 的 `ud_sync()` 帮助函数存在（`:644-648`，`flush_dcache64` 在 `:647`），只是 `ud_events()` 没调用它。

## 4. 判据清单

### 4.1 现在就能跑的离线判据（不构建、不烧机）

| ID | 判据 | 命令 | 期望输出 | 不通过意味着 |
| --- | --- | --- | --- | --- |
| C1 | 27 内核含 gadget 符号 | `llvm-nm-18 <kernel>` \| `grep -E "_k60_usblog_(init|mode|start|reset_to_fastboot)$"` | 四条：`_init`/`_start`/`_reset_to_fastboot` 为 `S`，`_mode` 为本地 `d`（2026-11-24 实测） | 0547/0549 未进构建 |
| C2 | 早期探针调用点编译 | `llvm-nm-18 -u .../osfmk/DEVELOPMENT/arm_init.o` | 含 `_k60_usblog_init` | arm_init.c:726 的条件或对象过期 |
| C3 | worker 起点编译 | `llvm-nm-18 -u .../bsd/DEVELOPMENT/bsd_init.o` | 含 `_k60_usblog_start`、`_k60_autoreset_start` | bsd_init.c:1340 未编进 |
| C4 | boot-arg 进了 payload | `python3 -c 'import json;print(json.load(open("payload/payload.json"))["kernel_args"])'` | 含 `k60_usblog=2` 与 `k60_console_export=1` | 参数未传给内核 |
| C5 | worker 字符串在镜像里 | `strings -a <kernel>` \| `grep -c "K60 USBLOG"` | `51`（2026-11-24 构建实测） | 对象未链入 |
| C6 | gadget 对象自洽 | `python3 scripts/usb27/kc-surface.py object <kernel> <k60_usblog.o>` | `resolvable 19, missing 0` / `RESULT PASS` | 新内核删了某个被引用的内核函数 |
| C7 | reset 对象自洽 | 同上 `k60_usblog_reset.o` | `resolvable 7, missing 0` / `RESULT PASS` | 0550 依赖缺失 |
| C8 | `k60_console_export` 确为空转 | `ls -l .../k60_console_export.o`；`llvm-nm-18 <object>`；`strings <kernel> \| grep -c k60_console_export` | 336 B；无 `_k60_console_export_sysctl`；计数 0 | 若大于 1 KB 或出现 sysctl，说明 27 宏已修，本条结论作废 |
| C9 | 0307 全缺（四条一起判） | 在 27 源：`grep -n "ud_sync(UD_EVT"`、`grep -n "0x10c0"`、`grep -n "2, 2, 0, 64"`、`grep -n "flush_dcache64((addr64_t)ud.dma_pa"` | 四条全部无输出（exit 1） | 任一条命中 = 0307 某部分已补，D1–D4 需重算 |
| C10 | 0307 在 27 系列里没有等价补丁 | `grep -rn "ud_sync(UD_EVT\|0x10c0\|2, 2, 0, 64" /mnt/e/hackios/k60-gates/patches/xnu-12377/*.patch` | 无输出 | 若有命中，说明 27 已用别的补丁修了 |
| C11 | EP0 描述符身份 | 读 `k60_usblog.c:779-795` | 前 8 字节 `18 01 00 02 02 00 00 40`；字符串 `0x1209/0x0001` 在 `ud_dev_desc[8..11]` | 若 VID/PID 变了，主机侧判据要换 |
| C12 | 与 16.6.1 的差异规模 | `diff -u <16.6.1源> <27源>` | 18 个 `@@` hunk | 数目变化说明 27 又动过源，本表要重做 |
| C13 | 27 内核 sha 与 payload 一致 | `sha256sum kernel.macho`；`jq -r .kernel_sha256 payload/payload.json` | 都是 `7a5a603e…` | 产物不是同一构建，C1–C7 全部要重跑 |

复跑最短路径（WSL）：

```sh
P=/opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27
cd /mnt/e/hackios/k60-usb27
python3 scripts/usb27/kc-surface.py object $P/kernel/kernel.macho \
  $P/tree/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/bsd/DEVELOPMENT/k60_usblog.o
python3 scripts/usb27/kc-surface.py object $P/kernel/kernel.macho \
  $P/tree/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/bsd/DEVELOPMENT/k60_usblog_reset.o
strings -a $P/kernel/kernel.macho | grep -c "K60 USBLOG"
```

### 4.2 解冻后才可测的上机判据（全部 `unmeasured`）

**2026-11-22 起 BOOT-FREEZE state=frozen：以下 D1–D9 全部记 `unmeasured`，不是 PASS/FAIL。**
每一项的观察都在**同一次启动**的 USB CDC 输出或面板输出上做；没有通道时按 §9.3 的 INVALID 规则
（boot claim、`kernel_sha256`、≥30 s 观察窗、面板至少一行新输出）判 INVALID，不得判「USB 坏了」。

| ID | 观察 | 期望 | 判 INVALID / FAIL 的条件 | unmeasured |
| --- | --- | --- | --- | --- |
| R1 | 面板或 USB 首行 | `K60 USBLOG: worker entry` | 无 `worker entry` 且无任何 `K60 USBLOG` → 通道未起，INVALID | 是（冻结） |
| R2 | 同上 | `K60 USBLOG: UFS SMMU ready after N ms`，N ≤ 90000 | `not ready after 90 s; USB skipped` = FAIL（SMMU 前置未满足，不是枚举问题） | 是 |
| R3 | 同上 | `K60 USBLOG: running (DSTS 0x… after N ms), DMA at 0x…` | 无 `running` = FAIL，按上一行打印定位（GSNPSID / PRTCAPDIR / halt / SMMU） | 是 |
| R4 | 主机 `lsusb` / `ioreg -p IOUSB` | 出现 `1209:0001`（`K60 XNU console`） | 30 s 内不出现 = FAIL；出现 `VID_0000&PID_0002` Code 43 正是 D3 的签名 | 是 |
| R5 | `K60 USBLOG: event 0x…` | 至少一条非零事件；连接时有 `connected, speed N`、`bus reset`、`setup 80 06 …` | 只有 `event 0x00000000` 连续 8 条以上 = FAIL（D3 stale-cache 签名） | 是 |
| R6 | EP0 序列 | `setup 80 06 …`（GET_DESCRIPTOR）、`address N`、`configured (1)`、`DTR 1` 依次出现 | 停在 `setup 80 06` 后无 `address` = FAIL（EP0 data/status 未完成） | 是 |
| R7 | CDC 数据 | 主机 `/dev/ttyACM0` 或对应 COM 口收到之前所有 `K60 USBLOG` 文本；回环 `sent=64 received=64`（若测试脚本提供） | 枚举成功但零字节 = FAIL（drain 或 DTR 路径），不是 INVALID | 是 |
| R8 | Windows 绑定 | 设备管理器出现 `USB\Class_02&SubClass_02` / usbser.sys | 出现未知设备且硬件 ID 的 subclass 为 00 = D2 未修 | 是 |
| R9 | 若 R4–R7 全无但 R3 有 | — | 按 §9.3 判 INVALID（没有可用主机端口/线缆），先换线换口再判 | 是 |

## 5. 下一步（需要谁给什么）

- **Lead**：决定 0307 的四个 hunk 是否由你排进 27 的 xnu 系列（建议编号 056x，作为 0547 的后续）。
  这是 27 CDC 枚举从「0300 行为」走到 16.6.1 已验证行为的唯一必要补丁；不修的话第一次枚举预期失败。
- **Lead**：`k60_console_export=1` 可以从 27 `kernel_args` 去掉或保留（无消费者，保留无害）；
  若要它生效，需要把 `-DPONG -DXNU_PONG_RAMOOPS_CONSOLE` 加进 27 的编译（那是 16.6.1 的
  `DEVELOPMENT_ARM64_PONG` 语义，27 现在是 `DEVELOPMENT_ARM64_BCM2837`），或把 `k60_console_export.c`
  的 `#if` 改成 `defined(ARM64_BOARD_CONFIG_BCM2837)` 之类——这是决策，不是本线能改的。
- **我**（下一轮离线活）：可以把 0307 的四个 hunk 改写成 27 版补丁草案（`patches/proposed/`，不构建），
  以及把 R1–R9 的观察表并进 `usb-27-export-surface.md` §9.2。等你点名。

## 6. 参考源判定（iron-16）

| 源 | 位置 | 判定 | 理由 |
| --- | --- | --- | --- |
| 16.6.1 结案源（终版 k60_usblog.c） | `/opt/k60/trees/gates-out/mondrian/ipados-16.6.1-20G81/mondrian/tree/.cache/xnu-work/bsd/dev/k60_usblog.c:926,930,1112,1552-1560,1770` | **copied 参考**（只读行号） | 已在真机 PASS 的同一 SoC；0307 的四条修复均有日志证据 |
| 27 现源 | `.../ios27-out/.../bsd/dev/k60_usblog.c:600,604,779-795,1108-1146,1223-1233` | **本线基线** | 0547 是 0300 的移植（只去掉 PONG guard、加 `vm_kern_xnu.h`） |
| 27 reset 源 | `.../bsd/dev/k60_usblog_reset.c:2-11,21-45,47-105` | **adapted（decision A）** | 0308 的 reason recorder 被明确丢弃；0550/0551 是本板改写 |
| pong-usb | `Chengdong-Yu/pong-usb @6070a991`（经 0547 头注释引用） | **rejected as-is** | 0547 已按 K60 改写（无 UEFI handoff、无 PMIC battery），不再直接引用 |
