#!/usr/bin/env python3
"""Offline tests for mondrian-console-mcp.py -- no device, no COM port.

Why these cases: the failure this guards against is not "the log is missing"
(that is loud) but "the log belongs to another image" (silent).  A RAM boot can
be accepted while the console shows the previous kernel, and a rebuilt image
makes yesterday's evidence look current.  So the cases below are about telling
a proven boot from a stale one, with synthetic directories only.

Run with the MCP interpreter (it needs the `mcp` package to import the server):

    <venv>\\Scripts\\python.exe scripts/tests/test-mondrian-console-mcp.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import pathlib
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
SERVER = HERE.parent / 'mondrian-console-mcp.py'

_SPEC = importlib.util.spec_from_file_location('mondrian_console_mcp', SERVER)
server = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(server)

BANNER_A = b'Darwin Kernel Version 24.0.0: root:xnu-12377.1~1/RELEASE_ARM64_T6020'
BANNER_B = b'Darwin Kernel Version 23.0.0: root:xnu-10002.1~1/RELEASE_ARM64_T6020'

CASES = 0
FAILED = 0


def check(name: str, ok: bool, detail: str = '') -> None:
    global CASES, FAILED
    CASES += 1
    if ok:
        print('PASS ' + name)
    else:
        FAILED += 1
        print('FAIL ' + name + ('  ' + detail if detail else ''))


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make(root: pathlib.Path, name: str, console: bytes = b'',
         capture: dict | None = None, boot: dict | None = None,
         image_bytes: bytes | None = None) -> pathlib.Path:
    """One capture directory plus one image file, the shape the supervisor writes."""
    directory = root / name
    directory.mkdir(parents=True)
    (directory / 'console.log').write_bytes(console)

    image = root / 'images' / (name + '.img')
    image.parent.mkdir(exist_ok=True)
    image.write_bytes(image_bytes if image_bytes is not None else b'\x00' * 32)

    if capture is None:
        capture = {
            'state': 'captured',
            'complete': True,
            'bytes': len(console),
            'stopReason': 'budget',
            'logSha256': sha(console).upper(),
            'portSeen': True,
            'portOpened': True,
        }
    # PowerShell 5.1 writes UTF-8 with a BOM; the reader must survive it.
    (directory / 'capture.json').write_text(json.dumps(capture),
                                            encoding='utf-8-sig')
    if boot is None:
        boot = {
            'image': str(image),
            'imageSha256': sha(image.read_bytes()).upper(),
            'captureArmed': True,
            'bootAccepted': True,
            'returnedToFastboot': False,
        }
    if boot is not False:
        (directory / 'boot.json').write_text(json.dumps(boot), encoding='utf-8')
    return directory


def verdict(text: str) -> str:
    first = text.splitlines()[0] if text else ''
    return first.split(':', 1)[1].strip() if ':' in first else first


def main() -> int:
    with tempfile.TemporaryDirectory() as raw:
        root = pathlib.Path(raw) / 'evidence'
        root.mkdir()
        os.environ['K60_EVIDENCE'] = str(root)

        # --- pure functions -------------------------------------------------
        check('banners takes the last of several matches',
              server.banners(b'x' + BANNER_A + b'\x00' + BANNER_B)[-1]
              == BANNER_B.decode())
        check('banners ignores a truncated string',
              server.banners(b'Darwin Kernel Ver') == [])

        split = b'A' * 50 + BANNER_A + b'\x00' + b'B' * 50
        split_file = pathlib.Path(raw) / 'split.img'
        split_file.write_bytes(split)
        check('scan_banners finds a banner across a chunk edge',
              server.banners(BANNER_A)[0]
              in server.scan_banners(split_file, chunk=64),
              str(server.scan_banners(split_file, chunk=64)))

        text = 'one\ntwo hit\nthree\nfour\nfive hit\nsix'
        rows, hits = server.search(text, 'hit', 1, 10)
        check('search counts both hits', hits == 2, str(hits))
        check('search starts on the context line',
              rows[0] == '1- one', repr(rows[:2]))
        check('search marks the matching line with a colon',
              rows[1] == '2: two hit', repr(rows[:2]))
        check('search keeps the second window',
              '5: five hit' in rows and '6- six' in rows, repr(rows))
        check('tail keeps only the requested lines',
              server.tail('a\nb\nc\nd', 2) == 'c\nd')

        # --- capture discovery ----------------------------------------------
        old = make(root, 'usblog-20260101-000000', b'old')
        new = make(root, 'usblog-20260202-000000', b'new')
        os.utime(old, (1_600_000_000, 1_600_000_000))
        os.utime(new, (1_700_000_000, 1_700_000_000))
        check('list_captures is newest first',
              [p.name for p in server.list_captures(root)]
              == [new.name, old.name])
        check('resolve_capture defaults to the newest',
              server.resolve_capture()[0] == new)
        check('resolve_capture accepts a name',
              server.resolve_capture(old.name)[0] == old)
        missing, error = server.resolve_capture('does-not-exist')
        check('resolve_capture refuses an unknown name',
              missing is None and 'no such capture' in error, error)

        # --- the happy path --------------------------------------------------
        good = make(
            root, 'usblog-20260303-000000',
            console=b'loader\n' + BANNER_A + b'\nrunning\n',
            image_bytes=b'\x00' * 40 + BANNER_A + b'\x00' * 40,
        )
        out = server.prove_boot(good.name)
        check('prove_boot matches console and image', verdict(out) == 'MATCH', out)
        check('prove_boot reports the image hash',
              'image sha256' in out and 'matches boot.json' in out, out)

        summary = server.capture_summary(good.name)
        check('capture_summary reads a BOM capture.json',
              'state: captured' in summary, summary)
        check('capture_summary shows the console banner',
              BANNER_A.decode() in summary, summary)

        events = good / 'capture-events.jsonl'
        events.write_text('{"at":"t","event":"port-opened","detail":"COM5"}\n',
                          encoding='utf-8')
        check('capture_events formats the timeline',
              'port-opened' in server.capture_events(good.name), '')

        # --- every way a boot is not proof ----------------------------------
        stale = make(
            root, 'usblog-20260404-000000',
            console=b'x' + BANNER_A + b'\n',
            boot={
                'image': str(root / 'images' / 'usblog-20260404-000000.img'),
                'imageSha256': '00' * 32,
                'captureArmed': True,
                'bootAccepted': True,
            },
        )
        check('prove_boot refuses a rebuilt image',
              verdict(server.prove_boot(stale.name)) == 'STALE-IMAGE',
              server.prove_boot(stale.name))

        silent = make(root, 'usblog-20260505-000000', console=b'',
                      capture={'state': 'opened-no-data', 'complete': False,
                               'bytes': 0, 'stopReason': 'port-timeout'})
        check('prove_boot refuses zero bytes',
              verdict(server.prove_boot(silent.name)) == 'NO-CONSOLE',
              server.prove_boot(silent.name))

        rejected = make(
            root, 'usblog-20260606-000000', console=b'x' + BANNER_A,
            boot={'image': 'nowhere.img', 'imageSha256': '00',
                  'captureArmed': True, 'bootAccepted': False})
        check('prove_boot refuses a boot fastboot did not accept',
              verdict(server.prove_boot(rejected.name)) == 'BOOT-NOT-ACCEPTED',
              server.prove_boot(rejected.name))

        ledgerless = make(root, 'usblog-20260707-000000',
                          console=b'x' + BANNER_A, boot=False)
        check('prove_boot refuses a capture with no boot.json',
              verdict(server.prove_boot(ledgerless.name)) == 'NO-BOOT-RECORD',
              server.prove_boot(ledgerless.name))

        tampered = make(
            root, 'usblog-20260808-000000', console=b'x' + BANNER_A,
            capture={'state': 'captured', 'complete': True,
                     'bytes': 999, 'logSha256': '11' * 32})
        check('prove_boot refuses a console changed after capture',
              verdict(server.prove_boot(tampered.name)) == 'CONSOLE-CHANGED',
              server.prove_boot(tampered.name))

        wrong = make(
            root, 'usblog-20260909-000000',
            console=b'x' + BANNER_B + b'\n',
            image_bytes=b'\x00' + BANNER_A + b'\x00')
        check('prove_boot refuses a console from another kernel',
              verdict(server.prove_boot(wrong.name)) == 'MISMATCH',
              server.prove_boot(wrong.name))

        no_banner = make(
            root, 'usblog-20261010-000000', console=b'x' + BANNER_A + b'\n',
            image_bytes=b'\x00' * 64)
        check('prove_boot refuses an image with no banner',
              verdict(server.prove_boot(no_banner.name)) == 'NO-IMAGE-BANNER',
              server.prove_boot(no_banner.name))

        no_xnu = make(
            root, 'usblog-20261111-000000', console=b'loader only\n',
            image_bytes=b'\x00' + BANNER_A + b'\x00')
        check('prove_boot refuses a console without an XNU banner',
              verdict(server.prove_boot(no_xnu.name)) == 'NO-CONSOLE-BANNER',
              server.prove_boot(no_xnu.name))

        missing_image = make(
            root, 'usblog-20261212-000000', console=b'x' + BANNER_A,
            boot={'image': str(root / 'images' / 'gone.img'),
                  'imageSha256': '00', 'captureArmed': True,
                  'bootAccepted': True})
        check('prove_boot refuses a missing image',
              verdict(server.prove_boot(missing_image.name)) == 'IMAGE-MISSING',
              server.prove_boot(missing_image.name))

        # --- no evidence tree at all ----------------------------------------
        os.environ['K60_EVIDENCE'] = str(root / 'absent')
        out = server.captures()
        check('captures names the roots it tried when there is no tree',
              'no evidence directory' in out and 'absent' in out, out)
        check('prove_boot reports NO-EVIDENCE without a tree',
              verdict(server.prove_boot()) == 'NO-EVIDENCE',
              server.prove_boot())

    print()
    print(f'{CASES} cases, {FAILED} failed')
    return 1 if FAILED else 0


if __name__ == '__main__':
    raise SystemExit(main())
