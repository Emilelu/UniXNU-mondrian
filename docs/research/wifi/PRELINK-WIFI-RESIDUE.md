# 预链接 Wi-Fi 残留与三页官网页

> 只读记录。检查基线：`feat/wifi-ios27-tree` @ `5d2dfd6f`。没有构建、没有上机、没有修改
> `E:/hackios/k60-gates` 或共享 main。本文回答两个问题：24A446 预链接记录里 Wi-Fi 的 0 出现
> 说明什么；`building.md`、`porting/soc-support.md`、`drivers/ath12k-wifi.md` 三页怎么进官方
> 文档账本。

## 0. 结论

- 24A446 的 `prelink-regression.json` 是 iPad17,3 的基线，不是 iPhone17,2；`ios-27.0.1-24A446`
  的 profile 没有 `regression_policy`，所以本线 build 从不执行 `check_prelink_regressions`。
- 磁盘上的 `kernel.json` 是 93,061,120 B 的候选内核（`candidate_sha256 dee01c54…`）。同一棵树的
  native 内核是 23,783,640 B，`check-wifi-symbols.py` 报 0 个 Wi-Fi 符号；`kernel.map.json` 和
  `kernel.macho` 的 Wi-Fi 字符串也是 0。它不是本线 35,613,936 B 的历史 Wi-Fi 链接。
- 因此「missing/stubbed 里 0 个 Wi-Fi bundle」是构造性的：这张图没有链接 station；而且
  `missing`/`stubbed` 记的是 kext bundle 的未解析引用，station 是 `-force_load` 进内核的归档，
  不是 kext。预链接记录既不能证明也不能否定 Wi-Fi。
- Wi-Fi 的验收仍然只有两条线内命令：`scripts/check-wifi-station-archive.py`（arm64e、两个 API、
  stamp/header）和 `scripts/check-wifi27-link-inputs.py`（arch、provenance、stubs）。
  `check-ios27-artifacts.py --flight-ready` 不读链接账本。
- 三页：`building.md` 可 mapped 到 `check-ios27-artifacts.py --flight-ready`；`porting/soc-support.md`
  可 mapped 到 `check-device-tree.py`，但它只覆盖设备树半边，feed 的 40 字符 pin 仍靠
  `unixnu fetch/status`；`drivers/ath12k-wifi.md` 保持 unmapped，等
  `check-wifi-station-archive.py` 从 device 仓提升到 `k60-gates/scripts` 并让归档通过后才能 mapped。
  `drivers/wifi*.md` 不存在，`ath12k-wifi.md` 就是 Wi-Fi 驱动页。

## 1. A：预链接记录里有没有 Wi-Fi

### 1.1 policy 的适用域

`E:/hackios/UniXNU/scripts/policies/ipados-27.0.1-24A446/prelink-regression.json` 的抬头就写着
“This bounds regressions, not runtime qualification.”（:3）。它绑定的是 iPad17,3 的 kernelcache，
不是我们的 iPhone17,2。

| 项 | iPad17,3 policy | 本线 iOS27 build 20 |
| --- | --- | --- |
| `kernelcache_sha256` | `38e6d9fa…`（policy:2） | `fa07057b…`（`profiles/os/ios-27.0.1-24A446/profile.toml:35`） |
| `missing` | 2 bundle / 2 site（:8-15） | 3 bundle / 3 site |
| `stubbed` | 10 bundle / 24 site（:16-61） | 25 bundle / 205 site |
| `required_original_branches` | 2 条（:4-7） | `native_original_branches` 为空 |
| profile 接线 | `profiles/os/ipados-27.0.1-24A446/profile.toml:34` 有 `regression_policy` | `profiles/os/ios-27.0.1-24A446/profile.toml:29-43` 没有 |

