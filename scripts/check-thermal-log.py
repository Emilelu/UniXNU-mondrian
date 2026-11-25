#!/usr/bin/env python3
"""Read a thermal boot log against docs/research/thermal/CRITERIA.toml.

The criteria file is the machine-readable form of LEVEL-MAP.md section 5.3: every
row there is a sentence a person has to apply by reading the log. This script
applies the same rows as regular expressions, so a boot verdict does not depend on
someone scrolling 200 KB of console output.

Usage:
    python3 scripts/check-thermal-log.py                 # newest usblog
    python3 scripts/check-thermal-log.py --log FILE
    python3 scripts/check-thermal-log.py --profile cold  # force a profile
    python3 scripts/check-thermal-log.py --self-test     # prove it can fail

Exit code 0 only when every required criterion of the selected profile passes.
An advisory criterion prints a warning and never changes the exit code.
"""
import argparse
import json
import os
import re
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CRITERIA = REPO / "docs" / "research" / "thermal" / "CRITERIA.toml"


def load_criteria(path=CRITERIA):
    with open(path, "rb") as handle:
        return tomllib.load(handle)


def read_lines(path):
    """console.log carries NUL bytes; read bytes, then decode leniently."""
    text = Path(path).read_bytes().decode("utf-8", errors="replace")
    return [line.rstrip("\r") for line in text.split("\n")]


def newest_log(root):
    best = None
    for path in Path(root).glob("usblog-*/console.log"):
        if path.stat().st_size <= 4096:
            continue
        if best is None or path.stat().st_mtime > best.stat().st_mtime:
            best = path
    return best


def detect_profile(lines):
    """A bias line names the profile; without one the run is the cold baseline."""
    for line in lines:
        found = re.search(r"^PongThermal: bias (\d+) mC added", line)
        if found:
            return "bias-" + found.group(1)
    return "cold"


def check_count(criterion, lines):
    hits = [line for line in lines if re.search(criterion["pattern"], line)]
    low = criterion.get("min")
    high = criterion.get("max")
    if low is not None and len(hits) < low:
        return False, "%d line(s), need at least %d" % (len(hits), low)
    if high is not None and len(hits) > high:
        return False, "%d line(s), allow at most %d" % (len(hits), high)
    return True, "%d line(s)" % len(hits)


def check_each(criterion, lines):
    hits = [line for line in lines if re.search(criterion["pattern"], line)]
    if not hits:
        return False, "pattern matched nothing"
    bad = [line for line in hits if not re.search(criterion["must"], line)]
    if bad:
        return False, "%d of %d line(s) disagree, first: %s" % (len(bad), len(hits), bad[0].strip())
    return True, "%d line(s) agree" % len(hits)


def check_coverage(criterion, lines):
    seen = []
    for line in lines:
        found = re.search(criterion["pattern"], line)
        if found:
            label = found.group(criterion.get("label_group", 1))
            if label not in seen:
                seen.append(label)
    expected = criterion["expected"]
    missing = [name for name in expected if name not in seen]
    extra = [name for name in seen if name not in expected]
    allowed = criterion.get("max_missing", 0)
    if extra:
        return False, "unexpected label(s): %s" % ", ".join(extra)
    if len(missing) > allowed:
        return False, "%d missing (allow %d): %s" % (len(missing), allowed, ", ".join(missing))
    if missing:
        return True, "%d/%d labels, missing %s (within allowance)" % (len(seen), len(expected), ", ".join(missing))
    return True, "%d/%d labels" % (len(seen), len(expected))


def check_pair(criterion, lines):
    last_level = None
    published = 0
    for line in lines:
        level = re.search(criterion["level_pattern"], line)
        if level:
            last_level = level.group(1)
            continue
        found = re.search(criterion["pattern"], line)
        if not found:
            continue
        published += 1
        if last_level is None:
            return False, "published before any level line: %s" % line.strip()
        if found.group(1) != last_level:
            return False, "published level %s after level line %s" % (found.group(1), last_level)
    if published == 0:
        return False, "no published line to pair"
    return True, "%d published line(s) follow their level" % published


CHECKS = {"count": check_count, "each": check_each,
          "coverage": check_coverage, "pair": check_pair}


def image_of(log_path):
    """The image name and digest recorded beside a captured log, if any.

    record-boot writes boot.json next to console.log with the path it booted;
    the file starts with a BOM because PowerShell wrote it, so decode as
    utf-8-sig. The tag is the artifact directory name, which is what the
    ladder hint needs: thermal-20261115a and later carry the zone ladder.
    """
    boot = os.path.join(os.path.dirname(os.path.abspath(log_path)), "boot.json")
    try:
        with open(boot, "rb") as handle:
            document = json.loads(handle.read().decode("utf-8-sig", "replace"))
    except (OSError, ValueError):
        return None
    image = str(document.get("image") or document.get("tag") or "?")
    tag = os.path.basename(os.path.dirname(image.replace(chr(92), "/"))) or image
    digest = str(document.get("imageSha256") or document.get("kernel_sha256") or "?")
    return tag, image, digest[:16]


