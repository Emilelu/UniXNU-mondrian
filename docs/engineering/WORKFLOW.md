# K60 移植工作流

本文描述在这套仓库里改一行代码、打一个补丁、飞一次设备的标准流程。它不是建议，是门禁强制的。

## 1. 铁则（摘要）

完整清单见 `AGENTS.md` 与 `docs/engineering/RULES.toml`（`scripts/check-rules.py` 执行）。

1. 不用 `/tmp` 做持久化；所有证据、镜像、日志落在 `E:/k60-work/`。
2. 改动必须提交并推送；未提交的文件会挡住构建（iron-2 / hard-5 / hard-10 / hard-11）。
3. 每个硬件修复走八步：①同型号 ②官方文档 ③反编译/参考实现 ④广覆盖 ⑤方案 ⑥深入 ⑦验证 ⑧上机；
   构建要求 ①–⑥，上机要求 ①–⑦ + ⑧。
4. 移植门禁 `porting-gate.py` 必须先过。
5. 构建输入必须与仓库同步（`sync-device-input.py`），镜像必须可复现。
6. 上游研判：每个上游提交要有 `picked / not-applicable / deferred` 结论。
7. 快照 tag：`snap-rN` 是唯一的回退点；打 tag 前必须推送。
8. 无串口控制台的启动是盲实验：必须同时抓 console 与屏幕。
9. `main` 是稳定可启动基线；实验走 `feat/*`，合回要求 BUILD OK + 上机验证或
   `MAIN-BASELINE.toml` 的 `state="build-only"` 登记。
10. secrets 不入库；树归属用 `TREE-OWNERS.toml`；禁止在共享树里跑 `git worktree prune/gc/repack`。
11. 只 `fastboot boot`，**永不 flash**；`/dev/block/sda38`（unixnu 分区）是唯一允许写的块设备，
    且写前必须有备份与写后校验。
12. agent 消息先 `steer`、被拒再 `followup`。

## 2. 八步流程

每一步都要在 `docs/research/eight-step/<hardware>.toml` 留下可解析的引用与 `recorded_at`：

| 步骤 | 要求 |
|---|---|
| ① 同型号 | 找到同 SoC/同型号成功案例并记录路径与提交 |
| ② 官方 | 引用 https://unixnu.com/zh/porting/ 对应页锚点 |
| ③ 反编译 | 固件/内核二进制证据，标明 file:line 或偏移 |
| ④ 广覆盖 | 同类实现（sheng/zizhan/t970/pong）全部列进先例账本 |
| ⑤ 方案 | 写清改哪个文件、为什么、如何回退 |
| ⑥ 深入 | 追到寄存器/调用链，不留「可能」 |
| ⑦ 验证 | 静态检查 + 单测 + 产物校验三件齐全 |
| ⑧ 上机 | 预写成功/失败判据 + console 证据 + `record-boot.py` 记账 |

## 3. 构建

```bash
cd /mnt/e/hackios/k60-gates
K60_DEVICE_INPUT=/opt/k60/trees/gates-device \
K60_OUT=/opt/k60/trees/ios27-out \
UNIXNU=/opt/k60/trees/ios27-fw \
UNIXNU_OUT=/opt/k60/trees/ios27-out \
UNIXNU_UEFI=/mnt/e/hackios/uefi-mondrian \
bash scripts/build-ios27-linux.sh
```

- 门禁在 `scripts/build-ios27-linux.sh` 之前由 `build-strict.sh` 统一执行；任何一条红都不构建。
- 构建失败会 `rm -rf` 整棵 tree（P-171），重跑前必须重新 `sync-device-input.py`。
- 固件卷复用键包含 `board.toml`、UEFI HEAD 与工作区 diff；改了 `BootArgs.h` 而未提交会复用旧卷（P-317）。
- 内核补丁改动后，`kernel/kernel.patched.macho` 必须重生成；payload 与 boot 只允许用它（P-316/P-323）。
- 构建前先跑 `scripts/check-rules.py`、`check-ios27-artifacts.py`、`check-prelink-hazards.py`。

## 4. 上机

```bash
cd /mnt/e/hackios/k60-gates
K60_DEVICE_INPUT=/opt/k60/trees/gates-device K60_AGENT_ID=lead \
bash scripts/flash.sh /mnt/e/k60-work/artifacts/boot-*.img 300
```

- 只 `fastboot boot`；`scripts/flash.sh` 是唯一允许调 fastboot 的入口（`check-fastboot-callers.py` 执行）。
- 抓取器先武装再 boot；`console.log` 0 字节不等于内核没跑（先看屏幕与 `capture.json`）。
- 判据写在飞行前：例如 `K60PIC gic base`、`K60UFS` 分区表、`bsd_init`、`Early boot complete`。
- 绿屏 = Entry.S 已执行、内核在 console 前死亡；全屏洋红 = 文本控制台未接管；两者含义不同。

## 5. 证据与记账

- 每次上机：`E:/k60-work/evidence/usblog-YYYYMMDD-HHMMSS/{console.log,capture.json,boot.json}`。
- `scripts/record-boot.py --image --log --note` 写 `E:/k60-work/ledger.jsonl`；SB<100 拒记。
- 构建产物：`/opt/k60/trees/ios27-out/.../boot/boot.img` 与 `build-manifest.json` 必须同时归档。
- 文档：`docs/research/ios27/BUILD-YYYYMMDD.md` 记录每张图；`docs/engineering/PITFALLS.md` 记录每次踩坑（P-编号唯一）。

## 6. 分支与协作

