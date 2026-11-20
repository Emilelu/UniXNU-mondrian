# W11 只读模式 1 飞行包

日期：2026-11-21。对象：已经构建、尚未上机的 w11 镜像。目的：拿到就能飞，飞完能判，判完知道是否重飞。

> **先看边界。** w11 是 iOS 16.6.1 树上构建的 mode-1 A 镜像，不是 iOS 27 镜像，不消费 F1 的 27 预链接，也不验证 27 stage-0。若这次 slot 是给 iOS 27 的，停止，本包不适用。w11 的 `boot.json` 仍是 `hardware_tested=false`，截至本页没有任何真机读数。

## 1. 这一飞回答什么

只回答一件事：当前 `K60CpuFreqProbe` 的 **mode 1 只读 late read** 在真机上是否成立，并且系统是否仍能走到 SpringBoard。

具体是：

- 启动后先打一次 early read，电池 `begin` 成功后 5 s 再打一次 `late read begin (mode 1)` / `late read end`；
- late read 里 d0/d1/d2 都是 `enable=1`，`state != 0`，`rows/top/level` 自洽，`cap` 在 `1..top`；
- L3 的 `rows=15`；
- 整份日志没有 mode 2/3/6/7/8/10 的写行；
- 最后有 launchd 的 SpringBoard 行。

这一飞**不**回答：EPSS 写入、电压/互连/温控顺序、GPU 帧下限、ADSP handoff、PMIC 订阅、iOS 27 的 bsd_init 之后。mode 1 不写任何寄存器，所以它通过也不代表写路径安全；它失败也不代表 EPSS 不能写。

## 2. 镜像身份

| 项 | 值 |
|---|---|
| 路径 | `E:/k60-work/artifacts/power-conformance-20261119w11/boot.img` |
| 大小 | 201,887,744 B |
| boot.img sha256 | `6db4e6b78bdab557d4f34b17aaf6a25caa9990d564faf94ef18853fbde589844` |
| 内核槽 | 551,032 B，sha256 `00c466e5e7cf470cc037ccaefe30b8d9a2a374e37640417c800dbd264a8d2be4` |
| payload | 201,326,592 B @557056，sha256 `bd8ed29dd420be2829d68f9b3887b29976a3b0b3f79a3bf1c9dd40bc0cf2e63f` |
| payload 内 kernel.macho | 129,146,880 B，sha256 `30a058f274b3c4cbcfc88515ef4bbf6ef45adf47124af16aa0a54966b9345a90` |
| kernel.macho.adt | 16,132 B，sha256 `721fb484eb01800b5e1e0a94bb47db1edbdaf636d53ecdcff83659caa2be3853` |
| 参数 | 30 项，601 B，含 `k60_cpufreq=1`，不含 `applog=1` |

这些数字**只凭归档的那一张 boot.img 就能重算**，不需要旁边还有 kernel.macho。起飞前跑一次：

```sh
cd /mnt/e/hackios/k60-charger
sha256sum /mnt/e/k60-work/artifacts/power-conformance-20261119w11/boot.img
python3 scripts/extract-boot-img.py --img /mnt/e/k60-work/artifacts/power-conformance-20261119w11/boot.img
```

第二行必须打出 201,887,744 / `6db4e6b7…`、内核槽 551,032 / `00c466e5…`、payload `bd8ed29d…`、kernel.macho `30a058f2…`。对不上就不飞，先换回正确归档。

**不要给这个镜像加参数。** 601 B 是当前 board 契约去掉 `applog=1` 后的只读 A 形状；再加 `pong_handoff_publish=1` 会变成 31 项 624 B，超过 DarwinBoot 的 607 B 上限。mode 1 只读不需要 handoff，缺它不是缺陷。

## 3. 前置条件

### 3.1 主仓 blocker

先分清两件事：

