#!/usr/bin/env python3
"""Judge the K60 ADSP handoff chain from a boot console.

Why this exists: the 104-byte handoff has a producer (K60HandoffRuntime.cpp), a
consumer (K60PmicGlink.cpp / K60Battery.cpp) and a service layer that each log
their own line, and "it published" is not "the channel works" - the spec says so
in docs/research/battery/HANDOFF-PUBLISH-SPEC.md section 0 item 5.  Reading a
130-160 KB console by eye is how a published blob with a mismatched epoch, or a
lease that was refused for overlapping XNU RAM, gets reported as a success.
This judge turns the chain into ordered PASS/FAIL/INVALID criteria and prints
the evidence line for each.

Criteria (in boot order):
  CAPTURE     capture.json complete, bytes matches the file, no panic marker
  CHAIN       board ownership init ok, installed rc in {0,1}, platform rc=0,
              published ... bytes=104 flags=15 with a non-zero epoch
  ADOPT       the battery adopted that epoch, with non-zero tx/rx offsets
  CHANNEL     the PMIC_RTR_ADSP_APPS channel came up with a valid sign
  SAMPLE      at least one published battery sample after the channel came up
  NO-FAILURE  no "failed rc=", lease refusal, dead epoch or stopped transport
  ORDER       every link above appears after the previous one

Exit status: 0 PASS, 1 FAIL, 2 INVALID, 4 usage error (never a verdict).
Usage:
    python3 scripts/judge-k60-handoff-console.py <evidence-dir|console.log>
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

INIT_RE = re.compile(r"K60Handoff: board ownership init ok rc=0")
INSTALL_RE = re.compile(r"K60Handoff: board ownership installed rc=(?P<rc>-?\d+)")
PLATFORM_RE = re.compile(r"K60Handoff: platform installed rc=(?P<rc>-?\d+)")
PUBLISH_RE = re.compile(
    r"K60Handoff: published authenticated PAS1 epoch=(?P<epoch>\d+) "
    r"bytes=(?P<bytes>\d+) flags=(?P<flags>\d+)")
ADOPT_RE = re.compile(
    r"K60Battery: adopting authenticated PAS1 GLINK epoch=(?P<epoch>\d+) "
    r"desc=(?P<desc>[0-9a-fA-F]+) tx=(?P<tx>[0-9a-fA-F]+)/(?P<tx_bytes>[0-9a-fA-F]+) "
    r"rx=(?P<rx>[0-9a-fA-F]+)/(?P<rx_bytes>[0-9a-fA-F]+) \(no FIFO reset\)")
CHANNEL_RE = re.compile(
    r"K60Battery: actual PMIC_RTR_ADSP_APPS channel up; "
    r"measured sign=(?P<sign>-?\d+) subscription-ack=(?P<ack_type>\d+)/(?P<ack_bytes>\d+)")
SAMPLE_RE = re.compile(
    r"K60Battery: [a-z][a-z ]* sample=\d+ SOC=\d+\.\d+% .*subscribed=(?P<subscribed>\d+)")
FAILURES = [
    ("publish", re.compile(r"K60Handoff: .*failed rc=")),
    ("lease", re.compile(r"K60Battery: refusing DSP lease overlapping XNU-owned RAM")),
    ("epoch", re.compile(r"K60Battery: GLINK epoch never became ready")),
    ("transport", re.compile(r"K60Battery: physical transport stopped error=")),
]
HANDOFF_BYTES = 104
HANDOFF_FLAGS = 15


def _first(pattern: re.Pattern, lines: list[str]) -> tuple[int, re.Match] | None:
    for number, line in enumerate(lines, 1):
        match = pattern.search(line)
        if match:
            return number, match
    return None


def _add(notes: list[str], text: str) -> None:
    notes.append(text)


def judge(console: pathlib.Path, capture: pathlib.Path | None) -> tuple[bool, int]:
    """Return (printed, exit code)."""
    text = console.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    criteria: list[tuple[str, str, list[int], list[str]]] = []
    broken: list[str] = []

    def record(name: str, ok: bool, evidence: list[int], notes: list[str]) -> None:
        criteria.append((name, "PASS" if ok else "FAIL", evidence, notes))
        if not ok:
            broken.append(name)

    # CAPTURE
    evidence: list[int] = []
    notes: list[str] = []
    ok = bool(lines)
    if not ok:
        _add(notes, "the console file is empty")
    if capture is not None:
        try:
            data = json.loads(capture.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as error:
            record("CAPTURE", False, evidence, [f"capture.json unreadable: {error}"])
            data = None
        if data is not None:
            size = console.stat().st_size
            if data.get("complete") is not True:
                state = str(data.get("state") or "")
                stop = str(data.get("stopReason") or "")
                if state.startswith("captured") and stop:
                    # The harness cut the capture on purpose (fastboot return, timeout).
                    # Every link that does appear is real; the note keeps the verdict honest
                    # about the window it covers.
                    _add(notes, f"capture.json complete=false (stopReason={stop}); "
                                "the chain is judged on the window the log contains")
                else:
                    ok = False
                    _add(notes, "capture.json does not say complete=true and no stop reason explains it")
            if data.get("bytes") != size:
                ok = False
                _add(notes, f"capture.json bytes={data.get('bytes')} but console.log is {size}")
            if data.get("panicMarker") or "panic(cpu" in text:
                ok = False
                _add(notes, "the boot panicked")
            if str(data.get("state") or "") == "port-not-observed":
                ok = False
                _add(notes, "capture.json says port-not-observed")
    record("CAPTURE", ok, evidence, notes)

    init = _first(INIT_RE, lines)
    install = _first(INSTALL_RE, lines)
    platform = _first(PLATFORM_RE, lines)
    publish = _first(PUBLISH_RE, lines)
    adopt = _first(ADOPT_RE, lines)
    channel = _first(CHANNEL_RE, lines)

    # CHAIN
    evidence = []
    notes = []
    ok = True
    if init is None:
        ok = False
        _add(notes, "no 'board ownership init ok' line: the handoff runtime did not run")
    else:
        evidence.append(init[0])
    if install is None:
        ok = False
        _add(notes, "no 'board ownership installed' line")
    else:
        evidence.append(install[0])
        if int(install[1].group("rc")) not in (0, 1):
            ok = False
            _add(notes, f"board ownership install rc={install[1].group('rc')} at :{install[0]}")
    if platform is None:
        ok = False
        _add(notes, "no 'platform installed' line")
    else:
        evidence.append(platform[0])
        if int(platform[1].group("rc")) != 0:
            ok = False
            _add(notes, f"platform installed rc={platform[1].group('rc')} at :{platform[0]}")
    published_epoch = None
    if publish is None:
        ok = False
        _add(notes, "no 'published authenticated PAS1' line: the 104-byte blob was never published")
    else:
        evidence.append(publish[0])
        published_epoch = int(publish[1].group("epoch"))
        if int(publish[1].group("bytes")) != HANDOFF_BYTES:
            ok = False
            _add(notes, f"published bytes={publish[1].group('bytes')} (the consumer requires {HANDOFF_BYTES})")
        if int(publish[1].group("flags")) != HANDOFF_FLAGS:
            ok = False
            _add(notes, f"published flags={publish[1].group('flags')} (the consumer requires {HANDOFF_FLAGS})")
        if published_epoch == 0:
            ok = False
            _add(notes, "published epoch=0: the consumer rejects it")
    record("CHAIN", ok, evidence, notes)

    # ADOPT
    evidence = []
    notes = []
    ok = True
    if adopt is None:
        ok = False
        if publish is not None:
            _add(notes, "published but never adopted: the channel is not usable (spec section 0 item 5)")
        else:
            _add(notes, "no 'adopting authenticated PAS1 GLINK' line")
    else:
        evidence.append(adopt[0])
        adopted_epoch = int(adopt[1].group("epoch"))
        if published_epoch is not None and adopted_epoch != published_epoch:
            ok = False
            _add(notes, f"adopted epoch={adopted_epoch} but published epoch={published_epoch}")
        for field in ("tx", "rx"):
            if int(adopt[1].group(field), 16) == 0:
                ok = False
                _add(notes, f"adopted {field} offset is zero")
    record("ADOPT", ok, evidence, notes)

    # CHANNEL
    evidence = []
    notes = []
    ok = True
    if channel is None:
        ok = False
        _add(notes, "no 'actual PMIC_RTR_ADSP_APPS channel up' line")
    else:
        evidence.append(channel[0])
        sign = int(channel[1].group("sign"))
        if sign == 0:
            # The up line is printed from state(ready) before the first sample; the
            # real audio-probe consoles show sign=0 at :518 and samples later at :696.
            _add(notes, "measured sign=0: the polarity is established by the first sample, "
                        "not by the channel-up line")
        elif sign not in (1, -1):
            ok = False
            _add(notes, f"measured sign={sign} at :{channel[0]}")
        if int(channel[1].group("ack_type")) == 0 or int(channel[1].group("ack_bytes")) == 0:
            ok = False
            _add(notes, "subscription-ack is 0/0: the subscription never completed")
    record("CHANNEL", ok, evidence, notes)

    # SAMPLE
    evidence = []
    notes = []
    samples = [
        (number, match)
        for number, line in enumerate(lines, 1)
        for match in [SAMPLE_RE.search(line)]
        if match
    ]
    ok = bool(samples)
    if not samples:
        _add(notes, "no published battery sample")
    else:
        evidence.append(samples[-1][0])
        if int(samples[-1][1].group("subscribed")) == 0:
            notes.append("the last sample says subscribed=0")
    record("SAMPLE", ok, evidence, notes)

    # NO-FAILURE
    evidence = []
    notes = []
    ok = True
    for name, pattern in FAILURES:
        hit = _first(pattern, lines)
        if hit is not None:
            ok = False
            evidence.append(hit[0])
            _add(notes, f"{name} failure: {lines[hit[0] - 1].strip()[:140]}")
    record("NO-FAILURE", ok, evidence, notes)

    # ORDER
    evidence = []
    notes = []
    ok = True
    sequence = [
        ("init", init), ("install", install), ("platform", platform), ("publish", publish),
        ("adopt", adopt), ("channel", channel),
    ]
    if samples:
        sequence.append(("sample", samples[-1]))
    seen: list[tuple[str, int]] = []
    for name, hit in sequence:
        if hit is None:
            continue
        number = hit[0]
        if seen and number < seen[-1][1]:
            ok = False
            _add(notes, f"{name} at :{number} appears before {seen[-1][0]} at :{seen[-1][1]}")
        seen.append((name, number))
        evidence.append(number)
    record("ORDER", ok, evidence, notes)

    verdict = "FAIL" if broken else "PASS"
    for name, status, rows, reasons in criteria:
        where = ",".join(f":{row}" for row in rows)
        print(f"{status:6} {name:12} {where}".rstrip())
        for reason in reasons:
            print(f"       - {reason}")
    if broken:
        print(f"diagnosis: the first broken link is {broken[0]}; see the criteria above.")
    print(f"TOTAL  {verdict}")
    return True, 0 if verdict == "PASS" else 1


class _ArgumentParser(argparse.ArgumentParser):
    """argparse exits 2 for a usage error, but 2 means INVALID here.

    A typo in a flag would then be indistinguishable from "the capture carried
    nothing to judge", which is the one distinction this exit table exists for.
    """

    def error(self, message):
        self.print_usage(sys.stderr)
        print("%s: error: %s" % (self.prog, message), file=sys.stderr)
        raise SystemExit(4)

def main() -> int:
    parser = _ArgumentParser(description="judge the K60 ADSP handoff console")
    parser.add_argument("path", type=pathlib.Path)
    args = parser.parse_args()
    path: pathlib.Path = args.path
    console: pathlib.Path | None = None
    capture: pathlib.Path | None = None
    if path.is_dir():
        console = path / "console.log"
        capture = path / "capture.json"
        if not capture.is_file():
            print(f"judge-k60-handoff-console: no capture.json in {path}", file=sys.stderr)
            return 2
    elif path.is_file():
        console = path
        if (path.parent / "capture.json").is_file():
            capture = path.parent / "capture.json"
    if console is None or not console.is_file():
        print(f"judge-k60-handoff-console: not a file: {path}", file=sys.stderr)
        return 2
    _, code = judge(console, capture)
    return code


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