`scripts/unixnu/kernel.py:241-253` 是检查器的全部语义：把记录里的地址减去 `collection_slide`，
按 owner + 原始地址查 policy 允许值，计数大于允许值就报 `prelink regression`；最后要求
`required_original_branches` 全部出现在 `native_original_branches`。`kernel.py:297-301` 只在
profile 有 `regression_policy` 时才读 policy，且 `:299` 会拒绝 kernelcache 哈希不同的 policy。
我们的 iOS profile 没有这个键，所以这些检查在本线根本没有运行；即使强行挂上 iPad policy，
`:299` 也会因为 `38e6… != fa07…` 直接报 “prelink regression policy names another kernelcache”。

结论：iPad policy 的 2/24 不能拿来和本线的 3/205 比较，也不能拿来证明 Wi-Fi 干净或不干净。

### 1.2 磁盘上的 `kernel.json` 是哪张图

记录在 `/opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/kernel/kernel.json`
（14,078 B，2026-11-21）：

- `format = MH_FILESET`、`closure` 38 条、`collection_slide = 0x0`、`native_original_branches = []`。
- `candidate_bytes = 93061120`、`candidate_sha256 = dee01c54a73edf594bbe866ae020cb3331d31afe3edc4616b1a6fc0a34fbaad0`。
- `native` 指向同一棵树的 `build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837.unstripped.noctf`；
  这个文件 23,783,640 B，`scripts/check-wifi-symbols.py` 报 `wifi symbols: 0 (none)`。
- `loadable`、`mapping_complete`、`runtime_qualified` 都是 `false`。

`kernel.map.json`（3,028,736 B）的 `inputs` 只有三项：`kernelcache_sha256 = fa07057b…`、
`native_sha256 = b13875da…`、`entry = com.apple.kernel`。它没有归档清单，也没有 Wi-Fi；
`functions` 16,899 条、`data` 797 条、`conflicts` 57 条，整份 JSON 的 Wi-Fi 关键字 0 命中。
`kernel.macho` 是 93,061,120 B 的预链接输出；`strings` 搜 `PongWifi|pong_wifi|ath11k|nw_wifi`
为 0；`llvm-nm` 对它报 `no symbols`，因为 fileset 输出已经被剥符号。

这不是本线的 Wi-Fi 链接。本线的历史 Wi-Fi 镜像是 `/tmp/ios27ext4/…/DEVELOPMENT_ARM64_BCM2837`
下的 35,613,936 B 文件，30 个 Wi-Fi 符号，链接时 `-force_load` 了 `teardown27g/libPongWifiNative.a`
和 `/mnt/e/k60-work/scratch/libStub27.a`（`docs/research/wifi/FLIGHT-CRITERIA-REVIEW.md:45-50`）。
那份镜像没有预链接记录，也没有 `kernel.json`；它和 93 MB 的共享输出不是同一张图。

### 1.3 `missing` / `stubbed` 实测

`missing` 3 个 bundle / 3 个 site：`AppleARMWatchdogTimer` 1、`IOHIDFamily` 1、
`com.apple.security.sandbox` 1。

`stubbed` 25 个 bundle / 205 个 site：`AppleFSCompressionTypeZlib` 1、`AppleARMPlatform` 17、
`AppleARMWatchdogTimer` 6、`AppleEffaceableStorage` 2、`AppleIISController` 2、
`AppleM2ScalerCSCDriver` 4、`AppleMobileFileIntegrity` 41、`ApplePMGR` 7、`IODARTFamily` 1、
`apfs` 20、`CoreAnalyticsFamily` 3、`IOAVFamily` 16、`IOAudio2Family` 1、
`IOCryptoAcceleratorFamily` 2、`IOGPUFamily` 10、`IOHDCPFamily` 2、`IOHIDFamily` 14、
`IOMobileGraphicsFamily` 1、`IOReportFamily` 1、`IOStorageFamily` 5、`IOSurface` 9、
`kec.corecrypto` 3、`AppleImage4` 7、`Image4` 7、`sandbox` 23。

