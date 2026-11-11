#!/usr/bin/env python3
"""gate.py — 刷机前强制门禁（v2：加了"补丁集变化"这个今天真正漏掉的检查）。

今天（2026-11-11）5 次 0 字节日志的真相：补丁集从 201 条变成 211 条，
而我一直在查自己刚写的代码。**输入变了，却没人检查输入。**

本门禁的核心项：
  [S]  补丁集指纹 —— 和上次成功启动的指纹比，变了就要显式确认这是预期改动
  [B]  init 二进制 __TEXT 单页 + 签名形态（★27/P-94/P-99）
  [A]  boot-args 长度与必填项（HR-45/P-98）
  [K]  危险补丁不在 series（P-112/P-114）
  [X]  三处同步（P-44）+ series 真相源（P-90）
  [V]  一次只改一个变量
  [L]  账本里这组输入以前跑过吗

用法:
    gate.py                     # 全量
    gate.py --quick             # 跳过慢检查
    gate.py --force-new-series  # 明确声明"补丁集变化是预期的"
"""
import io
import json
import os
import re
import struct
import subprocess
import sys
import time

REPO = '/mnt/e/hackios/UniXNU-mondrian'
WORK = '/mnt/e/k60-work'
SERIES = WORK + '/scratch/SERIES-FINAL.txt'
PACK = WORK + '/scratch/packv15.sh'
XNU_WORK = ('/opt/k60/trees/k60build/out-baseline/mondrian/'
            'ipados-16.6.1-20G81/mondrian/tree/.cache/xnu-work')
KERNEL = ('/opt/k60/trees/k60build/out-baseline/mondrian/'
          'ipados-16.6.1-20G81/mondrian/kernel/kernel.macho')
DEV = '/tmp/usb-cdc-mainline/device/patches/xnu'
LEDGER = WORK + '/ledger.jsonl'

QUICK = '--quick' in sys.argv
FORCE_NEW = '--force-new-series' in sys.argv

fails, warns = [], []


def ok(sec, name, detail=''):
    print('    PASS  %-44s %s' % (name, detail))


def bad(sec, name, detail='', hard=True):
    print('    %s  %-44s %s' % ('FAIL' if hard else 'WARN', name, detail))
    (fails if hard else warns).append((sec, name, detail))


def sec(t, rule=''):
    print('\n[%s] %s' % (t, rule))


# ---------- series 指纹 ----------
def series_fingerprint():
    """补丁集指纹 = 名单 + 每个补丁的大小。名单相同但内容改了也算变化。"""
    import hashlib
    h = hashlib.sha256()
    try:
        names = [l.strip() for l in io.open(SERIES, encoding='utf-8',
                                            errors='ignore').read().split('\n')
                 if l.strip()]
    except Exception:
        return None, 0
    for n in names:
        h.update(n.encode())
        p = REPO + '/patches/xnu/' + n
        if os.path.exists(p):
            h.update(str(os.path.getsize(p)).encode())
    return h.hexdigest()[:16], len(names)






# ============ T. 文档一致性（★36 —— README/INDEX 必须及时更新）============
sec('T', '文档一致性（★36）')
try:
    _doc = subprocess.run(['python3', REPO + '/scripts/check-docs.py'],
                          capture_output=True, text=True, timeout=120)
    if _doc.returncode == 0:
        ok('T', 'README / INDEX 一致性', '链接有效、索引完整、中英同步')
    else:
        _lines = [l.strip() for l in (_doc.stdout or '').split('\n') if l.strip().startswith('- ')]
        bad('T', 'README / INDEX 需要更新', (_lines[0][2:] if _lines else '见 check-docs.py 输出'))
        for _l in _lines[1:6]:
            bad('T', '  ' + _l[2:], '', hard=False)
except Exception as _e4:
    bad('T', '文档一致性检查', str(_e4)[:60], hard=False)

# ============ R. porting.toml schema（★33 —— 官网设备页靠它渲染）============
sec('R', 'porting.toml schema（★33）')
try:
    import tomllib as _tml
except ImportError:
    try:
        import tomli as _tml
    except ImportError:
        _tml = None
PORTP = REPO + '/porting.toml'
if _tml is None:
    bad('R', 'TOML 解析器', '缺 tomllib/tomli', hard=False)
elif not os.path.exists(PORTP):
    bad('R', 'porting.toml', '文件不存在')
