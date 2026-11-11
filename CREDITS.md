# 贡献者与来源说明

本仓库的代码来自多个来源。GitHub 的 contributors 图只统计 commit 的 author 字段，
**不能反映实际的工作归属**——尤其是当代码经由 fork 搬运、rebase 或共享 git 身份时。

## 外部贡献

### yibiya（sduuub）

`https://github.com/yibiya/UniXNU-mondrian`

本仓库的以下工作来自 yibiya 的 fork 分支：

| 分支 | 内容 | 我们取用的部分 |
|---|---|---|
| `fix/ui-startup-blob` | UI 启动修复线 | `userland/ui_compat.c` 的 `f291b52`（CFPreferences 移出 constructor）；`patches/xnu/0394-k60-launchd-cache.patch` 的精选缓存（22 个核心 job）；`0340` 的 95,856 B UI 库 |
| `upstream-fix` | launchd / prelink 修复线 | `522c6ea` 的 prelink helper 修复 |

**注意**：这些提交在 git 元数据里的 author 是 `Emilelu`，
所以 GitHub contributors 图不会显示 yibiya。本文件是人工署名，
用来纠正这个偏差。

如果你认为本仓库还使用了 yibiya 的其他工作而此处未列出，请开 issue 指出。

## 其他参考来源

| 来源 | 用途 |
|---|---|
| `https://github.com/Seanding1998/hakios-xnu-kernel`（一加 Ace 2 / PHK110 / SM8475） | 同 SoC 触摸 PASS 全流程（`docs/phk110/waves/wave12c-electrical.md` 的 20ms 节拍）、launchd `hw.target` 根因（`wave20-launchd.md`） |
| `https://github.com/UniXNU/UniXNU` | 官方框架、组件目录、驱动仓库 |
| `https://github.com/UniXNU/Adreno740`、`UniXNU/AdrenoMetal`、`UniXNU/QcomGeniSpi` 等 | 官方驱动组件（详见 `docs/research/EIGHT-STEPS.toml` 的 catalog_result） |
| `https://github.com/UniXNU/UniXNU-pong` | Pong 原机参考实现 |
| `https://github.com/UniXNU/UniXNU-zizhan` | 同 SoC SM8475 参考（ST FTS 触摸 + Adreno 730） |

## 引用规范

从外部仓库取用代码时，应在 commit message 里写明：

```
Co-authored-by: <姓名> <邮箱>
(cherry picked from commit <sha>)
```

`git cherry-pick -x` 会自动带上第二行。手工复制代码时，请手动加
`Co-authored-by:` ——否则 GitHub 不会把贡献算给原作者。

参见 P-130（`docs/engineering/PITFALLS.md`）。
