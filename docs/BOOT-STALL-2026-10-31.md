# 启动进度条卡死 —— 现状、证据、下一步（2026-10-31）

本文只记**实测证据**，推断一律标 `[推断]`。镜像全部用 `fastboot boot`，不 flash 任何分区。

## 1. 症状

屏幕上出现 iOS 启动进度条（无 Apple logo），**会往前走一小段，然后停住不再动**。
控制台文本仍在偶尔滚动，内容几乎全是 `MiniIOMobileFramebuffer: ...` 的 5 秒统计行。

## 2. 帧统计的定量结论（这是本轮最硬的一条）

`MiniIOMobileFramebuffer` 的 5 秒统计行格式：

```
MiniIOMobileFramebuffer: <N> frames in <ms> ms (<x> a second), <us> us each in the driver,
  after <us> us waiting for the GPU and, <k> of them, <us> us for the next refresh;
  <a> swaps waited for the frame before, <b> gave up; <c> swaps came a refresh late themselves
```

关键实现细节：`fStatFrames` / `fStatSince` / `fStatDrawing` 都是**打完就清零**的窗口量
（`iokit/Kernel/MiniIOMobileFramebuffer.cpp`，`nanos >= 5 * NSEC_PER_SEC` 处）。

现场实测六个连续窗口：

| 窗口 | `frames` | 窗口长度 | 每帧 | 驱动耗时/帧 |
| --- | --- | --- | --- | --- |
| 1 | 2 | 24895 ms | 12.4 s | 36654 µs |
| 2 | 2 | 10191 ms | 5.1 s | 38139 µs |
| 3 | 2 | 11968 ms | 6.0 s | 39402 µs |
| 4 | 2 | 12053 ms | 6.0 s | 3412 µs |
| 5 | 2 | 7319 ms | 3.7 s | 2589 µs |
| 6 | 2 | 5597 ms | 2.8 s | 2898 µs |

四条结论：

1. 窗口长度有波动（24.9 / 10.2 / 12.0 / 12.1 / 7.3 / 5.6 s），末窗短于首窗；这些窗口内仍有帧提交，但不能据此断言启动持续改善。
2. **驱动耗时掉了 13 倍**（39.4 ms → 2.6 ms），且 `waiting for the GPU = 0 us`、
   `0 swaps waited for the frame before / 0 gave up / 0 came a refresh late`。
   ⇒ 已计量的驱动时间和 GPU 等待远短于帧间停顿，优先检查提交前的用户态路径；尚未排除其他显示路径问题。
3. 每个统计窗口为 2 帧，surface 12/14 交替。统计窗口在绘制时触发、首帧开始计时；不能将这一点解释为客户端刻意成对提交。
4. `tx_flush` 的 xid 仍在推进（1536 → 1662 → 1682），证明有事务完成；这几行本身不足以证明所有 APFS 调用均无阻塞。

优先检查用户态的启动、终止原因和等待路径；仅凭帧统计不能给出最终根因。

### 已知的观测陷阱

- 每 swap 的详细日志由 `report = fSwapsShown < 8` 限制在**头 8 帧**
  （`MiniIOMobileFramebuffer.cpp:920`）。"swap 行停在 8"是设计使然，**不是卡死证据**；
  判存活只能看 5 秒统计行。
- 屏幕上的裸数字（如 `83`）**不是进度百分比**。
- 控制台文本有像素级丢字（`xid` 被画成 `xld`、`surfaces` 被画成 `urfac s`），
  说明内核控制台与 UI 在抢同一块 framebuffer。属观感问题。

## 3. 本轮新增的探针（0235 / 0236）

### 0235 `k60-exec-exit-trace`（v2，已构建）

**v1 的教训**：v1 把 exec 上限设成 600、exit 上限设成 400，现场实测
`K60STAT execs=601 exits=400` —— **两个上限都被打满，最有价值的尾巴全被丢掉了**。
所以 v2 改成"冻结屏幕自己会说话"的三个形状：

