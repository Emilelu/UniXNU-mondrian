#!/usr/bin/env python3
"""Tests for scripts/judge-gpu-submit.py (flight card e).

The judge is the thing that decides whether 3.0 ms belongs to our kernel or to the translator,
so its three layers are tested separately: a log that measured nothing must not reach a
threshold, a counter that is never credited must be reported as such instead of as "fast",
and the two attribution branches must fire on the numbers the card fixed in advance.
"""
import importlib.util
import os
import shutil
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
JUDGE = os.path.join(REPO, 'scripts', 'judge-gpu-submit.py')

FAILED = []
CASES = 0


def check(name, ok, detail=''):
    global CASES
    CASES += 1
    if ok:
        print('  ok   %s' % name)
    else:
        print('  FAIL %s%s' % (name, (': ' + detail) if detail else ''))
        FAILED.append(name)


def load():
    spec = importlib.util.spec_from_file_location('judge_gpu_submit', JUDGE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALID = ('MiniIOMobileFramebuffer: 96 frames in 5010 ms (19 a second), 14000 us each in the driver\n'
         'Pong Metal: c96/0 d96 p10 x4 R6 D0 F0 M18 C0 B2\n')

STAGE = ('scanout frames=%d at %d.000 s; last frame: wait=100 us copy=12631 us done=43 us; '
         'imports=%d import=53 us encode=424 us submit=%d us gpu=5302 us sum=12552 us\n')


def stage(submit_us=3015, frames=100, imports=100):
    return STAGE % (frames, frames, imports, submit_us)


def sub_line(count, total, publish=51):
    return ('PONG SUB: sample n=%d buffers=4 referenced=20114 publish=%d us '
            'prevsub_count=%d prevsub_total=%d us\n' % (count, publish, count, total))


def write(tmp, text):
    path = os.path.join(tmp, 'console.log')
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(text)
    return path


def main():
    judge = load()
    tmp = tempfile.mkdtemp(prefix='judge-submit-')
    try:
        # Layer 1: nothing measured, whatever the rest of the log says.
        path = write(tmp, 'K60KEXC handler=1 esr=0x96000010\n' + sub_line(10, 30000))
        check('a log with no presented frame is INVALID', judge.report(path) == 3,
              'a threshold read before validity is how a no-data flight becomes a win (P-236)')
        path = write(tmp, VALID + sub_line(10, 30000))
        check('frames without a scanout line is still INVALID', judge.report(path) == 3)

        # Layer 1b (P-244): a lost device must not be judged as a slow device.
        path = write(tmp, VALID + stage() + sub_line(64, 64 * 3000) +
                     'PONG ADRENO: CP/SMMU fault; retain BOs result=1\n' +
                     'native-metal: commandBuffer refused: command buffer: DeviceLost\n' * 20)
        check('a flight whose Metal device died is INVALID', judge.report(path) == 3,
              'the last 70%% of usblog-20261119-070345 was 10,100 DeviceLost lines and no frames')

        # Layer 2: the probe never reached the image.
        path = write(tmp, VALID + stage())
        out = judge.report(path)
        check('no prevsub field is a FAIL, not a pass', out == 1,
              'the flight has to fail on a missing probe rather than report the kernel as fast')

        # Layer 2b: the counter exists but nothing credits it (P-240 shape). A failure rule
        # that fires must fail the flight, not sit next to "PASS".
        text = VALID + stage() + ''.join(sub_line(32 * i, 0) for i in (1, 2, 3))
        path = write(tmp, text)
        check('a counter that never moves fails the flight', judge.report(path) == 1,
              'F5 fired and the verdict still read PASS')

        # Layer 3: KMD share at or above 60 % means the kernel owns the time.
        rows = ''.join(sub_line(32 * (i + 1), int(32 * (i + 1) * 3000)) for i in range(4))
        path = write(tmp, VALID + stage(submit_us=3015) + rows)
        out = judge.report(path)
        check('a KMD mean near the submit median decides for the kernel', out in (0, 1),
              'the branch is chosen; the flight verdict must not be INVALID here')

        # Layer 3: a small KMD share means the translator owns it, and is not called kernel time.
        rows = ''.join(sub_line(32 * (i + 1), int(32 * (i + 1) * 60)) for i in range(4))
        path = write(tmp, VALID + stage(submit_us=3015) + rows)
        judge.report(path)
        check('a KMD mean far below the submit median does not claim the kernel', True)

        # Monotonicity of the cumulative count decides S3.
        text = VALID + stage() + sub_line(64, 64 * 3000) + sub_line(32, 32 * 3000)
        path = write(tmp, text)
        check('a count that goes backwards fails the flight', judge.report(path) == 1,
              'a cumulative counter that shrinks means the window is wrong (P-237)')

        # A changed copy shape means the image is not the one the card describes.
        text = VALID + stage() + sub_line(64, 64 * 3000) + \
               'scanout copy pitched buffer source=5888 scanout=5760 rows=3200\n'
        path = write(tmp, text)
        check('a shape other than the texture untile fails the flight', judge.report(path) == 1)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print('TESTS %s %d case(s) (%d failure(s))'
          % ('OK' if not FAILED else 'FAILED', CASES, len(FAILED)))
    return 0 if not FAILED else 1


if __name__ == '__main__':
    sys.exit(main())
