# route-a-18 状态（2026-11-01 round 27）

> 完整背景见 `ROUTE-A-18-HANDOFF-2026-11-01.md`。本文只记"现在在哪、下一步做什么"。

## 一句话

darwin24 内核**已经在 Linux 上完整构建并通过四道校验**；加载器 `boot_args` ABI 已从
Darwin 22 修正为 Darwin 24；最后一次上机**屏幕出现绿条**（证明 loader 跳板确实跳进了内核），
但内核仍**静默复位**。当前最大障碍是**观测盲区**——不是缺补丁，是看不见。

## 已完成（不要重做）

1. **平台层**：`libArmDTPlatform.a`(27,808 B) + `libArmCpu.a`(34,600 B) 针对 darwin24 构建成功，
   已用 `-Wl,-force_load` 链进内核。内核 20,848,416 → **20,872,376 B**
   （`2f485593…`）。`LC_SYMTAB` 206,179 符号，`ArmDTPlatform` 全部方法表在核内。
2. **`boot_args` ABI**：`BootArgs.h` 从 Darwin 22（`0x2e0`/608）改为 Darwin 24
   （`0x480`/1024，`BootFlags 0x470`、`MemorySizeActual 0x478`）。编译期断言全过；
   `DarwinBoot.obj` 含 `0x480 ×3`；FD 内 `0x2e0` 出现 **0 次**。
3. **loader 身份确认**：`Entry.S` 与 pong `DarwinBoot24` **sha256 完全一致**；
   `DarwinBoot.c` 只差 QR 调试行/前缀/ABI 字符串。→ 除 `BootArgs.h` 外我们本来就是 pong 的 loader。
4. **镜像布局已解析**：`ANDROID!`@0；偏移 4096 = gzip(FD) 547,073 B + `hardware.dtb` 1,862 B
   = kernel_size 548,935；payload@557,056；总 201,887,744 B；FD 前有 112 B BootShim（`ARMd`@+56）。

## 已排除

| 假设 | 依据 |
|---|---|
| 入口点错误 | 我们 darwin24 入口字与**能启动的** darwin22 **逐字节相同** |
| `boot_args` 结构体（xnu 侧）变了 | xnu-8796 与 xnu-11417 的 `struct boot_args` / `Boot_Video` 完全相同 |
| `start.s:756` 的 `bne .` 自旋 | PONG 是 `NO_MONITOR=1`（KTRR 关）→ 宏只 `msr` 不改 x0 → `cmp x0,x1` 恒等 |
| `start.s:568` 的 `bne .` | 由 `tbz w1,#0x1f` 保护，非 kext 内核会跳过 |
| 缺视频控制台驱动 | pong 驱动树只有 5 个驱动，本来就没有；`pong_display` 全树无读者 |

## 当前卡点

最后一次刷的是 `boot-darwin24-abi24.img`（`c249c547…`）。现象：

```
entry words 140006EF 00000000 00000000 00000000
HANDOFF EXIT RETURN 00000000000000803518
owned trampoline pa 0xC84F8000 (196 bytes)
Exiting boot services…
SecurityLock::LockType: SOFTWARE_LOCK …
```
**+ 屏幕上方一条绿条。** 绿条由 `Entry.S` 在关 MMU 之前绘制，`br x1` 跳 PA `0xC74C04A0`。
→ 内核入口已到达，之后静默死亡。

**盲区**：ramoops 控制台在 `arm_vm_init()` **之后**才初始化，所以那之前死亡全静默。

## 2026-11-01 03:45 面包屑结果：死点 = ml_parse_cpu_topology()

三列共 13 个色块（`0244` 的 FB 标记，见下）实测：左列 6 个、右列 0 个、第三列 1 个。
→ 依次排除入口、页表、开 MMU、`arm_init()`、`PE_init_platform`（含 ArmDTPlatform /
ADT 解析），死点落在 `arm_init.c` 里 `ml_parse_cpu_topology()` 内部。

**根因假设（高置信）**：`sm8475.dtsi` 给 8 个 CPU 的 `reg` 是 `0x000,0x100,…0x700`，
`MPIDR_CLUSTER_ID(reg)` 于是得到 **8 个物理簇**；而 `ml_parse_cpu_topology()` 里

```c
assert(phys_cluster_id <= MAX_CPU_CLUSTER_PHY_ID);
assert(topology_info.num_clusters < MAX_CPU_CLUSTERS);   // 非 Apple 板配置普遍 = 2
```

从第 3 个核起断言失败 → `panic()` → 此时控制台还不存在 → 静默挂死。
16.6.1 用的 Apple kernelcache 是 RELEASE，`assert` 被编掉，所以同一个 ADT 能过；
我们从源码编的是 DEVELOPMENT，断言活着。

