#!/usr/bin/env python3
"""Judge one cellular modem flight from its evidence directory.

Three exit codes, as the lead asked: 0 PASS, 1 FAILED, 2 INVALID.
INVALID means the console does not cover the observation window the modem needs
to start its QMI stack, so a missing line says nothing yet. The default window is
240 s; a shorter capture can never produce FAILED on a not-yet-observed item.

Every verdict line carries the numbers it was decided on.
"""

import argparse
import os
import re
import sys

WINDOW_DEFAULT = 240

# The first sixteen bytes of each EFS volume, as the reference record holds them.
# Storage 4 (fsc) being all zeros is itself the record: an empty head is the
# correct answer there, not a missing one.
EFS_HEADS = {
    1: "1000000003000000d801000020faa9c4",
    2: "1100000003000000d801000000026080",
    3: "1400000003000000d801000000000000",
    4: "0" * 32,
}

BOOT = [
    ("power ok", r"K60MODEM power ok cx="),
    ("power prepared", r"K60MODEM power prepared"),
    ("init_image ok", r"K60MODEM init_image ok metadata="),
    ("transport prepared", r"K60MODEM transport prepared"),
    ("mem_setup ok", r"K60MODEM mem_setup ok base="),
    ("auth_reset ok", r"K60MODEM auth_reset ok"),
]
BRIDGE = [
    ("bridge enabled", r"K60MODEM baseband: bridge enabled"),
    ("22 services published", r"COACHZ baseband: 22 of 22 services published"),
]


def read_log(path):
    """Accepts an evidence directory or a console log file."""
    if os.path.isdir(path):
        candidate = os.path.join(path, "console.log")
        if not os.path.exists(candidate):
            raise SystemExit("no console.log in %s" % path)
        path = candidate
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read()


def observation_window(text):
    """Largest wait stamp printed by the probe, in seconds."""
    stamps = [int(m) for m in re.findall(r"K60MODEM qrtr: wait (\d+) s", text)]
    if stamps:
        return max(stamps)
    verdict = re.search(r"polls=(\d+)", text)
    if verdict:
        return int(verdict.group(1)) // 500
    return 0


def first(pattern, text):
    match = re.search(pattern, text, re.MULTILINE)
    return match


