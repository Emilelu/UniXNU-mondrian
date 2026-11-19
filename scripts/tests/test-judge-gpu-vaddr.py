#!/usr/bin/env python3
"""Self-test for scripts/judge-gpu-vaddr.py.

The point of these cases is that each one can fail: an earlier judge of ours passed on a log
that did not contain the field it was judging (P-242), so every case here either proves the
judge refuses something it must refuse, or proves it reaches a conclusion from data that is
in the log.

    python3 scripts/tests/test-judge-gpu-vaddr.py
"""

import importlib.util
import io
import os
import sys

REPO = os.environ.get("K60_REPO") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
JUDGE = os.path.join(REPO, "scripts", "judge-gpu-vaddr.py")


def load():
    spec = importlib.util.spec_from_file_location("judge_gpu_vaddr", JUDGE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compositor(frames=40):
    return f"MiniIOMobileFramebuffer: {frames} frames in 2000 ms (20 a second), 14036 us each in the driver\n"


def commit(n=40):
    return f"KXPC 1 x pc=0x1\nPong Metal: c{n}/0 d{n} p14 x4 R6 D0 F0 M18 C0 B2\n"


def stage(frame, addr, prepare=10, total=20000, bytes_=18432000):
    return (f"PONG SCANOUT: frame={frame} prepare={prepare} us offer_and_copy={total} us"
            f" total={total} us addr=0x{addr} bytes={bytes_}\n")


def client(frame, import_us, encode=500, copy=20000, sum_=20000, imports=None):
    imports = frame if imports is None else imports
    return (f"Pong Metal: scanout frames={frame} at 88.081 s; last frame: wait=240 us"
            f" copy={copy} us done=16 us; imports={imports} import={import_us} us"
            f" encode={encode} us submit=400 us gpu=1600 us sum={sum_} us status=0x0\n")


PANEL = "K60 PANEL: INTF1 after the UI frame te 120/s … period 7447 us\n"


def flight(pairs, panel=True, extra=""):
    """pairs: list of (frame, addr, import_us)."""
    text = PANEL if panel else ""
    text += compositor() + commit()
    for frame, addr, import_us in pairs:
        text += stage(frame, addr) + client(frame, import_us)
    return text + extra


CASES = []


def case(name):
    def wrap(fn):
        CASES.append((name, fn))
        return fn
    return wrap


@case("every frame a fresh address is H1")
def _(m):
    text = flight([(1, "ffffa000", 14378), (2, "ffffb000", 65), (3, "ffffc000", 15184)])
    code, out = m.report(text)
    assert code == 0, out
    assert "H1:" in out and "addresses: 3 distinct over 3 frames" in out, out


@case("a repeated address that stayed expensive is H2")
def _(m):
    text = flight([(1, "ffffa000", 14000), (2, "ffffa000", 15000)])
    code, out = m.report(text)
    assert code == 0, out
    assert "H2:" in out and "do NOT start the token work" in out, out


@case("a repeated address that got cheap is neither, and the judge says so")
def _(m):
    text = flight([(1, "ffffa000", 14000), (2, "ffffa000", 65)])
    code, out = m.report(text)
    assert code == 1, out
    assert "H1'" in out, out


@case("zero frames is invalid, not a failure of the criteria")
def _(m):
    text = "MiniIOMobileFramebuffer: 0 frames in 2000 ms (0 a second)\n" + stage(1, "ffffa000")
    code, out = m.report(text)
    assert code == 3 and "INVALID" in out, out


@case("DeviceLost makes a run invalid even when frames were rendered")
def _(m):
    text = flight([(1, "ffffa000", 14378)]) + "native-metal: surface import refused: no-copy buffer: DeviceLost\n" * 3
    code, out = m.report(text)
    assert code == 3 and "DeviceLost" in out, out


@case("an image without the probe fails the path layer, not the validity layer")
def _(m):
    text = compositor() + commit() + "PONG SCANOUT: frame=1 prepare=10 us offer_and_copy=20000 us total=20000 us\n"
    text += client(1, 14378)
    code, out = m.report(text)
    assert code == 1 and "probe did not reach the image" in out, out


@case("imports disagreeing with the frame number fails")
def _(m):
    text = flight([(1, "ffffa000", 14378), (2, "ffffb000", 65)]) + client(3, 70, imports=1)
    code, out = m.report(text)
    assert code == 1 and "S7 fails" in out, out


@case("a missing log file exits 2")
def _(m):
    assert m.main(["judge", os.path.join(REPO, "no-such-evidence-dir")]) == 2


@case("the report names the panel rate so a stalled panel is visible")
def _(m):
    code, out = m.report(flight([(1, "ffffa000", 14378)]))
    assert "panel: 120 Hz" in out, out


def run():
    module = load()
    failures = 0
    for name, fn in CASES:
        try:
            fn(module)
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {name}\n     {exc}")
        else:
            print(f"ok   {name}")
    print(f"\nTESTS {'OK' if not failures else 'FAILED'}: {len(CASES) - failures}/{len(CASES)} cases")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
