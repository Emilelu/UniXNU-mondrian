# 官网页结论：userdata / security / qcom-baseband

2026-11-21。范围是 Lead 指定的三页：concepts/userdata.md、concepts/security.md、drivers/qcom-baseband.md。目标不是再抄一遍页面，而是让每一页在 OFFICIAL-REQUIREMENTS.toml 里有一个可复核的状态：mapped 要有能跑的门禁，na 要写出为什么这一页不约束本板。

## 0 当前读数与结论

以 2026-11-21 的 E:/hackios/k60-gates 为准，check-official-docs.py 读出的实际计数是：

- documented pages 103, mapped 20, na 2, unmapped 81。

Lead 消息里的 20 / 1 / 82 是更早的读数；本轮以实际文件为准，不按旧数字改。

三页的结论：

| 页面 | 现在 | 建议 | 依据 |
| --- | --- | --- | --- |
| concepts/userdata.md | mapped，gate 只查 Data UUID | mapped，改挂 check-userdata-layout.py | 页面还钉 SHNGROOT 头、1 MiB 首窗、1 MiB 对齐、512 B 块、容量上限；新门禁把这些和 UUID 一起查 |
| concepts/security.md | unmapped | na | K60 的 iOS 27 stage-0 不选 trust cache/AMFI/AppSync 栈，board.toml:221-226 明确丢弃 trust-cache 路径，configs 三个开关均为 n |
| drivers/qcom-baseband.md | unmapped | na | board.toml 的 [components] 与 27 override 都没有 QcomBaseband；页面第 11 行自己写明没有蜂窝基带的设备可跳过此组件 |

按这三块改，计数变成：

- documented pages 103, mapped 20, na 4, unmapped 79。

mapped 不增加，是因为 userdata 本来就在 mapped 里；这一轮是把它的门禁从“只查 UUID”换成“布局 + UUID”。security 和 qcom-baseband 从债务变成有理由的 na，所以 unmapped 少两条。

本 lane 不写 E:/hackios/k60-gates。可应用的补丁在：

- docs/research/official/OFFICIAL-REQUIREMENTS.power.patch

补丁带三个 registry 块和 scripts/check-userdata-layout.py；应用方法和复核命令见 §4。

## 1 concepts/userdata.md

页面 sha256 = 827a59d2908f1321869e8ec0bd59460ab943f6cdd96680a67cbbaf1aab7b9583，当前 registry 第 48-54 行。

页面不只是“Data 卷 UUID 不能是种子”。它同时钉住：

- 第 9 行 magic 为 SHNGROOT；
- 第 17 行 block_size 为 512；
- 第 27 行头部 4096 字节、零填充到 1 MiB，第一个窗口从 0x100000 开始，每个窗口按 1 MiB 对齐；
- 第 38-44 行容量计算，步骤拒绝超过容量的镜像，报告记录容量和镜像大小；
- 第 62-70 行 Data 卷独立于 userdata 镜像，来自负载 Data ramdisk 种子，卷 UUID 不变。

旧的 gate check-defconfig-uuid.py 只覆盖最后一个问题（种子 UUID 会让内核等一个永远不会出现的卷，在 USB console 之前 self-panic，P-209）。它不查 SHNGROOT 布局，所以页面在 registry 里虽然写着 mapped，布局改动不会被任何门禁发现。

新增 scripts/check-userdata-layout.py：

