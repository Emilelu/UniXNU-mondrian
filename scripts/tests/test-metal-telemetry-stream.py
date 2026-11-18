#!/usr/bin/env python3
"""P-241: a timing table with no caller is not a measurement.

The bridge accumulates per-commit and per-wait timing (rows T/G/J/V/K of
native_bridge_metal_telemetry), but nothing ever called it, so a flight could not
show where the client's time went. And status was sampled at 5/20/60 s only, so a
200 s flight never saw its own steady state.

These checks are structural: they assert the producer exists, that the plugin calls
it, and that the cadence reaches past the launch window.
"""

import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PLUGIN = os.path.join(ROOT, "drivers", "PongMetal", "PongMetalPlugin.mm")
FRONTEND = os.path.join(ROOT, "drivers", "PongMetal", "NativeBridgeMetalFrontend.mm")

CASES = []
FAILED = []


def case(fn):
    CASES.append(fn)
    return fn


def read(path):
    return io.open(path, encoding="utf-8").read()


@case
def the_telemetry_table_exists():
    text = read(FRONTEND)
    assert "size_t native_bridge_metal_telemetry(char *out,size_t size)" in text, \
        "the telemetry producer vanished; the plugin would stream nothing"


@case
def the_table_carries_the_timing_rows():
    text = read(FRONTEND)
    for row in ('row("T pipeline', 'row("G commit-to-complete', 'row("J completed wait',
                'row("V vkpipe', 'row("K%u t='):
        assert row in text, "the timing row %r is gone; the client's time is unmeasurable again" % row


@case
def the_plugin_calls_it():
    text = read(PLUGIN)
    assert "native_bridge_metal_telemetry(" in text, \
        "native_bridge_metal_telemetry has no caller again (P-241: the measurement exists, nothing produces it)"


@case
def the_plugin_splits_the_table_into_rows():
    text = read(PLUGIN)
    body = text[text.index("static void streamTelemetry"):]
    body = body[:body.index("\n}\n")]
    assert r"!='\n'" in body, "the streamer must split on newlines or report() gets one giant line"
    assert "report(blob+at,0)" in body, "each row must go through report() to reach the kernel log"


@case
def the_plugin_braces_balance():
    # Cost one Mac round trip: an earlier version of the patch opened a second
    # anonymous namespace and the plugin failed to compile with
    # "Objective-C declarations may only appear in global scope".
    text = read(PLUGIN)
    assert text.count("{") == text.count("}"), \
        "braces do not balance (%d open, %d close); a stray namespace would break the Objective-C scope" % (
            text.count("{"), text.count("}"))


@case
def the_cadence_reaches_the_steady_state():
    text = read(PLUGIN)
    loop = re.search(r"for\(unsigned seconds:\{([0-9u,]+)\}\)", text)
    assert loop, "the observation loop moved; re-read the plugin"
    values = [int(v.rstrip("u")) for v in loop.group(1).split(",") if v]
    assert max(values) >= 120, \
        "the last sample is at %d s; a 200 s flight would still miss its steady state" % max(values)
    assert values == sorted(values), "the cadence must stay increasing"


@case
def the_table_is_streamed_only_after_the_launch():
    text = read(PLUGIN)
    assert "if(seconds>=60u)streamTelemetry();" in text, \
        "streaming at 5 s would spend the launch window on an empty table"


def main():
    for fn in CASES:
        try:
            fn()
        except AssertionError as exc:
            FAILED.append((fn.__name__, str(exc)))
            print("FAIL %s: %s" % (fn.__name__, exc))
        else:
            print("ok   %s" % fn.__name__)
    if FAILED:
        print("\n%d/%d failed" % (len(FAILED), len(CASES)))
        return 1
    print("\nTESTS OK (%d cases)" % len(CASES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
