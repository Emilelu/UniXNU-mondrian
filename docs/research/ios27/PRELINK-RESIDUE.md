# 预链接残留：205 个桩到底是什么

来源：2026-11-21 独立审计（`E:/k60-work/scratch/stubs/{classify.py,REPORT.md,unreachable.toml}`，
`check` 子命令能在 1.8 s 内复现记录：`205 items / 203 keys / 25 bundles`，`check: OK`）。
本文只保留结论与判据，细节与逐目标表在那份交付里。

## 它们是「指针槽」，不是调用

179 个 `__auth_got` 导入槽 + 26 个 `__const` 表项，由 kext 持有，指向 131 个
`com.apple.kernel` 函数起点。第一版审计按 `bl` 指令找调用点，找到 272 个全在内核里——
**kext 从不 `bl` 到内核函数，它持有指针**。这是判据层面的纠正，不改数字。

复现链（`classify.py check` 断言）：594,801 个链式站点 → 45,852 个内核侧（从不重绑）
→ 548,949 个 kext 侧 → 462,405 个在闭包外 → 48,553 个已映射 → **205 个落桩**。

`203` 与 `205` 不矛盾：`0xfffffff00b430ab8` 与 `0xfffffff00b430bd4` 各被两个 bundle
（IOHIDFamily 与 IOStorageFamily）加载，所以 203 是地址数、205 是站点数。

## 没有一个「console 起来前可达」

这是结构性证明，不是逐目标推测：`osfmk/kern/startup.c` 的 `console_init()` 在 `:478`，
`code_signing_init()` 在 `:526`，bootstrap 线程在 `:565`，而第一个 kext 启动是
`PE_init_iokit()` 于 `:689`，在 `kernel_bootstrap_thread()` 内。**没有 kext 代码在 `:689`
之前执行**，而 205 个槽全部住在 kext 的 `__DATA_CONST`/`__const` 里 ⇒ 「console 前可达」
这一类的成员数为 0。

| verdict | bundle | target | item |
| --- | ---: | ---: | ---: |
| `reachable-early`（`console_init()` 之前） | 0 | 0 | 0 |
| `unreachable`（有机制说明） | 25 | 131 | 205 |
| …其中上游同类可登记为基线 | 10 | 55 | 84 |
| …其中只有我们有（无上游先例） | 15 | 76 | 121 |

## 但它们会在 console 之后咬人，顺序可排

1. **AMFI 41 项** — `vnode_check_signature`、trust-cache 钩子、`AMFIUpdateDeviceState`；
   第一次 `launchd` exec 就撞。其中 3 项就在 `early_security_init` 里。
2. **apfs 20 项** — `container_load_with_callback`、`apfs_vfsop_mount`、`handle_crypto_mount`；
   根卷挂不上。
3. **sandbox 23 项** — `hook_thread_userret`、pathmonitor、profile/extension 钩子；每个任务启动都走。
4. **AppleARMWatchdogTimer 6 项** — `wdt-version` / `reconfig-wdog-support`，在根挂载前就武装；
   这里停住会中途复位。
5. **IOStorageFamily 5 项** — `Start_Invoke`/`Stop_Invoke` 槽加 `_mach_absolute_time`；它下面什么都不挂。

其余：IOGPU+IOSurface+IOMobileGraphics+Scaler 共 24 项（显示组）、`IODARTFamily` 1 项在 IOMMU 路径、
AppleARMPlatform 有 5 个 `__const` 的 IOCPU/IOInterruptController 槽。

**最锋利的一条**：最早的一组（3 个目标 / 13 项）能在 `code_signing_init()`（`:526`）被触及——
那时 console *子系统* 已初始化但人读的那个控制台（K60 上是 USB CDC-ACM gadget）还没起来，
所以**这一类的第一次失败会是静默的**。这 13 项因此是「必须先实现」而不是「可以先观察」：
在它们上面失败，我们学不到任何东西。

## `native_original_branches` 为什么是空的