- 直接 import scripts/build-userdata.py，钉 MIB = 1 << 20、FIRST_LBA = 0x413248、LAST_LBA = 0x75A40EA、USERDATA_BYTES = (LAST_LBA - FIRST_LBA + 1) * 4096；
- 钉 builder 源码里的 header[:8] = b'SHNGROOT'、header = bytearray(4096)、struct.pack_into('<IIQ', header, 8, 1, len(entries), cursor)、entry 格式 '<32sQQII32s40s' 和 24 + index * 128、block_size 512、flags 1、header[4064:] 的 sha256；
- 钉 cursor = MIB、((size + MIB - 1) // MIB) * MIB 的对齐、cursor > USERDATA_BYTES 的拒绝、报告里的 capacity_bytes/image_bytes；
- 再 import check-defconfig-uuid.py 并调用 run(repo)，所以 UUID 那条没有丢；
- --self-test 有 4 个用例（baseline、magic、first-window、capacity-formula）。

本机与共享树都跑过：

    python3 scripts/check-userdata-layout.py
    python3 scripts/check-userdata-layout.py --repo E:/hackios/k60-gates
    python3 scripts/check-userdata-layout.py --self-test

三条都是 rc 0；共享树输出 userdata-layout: OK (SHNGROOT v1, 4096-byte header, first window 1 MiB, 1 MiB alignment, 512-byte blocks, capacity ceiling and Data UUID all pinned)。

因此建议把 registry 的 gate 从 check-defconfig-uuid.py 换成 check-userdata-layout.py，assertion 改成同时覆盖布局和身份。补丁把新门禁放进 k60-gates/scripts/，否则 gate_exists 会红。

## 2 concepts/security.md

页面 sha256 = baaede96059a1bc035a5af57dc96b3f671813127da24de4bda191ef9088fac09，当前 registry 第 42-46 行，state = unmapped。

这一页描述的是 sheng 的 Apple 安全组件栈：trust cache 包与 --trust-cache、[payload] trust_cache_sha256、native-trust-cache-runtime、4 KiB 代码签名哈希缓存、/chosen/amfi-only-platform-code、AMFI early_security_init、AppSync Unified、VerifiedRoot 与 verified block 驱动。

K60 的 iOS 27 stage-0 没有这套栈：

- board.toml:221 写着 “B decision (2026-11-03): align with pong and drop the whole trust-cache path.”；board.toml:226 是 trust_cache_sha256 = []；payload 不带 --trust-cache sidecar。
- configs/mondrian_defconfig:33 是 CONFIG_XNU_NATIVE_TRUST_CACHE=n；:57 是 CONFIG_XNU_OWNER_ROOT_TRUST=n；:76 是 CONFIG_XNU_TRUST_CACHE_RUNTIME=n。
- patches/xnu-12377/series 共 110 行，只有 ptrauth-string-discriminator、armcpu-sleep-hook 和 22 个 Bluetooth 补丁；没有 native-trust-cache-runtime、native-4k-signature-hash-cache、AMFI 或 AppSync 的补丁名。
- 16 线的 amfi_get_out_of_my_way=1 是 miniamfi 替身，不是这一页要求的原始 Apple AMFI/SEP 路径；把替身存在当成页面已覆盖，会重复 P-288 的错误。

所以这一页对当前 profile 不构成约束，判 na，而不是找一个只断言“trust cache 为空”的脚本硬挂成 mapped。只断言缺失的门禁不是页面合规，它只能守 na 的前提。

na 的重审条件写进 why：任一 CONFIG_XNU_*TRUST_CACHE* 或 OWNER_ROOT_TRUST 变成 y，trust_cache_sha256 非空，或 xnu-12377 系列出现 trust/AMFI/AppSync 补丁名，就必须先重读这一页再决定 mapped。scripts/check-official-scope.py 就是把这四个条件做成可执行的守卫；它不替代 registry 的 gate，只在前提移动时变红。

## 3 drivers/qcom-baseband.md

页面 sha256 = 275230714b756152d8ef5489f254b88eb1217f1e4903bf790e5def24120b011d，当前 registry 第 250-254 行，state = unmapped。

这一页是 QcomBaseband 组件：QMUX/QRTR、QMI CTL、SAHARA、AppleBaseband IOKit 服务、IPA/GSI/QMAP，板级提供 modem 启动、固件、电源、DMA、GLINK/QRTR 和 rmtfs。页面第 11 行最后一句自己写明：“没有蜂窝基带的设备可跳过此组件。”

K60 的当前 profile 没有选这个组件：

- board.toml:13-14 的 [components] include 是 ArmDTPlatform、ArmCpu、XnuPrelink、PongUfs；board.toml:358-360 的 ios-27.0.1-24A446 override 是 ArmDTPlatform、ArmCpu、XnuPrelink。两处都没有 QcomBaseband。
- configs 里没有 BASEBAND/MODEM/CELLULAR 开关；patches/xnu-12377/series 没有 baseband 补丁。
- components.toml:564-581 定义了这个组件，但定义不等于选择；board.toml 没有把它加进任何 include。

因此这一页也不约束当前 profile，判 na。重审条件写进 why：一旦 [components] 或 27 override 选入 QcomBaseband/AppleBaseband，或 configs 出现基带/ modem 开关，或 12377 系列出现 baseband 补丁，就必须重读页面并把 QcomBaseband 的 AppleBaseband 服务、IPA v4.2 数据通路和板级 modem 资源接成实际门禁。scripts/check-official-scope.py 同样守这个前提。

## 4 精确的 registry 块

补丁会替换下面三块；这里给出完整文本，便于在 k60-gates 里人工复核。

~~~toml
[[page]]
path = "concepts/security.md"
title = "完整性与启动策略"
sha256 = "baaede96059a1bc035a5af57dc96b3f671813127da24de4bda191ef9088fac09"
state = "na"
why = "K60 的 iOS 27 stage-0 不选 sheng 的 trust cache/AMFI/AppSync 栈：board.toml:221-226 丢弃 trust-cache 路径且 trust_cache_sha256 = []，configs/mondrian_defconfig:33/57/76 三个开关均为 n，patches/xnu-12377/series 只有 ptrauth、ArmCpu sleep 和 22 个 Bluetooth 补丁；任一开关变 y、trust_cache_sha256 非空或 12377 系列出现 trust/AMFI/AppSync 补丁时重审。"

[[page]]
path = "concepts/userdata.md"
title = "userdata 布局"
sha256 = "827a59d2908f1321869e8ec0bd59460ab943f6cdd96680a67cbbaf1aab7b9583"
state = "mapped"
gate = "check-userdata-layout.py"
assertion = "SHNGROOT v1 layout, 1 MiB windows and the Data volume identity are all pinned"

[[page]]
path = "drivers/qcom-baseband.md"
title = "QcomBaseband"
sha256 = "275230714b756152d8ef5489f254b88eb1217f1e4903bf790e5def24120b011d"
state = "na"
why = "K60 当前 profile 没有选 QcomBaseband：board.toml:13-14 和 :358-360 的 components include 是 ArmDTPlatform/ArmCpu/XnuPrelink(/PongUfs)，没有 QcomBaseband/AppleBaseband；configs 没有 BASEBAND/MODEM/CELLULAR 开关，patches/xnu-12377/series 没有 baseband 补丁；页面第 11 行自己也允许没有蜂窝基带组件的设备跳过。选入组件或出现基带开关时重审。"
~~~

## 5 应用与复核

补丁在 k60-gates 根目录应用：

    cd E:/hackios/k60-gates
    git apply E:/hackios/k60-charger/docs/research/official/OFFICIAL-REQUIREMENTS.power.patch
    python3 scripts/check-official-docs.py --docs E:/hackios/UniXNU/docs/zh

预期输出：

    documented pages 103, mapped 20, na 4, unmapped 79

然后再跑两条本 lane 的守卫：

    python3 scripts/check-userdata-layout.py --repo E:/hackios/k60-gates
    python3 scripts/check-official-scope.py --repo E:/hackios/k60-gates

两条都应 rc 0。check-userdata-layout.py 同时证明 SHNGROOT 布局和 Data UUID 两条；check-official-scope.py 证明 security 与 qcom-baseband 的 na 前提没有移动。

如果 k60-gates 的 registry 在本补丁生成后又被 Lead 改过，先 git apply --check；冲突时按上面三块手工替换，不要用旧行号硬贴。补丁只改这三个块，不动其它 100 页。
