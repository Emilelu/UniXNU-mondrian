# K60 WiFi 最终补丁系列

> 基线：`/opt/k60/trees/usb-cdc-mainline/device` 工作树（HEAD `70a1e4c`，含主 agent 的 GPU/触摸改动）。
> 2026-11-12 的原始系列为 `0001–0010`（`optional/0011` 仅阶段 6 使用），并已在隔离副本
> `../repo/` 上按顺序 `git apply --check` + `git apply` 通过，应用后的树与生成时的快照逐字节一致
> （见 `../evidence/final-series-verify.log`）。
> 2026-11-17 复核：实际目录为 `0001–0012` 共 12 个补丁，`series` 12 行，没有 `optional/` 子目录；
> `0011–0012` 是后续增量，见下表。

## 应用顺序（必需）

```bash
cd /opt/k60/trees/usb-cdc-mainline/device
for p in /mnt/e/k60-work/impl/wifi/patches/final/0*.patch; do
  git apply --check "$p" && git apply "$p" || exit 1
done
```

| # | 文件 | 作用 | 对应原补丁 |
|---|---|---|---|
| 0001 | `0001-drivers-PongWifi-vendor-zizhan-087416a.patch` | 引入 zizhan `drivers/PongWifi` 整树（14 文件，HEAD `087416a`，字节一致） | `new/drivers/PongWifi/SOURCE.txt` + rsync |
| 0002 | `0002-drivers-PongWifi-ath11k-compat-28de7b91.patch` | 删除 `PongCompat.h` 中与 Ath12kWifi `28de7b91` 冲突的 `skb_get_hash` 静态桩 | 无（本次编译发现） |
| 0003 | `0003-drivers-PongWifi-k60-rsc-gate.patch` | `pong_rpmh_vote()` 加 `k60_wifi_rsc` boot-arg 门，默认不触碰 APSS RSC/TCS4 | `optional/0007` |
| 0004 | `0004-drivers-NativeUfs-pong-ufs-ready.patch` | 补 `gWifiUfsReady` / `pong_ufs_ready()`；UFS SMMU plan 加 weak lease | `0001-nativeufs` |
| 0005 | `0005-drivers-ArmDTPlatform-pong-wifi-hook.patch` | `pong_wifi_start_optional()` 启动钩子（wifi→adreno 顺序） | `0002-armdtplatform` |
| 0006 | `0006-scripts-build-pong-platform-xnu-pong-wifi.patch` | `build-pong-platform-macos.py` 传 `-DXNU_PONG_WIFI=` | `0003-build-pong-platform` |
| 0007 | `0007-configs-mondrian-wifi-defconfig.patch` | 新增 `configs/mondrian_wifi_defconfig`（opt-in） | `0005-configs` |
| 0008 | `0008-configs-mondrian-wifi-sm8475.patch` | 新增 K60 board profile（82 PHY、6 rails、refgen index 10） | `new/configs/mondrian-wifi-sm8475.json` |
| 0009 | `0009-scripts-k60-wifi-build.patch` | 新增 4 个脚本，并修正 `build-k60-ath11k.py` 与 Ath12kWifi `28de7b91` 的兼容性（见下） | `new/scripts/*` |
| 0010 | `0010-scripts-build-xnu-wifi-archive.patch` | `build-xnu-4k-baseline.sh` 构建并 `-force_load` `libPongWifiNative.a` | `0004-build-xnu-4k-baseline` |
| 0011 | `0011-drivers-PongWifi-k60-bringup-stages.patch` | `k60_wifi_stage=N` 分阶段放开 MMIO 访问，把死机定位到单个块 | 无（后续增量） |
| 0012 | `0012-drivers-PongWifi-lease-lock-lazy-init.patch` | `pong_smmu_lease_lock()` 首次使用时分配锁，修复 NativeUfs 先取 lease 的启动失败 | 无（后续增量） |

> `0010` 只做 `build-xnu-4k-baseline.sh` 的 archive 接线。当前主仓 `0010` 只覆盖 `KERNEL_EXTRA_ARCHIVES`；`k60-wifi` 的更新版还覆盖 `PLATFORM_ARCHIVES`（见“与 k60-wifi/feat/wifi-bringup 的系列漂移”）。旧文提到的 `K60_WIFI_SHENG` 回退在当前 `0010` 中不存在，已删。

