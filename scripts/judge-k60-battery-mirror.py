#!/usr/bin/env python3
"""Judge our published battery snapshot against a sheng Linux charge mirror.

官网 power §4 step 6 asks for the raw readings and the published properties to be
compared against the target gauge or the vendor system reading. On this board the
ADSP owns charge control, so the honest offline comparison is between what our
driver publishes and what sheng's Linux reader saw on the same firmware protocol.

sheng reads the same PMIC GLINK firmware through Linux power_supply
(scripts/charge-sheng-linux.py, reference output
reports/sheng-linux-charge-734.json) and writes lines shaped

    [charge supply] qcom-battmgr-bat voltage_now=4156000
    [charge supply] qcom-battmgr-bat current_now=1452000
    [charge supply] qcom-battmgr-bat temp=234
    [charge supply] qcom-battmgr-bat capacity=73
    [charge supply] qcom-battmgr-bat status=Discharging
    [charge supply] qcom-battmgr-usb  online=1

Those values are in Linux power_supply units: microvolts, microamps, tenths of a
degree, whole percent. Our console prints millivolts, milliamps, hundredths of a
degree and hundredths of a percent. A comparison that forgets one factor still
passes a naive equality test, so this judge converts both sides into one base
unit, states the conversion it applied, and names the factor when a field is off
by exactly 10, 100 or 1000 - that is a unit slip, not a measurement.

Criteria:
  CONSOLE   the console carries at least one published battery sample line
  MIRROR    the mirror parses and carries a -bat supply with the four fields
  SOC       |our SOC - mirror capacity| <= 3.00 percentage points
  VOLTAGE   |our mV - mirror uV/1000| <= 60 mV
  CURRENT   |our mA| vs |mirror uA/1000| within 150 mA (magnitude; sign is a note)
  TEMP      |our hundredths - mirror tenths*10| <= 300 hundredths (3 C)
  EXTERNAL  our external flag agrees with the mirror's usb online flag
  CHARGING  our charging/full flags do not contradict BOTH mirror signals
            (status and the usb online flag); one contradicting signal is a note

Deliberate leniencies, both proven against the real sheng report:
  - the reference report carries usb online=1 together with bat
    status=Discharging and a positive current_now. Those mirror fields disagree
    with each other, so a disagreement with our flags can only be a note unless
    both mirror signals point the other way.
  - the current sign is a per-protocol convention (page §4 step 2 asks for it to
    be confirmed before use); the judge compares magnitude and prints both signs.

Exit: 0 PASS, 1 FAIL, 2 INVALID (an input is unusable) or usage.
"""

import argparse
import json
import pathlib
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

SAMPLE_RE = re.compile(
    r"K60Battery: (physical source published|physical source updated|physical source refreshed) "
    r"sample=(\d+) SOC=(\d+)\.(\d+)% charge=(\d+)/(\d+)mAh design=(\d+)mAh "
    r"cycles=(\d+) voltage=(\d+)mV current=(-?\d+)mA (?:current-source=[a-z]+ )?temp=(-?\d+)\.(\d+)C "
    r"external=(\d+) charging=(\d+) full=(\d+) subscribed=(\d+)")

# The same window judge-battery.py uses for its C3 Android comparison.
V_TOL_MV = 60
I_TOL_MA = 150
SOC_TOL_HUNDREDTHS = 300
T_TOL_HUNDREDTHS = 300


def read_text(path):
    return pathlib.Path(path).read_text(encoding="utf-8", errors="replace")


def parse_console(text):
    """Return the last published sample in base units, or None."""
    last = None
    for line in text.splitlines():
        match = SAMPLE_RE.search(line)
        if match:
            last = match
    if last is None:
        return None
    g = last.groups()
    # groups: kind, sample, soc, soc-frac, charge, charge-full, design, cycles,
    #         voltage, current, temp, temp-frac, external, charging, full, subscribed
    whole, frac = int(g[10]), int(g[11])
    sign = -1 if g[10].startswith("-") else 1
    return {
        "sample": int(g[1]),
        "soc": int(g[2]) * 100 + int(g[3]),
        "charge": int(g[4]),
        "design": int(g[6]),
        "cycles": int(g[7]),
        "voltage_mv": int(g[8]),
        "current_ma": int(g[9]),
        "temp_hundredths": whole * 100 + sign * frac,
        "external": int(g[12]),
        "charging": int(g[13]),
        "full": int(g[14]),
    }


