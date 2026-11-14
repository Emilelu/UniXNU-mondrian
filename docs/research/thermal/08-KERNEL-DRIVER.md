# 08 内核内建 tsens 驱动（patch 落地）

> 2026-11-14。`06-KEXT-SERVICE.md` 走的是 kext 归档路线（`drivers/PongThermal/*.cpp` + `-force_load`），
> 需要 `XNU_PONG_THERMAL=1` 整树构建、链接行与启动钩子三处集成。本篇是另一条路线：把只读驱动
> 直接做成 `bsd/dev/pong_thermal.c`，用补丁进树、用 `bsd/conf/files` 登记、用 `bsd_init.c` 起线程。
> 两条路线共享同一份寄存器语义与同一张 32 项传感器表，区别只在「谁把它链接进内核」。

## 1 为什么还要一条 in-tree 路线

| 维度 | kext 归档（06/07 篇） | in-tree 驱动（本篇） |
| --- | --- | --- |
| 进入内核的方式 | `-Wl,-force_load` 归档 + 链接行 | 补丁把 `.c` 放进 `bsd/dev/`，`conf/files` 编译进内核 |
| 需要的开关 | `CONFIG_XNU_PONG_THERMAL=y` 整树重建 | 无开关，补丁在就编 |
| 需要的集成改动 | 链接行、启动钩子、ADT 节点（3 处，跨线） | 只有补丁本身（1 处，本线写作用域内） |
| 服务能力 | 发布 `mTPL` 给 `thermalmonitord`（IOKit user client） | 无，只有内核日志与域温度 |
| 依赖 macOS 侧 | 是（归档由 Xcode SDK 编） | 否（CLT clang 即可，P-170） |

所以 in-tree 路线是「先让 32 路读数在真机上可见」的最短路径：它不需要 Lead 级的三处集成，
也不需要 iPhoneOS SDK。压力等级与 `mTPL` 发布仍归 kext 路线。

## 2 补丁结构（`patches/xnu/0617-k60-thermal-tsens.patch`，469 行，4 段）

| 段 | 目标 | 内容 | hunk 头 |
| --- | --- | --- | --- |
| 1 | `bsd/conf/files` | 在 `bsd/dev/pong_buttons.c\t\t\tstandard` 之后插 `bsd/dev/pong_thermal.c\t\t\tstandard` | `@@ -400,6 +400,7 @@` |
| 2 | `bsd/kern/bsd_init.c` | 在 `\t\tpong_buttons_init();` 之后插 `K60_PONG_LOCAL` 注释 + `extern void pong_thermal_init(void);` + 调用 | `@@ -1161,6 +1161,10 @@` |
| 3 | `bsd/dev/pong_thermal.c` | 新文件，232 行（仓库母本 `drivers/PongThermal/pong_thermal.c` 的逐字副本） | new file mode 100644 |
| 4 | `bsd/sys/pong_thermal.h` | 新文件，198 行（母本 `drivers/PongThermal/K60ThermalKernel.h`） | new file mode 100644 |

`patches/xnu/series` 第 230 行登记本补丁，排在 `0616-k60-init-legacy-helper.patch` 之后 ——
因为它的两个锚点（`pong_buttons.c` 那行、`pong_buttons_init()` 那行）由**更早的补丁**生成，
必须等它们全部落地后本补丁才能干净应用。

### 2.1 为什么锚点能用（P-171 的边界）

P-171 说「改构建期文件的补丁，锚点必须来自代码仓库里的稳定源」，不能来自 `.cache/xnu-work`。
本条补丁的两个锚点都是**补丁自己生成的稳定行**：`bsd/dev/pong_buttons.c` 由按键线补丁加入，
`pong_buttons_init()` 由同一个补丁加入，两者都写死在 series 里、每次构建都从 `refer/xnu` 干净 clone
再按序应用，因此它们在下一次构建里必然出现且字节相同。这与 P-171 的失败案例（锚在
「上一次成功构建后的树」的随机行）不是一回事。

