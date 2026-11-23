# GopFramebuffer 最小移植集：组件在 catalog 里，构建器只在 sheng 里

结论先说：`GopFramebuffer` 的**源码**是公开的（catalog pin
`e47c1b8de169cd2bd0b885c7d85e433010e3cdf2`，`https://github.com/UniXNU/GopFramebuffer.git`），
但把源码变成 `libGopFramebuffer.late.a` 的**构建器不在组件仓库里**——它只存在于
`UniXNU-sheng/scripts/build-gop-legacy-display-27.py`（45,825 B），而且那份脚本还合并了
keystore、键盘、USB、蓝牙四个探针。直接整支拷过来会把我们不需要的驱动一起链接进内核。

## 1. catalog 侧已有的东西

`E:/hackios/UniXNU/components.toml:206-225`：

| 字段 | 值 |
|---|---|
| `id` | `GopFramebuffer` |
| `os_abi` | `ipados-17.7.11-21H461`、`ipados-27.0.1-24A446` |
| `verified_devices` | `["sheng"]` |
| `source_files` | `NativeMobileDisplay.cpp`、`NativeLegacyDisplay.cpp` |
| `build` | **`[]`**（没有构建命令） |
| `outputs` | `build/gop-framebuffer/libGopFramebuffer.a`、`build/gop-framebuffer/libGopFramebuffer.late.a` |
| `legacy_outputs` | `build/native-mobile-display/libNativeMobileDisplay.late.a` → `build/gop-framebuffer/libGopFramebuffer.late.a` |

`build = []` 意味着**板子自己负责产出那两个归档**；catalog 只登记「有这个组件、哪个 ABI 验过」。

## 2. 组件仓库里的文件（10 个）

```
AGENTS.md  LICENSE  README.md
NativeLegacyDisplay.cpp    NativeLegacyRequest.h
NativeGOPPresenter.cpp     NativeGOPWire.h  NativeHalfCodes.h
NativeMobileDisplay.cpp    OriginalMobileFramebufferABI.h  NativeGpuTrace.h
Test/check-fence-wait.py
```

`NativeLegacyDisplay.cpp` 的 include 只依赖 IOKit/XNU 公共头 + 上面五个自有头。
它**不** include `kits/Sm8550Platform`；SM8550 的 DPU 基址 `0xae01000` 出现在
`NativeLegacyDisplay.cpp:282`，属于 `dpu-scanout=2` 分支，K60 必须用 SM8475 的值或不启用该分支。

## 3. 一个决定构建方式的结构事实

27 内核源码树里**没有** `IOFramebuffer`/`IOGraphicsFamily` 的源文件：
`grep -rn "class IOFRAMEBUFFER" <xnu>/iokit` 为空，`iokit/conf/files.arm64` 也没有相关条目。
显示 family 只以 **prelinked kext** 形式存在——`board.toml` 的 `[kernel.prelink] roots` 里有
`com.apple.iokit.IOMobileGraphicsFamily`（没有 `IOGraphicsFamily`）。

所以 `NativeLegacyDisplay.cpp` 不可能 include 头文件去继承原类；它靠
`OriginalLegacyFramebufferABI.h` + `legacy-display-24A446.json` 生成的 vtable 槽
（`original-bindings.cpp` / `original-addresses.cpp`）在运行期对接 prelinked 的
`IOFramebuffer`。这也解释了为什么 sheng 的构建器把这两个生成文件当成必需品，
以及为什么「只拷 `.cpp` 源码」是不够的。

## 4. 构建器缺什么

`sheng/scripts/build-gop-legacy-display-27.py` 里与显示相关的只有四段，其余都是别的东西：

| 段 | 行 | 作用 | 我们是否已有 |
|---|---|---|---|
| `ABI_PATH` + 生成 `original-bindings.cpp` / `original-addresses.cpp` | 23、95–260 | 从 `scripts/legacy-display-24A446.json`（31,972 B）生成原类 vtable 槽与地址表 | **无**，必须移植这段生成逻辑 |
| `NativeLegacyDisplay.cpp` / `NativeGOPPresenter.cpp` 编译 | 700–716 | 主体 | 源码有 |
| `LegacyDisplayProbe.cpp` | 267/312 | 注册服务、启动显示 | **缺文件，且无处可取**：sheng 仓库里 `git ls-files kits/` 只有 `kits/.gitkeep`，`git log --all -- kits/sheng*` 无提交，`feeds.toml` 与 CI 都没有填充这一步（§4.1） |
| `libNativeLegacyDisplay.late.a` 打包 | 700 | `xcrun ar rcs` + `llvm-objcopy` 去掉 `__DATA,__mod_init_func` 并把 `__GLOBAL__sub_I_NativeLegacyDisplay.cpp` 全局化 | Linux 有 `llvm-objcopy`/`ar`，只需换编译器驱动 |

