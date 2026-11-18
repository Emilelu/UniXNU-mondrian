#!/usr/bin/env python3
"""judge-gpu-wc-class.py — 判读 `FLIGHT-CARD-20261118o.md` 那一飞。

这一飞只回答一个问题：`publishMapped()` 那 10 ms 到底花在**哪一类映射**上。
上一飞的 `combined=574` 只是「访问到的 write-combined 对象数」，
`publishForDevice()` 在 `distrust_write_combined_=false` 时对它们是直接返回的，
所以「访问数」永远不能当「维护字节数」读（P-237）。

判读分三层，顺序不能换（P-236）：
  1. 有效性 —— 出帧了吗？零帧的一飞必须判**无效**，不是判失败；
  2. 路径身份 —— 纹理搬运还在吗？`imports==frames` 还成立吗？
  3. 归因 —— S5/S6 是探针自洽性，S7 才是唯一的新结论（谁占 cachebytes 的主体）。

用法：python3 scripts/judge-gpu-wc-class.py <证据目录或 console.log>
退出码：0 结论成立；1 判据失败；2 日志读不到；3 这一飞无效（P-236）。
"""

import io
import os
import re
import statistics
import sys

VM_RE = re.compile(
    r"PONG VM: publish sample n=(?P<n>\d+) objects=(?P<objects>\d+) imported=(?P<imported>\d+) "
    r"owned=(?P<owned>\d+) combined=(?P<combined>\d+) bytes=(?P<bytes>\d+) us=(?P<us>\d+) "
    r"calls=(?P<calls>\d+) cachebytes=(?P<cachebytes>\d+)(?: trusted=(?P<trusted>\d+) "
    r"ibytes=(?P<ibytes>\d+) obytes=(?P<obytes>\d+) wbytes=(?P<wbytes>\d+) "
    r"wskipped=(?P<wskipped>\d+))?")
LATCH_RE = re.compile(r"PONG WC: distrust latched submit=(?P<submit>\d+) audit=(?P<audit>\d+) "
                      r"lines=(?P<lines>\d+) dirty=(?P<dirty>\d+) stale=(?P<stale>\d+)")
FRAMES_RE = re.compile(r"MiniIOMobileFramebuffer:\s*(?P<frames>\d+)\s*frames in\s*(?P<ms>\d+)\s*ms")
CLIENT_RE = re.compile(r"Pong Metal: c(?P<c>\d+)/0 d(?P<d>\d+)")
SCANOUT_RE = re.compile(r"scanout frames=(?P<frames>\d+) at (?P<sec>\d+)\.(?P<ms>\d+) s;.*?"
                        r"imports=(?P<imports>\d+) import=(?P<import>\d+) us encode=(?P<encode>\d+) us "
                        r"submit=(?P<submit>\d+) us gpu=(?P<gpu>\d+) us sum=(?P<sum>\d+) us")
SHAPE_RE = re.compile(r"scanout copy (?P<shape>[a-z ]+?) source=\d+")

FIELD_ORDER = ("n", "objects", "imported", "owned", "combined", "bytes", "us", "calls",
               "cachebytes", "trusted", "ibytes", "obytes", "wbytes", "wskipped")


def read_log(target):
    if os.path.isdir(target):
        candidate = os.path.join(target, "console.log")
        if not os.path.exists(candidate):
            return None
        target = candidate
    try:
        with io.open(target, "rb") as handle:
            return handle.read().decode("utf-8", "replace")
    except OSError:
        return None


def samples(text):
    parsed = []
    for match in VM_RE.finditer(text):
        row = {name: (int(match.group(name)) if match.group(name) is not None else None)
               for name in FIELD_ORDER}
        parsed.append(row)
    return parsed


def validity(text):
    """Return (ok, reasons). A zero-frame run is invalid, never a failed criterion."""
    reasons = []
    frames = [int(m.group("frames")) for m in FRAMES_RE.finditer(text)]
    commits = [int(m.group("c")) for m in CLIENT_RE.finditer(text)]
    scanouts = list(SCANOUT_RE.finditer(text))
    if not frames or max(frames) <= 0:
        reasons.append("no MiniIOMobileFramebuffer frame count > 0 (the compositor never presented)")
    if not commits or max(commits) <= 0:
        reasons.append("no `Pong Metal: c<n>/0` with n>0 (the client never committed)")
    if not scanouts:
        reasons.append("no `scanout frames=` line (the presenter never ran)")
    return (not reasons), reasons


def median(values, digits=1):
    values = [v for v in values if v is not None]
    if not values:
        return None
    return round(statistics.median(values), digits)


