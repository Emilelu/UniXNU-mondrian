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

## 待查（优先）

1. **`hardware.dtb` vs 生成 ADT**：镜像里追加的是原始 `hardware.dtb`（1,862 B，14 节点），
   缺 `/chosen`、`/arm-io`、`/defaults`、`/options`——正是 `ArmDTPlatform::configure()` 声明必需的四项。
   `unixnu bootimg --dtb` 只做 `patch_dtb()`，**不调用 `devicetree.generate()`**。
   payload 里 `adt_sha256 = 78f8ecd0…` 但 `adt.bin` 不存在。
2. **可观测性**：在 `start.s` 的 `_start` 加不依赖 MMU 的面包屑（`x20` = boot_args PA，
   `Video[]`@+0x28，`v_rowBytes`@+0x38）；bootstrap 页表含 V=P 块映射，开 MMU 后仍可用 PA 访问。
   或直接在 `arm_init` 开头往 PA `0xA7000000` 写标记，之后从 Android root `dd if=/dev/mem` 读回。
3. 越过 `arm_vm_init` 后读 ramoops carveout（K60 基址 `0xA7000000`），看 `PONG DIAGNOSTIC v92`。

## 未刷的产物

`boot-darwin24-abi24b.img`（`6796e147…`）已构建并四道校验通过，只差刷入；
与已刷版本的唯一区别是两处 ABI 标签字符串改为 "Darwin 24"。

## 设备/安全

只 `fastboot boot`；绝不 flash boot/persist/modemst*/Android userdata；可写 `unixnu` 分区；
串号 `6033dbec`。设备目前 adb/fastboot 均无响应。
