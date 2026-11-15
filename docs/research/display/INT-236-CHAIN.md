# INT-236 连锁调查：backlight-control 打开时 backboardd 崩在哪里

状态：离线调查（Lead 的 (a-1) 项），**未上机**。日期 2026-11-15。
分支 `feat/display`（HEAD `ddbb754`，基线 `2f9f991`）。交付形态仍是 brightness-13（默认不发 backlight-control）。

本文件回答三个问题：谁持了 display lock、backboardd 崩在哪个调用栈（pc/lr 能否反推符号）、
「发布 backlight-control 但 IOObjectConformsTo 不成立」能否改成真的 conforms。
每条结论标注证据（文件:行 或日志行号），查不出来的写在「缺口」里，不猜。

---

## 0 口径更正（Lead 2026-11-15 更正）

- **int-236 只认一对对照**：brightness-4（control=1，backboardd 4 次 SIGSEGV）对
  brightness-13（control=0，0 次崩溃）。§1 结论 1 所说的「gpu-20261114t 前提不成立」
  是 Lead 此轮亲口更正的前提错误（原话「这是我这一轮的错」），gpu-20261114t 不在
  int-236 链条内，只作为 P-120（金属注入崩溃）的参考样本保留在 §2 对照表里。
- §2 三张图的可比性表中 gpu-20261114t 一列因此只服务于「排除金属注入」，不参与任何
  int-236 结论；本文件其余结论全部基于 brightness-4 对 brightness-13 这一对。

---

## 1 结论摘要

1. **Lead 给的 gpu-20261114t 前提不成立**：那份日志里没有背光服务，也不是 `control=1` 崩溃。
   它是已知坑 **P-120**（`pong_metal=1` 注入 PongAdrenoMetal 插件后 backboardd 抛
   `NSURL initFileURLWithPath: nil string parameter` 而 SIGABRT），与 int-236 无关。见 §4。
2. **brightness-4 的 4 次 backboardd 崩溃发生在「背光发布之后、显示管线第一次更新之前」**：
   整份日志 0 条 `MiniIOMobileFramebuffer: swap`、0 条 first frame、0 条 Pong UI 显示钩子活动，
   而同一镜像族的 brightness-13 在相同位置（:2150 起）开始出现 `display ignore update` 与 swap。
   见 §2、§6。
3. **崩的不是我们的兼容钩子**：钩子在 :1192-1200 全部安装成功（protection=0），但整个日志
   0 条钩子活动行——第一帧管线根本没走到 `ignore_update` / `begin_update` / `render_update`。见 §6。
4. **int-236 描述的「持锁阻塞」形态在 b4 上没有出现**：b4 是 SIGSEGV 后进程退出（4 次重启），
   不是挂起。K60 上可证的是「崩在显示管线启动段」，锁持有者无法从日志证明（缺口）。见 §6。
5. **pc/lr 反推符号离线做不到**：pc 落在 dyld 共享缓存，本地没有 20G81 的 shared cache，
   设备上的 coresymbolicationd 也因 `/private/var/root/Library/Caches` 缺失而失败。见 §7。
6. **「真的 conforms」在内核查询层面已经成立**：impersonation 返回的是 OSMetaClass 注册表里
   **真实的 AppleARMBacklight 元类**，IOObjectConformsTo 与沙箱走的就是这条真实链。
   假的只是 C++ 布局（vtable）。真正的 C++ 继承**做不到**：`superClassLink` 是 private。见 §8。

---

## 2 三张图的可比性

| | brightness-4 | brightness-13 | gpu-20261114t |
| --- | --- | --- | --- |
| 证据目录 | `usblog-20261115-013520` | `usblog-20261115-134638` | `usblog-20261114-235957` |
| 背光服务 | control=1（:183 旧格式） | conformance=0 control=0（:183 新格式） | **无**（0 条 `K60 BACKLIGHT`） |
| kernel_args | `['']` | `['']` | `['']` |
| payload_args | `pong_metal=2 … k60_skip_iosurface=1` | **完全相同** | `pong_metal=1 sheng-gpu-addon=1` |
| backboardd 崩溃 | 4 次 SIGSEGV | **0 次** | 16 次 SIGABRT |
| SpringBoard 行数 | 7 | 128 | — |
| `MiniIOMobileFramebuffer: swap` | **0** | 14 条（:2172 起） | 0 |
| `first frame presented` | 无 | :2342 | 无 |
| Pong UI 显示钩子活动 | **0** | 齐全（:2150/:2326/:2329…） | 0（`Pong Metal` 也 0） |

