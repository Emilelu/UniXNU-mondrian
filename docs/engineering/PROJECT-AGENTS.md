# 项目总闸（所有 Agent 进场必读）

## 0. 这是什么

一台 Redmi K60（`mondrian` / SM8475 / `taro`）上的 XNU/iOS 移植。当前主线是
**iOS 27.0.1（24A446，iPhone17,2、arm64e）跑在 xnu-12377（Darwin 25.5.0）之上，先走到 SpringBoard**。
iOS 16.6.1 线已归档为 `archive/ios16-20261120`，仍可用 `--os ipados-16.6.1-20G81` 构建。

## 1. 目录与仓库

```
E:\iOS Port
├─ Work\           开发期工作区（证据、构建产物、临时脚本、历史文档）
├─ Sources\
│  ├─ Repos\       四个 git 仓
│  │  ├─ UniXNU\UniXNU                  框架（origin 只读，推 fork）
│  │  ├─ UniXNU\UniXNU-mondrian         设备仓（origin 可写）
│  │  ├─ UniXNU\UniXNU-sm8475-common    SoC 仓（origin 可写）
│  │  └─ UEFI\uefi-mondrian             固件仓（origin 可写）
│  └─ Project\     当前会话的交接材料、补丁、证据快照
├─ WSL\Ubuntu-24.04\ext4.vhdx
└─ Tools\platform-tools
```

构建实际发生在 WSL 内（`/opt/k60/trees/…`），Windows 侧只放源码与产物。

## 2. 先读什么

1. `docs/engineering/COLLABORATION-RULES.md` —— 多线协作与禁止动作（机器可判）。
2. `docs/research/prior-art/PRIOR-ART-FIRST.md` —— 先例优先级：能进系统的机型 > 同 SoC > 同代 XNU。
3. `docs/engineering/FIRST-BOOT-PLAYBOOK.md` —— 从零到第一次出字的最短路径。
4. `docs/engineering/FAILURE-MODE-MATRIX.md` —— 症状 → 判据 → 下一步。
5. `docs/engineering/PORTING-PLAN.md` / `WORKFLOW.md` —— 四层架构与构建/上机流程。
6. `docs/archive/history/` —— 历史台账（commit 级）、历史坑卷、编号决策；只在回答「当年为什么这么定」时查。

## 3. 铁则与门禁

- 铁则正文：`AGENTS.md`；编号规则：`docs/engineering/RULES.toml`；坑：`docs/engineering/PITFALLS.md`。
- 每次改动后跑：`python3 scripts/check-rules.py`（当前 207 条，失败必须为 0）。
- 构建前必须：`sync-device-input.py`（iron-5）、`check-upstream-sync.py`（iron-15）、`check-series-order.py`（P-312）、`check-ios27-carryover`（P-320）、`check-branch-registry.py`（P-321）、`check-capability-reuse.py`（P-324）。

## 4. 上机

- 只有 Lead 上机；只 `fastboot boot`；**绝不** `fastboot flash`、**绝不**写 `/dev/block/sda38`。
- 冻结条件见 `docs/research/ios27/UNFREEZE-CHECKLIST.md`；未关闭前不构建诊断镜像、不上机。
- 每次上机必须有：预写判据、证据目录、`record-boot.py` 记账。

## 5. 当前状态（2026-11-26）

- 内核能在屏幕打印（r290n，`boot.img 311f4f54…`）；字形缩放 P-313 已修。
- r313h（`932d50ad…`）首飞全绿屏、console 0 字节 —— 待单变量二分，首嫌疑 `0580` GIC 映射补丁。
- `unixnu` 分区已写入 34,359,738,368 B 三窗口镜像（OS `4b8719fe…` / SystemOS `f6d10101…` / Data 18,095,276,032 B APFS）。
- 未解决 blocker：`prelink-map-unresolved`（155/34、234/34）、`root-storage-absent`（source-storage 已链接但未验证）、`boot-args-abi-608` 已关闭。

## 6. 交接

- 四仓 README 顶部有「接手 / Handoff」入口；framework / SoC / uefi 另有根 `HANDOFF.md`。
- 四仓当前均为 **archived** 状态；需要推送时先 `gh repo unarchive <owner>/<repo>`，推完再 archive。
