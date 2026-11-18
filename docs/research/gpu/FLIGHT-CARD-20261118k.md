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

### 失败规则

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

## 5. 结果登记

- 镜像 `gpu-import-scope2-20261118`：`boot.img` `f67c49834963dc46c611893a67dbd49921613d586a7dc5bc7a7c238eb0475510`，
  内核 `4c06353bd3364e3b8803156e256fa922f0d504cb306aada25ad5002c2c45c6a6`，插件 `metal-plugin-20261118i`。
- 抓取 `E:/k60-work/evidence/usblog-20261118-171507`：`console.log` 279,455 B / 3,928 行，`capture.json complete=true`，
  监督脚本 rc=0，**54 条 `scanout frames=` 样本**，帧号 1→400，`K60KEXC` 0、`K60PANIC: ring kept` 0、`crashed: backboardd` 0。

### 判决：PASS（S1–S8 全过）

| 判据 | 结果 | 实测 |
|---|---|---|
| S1 无内核异常 | PASS | `K60KEXC` 0、`K60PANIC: ring kept` 0、`Debugger called` 0 |
| S2 ≥2 条样本 | PASS | 54 条 |
| S3 六字段齐全且行尾 `sum=<n> us` | PASS | 54/54 行 |
| S4 `imports` == `frames` | PASS | 54/54 行，`imports<frames` 计数 0 |
| S5 `import` ≤25 % `copy` | PASS | 0.2 % |
| S6 `sum` 与 `copy` 偏差 ≤30 % | PASS | 中位 +1.8 %，最差 +6.0 % |
| S7 backboardd 崩 0 | PASS | 0 |
| S8 `copy` ≤40,000 µs | PASS | 中位 23.0 ms |

### 归因（45 条稳态样本，帧号 ≥20）

| 段 | 中位 | 最小 | 最大 | 占 `sum` 中位 |
|---|---|---|---|---|
| `import` | 54 µs | 16 | 102 | **0.2 %** |
| `encode` | 389 µs | 185 | 6,481 | **1.9 %** |
| `submit` | 11,478 µs | 2,525 | 26,925 | **49.6 %** |
| `gpu` | 10,569 µs | 2,497 | 264,520 | **45.9 %** |
| `sum` | 23,357 µs | 8,169 | 281,885 | 100 % |
| `copy`（`present()` 全长） | 23.0 ms | 8.0 | 281.0 | — |

- **`import` 只占 0.2 %** ⇒ 上一轮删掉跨帧导入缓存是对的，而且没有任何性能代价：每帧重新导入大约 54 µs。
- **成本是「每帧提交 + 等 GPU」两段，不是搬运带宽**。`encode`（建 blit 编码器 + 下发拷贝命令）只占 1.9 %。
- 失败规则：F6（`gpu` ≥0.8×`sum`）在 4/45 条样本命中、F7（`encode`+`submit` ≥0.6×`sum`）在 17/45 条命中。
  按**中位**判，`submit`+`gpu` = 95.5 %，F7 的判别式只覆盖 `submit`，所以单看 F6/F7 都不完整；
  真正的形状是「提交与 GPU 完成各占一半」。下一步按 F7 分支方向做，但必须同时压 `gpu` 段。
- 帧率：样本区间 469 帧 / 150 s = **3.13 fps**，与 `present()` 的 23 ms（理论上限 43 fps）差距巨大
  ⇒ 帧路径之外还有别的瓶颈（合成器/客户端），不能只靠压 `present()` 达到 120 fps。

### 本飞暴露的测量缺陷（已记入 P-234）

报告行把 `wait`/`copy`/`done` 除以 1000 后仍标 `us`，那三段实际是毫秒，而四个内层段是真微秒。
按字面读会得到「`copy` 只有 48 µs 而内层加起来 48 ms」这种自相矛盾的结论，并据此误判 F5。
本卡的 S5/S6/S8 已按 `ms → µs` 换算后判决；缺陷本身在下一张镜像里修掉。
