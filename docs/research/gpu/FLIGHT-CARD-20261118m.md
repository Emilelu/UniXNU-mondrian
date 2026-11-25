# 飞行卡：`gpu-texture-20261118`（保留线性纹理，形状上报三态）

## 1. 前置证据

- `gpu-stride-20261118`（`usblog-20261118-181618`）已证明逐行搬运比纹理慢
  14.6 ms（`encode` 389 → 15,040 µs，`copy` 23.0 → 37.6 ms），而 `submit` 两飞相同到 5 µs。
- 因此本次唯一的变量是**把搬运形状退回纹理**，其余（采样节奏、单位、字段）与上一飞完全一致。
- `submit` 与搬运形状无关这一结论来自两飞对照 + 45 样本的 `r(submit,gpu)=0.007`，
  见 `research/gpu/FLIGHT-CARD-20261118l.md` §5。

## 2. 镜像

`gpu-texture-20261118`（`scripts/build-strict.sh` 产出，`verify-boot-image: OK`）。

## 3. 抓取

`scripts/flash.sh <boot.img> 240`，证据落 `E:/iOS Port/Work/evidence/usblog-<ts>/`，
`capture.json` 必须 `complete=true`。

## 4. 判据

**成功判据**

- **S1** 无异常：`K60KEXC` 0 次、panic 0 次。
- **S2** 恰好一行形状行，且形状是 `texture untile`（不是 `per row`、不是 `single run`）。
- **S3** ≥2 条阶段行。
- **S4** 每一行 `imports` 与 `frames` 相等。
- **S5** 每一行 `copy` ≥ `sum`（P-234 的单位陷阱不得复发）。
- **S6** `encode` 中位数 ≤ 2,000 µs（纹理路径应回到亚毫秒量级，上一飞是 15,040 µs）。
- **S7** `copy` 中位数 ≤ 30,000 µs（上一飞 37.6 ms，纹理路径基线 23.0 ms）。
- **S8** 仍出帧（`actual GPU scanout copy completed` ≥ 2）且 `crashed: backboardd` 0 次。

### 失败规则

- **F1** `K60KEXC` 或 panic 出现 ⇒ 停飞，先看 ring。
- **F2** 没有形状行，或形状不是 `texture untile` ⇒ 说明兜底分支还在走，先查
  `minimumLinearTextureAlignmentForPixelFormat` 与实际 stride 的整除关系，不判性能。
- **F3** 某行 `copy` < `sum` ⇒ 单位回归（P-234），本次数据全部作废。
- **F4** `encode` 中位数仍 > 10,000 µs ⇒ 纹理路径没生效或还有别的逐条开销，回查改动是否真的进镜像。
- **F5** `copy` 中位数 > 30,000 µs 且 `encode` 已达标 ⇒ 成本在 `submit`/`gpu`，
  按 §5 结论进翻译层打点，不再调搬运形状。
- **F6** panic / 抓取不完整 ⇒ 无可判读。

## 5. 结果登记

（判决在出帧后填写，不在镜像之前填。）
