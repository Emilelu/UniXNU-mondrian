#!/usr/bin/env python3
"""P-323: fast-payload must be handed the linker output, not the patched copy.

fast-payload applies the declared transform itself and records `kernel_sha256`
as the hash of the file it was given.  Passing kernel.patched.macho therefore
records the *patched* hash in payload.json, and check-ios27-artifacts then
compares that against the linker output and refuses the image even though the
bytes it packs are correct (r290k, 2026-11-24).
"""
import pathlib
import re
import sys

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / 'scripts' / 'build-ios27-linux.sh'


def main() -> int:
	text = SCRIPT.read_text(encoding='utf-8')
	block = re.search(r'k60-fast-payload\.py.*?\n', text, re.S)
	if not block:
		print('FAIL: no fast-payload invocation found')
		return 1
	segment = text[block.start():block.start() + 400]
	if '--kernel "$BOARD_DIR/kernel/kernel.macho"' not in segment:
		print('FAIL: fast-payload is not handed the linker output')
		return 1
	if '--kernel "$PATCHED_KERNEL"' in segment:
		print('FAIL: fast-payload is handed the patched copy (P-323)')
		return 1
	tool = (SCRIPT.parent / 'k60-fast-payload.py').read_text(encoding='utf-8')
	if 'kernel_sha256 updated to the linker output' not in tool:
		print('FAIL: a byte-identical reuse cannot repair a stale kernel_sha256 (P-323)')
		return 1
	print('TESTS OK: fast-payload takes the linker output, and reuse still repairs the record')
	return 0


if __name__ == '__main__':
	sys.exit(main())
