#!/usr/bin/env python3
"""porting-gate 的内核产物必须由 K60_OUT 指名（P-230 同族）。

判断链：门禁的 [F] 段问的是「你准备上机的那个 kernel.macho 是不是新鲜」。
这个问题的对象只能来自调用者；写死一棵共享 out 时，那棵树一旦被清理（2026-11-17
磁盘回收就删了 out-baseline），门禁就报 "kernel.macho 存在 missing"，看上去像
「没构建过」，其实是在量一个已经不存在的目录。

本测试不跑真门禁（真门禁会读 787 个文件的镜像），只钉住三件事：
1. 脚本里不出现写死的 out 路径；
2. 给了 K60_OUT 时能通过 glob 找到产物（板级目录名跟 defconfig 走）；
3. 没给 K60_OUT 时是「跳过」而不是「失败」。
"""
import importlib.util
import os
import pathlib
import re
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
GATE = HERE.parent / 'porting-gate.py'
SRC = GATE.read_text(encoding='utf-8')

FAILS = []


def check(name, condition, detail=''):
    if condition:
        print('ok   %s' % name)
    else:
        print('FAIL %s %s' % (name, detail))
        FAILS.append(name)


def test_no_shared_out_is_hardcoded():
    bad = re.findall(r"/opt/k60/trees/[A-Za-z0-9_.-]+/mondrian/[^'\" ]*kernel\.macho", SRC)
    check('the script names no shared out for the kernel', not bad, str(bad))
    check('the kernel comes from K60_OUT', "os.environ.get('K60_OUT')" in SRC)
    check('the lookup is a recursive glob', "recursive=True" in SRC)


def test_an_unset_out_skips_instead_of_failing():
    marker = "未指名 K60_OUT"
    check('an unset K60_OUT is reported as a skip', marker in SRC)
    # the skip must not be a hard failure: it is the branch that says hard=False
    idx = SRC.find(marker)
    line_start = SRC.rfind('\n', 0, idx) + 1
    line_end = SRC.find('\n', idx)
    line = SRC[line_start:line_end]
    check('the skip is not blocking', 'hard=False' in line, line)


def test_the_glob_finds_a_board_dir_by_defconfig_name():
    with tempfile.TemporaryDirectory() as tmp:
        for board in ('mondrian', 'mondrian_wifi'):
            kernel = pathlib.Path(tmp) / board / 'ipados-16.6.1-20G81' / board / 'kernel' / 'kernel.macho'
            kernel.parent.mkdir(parents=True, exist_ok=True)
            kernel.write_bytes(b'x')
        import glob as globmod
        hits = sorted(globmod.glob(os.path.join(tmp, '**', 'kernel', 'kernel.macho'), recursive=True),
                      key=os.path.getmtime, reverse=True)
        check('both board layouts are visible', len(hits) == 2, str(hits))


def main():
    test_no_shared_out_is_hardcoded()
    test_an_unset_out_skips_instead_of_failing()
    test_the_glob_finds_a_board_dir_by_defconfig_name()
    print('TESTS %s (%d failure(s))' % ('OK' if not FAILS else 'FAILED', len(FAILS)))
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
