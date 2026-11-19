#!/usr/bin/env python3
"""A file-backed message bus for the K60 lanes.

`reply-<lane>-*.md` is a whole-file overwrite: one lane writes, the other reads
and rewrites the same file, and a message that arrives mid-write is either lost
or silently merged into someone else's paragraph. It also has no addressing, no
threading and no notion of "what is new since I last read".

This is the smallest thing that fixes those four properties while still being
one file on the shared disk, so every lane can use it from Windows Python or
from WSL Python with no daemon, no port and no dependency:

  * append-only      every message is one JSON line appended to `bus.jsonl`
  * addressed        `to` names a lane, a comma list, or `*` for everyone
  * threaded         `thread` groups a request and its answers
  * cursored         each lane keeps a byte offset, so `read` shows only what
                     arrived since that lane last read (use --peek to look
                     without moving the cursor)

Typical use, from a lane that has just been given a turn:

    python3 scripts/k60-bus.py read --for audio
    python3 scripts/k60-bus.py send --from audio --to lead --thread audio-cc \
        --body "cc flight finished: status=0, see usblog-20261120-... "

And from the lead, waiting inside one turn for an answer:

    python3 scripts/k60-bus.py wait --for lead --thread audio-cc --timeout 300

Whoever is idle can sit on `watch --for <lane>` and see messages as they land.

The bus lives outside the repository on purpose: it is runtime state, not
history. Default `E:/k60-work/bus`, override with `K60_BUS`.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

LANES = ("lead", "audio", "bt", "cellular", "power", "wifi")
KINDS = ("request", "answer", "status", "note")


def bus_root() -> Path:
    """Locate the bus directory, translating between the two path worlds.

    Lanes run either Windows Python (E:/...) or WSL Python (/mnt/e/...). The
    same physical directory must resolve for both, so an `E:` path is rewritten
    when we are on POSIX and a `/mnt/<drive>/` path when we are on Windows.
    """
    raw = os.environ.get("K60_BUS") or "E:/k60-work/bus"
    if os.name == "posix":
        if len(raw) > 2 and raw[1] == ":":
            drive, rest = raw[0].lower(), raw[2:].lstrip("/\\").replace("\\", "/")
            raw = f"/mnt/{drive}/{rest}"
    else:
        if raw.startswith("/mnt/") and len(raw) > 6 and raw[6] == "/":
            raw = f"{raw[5].upper()}:/{raw[7:]}"
    return Path(raw)


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def body_of(args) -> str:
    if args.body_file:
        return Path(args.body_file).read_text(encoding="utf-8").strip()
    if args.body is not None:
        return args.body.strip()
    data = sys.stdin.read().strip()
    if not data:
        raise SystemExit("k60-bus: empty body (pass --body, --body-file or stdin)")
    return data


def cmd_send(args) -> int:
    root = bus_root()
    root.mkdir(parents=True, exist_ok=True)
    targets = [t.strip() for t in args.to.replace(",", " ").split() if t.strip()]
    if not targets:
        raise SystemExit("k60-bus: --to needs at least one lane or *")
    recipients = ", ".join(targets)
    message = {
        "id": f"{int(time.time()*1000):x}-{secrets.token_hex(3)}",
        "ts": now_iso(),
        "from": args.sender,
        "to": recipients,
        "thread": args.thread or "",
        "kind": args.kind,
        "body": body_of(args),
    }
    line = json.dumps(message, ensure_ascii=False) + "\n"
    # One write of one line, opened in append mode: no read-modify-write, so two
    # lanes sending at the same moment cannot lose each other's message.
    with open(root / "bus.jsonl", "a", encoding="utf-8", newline="\n") as fh:
        fh.write(line)
        fh.flush()
        os.fsync(fh.fileno()) if os.name == "posix" else None
    print(f"sent {message['id']} {args.sender} -> {recipients}"
          + (f" [{args.thread}]" if args.thread else ""))
    return 0


def cursor_path(lane: str) -> Path:
    return bus_root() / "cursors" / f"{lane}.json"


def load_cursor(lane: str) -> int:
    p = cursor_path(lane)
    if not p.exists():
        return 0
    try:
        return int(json.loads(p.read_text(encoding="utf-8"))["offset"])
    except (ValueError, KeyError, OSError):
        return 0


def save_cursor(lane: str, offset: int) -> None:
    p = cursor_path(lane)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"lane": lane, "offset": offset, "ts": now_iso()}),
                 encoding="utf-8")


def addressed(message: dict, lane: str) -> bool:
    targets = [t.strip() for t in str(message.get("to", "")).replace(",", " ").split()]
    return lane in targets or "*" in targets


def collect(lane: str, start: int, thread: str | None) -> tuple[list[dict], int]:
    """Return the messages for `lane` from byte offset `start`, plus the new offset."""
    path = bus_root() / "bus.jsonl"
    if not path.exists():
        return [], start
    size = path.stat().st_size
    if start > size:          # the file was truncated or replaced; start over
        start = 0
    out: list[dict] = []
    with open(path, "rb") as fh:
        fh.seek(start)
        blob = fh.read()
    for raw in blob.splitlines():
        if not raw.strip():
            continue
        try:
            message = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue          # a half-written line from a crashed writer
        if not addressed(message, lane):
            continue
        if thread and message.get("thread") != thread:
            continue
        out.append(message)
    return out, size


def render(message: dict, human: bool) -> str:
    if not human:
        return json.dumps(message, ensure_ascii=False)
    head = f"[{message['ts']}] {message['from']} -> {message['to']}"
    if message.get("thread"):
        head += f"  # {message['thread']}"
    if message.get("kind") and message["kind"] != "note":
        head += f"  ({message['kind']})"
    body = "\n".join("    " + ln for ln in str(message.get("body", "")).splitlines())
    return f"{head}\n{body}"


def cmd_read(args) -> int:
    start = load_cursor(args.lane)
    messages, new_offset = collect(args.lane, start, args.thread)
    if args.limit:
        messages = messages[-args.limit:]
    for message in messages:
        print(render(message, human=not args.json))
    if not messages and not args.quiet:
        print(f"(nothing new for {args.lane})", file=sys.stderr)
    if not args.peek:
        save_cursor(args.lane, new_offset)
    return 0


def cmd_wait(args) -> int:
    start = load_cursor(args.lane)
    deadline = time.monotonic() + args.timeout
    while True:
        messages, new_offset = collect(args.lane, start, args.thread)
        if messages:
            for message in messages:
                print(render(message, human=not args.json))
            if not args.peek:
                save_cursor(args.lane, new_offset)
            return 0
        if time.monotonic() >= deadline:
            print(f"(timeout after {args.timeout}s waiting for {args.lane})",
                  file=sys.stderr)
            return 3
        time.sleep(args.interval)


def cmd_watch(args) -> int:
    start = load_cursor(args.lane) if not args.from_start else 0
    print(f"watching for {args.lane}; Ctrl-C to stop", file=sys.stderr)
    try:
        while True:
            messages, new_offset = collect(args.lane, start, args.thread)
            for message in messages:
                print(render(message, human=not args.json), flush=True)
            if messages:
                start = new_offset
                save_cursor(args.lane, new_offset)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 0


def cmd_threads(args) -> int:
    messages, _ = collect(args.lane, 0, None)
    if not messages:
        print(f"(no messages for {args.lane} at all)")
        return 0
    seen: dict[str, dict] = {}
    counts: dict[str, int] = {}
    for message in messages:
        thread = message.get("thread") or "(no thread)"
        seen[thread] = message
        counts[thread] = counts.get(thread, 0) + 1
    unread_from = load_cursor(args.lane)
    unread, _ = collect(args.lane, unread_from, None)
    unread_threads = {(m.get("thread") or "(no thread)") for m in unread}
    for thread in sorted(seen):
        last = seen[thread]
        mark = "*" if thread in unread_threads else " "
        print(f"{mark} {thread:<32} {counts[thread]:>3} msg  last {last['ts']} "
              f"from {last['from']}")
    if unread:
        print(f"\n{len(unread)} unread — run: k60-bus.py read --for {args.lane}")
    return 0


def cmd_doctor(args) -> int:
    root = bus_root()
    path = root / "bus.jsonl"
    print(f"bus   : {root}")
    print(f"file  : {path} " + (f"({path.stat().st_size} bytes)" if path.exists() else "(missing)"))
    if path.exists():
        messages, _ = collect(args.lane or "lead", 0, None)
        print(f"lines : {len(messages)} message(s) for {args.lane or 'lead'}")
    for lane in LANES:
        cursor = cursor_path(lane)
        off = load_cursor(lane)
        pending, _ = collect(lane, off, None)
        print(f"  {lane:<9} cursor={off:<8} pending={len(pending)}"
              + ("" if cursor.exists() else "  (never read)"))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="k60-bus.py",
        description="Append-only, addressed, threaded message bus for the K60 lanes.")
    sub = parser.add_subparsers(dest="command", required=True)

    send = sub.add_parser("send", help="append one message")
    send.add_argument("--from", dest="sender", required=True,
                      help="lane that owns this turn (lead, audio, bt, ...)")
    send.add_argument("--to", required=True, help="lane, comma list, or * for all")
    send.add_argument("--thread", default="", help="thread key, for example audio-cc")
    send.add_argument("--kind", default="note", choices=KINDS)
    send.add_argument("--body")
    send.add_argument("--body-file")
    send.set_defaults(func=cmd_send)

    read = sub.add_parser("read", help="print messages new to this lane")
    read.add_argument("--for", dest="lane", required=True)
    read.add_argument("--thread", default=None)
    read.add_argument("--limit", type=int, default=0, help="only the last N")
    read.add_argument("--peek", action="store_true", help="do not advance the cursor")
    read.add_argument("--json", action="store_true")
    read.add_argument("--quiet", action="store_true")
    read.set_defaults(func=cmd_read)

    wait = sub.add_parser("wait", help="block until a message arrives (for use inside a turn)")
    wait.add_argument("--for", dest="lane", required=True)
    wait.add_argument("--thread", default=None)
    wait.add_argument("--timeout", type=float, default=120.0)
    wait.add_argument("--interval", type=float, default=0.5)
    wait.add_argument("--peek", action="store_true")
    wait.add_argument("--json", action="store_true")
    wait.set_defaults(func=cmd_wait)

    watch = sub.add_parser("watch", help="follow the bus and print messages as they land")
    watch.add_argument("--for", dest="lane", required=True)
    watch.add_argument("--thread", default=None)
    watch.add_argument("--interval", type=float, default=0.5)
    watch.add_argument("--from-start", action="store_true")
    watch.add_argument("--json", action="store_true")
    watch.set_defaults(func=cmd_watch)

    threads = sub.add_parser("threads", help="list threads with counts and the last message")
    threads.add_argument("--for", dest="lane", required=True)
    threads.set_defaults(func=cmd_threads)

    doctor = sub.add_parser("doctor", help="show the bus path and every lane's cursor")
    doctor.add_argument("--for", dest="lane", default="lead")
    doctor.set_defaults(func=cmd_doctor)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
