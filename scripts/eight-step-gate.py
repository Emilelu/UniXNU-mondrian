#!/usr/bin/env python3
"""eight-step-gate.py — 八步流程硬门禁

用户要求（2026-11-12）：
  "每个硬件修复都必须按八步流程走，每步操作都要有可靠依据，
   一旦没有100%能成功的依据就禁止继续推进，直到有为止。实现这个门禁"

八步（EIGHT-STEP-EVIDENCE.md 定义）：
  ① 同型   —— 同型号机型的实现（本机最优先）
  ② 官方   —— 官方文档/官方驱动
  ③ 反编译 —— 反编译/取证（DT、固件、反汇编、实机寄存器）
  ④ 广域   —— 广域交叉验证（同 SoC、同外设芯片、多来源）
  ⑤ 方案   —— 明确的实现方案
  ⑥ 深挖   —— 深挖未解点（源码/汇编级）
  ⑦ 核验   —— 本地可验证的核验（不刷机就能证明）
  ⑧ 上机   —— 真机验证

门禁语义：
  - build：①②③④⑤⑥ 必须有依据（研究+方案完整）
  - flash：①~⑦ 全部 + ⑧ 的「预测」必须声明（成功看哪行、失败看哪行）
            否则拒绝刷机

「100% 能成功的依据」的机器表达：
  - 每条依据必须有 reference（文件:行号 / URL / 日志名:行号），不能只写结论
  - ⑦ 核验必须有 local_verified = true 且给出本地验证方法
  - ⑧ 必须有 prediction.success / prediction.failure 两行
"""
import io
import json
from pathlib import Path
import os
import subprocess
import re
import sys

# GBK 控制台（Windows 默认）打不出 '\u274c'：门禁最后那行结论自己先死在 print 上，
# 调用方看到的是空 stdout 加一个 traceback，判据全变成"没有输出"（同 P-248 壁纸判定器）。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

# 从脚本位置推仓库根，而不是写死一个检出路径：Lead 与触摸 agent 各有自己的
# worktree（P-184），写死路径会让一方的门禁去读另一方的树。
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, 'docs', 'research', 'EIGHT-STEPS.toml')

# 一本账本一个操作系统：16.6.1 的八步记录里写着 16 线才有的文件与编号，把它套在
# 27 树上只会产生永远解析不到的引用（P-302）。选账本与选 defconfig 同源，都看
# board.toml 的 os_profile；K60_EIGHT_STEP_LEDGER 只在测试里用来指定文件。
LEDGER_16 = os.path.join('docs', 'research', 'EIGHT-STEPS.toml')
LEDGER_27 = os.path.join('docs', 'research', 'EIGHT-STEPS-27.toml')
_OS27 = re.compile(r'(?:ios|ipados|macos)-27\.')


def read_os_profile(repo=None):
    """board.toml 里的 os_profile；读不到就返回空串，由调用方决定怎么办。"""
    if tomllib is None:
        return ''
    try:
        with open(os.path.join(repo or REPO, 'board.toml'), 'rb') as f:
            return str(tomllib.load(f).get('board', {}).get('os_profile', '') or '')
    except Exception:
        return ''


def choose_ledger(profile, repo=None):
    """按 os_profile 选账本，返回 (路径, 理由)。纯函数，测试直接调它。"""
    repo = repo or REPO
    if _OS27.search(profile or ''):
        return os.path.join(repo, LEDGER_27), 'os_profile %s' % profile
    return os.path.join(repo, LEDGER_16), 'os_profile %s' % (profile or '(unset)')

STEPS = ['same_model', 'official', 'decompile', 'wide', 'plan', 'deep', 'verify', 'device']
LABEL = {
    'same_model': '① 同型',
    'official': '② 官方',
    'decompile': '③ 反编译',
    'wide': '④ 广域',
    'plan': '⑤ 方案',
    'deep': '⑥ 深挖',
    'verify': '⑦ 核验',
    'device': '⑧ 上机',
}
# build 需要前 6 步；flash 需要前 7 步 + 第 8 步的预测
BUILD_STEPS = STEPS[:6]
FLASH_STEPS = STEPS[:7]


