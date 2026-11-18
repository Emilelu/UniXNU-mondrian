# 飞行卡 `gpu-import-scope2-20261118`

判据在镜像之前写死。本卡只回答一个问题：**16.8 ms 的 `presenter->present()` 由哪一段构成。**

上一飞（`FLIGHT-CARD-20261118j.md`）失败于 P-233 —— 报告行每 60 帧一条，而飞行只有 ~22 帧，
所以判据看不到任何样本。本卡唯一的镜像改动是把采样节奏改成「前 8 帧每帧一条、之后每 10 帧一条」，
判据本身与 j 卡相同，只是把「每 60 帧一条」改成了新节奏，并删掉了依赖条数的隐含假设。

## 1. 前置证据

| # | 前提 | 证据 |
|---|---|---|
| P1 | 采样节奏已改并受测试约束 | `scripts/tests/test-frame-stage-timing.py`：7 例，含 `if(copies<=8 \|\| !(copies%10))` |
| P2 | 阶段拆分与计时算术仍受测试约束 | `scripts/tests/test-present-stage-split.py` 17 例、`scripts/tests/test-scanout-timing.py` 11 例全部执行通过 |
| P3 | 不跨帧持有导入 | `scripts/tests/test-presenter-import-scope.py` 13 例 |
| P4 | 内核侧未改 | 本轮 `git diff` 只有 `drivers/PongMetal/PongMetalScanout.h` 与其两个测试 |
| P5 | 上一飞证明新插件在机上且无异常 | `evidence/usblog-20261118-161936`：4 条新格式串在镜像内核里、`K60KEXC` 0、`actual GPU scanout copy completed` 2 次 |
| P6 | 插件由当前源码重编 | 构建日志 `BUILD_EXIT=0` 与 bundle sha256 记入本轮提交 |
| P7 | 上一飞的内核侧数字复现 | 同证据 `PONG SCANOUT: frame=2..4 offer_and_copy=22569/35481/18364 us`、`prepare=4..19 us` |

## 2. 镜像

- tag `gpu-import-scope2-20261118`
- 唯一行为差异：`PongMetalScanout.h` 的报告采样节奏（判据可读性），不改帧路径本身
- 插件、桥接库、Turnip 库与上一张相同（不重编 Turnip）

## 3. 抓取

- 命令：`scripts/flash.sh <boot.img> 240`，证据落 `E:/k60-work/evidence/usblog-<ts>/`
- 只看 `console.log`；`capture.json` 的 `complete` 必须为真
- 新节奏下前 8 帧每帧一条、之后每 10 帧一条；至少有 2 条样本才算有效

## 4. 判据

**S1** `K60KEXC` 命中 0，且 `K60PANIC: ring kept` / `Debugger called` / `initproc exited` 均为 0。
**S2** 至少 2 条 `scanout frames=` 报告行（节奏修好后这是必然，除非没出帧）。
**S3** 每条报告行都含 `imports=`、`import=`、`encode=`、`submit=`、`gpu=`、`sum=` 六个字段，
且行尾是 `sum=<n> us`（`grep -a "sum=[0-9]* us$"` 命中数 == 报告行数）。
**S4** 每条报告行 `imports` == `frames`（没有跨帧复用导入）。
**S5** 末条 `import=` 占同段 `copy` ≤ 25%。
**S6** 末条 `sum` 与同段 `copy` 相差 ≤ 30%。
**S7** `crashed: backboardd` 为 0。
**S8** 末条 `copy` 与上一飞同量级（≤ 40,000 µs），即采样节奏改动没有拖慢帧路径。

## 5. 失败规则

**F1** `K60KEXC` > 0 ⇒ 立即回退上一张可启动镜像并重新审计，不再追帧率。
**F2** `scanout frames=` 仍为 0 条 ⇒ 采样节奏修改没有进镜像（查 bundle sha256 与
`K60METAL deploy files=`），本飞无结论。
**F3** 报告行缺 `sum=` 行尾或与下一条记录连成一行 ⇒ `report()` 的缓冲区/换行修复没进镜像。
**F4** 任意 `imports` < `frames` ⇒ 导入被跨帧复用，按 use-after-unmap 风险立即停飞。
**F5** `sum` 与 `copy` 稳定偏差 > 30% ⇒ 两侧记的不是同一段，不得据此归因；先把 `done`
拆成「交给内核」与「内核返回」。
**F6** 末条 `gpu` ≥ 0.8 × `sum` ⇒ 成本是 GPU 搬运本身 ⇒ 转 Turnip 渲染模式
（`PongMetalPlugin.mm` 的 `setenv("TU_DEBUG","sysmem,nocb",0)` 与官方默认 `gmem,nocb` 相反）。
**F7** 末条 `encode` + `submit` ≥ 0.6 × `sum` ⇒ 成本是每帧命令提交固定开销 ⇒ 转批量/复用策略。
**F8** `capture.json` 的 `complete` 为假或 `crashed: backboardd` > 0 ⇒ 本飞作废，重飞同一张镜像。

## 6. 结果登记

（判决在出帧后填写，不在镜像之前填。）
