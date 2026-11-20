#!/usr/bin/env python3
"""test-audio27-sheng-refs.py - the sheng inventory gate has to fail when it should.

Ten cases cover the happy path, inventory and citation drift, repeated or
missing research paths, and a machine with no checkout at all.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CHECKER = REPO / 'scripts' / 'check-audio27-sheng-refs.py'

SERIES = "bbb-sched.patch\naaa-audio-thing.patch\n"
KERN_EXEC = "diff --git a/bsd/kern/kern_exec.c b/bsd/kern/kern_exec.c\n--- a/bsd/kern/kern_exec.c\n+++ b/bsd/kern/kern_exec.c\n"
SCHED = "diff --git a/osfmk/kern/sched_clutch.c b/osfmk/kern/sched_clutch.c\n--- a/osfmk/kern/sched_clutch.c\n+++ b/osfmk/kern/sched_clutch.c\n"
GENI = "line one\nline two\nline three\n"
AUDIO_PATCH = "diff --git a/drivers/PongAudio/PongAudioGeniI2c.c b/drivers/PongAudio/PongAudioGeniI2c.c\n--- a/drivers/PongAudio/PongAudioGeniI2c.c\n+++ b/drivers/PongAudio/PongAudioGeniI2c.c\n"


def page(audio_row=None, sched_row=None, extra=''):
    """The page fixture: two rows, one judged audio, one judged no."""
    if audio_row is None:
        audio_row = "| " + chr(96) + "aaa-audio-thing.patch" + chr(96) + " | audio | the slot | sheng:patches/xnu-12377/aaa-audio-thing.patch:2 |"
    if sched_row is None:
        sched_row = "| " + chr(96) + "bbb-sched.patch" + chr(96) + " | no | scheduling | only sched_clutch.c |"
    return '\n'.join([
        "# page",
        "",
        "| patch | verdict | what | why |",
        "| --- | --- | --- | --- |",
        audio_row,
        sched_row,
        extra,
    ]) + '\n'


def sources(count=1):
    items = []
    names = ("package/GeniI2c.c", "patches/xnu-12377/aaa-audio-thing.patch",
             "patches/xnu-12377/bbb-sched.patch")
    for index in range(count):
        items.append('[[subsystem.audio.required]]')
        items.append('path = "UniXNU-sheng/%s"' % names[index])
        items.append('why = "reference for the audio port"')
        items.append('examined = "2026-11-20"')
        items.append('finding = "it reads the fifo depth from the hardware parameter register instead of hardcoding it."')
        items.append('')
    items.append("[subsystem.battery]")
    items.append('why = "battery"')
    return '\n'.join(items) + '\n'


def tree(root, page_text=None, sources_text=None, series=SERIES, geni=GENI, audio=KERN_EXEC, sched=None):
    (root / 'docs' / 'research' / 'audio').mkdir(parents=True)
    (root / 'docs' / 'research' / 'SOURCES.toml').write_text(sources_text if sources_text is not None else sources(3))
    (root / 'docs' / 'research' / 'audio' / 'IOS27-SHENG-REFS.md').write_text(page_text if page_text is not None else page())
    sheng = root / 'sheng' / 'patches' / 'xnu-12377'
    sheng.mkdir(parents=True)
    (sheng / "series").write_text(series)
    (sheng / "aaa-audio-thing.patch").write_text(audio)
    (sheng / "bbb-sched.patch").write_text(sched if sched is not None else SCHED)
    pkg = root / 'sheng' / 'package'
    pkg.mkdir(parents=True)
    (pkg / "GeniI2c.c").write_text(geni)
    return sheng


def run(where):
    """(rc, output)."""
    sheng = where / 'sheng'
    env = dict(os.environ)
    env['SHENG_REPO'] = str(sheng)
    done = subprocess.run([sys.executable, str(CHECKER), str(where)], cwd=str(where), env=env,
                          capture_output=True, text=True)
    return done.returncode, done.stdout + done.stderr


def main():
    failures = 0
    cases = 0

    def check(name, condition, detail=""):
        nonlocal failures
        if not condition:
            failures += 1
            print("  FAIL %s%s" % (name, (": " + detail) if detail else ""))

    def case(name, setup, want_rc, want_text):
        nonlocal cases
        cases += 1
        root = Path(tempfile.mkdtemp(prefix='shengrefs-'))
        try:
            setup(root)
            rc, output = run(root)
            check(name + " rc", rc == want_rc, "wanted %d, got %d\n%s" % (want_rc, rc, output))
            check(name + " text", want_text in output, "wanted %r in\n%s" % (want_text, output))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    case("consistent", lambda root: tree(root), 0, "SHENG REFS OK 2 listed patches (1 audio, 0 partial, 1 no)")

    def forgotten(root):
        tree(root, page_text=page(sched_row=""))
    case("a series patch with no row", forgotten, 1, "the series lists bbb-sched.patch and the page has no row")

    def contradicted(root):
        text = page(sched_row="| " + chr(96) + "bbb-sched.patch" + chr(96) + " | no | whatever | nothing |")
        tree(root, page_text=text, sched=AUDIO_PATCH)
    case("a no verdict the patch contradicts", contradicted, 1, "is judged no and touches")

    def uncited(root):
        tree(root, page_text=page(audio_row="| " + chr(96) + "aaa-audio-thing.patch" + chr(96) + " | audio | the slot | look at the patch |"))
    case("an audio row with no file:line", uncited, 1, "gives no sheng:path:line")

    def ghost(root):
        tree(root, page_text=page(extra="see sheng:package/Ghost.c:4 too"))
    case("a citation to a file that is not there", ghost, 1, "has no package/Ghost.c")

    def past_end(root):
        tree(root, page_text=page(extra="see sheng:package/GeniI2c.c:4 too"))
    case("a citation past the end", past_end, 1, "cannot be read")

    def empty_record(root):
        tree(root, sources_text='[subsystem.audio]\nwhy = "audio"\n\n[subsystem.battery]\nwhy = "battery"\n')
    case("a record with no sheng path", empty_record, 1, "fewer than 3")

    def repeated_source(root):
        tree(root, sources_text=sources(3).replace(
            "patches/xnu-12377/bbb-sched.patch", "package/GeniI2c.c"))
    case("repeated paths do not count as distinct", repeated_source, 1, "2 distinct sheng path(s)")

    def missing_source(root):
        tree(root, sources_text=sources(3).replace("package/GeniI2c.c", "package/Ghost.c"))
    case("a missing research path is named", missing_source, 1, "checkout: package/Ghost.c")

    def no_checkout(root):
        tree(root)
        shutil.rmtree(root / 'sheng')
    case("no sheng checkout", no_checkout, 3, "nothing to compare")

    if failures:
        print("TESTS FAILED %d of %d" % (failures, cases))
        return 1
    print("TESTS OK %d cases" % cases)
    return 0


if __name__ == '__main__':
    sys.exit(main())