b4 与 b13 的 `payload_args` 逐字相同（同一 board.toml 默认，
`board.toml:192` 的 `k60_skip_iosurface=1`、`pong_metal=2`、`k60_autoreset=300` 等），
两者 Kernel 侧唯一的实质差异就是 `K60Backlight.cpp` 的发布门：
b4 是「`impersonate()` 成功即发 backlight-control」，b13 是「默认不发 + conformance 查询」。

**这条对照的意义**：b4/b13 是同一 payload、同一 boot 参数、同一用户态钩子集，只有一个变量
（backlight-control 是否发布）。b4 崩、b13 不崩，归因范围被压到「发布 control 之后的系统路径」。

---

## 3 KX! / KXPC 怎么读

`bsd/kern/kern_exit.c:1776` 打印：

```
KX! %u %d %s exit=%u sig=%u r=%u ns=%u code=0x%llx rf=0x%llx jf=0x%x
```

依次是 记录号、pid、进程名、k60_status、k60_sig、有 reason、namespache、code、flags、jetsam flags；
`kern_exit.c:1791` 的 `KXPC %d %s pc=0x%llx lr=0x%llx sp=0x%llx` 用 `find_user_regs(current_thread())`
取崩溃线程的 PC/LR/SP（注释：为了让静默 SIGSEGV 也能指出故障地址）。

b4 首崩（`console.log:2145-2147`）：

```
KX! 16 55 backboardd exit=0 sig=11 r=1 ns=2 code=0xb rf=0x0 jf=0x0
KXPC 55 backboardd pc=0x1afa3f668 lr=0x1d7c90aa4 sp=0x16f4dde20
Process[55] crashed: backboardd. Too many corpses being created.
```

`sig=11`、`code=0xb`（=11）即 SIGSEGV，不是 jetsam 击杀（`jf=0`）。
后续 3 次（:2338 `Process[231]`、:2562 `Process[248]`、:2760 `Process[266]`）只有
`Process[N] crashed` 行，没有第二次 KXPC——寄存器只在第一次死亡记录里打一次。

**读 pc 时必须先分清「真实崩溃点」和「公共退出桩」**：b4 里 `sysstatuscheck`、`fileproviderd`、
`SpringBoard` 等进程的 KXPC 都是 `pc=0x1e9ca0508 lr=0x1b682c400`（同一 exit stub，不同 boot 有不同 slide）。
backboardd 的 `pc=0x1afa3f668` 不在那个桩上，是真实崩溃点。

对照 gpu-t（`console.log:1404-1405`）：

```
KX! 6 55 backboardd exit=0 sig=6 r=1 ns=2 code=0x6 rf=0x0 jf=0x0      ← SIGABRT
KXPC 55 backboardd pc=0x1e2239198 lr=0x1f16f55f8 sp=0x16ebb35f0
```

两份签名完全不同：b4 是 **SIGSEGV、日志里没有任何异常文本**；gpu-t 是 **SIGABRT、崩溃前有 17 条
ObjC 异常**（见 §4）。把两者当成同一种「int-236」会得出错误结论。

---

## 4 gpu-20261114t 不是 int-236（前提更正）

Lead 的描述是「gpu-20261114t（pong_metal=1 + control=1，backboardd SIGABRT 16 次）」。实测三点都不成立：

1. **没有 control=1**：`/mnt/e/k60-work/artifacts/gpu-20261114t/build-manifest.json` 的
   `kernel_args_requested` 是 `['']`，`payload_args` 里没有任何 `k60_backlight*`。
2. **没有背光服务**：该镜像是 `feat/gpu-yibiya` 的产物，那时 `K60Backlight.cpp` 还不在 `origin/main`
   （`git ls-tree origin/main drivers/PongAdreno/` 无此文件），日志 0 条 `K60 BACKLIGHT`。
