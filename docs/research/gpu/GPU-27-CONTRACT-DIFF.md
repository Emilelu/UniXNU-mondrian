# GPU 27 契约差异表（16.6.1 / 20G81 → iOS 27 / 24A446）

| 项 | 值 |
| --- | --- |
| 线 | 官方 porting 表第 5 行「GPU 与 Metal」 |
| 分支 / 树 | `feat/gpu-27` / `E:/hackios/k60-gpu-27` |
| 16.6.1 侧 | 20G81 kernelcache（`/opt/k60/trees/gates-out/ipsw/20G81/kernelcache.decompressed`，48,644,096 B，经典 prelink）+ 本树 `drivers/PongAdreno`、`drivers/PongMetal`、`drivers/PongAdreno/submit` |
| 27 侧 | 24A446 kernelcache（`/opt/k60/trees/ios27-out/ipsw/24A446/kernelcache.decompressed`，77,987,840 B，MH_FILESET，sha256 `38e6d9fa5f789b8228f4617ef4c6d2a3fd8ab564abdc9b62920f1db53fc1780a`）+ 官方树 `drivers/Adreno740`、`drivers/AdrenoMetal`、`kits/` + `UniXNU-sheng/package`（板级配方，实际执行 hw_init 的地方） |
| 官方口径 | `porting/gpu.md`（`docs/zh/porting/gpu.md`，171 行）、`porting/gpu-diagnostics.md`（76 行）、`drivers/adreno740.md`、`drivers/adreno-metal.md`、`drivers/adreno-firmware.md`、`drivers/adreno-pm4.md`、`drivers/air-nir.md`、`drivers/sm8550-platform.md`、`drivers/community-adreno830.md` |
| 状态 | **`done=false`**——本表逐行给出 27 侧读数，但用户态 selector 全集仍 unknown（§10），八步 ⑦ `verify` 保持 `false` |

## 0 这份表怎么读

每条一行，四件事必须同时在场：

1. **16.6.1 读数**：本树的 `文件:行`，或 20G81 的 JSON/Mach-O 产物。
2. **27 读数**：24A446 的 JSON/kernelcache，或官方树的 `文件:行`；没有就写**「27 侧不存在」**，并说明 27 上这件事由谁承担。
3. **判定**：相同 / 不同 / 只在 27 侧存在 / 只在 16.6.1 侧存在。
4. **官网页锚点**：`gpu.md` 有 `{#anchor}` 的六个位置（`#source-map:9`、`#memory-path:65`、`#scheduling:88`、`#render-mode:96`、`#frame-path:106`、`#shader-warmup:151`）可以直接引；`gpu-diagnostics.md` 与全部 driver 页**没有锚点**，只能按「页 + 小节标题 + 行号」引。

证据等级（每行末列）：

- **A** —— 双侧可执行证据（`文件:行`、JSON 字段、Mach-O/kext 名）。
- **B** —— 一侧有代码，另一侧只有官方文字（页/kit 注释），结论依赖文字与代码一致。
- **C** —— 只有推断，必须上机 A/B 才能定；**本表不把 C 当结论用**。

本表**不做**的事：重跑 16.6.1 已量化的事实（present 分解、三项收益、四个被推翻的假设都按原记录引用，不重测）；不申请 pitfall 号；不写实现。A730 与 A740 的 HWCg 差异单独成表（§7.2），因为它是唯一一组「整包搬 27 会静默改变硬件行为」的差异。

## 1 结论（先给能直接拿去判断的）

1. **`IOAcceleratorES` 基类 ABI 在 16.6.1 与 27 之间没有变化**：136 B 实例、168 个虚方法槽、覆写集合都是 `[0,1,7]`、metaclass 由 `IOGPUFamily` 以 size `0x88` 构造。变的只有 slide 之后的地址。⇒ 我们 16.6.1 的 accelerator 骨架可以原样作为 27 的起点（§2）。
2. **两代都没有 Adreno 专属 GPU kext**：20G81 是 `com.apple.AGXG9G`，24A446 是 `com.apple.AGXG17P`，都是 Apple 自家 GPU 家族。⇒ accelerator 类在两代都必须由我们提供，这不是 27 新增的负担（§2.6）。
3. **kernel↔userclient 的 wire ABI 从 v1 升到 v2**：`MaxBuffers` 16 → 128，`sizeof(NativeAdrenoAbiSubmit)` 416 → 3,104 B。其余每个 struct 的断言值两侧完全相同。⇒ 这是本线**最便宜也最必要**的一次迁移，也是「27 上 Turnip 一帧拆多 IB」的前提（§5）。
4. **我们的 Metal 前端是官方件的落后副本**：同一段 `_MTLAddDevice` 注释在官方件 `:1573`、在我们的 `:1281`，整体差约 292 行；`newCommandQueueWithMaxCommandBufferCount:` 的实现体两侧一致。⇒ 27 迁移按「重新 vendor 官方件」处理，不逐行补丁（§4）。
5. **hw_init 在 27 侧不在 driver kit 里执行**：`drivers/Adreno740/` 只有 `NativeAdrenoA740HwInit.h` 里的表，没有任何 `.cpp` 写这些寄存器；真正执行的是 `UniXNU-sheng/package/GpuPowerProbe.cpp:1568 gpuHwInit()`。⇒ 27 上「谁写硬件寄存器」的答案变了，这是移植时最容易漏的一条（§7.1）。
6. **我们 16.6.1 的 HWCg 表 = a730_hwcg 逐条照抄，只有 1 个值取自 A740**（`RBBM_CLOCK_CNTL3_TP0`）。A740 表相对 A730 有 12 处差异（9 处值不同、2 个寄存器 A730 表里没有、1 个 A740 表里没有）。⇒ 整包搬 27 会把这 12 处全部改掉，其中两处是「我们从不写而 27 会写」，一处是「我们写而 27 不会写」（§7.2）。
7. **同一段 hw_init 里 CGC 模式和顶层使能的写法都不同**：CGC mode 我们 `0x20000`、27 板级 `0x00020202`；顶层使能我们无条件写两次，27 先判断再写（hang 重启幂等）。⇒ 27 侧的重启路径比我们严谨，照抄它不会更糟（§7.3）。
8. **GMU 调档在 27 侧被挪到板级配方**：`drivers/Adreno740/*.cpp` 里没有任何 HFI 调档（`grep -i vote` 为空），27 的调档是 `UniXNU-sheng/package/ShengGmuVotes.c` 的 `ShengGmuBuildStartup`/`ShengGmuPerfVote`。⇒ 我们 `PongAdrenoGmu.c:260` 的 HFI id 30 在 27 上要么并入板级投票，要么保留但不再有官方对照（§8.3）。
9. **扫出 wire 与 zizhan 的布局不兼容却共用版本号 1**：我们是 48 B（`reserved`），zizhan 是 56 B（`token,evict,target`）。⇒ 27 定零拷贝 wire 时必须升版本号，否则跨树混用会静默错读（§9.4）。
10. **27 侧帧路径只有测量口径，没有代码**：`#frame-path:106-120` 规定七段，我们只测五段（缺「完成到回调」「显示更新」）。⇒ 120 fps 预算表要先补这两段才有 27 的判据（§9.1）。

