# iOS 27 · OS 服务与打包（安全与预检那半边）

状态（2026-11-21）：**B 段完成**。Lead 裁决 `2026-11-21T16:34`：先做 B（13 项静默优先集），A、C 排后不取消。
范围：SoftwareAES / AppleKeyStoreState / ShengPreflight，以及 205 个 prelink 指针槽里的「首次失败静默」子集。
不在范围：XnuPrelink、DarwinBoot（Lead 自己的线）。
全部结论离线取得：没有构建，没有上机。

---

## 0. 基线与两个数字

- **205 个指针槽 = 203 个不同目标地址 + 2 个被两个 bundle 共用的地址**（`0xfffffff00b430ab8`、`0xfffffff00b430bd4` 各被 `IOHIDFamily` 与 `IOStorageFamily` 持有）。`kernel.json` 的 `stubbed` 数按地址去重是 203，`unreachable.toml` 按槽位计是 205；任何一处写一个数字，同段必须给出另一个。
- 本板 build 20（2026-11-21 06:33）的 `kernel.json`：`missing` 3 项 / 3 bundle，`stubbed` 203 项 / 25 bundle。16:16 重建后 `candidate_sha256` 仍是 `dee01c54a73edf59…`、93,061,120 B ⇒ 计数与 13 项集合对当前产物同样成立。
- 上游 iPad17,3 `ipados-27.0.1-24A446` 基线：2 missing / 24 stubbed。本段的目标是「不比基线差 + 每项有机制说明」，不是清零。
- `missing` 与 `stubbed` 是两套机制：`missing` 是没找到映射（emitter 默认直接拒绝发射，`--allow-missing` 才继续），`stubbed` 是找到了映射关系但目标被重定向到桩。13 项**全部是 stubbed**。
- `scripts/check-ios27-artifacts.py:551-575` 的 `flight_ready()` 在任何 `missing`/`stubbed` 非零、任何 blocker 未关、`check-prelink-regressions.py` 报增长时一律拒绝放行。所以「把某项从 open 改 closed」不能靠在 emitter 侧放宽阈值。

**行号约定**：B 段所有 `osfmk/…`、`libkern/…`、`security/…`、`libsa/…`、`bsd/…` 的行号一律以 16:16 内核的构建快照为准，即
`/opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/tree/build/xnu/fileset-reference/snapshot-040b7fc83b90e0c9/source/`（下文简称 **SN**）。
同三处在 `E:/hackios/xnu-12377` 检出里是 `startup.c:582/:627/:802`，而 `unreachable.toml` / `PRELINK-RESIDUE.md` 用的是更早一版（`:478/:526/:689`）。三套行号不要混用；引用时写清是哪一套。

---

## B. 13 项静默优先清单

### B.1 机制：桩不是「返回」，是 `panic`

`E:/hackios/UniXNU/patches/xnu-12377/fileset-unmapped-call.patch:13-19` 新增了桩本体：

```c
__attribute__((noinline, noreturn, used))
void
unixnu_fileset_unmapped(uint64_t arg0, uint64_t arg1)
{
	panic("fileset: original component called an unmapped kernel function from %p (x0 0x%llx x1 0x%llx)",
	    __builtin_ptrauth_strip(__builtin_return_address(0), 0), arg0, arg1);
}
```

三条推论，全部决定后面的写法：

1. 任何一项被调用 ⇒ **立刻停机**，不是「少一个功能、继续跑」。
2. panic 串里带**原始调用点**（kext 里的 `bl` 返回地址，已做 ptrauth strip）与 `x0`/`x1` ⇒ 一次触发就把「哪个 bundle 的哪个函数、在什么阶段、要什么参数」变成可读记录。
3. 因此「静默」只能指**不上日志**，不能指「没有信息」。信息在屏上；拿不到日志不等于没线索。

产物核对（16:16 的 `kernel/kernel.macho`）：`llvm-nm-18 -m` 给出
`fffffff00b4687b4 (__TEXT_EXEC,__text) external _unixnu_fileset_unmapped`；`strings -a | grep -c 'fileset: original component called an unmapped kernel function'` = `1`。桩是真实代码，不是空符号。

### B.2 触发时刻：审计的「从 `code_signing_init()` 进入」不成立

`unreachable.toml` 每一行的 `reason` 都写「kernel 从 `code_signing_init()`（`osfmk/kern/startup.c:526`）进入该闭包」。**在本构建里这句话是错的**，B 段的优先级论证不能建在它上面：

- `bsd/kern/code_signing/xnu.c:56-61`（`!CODE_SIGNING_MONITOR` 分支）里 `code_signing_init()` 的函数体只有一句 `lck_mtx_init(&compilation_service_lock, …)`。它不启动任何 kext，也不进 MACF。

