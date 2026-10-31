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

1. **窗口长度单调变短**（24.9 s → 5.6 s），每帧 12.4 s → 2.8 s。机器在"越跑越快"，不是冻死。
2. **驱动耗时掉了 13 倍**（39.4 ms → 2.6 ms），且 `waiting for the GPU = 0 us`、
   `0 swaps waited for the frame before / 0 gave up / 0 came a refresh late`。
   ⇒ **帧缓冲与 GPU 路径不是瓶颈**，客户端只是"不怎么来要帧"。
3. **每个窗口恰好 2 帧**（surface 12/14 交替）。这是"提交一对再等"的节奏，
   不是 60 Hz 渲染循环。
4. `tx_flush` 的 xid 仍在推进（1536 → 1662 → 1682），APFS 没有阻塞。

⇒ **这是用户态阻塞，不是显示问题。** 需要的信息是"谁在画"和"卡在哪一支二进制"。

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
| `KE <n> <pid> <comm> <path>` | **按路径 djb2 去重**：每个不同的二进制只打一行。这就是"这个启动到底跑过哪些程序"的完整清单 | 128 行 |
| `KX! <n> <pid> <comm> exit= sig= (execs N)` | **只打异常退出**（`status != 0` 或 `sig != 0`）。干净的 `exit(0)` 不占行 | 300 行 |
| `K60 ex=A kx=B abn=C` | 三个计数器（无上限），随 5 秒统计行打出，**计数器一变就打** | — |
| `K60 last exec: <pid> '<comm>' <path>` | **最后一次 exec** —— 卡住时它就是 frontier | — |
| `K60 last bad : <pid> '<comm>' exit= sig=` | **最后一次异常退出** | — |
| `MiniIOMobileFramebuffer: swap client pid N '<comm>' on swap M` | 交 swap 的进程身份（最多 8 个不同 pid） | 8 行 |

后三行反复打、且总是**最后留在屏幕上**的那几行，所以不管卡在哪，末屏就是结论。

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
  这一行直接告诉我们它是否落在 VM 即将管理的区间内 —— **在 `INSIDE` 的情况下才需要移植 0170**。

- `k60_capmanaged=1` 才把 `mem_size`/`gPhysSize` 收敛到 `mem_actual`
  （等价于同族 `0172` 的 PONG 版）。注意只动 `mem_size`，
  **不动 `real_phys_size`**，所以 `phystokv()` 的 physmap 覆盖范围保持不变。

## 4. 已经拿到的一个硬数字：用户态其实很忙

首次上机（0235 v1）读到：

```
K60STAT execs=601 exits=400
```

两个上限都被打满，所以只能得出**下界**：**至少 601 次 exec、400 次进程退出**。
`ex - kx ≈ 200`，即此刻大约有 **200 个进程活着** —— 这是相当正常的一支 iOS 守护进程population，
**不是"什么都起不来"，也不是"集体崩溃循环"**。

推论：卡点不是"没有用户态"，而是**某一个具体的等待没被满足**。
v2 的 `KE`（按路径去重的完整清单，≤128 行）会直接回答：
`SpringBoard` / `backboardd` / `runningboardd` / `launchservicesd` / `Setup` / `purplebuddy`
到底有没有出现过；`KX!` 会回答谁被杀、被什么信号杀。

> 关于"KX 数字倒退"：计数器本身是只增的 `unsigned int`，代码上不可能倒退。
> 能造成"看起来倒退"的只有三种：① 屏幕滚动太快看错；② 控制台与 UI 抢同一块
> framebuffer 导致局部重绘/丢字（已实测到 `xid`→`xld`）；③ **内核真的 panic 重启了**，
> 那计数器会从 1 重新开始。三者在 v1 的输出里都分辨不出来 —— 这正是 v2 要解决的：
> 1) `KE` 与 `KX!` 前缀不同、各自独立的序号；2) `K60 ex= kx= abn=` 反复打且总在末屏；
> 3) 若真重启，`ex`/`kx` 会回到很小的数并伴随 UEFI/内核横幅重新出现。
> **在拿到 v2 的输出之前不对"倒退"下任何结论。**

## 5. ADT `/chosen` 身份（本轮已改）

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

⇒ **"缺渲染器/缺显示模式"这条基本可以排除。**

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

> `boot-trace2.img` 相对 `boot-wifi.img` 的 delta：**0235 v1→v2（追踪形状）** + **0236 v1→v2
> （多一行面板帧缓冲判定 + 一个默认关闭的内存上限开关）**。ADT 的**配置**完全相同；
> `adt_sha256` 每次构建都变，只是因为 `random-seed` / `boot-epoch` / nvram nonce 每次重新随机。

### 万一还是不够：下一颗可以加的东西（按价值排序）

1. 若 v2 的 `KE` 清单显示某支二进制**从未 exec** → 直接去查它为什么没被 launchd 排上
   （`disabled.plist` / job 缺失 / 上一次依赖失败），不需要再加探针。
2. 若 `KE` 清单完整但某进程**只 exec 不画** → 需要"谁在等什么"。那时加的是
   `stackshot`：XNU 自带 `bsd/kern/stackshot.c` 的 `stack_snapshot()`，
   由 MFB 统计线程在"连续 N 秒没有 swap"时触发一次，把全部线程栈落到 `dmar`/缓冲区。
3. 若确实存在重启 → 加一个**在 UEFI 前打不出来的开机序号**（由 payload 的
   `--kernel-arg k60_build=<tag>` 传，内核对不上就 panic），把重启变成不可否认的证据。

## 9. 下一步（严格一次一个变量）

1. **`boot-trace2.img` 已在跑（13:21 刷入）**。等它停住，拍**最后那一屏**。要找的五样：
   - `K60 ex=<A> kx=<B> abn=<C>` —— A 不再涨 = 彻底停住；若 A 回到很小的数 = **内核真的重启了**；
   - `K60 last exec: <pid> '<comm>' <path>` —— 最后一次 exec，这就是 frontier；
   - `K60 last bad : <pid> '<comm>' exit= sig=` —— 最后一次异常退出，`sig=9` 是 SIGKILL、
     `sig=6` 是 SIGABRT（多半是 C++ 异常或 assert）；
   - `KE ...` 清单里有没有 `SpringBoard` / `backboardd` / `runningboardd` / `Setup`；
   - **`K60 MEM:` 与 `K60 FB :` 两行**（应该出现在启动早期）。
2. 按这两行分派：
   - `K60 MEM: ... (cap available)` → 重建 payload+bootimg 时加 `--kernel-arg k60_capmanaged=1`
     （**不用重编内核**）→ `boot-cap.img`，单独看进展。
   - `K60 FB : ... -> INSIDE managed range` → 移植 0170：在 `vm_page_release_startup` /
     pmap 启动路径里把那一段物理页标记为"留在数组里但不上空闲队列"，
     **PONG 版、区间取自 `args->Video`**，不再硬编码 `0xb8000000`。
   - 两个都 `no cap` / `outside` → 排除这两条，转 `KE` 清单里"哪支二进制从没出现"的方向。
3. 触摸仍卡在 RSC 块不可访问（同族先例 `LOCKSCREEN-2026-10-28.md:30-40`），
   与当前卡点无关，暂不动。
