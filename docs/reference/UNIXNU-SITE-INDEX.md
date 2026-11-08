# UNIXNU-SITE-INDEX — unixnu.com 官网动态内容索引（人读入口）

> 本索引是 **unixnu.com 官网动态内容**的唯一入口，由程序生成，**禁止手改**。
> 重建：`python E:\k60-work\tools\unixnu-site\fetch.py --incremental`（自动重建本文件）。
> 生成时间：2026-11-04T08:48:18+08:00；收录 en 332 页 + zh 镜像（zh 与 en 逐页镜像，url 加 `/zh` 前缀，明细见机读索引）。

## 查询纪律（硬约束）

1. **实时优先**：任何 agent 查询官网内容必须先走网络取最新——
   `python E:\k60-work\tools\unixnu-site\query.py --live /devices/mondrian`
2. 本地存档只用于 diff 与离线兜底，**不得作为事实来源**；引用存档内容必须标注「存档 YYYY-MM-DD」（fetched_at）。
3. 本索引与 [INDEX.md](../INDEX.md)（项目文档入口）、[MASTER-INDEX.md](MASTER-INDEX.md)（本地资产地图）分工：
   INDEX 管项目文档，MASTER-INDEX 管本地资产，本文件管**官网远端内容**。
4. 机读入口：`unixnu-site-index.json`（全站）、`devices-map.json`（设备页→设备仓映射，字段 v2 2026-11-04：新增 soc/soc_source/doc_kind/device_list 条目；soc 只取官网标题、设备总表、主登记继承三处证据，不反推；缺证名单见 `missing-soc.txt`）。
5. 定时增量（建议每天一次，由主控挂载）：
   `python E:\k60-work\tools\unixnu-site\fetch.py --incremental >> E:\k60-work\references\unixnu-site\cron.log 2>&1`
   失败告警：进程退出码非 0（2=有页面失败，3=清单不可达），日志见 cron.log 与 `references\unixnu-site\CHANGES-<date>.md`。

## 本项目强相关（置顶：mondrian/K60/SM8475 + 参照设备 + 官方方法论文档）

