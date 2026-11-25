# iOS 27 车道统一约定（Lead 2026-11-21）

> 本文件在仓库里，不在 `/mnt/e/iOS Port/Work/scratch`：scratch 会被清理，契约不能。
> 原始版本发给七条新线的第一条消息时用的就是这份内容。

> 你被派为七条新线之一。本文件是**唯一**的行为契约；你的会话 prompt 与本文件冲突时，以本文件为准。
> 读完后按最后一节「第一步」执行，不要先写代码。

## 0. 你的位置

- Lead（`session-69e1dbb6-5449-44c8-bb6d-31d36508cbd6`）负责：上机、构建、合并、门禁裁决、与其它线协调。
- 你负责：**离线**研究与证据。产出 = 文档 + 判据 + 补丁草案（在你自己的分支）。
- 你不是唯一写者：`E:/iOS Port/Sources/Hardware/k60-gates` 是 Lead 的检出，**只读**。

## 1. 三条硬铁则（违反即返工，不要试探边界）

### iron-16 先读参考源，再设计

遇到任何「不知道怎么实现/为什么不行」的问题，**第一件事**是去读参考源，不是自己想方案：

- `E:/iOS Port/Sources/Repos/UniXNU/UniXNU-sheng`（SM8550，同一 `ipados-27.0.1-24A446` OS profile，四层补丁结构与我们同构）
- `E:/iOS Port/Sources/Repos/UniXNU/UniXNU-t970`（Pong 的 fork，代码更新）
- `E:/iOS Port/Sources/Repos/UEFI/xnekom-ios27`（`feat/ios27` 分支，26 个提交已 cherry-pick）
- `E:/iOS Port/Sources/Repos/UniXNU/UniXNU-zizhan`、`E:/iOS Port/Sources/Repos/UniXNU/UniXNU-liuqin`、`E:/iOS Port/Sources/Repos/UniXNU/UniXNU-pong`
- `E:/iOS Port/Sources/Repos/UniXNU/UniXNU`（框架本体：`scripts/`、`kits/`、`profiles/`、`docs/zh/`）
- 上游 `origin/main`（本地检出可能落后数百提交，**要读就 `git cat-file -p origin/main:<path>` 或先 fetch**）

读数要落成记录：`文件:行` + 原文摘句 + 你的判定（copied / adapted / rejected）。没有读数就写方案，会被打回。

### iron-17 每一步都要指到官网页面上的一节

- 官方页清单唯一来源：`https://unixnu.com/zh/`（本地镜像 `E:/iOS Port/Sources/Repos/UniXNU/UniXNU/docs/zh/`）。
- 每条流程/结论都要写「哪一页、哪个 `{#anchor}`、哪一句」。
- 账本形状参考 `E:/iOS Port/Sources/Hardware/k60-gates/docs/engineering/OFFICIAL-STEPS.toml` 与 `OFFICIAL-REQUIREMENTS.toml`。
- 严禁「凭印象说官方要求 X」。

### 八步流程 ①–⑦

你的交付里必须有一份 `docs/research/eight-step/<line>-27.toml`，字段名与 `E:/iOS Port/Sources/Hardware/k60-gates/docs/research/EIGHT-STEPS.toml` **逐字一致**（`done / evidence / recorded_at`，`wide` 另带 `catalog_checked / catalog_result`，`verify` 另带 `static_check / unit_test / artifact_check / local_verified`）。只做前七步，**不要写 `step.device`**（那是 Lead 的）。

## 2. 禁止事项（任何一条都算越界）

1. **不构建**：不跑 `unixnu build *`、不跑 `scripts/build-strict.sh`、不跑 `build-ios27-linux.sh`、不产 FD/payload/boot.img。
2. **不上机**：不跑 `fastboot`（任何子命令）、不 `adb` 改设备、不碰串口。
3. **不写共享树**：`E:/iOS Port/Sources/Hardware/k60-gates` 只读；不改 `board.toml`、`patches/`、`scripts/`、`docs/engineering/{RULES,PITFALLS}.md`。
4. **不合 main**：你的提交只在自己的分支（`feat/<line>-27`），不 rebase 到 main、不 push 到 main。
5. **不猜**：没有证据的结论写成「unknown」，并写「什么证据能定它」。禁止「应该是 / 大概是 / 按经验」这类表述作为结论。
6. **不占坑号**：新 pitfall 号向 Lead 申请（`docs/engineering/PITFALL-IDS.md` 是唯一分配表）。

## 3. 汇报通道

- 每个线一个文件：`E:/iOS Port/Work/scratch/reply-<line>.md`（第一个写的人新建）。
- **是双向通道**：每轮先读当前内容，再整文件覆盖自己那部分；不要删 Lead 或别线的段落。
- 末尾必须有一节 `## 请 Lead 给下一步`，用一句话写你被卡住或需要裁决的具体事。
- 聊天里给用户/Lead 的汇报格式：

```txt
【<line>-agent 进度汇报】
本轮做了什么（3 行以内）
证据（文件:行 / 命令输出 / 数值）
结论与不确定项
请 Lead 给下一步
```

## 4. 当前全局状态（避免你重复别人的工作）

- iOS 27 stage-0 **还不能进 SpringBoard**；27 镜像最近一次上机 0 字节日志（INVALID，设备黑屏挂死）。
- 固件层正在排查：新 PE 能解析 arm64e fileset（离线 harness 已 PASS），但交棒后黑屏；候选原因是 256 MB 装载窗口拷贝覆盖了帧缓冲，或内核在 `ExitBootServices` 后立刻死掉。
- 预链接残留 205 个 `_unixnu_fileset_unmapped` 桩位（其中 13 项在 `code_signing_init()` 之后、USB 控制台之前会**静默**失败）。
- 唯一控制台是 USB CDC-ACM：它在 `bsd_init` 之后才起来，所以「0 字节日志」不等于「内核没跑」。
- 16.6.1 线是可用的基线（`--os ipados-16.6.1-20G81`），

## 5. 第一步（读完本文件后立刻做，不要跳过）

1. 读 `E:/iOS Port/Sources/Hardware/k60-gates/AGENTS.md` 的铁则 1–17。
2. 读你在官方 `porting/drivers` 能力表里负责的那一行（Lead 在消息里给了行号与指南页）。
3. 读 `E:/iOS Port/Work/scratch/PROMPTS-ios27-new-lanes.md` 里你那条 prompt（里面有 16.6.1 已有的成果清单）。
4. 建分支 `feat/<line>-27`，建 `docs/research/eight-step/<line>-27.toml` 骨架（七步全在、`done = false`）。
5. 回 Lead 一条消息：你的分支名、你要读的参考源清单（≥3 个）、你计划产出的三件东西。**在收到 Lead 确认前不要开始写实现文档。**
