#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Host test for scripts/judge-audio-capture.py.

The judge replaced a human reading capture.json, which is exactly the step that got
the verdict wrong twice (panicMarker reads K60PANIC on a healthy boot too). These cases
pin the three outcomes and the two traps.

The replay cases pin the step-8 criterion for image k: 60 steps per amplifier, 120
writes and 120 readbacks, each half on the amplifier its I2C address belongs to, and
no placeholder driver in the log. The synthetic logs are built from the same register
values the tables carry, so a change to either side shows up here.
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(os.path.dirname(HERE), "judge-audio-capture.py")

spec = importlib.util.spec_from_file_location("judge_audio_capture", TOOL)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

fails = 0


def expect(cond, what):
    global fails
    if not cond:
        print("FAIL " + what)
        fails += 1


HEALTHY = [
    "K60PANIC: restart windows ready",
    "PongAudio: amp probe start (read pass first, then a replay pass that writes the tuning table)",
    "PongAudio: amp gcc gpll0 vote=0x00000001 mode=0x80000000 locked=1",
    "PongAudio: amp gcc clk core halt=0x00000002 running=1",
    "PongAudio: amp se15 ready config=0x03000021 status=0x00000000 level=2",
    "PongAudio: amp0 addr=0x34 id=0x2113 chip=AW88261",
    "PongAudio: amp1 addr=0x35 id=0x2113 chip=AW88261",
    "PongAudio: amp probe done found=2/2 transfers=26 failed=0 timeouts=0 stray=0 recovered=0",
]
SILENT = [
    "PongAudio: amp probe start (read pass first, then a replay pass that writes the tuning table)",
    "PongAudio: amp0 addr=0x34 no answer after 3 reads result=3 err=3 irq=0x00000000",
    "PongAudio: amp probe done found=0/2 transfers=6 failed=6 timeouts=3 stray=0 recovered=2",
]
STARTED_ONLY = [
    "PongAudio: amp probe start (read pass first, then a replay pass that writes the tuning table)",
    "PongAudio: se15 no DFS level",
]
ABSENT = ["K60PANIC: restart windows ready", "no audio here"]

# The two Music tables as the ACF carries them, cut down to the registers the
# replay judge looks at. Everything else in the table is irrelevant here.
MARKER_REGS = {0x06: (0x34E8, 0x38E8), 0x07: (0x3020, 0x3111),
               0x0F: (0x5064, 0x5264), 0x08: (0x00F6, 0x00F7)}
# probe index -> dev_index, the pairing AMPS.md section 8.5 warns about
PROBE_DEV = {0: 1, 1: 0}
VCALB = {0: 0x2094, 1: 0x2052}  # amp0's fuses give 8340, amp1's 8274


def replay_profile(dev):
    """57 register pairs, in order, for one half of the ACF."""
    pairs = []
    for step in range(57):
        reg = 0x03 + step if step < 20 else 0x30 + (step - 20)
        if reg in MARKER_REGS:
            value = MARKER_REGS[reg][dev]
            if reg == 0x08:
                value &= ~0x40  # TXEN cleared on the way in
        elif reg == 0x04:
            value = 0x7240 if dev == 1 else 0x7340  # three bits kept from hw
        else:
            value = 0x1000 + step
        pairs.append((reg, value))
    return pairs


def replay_log(amp, dev):
    """The lines one amplifier's replay pass prints."""
    lines = ["PongAudio: amp%d replay start dev_index=%d dbg=0x%04x vcalb=0x%04x steps=60"
             % (amp, dev, 0xC003 if dev == 0 else 0xC003, VCALB[amp])]
    steps = [(0x00, 0x55AA)] + replay_profile(dev) + [(0x50, VCALB[amp]),
                                                     (0x05, 0x1BC0 if amp == 1 else 0x13C0)]
    for index, (reg, value) in enumerate(steps):
        lines.append("PongAudio: amp%d replay %02d reg=0x%02x wrote=0x%04x read=0x%04x%s"
                     % (amp, index, reg, value, value,
                        " (three bits kept from hw)" if reg == 0x04 else ""))
    return lines


def replay_done(a0=60, a1=60, written=120, mismatched=0, failed=0):
    return ("PongAudio: amp replay done amp0=%d amp1=%d written=%d mismatched=%d failed=%d"
            " transfers=250" % (a0, a1, written, mismatched, failed))


def replay_run():
    """A complete, correct replay: both amplifiers, each with its own half."""
    lines = list(HEALTHY)
    lines += replay_log(0, PROBE_DEV[0])
    lines += replay_log(1, PROBE_DEV[1])
    lines.append(replay_done())
    return lines