else:
    try:
        _d = _tml.load(open(PORTP, 'rb'))
        ok('R', 'TOML 语法', '可解析')
        if _d.get('schema_version') != 1:
            bad('R', 'schema_version', '应为 1，实际 %r' % _d.get('schema_version'))
        else:
            ok('R', 'schema_version', '1')
        _areas = _d.get('area', [])
        _ids = [a.get('id') for a in _areas]
        REQ = ['configuration', 'firmware', 'cpu', 'memory', 'storage', 'display',
               'input', 'gpu', 'network', 'cellular', 'audio', 'power',
               'packaging', 'diagnostics']
        _miss = [r for r in REQ if r not in _ids]
        if _miss:
            bad('R', '必需部分缺失', ', '.join(_miss))
        else:
            ok('R', '必需部分', '%d/%d 齐全' % (len(REQ), len(REQ)))
        VALID = ['planned', 'implemented', 'host-verified', 'device-verified', 'not-applicable']
        _badst = [a.get('id') for a in _areas if a.get('status') not in VALID]
        if _badst:
            bad('R', 'status 非法', ', '.join(str(x) for x in _badst[:4]))
        else:
            ok('R', 'status 取值', '全部合法')
        # 核心：evidence 必须是表
        _bad_ev = []
        _miss_f = []
        for a in _areas:
            for e in a.get('evidence', []):
                if not isinstance(e, dict):
                    _bad_ev.append(a.get('id'))
                    break
                for f in ['kind', 'reference', 'result']:
                    if f not in e:
                        _miss_f.append('%s:%s' % (a.get('id'), f))
                        break
        if _bad_ev:
            bad('R', 'evidence 裸字符串', ', '.join(str(x) for x in _bad_ev[:5]) + '（会让官网渲染崩）')
        else:
            ok('R', 'evidence 全是表', '')
        if _miss_f:
            bad('R', 'evidence 缺字段', ', '.join(_miss_f[:5]), hard=False)
        else:
            ok('R', 'evidence 字段', 'kind/reference/result 齐全')
        # 字段完整性
        FIELDS = ['id', 'status', 'components', 'paths', 'inputs', 'configuration',
                  'procedure', 'findings', 'completion', 'limits', 'next_action', 'evidence']
        _incomplete = []
        for a in _areas:
            _m = [f for f in FIELDS if f not in a]
            if _m:
                _incomplete.append('%s(缺 %s)' % (a.get('id'), ','.join(_m)))
        if _incomplete:
            bad('R', 'area 字段不完整', '; '.join(_incomplete[:3]), hard=False)
        else:
            ok('R', 'area 字段', '全部完整')

        # 官网语义验证：复刻 sync-devices.py 的 validate(allow_custom_components=True)
        try:
            import importlib.util as _ilu
            _spec = _ilu.spec_from_file_location(
                'pr', '/mnt/e/k60-work/references/UniXNU/scripts/porting-record.py')
            if _spec:
                _pr = _ilu.module_from_spec(_spec)
                _spec.loader.exec_module(_pr)
                _board = _tml.load(open(REPO + '/board.toml', 'rb'))
                _pr.validate(_d, _board, 'mondrian', allow_custom_components=True)
                ok('R', '官网 validate 语义', 'allow_custom_components=True 通过')
        except Exception as _e2:
            bad('R', '官网 validate 语义', str(_e2)[:70], hard=False)

    except Exception as _e:
        bad('R', 'porting.toml 解析', str(_e)[:60])

# ============ Q. 补丁结构（★31 —— Python 转义把 \n 变成真换行，补丁被拆断）============
sec('Q', '补丁结构（★31）')
bad_struct = 0
try:
    _dirty = subprocess.run(['git', 'status', '--porcelain', 'patches/xnu/'],
                            cwd=REPO, capture_output=True, text=True).stdout
    _targets = [os.path.basename(l.split()[-1]) for l in _dirty.strip().split('\n') if l.strip()]
    _targets = [t for t in _targets if t.endswith('.patch')]
except Exception:
    _targets = []
if not _targets:
    ok('Q', '本次没有改动补丁', '跳过')
    _targets = []
for name in _targets:
    if not name.endswith('.patch'):
        continue
    p = REPO + '/patches/xnu/' + name
    lines = io.open(p, encoding='utf-8', errors='ignore').read().split('\n')
    in_hunk = False
    illegal = 0
    for i, l in enumerate(lines):
        if l.startswith('@@'):
            in_hunk = True; continue
        if l.startswith('--- a/') or l.startswith('+++ b/') or l.startswith('diff --git'):
            in_hunk = False; continue
        if not in_hunk:
            continue
        if i == len(lines) - 1 and l == '':
            continue
        if l == '' or l[0] not in ' +-\\':
            illegal += 1
    if illegal:
        bad_struct += 1
        if bad_struct <= 3:
            bad('Q', '%s 结构损坏' % name[:34], '%d 行缺 +/- 前缀' % illegal)