`emit_prelink.py` 没有对应开关；字段来自 `fileset_segmented.py:63-64` →
`relocate_original_stubs()`（`fileset_layout.py:255-283`），只有在原生内核导出一个以
`.original` 结尾、唯一配对的符号、形状是 `bti c; b`、且位移等于声明的绝对目标、落在
`retained_code` 范围内时才记录。**我们的内核一个 `.original` 符号都没有**——没有
`IOMobileFramebufferLegacy` 适配器、没有 `IOHIDDevice::handleOpen` 适配器（只有
`iokit/Kernel/IOUserClient.cpp:6630` 的字符串提及）。对这棵树来说空是正确答案；
把上游那两个名字抄进 policy 只会让警报变绿而什么都没量到（P-289 家族）。

要有意义地非空，得为我们**真的会走**的内核→kext 绝对分支写一个 `.original` 适配器；
而今天唯一的内核→kext 路径是 `early_security_init` 那个钩子，它是 hook 不是绝对分支。
所以要么找到一条真的绝对分支，要么在 policy 里写明「本内核没有这类分支」并把列表钉成空——
两者都要有证据，后者不能让警报静默失效。

## 仍然未知（写清楚，不要当成已解决）

- 131 个目标里 105 个没有名字（26 个有名字：4 个来自字面串、22 个按链接顺序+大小+形状
  与同构建 iPad 夹具比对为「很可能」）。
- `_unixnu_fileset_unmapped` 被调用时的确切行为未建立（`kernel.json` 里的 native 路径已不在，
  但 `kernel.macho` 带着我们 221,318 个符号的表）。
- 每个「首次执行」阶段是从 bundle 字面串 + XNU 启动顺序推出的**预测**，不是 K60 日志。
## 追补（同日，bt 线的独立结论）：那两个分支的来历

上游 `required_original_branches` 的两条（`__ZN25IOMobileFramebufferLegacyC2EPK11OSMetaClass`、
`__ZN11IOHIDDevice10handleOpenEP9IOServicejPv`）不是 XNU 自己的符号，而是 Sheng 的
`libNativeLegacyDisplay.late.a` 提供的 `.original` 适配器（display 与 HID 各一条，形状 `bti c; b`）。
本支 `CONFIG_XNU_NATIVE_LEGACY_DISPLAY=n` 且不链这个 archive，所以：

- 写入点 `fileset_emit.py:731-732` -> `fileset_segmented.py:63-64` -> `fileset_layout.py:250-288`，
  只在原生内核导出唯一配对的 `.original` 时记录；
- `--lto` 参考只影响匹配，不产生这个字段（所以「等 LTO 就好了」不成立）；
- 空列表是这棵树的正确测量。

这给出比日期更硬的复审条件：若哪天把 `CONFIG_XNU_NATIVE_LEGACY_DISPLAY` 打开并链接
`libNativeLegacyDisplay.late.a`，`required_original_branches` 必须变成非空；反之保持空并写明原因。
证据来自 bt 线 `feat/xnu27-data-gate` 的 `docs/research/storage/PRELINK-ORIGINAL-BRANCHES.md`
（234 行）与 `E:/k60-work/scratch/reply-bt-20261115.md`。
## 地址不能用来回答「我们到底有没有编出来」

一次直接的测量（`E:/k60-work/scratch/classify_targets.py`，读 `unreachable.toml` 的 131 个 target，
对两份内核按 `__TEXT_EXEC` 段范围筛符号）：

| 产物 | `__TEXT_EXEC` | 段内符号 |
| --- | --- | ---: |
| `mach.development.bcm2837.unstripped.noctf`（我们） | `0xfffffff0072c0000..0xfffffff007c28000` | 29,010 |
| `mach.release.bcm2837.unstripped.noctf`（我们的 LTO 参考） | `0xfffffff0071b4000..0xfffffff0079f0000` | 19,789 |
| 131 个 target（Apple 24A446 集合空间） | `0xfffffff00ab86b04` 起 | — |