### 4.1 `kits/sheng` 不是「没 fetch」，是上游根本没有

穷举过的证据（2026-11-23，全部只读）：

```bash
cd /mnt/e/hackios/UniXNU-sheng
git ls-files kits/            # 只有 kits/.gitkeep
git log --all --oneline -- 'kits/sheng*'   # 空
grep -n 'kit' board.toml      # 只有 :7 "kit" = "sheng"（名字，不是来源）
grep -in 'kit' feeds.toml     # 空
grep -in 'kit' .github/workflows/package.yml  # 空
```

框架 `UniXNU/kits/` 只有 `AdrenoFirmware`/`AdrenoPM4`/`AirNir`/`ArmSmmu4K`/`VerifiedRoot`/`XnuPrelink`；
装配树 `tree/kits/` 只有 `XnuPrelink` 与板级 kit（我们的是 `mondrian`，sheng 的是 `sheng`）。
`scripts/unixnu/tree.py` 只为 catalog 组件与板级 kit 建目录，不会凭空生出 `kits/sheng/*.cpp`。

⇒ 结论：`LegacyDisplayProbe.cpp` 没有任何公开副本，必须按语义重写。反过来，这也说明
路线 B 里「整支复用 sheng 构建器」在干净克隆上根本跑不通——它会先死在缺这个文件。

不在显示集里、必须剔除的：`KeyStoreProbe.cpp`、`NativeKeyStoreEvents.cpp`、
`KeyboardCover.cpp`、`KeyboardProbe.cpp`、`Wn8030.c`、`GeniI2c.c`、`QcomDwc3.cpp`、
`UsbProbe.cpp`、`BluetoothProbe.cpp`、`GpuPowerProbe.cpp`、`AdspFirmware.c`。

## 5. 两条可选路线

**路线 A（推荐，先做）**：把 sheng 构建器的「显示四段」抽成
`scripts/build-k60-legacy-display.py`（**已落盘**，离线 check 模式可用，见 §5.1）：

- 输入：`drivers/GopFramebuffer`（catalog fetch 得到）+ `scripts/legacy-display-24A446.json`（从 sheng 复制）；
- 编译器：本机 clang 18，`-target arm64-apple-ios27.0`（我们已用同一方式产出
  `libArmCpu.a` 的 arm64e 归档，`cputype=0x0100000c cpusubtype=0x80000002` 已验证）；
- 输出：`build/gop-framebuffer/libGopFramebuffer.late.a` + `build-report.json`（`archive_sha256`/`source_sha256`，
  满足 `build-xnu-generic.sh:675-687` 的校验）；
- 需要自写 `LegacyDisplayProbe.cpp` 的等价物——它的职责是「注册 `IOFramebuffer` 服务并启动显示」，
  可以从 sheng 的实现读语义后重写，不能盲抄（缺文件，也没有第二来源）。

### 5.1 构建器现状（离线可验，未编译）

`scripts/build-k60-legacy-display.py` 三种模式：

- `--check`（默认）：校验组件目录的 2 个源文件 + 5 个头文件、fixture 的
  12 个顶层键与 `slots` 长度，打印计划；**不调用编译器**。对真实输入实测：
  `379 slots, 13 methods, 14 bindings`。
- `--plan`：额外打印完整命令行。
- `--run`：执行；`K60_ALLOW_BUILD != 1` 时退 3（冻结期防误触）。

头文件实测名是 `OriginalMobileFramebufferABI.h`（不是 `…Legacy…`）——第一次
check 就是被这个文件名挡住，说明「按记忆列输入」会立刻红，这是想要的形状。