**第一次尝试的教训（已修正）**：最初的 hunk 锚在 `bsd/dev/pong_fat.c` 之后，而那行不是 series 的产物 ——
它是 `K60_CONF_FILES_HOOK`（`build-xnu-4k-baseline.sh:11-19`）在 format-1 构建路径里追加的，
build-strict 走的 unixnu 路径根本不跑该 hook。结果 `git apply` 在 `bsd/conf/files:406` 直接失败，
日志 `error: patch failed: bsd/conf/files:406 / patch does not apply`。锚点必须选 series 内补丁确实写入的行。

### 2.2 应用链

`build-strict.sh` → `unixnu build kernel` → `scripts/unixnu/patches.py:prepare()`：
按 `board.toml:20` 的 `kernel.patch_series = ["device:patches/xnu/series"]` 逐行解析，
从 `refer/xnu` `git clone --shared` 建 `.cache/xnu-work`，再逐个 `git apply`（**无 fuzz 回退**）。
因此 hunk 上下文必须精确 —— 本地验证方式：在一棵「已打完 229 个补丁」的树上跑
`git apply --check`（本补丁 2026-11-14 实测 `APPLY_CHECK_OK`）。

## 3 驱动本体（`bsd/dev/pong_thermal.c`，232 行）

```
pong_thermal_init()                        // bsd_init.c 在 pong_buttons_init() 之后调用
  ├─ PE_parse_boot_argn("pong_thermal", &enabled, sizeof(enabled))   // 默认 1，=0 只打日志
  ├─ ml_io_map(TM 0x0c263000, 0x1000) / ml_io_map(SROT 0x0c222000, 0x1000)   // tsens0
  ├─ ml_io_map(TM 0x0c265000, 0x1000) / ml_io_map(SROT 0x0c223000, 0x1000)   // tsens1
  ├─ 读 SROT_HW_VER(0x000) / SROT_CTRL(0x004)  →  ver=a.b.c ctrl=0x… enabled=0/1
  ├─ pong_thermal_dump()                   // 2 行控制器行 + 32 行传感器行
  └─ kernel_thread_start(pong_thermal_worker) → thread_deallocate

pong_thermal_worker()                      // 1 s 一轮
  ├─ clock_interval_to_deadline(1000, NSEC_PER_MSEC, &deadline)
  ├─ assert_wait_deadline((event_t)pong_thermal_controllers, THREAD_UNINT, deadline)
  ├─ thread_block(THREAD_CONTINUE_NULL)
  └─ 每轮重采样；任一分域温度变化 ≥ 1 ℃ 或满 30 轮时打一行 little/big/gpu/npu/ddr
```

寄存器语义与 `06` 篇完全一致（同一张 32 项表、同一套解码）：
`TM_Sn_STATUS(n) = 0xa0 + 4n`，`LAST_TEMP = [11:0]` 符号扩展后 ×100 得毫摄氏度，
`VALID = bit21`，`SROT_HW_VER` 的 major/minor/step 拆位见 `K60ThermalKernel.h`。
**全程只读**：没有任何对映射窗口的写、没有中断、不编程 trip、不碰 SROT_CTRL。

### 3.1 日志串（上机判据）

```
PongThermal: tsens0 tm=0xc263000 srot=0xc222000 ver=1.2.3 ctrl=0x1 enabled=1
PongThermal: tsens0[0] aoss-0 zone24 54900 mC
…（32 行）…
PongThermal: little=60000 big=67000 gpu=53000 npu=49000 ddr=52000 mC
```

串口里 `grep -c 'PongThermal: '` 应 ≥ 36（2 控制器 + 32 传感器 + ≥2 轮域温度）。

## 4 离线核验（本轮已做）