if bad_struct == 0:
    ok('Q', '所有补丁结构合法', '')
elif bad_struct > 3:
    bad('Q', '共 %d 个补丁结构损坏' % bad_struct, '只列前 3')

# ============ P. 协议/型号断言（★30 —— 防止再拿错协议做一整天）============
sec('P', '协议断言（★30 硬件真值表 vs 代码）')
TRUTH = WORK + '/docs/ANDROID-HW-TRUTH.md'
TOUCH_PATCH = REPO + '/patches/xnu/zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-touch-console.patch'
try:
    truth = io.open(TRUTH, encoding='utf-8', errors='ignore').read()
    # 从真值表里读出触摸协议
    m = re.search(r'驱动\s*\|\s*\*\*`([^`]+)`.*?协议', truth)
    proto = None
    if 'GTP' in truth and 'Berlin-D' in truth:
        proto = 'GTP'
    elif 'GTP' in truth and '协议' in truth:
        proto = 'GTP'
    if proto:
        ok('P', '真值表声明的触摸协议', proto)
        if os.path.exists(TOUCH_PATCH):
            code = io.open(TOUCH_PATCH, encoding='utf-8', errors='ignore').read()
            gtp_marks = len(re.findall(r'0x8140|0x814E|0x804E|0x8047', code))
            brl_marks = len(re.findall(r'dev_confirm|0x10000u', code))
            ok('P', '代码里有 GTP 寄存器', '%d 处' % gtp_marks)
            if gtp_marks == 0:
                bad('P', '代码未实现真值表声明的协议',
                    '真值表说 %s，代码里 0x8140/0x814E 出现 0 次' % proto)
            else:
                ok('P', 'GTP 协议已落地', '')
            if brl_marks and gtp_marks == 0:
                bad('P', '代码仍在用 BRL', 'dev_confirm/0x10000 %d 处' % brl_marks)
            elif brl_marks:
                ok('P', 'BRL 代码存在但有 GTP', 'BRL %d 处（可共存）' % brl_marks)
    else:
        bad('P', '真值表可解析', 'ANDROID-HW-TRUTH.md 未声明协议', hard=False)
except Exception as e:
    bad('P', '协议断言', str(e), hard=False)

# ============ S. 补丁集变化（今天真正漏掉的那一项）============
sec('S', '补丁集指纹（★28 —— 今天 5 次死机的真因）')
fp, n_patches = series_fingerprint()
if fp is None:
    bad('S', 'series 可读', 'SERIES-FINAL.txt 不可读')
else:
    ok('S', 'series 指纹', '%s (%d 条)' % (fp, n_patches))

    # 从账本找最近一次成功启动的指纹
    last_ok_fp = None
    last_ok_at = None
    if os.path.exists(LEDGER):
        for line in io.open(LEDGER, encoding='utf-8', errors='ignore'):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get('result') == 'ok' and r.get('series'):
                last_ok_fp = r['series']
                last_ok_at = r.get('at')

    if last_ok_fp is None:
        bad('S', '账本里有成功记录', '没有 —— 先刷一个已知能跑的镜像并 record',
            hard=False)
    elif last_ok_fp == fp:
        ok('S', '与上次成功启动的补丁集相同', last_ok_at or '')
    else:
        detail = '上次成功 %s (%s) != 现在 %s' % (last_ok_fp, last_ok_at, fp)
        if FORCE_NEW:
            ok('S', '补丁集变了（已声明为预期）', detail)
        else:
            bad('S', '补丁集变了 —— 必须显式确认', detail)

    # 与上一批 series 的差异行数
    prev = WORK + '/scratch/.last-series'
    if os.path.exists(prev):
        try:
            a = [l for l in io.open(prev, encoding='utf-8', errors='ignore').read().split('\n') if l.strip()]
            b = [l for l in io.open(SERIES, encoding='utf-8', errors='ignore').read().split('\n') if l.strip()]
            added = [x for x in b if x not in a]
            removed = [x for x in a if x not in b]
            if added or removed:
                bad('S', 'series 相对上次有变化',
                    '+%d / -%d（%s）' % (len(added), len(removed),
                                        ', '.join((added + removed)[:2])[:50]),
                    hard=not FORCE_NEW)
            else:
                ok('S', 'series 相对上次无变化', '')
        except Exception:
            pass


