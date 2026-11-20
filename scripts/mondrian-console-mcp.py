#!/usr/bin/env python3
"""Read-only MCP bridge for one K60 console evidence directory.

Why this exists: `docs/engineering/BOOT-PROCEDURE.md` writes one evidence
directory per boot (`console.log`, `capture.json`, `boot.json`,
`capture-events.jsonl`) and states the rule the rest of the loop depends on --
a boot without a serial log is a blind experiment.  Reading that directory by
hand costs four steps that fail quietly: find the newest directory, know which
capture state still allows a diagnosis, compare the image on disk with the one
`boot.json` recorded, and find the `Darwin Kernel Version` line that belongs to
this boot rather than to a previous one.

This server answers those questions in one call.  It never opens COM5 and never
starts a process: the collector owns the port (`capture-k60-usblog.ps1` holds
the named mutex), so a read here cannot take a byte from a capture that is
still running.

`prove_boot` is the point.  `fastboot boot` can be accepted while the console
shows a kernel other than the image just built -- the path in `boot.json` is
not proof, and neither is a timestamp.  Hash the image, scan its payload for
the banner, and compare that with the last banner in the console.

Read-only means read-only: no subprocess, no WSL, no fastboot, no serial port,
no file writes.

Usage (the OpenCode config runs it with the mcp<2 interpreter):

    python3 scripts/mondrian-console-mcp.py          # stdio MCP server
    python3 scripts/tests/test-mondrian-console-mcp.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP

REPO = Path(os.environ.get('K60_REPO') or Path(__file__).resolve().parents[1])
BANNER = re.compile(rb'Darwin Kernel Version[^\x00\r\n;]*')
LOG_MAX_LINES = 4000
LOG_MAX_LINE = 4000
SEARCH_MAX = 80

mcp = FastMCP('mondrian-console')


def evidence_roots() -> list[Path]:
    """Where an evidence tree may live, most specific first.

    The documented location comes before a sibling of the checkout: a stray
    `evidence/` next to the repo must not shadow E:\\k60-work\\evidence.
    """
    roots: list[Path] = []
    env = os.environ.get('K60_EVIDENCE')
    if env:
        roots.append(Path(env))
    roots.append(Path('E:/k60-work/evidence'))
    roots.append(REPO.parent / 'evidence')
    return roots


def evidence_root() -> Path | None:
    for root in evidence_roots():
        if root.is_dir():
            return root
    return None


def list_captures(root: Path) -> list[Path]:
    """Capture directories, newest write first (the order PB-2 uses)."""
    found = []
    try:
        for entry in root.iterdir():
            if not entry.is_dir():
                continue
            if (entry / 'capture.json').is_file() or (entry / 'console.log').is_file():
                found.append(entry)
    except OSError:
        return []
    found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return found


def resolve_capture(name: str = '') -> tuple[Path | None, str]:
    root = evidence_root()
    if name:
        path = Path(name)
        if not path.is_absolute() and root is not None:
            path = root / name
        if path.is_dir():
            return path, ''
        return None, f'no such capture directory: {path}'
    if root is None:
        tried = ', '.join(str(r) for r in evidence_roots())
        return None, ('no evidence directory found; set K60_EVIDENCE. '
                      f'looked in: {tried}')
    captures = list_captures(root)
    if not captures:
        return None, f'{root} has no capture directory'
    return captures[0], ''


def read_json(path: Path) -> dict:
    """PowerShell 5.1 writes UTF-8 with a BOM; json would choke on it."""
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return {}


def capture_meta(directory: Path) -> dict:
    return read_json(directory / 'capture.json')


def boot_meta(directory: Path) -> dict:
    return read_json(directory / 'boot.json')


def console_path(directory: Path) -> Path:
    return directory / 'console.log'


def console_text(directory: Path) -> str:
    path = console_path(directory)
    try:
        return path.read_bytes().decode('utf-8', 'replace')
    except OSError:
        return ''


def tail(text: str, lines: int) -> str:
    chunk = text.splitlines()[-max(1, lines):]
    return '\n'.join(line[:LOG_MAX_LINE] for line in chunk)


def search(text: str, pattern: str, context: int, limit: int) -> tuple[list[str], int]:
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        raise ValueError(f'invalid regular expression: {exc}') from exc
    rows = text.splitlines()
    out: list[str] = []
    hits = 0
    last = -1
    for number, line in enumerate(rows):
        if not regex.search(line):
            continue
        hits += 1
        if len(out) >= limit * (2 * context + 1):
            continue
        first = max(0, number - context)
        if first <= last:
            first = last + 1
        for index in range(first, min(len(rows), number + context + 1)):
            mark = ':' if index == number else '-'
            out.append(f'{index + 1}{mark} {rows[index][:LOG_MAX_LINE]}')
            last = index
    return out, hits


def banners(data: bytes) -> list[str]:
    """Every distinct banner in order; the last one is the running kernel."""
    found: list[str] = []
    for match in BANNER.finditer(data):
        text = match.group(0).decode('utf-8', 'replace').strip()
        if text and text not in found:
            found.append(text)
    return found


def scan_banners(path: Path, chunk: int = 8 << 20, overlap: int = 256) -> list[str]:
    """Scan a large image without loading it whole; banners span chunk edges."""
    found: list[str] = []
    carry = b''
    with path.open('rb') as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            data = carry + block
            at_eof = len(block) < chunk
            for match in BANNER.finditer(data):
                # A match touching the end of a non-final window may continue
                # in the next chunk; the carry rescans it whole.  Recording it
                # now would keep a truncated banner as a second, false entry.
                if match.end() == len(data) and not at_eof:
                    continue
                text = match.group(0).decode('utf-8', 'replace').strip()
                if text and text not in found:
                    found.append(text)
            carry = data[-overlap:]
    return found


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def human_age(seconds: float) -> str:
    if seconds < 90:
        return f'{int(seconds)} s'
    if seconds < 5400:
        return f'{int(seconds // 60)} min'
    return f'{seconds / 3600:.1f} h'


def describe(directory: Path) -> str:
    cap = capture_meta(directory)
    boot = boot_meta(directory)
    log = console_path(directory)
    size = log.stat().st_size if log.is_file() else 0
    declared = cap.get('bytes')
    lines = [
        f'capture: {directory}',
        f'  state: {cap.get("state", "(no capture.json)")}'
        f'  complete: {cap.get("complete", "?")}'
        f'  stop: {cap.get("stopReason", "?")}',
        f'  bytes: {size} on disk'
        + (f', {declared} declared' if declared is not None else ''),
    ]
    if cap.get('panicMarker'):
        lines.append(f'  panic marker: {cap["panicMarker"]}')
    if cap.get('resetMarker'):
        lines.append(f'  reset marker: {cap["resetMarker"]}')
    if cap.get('lastError'):
        lines.append(f'  last error: {cap["lastError"]}')
    if boot:
        lines.append(
            f'  boot: accepted={boot.get("bootAccepted", "?")}'
            f'  armed={boot.get("captureArmed", "?")}'
            f'  back-to-fastboot={boot.get("returnedToFastboot", "?")}'
        )
        if boot.get('image'):
            lines.append(f'  image: {boot["image"]}')
        if boot.get('error'):
            lines.append(f'  boot error: {boot["error"]}')
    else:
        lines.append('  boot: (no boot.json: no supervisor ledger for this boot)')
    text = console_text(directory)
    found = banners(text.encode('utf-8', 'replace'))
    if found:
        lines.append(f'  console banner: {found[-1]}')
    else:
        lines.append('  console banner: (none)')
    return '\n'.join(lines)


@mcp.tool()
def captures(limit: int = 8) -> str:
    """List recent capture directories, newest first (read-only; no COM port)."""
    root = evidence_root()
    if root is None:
        tried = ', '.join(str(r) for r in evidence_roots())
        return ('no evidence directory found; set K60_EVIDENCE. '
                f'looked in: {tried}')
    found = list_captures(root)[:max(1, min(limit, 50))]
    if not found:
        return f'{root} has no capture directory'
    now = time.time()
    rows = [f'{root}']
    for directory in found:
        cap = capture_meta(directory)
        boot = boot_meta(directory)
        log = console_path(directory)
        size = log.stat().st_size if log.is_file() else 0
        age = human_age(max(0.0, now - directory.stat().st_mtime))
        state = cap.get('state', 'no-meta')
        accepted = boot.get('bootAccepted')
        flag = 'boot=OK' if accepted is True else (
            'boot=NO' if accepted is False else 'boot=?')
        rows.append(f'  {directory.name}  {age:>7}  {size/1024:9.1f} KiB  '
                    f'{state:<24} {flag}')
    return '\n'.join(rows)


@mcp.tool()
def capture_summary(capture: str = '') -> str:
    """Structured summary of one capture (default: the newest)."""
    directory, error = resolve_capture(capture)
    if directory is None:
        return error
    return describe(directory)


@mcp.tool()
def console_tail(capture: str = '', lines: int = 200) -> str:
    """Tail of console.log (default: newest capture)."""
    directory, error = resolve_capture(capture)
    if directory is None:
        return error
    text = console_text(directory)
    if not text:
        return f'{console_path(directory)} is empty'
    return tail(text, max(1, min(lines, LOG_MAX_LINES)))


@mcp.tool()
def console_search(pattern: str, capture: str = '', context: int = 2,
                   limit: int = 40) -> str:
    """Regex search of console.log with line numbers and context."""
    directory, error = resolve_capture(capture)
    if directory is None:
        return error
    text = console_text(directory)
    if not text:
        return f'{console_path(directory)} is empty'
    try:
        rows, hits = search(text, pattern, max(0, min(context, 10)),
                            max(1, min(limit, SEARCH_MAX)))
    except ValueError as exc:
        return str(exc)
    if not hits:
        return f'no match for {pattern!r} in {directory.name}'
    header = f'{hits} match(es) for {pattern!r} in {directory.name}'
    shown = (f' (showing the first {len(rows)} lines)'
             if len(rows) < hits else '')
    return '\n'.join([header + shown, *rows])


@mcp.tool()
def capture_events(capture: str = '', lines: int = 30) -> str:
    """Tail of capture-events.jsonl: port observed/opened, markers, finish."""
    directory, error = resolve_capture(capture)
    if directory is None:
        return error
    path = directory / 'capture-events.jsonl'
    if not path.is_file():
        return f'{path} does not exist'
    rows = []
    for line in path.read_text(encoding='utf-8-sig', errors='replace').splitlines()[-max(1, lines):]:
        try:
            event = json.loads(line)
        except ValueError:
            rows.append(line[:LOG_MAX_LINE])
            continue
        rows.append(f'{event.get("at", "?")}  {event.get("event", "?"):<16} '
                    f'{event.get("detail", "")}')
    return '\n'.join(rows)


@mcp.tool()
def prove_boot(capture: str = '', image: str = '') -> str:
    """Prove the console belongs to this image: hashes, state and banner."""
    directory, error = resolve_capture(capture)
    if directory is None:
        return f'verdict: NO-EVIDENCE\n  {error}'

    cap = capture_meta(directory)
    boot = boot_meta(directory)
    log = console_path(directory)
    warnings: list[str] = []
    notes: list[str] = []

    if not boot:
        return ('verdict: NO-BOOT-RECORD\n'
                f'  {directory} has no boot.json; without the supervisor ledger '
                'nothing ties this console to an image')
    if boot.get('captureArmed') is not True:
        warnings.append('captureArmed is not true: the collector may have '
                        'started after the boot')
    if boot.get('bootAccepted') is not True:
        return ('verdict: BOOT-NOT-ACCEPTED\n'
                '  fastboot never reported Booting OKAY for this run; the '
                'console (if any) is not evidence about the requested image')

    declared = cap.get('bytes')
    size = log.stat().st_size if log.is_file() else 0
    if size == 0 or declared == 0:
        return (f'verdict: NO-CONSOLE\n  state={cap.get("state", "?")} '
                f'bytes={size} (declared {declared}); no kernel diagnosis is '
                'supported')

    text = console_text(directory)
    if not text.strip():
        return 'verdict: NO-CONSOLE\n  console.log carries no printable byte'

    want_log = cap.get('logSha256')
    if want_log:
        got_log = sha256_file(log)
        if got_log.lower() != str(want_log).lower():
            return ('verdict: CONSOLE-CHANGED\n'
                    f'  console.log sha256 {got_log[:16]} != capture.json '
                    f'{str(want_log)[:16]}; the evidence was modified '
                    'after the collector closed it')

    if not image and not boot.get('image'):
        return 'verdict: IMAGE-MISSING\n  boot.json carries no image path'
    image_path = Path(image) if image else Path(str(boot['image']))
    if not image_path.is_file():
        return (f'verdict: IMAGE-MISSING\n  {image_path} is not readable here; '
                'pass image= with the copy that was booted')

    want_image = boot.get('imageSha256')
    got_image = sha256_file(image_path)
    if want_image and got_image.lower() != str(want_image).lower():
        return ('verdict: STALE-IMAGE\n'
                f'  image now {got_image[:16]} != boot.json {str(want_image)[:16]}\n'
                '  the image changed after this boot: the console describes a '
                'kernel that is no longer on disk')
    if not want_image:
        warnings.append('boot.json carries no imageSha256')

    found_console = banners(text.encode('utf-8', 'replace'))
    if not found_console:
        return ('verdict: NO-CONSOLE-BANNER\n'
                f'  {size} bytes captured but no Darwin Kernel Version line; '
                'the console died before XNU printed')
    console_banner = found_console[-1]
    if len(found_console) > 1:
        warnings.append(f'{len(found_console)} banners in the console; using the last')

    found_image = scan_banners(image_path)
    if not found_image:
        return ('verdict: NO-IMAGE-BANNER\n'
                f'  no Darwin Kernel Version string inside {image_path.name}; '
                'cannot prove which kernel the payload carries')

    notes.append(f'state={cap.get("state", "?")} bytes={size} '
                 f'stop={cap.get("stopReason", "?")}')
    notes.append(f'image sha256 {got_image[:16]} matches boot.json')
    notes.append(f'console banner: {console_banner}')
    notes.append(f'image banners: {len(found_image)}')

    if console_banner not in found_image:
        rows = [f'verdict: MISMATCH',
                f'  console: {console_banner}']
        rows += [f'  image:   {item}' for item in found_image[:4]]
        rows.append('  the console is running a kernel the image does not carry')
        return '\n'.join(rows)

    rows = ['verdict: MATCH', *[f'  {note}' for note in notes]]
    if warnings:
        rows += [f'  warning: {warning}' for warning in warnings]
    return '\n'.join(rows)


if __name__ == '__main__':
    mcp.run()
