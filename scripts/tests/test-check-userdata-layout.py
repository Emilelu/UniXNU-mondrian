#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Self-test for scripts/check-userdata-layout.py.

The gate has three outcomes, and the test keeps all three distinct: a missing
image is 2 (cannot judge), a malformed image or a wrong OS-window UUID is 1,
and a complete image is 0.  The 1BCD69FF fixture is the 16.6.1 Data UUID; it must
fail against the 27 OS-window UUID even though the SHNGROOT header is valid.
"""
from __future__ import annotations

import hashlib
import importlib.util
import struct
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / 'scripts/check-userdata-layout.py'
VALID = 'E3F4AED0-4454-4D5B-833C-E27E99C4F67B'
OLD_DATA = '1BCD69FF-24A5-48B1-94B6-8FE592B2F597'
IMAGE_BYTES = 0x200000
FIRST = 0x100000
WINDOW_SIZE = 0x100000
CASE = []


def case(fn):
    CASE.append(fn)
    return fn


def load_gate():
    spec = importlib.util.spec_from_file_location('check_userdata_layout', GATE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_image(path: Path, uuid_text: str = VALID, *, magic: bytes = b'SHNGROOT',
               offset: int = FIRST, size: int = WINDOW_SIZE, block: int = 512,
               flags: int = 1, declared: int | None = None,
               keep_digest: bool = True) -> Path:
    data = bytearray(IMAGE_BYTES)
    struct.pack_into('<8sIIQ', data, 0, magic, 1, 1,
                     IMAGE_BYTES if declared is None else declared)
    struct.pack_into('<32sQQII32s40s', data, 24, b'OS', offset, size, block, flags,
                     hashlib.sha256(b'OS').digest(), bytes(40))
    data[4064:4096] = hashlib.sha256(data[:4064]).digest()
    at = offset + 0xA2020 + 0xD0
    data[at:at + 16] = uuid.UUID(uuid_text).bytes
    if not keep_digest:
        data[4064] ^= 0xFF
    path.write_bytes(data)
    return path


@case
def a_valid_image_passes():
    with tempfile.TemporaryDirectory(prefix='k60-userdata-valid-') as tmp:
        image = make_image(Path(tmp) / 'userdata.img')
        code, messages = load_gate().diagnose(image, VALID, capacity=IMAGE_BYTES)
        assert code == 0, messages
        assert 'OS-window UUID' in messages[0], messages


@case
def a_missing_image_is_cannot_judge():
    with tempfile.TemporaryDirectory(prefix='k60-userdata-missing-') as tmp:
        code, messages = load_gate().diagnose(Path(tmp) / 'absent.img', VALID)
        assert code == 2, (code, messages)
        assert 'does not exist' in messages[0], messages
        assert 'P-279' in messages[0], messages


@case
def the_16_6_1_data_uuid_fails():
    with tempfile.TemporaryDirectory(prefix='k60-userdata-old-') as tmp:
        image = make_image(Path(tmp) / 'userdata.img', OLD_DATA)
        code, messages = load_gate().diagnose(image, VALID)
        text = '\n'.join(messages)
        assert code == 1, (code, messages)
        assert OLD_DATA in text, messages
        assert '16.6.1 Data UUID' in text, messages


@case
def a_bad_magic_fails():
    with tempfile.TemporaryDirectory(prefix='k60-userdata-magic-') as tmp:
        image = make_image(Path(tmp) / 'userdata.img', magic=b'SHNGROO7')
        code, messages = load_gate().diagnose(image, VALID)
        assert code == 1, (code, messages)
        assert any('SHNGROOT' in message for message in messages), messages


@case
def a_misaligned_window_fails():
    with tempfile.TemporaryDirectory(prefix='k60-userdata-align-') as tmp:
        image = make_image(Path(tmp) / 'userdata.img', offset=0x100800)
        code, messages = load_gate().diagnose(image, VALID)
        assert code == 1, (code, messages)
        assert any('aligned' in message or 'past' in message for message in messages), messages


@case
def a_broken_header_digest_fails():
    with tempfile.TemporaryDirectory(prefix='k60-userdata-digest-') as tmp:
        image = make_image(Path(tmp) / 'userdata.img', keep_digest=False)
        code, messages = load_gate().diagnose(image, VALID)
        assert code == 1, (code, messages)
        assert any('SHA-256' in message for message in messages), messages


def main() -> int:
    failures = 0
    for fn in CASE:
        try:
            fn()
            print(f'ok   {fn.__name__}')
        except AssertionError as error:
            failures += 1
            print(f'FAIL {fn.__name__}: {error}')
    print(f'TESTS OK {len(CASE) - failures} case(s) ({failures} failure(s))')
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