真正的路径（逐行，全部在本构建快照里核对过）：

1. `osfmk/kern/startup.c:806` `PE_init_iokit()` —— 在 `kernel_bootstrap_thread()`（`:704`）里，这是**第一个 kext 启动点**。
2. `:822` `initialize_screen(NULL, kPEAcquireScreen)` —— 进度显示开始。
3. `:835-836` `kernel_bootstrap_log("mac_policy_initmach"); mac_policy_initmach();`
   `security/mac_base.c:365-381`：`mac_policy_initmach()` 调 `load_security_extensions_function()`，**然后** `mac_late = 1`。
4. `libsa/bootstrap.cpp:505` `KLDBootstrap::loadSecurityExtensions()`：遍历 `com.apple.*` 且 `AppleSecurityExtension == true` 的 kext，`OSKext::loadKextWithIdentifier(bundleID, /*allowDefer*/ false)`。
5. `libkern/c++/OSKext.cpp:8497-8551`：`OSKext::start()` 里 `startfunc` 成功后，若 plist 有 `_NativePrelinkEarlySecurityInit`，先校验四个条件（`mac_late == false`、`isPrelinked()`、`AppleSecurityExtension == true`、目标地址落在该 kext 的 RX 段内），再 `blr x16`，`x16 = 0xfffffff00921000c`（AMFI 的 `initializeAppleMobileFileIntegrity`）。
6. AMFI 的初始化代码执行中解引用 13 个 `__auth_got` 槽 → 各自位点指向已桩掉的目标 → `unixnu_fileset_unmapped` → panic。

所以 13 项的窗口是 **[`PE_init_iokit()` `:806`，`bsd_init()` `:926`)**，紧贴在 `mac_policy_initmach()`（`:836`）上。这也解释了为什么这 13 项排在 205 里所有其它项之前：其它 24 个 bundle 的槽要等各自 kext 在 `bsd_init` 及其后 start 才被解引用，而这 13 槽在**第一个安全扩展 start 的那一刻**就被解引用。

两处需要一起修的旧说法：

- 「no kext code before `PE_init_iokit()`」对普通 kext 成立，但 **MACF 安全扩展在 `mac_policy_initmach()` 里被提前 start**（`:836`），早于 `bsd_init`，且不违反 `console_init()`（`:585`）在前的顺序。
- 「`code_signing_init()` 之后」这个措辞要保留意义的话，应写成「`code_signing_init()`（`:630`）之后、`bsd_init()`（`:926`）之前」。

第二个必要条件：`mac_late == 0`。`mac_policy_initmach()` 调完 loader 立刻置 `mac_late = 1`，这条路一次性；任何「晚一点再试」的补丁都进不来，只能靠 `_NativePrelinkEarlySecurityInit` 或改 AMFI 自身。

审计侧已按 Lead 裁决（2026-11-21）改在生成器里，而不是手改产物：`E:/k60-work/scratch/stubs/classify.py` 的 `mechanism()`、`unreachable.toml` 的 stanza `reason`、`REPORT.md` 的 Headline 三处都换成上面这条链，并在同一句里保留「早前写法说 `code_signing_init()`，实际只初始化互斥量」的撤回说明。重新生成后计数不变（`stubbed 205` / `items=205 keys=203 bundles=25` / `earliest-post-console=3` / `baseline-targets=55`），`classify.py check` 仍 `check: OK`，`scripts/check-osservices27-silent13.py --strict` 仍 `TESTS OK 48 cases`。`unreachable.toml` 里已无 `enters from code_signing_init()`（0 处），13 行新措辞都在。

### B.3 可观测性：这次为什么是「黑屏 + 0 字节」

三条输出通道，各自有独立开关：

1. **F2 预热条**（`patches/xnu-12377/0542-k60-f2-start-breadcrumbs.patch`）：MMU 未开时直接往 framebuffer 涂三条（红 / 黄 / 青）。宏第一句是 `ldr x9, [args, #0x28]`（`boot_args.Video.v_baseAddr`）后 `cbz x9, 9f` ⇒ **`v_baseAddr == 0` 时一条都不涂**，屏保持全黑。
2. **panel 文本控制台**（`patches/xnu-12377/0543-k60-ios27-panel-console.patch`）：改 `pexpert/arm/pe_init.c` 的 `PE_create_console()`，当带 `-v`、video 参数齐、`v_depth == 32` 时把 `v_baseAddr |= 1`（告诉 `vc_attach` kernel_map 已存在、framebuffer 需要内核映射），再 `PE_initialize_console(&PE_state.video, kPETextMode)` + `kPEAcquireScreen`。`PE_create_console()` 由 `osfmk/arm/arm_init.c:627` 调用，早于 `kernel_bootstrap()`。
3. **串口 / USB**：`osfmk/console/serial_console.c:122-131` 的 `cons_ops[]` 索引 0 是 serial、1 是 video，默认 `cons_ops_index = VC_CONS_OPS`（video）。`osfmk/arm/arm_init.c:621-626` 只有 `(serialmode & SERIALMODE_OUTPUT) && serial_exists` 才 `switch_to_serial_console()`；K60 没有 UART ⇒ `serial=3` 既不会抢走输出，也不会产生任何字节。USB CDC-ACM 要等 `bsd_init` 之后的 USB 栈。**「0 字节日志」是结构性的，与内核是否运行无关。**