EVIDENCE_ROOTS = ['/mnt/e/k60-work/evidence', '/mnt/e/k60-work/reports',
                  '/mnt/e/k60-work', '/mnt/e/hackios']


def _anchor_candidates(path, root=None):
    """Every place an anchor of this shape could legitimately live.

    Windows drive paths and leading-slash paths used to be turned into a single
    absolute path that does not exist: `Path('/mnt/e/k60-work') / '/k60-work/x'`
    is `/k60-work/x` because pathlib drops the base for an absolute right side.
    The ledgers are written in the Windows form (`E:/k60-work/...`), so this is the
    common case, not the corner case (P-304).
    """
    raw = str(path).replace('\\', '/')
    out = []
    m = re.match(r'^([A-Za-z]):/(.*)$', raw)
    if m:
        drive, rest = m.group(1).lower(), m.group(2)
        out.append(Path('/mnt/%s/%s' % (drive, rest)))          # WSL
        out.append(Path('%s:/%s' % (drive.upper(), rest)))       # Windows
    if raw.startswith('/'):
        out.append(Path(raw))
        out += [Path(base) / raw.lstrip('/') for base in EVIDENCE_ROOTS]
    out.append(Path(root or REPO) / raw.lstrip('/'))
    out += [Path(base) / raw.lstrip('/') for base in EVIDENCE_ROOTS]
    seen, uniq = set(), []
    for c in out:
        k = str(c)
        if k not in seen:
            seen.add(k)
            uniq.append(c)
    return uniq


def resolve_file_line(anchor, root=None):
    """A file:line anchor must resolve to a real line, in the repo or an evidence root."""
    path, _, line = anchor.rpartition(':')
    if path and re.match(r'^[A-Za-z]$', path):
        # `E:/x.md:1` split on the drive colon too; put it back.
        path, _, line = anchor.rpartition(':')
    candidates = _anchor_candidates(path, root)
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            count = sum(1 for _ in candidate.open('rb'))
        except OSError:
            return 'unreadable'
        return None if 1 <= int(line) <= count else 'past the end of %s' % candidate
    return 'no such file'


def unresolvable_reference(text):
    """Report the first anchor in the evidence that does not resolve, or None."""
    if not text:
        return 'no evidence'
    for match in re.finditer(r'(?:[A-Za-z]:)?[\w./-]+\.(?:c|h|mm|cpp|py|sh|md|toml|dts|dtsi|log|txt):\d+', text):
        problem = resolve_file_line(match.group(0))
        if problem:
            return '%s (%s)' % (match.group(0), problem)
    for match in re.finditer(r'usblog-\d{8}-\d{6}', text):
        if not any((Path(base) / match.group(0)).is_dir() for base in EVIDENCE_ROOTS):
            return '%s is not an evidence directory' % match.group(0)
    for match in re.finditer(r'\bP-\d{2,3}\b', text):
        if ('id = "%s"' % match.group(0)) not in RULES_TEXT():
            return '%s is not registered in RULES.toml' % match.group(0)
    return None


def RULES_TEXT():
    cached = getattr(RULES_TEXT, '_cache', None)
    if cached is None:
        path = Path(REPO) / 'docs/engineering/RULES.toml'
        cached = path.read_text(encoding='utf-8') if path.is_file() else ''
        RULES_TEXT._cache = cached
    return cached


