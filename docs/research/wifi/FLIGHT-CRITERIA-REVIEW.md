# 飞行判据复核：`--flight-ready` 能拦住我们哪几种历史失败

这份复核只读。它审的是 Lead 的 `E:/hackios/k60-gates/scripts/check-ios27-artifacts.py`（395 行，
sha256 `b6216d66d4a72e86bcc8dd3f15ccec8245025d9ed6ad833f207cea525b2a8891`）与
`docs/engineering/IOS27-FLIGHT-BLOCKERS.toml`（26 行，2 条均 open），对照的是本线 2026-11-14 至
2026-11-20 的五种失败形态。没有构建、没有上机、没有改共享仓。

我方分支里的同名副本是旧的：232 行、没有 `--flight-ready`、不读 blockers 文件；用 sha256 `59c5996b…`
可以把它和权威副本区分开。分支内这份副本不能当判据，等 merge 换新，不要手抄。

## 1. 现有 gate 覆盖什么

| 层 | 断言 | 失败信息 |
|---|---|---|
| Mach-O 头 | `MH_MAGIC_64`、`cputype 0x0100000C`、`cpusubtype&0xFFFFFF==2`（arm64e）、filetype 是 `MH_EXECUTE` 或 `MH_FILESET` | 头不合格 |
| 可执行 | `MH_NOUNDEFS`、`MH_PIE`、`LC_BUILD_VERSION` platform 2（iOS）、minos/sdk 主版本 27 | 不是 27 的 iOS 可执行 |
| fileset | 至少一条 `LC_FILESET_ENTRY` | 空 fileset |
| 载荷 | 重放 `patch-armcpu-validate.py --apply`，FAT 成员逐字节比对；`payload.json` 的 `kernel_sha256` 必须等于实际内核 | 包装变换或账本不符 |
| ADT | `/chosen` random-seed 256 B 全同、chip-id `8140`、unique-chip-id `4d4f4e445249414e` | 身份不符 |
| boot.img | `ANDROID!` v4、0x300000 尾部固件卷、`_FVH`、DTB、ramdisk 等于 payload | 组装不符 |
| prelink | 从 `kernel/kernel.json` 读 `missing_refs` / `stubbed_refs` | fileset 有未解析则拒飞 |
| 阻断账本 | 任一 blocker 的 `state` 不是 `closed` | `structurally valid, but not flyable: …` |

它完全不看链接输入：内核里有哪些归档、归档是不是同一架构、符号是不是临时桩提供的。
这恰好是我们这条线三次假绿的所在地。

## 2. 五种历史失败形态与可判定性

| 形态 | 证据 | 现有 gate 能否拦 | 补什么能在飞行前判 |
|---|---|---|---|
| S1 静默：console 0 字节、`port-not-observed`、`fastboot-return` | c0 `usblog-20261115-213221`（`DARWINBOOT-POOL.md:238-256`）；z0、mhi3/mhi4（`BOOT-DEATH-BISECT.md:37-38,144-147,200`） | 否。结构全对；c0 的死因是配置里写了 32 MiB seed 的 Data 卷 UUID（P-152），内核在 USB 控制台起来前就 self-panic | 对**镜像里的内核**比对 Data 卷 UUID 与设备最新 `PongDataWindow` 日志，而不是只比 defconfig（`scripts/check-data-identity.py:1-24` 已在做前半段） |
| S2 驱动起来但端口没出现 | `usblog-20261118-005525`（143,253 B / 2,079 行）：到 SpringBoard、`ath11k: failed to power up mhi: -110`、无接口；机制 `SBL-QUEUE.md:169-176` | 否。这是运行时结果，不是镜像属性 | 预声明验收行（见 §5.3） |
| S3 错架构归档被静默丢弃 | 27 内核 arm64e、归档 arm64，ld 只打 `ignoring file … built for iOS-arm64`，符号数 0（SBL §67.1） | 否 | 读 `linkarchives`，对每个 `-force_load` 归档断言 cputype/subtype 等于内核（见 §5.1） |
| S4 临时桩提供链接符号 | 九个 scratch 定义让 35,613,936 B 镜像链接成功（SBL §67.5） | 否 | 同一份 `linkarchives` 里做来源白名单（见 §5.1） |
| S5 镜像身份混淆 | z0 117,305,344 B 与 66 MB 的 C 格不符；trial a2 没有 series 指纹（P-201） | 部分。已比 `kernel_sha256`，但不能说明是哪个源码树、哪份配置产的 | 构建记录带 series 指纹与配置名；见 §5.2 |

结论：**五种里四种可以在飞行前离线判定**（S1、S3、S4、S5），S2 只能靠预声明的验收行；
把 S2 写成更强的结构检查是方向性错误。

## 3. 链接输入其实是可读的

历史 scratch 镜像（`/tmp/ios27ext4/ios-27.0.1-24A446/mondrian_ios27/tree/build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837`，
35,613,936 B，非可复现构建）旁边就有两份现成记录：

- `mach.development.bcm2837.link/mach.development.bcm2837.linkarchives`（670 B）逐项列出 `-L` 与
  `-Wl,-force_load,<path>`：firehose、corecrypto 名字空间版、ArmDTPlatform、ArmCpu、libpthread、
  `teardown27g/libPongWifiNative.a`，最后一项是 **`/mnt/e/k60-work/scratch/libStub27.a`**——S4 自己就写在这份清单里。
- `link.filelist`（1,075 个 `.o`）和 `mach.development.bcm2837.linkarguments`（2,739 B）。

也就是说 S3/S4 不是「需要新仪器」，而是「已经有账本没人对账」。

## 4. 建议加在 gate 本身的两条断言（不是 blocker 条目）

### 4.1 归档架构一致（S3）

