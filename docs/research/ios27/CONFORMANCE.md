# 与 Sheng 的 27 配方逐项对照（机器生成 + 人工理由）

`scripts/audit-ios27-conformance.py` 把我们的 27 内核配方与 `E:/hackios/UniXNU-sheng`
（同一 OS profile 家族、同一 xnu-12377）逐字段比对。三态：

- `same` 两边一致；
- `justified` 有差异，但 `CONFORMANCE-DEVIATIONS.toml` 给了理由，且理由引用的文件在本仓可解析；
- `GAP` 有差异且无人解释 —— 这一项就不能说「严格参考了 Sheng」。

首跑读数 **SAME 6 / JUSTIFIED 0 / GAP 66**（只比 `board.toml`，比错了层）；把 OS profile 那层合并进来后 **SAME 40 / GAP 17**，其中 12 条是真缺的 USB/HID/SCSI 家族；把这 12 条写进 `[kernel.prelink].roots`（42 包含 + 2 排除）之后 **SAME 55 / JUSTIFIED 36 / GAP 0**（`diag/menu-hold-20261121`，2026-11-22）。原始读数：
官方 registry 103 页里 mapped 21、na 4、**unmapped 78（76% 从未审）**。

## 一、结构差异（K60 与 Sheng 的板子不同，属设计差异）

| 项 | 我们 | Sheng | 理由 |
| --- | --- | --- | --- |
| `board.os_profile` | `ios-27.0.1-24A446` | `ipados-27.0.1-24A446` | 同一次 24A446 构建；K60 是手机，用 iOS profile 名 |
| `kernel.driver_records` | `DEVELOPMENT_ARM64_BCM2837` | 不声明（走 profiles 默认） | 12377 没有 `PONG.h`，`makedefs/MakeInc.kernel:22` 对 `PONG` 直接 `Stop.`；BCM2837 是 12377 里唯一的 4 KiB 机器配置 |
| `kernel.config_fragments` | arch + **soc:sm8475** + os | arch + os | K60 的 SoC 片段是本仓提供的；Sheng 的 SM8550 参数在 arch 层 |
| `package.defconfig[27]` | `mondrian_ios27_defconfig` | `sheng_ipados27_defconfig` | 不同板子各自的 defconfig |

## 二、stage-0 有意不做的事（可由目标定义解释）

`docs/engineering/IOS27.md` 把 F1/F2 的出口定为「`arm_init` → `bsd_init` → root mount →
`Early boot complete`」。下面这些开关属于「起来之后」的能力，stage-0 打开只会把
未验证的子系统放进内核：

- `CONFIG_XNU_NATIVE_ADRENO` / `NATIVE_LEGACY_DISPLAY` / `NATIVE_RAM_BLOCK`
- `CONFIG_XNU_OWNER_*`（root audit/trust、cache mount/startup、boot manifest、union systemos）
- `CONFIG_XNU_SOURCE_STORAGE*` / `CONFIG_XNU_EXTRA_LD_ARCHIVES`（`libShengSourceStorage.a`）
- `CONFIG_XNU_NATIVE_UFS`（27 侧 `n`；16.6.1 侧才是 `y`）
- 归档：`component:Adreno740`/`ShengUfs`/`RamBlock`/`AppleKeyStoreState`、
  `build-adreno740-*`、`build-sheng-source-storage.py`、`fetch-sheng-dts.py`、
  `prepare-sheng-gmu*.py`、`build-gop-legacy-display-27.py`

我们这一侧多了三件 Sheng 没有的：`build-firehose-stub.py`（arm64e 桩，27 的
`libfirehose_kernel.a` 只有 arm64）、`build-k60-platform-archives.py`（K60 的
ArmDTPlatform/ArmCpu 归档）、`build-k60-fileset-reference.py`（把 Mac 上建的 LTO
参考装回构建缓存）。

## 三、真正的缺口（不是设计差异）

1. **`[kernel.prelink].roots` 我们一项都没声明**，Sheng 声明了 44 项。我们不声明就等于
   接受 `kits/XnuPrelink` 的默认集合 —— 结果是 prelink 残留 94 项无地址 / 203 项落桩，
   而上游 policy 基线是 2 / 24。这一项**不能**用「stage-0 不需要」解释：roots 决定的是
   **集合里有哪些 kext**，直接决定那 203 个桩会不会被调用。
2. **defconfig 8 键 vs 19 键**：其中 `CONFIG_XNU_CRYPTO_BOOTSTRAP`、`CHAINED_FIXUPS`、
   `DT_PANIC_REGION`、`ARMVIRT_PLATFORM` 四条两边相同（基础形状已被独立验证），
   其余属上面第二节；但「不需要」目前是**推断**，没有逐条证据。
3. **Sheng 的三件实现我们一件都没用**：`T0SZ_USER != T0SZ_BOOT`（4 KiB 用户 ABI 定稿）、
   `sheng_sigp_recover()`（SMP 下 UFS 根起不来）、`native_kobj_map_grant`（GPU 映射沙箱）。
4. 我们自造了两处：`drivers/ArmCpu` 遮蔽 catalog 组件 + 真 `psci_smp.c`（`0540`）；
   `0546` ramoops 控制台（官方文档与 Sheng 都没有）。

## 四、纪律

- 这张表每轮跑一次，`GAP` 数必须单调下降；每条转 `justified` 都要在
  `CONFORMANCE-DEVIATIONS.toml` 加理由 + 可解析证据。
- **不许**为了让脚本变绿把 `prelink-root:*` 写成「stage-0 不需要」。
- 官方页覆盖率（`unmapped 78/103`）与站点真实规模（581 页）的差距记在
  `docs/engineering/OFFICIAL-REQUIREMENTS.toml` 的待办里，不在这里重复。

## 2026-11-22 00:40 · 12 个 USB/HID/SCSI 家族退回（实测代价）

把 Sheng 的 12 个家族并进 kernel.prelink 的 roots 表（42 包含 + 2 排除 = 44）之后重建，
读数往坏的方向走：

| 项 | 30 roots（OS profile 原样） | 44 roots |
| --- | --- | --- |
| kext 条目 | 32 | 49 |
| 无地址引用 | 94 项 / 21 bundles | 155 项 / 34 bundles |
| 落 panic 桩 | 203 / 25 | 234 / 34 |

原因是每个 Apple 编译好的 kext 都带着自己的导入表，而符号定义者在我们这棵内核里没有。
inclusion 越多、未配对越多，console 起来之前的风险面越大。上游 policy 还点名四条
AppleARMPlatform 的 original 各 1 个站点，而 policy 写的是 allowed 0。

裁决：stage-0 只保留 OS profile 的 30 个 root，12 个家族等 USB 控制台那两条
（0243 / 0300）真正落地时再并入——那时它们才有调用者。已用
git checkout 14e7a1f0 -- board.toml 退回，check-prelink-roots.py 仍绿。

这条与 P-306 是同族但方向相反：抄列表要逐条判，判的是「现在有没有调用者」，
不是「对方有没有」。
