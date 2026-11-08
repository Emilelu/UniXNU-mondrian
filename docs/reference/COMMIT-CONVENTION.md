# Commit 规范（K60 自有仓库）

> 来源：`feflow/git-commit-style-guide` 官方 README 原文（2026-11-03 经 `gh api repos/feflow/git-commit-style-guide/readme` 取回，
> 存档于 `references/feflow-git-commit-style-guide.md`，仓库默认分支 `master`）。
> 适用范围：**仅用户自有仓库**（`UniXNU-mondrian`、`uefi-mondrian`、`UniXNU`、`ios-sweet-k60`、`PongUfs`、`UniXNU-sm8475-common`）。
> 参考仓库（pong、sheng、ios-sweet 上游等）只读，不适用、不改其历史与模板。
> 生效方式：**自 2026-11-03 起向后适用**；不改写任何已推送历史。

## 一、指南核心规则（原文逐条）

1. **消息格式**：
   ```
   <type>(<scope>): <subject>
   <空行>
   <body>
   <空行>
   <footer>
   ```
2. **type 九种**（超出即不合规）：`feat`（新功能）、`fix`（修 bug）、`docs`（仅文档，README/CHANGELOG/CONTRIBUTE 等）、
   `style`（空格/缩进/格式，不改逻辑）、`refactor`（重构，不加功能不修 bug）、`perf`（性能/体验优化）、
   `test`（测试用例）、`chore`（构建流程、依赖库、工具）、`revert`（回滚）。
3. **标题行 ≤ 50 字符**，描述主要变更。
4. **正文建议 ≤ 72 字符/行**，须回答三点：为什么必须改（背景/动机）、怎么解决的（步骤）、有无副作用/风险。
5. **footer**：可放 issue 链接或关闭 issue（如 `Closes #123`）或文档链接。
6. **分支规范**：master 为保护分支，不直接提交；从 master 切 feature/bugfix 分支，验证后合回主干、打 tag、删分支。
   分支命名 `类型_年月日_功能`（snake_case，如 `feat_20170401_fairy_flower`），类型限 feat/fix/refactor。
7. **tag 规范**：`v` + 三位版本号（`v1.2.31`）；新功能动第二位、bug 修复动第三位；灰度后缀 `-alpha.N`/`-belta.N`。
   正式发布前先生成 changelog。
8. **配套工具链**（Node 生态，非强制内容）：commitizen（交互式写消息）、validate-commit-msg（`.vcmrc` 校验 type 词表）、
   conventional-changelog（从消息生成 CHANGELOG）、husky（commitmsg 钩子）。

## 二、落地到本项目的映射

我们的仓库是 C/Python/shell/Makefile 体系，**没有 Node 工具链**，故只采用「消息格式 + 类型词表 + tag 规则」，
工具链不接入（无 package.json；引入 commitizen 反而破坏纯标准库约束）。以提交模板 + 评审代替自动校验。

### 2.1 提交模板（可存为 `.gitmessage`，`git config commit.template` 启用）

```
# <type>(<scope>): <subject>   <= 50 字符
# type ∈ feat / fix / docs / style / refactor / perf / test / chore / revert
#
# 正文（<= 72 字符/行）：
# 1. 为什么必须改？
# 2. 怎么解决的？
# 3. 有无副作用/风险？
#
# Footer：镜像/boot sha、证据文件、issue 链接
```

### 2.2 scope 约定（各仓）

| 仓库 | 建议 scope |
|---|---|
| UniXNU-mondrian（设备仓） | `board` / `dts` / `series` / `scripts` / `docs` / `porting` / `ci` |
| UniXNU（核心编排） | `payload` / `prelink` / `profiles` / `ci` / `k60` |
| uefi-mondrian | `fd` / `memory` / `bootargs` / `ci` |
| 内核归档分支（progress-bar-*） | `xnu-NNNN`（批次号）/ `xnu-base` / `xnu-zzzz` / `xnu-diag` |
| ios-sweet-k60 / PongUfs / sm8475-common | 沿用各仓既有习惯，type 必须合规 |

### 2.3 与本项目现状的差异说明

- **分支命名**：指南是 `类型_日期_功能`；本项目现行 `fix/k60-measured-high-window`（type/topic）风格已大量使用，
  存量分支不改名；**新建分支建议 `type/topic` 或 `type_yyyymmdd_topic` 二选一并在 AGENTS.md 保持一致**。
- **tag 命名**：指南是 `v`+三位版本；本项目移植尚未到"版本发布"阶段，里程碑 tag 采用 `v0.<n>.0-<里程碑名>`
  （如 `v0.1.0-progressbar`），后缀部分承载里程碑语义，视同指南的灰度后缀扩展。
- **历史不改写**：已推送的非合规消息保持原样。

### 2.4 历史消息改写示例（对照，仅示范不执行）

| 原消息 | 合规改写 |
|---|---|
| `k60: give FBSDisplayMode a nonzero preferred scale` | `fix(payload): FBSDisplayMode nonzero preferred scale`（47 字符；正文写清 SpringBoard display-mode trap 因果） |
| `fix(armcpu): restore the Darwin 22 start order the 16.6.1 kernel links`（71 字符，超长） | `fix(armcpu): restore Darwin 22 cpu start order`（47 字符；细节移正文） |

### 2.5 批量重放场景的机械 type 判定（progress-bar-20261102 重放已使用）

补丁重放属机械操作，逐个判定 type 会引入猜测。规则写死：
**文件名含 fix/restore/revert/repair → `fix`，其余 → `feat`**；诊断专用文件单独成提交用 `chore` 并在正文注明
「仅诊断、不含功能变更」。规则属本项目自定义扩展，特此记录。