def judge(text, window, require_efs=False):
    """Returns (verdict, items) where items is a list of (state, name, detail)."""
    items = []
    missing_required = 0
    observed = observation_window(text)

    for name, pattern in BOOT + BRIDGE:
        match = first(pattern, text)
        if match:
            items.append(("PASS", name, match.group(0).strip()))
        else:
            items.append(("FAIL", name, "no line"))
            missing_required += 1

    # A failure line outranks a missing one: the sequence reached a step and it
    # refused, which is a real failure at any window.
    refusals = re.findall(r"K60MODEM [a-z_]+ failed [^\n]*", text)
    if refusals:
        items.append(("FAIL", "no refusal line", refusals[0].strip()))
        missing_required += 1

    panic = "Attempting to remove permanent VM map entry" in text or "panic(cpu" in text
    if panic:
        items.append(("FAIL", "no panic", "console carries a panic"))
        missing_required += 1

    # Storage: k51 serves the reads the modem asks for right after the announce.
    opens = re.findall(r"rmtfs open path=(\S+) storage=(\d+)", text)
    paths = sorted({m[0] for m in opens})
    if paths:
        items.append(("PASS", "rmtfs open", "%d open(s): %s" % (len(opens), ", ".join(paths))))
    else:
        items.append(("FAIL", "rmtfs open", "the modem never opened an EFS image"))
        missing_required += 1

    allocs = re.findall(r"rmtfs alloc storage=(\d+) bytes=(\d+) physical=(0x[0-9a-f]+)", text)
    live = [a for a in allocs if int(a[2], 16) != 0]
    if live:
        storage, size, physical = live[0]
        ok = int(physical, 16) < (1 << 32)
        items.append(("PASS" if ok else "FAIL", "alloc below 4 GiB",
                      "storage=%s bytes=%s physical=%s" % (storage, size, physical)))
        if not ok:
            missing_required += 1
    else:
        items.append(("FAIL", "alloc below 4 GiB",
                      "%d alloc line(s), none with a physical address" % len(allocs)))
        missing_required += 1

    # The outcome token decides: a bare 'served' search would count 'not-served'
    # as a served read, because the word is a suffix of the refusal.
    rw = re.findall(
        r"^(?:\[[^\]\r\n]*\][ \t]*)?K60MODEM qrtr: rmtfs rw "
        r"storage=(\d+) direction=(\d+) vectors=(\d+) (\S+)"
        r"(?:[ \t]+offset=\d+[ \t]+bytes=\d+)?[ \t]*$", text, re.MULTILINE)
    served = [entry for entry in rw
              if entry[3] == "served" and entry[1] == "0" and int(entry[2]) > 0]
    if served:
        items.append(("PASS", "rmtfs rw served",
                      "%d read(s), e.g. storage=%s direction=%s vectors=%s" % ((len(served),) + served[0][:3])))
    else:
        detail = "%d rw line(s), none served" % len(rw)
        if rw:
            detail += " (last: storage=%s direction=%s vectors=%s %s)" % rw[-1]
        items.append(("FAIL", "rmtfs rw served", detail))
        missing_required += 1

    # W2 compares a sixteen-byte sample, not every byte in the vector. Legacy
    # k54 captures have no sample: SKIP by default, required explicitly for k55.
    # Collect candidates before validating hex so malformed evidence cannot
    # disappear and be mistaken for a legacy capture.
    summary_row = re.compile(
        r"storage=\d+ direction=\d+ vectors=\d+ (?:served|refused|not-served)"
        r"(?:[ \t]+offset=\d+[ \t]+bytes=\d+)?[ \t]*")
    rows = re.findall(
        r"^(?:\[[^\]\r\n]*\][ \t]*)?K60MODEM qrtr: rmtfs rw ([^\r\n]*)$",
        text, re.MULTILINE)
    rows = [row for row in rows if summary_row.fullmatch(row) is None]
    read_storages = {int(entry[0]) for entry in served}
    checked = 0
    bad = 0
    for row in rows:
        match = re.fullmatch(
            r"storage=(\d+) direction=(\d+) offset=(\d+) bytes=(\d+) head=(\S+)[ \t]*", row)
        if match is None:
            bad += 1
            items.append(("FAIL", "efs bytes reported", "malformed sample: " + row))
            continue
        storage, direction, offset, length = map(int, match.groups()[:4])
        head = match.group(5).lower()
        problem = None
        if storage not in EFS_HEADS:
            problem = "storage=%d has no independent reference" % storage
        elif direction != 0:
            problem = "direction=%d is not a read" % direction
        elif offset != 0:
            problem = "offset=%d, the reference starts at 0" % offset
        elif length < 512 or length % 512:
            problem = "bytes=%d is not a positive whole number of 512-byte sectors" % length
        elif re.fullmatch(r"[0-9a-f]{32}", head) is None:
            problem = "head=%s is not exactly sixteen hexadecimal bytes" % head
        elif storage not in read_storages:
            problem = "storage=%d has no served nonempty read" % storage
        elif head != EFS_HEADS[storage]:
            problem = "head=%s, expected %s" % (head, EFS_HEADS[storage])
        if problem:
            bad += 1
            items.append(("FAIL", "efs bytes storage=%d" % storage, problem))
        else:
            checked += 1
            items.append(("PASS", "efs bytes storage=%d" % storage,
                          "offset=0 bytes=%d head=%s (16-byte sample)" % (length, head)))
    missing_required += bad
    if not rows:
        state = "FAIL" if require_efs else "SKIP"
        items.append((state, "efs bytes reported", "no sixteen-byte sample was printed"))
        missing_required += int(require_efs)
    elif checked == 0 and bad == 0:
        items.append(("FAIL", "efs bytes reported", "no comparable sample"))
        missing_required += 1
    # Which disk answered. The modem partitions live on their own LUN here, so a
    # served read without this line cannot be told apart from a read off the
    # wrong table (P-261).
    volume = re.findall(r"K60UFS volume name=(\S+) lun=(\d+) first=(\d+) last=(\d+)", text)
    if volume:
        name, lun, vfirst, vlast = volume[0]
        items.append(("PASS", "volume lun chosen",
                      "name=%s lun=%s first=%s last=%s" % (name, lun, vfirst, vlast)))
    elif served:
        items.append(("FAIL", "volume lun chosen", "a read was served but no LUN was named"))
        missing_required += 1
    else:
        items.append(("SKIP", "volume lun chosen", "no named read happened"))
    # Heap: k52 announces 0x34/1 on 0x101 and answers 0x22/0x23/0x24.
    announce = first(r"announced memshare service (\d+) instance (\d+) port (0x[0-9a-f]+)", text)
    if announce:
        items.append(("PASS", "memshare announced",
                      "service=%s instance=%s port=%s" % announce.groups()))
    else:
        items.append(("FAIL", "memshare announced", "no announce line"))
        missing_required += 1

    requests = re.findall(r"memshare request=(0x[0-9a-f]+) client=(\d+) bytes=(\d+) result=(\d+)", text)
    by_kind = {}
    for kind, client, size, result in requests:
        by_kind.setdefault(kind, []).append((client, size, result))
    for kind, label in (("0x22", "memshare 0x22 allocate"), ("0x23", "memshare 0x23 free"),
                        ("0x24", "memshare 0x24 query")):
        seen = by_kind.get(kind, [])
        if seen:
            client, size, result = seen[0]
            items.append(("PASS", label, "%d request(s), e.g. client=%s bytes=%s result=%s" % (len(seen), client, size, result)))
        elif kind == "0x22":
            items.append(("FAIL", label, "the modem never asked for the heap"))
            missing_required += 1
        else:
            items.append(("SKIP", label, "not asked for in this window"))

    buffer = first(r"memshare buffer va=(0x[0-9a-f]+) physical=(0x[0-9a-f]+) bytes=(\d+)", text)
    if buffer:
        physical = int(buffer.group(2), 16)
        items.append(("PASS" if physical < (1 << 32) else "FAIL", "memshare buffer below 4 GiB",
                      "physical=%s bytes=%s" % (buffer.group(2), buffer.group(3))))
        if physical >= (1 << 32):
            missing_required += 1
    else:
        items.append(("SKIP", "memshare buffer below 4 GiB", "no allocation"))

    assign = re.findall(r"assign physical=(0x[0-9a-f]+) bytes=(\d+) from=(\d+) to=(\d+) rc=(-?\d+) sources=(\d+) destinations=(\d+)", text)
    good = [a for a in assign if int(a[4]) == 0]
    if good:
        physical, size, source, target, rc, sources, destinations = good[0]
        items.append(("PASS", "ownership transferred",
                      "physical=%s bytes=%s %s->%s rc=%s sources=%s destinations=%s" % (physical, size, source, target, rc, sources, destinations)))
    else:
        items.append(("SKIP", "ownership transferred", "%d assign line(s), none rc=0" % len(assign)))

    # SMP2P: k53 clears the stop bit and answers the ipa clock question.
    stop = first(r"K60MODEM transport: smp2p stop released was=(0x[0-9a-f]+) now=(0x[0-9a-f]+)", text)
    if stop:
        items.append(("PASS", "smp2p stop released", "was=%s now=%s" % stop.groups()))
    else:
        items.append(("FAIL", "smp2p stop released", "no line"))
        missing_required += 1

    query = re.findall(r"ipa query=(0x[0-9a-f]+) reply=(0x[0-9a-f]+)", text)
    if query:
        value, answer = query[0]
        items.append(("PASS", "ipa clock answered", "%d query(s), e.g. query=%s reply=%s" % (len(query), value, answer)))
    else:
        items.append(("SKIP", "ipa clock answered", "the modem never raised bit 0"))

    verdict_line = first(r"K60MODEM qrtr: verdict (\w+) services=(\d+)", text)
    if verdict_line:
        items.append(("PASS" if verdict_line.group(1) == "ok" else "SKIP", "verdict line",
                      "verdict=%s services=%s" % verdict_line.groups()))
    else:
        items.append(("SKIP", "verdict line", "the loop did not reach the verdict"))

    dms = re.findall(r"K60MODEM qrtr: dms revision", text)
    if dms:
        items.append(("PASS", "dms revision", "%d line(s)" % len(dms)))
    else:
        items.append(("SKIP", "dms revision", "not reached"))

    if missing_required == 0:
        return "PASS", items, observed
    # Only positive evidence of a failure outranks the window: a refusal line or
    # a panic. A boot-stage line that simply has not appeared yet is not evidence,
    # because a 60 s capture and a 60 s hang look identical (Lead 2026-11-20 05:13:
    # a console that stops at 60 s must read INVALID, never FAILED).
    hard = bool(refusals) or panic
    if hard:
        return "FAILED", items, observed
    if observed < window:
        return "INVALID", items, observed
    return "FAILED", items, observed