**待定**：`reg` 到底该是扁平 `0x0..0x7`（一簇）还是真实 3 簇（`0x0-0x3 / 0x100-0x102 / 0x200`）。
两者都要求 `MAX_CPU_CLUSTERS` ≥ 实际簇数；扁平值还要求硬件 MPIDR 也扁平，
否则 `ml_get_cpu_number(MPIDR)` 在副核启动阶段会算错索引。

## 待查（优先）

1. **prelink 缺口（2026-11-01 新发现）**：内核 `__PRELINK_TEXT / __PRELINK_INFO /
   __PRELINK_DATA / __PLK_*` 六段 size 全 0（能启动的 20G81 内核是
   `0x714000 / 0x71000 / 0x158000`）。darwin24 路线没有 OS profile，`unixnu build kernel`
   的 prelink 步骤被整个绕过。22H374 kernelcache 已解密完整（`__PRELINK_INFO` 明文 XML、
   852 个 kext），可用 `kits/XnuPrelink` 在 Linux 补，`slide = -0x112C000`。
2. **可观测性**：`start.s` M00–M03 + `arm_init.c` M04–M07，统一写 PA `0xA73FF000`
   （4 MiB carveout 最后一页）。需在 bootstrap 页表补 2 MiB Device 块
   （`0xA7200000`，`0x00400000A720040D`）。帧缓冲 `0xB8000000` 与 ramoops `0xA7000000`
   **都不在** bootstrap 映射内，开 MMU 后直写必 data abort。
3. 越过 `arm_vm_init` 后读 ramoops carveout（K60 基址 `0xA7000000`），看 `PONG DIAGNOSTIC v92`。

## 待查（已作废，别再查）

- ~~`hardware.dtb` 缺 `/chosen` `/arm-io` `/defaults` `/options` 导致 `configure()` 失败~~
  → **不成立**。XNU 读的是 payload 里的 `Payloads/kernel.macho.adt`（14,672 B，
  `78f8ecd0…`，五节点齐全），boot.img 尾部的 1862 B DTB 没有消费者；
  20G81 用同一份 DTB 启动到 SpringBoard。详见 HANDOFF §7。

## 未刷的产物

`boot-darwin24-bc1.img`（2026-11-01，`eb7d2be9…`，201,887,744 B）= **面包屑 + prelink 同镜**：

| 层 | 内容 | 大小 / sha256 |
|---|---|---|
| kernel 槽 | BootShim(112 B) + `SILICIUM_UEFI.fd` | FD `a8a6f79c…`（与上一次刷的完全一样，loader 未改） |
| 追加 DTB | `hardware.dtb` | 1,862 B，`8b8618…`（未变） |
| payload | `payload.img` | 201,326,592 B，`6a134fe8…` |
| payload 内内核 | `Payloads/kernel.macho` | **54,808,576 B**，`be549abb…` |
| payload 内 ADT | `Payloads/kernel.macho.adt` | 14,672 B，`5dc18cf9…`（与旧 ADT 只差 `/chosen/random-seed` 64 B） |

上一版 `boot-darwin24-abi24b.img`（`6796e147…`）已作废：只有 ABI 标签差异，不含这两项。

### 这一版改了什么

1. **prelink 补上**：`__PRELINK_TEXT` `0x7a8000`、`__PRELINK_INFO` `0x31000`，
   15 个组件（5 个 root + 依赖）。`AppleARMPlatform` / `AppleARMWatchdogTimer` /
   `AppleEffaceableStorage` 走 `library_only_components`：代码保留、`IOKitPersonalities` 删掉，
   以免 `AppleARMPE` 抢我们 `-force_load` 的 `ArmDTPlatform`、看门狗被挂上。
   复现：`python3 scripts/k60-prelink-darwin24.py`（slide 写死 `-0x112C000`）。
2. **面包屑**：`patches/xnu-ipados18/0244-k60-breadcrumbs.patch`，8 个槽写 `0xA73FF000`。
3. **入口 PA 变了**：prelink 后内核 Base 从 `0xfffffff007004000` 降到 `0xfffffff004004000`，
   loader 落位 `0xC7004000`，入口 PA 从 `0xC74C04A0` 变成 **`0xCA4C84A0`**。
   旧文档/脚本里 grep 到 `0xC74C04A0` 的是历史日志，别当成本次预期值。

### 校验（已过，`scripts/verify-boot-img-payload.py`）

kernel 槽 = shim + FD；ramdisk 槽逐字节等于 `payload.img`；payload 内 `kernel.macho` 逐字节等于
新内核；`payload.json` 的 `kernel_sha256` / `adt_sha256` 与卷内一致。

## 设备/安全

只 `fastboot boot`；绝不 flash boot/persist/modemst*/Android userdata；可写 `unixnu` 分区；
串号 `6033dbec`。设备目前 adb/fastboot 均无响应。