## 与 k60-wifi/feat/wifi-bringup 的系列漂移（2026-11-17 实测）

主仓这套 `patches/wifi` 比 `k60-wifi` 检出 `feat/wifi-bringup` 的同目录旧：两边 `series` 都是 12 行，
但主仓 12 个补丁合计 **221,744 B**，k60-wifi 为 **228,302 B**；5 个文件字节不同：

| 文件 | 主仓 | k60-wifi | 差在哪 |
|---|---|---|---|
| `0003-drivers-PongWifi-k60-rsc-gate.patch` | 2,181 B | 2,586 B | k60-wifi 的 RSC 探针按 `0xd00 + 4*0x2a0` 读 TCS4 的 id/caps/idle/status 并校验 count/ncpt，主仓仍按 `0x17a20000 + 0x10000` 读一次 |
| `0007-configs-mondrian-wifi-defconfig.patch` | 3,141 B | 3,291 B | 主仓写旧 Data UUID `6DCCF70A-6FD6-403E-ACED-95313CD7CBB8`；k60-wifi 改为实机发布的 `1BCD69FF-24A5-48B1-94B6-8FE592B2F597`（console 2026-11-12 17:09 `window media uuid=1BCD69FF-... bsd=disk5s1`），旧值会让 K60DATA 等 5 s 后 `dataerr=2` 并触发 P-152 |
| `0009-scripts-k60-wifi-build.patch` | 51,753 B | 56,810 B | k60-wifi 带更完整的 `build-k60-ath11k.py` 兼容修复与脚本 |
| `0010-scripts-build-xnu-wifi-archive.patch` | 1,629 B | 2,575 B | 主仓只把 `XNU_PONG_WIFI` 加到 `KERNEL_EXTRA_ARCHIVES`；mondrian 实际走 `PLATFORM_ARCHIVES`，k60-wifi 已补第二个分支，否则内核会静默不带 PongWifi |
| `README.md` | 7,481 B | 8,282 B | k60-wifi 版保留更多历史说明 |

> **结论**：主仓 `patches/wifi` 不能直接接进构建。接线时要以 k60-wifi 的 12 个补丁为准，先合并 `0007` 的 UUID 与 `0010` 的双归档分支差量；两边 `board.toml:20` 都仍只挂 `patches/xnu/series`，没有自动 applier，等 Lead 裁决。

## `build-k60-ath11k.py` 相对 zizhan 原脚本的 5 处兼容修复（0009 内含）

均因 `Ath12kWifi` pin `28de7b91` 比 zizhan 脚本编写时的 ABI 新：

1. `adapt_dispatcher_timers()`：pin 已内置 bounded dispatcher（`for (unsigned budget = 0; budget < 64; ...)`），旧的 `old` 文本不存在；改为检测已修复形态则原样返回，否则仍按旧文本替换/报错。
2. 编译 flags 增加 `-I <linux>/include` 与 `-I <linux>/include/uapi`：pin 的 `shim/include/lx.h` 包含 `<linux/kconfig.h>`。
3. 从 `include/linux/netdevice.h` 生成 `pinned/linux/netdevice_enums.h`（与 Ath12kWifi `tools/pin-headers.sh` 同一提取规则），因为 `lx_skb.h` 引用该拆分头。
4. `pci.c` 重命名同时处理 `module_exit(ath11k_pci_exit)` → `module_exit(pong_ath11k_pci_exit)`，否则 shim 的 `module_exit` 展开产生未声明调用。
5. `common_sources` 补 `src/nw_events.c`、`src/nw_netdev.c`，并编译 Linux `lib/rbtree.c`：pin 把 netdevice/events 从 `nw_net.c` 拆出，且 `nw_net.c` 使用 `rb_insert_color`/`rb_erase`。

## 校验