def has_reference(text):
    """依据里必须有一个可核查的引用锚点"""
    if not text:
        return False
    pats = [
        r'[\w./-]+\.(c|h|mm|cpp|py|sh|md|toml|dts|dtsi|log|txt):\d+',  # file:line（最强）
        r'[\w./-]+\.(c|h|mm|cpp|py|sh|md|toml|dts|dtsi|log|txt)\b',     # 文件路径
        r'https?://',                                                   # URL
        r'unixnu\.com/[\w/.-]+',                                       # 站内链接
        r'usblog-\d{8}-\d{6}(:\d+)?',                                   # 日志名[:行]
        r'0x[0-9a-fA-F]{2,}',                                           # 寄存器/地址
        r'[A-Z]-\d{2,3}',                                               # 坑编号
        r'★\d+',                                                        # 铁则编号
        r'sha256\s*[0-9a-f]{8,}',                                       # 构建哈希
    ]
    return any(re.search(p, text) for p in pats)


# 一次构建只针对某些硬件项时，用 K60_EIGHT_STEP_ITEMS 明确声明（逗号分隔）。
# 默认不声明 = 校验全部 active 项（整机口径），所以不会因为漏写而变松。
# build-strict.sh 会把这个值写进 build-manifest.json，谁放窄了范围是可审计的。
def declared_items(hw, all_items=None):
    """Items this build is working on, or None for the whole-device default.

    A parked or planned item may be declared: a line that is actively being
    worked on must be able to build without waiting for an unrelated line to
    go green (P-192).  The declared item is then held to the same evidence
    rules as an active one, so this narrows scope without loosening it.
    """
    raw = (os.environ.get("K60_EIGHT_STEP_ITEMS") or "").strip()
    if not raw:
        return None
    names = [n.strip() for n in raw.split(",") if n.strip()]
    pool = dict(all_items or hw)
    unknown = [n for n in names if n not in pool]
    if unknown:
        raise SystemExit("K60_EIGHT_STEP_ITEMS 里有不存在的硬件项: %s（可选: %s）"
                         % (", ".join(unknown), ", ".join(pool)))
    return {n: pool[n] for n in names}


