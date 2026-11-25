#!/usr/bin/env python3
"""judge-gpu-flight.py — 上机日志的有效性层与探针窗口层。

为什么有这个脚本：2026-11-18 的两份日志各踩了一个坑，而当时的判决脚本只存在于
`E:/iOS Port/Work/scratch/` 里，没有进仓库，于是同一类误读无法被门禁挡住。

坑 1（P-236）：`usblog-20261118-185517` 完整、无 panic，但合成器一次也没提交帧，
于是 `scanout` 行一条都没有。判据全部"失败"，可那一飞什么都没测——判据失败与
没有数据是两件事，零帧的日志必须先判无效，不能算失败规则命中。

坑 2（P-237）：`PONG VM: publish sample … n=2688 … calls=565 cachebytes=139517952`
被读成"开机以来累计"，于是算出"每次提交只维护 52 KB"，进而得出"耗时按对象数增长"。
实际上那两个量是**单次被抽样调用**前后读取的全局计数差，相邻样本还会变小
（`n=480 calls=538` → `n=512 calls=412`），根本不可能是累计值。

用法：
  python3 scripts/judge-gpu-flight.py <console.log>            # 只打印结论
  python3 scripts/judge-gpu-flight.py <console.log> --require-valid
  退出码：0 有效；3 无效（无数据）；2 文件读不到。
"""

import argparse
import os
import re
import sys

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

FRAMES_RE = re.compile(r"MiniIOMobileFramebuffer:\s*(\d+)\s*frames in\s*(\d+)\s*ms")
CLIENT_RE = re.compile(r"Pong Metal: c(\d+)/0 d(\d+)")
SCANOUT_RE = re.compile(r"scanout frames=(\d+) at ")
STAGE_RE = re.compile(r"scanout frames=(\d+) at .*sum=(\d+) us")
VM_RE = re.compile(
    r"PONG VM: publish sample n=(\d+) objects=(\d+) imported=(\d+) owned=(\d+) "
    r"combined=(\d+) bytes=(\d+) us=(\d+) calls=(\d+) cachebytes=(\d+)"
)
SUB_RE = re.compile(
    r"PONG SUB: sample n=(\d+) buffers=(\d+) referenced=(\d+) publish=(\d+) us"
)


def read_log(path):
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def validity(text):
    """先判这一层：没有帧就什么都没有测到（P-236）。"""
    frames = [int(m.group(1)) for m in FRAMES_RE.finditer(text)]
    clients = [(int(m.group(1)), int(m.group(2))) for m in CLIENT_RE.finditer(text)]
    scanout = [int(m.group(1)) for m in SCANOUT_RE.finditer(text)]
    best_frames = max(frames) if frames else 0
    best_client = max((c for c, _ in clients), default=0)
    reasons = []
    if not frames:
        reasons.append("no MiniIOMobileFramebuffer frame line: the compositor never reported a frame")
    elif best_frames == 0:
        reasons.append("the compositor reported 0 frames")
    if best_client == 0:
        reasons.append("the render client never committed (Pong Metal: c0)")
    if not scanout:
        reasons.append("no scanout frame line: present() never ran")
    return {
        "frames": best_frames,
        "client_commits": best_client,
        "scanout_lines": len(scanout),
        "valid": not reasons,
        "reasons": reasons,
    }


def vm_samples(text):
    out = []
    for m in VM_RE.finditer(text):
        out.append(
            {
                "n": int(m.group(1)),
                "objects": int(m.group(2)),
                "imported": int(m.group(3)),
                "owned": int(m.group(4)),
                "combined": int(m.group(5)),
                "bytes": int(m.group(6)),
                "us": int(m.group(7)),
                "calls": int(m.group(8)),
                "cachebytes": int(m.group(9)),
            }
        )
    return out


def sub_samples(text):
    return [
        {
            "n": int(m.group(1)),
            "buffers": int(m.group(2)),
            "referenced": int(m.group(3)),
            "publish_us": int(m.group(4)),
        }
        for m in SUB_RE.finditer(text)
    ]


