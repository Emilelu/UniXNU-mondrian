#!/usr/bin/env python3
"""铁则 9：main 上的每个提交都必须是一次被声明的基线。"""
import re, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BOOK = REPO / "docs/engineering/MAIN-BASELINE.toml"
RISKY = ("patches/", "drivers/", "scripts/build-", "board.toml", "configs/")


def git(*a):
    return subprocess.run(["git", "-C", str(REPO)] + list(a), capture_output=True, text=True).stdout


def entries(text):
    out = []
    for m in re.finditer(r"\[\[entry\]\](.*?)(?=\n\[\[|\Z)", text, re.S):
        blk = m.group(1)
        d = dict(re.findall(r'^(\w+)\s*=\s*"([^"]*)"', blk, re.M))
        if "sha" in d:
            out.append(d)
    return out


def main():
    head = git("rev-parse", "--short", "HEAD").strip()
    text = BOOK.read_text() if BOOK.is_file() else ""
    known = {e["sha"]: e for e in entries(text)}
    problems, notes = [], []

    if head not in known:
        # 文档与门禁自身的提交不需要登记；只有会改变镜像的路径才需要。
        # 只有“新增或修改”风险路径才需要登记；删除只会缩小 main 的表面，不构成风险。
        touched = [f for f in git("show", "--name-only", "--diff-filter=ACMR", "--format=", head).splitlines()]
        risky = [f for f in touched if f.startswith(RISKY)]
        if risky:
            problems.append(
                "HEAD %s 改了会进镜像的路径（%s），却没有在 MAIN-BASELINE.toml 登记 sha/tag/kernel/state（铁则 9）"
                % (head, ", ".join(risky[:4])))
        else:
            notes.append("HEAD %s 只动文档/门禁，免登记" % head)

    anchor = None
    for m in re.finditer(r'^anchor\s*=\s*"([^"]+)"', text, re.M):
        anchor = m.group(1)
    if anchor:
        risky = [l for l in git("log", "--oneline", "%s..HEAD" % anchor).splitlines()]
        if risky:
            touched = set()
            for c2 in risky:
                sha = c2.split()[0]
                for f in git("show", "--name-only", "--format=", sha).splitlines():
                    if f.startswith(RISKY):
                        touched.add((sha, f))
            if touched:
                sample = ", ".join(sorted({s for s, _ in touched})[:5])
                notes.append("自 anchor %s 以来 %d 个提交动了风险路径（%s…）：这些应是分支工作，或需登记为 build-only" % (anchor, len({s for s, _ in touched}), sample))

    for p in problems:
        print("❌ iron-9  " + p)
    for n in notes:
        print("⚠️  iron-9  " + n)
    if problems:
        print("结论: ❌ main 基线登记不完整")
        return 1
    if notes:
        print("结论: ⚠️ main 基线已登记，但有未上机验证的欠账（P-174）")
        return 0
    print("结论: ✅ main 基线一致（铁则 9）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