def validate(mode='build', verbose=True):
    """mode: 'build' | 'flash'"""
    if tomllib is None:
        return False, ['缺 tomllib/tomli']
    if not os.path.exists(DATA):
        return False, ['%s 不存在（账本由 os_profile 选择；见 P-302）'
                       % os.path.relpath(DATA, REPO)]

    ledger_source = os.environ.get('K60_EIGHT_STEP_LEDGER_SOURCE') or \
        choose_ledger(read_os_profile(), REPO)[1]
    d = tomllib.load(open(DATA, 'rb'))
    problems = []
    notes = []
    need = BUILD_STEPS if mode == 'build' else FLASH_STEPS
    checked = 0

    hw_all = d.get('hardware', {})
    # 只有 status=active 的硬件做硬检查。parked/planned 如实记录但不阻断构建：
    # 八步流程约束的是「正在做的修复」，不是历史清单。
    hw = {k: v for k, v in hw_all.items() if v.get('status', 'active') == 'active'}
    # 停放不是消失：每一项停放都要写清为什么停、什么条件下再看。
    for name, body in hw_all.items():
        if body.get('status', 'active') == 'active':
            continue
        if len((body.get('why') or '').strip()) < 20:
            problems.append('%s :: 停放/计划中但没写 why（为什么现在不做）' % name)
        if len((body.get('revisit') or '').strip()) < 10:
            problems.append('%s :: 停放/计划中但没写 revisit（什么条件下重新开始）' % name)
    if not hw_all:
        return False, ['%s 里没有 [hardware.*] 条目'
                       % os.path.relpath(DATA, REPO)]
    if not hw:
        return False, ['%s 里每一项都是 parked/planned：没有正在做的修复可判，'
                       '刷机门禁因此没有对象（P-290：永远为绿的规则等于没有规则）'
                       % os.path.relpath(DATA, REPO)]

    # build 模式可以用 K60_EIGHT_STEP_ITEMS 收窄到本次真正在修的硬件项；
    # 不声明就还是整机口径。flash 模式永远整机。
    if mode == 'build':
        scoped = declared_items(hw, hw_all)
        if scoped is not None:
            if verbose:
                names = ', '.join('%s[%s]' % (k, v.get('status', 'active'))
                                  for k, v in scoped.items())
                print('  声明范围: %s（K60_EIGHT_STEP_ITEMS）' % names)
            hw = scoped

    for name, body in hw.items():
        steps = body.get('step', {})
        for st in need:
            entry = steps.get(st)
            label = '%s :: %s' % (name, LABEL[st])
            if not entry:
                problems.append('%s 缺失' % label)
                continue
            # 16 线账本用字符串，27 线账本（assemble-27-eight-step.py 生成）用列表：
            # 一个字段两种形状，归一化放在读取层，账本本身不改（P-302）。
            raw_ev = entry.get('evidence') or ''
            ev = raw_ev if isinstance(raw_ev, str) else ' '.join(str(x) for x in raw_ev)
            ev = ev.strip()
            if len(ev) < 30:
                problems.append('%s 依据太短（需 >=30 字）' % label)
                continue
            if not has_reference(ev):
                problems.append('%s 依据缺可核查引用（需 file:line / URL / usblog-… / 0x… / P-xx / ★xx）' % label)
                continue
            if entry.get('done') is not True:
                problems.append('%s 未标记 done=true' % label)
                continue
            # ⑦ 核验额外要求本地已验证 + 三类验证齐全
            if st == 'verify':
                if entry.get('local_verified') is not True:
                    problems.append('%s 未 local_verified=true（不能在没本地证明前推进）' % label)
                    continue
                for kind in ('static_check', 'unit_test', 'artifact_check'):
                    if not (entry.get(kind) or '').strip():
                        problems.append('%s 缺 %s（⑦ 要求静态对照/离线单测/产物检查三类齐全）'
                                        % (label, kind))
                        continue
            # ④ 广域额外要求：官方组件目录必须查过
            if st == 'wide':
                if entry.get('catalog_checked') is not True:
                    problems.append('%s 未 catalog_checked=true（必须先查 UniXNU/components.toml，避免重复造轮子）' % label)
                    continue
                cr = (entry.get('catalog_result') or '').strip()
                if len(cr) < 40:
                    problems.append('%s catalog_result 太短（要逐个说明官方组件能不能用）' % label)
                    continue
            problem = _resolves(ev)
            if problem:
                # 构建不因文档引用债务停摆；一次上机是最终判据，那里必须干净
                fatal = mode == 'flash'
                if fatal:
                    problems.append('%s 依据里的引用解析不到：%s' % (label, problem))
                    continue
                notes.append('%s 引用解析债务：%s（构建不拦，飞行必拦）' % (label, problem))
            if mode == 'flash' and not (entry.get('recorded_at') or '').strip():
                problems.append('%s 缺 recorded_at（⑦之前每一步都要记时间，才能证明早于上机）' % label)
                continue
            checked += 1

        # flash 模式额外检查第 8 步的预测
        if mode == 'flash':
            dev = steps.get('device') or {}
            pred = dev.get('prediction') or {}
            if not (pred.get('success') or '').strip():
                problems.append('%s :: ⑧ 上机 未声明 prediction.success（成功看哪一行日志）' % name)
            elif not (pred.get('failure') or '').strip():
                problems.append('%s :: ⑧ 上机 未声明 prediction.failure（失败看哪一行日志）' % name)
            else:
                checked += 1


    # --- 上机顺序：已有 boot 记录时，七步必须早于它 ---
    if mode == 'flash':
        booted = last_boot_time()
        if booted:
            for name, body in hw.items():
                # 这条规则要抓的是「证据写在它要解释的那次上机之后」（回填证据）。
                # 只在条目已经声称上机完成时才有意义：飞行前的证据必然晚于上一次上机，
                # 把它判红等于禁止为下一次飞行补证据（P-290 形状）。
                if not ((body.get("step", {}).get("device")) or {}).get("done"):
                    continue
                for st in FLASH_STEPS:
                    recorded = ((body.get('step', {}).get(st)) or {}).get('recorded_at') or ''
                    try:
                        when = _timestamp(recorded)
                    except ValueError:
                        continue
                    if when > booted:
                        problems.append('%s :: %s 的 recorded_at 晚于最近一次上机，先补证据再飞'
                                        % (name, LABEL[st]))

    # --- README 表格一致性（防止 README 与 EIGHT-STEPS.toml drift）---
    # 27 账本没有 renderer：它由 assemble-27-eight-step.py 生成，表格另外渲染。
    # 硬套 16 线的 renderer 只会把「两本账本尚未合并」报成「README 过时」。
    _renderer_applies = os.path.abspath(DATA) == os.path.abspath(os.path.join(REPO, LEDGER_16))
    try:
        if not _renderer_applies:
            raise ValueError('no renderer for this ledger')
        import subprocess as _sp
        _r = _sp.run(['python3', os.path.join(REPO, 'scripts', 'render-eight-step-table.py'), '--check'],
                     capture_output=True, text=True, timeout=60)
        if _r.returncode != 0:
            problems.append('README 八步表格与 EIGHT-STEPS.toml 不一致，'
                            '跑 scripts/render-eight-step-table.py 重新生成并覆盖 README 的「八步流程进度」段')
        elif verbose:
            print('  README 八步表格: ✅ 与数据一致')
    except ValueError:
        if verbose:
            print('  README 八步表格: 跳过（本账本没有 renderer）')
    except Exception as _e3:
        problems.append('README 表格一致性检查失败: %s' % str(_e3)[:50])

    if verbose:
        print('  账本: %s（%s）' % (os.path.relpath(DATA, REPO), ledger_source))
        print('  模式: %s' % mode)
        print('  硬件项: %d 个（%s）' % (len(hw), ', '.join(hw.keys())))
        print('  通过 %d 项检查' % checked)
        if problems:
            print('  问题 %d 处:' % len(problems))
            for p in problems[:12]:
                print('    - %s' % p)

    return len(problems) == 0, problems


