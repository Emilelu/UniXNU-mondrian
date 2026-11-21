#!/usr/bin/env python3
"""Are the three IOAudio2Family residue criteria still true?

The audio page records one stubbed IOAudio2Family slot and three claims about it:
the slot is a kext-held pointer rather than a call site, its only loader belongs
to the post-SpringBoard audio-client path, and no kext code runs before
console_init(). This gate re-reads the audit table that produced those claims and
turns each one into a field comparison. It deliberately carries the expected
numbers and addresses in the source, so a changed audit cannot silently keep the
page green.

The audit file is outside the repository. The gate accepts --audit, then
AUDIO27_RESIDUE_AUDIT, K60_AUDIT, /mnt/e/k60-work/scratch/stubs/unreachable.toml
and E:/k60-work/scratch/stubs/unreachable.toml. A missing file exits 3; a file
that parses but disagrees exits 1 and names the field.

Usage: python3 scripts/check-audio27-residue.py [--audit PATH]
"""

import argparse
import collections
import os
import sys

try:
    import tomllib
except ImportError:  # pragma: no cover - the build hosts use Python 3.11+
    tomllib = None

AUDIO_BUNDLE = "com.apple.iokit.IOAudio2Family"
AUDIO_TARGET = "0xfffffff00b36e788"
AUDIO_KIND = "__auth_got"
AUDIO_SITE = "0xfffffff008273608"
AUDIO_LOADER = "0xfffffff009f870bc+0x144"
AUDIO_STAGE = "post-SpringBoard (audio client)"
COUNTER_BUNDLE = "com.apple.iokit.IOGPUFamily"
COUNTER_SITE = "0xfffffff00829c560"
CONSOLE_LINE = "osfmk/kern/startup.c:478"
PE_INIT_LINE = "startup.c:689"
EXPECTED_SLOTS = 205
EXPECTED_KEYS = 203
EXPECTED_FUNCTIONS = 131
EXPECTED_BUNDLES = 25
EXPECTED_AUTH_GOT = 179
EXPECTED_CONST = 26
DEFAULT_AUDIT = "/mnt/e/k60-work/scratch/stubs/unreachable.toml"
WINDOWS_AUDIT = "E:/k60-work/scratch/stubs/unreachable.toml"


def show(value):
    """Print booleans the way the audit writes them, not as 0/1."""
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "none"
    return str(value)


def candidates():
    for name in ("AUDIO27_RESIDUE_AUDIT", "K60_AUDIT"):
        value = os.environ.get(name)
        if value:
            yield value
    yield DEFAULT_AUDIT
    yield WINDOWS_AUDIT


def resolve(path):
    if path:
        return path if os.path.isfile(path) else None
    for candidate in candidates():
        if os.path.isfile(candidate):
            return candidate
    return None