def parse_mirror(path):
    """Return ({"battery": {...}, "usb": {...}}, problems)."""
    problems = []
    raw = read_text(path)
    if raw.lstrip().startswith("{"):
        try:
            report = json.loads(raw)
        except json.JSONDecodeError as error:
            return {}, ["the report is not valid JSON: %s" % error]
        readings = report.get("readings")
        if not isinstance(readings, list):
            return {}, ["the report carries no readings list"]
        lines = [str(item) for item in readings]
    else:
        lines = raw.splitlines()
    battery, usb = {}, {}
    for line in lines:
        match = re.search(r"\[charge supply\]\s+(\S+)\s+(\w+)=(\S+)", line)
        if not match:
            continue
        supply, key, value = match.group(1), match.group(2), match.group(3)
        if supply.endswith("-bat"):
            battery[key] = value
        elif supply.endswith("-usb"):
            usb[key] = value
    if not battery:
        problems.append("the mirror carries no -bat supply (nothing to compare)")
    for field in ("capacity", "voltage_now", "current_now", "temp"):
        if battery and field not in battery:
            problems.append("the mirror -bat supply carries no %s" % field)
    return {"battery": battery, "usb": usb}, problems


def as_int(value, field, problems):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        problems.append("the mirror %s is not a whole number: %r" % (field, value))
        return None


def factor_note(ours, theirs, ours_unit, theirs_unit):
    """Name the unit slip when the two sides differ by one power of ten."""
    if not ours or not theirs:
        return ""
    ratio = float(ours) / float(theirs)
    for factor in (1000.0, 100.0, 10.0):
        if abs(ratio - factor) < 0.02 * factor:
            return " (off by %gx: mirror in %s, this side in %s)" % (factor, theirs_unit, ours_unit)
        if abs(ratio - 1.0 / factor) < 0.02 / factor:
            return " (off by 1/%gx: mirror in %s, this side in %s)" % (factor, theirs_unit, ours_unit)
    return ""