## 2 A 组：类布局

| # | 契约面 | 16.6.1 | iOS 27 | 判定 | 官网页锚点 | 等 |
| --- | --- | --- | --- | --- | --- | --- |
| A1 | `IOAcceleratorES` 实例大小 | `drivers/PongAdreno/PongIOAcceleratorABI.h:4-11`「Actual 20G81 IOAcceleratorES: 168 IOService slots, no operational overrides, 136-byte instance」，`static_assert(sizeof(IOService)==136 && sizeof(IOAcceleratorES)==136)` | `scripts/data/ioaccelerator-base-abi-24A446.json`：`instance_bytes=136`，evidence 记 `constructs IOAcceleratorES::gMetaClass with size 0x88` | **相同** | `porting/gpu.md#source-map:16-18`；`drivers/adreno740.md`§运行路径:5-9 | A |
| A2 | 虚方法条目 | 同上，168 | 同上 JSON `virtual_entries=168` | 相同 | 同上 | A |
| A3 | vtable 与地址点 | `ioaccelerator-base-abi.json`：`vptr=0xfffffff005d439a0`、`metaclass=0xfffffff006aeb688` | `…-24A446.json`：`vtable=0xfffffe000832f2e8`（`+0x10` address point）、`metaclass=0xfffffe000bb3f290` | 形状相同，仅 slide 后地址不同 | 同上 | A |
| A4 | metaclass 构造 | 我们只在名字查不到时补构造：`drivers/PongAdreno/PongAdrenoAccelerator.cpp:21-22` 取 `IOAcceleratorES` 的 `OSMetaClass`，`:31` `PongIOAcceleratorMetaConstruct((void*)&IOAcceleratorES::gMetaClass)` | `IOGPUFamily` 静态初始化器 `0xfffffe000a14da80` 构造 `IOAcceleratorES::gMetaClass`（JSON evidence 原文） | 相同（都由父类自己提供，我们只做兜底） | `#source-map:16-18` | A |
| A5 | 地址是否需要减 slide | 20G81 是经典 prelink，`llvm-nm` 直接给可用地址 | 24A446 是 MH_FILESET + `collection_slide=0x1f000000000`；本表所有 27 地址都是**slide 后**值 | 判定方法不同，数值不可直接比较 | — | A |
| A6 | 随 OS 附带的 GPU 驱动 | `com.apple.AGXG9G`、`AGXFirmwareKextG9GRTBuddy`、`AGXFirmwareKextRTBuddy`、`com.apple.AGXCompilerService`（20G81 `grep -a -o`） | `com.apple.AGXG17P`、`AGXFirmwareKextG17PRTBuddy`、`AGXFirmwareKextRTBuddy64`、`AGXCompilerService`（24A446 同法） | **两代都没有 Adreno 类** ⇒ accelerator 必须我们提供 | `porting/gpu.md`§1:26-27（匹配 GPU 代际与 OS ABI） | A |

**这条链的意义**：27 并没有把 GPU 的类布局改难，改难的是「谁在什么时候把类挂上去、谁的 userclient 能连上」。A 组因此可以判定为**零工作量**，除非 §5 的 ABI 升级触动了 accelerator 的实例大小（它不会：wire ABI 只在 `submit/` 里）。

## 3 B 组：虚方法槽位与发布时序

| # | 契约面 | 16.6.1 | iOS 27 | 判定 | 官网页锚点 | 等 |
| --- | --- | --- | --- | --- | --- | --- |
| B1 | 覆写的槽位 | `metadata_overrides=[0,1,7]`（20G81 JSON） | `overrides=[0,1,7]`（24A446 JSON） | 相同 | `#source-map:16-18` | A |
| B2 | 槽位 0/1/7 的实际符号 | JSON：ctor `0xfffffff004bd3b20`/`…b40`、非删除析构 `…b64`、`getMetaClass` `…bac` | JSON：ctor `0xfffffe000a14d990`/`…d9c8`、析构 `0xfffffe000a14da00`、`getMetaClass` `0xfffffe000a14da70` | 三个槽的功能一一对应 | 同上 | A |
| B3 | 发布时序 | `drivers/PongAdreno/PongAdrenoNativeGlue.cpp:146` 注释「Before native_adreno_publish(), because the published client may submit immediately」；`:155` publish、`:158` `PongAdrenoConfigureService(native_adreno_published_service())` | `drivers/Adreno740/NativeAdrenoPublish.cpp:736` 同签名 `native_adreno_publish(NativeAdrenoVm*,NativeAdrenoSubmit*,NativeAdrenoRing*,…)`、`:740` 参数校验返回 `kIOReturnBadArgument`、`:748` 先置 `g.service/g.published`、`:750` `registerService()` | 语义一致：先让 client 能提交，再暴露服务 | `#memory-path:65-86`；`drivers/adreno740.md`:5-9 | A |
| B4 | 运行时是否真的按名字查父类 | 我们按 `OSSymbol("IOAcceleratorES")` 查（`PongAdrenoAccelerator.cpp:21-22`），查不到才兜底 | 未读 dyld 侧证据；27 侧只有 kernelcache 里 `IOGPUFamily` 注册该类的证据 | **未定**（不影响 A 组结论） | — | C |

## 4 C 组：selector 面（Metal 用户态）