3. **崩溃形态是 P-120**：`docs/engineering/PITFALLS.md:2644` 起的
   **P-120「注入 PongAdrenoMetal 插件后 backboardd 崩溃，屏幕永远停在刷码」**记录得一模一样：
   `backboardd[55] *** Terminating app … 'NSInvalidArgumentException' … '-[NSURL initFileURLWithPath:]: nil string parameter'`；
   机制是 `pong_metal=1` 时把 `/private/var/pong/PongAdrenoMetal.bundle/PongAdrenoMetal backboardd`
   塞进 `kern.exec_inject` 的 `DYLD_INSERT_LIBRARIES`（PITFALLS.md:2679-2683 有注入代码）；
   判据是插件自己的 `Pong Metal` 日志 0 条（崩在 dyld 加载/初始化阶段），而 gpu-t 正是 0 条。
   P-120 还记了零重建开关 `pong_metal=2`（`strncmp` 精确匹配 `pong_metal=1`），实测崩溃 0 次。

gpu-t 的 16 个 `Process[N] crashed: backboardd`（例子 `:1400` 起共 17 条 NSURL 异常，约每 10 s 一条）
是插件加载循环，**不能用来解释 int-236**。同一类 NSURL nil 噪声也出现在 b4（`:2138-2144`，3 条
`syncdefaultsd` 异常 + `Process[229] crashed`）和 b13 里——那是
`docs/reference/PITFALLS-FROM-HISTORY.md` #131 记录的老噪声（syncdefaultsd 每次都因同一个 nil 路径被打死），
与背光无关，b13 也有却 0 崩溃。

---

## 5 int-236 原文与拆解

sheng 的 `/mnt/e/hackios/UniXNU-sheng/package/AppleARMBacklight.cpp` 在 `publishFirst` 上方逐字写着：

> CoreBrightness finds the backlight by backlight-control = true and takes it for the built-in
> display's only when IOObjectConformsTo(service, "AppleARMBacklight") holds (CBDisplayContaineriOS
> findBacklight). Only for the built-in display does CoreBrightness start the libEDR server
> (com.apple.libEDR.Notification) that QuartzCore's IOMFBServer sends to synchronously once
> backlight-control makes CADeviceHasBacklight true. int-236 published backlight-control without
> the conformance: the server never started, the send blocked with the display server lock held
> and the screen stopped updating. sheng-backlight-control=0 leaves both out.

拆成四条机制：

1. `backlight-control=true` 让 CoreBrightness 认为「这块屏有背光」（`CADeviceHasBacklight`）。
2. 只有 conformance 成立（`IOObjectConformsTo(service,"AppleARMBacklight")`）才被当作**内置屏**的背光，
   也才会启动 `com.apple.libEDR.Notification` 服务器。
3. QuartzCore 的 IOMFBServer 在 `CADeviceHasBacklight` 为真后**同步**发消息给该服务器。
4. int-236 发 control 但没有 conformance → 服务器没起来 → 同步发送卡住且**握着 display server lock** → 屏幕停止更新。

K60 的 b4 与第 4 条不同：它发 control **且** impersonate 成功（旧门是 `impersonate()` 返回真），
按 sheng 的语义 conformance 应当成立、libEDR 应当启动。**但 b4 仍然崩了，而且是 SIGSEGV 不是挂起。**
所以 K60 上真正被 `control=1` 打到的，是第 2 条之后的另一段路径：CADeviceHasBacklight 变真后
QuartzCore 走「有背光的屏」的初始化，而我们的显示栈（`k60_skip_iosurface=1` + 软件合成器 +
`0600-k60-display-composition.patch` 的保留帧模型）在这条路径上做了空指针解引用。
这是**推断**，证据是「崩在管线启动段、钩子之前、无异常文本」，不是栈回溯——见 §6/§7 的缺口。

---

## 6 Q1：谁持了 display lock？

### 6.1 日志能证明什么

- b4 崩之前**没有任何**显示活动：0 条 swap、0 条 first frame、0 条钩子活动（§2 表）。
- b4 崩之后同样没有：4 次重启（`:2147 :2338 :2562 :2760`），SpringBoard 在 `:2340` 以
  `exit=255 sig=0` 退出（不是崩），整份日志到 `:2865` 结束都没有一帧。