| 项 | 命令 | 结果 |
| --- | --- | --- |
| 纯算术单测 | `cc -std=c11 -O1 -Wall -Wextra -Werror -I drivers/PongThermal -o build/thermal/test-kernel scripts/tests/test-k60-thermal-kernel.c` | `TESTS OK 264` |
| 既有解码单测 | 同法 `test-k60-thermal-tsens.c` | `TESTS OK 16` |
| 压力等级单测 | 同法 `test-k60-thermal-level.c` | `TESTS OK 72` |
| 补丁 ↔ 母本一致性 | `python3 scripts/check-thermal-kernel-patch.py` | `thermal kernel patch: OK (7 checks)` |
| 补丁可应用性 | 在已打完 229 个补丁的树上 `git apply --check` | `APPLY_CHECK_OK` |

`check-thermal-kernel-patch.py` 做 7 件事：从 patch 重建两个新文件并与 `drivers/PongThermal/`
母本逐字节比对；series 登记且为最后一行；`conf/files` 登记；`bsd_init.c` 的 extern 与调用都在；
母本里没有「经映射指针的写」。任何一项不成立就退出非零。

## 5 仍未完成

1. ~~**从未构建过含本补丁的内核**~~ **已构建（2026-11-14 20:38）**：`build-strict.sh thermal-20261114c`
   在自己的构建树（`K60_DEVICE_INPUT=/opt/k60/trees/thermal-device`、`K60_OUT=/opt/k60/trees/thermal-out`）
   里跑通全链（八步门禁 30 项 → 补丁应用 230/230 → 内核 → 合规门禁 → payload → bootimg）：
   `kernel.macho` 54,173,696 B，sha256 `ed0bfe2327ea55244eb95b3313264404dd43fb1d4b0caa68846dc729853331d1`，
   `strings | grep -c 'PongThermal: '` = **10**（§3.1 预言的全部串都在），
   `llvm-nm` 有 `_pong_thermal_init`/`_pong_thermal_worker`/`_pong_thermal_sample`/`_pong_thermal_sensors`/
   `_pong_thermal_controllers` 五个符号；payload kernel sha256 `827797e6ae11174908c3c161b67a1c30614b8fb6fbabf0f1b4675f1eaebe935e`，
   boot.img sha256 `09a38cb7085eef1aa97bcf8810b5b456906dbc524cd21349638e8d51a3c952f1`，
   manifest `/mnt/e/k60-work/artifacts/thermal-20261114c/build-manifest.json`。
2. **从未上机**：`SROT_HW_VER`/`SROT_CTRL` 的现场值、32 路 `VALID` 原始字都还没有。
3. **没有压力等级**：in-tree 驱动只打日志，不发布 `mTPL`；那部分仍归 kext 路线（`06`/`07` 篇）。
4. **没有 trip 编程与冷却设备**：本板 AP 侧 trip 全是被动 trip，且 `polling-delay` 多为 0，
   真要控温需要自己起策略，属后续工作。

## 6 构建阻塞（2026-11-14，环境而非代码）

`build-strict.sh thermal-20261114a --fd touch-20261114a-cf4485712c29.fd` 在
`unixnu build kernel` 的合规门禁处被拒（`scripts/check-rules.py`），失败项与 thermal 代码无关：

| 失败项 | 原因 | 归属 |
| --- | --- | --- |
| `iron-2` / `hard-5` / `hard-10` / `hard-11` | 工作树有未提交文件（本轮正在提交的就是它们） | 提交后消失 |
| `iron-1` | 三个文件注释里写了 `/tmp/...` 路径，未进 `TMP-ALLOWLIST.toml` | **本轮已修**（改成引用 `01-SAME-HARDWARE.md §5` 与 `build/thermal/`） |
| `hard-8` / `P-156` | `k60-thermal` 与 `pong_thermal` 两个 boot-arg 未登记进 `BOOT-ARGS.md` | **本轮已修**（补两行，见 `BOOT-ARGS.md`） |
| `hard-38` | `.config` 与 defconfig 不一致 —— 从 `lead-out` 复制的旧 `.config` 里 `CONFIG_XNU_K60_PHYSICAL_BATTERY=y`，本仓 defconfig 是 `not set` | **本轮已修**（删 `.config` 后用 `unixnu defconfig` 重生成） |
| `P-165` / `P-166` | 序列与构建输入不一致；`K60_DEVICE_INPUT` 未导出时比对的是共享目录 `usb-cdc-mainline/device`（含 BT 四个补丁） | 环境；设好 `K60_DEVICE_INPUT=/opt/k60/trees/thermal-device` 后 `patches/xnu` 与仓库逐项相同 |
| `iron-11` | `check-tree-owner.py` 见到未提交文件 | 提交后消失 |
| `hard-33` | `porting-gate.py --quick` 报「脏补丁 <= 1 → 2」 | 提交后消失 |

