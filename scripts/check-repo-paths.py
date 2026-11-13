#!/usr/bin/env python3
"""check-repo-paths.py — 门禁必须评判「正在运行它的那棵树」（P-183）

2026-11-14 的代价：scripts/ 里曾有 11 个脚本把主工作区路径写死成 REPO。多 worktree
并行之后，这句话的含义变成「永远读主工作区」，于是分支自己的数据永远进不了判定：

  - eight-step-gate.py 让音频线在 36 项检查全过的情况下被判「禁止构建」；
  - sync-device-input.py 把主工作区的 series 写进构建输入，分支补丁永远进不去；
  - render-eight-step-table.py --apply 把主工作区的旧数据渲染进当前 README；
  - check-build-applied.py 拿固定输入副本比对，P-165/P-166 长期误红。

规则：判定/构建类脚本必须从脚本自身位置推导仓库根。确实要跨树操作的工具
（把仓库名映射到本地路径的那种）要写进 ALLOW 并说明理由。

退出码 0 通过，1 有未登记的硬编码。
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"

# 拆开拼，避免本文件命中自己
NEEDLE = "/mnt/e/hackios/" + "UniXNU-mondrian"
SELF = Path(__file__).name

# 确实需要跨树的工具：写死目标树是正确的
ALLOW = {
    "pick-upstream.py": "把仓库名映射到本地路径，天生跨树；写死目标树正是它的职责",
}

# 这些脚本必须自带「从自身位置推导根」的写法
GATE_REQUIRED = [
    "check-docs.py",
    "check-build-applied.py",
    "check-repo-paths.py",
    "eight-step-gate.py",
    "flash.sh",
    "build-strict.sh",
    "porting-gate.py",
    "render-eight-step-table.py",
    "sync-device-input.py",
]
MARKERS = ("__file__", '$(dirname "$0")', '$(dirname "${BASH_SOURCE[0]}")')


def iter_scripts():
    for path in sorted(SCRIPTS.iterdir()):
        if path.is_file() and path.suffix in (".py", ".sh") and path.name != SELF:
            yield path


def main() -> int:
    problems = []
    hardcoded = 0
    allowed = 0
    for path in iter_scripts():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if NEEDLE in text:
            if path.name in ALLOW:
                allowed += 1
                continue
            hardcoded += 1
            lines = [str(n) for n, line in enumerate(text.splitlines(), 1) if NEEDLE in line]
            problems.append(
                "%s:%s 把主工作区写死成仓库根，应改成从 __file__ 推导"
                % (path.name, ",".join(lines[:4]))
            )
    missing = []
    for name in GATE_REQUIRED:
        path = SCRIPTS / name
        if not path.is_file():
            missing.append("%s 不存在" % name)
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if not any(marker in text for marker in MARKERS):
            missing.append("%s 没有从自身位置推导仓库根的写法" % name)

    stale = [name for name in ALLOW if not (SCRIPTS / name).is_file()]
    if stale:
        print("  · ALLOW 里有 %d 条文件已不存在，可以删掉：%s" % (len(stale), ", ".join(stale)))

    problems += missing
    if problems:
        print("❌ 脚本路径检查未通过（P-183）：")
        for problem in problems[:20]:
            print("   - %s" % problem)
        if len(problems) > 20:
            print("   … 还有 %d 处" % (len(problems) - 20))
        print("   判定/构建脚本要用 from __file__ 推导仓库根；跨树工具写进 ALLOW 并说明理由。")
        return 1
    print(
        "✅ 共检查 %d 个脚本：%d 个硬编码（全部已登记），%d 个跨树工具已说明理由（P-183）"
        % (len(list(iter_scripts())), allowed, len(ALLOW))
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