- 对照 b13：`:2150` 起 `display ignore update`，`:2172-2174` 起
  `MiniIOMobileFramebuffer: swap client pid 55 'backboardd' on swap 1`，`:2342` first frame。

所以「屏幕不再更新」在 b4 上是 **backboardd 不再存在**的直接结果（没有合成进程就没有 swap），
不是「某个锁被一直握着」的结果。int-236 的锁叙事在 K60 上**没有证据支持**，也不必要：
崩溃本身就足以解释黑屏。

### 6.2 排除掉的候选

- `: 6ee9e000 : waiting for matching IOKit service: { IOPropertyMatch = { EmbeddedDeviceTypeRoot = 1; } }`
  这类轮询在 b4 出现 49 次、b13 出现 60 次，而且 b4 在崩溃**之后**仍继续出现（`:2174` 起）——
  是别的进程在等一个本板永远不匹配的服务，两份日志都有，与 backboardd 无关，排除。
- 我们的兼容钩子：`:1190` backboardd 进入兼容库，`:1192-1200` 六个钩子全部 installed
  （`software renderer fallback` / `software framebuffer format` / `display readiness` /
  `display update gate` / `display begin update` / `compositor render update`，protection=0），
  但 0 条调用记录 → 崩溃发生在它们之前。**排除钩子作为崩溃点**。
- syncdefaultsd 的 NSURL 异常风暴（`:2138-2144`）紧挨着 backboardd 首崩，但同一噪声在 b13 里也有
  且 b13 不崩（PITFALLS-FROM-HISTORY #131），排除因果。

### 6.3 锁候选清单（若将来要插桩）

| 锁 | 位置 | 谁用 |
| --- | --- | --- |
| `fLock` | `MiniIOMobileFramebuffer.cpp:273` | 整个 framebuffer 的粗粒度锁 |
| `fSwapLock` | `MiniIOMobileFramebuffer.cpp:293`、分配于 `:461` | 交换队列与其 surface 持有者 |
| `fHelperLock` | `MiniIOMobileFramebuffer.cpp:351`、等待/唤醒在 `:735-761`、`:830-844` | 合成 helper 线程，有 `IOLockSleep`/`IOLockWakeup` |
| `gSurfaceLock` | `MiniIOSurface.cpp:87` | IOSurface 全局锁 |
| IOSurface 跨进程 lock trap | `MiniIOSurface.cpp:942 lockCommon`、`:977 trapUnlock` | 用户态拿锁、内核记账 |

注意 `k60_skip_iosurface=1`（`BOOT-ARGS.md:54` 的 `0332-k60-skip-prelinked-load.patch`，
P-98 记录「目前是必需的」）跳过的是**预链接的 IOSurface 加载**，树内的 MiniIOSurface 仍在用，
所以 `gSurfaceLock`/`lockCommon` 不是死代码，但也没有任何日志证据指向它们。

### 6.4 缺口

要回答「锁在谁手里」需要**崩溃前**的观测点，而现有钩子都在崩溃点之后。可选的最小插桩：
在 `ui_compat.c` 里把钩子安装时间点再往前挪（`display_ready` 已是就位的最早观测点，
`ui_compat.c:868-878`，它在 `+0x9f2` 读 flags 并打印），或在 `MiniIOMobileFramebuffer.cpp:735`
的 `IOLockSleep` 前后加计数（会写内核日志，成本低）。**这一项没有做**，因为它需要一次新镜像。

---

## 7 Q2：pc/lr 能否反推符号？

b4 首崩 `pc=0x1afa3f668 lr=0x1d7c90aa4`。两者都在 dyld 共享缓存地址段（`< 0x200000000`），
不是我们的代码（我们注入的 dylib 在 `0x100xxxxxx` 段，见 b4 `:2138-2144` 的栈帧 `0x10070af48`）。

- **每 boot 的 slide 不同**：同一 exit stub 在 b4 是 `pc=0x1e9c9f538`（launchd），b13 是 `0x1df0ab538`，
  gpu-t 是 `0x1e2237538`。所以 pc 不能跨日志直接比，必须先对齐 slide 再落到镜像偏移。
