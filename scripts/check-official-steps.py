#!/usr/bin/env python3
"""铁则 17 的门禁：流水线的每一步都要指到官网页面上的一节。

2026-11-21：为了修「加载器不认文件集」，我直接改了固件里的 DarwinBoot 就让新 PE 进镜像，
没按 porting/uefi-firmware 的「必需的集成」逐项核对，也没按 guide/debugging 的绿条诊断先确认
交接阶段，结果三张图全黑、固件界面都没起来。这条门禁把「先读哪一页、哪一节」变成可校验的数据：
账本里没有对应行的构建命令即失败，写了不存在的锚点也失败。

退出码：0 通过 / 1 有缺 / 2 判不了（账本或文档镜像缺失，判不了不等于通过，P-279）。
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / 'docs/engineering/OFFICIAL-STEPS.toml'
SCRIPT = ROOT / 'scripts/build-ios27-linux.sh'
SUBS = ('fetch', 'defconfig', 'build kernel', 'build payload', 'build firmware', 'bootimg')
MIN_WHAT = 30
ANCHOR = re.compile(r'\{#([^}]+)\}')


def commands(text: str) -> list[str]:
    """构建脚本里实际调用的 unixnu 子命令，按首次出现排序。"""
    found: list[str] = []
    for match in re.finditer(r'unixnu\s+((?:build\s+)?[a-z][a-z-]*)', text):
        name = ' '.join(match.group(1).split())
        if name in SUBS and name not in found:
            found.append(name)
    return found


def normalised(command: str) -> str:
    return ' '.join(command.replace('unixnu ', '').split())


def check(ledger: Path, docs: Path, script: Path) -> list[str]:
    problems: list[str] = []
    data = tomllib.loads(ledger.read_text(encoding='utf-8'))
    steps = data.get('step') or []
    if not steps:
        return ['the ledger has no [[step]] rows']

    seen: set[str] = set()
    for row in steps:
        name = row.get('command', '')
        where = f'{row.get("id", "?")} ({name})'
        for field in ('id', 'command', 'page', 'anchor', 'what', 'evidence'):
            if not str(row.get(field, '')).strip():
                problems.append(f'{where}: {field} is empty')
        if len(str(row.get('what', ''))) < MIN_WHAT:
            problems.append(f'{where}: what is shorter than {MIN_WHAT} characters; say what the page requires')

        page = docs / str(row.get('page', ''))
        if not page.is_file():
            problems.append(f'{where}: {row.get("page")} is not in the documentation mirror {docs}')
            continue
        text = page.read_text(encoding='utf-8', errors='replace')
        anchor = str(row.get('anchor', ''))
        if anchor not in ANCHOR.findall(text):
            problems.append(f'{where}: {row.get("page")} has no {{#{anchor}}} anchor')

        evidence = ROOT / str(row.get('evidence', '')).split(':')[0]
        if not evidence.exists():
            problems.append(f'{where}: evidence {row.get("evidence")} does not exist')

        if name in ('unixnu ' + s for s in SUBS):
            key = normalised(name)
            seen.add(key)
            if not re.search(r'unixnu\s+' + re.escape(key).replace(r'\ ', r'\s+'), script.read_text(encoding='utf-8')):
                problems.append(f'{where}: the build script never runs this command')

    for name in commands(script.read_text(encoding='utf-8')):
        if name not in seen:
            problems.append(
                f'the build script runs "unixnu {name}" but no [[step]] row covers it; '
                'write down which official section governs that step'
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger', default=str(LEDGER))
    parser.add_argument('--docs', default='/mnt/e/hackios/UniXNU/docs/zh')
    parser.add_argument('--script', default=str(SCRIPT))
    args = parser.parse_args(argv)

    ledger, docs, script = Path(args.ledger), Path(args.docs), Path(args.script)
    missing = [str(p) for p in (ledger, script) if not p.is_file()]
    if not docs.is_dir():
        missing.append(str(docs))
    if missing:
        print('FAIL official-steps: cannot judge, missing ' + ', '.join(missing)
              + ' (an absent input is not a pass, P-279)', file=sys.stderr)
        return 2

    problems = check(ledger, docs, script)
    for problem in problems:
        print(f'FAIL official-steps: {problem}')
    if problems:
        return 1
    print('OK official-steps: every pipeline command cites an official page and anchor')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