与 Lead 给的 3 / 205 一致。extra `com.apple.security.sandbox` 的 missing 和这 205 个 stub 都是
sandbox/kext 覆盖差异，不应记到 Wi-Fi 头上。

### 1.4 0 命中的含义

对整份 `kernel.json`、`kernel.map.json`、native 内核和 `kernel.macho` 做 Wi-Fi 关键字/符号检查，
结果都是 0。这个 0 有三层原因，任何一层都足以让它不能当 Wi-Fi 结论：

1. **这张图没有链接 station。** native 内核 23,783,640 B、0 个 Wi-Fi 符号；本线的 Wi-Fi native
   是 35,613,936 B、30 个符号。记录属于前者。
2. **prelink 的 missing/stubbed 不是内核符号表。** 它按 kext bundle 记未解析引用；station 由
   `scripts/build-xnu-generic.sh` 的 `XNU_PONG_WIFI` 钩子用 `-force_load` 带进内核，不是 kext，
   不会出现在这两个字典里。
3. **最终 `kernel.macho` 已剥符号。** `llvm-nm` 报 `no symbols`；能读符号的是 native `.noctf`，
   不是预链接输出。

所以正确的说法不是「27 的 Wi-Fi 栈不在预链接集合里，所以它是干净的」，而是「预链接记录没有
建模 Wi-Fi station，0 命中只是这张图没带它」。

### 1.5 预链接不能验收 Wi-Fi

如果要在预链接侧验收 Wi-Fi，至少需要三件现在没有的东西：

1. 一个 iOS 27、iPhone17,2 的 `regression_policy`，其 `kernelcache_sha256` 是 `fa07057b…`，
   而不是 iPad 的 `38e6…`；
2. 一份在该 kernelcache 上取得资格的基线；
3. 一种能把 `-force_load` 进内核的 station 符号和 kext 的 missing/stubbed 分开的表示。当前
   `kernel.map.json` 的 `functions`/`data` 是 reference-driven 的，不能替代这项。

在这些出现之前，Wi-Fi 的验收只有两条线内命令：

- `scripts/check-wifi-station-archive.py`：成员 arm64e、`_nw_wifi_power` 与
  `_nw_wifi_scan_frequencies` 已定义、`abi/nw_abi.stamp` 的 `ie_bytes`/`header_sha256` 对齐
  `abi/nw_abi.h`；
- `scripts/check-wifi27-link-inputs.py`：`linkarchives` 的 arch、provenance、stubs 三条断言。

`check-ios27-artifacts.py --flight-ready` 只读最终 Mach-O/payload/boot.img 和 `kernel.json` 的
`missing_refs`/`stubbed_refs`，不读链接账本（`FLIGHT-CRITERIA-REVIEW.md:24-25`），所以它看不见
station 的架构/来源/桩。

## 2. B：三页官网页

### 2.1 账本机制

`E:/hackios/k60-gates/docs/engineering/OFFICIAL-REQUIREMENTS.toml` 实测 103 页：20 mapped、
1 na、82 unmapped。`check-official-docs.py:59-61` 的 `gate_exists()` 只检查 `k60-gates/scripts`
或 `scripts/tests` 下有没有这个名字，**不执行 gate**；`:89-98` 对 mapped 要求 gate + assertion，
对 na 要求 why。因此 device 仓里的 `scripts/check-wifi-station-archive.py` 不能直接写进账本，
必须先复制/提升到 `k60-gates/scripts`。这一点决定了下面三页的写法。

### 2.2 `building.md`

页面在 `E:/hackios/UniXNU/docs/zh/building.md:52-70` 给出三个输出：
`<output>/kernel/kernel.macho`（:65）、`AARCH64-DEBUG/UniXNU.efi`（:66）、`[firmware] fd`（:67）；
前面的 `defconfig`/`fetch`/`status` 在 :23-25，`ipsw info/fetch/tree` 在 :44-46。

