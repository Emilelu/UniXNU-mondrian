# 未归属旧脚本：目录 / owner 清单

来源：`feat/power-ios27-branch` @ `ee12c7e1`（首次清单生成于 `99a711d9`，本文按当前树复核）。
门禁（应用前）：`PYTHONUTF8=1 PYTHONIOENCODING=utf-8 python3 scripts/check-porting-paths.py --quiet` → `FAILED: 205 problem(s)`。
门禁（应用 41 条 pattern 后）：→ `FAILED: 1 problem(s)`，只剩 §6 的 cpu evidence 悬空引用。
其中 **204** 个是 `no area claims tracked path`，**1** 个不是未归属错误。
机器可读清单：[`PORTING-OWNER-MAP.tsv`](PORTING-OWNER-MAP.tsv)（204 行，`path/last_commit/last_scope/area/owner/basis`）。

**41 条 pattern 已应用到本分支 `porting.toml`；** 只加 area/owner，不改脚本行为。`owner` 仍是建议审查人，`area` 是 porting 归属；`porting.toml:76` 的 cpu evidence 悬空引用按 Lead 裁定单独修，不混入这次提交。

## 1. 结论

- 204 个路径全部可以归入 8 个 area；按目录/脚本组追加 **41 条 pattern** 即可收口，不需要逐文件写 204 条。
- 最大的一组是 `scripts/tests/**`：148 个测试。测试内容规则分属 power/gpu/wifi 等线，但 porting 归属按“测试基础设施”记 `diagnostics`，owner 默认 `hygiene-agent`；其中 13 个 ADSP/handoff 测试按 `TREE-OWNERS.toml:139` 归 `adsp-handoff-agent`。
- `scripts/` 根 36 个必须拆：7 个 power 判读器、4 个 network、1 个 audio、1 个 input、1 个 display、1 个 ios27、21 个 diagnostics（其中 `sync-device-input.py` 归 adsp）。
- `drivers/PongWifi/**` 16 + `drivers/QcaBluetooth` 1 归 `network`；`blobs/**` 2 归 `firmware`；`CREDITS.md` 归 `ios27-arm64e`。

## 2. 目录 × area × owner

| 目录 / 模式 | 文件数 | 建议 area | 建议 owner | 依据 |
|---|---:|---|---|---|
| `scripts/tests/**` | 148 | `diagnostics` | `hygiene-agent` 135；`adsp-handoff-agent` 13 | 测试基础设施；13 个 ADSP/handoff 测试按 TREE-OWNERS 例外 |
| `scripts/` 根：power 判读器 | 7 | `power` | `charger-agent` | judge-handoff/mode1/sleep、record-hw-contracts、refresh-xnu-generic、render-eight-step-table、extract-boot-img |
| `scripts/` 根：diagnostics | 20 | `diagnostics` | `hygiene-agent` | 构建、飞行、仓库诊断脚本 |
| `scripts/` 根：ADSP 输入 | 1 | `diagnostics` | `adsp-handoff-agent` | `sync-device-input.py`（TREE-OWNERS:139） |
| `scripts/` 根：audio | 1 | `audio` | `adsp-handoff-agent` | `append-conffiles.py`，ADSP 生产 blob 的 conf 接线 |
| `scripts/` 根：network | 4 | `network` | `wifi-agent` 2；`bt-agent` 2 | `pong_paths.py`/`judge-z0.sh`；`gen-k60-bt-blob.py`/`make-bt-firmware-addon.py` |
| `scripts/` 根：input | 1 | `input` | `touch-agent` | `test-goodix-config.py` |
| `scripts/` 根：display | 1 | `display` | `display-agent` | `dyld-cache-index.py` |
| `scripts/` 根：ios27 | 1 | `ios27-arm64e` | `lead` | `pick-xnu-builder.sh` |
| `drivers/PongWifi/**` | 16 | `network` | `wifi-agent` | PongWifi 目录 |
| `drivers/QcaBluetooth` | 1 | `network` | `bt-agent` | BT 厂商目录；TREE-OWNERS 未显式加 scope |
| `blobs/**` | 2 | `firmware` | `springboard-agent` | init v10guard 及其 entitlements |
| `CREDITS.md` | 1 | `ios27-arm64e` | `lead` | 仓库级署名 |
| **合计** | **204** | | | |

owner 合计：`hygiene-agent` 155、`adsp-handoff-agent` 15、`charger-agent` 7、`wifi-agent` 18、`bt-agent` 3、`touch-agent` 1、`display-agent` 1、`lead` 2、`springboard-agent` 2。

## 3. 建议追加的 `porting.toml` pattern

下面是按 area 的追加内容；**本分支已应用**。现有 pattern 不动，只追加。

