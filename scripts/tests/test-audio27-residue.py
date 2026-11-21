#!/usr/bin/env python3
"""Twenty-one cases for scripts/check-audio27-residue.py."""

import copy
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
GATE = os.path.join(REPO, "scripts/check-audio27-residue.py")

AUDIO_BUNDLE = "com.apple.iokit.IOAudio2Family"
AUDIO_TARGET = "0xfffffff00b36e788"
AUDIO_SITE = "0xfffffff008273608"
COUNTER_BUNDLE = "com.apple.iokit.IOGPUFamily"
COUNTER_SITE = "0xfffffff00829c560"


def entry(bundle, target, kind, site, verdict="unreachable-before-console",
          stage="post-SpringBoard (audio client)", baseline=False, reason="filler",
          review="re-open if a frame appears before the console_init line"):
    return {
        "bundle": bundle,
        "target": target,
        "kind": kind,
        "site": site,
        "verdict": verdict,
        "stage": stage,
        "baseline": baseline,
        "reason": reason,
        "review": review,
    }


def fixture():
    """205 slots, 203 keys, 131 functions, 25 bundles, 179 + 26 kinds."""
    audio = entry(
        AUDIO_BUNDLE, AUDIO_TARGET, "__auth_got", AUDIO_SITE,
        reason=("slot __auth_got at %s is loaded only by 0xfffffff009f870bc+0x144; "
                "no code runs before console_init() (osfmk/kern/startup.c:478); "
                "the first kext entry point is PE_init_iokit() at startup.c:689"
                % AUDIO_SITE),
        review=("re-open if a K60 boot log shows a frame in %s before the "
                "console_init line" % AUDIO_BUNDLE))
    counter = entry(COUNTER_BUNDLE, AUDIO_TARGET, "__auth_got", COUNTER_SITE,
                    stage="display bring-up, before SpringBoard")
    targets = [audio, counter]
    for index in range(203):
        # The last two repeat the first two (bundle,target) keys while keeping
        # their own sites, which is how the audit gets 205 slots but 203 keys.
        key = index - 201 if index >= 201 else index
        targets.append(entry(
            "B_%d" % (key % 23),
            "T_%d" % (key % 130),
            "__auth_got" if index < 177 else "__const",
            "0xfffffff000000000+%04x" % index))
    return targets


def write(path, targets):
    lines = []
    for item in targets:
        lines.append("[[target]]")
        for key in ("bundle", "target", "kind", "site", "verdict", "stage",
                    "reason", "review"):
            lines.append("%s = %s" % (key, json.dumps(item[key], ensure_ascii=False)))
        lines.append("baseline = %s" % ("true" if item["baseline"] else "false"))
        lines.append("")
    io.open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines))


def run(path):
    return subprocess.run([sys.executable, GATE, "--audit", path],
                          capture_output=True, text=True)