一次上机就能把四种情况分开（这是 13 项最高优先级的真正理由：它们是唯一能用「屏上有没有那行字」把「内核没跑」和「内核跑到安全扩展」分开的类别）：

| 屏上看到 | 结论 | 下一步 |
| --- | --- | --- |
| 全黑、无 F2 条 | `boot_args.Video` 没传进来，或 `v_baseAddr == 0` | 查 firmware / DarwinBoot 的 video 参数，与 13 项无关 |
| 有 F2 三条、无白字 | 停在 `common_start` 与 `console_init()` 之间（`arm_vm_init` / `PE_create_console` / `initialize_screen` 的 framebuffer 映射） | 查 0543 的 `v_baseAddr |= 1` 与映射条件 |
| 有白字，最后一行是 `panic`，含 `fileset: original component called an unmapped kernel function from 0x…` | 13 项之一被触发 | 用返回地址在 B.4 表里定位，按 B.6 收证据 |
| 有白字，最后一行是 `NativePrelink: …` 或 `Kext … early security initializer failed: …` | 不是桩，是 early init 的四道守卫之一（`mac_late` / 段校验 / 返回值） | 按 `OSKext.cpp:8501-8540` 逐条查 |

本表第二、三行是**待证假设**，写在这里是为了让一次上机同时验证三件事，不是当结论用。

飞行时照着读的版本是单页 [`osservices-27-screen.md`](osservices-27-screen.md)（六行判据 + 抄录清单 + 回填位置）；本节保留论证，那一页只留「现象 → 结论 → 命令」。

### B.4 13 项清单

槽位级（13 行）。`site` 是 kext 里的 `__auth_got` 槽位地址；`加载点` 是解引用该槽的函数与偏移（全部在 `mac_policy_initmach()` 的 early security init 闭包内）；`baseline` 是 bundle 级判定，见 B.7。

| # | site（槽位） | bundle | 目标 | 加载点 | baseline | 目标身份（假设） |
| ---: | --- | --- | --- | --- | --- | --- |
| 1 | `0xfffffff007f0dcd0` | AppleARMWatchdogTimer | `0xfffffff00b4320d8` | `0xfffffff00864e320`+0x2c | true | unknown |
| 2 | `0xfffffff008074ce0` | AppleImage4 | `0xfffffff00b4320d8` | `0xfffffff008fdbaf4`+0x38 | true | unknown |
| 3 | `0xfffffff0080c7e78` | AppleMobileFileIntegrity | `0xfffffff00b4320d8` | `0xfffffff00920929c`+0x288 | false | unknown |
| 4 | `0xfffffff0083ae748` | Image4 | `0xfffffff00b4320d8` | `0xfffffff00a86cb84`+0x38 | true | unknown |
| 5 | `0xfffffff0083c1db0` | sandbox | `0xfffffff00b4320d8` | `0xfffffff00a8e1350`+0x138 | false | unknown |
| 6 | `0xfffffff007f0dce8` | AppleARMWatchdogTimer | `0xfffffff00b432308` | `0xfffffff00864b8fc`+0x7d4 | true | `DTGetProperty` 家族（probable） |
| 7 | `0xfffffff008074ce8` | AppleImage4 | `0xfffffff00b432308` | `0xfffffff008fee294`+0x5c | true | 同上 |
| 8 | `0xfffffff0080c7e80` | AppleMobileFileIntegrity | `0xfffffff00b432308` | `0xfffffff00920929c`+0x260 | false | 同上 |
| 9 | `0xfffffff0083ae750` | Image4 | `0xfffffff00b432308` | `0xfffffff00a86cdf0`+0x70 | true | 同上 |
| 10 | `0xfffffff0083c1db8` | sandbox | `0xfffffff00b432308` | `0xfffffff00a8e1350`+0x110 | false | 同上 |
| 11 | `0xfffffff008074e20` | AppleImage4 | `0xfffffff00b11a998` | `0xfffffff008fd8f50`+0x20 | true | `_code_signing_configuration`（probable） |
| 12 | `0xfffffff0080c8060` | AppleMobileFileIntegrity | `0xfffffff00b11a998` | `0xfffffff00920929c`+0x2c | false | 同上 |
| 13 | `0xfffffff0083ae858` | Image4 | `0xfffffff00b11a998` | `0xfffffff00a869f48`+0x21c | true | 同上 |

