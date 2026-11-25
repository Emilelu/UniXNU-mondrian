#!/usr/bin/env python3
"""Tests for scripts/check-bootargs-abi.py."""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / 'scripts' / 'check-bootargs-abi.py'

KERNEL = '''\
#define BOOT_LINE_LENGTH 1024

typedef struct boot_args {
	char        CommandLine[BOOT_LINE_LENGTH];
	uint64_t    bootFlags;
	uint64_t    memSizeActual;
} boot_args;
'''

HEADER_OK = '''\
#define DARWIN_BOOT_LINE_LENGTH 1024
typedef struct {
  CHAR8   CommandLine[DARWIN_BOOT_LINE_LENGTH];
} DARWIN_BOOT_ARGS;
STATIC_ASSERT (OFFSET_OF (DARWIN_BOOT_ARGS, BootFlags) == 0x470, "flags ABI");
STATIC_ASSERT (OFFSET_OF (DARWIN_BOOT_ARGS, MemorySizeActual) == 0x478, "memory ABI");
STATIC_ASSERT (sizeof (DARWIN_BOOT_ARGS) == 0x480, "boot_args ABI");
'''

HEADER_BAD = '''\
#define DARWIN_BOOT_LINE_LENGTH 608
typedef struct {
  CHAR8   CommandLine[DARWIN_BOOT_LINE_LENGTH];
} DARWIN_BOOT_ARGS;
STATIC_ASSERT (OFFSET_OF (DARWIN_BOOT_ARGS, BootFlags) == 0x2d0, "flags ABI");
STATIC_ASSERT (OFFSET_OF (DARWIN_BOOT_ARGS, MemorySizeActual) == 0x2d8, "memory ABI");
STATIC_ASSERT (sizeof (DARWIN_BOOT_ARGS) == 0x2e0, "Darwin 22 boot_args ABI");
'''


def run(header: Path, kernel: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECK), '--header', str(header), '--boot-h', str(kernel)],
        capture_output=True, text=True)


def main() -> int:
    cases = 0
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        kernel = root / 'boot.h'
        kernel.write_text(KERNEL)

        good = root / 'good.h'
        good.write_text(HEADER_OK)
        result = run(good, kernel)
        assert result.returncode == 0, result.stdout + result.stderr
        assert 'BOOTARGS OK' in result.stdout, result.stdout
        cases += 1

        bad = root / 'bad.h'
        bad.write_text(HEADER_BAD)
        result = run(bad, kernel)
        assert result.returncode == 1, result.stdout
        assert 'command line is 608 bytes, the kernel reads 1024' in result.stdout
        assert 'BootFlags asserted at 0x2d0' in result.stdout
        assert 'sizeof(DARWIN_BOOT_ARGS) is 0x2e0' in result.stdout
        cases += 1

        result = run(root / 'missing.h', kernel)
        assert result.returncode == 2, result.stdout
        cases += 1

    print(f'TESTS OK {cases} cases')
    return 0


if __name__ == '__main__':
    sys.exit(main())