测试 `scripts/tests/test-build-k60-legacy-display.py` 5 例：完整输入出计划、
缺源文件点名、缺 fixture 键点名、`slots` 过短拒绝、`--run` 无许可退 3。

**路线 B（不推荐）**：整支复用 sheng 的 `build-gop-legacy-display-27.py`，把十来个无关探针一起链进内核。
代价是内核多背上 USB/蓝牙/键盘/keystore 的探针代码，且这些探针都假设 SM8550 的地址。

## 6. 判定

- `GopFramebuffer` 仍是 SpringBoard 的**必需**项（没有它就没有 `IOFramebuffer`/`IOMobileFramebuffer` provider）。
- 但它**不是**文本控制台的前置——文本控制台已经能打印，之前看到的洋红横杠是字体缩放越界（P-313），不是缺 provider。
- 在解冻前能做完的部分：路线 A 的构建器（离线可编、可用 `llvm-nm` 验符号），以及 `LegacyDisplayProbe` 的语义重写。
  这两件都不需要上机，也不需要改 `board.toml` 的 include（归档不存在前 `test -f` 会直接红）。

## 6.1 探针要提供什么（首版清单，待 nm 复核）

组件两个源文件共出现 **57** 个 `native_legacy_*` 符号，其中 31 个在本文件内有定义
（含 14 个 `volatile` 观察数组与 `native_legacy_ring` 等），其余由 probe 侧提供。
按「只有声明、没有函数体/初始化」筛出的首版清单是 26 个：

```
native_legacy_backend_guard            native_legacy_surface_descriptor
native_legacy_client_enter             native_legacy_surface_rejected
native_legacy_client_observed          native_legacy_swap_info_dispatch
native_legacy_copy_diff                native_legacy_swap_stage
native_legacy_copy_timing_observed     native_legacy_swap_validation_observed
native_legacy_frame_colors_observed    native_legacy_transfer_observed
native_legacy_frame_observed           native_legacy_vsync_notify
native_legacy_gop_mapping_observed     native_legacy_vsync_observed
native_legacy_gpu_fallback_observed    native_legacy_pm_observed
native_legacy_hotplug_notify           native_legacy_registration_observed
native_legacy_ioav_color               native_legacy_retirement_observed
native_legacy_ioav_timing              native_legacy_set_refresh_properties
native_legacy_ioav_timing_colors       native_legacy_snap
```

**这张表是线索不是判据**：正则统计会把 `extern "C" IOService *native_legacy_display_allocate(void);`
这类纯声明与 `native_legacy_*` 宏/注释混在一起，已知至少 `native_legacy_display_allocate`、
`native_legacy_surface_width/height/stride/allocation/format/planes`、`native_legacy_prepare_scanout`、
`native_legacy_gpu_offer` 也是外部提供。**唯一权威判据是归档产出后 `llvm-nm -u` 的未定义符号表**；
`scripts/build-k60-legacy-display.py --run` 之后应把这张表与 `llvm-nm -u` 对账，缺一即失败。

## 7. 复现与参考

```bash
ls /mnt/e/k60-work/references/GopFramebuffer            # 组件源码克隆（不入库）
sed -n '95,260p' /mnt/e/hackios/UniXNU-sheng/scripts/build-gop-legacy-display-27.py
python3 scripts/compare-board-parity.py --ours . --theirs /mnt/e/hackios/UniXNU-sheng \
  --profile ios-27.0.1-24A446
```


## 9. 2026-11-24：两处新事实（构建实测）

- **`__LASTDATA_CONST` 撞保留段的原因**：本内核 `__DATA_CONST` 为 `0x120000`（最后实数据 `0x11ca50`），Apple kext 的 `__DATA_CONST` 从 `0xfffffff007ef3578` 起，`__LASTDATA_CONST` 固定占 `0x4000`，差 `0xA88` 字节。把 `__sdt`（`0xd950`）用 `-Wl,-rename_section,__DATA_CONST,__sdt,__DATA,__sdt` 移出后该检查通过（`scripts/build-xnu-generic.sh` 新增 `K60_KERNEL_LDFLAGS` 入口）。
- **`legacy-display-24A446.json` 不能直接用**：文件里 `kernelcache_sha256 = 38e6d9fa…`，本机 24A446 是 `fa07057b…`；`collection_slide = 0x1f000000000` 加上去后 `_native_legacy_surface_allocate` 落在 `com.apple.iokit.IOThunderboltFamily` 的 `__TEXT_EXEC`，而该 kext 不在我们的 roots 里 ⇒ `ValueError: Original target is not retained executable code`。sheng 仓库没有该 JSON 的生成器（只有 hid/usb 的 `gen-*27-abi.py`），`kits/` 也是空的。
- 结论：显示端口的「按先例复制」到此为止；下一步必须**从本机 kernelcache 重新推导 vtable 绑定地址**（按 IOMobileGraphicsFamily 的 slot 序 + 名称），不能复用 sheng 的绝对地址。