| 页面 | 一句话摘要 | 更新于 | 官网 URL | 本地存档 |
|---|---|---|---|---|
| [Redmi K60 (mondrian/SM8475): UniXNU UEFI bring-up](https://unixnu.com/devices/mondrian) | Emilelu/UniXNU-mondrian | 2026-11-03 | https://unixnu.com/devices/mondrian | `E:/k60-work/references/unixnu-site/en/devices/mondrian.md` |
| [Redmi K60 (mondrian/SM8475): UniXNU UEFI bring-up (mzyxsl)](https://unixnu.com/devices/mondrian-mzyxsl) | mzyxsl/UniXNU-mondrian | 2026-11-03 | https://unixnu.com/devices/mondrian-mzyxsl | `E:/k60-work/references/unixnu-site/en/devices/mondrian-mzyxsl.md` |
| [Redmi K60 (mondrian/SM8475): UniXNU UEFI bring-up (wohusaixing)](https://unixnu.com/devices/mondrian-wohusaixing) | wohusaixing/UniXNU-mondrian | 2026-11-03 | https://unixnu.com/devices/mondrian-wohusaixing | `E:/k60-work/references/unixnu-site/en/devices/mondrian-wohusaixing.md` |
| [Redmi K60 (mondrian/SM8475): UniXNU UEFI bring-up (XTOM0706)](https://unixnu.com/devices/mondrian-xtom0706) | XTOM0706/UniXNU-mondrian | 2026-11-03 | https://unixnu.com/devices/mondrian-xtom0706 | `E:/k60-work/references/unixnu-site/en/devices/mondrian-xtom0706.md` |
| [Nothing Phone (2) (pong)](https://unixnu.com/devices/pong) | Chengdong-Yu/UniXNU-pong | 2026-11-03 | https://unixnu.com/devices/pong | `E:/k60-work/references/unixnu-site/en/devices/pong.md` |
| [Nothing Phone (2): UniXNU UEFI bring-up (AGXMX666)](https://unixnu.com/devices/pong-agxmx666) | AGXMX666/UniXNU-pong | 2026-11-03 | https://unixnu.com/devices/pong-agxmx666 | `E:/k60-work/references/unixnu-site/en/devices/pong-agxmx666.md` |
| [UniXNU](https://unixnu.com/devices/pong-hxzbaka) |  | 2026-11-03 | https://unixnu.com/devices/pong-hxzbaka | `E:/k60-work/references/unixnu-site/en/devices/pong-hxzbaka.md` |
| [UniXNU](https://unixnu.com/devices/pong-y3d4) | Y3d4/UniXNU-pong-clean | 2026-11-03 | https://unixnu.com/devices/pong-y3d4 | `E:/k60-work/references/unixnu-site/en/devices/pong-y3d4.md` |
| [Xiaomi Pad 6S Pro (sheng)](https://unixnu.com/devices/sheng) | Xiaomi Pad 6S Pro 12.4 uses shared SM8550 support and board-owned storage, input | 2026-11-03 | https://unixnu.com/devices/sheng | `E:/k60-work/references/unixnu-site/en/devices/sheng.md` |
| [UniXNU](https://unixnu.com/devices/sheng-16crow) |  | 2026-11-03 | https://unixnu.com/devices/sheng-16crow | `E:/k60-work/references/unixnu-site/en/devices/sheng-16crow.md` |
| [Xiaomi Pad 6S Pro (airalex002)](https://unixnu.com/devices/sheng-airalex002) | airalex002/UniXNU-sheng | 2026-11-03 | https://unixnu.com/devices/sheng-airalex002 | `E:/k60-work/references/unixnu-site/en/devices/sheng-airalex002.md` |
| [UniXNU](https://unixnu.com/devices/sheng-alghiffaryfa19) | alghiffaryfa19/UniXNU-sheng | 2026-11-03 | https://unixnu.com/devices/sheng-alghiffaryfa19 | `E:/k60-work/references/unixnu-site/en/devices/sheng-alghiffaryfa19.md` |
| [Xiaomi Pad 6S Pro (bai805)](https://unixnu.com/devices/sheng-bai805) | Xiaomi Pad 6S Pro 12.4 uses shared SM8550 support and board-owned storage, input | 2026-11-03 | https://unixnu.com/devices/sheng-bai805 | `E:/k60-work/references/unixnu-site/en/devices/sheng-bai805.md` |
| [Xiaomi Pad 6S Pro (chenjin1494)](https://unixnu.com/devices/sheng-chenjin1494) | chenjin1494/UniXNU-sheng | 2026-11-03 | https://unixnu.com/devices/sheng-chenjin1494 | `E:/k60-work/references/unixnu-site/en/devices/sheng-chenjin1494.md` |
| [Xiaomi Pad 6S Pro (FFT-infra)](https://unixnu.com/devices/sheng-fft-infra) | FFT-infra/UniXNU-alioth-sheng-template | 2026-11-03 | https://unixnu.com/devices/sheng-fft-infra | `E:/k60-work/references/unixnu-site/en/devices/sheng-fft-infra.md` |
| [Xiaomi Pad 6S Pro (ht94911)](https://unixnu.com/devices/sheng-ht94911) | ht94911/UniXNU-sheng | 2026-11-03 | https://unixnu.com/devices/sheng-ht94911 | `E:/k60-work/references/unixnu-site/en/devices/sheng-ht94911.md` |
| [Xiaomi Pad 6S Pro (hxzbaka)](https://unixnu.com/devices/sheng-hxzbaka) | hxzbaka/UniXNU-sheng | 2026-11-03 | https://unixnu.com/devices/sheng-hxzbaka | `E:/k60-work/references/unixnu-site/en/devices/sheng-hxzbaka.md` |
| [UniXNU](https://unixnu.com/devices/sheng-jn7163) |  | 2026-11-03 | https://unixnu.com/devices/sheng-jn7163 | `E:/k60-work/references/unixnu-site/en/devices/sheng-jn7163.md` |
| [Xiaomi Pad 6S Pro (jsongmax)](https://unixnu.com/devices/sheng-jsongmax) | jsongmax/UniXNU-sheng | 2026-11-03 | https://unixnu.com/devices/sheng-jsongmax | `E:/k60-work/references/unixnu-site/en/devices/sheng-jsongmax.md` |
| [UniXNU](https://unixnu.com/devices/sheng-kkkpc) | kkkpc/UniXNU-fuxi-xiaomi13-forked-bypass-sheng | 2026-11-03 | https://unixnu.com/devices/sheng-kkkpc | `E:/k60-work/references/unixnu-site/en/devices/sheng-kkkpc.md` |
| [Xiaomi Pad 6S Pro (ks114514)](https://unixnu.com/devices/sheng-ks114514) | ks114514/UniXNU-sheng | 2026-11-03 | https://unixnu.com/devices/sheng-ks114514 | `E:/k60-work/references/unixnu-site/en/devices/sheng-ks114514.md` |
| [UniXNU](https://unixnu.com/devices/sheng-liangkam) | LiangKam/UniXNU-sheng | 2026-11-03 | https://unixnu.com/devices/sheng-liangkam | `E:/k60-work/references/unixnu-site/en/devices/sheng-liangkam.md` |
| [UniXNU](https://unixnu.com/devices/sheng-lilinnan) | lilinnan/UniXNU-sheng | 2026-11-03 | https://unixnu.com/devices/sheng-lilinnan | `E:/k60-work/references/unixnu-site/en/devices/sheng-lilinnan.md` |
| [Xiaomi Pad 6S Pro (Lithosss)](https://unixnu.com/devices/sheng-lithosss) | Lithosss/UniXNU-sheng | 2026-11-03 | https://unixnu.com/devices/sheng-lithosss | `E:/k60-work/references/unixnu-site/en/devices/sheng-lithosss.md` |
| [macOS on sheng](https://unixnu.com/devices/sheng-macos) | A community-maintained port for SM8550. Current results are based on the maintai | 2026-11-03 | https://unixnu.com/devices/sheng-macos | `E:/k60-work/references/unixnu-site/en/devices/sheng-macos.md` |
| [Xiaomi Pad 6S Pro (TheArchitectEngineer)](https://unixnu.com/devices/sheng-thearchitectengineer) | TheArchitectEngineer/UniXNU-sheng | 2026-11-03 | https://unixnu.com/devices/sheng-thearchitectengineer | `E:/k60-work/references/unixnu-site/en/devices/sheng-thearchitectengineer.md` |
| [Xiaomi Pad 6S Pro (tkings4chan)](https://unixnu.com/devices/sheng-tkings4chan) | tkings4chan/UniXNU-sheng | 2026-11-03 | https://unixnu.com/devices/sheng-tkings4chan | `E:/k60-work/references/unixnu-site/en/devices/sheng-tkings4chan.md` |
| [Xiaomi Pad 6S Pro (v1-727)](https://unixnu.com/devices/sheng-v1-727) | Xiaomi Pad 6S Pro 12.4 uses shared SM8550 support and board-owned storage, input | 2026-11-03 | https://unixnu.com/devices/sheng-v1-727 | `E:/k60-work/references/unixnu-site/en/devices/sheng-v1-727.md` |
| [Xiaomi Pad 6S Pro (yeyingjun-codes)](https://unixnu.com/devices/sheng-yeyingjun-codes) | yeyingjun-codes/UniXNU-sheng | 2026-11-03 | https://unixnu.com/devices/sheng-yeyingjun-codes | `E:/k60-work/references/unixnu-site/en/devices/sheng-yeyingjun-codes.md` |
| [UniXNU](https://unixnu.com/devices/sheng-yuyaukong) | yuyaukong/UniXNU-sheng | 2026-11-03 | https://unixnu.com/devices/sheng-yuyaukong | `E:/k60-work/references/unixnu-site/en/devices/sheng-yuyaukong.md` |
| [Redmi Note 10 Pro (sweet)](https://unixnu.com/devices/sweet) | A community-maintained port for SM7150. Current results are based on the maintai | 2026-11-03 | https://unixnu.com/devices/sweet | `E:/k60-work/references/unixnu-site/en/devices/sweet.md` |
| [Xiaomi Redmi Note 10 Pro (zeroninevibedslop)](https://unixnu.com/devices/sweet-zeroninevibedslop) | zeroninevibedslop/UniXNU-sweet | 2026-11-03 | https://unixnu.com/devices/sweet-zeroninevibedslop | `E:/k60-work/references/unixnu-site/en/devices/sweet-zeroninevibedslop.md` |
| [Microsoft Surface Duo 2 (zeta)](https://unixnu.com/devices/zeta) | A community-maintained port for SM8350. Current results are based on the maintai | 2026-11-03 | https://unixnu.com/devices/zeta | `E:/k60-work/references/unixnu-site/en/devices/zeta.md` |
| [Build and boot](https://unixnu.com/building) | `unixnu` resolves ARM64, SoC, OS, and device profiles, selects component depende | 2026-11-03 | https://unixnu.com/building | `E:/k60-work/references/unixnu-site/en/_root/building.md` |
| [Boot chain](https://unixnu.com/concepts/boot-chain) | UniXNU is a general UEFI environment and driver loading system, similar to OpenC | 2026-11-03 | https://unixnu.com/concepts/boot-chain | `E:/k60-work/references/unixnu-site/en/concepts/boot-chain.md` |
| [Boot payload](https://unixnu.com/concepts/payload) | The payload is a FAT volume that becomes the ramdisk of the Android boot image.  | 2026-11-03 | https://unixnu.com/concepts/payload | `E:/k60-work/references/unixnu-site/en/concepts/payload.md` |
| [Kernel prelink](https://unixnu.com/concepts/prelink) | The prelinked kernel combines a kernel built from source with the original Apple | 2026-11-03 | https://unixnu.com/concepts/prelink | `E:/k60-work/references/unixnu-site/en/concepts/prelink.md` |
| [Integrity and boot policy](https://unixnu.com/concepts/security) | UniXNU keeps the original Apple security components and supplies the inputs they | 2026-11-03 | https://unixnu.com/concepts/security | `E:/k60-work/references/unixnu-site/en/concepts/security.md` |
| [Userdata layout](https://unixnu.com/concepts/userdata) | The userdata partition carries the Darwin root file system. UniXNU keeps the ori | 2026-11-03 | https://unixnu.com/concepts/userdata | `E:/k60-work/references/unixnu-site/en/concepts/userdata.md` |
| [Boot the image](https://unixnu.com/guide/boot) | Follow Building through boot-image assembly first. The procedure below starts th | 2026-11-03 | https://unixnu.com/guide/boot | `E:/k60-work/references/unixnu-site/en/guide/boot.md` |
| [Build the kernel](https://unixnu.com/guide/build-kernel) | The kernel step builds Apple's XNU source with UniXNU patches, then prelinks the | 2026-11-03 | https://unixnu.com/guide/build-kernel | `E:/k60-work/references/unixnu-site/en/guide/build-kernel.md` |
| [Debugging and logs](https://unixnu.com/guide/debugging) | Collect firmware logs, kernel output, diagnostic screenshots and build reports f | 2026-11-03 | https://unixnu.com/guide/debugging | `E:/k60-work/references/unixnu-site/en/guide/debugging.md` |
| [MobileGestalt identity](https://unixnu.com/guide/mobilegestalt) | MobileGestalt answers device queries from the Apple device tree (ADT). The paylo | 2026-11-03 | https://unixnu.com/guide/mobilegestalt | `E:/k60-work/references/unixnu-site/en/guide/mobilegestalt.md` |
| [Port a device](https://unixnu.com/guide/overview) |  | 2026-11-03 | https://unixnu.com/guide/overview | `E:/k60-work/references/unixnu-site/en/guide/overview.md` |
| [Requirements](https://unixnu.com/guide/requirements) | 1. Choose the host toolchain for the steps you will run. Complete the macOS or L | 2026-11-03 | https://unixnu.com/guide/requirements | `E:/k60-work/references/unixnu-site/en/guide/requirements.md` |
| [Skip Setup](https://unixnu.com/guide/skip-setup) | Requires macOS image tools, a matching packed Data seed and the board's `skip_se | 2026-11-03 | https://unixnu.com/guide/skip-setup | `E:/k60-work/references/unixnu-site/en/guide/skip-setup.md` |
| [Userdata image](https://unixnu.com/guide/userdata) | The userdata image supplies the root file system to XNU. It holds the unchanged  | 2026-11-03 | https://unixnu.com/guide/userdata | `E:/k60-work/references/unixnu-site/en/guide/userdata.md` |
| [Welcome](https://unixnu.com/porting/) | UniXNU is a general UEFI environment and driver loading system, similar to OpenC | 2026-11-03 | https://unixnu.com/porting/ | `E:/k60-work/references/unixnu-site/en/porting/_index.md` |
| [arm64e OS profiles](https://unixnu.com/porting/arm64e) | **Applies to supported devices only.** Use this method only on a device that mee | 2026-11-03 | https://unixnu.com/porting/arm64e | `E:/k60-work/references/unixnu-site/en/porting/arm64e.md` |
| [Baseband and cellular adaptation](https://unixnu.com/porting/baseband) | Wi-Fi-only tablets without a cellular modem can skip this page. Set the cellular | 2026-11-03 | https://unixnu.com/porting/baseband | `E:/k60-work/references/unixnu-site/en/porting/baseband.md` |
| [Bring-up order](https://unixnu.com/porting/bring-up) | Bring-up proceeds in stages. Each stage has a visible result and a log line. Iso | 2026-11-03 | https://unixnu.com/porting/bring-up | `E:/k60-work/references/unixnu-site/en/porting/bring-up.md` |
| [Device repository](https://unixnu.com/porting/device-repository) | Complete steps 1 through 4 of Port a device before using this field reference. T | 2026-11-03 | https://unixnu.com/porting/device-repository | `E:/k60-work/references/unixnu-site/en/porting/device-repository.md` |
| [Device tree](https://unixnu.com/porting/device-tree) | Format 2 compiles a hardware tree and generates the Apple device tree centrally. | 2026-11-03 | https://unixnu.com/porting/device-tree | `E:/k60-work/references/unixnu-site/en/porting/device-tree.md` |
| [Display and brightness](https://unixnu.com/porting/display) | Start after platform and memory. Collect the firmware GOP base, size, dimensions | 2026-11-03 | https://unixnu.com/porting/display | `E:/k60-work/references/unixnu-site/en/porting/display.md` |
| [Adapt the drivers](https://unixnu.com/porting/drivers) | Use this checklist after creating and resolving the device repository. Start wit | 2026-11-03 | https://unixnu.com/porting/drivers | `E:/k60-work/references/unixnu-site/en/porting/drivers.md` |
| [UniXNU partition (experimental)](https://unixnu.com/porting/dual-system-partition) | `scripts/dual_sys/partition.py` detects the device and partition layout through  | 2026-11-03 | https://unixnu.com/porting/dual-system-partition | `E:/k60-work/references/unixnu-site/en/porting/dual-system-partition.md` |
| [GPU and Metal adaptation](https://unixnu.com/porting/gpu) | Complete platform DMA and basic display presentation first. Read the Adreno740 r | 2026-11-03 | https://unixnu.com/porting/gpu | `E:/k60-work/references/unixnu-site/en/porting/gpu.md` |
| [GPU frame diagnostics](https://unixnu.com/porting/gpu-diagnostics) | The reference latency capture records only the evidence for seven frame-latency  | 2026-11-03 | https://unixnu.com/porting/gpu-diagnostics | `E:/k60-work/references/unixnu-site/en/porting/gpu-diagnostics.md` |
| [Touch and button adaptation](https://unixnu.com/porting/input) | Complete display geometry and interrupt/DMA setup. Record touch-controller model | 2026-11-03 | https://unixnu.com/porting/input | `E:/k60-work/references/unixnu-site/en/porting/input.md` |
| [Capture logs and automate boot tests](https://unixnu.com/porting/log-capture) | Set up log capture as you bring up the board. Start with firmware logs, collect  | 2026-11-03 | https://unixnu.com/porting/log-capture | `E:/k60-work/references/unixnu-site/en/porting/log-capture.md` |
| [Migrate a device port](https://unixnu.com/porting/migration) | Format 2 lets devices reuse SoC support, OS profiles and component build recipes | 2026-11-03 | https://unixnu.com/porting/migration | `E:/k60-work/references/unixnu-site/en/porting/migration.md` |
| [Wi-Fi adaptation](https://unixnu.com/porting/network) | Start with platform interrupts and DMA. Identify the actual radio, PCI ID, firmw | 2026-11-03 | https://unixnu.com/porting/network | `E:/k60-work/references/unixnu-site/en/porting/network.md` |
| [Device packaging script](https://unixnu.com/porting/packaging) | **Mandatory for every device repository.** A device repository carries `scripts/ | 2026-11-03 | https://unixnu.com/porting/packaging | `E:/k60-work/references/unixnu-site/en/porting/packaging.md` |
| [Platform, memory and OS services](https://unixnu.com/porting/platform) | Start with a resolved device repository. Read the device-tree bindings, matching | 2026-11-03 | https://unixnu.com/porting/platform | `E:/k60-work/references/unixnu-site/en/porting/platform.md` |
| [DSP, audio and power drivers](https://unixnu.com/porting/power) | Complete platform memory, interrupts and DMA first. Implement the transport, dev | 2026-11-03 | https://unixnu.com/porting/power | `E:/k60-work/references/unixnu-site/en/porting/power.md` |
| [Device porting records](https://unixnu.com/porting/records) | Format 2 device repositories maintain `porting.toml`. Maintainers and agents upd | 2026-11-03 | https://unixnu.com/porting/records | `E:/k60-work/references/unixnu-site/en/porting/records.md` |
| [Select and add SoC support](https://unixnu.com/porting/sm8550) | Select and add SoC support | 2026-11-03 | https://unixnu.com/porting/sm8550 | `E:/k60-work/references/unixnu-site/en/porting/sm8550.md` |
| [Select and add SoC support](https://unixnu.com/porting/soc-support) | A SoC repository supplies hardware descriptions and platform code shared by boar | 2026-11-03 | https://unixnu.com/porting/soc-support | `E:/k60-work/references/unixnu-site/en/porting/soc-support.md` |
| [Port a device](https://unixnu.com/porting/steps) | UniXNU runs iOS or macOS on ARM64 devices through UEFI. The welcome page explain | 2026-11-03 | https://unixnu.com/porting/steps | `E:/k60-work/references/unixnu-site/en/porting/steps.md` |
| [UEFI firmware](https://unixnu.com/porting/uefi-firmware) | The UEFI firmware port comes from Mu-Silicium. It supplies the services UniXNU a | 2026-11-03 | https://unixnu.com/porting/uefi-firmware | `E:/k60-work/references/unixnu-site/en/porting/uefi-firmware.md` |
| [UFS porting](https://unixnu.com/porting/ufs) | Start with the storage section of the device's `porting.toml` and the component  | 2026-11-03 | https://unixnu.com/porting/ufs | `E:/k60-work/references/unixnu-site/en/porting/ufs.md` |
| [Technical reference](https://unixnu.com/reference/) | Use this page to find the file, procedure and verification for a change. For a c | 2026-11-03 | https://unixnu.com/reference/ | `E:/k60-work/references/unixnu-site/en/reference/_index.md` |
| [Boot configuration](https://unixnu.com/reference/boot-configuration) | The UniXNU boot manager reads `\EFI\UniXNU\unixnu.toml` from the volume it was s | 2026-11-03 | https://unixnu.com/reference/boot-configuration | `E:/k60-work/references/unixnu-site/en/reference/boot-configuration.md` |
| [Command line](https://unixnu.com/reference/cli) | Options follow the command. The driver reads a device repository from `-D`, `UNI | 2026-11-03 | https://unixnu.com/reference/cli | `E:/k60-work/references/unixnu-site/en/reference/cli.md` |
| [Component catalog](https://unixnu.com/reference/components) | `components.toml` in UniXNU records the maintained components. Profiles select c | 2026-11-03 | https://unixnu.com/reference/components | `E:/k60-work/references/unixnu-site/en/reference/components.md` |
| [Device configuration](https://unixnu.com/reference/configuration) | Format 2 uses `schema_version = 2` at the top of `board.toml`. Files without thi | 2026-11-03 | https://unixnu.com/reference/configuration | `E:/k60-work/references/unixnu-site/en/reference/configuration.md` |
| [Glossary](https://unixnu.com/reference/glossary) | - Port a device - Command line - Devices | 2026-11-03 | https://unixnu.com/reference/glossary | `E:/k60-work/references/unixnu-site/en/reference/glossary.md` |
| [Output layout](https://unixnu.com/reference/output-layout) | Format 2 isolates outputs by device, OS profile, and configuration under `out/`. | 2026-11-03 | https://unixnu.com/reference/output-layout | `E:/k60-work/references/unixnu-site/en/reference/output-layout.md` |
| [QEMU testing](https://unixnu.com/reference/qemu) | QEMU tests UniXNU, the injection paths, DarwinBoot and the kernel entry without  | 2026-11-03 | https://unixnu.com/reference/qemu | `E:/k60-work/references/unixnu-site/en/reference/qemu.md` |
| [Troubleshooting](https://unixnu.com/reference/troubleshooting) | 1. Save the failing command and first error. For a boot failure, record the last | 2026-11-03 | https://unixnu.com/reference/troubleshooting | `E:/k60-work/references/unixnu-site/en/reference/troubleshooting.md` |
| [Boot arguments](https://unixnu.com/xnu/boot-arguments) | The effective command line combines `[payload] kernel_args` in the board profile | 2026-11-03 | https://unixnu.com/xnu/boot-arguments | `E:/k60-work/references/unixnu-site/en/xnu/boot-arguments.md` |
| [Four-kilobyte pages](https://unixnu.com/xnu/four-k-page-tables) | Apple ARM64 kernels use a 16 KiB page on most SoCs. Non-Apple ARM64 SoCs commonl | 2026-11-03 | https://unixnu.com/xnu/four-k-page-tables | `E:/k60-work/references/unixnu-site/en/xnu/four-k-page-tables.md` |
| [Patch reference](https://unixnu.com/xnu/patch-reference) | Format 2 applies `[kernel] patch_series` in declared order. Series can reference | 2026-11-03 | https://unixnu.com/xnu/patch-reference | `E:/k60-work/references/unixnu-site/en/xnu/patch-reference.md` |
| [Source and patches](https://unixnu.com/xnu/source-and-patches) | The selected OS profile pins XNU and its ABI inputs. The arm64 iPadOS 17.7.11 pr | 2026-11-03 | https://unixnu.com/xnu/source-and-patches | `E:/k60-work/references/unixnu-site/en/xnu/source-and-patches.md` |

## 全站分栏目（en；zh 为逐页镜像）

### devices（202 页）

| 页面 | 摘要 | 更新于 | 本地存档 |
|---|---|---|---|
| [Devices](https://unixnu.com/devices/) | Open a device page for its sources, configuration and porting record.  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/_index.md` |
| [Benesse TAB-A04-BR3 (a04br3)](https://unixnu.com/devices/a04br3) | a04br3 is the Benesse TAB-A04-BR3 tablet with the MediaTek MT8167 SoC, | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/a04br3.md` |
| [OnePlus Ace 6 PLQ110 (OP6113L1): SM8750 Sun v1, 12 GiB, AA605 panel, S3910 touch](https://unixnu.com/devices/ace6) | xiaoan919/UniXNU-ace6 | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/ace6.md` |
| [Redmi K40 (alioth)](https://unixnu.com/devices/alioth) | FFT-infra/UniXNU-alioth | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/alioth.md` |
| [Xiaomi Redmi K40 (alioth, M2012K11AC) (fjcx555)](https://unixnu.com/devices/alioth-fjcx555) | fjcx555/UniXNU-alioth | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/alioth-fjcx555.md` |
| [Xiaomi Redmi K40 (alioth, M2012K11AC) (songchiyu)](https://unixnu.com/devices/alioth-songchiyu) | songchiyu/UniXNU-alioth | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/alioth-songchiyu.md` |
| [Xiaomi Redmi K40 (alioth, M2012K11AC) (Taishang1024)](https://unixnu.com/devices/alioth-taishang1024) | Taishang1024/UniXNU-alioth | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/alioth-taishang1024.md` |
| [Xiaomi Redmi K40 (alioth, M2012K11AC) (yang232138)](https://unixnu.com/devices/alioth-yang232138) | yang232138/UniXNU-alioth | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/alioth-yang232138.md` |
| [Redmi Note 14 Pro+ 5G (amethyst)](https://unixnu.com/devices/amethyst) | andr0d1v/UniXNU-amethyst | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/amethyst.md` |
| [Xiaomi Redmi Note 14 Pro+ 5G (BluedMC-Amethyst) (IOS4Amethyst)](https://unixnu.com/devices/amethyst-bluedmc-amethyst) | IOS4Amethyst/UniXNU-amethyst | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/amethyst-bluedmc-amethyst.md` |
| [Nothing Phone (3a) (asteroids)](https://unixnu.com/devices/asteroids) | rootstockos/UniXNU-asteroids | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/asteroids.md` |
| [BBK/EEBBK A2, X2 and X2P tablet (ums512_1h190, Unisoc T610 / UMS512 SharkL5Pro)](https://unixnu.com/devices/bbk-a2) | woshimaniubi8/unixnu-eebbk-a2_x2-ums512 | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/bbk-a2.md` |
| [Brave Ark tablet (braveark)](https://unixnu.com/devices/braveark) | Brave Ark tablet (braveark) is a SM8635 device. The port below is an i | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/braveark.md` |
| [OnePlus Pad Pro (caihong)](https://unixnu.com/devices/caihong) | A community-maintained port for SM8650. Current results are based on t | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/caihong.md` |
| [Redmi Note 10 5G (camellia)](https://unixnu.com/devices/camellia) | stanveyjiang/UniXNU-camellia | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/camellia.md` |
| [Xiaomi 10 Ultra (cas)](https://unixnu.com/devices/cas) | Xiaomi 10 Ultra: UEFI menu and CPU0 platform start verified; moving to | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/cas.md` |
| [UniXNU](https://unixnu.com/devices/cas-pxl777806) | pxl777806/UniXNU-cas | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/cas-pxl777806.md` |
| [Xiaomi Mi 9 (cepheus)](https://unixnu.com/devices/cepheus) | Xiaomi Mi 9 (cepheus) is a SDM855 device. The port below is an indepen | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/cepheus.md` |
| [UniXNU](https://unixnu.com/devices/cepheus-c0der88) | c0der88/UniXNU-cepheus | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/cepheus-c0der88.md` |
| [UniXNU](https://unixnu.com/devices/cepheus-didazhiqian) | didazhiqian/UniXNU-cepheus1 | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/cepheus-didazhiqian.md` |
| [UniXNU](https://unixnu.com/devices/cepheus-yangqi0408) | YangQi0408/UniXNU-cepheus | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/cepheus-yangqi0408.md` |
| [OnePlus 5 (cheeseburger)](https://unixnu.com/devices/cheeseburger) | DinnerABC/UniXNU-cheeseburger | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/cheeseburger.md` |
| [UniXNU](https://unixnu.com/devices/cheeseburger-lss717) | lss717/UniXNU-cheeseburger | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/cheeseburger-lss717.md` |
| [UniXNU](https://unixnu.com/devices/cheeseburger-maozedongae) | maozedongae/UniXNU-cheeseburger | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/cheeseburger-maozedongae.md` |
| [Xiaomi MIX 2 (chiron)](https://unixnu.com/devices/chiron) | Xiaomi MIX 2 (chiron) is a SDM835 device. The port below is an indepen | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/chiron.md` |
| [UniXNU](https://unixnu.com/devices/chiron-sbccc1888) |  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/chiron-sbccc1888.md` |
| [Xiaomi Mi Pad 4 LTE (clover)](https://unixnu.com/devices/clover) | A community-maintained port for SDM660. Current results are based on t | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/clover.md` |
| [Samsung Galaxy Note10+ 5G (SM-N9760)](https://unixnu.com/devices/d2xq) | awacomplex/UniXNU-d2xq | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/d2xq.md` |
| [Xiaomi 15 (dada)](https://unixnu.com/devices/dada) | 7Night-kqx/UniXNU-dada | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/dada.md` |
| [Redmi K80 Pro](https://unixnu.com/devices/dada2) | Nanawwa/UniXNU-dada2 | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/dada2.md` |
| [Redmi K80 Ultra (dali)](https://unixnu.com/devices/dali) | Redmi K80 Ultra (dali) is a MT6991 device. The port below is an indepe | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/dali.md` |
| [Redmi 9A (dandelion)](https://unixnu.com/devices/dandelion) | licg89/UniXNU-dandelion | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/dandelion.md` |
| [Xiaomi Mi 8 (dipper)](https://unixnu.com/devices/dipper) | Xiaomi Mi 8 (dipper) is a SDM845 device. The port below is an independ | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/dipper.md` |
| [Xiaomi Redmi Pad Pro (dizi); ruan unverified](https://unixnu.com/devices/dizi) | vildangil/UniXNU-Dizi-Ruan | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/dizi.md` |
| [DroidVM guest (crosvm on Gunyah)](https://unixnu.com/devices/droidvm) | The DroidVM target runs UniXNU as a guest under crosvm on the Gunyah h | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/droidvm.md` |
| [UniXNU](https://unixnu.com/devices/droidvm-lateautumn233) | lateautumn233/UniXNU-droidvm | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/droidvm-lateautumn233.md` |
| [UniXNU](https://unixnu.com/devices/droidvm-neko17awa) | Neko17awa/UniXNU-droidvm | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/droidvm-neko17awa.md` |
| [Rongyue E5 (e5)](https://unixnu.com/devices/e5) | Rongyue E5 is a 5G senior bar phone (feature-phone form factor) with a | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/e5.md` |
| [Lenovo Legion Y700 Gen 4 (elden)](https://unixnu.com/devices/elden) | jerry-2009/UNIXNU_elden | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/elden.md` |
| [Xiaomi Pad 5 Pro Wi-Fi (elish)](https://unixnu.com/devices/elish) | A community port for SM8250-AC, maintained by hpadmx. | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/elish.md` |
| [OnePlus 6 (enchilada)](https://unixnu.com/devices/enchilada) | OnePlus 6 (enchilada) is a SDM845 device. The port below is an indepen | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/enchilada.md` |
| [UniXNU](https://unixnu.com/devices/enchilada-keyfan) | keyfan/UniXNU-enchilada-bringup | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/enchilada-keyfan.md` |
| [UniXNU](https://unixnu.com/devices/enchilada-wangshaofan82-png) | wangshaofan82-png/UniXNU-enchilada-port | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/enchilada-wangshaofan82-png.md` |
| [Xiaomi Pad 5 Pro 5G (enuma)](https://unixnu.com/devices/enuma) | A community-maintained port for SM8250-AC. Current results are based o | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/enuma.md` |
| [UniXNU](https://unixnu.com/devices/enuma-alghiffaryfa19) | alghiffaryfa19/UniXNU-enuma-5g | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/enuma-alghiffaryfa19.md` |
| [UniXNU](https://unixnu.com/devices/enuma-tlrenhb) | Tlrenhb/UniXNU-enuma | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/enuma-tlrenhb.md` |
| [OnePlus Pad 2 Pro (erhai)](https://unixnu.com/devices/erhai) | erhai is the OnePlus Pad 2 Pro (OPD2413) with the SM8750 SoC. The port | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/erhai.md` |
| [Rockchip RK3588 EVB10 V10](https://unixnu.com/devices/evb10) | Rockchip RK3588 EVB10 V10 runs the iPadOS 17.7.11 userland on a source | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/evb10.md` |
| [OnePlus 15T (fairlady)](https://unixnu.com/devices/fairlady) | OnePlus 15T (fairlady) is a SM8850 device. The port below is an indepe | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/fairlady.md` |
| [OnePlus 6T (fajita)](https://unixnu.com/devices/fajita) | fajita is the OnePlus 6T with the SDM845 SoC. The port below is an ind | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/fajita.md` |
| [UniXNU](https://unixnu.com/devices/flashlm) | drx1x2/UniXNU-flashlm | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/flashlm.md` |
| [Xiaomi 13 (fuxi)](https://unixnu.com/devices/fuxi) | matejkoo217/UniXNU-fuxi | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/fuxi.md` |
| [UniXNU](https://unixnu.com/devices/fuxi-0721gpt) |  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/fuxi-0721gpt.md` |
| [UniXNU](https://unixnu.com/devices/fuxi-hanzi123-bilp) | hanzi123-bilp/unixnu-fuxi | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/fuxi-hanzi123-bilp.md` |
| [UniXNU](https://unixnu.com/devices/fuxi-kerfand) |  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/fuxi-kerfand.md` |
| [Xiaomi 13 (kkkpc)](https://unixnu.com/devices/fuxi-kkkpc) | Xiaomi 13 (fuxi, SM8550). Clean Format 2 port targeting iPadOS 17.7.11 | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/fuxi-kkkpc.md` |
| [UniXNU](https://unixnu.com/devices/fuxi-ljhhkx529) | ljhhkx529/unixnu-fuxi | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/fuxi-ljhhkx529.md` |
| [UniXNU](https://unixnu.com/devices/fuxi-minecraftvm) | MinecraftVM/UniXNU-fuxi | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/fuxi-minecraftvm.md` |
| [Xiaomi 13 (mouse233)](https://unixnu.com/devices/fuxi-mouse233) | mouse233/unixnu-fuxi | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/fuxi-mouse233.md` |
| [Xiaomi 13 (OddlyLabs)](https://unixnu.com/devices/fuxi-oddlylabs) | OddlyLabs/unixnu-fuxi | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/fuxi-oddlylabs.md` |
| [UniXNU](https://unixnu.com/devices/fuxi-sohytrs) |  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/fuxi-sohytrs.md` |
| [Xiaomi 13 (Star-mailaz)](https://unixnu.com/devices/fuxi-star-mailaz) | Star-mailaz/fuxi-ios16-device | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/fuxi-star-mailaz.md` |
| [UniXNU](https://unixnu.com/devices/fuxi-xyvern08371) | Xyvern08371/UniXNU-sheng | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/fuxi-xyvern08371.md` |
| [UniXNU](https://unixnu.com/devices/fuxi-yigezhong011-ops) | yigezhong011-ops/unixnu-fuxi | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/fuxi-yigezhong011-ops.md` |
| [Motorola Moto G 5G (gauguin)](https://unixnu.com/devices/gauguin) | Motorola Moto G 5G (gauguin) is a SM7125 device. The port below is an  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/gauguin.md` |
| [OnePlus Ace 5 (giulia)](https://unixnu.com/devices/giulia) | A community-maintained port for SM8650. Current results are based on t | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/giulia.md` |
| [Samsung Galaxy Tab A7 10.4 (gta4l)](https://unixnu.com/devices/gta4l) | gta4l is the Samsung Galaxy Tab A7 10.4 (2020), model SM-T500 or SM-T5 | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/gta4l.md` |
| [Samsung Galaxy Tab A7 10.4 (2020) (gta4lunix)](https://unixnu.com/devices/gta4l-gta4lunix) | gta4lunix/UniXNU-gta4l | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/gta4l-gta4lunix.md` |
| [UniXNU](https://unixnu.com/devices/gta4l-ilovemykedi) | ilovemykedi/UniXNU-gta4l | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/gta4l-ilovemykedi.md` |
| [Samsung Galaxy Tab S9 Ultra Wi-Fi (gts9uwifi)](https://unixnu.com/devices/gts9uwifi) | Samsung Galaxy Tab S9 Ultra Wi-Fi (gts9uwifi) is a SM-X910 device. The | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/gts9uwifi.md` |
| [OnePlus 7 Pro (guacamole)](https://unixnu.com/devices/guacamole) | guacamole is the OnePlus 7 Pro (GM1910) with the SM8150 SoC. The port  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/guacamole.md` |
| [Motorola Moto G9 Play (guamp)](https://unixnu.com/devices/guamp) | Motorola Moto G9 Play (guamp) is a SM6115 device. The port below is an | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/guamp.md` |
| [Redmi K40 Pro (haydn)](https://unixnu.com/devices/haydn) | haydn is the Redmi K40 Pro with the SM8350 SoC. The port below is an i | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/haydn.md` |
| [Xiaomi Redmi K40 Pro / K40 Pro+ / Mi 11i (haydn), SM8350 (iamOJZ)](https://unixnu.com/devices/haydn-iamojz) | Complete and validate porting.toml in the device repository to publish | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/haydn-iamojz.md` |
| [UniXNU](https://unixnu.com/devices/haydn-xiaomi-haydn-dev) | xiaomi-haydn-dev/UniXNU-haydn4 | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/haydn-xiaomi-haydn-dev.md` |
| [Samsung Galaxy S7 Edge (hero2lte)](https://unixnu.com/devices/hero2lte) | DokuroMitsukai/UniXNU-hero2lte | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/hero2lte.md` |
| [Xiaomi 14 (houji)](https://unixnu.com/devices/houji) | A community device port for SM8650. | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/houji.md` |
| [UniXNU](https://unixnu.com/devices/houji-kizashi3) | Kizashi3/UniXNU-houji | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/houji-kizashi3.md` |
| [UniXNU](https://unixnu.com/devices/houji-sakayorilroha) | SAKAYORILROHA/unixnu-houji | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/houji-sakayorilroha.md` |
| [OnePlus Ace 5 Pro (hummer)](https://unixnu.com/devices/hummer) | A community-maintained port for SM8750. Current results are based on t | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/hummer.md` |
| [OnePlus 8 Pro (instantnoodlep)](https://unixnu.com/devices/instantnoodlep) | zhangp996/UniXNU-instantnoodlep | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/instantnoodlep.md` |
| [OnePlus 8 Pro IN2020, 8 GiB, 1080x2376, UFS root (zhangp996)](https://unixnu.com/devices/instantnoodlep-zhangp996) | zhangp996/UniXNU-instantnoodlep-own | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/instantnoodlep-zhangp996.md` |
| [Xiaomi 13 Ultra (ishtar)](https://unixnu.com/devices/ishtar) | peter8889/UniXNU-ishtar | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/ishtar.md` |
| [UniXNU](https://unixnu.com/devices/ishtar-markakash) | markakash/UniXNU-ishtar-old | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/ishtar-markakash.md` |
| [UniXNU](https://unixnu.com/devices/ishtar-peter8889) | peter8889/UniXNU-ishtar-1 | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/ishtar-peter8889.md` |
| [Lenovo Xiaoxin Pad Pro 2021 (j716f)](https://unixnu.com/devices/j716f) | Denis0x00/UniXNU-j716f | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/j716f.md` |
| [Lenovo Xiaoxin Pad Pro 2021 TB-J716F UniXNU bring-up (EmptyGhost)](https://unixnu.com/devices/j716f-emptyghost) | EmptyGhost/UniXNU-j716f | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/j716f-emptyghost.md` |
| [OnePlus 8T (kebab)](https://unixnu.com/devices/kebab) | A community-maintained port for SM8250. Current results are based on t | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/kebab.md` |
| [OnePlus 8T (stevedang67889)](https://unixnu.com/devices/kebab-stevedang67889) | stevedang67889/UniXNU-kebab | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/kebab-stevedang67889.md` |
| [Google Pixel 9 Pro XL (komodo)](https://unixnu.com/devices/komodo) | A community-maintained port for Tensor G4. Current results are based o | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/komodo.md` |
| [UniXNU](https://unixnu.com/devices/lafa) | ky554640/UniXNU-lafa | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/lafa.md` |
| [UniXNU](https://unixnu.com/devices/lavender) | Chromitsune/UniXNU-Lavender | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/lavender.md` |
| [OnePlus 9R (lemonades)](https://unixnu.com/devices/lemonades) | A community port for SM8250-AC, maintained by soooink. | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/lemonades.md` |
| [Xiaomi Pad 6 Pro (liuqin)](https://unixnu.com/devices/liuqin) | Xiaomi Pad 6 Pro (liuqin) is a SM8475 device. The port below is an ind | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/liuqin.md` |
| [Redmi K30 Pro Zoom Edition (lmipro)](https://unixnu.com/devices/lmipro) | yang232138/UniXNU-lmipro-v2 | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/lmipro.md` |
| [UniXNU](https://unixnu.com/devices/lmipro-yang232138) | yang232138/UniXNU-lmipro | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/lmipro-yang232138.md` |
| [Microsoft Lumia 950](https://unixnu.com/devices/lumia950) | Microsoft Lumia 950 is a MSM8992 device. The port below is an independ | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/lumia950.md` |
| [UniXNU](https://unixnu.com/devices/lumia950-shrimpapplepro) | shrimpapplepro/UniXNU-lumia950xl | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/lumia950-shrimpapplepro.md` |
| [UniXNU](https://unixnu.com/devices/lumia950-twisstedtoast) | TwisstedToast/UniXNU-lumia950 | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/lumia950-twisstedtoast.md` |
| [Xiaomi Civi 5 Pro (luming)](https://unixnu.com/devices/luming) | A community-maintained port for SM8735. Current results are based on t | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/luming.md` |
| [Xiaomi Civi 5 Pro (SM8735; format-2 bring-up, iPadOS 17.7.11 profile) (infinityEX-RSXQ)](https://unixnu.com/devices/luming-infinityex-rsxq) | infinityEX-RSXQ/UniXNU-luming-f2-ci | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/luming-infinityex-rsxq.md` |
| [Meizu 20 Classic (m2381)](https://unixnu.com/devices/m2381) | A community port for SM8550, maintained by RiverKawa271828. | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/m2381.md` |
| [Meizu 20 Classic (RiverKawa271828)](https://unixnu.com/devices/m2381-riverkawa271828) | RiverKawa271828/UniXNU-m2381 | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/m2381-riverkawa271828.md` |
| [POCO X7 / Redmi Note 14 Pro 5G (malachite)](https://unixnu.com/devices/malachite) | malachite is the Xiaomi POCO X7 and Redmi Note 14 Pro 5G with the Medi | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/malachite.md` |
| [Redmi Note 12 Turbo / POCO F5 (marble)](https://unixnu.com/devices/marble) | sing0626/UniXNU-marble | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/marble.md` |
| [Redmi Note 12 Turbo / POCO F5 (marble), Qualcomm SM7475 (Snapdragon 7+ Gen 2) (MiLacy)](https://unixnu.com/devices/marble-milacy) | MiLacy/UniXNU-marble | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/marble-milacy.md` |
| [Xiaomi Redmi Note 9 (merlinx)](https://unixnu.com/devices/merlinx) | Dracen-W/UniXNU-merlinx | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/merlinx.md` |
| [UniXNU](https://unixnu.com/devices/mh2lm) | shenli99/UniXNU-mh2lm | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/mh2lm.md` |
| [Xiaomi Redmi K40S (munch, 22021211RC)](https://unixnu.com/devices/munch) | WuBarlynn/unixnu-munch | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/munch.md` |
| [Xiaomi Redmi K40S (munch, 22021211RC) (ErodeNine)](https://unixnu.com/devices/munch-erodenine) | ErodeNine/unixnu-munch | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/munch-erodenine.md` |
| [UniXNU](https://unixnu.com/devices/muyu) | yehua123-oos/UniXNU-muyu | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/muyu.md` |
| [Redmi K90 Pro Max / Poco F8 Ultra (myron)](https://unixnu.com/devices/myron) | myron is the Redmi K90 Pro Max and Poco F8 Ultra with the SM8850 SoC.  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/myron.md` |
| [UniXNU](https://unixnu.com/devices/myron-typeun) |  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/myron-typeun.md` |
| [Xiaomi Pad 5 (nabu)](https://unixnu.com/devices/nabu) | A community-maintained port for SM8150. Current results are based on t | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/nabu.md` |
| [UniXNU](https://unixnu.com/devices/nabu-3214791900-del) | 3214791900-del/unixnu-nabu-build | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/nabu-3214791900-del.md` |
| [UniXNU](https://unixnu.com/devices/nabu-lee-kenneth) | lee-kenneth/unixnu-nabu | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/nabu-lee-kenneth.md` |
| [UniXNU](https://unixnu.com/devices/nabu-zzc775) |  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/nabu-zzc775.md` |
| [Xiaomi Pad 5 (zzweiqing)](https://unixnu.com/devices/nabu-zzweiqing) | zzweiqing/UniXNU-nabu | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/nabu-zzweiqing.md` |
| [Motorola Moto Z2 Force (nash)](https://unixnu.com/devices/nash) | A community-maintained port for MSM8998. Current results are based on  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/nash.md` |
| [OnePlus 10 Pro 5G (negroni)](https://unixnu.com/devices/negroni) | Community ports for OnePlus 10 Pro 5G (negroni, SM8450). The pawlicker | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/negroni.md` |
| [MOTO Edge S (XT2125-4) / SM8250-AC UniXNU bring-up](https://unixnu.com/devices/nio) | 18178786617/UniXNU-nio | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/nio.md` |
| [Xiaomi 13 Pro (nuwa)](https://unixnu.com/devices/nuwa) | A community-maintained port for SM8550. Current results are based on t | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/nuwa.md` |
| [UniXNU](https://unixnu.com/devices/nuwa-alex-enix) |  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/nuwa-alex-enix.md` |
| [UniXNU](https://unixnu.com/devices/nuwa-pubglite55) | pubglite55/UniXNU-nuwa | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/nuwa-pubglite55.md` |
| [UniXNU](https://unixnu.com/devices/nuwa-wuuuweiii) | WuuuWeiii/UniXNU-nuwa | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/nuwa-wuuuweiii.md` |
| [ZTE Nubia Z60 Ultra (nx721j)](https://unixnu.com/devices/nx721j) | A community-maintained port for Pineapple. Current results are based o | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/nx721j.md` |
| [Nubia RedMagic 8 Pro / 8 Pro+ (nx729j)](https://unixnu.com/devices/nx729j) | nx729j is the Nubia RedMagic 8 Pro and 8 Pro+ with the SM8550 SoC. The | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/nx729j.md` |
| [nubia RedMagic 9 Pro / 9 Pro+ / 9S Pro / 9S Pro+ (NX769J)](https://unixnu.com/devices/nx769j) | Asultop/UniXNU-NX769J | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/nx769j.md` |
| [Xiaomi Mi MIX 4 (odin, Snapdragon 888+ / SM8350)](https://unixnu.com/devices/odin) | Xiaomi Mi MIX 4 (Snapdragon 888+). Inputs and shared-support gaps live | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/odin.md` |
| [AYN Odin 3 (Dragonwing Q8, SM8750), 16 GiB](https://unixnu.com/devices/odin3) | darkplace/UniXNU-Odin3 | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/odin3.md` |
| [OnePlus 13T (oneplus13t)](https://unixnu.com/devices/oneplus13t) | IssacL04/UniXNU-Pagani_SM8750 | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/oneplus13t.md` |
| [Orange Pi 5 (Rockchip RK3588S)](https://unixnu.com/devices/orangepi5) | Ken-u/UniXNU-orangepi5 | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/orangepi5.md` |
| [Xiaomi 17 Pro (pandora)](https://unixnu.com/devices/pandora) | A community-maintained port for SM8850. Current results are based on t | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/pandora.md` |
| [UniXNU](https://unixnu.com/devices/pd2049) | Kaurisss/UniXNU-PD2049 | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/pd2049.md` |
| [Sony Xperia 1 II (pdx203)](https://unixnu.com/devices/pdx203) | Sony Xperia 1 II (pdx203) is a SM8250 device. The port below is an ind | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/pdx203.md` |
| [Redmi Turbo 3 / Poco F6 (peridot)](https://unixnu.com/devices/peridot) | Redmi Turbo 3 / Poco F6 (peridot) is a SM8635 device. The port below i | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/peridot.md` |
| [Xiaomi Poco F6 / Redmi Turbo 3 (hoshikv)](https://unixnu.com/devices/peridot-hoshikv) | hoshikv/UniXNU-peridot | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/peridot-hoshikv.md` |
| [Poco F6 / Redmi Turbo 3 (wzy114514sb)](https://unixnu.com/devices/peridot-wzy114514sb) | wzy114514sb/UniXNU-peridot | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/peridot-wzy114514sb.md` |
| [OPPO Find X7 Ultra (PHY120)](https://unixnu.com/devices/phy120) | PHY120 is the OPPO Find X7 Ultra with the SM8650 SoC. The port below i | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/phy120.md` |
| [Xiaomi Pad 8 Pro (piano)](https://unixnu.com/devices/piano) | piano is the Xiaomi Pad 8 Pro with the SM8750 SoC. The port below is a | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/piano.md` |
| [Redmi K30 5G (picasso)](https://unixnu.com/devices/picasso) | A community-maintained port for SM7250. Current results are based on t | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/picasso.md` |
| [UniXNU](https://unixnu.com/devices/picasso-huydre) | huydre/UniXNU-picasso | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/picasso-huydre.md` |
| [UniXNU](https://unixnu.com/devices/picasso-minhtritt1996) | minhtritt1996/UniXNU-picasso | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/picasso-minhtritt1996.md` |
| [UniXNU](https://unixnu.com/devices/picasso-silenzio111) | silenzio111/UniXNU-picasso | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/picasso-silenzio111.md` |
| [Redmi K30 5G targeting iPhone X iOS 16; Darwin 22 ABI and firmware pending (SuzukiR1n)](https://unixnu.com/devices/picasso-suzukir1n) | SuzukiR1n/UniXNU-Picasso | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/picasso-suzukir1n.md` |
| [UniXNU](https://unixnu.com/devices/picasso-tselongson) | tselongson/UniXNU-picasso | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/picasso-tselongson.md` |
| [Xiaomi Pad 6 (pipa)](https://unixnu.com/devices/pipa) | A community-maintained port for SM8250. Current results are based on t | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/pipa.md` |
| [UniXNU](https://unixnu.com/devices/pipa-fft-infra) | FFT-infra/UniXNU-alioth-ARCHIVE | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/pipa-fft-infra.md` |
| [UniXNU](https://unixnu.com/devices/pipa-xvanturing) | xVanTuring/UniXNU-pipa | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/pipa-xvanturing.md` |
| [Xiaomi Mi MIX 2S (polaris)](https://unixnu.com/devices/polaris) | polaris is the Xiaomi Mi MIX 2S with the SDM845 SoC, Snapdragon 845 an | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/polaris.md` |
| [UniXNU](https://unixnu.com/devices/polaris-puszekreksio) | PuszekReksio/UniXNU-judyln | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/polaris-puszekreksio.md` |
| [UniXNU](https://unixnu.com/devices/polaris-sprmd) | SPRMD/UniXNU-polaris | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/polaris-sprmd.md` |
| [Xiaomi 17 (pudding, qcom,canoe, SM8850)](https://unixnu.com/devices/pudding) | daisukiKaffuChino/UniXNU-pudding | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/pudding.md` |
| [Galaxy Z Fold3 (q2q)](https://unixnu.com/devices/q2q) | q2q is the Samsung Galaxy Z Fold3 with the SM8350 SoC. The port below  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/q2q.md` |
| [QEMU virt](https://unixnu.com/devices/qemu) | The QEMU target runs UniXNU on the AArch64 `virt` machine. It substitu | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/qemu.md` |
| [OPPO R11 (r11)](https://unixnu.com/devices/r11) | OPPO R11 (r11) is a SDM660 device. The port below is an independent co | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/r11.md` |
| [Redmi K20 Pro / Mi 9T Pro (raphael)](https://unixnu.com/devices/raphael) | GitHub public access cannot currently retrieve this repository. Curren | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/raphael.md` |
| [UniXNU](https://unixnu.com/devices/raphael-johnleeeeeee678) | JohnLeeeeeee678/UniXNU-raphael | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/raphael-johnleeeeeee678.md` |
| [Realme 5 Pro](https://unixnu.com/devices/rmx1971) | AppleCampus/UniXNU-rmx1971 | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/rmx1971.md` |
| [realme GT5 240W (RMX3823), kalama, 24 GiB, 1240x2772 AMOLED](https://unixnu.com/devices/rmx3823) | Janit8r/UniXNU-rmx3823-new | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/rmx3823.md` |
| [Xiaomi MIX Flip (ruyi)](https://unixnu.com/devices/ruyi) | A community port for SM8650, maintained by ArnoDorian123. | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/ruyi.md` |
| [UniXNU](https://unixnu.com/devices/ruyi-arnodorian123) | ArnoDorian123/UniXNU-ruyi-min | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/ruyi-arnodorian123.md` |
| [UniXNU](https://unixnu.com/devices/ruyi-ehunshuaige) | ehunshuaige/UniXNU-ruyi | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/ruyi-ehunshuaige.md` |
| [Xiaomi Mi 6 (sagit)](https://unixnu.com/devices/sagit) | GitHub public access cannot currently retrieve this repository. Curren | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/sagit.md` |
| [Xiaomi 14 Pro 23116PN5BC](https://unixnu.com/devices/shennong) | YX2748198202-lab/UniXNU-shennong | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/shennong.md` |
| [Xiaomi Mi 8 SE (sirius)](https://unixnu.com/devices/sirius) | Xiaomi Mi 8 SE running the UniXNU source kernel through its own U-Boot | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/sirius.md` |
| [Xiaomi Mi 8 SE (dddqmmx)](https://unixnu.com/devices/sirius-dddqmmx) | dddqmmx/UniXNU-sirius | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/sirius-dddqmmx.md` |
| [Xiaomi Mi 8 SE (HuajiFruit)](https://unixnu.com/devices/sirius-huajifruit) | HuajiFruit/UniXNU-sirius | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/sirius-huajifruit.md` |
| [Xiaomi Mi 8 SE (Yooglery)](https://unixnu.com/devices/sirius-yooglery) | Yooglery/UniXNU-sirius | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/sirius-yooglery.md` |
| [Samsung Galaxy Tab S7 FE Wi-Fi (SM-T733)](https://unixnu.com/devices/sm-t733) | RigoLigoRLC/unixnu-sm-t733 | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/sm-t733.md` |
| [UniXNU](https://unixnu.com/devices/songyuan) | WUKAWL/songyuan-unixnu | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/songyuan.md` |
| [UniXNU](https://unixnu.com/devices/songyuan-aogg2023) | aogg2023/songyuan-device | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/songyuan-aogg2023.md` |
| [UniXNU](https://unixnu.com/devices/songyuan-wukawl) | WUKAWL/songyuan-device | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/songyuan-wukawl.md` |
| [Unisoc UMS512 / T610YP](https://unixnu.com/devices/t610yp) | Unisoc UMS512 / T610YP is a UMS512 device. The port below is an indepe | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/t610yp.md` |
| [Lenovo Xiaoxin Pad 2022 (tb128fu)](https://unixnu.com/devices/tb128fu) | tb128fu is the Lenovo Xiaoxin Pad 2022 (TB128FU) with the Snapdragon 6 | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/tb128fu.md` |
| [UniXNU](https://unixnu.com/devices/tb128fu-riceneeder) | Riceneeder/UniXNU-tb128fu | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/tb128fu-riceneeder.md` |
| [Lenovo Xiaoxin Pad 12.1 (2025), Lenovo TB365FC (board cava_prc_consumer_wifi)](https://unixnu.com/devices/tb365fc) | LittleStar-OuO/UniXNU-tb365fc | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/tb365fc.md` |
| [Xiaomi Mi 10S (thyme)](https://unixnu.com/devices/thyme) | A community-maintained port for SM8250-AC. Current results are based o | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/thyme.md` |
| [UniXNU](https://unixnu.com/devices/thyme-coryyi) |  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/thyme-coryyi.md` |
| [UniXNU](https://unixnu.com/devices/tundra) | Meltemi-9264/unixnu-tundra | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/tundra.md` |
| [OnePlus Ace 2 / 11R (udon)](https://unixnu.com/devices/udon) | A community device port for SM8475. | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/udon.md` |
| [Xiaomi Pad 7 / POCO Pad X1 (uke)](https://unixnu.com/devices/uke) | Xiaomi Pad 7 (SM7675/cliffs) port: format-2 repository migration verif | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/uke.md` |
| [UniXNU](https://unixnu.com/devices/uke-iosnjbrepo) | iOSNJBrepo/UniXNU-uke | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/uke-iosnjbrepo.md` |
| [Xiaomi Pad 7 (TongHuaQWQ)](https://unixnu.com/devices/uke-tonghuaqwq) | TongHuaQWQ/UniXNU-uke | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/uke-tonghuaqwq.md` |
| [UniXNU](https://unixnu.com/devices/uke-wuhaoran956-cyber) | wuhaoran956-cyber/UniXNU-uke | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/uke-wuhaoran956-cyber.md` |
| [Xiaomi Mi 10 (umi)](https://unixnu.com/devices/umi) | umi is the Xiaomi Mi 10 with the SM8250 SoC. This is an independent co | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/umi.md` |
| [UniXNU](https://unixnu.com/devices/umi-agxmx666) |  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/umi-agxmx666.md` |
| [UniXNU](https://unixnu.com/devices/umi-mouya-q) |  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/umi-mouya-q.md` |
| [UniXNU](https://unixnu.com/devices/umi-neowiseq) |  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/umi-neowiseq.md` |
| [Unisoc devices](https://unixnu.com/devices/unisoc) | The UniXNU-Unisoc fork targets Unisoc devices. It is an independent co | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/unisoc.md` |
| [unixnu-build](https://unixnu.com/devices/unixnu-build) | This repository is a UniXNU build tree. It is an independent repositor | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/unixnu-build.md` |
| [Xiaomi Mi 11 M2011K2C: single-CPU platform bring-up](https://unixnu.com/devices/venus) | Sulee7z/UniXNU-venus | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/venus.md` |
| [Redmi K70 (vermeer)](https://unixnu.com/devices/vermeer) | A community-maintained port for SM8550. Current results are based on t | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/vermeer.md` |
| [Redmi K70 (ahzcpp)](https://unixnu.com/devices/vermeer-ahzcpp) | ahzcpp/UniXNU-vermeer | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/vermeer-ahzcpp.md` |
| [UniXNU](https://unixnu.com/devices/vermeer-xyyyds0106) | xyyyds0106/UniXNU-vermeer | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/vermeer-xyyyds0106.md` |
| [UniXNU](https://unixnu.com/devices/vermeer-yyx2025) | yyx2025/UniXNU-vermeer | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/vermeer-yyx2025.md` |
| [Xiaomi 11T Pro (vili, 2107113SG), SM8350 / Snapdragon 888](https://unixnu.com/devices/vili) | Matthew7577/UniXNU-vili | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/vili.md` |
| [Xiaomi Mi 6X (2018)](https://unixnu.com/devices/wayne) | gs240333/UniXNU-wayne | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/wayne.md` |
| [OPPO Find X9 (x9)](https://unixnu.com/devices/x9) | OPPO Find X9 (x9) is a MT6993 device. The port below is an independent | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/x9.md` |
| [Redmi Pad format-2 qualification candidate; boot Mu and cust UniXNU must remain separate](https://unixnu.com/devices/yunluo) | woaphone/UniXNU-yunluo | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/yunluo.md` |
| [Xiaomi MIX Fold 2 (zizhan, SM8475): UniXNU bring-up derived from Pong](https://unixnu.com/devices/zizhan) | qiumochen/UniXNU-zizhan | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/zizhan.md` |
| [Redmi K80 (zorn)](https://unixnu.com/devices/zorn) | Redmi K80: owner-confirmed desktop/basic touch, eight-core checks, ret | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/devices/zorn.md` |

### drivers（43 页）

| 页面 | 摘要 | 更新于 | 本地存档 |
|---|---|---|---|
| [AdrenoFirmware](https://unixnu.com/drivers/adreno-firmware) | Start with the adaptation procedure for board inputs, source changes,  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/adreno-firmware.md` |
| [AdrenoMetal](https://unixnu.com/drivers/adreno-metal) | AdrenoMetal publishes a Metal device through `MTLAddDevice`. It transl | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/adreno-metal.md` |
| [AdrenoPM4](https://unixnu.com/drivers/adreno-pm4) | Start with the adaptation procedure for board inputs, source changes,  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/adreno-pm4.md` |
| [Adreno740](https://unixnu.com/drivers/adreno740) | Adreno740 implements the A740 kernel GPU interface on SM8550. It owns  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/adreno740.md` |
| [AirNir](https://unixnu.com/drivers/air-nir) | Start with the adaptation procedure for board inputs, source changes,  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/air-nir.md` |
| [AppleKeyStoreState](https://unixnu.com/drivers/apple-key-store-state) | Start with the adaptation procedure for board inputs, source changes,  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/apple-key-store-state.md` |
| [ArmCpu](https://unixnu.com/drivers/arm-cpu) | Start with the adaptation procedure for board inputs, source changes,  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/arm-cpu.md` |
| [ArmDTPlatform](https://unixnu.com/drivers/arm-dt-platform) | Start with the adaptation procedure for board inputs, source changes,  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/arm-dt-platform.md` |
| [ArmSmmu4K](https://unixnu.com/drivers/arm-smmu4k) | Start with the adaptation procedure for board inputs, source changes,  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/arm-smmu4k.md` |
| [ArmVirtPlatform](https://unixnu.com/drivers/arm-virt-platform) | ARM virtual platform for QEMU. Publishes the QEMU virt platform device | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/arm-virt-platform.md` |
| [Ath12kWifi](https://unixnu.com/drivers/ath12k-wifi) | Ath12kWifi runs Linux ath12k, mac80211 and cfg80211 on XNU. It uses MH | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/ath12k-wifi.md` |
| [NativeAdreno-fuxi](https://unixnu.com/drivers/community-native-adreno-fuxi) | Adreno driver fork for the Xiaomi 13 (fuxi, SM8550). Tracks the offici | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/community-native-adreno-fuxi.md` |
| [NativeAdreno-myron](https://unixnu.com/drivers/community-native-adreno-myron) | Adreno driver fork for the Redmi K90 Pro Max / Poco F8 Ultra (myron, S | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/community-native-adreno-myron.md` |
| [NativeDwc3](https://unixnu.com/drivers/community-native-dwc3) | Native DWC3 USB3 DRD controller driver for the Xiaomi Pad 5 (nabu, SM8 | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/community-native-dwc3.md` |
| [NativeEmmc](https://unixnu.com/drivers/community-native-emmc) | Native eMMC storage driver for the Redmi Note 9 (merlinx). Publishes t | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/community-native-emmc.md` |
| [NativeMsdc (community)](https://unixnu.com/drivers/community-native-msdc) | MediaTek MT8167 MSDC eMMC block driver for the Benesse TAB-A04-BR3. Pu | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/community-native-msdc.md` |
| [NativeUfs-alioth](https://unixnu.com/drivers/community-native-ufs-alioth) | UFS driver fork for alioth, the Redmi K40 / Poco F3 family. Tracks the | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/community-native-ufs-alioth.md` |
| [NativeUfs-myron](https://unixnu.com/drivers/community-native-ufs-myron) | UFS driver fork for myron. Tracks the official NativeUfs controller an | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/community-native-ufs-myron.md` |
| [unixnu-nativefocaltechtouch](https://unixnu.com/drivers/community-nativefocaltechtouch) | FT8203 touch controller support over Qualcomm GENI SPI for the Samsung | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/community-nativefocaltechtouch.md` |
| [unixnu-nativemobiledisplay](https://unixnu.com/drivers/community-unixnu-nativemobiledisplay) | CPU software display, framebuffer copying and presentation for the Sam | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/community-unixnu-nativemobiledisplay.md` |
| [unixnu-nativeramblock](https://unixnu.com/drivers/community-unixnu-nativeramblock) | Persistent Data storage and explicit reset handling for the Samsung Ga | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/community-unixnu-nativeramblock.md` |
| [unixnu-nativeufs](https://unixnu.com/drivers/community-unixnu-nativeufs) | SM7325 UFS, SMMU and root storage support for the Samsung Galaxy Tab S | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/community-unixnu-nativeufs.md` |
| [DarwinBoot](https://unixnu.com/drivers/darwin-boot) | Start with the adaptation procedure for board inputs, source changes,  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/darwin-boot.md` |
| [Device tree matching](https://unixnu.com/drivers/device-tree-matching) | A driver binds to a provider through an IOKit personality. The persona | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/device-tree-matching.md` |
| [GopFramebuffer](https://unixnu.com/drivers/gop-framebuffer) | Start with the adaptation procedure for board inputs, source changes,  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/gop-framebuffer.md` |
| [Kext bundles](https://unixnu.com/drivers/kexts) | The shipped DarwinBoot starts prelinked kernels. Its driver integratio | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/kexts.md` |
| [Develop a driver](https://unixnu.com/drivers/overview) | To adapt hardware, follow the driver checklist. It covers component dr | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/overview.md` |
| [QcomBaseband](https://unixnu.com/drivers/qcom-baseband) | Qualcomm baseband bridge and SC7180 IPA v4.2 data path by **HoshinoYum | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/qcom-baseband.md` |
| [QcomGeniSpi](https://unixnu.com/drivers/qcom-geni-spi) | Start with the adaptation procedure for board inputs, source changes,  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/qcom-geni-spi.md` |
| [RamBlock](https://unixnu.com/drivers/ram-block) | Start with the adaptation procedure for board inputs, source changes,  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/ram-block.md` |
| [Driver repositories](https://unixnu.com/drivers/repositories) | Drivers and libraries have independent repositories. The component cat | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/repositories.md` |
| [ShengHidInput](https://unixnu.com/drivers/sheng-hid-input) | Start with the adaptation procedure for board inputs, source changes,  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/sheng-hid-input.md` |
| [Novatek NT36532E touch driver](https://unixnu.com/drivers/sheng-novatek-touch) | Start with the adaptation procedure for board inputs, source changes,  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/sheng-novatek-touch.md` |
| [ShengPreflight](https://unixnu.com/drivers/sheng-preflight) | Start with the adaptation procedure for board inputs, source changes,  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/sheng-preflight.md` |
| [ShengUfs](https://unixnu.com/drivers/sheng-ufs) | Start with the adaptation procedure for board inputs, source changes,  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/sheng-ufs.md` |
| [Sm8550Platform](https://unixnu.com/drivers/sm8550-platform) | Start with the adaptation procedure for board inputs, source changes,  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/sm8550-platform.md` |
| [SoftwareAES](https://unixnu.com/drivers/software-aes) | Start with the adaptation procedure for board inputs, source changes,  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/software-aes.md` |
| [UEFI drivers](https://unixnu.com/drivers/uefi-drivers) | 1. Prepare the package DEC and its protocol declarations. Generate dis | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/uefi-drivers.md` |
| [VerifiedRoot](https://unixnu.com/drivers/verified-root) | Start with the adaptation procedure for board inputs, source changes,  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/verified-root.md` |
| [VirtioMmioBlock](https://unixnu.com/drivers/virtio-mmio-block) | Start with the adaptation procedure for board inputs, source changes,  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/virtio-mmio-block.md` |
| [VirtioMmioConsole](https://unixnu.com/drivers/virtio-mmio-console) | VirtIO 1.2 MMIO console transport using split queues. | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/virtio-mmio-console.md` |
| [XNU drivers](https://unixnu.com/drivers/xnu-drivers) | Follow driver discovery and adaptation first. This page implements a n | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/xnu-drivers.md` |
| [XnuPrelink](https://unixnu.com/drivers/xnu-prelink) | Start with the adaptation procedure for board inputs, source changes,  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/drivers/xnu-prelink.md` |

### contributing（2 页）

| 页面 | 摘要 | 更新于 | 本地存档 |
|---|---|---|---|
| [Documentation site](https://unixnu.com/contributing/documentation) | The documentation is a VitePress site in `docs/`. It is published to ` | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/contributing/documentation.md` |
| [Repository layout](https://unixnu.com/contributing/repository) | UniXNU assembles independent SoC, device, and component repositories.  | 2026-11-03 | `E:/k60-work/references/unixnu-site/en/contributing/repository.md` |

### _root（1 页）

| 页面 | 摘要 | 更新于 | 本地存档 |
|---|---|---|---|
| [UniXNU](https://unixnu.com/) |  |  | `E:/k60-work/references/unixnu-site/en/_root/index.md` |