目标级（3 行）：

| 目标 | 大小 | 项数 | bundle 数 | 静态锚点 | 状态 |
| --- | ---: | ---: | ---: | --- | --- |
| `0xfffffff00b4320d8` | 28 | 5 | 5 | `_get_arm_cpu_version`（`0xfffffff00b431f70`）+360，其后无任何已匹配函数 | unknown |
| `0xfffffff00b432308` | 664 | 5 | 5 | 同上锚点 +920 | probable |
| `0xfffffff00b11a998` | 240 | 3 | 3 | `_code_signing_deallocate`（`0xfffffff00b11a890`）+264 / `_disable_code_signing_feature`（`0xfffffff00b11aa88`）−240 | probable |

三个目标都不在 `kernel.map.json` 的 16,899 个已匹配原始函数里（`in_map=False`），所以它们的身份不能靠常量偏移配对拿到（`PRELINK-RESIDUE.md` 已把那条路关掉），只能靠运行时命名，或与 24A446 fixture 的链接顺序 / 大小 / shape 比对。

### B.5 三个目标的身份：假设与证伪

- `0xfffffff00b4320d8`（28 B，5 项）：`unknown`。静态锚点是 `kernel.map.json` 里**最后一个**被匹配到的原始函数 `_get_arm_cpu_version`（`0xfffffff00b431f70`，native `0xfffffff007542bb0`，how=`reference-symbol`）**+360**，它之上再没有任何匹配到的函数 ⇒ 位于「我们从未匹配过的尾部」。`REPORT.md:100` 把它归到 pexpert device tree。
- `0xfffffff00b432308`（664 B，5 项）：同锚点 **+920**。664 B 的可执行体量与 `DTGetProperty` 一类 getter 相称（`REPORT.md:101` 判 probable）。其加载点 `0xfffffff00864b8fc`+0x7d4 还用到字符串 `wdt-version` / `reconfig-wdog-support`，说明这段是 watchdog 读 DT 属性的代码。
- `0xfffffff00b11a998`（240 B，3 项）：夹在 `_code_signing_deallocate` 与 `_disable_code_signing_feature` 之间，与「probable `_code_signing_configuration`」一致（`REPORT.md:105`）。

每一条都可被证伪，且证伪方式都离线可见或一次运行可见：

| 假设 | 证伪方式 |
| --- | --- |
| 目标 1/2 是 pexpert DT getter | 上机 panic 打印的 return address 若落在 `0xfffffff00864e320`… 之外的函数，则「watchdog 读 DT」这条具体路径错了（目标仍可能是别处的 DT getter） |
| 目标 3 是 `_code_signing_configuration`（数据对象） | 反汇编 `0xfffffff00920929c`+0x2c 处的用法：若把槽当结构体指针 `ldr x?, [x?, #off]` 用，假设成立；若直接 `blr`，则目标是函数、假设错 |
| 三者的加载点都在 `mac_policy_initmach()` 闭包内 | 若某条的调用点不在 AMFI 的 early init 调用图上（例如只在 user client 路径），则该条要被移出「静默优先」集，降到普通 205 项 |

### B.6 逐项验证方法：离线三件 + 上机一件

每一行共用同一套四法；具体命令与判据：

1. **静态比对（static）**——目标缺席 + 锚点 + 槽位绑定
   `kernel.map.json`：三个目标 `in_map = False`，锚点与距离如 B.4 表；`sites_chain.json` / `unreachable.toml`：13 个 `site` 与 `target` 的绑定逐行一致（`__auth_got` 槽解码所得）。
   判据：13/13 绑定一致；`0xfffffff00b4320d8`/`0xfffffff00b432308` 的锚点距离恒为 +360/+920；目标 3 的左右邻函数恒为 `_code_signing_deallocate` / `_disable_code_signing_feature`。
2. **离线单测（unit）**
   `python3 scripts/check-osservices27-silent13.py --strict`（本线新增，见 §B.8）：断言 13 行集合与 `unreachable.toml` 的 `early_security_init` 过滤结果完全相等、每目标项数 5/5/3、`205/203/25` 声明、每个 `(bundle,target)` 在 `kernel.json` 的 `stubbed` 里且不在 `missing` 里、三个目标不在 `kernel.map.json`、目标 3 的左右邻。
   判据：`TESTS OK`，退出 0；任何一条不等就失败。
