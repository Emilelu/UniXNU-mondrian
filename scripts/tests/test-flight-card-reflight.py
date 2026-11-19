#!/usr/bin/env python3
"""The flight-card gate must accept a legitimate re-flight and nothing weaker.

Three things are being pinned here:

  * a card with no recorded digest still cannot be written after its image --
    the relaxation must not become a hole;
  * a re-flight passes only while the criteria are byte-identical, so appending
    a verdict is allowed and moving a threshold is not;
  * the digest covers the criteria section only, so the verdict itself is free
    to grow.

Every case runs the real gate against real files in a temp directory.
"""

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GATE = os.path.join(os.path.dirname(HERE), 'check-flight-card.py')
IMAGE_DIR = 'gpu-example-20261119'

CARD = u"""# Flight card: example

镜像 `gpu-example-20261119`。

## 1. 为什么飞

上一飞量到每次提交要清 93.2 MiB 导入帧，`publishMapped()` 中位 6,635 µs。这一飞把
`native_adreno_io_coherent` 的证明补上，看能不能让那三处跳过判据第一次生效。判据里的
数字都必须来自这一飞自己的日志，不来自上一飞的推断。

## 2. 改了什么

`drivers/PongAdreno/PongAdrenoNativeGlue.cpp` 增加 coherence 探针，默认 `pong_gpu_coherent=2`
跑证明；不放宽任何缓存策略，探针说不过就保持原样。

## 3. 前置条件

- 产物里三条探针串都在场；
- 镜像参数审计通过；
- boot claim 由 supervisor 持有。

## 4. 判据

### 4.1 有效性

先判有效性：合成器报帧、客户端 commit、`scanout frames=` 三者都要非零，否则判无效。

### 4.2 成功判据

- **S1** 没有 panic，没有 K60KEXC，没有 backboardd 崩溃。
- **S2** 恰有一条 coherence 行，且结论是 on。

### 4.3 失败规则

- **F1** 崩了就把默认值改回 0。
- **F2** 探针说没通过就不得强开再飞。

## 5. 结果登记

（飞行后由 judge 写入）
"""

VERDICT = u"""
### 5.1 飞行事实

判据没动，只是登记结果。
"""


def digest(text):
    start = text.find(u'## 4. 判据')
    end = text.find(u'## 5. 结果登记', start)
    section = text[start:end]
    lines = [line.rstrip() for line in section.splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    return hashlib.sha256(u'\n'.join(lines).encode('utf-8')).hexdigest()


class Case(object):
    def __init__(self, name, text, card_newer, expect_pass):
        self.name = name
        self.text = text
        self.card_newer = card_newer
        self.expect_pass = expect_pass


def run(case, root):
    repo = os.path.join(root, case.name)
    image_dir = os.path.join(repo, 'artifacts', IMAGE_DIR)
    os.makedirs(image_dir)
    card = os.path.join(repo, 'CARD.md')
    image = os.path.join(image_dir, 'boot.img')
    with open(card, 'w') as handle:
        handle.write(case.text)
    with open(image, 'wb') as handle:
        handle.write(b'\x00' * 64)
    # git so that the committed() check can pass
    subprocess.run(['git', 'init', '-q', repo], check=True)
    subprocess.run(['git', '-C', repo, 'add', 'CARD.md'], check=True)
    subprocess.run(['git', '-C', repo, '-c', 'user.email=t@t', '-c', 'user.name=t',
                    'commit', '-q', '-m', 'card'], check=True)
    if case.card_newer:
        os.utime(card, (os.path.getmtime(image) + 120,) * 2)
    else:
        os.utime(card, (os.path.getmtime(image) - 120,) * 2)
    env = dict(os.environ)
    env['K60_REPO'] = repo
    proc = subprocess.run([sys.executable, GATE, '--card', card, '--image', image,
                           '--repo', repo], capture_output=True, text=True, env=env)
    passed = proc.returncode == 0
    output = (proc.stdout + proc.stderr).strip()
    return passed, output


def main():
    base = CARD
    sha = digest(base)

    cases = [
        Case('fresh-before', base, False, True),
        Case('fresh-after', base, True, False),
        Case('reflight-same-criteria',
             base.replace(u'## 5. 结果登记\n\n（飞行后由 judge 写入）',
                          u'## 5. 结果登记\n\ncriteria-sha256: %s\n' % sha) + VERDICT,
             True, True),
        Case('reflight-moved-threshold',
             base.replace(u'- **S2** 恰有一条 coherence 行，且结论是 on。',
                          u'- **S2** 恰有一条 coherence 行，且结论是 on，且 publish < 2,000 us。')
                 .replace(u'## 5. 结果登记\n\n（飞行后由 judge 写入）',
                          u'## 5. 结果登记\n\ncriteria-sha256: %s\n' % sha) + VERDICT,
             True, False),
        Case('reflight-two-digests',
             base.replace(u'## 5. 结果登记\n\n（飞行后由 judge 写入）',
                          u'## 5. 结果登记\n\ncriteria-sha256: %s\ncriteria-sha256: %s\n'
                          % (sha, 'a' * 64)) + VERDICT,
             True, False),
        Case('reflight-no-digest', base + VERDICT, True, False),
    ]

    failures = []
    root = tempfile.mkdtemp(prefix='k60-card-')
    try:
        for case in cases:
            passed, output = run(case, root)
            if passed != case.expect_pass:
                failures.append('%s: expected %s, got %s\n    %s'
                                % (case.name, 'pass' if case.expect_pass else 'refuse',
                                   'pass' if passed else 'refuse',
                                   output.replace('\n', '\n    ')))
            else:
                print('  ok   %-28s %s' % (case.name, output.splitlines()[0]))
    finally:
        shutil.rmtree(root, ignore_errors=True)

    if failures:
        for item in failures:
            print('FAIL  ' + item)
        return 1
    print('TESTS OK  %d cases' % len(cases))
    return 0


if __name__ == '__main__':
    sys.exit(main())
