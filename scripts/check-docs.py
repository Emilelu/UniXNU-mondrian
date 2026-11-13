#!/usr/bin/env python3
"""check-docs.py — 文档一致性门禁

解决的问题（2026-11-12 用户要求）：
  "这个 还有readme更新也要加门禁 确保及时更新"

三道检查：
  1. 链接完整性 —— README.md / README_EN.md / docs/INDEX.md 里每个相对链接
     必须指向真实存在的文件（外部 http 与纯锚点除外）
  2. INDEX 覆盖 —— docs/engineering/ 与 docs/research/ 下的每个 .md
     必须在 docs/INDEX.md 里被提到
  3. 中英同步 —— README.md 与 README_EN.md 必须互相链接，
     且都有 EIGHT-STEP-TABLE 标记块

任何一项失败 = 门禁 FAIL = 拒绝构建/刷机。
"""
import io
import os
import re
import sys

from pathlib import Path

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = [
    REPO + '/README.md',
    REPO + '/README_EN.md',
    REPO + '/docs/INDEX.md',
    REPO + '/AGENTS.md',
]

LINK_RE = re.compile(r'\[[^\]]*\]\(([^)]+)\)')


def check_links(verbose=True):
    """每个相对链接必须存在"""
    problems = []
    checked = 0
    for f in FILES:
        if not os.path.exists(f):
            problems.append('%s 不存在' % os.path.basename(f))
            continue
        base = os.path.dirname(f)
        s = io.open(f, encoding='utf-8', errors='ignore').read()
        for m in LINK_RE.finditer(s):
            target = m.group(1).strip()
            # 去掉锚点与标题
            target = target.split('#')[0].strip()
            if not target:
                continue
            if target.startswith(('http://', 'https://', 'mailto:')):
                continue
            # 绝对路径（以 / 开头）视为仓库根相对
            if target.startswith('/'):
                path = os.path.join(REPO, target.lstrip('/'))
            else:
                path = os.path.normpath(os.path.join(base, target))
            checked += 1
            if not os.path.exists(path):
                problems.append('%s: 链接失效 -> %s' % (os.path.basename(f), target))
    if verbose:
        print('  检查 %d 个相对链接' % checked)
    return problems, checked


def check_index_coverage(verbose=True):
    """docs/engineering/*.md 与 docs/research/*.md 必须被 INDEX.md 提到"""
    index = REPO + '/docs/INDEX.md'
    if not os.path.exists(index):
        return ['docs/INDEX.md 不存在'], 0
    s = io.open(index, encoding='utf-8', errors='ignore').read()

    problems = []
    counted = 0
    for sub in ('engineering', 'research'):
        d = os.path.join(REPO, 'docs', sub)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if not name.endswith('.md'):
                continue
            counted += 1
            # INDEX 里应出现 "engineering/NAME" 或 "NAME"
            if ('%s/%s' % (sub, name)) not in s and name not in s:
                problems.append('docs/%s/%s 未在 INDEX.md 中登记' % (sub, name))
    if verbose:
        print('  检查 %d 个文档的 INDEX 覆盖' % counted)
    return problems, counted


def check_bilingual(verbose=True):
    """README 与 README_EN 互链 + 都有八步表格标记"""
    problems = []
    zh = REPO + '/README.md'
    en = REPO + '/README_EN.md'
    if not os.path.exists(zh) or not os.path.exists(en):
        return ['README.md 或 README_EN.md 不存在'], 0
    a = io.open(zh, encoding='utf-8', errors='ignore').read()
    b = io.open(en, encoding='utf-8', errors='ignore').read()

    if 'README_EN.md' not in a:
        problems.append('README.md 没有指向 README_EN.md 的链接')
    if 'README.md' not in b:
        problems.append('README_EN.md 没有指向 README.md 的链接')
    for label, txt in (('README.md', a), ('README_EN.md', b)):
        if 'EIGHT-STEP-TABLE:BEGIN' not in txt:
            problems.append('%s 缺 EIGHT-STEP-TABLE 标记块' % label)
    if verbose:
        print('  检查中英互链与八步表格标记')
    return problems, 2