def cases():
    code, report = mod.judge(HEALTHY, {"state": "captured-truncated", "complete": False,
                                       "panicMarker": "K60PANIC"})
    expect(code == 0, "healthy capture is SUCCESS even with panicMarker set and complete=false")
    expect(any("SUCCESS" in l for l in report), "healthy report names SUCCESS")
    expect(any("amp0=0x2113(AW88261)" in l for l in report), "known chip id is named")
    expect(any("bus ready" in l and l.strip().endswith("3 line(s)") for l in report),
           "the three real bus lines are recognised")

    code, _ = mod.judge(SILENT, {"state": "captured", "complete": True,
                                 "panicMarker": "K60PANIC"})
    expect(code == 1, "complete=true does not rescue a silent amplifier")

    code, report = mod.judge(STARTED_ONLY, {})
    expect(code == 1, "started but unfinished is a failure")
    expect(any("never finished" in l for l in report), "unfinished report says so")
    expect(any("last PongAudio line before the stop" in l for l in report),
           "unfinished report points at the line that stopped it")

    code, report = mod.judge(ABSENT, {})
    expect(code == 2, "no probe line means the probe never ran")
    expect(any("never ran" in l for l in report), "absent report says so")
    expect(any("pong_audio_probe=1" in l and "0531" in l for l in report),
           "absent report names the two wiring causes rather than the hardware")

    # an unknown id must not be accepted just because the count matches
    odd = list(HEALTHY)
    odd[4] = "PongAudio: amp0 addr=0x34 id=0x1234 chip=unknown"
    code, _ = mod.judge(odd, {})
    expect(code == 1, "unknown chip id fails even at found=2/2")

    # one amplifier identified is not success either
    half = [l for l in HEALTHY if "amp1 addr" not in l]
    code, _ = mod.judge(half, {})
    expect(code == 1, "found=2/2 with one id read fails")

    expect(mod.KNOWN[0x2113] == "AW88261", "chip table matches PongAudioPlan.h")
    expect(len(mod.KNOWN) == 9, "nine known ids")


def replay_cases():
    """The step-8 criterion: 120 writes and 120 readbacks, both halves right."""
    lines = replay_run()
    code, report = mod.judge_replay(lines)
    expect(code == 0, "a complete replay is SUCCESS")
    expect(any("REPLAY VERDICT: SUCCESS" in l for l in report), "replay report names SUCCESS")
    expect(any("120 writes, 120 readbacks" in l for l in report),
           "the success line counts writes and readbacks")
    expect(any("replay step lines    : 120" in l for l in report), "120 step lines seen")

    # run 1 (image j) had no replay pass: the probe verdict must stay untouched
    code, _ = mod.judge(HEALTHY, {})
    expect(code == 0, "the probe verdict is unchanged when there is no replay")
    code, report = mod.judge_replay(HEALTHY)
    expect(code == 2, "a log with no replay pass is 'never ran', not a failure")
    expect(any("never ran" in l for l in report), "missing replay is reported as never ran")

    # the trap this whole criterion exists for: each half on its own amplifier
    swapped = list(HEALTHY) + replay_log(0, 0) + replay_log(1, 1) + [replay_done()]
    code, report = mod.judge_replay(swapped)
    expect(code == 1, "tables swapped between amplifiers fails")
    expect(any("took dev_index" in l for l in report), "the swapped dev_index is named")
    expect(any("its own table says 0x34e8" in l or "its own table says 0x34E8" in l
               for l in report) or any("wrote 0x06" in l for l in report),
           "the wrong register value is named")

    # a single readback that differs is a failure, even if the tally says otherwise
    one = list(replay_run())
    for index, line in enumerate(one):
        if "replay 05 reg=0x07" in line:
            one[index] = line.replace("read=0x%04x" % MARKER_REGS[0x07][1],
                                      "read=0x0000") + " differs"
            break
    code, report = mod.judge_replay(one)
    expect(code == 1, "one differing readback fails")
    expect(any("read back something other than" in l for l in report),
           "the differing readback is named")

    # the driver's own tally has to agree
    bad_tally = list(replay_run())
    bad_tally[-1] = replay_done(written=119)
    code, _ = mod.judge_replay(bad_tally)
    expect(code == 1, "written=119 fails")
    bad_tally[-1] = replay_done(mismatched=2)
    code, _ = mod.judge_replay(bad_tally)
    expect(code == 1, "mismatched=2 fails")
    bad_tally[-1] = replay_done(a1=57)
    code, _ = mod.judge_replay(bad_tally)
    expect(code == 1, "one amplifier stopping early fails")

    # a missing step line
    short = [l for l in replay_run() if "amp1 replay 30 " not in l]
    code, report = mod.judge_replay(short)
    expect(code == 1, "a missing step fails")
    expect(any("amp1 has 59 step lines" in l for l in report), "the missing step is counted")

    # the placeholder driver must not be the thing that ran
    with_todo = list(replay_run())
    with_todo.append("AW882xx: addr=0x34 chip=0x0000 rev=0x0001 (TODO: verify against vendor IDs)")
    code, report = mod.judge_replay(with_todo)
    expect(code == 1, "the placeholder AW882XX_TODO driver fails the criterion")
    expect(any("AW882XX_TODO" in l for l in report), "the placeholder line is quoted")

    # vcalb refused (fuses unreadable) is a failure, not a silent zero
    refused = [l.replace("vcalb=0x2094", "vcalb=refused 0x0000") for l in replay_run()]
    code, report = mod.judge_replay(refused)
    expect(code == 1, "a refused vcalb fails")
    expect(any("refused to compute vcalb" in l for l in report), "the refused vcalb is named")

    # the constants themselves, so a table edit cannot drift past this test
    expect(mod.STEPS_PER_AMP == 60, "57 profile pairs + reset + vcalb + volume")
    expect(mod.AMP_DEV_INDEX == {0: 1, 1: 0}, "0x34 is dev_index 1, 0x35 is dev_index 0")
    expect(mod.PROFILE_MARKERS[0][0x06] == 0x34E8, "dev_index 0 carries 0x06=0x34e8")
    expect(mod.PROFILE_MARKERS[1][0x06] == 0x38E8, "dev_index 1 carries 0x06=0x38e8")
    expect(mod.I2SCTRL3_EXPECTED[0] == 0x00B6, "dev_index 0 writes 0x08=0x00b6")
    expect(mod.I2SCTRL3_EXPECTED[1] == 0x00B7, "dev_index 1 writes 0x08=0x00b7")
    expect(mod.MUTE_VOLUME == 0x3C0, "mute volume is 0x3c0")