- **F1 的 150 个未决地址不阻塞 w11。** F1 只阻塞 iOS 27 图像；w11 是 iOS 16 图像。若 Lead 的飞行策略是“F1 出图前不飞任何镜像”，那 w11 是被**排程**挡住，不是被产物挡住。
- **w11 也不要求 PMIC/handoff 那一串 C0/C1 先绿。** mode 1 在电池 `begin` 后读 EPSS，不订阅 PMIC，不发布 handoff。把 P-01..P-08 当成本飞的前置会把两件事混在一起。

起飞时主仓必须满足：

| 检查 | 现在的状态 | 说明 |
|---|---|---|
| 树干净、与 origin 平齐 | 本行要求 | `git status --porcelain` 空；本分支 `feat/power-ios27-branch` |
| `eight-step-gate.py --flash` | ✅ 9 个 active 项、72 项检查 | flash 模式永远整机，`K60_EIGHT_STEP_ITEMS` 不参与 |
| `check-boot-procedure.py` | ✅ 通过 | 串口先武装、supervisor 在 claim 内重启、无 `fastboot flash` |
| `porting-gate.py --quick` | 起飞时由 flash.sh 重跑 | 红了就不启动；在 WSL 里跑，Windows GBK 控制台可能在打印 ✅ 时崩，不能把崩溃当通过 |
| `research-gate.py` | 起飞时由 flash.sh 重跑 | 同上 |
| `check-tree-owner.py` | `charger-agent` | 共享树不是本线，不能写 `E:/hackios/k60-gates` |

设备侧：

- 序列号 `6033dbec`；
- 机器级 boot claim 空闲，没有别的 agent 正在飞；
- `K60_AGENT_ID=lead`（Lead 是唯一有权碰设备的人；本包不由本线执行）；
- 串口采集由 supervisor 在 boot 前武装；不要手工先开串口。

起飞前按顺序看：

```sh
cd /mnt/e/hackios/k60-charger
K60_AGENT_ID=lead bash scripts/k60-device.sh state
powershell.exe -NoProfile -File E:/k60-work/scratch/list-boot-watchers.ps1
```

第一条输出 `adb`、`fastboot` 或 `none`。`none` 不一定是没连上：可能是另一个 agent 正在重启，交给 supervisor 判；不要在这时自己 `adb reboot`。第二条必须打印 `no watchers`；出现任何 `WATCHER …` 就等，不要抢。

### 3.2 本线证据

| 检查 | 命令 | 期望 |
|---|---|---|
| 判读器夹具 | `python3 scripts/tests/test-judge-k60-mode1-console.py` | `TESTS OK 14 cases, 0 failures` |
| 参数审计 | `python3 scripts/check-image-args.py --image … --board /mnt/e/k60-work/scratch/board.toml.mode1.probe` | `image-arg-audit: OK (30 arguments, 601 bytes)` |
| 镜像重算 | `python3 scripts/extract-boot-img.py --img …` | 第 2 节的四个哈希全对；工具自带 30 项用例 |
| 控制台契约 | `python3 scripts/check-console-contract.py` | 31 条已判、8 条豁免，0 红 |
| 电源计数 | `python3 scripts/check-power-counts.py` | 10 C / 1915 项、23 Python 套件、36 契约行 |
| 八步逐条 | `python3 scripts/eight-step-gate.py --flash` | 9 个 active、72 项通过 |

参数审计需要 `mtype`，在 WSL 里跑；Windows 原生会报 `mtype not found (install mtools)`。这不是镜像错。

## 4. 预测原文

**当前 `EIGHT-STEPS.toml` 没有 `power` 或 `cpu` 这个键。** 现有键是 touch、gpu、storage、display、brightness、bootchain、buttons、bluetooth、wifi、audio、battery、charger、usb、thermal、cellular、springboard。所以今天没有一个合法的 `[hardware.<key>.step.device.prediction]` 可以“直接抄进去”；硬抄到 `gpu` 会把 GPU 的判据改掉，硬写 `K60_EIGHT_STEP_ITEMS=power` 会被门禁按“不存在的硬件项”拒绝。