# Synthetic LUN/address values exercise parsing; they are not controller truth.
FIXTURE_PASS = """
K60MODEM power ok cx=0x30000/6 mss=0x30060/7 xo=0x300b0/3
K60MODEM power prepared
K60MODEM init_image ok metadata=0xb7ff0000 bytes=5884
K60MODEM transport prepared
K60MODEM transport: smp2p stop released was=0x1 now=0x0 ipa=0x1
K60MODEM mem_setup ok base=0x8bc00000 span=0x13200000
K60MODEM auth_reset ok
K60MODEM baseband: bridge enabled
COACHZ baseband: 22 of 22 services published
K60MODEM qrtr: announced rmtfs service 14 instance 1 port 0x102
K60MODEM qrtr: rmtfs open path=/boot/modem_fs1 storage=1
K60MODEM qrtr: rmtfs open path=/boot/modem_fs2 storage=2
K60MODEM qrtr: rmtfs alloc storage=1 bytes=2621440 physical=0x8f000000
K60UFS volume name=modemst1 lun=4 first=6 last=16389
K60MODEM qrtr: rmtfs rw storage=1 direction=0 vectors=2 served
K60MODEM qrtr: rmtfs rw storage=1 direction=0 offset=0 bytes=4096 head=1000000003000000d801000020faa9c4
K60MODEM qrtr: announced memshare service 52 instance 1 port 0x101
K60MODEM qrtr: memshare request=0x24 client=1 bytes=0 result=0
K60MODEM qrtr: memshare buffer va=0xffffff8020000000 physical=0x8f400000 bytes=1048576 node=0 port=0x4
K60MODEM qrtr: assign physical=0x8f400000 bytes=1048576 from=3 to=15 rc=0 sources=1 destinations=1
K60MODEM qrtr: memshare request=0x22 client=1 bytes=1048576 result=0
K60MODEM qrtr: memshare request=0x23 client=1 bytes=0 result=0
K60MODEM qrtr: ipa query=0x1 reply=0x1 at 12 s
K60MODEM qrtr: wait 240 s services=2 wanted=0 dms=0 malformed=0
"""

