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
