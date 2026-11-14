#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Judge one captured boot against the audio step-8 criteria.

Why this exists: capture.json has no verdict field, and panicMarker reads K60PANIC on
both a healthy boot and a broken one (usblog-20261113-noinitblob was healthy, the
-rev0340 capture was not, and both carry the marker). complete=true is likewise not a
health signal: the broken capture had complete=true and the healthy one had false.
The only evidence that decides this subtask is the PongAudio lines in console.log, so
this script reads those and nothing else.

Exit codes: 0 = probe succeeded, 1 = probe ran but failed, 2 = probe never ran.

--replay adds the criterion for image k and later: the replay pass in
PongAudioAmp.c must also have run to completion. That means 60 steps per
amplifier (120 writes and 120 readbacks), no step reading back something other
than what was written, no placeholder (AW882XX_TODO) driver in the log, and each
amplifier carrying the ACF half that belongs to its I2C address - the 0x34 part
takes dev_index 1 and the 0x35 part dev_index 0 (AMPS.md section 8.5). Without
--replay the verdict is the probe-only one, so the run 1 evidence keeps judging
exactly as it did.
"""
import json
import os
import re
import sys

MARK_START = "PongAudio: amp probe start"
# Literal prefixes of three printf() calls in PongAudioAmp.c: the GPLL0 lock
# report (HR-02 step 1), the per-clock CBCR report (step 3) and the serial
# engine report (step 5). Counting them separately is what tells a capture
# "GPLL0 never locked" from "branch never left halt" from "engine unusable".
MARK_BUS = ("PongAudio: amp gcc gpll0", "PongAudio: amp gcc clk",
            "PongAudio: amp se15 ready")
MARK_ID = re.compile(r"PongAudio: amp(\d) .*id=0x([0-9a-fA-F]{4})")
MARK_DONE = re.compile(
    r"PongAudio: amp probe done found=(\d+)/(\d+) .*failed=(\d+) timeouts=(\d+)"
    r" .*recovered=(\d+)"
)

# The replay pass (PongAudioAmp.c amp_replay_one).
MARK_REPLAY_START = re.compile(
    r"PongAudio: amp(\d) replay start dev_index=(\d+) dbg=0x([0-9a-fA-F]{4})"
    r" vcalb=(refused )?0x([0-9a-fA-F]{4}) steps=(\d+)"
)
MARK_REPLAY_STEP = re.compile(
    r"PongAudio: amp(\d) replay (\d+) reg=0x([0-9a-fA-F]{2}) wrote=0x([0-9a-fA-F]{4})"
    r" read=0x([0-9a-fA-F]{4})"
)
MARK_REPLAY_DONE = re.compile(
    r"PongAudio: amp replay done amp0=(\d+) amp1=(\d+) written=(\d+)"
    r" mismatched=(\d+) failed=(\d+)"
)

# Which ACF half each probe index must carry. The probe calls 0x34 "amp0", but
# the tuning file numbers 0x34 as dev_index 1 and 0x35 as dev_index 0
# (AMPS.md section 8.5, hakios.speaker.c:430-431).
AMP_DEV_INDEX = {0: 1, 1: 0}
# Registers that identify a half: they differ between the two tables and are
# written once, in the profile phase, before anything else touches them.
# dev_index -> {register: value as the tuning file carries it}
PROFILE_MARKERS = {
    0: {0x06: 0x34E8, 0x07: 0x3020, 0x0F: 0x5064},
    1: {0x06: 0x38E8, 0x07: 0x3111, 0x0F: 0x5264},
}
# 0x08 identifies a half too, but its transmit-enable bit is cleared on the way
# in (PongAudioAmpReplay.h, action TxOff).
I2SCTRL3 = 0x08
I2STXEN = 0x40
I2SCTRL3_EXPECTED = {0: 0x00F6 & ~I2STXEN, 1: 0x00F7 & ~I2STXEN}
RESET_REG, RESET_VALUE = 0x00, 0x55AA
VCALB_REG, VOLUME_REG = 0x50, 0x05
MUTE_VOLUME = 0x3C0  # pong_replay_volume(): mute level, top six bits kept
PROFILE_STEPS = 57
STEPS_PER_AMP = PROFILE_STEPS + 3
AMPS = (0, 1)

# chip ids the probe is allowed to report (PongAudioPlan.h pong_audio_amp_name)
KNOWN = {
    0x2113: "AW88261", 0x2013: "AW88264", 0x2032: "AW88266", 0x2049: "AW88395",
    0x2055: "AW88256", 0x2066: "AW88166", 0x2071: "AW88350", 0x2183: "AW88399",
    0x2308: "AW88230",
}


def read_capture(directory):
    """Return (console lines, capture.json dict). Missing files yield empty values."""
    lines = []
    log_path = os.path.join(directory, "console.log")
    if os.path.isfile(log_path):
        with open(log_path, "r", encoding="utf-8", errors="replace") as handle:
            lines = handle.read().splitlines()
    meta = {}
    meta_path = os.path.join(directory, "capture.json")
    if os.path.isfile(meta_path):
        try:
            # capture-k60-usblog.ps1 writes UTF-8 with a BOM.
            with open(meta_path, "r", encoding="utf-8-sig") as handle:
                meta = json.load(handle)
        except (OSError, ValueError):
            meta = {}
    return lines, meta


def judge(lines, meta):
    """Return (exit code, report lines). Pure: no file access, so it is host-testable."""
    report = []
    report.append("capture.json: state=%s complete=%s stopReason=%s panicMarker=%s openErrors=%s"
                  % (meta.get("state"), meta.get("complete"), meta.get("stopReason"),
                     meta.get("panicMarker"), meta.get("openErrors")))
    starts = [l for l in lines if MARK_START in l]
    buses = [l for l in lines if any(m in l for m in MARK_BUS)]
    text = "\n".join(lines)
    ids = MARK_ID.findall(text)
    dones = MARK_DONE.findall(text)

    report.append("amp probe start      : %d line(s)" % len(starts))
    report.append("gcc/se15 bus ready   : %d line(s)" % len(buses))
    report.append("chip id reads        : %d %s" % (
        len(ids), ", ".join("amp%s=0x%s(%s)" % (n, i, KNOWN.get(int(i, 16), "unknown"))
                            for n, i in ids)))
    report.append("amp probe done       : %d %s" % (len(dones), dones))

    if not starts:
        report.append("VERDICT: probe never ran (no 'amp probe start')")
        return 2, report
    if not dones:
        report.append("VERDICT: probe started but never finished")
        return 1, report

    found, want, failed, timeouts, recovered = (int(x) for x in dones[-1])
    good = found == want and failed == 0 and timeouts == 0 and recovered == 0
    good = good and len(ids) == want and all(int(i, 16) in KNOWN for _, i in ids)
    report.append("VERDICT: %s" % ("SUCCESS - amplifiers identified" if good else "FAILED"))
    return (0 if good else 1), report


def todo_lines(lines):
    """Lines where the placeholder AW882xx driver announced itself.

    patches/xnu/0503 prints 'AW882xx: addr=.. chip=.. rev=.. (TODO: verify
    against vendor IDs)' from its AW882XX_TODO_* register numbers. A step-8 run
    must not lean on those, so any such line fails the replay criterion.
    """
    out = []
    for line in lines:
        if "TODO" not in line:
            continue
        if "AW882xx" in line or "aw882xx" in line or "PongAudio" in line:
            out.append(line)
    return out


def judge_replay(lines):
    """Return (exit code, report lines) for the replay pass. Pure, like judge()."""
    report = []
    text = "\n".join(lines)
    starts = MARK_REPLAY_START.findall(text)
    steps = MARK_REPLAY_STEP.findall(text)
    dones = MARK_REPLAY_DONE.findall(text)
    todos = todo_lines(lines)
    differs = [l for l in lines
               if l.startswith("PongAudio: amp") and l.rstrip().endswith("differs")]

    report.append("replay start lines   : %d %s" % (len(starts), starts))
    report.append("replay step lines    : %d (want %d = %d x %d)"
                  % (len(steps), STEPS_PER_AMP * len(AMPS), STEPS_PER_AMP, len(AMPS)))
    report.append("replay done lines    : %d %s" % (len(dones), dones))
    report.append("replay TODO lines    : %d" % len(todos))
    report.append("replay differs lines : %d" % len(differs))

    if not starts:
        report.append("REPLAY VERDICT: the replay pass never ran")
        return 2, report

    problems = []

    # One start per amplifier, carrying the ACF half that matches its address.
    for amp in AMPS:
        mine = [s for s in starts if int(s[0]) == amp]
        if len(mine) != 1:
            problems.append("amp%d replay start appears %d time(s)" % (amp, len(mine)))
            continue
        _, dev, _dbg, refused, _vcalb, steps_want = mine[0]
        if int(dev) != AMP_DEV_INDEX[amp]:
            problems.append("amp%d took dev_index %s, its address is dev_index %d"
                            % (amp, dev, AMP_DEV_INDEX[amp]))
        if refused:
            problems.append("amp%d refused to compute vcalb from its fuses" % amp)
        if int(steps_want) != STEPS_PER_AMP:
            problems.append("amp%d announced %s steps, want %d"
                            % (amp, steps_want, STEPS_PER_AMP))

    # Every step present exactly once, with the register and value it should have.
    for amp in AMPS:
        mine = sorted((int(s[1]), int(s[2], 16), int(s[3], 16), int(s[4], 16))
                      for s in steps if int(s[0]) == amp)
        if len(mine) != STEPS_PER_AMP:
            problems.append("amp%d has %d step lines, want %d"
                            % (amp, len(mine), STEPS_PER_AMP))
            continue
        seen = [s[0] for s in mine]
        if seen != list(range(STEPS_PER_AMP)):
            problems.append("amp%d step numbers are not 0..%d" % (amp, STEPS_PER_AMP - 1))
            continue
        dev = AMP_DEV_INDEX[amp]
        by_step = {step: (reg, wrote, read) for step, reg, wrote, read in mine}
        if by_step[0][:2] != (RESET_REG, RESET_VALUE):
            problems.append("amp%d step 0 is %s, want the soft reset 0x00<-0x55aa"
                            % (amp, by_step[0][:2]))
        vcalb_step = by_step[STEPS_PER_AMP - 2]
        if vcalb_step[0] != VCALB_REG:
            problems.append("amp%d vcalb step writes 0x%02x, want 0x50"
                            % (amp, vcalb_step[0]))
        volume_step = by_step[STEPS_PER_AMP - 1]
        if volume_step[0] != VOLUME_REG:
            problems.append("amp%d volume step writes 0x%02x, want 0x05"
                            % (amp, volume_step[0]))
        elif (volume_step[1] & 0x3FF) != MUTE_VOLUME:
            problems.append("amp%d volume step wrote 0x%04x, mute level is 0x%03x"
                            % (amp, volume_step[1], MUTE_VOLUME))
        for reg, want in PROFILE_MARKERS[dev].items():
            got = [wrote for step, (r, wrote, _read) in by_step.items()
                   if r == reg and step <= PROFILE_STEPS]
            if got != [want]:
                problems.append("amp%d (dev_index %d) wrote 0x%02x=%s, its own table says 0x%04x"
                                % (amp, dev, reg, [hex(v) for v in got] or "nothing", want))
        got = [wrote for step, (r, wrote, _read) in by_step.items()
               if r == I2SCTRL3 and step <= PROFILE_STEPS]
        if got != [I2SCTRL3_EXPECTED[dev]]:
            problems.append("amp%d (dev_index %d) wrote 0x08=%s, want 0x%04x (TXEN cleared)"
                            % (amp, dev, [hex(v) for v in got] or "nothing",
                               I2SCTRL3_EXPECTED[dev]))

    # The driver's own tally, and its per-step mismatch flag.
    if not dones:
        problems.append("no 'amp replay done' line")
    else:
        a0, a1, written, mismatched, failed = (int(x) for x in dones[-1])
        if (a0, a1) != (STEPS_PER_AMP, STEPS_PER_AMP):
            problems.append("replay done says amp0=%d amp1=%d, want %d each"
                            % (a0, a1, STEPS_PER_AMP))
        if written != STEPS_PER_AMP * len(AMPS):
            problems.append("replay done says written=%d, want %d"
                            % (written, STEPS_PER_AMP * len(AMPS)))
        if mismatched != 0:
            problems.append("replay done says mismatched=%d" % mismatched)
        if failed != 0:
            problems.append("replay done says failed=%d" % failed)
    if differs:
        problems.append("%d step(s) read back something other than what was written"
                        % len(differs))
    if todos:
        problems.append("the placeholder AW882XX_TODO driver ran: %s" % todos[0].strip())

    for line in problems:
        report.append("  - " + line)
    if problems:
        report.append("REPLAY VERDICT: FAILED (%d problem(s))" % len(problems))
        return 1, report
    report.append("REPLAY VERDICT: SUCCESS - %d writes, %d readbacks, both halves on the "
                  "right amplifier" % (STEPS_PER_AMP * len(AMPS), STEPS_PER_AMP * len(AMPS)))
    return 0, report


def severity(code):
    """Rank the three outcomes by how much attention they need.

    max() over the raw exit codes would be wrong: a run that never reached the probe
    (2) would outrank a run where the probe ran and failed (1), and the combined
    verdict would then hide the more useful evidence. A failure is the worse news.
    """
    return {0: 0, 1: 2, 2: 1}.get(code, 2)


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    replay = "--replay" in argv[1:]
    if not args:
        sys.stderr.write("usage: judge-audio-capture.py [--replay] <evidence-dir> [...]\n")
        return 2
    worst = 0
    for directory in args:
        lines, meta = read_capture(directory)
        code, report = judge(lines, meta)
        if replay:
            replay_code, replay_report = judge_replay(lines)
            report = report + replay_report
            if severity(replay_code) > severity(code):
                code = replay_code
        print("== %s" % directory)
        for line in report:
            print("   " + line)
        if severity(code) > severity(worst):
            worst = code
    return worst


if __name__ == "__main__":
    sys.exit(main(sys.argv))