| # | 契约面 | 16.6.1 | iOS 27 | 判定 | 官网页锚点 | 等 |
| --- | --- | --- | --- | --- | --- | --- |
| C1 | `newCommandQueueWithMaxCommandBufferCount:` | `drivers/PongMetal/NativeBridgeMetalFrontend.mm:1340` `{(void)count;return [(id<MTLDevice>)self newCommandQueue];}` | `drivers/AdrenoMetal/NativeBridgeMetalFrontend.mm:1632` **同一行实现体** | 实现相同；名额语义按 `drivers/adreno-metal.md`:7-17 | `drivers/adreno-metal.md`§渲染和接口:5-17 | A |
| C2 | `_MTLAddDevice` 注册流程 | 我们副本 `:1281`「The original discovery (_MTLAddDevice) runs these four on every device it registers…」 | 官方件 `:1573` 同一段文本 | 官方件比我们多约 292 行前置内容 ⇒ **我们的 vendored frontend 落后** | `drivers/adreno-metal.md`:5-19 | A |
| C3 | private device protocol 断言 | 我们副本 `:1573` | 官方件 `:1869` | 同 C2（位差 296 行） | 同上 | A |
| C4 | 我们的扫出 presenter 用哪条 selector | `drivers/PongMetal/GpuScanoutPresenter.h:34` `queue_ = [device newCommandQueue];` | 27 侧要求名额语义（`newCommandQueueWithMaxCommandBufferCount:`，`drivers/adreno-metal.md`:7-17） | **我们没走名额路径** ⇒ 27 门禁必须检查 maxCommandBufferCount | `drivers/adreno-metal.md`:7-17 | B |
| C5 | `MTLLanguageVersion3_1` 缺可用性守卫 | 两侧 `grep MTLLanguageVersion` 均**无命中** | 同 | **旧记录失效**：该假设不再引用（连同 16-专属三 selector 一并按 `docs/engineering/IOS-SCOPE.md` 停做） | — | A |
| C6 | 运行时 selector 全集（谁给谁发什么消息） | unknown | unknown（缺 24A446 `dyld_shared_cache_arm64e`） | 见 §10；不影响 C1–C4 | `porting/gpu-diagnostics.md`§保留的证据:11-21 | C |
| C7 | 编码失败仍返回 encoder | 桥接层从不返回 nil encoder（`porting/gpu.md`§4:124-149 原文） | 同 | 一致 | `porting/gpu.md`:124-149 | B |

C 组的结论：**能定的是「代码面的 selector 集合」，不能定的是「运行时谁真的发了它」。** 这与 Lead 接受 unknown 的口径一致；§10 给可执行证据链。

## 5 D 组：参数结构（kernel ↔ userclient wire ABI）

两个头文件是同一族的两个版本，`diff -u` 只有两处 hunk，这是本线最干净的一条差异：

| # | 契约面 | 16.6.1（`drivers/PongAdreno/submit/NativeAdrenoABI.h`） | iOS 27（`drivers/Adreno740/NativeAdrenoABI.h`） | 判定 | 等 |
| --- | --- | --- | --- | --- | --- |
| D1 | 版本 | `:14` `NativeAdrenoAbiVersion = 1` | `:14` `= 2` | **不同** | A |
| D2 | 单次提交的 IB 上限 | `:15` `NativeAdrenoAbiMaxBuffers = 16` | `:15` `= 128`，注释「a frame's IBs in one submission (Turnip splits a larger one)」 | **不同（8×）** | A |
| D3 | `sizeof(NativeAdrenoAbiSubmit)` | `:154` `== 416` | `:154` `== 32 + 24 * NativeAdrenoAbiMaxBuffers`（= 3,104） | **不同（7.46×）** | A |
| D4 | 其余 struct 尺寸 | `:150-157`：BoAlloc 16、BoMap 32、BoImport 16、SubmitBuffer 24、BoCpuMap 8、BoCpuMapReply 16、BoCpuUnmap 16 | 同一组断言，值完全相同 | 相同 | A |
| D5 | 未知版本怎么处理 | `:10-13` 头注释「Unknown versions, methods and flags are refused rather than ignored」；`drivers/PongAdreno/PongAdrenoClient.cpp:53` `core->open(NativeAdrenoAbiVersion,…)` | 同族检查（同一份头注释与 `open` 契约） | ⇒ **v1 内核 + v2 presenter 在 open 就被拒**，必须先升 ABI | A |
| D6 | 方法号 | `NativeAdrenoMethodQuery…BoImport` = 1..16（`:17-32`） | 同名同号 | 相同 | A |
| D7 | 队列/元数据 | `MaxQueues=8`（`:34`）、`MetadataBytes=64`（`:33`） | 相同 | 相同 | A |

对应官网页：`porting/gpu.md#memory-path:65-86`（映射规则）、§3:51-63（命令路径五步）、`drivers/adreno740.md`:9（4 KiB 页 + 句柄索引）。**为什么 v2 是 27 的必要条件**：`MaxBuffers` 的注释直接写明了原因——Turnip 把一帧拆成更多 IB，128 是它的上限；v1 的 16 在 27 的 Turnip 下会在提交侧溢出。这一条是「27 上还要补什么」清单里的第一项，且**可以离线验证**（sizeof 断言 + open 的版本检查都在源码里）。

## 6 E 组：符号绑定与发布

| # | 契约面 | 16.6.1 | iOS 27 | 判定 | 官网页锚点 | 等 |
| --- | --- | --- | --- | --- | --- | --- |
| E1 | 父类符号 | `OSSymbol("IOAcceleratorES")` + `OSMetaClass::getMetaClassWithName`（`PongAdrenoAccelerator.cpp:21-22`），`:32` 校验 `getClassSize()!=sizeof(IOAcceleratorES)` | `IOGPUFamily` 注册同名类（24A446 JSON evidence） | 名字绑定两代都成立 | `#source-map:16-18` | A |
| E2 | 发布 C 符号 | `native_adreno_publish(…)` / `native_adreno_published_service()`（`PongAdrenoNativeGlue.cpp:9-11`） | 同名同签名（`NativeAdrenoPublish.cpp:736`、`:758`），另有 `native_adreno_publish_stats(uint32_t*)` `:753` | 相同 | `#memory-path:65-86` | A |
| E3 | 运行时插件名 | 我们的产物是 `PongAdrenoMetal.bundle`（`k60-gates/docs/research/gpu/UPSTREAM-PARITY.md:54`，YB-01：zzy patch 校验 `NativeAdrenoMetal.bundle` 与真实产物不符） | 官方要求 `NativeAdrenoMetal`（`porting/gpu.md`:143-149，`sheng-gpu-addon=1` + `--publish build/gpuaddon.bin`） | **不一致**，属上游缺陷导致的挂载失败风险 | `porting/gpu.md`:124-149 | A |
| E4 | 构建标识 | 我们只记 Turnip 侧 UUID | `#shader-warmup:151-167`：构建标识 = 运行时转换器 + Turnip `LC_UUID` | 27 门禁要核 `LC_UUID` | `#shader-warmup:151-167` | B |
| E5 | 板级启动参数名 | `sheng-gpu-preempt`、`sheng-fb-bgra`、`sheng-metal-flow`、`sheng-gpu-addon`、`sheng-wallpaper-freeze` | 同名（`#scheduling:88-94`、`#render-mode:96-104`、`porting/gpu.md`:139-149、`drivers/adreno-metal.md`:56） | 一致 | 见左 | B |