def judge(console_path, mirror_path):
    checks = []
    notes = []

    def record(name, ok, detail):
        checks.append({"name": name, "ok": ok, "detail": detail})

    sample = parse_console(read_text(console_path))
    if sample is None:
        record("CONSOLE", False, "no 'K60Battery: ... sample=' line in this console")
        return checks, notes, "INVALID"
    record("CONSOLE", True, "sample=%d SOC=%d.%02d%%" % (
        sample["sample"], sample["soc"] // 100, sample["soc"] % 100))

    mirror, problems = parse_mirror(mirror_path)
    if problems:
        for problem in problems:
            record("MIRROR", False, problem)
        return checks, notes, "INVALID"
    battery, usb = mirror["battery"], mirror["usb"]
    record("MIRROR", True, "bat supply %d field(s), usb supply %d field(s)" % (
        len(battery), len(usb)))

    unparseable = []
    capacity = as_int(battery["capacity"], "capacity", unparseable)
    if capacity is not None:
        theirs = capacity * 100
        delta = abs(sample["soc"] - theirs)
        extra = ""
        if delta > SOC_TOL_HUNDREDTHS:
            extra = factor_note(sample["soc"], theirs, "hundredths of a percent", "whole percent")
        record("SOC", delta <= SOC_TOL_HUNDREDTHS,
               "%d.%02d%% vs %d%% (capacity*100) delta=%d.%02dpp%s" % (
                   sample["soc"] // 100, sample["soc"] % 100, capacity,
                   delta // 100, delta % 100, extra))

    microvolts = as_int(battery["voltage_now"], "voltage_now", unparseable)
    if microvolts is not None:
        theirs = int(round(microvolts / 1000.0))
        delta = abs(sample["voltage_mv"] - theirs)
        extra = ""
        if delta > V_TOL_MV:
            extra = factor_note(sample["voltage_mv"], theirs, "millivolts", "microvolts")
        record("VOLTAGE", delta <= V_TOL_MV,
               "%d mV vs %d uV/1000 = %d mV delta=%d mV%s" % (
                   sample["voltage_mv"], microvolts, theirs, delta, extra))

    microamps = as_int(battery["current_now"], "current_now", unparseable)
    if microamps is not None:
        theirs = int(round(abs(microamps) / 1000.0))
        ours = abs(sample["current_ma"])
        delta = abs(ours - theirs)
        extra = ""
        if delta > I_TOL_MA:
            extra = factor_note(ours, theirs, "milliamps", "microamps")
        record("CURRENT", delta <= I_TOL_MA,
               "|%d| mA vs |%d| uA/1000 = %d mA delta=%d mA%s" % (
                   sample["current_ma"], microamps, theirs, delta, extra))
        if (sample["current_ma"] < 0) != (microamps < 0):
            notes.append("current sign differs (ours %d mA, mirror %d uA): a sign is a "
                         "protocol convention, not a fault (page §4 step 2)"
                         % (sample["current_ma"], microamps))

    tenths = as_int(battery["temp"], "temp", unparseable)
    if tenths is not None:
        theirs = tenths * 10
        delta = abs(sample["temp_hundredths"] - theirs)
        extra = ""
        if delta > T_TOL_HUNDREDTHS:
            extra = factor_note(sample["temp_hundredths"], theirs,
                                "hundredths of a degree", "tenths of a degree")
        record("TEMP", delta <= T_TOL_HUNDREDTHS,
               "%d.%02dC vs %d (tenths)*10 = %d.%02dC delta=%d.%02dC%s" % (
                   sample["temp_hundredths"] // 100, abs(sample["temp_hundredths"] % 100),
                   tenths, int(theirs / 100), abs(theirs % 100), delta // 100, delta % 100, extra))

    online = usb.get("online")
    usb_online = None
    if online is not None:
        value = as_int(online, "usb online", unparseable)
        if value is not None:
            usb_online = value != 0
            record("EXTERNAL", (sample["external"] != 0) == usb_online,
                   "our external=%d, mirror usb online=%d" % (sample["external"], value))
    else:
        notes.append("the mirror carries no usb supply; the external flag is unchecked")

    status = battery.get("status")
    if status is None:
        notes.append("the mirror carries no bat status; the charging flags are unchecked")
    else:
        ours = sample["charging"] != 0 or sample["full"] != 0
        says_discharging = status.strip().lower() == "discharging"
        if ours and says_discharging and usb_online is False:
            record("CHARGING", False,
                   "we publish charging=%d full=%d but the mirror says status=%s with usb online=0"
                   % (sample["charging"], sample["full"], status))
        else:
            record("CHARGING", True, "our charging=%d full=%d, mirror status=%s" % (
                sample["charging"], sample["full"], status))
            if ours and says_discharging:
                notes.append("we publish charging/full while the mirror says %s; its own usb "
                             "online=%s disagrees with that status, so this is a note, not a fault"
                             % (status, online))

    for problem in unparseable:
        record("MIRROR", False, problem)

    for field in ("charge", "design", "cycles"):
        notes.append("we publish %s=%d, the mirror publishes no equivalent field"
                     % (field, sample[field]))

    if any(not check["ok"] and check["name"] == "MIRROR" for check in checks):
        return checks, notes, "INVALID"
    return checks, notes, "PASS" if all(check["ok"] for check in checks) else "FAIL"


def main(argv):
    parser = argparse.ArgumentParser(
        description="Compare a K60 battery sample against a sheng Linux charge mirror")
    parser.add_argument("console", help="console.log carrying K60Battery sample lines")
    parser.add_argument("--mirror", required=True,
                        help="sheng report JSON, or a plain [charge supply] readings file")
    args = parser.parse_args(argv)

    console_path = pathlib.Path(args.console)
    mirror_path = pathlib.Path(args.mirror)
    for path in (console_path, mirror_path):
        if not path.is_file():
            print("judge-k60-battery-mirror: not a file: %s" % path, file=sys.stderr)
            return 2

    checks, notes, verdict = judge(console_path, mirror_path)
    for check in checks:
        print("%s %-9s %s" % ("PASS" if check["ok"] else "FAIL", check["name"], check["detail"]))
    for note in notes:
        print("       - %s" % note)
    print("TOTAL  %s" % verdict)
    if verdict == "PASS":
        return 0
    return 2 if verdict == "INVALID" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