FIXTURE_SHORT = """
K60MODEM power ok cx=0x30000/6 mss=0x30060/7 xo=0x300b0/3
K60MODEM power prepared
K60MODEM init_image ok metadata=0xb7ff0000 bytes=5884
K60MODEM transport prepared
K60MODEM transport: smp2p stop released was=0x1 now=0x0 ipa=0x1
K60MODEM mem_setup ok base=0x8bc00000 span=0x13200000
K60MODEM auth_reset ok
K60MODEM baseband: bridge enabled
COACHZ baseband: 22 of 22 services published
K60MODEM qrtr: announced rmtfs service 14 instance 1 port 0x102
K60MODEM qrtr: wait 60 s services=2 wanted=0 dms=0 malformed=0
"""

FIXTURE_FAILED = FIXTURE_SHORT.replace("K60MODEM auth_reset ok", "K60MODEM auth_reset failed rc=-3")
# A capture that dies before the bridge is not a verdict: at 60 s the two bridge
# lines have simply not been printed yet.
FIXTURE_EARLY = FIXTURE_SHORT.replace("K60MODEM baseband: bridge enabled" + chr(10), "")
FIXTURE_EARLY = FIXTURE_EARLY.replace("COACHZ baseband: 22 of 22 services published" + chr(10), "")
FIXTURE_REFUSED = FIXTURE_PASS.replace("vectors=2 served", "vectors=2 not-served")