## 7 F 组：hw_init 与 HWCg

### 7.1 谁写这些寄存器（27 侧换了执行者）

| # | 契约面 | 16.6.1 | iOS 27 | 判定 | 等 |
| --- | --- | --- | --- | --- | --- |
| F1 | hw_init 执行者 | 我们自己：`drivers/PongAdreno/PongAdrenoCp.cpp:236-255`（序列写在驱动里） | **driver kit 不执行**：`drivers/Adreno740/` 里 `RBBM_CLOCK_*` 只出现在 `NativeAdrenoA740HwInit.h`（表头 `:61` 起，生成说明 `:6`），**无任何 `.cpp` 引用**；执行者是板级 `UniXNU-sheng/package/GpuPowerProbe.cpp:1568 gpuHwInit()`（`:72` `#include "NativeAdrenoA740HwInit.h"`） | **执行者不同** | A |
| F2 | hwcg 表的来源 | `drivers/PongAdreno/PongAdrenoCpProfile.h:1125` `PongCpHwcg[][2]`，53 行，写入点 `PongAdrenoCp.cpp:252` | 官方表 `NativeAdrenoA740HwInit.h:61`；执行 `GpuPowerProbe.cpp:1580` | 表在两侧都有，**但内容按代际不同**（§7.2） | A |
| F3 | A730 的表从哪来 | 我们手抄 a730_hwcg（§7.2 逐条核实） | 27 侧**没有** `NativeAdrenoA730HwInit.h`（`scripts/derive-a730-hwinit.py:5,13-14`：写 `build/adreno730/include/NativeAdrenoA730HwInit.h`，`REFERENCE` 指向 `drivers/Adreno740/NativeAdrenoA730HwInit.h`，说明 A730 表要靠生成器产出） | 「27 侧不存在」⇒ A730 的表必须我们维护 | A |
| F4 | `a730_protect` | `PongAdrenoCpProfile.h:1187` `PongCpProtect[][2]`，`PongAdrenoCp.cpp:247` 写 | sheng `GpuPowerProbe.cpp:1594-1596`：`CP_PROTECT_CNTL=(1\|2\|8)` 后写 `NativeAdrenoA740Protect`（生成时用 a730_protect） | 表源相同，写法等价 | A |

### 7.2 A730 与 A740 的 HWCg 差异（12 行专表）

数据全部机械生成（`a6xx_catalog.c` 逐行解析 + 位异或），不是手抄：

- `a730_hwcg[]`：`E:/hackios/UniXNU/.cache/adreno-source/drivers/gpu/drm/msm/adreno/a6xx_catalog.c:1195` 起，`:1250` 止，**53 条**。
- `a740_hwcg[]`：同文件 `:1252` 起，`:1308` 止，**54 条**。
- 同名 52 个，其中 43 条值相同 ⇒ **12 行差异**（9 行值不同 + 2 行只有 A740 有 + 1 行只有 A730 有）。
- 我们 16.6.1 的表（`PongAdrenoCpProfile.h:1126-1174`，53 条）与 `a730_hwcg` **寄存器名完全一致**，值只有 **1 处**不同：`RBBM_CLOCK_CNTL3_TP0` 我们写 `0x22222222`（= A740 值），A730 目录是 `0x22220222`。`CNTL2_UCHE`、`HYST2_VFD` 我们也没有（与 A730 目录一致）。

复现方式（不依赖本文件以外的脚本）：两侧目录表按正则 `REG_(A6XX|A7XX)_(RBBM_\w+), (0x[0-9a-f]+)` 抽名字与值（`A7XX_` 前缀归一），按名字求交后比 `_hwcg` 表；本树按 `\{GEN7_(RBBM_[0-9A-Z_]+),(0x[0-9a-fA-F]+)\},` 抽 `PongAdrenoCpProfile.h:1126-1174`；位差先把 `a^b` 与 `b` 相与得「A740 多置的位」、与 `a` 相与得「A740 清掉的位」。