```bash
# 逐个应用（隔离副本）
bash /mnt/e/k60-work/impl/wifi/tools/verify_series.sh

# 语法
bash /mnt/e/k60-work/impl/wifi/tools/syntax_check_core.sh
bash /mnt/e/k60-work/impl/wifi/tools/lint_scripts.sh

# 真实编译（不含内核链接）
bash /mnt/e/k60-work/impl/wifi/tools/build_ath11k_check.sh
bash /mnt/e/k60-work/impl/wifi/tools/build_wifi_native_check.sh
```

> 原补丁与原始 `new/` 文件保留在 `patches/original/` 供对照；最终系列已包含全部新增文件，主 agent 无需再手工 `rsync`/`cp`。

---

## 接线状态（2026-11-12 核实，SA-03；2026-11-17 复核）

**2026-11-12 时这 9 个补丁从未被应用** —— 全仓没有任何 `series` 或 applier 引用 `patches/wifi`。
本目录现在有 `series`（0001-0012），但 main 仍没有 applier 读它，只有 `scripts/tests/test-pong-smmu-lease.py:76`
断言 0012 在 series；接线仍等 Lead 对 `patches/wifi` 的裁决。要真正生效还需要两步：

1. **接入构建**：`unixnu` 目前只认 `patches/xnu/series`。要么把 wifi 补丁并进那条系列，
   要么在构建流程里加一个 applier 步骤。
2. **`0010` 已补（2026-11-12）**：`0010-scripts-build-xnu-wifi-archive.patch`
   在 `build-xnu-4k-baseline.sh` 的归档块里加 `XNU_PONG_WIFI` 门禁 +
   `-Wl,-force_load,$PONG_WIFI_ARCHIVE` + 依赖项。写法照抄现有四个 probe 归档
   （`ADRENO_PROBE` / `PM4_PROBE` / `SMMU4K_PROBE` / `CONSTANT_UPLOADS`）。
   默认 `XNU_PONG_WIFI=0`，没有 archive 的树照样链接。

## 已知 bug：refgen 索引写错

`PongWifiPlatform.cpp:221`（在 `0001` 补丁里）：

```c
gcc.w(0x7b04c, (1u << 8) | 11u);
```

`11` 是 **Pong 的** refgen 索引。K60 profile 的 100 MHz 在 **index 10**
（index 11 全 0），而 `0009` 的脚本也断言 `[10]`。

**首次 bring-up 必选错父时钟，链路训练会失败。**

`:335` 的 `gcc.w(0x7b04c, 1)` 也要按 K60 重算。

**已修（2026-11-12）**：`0001` 补丁第 1495 行 `(1u<<8)|11u` → `(1u<<8)|10u`。

`:335` 的 `gcc.w(0x7b04c, 1)` 仍然未动 —— 那一处写的是另一个寄存器位的使能，
不是 refgen 索引，但它的位含义也要按 K60 的 RCG 表重算。等能读到 K60 的
GCC 时钟树（Android 侧 `/sys/kernel/debug/clk/` 或 live FDT）再定。

## RSC 策略（2026-11-12 决定）

`0003` 原本只有一档：`k60_wifi_rsc=1` 才投票，默认全关。
现在拆成两档，因为**探针和投票的风险不同**：

| 值 | 行为 |
|---|---|
| 不设 / 0 | 完全不碰 RSC，`supplies()` fail-safe |
| **1** | **只读探针**：`rsc.open(0x17a20000,0x10000)` 读一次 TCS4，打印值，**拒绝一切投票** |
| **2** | 允许投票（前提是探针读到合理的 TCS4，非 0 / 非 0xFFFFFFFF）|

判据来自 `0003` 自己的注释：`K60-TOUCH-PARAMS.md:120,174` 说在 RSC 电源/互联域
未证明可用时访问会**硬挂整机**。而「读一次」的失败是可观察的（拿到 0 或 0xffffffff），
「写一次」的失败不是。所以先给一个只读档。

**证据缺口**：触摸驱动只 `ml_io_map` 了 `0x17a20000`（`Pong touch: DIAG mapped ... rsc=`），
没有任何代码真的**读**过它。所以「映射安全」不等于「读取安全」，第一档仍需实测。