# ============ B. init 二进制 ============
sec('B', 'init 二进制（★27 / P-94 / P-99）')
blob = None
try:
    s = io.open(REPO + '/patches/xnu/0391-k60-embedded-init.patch',
                encoding='utf-8', errors='ignore').read()
    m = re.search(r'k60_init_blob\[K60_INIT_BLOB_LEN\] = \{(.*?)\};', s, re.S)
    if m:
        blob = bytes(int(x, 16) for x in re.findall(r'0x([0-9a-f]{2})', m.group(1)))
except Exception:
    pass

if blob is None:
    bad('B', '0391 可解析', '不在 series 时这一项跳过', hard=False)
else:
    ncmds = struct.unpack_from('<I', blob, 16)[0]
    off, segs = 32, {}
    cs_magic = cs_size = None
    for _ in range(ncmds):
        cmd, size = struct.unpack_from('<II', blob, off)
        if cmd == 0x19:
            seg = blob[off + 8:off + 24].split(b'\x00')[0].decode('ascii', 'replace')
            segs[seg] = struct.unpack_from('<QQ', blob, off + 40)
        if cmd == 0x1D:
            o, sz = struct.unpack_from('<II', blob, off + 8)
            cs_size, cs_magic = sz, struct.unpack_from('>I', blob, o)[0]
        off += size

    t = segs.get('__TEXT', (0, 0))[1]
    bad('B', '__TEXT <= 16384', '__TEXT=%d' % t) if t > 16384 else ok('B', '__TEXT <= 16384', '__TEXT=%d' % t)
    ok('B', 'ncmds == 9', '') if ncmds == 9 else bad('B', 'ncmds == 9', 'ncmds=%d' % ncmds)
    if cs_magic == 0xFADE0CC0 and cs_size and cs_size < 1000:
        ok('B', '签名形态', 'datasize=%d' % cs_size)
    else:
        bad('B', '签名形态', 'magic=%s size=%s' % (hex(cs_magic or 0), cs_size))
    ok('B', 'v10guard 线', '') if b'v10guard' in blob else bad('B', 'v10guard 线', 'P-104')


# ============ A. boot-args ============
sec('A', 'boot-args（HR-45 / P-98）')
try:
    s = io.open(PACK, encoding='utf-8').read()
    m = re.search(r'G = \("(.*?)"\)', s, re.S)
    args = m.group(1) if m else ''
    toks = args.split()
    ok('A', 'length <= 600', '%d/608' % len(args)) if len(args) <= 600 else bad('A', 'length <= 600', '%d OVER' % len(args))
    # P-118：这几个是日志通道的红线。缺了 → 主机看到 0 字节，
    # 但内核可能活得好好的。一整天 8 次死机全是这个原因。
    LOG_REDLINE = ['debug=0x140', 'applog=1', 'k60_console_export=1',
                   'k60_usblog=2']
    MISSING_LOG = [x for x in LOG_REDLINE
                   if not any(t == x or t.startswith(x.split('=')[0] + '=')
                              for t in toks)]
    if MISSING_LOG:
        bad('A', '★日志红线（P-118）',
            '缺 %s → 会看到 0 字节日志' % ', '.join(MISSING_LOG))
    else:
        ok('A', '★日志红线（P-118）', 'debug/applog/console/usblog 齐全')

    MUST = ['native-ufs=1', 'pong_init_path=/private/var/pong/init',
            'k60_usblog=2', 'k60_console_export=1', 'pong_data_mount=1',
            'amfi_get_out_of_my_way=1', 'cs_enforcement_disable=1',
            'k60_skip_iosurface=1']
    # epoch 是带值的，单独用前缀匹配
    if not any(t.startswith('epoch=') for t in toks):
        bad('A', 'epoch 存在', '缺 epoch= 会让 launchd 时间戳变 1970（P-106）')
    else:
        ok('A', 'epoch 存在', [t for t in toks if t.startswith('epoch=')][0])
    miss = [x for x in MUST if x not in toks]
    if miss:
        bad('A', '必填项', 'missing: %s' % ', '.join(miss))
    else:
        ok('A', '必填项', '%d/%d' % (len(MUST), len(MUST)))
except Exception as e:
    bad('A', 'packv15.sh', str(e))


