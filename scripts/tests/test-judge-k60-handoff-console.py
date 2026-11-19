#!/usr/bin/env python3
"""Exercise scripts/judge-k60-handoff-console.py against synthetic consoles.

Each case is one way the handoff chain can look fine when skimmed and still be
broken: a published blob with the wrong byte count or flags, an epoch that the
battery did not adopt, a lease refused for overlapping XNU RAM, a channel that
came up before the adoption, a sample published before the channel.  The judge
must name all of them, and it must not fail a healthy console.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
JUDGE = ROOT / "scripts" / "judge-k60-handoff-console.py"
WORK = ROOT / "build" / "handoff-judge-tests"
ENV = dict(os.environ, PYTHONIOENCODING="utf-8")
RUN = dict(capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV)

INIT = "K60Handoff: board ownership init ok rc=0"
INSTALL = "K60Handoff: board ownership installed rc=0"
PLATFORM = "K60Handoff: platform installed rc=0"
PUBLISH = "K60Handoff: published authenticated PAS1 epoch=7 bytes=104 flags=15"
ADOPT = ("K60Battery: adopting authenticated PAS1 GLINK epoch=7 desc=800a "
         "tx=10/80 rx=20/80 (no FIFO reset)")
CHANNEL = ("K60Battery: actual PMIC_RTR_ADSP_APPS channel up; "
           "measured sign=-1 subscription-ack=1/28")
SAMPLE = ("K60Battery: lithium sample=12 SOC=57.00% charge=2500/5000mAh "
          "design=5000mAh cycles=30 voltage=3900mV current=-450mA "
          "current-source=dsp temp=25.50C external=0 charging=0 full=0 subscribed=1")

checks = 0
failures = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global checks, failures
    checks += 1
    if not ok:
        failures += 1
        print(f"FAIL {name}" + (f": {detail}" if detail else ""))


def healthy() -> list[str]:
    return [INIT, INSTALL, PLATFORM, PUBLISH, ADOPT, CHANNEL, SAMPLE,
            "K60Battery: dangling request timeout, resubscribing"]


def run(lines: list[str], capture: dict | None = None, name: str = "case",
        directory: bool = True) -> subprocess.CompletedProcess:
    where = WORK / name
    where.mkdir(parents=True, exist_ok=True)
    console = where / "console.log"
    console.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")
    if capture is None:
        capture = {"complete": True, "bytes": console.stat().st_size, "state": "captured"}
    elif not capture.get("bytes"):
        capture["bytes"] = console.stat().st_size
    (where / "capture.json").write_text(json.dumps(capture), encoding="utf-8")
    target = where if directory else console
    return subprocess.run([sys.executable, str(JUDGE), str(target)], **RUN)


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)

    # Healthy chain with a capture whose byte count matches the file.
    where = WORK / "healthy"
    where.mkdir(parents=True, exist_ok=True)
    lines = healthy()
    (where / "console.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
    size = (where / "console.log").stat().st_size
    (where / "capture.json").write_text(
        json.dumps({"complete": True, "bytes": size, "state": "captured"}), encoding="utf-8")
    result = subprocess.run([sys.executable, str(JUDGE), str(where)], **RUN)
    check("healthy chain passes", result.returncode == 0, result.stdout + result.stderr)
    check("healthy chain prints TOTAL PASS", "TOTAL  PASS" in result.stdout, result.stdout)
    check("healthy chain has no diagnosis line", "diagnosis:" not in result.stdout, result.stdout)

    # Missing publish.
    result = run([INIT, INSTALL, PLATFORM, ADOPT, CHANNEL, SAMPLE], name="no-publish")
    check("missing publish fails", result.returncode == 1, result.stdout)
    check("missing publish names the chain", "FAIL   CHAIN" in result.stdout, result.stdout)
    check("missing publish explains itself",
          "never published" in result.stdout, result.stdout)

    # Wrong byte count.
    result = run(healthy()[:3] + [PUBLISH.replace("bytes=104", "bytes=103")] + healthy()[4:],
                 name="bytes-103")
    check("bytes=103 fails", result.returncode == 1, result.stdout)
    check("bytes=103 names the requirement", "the consumer requires 104" in result.stdout, result.stdout)

    # Wrong flags.
    result = run(healthy()[:3] + [PUBLISH.replace("flags=15", "flags=14")] + healthy()[4:],
                 name="flags-14")
    check("flags=14 fails", result.returncode == 1, result.stdout)
    check("flags=14 names the requirement", "the consumer requires 15" in result.stdout, result.stdout)

    # Epoch mismatch.
    result = run(healthy()[:4] + [ADOPT.replace("epoch=7", "epoch=8")] + healthy()[5:],
                 name="epoch-mismatch")
    check("epoch mismatch fails", result.returncode == 1, result.stdout)
    check("epoch mismatch is named", "adopted epoch=8 but published epoch=7" in result.stdout,
          result.stdout)

    # Published but never adopted.
    result = run([INIT, INSTALL, PLATFORM, PUBLISH, CHANNEL, SAMPLE], name="no-adopt")
    check("published without adoption fails", result.returncode == 1, result.stdout)
    check("published without adoption says not usable",
          "the channel is not usable" in result.stdout, result.stdout)

    # Lease refused for overlapping XNU RAM.
    result = run([INIT, INSTALL, PLATFORM, PUBLISH,
                  "K60Battery: refusing DSP lease overlapping XNU-owned RAM base=80000000 bytes=1000"],
                 name="lease-overlap")
    check("lease overlap fails", result.returncode == 1, result.stdout)
    check("lease overlap is under NO-FAILURE", "FAIL   NO-FAILURE" in result.stdout, result.stdout)

    # Platform install failed.
    result = run(healthy()[:2] + ["K60Handoff: platform installed rc=-5"] + healthy()[3:],
                 name="platform-rc")
    check("platform rc=-5 fails", result.returncode == 1, result.stdout)
    check("platform rc=-5 is named", "platform installed rc=-5" in result.stdout, result.stdout)

    # Adoption before publication.
    result = run([INIT, INSTALL, PLATFORM, ADOPT, PUBLISH, CHANNEL, SAMPLE], name="order")
    check("adoption before publication fails", result.returncode == 1, result.stdout)
    check("order failure names the pair", "appears before" in result.stdout, result.stdout)

    # Sample before the channel came up.
    result = run([INIT, INSTALL, PLATFORM, PUBLISH, ADOPT, SAMPLE, CHANNEL], name="order-sample")
    check("sample before channel fails", result.returncode == 1, result.stdout)
    check("sample order failure is named", "sample at" in result.stdout, result.stdout)

    # Capture directory without capture.json.
    where = WORK / "no-capture"
    where.mkdir(parents=True, exist_ok=True)
    (where / "console.log").write_text("\n".join(healthy()) + "\n", encoding="utf-8")
    if (where / "capture.json").exists():
        (where / "capture.json").unlink()
    result = subprocess.run([sys.executable, str(JUDGE), str(where)], **RUN)
    check("missing capture.json is INVALID", result.returncode == 2, result.stdout)

    # Capture with a UTF-8 BOM is still readable.
    where = WORK / "bom"
    where.mkdir(parents=True, exist_ok=True)
    text = "\n".join(healthy()) + "\n"
    (where / "console.log").write_text(text, encoding="utf-8")
    (where / "capture.json").write_text(
        "\ufeff" + json.dumps({"complete": True,
                                "bytes": (where / "console.log").stat().st_size,
                                "state": "captured"}),
        encoding="utf-8")
    result = subprocess.run([sys.executable, str(JUDGE), str(where)], **RUN)
    check("BOM capture is accepted", result.returncode == 0, result.stdout + result.stderr)

    # A capture the harness cut on purpose (fastboot return) still judges its window.
    result = run(healthy(), capture={"complete": False, "bytes": 0,
                                     "state": "captured-disconnected",
                                     "stopReason": "fastboot-return"}, name="cut-capture")
    check("a cut capture still passes its window", result.returncode == 0, result.stdout + result.stderr)
    check("a cut capture says what window it covers", "stopReason=fastboot-return" in result.stdout,
          result.stdout)

    # Ignoring the sign=0 case: the up line legitimately precedes the first sample.
    result = run(healthy()[:5] + [CHANNEL.replace("sign=-1", "sign=0")] + healthy()[6:],
                 name="sign-zero")
    check("sign=0 at channel up passes", result.returncode == 0, result.stdout + result.stderr)
    check("sign=0 is explained", "the polarity is established by the first sample" in result.stdout,
          result.stdout)

    # Panic marker in the capture.
    where = WORK / "panic"
    where.mkdir(parents=True, exist_ok=True)
    (where / "console.log").write_text("\n".join(healthy()) + "\n", encoding="utf-8")
    (where / "capture.json").write_text(
        json.dumps({"complete": True, "bytes": (where / "console.log").stat().st_size,
                    "panicMarker": "panic(cpu 0)", "state": "captured"}), encoding="utf-8")
    result = subprocess.run([sys.executable, str(JUDGE), str(where)], **RUN)
    check("panic marker fails", result.returncode == 1, result.stdout)
    check("panic is named", "panicked" in result.stdout, result.stdout)

    # Empty console.
    result = run([], name="empty")
    check("empty console fails", result.returncode == 1, result.stdout)
    check("empty console is named", "console file is empty" in result.stdout, result.stdout)

    # Missing path.
    result = subprocess.run([sys.executable, str(JUDGE), str(WORK / "does-not-exist")], **RUN)
    check("missing path is INVALID", result.returncode == 2, result.stdout)

    summary = f"TESTS OK {checks} checks" if failures == 0 else f"TESTS OK {checks} checks ({failures} failure(s))"
    print(summary)
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
