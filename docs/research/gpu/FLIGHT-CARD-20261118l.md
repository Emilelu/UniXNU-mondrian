# 飞行卡 `gpu-stride-20261118`

判据在镜像之前写死。本卡回答两个问题，且只回答这两个：

1. 这条拷贝走的是**整段一次 `copyFromBuffer`**，还是**逐行 3200 次拷贝**？（历史上还有第三条
   线性纹理路，本轮已删除）
2. 若走逐行，`commit`（`submit` 段）是否从 11,478 µs 显著下降？

## 1. 前置证据

| # | 前提 | 证据 |
|---|---|---|
| P1 | 上一飞判决 PASS，且给出归因 | `FLIGHT-CARD-20261118k.md` §5：S1–S8 全过；45 条稳态样本中位 `import` 0.2% / `encode` 1.9% / `submit` 49.6% / `gpu` 45.9% |
| P2 | `submit` 是 CPU 侧工作，不是等上一帧 GPU | 同证据 45 条样本 `pearson r(submit, gpu) = 0.007`、`r(submit, prev_gpu) = 0.088`、`submit/gpu` 中位 1.13 但极差 0.05–4.99 |
| P3 | 单位缺陷已修 | `drivers/PongMetal/PongMetalScanout.h` 去掉三处 `/1000`；`scripts/tests/test-present-stage-split.py` 21 例含「每段时间真为微秒」两例 |
| P4 | 拷贝形状可被判读 | `present()` 记录 `singleRun`，worker 在首帧打印一行 `scanout copy single run stride=…` 或 `scanout copy per row source=… scanout=… rows=…` |
| P5 | 逐行路正确性 | 每行拷 `width*4` 字节；内核侧已保证 `stride >= width*4`、`bytes == stride*height`，两侧行数相同 |
| P6 | 不跨帧持有导入 | `scripts/tests/test-presenter-import-scope.py` 13 例 |

## 2. 镜像

- tag `gpu-stride-20261118`
- 相对上一张的行为差异只有一处：**pitch 不同时改用逐行 `copyFromBuffer`**，删除线性纹理分支
  （该分支会让翻译层每帧建一个 Vulkan image 并分配内存）
- 另一处非行为差异：报告行的 `wait/copy/done` 改为真微秒（P-234）

## 3. 抓取

- `scripts/flash.sh <boot.img> 240`，证据落 `E:/k60-work/evidence/usblog-<ts>/`
- 只看 `console.log`，`capture.json` 的 `complete` 必须为真

## 4. 判据

**S1** `K60KEXC` 命中 0；`K60PANIC: ring kept` / `Debugger called` / `initproc exited` 均为 0。
**S2** `scanout copy ` 形状行**恰好 1 条**，且形如 `scanout copy single run stride=<n> rows=<n>`
或 `scanout copy per row source=<n> scanout=<n> rows=<n>`。
**S3** 至少 2 条 `scanout frames=` 报告行，六字段齐全并以 `sum=<n> us` 结尾。
**S4** 每条报告行 `imports` == `frames`。
**S5** 每条报告行 `copy`（µs）≥ 同段 `sum`（µs）——单位修好后这必须恒成立，且偏差 ≤30%。
**S6** 若 S2 判为**逐行**：稳态中位 `submit` ≤ 6,000 µs（相对 11,478 µs 至少降 40%）。
**S7** 若 S2 判为**整段一次**：稳态中位 `submit` 落在 11,478 µs 的 ±30% 内（即纹理路径从来不是成本），
此时本卡只能否证假设，不算改进。
**S8** 仍出帧：`actual GPU scanout copy completed` ≥1 且 `crashed: backboardd` 为 0。

### 失败规则

**F1** `K60KEXC` > 0 ⇒ 立即回退上一张可启动镜像，不再追帧率。
**F2** S2 形状行缺失 ⇒ 打点没进镜像（查 bundle sha256 与 `K60METAL deploy files=`），本飞无结论。
**F3** 任意报告行 `copy` < `sum` ⇒ 单位缺陷复发，停飞，先修测量。
**F4** 逐行且中位 `submit` > 16,000 µs ⇒ 逐行录制本身更贵 ⇒ 撤销本改动（等 pitch 相同才用整段），
          转而测量翻译层内部（`commit_now` 的镜像创建/分配/提交三段）。
**F5** 中位 `copy` > 40 ms ⇒ 相对上一飞（23.0 ms）明显退化，先解释再继续。
**F6** `K60PANIC`/`backboardd` 崩 > 0 或 `capture.json complete=false` ⇒ 本飞作废，重飞同一张镜像。

## 5. 结果登记

（判决在出帧后填写，不在镜像之前填。）
