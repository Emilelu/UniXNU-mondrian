# AGENTS.md — 一页契约

目标：**K60（Redmi K60 / mondrian / SM8475）启动 iOS 27 并驱动全部硬件。**

只读这一页。仓库里 `RULES.toml`（1402 行）、`HARD-RULES.md`（2504 行）、
`PITFALLS.md`（8028 行）是机器检索库——用 `grep` 查，不要通读。

## 不可违反（违反就停手）

### 铁则 1 — 先例未对齐，禁止构建与上机

能进 userland 的 iOS 27 仓库（asteroids、uke、cupid、vermeer、sheng）每一条补丁/配置都要在
`docs/research/ios27/PRECEDENT-PARITY.toml` 里有判定；`missing-must-copy` 或 `unknown` 不为零时不构建、不上机。

### 铁则 2 — 不许猜

每个结论要能指到：知识库分块（`kb:`）、仓库 `文件:行`、或官方 URL。三者都没有就写「未证」，不许写成结论。

### 铁则 3 — 八步流程

每个硬件项都走：① 同型号证据 ② 官方文档页 ③ 反编译/设备数据 ④ 同 SoC/同芯片横向对比
⑤ 计划 ⑥ 深挖 ⑦ 离线验证 ⑧ 上机验证。缺任何一步，该项不算完成。

### 铁则 4 — 上机只由 Lead 发起

只 `fastboot boot`；**永不 flash，永不写 `/dev/block/sda38`**。

### 铁则 5 — 提交信息用英文，树必须干净再构建

`scripts/check-tree-clean.py` 判。

### 铁则 6 — 构建/上机前跑门禁

`python3 scripts/check-goal-constraints.py` 退 2 就不许动。

### 铁则 7 — 不再新增规范文档

只写代码、提交、和下面这三个状态文件。

## 协作

### 铁则 8 — 没有串口日志的启动是盲实验

8. **没有串口日志的启动是盲实验**：抓不到 0 字节就只能记 INVALID。

`fastboot boot` 必须同时抓 `VID_1209&PID_0001` 的串口日志；抓不到（`port-not-observed`、0 字节）
就只能记 INVALID，不能写成 PASS 或 FAIL。判据见 `scripts/check-boot-procedure.py` 与
`docs/engineering/BOOT-PROCEDURE.md`。

### Iron rule 12 — an agent message tries `steer` first

给另一条线发消息，先 `steer`（或 `inject`），被拒（目标离线/idle）才用 `followup`，并在回执首行写
`delivery: followup, steer-rejected: <原因>`。禁止开场就 followup，禁止 steer 成功后补发 followup。

## 状态只有三处

- `docs/engineering/STATUS.md` — 现在在哪一步
- `docs/research/ios27/PRECEDENT-PARITY.toml` — 先例对照（机器可判）
- `docs/research/EIGHT-STEPS-27.toml` — 每个硬件项的八步证据

## 当前状态

构建与上机：**冻结**（`docs/engineering/BUILD-FREEZE.md`）。