| # | 寄存器 | 偏移（XML） | 16.6.1 本树（`PongAdrenoCpProfile.h`） | A730 目录（`a6xx_catalog.c`） | A740 目录（同） | 27 侧（sheng `gpuHwInit`）会写 | 27 上会导致什么行为 | 等 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| H1 | `RBBM_CLOCK_CNTL2_SP0` | 0xb4 | `:1127` `0x02022222` | `:1197` `0x02022222` | `:1254` `0x22022222` | A740 值（`GpuPowerProbe.cpp:1578` 循环写整表） | A740 值多置 bit29、无清位。若在 A730 上照写，SP0 时钟控制多一个使能位；位语义无公开文档，**行为只能上机 A/B**（判据见 §11） | A(值)/C(行为) |
| H2 | `RBBM_CLOCK_HYST_SP0` | 0xbc | `:1128` `0x0000f3cf` | `:1198` 同 | `:1255` `0x003cf3cf` | A740 值 | 多置 bit18–21（整个 nibble 从 0 变 `0x3`）。迟滞计数从 0 变为非零 ⇒ SP0 时钟关断延迟变长（更保守）——方向可判、量级不可判 | A/C |
| H3 | `RBBM_CLOCK_CNTL3_TP0` | 0xc8 | `:1132` **`0x22222222`（A740 值）** | `:1202` `0x22220222` | `:1259` `0x22222222` | A740 值（= 我们现在写的） | **唯一一处我们已经偏离 A730 目录的地方**。16.6.1 实测能出帧、未爆 hang ⇒ 该 bit13 在 A730 上要么无害要么被忽略；但这条偏差会让「我们和 A730 一致」的说法站不住 | A/C |
| H4 | `RBBM_CLOCK_HYST_UCHE` | 0x110 | `:1143` `0x00000004` | `:1213` 同 | `:1271` `0x00000444` | A740 值 | 多置 bit6、bit10 ⇒ UCHE 关断迟滞变长（更保守） | A/C |
| H5 | `RBBM_CLOCK_DELAY_UCHE` | 0x10f | `:1144` `0x00000002` | `:1214` 同 | `:1272` `0x00000222` | A740 值 | 多置 bit5、bit9 ⇒ UCHE 关断延迟变长 | A/C |
| H6 | `RBBM_CLOCK_MODE_VFD` | 0x111 | `:1157` `0x00002222` | `:1227` 同 | `:1285` `0x00222222` | A740 值 | 多置 bit17、bit21 ⇒ VFD 多两个门控模式位 | A/C |
| H7 | `RBBM_CLOCK_DELAY_TSE_RAS_RBBM` | 0x109 | `:1163` `0x00004000` | `:1233` 同 | `:1291` **`0x00000000`** | A740 值 = 0 | **清掉 bit14** ⇒ TSE/RAS→RBBM 的关断延迟归零，门控更激进。这是 12 行里**唯一明确放松**的一条，也是最可能影响帧稳定性的 | A/C |
| H8 | `RBBM_CLOCK_DELAY_VFD` | 0x112 | `:1165` `0x00002222` | `:1235` 同 | `:1293` **`0x00000000`** | A740 值 = 0 | 清掉 bit1、5、9、13 ⇒ VFD 关断延迟全部归零，同 H7 的放松方向 | A/C |
| H9 | `RBBM_CLOCK_MODE_CP`（A7XX） | 0x260 | `:1171` `0x00000223` | `:1241` 同 | `:1299` `0x00000222` | A740 值 | 清掉 bit0 ⇒ CP 的门控模式少一个使能位（更保守）。注意该寄存器 XML 标 `variants="A7XX"`，A730 也在 A7XX 内 | A/C |
| H10 | `RBBM_CLOCK_DELAY_HLSQ_2` | 0x117 | `:1169` `0x00000002` | `:1239` `0x00000002` | **A740 表里没有** | **不写** | 若照搬 A740 表，我们在 16.6.1 写的这条会消失，HLSQ 第二段延迟回到复位值（大概率更激进）。**这是我们独有的行为，搬表会静默丢掉** | A/C |
| H11 | `RBBM_CLOCK_CNTL2_UCHE` | 0x10c | **我们不写** | **A730 表里没有** | `:1270` `0x00222222` | A740 值 | 若照搬，A730 上会新写一个 `0x00222222`（bit21 等）。XML 标 A6XX-A7XX ⇒ **寄存器在 A730 上存在**，只是目录没配 | A/C |
| H12 | `RBBM_CLOCK_HYST2_VFD`（A7XX） | 0x12f | **我们不写** | **A730 表里没有** | `:1298` `0x00000000` | A740 值 = 0 | 同 H11，写 0；A730 上存在（`variants="A7XX"`） | A/C |

两条机械事实支撑整张表：**(a)** 12 行里 10 行是 A740 多置位或置非零（更细的门控/更长的迟滞），2 行（H7、H8）是 A740 把延迟清零（更激进），1 行（H9）少一个使能位；**(b)** A740 新增的位在字段内呈「每 4 位一组多置 1 位」的规律（bit 2/5/6/9/10/13/17/18-21/29），像是「每 quad 多使能一路」——这是**推断**，不作为结论，只说明它不像随手写的脏数据。

**27 上的净结论**：整包搬 `NativeAdrenoA740Hwcg` 到 A730，会（i）改变 9 个值、（ii）新写 2 个我们从不写的寄存器、（iii）丢掉 1 个我们独有的写、（iv）其中 H3 恰好是「我们已经写了 A740 值」的那一条（所以那条不会变）。真正的风险不在值本身，而在「搬了之后我们不再有一张与 A730 目录逐条对齐的表」——这也是门禁要用 §11 的 A/B 判据守的地方。

### 7.3 同一步里的另外两处写法差异

| # | 契约面 | 16.6.1 | iOS 27（sheng） | 判定 | 等 |
| --- | --- | --- | --- | --- | --- |
| F5 | `GPU_GMU_AO_GMU_CGC_MODE_CNTL` | `PongAdrenoCp.cpp:250` 写 `0x20000` | `GpuPowerProbe.cpp:1574` 写 `0x00020202`（注释 `a6xx_set_hwcg(true)`） | **不同**；`CGC_DELAY_CNTL=0x10111`、`CGC_HYST_CNTL=0x5555` 两侧相同（我们 `:250-251`） | A |
| F6 | 顶层使能的写法 | `:252` 整表循环（表内 `:1172` 已含 `RBBM_CLOCK_CNTL=0x8aa8aa82`），`:255` 再写一次并回读校验 | `:1577-1579` `if (gpuRd(CLOCK_CNTL) != 0x8aa8aa82) { 写表; 写 enable; }` | 27 版对 hang 重启幂等，我们版每次重写 | A |
| F7 | GMEM 范围 | `PongAdrenoCpProfile.h` 走 A730 参数 | `:1586-1587` `UCHE_GMEM_RANGE_MIN=0x1000000`、`MAX=+3MiB-1`（注释 `gmem 3 MiB`） | A730 的 GMEM 大小需按 ADT 核（不照抄 3 MiB） | B |
| F8 | UBWC 参数 | 我们的 `PongAdrenoHighestBankBit` 从 FDT 取（`PongAdrenoCp.cpp:236-238` 用 bank bit） | `:1601-1608` 写死 `sm8550_data`（hbb_lo 3/hbb_hi 0、swizzle 2+3、AMSBC、rgb565 predicator） | 27 的值绑 SM8550 ⇒ **不能整包搬** | B |

## 8 G 组：内存与命令路径