**131 个 target 全部高过我们自己内核的 `__TEXT_EXEC` 末端**，因为它们是 Apple 那份
kernelcache 的链接布局，不是我们的。所以「按地址查我们有没有编出来」这条路本身是错的：
同一个函数在两份内核里地址不同，减 slide 也没有意义（我们的 `collection_slide = 0x0`）。

这也解释了 `llvm-nm` 的第一版读数：Mach 内核的代码在 `__TEXT_EXEC`，`llvm-nm` 把它报成
通用 section 符号（`s`/`S`）而不是 `t`/`T`，所以按符号类型筛会得到「零个函数」——
又一次「用错了坐标轴，然后得到一个看起来很确定的数字」。

结论：残留的 131 个目标**只能按名字判定**，而 Apple 的 cache 里没有名字（`imports_count = 0`、
`LC_SYMTAB nsyms = 0`）。因此在拿到带符号的同族产物之前，「这些是不是我们没编出来」是一个
**不可回答**的问题，不是「不需要回答」。可回答的那部分是已记录的结构结论：它们全部住在 kext
的 `__DATA_CONST`/`__const` 表里，而 kext 代码在 `PE_init_iokit()`（`startup.c:689`）之前不执行。
## 常数偏移也不行，所以只能靠运行期点名

按 `__TEXT_EXEC` 起点算常数偏移（Apple `0xfffffff00ab48000`，我们 DEVELOPMENT `0xfffffff0072c0000`，
delta `0x3888000`；LTO 参考 `0xfffffff0071b4000`，delta `0x3994000`），再映射 131 个 target：

| 产物 | 落在段内 | 恰好是函数起点 |
| --- | ---: | ---: |
| DEVELOPMENT 内核 | 131 / 131 | **1** |
| LTO 参考 | 126 / 131 | **2** |

131 个里只有 1–2 个在常数偏移下正好落在函数起点，与随机命中无异。这说明两份内核的函数排布
不是「同一套代码换基址」，而是真的不同（编译器、配置、内联都不同）。因此：

- **按地址配对**：不可行（已在上一节证明连段都不重合，这里再证明常数偏移也救不了）；
- **按名字配对**：不可行（Apple cache `imports_count 0`、`LC_SYMTAB nsyms 0`）。

那 45,423 个成功配对是**我们自己编译的 kext** 的导入（它们的导入带名字）；剩下 205 个全部来自
Apple 预编译 kext 的导入，那些导入在写 cache 时已被解析成 Apple 的地址，名字没有留下来。

### 所以这 205 个的正确处理方式是「用运行期点名」

`_unixnu_fileset_unmapped` 在 panic 时会打印调用点（`__builtin_return_address(0)` 加 x0/x1）。
也就是说：**一次真实的启动会把「哪个地址在哪一步被调用」变成日志**，把 205 个未知数变成一条
可测的清单。这不是「先飞再说」，而是这套机制被设计出来的用法——上游 policy 的注释也写着
`This bounds regressions, not runtime qualification.`

在没有那次启动之前，205 个的正确状态是：**结构上已知（全在 kext 指针槽、全部晚于 console）、
归属上未知（不知道我们有没有编出来）、运行期未测**。三者分开写，不合并成一句「还剩 205 个」。

## `note prelink policy: missing grew` 是常驻提示，不是新回归

2026-11-22 05:38 第一次注意到这行（`com.apple.security.sandbox original 0xfffffff007e8a9e0
has 1 site(s), the policy allows 0`），当时怀疑是 0546/0547 带进来的。核过两件事：

- 同一个措辞在 **console4**（0547 之前）就已经在打，只是那几次报的是
  `com.apple.driver.AppleARMPlatform` 的四个地址；
- 05:41 用 `check-ios27-artifacts.py <board>` 重读计数：**94 unresolved / 21 bundles、
  203 stubbed / 25 bundles**，与 0546 之前完全一致。

⇒ 这行是「policy 里某个 original 当前有 n 个站点，而 policy 允许 0」的逐条读数，
换一次构建就可能换成另一个 bundle；**它不是计数增长**。判据应看上面那两个总数，
不看这一行的主语是谁。