def print_ladder_hint(document, lines, failures, log_path=None):
    """Distinguish a broken ladder from a kernel that has no ladder yet."""
    if not failures:
        return
    if not any(item[0]["id"].startswith(("level.", "published.follows", "cold.level"))
               for item in failures):
        return
    for criterion in document.get("criterion", []):
        if criterion["id"] != "level.line":
            continue
        if any(re.search(criterion["pattern"], line) for line in lines):
            return
        print("       note: no \"level N/3\" line at all. Every kernel before thermal-20261115a")
        print("       prints only the publisher line, so these criteria are not applicable.")
        image = image_of(log_path) if log_path else None
        if image is not None:
            tag, path, digest = image
            print("       this log came from image %s (%s, boot.img sha256 %s...)" % (tag, path, digest))
            print("       confirm the tag first: a ladder kernel is thermal-20261115a or later.")
        else:
            print("       no boot.json beside the log; check the image tag before reading this")
            print("       as a defect.")
        return


def evaluate(document, lines, profile, verbose=True, log_path=None):
    failures = []
    advisories = []
    passed = 0
    skipped = 0
    for criterion in document.get("criterion", []):
        wanted = criterion.get("profile", "*")
        if wanted != "*" and wanted != profile:
            skipped += 1
            continue
        check = CHECKS.get(criterion.get("kind", "count"))
        if check is None:
            failures.append((criterion, "unknown kind %r" % criterion.get("kind")))
            continue
        ok, detail = check(criterion, lines)
        if ok:
            passed += 1
            if verbose:
                print("  ok   %-30s %s" % (criterion["id"], detail))
            continue
        if criterion.get("severity", "required") == "advisory":
            advisories.append((criterion, detail))
            if verbose:
                print("  warn %-30s %s" % (criterion["id"], detail))
        else:
            failures.append((criterion, detail))
            if verbose:
                print("  FAIL %-30s %s" % (criterion["id"], detail))
    if verbose:
        for criterion, _ in failures + advisories:
            print("       %s: %s" % (criterion["title"], criterion.get("why", "")))
            if criterion.get("see"):
                print("       -> see: %s" % criterion["see"])
        print_ladder_hint(document, lines, failures, log_path)
        print("  %d passed, %d failed, %d advisory, %d outside profile %r" % (passed, len(failures), len(advisories), skipped, profile))
    return failures, advisories


GOOD_CONTROLLERS = [
    "PongThermal: tsens0 tm=0xc263000 srot=0xc222000 ver=2.8.0 ctrl=0x9d67fff9 enabled=1",
    "PongThermal: tsens1 tm=0xc265000 srot=0xc223000 ver=2.8.0 ctrl=0x9d67fff9 enabled=1",
    "PongThermal: polling 2 controllers every 1000 ms",
]

SENSORS = [
    (0, 0, "aoss-0", 24), (0, 1, "cpuss-0", 25), (0, 2, "cpuss-1", 26),
    (0, 3, "cpuss-2", 27), (0, 4, "cpuss-3", 28), (0, 5, "cpu-1-0", 29),
    (0, 6, "cpu-1-1", 30), (0, 7, "cpu-1-2", 31), (0, 8, "cpu-1-3", 32),
    (0, 9, "cpu-1-4", 33), (0, 10, "cpu-1-5", 34), (0, 11, "cpu-1-6", 35),
    (0, 12, "cpu-1-7", 36), (0, 13, "cpu-1-8", 37), (0, 14, "gpuss-0", 38),
    (0, 15, "gpuss-1", 39), (1, 0, "aoss-1", 40), (1, 1, "cpu-0-0", 41),
    (1, 2, "cpu-0-1", 42), (1, 3, "cpu-0-2", 43), (1, 4, "cpu-0-3", 44),
    (1, 5, "nspss-0", 45), (1, 6, "nspss-1", 46), (1, 7, "nspss-2", 47),
    (1, 8, "video", 48), (1, 9, "ddr", 49), (1, 10, "mdmss-0", 50),
    (1, 11, "mdmss-1", 51), (1, 12, "mdmss-2", 52), (1, 13, "mdmss-3", 53),
    (1, 14, "camera-0", 54), (1, 15, "camera-1", 55),
]

LEVEL_NAMES = ["nominal", "moderate", "heavy", "trapping"]
BIAS_LEVEL = {"50000": 1, "75000": 2, "85000": 3}