| # | 契约面 | 16.6.1 | iOS 27 | 判定 | 官网页锚点 | 等 |
| --- | --- | --- | --- | --- | --- | --- |
| G1 | SMMU 页大小与失效 | 4 KiB：`drivers/PongAdreno/ArmSmmu4K/ArmSmmu4KProgram.c:26`「TLBIASID (+0x610 …) … then TLBSYNC/TLBSTATUS」；`ArmSmmu4KLive.c:476`「The unmap invalidates the ASID before it reports the translation removed」 | `drivers/adreno740.md`:9（4 KiB 页、句柄索引查找）；`drivers/Adreno740/NativeAdrenoRing.cpp:37`「What the SQE's `CP_SMMU_TABLE_UPDATE` handler does before it switches tables (a740_sqe.fw, qrisc-disasm): CACHE_FLUSH7 (0x32)」 | 页大小一致；27 多一条「切表前 flush」由 **SQE 固件**做，不在内核 | `#memory-path:65-86`；`drivers/adreno740.md`:9 | A |
| G2 | 提交时是否做 TLB 失效 | 页面写「提交不做 TLB 失效」（`#memory-path:65-86` 规则 5） | 同页同规则 | 一致 | `#memory-path:65-86` | B |
| G3 | 抢占与环 | `PongAdrenoCp.cpp:24` `get_preemption_level()`、`:62` 中断要求非抢占层、`:80` RB-done/preemption 不算错误、`:94` 中断上下文不分配不改环、`:109` `publish_ring`、`:126` `ring.wait(…,500000,…)`（500 ms） | `drivers/adreno740.md`:11-22：`CP_SMMU_TABLE_UPDATE` 记录实际页表供恢复、ring0 空闲或 ring1 最早任务等待 >250 ms 才调度、时间片 2 ms、切环超时 1 s、失败后停抢占并在 ring0 重放；`#scheduling:88-94` 同数字 | 数字口径一致；27 把「实际页表」记下来（我们没有等价物） | `#scheduling:88-94`；`drivers/adreno740.md`:11-22 | B |
| G4 | GMU 调档（`gperf` 收益的来源） | `PongAdrenoGmu.c:260` `PongAdrenoHfiSend(&d->hfi,30,vote,3,&r->header)`（HFI id 30） | **27 侧 driver kit 无 HFI 调档**（`grep -i "vote\|perf\|level" drivers/Adreno740/*.cpp` 为空）；27 的调档是 `UniXNU-sheng/package/ShengGmuVotes.c:4` `ShengGmuBuildStartup`、`:12/:22` `AdrenoHfiArcVotes`（GPU/GMU 两张 OPP 表）、`:38` `ShengGmuPerfVote` | **形态不同**：27 把调档挪到板级配方，按 OPP 表投票 | `#scheduling:88-94`；`drivers/sm8550-platform.md`§源码:29 | A |
| G5 | 固件三件套 | 我们：`gmu_gen70000.bin`、`a730_sqe.fw`、`a730_zap.mdt/b01/b02`（`E:/k60-work/adsp-device-20261116/.cache/firmware/k60-gpu/`） | 官方 `#2:37-48`：`qcom/gmu_gen70200.bin`、`qcom/a740_sqe.fw`、`qcom/sm8550/sheng/a740_zap.mbn` | **代际不同**，不可整包搬；表里逐项对号即可 | `porting/gpu.md`:37-48；`drivers/adreno-firmware.md`§状态:11 | A |
| G6 | 固件加载路径 | `.cache/firmware/k60-gpu/` + `scripts/data/adreno-inputs.json` | `.cache/firmware/sheng-gpu/` + 同 JSON（`#2:37-48`） | 机制相同，目录名不同 | `porting/gpu.md`:37-48 | B |

## 9 H 组：帧路径与扫出

| # | 契约面 | 16.6.1 | iOS 27 | 判定 | 官网页锚点 | 等 |
| --- | --- | --- | --- | --- | --- | --- |
| H1 | 一段帧分成几段 | 五段：`import`/`encode`/`submit`/`gpu` + `sum`（`drivers/PongMetal/GpuScanoutPresenter.h:160-166` 的 accessor；样本值见 `docs/research/gpu/FLIGHT-CARD-20261119j.md:96-97`） | **七段**：创建到 commit／commit 到编码／编码到运行时 commit／运行时 commit 到提交／提交到 GPU 完成／完成到回调／显示更新（`#frame-path:106-120`，CPU 用 uptime、GPU 用硬件时钟校准） | **缺两段**：「完成到回调」「显示更新」 | `#frame-path:106-120` | A |
| H2 | 时钟基准 | 我们按 uptime 取 CPU 段，GPU 段用 fence 差值 | 页要求 CPU 用 uptime、GPU 用**硬件时钟校准** | 27 要补校准（否则 `gpu` 段与面板刷新对不上） | `#frame-path:106-120` | B |
| H3 | 量级基线 | 卡 j（92 样本中位）：`import 51 / encode 335 / submit 967 / gpu 5,983 / sum 8,281 µs`（`FLIGHT-CARD-20261119j.md:96-97,108`）；bench 自测循环终态：`27 / 3,059 / 362 / 2,470 / 5,907 µs`（`docs/research/eight-step/gpu-27.toml:24`） | **27 侧无读数**（27 stage-0 进不了 SpringBoard） | unknown，见 §10 | `#frame-path:106-120` | A |
| H4 | 扫出 wire 的形状 | `drivers/PongAdreno/PongScanoutWire.h:13` `{sequence,address,bytes,stride,width,height,format,reserved}`，48 B，`:15` `static_assert(...==48)`；每帧交 `IOMemoryDescriptor*` 给 presenter，presenter **import + GPU copy**（`GpuScanoutPresenter.h:3,39,46-53`） | **「27 侧不存在」**：Adreno740 kit 没有 scanout wire；27 只有 `#frame-path` 的测量口径 | 27 要自己定；这是零拷贝的落点 | `#frame-path:106-120`；`#render-mode:96-104` | A |
| H5 | 零拷贝 wire 的参考形状 | 我们没有 token/evict/target | zizhan（iPadOS 18 参考）：`UniXNU-zizhan/drivers/PongAdreno/PongScanoutWire.h:12-18` 加 `token,evict,target`，56 B，注释说明「token 非零 ⇒ 保留映射给后续帧；evict ⇒ 本帧前必须丢弃的 token；target ⇒ 扫出映射内的字节偏移（`pong_dpu_flip` 时取面板缓冲）」 | **两个不兼容布局共用 `PongScanoutVersion=1`**（两侧 `:5`）⇒ 跨树混用会静默错读 | — | A |
| H6 | 显示更新（flip） | `pong_scanout_frame(IOMemoryDescriptor*,…)`（`drivers/PongAdreno/PongAdrenoScanout.h:7`）只做 copy；flip 归 display 线 | 官方 27 无 GPU 侧 flip 合同；`#frame-path` 只要求**测**显示更新 | 需与 display 线对齐（本表只记录缺口） | `#frame-path:106-120` | B |
| H7 | 渲染模式 | `TU_DEBUG=sysmem,nocb` 默认、lazy transient 走 GMEM、`sheng-metal-flow` 三条路径（`#render-mode:96-104`） | 同页同规则；Metel 默认单采样 `NATIVE_METAL_SINGLE_SAMPLE=0`（`drivers/adreno-metal.md`:7-17） | 一致（都在我们的 16.6.1 驱动里已实现） | `#render-mode:96-104` | B |
| H8 | 120 Hz 上限的物理墙 | 每帧全屏拷贝 16–20 ms ⇒ 上限约 74 fps；实测 13.5–23 ms（`usblog-20261119-044558`，记录于 `docs/engineering/PITFALLS.md:6621` 与其后的 flight card） | 27 侧没有新证据 | 结论不随 27 改变：只有零拷贝能过墙 | `#frame-path:106-120` | A |