def load(path):
    if tomllib is None:
        return None, "this python3 has no tomllib; use Python 3.11 or newer"
    try:
        with open(path, "rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as error:
        return None, str(error)
    targets = data.get("target")
    if not isinstance(targets, list):
        return None, "no [[target]] array"
    if any(not isinstance(item, dict) for item in targets):
        return None, "a [[target]] entry is not a table"
    return targets, None


def check(targets):
    problems = []
    slots = len(targets)
    keys = len({(item.get("bundle"), item.get("target")) for item in targets})
    sites = len({item.get("site") for item in targets})
    functions = len({item.get("target") for item in targets})
    bundles = len({item.get("bundle") for item in targets})
    kinds = collections.Counter(item.get("kind") for item in targets)

    if slots != EXPECTED_SLOTS:
        problems.append("audit has %d slot(s), expected %d" % (slots, EXPECTED_SLOTS))
    if keys != EXPECTED_KEYS:
        problems.append("audit has %d unique (bundle,target) key(s), expected %d"
                        % (keys, EXPECTED_KEYS))
    if sites != EXPECTED_SLOTS:
        problems.append("audit has %d unique site(s), expected %d"
                        % (sites, EXPECTED_SLOTS))
    if functions != EXPECTED_FUNCTIONS:
        problems.append("audit has %d distinct target function(s), expected %d"
                        % (functions, EXPECTED_FUNCTIONS))
    if bundles != EXPECTED_BUNDLES:
        problems.append("audit has %d bundle(s), expected %d"
                        % (bundles, EXPECTED_BUNDLES))
    if kinds.get("__auth_got", 0) != EXPECTED_AUTH_GOT:
        problems.append("audit has %d __auth_got slot(s), expected %d"
                        % (kinds.get("__auth_got", 0), EXPECTED_AUTH_GOT))
    if kinds.get("__const", 0) != EXPECTED_CONST:
        problems.append("audit has %d __const slot(s), expected %d"
                        % (kinds.get("__const", 0), EXPECTED_CONST))

    bad_kind = [item for item in targets if item.get("kind") not in ("__auth_got", "__const")]
    if bad_kind:
        problems.append("%d slot(s) are not pointer slots: %s"
                        % (len(bad_kind), ", ".join("%s %s %s" % (
                            item.get("bundle"), item.get("site"), item.get("kind"))
                            for item in bad_kind[:3])))

    bad_verdict = [item for item in targets
                   if item.get("verdict") != "unreachable-before-console"]
    if bad_verdict:
        problems.append("%d slot(s) are not unreachable-before-console: %s"
                        % (len(bad_verdict), ", ".join("%s %s" % (
                            item.get("bundle"), item.get("verdict"))
                            for item in bad_verdict[:3])))

    audio = [item for item in targets if item.get("bundle") == AUDIO_BUNDLE]
    if not audio:
        problems.append("no %s slot in the audit" % AUDIO_BUNDLE)
    elif len(audio) > 1:
        problems.append("%d %s slots in the audit, expected 1"
                        % (len(audio), AUDIO_BUNDLE))
    else:
        item = audio[0]
        for field, expected in (("target", AUDIO_TARGET),
                                ("kind", AUDIO_KIND),
                                ("site", AUDIO_SITE),
                                ("verdict", "unreachable-before-console"),
                                ("stage", AUDIO_STAGE)):
            got = item.get(field)
            if got != expected:
                problems.append("audio slot %s is %s, expected %s"
                                % (field, show(got), show(expected)))
        if item.get("baseline") is not False:
            problems.append("audio slot baseline is %s, expected false"
                            % show(item.get("baseline")))
        reason = item.get("reason")
        if not isinstance(reason, str):
            problems.append("audio slot reason is not text")
        else:
            if AUDIO_LOADER not in reason:
                problems.append("audio slot reason does not name loader %s" % AUDIO_LOADER)
            if "console_init()" not in reason or CONSOLE_LINE not in reason:
                problems.append("audio slot reason does not name console_init() at %s"
                                % CONSOLE_LINE)
            if "PE_init_iokit()" not in reason or PE_INIT_LINE not in reason:
                problems.append("audio slot reason does not name PE_init_iokit() at %s"
                                % PE_INIT_LINE)
        review = item.get("review")
        if not isinstance(review, str) or "before the console_init line" not in review:
            problems.append("audio slot review does not say when to re-open "
                            "(before the console_init line)")

    counter = [item for item in targets
               if item.get("bundle") == COUNTER_BUNDLE
               and item.get("target") == AUDIO_TARGET
               and item.get("site") == COUNTER_SITE]
    if not counter:
        problems.append("no %s reference to %s at %s"
                        % (COUNTER_BUNDLE, AUDIO_TARGET, COUNTER_SITE))

    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="check the three IOAudio2Family residue criteria")
    parser.add_argument("--audit", metavar="PATH",
                        help="the audit TOML; default searches the scratch trees")
    args = parser.parse_args(argv)

    path = resolve(args.audit)
    if path is None:
        wanted = args.audit or DEFAULT_AUDIT
        print("RESIDUE SKIP: no audit file at %s" % wanted)
        return 3

    targets, error = load(path)
    if error:
        print("RESIDUE FAILED: %s: %s" % (path, error))
        return 1

    problems = check(targets)
    if problems:
        for problem in problems:
            print("RESIDUE FAILED: %s" % problem)
        print("RESIDUE FAILED %d problem(s)" % len(problems))
        return 1

    print("RESIDUE OK: criterion 1: bundle=%s target=%s kind=%s site=%s loader=%s"
          % (AUDIO_BUNDLE, AUDIO_TARGET, AUDIO_KIND, AUDIO_SITE, AUDIO_LOADER))
    print("RESIDUE OK: criterion 2: verdict=unreachable-before-console stage=%s baseline=false"
          % AUDIO_STAGE)
    print("RESIDUE OK: criterion 3: slots=%d keys=%d functions=%d bundles=%d "
          "auth_got=%d const=%d reachable-before-console=0; "
          "console_init=%s before PE_init_iokit=%s"
          % (EXPECTED_SLOTS, EXPECTED_KEYS, EXPECTED_FUNCTIONS, EXPECTED_BUNDLES,
             EXPECTED_AUTH_GOT, EXPECTED_CONST, CONSOLE_LINE, PE_INIT_LINE))
    print("RESIDUE OK: counterexample=%s target=%s site=%s"
          % (COUNTER_BUNDLE, AUDIO_TARGET, COUNTER_SITE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