3. **产物检查（artifact）**
   `llvm-nm-18 -m kernel.macho | grep unixnu_fileset_unmapped` → `fffffff00b4687b4 (__TEXT_EXEC,__text) external`；`strings -a kernel.macho | grep -c 'fileset: original component called an unmapped kernel function'` → `1`。
   判据：桩在 `__TEXT_EXEC,__text`（真实可执行代码），panic 串在产物里恰好一份。
4. **上机（device，Lead 独占）**
   一次 boot，拍照；按 B.3 的四行判据读屏。若出现 `fileset:` 行，把 `from 0x…` 的返回地址填回 B.4 表对应行，并把该行的状态从 `open` 改 `located`（不是 `closed`，见 C）。

### B.7 baseline 是 bundle 级，不是地址级

- `classify.py:420-433` 的 `BASELINE_BUNDLES` 就是上游 24A446 `prelink-regression.json` 里「容许 stubbed」的 10 个 bundle（AppleARMPlatform、AppleARMWatchdogTimer、ApplePMGR、IOCryptoAcceleratorFamily、IOGPUFamily、IOHIDFamily、IOStorageFamily、IOSurface、AppleImage4、Image4）；`classify.py:1476` 的判定是 `baseline = b in BASELINE_BUNDLES`，即**按 bundle**，不是按地址。
- 13 项里 8 项落在这些 bundle（watchdog 2、AppleImage4 3、Image4 3），5 项落在 AMFI（3）/ sandbox（2）——这两个 bundle 上游从不容许 stubbed。所以若问题变成「本板为什么比 iPad 差」，能解释差异的是那 5 项。
- 但**优先级不按 baseline 排**：这 13 项在同一个 `mac_policy_initmach()` 调用里被解引用，谁先被用到谁先停，与上游是否容许无关。这一点必须写死，否则下一轮会有人拿 baseline=true 把 8 项降级。

### B.8 离线证据（本次运行记录）

1. `classify.py check`（WSL，root 读 `kernel.json`；`kernelcache.decompressed` 77,987,840 B）
   `chain sites 594801, kext-side 548949, outside closure 462405, paired 48553, stubbed 205`
   `items=205 keys=203 bundles=25  (declared 205/203/25)`
   `check: OK`，1.97 s
2. 静态锚点检查（`kernel.map.json`）
   `0xfffffff00b11a998 in_map=False items=3`；prev `0xfffffff00b11a890 _code_signing_deallocate` +264；next `0xfffffff00b11aa88 _disable_code_signing_feature` −240
   `0xfffffff00b4320d8 in_map=False items=5`；prev `0xfffffff00b431f70 _get_arm_cpu_version` +360；next（无，map 最高就是 `0xfffffff00b431f70`）
   `0xfffffff00b432308 in_map=False items=5`；prev 同 +920
3. 产物检查：`fffffff00b4687b4 (__TEXT_EXEC,__text) external _unixnu_fileset_unmapped`；panic 串 1 处
4. `kernel.json`（16:16）：`missing` 3/3、`stubbed` 203/25、`candidate_sha256 dee01c54…`、`early_security_init {AMFI: 0xfffffff00921000c}`、`collection_slide 0x0`
5. 单测：`python3 scripts/check-osservices27-silent13.py --strict`（WSL root 跑，需读 `kernel.json`/`kernel.map.json`）
   `ok - items per target are 5/5/3` … `ok - table triples equal the audit triples` … `ok - target 0xfffffff00b4320d8 sits above the last matched function (0xfffffff00b431f70)`
   `TESTS OK 48 cases`，退出 0

### B.9 与「不比基线差」门槛的关系

- 13 项全部是 `stubbed`；`missing` 的 3 项（AppleARMWatchdogTimer `0xfffffff007044478`、IOHIDFamily `0xfffffff00b72fce8`、sandbox `0xfffffff00b739538`）是另一套机制，不在 B 段。
- 因此「把某一条从 open 改 closed」不能靠放宽 `--allow-missing`：那只会把 panic 变成「同样 panic、计数好看」。判据表见 C 段（待写）。

---

## A. 三组件 27 接入点与依赖

Lead 裁决顺序：B → A → C（2026-11-21）。本段只写**接入点、依赖、以及两个缺失输入怎么离线拿到**；
不写「应该是」，凡未取到的值都标 `unknown` 并给获取步骤（§A.4）。

### A.0 总表