- `main` 只放可构建/可启动基线；实验在 `feat/*`，合并前跑 `check-branch-registry.py`。
- 每个 `feat/*` 必须在 `docs/engineering/BRANCH-REGISTRY.toml` 写 `purpose` 与 `merge_plan`，
  触 `drivers/` 或 `package/` 的分支 `purpose=TBD` 会直接拒绝构建（P-324 / iron-20）。
- 新驱动先跑 `check-capability-reuse.py`：同基类在任一分支已有实现，必须写 `CAPABILITY-REUSE.toml` 决策。
- 上游同步：`scripts/sync-repos.sh` + `k60-sync-refs.sh`（ff-only；禁强推、禁 reset --hard）。

## 7. 交接检查表

- [ ] `git log --branches --not --remotes` 为空（所有提交都在远端）。
- [ ] `check-rules.py` 全绿（含 waiver 列表解释）。
- [ ] `check-ios27-artifacts.py` 结构与 `--flight-ready` 状态已记录。
- [ ] 最近一张能打印文字的镜像与最近一张失败的镜像都归档，并写明差异。
- [ ] unixnu 分区镜像与写盘脚本、校验命令一并留在 `docs/research/ios27/BUILD-*.md`。

## 8. DSH 多线 Agent 并行协作

移植不是一个人做完的：音频、蓝牙、蜂窝、电源/充电、WiFi、显示、GPU、USB、存储各有一条独立工作线，
每条线由一个 DSH agent 会话负责，Lead 负责裁决、合流与上机。

### 8.1 DSH 侧的基础设施

- **Profile**：`C:\Users\Emilelu\.dsh\profiles\desktop`。`cordis.patch.yml` 里每个 provider 必须带
  `retryPolicy: {mode: always, backoff: {initialDelayMs: 1000, maxDelayMs: 30000, jitterRatio: 0.2}}`；
  少了它，一轮重试耗尽后会话就退化到「必须手动发继续」。
- **模型设置页会重写 `cordis.patch.yml`**：`"off"` 的引号、缩进、未知字段都可能被改掉；每次在 GUI 改过 provider
  都要重新校验（`reasoningEfforts` 的关闭键是带引号的 `"off"`，不是 `none`）。
- **MCP / 插件**：`windows-mcp-bridge` 这类 stdio MCP 只在 DSH 启动时连接；改配置后必须重启 DSH，
  不是热重载。`plugin_manager` 管 bundle/plugin，`cordis_inspect_*` 只读查询运行时 schema 与 slot。
- **定时任务**：`schedule_create` / `schedule_list`。本移植常用：
  - 上游轻量跟进（pick + 追踪）每 30 分钟；
  - 全量仓库同步 + 全分支追踪每 4 小时（:10，与 :00 错开避免 `index.lock` 争用）；
  - WSL 磁盘回收每 4 小时；
  - 各线回复巡检每 5 分钟。
- **子代理**：`subagent` / `subagent_fork` 用于一次性深挖（先例扫描、单线调研、离线验证）；子代理不共享本会话
  上下文，prompt 必须自带路径、判据与禁止项。`workflow` 仅用于大规模 fan-out（几十个独立文件/仓库的审计）。

### 8.2 多线协作规则

- **一线一树**：每条线有自己的 linked worktree（`E:/hackios/k60-<line>`）与自己的
  `K60_DEVICE_INPUT` / `K60_OUT`；禁止共用构建目录（会把别线的产物当成本线的）。
- **树归属**：`docs/engineering/TREE-OWNERS.toml` 记录每个 checkout 的 owner；`check-tree-owner.py` 与
  系统级 `/usr/local/bin/git` 守卫会在非 owner 执行危险 git 操作（`worktree prune`/`gc`/`repack`）时拒绝。
- **消息**：先 `steer`（运行中插话），被拒（idle）才 `followup`；这是铁则 12，`check-agent-messaging.py` 校验。
  每条线一个双向通道文件 `E:/k60-work/scratch/reply-<line>-YYYYMMDD.md`：**覆盖写之前必须先读**，
  先执行/回应对方的新汇报，再写本轮回复。
- **上机权**：只有 Lead 可以 `fastboot boot`；其他线只能提交镜像与判据，不能动设备。
- **分支**：每条线的实验分支必须在 `docs/engineering/BRANCH-REGISTRY.toml` 登记 `purpose` 与 `merge_plan`；
  触 `drivers/` 或 `package/` 的分支不登记会被 `check-branch-registry.py` 拒绝（P-321 / P-324）。
- **交付物**：子代理与各线的交付必须落到 `docs/research/**` 或 `docs/engineering/**` 并在
  `docs/research/SUBAGENT-DELIVERABLES.md` 记账（`check-subagent-ledger.py`），不接受「只在对话里说过」。
- **禁止**：在共享检出里 `git checkout -- .`/`reset --hard`/`stash`（P-184 事故）；`push --force` 任何分支（iron-18）；
  在 linked worktree 里 `git worktree prune`（P-203，会删掉主仓全部 worktree 管理目录）。

### 8.3 并行时的构建纪律

- 构建前先 `sync-device-input.py`，它会拒绝把别线的脏文件带进镜像。
- 每条线构建用独立 tag，日志与 `build-manifest.json` 留在自己的 `K60_OUT`。
- 同一时间只允许一个固件卷构建（`build/firmware` 的缓存键是全局的）；需要并行时用
  `K60_FORCE_FIRMWARE=0` 复用已有卷，或在各自 `K60_OUT` 下复制一份构建树。
- 上机前 Lead 汇总：该线最近一次 `check-rules.py`、`check-ios27-artifacts.py`、八步账本状态，缺一不飞。
