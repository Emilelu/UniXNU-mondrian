#!/usr/bin/env python3
"""八步 ① ② ③ 的逐条断言门禁（ADSP 层）。

research-gate.py 只问「有没有 RESEARCH.md」，问不出「你这次动的这一层，依据是
哪份同芯片实现的哪一行」。2026-11-13 我在同一层连着改三次都过了门禁，用户当场
点破：「没找到同芯片可 100% 执行的方法怎么又擅自改来改去」。

所以这里把依据写成可核对的断言：
  动 ADSP 相关文件 → docs/research/audio/ADSP-CLAIMS.toml 里必须有 verified
  断言，而且 evidence 指向的文件里真的能找到 evidence_needle。
"""
import io
import os
import re
import subprocess
import sys

REPO = '/mnt/e/hackios/UniXNU-mondrian'
CLAIMS = REPO + '/docs/research/audio/ADSP-CLAIMS.toml'
EVIDENCE = '/mnt/e/k60-work/evidence'
GUARDED = ('drivers/PongPower/K60Adsp', 'drivers/PongPower/K60Fat',
           'drivers/PongPower/K60Smem', 'patches/xnu/061')


def git(*args):
    return subprocess.run(['git', '-C', REPO] + list(args),
                          capture_output=True, text=True).stdout


def changed_files():
    base = 'main'
    out = git('diff', '--name-only', '%s...HEAD' % base)
    out += git('diff', '--name-only')
    return sorted({l.strip() for l in out.splitlines() if l.strip()})


def parse_claims(text):
    claims = []
    for block in re.split(r'^\[\[claim\]\]', text, flags=re.M)[1:]:
        d = dict(re.findall(r'^(\w+)\s*=\s*"([^"]*)"', block, re.M))
        flags = dict(re.findall(r'^(\w+)\s*=\s*(true|false)', block, re.M))
        if 'claim' in d:
            d['verified'] = flags.get('verified', 'false') == 'true'
            claims.append(d)
    return claims


def resolve(path):
    if path.startswith('usblog-'):
        return os.path.join(EVIDENCE, path, 'console.log')
    if path.startswith('/'):
        return path
    return os.path.join(REPO, path)


def main():
    text = io.open(CLAIMS, encoding='utf-8').read() if os.path.exists(CLAIMS) else ''
    claims = parse_claims(text)
    touched = [f for f in changed_files() if f.startswith(GUARDED)]

    bad = []
    for c in claims:
        if not c['verified']:
            continue
        f = resolve(c['evidence'])
        if not os.path.exists(f):
            bad.append('依据文件不存在：%s（%s）' % (c['evidence'], c['topic']))
            continue
        needle = c.get('evidence_needle', '')
        if needle and needle not in io.open(f, encoding='utf-8', errors='ignore').read():
            bad.append('依据里找不到锚点 %r（%s）' % (needle, c['topic']))

    verified = [c for c in claims if c['verified']]
    if touched and not verified:
        bad.append('动了 ADSP 层（%s）但 ADSP-CLAIMS.toml 里没有一条 verified 断言'
                   % ', '.join(os.path.basename(x) for x in touched[:3]))

    if bad:
        print('❌ adsp-claims  八步 ①③ 断言不足')
        for b in bad:
            print('   - ' + b)
        return 1
    print('✅ adsp-claims  %d 条断言全部可核对；本次改动 %d 个受管文件'
          % (len(verified), len(touched)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
