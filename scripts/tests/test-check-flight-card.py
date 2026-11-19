#!/usr/bin/env python3
"""Tests for scripts/check-flight-card.py."""

import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
GATE = os.path.join(HERE, '..', 'check-flight-card.py')

GOOD = u"""# 上机卡：测试

## 1. 目的

判定一次虚构的上机是否成立，并给出足够长的正文以满足最小长度要求。
这段文字只是为了把卡片撑到 400 字节以上，内容不参与判定逻辑本身。
再多写两行，确保长度检查不会因为纯模板而失败。

这一段是补充说明：卡片必须同时具备「改动证据表」「已知未闭合项清单」
「先写死的判据」三部分，缺任何一部分都不应该允许上机。

## 2. 改动

| 改动 | 静态 | 单元 | 产物 |
| --- | --- | --- | --- |

## 3. 已知未闭合项

无。

## 4. 判据

成功需同时满足 S1–S2：

- **S1** 没有 panic
- **S2** 出现 `present #` 行

失败分级：

- **F1** 出 panic ⇒ 停止
- **F2** 无 panic 但 S2 不满足 ⇒ 记为 FAIL(F2)

## 5. 结果登记

- 证据目录：EVIDENCE
- 判决：PASS（S1 0 次 / S2 9 次）
"""


class FlightCardTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='flight-card-')
        self.repo = os.path.join(self.root, 'repo')
        os.makedirs(os.path.join(self.repo, 'docs'))
        subprocess.run(['git', 'init', '-q', self.repo], check=True)
        self.image = os.path.join(self.root, 'image-aaa', 'boot.img')
        os.makedirs(os.path.dirname(self.image))
        io.open(self.image, 'wb').write(b'x' * 32)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def card(self, text, commit=True, age_after_image=False):
        path = os.path.join(self.repo, 'docs', 'CARD.md')
        io.open(path, 'w', encoding='utf-8').write(text)
        past = os.path.getmtime(self.image) - 60
        future = os.path.getmtime(self.image) + 60
        os.utime(path, (future if age_after_image else past,) * 2)
        if commit:
            subprocess.run(['git', '-C', self.repo, 'add', 'docs/CARD.md'], check=True)
            subprocess.run(['git', '-C', self.repo, '-c', 'user.name=t', '-c', 'user.email=t@t',
                            'commit', '-qm', 'card'], check=True)
        return path

    def run_gate(self, card):
        return subprocess.run([sys.executable, GATE, '--card', card, '--image', self.image,
                               '--repo', self.repo], capture_output=True, text=True)

    def test_a_complete_card_passes(self):
        out = self.run_gate(self.card(GOOD.replace('EVIDENCE', 'image-aaa')))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn('2 success criteria', out.stdout)

    def test_a_card_written_after_the_image_is_refused(self):
        out = self.run_gate(self.card(GOOD.replace('EVIDENCE', 'image-aaa'), age_after_image=True))
        self.assertEqual(out.returncode, 1)
        self.assertIn('written after the image', out.stderr)

    def test_an_uncommitted_card_is_refused(self):
        out = self.run_gate(self.card(GOOD.replace('EVIDENCE', 'image-aaa'), commit=False))
        self.assertEqual(out.returncode, 1)
        self.assertIn('not committed', out.stderr)

    def test_a_card_without_failure_rules_is_refused(self):
        text = GOOD.replace(
            '- **F1** 出 panic ⇒ 停止\n- **F2** 无 panic 但 S2 不满足 ⇒ 记为 FAIL(F2)\n',
            u'（本节故意不写失败分级，用来验证门禁会拒绝这样的卡片。）\n'
            u'补充说明：失败分级必须是独立的 F 编号条目，不能写成散文段落。\n')
        out = self.run_gate(self.card(text.replace('EVIDENCE', 'image-aaa')))
        self.assertEqual(out.returncode, 1)
        self.assertIn('no F<n> failure rule', out.stderr)

    def test_a_card_without_success_criteria_is_refused(self):
        text = GOOD.replace('- **S1** 没有 panic\n- **S2** 出现 `present #` 行\n', '')
        out = self.run_gate(self.card(text.replace('EVIDENCE', 'image-aaa')))
        self.assertEqual(out.returncode, 1)
        self.assertIn('no S<n> success criterion', out.stderr)

    def test_a_card_that_never_names_the_image_is_refused(self):
        out = self.run_gate(self.card(GOOD.replace('EVIDENCE', 'somewhere-else')))
        self.assertEqual(out.returncode, 1)
        self.assertIn('never names the image', out.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
