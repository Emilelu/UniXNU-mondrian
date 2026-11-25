# 多线协作规则（DSH 多 Agent）

本仓由多个并行 Agent 线推进（audio / bluetooth / cellular / power / wifi / display / ufs / gpu …）。
以下规则是**机器可判的**（有门禁脚本），不是倡议。

## 1. 一线一树

- 每条线一个 `git worktree`，目录名 `k60-<line>`，分支 `feat/<line>-*`。
- 四条主仓：`UniXNU`（框架）、`UniXNU-mondrian`（设备仓）、`UniXNU-sm8475-common`（SoC）、`uefi-mondrian`（固件）。
- 工作树归属登记在 `docs/engineering/TREE-OWNERS.toml`；跨树操作前必须查它。
- 共享检出（主工作树）任何人不得直接改：只做 ref 操作（`git push origin <ref>:refs/heads/<name>`）。

## 2. 消息纪律（iron-12）

1. 先 `steer`（目标 running 时插入一步）。
2. 被拒（目标 idle / 不存在 steer 通道）才用 `followup`。
3. 每周期的回执写在 `reply-<line>-YYYYMMDD.md`；**覆盖前必须先读当前内容**，把对方新汇报先执行/回应，再整文件覆盖。

## 3. 上机权限

- 只有 **Lead** 可以 `fastboot boot`；其它线不得自行上机、不得 `fastboot flash`、不得写 `/dev/block/sda38`。
- 上机前必须满足：八步门禁 `--flash` 通过 + 镜像参数审计通过 + 冻结条件全部关闭（`docs/research/ios27/UNFREEZE-CHECKLIST.md`）。
- 任何一次上机都要落证据目录与 `record-boot.py` 记账。

## 4. 分支与合并

- `main` 只放可构建/可启动基线；未上机的以 `docs/engineering/MAIN-BASELINE.toml` 的 `state` 登记。
- 每条非 archive 且领先 main 的分支必须在 `docs/engineering/BRANCH-REGISTRY.toml` 写 `purpose` 与 `merge_plan`；触 `drivers/` 或 `package/` 的分支留 TBD 会被门禁拒绝（`check-branch-registry.py`）。
- 新增驱动/组件前必须 `check-capability-reuse.py` 通过：先在所有分支里搜同一基类，确认没有既有实现（P-324 / iron-20）。

## 5. 禁止动作

- `git push --force`、`reset --hard`、`checkout -f`、`-X ours` 合并（iron-18）。
- 在 linked worktree 里执行 `git worktree prune` / `gc` / `repack`（P-203）。
- 把 `/tmp` 当持久存储（iron-1）；构建输入必须经 `sync-device-input.py` 同步（iron-5）。
- 用别的线的构建目录 / 输出目录（`K60_DEVICE_INPUT`、`K60_OUT` 必须各自独立）。

## 6. 构建与门禁

- 唯一合法实验构建入口：`scripts/build-strict.sh`（16.x 线）或 `scripts/build-ios27-linux.sh`（27 线）。
- 27 线固定环境：
  `K60_DEVICE_INPUT=/opt/k60/trees/gates-device`、`K60_OUT=/opt/k60/trees/ios27-out`、
  `UNIXNU=/opt/k60/trees/ios27-fw`、`UNIXNU_OUT=/opt/k60/trees/ios27-out`、
  `UNIXNU_UEFI=/mnt/e/iOS Port/Sources/Repos/UEFI/uefi-mondrian`。
- 门禁注册表：`docs/engineering/RULES.toml`，运行 `python3 scripts/check-rules.py`。
- 构建失败先看门禁段落，不要先怀疑编译器。

## 7. 证据

- 串口/屏幕证据目录：`<Work>/evidence/usblog-YYYYMMDD-HHMMSS/`（`console.log` + `capture.json` + `boot.json`）。
- 判据必须写成「一条命令的读数」；贴不上就是没满足（P-300 / P-301）。
- 0 字节日志不等于内核没跑：先确认控制台通路（P-300）。