| 组件 | catalog 声明 | 27 现状 | 27 接入点 | 阻塞依赖 |
|---|---|---|---|---|
| SoftwareAES | `components.toml:228`；os_abi 仅 `ipados-17.7.11-21H461`；产物 `build/software-aes/libSoftwareAES.a`；build_stage kernel | 未接入：27 的 `components.include` 只有 ArmDTPlatform/ArmCpu/XnuPrelink（`board.toml:341-410`），`kernel.archives` 八项里没有 software-aes | `[os_overrides."ios-27.0.1-24A446"]` 的 `components.include` + `kernel.archives` | 27 的类布局（vtable 槽数 / 签名 discriminator / `IOAESKeyData.selector` 偏移）是 `unknown` |
| AppleKeyStoreState | `components.toml:250`；os_abi 17.7.11 **与** 27.0.1；产物 `build/apple-key-store-state/libAppleKeyStoreState.a`；board_dependencies `["platform state callbacks"]` | 未接入；它是 6 个 `native_aks_*` 符号的**客户端**，本板无 provider | 同上（`kernel.archives` 加静态库）+ `payload.kernel_args` 需要 `sheng-aks=1`（现在没有） | 符号 provider 不存在；27 的 selector 表是 `unknown` |
| ShengPreflight | `components.toml:534`；os_abi UEFI；hardware Xiaomi Pad 6S Pro；`build = []`、`outputs = []` | 未接入：本板 `board.toml` 无 `[firmware] preflight`；子模块目录空（gitlink `9cfc8d2c…`） | `[firmware] preflight`（`scripts/unixnu/firmware.py` 调它，`--skip-preflight` 可跳，见 `docs/zh/porting/uefi-firmware.md:169-172`） | 输入清单（FV 大小/路径、DTB、内存图）未写成脚本；sheng 的检查拿不到源码 |

### A.1 SoftwareAES：接入点是 ABI 匹配，不是编译期继承

- 27 内核源码里**没有**这两个类：`E:/hackios/xnu-12377` 对 `IOAESAccelerator` / `IOCryptoAccelerator` 全库 0 命中；`xnu-12377/iokit/conf/files:7` 只有 `OPTIONS/crypto optional crypto`。所以类来自 prelinked `com.apple.iokit.IOCryptoAcceleratorFamily`，`drivers/SoftwareAES/OriginalAESABI.h` 的重新声明是唯一通路。
- 该头把形状钉死成硬断言：`sizeof(IOService)==0x88`、`sizeof(IOCryptoAccelerator)==0x88`、`sizeof(IOAESAccelerator)==0x120`、`sizeof(IOAESIV)==16`、`offsetof(IOAESKeyData,selector)==36`、16 个虚函数。这六个值现在是 **16 行实测值**，在 27 上一条都没重测过。
- arm64e 的额外风险：`patches/xnu-12377/series` 第一条就是 `ptrauth-string-discriminator`。vtable 槽仍是 8 B，但槽里是**已签名**指针 ⇒ 槽数与 `sizeof` 断言可以不变，而虚调用要对上 discriminator；否则调用成功但认证失败。这条是 SoftwareAES 在 27 上最容易「断言过、运行炸」的地方。
- 依赖顺序：`IOCryptoAcceleratorFamily` 自身在 205/203 残留里占 **2 项**（25 bundle 名单中有它）⇒ 类族的符号绑定还没闭合；SoftwareAES 的接入必须排在它之后，否则 KAT 计数只会在桩上打转。
- 已知的下游等待关系（他人实现，库内命中）：`E:\hackios\UniXNU\docs\devices\evb10.md`「Development findings」节记着 —— AppleImage4 的 start 会**无超时地等 `IOAESAccelerator`**，没人 publish 时 registry 永远静不下来（"its start waits without a timeout for IOAESAccelerator, which nothing provided, so the registry never went quiet"）。所以 SoftwareAES 不只是「加密服务」：**Image4 / AMFI 的启动顺序依赖它 publish**，而 Image4 自己也在 205 里占 14 项（AppleImage4 7 + Image4 7）。这条把 A.1 与 B 段的 13 项连起来：先 publish，再谈 Image4 的桩。
- 库内检索结论（2026-11-22，规则 2）：`IOAESAccelerator` / `IOCryptoAccelerator` 各 4 条命中，全部是本仓自己的文档（`k60-gates/docs/plans/DOCS-DRIVERS-ALL.md`、`OFFICIAL-DRIVER-MAP.md`、`PRELINK-CLOSURE.md`、`UniXNU/docs/devices/{evb10,uke}.md`），**没有一条给出 27 的类布局** ⇒ 类布局与 selector 表仍是「未证」，走 §A.4 的离线程序。
- 但库内另一条命中给了原始字符串证据（**16 线，非 27**，务必按此引用）：`E:\k60-work\scratch\camera-work\work\kc-strings-clean.txt` 是 20G81 kernelcache（48,644,096 B，sha256 `d260defcc2eaac258fd3a2234454dda46791dae45e97608c5416f9ba8fd366e9`，见 `camera-work/03-reverse-and-device-data.md:6,101`）的 `strings -a -n 4` 产物，其中：
  - `:55206-55228` 有 `IOAESAccelerator` / `IOAESAcceleratorUserClient` / `IOAESAcceleratorCommand` / `IOAESAccelerator::performAES -- unable to prepare plainText error - %08x (%s)` / `IOAESAccelerator.cpp` / `site.*` ⇒ 这两个类确实随 `IOCryptoAcceleratorFamily` 一起发布，`OriginalAESABI.h` 声称的 ABI 面有实物对应；
  - `:55242-55245` 在 `IOCryptoAccelerator` 之后紧跟一行 `12111112122212121` 与 `"subclass is required to implement getAlgorithmName" @%s:%d` ⇒ **17 个类型码**的类元数据行；与 `OriginalAESABI.h` 的 16 个虚函数是「同一类、同一侧」的旁证（17 = 16 + 1 个非虚/元数据槽，或 1 个基类槽，**未定，不作结论**）；
  - `:56079-56080` 有 `IOAESAccelerator` 与 `cannot find IOAESAccelerator` 两条相邻字符串 ⇒ 某个 Apple 二进制在**查不到** `IOAESAccelerator` 时会打这条日志；这与 §A.1 上面 evb10/zizhan 的「Image4 无超时等 AES」互为证据（一条是行为描述，一条是二进制自己的诊断串）。
  - 引用纪律：以上三条只证明 **16 线的类确实存在、槽位数在类元数据里可读、查不到时会打诊断串**；27 的布局与 selector 表**仍未测**，仍由 §A.4 定。