若 Lead 决定新增 `[hardware.power]`，下面两行是原文；只有先补齐该键的七步（或先把它记成 `status = "planned"`，planned 不参与 flash 门禁）再贴，否则会制造一个空 active 项，flash 门禁反而变红。

```toml
# 目标表头（当前不存在）：
# [hardware.power.step.device.prediction]
success = "`K60CpuFreq: mode=1 EPSS domains=3 cpus=8 lut-rows=40` 出现，`late read begin (mode 1)` 到 `late read end` 之间 d0/d1/d2 各有一条 `mode1=read-only`，enable=1、state≠0、rows>0、top>0、level<rows、cap∈[1,top]；L3 行 rows=15 且 level<15；全日志无 mode2/3/6/7/8/10 的 apply/vote/pdmem/restore 写行；capture.json complete=true、bytes 与 console.log 一致、panicMarker=null；有 launchd SpringBoard 行；judge-k60-mode1-console.py 退出 0"
failure = "`k60-mode1: FAIL` 或 `k60-mode1: INVALID`；先看 `MODE1 : FAIL` 的 `no 'mode=1 EPSS domains=3 cpus=8 lut-rows=40' header`、`d1 enable=0`、`d1 is enabled but state=0`、`L3 rows=... expected 15`、`write line ...`，或 `CAPTURE : FAIL` 的 `panicMarker=...`、`bytes ... but console.log ...`、`capture state is port-not-observed`；judge 退出 1 或 2"
```

`K60_EIGHT_STEP_ITEMS` 的实际取值：

- **本飞不设置（空）**。镜像是预构建的，flash 门禁永远整机；这个变量只收窄 build 模式，不改变 flash 范围。
- 如果同一会话要重建 GPU 镜像，取值是 `K60_EIGHT_STEP_ITEMS=gpu`，不是 `power`。
- 不存在 `power` 这个项；写了会直接报“不存在的硬件项”。

## 5. 起飞

只有 Lead 执行。前置全绿后：

```sh
cd /mnt/e/hackios/k60-charger
export K60_AGENT_ID=lead
bash scripts/flash.sh /mnt/e/k60-work/artifacts/power-conformance-20261119w11/boot.img 300
```

- 300 s 是为了覆盖日志里的 300 s autoreset；late read 在电池 begin 后 5 s 就出现，SpringBoard 通常在更早的行，300 s 不会漏掉判据。
- `flash.sh` 会在 claim 内自己把设备从 adb 重启到 fastboot；不要先手工重启。
- 它先跑 porting / 八步（flash）/ 启动流程 / 研究四个门禁，任一红就退出，boot 不会发出。
- 证据目录由脚本打印：`E:\k60-work\evidence\usblog-<YYYYMMDD-HHMMSS>\`。
- 退出码：0 抓取完整；1 监督失败；2 零字节/端口未出现；3 串口被另一个抓取占用；4 截断/断线；5 设备自己回到 fastboot（可能 panic 复位）；6 另一个 agent 持有 boot claim；7 未设 `K60_AGENT_ID`。

## 6. 判读

```sh
cd /mnt/e/hackios/k60-charger
OUT=/mnt/e/k60-work/evidence/usblog-YYYYMMDD-HHMMSS
python3 scripts/judge-k60-mode1-console.py "$OUT" > "$OUT/judge.txt" 2>&1
rc=$?
cat "$OUT/judge.txt"
echo "judge rc=$rc"
```

退出码：

| rc | 含义 |
|---|---|
| 0 | PASS：CAPTURE、MODE1、SPRINGBOARD 全 PASS |
| 1 | FAIL：至少一个判据 FAIL（含 panicMarker、write line、d1 enable=0、L3 rows≠15、无 SpringBoard） |
| 2 | INVALID：没有 FAIL，但 capture.json 缺失/不可读，无法证明抓取完整 |
| 4 | 用法错：参数、路径或 target 不对，不是判据结论 |

判读器有一条容易误读的优先级：**只要有一个 FAIL，总判就是 FAIL，即使 capture.json 也缺失**。所以看到 rc=1 不要立刻说“抓取坏了”；先看 `CAPTURE :` 那一段。反过来，只有“没有 FAIL 且 CAPTURE 无法证明”才是 rc=2。

输出形状（旧 mode 8 日志的实例，只作格式参考）：

```text
k60-mode1: FAIL (mode-1 A) (console.log, 165881 bytes on disk) [exit 1]
CAPTURE : PASS (evidence none)
  - complete=true bytes=165881 panicMarker=null
