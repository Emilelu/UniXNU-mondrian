# 预链接闭合审计（F1 最后一关）

镜像：`/opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/kernel/kernel.json`
参考：`scripts/xnu-fileset-reference/mach.release.bcm2837.unstripped.noctf`（LTO，6,102 符号，sha256 `71d351ce…`）
日期：2026-11-21

## 结论先行

LTO 参考把未解析引用从 **384 条 / 2262 个桩站点** 降到 **95 条 / 205 条**。剩下的 150 个**不同**地址按 bundle 分组后，形状很清楚：**绝大多数是我们这棵树根本没编的功能**，不是 ABI 对不上。

`.config`（46 行、15 个 `=y`）里 **MACF / AMFI / sandbox / APFS 一个键都没有**。所以：

| 证据 | 数值 |
| --- | --- |
| `com.apple.driver.AppleMobileFileIntegrity` | 41 处（最大单一来源） |
| `com.apple.security.sandbox` | 23 处 |
| `com.apple.filesystems.apfs` | 20 处 |
| `com.apple.security.Image4` / `AppleImage4` | 7 / 7 处 |
| `com.apple.kec.corecrypto` | 3 处 |

这些 kext 进了 roots（所以它们**在集合里**），但它们调用的内核符号属于我们没编进去的子系统（MACF 框架、sandbox 策略表、APFS 挂载栈、Image4、crypto 选项）。参考里有 `mac_policy` 17 个、`amfi` 6 个、`sandbox` 3 个符号正是它们要的。

## 分组全表（missing / stubbed 合计）

去掉上面五个子系统后剩下约 60 处，集中在：

| bundle | 处数 | 初判 |
| --- | --- | --- |
| `AppleARMPlatform` | 28 | 真 ABI 缺口（我们用的是 vendored fork 的 CPU provider，catalog 版符号不同） |
| `IOAVFamily` | 24 | 一半是 config（`CONFIG_XNU_MEDIA` 之类），待查 |
| `IOHIDFamily` | 24 | 部分 `armcpu_spi_attach` 系（我们 ArmCpu fork 加的 SPI owner 表） |
| `IOSurface` / `IOGPUFamily` | 18 / 14 | GPU 线的东西，stage-0 有意未接 |
| `AppleARMWatchdogTimer` / `ApplePMGR` | 10 / 11 | PMGR 钩子在 soc 层补丁里，需确认是否编进去 |
| `IOStorageFamily` / `CoreAnalytics` / `IOAudio2` / `IODART` / `IOReport` / `IOHDCP` / `IOCEC` / `IOCryptoAccelerator` / `M2ScalerCSC` | 各 1–5 | 零散，逐个看 |

## 处方（按顺序，每步都离线可验）

1. **把 27 stage 真正需要的安全/存储开关打开**。sheng 的 `configs/sheng_ipados27_defconfig` 有一整组我们没开的键（`CONFIG_XNU_CRYPTO_BOOTSTRAP="source"`、`CONFIG_XNU_OWNER_ROOT_TRUST/AUDIT`、`CONFIG_XNU_SOURCE_STORAGE*`、`CONFIG_XNU_KERNEL_CHAINED_FIXUPS` 等），先照它开、再看 MACF/AMFI/sandbox 是否随碎片进来。
2. 重新 prelink，看前五行子系统是否塌下去。塌不掉就说明还有独立开关没开，继续按缺失符号反查它属于哪个 `CONFIG_`。
3. 对剩下的约 60 处，用 `scripts/xnu-symbolize.py --find <指令字>` 定位调用点，逐个判定：补开关、补符号、或确认「这条路径 stage-0 走不到」。
4. 全部有结论后才把 `prelink-map-unresolved` 改 `closed`，再谈飞行。

## 纪律

- **不许**为了让计数好看去加 root 里没有的 kext，也不许放宽 `--allow-missing` 的语义。
- 每一条「走不到」都要写成「什么条件下会走到 / 为什么现在走不到」，不是一句「应该没事」。
- 这张表每轮更新，计数减少要有对应提交。