| 输出 | 含义 | 上限 |
| --- | --- | --- |
| `KE <n> <pid> <comm> <path>` | 按路径哈希去重的 exec 尝试样本；不保证完整或已加载成功 | 128 行 |
| `KX! <n> <pid> <comm> exit= sig= (execs N)` | **只打异常退出**（`status != 0` 或 `sig != 0`）。干净的 `exit(0)` 不占行 | 300 行 |
| `K60 ex=A kx=B abn=C` | 三个计数器（无上限），随 5 秒统计行打出，**计数器一变就打** | — |
| `K60 last exec: <pid> '<comm>' <path>` | 最近 exec 尝试摘要（字段可能并发混合），不能直接判定阻塞位置 | — |
| `K60 last bad : <pid> '<comm>' exit= sig=` | **最后一次异常退出** | — |
| `MiniIOMobileFramebuffer: swap client pid N '<comm>' on swap M` | 交 swap 的进程身份（最多 8 个不同 pid） | 8 行 |

摘要随绘制统计触发，且只有计数变化时打印；完全停止绘制时不再更新。共享字段尚未同步，末屏提供排查线索，不能直接作为根因结论。

实现要点：

- `KE` 打在 `bsd/kern/kern_exec.c` 的 `exec_activate_image()` 里
  `DTRACE_PROC1(exec, uintptr_t, excpath)` 之后 —— 此时 `excpath` 是已经 `copyin` 好的路径。
  注意 `posix_spawn` 路径下 `p` 是**父进程**（launchd），所以进程名不可靠，**路径才是判据**。
- `KX!` 打在 `bsd/kern/kern_exit.c` 的 `exit_with_reason()` 里 `p->p_xstat = rv;` 之后。
  `rv` 已是 `W_EXITCODE` 形式：`(rv >> 8) & 0xff` = 退出码，`rv & 0x7f` = 信号号。
- 客户端身份用 `current_proc()->p_pid` + `p_comm`。
  注意：**IOKit 里不能调 `proc_getpid()`**（内核不导出 `__Z11proc_getpidP4proc`，
  链接会失败 `Undefined symbols`）。必须直接读 `p_pid`。
- 跨文件共享靠 `extern` 声明 + 在 `kern_exec.c` 里定义；`strlcpy` 可用。

### 0236 `k60-managed-memory-and-panel`（v2，已构建）

**默认完全只读**：不打任何 boot-arg 时它只打两行、不改任何值。第三段改动挂在
`k60_capmanaged` 上，所以"量"和"试"可以是同一颗镜像 —— 换 boot-arg 只要重建
payload+bootimg（约 1 分钟），**不必重编内核**。

```
K60 MEM: memSize <A> MiB, memSizeActual <B> MiB (cap available|no cap), physBase 0x.. physSize 0x..
K60 FB : base 0x.. <w>x<h> depth 0x.. stride <n> bytes 0x.. end 0x.. -> INSIDE|outside managed range
```

- `K60 MEM:` 判定的问题：`osfmk/arm64/arm_vm_init.c` 里

  ```c
  gPhysSize = mem_size = ((gPhysBase + args->memSize) & ~PAGE_MASK) - gPhysBase;
  mem_actual = args->memSizeActual ? args->memSizeActual : mem_size;   /* 只用来算 max_mem_actual */
  ```

  `mem_actual` **不会**收敛 `mem_size`。同族 K60 分支的现场是
  `memSize=0x4c000000`(1216 MiB) / `memActual=0x2bf00000`(703 MiB)，
  结论是"多出来的 RAM 有一截是 XPU 拒绝解码的，第一次在上面分配就**整机死、
  无 panic、无控制台输出**"（`FORECAST-K60-IOS.md:573-578`）。
  我们这边的两个数是多少，就是这一行要回答的。

- `K60 FB :` 判定的问题：同族补丁 `0170` 的注释说，ABL 显示控制器一直在扫面板缓冲
  （他们那边是 `0xb8000000-0xb9200000`），那些页只要进了用户映射或页表就会被
  控制台文字覆盖，**表现为"条纹屏 + 随机的 PTE/pthread/heap 损坏"**；
  正确做法是页照常留在 `vm_page` 数组里、只是**永远不上空闲队列**
  （在数组里挖洞会触发 `vm_page_init` 的断言）。我们这边面板帧缓冲的物理范围
  是 `boot_args->Video.v_baseAddr`（`boot_args` 在 `arm_vm_init` 里就是现成的 `args`），
  这一行只比较地址区间；即使是 `INSIDE`，仍需验证该区间是否已经通过其他路径保留，不能据此直接断言需要移植 0170。

- `k60_capmanaged=1` 才把 `mem_size`/`gPhysSize` 收敛到 `mem_actual`
  （等价于同族 `0172` 的 PONG 版）。注意只动 `mem_size`，
  **不动 `real_phys_size`**，所以 `phystokv()` 的 physmap 覆盖范围保持不变。

