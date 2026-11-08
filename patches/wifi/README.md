# K60 WiFi 最终补丁系列

> 基线：`/opt/k60/trees/usb-cdc-mainline/device` 工作树（HEAD `70a1e4c`，含主 agent 的 GPU/触摸改动）。
> 本目录 `/mnt/e/k60-work/impl/wifi/patches/final/` 是自包含系列：`0001–0010` 为必需项，
> `optional/0011` 仅阶段 6（真机 WiFi 开关）使用。全部已在隔离副本 `../repo/` 上按顺序
> `git apply --check` + `git apply` 通过，且应用后的树与生成时的快照逐字节一致
> （见 `../evidence/final-series-verify.log`）。

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
| 0010 | `0010-scripts-build-xnu-4k-baseline-wifi.patch` | `build-xnu-4k-baseline.sh` 构建并 `-force_load` `libPongWifiNative.a` | `0004-build-xnu-4k-baseline` |
| optional/0011 | `optional/0011-board-toml-pong-wifi-arg-OPTIONAL.patch` | `board.toml` `kernel_args` 加 `pong_wifi=1`，仅临时 fastboot 镜像 | `0006-board-toml` |

> `0010` 还包含一个集成修复：`K60_WIFI_SHENG` 支持从 `PONG_SHENG_ROOT` 回退，并在调用
> `build-k60-wifi-native.py` 前 `export PONG_SHENG_ROOT="$K60_WIFI_SHENG"`，否则该脚本的
> `pong_paths.sheng_root()` 找不到 Ath12kWifi include 树。

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
