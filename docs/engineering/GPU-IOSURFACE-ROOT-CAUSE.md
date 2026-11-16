# GPU Metal：加速器从未被用户态打开（含一次被推翻的归因）

日期：2026-11-16（round 58–61）
证据：`E:/k60-work/evidence/usblog-20261116-{164726,221257,224736,230446}/console.log`

## 1. 受控对照

| 镜像 | `pong_metal` | 行数 | SpringBoard | `crashed: backboardd` | 软件回退 | IOSurface 客户端 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `usblog-20261116-164726`（bt d8） | `=2` | 3,749 | 128 | 0 | 1 | 3 |
| `usblog-20261116-221257`（新 plugin） | `=1` | 3,285 | 13 | 16 | 19 | 1 |
| `usblog-20261116-224736`（0622 注册名） | `=1` | 3,262 | 13 | 16 | 18 | 0 |
| `usblog-20261116-230446`（0623 类名） | `=1` | 3,245 | 13 | 15 | 18 | 0 |

内核侧一直成功：`PONG METAL: real IOAcceleratorES provider published`、
`NativeAdreno complete runtime publication status=0x0`。用户态一直回退：
`Pong UI: 20G81 software renderer fallback installed (protection=0)` +
`optional camera-filter GPU prewarm skipped (software-only platform)` ⇒
`MTLCreateSystemDefaultDevice()` 返回 nil。

## 2. 断点不在 IOSurface（本节推翻我先前写下的归因）

先前我把 `:132/:135 Couldn't alloc class "IOSurfaceRoot"`（`0332` 在
`k60_skip_iosurface=1` 时跳过真 `com.apple.iokit.IOSurface` kext 的构造器）当成 GPU 根因。
离线审计（`E:/k60-work/scratch/iosurface-trap-audit.md`，133 行）用对照日志否掉了它：

1. `usblog-20261116-164726` 那棵树**没有** 0622/0623（仍是 `class IOCoreSurfaceRoot` +
   `setName("IOCoreSurfaceRoot")`），却成功建了 3 个 `K60UF … cls=IOSurfaceRootUserClient`
   （`:2059/:2647/:2748`）并有 2 个大 surface（`:2896 MiniIOSurface: 2 big surfaces made`）。
   ⇒ `IOSurfaceRootUserClient` 与 `IOSurfaceCreate` 本来就能用。
2. 0623（类名改成 `IOSurfaceRoot`）确实把 3 条 `Couldn't alloc class` 消到 0，
   但回退次数、SpringBoard、backboardd 崩全都没变 ⇒ alloc 失败与软件回退无关。
3. 四份日志里从未出现 `selector N not implemented` / `create failed`；
   回退次数与 IOSurface 可用性不相关（18/0、19/1、1/3）。
4. `K60UF` 直方图里**从来没有加速器 user client**，而
   `PONG METAL: real IOAcceleratorES provider published` 来自 `0212` 的桩。
   ⇒ 断点在 IOSurface **上游**：用户态根本没打开加速器客户端。

仍然成立的旁证：`0332` 跳 kext 确实会让 3 个 personality alloc 失败（0623 已修）；
`IOSurfaceRoot::start()` 的注册前提（`native_pong_ui_services_start()` 被 bsd_init 调用、
未被 `pong_software_ui=0` 关掉、`IOService::getPlatform()` 非 NULL、`MiniIOSurfaceStart`
四个分配/start 步骤全成功）各有独立日志且都未触发失败。

## 3. 已提交的两步（保留为消除噪声，不作为根因修复）

| 提交 | 补丁 | 效果 |
| --- | --- | --- |
| `3524eb7f` | `0622` 注册名 → `IOSurfaceRoot` | 无效（alloc 失败仍 3） |
| `1a47f11b` | `0623` 类名 → `IOSurfaceRoot` | `Couldn't alloc class` 3 → 0 |

## 4. 下一层的候选断点（按证据强度排序）

1. **扫描输出未启用**：`drivers/PongAdreno/PongAdrenoScanout.cpp:45` 无
   `pong_gpu_scanout=1` 时直接 `return`；upstream 主线 `board.toml:212` 有该参数，
   我们因为命令行曾到 593/607 把它砍掉了。上游 `docs/plans/GPU-ENABLE-PLAN.md` §7.14
   记录 9 条 `present #` 样本（linear encode 222 µs / texture 5,099 µs，total 15.8–16.3 ms，
   8–17 fps）证明他那一侧确实出帧。我们已在 `1b8eaf47` 把它加回（575 → 595 B）。
2. **加速器 user client 未被打开**：需要在 `IOService::newUserClient`
   （`iokit/Kernel/IOService.cpp:7904`）为 `IOSurfaceRootUserClient` 打 provider 的
   `getMetaClass()->getClassName()` 与 `getName()`，区分「用户态没找」与「找了但失败」。
3. **selector 7 `WrapClientMemory` 未实现** ⇒ `kIOReturnUnsupported`；以及
   `IOConnectTrap` index ≥ 6 的**假成功**（`IOUserClient.cpp:6255-6325` 把 result 初值设为
   `kIOReturnSuccess`，`getTargetAndTrapForIndex` 返回 NULL 时仍返回成功、零动作）。
   `selector 0` 的回程契约也可疑：mini 把 `structureOutputSize` 改成
   `0x68 + planes×0x80`（单平面 0xe8），而头文件写 `MINISURF_RESULT_MAX 0xa68` 是
   「IOSurface.framework 预留的结果长度」。

## 5. 教训

- 把「某个类/服务没出现」当根因之前，必须先在**能进桌面的对照镜像**里确认那条路径
  本来是否该出现；否则就是 P-204 形状（拿一条与自己无关的记录解释现象）。
- `IOConnectTrap` 越界返回成功是「假成功」类缺陷：判据要看副作用，不能只看返回值。
- 在 `bash -lc "..."` 里写含反引号或 `$` 的 Markdown 会被外层 shell 吃掉；
  这类文本只能用文件写入工具，不能经 shell 拼接。
