#!/usr/bin/env python3
"""research-gate.py — 研究完整性门禁

问题背景（2026-11-12 用户质问）：
  "你这种坑如何避免再犯 之前各种铁则 八步流程 完全不执行 丢三落四"

根因分析：
  1. 铁则是散文，读不读全凭自觉
  2. 八步流程写在文档里，没有强制入口
  3. 参考资料散落在 references/ 下几十个目录，没有任何清单说
     "做触摸必须读这些文件"
  4. 结果：wave12c-electrical.md 在本地躺了两天没被打开，
     却去抄了同仓库另一台机器（POCO X5 Pro）的驱动

机制：
  用 SOURCES.toml 声明每个子系统"必须考察的参考源"，
  每个源必须填写 examined（日期）+ finding（学到了什么）。
  未填 = 门禁 FAIL = 禁止构建。

这不是文档，是可执行的检查。写完不填 = 构建不了。
"""
import io
import os
from pathlib import Path
import sys

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

# 仓库根：默认本脚本所在的检出（worktree 里跑就用 worktree），K60_REPO 可覆盖。
REPO = os.environ.get('K60_REPO') or str(Path(__file__).resolve().parents[1])
SOURCES = os.path.join(REPO, 'docs', 'research', 'SOURCES.toml')

# 参考源搜索前缀。SOURCES.toml 里的 path 相对这些前缀之一；顺序即优先级。
#   REPO            -- 本仓库内的文件（docs/、references/ 的本地副本）
#   /mnt/e/k60-work -- 参考仓库的规范检出位置
#   /mnt/e/hackios  -- 直接从上游 clone 的参考仓库（QcaBluetooth、UniXNU-liuqin 等）
REFERENCE_PREFIXES = (
    str(REPO),
    '/mnt/e/k60-work',
    '/mnt/e/hackios',
)



def check(verbose=True):
    """返回 (ok, problems)"""
    if tomllib is None:
        return False, ['缺 tomllib/tomli']
    if not os.path.exists(SOURCES):
        return False, ['docs/research/SOURCES.toml 不存在']

    d = tomllib.load(open(SOURCES, 'rb'))
    problems = []
    checked = 0

    for sub, body in d.get('subsystem', {}).items():
        req = body.get('required', [])
        for item in req:
            path = item.get('path', '')
            examined = item.get('examined', '')
            finding = item.get('finding', '')
            label = '%s :: %s' % (sub, os.path.basename(path))

            # 1) 文件必须在本地存在（按 REFERENCE_PREFIXES 逐个试）
            tried = [os.path.join(prefix, path) for prefix in REFERENCE_PREFIXES]
            if not any(os.path.exists(candidate) for candidate in tried):
                problems.append(
                    '%s 文件不存在: %s（已试 %d 个前缀）'
                    % (label, path, len(tried))
                )
                continue

            # 2) 必须标记已考察
            if not examined:
                problems.append('%s 未标记 examined' % label)
                continue

            # 3) 必须写下 finding（至少 20 字）
            if not finding or len(finding.strip()) < 20:
                problems.append('%s 的 finding 太短或为空' % label)
                continue

            checked += 1

    if verbose:
        print('  已考察 %d 个参考源' % checked)
        if problems:
            print('  问题 %d 处:' % len(problems))
            for p in problems[:10]:
                print('    - %s' % p)

    return len(problems) == 0, problems


if __name__ == '__main__':
    ok, probs = check()
    print()
    print('结论: %s' % ('✅ 研究完整性通过' if ok else '❌ 研究完整性未通过'))
    sys.exit(0 if ok else 1)
