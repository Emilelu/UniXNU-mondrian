#!/usr/bin/env python3
"""Tests for scripts/k60-bus.py.

The properties that matter are the four the reply markdown got wrong, so each
one gets a case: messages must not be lost, must be addressed, must be
threadable, and reading must not show the same message twice.
"""

import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import importlib

bus = importlib.import_module("k60-bus")

CASES = []
FAILURES = []


def case(fn):
    CASES.append(fn)
    return fn


class Sandbox:
    """A private bus directory plus a captured stdout/stderr pair."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "bus"
        self._previous = os.environ.get("K60_BUS")
        os.environ["K60_BUS"] = str(self.root)

    def run(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = bus.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def lines(self):
        path = self.root / "bus.jsonl"
        if not path.exists():
            return []
        return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]

    def close(self):
        if self._previous is None:
            os.environ.pop("K60_BUS", None)
        else:
            os.environ["K60_BUS"] = self._previous
        self.tmp.cleanup()


def with_bus(fn):
    def wrapper():
        box = Sandbox()
        try:
            fn(box)
        finally:
            box.close()
    wrapper.__name__ = fn.__name__
    return wrapper


def check(condition, message):
    if not condition:
        FAILURES.append(f"{CURRENT}: {message}")


@case
def send_appends_exactly_one_line():
    @with_bus
    def body(box):
        code, out, _ = box.run("send", "--from", "lead", "--to", "audio",
                              "--thread", "audio-cc", "--body", "first")
        check(code == 0, "send should exit 0")
        check(len(box.lines()) == 1, "one send must leave exactly one line")
        message = box.lines()[0]
        check(message["from"] == "lead", "sender recorded")
        check(message["to"] == "audio", "recipient recorded")
        check(message["thread"] == "audio-cc", "thread recorded")
        check(message["body"] == "first", "body recorded")
        check("sent " in out, "send should print the id it assigned")
    body()


@case
def read_advances_the_cursor_and_never_repeats():
    @with_bus
    def body(box):
        box.run("send", "--from", "lead", "--to", "audio", "--body", "one")
        code, out, _ = box.run("read", "--for", "audio")
        check(code == 0, "read should exit 0")
        check("one" in out, "first read shows the message")
        code, out, _ = box.run("read", "--for", "audio")
        check("one" not in out, "second read must not show it again")
        check("nothing new" in _, "second read should say there is nothing new")
    body()


@case
def peek_does_not_advance():
    @with_bus
    def body(box):
        box.run("send", "--from", "lead", "--to", "audio", "--body", "kept")
        box.run("read", "--for", "audio", "--peek")
        _, out, _ = box.run("read", "--for", "audio")
        check("kept" in out, "peek must leave the message unread")
    body()


@case
def broadcast_reaches_every_lane_but_a_direct_message_does_not():
    @with_bus
    def body(box):
        box.run("send", "--from", "lead", "--to", "*", "--body", "all hands")
        box.run("send", "--from", "lead", "--to", "wifi", "--body", "wifi only")
        _, audio, _ = box.run("read", "--for", "audio")
        _, wifi, _ = box.run("read", "--for", "wifi")
        check("all hands" in audio, "audio gets the broadcast")
        check("wifi only" not in audio, "audio must not get wifi's mail")
        check("all hands" in wifi and "wifi only" in wifi, "wifi gets both")
    body()


@case
def a_comma_list_addresses_every_name_in_it():
    @with_bus
    def body(box):
        box.run("send", "--from", "lead", "--to", "audio,bt", "--body", "two lanes")
        _, audio, _ = box.run("read", "--for", "audio", "--peek")
        _, bt, _ = box.run("read", "--for", "bt", "--peek")
        check("two lanes" in audio and "two lanes" in bt, "comma list reaches both")
    body()


@case
def thread_filter_selects_one_conversation():
    @with_bus
    def body(box):
        box.run("send", "--from", "lead", "--to", "audio", "--thread", "a", "--body", "in a")
        box.run("send", "--from", "lead", "--to", "audio", "--thread", "b", "--body", "in b")
        _, out, _ = box.run("read", "--for", "audio", "--thread", "b", "--peek")
        check("in b" in out and "in a" not in out, "thread filter keeps only its thread")
    body()


@case
def wait_returns_at_once_when_something_is_waiting():
    @with_bus
    def body(box):
        box.run("send", "--from", "audio", "--to", "lead", "--thread", "t", "--body", "ready")
        code, out, _ = box.run("wait", "--for", "lead", "--thread", "t", "--timeout", "1")
        check(code == 0, "wait should find the pending message")
        check("ready" in out, "wait prints the message it found")
    body()


@case
def wait_times_out_with_exit_3_and_keeps_the_cursor():
    @with_bus
    def body(box):
        code, _, err = box.run("wait", "--for", "lead", "--timeout", "0.2")
        check(code == 3, f"a timeout must be exit 3, got {code}")
        check("timeout" in err, "the timeout is reported on stderr")
        check(box.root.joinpath("cursors", "lead.json").exists() is False,
              "a timeout must not create or move a cursor")
    body()


@case
def a_half_written_line_is_skipped_not_fatal():
    @with_bus
    def body(box):
        box.root.mkdir(parents=True, exist_ok=True)
        with open(box.root / "bus.jsonl", "w", encoding="utf-8") as fh:
            fh.write('{"ts": "x", "from": "lead", "to": "audio", "body": "good"}\n')
            fh.write('{"ts": "y", "from": "lead", "to": "aud')     # crashed writer
        code, out, _ = box.run("read", "--for", "audio")
        check(code == 0, "a truncated line must not fail the read")
        check("good" in out, "the complete line is still delivered")
    body()


@case
def threads_lists_counts_and_marks_unread():
    @with_bus
    def body(box):
        box.run("send", "--from", "lead", "--to", "wifi", "--thread", "b1", "--body", "x")
        box.run("send", "--from", "wifi", "--to", "lead", "--thread", "b1", "--body", "y")
        box.run("send", "--from", "wifi", "--to", "lead", "--thread", "b1", "--body", "y2")
        box.run("send", "--from", "lead", "--to", "lead", "--thread", "other", "--body", "z")
        code, out, _ = box.run("threads", "--for", "lead")
        check(code == 0, "threads should exit 0")
        check("b1" in out and "other" in out, "both threads are listed")
        # b1 has two messages *addressed to lead*; the lead->wifi one is not lead's mail.
        check("2 msg" in out, f"counts are per addressed message, got:\n{out}")
    body()


@case
def doctor_reports_every_lane_cursor():
    @with_bus
    def body(box):
        box.run("send", "--from", "lead", "--to", "audio", "--body", "hi")
        box.run("read", "--for", "audio")
        code, out, _ = box.run("doctor", "--for", "audio")
        check(code == 0, "doctor should exit 0")
        check("audio" in out and "cursor=" in out, "doctor lists lanes with cursors")
        check("pending=0" in out.split("audio")[1][:80],
              "audio's cursor should be current after the read")
    body()


@case
def bus_root_translates_between_windows_and_wsl_paths():
    previous = os.environ.get("K60_BUS")
    try:
        os.environ["K60_BUS"] = "E:/k60-work/bus"
        first = bus.bus_root()
        if os.name == "posix":
            check(str(first) == "/mnt/e/k60-work/bus",
                  f"POSIX must see /mnt/e/k60-work/bus, got {first}")
        else:
            check(str(first).lower().startswith("e:"), f"Windows keeps E:, got {first}")
        if os.name != "posix":
            os.environ["K60_BUS"] = "/mnt/e/k60-work/bus"
            check(str(bus.bus_root()).lower().startswith("e:"),
                  "Windows must translate /mnt/e back to E:")
    finally:
        if previous is None:
            os.environ.pop("K60_BUS", None)
        else:
            os.environ["K60_BUS"] = previous


def main() -> int:
    global CURRENT
    for fn in CASES:
        CURRENT = fn.__name__
        fn()
    if FAILURES:
        print(f"TESTS FAILED: {len(FAILURES)} failure(s) in {len(CASES)} case(s)")
        for line in FAILURES:
            print(f"  {line}")
        return 1
    print(f"TESTS OK: {len(CASES)} cases (0 failure(s))")
    return 0


CURRENT = ""

if __name__ == "__main__":
    raise SystemExit(main())
