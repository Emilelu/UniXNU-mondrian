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
for p in glob.glob(os.path.join(ROOT, 'drivers/**/*'), recursive=True):
    if not p.endswith(('.c', '.cpp', '.mm', '.h')):
        continue
    try:
        t = io.open(p, encoding='utf-8', errors='ignore').read()
    except Exception:
        continue
    for m in re.finditer(r'PE_parse_boot_argn\s*\(\s*"([^"]+)"', t):
        src.add(m.group(1))

# 框架/系统级参数，不属于本项目文档范围
SKIP = {
    '-v', 'debug', 'cs_enforcement_disable', 'amfi_get_out_of_my_way',
    'disable_exc_resource', 'epoch',
}

missing = sorted((cfg | src) - documented - SKIP)
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
sys.exit(0)