结论：这些都不是补丁或驱动的问题，而是「本地工作树尚未提交 + 构建输入没指对」造成的。
提交并重新同步 `K60_DEVICE_INPUT` 后重跑即可。

### 6.1 修完上面这批之后又撞到的四个坑（同样与驱动代码无关）

| 现象 | 根因 | 修法 |
| --- | --- | --- |
| `unixnu: XNU patch …/0617-k60-thermal-tsens.patch: git failed (1): error: patch failed: bsd/conf/files:406` | 第一段 hunk 锚在 `bsd/dev/pong_fat.c`，那行是 `K60_CONF_FILES_HOOK`（`build-xnu-4k-baseline.sh:11-19`）在 format-1 路径追加的；build-strict 走 unixnu，不跑该 hook | 改锚到 `bsd/dev/pong_buttons.c`（series 内补丁确实写入的行），`git apply --check` 通过 |
| `feeds.toml needs a source with kind = "soc" and name = "sm8475"` | `scripts/sync-device-input.py` 不复制 `feeds.toml` | `cp /opt/k60/trees/usb-cdc-mainline/device/feeds.toml /opt/k60/trees/thermal-device/` |
| `bash: …/scripts/build-battery-archive.sh: No such file or directory` | 从 `lead-out` 复制的 `.config` 里 `CONFIG_XNU_K60_PHYSICAL_BATTERY=y` | 删 `.config` 后 `unixnu defconfig` 重生成（§7 第 2 步） |
| `FileNotFoundError: …/thermal-device/.cache/firmware/k60-gpu/gmu_gen70000.bin` | `sync-device-input.py` 也不复制 `.cache/firmware`（GPU 固件由 `build-pong-adreno-platform-linux.py:91` 读取） | `rsync -a /opt/k60/trees/usb-cdc-mainline/device/.cache/firmware/ /opt/k60/trees/thermal-device/.cache/firmware/`（152 KB） |

这四条都是「自建构建输入目录比共享目录少了非仓库内容」这一类问题。下次从零建目录时，
`feeds.toml` 与 `.cache/firmware/` 要一起拷，否则会在链接前十几分钟才失败。

## 7 复现命令

```bash
# 1. 同步构建输入（把仓库镜像进自己的 device 目录）
K60_DEVICE_INPUT=/opt/k60/trees/thermal-device python3 scripts/sync-device-input.py
# 2. 用仓库 defconfig 生成 .config（不要复用别人 out 里的旧 .config）
cd /opt/k60/trees/k60build && ./unixnu defconfig -D /opt/k60/trees/thermal-device \
    --os ipados-16.6.1-20G81 --out /opt/k60/trees/thermal-out mondrian_defconfig
# 3. 严格构建
K60_OUT=/opt/k60/trees/thermal-out K60_DEVICE_INPUT=/opt/k60/trees/thermal-device \
    bash scripts/build-strict.sh thermal-<tag> --fd /mnt/e/k60-work/artifacts/fd/<fd>.fd
# 4. 验收
strings /opt/k60/trees/thermal-out/mondrian/ipados-16.6.1-20G81/mondrian/kernel/kernel.macho \
    | grep -c 'PongThermal: '
```

注意：`unixnu defconfig` 的 positional 参数要写 `mondrian_defconfig`（写 `mondrian` 会报
`configs/mondrian not found`）；`--os` 要写 `ipados-16.6.1-20G81`（写 `16.6.1-20G81` 会被拒）。
device 目录里必须存在 `feeds.toml`，`sync-device-input.py` 不复制它（需手工从共享 device 拷一份）。
