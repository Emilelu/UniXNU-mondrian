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

**镜像**：`gpu-stride-20261118`，`boot.img 1860bc01e727ba1d679fcda78d6268afcb7155f1f10157fd7b66b8aeae8900ef`，
内核 `92bcd4f26ab1d3d4d98fbd97ecfda9ce4edf8c115022f94363eb18af7a302abc`，
Metal 插件 `metal-plugin-20261118j`（`PongAdrenoMetal` 94,256 B，sha256 `b84e053a2a509d1829c10145e4b9954c8e2ce174b4d717b03cb623352f5d8f1c`），
series 228，参数 30 项 / 596 B。

**抓取**：`E:/k60-work/evidence/usblog-20261118-181618`，295,620 B / 4,002 行，
`capture.json complete=true`，supervisor rc=0，`K60KEXC` 0，panic 0，`crashed: backboardd` 0。

**判决：FAIL**（唯一失败项是 S6，`submit` 没有降下来；其余七项全过）

| 判据 | 结果 | 实测 |
| --- | --- | --- |
| S1 无异常 | PASS | `K60KEXC` 0，panic 0 |
| S2 恰好一行形状行 | PASS | `scanout copy per row source=5888 scanout=5760 rows=3200` |
| S3 ≥2 条阶段行 | PASS | 74 条 |
| S4 `imports` 等于 `frames` | PASS | 每一行都相等（F4 计数 0） |
| S5 `copy` ≥ `sum` | PASS | 稳态 65 个样本里 0 个反向 |
| S6 逐行时 `submit` 中位数 ≤ 6,000 µs | **FAIL** | **11,483 µs** |
| S7 单次搬运时 `submit` 与 11,478 µs 相差 ±30% | n/a | 本次是逐行 |
| S8 仍出帧且 backboardd 不崩 | PASS | `actual GPU scanout copy completed` 2 次，崩溃 0 |

稳态中位数（`frames≥20`，n=65）：`wait` 104 µs、`copy` **37,646 µs**、`done` 46 µs、
`import` 35 µs、`encode` **15,040 µs**、`submit` **11,483 µs**、`gpu` **11,211 µs**、
`sum` 37,596 µs（`sum/copy` 中位数 99.8%）。样本帧率 669 帧 / 95 s = **7.04 fps**。

**这一飞的两条硬结论**

1. **纹理不是 CPU 成本，逐行才是。** 与 `gpu-import-scope2`（纹理路径，n=45）逐项对照：
   `encode` 389 → **15,040 µs**（+14.6 ms），`submit` 11,478 → **11,483 µs**（差 5 µs），
   `gpu` 10,569 → 11,211 µs，`sum` 23,357 → 37,596 µs，`copy` 23.0 → **37.6 ms**。
   3,200 条 `copyFromBuffer` 每条要 ~4.7 µs 去编码，而一张线性纹理只要一次命令。
   **删掉每帧的纹理让每帧慢了 14.6 ms**，所以逐行分支被撤回，纹理路径保留（见提交
   `perf(gpu): keep the linear texture`）。
2. **`submit` 与搬运形状完全无关。** 两种毫不相干的搬运形状下 `submit` 是 11,478 µs 与
   11,483 µs（0.04% 以内），再加上此前 45 个样本的 `r(submit,gpu)=0.007`、`r(submit,前帧 gpu)=0.088`，
   可以判定 `[commands commit]` 是翻译层里**每次提交固定**的 CPU 成本，既不随搬运量变化，
   也不在等 GPU。下一步必须进翻译层内部测（`commit_now` → `submit_batch`），
   不能继续在外层调搬运。

**为什么没命中任何失败规则**：F4 的门槛是「逐行且 `submit` > 16,000 µs」，实测 11,483 µs，
所以 F4 不成立；这也说明**S6 的方向本来是对的、只是幅度不够**——真正的判决来自与上一飞的
逐项对照，而不是单飞的绝对阈值。这条已写入 P-235。