def check_freshness(verbose=True):
    """README 与 INDEX 必须链接 STATUS.md（确保详细状态有出口）"""
    problems = []
    pairs = [
        (REPO + '/README.md', 'STATUS.md'),
        (REPO + '/README_EN.md', 'STATUS.md'),
        (REPO + '/docs/INDEX.md', 'STATUS.md'),
    ]
    for path, needle in pairs:
        if not os.path.exists(path):
            continue
        s = io.open(path, encoding='utf-8', errors='ignore').read()
        if needle not in s:
            problems.append('%s 未链接 %s（详细状态无处可去）'
                            % (os.path.basename(path), needle))
    if verbose:
        print('  检查 STATUS.md 引用')
    return problems, len(pairs)



def check_subdir_indexes(verbose=True):
    """docs/engineering/README.md 必须登记该目录下每个 .md"""
    problems = []
    counted = 0
    pairs = [
        ('engineering', os.path.join(REPO, 'docs', 'engineering', 'README.md')),
    ]
    for sub, index_path in pairs:
        if not os.path.exists(index_path):
            problems.append('%s 不存在' % os.path.relpath(index_path, REPO))
            continue
        s = io.open(index_path, encoding='utf-8', errors='ignore').read()
        d = os.path.join(REPO, 'docs', sub)
        for name in sorted(os.listdir(d)):
            if not name.endswith('.md'):
                continue
            counted += 1
            if name == os.path.basename(index_path):
                continue
            if name not in s:
                problems.append('docs/%s/%s 未在 %s 中登记'
                                % (sub, name, os.path.basename(index_path)))
    if verbose:
        print('  检查子目录索引覆盖 %d 个文档' % counted)
    return problems, counted



def check_root_docs_linked(verbose=True):
    """仓库根目录每个 .md（除 README.md 自身）都必须被 README.md 链接，
    且 README.md 必须链接 docs/INDEX.md 作为文档总入口。"""
    problems = []
    README = os.path.join(REPO, 'README.md')
    if not os.path.exists(README):
        return ['README.md 不存在'], 0
    s = io.open(README, encoding='utf-8', errors='ignore').read()

    counted = 0
    for name in sorted(os.listdir(REPO)):
        if not name.endswith('.md'):
            continue
        if name == 'README.md':
            continue
        counted += 1
        if '](%s)' % name not in s:
            problems.append('根目录 %s 未在 README.md 中链接' % name)

    # docs/INDEX.md 必须作为文档总入口被链接
    counted += 1
    if '](docs/INDEX.md)' not in s:
        problems.append('README.md 未链接 docs/INDEX.md（文档总入口）')

    if verbose:
        print('  检查 %d 个根目录文档与 docs 入口的 README 链接' % counted)
    return problems, counted



# README 章节的重要性顺序（2026-11-12 用户要求按重要性排序）
SECTION_ORDER = {
    'README.md': ['八步流程进度', '构建', '门禁', '数据安全', '作业纪律',
                  '结构', '四层仓库', '分支', '文档', '许可'],
    'README_EN.md': ['Eight-step progress', 'Building', 'Gates', 'Data safety',
                     'Working discipline', 'Layout', 'Four-layer repository model',
                     'Branches', 'Documentation', 'License'],
}


def check_section_order(verbose=True):
    """README 的 ## 章节必须严格按重要性顺序排列"""
    problems = []
    counted = 0
    for name, expected in SECTION_ORDER.items():
        path = os.path.join(REPO, name)
        if not os.path.exists(path):
            continue
        s = io.open(path, encoding='utf-8', errors='ignore').read()
        actual = re.findall(r'^## (.+)$', s, re.M)
        counted += len(expected)
        if actual != expected:
            problems.append('%s 章节顺序不符。期望 %s；实际 %s'
                            % (name, ' → '.join(expected), ' → '.join(actual)))
    if verbose:
        print('  检查 %d 个章节的顺序' % counted)
    return problems, counted




# 待办/计划类文档里禁止硬编码上游 SHA（★37 / HR-72）
#
# 只在明确的 commit 语境里检测，避免把寄存器地址（1c00000）、
# 分区大小（5096113664）、设备序列号（6033dbec）当成 SHA。
# 判据：7-40 位十六进制，至少含一个 a-f，且同一行出现 commit 语境词。
SHA_RE = re.compile(r'\b(?=[0-9a-f]{7,40}\b)(?=[0-9]*[a-f])[0-9a-f]{7,40}\b')
SHA_COMMIT_CONTEXT = re.compile(
    r'提交|commit|cherry.?pick|取自|取用|upstream|上游|分支.*@|@[0-9a-f]{7}', re.I)