- 待验证（命令已给在 §A.4）：`libkern/crypto/aes.h` 与 `libkern/crypto/crypto_internal.h` 在 12377 是否存在 —— `NativeAES.cpp` include 了它们，本线没有实测。

### A.2 AppleKeyStoreState：先有 provider，再谈 selector

- 它消费 6 个符号：`native_aks_state_enabled()`、`native_aks_lock_state()`、`native_aks_call(sel,rc)`、`native_aks_opened()`、`native_aks_encode_state(out,cap,lockState)`、`native_keyevents_allocate/open_refused`。全仓搜索（UniXNU-sheng / -mondrian / -pong / -zizhan / xnekom-ios27 / k60-gates）**没有任何内核侧定义**；只有 `UniXNU-sheng/package/KeyStoreProbe.cpp`，那是 payload 侧探针，不能链接。
- 它成功的 selector 是 11 个（0、4、5、9、12、13、26、27、55、101、102），其余一律 `kIOReturnError`。27 的 selector 表 `unknown`（§A.4）。
- 两条路线，选一条写进 plan（现在不选）：
  1. **补 provider**：沿 16.6.1 `zzzzzzzzzzzzzzzzzzzzzzzz-pong-software-keybag.patch` 的 `iokit/Kernel/MiniAppleKeyStore.cpp`（281 行、12 selector、`#if defined(PONG) && (DEVELOPMENT || DEBUG) && !SECURE_KERNEL`）搬到 27 的 `iokit/conf/files` + 启动钩子。代价：引入 keybag 语义，要回答「wrap 只是可逆映射」这件事在 27 的 libaks 下够不够。
  2. **只报状态**：不补 provider，明确「无 keybag、`sheng-aks-sls=3` 报无密码」是设计状态，AppleKeyStoreState 在 27 只作为观测点存在。代价：凡是需要 device key 的路径必须另有结论。
- 启动参数依赖：`sheng-aks=1` 与 `sheng-aks-sls` 现在都不在 27 的 `payload.kernel_args` 里（`board.toml:341-410` 只有 `-v serial=3 debug=0x14e kt_fixed_zones=120 -no_slto_panic use_contiguous_hint=0 amfi_get_out_of_my_way=1 k60_fontscale=3`）⇒ 即使库接进去也会走「未启用」分支。

### A.3 ShengPreflight：机制在，检查项不在