本线对应：`scripts/build-wifi27-kernel.sh:48-56` 用 `python3 unixnu build kernel --device … --os
ios-27.0.1-24A446`，然后找 `mach.development.*.unstripped.noctf` 并数符号；
`scripts/tests/test-build-wifi27-kernel.py` 钉住默认 OS、archive 缺失退 2、未知参数退 2、
`find` 深度 ≥7。它不跑 `build package`、`build firmware`、`userdata`，也不声称跑过。

建议：mapped 到 `check-ios27-artifacts.py --flight-ready`，assertion 只写内核/payload/boot.img
这一半，package/firmware/userdata 留给各自的页。

### 2.3 `porting/soc-support.md`

页面要求：`UniXNU-<soc>-common` 的 `soc.toml`、`dts/<soc>.dtsi`、`configs/<soc>.config`、
`patches/xnu/series`、`kits/`（:33-70）；设备 `feeds.toml` 用固定提交选 SoC（:72-80）；
`board.toml` 设 `soc`/`soc_source`/`os_profile`、`[device_tree]` 和 `[kernel]` 的
`config_fragments`/`patch_series`（:82 起）。

本板对应：`board.toml:5-7` 是 `SM8475`/`sm8475`/`ios-27.0.1-24A446`；`:14` 的 components 是
`ArmDTPlatform`、`ArmCpu`、`XnuPrelink`、`PongUfs`；`:18`/`:20` 是 16 线的 config/series；
27 override 在 `:355-387`，`:364` 用 `arch/soc/os` 三个 config fragment，`:369` 用
`arch/soc/os/device` 四层 series。`feeds.toml:7-14` 把 `sm8475` 固定在
`20a30fd623dbcfacdd71350a24fae67a2158884f`（xNekom/UniXNU-sm8475-common）。

建议：mapped 到 `check-device-tree.py`，assertion 写「`[device_tree]` 的 `soc:` include 能通过
已取回的 SM8475 feed 解析，`dtc` 接受整棵树」。该 gate 的 `find_soc_feed()`（:63-72）只按
include 文件找 feed，不校验 40 字符 commit；commit pin 由 `unixnu fetch/status --json` 解析。
如果账本要强制 pin，需要一个新 `check-feed-pins.py`，本次只建议、不实现。
`check-27-series-composition.py`（:1-28）可作为四层 series 的伴随检查，它同样消费已取回的 feed，
不单独校验 pin。`check-component-pin.py` 只对 `[components]` 与 catalog 的 pin，不管 SoC feed；
`Ath12kWifi` 也不在 `[components]` 里。

### 2.4 `drivers/ath12k-wifi.md`

页面把生产路径写得很清楚：ath12k/mac80211/cfg80211 + 用户态 wpa_supplicant 2.12（:3-5），
sheng 的 iPadOS 27 集成是 WifiProbe/WifiNet、`/arm-io/wlan`、128 MiB DMA、签名 supplicant、
`/private/var/ngpu/etc/wifi/`、launchd cache 合并（:34-49），24A446 关联请求 592/656 B、
540 B 异步结果、结果/有效标志在 0x214/0x218（:51-52），启动参数 `sheng-wifi=5`、
`sheng-wifi-aj=0`、`log-wifi=1`（:60-64），验证命令在 Ath12kWifi `tools/`（:68-88）。

本线的实际路径不是这个页面的生产路径：仓内只有 `drivers/PongWifi`，station 由
`scripts/build-k60-ath11k.py` 从外部源码根 `E:/k60-work/impl/ath12kwifi27` 编成归档；
`drivers/Ath12kWifi` 在本仓库不存在（`git ls-tree HEAD drivers/Ath12kWifi` 为空，
`drivers/` 下只有 `PongWifi`）。sheng 仓 `E:/k60-work/impl/sheng27-full` 里的
`drivers/Ath12kWifi` 才是 gitlink `f087c7dd…`；不要把它当成我们的路径。