## 10 unknown 清单与「怎么把它变成 known」

### 10.1 还 unknown 的三项

| # | unknown | 为什么要它 | 27 侧读它需要什么 |
| --- | --- | --- | --- |
| U1 | Metal 用户态 selector 全集：27 上 QuartzCore/Metal/UIKitCore 到底引用哪些 Metal 协议 selector | C 组只能定「代码面 selector」，定不了「运行时谁发什么」；决定 27 的插件要覆盖多少 selector | 24A446 的 `dyld_shared_cache_arm64e` + macOS 上的 SDK |
| U2 | 27 侧真实帧时间（present 各段、扫出耗时） | H3 的读数只有 16.6.1；27 没有一帧到过面板 | 27 进到 SpringBoard（本线不能做，等 stage 推进） |
| U3 | A730 上 12 行 HWCg 差异的实际行为 | §7.2 只能给「位怎么变」；「帧稳不稳/快不快」必须上机 | A/B 两次 boot（判据见 §11） |

### 10.2 U1 的可执行证据链（不是「需要 macOS」一句话）

1. 输入：`24A446.ipsw`（12,314,041,166 B，sha256 `2b846dfd…`，Mac 上 `/home/emilelu/ipsw/`）。
2. `aea -d 043-68526-711.dmg.aea` → 2,348,810,240 B 的 SystemOS DMG。
3. `hdiutil attach` 挂载 → 取 `System/Library/Caches/com.apple.dyld/dyld_shared_cache_arm64e`。
4. 在 Mac 上跑 `E:/hackios/UniXNU/scripts/audit-metal-api-surface.py`（需要 `xcrun clang++` 与 pin 在 `refer/dyld` `a571176e` 的 dyld），产出 `build/gpu-analysis/metal-api-surface.json`。
5. 把该 JSON 交回本线；本表 C5 与 §11 的 selector 判据改为 known。

**为什么现在不做**：IPSW 11.5 GiB 在 Mac 侧、解包后 SystemOS 再加 2.2 GiB、脚本还要 iPhoneOS SDK 与 `refer/dyld` 的构建；这一条需要 Mac 在线且有人值守，不属于「离线可完成」的活。Lead 已另派人做抽取，本线只留接口。

**接口（消费侧只依赖这些字段）** —— 来自脚本自身的 `report` 构造（`audit-metal-api-surface.py:145-153`）与 `IMAGES`（`:30-32`）：

```jsonc
{
  "sdk_protocol_selectors": { "<protocol>": 0 },          // 协议名 -> SDK 声明数
  "images": {
    "/System/Library/Frameworks/QuartzCore.framework/QuartzCore": {
      "selector_references": 0,                            // 该镜像 __objc_selrefs 条数
      "declared_and_referenced": { "<protocol>": ["selector", "..."] },
      "distinct_declared_and_referenced": 0
    }
  },
  "quartzcore_metal_like_selectors_not_in_sdk_protocols": ["selector", "..."]
}
```

判据落点：`images[QuartzCore].declared_and_referenced` 就是 27 组合层实际能发的 Metal 消息上界；`quartzcore_metal_like_selectors_not_in_sdk_protocols` 是私有 SPI 面，决定插件是否要额外实现 `_MTLDevice` 之外的私有 selector。**接口不做的事**：不假设字段顺序、不假设图像集合固定（`IMAGES` 可能被改），只按名字取。

### 10.3 U3 的判据（离线可写，上机才跑）

见 §11 的 G-HWCG 判据。

## 11 每条差异对应的门禁判据（第 ④ 件的输入）

只列能落成「一个脚本 + 一组正则 + 退出码」的判据；字段名尽量贴着官方 `gpu-diagnostics.md` 的判据字段（§保留的证据:11-21）。

| 门禁 | 守住哪几条 | 判据（离线可行部分） | 需要 27 读数才有意义的部分 |
| --- | --- | --- | --- |
| G-ABI | D1–D7 | 解析两侧 `NativeAdrenoABI.h`：版本、`MaxBuffers`、`sizeof(Submit)` 必须与 27 侧相等；`static_assert` 值必须能算出来 | 27 上 UserClient `open` 的返回值（`[gpu client]` 行） |
| G-PUBLISH | B3、E1、E2 | 源码：`native_adreno_publish` 的三个符号存在且签名一致；服务先 register 再返回 | `[gpu client text]` 首行、`native_adreno_publish_stats` 的 closed 计数 |
| G-SELECTOR | C1–C5 | 源码：前台件里 `newCommandQueueWithMaxCommandBufferCount:` 与 `presenter` 用哪条 selector；`docs/engineering/IOS-SCOPE.md` 的停做清单不得回潮 | U1 的 JSON：`declared_and_referenced` 覆盖率 |
| G-HWCG | §7.2 全部 12 行 + F5/F6 | 三方表逐条比对（我们的、a730 目录、a740 目录）必须在 CI 里跑成 0 意外差异，且 H3 单列白名单并写明原因 | A/B 两次 boot 的 `gpu` 段与 `scanout frames=`（判据：A740 表不得让 fps 或 `gpu` 段变差超过噪声） |
| G-FRAMEPATH | H1、H2 | 前台件必须输出七段而非五段（少一段即 fail） | `#frame-path:106-120` 七段的实测值 |
| G-SCANOUT | H4–H6 | wire 版本号必须与布局绑定（48 B ⇒ v1、56 B ⇒ v2）；`static_assert` 与版本表同源 | 扫出帧数、`wait` 段、flip 次数 |
| G-DIAG | 全部 | 启动参数 `sheng-log=1 sheng-gpu-trace=1 sheng-gpu-perf=1 sheng-diag-export=240`（`gpu-diagnostics.md`:5-6）、导出清单 ≤8 MiB（`:37`）、`scripts/check-gpu-trace.py` 与 `check-native-adreno-scheduling.py`（`:73-76`） | 实机导出是否齐全 |