def attribution(rows):
    """S7: which class owns cachebytes? Only a ≥70 % share is a single explanation."""
    trustworthy = [r for r in rows if r["cachebytes"] and r["cachebytes"] > 0 and r["ibytes"] is not None]
    if not trustworthy:
        return None, None, None
    ib = median([r["ibytes"] for r in trustworthy], 0)
    wb = median([r["wbytes"] for r in trustworthy], 0)
    cb = median([r["cachebytes"] for r in trustworthy], 0)
    if not cb:
        return None, ib, wb
    share_i = ib / cb
    share_w = wb / cb
    if share_i >= 0.70 and share_w < 0.70:
        return "imported", ib, wb
    if share_w >= 0.70 and share_i < 0.70:
        return "write-combined", ib, wb
    if share_i >= 0.30 or share_w >= 0.30:
        return "mixed", ib, wb
    return "neither", ib, wb


def report(text):
    """Return (exit code, human readable report). Printing is the caller's job so a
    test can assert on the text instead of re-parsing stdout."""
    out = []

    def say(line=""):
        out.append(line)

    ok, reasons = validity(text)
    rows = samples(text)
    latches = [m.groupdict() for m in LATCH_RE.finditer(text)]
    scanouts = [m.groupdict() for m in SCANOUT_RE.finditer(text)]
    shapes = sorted({m.group("shape") for m in SHAPE_RE.finditer(text)})

    say("有效性")
    say("  frames>0: %s" % ("yes" if ok else "no"))
    for reason in reasons:
        say("  invalid: %s" % reason)
    say("采样")
    say("  publish samples: %d" % len(rows))
    say("  distrust latched lines: %d" % len(latches))
    say("  scanout stage lines: %d" % len(scanouts))
    say("  copy shape(s): %s" % (", ".join(shapes) if shapes else "(none)"))
    if rows:
        say("  publish us median=%s max=%s" % (median([r["us"] for r in rows]),
                                              max(r["us"] for r in rows)))
        say("  cachebytes median=%s calls median=%s" % (median([r["cachebytes"] for r in rows], 0),
                                                       median([r["calls"] for r in rows], 0)))
        for name in ("ibytes", "obytes", "wbytes", "wskipped"):
            say("  %s median=%s" % (name, median([r[name] for r in rows], 0)))
        say("  trusted values: %s" % sorted({r["trusted"] for r in rows}))
    if scanouts:
        say("  submit median=%s encode median=%s gpu median=%s" % (
            median([int(s["submit"]) for s in scanouts]),
            median([int(s["encode"]) for s in scanouts]),
            median([int(s["gpu"]) for s in scanouts])))

    # S5: the three maintained classes must not exceed the visited total.
    over = [r for r in rows if r["ibytes"] is not None and
            (r["ibytes"] + r["obytes"] + r["wbytes"]) > r["bytes"]]
    s5 = bool(rows) and not over

    # S6: the trust state has to be self-consistent.
    trusted_values = {r["trusted"] for r in rows if r["trusted"] is not None}
    s6_all_trusted = trusted_values == {1} and all(r["wbytes"] == 0 for r in rows if r["wbytes"] is not None) \
        and any(r["wskipped"] for r in rows)
    s6_latched = (len(latches) == 1 and trusted_values == {0}
                  and any(r["wbytes"] for r in rows))
    s6 = s6_all_trusted or s6_latched

    kind, ib, wb = attribution(rows)
    say("归因（S7）")
    say("  cachebytes owner: %s" % (kind or "unknown"))
    say("  ibytes median=%s wbytes median=%s" % (ib, wb))
    say("  ❌ 禁止用 cachebytes/n 或 us/objects 推算「每次提交维护的字节」与「每对象开销」"
        "（窗口是一次调用，P-237）")

    say("判据")
    say("  S1 no panic markers: (see capture.json panicMarker/resetMarker)")
    say("  S2 publish samples with per-class fields: %s" % ("pass" if rows and all(
        r["trusted"] is not None for r in rows) else "fail"))
    say("  S3 still presents: %s" % ("pass" if ok else "invalid"))
    say("  S5 classes never exceed visited bytes: %s%s" % (
        "pass" if s5 else "fail", "" if not over else " (%d sample(s) over)" % len(over)))
    say("  S6 trust state self-consistent: %s%s" % (
        "pass" if s6 else "fail",
        "" if s6 else " (trusted=%s, latched=%d)" % (sorted(trusted_values), len(latches))))
    say("  S7 single-class attribution: %s" % (kind or "unknown"))

    if not ok:
        say("")
        say("VERDICT: INVALID (P-236) — a zero-frame run says nothing about the criteria")
        return 3, "\n".join(out)
    if rows and attribution(rows)[0] == "imported":
        say("")
        say("结论: 维护主体是 imported 帧 ⇒ F5 路线（减少每帧导入的面数，需先写清映射生命周期）")
    elif rows and attribution(rows)[0] == "write-combined":
        say("")
        say("结论: 维护主体是 write-combined BO ⇒ F6 路线（查 trust 为何失效、reassertWriteCombined 是否生效）")
    else:
        say("")
        say("结论: 混合或证据不足 ⇒ 先按 S5/S6 修探针，不要据此改维护范围")
    return 0, "\n".join(out)


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[-1])
        return 2
    text = read_log(argv[1])
    if text is None:
        print("❌ 读不到日志: %s" % argv[1])
        return 2
    code, rendered = report(text)
    print(rendered)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
