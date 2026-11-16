# GPU Metal：`IOSurfaceRoot` 不存在是加速失败的根因

日期：2026-11-16（round 58）
证据：`E:/k60-work/evidence/usblog-20261116-221257/console.log`（`pong_metal=1` + 当前源码重编的 plugin）

## 1. 受控对照

| 镜像 | `pong_metal` | 行数 | SpringBoard | `crashed: backboardd` | `Too many corpses` |
| --- | --- | --- | --- | --- | --- |
| `usblog-20261116-164726`（bt d8） | `=2` 软件渲染 | 3,749 | 128 | 0 | 7 |
| `usblog-20261116-221257`（新 plugin） | `=1` | 3,285 | 13 | 16 | 30 |

内核侧是成功的：`:643` `PONG METAL: real IOAcceleratorES provider published`、`:645`
`NativeAdreno complete runtime publication status=0x0`。用户态仍 19 次
`Pong UI: 20G81 software renderer fallback installed (protection=0)` 与
`optional camera-filter GPU prewarm skipped (software-only platform)` ⇒
`MTLCreateSystemDefaultDevice()` 返回 nil。首次崩溃 `:1988`，紧跟 6 个 hook 安装之后：
`-[NSURL initFileURLWithPath:]: nil string parameter`。

⇒ `pong_metal=1` 是崩溃循环的唯一变量；重编 plugin 不改变结局（仍 16 次）。

## 2. 根因（日志直接给出）

```
:131 NATIVEPRELINK: skip load of com.apple.iokit.IOSurface
:132 Couldn't alloc class "IOSurfaceRoot"
:135 Couldn't alloc class "IOSurfaceRoot"
:237 Couldn't alloc class "IOSurfaceRoot"
```

`patches/xnu/0332-k60-skip-prelinked-load.patch` 在 `k60_skip_iosurface=1` 时跳过
`com.apple.iokit.IOSurface` 的 `OSRuntimeInitializeCPP()`，即**整个 kext 的类都不注册**，
但它在 prelink 元数据里的 personality 仍在。`iokit/Kernel/IOService.cpp:4014`
的匹配循环因此三次 alloc 失败，`IOSurfaceRoot` 服务从未出现。

我们的 mini 实现用的是**另一个类名**：`patches/xnu/zzzzzzzzzzzzzzzzzzz-pong-hackios-ui-foundation.patch:816`
定义 `IOCoreSurfaceRoot : public IOService`，`:833` `setName("IOCoreSurfaceRoot")`，
`:832` 才把 `kIOUserClientClassKey` 设成 `IOSurfaceRootUserClient`。而 Apple 用户态
（IOSurface.framework / QuartzCore）用 `IOServiceMatching("IOSurfaceRoot")` 匹配，
`IOService::nameMatching()` 比的是**类名**，不是注册名 ⇒ 永远匹配不到我们的实例。

⇒ 没有 IOSurface 就没有共享表面 ⇒ Metal 无法枚举/分配 ⇒ 软件回退 ⇒ `pong_metal=1`
路径上拿 nil 建 NSURL 崩溃。这也解释了 P-98（删参数内核连控制台都不出现）：
不能删参数，要修的是“重复类”这一层的表达方式。

## 3. 修法（未实施）

在 mini driver 里让 surface root 的**类名**就是用户态要找的名字：

1. 新增 `class IOSurfaceRoot : public IOCoreSurfaceRoot`（`OSDeclareDefaultStructors` +
   `OSDefineMetaClassAndStructors`），保留 `kIOUserClientClassKey = "IOSurfaceRootUserClient"`。
2. `k60_skip_iosurface=1` 时用 `OSTypeAlloc(IOSurfaceRoot)` 发布；arg 为 0 时不实例化
   （真 kext 会自己注册同名类，此时我们的静态注册可能与之冲突——但 arg=0 目前本就不可用，P-98）。
3. 判据：`Couldn't alloc class "IOSurfaceRoot"` 0 命中 + 出现 `IOSurfaceRoot` 服务 +
   `software renderer fallback installed` 0 命中 + `MTLCreateSystemDefaultDevice` 非 nil +
   `crashed: backboardd` 0 + SpringBoard ≥100。

## 4. 教训

- 跳过 kext 的**加载**不等于移除它的 personality：日志里“找不到类”与“跳过了谁”必须成对读。
- 用户态按**类名**匹配 IOKit 服务；把 mini 实现起个自造名字（`IOCoreSurfaceRoot`）
  等价于没有实现，而症状会伪装成“驱动没发布 accelerator”。