对 `linkarchives` 里每个 `-force_load` 路径：`llvm-readobj --macho-version-min`/`--file-headers` 读成员，
要求每个成员的 `cputype` 与 `cpusubtype & 0xFFFFFF` 等于内核；任一不等即 refuse，并把
`ignoring file … built for iOS-arm64` 这类只看 warning 的信息升级为错误。归档不存在也 refuse。

### 4.2 归档来源白名单（S4）

把 `-force_load` 集合与板级声明（`board.toml` 的 archives、`components.toml` 的 outputs、以及
`XNU_PONG_WIFI_ARCHIVE` 这类显式输入）做集合比较；清单外的归档一律 refuse。判据是「来源可声明」，
不是「路径长得像」。这一条能直接拦住 `libStub27.a`。

### 4.3 为什么不做成 blocker 条目

现有 `IOS27-FLIGHT-BLOCKERS.toml` 是**全局**账本：任一条 open 就拒绝**所有** 27 镜像飞行。
把 Wi-Fi 归档契约写成 open 条目，会连没有 `CONFIG_XNU_PONG_WIFI=y` 的 stage-0 试飞一起拒掉。
要么给条目加适用条件（例如 `applies_when` 指定配置键），要么把上面两条放进 gate 的结构检查。
后者更简单，也不改账本语义。

### 4.4 已实现：`scripts/check-wifi27-link-inputs.py`

两条断言都落成一条命令，输入就是内核构建自己留下的 `linkarchives`，不需要重新构建：

```sh
python3 scripts/check-wifi27-link-inputs.py --link-record <obj>/mach.development.bcm2837.linkarchives \
    --allow-root /tmp/<tree> --allow-root /opt/k60/trees/k60build/wifi
```

- **arch**：每个成员的 cputype/subtype 必须等于内核；归档不存在或为空都 refuse，不跳过。
- **provenance**：每个 `-force_load`（以及记录里的 `.a`、能按 `-L` 解析的 `-l`）必须落在声明根内，
  或出现在带 sha256 的 `--declared` 清单里，且不匹配 `--forbid`（默认 `libStub|stub[0-9]|/scratch/`）。

对真实记录三跑（`--ar llvm-ar-18`）：

```
PASS arch: 6 archives, arm64e          # 在构建原样记录里去掉 libStub27.a 那一行
PASS provenance: 6 archives declared    rc=0

PASS arch: 7 archives, arm64e          # 构建原样写下的记录
FAIL provenance: /mnt/e/k60-work/scratch/libStub27.a is named like a scratch stub
                                        rc=1
FAIL arch: /opt/k60/trees/k60build/wifi/ath11k-abi27s/libPongAth11k.a(PongAth11k-linked.o) is not arm64e
PASS provenance: 1 archives declared    rc=1（真实 arm64 归档当负例）
```

这正是 §4.3 的选择：它只读这条线自己的链接账本，没有 Wi-Fi 归档的 stage-0 镜像不会被它拒绝。
全局 `IOS27-FLIGHT-BLOCKERS.toml` 保持不动；坏例的五个形态（成员非 arm64e、符号缺失、stamp 与 header
不一致等）分别由本脚本的 7 个用例和 `test-wifi-station-archive.py` 的 5 个用例钉住。

## 5. 不进 gate 的两条数据检查

### 5.1 Data 卷 UUID 对镜像比对（S1）

`scripts/check-data-identity.py` 现在只比对 `configs/*defconfig` 与最新 `PongDataWindow` 日志。
c0 证明「配置对、构建却用了别的配置」这一层没人查。最小补法：在镜像的内核载荷里搜卷 UUID
（c0 的 `6DCCF70A…` 与真机的 `1BCD69FF…` 都是可搜字符串），与设备日志比对；无日志时 SKIP，不猜。

### 5.2 series 指纹（S5）

`payload.json` 已有 `kernel_sha256`，但没有「哪个源码树、哪份 defconfig、哪次 series 应用」的记录。
P-201 的 a2 就是靠人眼发现少了指纹。建议构建记录里强制写 series 指纹与 defconfig 名，缺了 refuse。

### 5.3 验收行（S2）

板级 profile 里声明 `expect` / `forbid` 行集合，例如 expect `wifi-net: station start`，
forbid `failed to power up mhi`；判读器只输出三类结论：`accepted`、`port-not-observed`、`died-before-<marker>`。
没有预声明时，任何「驱动起来了」的叙述都不成立——这正是 `SBL-QUEUE.md:144-148` 的教训。

## 6. 不建议做的事

- 不要把 232 行的分支副本当 gate 用，也不要把 395 行版本手抄进本仓；等 merge。
- 不要把语义未定的东西（例如 C3 的 0x80 频道位）写成飞行阻断项：它既拦不住飞行，也会把
  「没有 0x80」误标成不合格。C3 的判据见 `SHENG-KERNEL-REFERENCE.md` 的 I 节阶梯。
- 不要用「gate 通过」替代验收：结构合格只说明镜像自洽，不说明端口出现。

## 7. 复现

```sh
sha256sum /mnt/e/hackios/k60-gates/scripts/check-ios27-artifacts.py   # b6216d66…
wc -l /mnt/e/hackios/k60-wifi/scripts/check-ios27-artifacts.py       # 232, 无 --flight-ready
cat '<obj>/mach.development.bcm2837.link/mach.development.bcm2837.linkarchives'

# 链接输入两条断言（§4.4）：6 个归档 arm64e 且都在声明根内才是 0
python3 scripts/check-wifi27-link-inputs.py --link-record '<obj>/…linkarchives' \
    --allow-root /tmp/ios27ext4 --allow-root /opt/k60/trees/k60build/wifi
python3 scripts/tests/test-wifi27-link-inputs.py    # 7 cases
```
