#!/usr/bin/env python3
"""P-221: 上游扫描不许退化成逐文件子进程。

现场：`pick-upstream.py --plan` 连续三次超时（600 s / 900 s / 300 s 全 rc=124），
输出恒为 0 行。两个原因叠在一起：

  1. `discover_branches()` 只过滤 `endswith('/HEAD')`，于是 `refs/remotes/origin/`
     本身（短名就是 `origin`）被当成一个分支。它的 `rev-parse` 返回字面量
     `origin/origin`，被写进 seen 当成水位 —— 永远不等于真实 sha，所以每次
     运行都把它当新分支。
  2. 「新分支」走的是逐文件 `git show <ref>:<path>`，三个镜像各约 5,000 个文件，
     合计 15,000+ 次子进程。

这里锁住三件事：blob id 算得对、`tree_blobs()` 只收 blob 不收 gitlink、
脏水位在 load_seen() 里被丢掉。
"""
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
GATE = os.path.join(HERE, '..', 'pick-upstream.py')


def load_gate():
    spec = importlib.util.spec_from_file_location('pick_upstream', GATE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class BlobHashTest(unittest.TestCase):
    def setUp(self):
        self.gate = load_gate()

    def test_a_known_blob_id(self):
        # `printf hello | git hash-object --stdin` == b6fc4c620b67d95f953a5c1c1230aaab5db5a1b0
        self.assertEqual(
            self.gate.blob_sha(b'hello'),
            'b6fc4c620b67d95f953a5c1c1230aaab5db5a1b0')

    def test_the_empty_blob_id(self):
        # `git hash-object -t blob /dev/null`
        self.assertEqual(
            self.gate.blob_sha(b''),
            'e69de29bb2d1d6434b8b29ae775ad8c2e48c5391')

    def test_a_file_on_disk_hashes_the_same_way(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'f')
            with io.open(path, 'wb') as handle:
                handle.write(b'hello')
            self.assertEqual(self.gate.file_blob_sha(path),
                             self.gate.blob_sha(b'hello'))

    def test_a_missing_file_is_not_an_empty_blob(self):
        # 缺失必须与「存在但为空」区分开，否则新文件会被判成 SAME。
        self.assertIsNone(self.gate.file_blob_sha('/nonexistent/k60/nope'))
        self.assertNotEqual(self.gate.file_blob_sha('/nonexistent/k60/nope'),
                            self.gate.blob_sha(b''))


class TreeBlobsTest(unittest.TestCase):
    def setUp(self):
        self.gate = load_gate()

    def test_a_real_tree_yields_blob_ids_and_skips_gitlinks(self):
        tmp = tempfile.mkdtemp()
        sub = os.path.join(tmp, 'sub')
        os.makedirs(sub)
        env = dict(os.environ, GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@t',
                   GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@t')
        run = lambda *a: subprocess.run(['git'] + list(a), cwd=tmp, env=env,
                                        capture_output=True, text=True)
        run('init', '-q')
        os.makedirs(os.path.join(tmp, 'd'))
        for rel, body in (('a.txt', 'a\n'), ('d/b.txt', 'b\n')):
            with io.open(os.path.join(tmp, rel), 'w') as handle:
                handle.write(body)
        run('add', 'a.txt', 'd/b.txt')
        run('commit', '-q', '-m', 'one')
        # 造一个 gitlink（子模块条目），它必须被跳过。
        run('update-index', '--add', '--cacheinfo',
            '160000,1111111111111111111111111111111111111111,sm')
        run('commit', '-q', '-m', 'with gitlink')

        blobs = self.gate.tree_blobs(tmp, 'HEAD')
        self.assertIn('a.txt', blobs)
        self.assertIn('d/b.txt', blobs)
        self.assertNotIn('sm', blobs)
        self.assertEqual(blobs['a.txt'], self.gate.blob_sha(b'a\n'))


class SeenWatermarkTest(unittest.TestCase):
    def setUp(self):
        self.gate = load_gate()

    def test_the_bare_origin_watermark_is_dropped(self):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, 'seen.json')
        with io.open(path, 'w') as handle:
            handle.write(
                '{"UniXNU-mondrian/origin": "origin/origin",'
                ' "UniXNU-mondrian/main": "d855ce2d430be0042babb193cd461a052a601e2a"}')
        saved = self.gate.SEEN
        self.gate.SEEN = path
        try:
            seen = self.gate.load_seen()
        finally:
            self.gate.SEEN = saved
        self.assertNotIn('UniXNU-mondrian/origin', seen)
        self.assertIn('UniXNU-mondrian/main', seen)

    def test_a_real_watermark_survives(self):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, 'seen.json')
        with io.open(path, 'w') as handle:
            handle.write('{"uefi-mondrian/main": "4a6966b351d3fe76a57be400bd7a9ff9b3628f9f"}')
        saved = self.gate.SEEN
        self.gate.SEEN = path
        try:
            seen = self.gate.load_seen()
        finally:
            self.gate.SEEN = saved
        self.assertEqual(seen['uefi-mondrian/main'],
                         '4a6966b351d3fe76a57be400bd7a9ff9b3628f9f')


class DiscoverBranchesTest(unittest.TestCase):
    def setUp(self):
        self.gate = load_gate()

    def test_origin_and_head_are_not_branches(self):
        # 直接验过滤条件，不依赖镜像是否在场：把 REPOS 指到一个真 git 仓。
        tmp = tempfile.mkdtemp()
        env = dict(os.environ, GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@t',
                   GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@t')
        run = lambda *a: subprocess.run(['git'] + list(a), cwd=tmp, env=env,
                                        capture_output=True, text=True)
        run('init', '-q')
        with io.open(os.path.join(tmp, 'f'), 'w') as handle:
            handle.write('x\n')
        run('add', 'f')
        run('commit', '-q', '-m', 'one')
        run('update-ref', 'refs/remotes/origin/main', 'HEAD')
        run('symbolic-ref', 'refs/remotes/origin/HEAD', 'refs/remotes/origin/main')
        saved = self.gate.REPOS
        self.gate.REPOS = {'probe': tmp}
        try:
            found = self.gate.discover_branches()
        finally:
            self.gate.REPOS = saved
        names = [b for _, b in found]
        self.assertEqual(names, ['main'])
        self.assertNotIn('origin', names)
        self.assertNotIn('HEAD', names)


if __name__ == '__main__':
    unittest.main(verbosity=2)