## 4. 计数与 SIGKILL：已证实的事实及观测限制

v1 输出 `K60STAT execs=601 exits=400` 仅表明两个计数均达到记录上限，**不能相减推算
存活进程数，也不能据此排除反复启动/终止**。

v2 的用户实录包含：

```
K60 ex=680 kx=292 abn=267
K60 last bad : 339 'contextstored' exit=0 sig=9
KX! 268 343 ptpd exit=0 sig=9 (execs 680)
KX! 269 315 mediaserverd exit=0 sig=9 (execs 681)
K60 ex=707 kx=295 abn=270
```

此外还有 usermanagerd、mobiletimerd、coreduetd、powerd 等 `sig=9` 记录。
这能确认多进程被 SIGKILL 终止、启动活动仍继续；**信号号本身不能判断发起者或原因**。
应区分 jetsam（其中也包括正常 idle-exit）、用户态主动终止、签名/执行策略等路径。

0235 当前实现的限制：

- `ex` 在 `exec_activate_image()` 路径复制后、加载成功前递增，是 exec 尝试数；
  一个进程也可能经历多次 exec（例如 xpcproxy），所以 `ex-kx` 不是存活进程数。
- 三个计数器使用非原子的 `++`，多个 CPU 的写入可能丢失或被观察到乱序；打印也可能交错。
  因此撤回“代码上不可能倒退”及“仅由计数即可认定重启”的表述。
- `last exec`/`last bad` 的 PID、comm、path、信号分别写入，没有快照锁；字段可能混合，
  不能把最后一行当作已证实的阻塞点。用户也已明确“倒退”可能是看错，目前无重启结论。
- `KE` 只有至多 128 个路径哈希样本，还可能哈希碰撞；没有出现不代表没有尝试执行。
- `KX!` 只输出前 300 次异常退出；后续全局计数仍变化，但该行不会无限打印。

只读代码核对显示 `exit_with_reason()` 在提交 `p->p_exit_reason` 后仍持有目标进程锁，
现有 `KX!` 附近可读取 reason 的 namespace/code/flags，并记录 `jetsam_flags` 参数。
下一颗归因镜像应从这里取得原因，而非从 `SIGKILL` 或当前执行上下文猜测来源。

### 0237：默认关闭 K60WATCH

`K60WATCH` 是 `k60_var_watch()` 的周期 keybag/AKS 状态探针，每 2 秒一次、最多 90 次，
不是 watchdogd。0237 保留该诊断函数，但将 worker 的启动改为显式 opt-in：

```
int k60_watch_enabled = 0;
PE_parse_boot_argn("k60_watch", &k60_watch_enabled, sizeof(k60_watch_enabled));
if (k60_watch_enabled == 1 && kernel_thread_start(...) == KERN_SUCCESS) { ... }
```

默认既不启动该线程，也不执行周期目录查询。仅 `k60_watch=1` 恢复旧探针。
keybag 初始化、watchdog 策略、0235/0236 探针和启动参数其余部分保持相同。
本次镜像 `boot-nowatch.img` 已完成：

- 完整内核构建和补丁应用通过；默认值为 0，线程启动有显式 `== 1` 条件。
- 从最终启动镜像提取 FAT，再提取实际 kernel/ADT/unixnu.toml；新内核哈希一致、
  启动参数无 `k60_watch=1`，ADT 的 MAC、8 字节 unique-chip-id 和 4 字节 chip-id 校验通过。
- 独立 boot v4/UEFI/DTB/FAT 内容校验 `RESULT == PASS`。
- `fastboot -s 6033dbec boot boot-nowatch.img` 已返回 Sending OKAY / Booting OKAY / exit=0。
  这证明加载器接受镜像；手机屏幕上的启动结果尚待观察，不能写成 UI 已修复。

校验值：kernel SHA-256 `6c5585287185161efc84730dd38990ce7746d29f106491cdf689c04ec5e6281d`，
image SHA-256 `5ece69443b55b4099eca39e0a05b2151bafea0d5caeca3f9c7bf266fdcea8c7b`。

## 5. ADT `/chosen` 身份（沿用既有配置）

