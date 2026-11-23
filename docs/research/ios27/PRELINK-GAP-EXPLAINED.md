# prelink 残留差额：我们 94/203 对上游 2/24

日期 2026-11-23。只读分析，未构建。

## 两边数的是不同构建

| | 上游 policy | 我们的 record |
| --- | --- | --- |
| 依据 | `kernelcache_sha256 = 38e6d9fa…`（Apple 24A446 自家 kernelcache） | `candidate_sha256` = 我们自己的 `kernel.macho` |
| missing | 2 owners / 2 points | 21 owners / 94 points |
| stubbed | 10 owners / 24 points | 25 owners / 203 points |
| required branches | 2 条（`IOMobileFramebufferLegacy`、`IOHIDDevice::handleOpen`） | `native_original_branches = []`（本支不链 `libNativeLegacyDisplay`，有 waiver） |

上游 policy 的语义是「拿**同一次 Apple 构建**的符号化 RELEASE 参考去匹配 Apple 自己的 kernelcache，不许变差」。
我们用的是**自己编的 kernel + 自己的参考**，两边 bundle 集合、LTO 参考、链接顺序都不同 ⇒ **数字不可直接相减**。
把 2/24 当成目标等于要求我们的内核和 Apple 的内核二进制同形，这不可能。

## 我们的 21 + 25 个 owner 是谁

`missing`（94）：AppleARMPlatform 11、IOHIDFamily 10、IOAVFamily 8、IOSurface 8、IOMobileGraphicsFamily 7、apfs 6、IOStorageFamily 6、sandbox 6、AppleARMWatchdogTimer 4、ApplePMGR 4、IOAudio2Family 4、IOGPUFamily 4、M2ScalerCSC 3、CoreAnalytics 3、AMFI 2、IOHDCP 2、IOReport 2、IODART 1、IOCEC 1、IOCryptoAccelerator 1、AppleImage4 1。

`stubbed`（203）：AMFI 41、sandbox 23、apfs 20、AppleARMPlatform 17、IOAVFamily 16、IOHIDFamily 12、IOGPUFamily 10、IOSurface 9、ApplePMGR 7、AppleImage4 7、Image4 7、AppleARMWatchdogTimer 6、IOStorageFamily 5、M2ScalerCSC 4、CoreAnalytics 3、corecrypto 3、其余 9 个 owner 各 1–2。

两岸都在的 owner 有 10 个（AppleARMPlatform / IOHIDFamily / IOStorageFamily / ApplePMGR / AppleARMWatchdogTimer / AppleImage4 / Image4 / IOSurface / IOGPUFamily / IOCryptoAcceleratorFamily）；
**只我们有**的 15 个（AMFI、sandbox、apfs、IOAVFamily、IOMobileGraphicsFamily、IOAudio2Family、M2ScalerCSC、CoreAnalytics、IOHDCP、IOReport、IODART、IOCEC、corecrypto、AppleEffaceableStorage、AppleIISController、AppleFSCompression）是因为我们的 prelink roots 包含了这些 bundle，而上游 27 policy 描述的 kernelcache 里它们不需要跨 bundle 引用。

## 为什么这不能证明「可以飞」

结构证据（已有，`PRELINK-RESIDUE.md`）：console 在 `osfmk/kern/startup.c:478`（`console_init()`）与 `:585`，`PE_init_iokit()` 在 `:689`；203 个桩站点全在 kext 指针槽，只有 kext 初始化之后才会被调用 ⇒ **console 之前可达数 0**。
反证：这只是「按初始化顺序推断」，没有一次运行证明。桩的用处正是把「推断」变成「实测」——它 panic 时打印 `__builtin_return_address(0)`，一次启动就能点名调用者。

## 结论（两条互斥的路）

1. **接受风险**：把 `prelink-map-unresolved` 记为「已知、已量化、console 前不可达」，允许 `--flight-ready` 放行一次，用桩的输出换实测清单。这需要用户明确同意（因为门禁现在是硬红）。
2. **不接受到能证明为止**：则永远不能飞——因为证明它需要飞行，而飞行被这条门禁挡住。这是死循环，必须先由人打破。

本地 policy 基线（`check-prelink-regressions.py --write --force`）只解决「policy 未命名」这一半，**不改变 blocker 的 open 状态**，也不改变上面这个死循环。