def bom_case():
    """capture.json is written with a BOM; reading it as plain utf-8 used to fail."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "capture.json"), "w", encoding="utf-8-sig") as handle:
            handle.write('{"state": "captured", "complete": true}')
        with open(os.path.join(tmp, "console.log"), "w", encoding="utf-8") as handle:
            handle.write("\n".join(replay_run()))
        lines, meta = mod.read_capture(tmp)
        expect(meta.get("state") == "captured", "BOM-prefixed capture.json parses")
        expect(len(lines) == len(replay_run()), "console.log is read whole")
        code, _ = mod.judge_replay(lines)
        expect(code == 0, "--replay works on a capture read from disk")
    code, _ = mod.judge(*mod.read_capture("/nonexistent-evidence-dir"))
    expect(code == 2, "a missing directory is not a success")


PLAYBACK_HEAD = "PongAudio: amp play done playing=2/2"


def step_line(n, nbytes, opcode, token):
    return ("PongAudio: playback step %d send bytes=%d opcode=0x%08x token=0x%08x rc=0"
            % (n, nbytes, opcode, token))


def rx_line(opcode, token, status, kind=1):
    return ("PongAudio: glink adsp_apps rx bytes=32 kind=%d opcode=0x%08x "
            "token=0x%08x status=%d src=2:0x1 dst=3:0x2001 echoed=0x00000000"
            % (kind, opcode, token, status))


def playback_run(speaker_status=0, clock_status=0, switch="on", sysst=0x0011,
                 write_done=0, extra=()):
    """One synthetic playback plan, shaped like the real console lines."""
    plan = [(0, 296, 0x01001000, 0x02001005, 0),
            (1, 168, 0x01001006, 0x02001005, 0),
            (2, 408, 0x01001000, 0x02001005, speaker_status),
            (3, 136, 0x01001006, 0x02001005, 0),
            (4, 88, 0x01001006, 0x02001005, 0),
            (5, 60, 0x0100100C, 0x02001001, 0),
            (6, 76, 0x0100100F, 0x02001002, clock_status),
            (7, 64, 0x01001001, 0x02001005, 0),
            (8, 64, 0x01001001, 0x02001005, 0),
            (9, 72, 0x01001002, 0x02001005, 1),
            (10, 64, 0x01001002, 0x02001005, speaker_status),
            (11, 64, 0x01001002, 0x02001005, 0)]
    lines = ["K60PANIC: ring kept"]
    # the judge needs >= 500 lines for F2, and a boot that reached playback has many
    lines += ["K60USBLOG: keepalive %d" % i for i in range(520)]
    for n, nbytes, opcode, reply_opcode, status in plan:
        token = 0x00030000 + n
        lines.append(step_line(n, nbytes, opcode, token))
        lines.append(rx_line(reply_opcode, token, status, 6 if reply_opcode == 0x02001002 else 1))
    if switch != "none":
        read = "0x00000002" if switch == "on" else "0x00000000"
        lines.append("PongAudio: amp spk switch gpio=52 on=%d cfg=0x00000204 io=0x%08x read=%s"
                     % (1 if switch == "on" else 0,
                        0x2 if switch == "on" else 0x0, read))
    for amp in (0, 1):
        lines.append("PongAudio: amp%d play pll=%d status=0x%04x faults=0x0000 tries=51"
                     % (amp, 1 if sysst & 0x1 else 0, sysst))
    lines.append("PongAudio: amp play done playing=%d/2" % (2 if switch == "on" else 0))
    for _ in range(write_done):
        lines.append(rx_line(0x05001004, 0x10000001, 0, 3))
    lines.extend(extra)
    return lines


def playback_cases():
    """The cc card is judged by a tool, so the tool itself is pinned here."""
    meta = {"state": "captured-budget-complete", "complete": True,
            "stopReason": "budget", "panicMarker": None}

    code, report = mod.judge_playback(playback_run(), meta)
    expect(code == 0, "a full playback run with the switch high passes")
    expect(any("SUCCESS" in l for l in report), "the verdict line says SUCCESS")
    expect(any("PLLS|CLKS" in l for l in report), "S6 reports the clock bits")

    # K60PANIC: ring kept is a ring marker, not a panic; the healthy run carries it
    expect(not any("F1" in l for l in report), "ring kept is not a panic")

    # no plan at all is 'never ran', not a failure
    code, report = mod.judge_playback(["K60USBLOG: keepalive"] * 600, meta)
    expect(code == 2, "a capture without the playback plan is 'never ran'")

    # S5: the switch must be high and must read back high
    code, report = mod.judge_playback(playback_run(switch="none"), meta)
    expect(code == 1, "a missing switch drive fails")
    expect(any("S5" in l for l in report), "the missing switch is named S5")

    code, report = mod.judge_playback(playback_run(switch="low"), meta)
    expect(code == 1, "a switch never driven high fails")

    # driven high but the pad reads back low: a different failure, reported apart
    stuck = [l.replace("read=0x00000002", "read=0x00000000")
             if l.startswith("PongAudio: amp spk switch") else l
             for l in playback_run(switch="on")]
    code, report = mod.judge_playback(stuck, meta)
    expect(code == 1, "a switch that reads back low fails")
    expect(any("reads back" in l for l in report), "the readback mismatch is named")

    # F3: the I2S sink was refused
    code, report = mod.judge_playback(playback_run(speaker_status=1), meta)
    expect(code == 1, "a refused speaker open fails")
    expect(any("F3" in l for l in report), "the refusal is named F3")

    # F4: PRM would not give the bit clock
    code, report = mod.judge_playback(playback_run(clock_status=2), meta)
    expect(code == 1, "a refused clock vote fails")
    expect(any("F4" in l for l in report), "the clock refusal is named F4")

    # F1: a real panic fails even when every step succeeded
    code, report = mod.judge_playback(playback_run(extra=["K60KEXC: esr=0x96000010"]), meta)
    expect(code == 1, "a panic fails the run")
    expect(any("F1" in l for l in report), "the panic is named F1")
    code, _ = mod.judge_playback(playback_run(), {"state": "captured", "panicMarker": "K60PANIC"})
    expect(code == 1, "a panicMarker in capture.json fails the run")

    # F5: the ADSP dropped, so the run proves nothing
    code, report = mod.judge_playback(playback_run(extra=["PongAudio: glink adsp_apps down"]), meta)
    expect(code == 1, "a glink drop fails the run")
    expect(any("F5" in l for l in report), "the drop is named F5")

    # S1: the capture must be complete
    code, report = mod.judge_playback(playback_run(), {"state": "captured-disconnected"})
    expect(code == 1, "a disconnected capture fails")
    expect(any("S1" in l for l in report), "the state is named S1")

    # S6 is reported, not gated: a clean run with no clock bits still exits 0
    code, report = mod.judge_playback(playback_run(sysst=0x0000), meta)
    expect(code == 0, "no clock bits is a finding, not a failure")
    expect(any("no clock bits" in l for l in report), "0x0000 is reported as no clock bits")
    code, report = mod.judge_playback(playback_run(sysst=0x0020), meta)
    expect(code == 0, "NOCLKS is a finding, not a failure")
    expect(any("NOCLKS" in l for l in report), "0x0020 is reported as NOCLKS")

    # S7: the DSP never consumed a period on any image so far
    code, report = mod.judge_playback(playback_run(write_done=3), meta)
    expect(any("WRITE_DONE replies=3" in l for l in report), "write-done replies are counted")

    # S8: which buffer the PCM path had, and whether the pages could be lent.
    # Reported, not gated - the next build needs the line to know what to fix.
    for marker, want in (
            ("PongAudio: PCM buffer in the CVP carveout pa=0x9ee00000 size=0x10000",
             "CVP carveout"),
            ("PongAudio: low DMA lease pa=0x9ee00000 size=0x10000", "loader lease"),
            ("PongAudio: low DMA allocated pa=0x9ee00000 size=0x10000", "kernel allocation"),
            ("PongAudio: low DMA unavailable: no handoff", "none")):
        code, report = mod.judge_playback(playback_run(extra=[marker]), meta)
        expect(code == 0, "the buffer path is reported, not gated")
        expect(any("S8 PCM buffer=" + want in l for l in report), "S8 names " + want)
    code, report = mod.judge_playback(playback_run(extra=["PongAudio: PCM slot 0 lend refused"]), meta)
    expect(any("lend refused=1" in l for l in report), "a refused lend is counted")
    code, report = mod.judge_playback(playback_run(), meta)
    expect(any("S8 PCM buffer=not reported" in l for l in report),
           "an image without the line says so")
    # the constants the card names, so a script edit cannot drift past this test
    expect(mod.SPEAKER_OPEN_STEP == 2 and mod.SPEAKER_OPEN_BYTES == 408,
           "step 2 is the 408-byte speaker open")
    expect(mod.SPEAKER_START_STEP == 10, "step 10 is the speaker start")
    expect(mod.CLOCK_STEP == 6 and mod.CLOCK_OPCODE == 0x0100100F, "step 6 votes the clock")
    expect(mod.SPK_SWITCH_GPIO == 52 and mod.SPK_SWITCH_ON_IO == 2, "gpio52 reads 0x2 when on")
    expect(mod.SYSST_CLOCKS == 0x11 and mod.SYSST_NOCLKS == 0x20, "SYSST bits match section 8")


def severity_case():
    """Two runs are combined by need, not by numeric max: failure outranks absent."""
    expect(mod.severity(1) > mod.severity(2), "a failed run outranks a run that never started")
    expect(mod.severity(2) > mod.severity(0), "a run that never started outranks success")
    expect(mod.severity(0) == 0, "success is the least severe")


def capture_cases():
    """The evidence directory, not a file: renamed logs resolve, empty ones invalid."""
    import tempfile

    root = tempfile.mkdtemp(prefix="k60-evi-")
    # console.log wins over the sidecar by name, whatever the sizes.
    with open(os.path.join(root, "console.log"), "w") as f:
        f.write(step_line(1, 24, 0x100e5, 0x25a00) + chr(10))
    with open(os.path.join(root, "notes.log"), "w") as f:
        f.write("x" * 4000)
    expect(mod.find_log(root).endswith("console.log"), "console.log is preferred by name")

    # A hand-merged directory keeps the log under another name; largest wins.
    renamed = tempfile.mkdtemp(prefix="k60-evi-")
    with open(os.path.join(renamed, "side.log"), "w") as f:
        f.write("small")
    with open(os.path.join(renamed, "console-1.log"), "w") as f:
        f.write("PongAudio: amp probe start" + chr(10))
    path = mod.find_log(renamed)
    expect(path.endswith("console-1.log"), "the largest *.log is the console: %s" % path)
    lines, meta = mod.read_capture(renamed)
    expect(any("amp probe start" in l for l in lines), "the renamed log is read")

    # An empty directory is INVALID (2), never a quiet pass or a failure.
    empty = tempfile.mkdtemp(prefix="k60-evi-")
    lines, meta = mod.read_capture(empty)
    code, report = mod.judge(lines, meta)
    expect(code == 2, "an empty directory is INVALID, got %d" % code)
    expect(any("INVALID" in l for l in report), "the report says INVALID: %s" % report)
    expect(mod.find_log(os.path.join(empty, "absent")) is None,
           "a path that is not a directory has no log")


def main():
    cases()
    capture_cases()
    replay_cases()
    playback_cases()
    bom_case()
    severity_case()
    if fails:
        print("TESTS FAILED %d case(s)" % fails)
        return 1
    print("TESTS OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
