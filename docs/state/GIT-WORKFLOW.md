# Git 工作流铁则（2026-11-08 用户确认，必须遵守）

## 核心事实

**WSL 里的 git 永远 push 不上去**（网络/代理限制）。因此：

1. **所有 `git commit` / `git push` 必须在 Windows 侧执行**（Windows Git，例如 PowerShell 里的 `git`，工作目录 `E:\hackios\...`）。
2. WSL 里只做**文件修改与构建**；可以在 WSL 里 `git add`/`git status` 查看，但**不要在 WSL 里 push**，也不要依赖 WSL 的 git 远端。
3. 子 agent 在 WSL 里的本地 commit 只是"暂存"；**Lead 必须用 Windows git 统一 push**。
4. 每次 push 前先在 Windows 侧 `git log --oneline -3` 确认要推的提交，再 `git push origin HEAD`。

## 具体命令（Windows）

```powershell
$r = 'E:\hackios\UniXNU-mondrian'
git -C $r status --short
git -C $r add -A
git -C $r -c user.name='Emilelu' -c user.email='kimiuso@vip.qq.com' commit -m '...'
git -C $r push origin HEAD
```

## 历史教训

- 曾在 WSL 里执行 `git push` 长时间无输出/超时，误以为是网络抖动，实际是 WSL 无法出网到 GitHub。
- 曾在 WSL 里 `git fetch` 得到 `fetch-pack: invalid index-pack output`，同样应改用 Windows git 或本地 feed 缓存。
- 本文档写于 2026-11-08，用户明确要求"记进文档，不要反复踩坑"。
