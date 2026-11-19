#!/usr/bin/env python3
"""test-judge-gpu-flight.py — P-236/P-237 的可执行判据。

三条必须永远成立的性质：
1. 零帧日志 ⇒ 无效，且 --require-valid 以 3 退出（不能把"没测到"判成"失败规则命中"）。
2. 有帧、有客户端提交、有 scanout 行 ⇒ 有效。
3. 探针窗口层必须指出计数变小的相邻样本，并禁止 cachebytes/n 这类推算。
"""

import importlib.util
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(REPO, "scripts", "judge-gpu-flight.py")

FAILED = []


def load():
    spec = importlib.util.spec_from_file_location("judge_gpu_flight", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def case(name, condition, detail=""):
    if condition:
        print("ok   %s" % name)
    else:
        print("FAIL %s %s" % (name, detail))
        FAILED.append(name)


ZERO_FRAME = """Early boot complete
Pong Metal: c0/0 d0 p14 x4 R6 D0 F0 M18 C0 B2 status=0x0
"""

STUCK_CLIENT = """Pong Metal: c0/0 d0 p14 x4 R6 D0 F0 M18 C0 B2 status=0x0
MiniIOMobileFramebuffer: 22 frames in 54713 ms (0 a second)
"""

GOOD = """Pong Metal: c754/0 d754 p42 x4 R61 D551 F15 M4500 C0 B8 status=0x0
MiniIOMobileFramebuffer: 359 frames in 49000 ms (7 a second)
scanout frames=360 at 49.000 s; last frame: wait=46 us copy=25347 us done=49 us
"""

VM_LINES = """PONG VM: publish sample n=480 objects=595 imported=39 owned=0 combined=556 bytes=690958336 us=3047 calls=538 cachebytes=119365632
PONG VM: publish sample n=512 objects=595 imported=39 owned=0 combined=556 bytes=690958336 us=10341 calls=412 cachebytes=99602432
PONG VM: publish sample n=544 objects=595 imported=39 owned=0 combined=556 bytes=690958336 us=3142 calls=412 cachebytes=99602432
PONG SUB: sample n=544 buffers=16 referenced=47816 publish=10152 us
"""


def main():
    module = load()
    with tempfile.TemporaryDirectory() as scratch:
        zero = os.path.join(scratch, "zero.log")
        stuck = os.path.join(scratch, "stuck.log")
        good = os.path.join(scratch, "good.log")
        windows = os.path.join(scratch, "windows.log")
        for path, body in ((zero, ZERO_FRAME), (stuck, STUCK_CLIENT), (good, GOOD), (windows, GOOD + VM_LINES)):
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(body)

        zero_verdict = module.validity(module.read_log(zero))
        case("a run with no frame at all is invalid", zero_verdict["valid"] is False, zero_verdict)
        case(
            "the invalid reason names the missing compositor frame line",
            any("MiniIOMobileFramebuffer" in reason for reason in zero_verdict["reasons"]),
            zero_verdict["reasons"],
        )

        stuck_verdict = module.validity(module.read_log(stuck))
        case("frames without a single client commit are still invalid", stuck_verdict["valid"] is False, stuck_verdict)
        case("the frame count is still reported for the record", stuck_verdict["frames"] == 22, stuck_verdict["frames"])

        good_verdict = module.validity(module.read_log(good))
        case("a presenting run with commits and present() is valid", good_verdict["valid"] is True, good_verdict)
        case("the client commit count is read from the source format", good_verdict["client_commits"] == 754, good_verdict)

        report = module.window_report(module.vm_samples(module.read_log(windows)))
        case("counters that shrink prove they are not cumulative", report["either_decreases"] >= 1, report)
        case(
            "shrinkage is reported per counter, not merged into one number",
            report["calls_decreases"] >= 1 and report["cachebytes_decreases"] >= 1,
            report,
        )
        case(
            "identical inputs with different durations are flagged",
            len(report["same_input_spread"]) >= 1,
            report["same_input_spread"],
        )

        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        invalid_rc = subprocess.run(
            [sys.executable, SCRIPT, zero, "--require-valid"],
            capture_output=True,
            env=env,
        ).returncode
        case("--require-valid exits 3 on an invalid run", invalid_rc == 3, invalid_rc)
        valid_rc = subprocess.run(
            [sys.executable, SCRIPT, good, "--require-valid"],
            capture_output=True,
            env=env,
        ).returncode
        case("--require-valid exits 0 on a valid run", valid_rc == 0, valid_rc)
        missing_rc = subprocess.run(
            [sys.executable, SCRIPT, os.path.join(scratch, "absent.log")],
            capture_output=True,
            env=env,
        ).returncode
        case("a missing log exits 2 rather than pretending to judge", missing_rc == 2, missing_rc)

        judged = subprocess.run(
            [sys.executable, SCRIPT, windows],
            capture_output=True,
            env=env,
        )
        text = judged.stdout.decode("utf-8", "replace")
        case("the report refuses per-submit cache bytes inference", "禁止用 cachebytes/n" in text, text[-400:])
        case("the report states referenced is indirect-buffer only", "indirect-buffer" in text, text[-400:])

    if FAILED:
        print("\nTESTS FAILED %d: %s" % (len(FAILED), ", ".join(FAILED)))
        return 1
    print("\nTESTS OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