# ============ K. 危险补丁 ============
sec('K', '危险补丁（P-112 / P-114）')
try:
    stxt = io.open(SERIES, encoding='utf-8', errors='ignore').read()
    for name, pats in {
        '0404-k60-metal-deploy.patch': [r'^\+.*vnode_open\s*\(', r'^\+.*mount\s*\(\s*p'],
    }.items():
        if name in stxt:
            p = REPO + '/patches/xnu/' + name
            if os.path.exists(p):
                txt = io.open(p, encoding='utf-8', errors='ignore').read()
                if any(re.search(pt, txt, re.M) for pt in pats):
                    bad('K', '%s 在建文件' % name[:20], 'vnode_open/mount')
                else:
                    ok('K', '%s 安全' % name[:20], '')
        else:
            ok('K', '%s 不在 series' % name[:20], '')
except Exception as e:
    bad('K', 'series 可读', str(e))


# ============ X. 同步 ============
sec('X', '同步与真相源（P-44 / P-90）')
try:
    nbad = 0
    for f in sorted(os.listdir(REPO + '/patches/xnu')):
        if not f.endswith('.patch'):
            continue
        a, b = REPO + '/patches/xnu/' + f, DEV + '/' + f
        if os.path.exists(b) and os.path.getsize(a) != os.path.getsize(b):
            nbad += 1
            if nbad <= 2:
                bad('X', '%s 未同步' % f[:22], '%d vs %d' % (os.path.getsize(a), os.path.getsize(b)))
    if nbad == 0:
        ok('X', '补丁全域同步', '')
    elif nbad > 2:
        bad('X', '%d 个未同步' % nbad, '只列前 2')
    a = io.open(SERIES, encoding='utf-8', errors='ignore').read()
    b = io.open(REPO + '/patches/xnu/series', encoding='utf-8', errors='ignore').read()
    c = io.open(DEV + '/series', encoding='utf-8', errors='ignore').read()
    ok('X', 'series 三处一致', '') if a == b == c else bad('X', 'series 三处一致', '不一致')
except Exception as e:
    bad('X', '同步检查', str(e))


# ============ V. 变量隔离 ============
sec('V', '变量隔离（一次只改一个）')
try:
    dirty = subprocess.run(['git', 'status', '--porcelain', 'patches/xnu/'],
                           cwd=REPO, capture_output=True, text=True).stdout
    changed = [l.split()[-1] for l in dirty.strip().split('\n') if l.strip()]
    ok('V', '脏补丁 <= 1', '%d' % len(changed)) if len(changed) <= 1 else bad(
        'V', '脏补丁 <= 1', '%d: %s' % (len(changed),
                                        ', '.join(os.path.basename(x) for x in changed[:3])))
except Exception as e:
    bad('V', 'git status', str(e))


# ============ L. 账本 ============
sec('L', '账本（这组输入跑过吗）')
if os.path.exists(LEDGER):
    rows = []
    for line in io.open(LEDGER, encoding='utf-8', errors='ignore'):
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    n_ok = len([r for r in rows if r.get('result') == 'ok'])
    n_bad = len([r for r in rows if r.get('result') in ('fail', 'panic')])
    ok('L', '账本可读', 'ok=%d bad=%d' % (n_ok, n_bad))
    # 键 = series 指纹 + args 指纹（P-118：args 不同，结果完全不同）
    args_fp = hashlib.sha256(args.encode()).hexdigest()[:12] if args else 'unknown'
    same = [r for r in rows if r.get('series') == fp
            and r.get('args_fp') in (args_fp, None)]
    if same:
        lastr = same[-1]
        if lastr.get('result') == 'ok':
            ok('L', '这组 series+args 以前成功过', '%s args=%s' % (lastr.get('at', ''), args_fp))
        else:
            bad('L', '这组 series+args 以前失败过',
                '%s @ %s' % (lastr.get('result'), lastr.get('at', '')))
    else:
        bad('L', '这组 series+args 没跑过', '第一次跑，风险最高', hard=False)
else:
    bad('L', '账本存在', '还没有 ledger.jsonl', hard=False)


# ============ F. 内核新鲜度 ============
sec('F', '内核新鲜度')
if os.path.exists(KERNEL):
    age = time.time() - os.path.getmtime(KERNEL)
    ok('F', '10 分钟内', '%.0fs' % age) if age < 600 else bad('F', '10 分钟内', '%.0fs 前' % age, hard=False)
else:
    bad('F', 'kernel.macho 存在', 'missing')


print('\n' + '=' * 74)
if fails:
    print('❌ %d 项阻断 —— 禁止刷机' % len(fails))
    for s_, n, d in fails:
        print('   [%s] %-42s %s' % (s_, n, d))
    if warns:
        print('⚠️  %d 项警告' % len(warns))
    print('=' * 74)
    sys.exit(1)
print('✅ 门禁通过' + ('（%d 项警告）' % len(warns) if warns else ''))
print('=' * 74)
sys.exit(0)