FIXTURE_NOLUN = FIXTURE_PASS.replace("K60UFS volume name=modemst1 lun=4 first=6 last=16389" + chr(10), "")

# Legacy k54 kernels printed no sample. They stay comparable without the strict
# flag; k55 explicitly requires the sample in its flight command.
SAMPLE_LINE = ("K60MODEM qrtr: rmtfs rw storage=1 direction=0 offset=0 "
               "bytes=4096 head=" + EFS_HEADS[1])
FIXTURE_NOHEAD = FIXTURE_PASS.replace(SAMPLE_LINE + chr(10), "")


def self_test():
    cases = (("PASS", FIXTURE_PASS), ("INVALID", FIXTURE_SHORT),
             ("FAILED", FIXTURE_FAILED), ("FAILED", FIXTURE_REFUSED),
             ("FAILED", FIXTURE_NOLUN), ("INVALID", FIXTURE_EARLY),
             ("PASS", FIXTURE_NOHEAD))
    for expected, text in cases:
        verdict, items, observed = judge(text, WINDOW_DEFAULT)
        assert verdict == expected, (expected, verdict)
        assert len(items) > 5
    verdict, items, observed = judge(FIXTURE_REFUSED, WINDOW_DEFAULT)
    rw = next(item for item in items if item[1] == "rmtfs rw served")
    assert rw[0] == "FAIL", rw
    verdict, items, observed = judge(FIXTURE_NOHEAD, WINDOW_DEFAULT, True)
    efs = next(item for item in items if item[1] == "efs bytes reported")
    assert verdict == "FAILED" and efs[0] == "FAIL", (verdict, efs)
    verdict, items, observed = judge(FIXTURE_NOHEAD, WINDOW_DEFAULT)
    efs = next(item for item in items if item[1] == "efs bytes reported")
    assert verdict == "PASS" and efs[0] == "SKIP", (verdict, efs)

    # One independently matched storage is sufficient. Each other storage uses
    # its own reference, including the valid all-zero fsc sample.
    for storage, head in EFS_HEADS.items():
        text = FIXTURE_NOHEAD.replace("rw storage=1 direction=0 vectors=2 served",
                                     "rw storage=%d direction=0 vectors=2 served" % storage)
        text += ("K60MODEM qrtr: rmtfs rw storage=%d direction=0 offset=0 "
                 "bytes=4096 head=%s\n" % (storage, head.upper()))
        verdict, items, observed = judge(text, WINDOW_DEFAULT, True)
        efs = next(item for item in items if item[1] == "efs bytes storage=%d" % storage)
        assert verdict == "PASS" and efs[0] == "PASS", (storage, verdict, efs)

    bad_rows = (
        SAMPLE_LINE.replace("storage=1", "storage=0"),
        SAMPLE_LINE.replace("storage=1", "storage=5"),
        SAMPLE_LINE.replace("storage=1", "storage=2"),
        SAMPLE_LINE.replace("direction=0", "direction=1"),
        SAMPLE_LINE.replace("offset=0", "offset=512"),
        SAMPLE_LINE.replace("bytes=4096", "bytes=0"),
        SAMPLE_LINE.replace("bytes=4096", "bytes=16"),
        SAMPLE_LINE.replace("bytes=4096", "bytes=513"),
        SAMPLE_LINE.replace(EFS_HEADS[1], EFS_HEADS[2]),
        SAMPLE_LINE.replace(EFS_HEADS[1], "0" * 32),
        SAMPLE_LINE.replace(EFS_HEADS[1], "z" * 32),
        SAMPLE_LINE[:-1], SAMPLE_LINE + "0", SAMPLE_LINE.split("head=")[0] + "head=",
        SAMPLE_LINE.replace("offset=0 ", ""), SAMPLE_LINE + " vectors=1",
        "K60MODEM qrtr: rmtfs rw storage=1 direction=0 vectors=2 garbage",
    )
    for row in bad_rows:
        # A malformed sample cannot become a legacy SKIP, even without strict mode.
        verdict, items, observed = judge(FIXTURE_PASS.replace(SAMPLE_LINE, row), WINDOW_DEFAULT)
        efs = [item for item in items if item[1].startswith("efs bytes")]
        assert verdict == "FAILED" and any(item[0] == "FAIL" for item in efs), (row, verdict, efs)
    for outcome in ("vectors=0 served", "vectors=2 not-served", "vectors=2 refused"):
        text = FIXTURE_PASS.replace("vectors=2 served", outcome)
        verdict, items, observed = judge(text, WINDOW_DEFAULT, True)
        efs = next(item for item in items if item[1] == "efs bytes storage=1")
        assert verdict == "FAILED" and efs[0] == "FAIL", (outcome, verdict, efs)
    text = FIXTURE_PASS.replace(SAMPLE_LINE, "[12.345] " + SAMPLE_LINE.upper().replace(
        "K60MODEM QRTR: RMTFS RW STORAGE=1 DIRECTION=0 OFFSET=0 BYTES=4096 HEAD=",
        "K60MODEM qrtr: rmtfs rw storage=1 direction=0 offset=0 bytes=4096 head="))
    assert judge(text, WINDOW_DEFAULT, True)[0] == "PASS"
    # A row that looks like a summary but lost its outcome word is evidence.
    # It was once dropped by a permissive fourth-token match: a capture carrying
    # only this row passed as legacy, and a valid sample beside it still passed
    # with --require-efs-bytes.
    lost_outcome = ("K60MODEM qrtr: rmtfs rw storage=1 direction=0 "
                    "vectors=2 head=" + EFS_HEADS[1])
    for text in (FIXTURE_PASS.replace(SAMPLE_LINE, lost_outcome),
                 FIXTURE_PASS + lost_outcome + chr(10)):
        for strict in (False, True):
            verdict, items, observed = judge(text, WINDOW_DEFAULT, strict)
            efs = [item for item in items if item[1].startswith("efs bytes")]
            assert verdict == "FAILED" and any(item[0] == "FAIL" for item in efs), (
                strict, verdict, efs)
    # The real k55 summary gained offset/bytes; it must stay a summary and not
    # be mistaken for a malformed sample.
    text = FIXTURE_PASS.replace("vectors=2 served",
                                "vectors=2 served offset=0 bytes=4096")
    assert judge(text, WINDOW_DEFAULT, True)[0] == "PASS"
    print("K60 FLIGHT JUDGE PASS legacy/strict, four independent heads, malformed samples, served-read guards")
    return 0

def main():
    parser = argparse.ArgumentParser(description="Judge a K60 cellular modem flight")
    parser.add_argument("evidence", nargs="?", help="evidence directory or console.log")
    parser.add_argument("--window", type=int, default=WINDOW_DEFAULT, help="seconds the modem needs before a missing line means failure")
    parser.add_argument("--require-efs-bytes", action="store_true",
                        help="treat a served read without comparable bytes as a failure")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if not args.evidence:
        parser.error("evidence directory required")
    text = read_log(args.evidence)
    verdict, items, observed = judge(text, args.window, args.require_efs_bytes)
    for state, name, detail in items:
        print("%-5s %-26s %s" % (state, name, detail))
    print("")
    print("observed window: %d s (need %d s before a missing line counts as failure)" % (observed, args.window))
    print("VERDICT: %s" % verdict)
    return {"PASS": 0, "FAILED": 1, "INVALID": 2}[verdict]


if __name__ == "__main__":
    sys.exit(main())
