# BT-27 预飞判据（①–⑦）

状态：pre-boot（2026-11-22）。本页只给离线判据和已观测读数，不声称任何硬件已经通过。
范围：Redmi K60 / SM8475，iPadOS 27.0.1 24A446，QCA6490 over GENI UART。
约束：不构建、不 boot、不写共享树；命令从 `E:/hackios/xnekom-ios27` 运行。

## 1. 判据规则

每个硬件项的研究步 ①–⑦ 必须同时有：

1. **命令**：从仓库根可执行，不依赖人工判断；
2. **期望读数**：命令成功时必须出现的字符串；
3. **负例**：证明这条判据在坏输入上会红的测试；
4. **先例**：同 ABI 或同型的真实成功证据；没有就写 `无先例` 并停手；
5. **三级结论**：`有证据` / `有推断` / `不知道`，并写清阻塞。

机器可读源是 `docs/research/eight-step/bt-27.toml` 的
`[hardware.bluetooth.acceptance]`。本页的表由
`python3 scripts/check-bt-27-acceptance.py --markdown` 生成；不要手改表。

`--check` 只校验表形（7 行、字段齐全、结论枚举、`无先例` 必须带 `stop`、
`不知道` 必须带 `blocked`）。`--run` 才真正执行命令；它按当前主机的
解释器运行，所以 ③ 必须在 WSL/Linux 跑，不能把 Windows 的
`no C compiler` 当成 ③ 红。

## 2. 七步判据

| 步 | 判据（命令） | 期望读数 | 实测读数 | 负例自测 | 先例 | 结论 | 阻塞 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ① 同型 | `grep -n -A12 QcaBluetooth E:/hackios/UniXNU/components.toml` | verified_devices = ["sheng"] | verified_devices = ["sheng"]; no mondrian entry | `python3 scripts/tests/test-bt-27-acceptance.py` | E:/hackios/UniXNU/components.toml:505 | 有推断 | no same-model 27 implementation; this row is an inventory reading, not a hardware test |
| ② 官方 | `python3 scripts/check-bluetooth-dt.py && python3 scripts/check-bluetooth-power.py --source "E:/hackios/UniXNU/out/mondrian/ios-27.0.1-24A446/mondrian_ios27/tree/.cache/xnu-work/bsd/dev/qbt_k60.c"` | bluetooth-power: OK (22 check(s)) | bluetooth-dt-check: OK (0 failure(s)); bluetooth-power: OK (22 check(s)) | `python3 scripts/tests/test-bt-0524-dt-node.py && python3 scripts/tests/test-bt-power-check.py` | E:/hackios/UniXNU-sheng/dts/sheng.dts:17-23 | 有推断 | the sheng node is wcn7850-bt at 3.2 Mbaud; the K60 node is wcn6855-bt at 3.0 Mbaud, so the transport values are inferred, not copied |
| ③ 反编译 | `python3 scripts/check-bluetooth-geni.py && python3 scripts/check-bluetooth-gic.py` | bluetooth-geni-check: OK (64 assertion(s), 36 register(s)) | geni 64 assertions/36 registers; gic 43 assertions/16 writes | `python3 scripts/tests/test-bt-geni-model.py && python3 scripts/tests/test-bt-gic-shared.py` | E:/hackios/UniXNU/components.toml:493-508 | 有推断 | the Windows host has no C compiler; the command was run under WSL Ubuntu-24.04 |
| ④ 广域 | `python3 scripts/check-bluetooth-data-gate-chain.py && python3 scripts/check-bluetooth-addon-prefixes.py` | bluetooth-addon-prefixes: OK | data-gate-chain: OK; addon-prefixes: OK (bluetooth-bin, bluetooth-lib; xpc SKIP) | `python3 scripts/tests/test-bt-data-gate-chain.py && python3 scripts/tests/test-bt-addon-prefixes.py` | E:/hackios/UniXNU-sheng/board.toml:66 | 有推断 | the xpc mount is not checked out, so the addon prefix check skips it |
| ⑤ 计划 | `python3 scripts/check-bluetooth-runtime-gate.py` | bluetooth-runtime-gate: OK | series 30 entries, mounts 0526/0527; defconfig CONFIG_XNU_OWNER_DATA_MOUNT=absent; state gated-off | `python3 scripts/tests/test-bt-runtime-gate.py` | E:/hackios/UniXNU-sheng/board.toml:68-84 | 有推断 | the runtime mounts are compiled out; this is a stage-0 boundary, not a runtime pass |
| ⑥ 深入 | `python3 scripts/check-bluetooth-kernel.py --kernel "E:/hackios/ci-artifacts/44518998961/ext/mondrian/ios-27.0.1-24A446/mondrian_ios27/kernel/kernel.macho"` | bluetooth-kernel-check: OK (0 failure(s)) | bluetooth-kernel-check: OK (0 failure(s)) on 93,077,504 B CI kernel sha256 4e57f1822d352022b2a825f93ac41d653a149c63872a6cca8e42d505a0bb9f86 | `python3 scripts/tests/test-bt-kernel-check.py` | E:/hackios/UniXNU/components.toml:493-508 | 有推断 | the CI kernel is not 24A446 and its head 33f5229 is not an ancestor of this branch |
| ⑦ 核验 | `python3 scripts/check-bluetooth-userspace.py --stage "E:/hackios/k60-bt-work/bt24/stage"` | bluetooth-userspace-check: OK | FAILED (1): BlueTool links /usr/lib/libSystem.B.dylib, not libxpc | `python3 scripts/tests/test-bt-userspace-check.py` | E:/hackios/UniXNU-sheng/board.toml:68-84 | 不知道 | the historical stage is red on the libxpc assertion; ⑦ is not green |

