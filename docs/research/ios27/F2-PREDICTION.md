# F2 diagnostic flight — prediction written before the flight

Image: `/opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/boot/boot.img`
sha256 `5c060f27d7188e0d4cc41c5c6c715e8106871bbf85f5a296292b0117d817a6b6`, 201,895,936 B.
Kernel `652237c6bf54` (0 loader violations), payload transform `8ae0ab4be80a`, FD `46cc97828139`.
Written 2026-11-21 09:14, before the flight. Authorised by the user as a diagnostic flight.

## What I expect, in order

1. `112 B shim -> FD -> DarwinBoot.efi` starts; the loader now accepts the fileset collection, so this
   stage is expected to pass where round-17d was refused.
2. ADT is parsed and handed to XNU; `arm_init` runs; `PE_init_iokit()` at `osfmk/kern/startup.c:689`
   is the first moment any kext code can run.
3. The USB CDC-ACM console appears (this is the moment a human can read anything).
4. The Data gate runs; with the stamped child subtype and 16 folded data pairings, I do not expect a
   prelink trap before this point.
5. Somewhere in the kext start-up order the image hits one of the 205 stubbed slots. The expected
   signature is `_unixnu_fileset_unmapped` panicking and printing `original component called an
   unmapped kernel function from <return address>`.

## What would make this flight worth it

- **PASS (informational)**: a console log of non-zero length that reaches at least `arm_init`, and
  either proceeds past the Data gate or panics with the stub naming a call site. Either outcome
  converts unknown addresses into measured ones.
- **FAIL (real defect)**: a console log that stops before the console comes up, or a panic whose text
  is not the stub (that would be a different, fixable bug).
- **INVALID**: a 0-byte log. That means the capture or the loader failed, and it teaches us nothing
  about the residue.

## What I will not do

No `fastboot flash`, no write to `/dev/block/sda38`, no change to the image after the fact. If the
flight is INVALID I re-run once with the same image before drawing any conclusion.

## 条件四（自动复位）的上机判据（2026-11-22 加入）

镜像：`boot.img cfd0fd2d0f9db3fef4c2b376518bbe0128c27d166846b91f22a7a13dd9416fe4`
（201,900,032 B，payload 内核 `363cf8d26c87` + declared transform `7cc20ab8620e`，参数 8 项 120 B 含隐式 `k60_autoreset=300`）。

三段读数，缺一不可：

1. `k60-autoreset: armed for 300 s after 30 s idle` ⇒ 线程起来了（`0550` 被调用）；
2. `k60-autoreset: 300 s after 30 s idle; resetting` ⇒ 到点触发（时间戳应与第 1 行相差 ≥330 s）；
3. 之后 30 s 内 `fastboot devices` 能看到 `6033dbec` ⇒ PSCI `SYSTEM_RESET` 真的把设备带回 fastboot。

**如果第 1 行出现、第 2 行没出现** ⇒ 内核在 300 s 内已经死了（那就不是复位没做，而是它先崩了）；**如果第 1 行都没有** ⇒ `k60_autoreset` 参数没到内核或 `bsp_init` 没走到调用点。两种情形都不能写成「复位失败」。

## 2026-11-22 08:2x — 待飞镜像换成带色块的 `1112553c…`

`boot.img` 201,900,032 B，`sha256 1112553ced41855f05f737504349e2d6f5c9f6de79a28a257b9bcb1e95f791b6`；
payload 内核 `327bb3a5ad2d`，declared transform `7817e6332181`。镜像内核里三条字符串/符号各 1 次：
`_k60_bootbar`、`k60-bootbar: painted`、`pong-ramoops: console attached`。

四路证据的读法（互不依赖，任一条成立就够定位）：

| 现象 | 结论 |
| --- | --- |
| 8,8 处绿块 | 执行过 `arm_vm_init` 之后（含 `pong_ramoops_console_init()`） |
| 绿块后出现蓝块 | 已到 `bsd_init` 的 `k60_usblog_start()` 之后 |
| 两色块都没有 | 死在 `pe_init` 之前（或帧缓冲映射失败，日志会有 `k60-bootbar:` 行） |
| 屏幕有字（PE 控制台） | 文本通道本来就没坏，前两次 0 字节是串口侧的问题 |

色块是**覆盖式**的：它在 `8,8` 到 `72,72` 涂 64×64，不依赖字体、文本模式或行列计算。