LEDGER = '/mnt/e/k60-work/ledger.jsonl'


def _resolves(text):
    return unresolvable_reference(text)


def _timestamp(text):
    import datetime as _dt
    return _dt.datetime.fromisoformat(text.replace('Z', '+00:00'))


def last_boot_time():
    """Time of the most recent recorded boot, or None."""
    path = Path(LEDGER)
    if not path.is_file():
        return None
    latest = None
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        stamp = record.get('recorded_at') or record.get('at') or ''
        try:
            when = _timestamp(stamp)
        except ValueError:
            continue
        latest = when if latest is None else max(latest, when)
    return latest

if __name__ == '__main__':
    # 选账本：测试可用 K60_EIGHT_STEP_LEDGER 指文件，平时按 os_profile（P-302）。
    _override = os.environ.get('K60_EIGHT_STEP_LEDGER')
    if _override:
        DATA = _override
        os.environ['K60_EIGHT_STEP_LEDGER_SOURCE'] = 'K60_EIGHT_STEP_LEDGER'
    else:
        DATA, _src = choose_ledger(read_os_profile(), REPO)
        os.environ['K60_EIGHT_STEP_LEDGER_SOURCE'] = _src
    mode = 'flash'
    for a in sys.argv[1:]:
        if a in ('--build', 'build'):
            mode = 'build'
        elif a in ('--flash', 'flash'):
            mode = 'flash'
    ok, probs = validate(mode)
    print()
    print('结论: %s' % ('✅ 八步流程通过（可以%s）' % ('构建' if mode == 'build' else '刷机')
                        if ok else '❌ 八步流程未通过，禁止%s' % ('构建' if mode == 'build' else '刷机')))
    sys.exit(0 if ok else 1)