## 3. 负例自测（dry-run）

### 3.1 判据阅读器

`python3 scripts/tests/test-bt-27-acceptance.py` 有 8 个 case，当前 8/8 通过：

- 完整 7 行表：`--check` rc0；
- 删掉 `same_model.expect`：rc1，错误点名 `same_model.expect`；
- `plan.conclusion = "确定"`：rc1，错误点名 `plan.conclusion`；
- `wide.precedent = "无先例"` 但不设 `stop`：rc1，错误点名 `wide.stop`；
- 删掉整个 `verify` 表：rc1，错误点名 `verify`；
- `--run --only same_model` 且期望值匹配：rc0；
- `--run --only same_model` 且期望值改为 `999`：rc1；
- `--markdown`：输出表头、命令和结论。

### 3.2 真实 checker 的负例

在 WSL Ubuntu-24.04（`/usr/bin/clang`、`/usr/bin/clang++`）下，
12 个 `scripts/tests/test-bt-*` 文件全部 rc0：

- `test-bt-userspace-stage` 12 case；
- `test-bt-0524-dt-node` 15 case；
- `test-bt-userspace-check` OK；
- `test-bt-geni-model` 26 case；
- `test-bt-gic-shared` 20 case；
- `test-bt-power-check` 18 case；
- `test-bt-kernel-check` OK；
- `test-bt-runtime-gate` 13 case；
- `test-bt-addon-prefixes` 10 case；
- `test-bt-launchd-cache` 10 case；
- `test-bt-payload-host` 12 case；
- `test-bt-data-gate-chain` OK。

Windows 主机在 ③ 缺 C 编译器，在 launchd/payload-host 缺 framework/Mach-O 探针；
这些是主机限制，不是判据红。相反，④ 的 addon 检查原先在
Windows 用默认 GBK 读 UTF-8 补丁，非 ASCII 补丁会 `UnicodeDecodeError`。
已把 `scripts/check-bluetooth-addon-prefixes.py` 的三处 `read_text()` 改成
`encoding='utf-8'`，并加了一个 UTF-8 回归 case（10 case 通过）。这条修复本身就是“判据在坏输入上真会红”的实例。

### 3.3 ⑦ 是真实红，不是主机限制

`python3 scripts/check-bluetooth-userspace.py --stage E:/hackios/k60-bt-work/bt24/stage`
在 11 个 PASS 后报：