- **本地没有 cache**：`find /mnt/e/hackios /mnt/e/k60-work/firmware -maxdepth 6 -name 'dyld_shared_cache*'`
  → 0 命中。没有 20G81 的 `dyld_shared_cache_arm64e` 就无法把偏移翻译成符号。
- **设备侧也没戏**：b4 末尾 `:2864-2865`
  `Attempt to create [/private/var/root/Library/Caches/com.apple.coresymbolicationd/20G81] failed. No such file or directory`
  → 我们的 Data 目录准备方式让符号化缓存目录不存在，系统自己的 coresymbolicationd 也失败。

**可行路径（未执行）**：从 20G81 IPSW 抽 `dyld_shared_cache_arm64e`（或从设备
`/System/Library/Caches/com.apple.dyld/` 拷），用 `ipsw`/`jtool2` 或 `dyld_info -addresses` 把
b4 的 pc 落到某个 dylib 的偏移，再查该偏移附近的调用。**缺口明确：需要 cache 文件，属于离线素材**。

---

## 8 Q3：「发布 backlight-control 但 IOObjectConformsTo 不成立」能改成真的 conforms 吗？

### 8.1 现状到底假不假

`K60Backlight.cpp:128-152` 的 `impersonate()`：从 OSMetaClass 注册表取
`OSMetaClass::getMetaClassWithName("AppleARMBacklight")`（`:1073`），复制 320 槽 vtable、
把槽 7（`getMetaClass`）换成返回该元类的静态函数，再 `dmb ish` + 换 vptr。
查询链是 `OSMetaClassBase::metaCast(const char*)`（`OSMetaClass.cpp:415`）→
`checkMetaCastWithName`（`:1326`）→ `OSMetaClass::checkMetaCast`（`:1381-1402`）：

```
for (fromMeta = check->getMetaClass();; fromMeta = fromMeta->superClassLink) {
    if (toMeta == fromMeta) return const_cast<OSMetaClassBase *>(check);
    if (!fromMeta->superClassLink) break;
}
```

`check->getMetaClass()` 走虚拟派发 → 我们换过的槽 7 → 返回**真实的 AppleARMBacklight 元类**，
于是循环第一轮就命中。用户态 `IOObjectConformsTo` 走的是同一张注册表
（`is_io_object_get_class` 用 `getMetaClass()->getClassName()`，`IOUserClient.cpp`），
沙箱的 `iokit-set-properties` 判定也按 sheng 注释所说「walk getMetaClass's superclass chain by name」。

**结论：在内核查询语义上，conformance 是「真」的**——不是伪造一个字符串，而是真的返回了系统里
那个 AppleARMBacklight 元类，它的 `superClassLink` 链上也真的有 AppleARMBacklight。见
`K60Backlight.cpp:161` 的 `conformsToAppleBacklight()`（`metaCast("AppleARMBacklight") != nullptr`）
就是这条链的自检。

**假的是 C++ 布局**：vtable 是我们自己类的 320 槽拷贝，不是 AppleARMBacklight 的真实布局。
任何把服务 `OSDynamicCast` 成 AppleARMBacklight 再调虚函数的代码都会派发到错误槽位。

### 8.2 能不能做「真的继承」

不能，三条硬约束：

1. `OSMetaClass.h:1020` 的 `const OSMetaClass *superClassLink;` 在 **private** 段，外部无法把它指向
   AppleARMBacklight 元类；没有它 `checkMetaCast` 的循环就永远走不到 Apple 类。
2. 即便能改，继承后的 vtable 槽位必须与 AppleARMBacklight 完全一致，而我们没有它的头文件/布局
   （AppleARMPlatform 是预链接里的闭源类）。
3. 类名不能直接叫 AppleARMBacklight：AppleARMPlatform 已定义该类，重名注册即 panic（int-229）。

### 8.3 另一条路：造一个真的 AppleARMBacklight 实例

`gAppleClass->alloc()` 会调用该元类的 `alloc()`，得到**真正的 AppleARMBacklight 对象**（`getClassSize()`
在 `OSMetaClass.h:1683`，大小由 Apple 类自己声明）。理论上有真 conformance，但：