def window_report(vms):
    """P-237：把计数差说清单次窗口，并验证它不是累计值。"""
    calls_decreases = 0
    bytes_decreases = 0
    either_decreases = 0
    pairs = 0
    for previous, current in zip(vms, vms[1:]):
        pairs += 1
        calls_down = current["calls"] < previous["calls"]
        bytes_down = current["cachebytes"] < previous["cachebytes"]
        calls_decreases += int(calls_down)
        bytes_decreases += int(bytes_down)
        either_decreases += int(calls_down or bytes_down)
    identical = {}
    for sample in vms:
        key = (sample["objects"], sample["bytes"], sample["calls"], sample["cachebytes"])
        identical.setdefault(key, []).append(sample["us"])
    spread = [
        (key, values) for key, values in identical.items() if len(values) > 1 and max(values) - min(values) > 1000
    ]
    return {
        "pairs": pairs,
        "calls_decreases": calls_decreases,
        "cachebytes_decreases": bytes_decreases,
        "either_decreases": either_decreases,
        "same_input_spread": spread,
    }


def median(values):
    ordered = sorted(values)
    if not ordered:
        return 0
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) // 2


def main(argv=None):
    parser = argparse.ArgumentParser(description="judge a GPU flight log: validity first, then the probe windows")
    parser.add_argument("log")
    parser.add_argument("--require-valid", action="store_true", help="exit 3 when the log measured nothing")
    args = parser.parse_args(argv)
    if not os.path.exists(args.log):
        print("❌ 读不到日志: %s" % args.log)
        return 2
    text = read_log(args.log)
    verdict = validity(text)
    print("=== 1) 有效性（P-236）===")
    print("frames=%d client_commits=%d scanout_lines=%d" % (verdict["frames"], verdict["client_commits"], verdict["scanout_lines"]))
    if verdict["valid"]:
        print("✅ 这一飞测到了东西：合成器出帧、客户端提交、present() 执行过")
    else:
        print("❌ 无效：这一飞没有测到任何东西，下面的判据一律不得判失败")
        for reason in verdict["reasons"]:
            print("   - %s" % reason)

    stages = [int(m.group(2)) for m in STAGE_RE.finditer(text)]
    vms = vm_samples(text)
    subs = sub_samples(text)
    print("\n=== 2) 采样 ===")
    print("stage=%d vm=%d sub=%d" % (len(stages), len(vms), len(subs)))
    if stages:
        print("sum 中位 = %d us" % median(stages))

    if vms:
        print("\n=== 3) 探针窗口（P-237）===")
        report = window_report(vms)
        print("cachebytes 中位 = %.1f MiB, calls 中位 = %d（均为单次被抽样调用窗口内的计数差）" % (
            median([v["cachebytes"] for v in vms]) / (1024 * 1024),
            median([v["calls"] for v in vms]),
        ))
        print("相邻样本里 calls 变小 %d 对、cachebytes 变小 %d 对（合计 %d / %d 对至少一项变小）"
              " ⇒ 这两个量不是开机累计值" % (
                  report["calls_decreases"],
                  report["cachebytes_decreases"],
                  report["either_decreases"],
                  report["pairs"],
              ))
        if report["either_decreases"] == 0 and report["pairs"] > 0:
            print("⚠️ 所有相邻样本都单调增，仍不能据此断言累计；窗口语义由代码位置决定")
        print("❌ 禁止用 cachebytes/n 或 us/objects 推算「每次提交的清 cache 字节」与「每对象开销」")
        if report["same_input_spread"]:
            print("相同输入（objects/bytes/calls/cachebytes 全同）而耗时不同的样本组：")
            for key, values in report["same_input_spread"][:5]:
                print("   objects=%d bytes=%d calls=%d cachebytes=%d -> us=%s" % (key[0], key[1], key[2], key[3], values))
            print("   ⇒ 对象数或请求字节数都不能单独解释耗时")
    if subs:
        print("\n=== 4) 提交引用范围 ===")
        print("buffers 中位 = %d, referenced 中位 = %d B" % (
            median([s["buffers"] for s in subs]),
            median([s["referenced"] for s in subs]),
        ))
        print("referenced 是 indirect-buffer 字节，不是 GPU 间接访问的全部资源；不得据此限缩维护范围")

    if args.require_valid and not verdict["valid"]:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
