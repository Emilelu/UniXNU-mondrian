#!/usr/bin/env python3
"""Fixture test for scripts/judge-k60-battery-mirror.py.

The fixture console line is derived from the real sheng reference report
(reports/sheng-linux-charge-734.json: bat 4156000 uV / 1452000 uA / 234 tenths /
capacity 73 / Discharging, usb online=1), so the passing case is a real pair and
every failing case changes exactly one field away from it.
"""

import json
import os
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
JUDGE = ROOT / "scripts" / "judge-k60-battery-mirror.py"
WORK = ROOT / "build" / ("battery-mirror-tests-%d" % os.getpid())

ENV = dict(os.environ, PYTHONIOENCODING="utf-8")
RUN = dict(capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV)

failures = 0
checks = 0


def check(name, got, want):
    global failures, checks
    checks += 1
    if got != want:
        failures += 1
        print("FAIL %s: got %r, want %r" % (name, got, want))
    else:
        print("ok   %s" % name)


def sample_line(**over):
    values = dict(
        kind="physical source updated", sample=12, soc="73.05", charge="4300",
        design="5000", cycles="310", voltage="4156", current="-1452", temp="23.40",
        external="1", charging="0", full="0", subscribed="1")
    values.update(over)
    return ("K60Battery: %(kind)s sample=%(sample)d SOC=%(soc)s%% "
            "charge=%(charge)s/%(design)smAh design=%(design)smAh cycles=%(cycles)s "
            "voltage=%(voltage)smV current=%(current)smA temp=%(temp)sC "
            "external=%(external)s charging=%(charging)s full=%(full)s "
            "subscribed=%(subscribed)s" % values)


def report(**over):
    fields = dict(voltage_now="4156000", current_now="1452000", temp="234",
                  capacity="73", status="Discharging")
    fields.update({k: str(v) for k, v in over.items() if k not in ("online", "drop")})
    readings = ["[charge sysfs] /sys/bus/auxiliary/devices/pmic_glink.power-supply.0/xiaomi"]
    readings += ["[charge supply] qcom-battmgr-bat %s=%s" % (k, v) for k, v in fields.items()]
    if "online" in over:
        readings.append("[charge supply] qcom-battmgr-usb online=%s" % over["online"])
    else:
        readings.append("[charge supply] qcom-battmgr-usb online=1")
    if "drop" in over:
        readings = [ln for ln in readings if not ln.endswith(" " + over["drop"] + "=" + fields.get(over["drop"], ""))]
        readings = [ln for ln in readings if ("bat %s=" % over["drop"]) not in ln]
    return json.dumps({"device": "sheng", "readings": readings}, indent=2)


def write(name, text):
    path = WORK / name
    path.write_text(text, encoding="utf-8", newline="\n")
    return str(path)


def run(console, mirror):
    return subprocess.run([sys.executable, str(JUDGE), console, "--mirror", mirror], **RUN)


def case(name, expect_rc, expect=(), forbid=(), console=None, mirror=None):
    console = console or write("console-%s.log" % name, sample_line() + "\n")
    mirror = mirror or write("mirror-%s.json" % name, report())
    result = run(console, mirror)
    text = (result.stdout or "") + (result.stderr or "")
    problems = ["rc=%d want %d" % (result.returncode, expect_rc)] if result.returncode != expect_rc else []
    for needle in expect:
        if needle not in text:
            problems.append("output lacks %r" % needle)
    for needle in forbid:
        if needle in text:
            problems.append("output carries %r" % needle)
    check(name, "; ".join(problems) or "ok", "ok")
    if problems:
        print("     ---\n" + text.rstrip() + "\n     ---")


def main():
    if WORK.exists():
        shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)

    check("judge exists", JUDGE.is_file(), True)
    check("judge compiles", (lambda: (compile(JUDGE.read_text(encoding="utf-8"), str(JUDGE), "exec"), "ok")[1])(), "ok")

    case("real pair passes", 0, ("PASS VOLTAGE   4156 mV vs 4156000 uV/1000 = 4156 mV",
                                 "PASS TEMP", "PASS EXTERNAL", "TOTAL  PASS"))
    case("current sign is a note", 0, ("TOTAL  PASS", "current sign differs"))
    case("capacity in hundredths of a percent", 1,
         ("FAIL SOC", "off by 1/100x"),
         mirror=write("mirror-cap-hundredths.json", report(capacity="7305")))
    case("temp in hundredths of a degree", 1,
         ("FAIL TEMP", "off by 1/10x"),
         mirror=write("mirror-temp-hundredths.json", report(temp="2340")))
    case("voltage off by 200 mV", 1, ("FAIL VOLTAGE", "delta=200 mV"),
         console=write("console-v.log", sample_line(voltage="4356") + "\n"))
    case("usb online disagrees", 1, ("FAIL EXTERNAL",),
         mirror=write("mirror-usb-off.json", report(online="0")))
    case("both mirror signals contradict", 1, ("FAIL CHARGING",),
         console=write("console-chg.log", sample_line(charging="1") + "\n"),
         mirror=write("mirror-chg.json", report(online="0")))
    case("one mirror signal contradicts", 0, ("PASS CHARGING", "disagrees with that status"),
         console=write("console-chg2.log", sample_line(charging="1") + "\n"))
    case("no bat supply", 2, ("no -bat supply",),
         mirror=write("mirror-nobat.json", json.dumps({"readings": ["[charge supply] qcom-battmgr-usb online=1"]})))
    case("report lacks temp", 2, ("carries no temp",),
         mirror=write("mirror-notemp.json", report(drop="temp")))
    case("report is not json", 2, ("not valid JSON",),
         mirror=write("mirror-bad.json", "{not json"))
    case("plain readings file works", 0, ("TOTAL  PASS",),
         mirror=write("mirror-plain.txt",
                      "[charge supply] qcom-battmgr-bat voltage_now=4156000\n"
                      "[charge supply] qcom-battmgr-bat current_now=1452000\n"
                      "[charge supply] qcom-battmgr-bat temp=234\n"
                      "[charge supply] qcom-battmgr-bat capacity=73\n"
                      "[charge supply] qcom-battmgr-bat status=Charging\n"
                      "[charge supply] qcom-battmgr-usb online=1\n"))
    case("console without a sample", 2, ("no 'K60Battery",),
         console=write("console-empty.log", "Fastboot: boot\n"))

    missing = subprocess.run([sys.executable, str(JUDGE), str(WORK / "nope.log"),
                              "--mirror", str(WORK / "nope.json")], **RUN)
    check("missing inputs exit 2", missing.returncode, 2)
    usage = subprocess.run([sys.executable, str(JUDGE)], **RUN)
    check("no arguments exit 2", usage.returncode, 2)

    print("TESTS OK %d checks (%d failure(s))" % (checks, failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