- 它的方法几乎肯定要求 `AppleARMPlatform` 类型的 provider（本板是 `ArmDTPlatform`，
  `drivers/ArmDTPlatform/ArmDTPlatform.cpp:39`），`start()` 可能失败或 panic；
- 它的背光写路径由 Apple 自己实现（PWM/SPI/DCS 未知），我们无法把 DCS 0x51 接到它里面；
- 未验证，风险高于收益。

**因此 K60 的正确形态就是现状**：默认不发 control（brightness-13），需要时才 impersonate 并用
`metaCast` 自检。int-236 的根因**不是「conforms 是假的」**，而是「发了 control 之后系统进入
EDR/背光路径，而我们的显示栈承受不了那条路径」。

---

## 9 缺口与下一步

1. **符号化缺口**（§7）：要一份 20G81 的 `dyld_shared_cache_arm64e` 才能把 `pc=0x1afa3f668` 变成函数名。
   没有它，b4 的崩溃点只能定位到「共享缓存里某个 dylib」，不能定位到调用。
2. **插桩缺口**（§6.4）：现有钩子都在崩溃点之后。若要再试 control=1，应先加一个**崩溃前**的观测点
   （例如 `ui_compat.c` 里 `display_ready` 前后的更早符号，或内核 `fHelperLock` 等待计数），
   而不是盲目再飞一张。
3. **brightness-14 已构建但不飞**（Lead 裁定，见 `HANDOFF-20261114.md`）：它的作用是照出
   「control=1 会崩」，b4 已经照过一次；重复飞只会再收一份 4 次 SIGSEGV。
4. **交付形态不变**：brightness-13（`boot.img c8c33b9e…`）是唯一在飞的背光镜像；
   亮度滑块三档真机可见仍挂后续（`08-on-device.md` 第 2 轮待测）。
5. 本文件只做离线归因，不改代码、不加 boot-arg、不动 stats 语义。

---

## 10 引用清单

- `/mnt/e/hackios/UniXNU-sheng/package/AppleARMBacklight.cpp`：impersonate 与 publishFirst 上方注释、
  `publishFirst` 的 control/impersonate/stats[0] 代码。
- `xnu-work/bsd/kern/kern_exit.c:1776`、`:1791`（KX!/KXPC 格式与 find_user_regs）。
- `xnu-work/libkern/c++/OSMetaClass.cpp:415`、`:1326`、`:1381-1402`（metaCast / checkMetaCast 链）。
- `fakeroot/…/Kernel.framework/Headers/libkern/c++/OSMetaClass.h:1020`（superClassLink private）、
  `:1073`（getMetaClassWithName）、`:1683`（getClassSize）。
- `xnu-work/iokit/Kernel/MiniIOMobileFramebuffer.cpp:273`（fLock）、`:293`/`:461`（fSwapLock）、
  `:351`/`:735-761`/`:830-844`（fHelperLock）。
- `xnu-work/iokit/Kernel/MiniIOSurface.cpp:87`（gSurfaceLock）、`:942`（lockCommon）、`:977`（trapUnlock）。
- `userland/ui_compat.c:868-878`（display_ready）、`:880-895`（ignore_update）、`:897-905`（begin_update）、
  `:907-915`（render_update）、`:917-941`（replace_virtual，shared cache slide）、`:943-949`（钩子安装地址）。
- `drivers/PongAdreno/K60Backlight.cpp:128-152`（impersonate）、`:161`（conformsToAppleBacklight）。
- `docs/engineering/PITFALLS.md:2644`（P-120）、`:2679-2683`（exec_inject 注入代码）、`:1835`（P-98）。
- `docs/reference/PITFALLS-FROM-HISTORY.md` #131（syncdefaultsd NSURL nil）、#132（注入钩子导致 SpringBoard 循环）。
- `docs/engineering/BOOT-ARGS.md:54`（k60_skip_iosurface）、`board.toml:192`（payload 默认参数）。
- 日志：`/mnt/e/k60-work/evidence/usblog-20261115-013520/console.log`（b4）、
  `usblog-20261115-134638/console.log`（b13）、`usblog-20261114-235957/console.log`（gpu-t）。
