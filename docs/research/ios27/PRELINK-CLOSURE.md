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

## 第二轮（2026-11-21 03:30）：配置假设被证否，剩下的是配对与版本差

第一版把 150 个地址归因成「我们没编那些子系统」，**这是错的**，本轮实测推翻：

- `CONFIG_XNU_*` 不是 XNU 的选项机制。`UniXNU/scripts/unixnu/kernel.py:17-26` 只把 `XNU_`
  前缀的键转成环境变量；真正决定编什么的是 `KERNEL_CONFIGS=DEVELOPMENT`，硬编码在
  `scripts/build-xnu-generic.sh:147`（和 `:840`），由 `config/MASTER*` 解析成
  `security/DEVELOPMENT/config.DEVELOPMENT_ARM64`（184 行，`CONFIG_MACF` 在第 126 行）。
- 结果是 MACF 一直在编：我们内核里有 23 个 `mac_*.o`、`_amfi*`、`_image4_v2_interface*`、
  36 个 `_apfs*`。
- 对照实验否掉「符号不在 = 开关没开」：`CONFIG_ECC_LOGGING` 与 `CONFIG_IMAGEBOOT_IMG4`
  都开着，而 `_ecc_*`、`_image4_v2_evaluate` 既不在我们内核里、也不在 `refer/xnu` 任何
  文件里。

于是 150 分成两类：

| 类 | 数量 | 结局 | 危险度 |
| --- | --- | --- | --- |
| 数据（`__ZN*10gMetaClassE` 等） | 19 地址 / 95 项 | `rebind()` 找不到配对就**原样保留 Apple 的地址** | **高**：不跳桩、不报错，首次解引用即垃圾/abort；13 个落进无关本地段、6 个落在所有段之外；AMFI 占两个，而 AMFI 是 `early_security_init` 点名的 bundle |
| 函数 | 131 地址 / 205 项 | 重定向到 `_unixnu_fileset_unmapped`，会打印调用点 | 中：会明确报点 |

关闭这条路只有两种走法，都不能靠猜：

1. **拿到 19 个数据目标的符号名**——Apple 的 kernelcache `LC_SYMTAB nsyms 0`，读不出来；
   所以只能从结构上恢复（C++ 元类全局的形状），这属于推断，需要逐条证据。
2. **逐站点人工绑定**（kit 已支持的 `fixtures/fileset-*-symbols.json` 扩展点：每个 site
   绑定一个 native 符号并附 `evidence`），并且让 6 个落在所有段之外的槽位 **fail-closed**，
   而不是保留陈旧地址。

结论：`prelink-map-unresolved` 保持 open，且**不许**用「反正走不到」放过——数据类没有桩，
走不到与走得到在日志里是同一个样子（都没有日志）。