```text
FAIL BlueTool links libxpc /usr/lib/libSystem.B.dylib
bluetooth-userspace-check: FAILED (1)
```

同目录的 `check-bluetooth-launchd.py` 报 `bluetooth-launchd: OK`，说明红点是
BlueTool 的 `libxpc` 链接断言，不是 stage 目录缺失或 Windows 探针失败。

## 4. 三级结论

| 级别 | 能说到哪 | 证据 |
| --- | --- | --- |
| 有证据 | sheng 的 QcaBluetooth 组件与 DT 节点是 27 ABI 的真实先例；本机 DT、power、GENI、GIC、data-gate、runtime-gate、kernel 的 checker 都能复现其记录的绿读数（runtime-gate 是 gated-off） | `UniXNU/components.toml:493-508`；`UniXNU-sheng/dts/sheng.dts:17-23`；`UniXNU-sheng/board.toml:66,68-84` |
| 有推断 | K60 的 SE20 `0x894000`、IRQ 587、GPIO 79/208、3.0 Mbaud、`qcom,wcn6855-bt` 来自本地 DT 和 0500–0523 补丁，不是一次 27 启动的观测 | `dts/mondrian.dts:109-116`；`qbt_k60.c`；`bt-27.toml` 的 ①–⑥ evidence |
| 不知道 | 24A446 BlueTool 的 `libxpc`、bluetoothd 的 MobileGestalt 依赖、`payload.runtime` 挂载后的真实行为；没有 24A446 payload 或启动日志 | ⑦ `FAILED (1)`；⑤ `state: gated-off`；⑥ 的 CI kernel 不是 24A446 |

## 5. 停止条件

- **⑦ 红**：在正确的 24A446 BlueTool / bluetoothd stage 出现前，不得把 ⑦ 标绿；
  也不得用 ⑤ 的 `gated-off` 或 ⑥ 的 CI kernel 替代。
- **⑤ 不是 runtime pass**：`bluetooth-runtime-gate: OK` 只证明 series 里有
  `0526`/`0527` 且 `CONFIG_XNU_OWNER_DATA_MOUNT` 关闭。
- **⑥ 不是 24A446**：CI kernel 93,077,504 B / sha256 `4e57f182…`，且 head
  `33f5229` 不是本分支祖先。
- **① 不是同型通过**：`verified_devices = ["sheng"]` 证明只有 sheng；没有 K60
  27 实现。sheng 是 WCN7850 / 3.2 Mbaud，K60 是 WCN6855 / 3.0 Mbaud，不能直接抄。
- **本任务不构建、不 boot**：没有 24A446 payload，也没有 stage-0 SpringBoard。

## 6. 复现

```sh
cd E:/hackios/xnekom-ios27
python3 scripts/check-bt-27-acceptance.py                 # 表形校验，7 步
python3 scripts/check-bt-27-acceptance.py --markdown      # 生成本页的表
python3 scripts/tests/test-bt-27-acceptance.py            # 8 case
```

静态判据（Windows 主机）：

```sh
python3 scripts/check-bt-27-acceptance.py --run --only same_model,official,wide,plan,deep
```

③ 必须在 WSL/Linux 跑（Windows 没有 C 编译器）：

```sh
wsl.exe -d Ubuntu-24.04 -- bash -lc "cd /mnt/e/hackios/xnekom-ios27 && python3 scripts/check-bt-27-acceptance.py --run --only decompile"
```

⑦ 的当前预期是 rc1；这是已记录的阻塞，不是脚本坏了：

```sh
python3 scripts/check-bt-27-acceptance.py --run --only verify   # expected rc1
```

## 7. 边界

本页只回答“起飞前有没有可执行判据、负例是否真会红、先例在哪”。
它不回答“K60 的蓝牙已经能工作”：⑦ 仍红，`status = parked`，
且没有任何硬件已验证的记录。下一步需要 24A446 的 BlueTool / bluetoothd
stage，或 Lead 明确放行的 F3/首次 27 镜像。