当前候选 `ath11k-abi27e/libPongAth11k.a` 用新检查器实测：成员 arm64e、stamp/header 通过，
但 `_nw_wifi_power` 和 `_nw_wifi_scan_frequencies` 都是 undefined（`FAIL station API`，rc=1）。
源码定义在 `E:/k60-work/impl/ath12kwifi27/src/nw_mainline.c:223`（scan frequencies）与
`:266`（power）；当前 `scripts/build-k60-ath11k.py:720-722` 的 `common_sources` 还是 16 的
`src/nw_sta.c`，没有把 `nw_mainline.c` 编进去。所以即使现在把页面 mapped 到 station 归档
检查器，它也会红；先补源清单/重建归档，再谈 mapped。

建议：现在保持 `unmapped`；把 `scripts/check-wifi-station-archive.py` 提升到
`k60-gates/scripts` 后，等归档通过再写 `mapped`，assertion 用「成员 arm64e、两个 API 已定义、
stamp/header 对齐」。`check-wifi27-link-inputs.py` 是出图前的线内 preflight（arch/provenance/stubs），
它不能替代这个页面的 ABI 检查。

### 2.5 没有 `drivers/wifi*.md`，为什么不是 na

`E:/hackios/UniXNU/docs/zh/drivers` 有 47 个 `.md`，只有 `ath12k-wifi.md` 命中 wifi；
`drivers/wifi*.md` 不存在。Wi-Fi 驱动页就认领 `ath12k-wifi.md`。

不能写 na：页面的生产路径（主线 station、supplicant、540 B 结果、launchd cache）直接约束本板；
我们的 station 归档和这个页面是同一件事。它是 unmapped 债，不是豁免。

## 3. 建议 Lead 合并的 TOML stanza

下面三段只改 `OFFICIAL-REQUIREMENTS.toml`，不改 `k60-gates` 的任何脚本。

```toml
[[page]]
path = "building.md"
title = "构建与启动"
sha256 = "44bfb3eea57de117b2e333241cfdc12637b9f922092e1f743527bae403e47c28"
state = "mapped"
gate = "check-ios27-artifacts.py --flight-ready"
assertion = "the 24A446 kernel.macho, payload and boot.img exist and pass the declared transform; package/firmware/userdata stay on their own pages"

[[page]]
path = "porting/soc-support.md"
title = "选择与添加 SoC 支持"
sha256 = "be9c587e88867def4f6b3428e0b937ed0fbf2b9299ac93e150d3b5303e2f9680"
state = "mapped"
gate = "check-device-tree.py"
assertion = "board [device_tree] resolves soc: includes through the fetched SM8475 feed and dtc accepts the tree; the 40-character feed pin is resolved by unixnu fetch/status, not by this gate"

[[page]]
path = "drivers/ath12k-wifi.md"
title = "Ath12kWifi"
sha256 = "45384811d658b0bcb624b973b14ef85e957ccb9c1160d9f66fd55f883e76779b"
state = "unmapped"
# Promote scripts/check-wifi-station-archive.py into k60-gates/scripts first; the current
# ath11k-abi27e archive is arm64e and its stamp matches, but it does not define
# _nw_wifi_power or _nw_wifi_scan_frequencies. Set mapped only after it passes.
```

## 4. 未关闭的边界

- C1（22H374 的 selector/ioctl 传输）、C2（launchd 任务与 `/usr/libexec` 视图）、C3（24A446
  `kSupportedChannels` 的 0x80 证据）都保持 open；C3 没有真实 24A446 消费者证据，不拿 22H374
  代替，也不猜 0x80。
- 本文没有构建、没有预链接、没有上机；93 MB 的 `kernel.json` 不是 Wi-Fi 图，35,613,936 B 的历史
  图有九个 scratch 桩、不可启动，两者都不能当验收。
- 建议的 stanza 是给 Lead 合并的；本线没有改 `E:/hackios/k60-gates`，也没有把 device 仓脚本
  复制进共享仓。