def fabricate(profile="cold", drop_sensors=0):
    """A log that satisfies its profile, before any mutation."""
    lines = list(GOOD_CONTROLLERS)
    level = 0
    if profile != "cold":
        bias = profile.split("-", 1)[1]
        lines.insert(2, "PongThermal: bias %s mC added to every reading (validation only)" % bias)
        level = BIAS_LEVEL[bias]
    for slot, (controller, index, name, zone) in enumerate(SENSORS):
        if slot < drop_sensors:
            continue
        lines.append("PongThermal: tsens%d[%d] %s zone%d 42.0 C" % (controller, index, name, zone))
    lines.append("PongThermal: little=42000 big=42600 gpu=43000 npu=42400 ddr=42000 mC")
    lines.append("PongThermal: level %d/3 %s (domains 0/3); closest ddr 42.0 C, 48.0 C below tier 1" % (level, LEVEL_NAMES[level]))
    lines.append("PongThermal: level %s (%d) published as Thermal_Level_Warning=%d" % (LEVEL_NAMES[level], level, level))
    return lines


def self_test():
    """A verifier that cannot fail is worse than none (see test-verify-boot-image.py)."""
    document = load_criteria()
    problems = []

    def expect(label, lines, profile, want_pass):
        failures, _ = evaluate(document, lines, profile, verbose=False)
        got = not failures
        if got != want_pass:
            problems.append("%s: expected %s, got %s (%s)" % (
                label, "pass" if want_pass else "fail",
                "pass" if got else "fail",
                ", ".join(item[0]["id"] for item in failures)))

    for profile in ("cold", "bias-50000", "bias-75000", "bias-85000"):
        expect("clean " + profile, fabricate(profile), profile, True)
    expect("one sensor lost", fabricate("cold", drop_sensors=1), "cold", True)
    expect("two sensors lost", fabricate("cold", drop_sensors=2), "cold", False)
    lines = [line for line in fabricate("cold") if "tsens1 tm=" not in line]
    expect("one controller lost", lines, "cold", False)
    lines = [line for line in fabricate("cold") if "level 0/3" not in line]
    expect("no level line", lines, "cold", False)
    lines = fabricate("cold")
    lines.append("PongThermal: tsens1[3] cpu-0-2 zone43 raw=0x0 no-valid-reading")
    expect("a no-valid-reading line", lines, "cold", False)
    lines = fabricate("cold")
    lines[-1] = "PongThermal: level nominal (0) published as Thermal_Level_Warning=9"
    expect("published value out of range", lines, "cold", False)
    # The publisher dedupes on the level (pong_thermal_pm.cpp:87-89), so a second
    # line at the same level means the dedupe broke, not that a sample was lost.
    lines = fabricate("cold")
    lines.append(lines[-1])
    expect("the same level published twice", lines, "cold", False)
    lines = fabricate("cold")
    lines[-1] = "PongThermal: level nominal (1) published as Thermal_Level_Warning=1"
    expect("name and value disagree", lines, "cold", False)
    lines = [line for line in fabricate("cold") if "level 0/3" not in line]
    lines[-1] = "PongThermal: level nominal (0) published as Thermal_Level_Warning=0"
    expect("a kernel from before the ladder", lines, "cold", False)
    expect("cold log judged as a bias run", fabricate("cold"), "bias-50000", False)
    expect("bias log judged as cold", fabricate("bias-50000"), "cold", False)

    if problems:
        print("FAILED: %d self-test case(s)" % len(problems))
        for problem in problems:
            print("  - " + problem)
        return 1
    print("self-test OK: the clean logs pass and every mutation fails")
    return 0


def main():
    parser = argparse.ArgumentParser(description="apply CRITERIA.toml to a boot log")
    parser.add_argument("--criteria", help="criteria TOML; default docs/research/thermal/CRITERIA.toml")
    parser.add_argument("--log", help="console.log to read; default the newest usblog")
    parser.add_argument("--profile", default="auto", help="auto, cold, or bias-<milli>")
    parser.add_argument("--list-profiles", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    document = load_criteria(Path(args.criteria) if args.criteria else CRITERIA)

    profiles = sorted({c.get("profile", "*") for c in document.get("criterion", [])} - {"*"})
    if args.list_profiles:
        print("profiles: * (always), " + ", ".join(profiles))
        return 0
    if args.self_test:
        return self_test()

    if args.log:
        path = Path(args.log)
        if not path.exists():
            print("FAILED: no such log: %s" % path)
            return 2
    else:
        root = document.get("log", {}).get("evidence_root", "/mnt/e/iOS Port/Work/evidence")
        path = newest_log(root)
        if path is None:
            print("FAILED: no usblog-*/console.log over 4 KB under %s" % root)
            return 2

    lines = read_lines(path)
    profile = detect_profile(lines) if args.profile == "auto" else args.profile
    if profile not in profiles:
        print("FAILED: unknown profile %r; known: %s" % (profile, ", ".join(profiles)))
        return 2
    if not args.quiet:
        print("thermal criteria: %s (%d lines, profile %s)" % (path, len(lines), profile))
    failures, advisories = evaluate(document, lines, profile, verbose=not args.quiet,
                                     log_path=path)
    if failures:
        print("FAILED: %d required criterion/criteria failed (profile %s)" % (len(failures), profile))
        return 1
    print("OK: every required criterion holds (profile %s, %d advisory)" % (profile, len(advisories)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
