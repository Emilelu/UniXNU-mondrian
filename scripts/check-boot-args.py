#!/usr/bin/env python3
"""Boot-args 文档覆盖检查（独立脚本）。

规则：board.toml 里配置的 key、drivers/ 里 PE_parse_boot_argn 解析的 key，
      都必须在 docs/engineering/BOOT-ARGS.md 里有条目。

退出码：0 通过，1 有未文档化参数。

动机：P-144（pong_metal=2 不发布）、P-145（pong_adreno_start 从未配过）
都是「参数存在但语义没写下来」造成的。
"""
import glob
import io
import os
import re
import sys

try:
    import tomllib as tl
except ImportError:
    import tomli as tl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BO = os.path.join(ROOT, 'docs/engineering/BOOT-ARGS.md')

if not os.path.isfile(BO):
    print('  ❌ docs/engineering/BOOT-ARGS.md 不存在')
    sys.exit(1)

doc = io.open(BO, encoding='utf-8', errors='ignore').read()
# 只认标题里的 `name`，以及表格首列的 `name`
documented = set(re.findall(r'^### `([A-Za-z0-9_\-]+)`', doc, re.M))
documented |= set(re.findall(r'^\| `([A-Za-z0-9_\-]+)`', doc, re.M))

# board.toml
cfg = set()
try:
    bd = tl.load(io.open(os.path.join(ROOT, 'board.toml'), 'rb'))
    for a in bd.get('payload', {}).get('kernel_args', []):
        cfg.add(a.split('=')[0])
except Exception as e:
    print('  ❌ board.toml 解析失败: %s' % e)
    sys.exit(1)

# drivers
src = set()

# Kernel-side arguments live inside patches, not in drivers/: a patch that adds
# PE_parse_boot_argn("pong_x", ...) is exactly as real as one in a driver, but until
# 2026-11-19 only drivers/** was scanned, so pong_surface_pitch slipped through while the
# gate reported a clean count (the same shape as P-242: a check that does not cover the
# path it names).
for p in glob.glob(os.path.join(ROOT, 'patches/**/*.patch'), recursive=True):
    try:
        t = io.open(p, encoding='utf-8', errors='ignore').read()
    except Exception:
        continue
    for m in re.finditer(r'PE_parse_boot_argn\s*\(\s*"([^"]+)"', t):
        src.add(m.group(1))
for p in glob.glob(os.path.join(ROOT, 'drivers/**/*'), recursive=True):
    if not p.endswith(('.c', '.cpp', '.mm', '.h')):
        continue
    try:
        t = io.open(p, encoding='utf-8', errors='ignore').read()
    except Exception:
        continue
    for m in re.finditer(r'PE_parse_boot_argn\s*\(\s*"([^"]+)"', t):
        src.add(m.group(1))
    # A driver that reads the boot line itself through sysctlbyname("kern.bootargs")
    # matches a literal `key=value` instead of calling PE_parse_boot_argn. Before this
    # pattern existed, that whole class of arguments was invisible to the gate: the
    # 2026-11-19 `pong_gpu_blit_probe` check passed while the key was documented nowhere
    # (the same shape as P-240/P-241 - a check that does not cover the path it names).
    for m in re.finditer(r'\[\s*\]\s*=\s*"([A-Za-z0-9_.-]+)=', t):
        src.add(m.group(1))

# 框架/系统级参数，不属于本项目文档范围
SKIP = {
    '-v', 'debug', 'cs_enforcement_disable', 'amfi_get_out_of_my_way',
    'disable_exc_resource', 'epoch',
}

# The debt ledger: arguments a patch introduces but the document does not cover yet. Scanning
# patches/** on 2026-11-19 surfaced 42 at once, so they are accepted as a fixed list rather than
# silently ignored. The list may not grow; documenting one means deleting its line and lowering
# `count`. A stale line (already documented) is also a failure, because it hides the progress.
PENDING_PATH = os.path.join(ROOT, 'docs/engineering/BOOT-ARGS-PENDING.toml')
pending = set()
pending_ceiling = 0
if os.path.exists(PENDING_PATH):
    try:
        ledger = tl.load(io.open(PENDING_PATH, 'rb'))
        pending_ceiling = int(ledger.get('count', 0))
        pending = set(entry.get('name', '') for entry in ledger.get('pending', []))
        pending.discard('')
    except Exception as e:
        print('  ❌ BOOT-ARGS-PENDING.toml 解析失败: %s' % e)
        sys.exit(1)

stale = sorted(pending & documented)
if stale:
    print('  ❌ BOOT-ARGS-PENDING.toml 里 %d 个参数已经文档化，请删掉它们并把 count 减下来:'
          % len(stale))
    for name in stale:
        print('      %s' % name)
    sys.exit(1)
if len(pending) > pending_ceiling:
    print('  ❌ BOOT-ARGS-PENDING.toml 长到 %d 条，超过它记录的 count=%d；这份债只允许减少'
          % (len(pending), pending_ceiling))
    sys.exit(1)

missing = sorted((cfg | src) - documented - SKIP - pending)
if missing:
    print('  ❌ BOOT-ARGS.md 缺少 %d 个参数:' % len(missing))
    for m in missing:
        where = []
        if m in cfg:
            where.append('board.toml')
        if m in src:
            where.append('drivers/')
        print('      %-28s (%s)' % (m, '+'.join(where)))
    sys.exit(1)

print('  ✅ BOOT-ARGS.md 覆盖 config %d / 源码 %d 个参数（已文档化 %d）'
      % (len(cfg), len(src), len(documented)))

# P-156：文档写了范围，配置却越界。2026-11-12 board.toml 里是 k60_touch_se=19，
# 而驱动只接受 1..7（`if (stage > 7) { printf("unsupported k60_touch_se=…"); return; }`），
# 于是触摸整条线在 boot 时就被自己的参数关掉了，日志只有一行 unsupported，
# 而且"正常 UI 启动继续"，看起来像驱动坏了。
# 文档表格的「范围」列因此成为判据来源：写下来就必须被检查。
ranges = {}
for m in re.finditer(r'^\| `([A-Za-z0-9_\-]+)` \|[^|]*\|\s*([^|]+?)\s*\|', doc, re.M):
    name, spec = m.group(1), m.group(2)
    lo = hi = None
    r2 = re.match(r'^(\d+)\.\.(\d+)$', spec)
    r1 = re.match(r'^≤\s*(\d+)$', spec)
    if r2:
        lo, hi = int(r2.group(1)), int(r2.group(2))
    elif r1:
        lo, hi = 0, int(r1.group(1))
    if lo is not None:
        ranges[name] = (lo, hi)

try:
    bd2 = tl.load(io.open(os.path.join(ROOT, 'board.toml'), 'rb'))
    args2 = bd2.get('payload', {}).get('kernel_args', [])
except Exception:
    args2 = []

bad = []
for a in args2:
    if '=' not in a:
        continue
    name, value = a.split('=', 1)
    if name not in ranges:
        continue
    try:
        number = int(value, 0)
    except ValueError:
        continue
    lo, hi = ranges[name]
    if not (lo <= number <= hi):
        bad.append((name, value, lo, hi))

if bad:
    print('  ❌ board.toml 里 %d 个参数越出 BOOT-ARGS.md 声明范围:' % len(bad))
    for name, value, lo, hi in bad:
        print('      %-24s = %s（允许 %d..%d）' % (name, value, lo, hi))
    sys.exit(1)
if ranges:
    print('  ✅ 已声明范围的 %d 个参数都在范围内' % len(ranges))
sys.exit(0)