ADT 由 `tree/scripts/unixnu/devicetree.py::generate()` 生成，配置来自
`profiles/arch/arm64` → `soc.toml` → `profiles/os/ipados-16.6.1-20G81/profile.toml` → **本仓 `board.toml`**
四层深合并，`board.toml` 最后合并、优先级最高。`generate()` 里
`chosen += typed_properties(platform.get('chosen', {}))`，所以 `board.toml` 的
`[adt."chosen"."bytes"]` / `[adt."chosen"."u32"]` 会直接进 ADT。

本仓 `board.toml` 新增：

```toml
[adt."chosen"."bytes"]
"mac-address-wifi0" = "525400123456"      # 52:54:00:12:34:56，本地管理/单播
```

`[payload."adt"]` 新增 `"chip_id" = "8015"`；构建时另加 `--unique-chip-id 4B36305400000001`
（`unique-chip-id` 只从 CLI/`UNIXNU_UNIQUE_CHIP_ID` 进来，ADT 里不存 seed）。

理由（都来自**同一台机器**、已进过锁屏的分支）：

- `/chosen/mac-address-wifi0`：`refs/ios-sweet-k60/docs/REBUILD-FROM-SCRATCH.md:41-42` ——
  "没有它 **lsd 建库时会卡在 MobileGestalt 的网络匹配通知上**"。
  这是一个**用户态 hang**，和当前的症状同一类。
- `/chosen/unique-chip-id` + `/chosen/chip-id`：`refs/ios-sweet-k60/NOTES.md:77` ——
  "On arm XNU publishes IOPlatformUUID (gethostuuid) only from `/chosen/unique-chip-id` (8 bytes)
  + `/chosen/chip-id` (4 bytes) ... so **every CurrentHost preference write failed**"。
  没有 IOPlatformUUID，DataMigration 永远记不下 `LastSystemVersion`，
  而 backboardd 会在 `-[BKSSystemShellService _checkIn]` 里扣住 SpringBoard
  直到 `DMPerformMigrationIfNeeded` 返回（`NOTES.md:81`）。

**校验方式**（不依赖 `unixnu bootimg`）：直接对 `payload.img` 做字节搜。
改前 `mac-address-wifi0` = `-1`，改后 = `54669436`，6 字节 MAC 值 `52 54 00 12 34 56` 在 `54669472`，
`unique-chip-id` 在 `54668968`，seed 小端 `01 00 00 00 54 30 36 4B` 在 `54669004`。

## 6. 同机先例：`refs/ios-sweet-k60`

`refs/ios-sweet-k60/docs/LOCKSCREEN-2026-10-28.md`：**同一台 K60（mondrian/SM8475）已经进过锁屏**
（iOS 16.7.16，HFSX 可写根写在 `userdata`），判据是"进度条走完后出现锁屏"。

它给出的"CoreAnimation 一帧也不提交"的四个必要条件，逐条对我们核对：

| 条件 | 我们 |
| --- | --- |
| 画布按面板原生 1440×3200 报 | ✅ `0210-k60-display-native-canvas`；实测 swap 已是 `1440x3200 BGRA` |
| `AppleCLCD` 发布 `TimingElements` / `ColorElements` | ✅ `MiniIOMobileFramebuffer.cpp:363-365` |
| `GetID` 返回 1；实现选择器 77 / 79（`GetBlock(0x40)`） | ✅ `kFBDisplayID 1`（`:320`）、`:1285`、`:1387` |
| 发布一个空 `IOAcceleratorES` | ✅ `0212-k60-empty-accelerator`，`XNU_K60_ACCEL_STUB` 默认 1 |

这些代码路径已存在，不能仅以服务或属性存在就认定实际渲染与用户态 ABI 均正确。

## 7. 0170 / 0172 的适用性判定

两条都在 `D:\Android\k60-ios\ios-sweet-k60\xnu\patches\`，本次实测：

```
0170-k60-panel-buffer-out-of-vm.patch   (osfmk/vm/vm_resident.c, osfmk/vm/vm_shared_region.c)
0172-k60-cap-managed-ram.patch          (osfmk/arm64/arm_vm_init.c)
git apply --check  →  FAIL（两个都失败）
git apply --3way   →  FAIL
```

**关键**：`0172` 的全部改动包在 `#if defined(ARM64_BOARD_CONFIG_SWEET)` 里，
即使强行打上去，对 PONG 板也是**空操作**。要生效必须重写成 PONG 版本。
我们树上对应的锚点已经在同一位置（`arm_vm_init.c`）：

```c
mem_actual = args->memSizeActual ? args->memSizeActual : mem_size;

if ((memory_size != 0) && (mem_size > memory_size)) {
```

