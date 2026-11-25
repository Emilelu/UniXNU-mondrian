import pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'

# 一份文档只有在**声明**自己描述某个证据仪器时，才受这四问约束。
# 判据从「关键词猜」改成「作者声明」：猜会误伤归档、审计、参数手册（实测 12 份误报），
# 而误报会让规则变红到被人忽略（P-290）。
MARK = re.compile(r'^\s*(?:;\s*)?instrument:\s*(\S.*)$', re.M | re.I)
FIELDS = ('lifetime', 'read_moment', 'writer', 'loss_condition')

HELP = """证据仪器文档必须回答四问（与 instrument: 同一份文档内）：
  lifetime       这条证据在什么条件下还存在（掉电 / 复位 / 写者退出 / 缓存未回写）
  read_moment    谁在什么时刻读它（同一次启动内 / 下次启动 / 宿主侧 / 事后离线）
  writer         谁写它，写到哪块内存或哪个介质
  loss_condition 什么操作会让它消失（长按电源、复位、固件训练内存、写者被 kill）
P-307 的由来：ramoops 在 DRAM，掉电即归零；这条事实 2026-10-30 已写进 PROGRESS-2026-10-30-PM.md §三，
2026-11-22 仍被重新发明一次 —— 所以改成「声明了就要回答」，而不是「提到就判红」。"""


def main(argv):
    targets = [pathlib.Path(a) for a in argv] or sorted(DOCS.rglob('*.md'))
    problems, checked = [], 0
    for path in targets:
        try:
            text = path.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            continue
        marks = MARK.findall(text)
        if not marks:
            continue
        checked += 1
        low = text.lower()
        gaps = [f for f in FIELDS if f not in low]
        if gaps:
            try:
                rel = path.resolve().relative_to(ROOT).as_posix()
            except ValueError:
                rel = path.as_posix()
            problems.append('%s (instrument: %s) 缺 %s' % (rel, marks[0].strip(), ', '.join(gaps)))
    for p in problems:
        print('FAIL: %s' % p)
    if problems:
        print()
        print(HELP)
        return 1
    print('OK channel docs: %d instrument doc(s) answer all four questions' % checked)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