- 框架侧机制是现成的：`[firmware] preflight` 里的脚本在 EDK II 构建前跑，`--skip-preflight` 可跳过，输入要带 hash 校验（`docs/zh/porting/uefi-firmware.md:169-172`；构建顺序「1 preflight → 子模块 → BaseTools → 补丁 → 构建 → 还原 → 查 FV 大小/路径」）。
- 本板缺的是**检查项**：`board.toml` 的 `[firmware]` 只有 `dsc = Platforms/Xiaomi/mondrianPkg/mondrian.dsc` 与 packages 列表，没有 `preflight` 键；`drivers/ShengPreflight` 是空子模块（gitlink `9cfc8d2c…`），sheng 的 `board.toml` 里也没有 `[firmware]` 表 ⇒ 没有可抄的现成脚本，只能按本板目标写。
- 本板可写的三条（依据在 27 profile 与 flight blockers 里，不靠猜）：
  1. **FV 大小**：产物 FV 必须与 `[uefi_fd] size` 对得上（`uefi-firmware.md` 验证表）；现存 `firmware-fileset-provider` 已 closed（uefi-mondrian 39fa61c，PE 55,296 B，sha256 `52b064d6…`），可作基线哈希。
  2. **加载窗口**：platform27 现在的怀疑是 256 MB 载入窗口压掉 framebuffer；预检应给出「载入窗口 + ADT `video` 节点 + FV 末端」三者的数值关系，超界即失败。这一条与 B 段第 1/2 行判据直接互补。
  3. **启动输入**：`payload.adt.chip_id = "8140"`、`random_seed = "11"`、`root_match_volume_uuid = E3F4AED0-…` 与 27 profile 的 `roots`（30 项）必须一致；不一致时预检失败比黑屏便宜。

### A.4 两个缺失输入：怎么离线拿到（不许用 24A446 猜）

**输入 1：`IOCryptoAcceleratorFamily` 的类布局（vtable 槽数 / 判别器 / `IOAESKeyData` 偏移）**

1. 用**本板** prelink 后的 `kernel.macho`（kext 侧仍有符号表；Apple kernelcache 是 `LC_SYMTAB nsyms 0`，读不到名字 —— 所以不要先拿 24A446 反汇编去猜）。
2. `llvm-nm-18 -m kernel.macho | grep -i 'IOCryptoAccelerator\|IOAESAccelerator'` → 有 `__ZTV…` 就拿到 vtable 符号；没有则按「`IOAESAccelerator` 16 字符」拼 `__ZTV16IOAESAccelerator` 再试。
3. `llvm-objdump-18 --macho --section=__TEXT,__const`（或该 kext 的 `__DATA_CONST`）读 vtable：长度应为 `2 + 16` 槽 = 0x90 B；逐槽取归属函数地址，按 `OriginalAESABI.h` 的顺序核对（`getAlgorithmName` → 两个 `performAES` 重载 → `isKeySupported` → `getSupportedOptions` → …）。
4. `IOAESKeyData.selector` 偏移：在 `performAES` 的调用者里找该参数结构的字段装载（`ldr w?, [x?, #0x24]`），0x24 = 36 即为对上。
5. **通过判据**：槽数 18、顺序一致、偏移 0x24。**任一不符** ⇒ 不接 SoftwareAES，改走 ABI 探测（`native_aes_kat_status` 计数 + `_unsupported_key`），并在 §C 记 `unknown`。

**输入 2：27 的 AKS selector 表**

1. 先在 27 profile 的 30 个 `roots` 里确认 `com.apple.driver.AppleKeyStore` 是否在列；不在列就说明 27 stage-0 根本没加载 AKS kext，此时「selector 表」对 stage-0 无意义，AppleKeyStoreState 的接入应直接降级为路线 2（只报状态）。
2. 若在列：在 `kernel.macho` 里找该 kext 的 `externalMethod`（selector 比较链）或常量表，逐个 case 记 `selector → 返回码`；与 AppleKeyStoreState 的 11 个成功 selector 求差。
3. **通过判据**：差集为空，或只差在「不产生输出」的 bookkeeping 类。**不通过** ⇒ 要么扩成功集（须有调用者证据），要么维持 11 个并在 §A 记 `unknown`；**不许**为了让用户态不报错而把 `kIOReturnError` 改成 `kIOReturnSuccess`（那是把「没实现」伪装成「实现了」）。
4. 附带验证：`xnu-12377` 只有 `iokit/Kernel/i386/IOKeyStoreHelper.cpp` 与 `iokit/IOKit/AppleKeyStoreInterface.h`，没有 ARM 实现 ⇒ 表只能从 kext 取，不能从源码读。

## C. open→closed 判据表（待写）

将按「一条判据只能由一种证据满足」写死，至少包含：`located`（上机 panic 返回地址命中）/ `named`（运行时命名或 fixture 比对）/ `mapped`（emitter 真的把目标映射到本板函数，`check-prelink-regressions.py` 计数下降而不增长）/ `exercised`（该路径在本板跑过且无 panic）四档；并写死「禁止通过放宽 `--allow-missing`、改 `stub_symbol`、或把 bundle 从 `roots` 里删掉来降计数」。