所以正确做法是用 0236 先量出 `memSize` / `memSizeActual`，再决定要不要写
`0236b` 去收敛。**在量出来之前不动 VM 尺寸**（改 VM 尺寸爆炸半径太大）。

## 8. 镜像台账

| 镜像 | 时间 | kernel | 内容 | 结果 |
| --- | --- | --- | --- | --- |
| `boot-fixed.img` | 04:49 | `40871b93` | 平台库重链修复 + 0214 | 存活 ~5 h，日志可读 |
| `boot-gpu.img` | 09:48 | `b5dea24f` | + PongAdreno 链接 | — |
| `boot-selector.img` | 10:02 | `063a1408` | + 0233 selector 兜底 | UI 起，进度条间歇 |
| `boot-noexc.img` | 10:43 | — | 实验无效（0230 是源码补丁） | 废 |
| `boot-prefs.img` | 11:32 | `223bdf74` | + 0234 偏好种子 | 进度条走一小段后停住 |
| `boot-trace.img` | 12:17 | `5d1c13d3` | + 0235 v1 追踪 | 已刷；读到 `execs=601 exits=400`（两个上限打满） |
| `boot-wifi.img` | 12:39 | `5d1c13d3` | + `/chosen` 三条身份（**delta 仅 ADT**） | 已刷 12:41 |
| `boot-mem.img` | 12:47 | `d47a65fe` | + 0236 v1 内存报数 | 被下面这颗取代 |
| **`boot-trace2.img`** | **13:20** | **`27e06e64`** | **0235 v2 去重追踪 + 0236 v2（内存 + 面板帧缓冲报数 + `k60_capmanaged` 开关）+ `/chosen` 三条** | **已刷 13:21，正在跑** |
| `boot-nowatch.img` | 0237 | `6c558528` | K60WATCH worker 默认关闭；其余启动配置沿用 trace2 | 构建、提取校验、fastboot 临时引导成功；屏幕结果待观察 |

> `boot-trace2.img` 相对 `boot-wifi.img` 的 delta：**0235 v1→v2（追踪形状）** + **0236 v1→v2
> （多一行面板帧缓冲判定 + 一个默认关闭的内存上限开关）**。ADT 的**配置**完全相同；
> `adt_sha256` 每次构建都变，只是因为 `random-seed` / `boot-epoch` / nvram nonce 每次重新随机。

### 退出原因诊断：代码核对结论（尚未加入本次镜像）

- `exit_with_reason()` 在提交 `p->p_exit_reason` 后仍持有目标进程锁，可在现有退出日志
  附近 NULL 检查后读取 namespace/code/flags，同时记录 `jetsam_flags` 参数。
- jetsam 有直接调用 `exit_with_reason()` 的路径，绕过 `psignal()`。namespace 为
  JETSAM 也不自动等于内存不足：其中包含 idle-exit、CPU limit 等原因，需要结合 code。
- 多条安全/终止策略也发送不带专用 reason 的 SIGKILL，最终可能仅显示 SIGNAL/9；
  所以 SIGNAL/9 不能排除代码签名，也不能证明是普通用户态 kill 请求。
- `psignal()` 时的 `current_proc()` 只能称为执行上下文 ctx，不能直接称为原始发送者。
  若需确证用户态请求，应在实际 kill/group-kill/terminate syscall 点记录请求者和目标。
- `proc_exit()` 的 `!P_LEXIT` 兜底路径不经过现有 `KX!`；只加 psignal 或 KX 字段都不完整。
  后续应单独覆盖这条路径，且保持日志有界。

## 9. 下一步

1. 校验并临时引导 `boot-nowatch.img`，确认 K60WATCH 默认不再刷屏。
2. 单独增加退出原因诊断，记录 reason namespace/code/flags 与 jetsam_flags。
   对 reason 为 SIGNAL 的路径，才进一步记录实际用户态请求或内核调用点。
3. 内存与面板报告只用于筛查：`cap available` 不证明内存范围错误，`INSIDE` 不证明帧缓冲
   已进入空闲队列；必须核对 loader 内存契约与实际保留页逻辑后，才决定启用 cap 或移植 0170。
4. 参考分支使用另一套 loader、iOS 版本和 HFSX 布局。本项目继续使用独立 unixnu 分区的
   APFS OS/Data 窗口；不因参考实现而改写 Android userdata 或改换根文件系统。