SHA_SKIP = re.compile(
    r'revision|cherry.?picked|sha256|image size|sectors|serial|adb -s|LBA', re.I)
# 只有「待办/计划」性质的文档受约束。调研记录、审计、参考文档里的
# SHA 是历史事实，不在管辖范围内。
# 只扫「待办/计划」文档。STATUS.md 是已完成工作的记录，按 HR-72
# 的例外条款允许写 SHA（它每一行都带取用日期）。
SHA_SCAN_FILES = [
    'docs/plans/BACKLOG.md',
    'docs/plans/GPU-TODO.md',
]


def check_no_hardcoded_sha(verbose=True):
    """待办与计划文档不得写死上游 SHA；写死的第二天就过时"""
    problems = []
    counted = 0
    for rel in SHA_SCAN_FILES:
        p = os.path.join(REPO, rel)
        if not os.path.exists(p):
            continue
        counted += 1
        for lineno, line in enumerate(
                io.open(p, encoding='utf-8', errors='ignore'), 1):
            if SHA_SKIP.search(line):
                continue
            if not SHA_COMMIT_CONTEXT.search(line):
                continue
            for m in SHA_RE.finditer(line):
                problems.append('%s:%d 硬编码上游 SHA `%s`（★37：改写查询命令）'
                                % (rel, lineno, m.group(0)))
                break
    if verbose:
        print('  检查 %d 个待办/计划文档的 SHA 硬编码' % counted)
    return problems, counted


OFFICIAL = "https://github.com/UniXNU/UniXNU"
FORK = "https://github.com/Emilelu/UniXNU"


def check_readme_links(verbose=True):
    """README 里的仓库链接必须指向我们自己的仓库。

    两类错误都会让读者克隆错仓库：
      - 框架：官方 UniXNU/UniXNU 只能作为「官方/上游」标注出现，工作用的是 fork；
      - 本项目自有仓库（UniXNU-mondrian / UniXNU-sm8475-common / uefi-mondrian）
        必须指向 Emilelu，不能写成 UniXNU 组织（2026-11-13 用户：UniXNU-sm8475-common
        是我的仓库，README 里链接错了，其他同类问题也要修）。
    """
    own = ("UniXNU-mondrian", "UniXNU-sm8475-common", "uefi-mondrian")
    bad = []
    for name in ("README.md", "README_EN.md", "CREDITS.md"):
        f = Path(REPO) / name
        if not f.is_file():
            continue
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            for repo in own:
                wrong = "github.com/UniXNU/%s" % repo
                right = "github.com/Emilelu/%s" % repo
                if wrong in line and right not in line:
                    bad.append("%s:%d %s 指向 UniXNU 组织，应指向 Emilelu" % (name, i, repo))
            # the bare-framework rule only applies to README files: CREDITS has a
            # dedicated "official" section where listing UniXNU/UniXNU is correct
            if name == "CREDITS.md":
                continue
            if not re.search(r'UniXNU/UniXNU(?![A-Za-z0-9._-])', line):
                continue
            marked = any(k in line for k in ("官方", "上游", "official", "upstream"))
            if FORK not in line and not marked:
                bad.append("%s:%d 链接到官方仓库但没有标注 fork/官方" % (name, i))
    return bad, 2


def run(verbose=True):
    all_problems = []
    total = 0
    for fn in (check_links, check_index_coverage, check_subdir_indexes,
               check_root_docs_linked, check_section_order, check_no_hardcoded_sha,
               check_bilingual, check_freshness, check_readme_links):
        p, n = fn(verbose)
        all_problems += p
        total += n

    if verbose:
        print('  共检查 %d 项' % total)
        if all_problems:
            print('  问题 %d 处:' % len(all_problems))
            for x in all_problems[:15]:
                print('    - %s' % x)
    return len(all_problems) == 0, all_problems


if __name__ == '__main__':
    ok, probs = run()
    print()
    print('结论: %s' % ('✅ 文档一致性通过' if ok else '❌ 文档一致性未通过，请修复后重试'))
    sys.exit(0 if ok else 1)