## 10. 2026-11-24：surface slot 的来历与 provenance 门禁

`legacy-display-24A446.json` 的 `kernelcache_sha256` 是 `38e6d9fa…`（sheng 的那份 24A446），
本机 24A446 是 `fa07057b…`。`slots` 里 213 条绝对地址，205 条落在两边都有的
`IOMobileGraphicsFamily` `__TEXT_EXEC` 内，剩下 8 条 `_native_legacy_surface_*` 在 sheng 的缓存里
属于另一个 kext；加到本机上（`collection_slide 0x1f000000000`）会落进
`IOThunderboltFamily`（0xa35eb40–0xa52eb4c），prelink 因此在
`fileset_layout.py:281 relocate_original_stubs` 拒绝：
`Original target is not retained executable code`。

已确认这 8 条来自 `slots` 数组而不是 `bindings` 字典：把 `bindings` 从 14 删到 6、重建之后
`original-addresses.o` 仍有 8 个 surface 符号。`UniXNU-sheng` 从未提交 `kits/`
（`git log --all -- "kits/*"` 只有 `.gitkeep`），也没有显示 ABI 生成器，所以「换一份 JSON」
不是一条能照抄的路。

现在 `scripts/gen-legacy-display-abi.py` 在读取 fixture 后立刻比对 `kernelcache_sha256`
与本机 kernelcache 的 sha256，不一致直接拒绝（`K60_ALLOW_FOREIGN_FIXTURE=1` 只能用于查看）。
判据测试：`scripts/tests/test-display-fixture-provenance.py`（5 例）。

剩下两条路，都需要语义决定，不能靠猜：

* **A：surface 组由本组件实现**——把这 8 个 slot 标成 owned，在组件里实现
  descriptor/width/height/stride/format/planes/create/allocate 的等价语义。代价是要读
  `NativeLegacyDisplay.cpp` 里 10 处 surface 调用，确认它们只需要「一块我们自己的内存 + 尺寸」。
* **B：从本机 kernelcache 重新枚举 213 个 slot**——正确但工作量大，仓库里没有现成枚举器
  （`kits/XnuPrelink/kc_image.py` 只解 chained fixup，不解 C++ vtable 布局）。

在作出决定之前，构建会停在这道 provenance 门禁上，而不是带着错误地址进 prelink。

### 10.1 本机 24A446 的 kext 段实测

用 `kits/XnuPrelink/kc_image.py` 解析 `/home/emilelu/kc24A446/ipsw/24A446/kernelcache.decompressed`
（sha256 `fa07057bf34f33af1ec26681ad0c87c13e5aaa548a300740eddb0e92876e5f95`，305 个 kext entry）：

| kext | `__TEXT_EXEC` va | size |
| --- | --- | --- |
| `com.apple.iokit.IOMobileGraphicsFamily` | `0xfffffff00a1778f0` | `0x23230` |
| `com.apple.iokit.IOThunderboltFamily` | `0xfffffff00a35eb40` | `0x1d000c` |
| `com.apple.iokit.IOAVFamily` | `0xfffffff009e19db0` | `0x7e9dc` |

`0xfffffff00a42f464`、`0xfffffff00a4330a4`、`0xfffffff00a444a68` 三个探针地址全部落在
`IOThunderboltFamily` 的 `__TEXT_EXEC` 内，不在 `IOMobileGraphicsFamily`（结束于
`0xfffffff00a39aa20`）。这与 §10 的结论一致：它们属于另一份 kernelcache 的另一个 kext。

复现命令：`python3 /mnt/e/k60-work/scratch/probe_kexts.py`（脚本只读，不构建）。