```toml
# diagnostics.paths +=
  "scripts/tests/**",
  "scripts/boot-and-capture.ps1",
  "scripts/capture-k60-usblog.ps1",
  "scripts/compact-wsl.cmd",
  "scripts/compact-wsl.ps1",
  "scripts/eight-step-gate.py",
  "scripts/flash.sh",
  "scripts/git-guard",
  "scripts/git-safe.sh",
  "scripts/judge-wallpaper-log.py",
  "scripts/k60-boot-lock.ps1",
  "scripts/k60-bus.py",
  "scripts/k60-capture-state.ps1",
  "scripts/k60-janitor.py",
  "scripts/pick-upstream.py",
  "scripts/porting-gate.py",
  "scripts/record-boot.py",
  "scripts/research-gate.py",
  "scripts/series-fingerprint.py",
  "scripts/snapshot-worktree.py",
  "scripts/sync-device-input.py",
  "scripts/watch-upstream.py",
# power.paths +=
  "scripts/extract-boot-img.py",
  "scripts/judge-k60-handoff-console.py",
  "scripts/judge-k60-mode1-console.py",
  "scripts/judge-k60-sleep-console.py",
  "scripts/record-hw-contracts.py",
  "scripts/refresh-xnu-generic.py",
  "scripts/render-eight-step-table.py",
# audio.paths +=
  "scripts/append-conffiles.py",
# network.paths +=
  "drivers/PongWifi/**",
  "drivers/QcaBluetooth",
  "scripts/gen-k60-bt-blob.py",
  "scripts/make-bt-firmware-addon.py",
  "scripts/pong_paths.py",
  "scripts/judge-z0.sh",
# input.paths +=
  "scripts/test-goodix-config.py",
# display.paths +=
  "scripts/dyld-cache-index.py",
# ios27-arm64e.paths +=
  "scripts/pick-xnu-builder.sh",
  "CREDITS.md",
# firmware.paths +=
  "blobs/**",
```

为什么用 `scripts/tests/**` 而不是把 148 个测试逐个登记：`check-porting-paths.py:53-77` 的 `*`/`**` 只按路径段匹配，测试目录新增文件不会改变 owner；逐个登记会每加一个测试就多一条维护项。

## 4. `scripts/tests` 的 last_scope 拆分

如果 Lead 要按“内容线”而不是“测试基础设施”分 owner，用这张表拆；总计 148。

| last_scope | 测试数 | 内容线建议 |
|---|---:|---|
| `power` | 36 | charger-agent |
| `gpu` | 23 | gpu-user-agent |
| `gate` | 17 | hygiene-agent |
| `(empty)` | 13 | hygiene-agent |
| `scripts` | 10 | hygiene-agent |
| `wifi` | 6 | wifi-agent |
| `touch` | 4 | touch-agent |
| `charger` | 4 | charger-agent |
| `adsp` | 4 | adsp-handoff-agent |
| `boot` | 3 | lead 复核 |
| `build` | 3 | lead 复核 |
| `battery` | 3 | charger-agent |
| `xnu` | 2 | lead 复核 |
| `gates` | 2 | lead 复核 |
| `engineering` | 2 | hygiene-agent |
| `bootimg` | 1 | lead 复核 |
| `pitfall` | 1 | lead 复核 |
| `data` | 1 | lead 复核 |
| `firmware` | 1 | lead 复核 |
| `probe` | 1 | charger-agent |
| `readme` | 1 | lead 复核 |
| `main` | 1 | lead 复核 |
| `flight-card` | 1 | lead 复核 |
| `userland` | 1 | springboard-agent |
| `bt` | 1 | bt-agent |
| `bus` | 1 | hygiene-agent |
| `smem` | 1 | adsp-handoff-agent |
| `rules` | 1 | lead 复核 |
| `ufs` | 1 | lead 复核 |
| `springboard` | 1 | springboard-agent |
| `sync` | 1 | adsp-handoff-agent |
| **合计** | **148** | |

## 5. 全量清单

204 行逐路径在 [`PORTING-OWNER-MAP.tsv`](PORTING-OWNER-MAP.tsv)。字段：`path`、`directory`、`last_commit`（99a711d9 的最后一次改动）、`last_scope`（该提交的 scope）、`area`、`owner`、`basis`。

## 6. 唯一的非未归属错误

- `cpu: evidence reference does not exist: drivers/armcpu-darwin24/ArmCpu.cpp`
- 位置：`porting.toml:76`（cpu evidence）与 `:65`（area）。这不是 pattern 能修的路径归属；要么恢复该文件，要么把 evidence 的 `reference` 换成一个存在的文件。本分支不改。

## 7. 自检

- 204/204 条路径唯一；用与 `scripts/check-porting-paths.py:53-77` 相同的 `*`/`**` 段匹配做 dry-run，41 条建议 pattern 命中全部 204 条。
- 41 条已应用，实测 `FAILED: 1 problem(s)`；唯一错误是 §6 的 cpu evidence 悬空引用。
- `porting.toml` 的修改仅限这 41 条 pattern，不新增 owner 登记，不碰 `E:/hackios/k60-gates`；提交纪律见 `docs/research/power/LANE-RULES.md` R-02。