字段级对齐：`gpu-diagnostics.md` 的七类证据分别对应本表的 —— 前台大块分配 ⇒ G-ABI/G-SCANOUT 的 import 段；提交前延迟 ⇒ G-FRAMEPATH 的 `submit` 段；GPU pass 耗时 ⇒ G-HWCG 的 A/B；显示更新空档 ⇒ H6。采集策略里「<250 µs 释放不记」（`:27-31`）意味着 G-SCANOUT 不能靠释放事件判零拷贝是否生效，必须看 `token/evict` 计数。

## 12 引用清单

**官方页（requirement）**

- `porting/gpu.md`：`#source-map:9`、`:16-18`；§1:26-27；§2:37-48；§3:51-63；`#memory-path:65-86`；`#scheduling:88-94`；`#render-mode:96-104`；`#frame-path:106-120`；§4:124-149；`#shader-warmup:151-167`。
- `porting/gpu-diagnostics.md`：`:5-6`、§保留的证据:11-21、§采集策略:25-31、`:33`、§导出内容:37、§读取与解码:39-56、§检查:71-76。
- `drivers/adreno740.md`：§运行路径:5-9、§调度:11-22、§构建和验证:24-34。
- `drivers/adreno-metal.md`：§渲染和接口:5-19、§缓存和优先级:21-36、§构建和检查:38-46、`:54`、`:56`。
- `drivers/adreno-firmware.md`§状态:11、§构建:15；`drivers/adreno-pm4.md`:11/15；`drivers/air-nir.md`:11/15；`drivers/sm8550-platform.md`§要求:11、§源码:29、§验证:37、§集成:41；`drivers/community-adreno830.md`:11。

**16.6.1 侧（本树）**

- `drivers/PongAdreno/PongIOAcceleratorABI.h:4-11`；`PongAdrenoAccelerator.cpp:21-22,31,32,47,48`；`PongAdrenoNativeGlue.cpp:9-11,146,155,158`。
- `drivers/PongAdreno/submit/NativeAdrenoABI.h:10-15,17-34,150-157`；`PongAdrenoClient.cpp:45,53`。
- `drivers/PongAdreno/PongAdrenoCp.cpp:236-255`；`PongAdrenoCpProfile.h:1125-1174,1187`；`PongAdrenoGmu.c:260`。
- `drivers/PongAdreno/ArmSmmu4K/ArmSmmu4KProgram.c:26`、`ArmSmmu4KLive.c:476`、`ArmSmmu4KAudit.c:168`、`ArmSmmu4KContext.c:80`。
- `drivers/PongAdreno/PongScanoutWire.h:5-15`；`PongAdrenoScanout.h:7`。
- `drivers/PongMetal/NativeBridgeMetalFrontend.mm:1281,1312,1340,1573`；`GpuScanoutPresenter.h:3,34,39,46-53,60-71,160-165`。
- 证据 JSON：`E:/k60-work/UniXNU-carrier/scripts/data/ioaccelerator-base-abi.json`、`ioaccelerator-base-abi-24A446.json`。
- kernelcache：`/opt/k60/trees/gates-out/ipsw/20G81/kernelcache.decompressed`（48,644,096 B）、`/opt/k60/trees/ios27-out/ipsw/24A446/kernelcache.decompressed`（77,987,840 B，sha256 `38e6d9fa…`）。

**27 侧（官方树 / 板级配方 / 数据）**

- `drivers/Adreno740/NativeAdrenoABI.h:14-15,150-156`；`NativeAdrenoPublish.cpp:736,740,748,750,753,758`；`NativeAdrenoRing.cpp:37`；`NativeAdrenoA740HwInit.h:6,61`。
- `drivers/AdrenoMetal/NativeBridgeMetalFrontend.mm:1573,1632,1869`。
- `UniXNU-sheng/package/GpuPowerProbe.cpp:38,72,1568,1573-1580,1586-1588,1595-1605`；`GpuPowerBoard.h:90-92`；`ShengGmuVotes.c:4,12,22,38`。
- 目录数据：`E:/hackios/UniXNU/.cache/adreno-source/drivers/gpu/drm/msm/adreno/a6xx_catalog.c:1195-1308`；`registers/adreno/a6xx.xml`（0xb4/0xbc/0xc8/0x109/0x10c/0x10f/0x110/0x111/0x112/0x117/0x12f/0x260）。

**参考实现（非 27，仅作形状参考）**

- `UniXNU-zizhan/drivers/PongAdreno/PongScanoutWire.h:12-18`（token/evict/target，56 B）。
- `UniXNU-t970/drivers/T970Adreno/PongAdrenoCpT970.cpp`、`patches/xnu-ipados18/…-pong-gpu-perf.patch`（逐条判定是否依赖 PongPlatform24/iPadOS 契约，见八步 ⑦）。

## 请 Lead 给下一步

按契约顺序，本表（第①件）已逐行落地，用户态一行按裁决留 unknown + 可执行证据链 + JSON 接口。下一步建议二选一：

- **(A)** 继续第③件 **120fps 端到端预算表**（present 五段现状 + 27 要求的七段 + 扫出零拷贝路径），它要引用本表 H1/H3/H8 与 §10.1 的 U2；
- **(B)** 先写第④件**离线判读器/门禁草案**，把 §11 的七个判据落成脚本骨架（不构建、不写 k60-gates）。

`done=false` 保持到 U1/U2 至少一项变成 known。