MODE1 : FAIL (evidence none)
  - no 'mode=1 EPSS domains=3 cpus=8 lut-rows=40' header
SPRINGBOARD : PASS (evidence :1116)
  - SpringBoard launch line present
TOTAL: 2 PASS / 1 FAIL / 0 INVALID
```

w11 的正常 PASS 应出现：`mode=1 EPSS …` 头、`late read begin (mode 1)`、d0/d1/d2 三条 `mode1=read-only`、L3 一条、`late read end`，以及 `judge rc=0`。d1/d2 的 early read 仍可能是 `enable=0`，判读器故意忽略它；只看 late read。

## 7. 证据目录

`flash.sh` 产出的目录就是证据，不要事后改名或覆盖。至少应有：

| 文件 | 证明什么 |
|---|---|
| `boot.json` | `image`、`imageSha256`、`bootAccepted`、`bootExitCode`、`returnedToFastboot`、`error` |
| `capture.json` | `state`、`complete`、`bytes`、`logSha256`、`panicMarker`、`stopReason`、`reopenCount` |
| `console.log` | 主证据：mode 1 行、late read、SpringBoard |
| `fastboot.log` | `Booting OKAY`；fastboot 的退出码不可靠时以文本为准 |
| `capture.ready` | 串口在 boot 前已武装 |
| `collector.stdout.log` / `collector.stderr.log` | 端口重开、COM 号、读线程错误 |
| `capture-events.jsonl` | 打开/关闭/停止的时间线 |
| `judge.txt` | 本页第 6 节的判读输出，由 Lead 追加 |

先做三个硬核对，再看判据：

1. `boot.json.imageSha256` 必须等于 `6db4e6b7…`；不等 = 飞错镜像，INVALID。
2. `capture.json.bytes` 必须等于 `console.log` 的实际字节数；不等 = 抓取不完整，INVALID。
3. `capture.json.panicMarker` 必须为空；非空 = 镜像失败，FAILED，不是 INVALID。

## 8. 什么时候这一飞不成立（INVALID），什么时候是 FAILED

先判“这一飞算不算数”，再抄判读器的结论。两者不是同一层：

- **INVALID / 不成立**：镜像没有得到一次公平的运行，或抓取无法证明完整。不能写 A PASS，也不能写 A FAIL；修一个采集条件后可以用同一张镜像重飞。
- **FAILED**：镜像跑起来了、抓取完整，判据不成立。不能原样重飞；要改一个变量、重出镜像。

| 现象 | 结论 | 处理 |
|---|---|---|
| `Booting OKAY` 没出现 / supervisor rc=2（零字节） | INVALID | 查 COM、DTR、capture.ready；同镜像重飞 |
| supervisor rc=3（串口被占）或 rc=6（claim 被占） | INVALID | 等占用者结束；boot 没发出，同镜像重飞 |
| supervisor rc=7（未设 actor） | INVALID | 设 `K60_AGENT_ID=lead` 再走 |
| 设备在 boot 前被人工复位，或 rc=5 但日志没有 panic、没有 A 证据 | INVALID | 记录原因；同镜像重飞 |
| 日志截断在 `late read end` 之前 / `capture.json complete=false` | INVALID | 加大秒数、修端口；同镜像重飞 |
| `capture.json` 缺失/不可读，且 MODE1 没有 FAIL（judge rc=2） | INVALID | 修采集；同镜像重飞 |
| 判读器 rc=1，且 `MODE1 : FAIL`（无头、d1 enable=0、state=0、L3≠15、write line） | FAILED | 不改镜像不重飞；先查探针是否真的链入、boot arg 是否真的是 1 |
| 判读器 rc=1，`CAPTURE : FAIL panicMarker=…` | FAILED | 这是镜像 panic，不是采集错；回滚相关改动 |
| `SPRINGBOARD : FAIL`，其余 PASS | FAILED | 读到了 EPSS 但系统没到 UI；按启动问题查 |
| judge rc=4 | 没有判据结论 | 修命令/路径，不登记为 FAILED 或 INVALID |

两个常见误判：

- **把截断当 FAILED。** 判读器确实会把 `complete=false` 记成 CAPTURE FAIL 并返回 1，但这不是“d1 坏了”，是这次采集没跑完。先按 INVALID 处理，修采集后重飞。
- **把 panic 当 INVALID。** `panicMarker` 非空是 CAPTURE FAIL、judge rc=1；这是镜像失败，不是串口问题。不要用“再飞一次”掩盖。

重飞条件：

- INVALID：同镜像、同哈希、无 panic，允许重飞；每次换一个新的证据目录，并在目录里留一行“上次为什么不算数”。只改一个条件（秒数、端口、占用者），不要同时改镜像和采集。
- FAILED：同一张镜像不再重飞；改一个变量（探针选择、boot arg、代码）后重出镜像，重新过参数审计和判读器夹具。出现 panic 时先回滚到上一个可启动镜像，不为一条日志冒第二次启动风险。
- 哈希不等 / 镜像不是 6db4e6b7…：不是 INVALID，也不是 FAILED，是**飞错了对象**；停止，换回归档。

## 9. 飞完之后

- 证据留在 `E:/k60-work/evidence/usblog-<stamp>/`，不要搬进仓库；仓库只记结论、镜像哈希和证据目录名。
- 在 `docs/research/power/01-EPSS-PROBE.md` 的 w11 条目后补一行：日期、judge 总判、`console.log` 行号、证据目录。不要写当前时刻、会话 id 或 fastboot 过程。
- 若判 PASS：w11 从“未上机”变为“A 已验证”；这只证明只读 late read 和 SpringBoard，不证明写入、电压、温控或 27。
- 若判 FAILED：把 `MODE1 : FAIL` 的第一条 note 原文抄进 probe 页，不要只写“读不到”。
- 若判 INVALID：只记录“这一飞不算数”和修复的采集条件；不要把 w11 标成失败镜像。

## 10. 出处

- w11 身份与构建记录：`docs/research/power/01-EPSS-PROBE.md:536-564`。
- 判读器：`scripts/judge-k60-mode1-console.py`；夹具 `scripts/tests/test-judge-k60-mode1-console.py`。
- 参数审计：`scripts/check-image-args.py`；探针 board 快照 `E:/k60-work/scratch/board.toml.mode1.probe`。
- 镜像重算：`scripts/extract-boot-img.py`（不依赖 mtools，Windows/WSL 同结果）。
- 飞行入口：`scripts/flash.sh`、`scripts/boot-and-capture.ps1`、`scripts/k60-boot-lock.ps1`。
- 同类飞行卡写法：`docs/research/gpu/FLIGHT-CARD-20261119i.md`（有效性先于判据、INVALID 可同镜像重飞）。
- 探针上机前清单的原则：`docs/research/charger/ARM64E-PROBE.md` §9（缺格式串是 build，不是硬件不支持）。