def main():
    base = tempfile.mkdtemp(prefix="residue-")
    kept = 0
    cases = [
        ("all three criteria hold", 0,
         ["RESIDUE OK: criterion 1:",
          "RESIDUE OK: criterion 3: slots=205 keys=203 functions=131 bundles=25",
          "RESIDUE OK: counterexample="], None),
        ("audio slot missing", 1,
         ["no %s slot in the audit" % AUDIO_BUNDLE], lambda es: es.pop(0)),
        ("audio kind is not a pointer", 1,
         ["audio slot kind is __text, expected __auth_got"],
         lambda es: es[0].update(kind="__text")),
        ("audio target moved", 1,
         ["audio slot target is 0xdeadbeef, expected %s" % AUDIO_TARGET],
         lambda es: es[0].update(target="0xdeadbeef")),
        ("audio site moved", 1,
         ["audio slot site is 0xdead, expected %s" % AUDIO_SITE],
         lambda es: es[0].update(site="0xdead")),
        ("loader missing from reason", 1,
         ["does not name loader 0xfffffff009f870bc+0x144"],
         lambda es: es[0].update(reason="slot")),
        ("console line missing", 1,
         ["does not name console_init() at osfmk/kern/startup.c:478"],
         lambda es: es[0].update(reason=es[0]["reason"].replace(
             "osfmk/kern/startup.c:478", "osfmk/kern/startup.c:999"))),
        ("stage is not post-SpringBoard", 1,
         ["audio slot stage is boot-time, expected post-SpringBoard (audio client)"],
         lambda es: es[0].update(stage="boot-time")),
        ("verdict is reachable", 1,
         ["audio slot verdict is reachable-early, expected unreachable-before-console",
          "slot(s) are not unreachable-before-console"],
         lambda es: es[0].update(verdict="reachable-early")),
        ("baseline is claimed", 1,
         ["audio slot baseline is true, expected false"],
         lambda es: es[0].update(baseline=True)),
        ("review has no falsifier", 1,
         ["audio slot review does not say when to re-open"],
         lambda es: es[0].update(review="no falsifier")),
        ("IOGPU counterexample missing", 1,
         ["no %s reference to %s at %s" % (COUNTER_BUNDLE, AUDIO_TARGET, COUNTER_SITE)],
         lambda es: es.pop(1)),
        ("slot count drifts", 1, ["audit has 204 slot(s), expected 205"],
         lambda es: es.pop()),
        ("key count drifts", 1,
         ["unique (bundle,target) key(s), expected 203"],
         lambda es: es[203].update(target="T_NEW")),
        ("site count drifts", 1, ["unique site(s), expected 205"],
         lambda es: es[2].update(site=es[3]["site"])),
        ("function count drifts", 1,
         ["distinct target function(s), expected 131"],
         lambda es: es[2].update(target="T_NEW")),
        ("bundle count drifts", 1, ["bundle(s), expected 25"],
         lambda es: es[2].update(bundle="B_NEW")),
        ("auth_got count drifts", 1,
         ["__auth_got slot(s), expected 179"],
         lambda es: es[2].update(kind="__const")),
    ]
    for name, want, needles, mutate in cases:
        targets = copy.deepcopy(fixture())
        if mutate is not None:
            mutate(targets)
        path = os.path.join(base, name.replace(" ", "-") + ".toml")
        write(path, targets)
        done = run(path)
        text = done.stdout + done.stderr
        good = done.returncode == want and all(needle in text for needle in needles)
        if not good:
            print("FAILED %s: exit %d, wanted %d\n%s"
                  % (name, done.returncode, want, text.strip()))
        kept += 1 if good else 0

    # A missing file and a malformed file are not a pass.
    missing = run(os.path.join(base, "absent.toml"))
    text = missing.stdout + missing.stderr
    good = missing.returncode == 3 and "RESIDUE SKIP: no audit file" in text
    if not good:
        print("FAILED missing file: exit %d\n%s" % (missing.returncode, text.strip()))
    kept += 1 if good else 0

    broken = os.path.join(base, "broken.toml")
    io.open(broken, "w", encoding="utf-8", newline="\n").write("[[target]\n")
    done = run(broken)
    text = done.stdout + done.stderr
    good = done.returncode == 1 and "RESIDUE FAILED:" in text
    if not good:
        print("FAILED malformed file: exit %d\n%s" % (done.returncode, text.strip()))
    kept += 1 if good else 0

    help_run = subprocess.run([sys.executable, GATE, "--help"],
                              capture_output=True, text=True)
    text = help_run.stdout + help_run.stderr
    good = help_run.returncode == 0 and "usage:" in text
    if not good:
        print("FAILED help: exit %d\n%s" % (help_run.returncode, text.strip()))
    kept += 1 if good else 0

    total = len(cases) + 3
    shutil.rmtree(base, ignore_errors=True)
    if kept != total:
        print("TESTS FAILED %d of %d cases" % (total - kept, total))
        return 1
    print("TESTS OK %d cases" % total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
