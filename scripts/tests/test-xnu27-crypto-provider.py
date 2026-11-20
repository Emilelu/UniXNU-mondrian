#!/usr/bin/env python3
"""Exercise scripts/check-xnu27-crypto-provider.py against synthetic kernels."""
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / 'scripts/check-xnu27-crypto-provider.py'

LC_FILESET_ENTRY = 0x80000035
LC_SEGMENT_64 = 0x19
CORECRYPTO = 'com.apple.kec.corecrypto'

passed = 0
failed = 0


def case(name, ok, detail=None):
    global passed, failed
    if ok:
        passed += 1
        print(f'  OK   {name}')
    else:
        failed += 1
        print(f'  FAIL {name}')
        if detail:
            print(detail)


def macho(path, names=(), filetype=12, markers=True):
    """A 64-bit Mach-O with one segment command and one LC_FILESET_ENTRY per name."""
    strings = bytearray()
    starts = []
    commands_start = 32 + 72
    strings_start = commands_start + 32 * len(names)
    for name in names:
        starts.append(strings_start + len(strings))
        strings += name.encode() + b'\0'
    commands = bytearray(struct.pack('<2I', LC_SEGMENT_64, 72) + b'\0' * 64)
    for index, start in enumerate(starts):
        # The entry identifier is an offset from the start of its own command.
        entry_id = start - (commands_start + 32 * index)
        commands += struct.pack('<2I2QII', LC_FILESET_ENTRY, 32, 0, 0, entry_id, 0)
    header = struct.pack('<8I', 0xfeedfacf, 0x0100000c, 0, filetype, 1 + len(names),
                         len(commands), 0, 0)
    payload = bytes(header) + bytes(commands) + bytes(strings)
    if markers:
        payload += b'\0source_corecrypto14_bootstrap\0source_corecrypto14_start_once\0corecrypto_kext_start\0'
    Path(path).write_bytes(payload)


def run(work, kernel, layers=(), mode=None):
    arguments = [sys.executable, str(CHECKER), '--kernel', str(kernel)]
    for index, text in enumerate(layers):
        layer = Path(work) / f'layer{index}.config'
        layer.write_text(text)
        arguments += ['--layer', str(layer)]
    if mode:
        arguments += ['--mode', mode]
    done = subprocess.run(arguments, capture_output=True, text=True)
    return done.returncode, done.stdout + done.stderr


def main():
    with tempfile.TemporaryDirectory() as work:
        work = Path(work)

        kernel = work / 'bare.macho'
        macho(kernel)
        code, output = run(work, kernel, ['CONFIG_XNU_CRYPTO_BOOTSTRAP="source"\n'])
        case('source mode with the compiled-in provider passes', code == 0, output)
        case('it says how many fileset entries it saw', 'fileset entries: 0' in output, output)

        kernel = work / 'stripped.macho'
        macho(kernel, markers=False)
        code, output = run(work, kernel, ['CONFIG_XNU_CRYPTO_BOOTSTRAP="source"\n'])
        case('source mode without the provider fails', code == 1, output)
        case('it names both missing markers',
             'source_corecrypto14' in output and 'corecrypto_kext_start' in output, output)

        kernel = work / 'collection.macho'
        macho(kernel, ['com.apple.kernel', CORECRYPTO])
        code, output = run(work, kernel, ['CONFIG_XNU_CRYPTO_BOOTSTRAP="prelinked"\n'])
        case('prelinked mode with a corecrypto entry passes', code == 0, output)
        case('it prints the entry it found', CORECRYPTO in output, output)

        kernel = work / 'no-crypto.macho'
        macho(kernel, ['com.apple.kernel'])
        code, output = run(work, kernel, ['CONFIG_XNU_CRYPTO_BOOTSTRAP="prelinked"\n'])
        case('prelinked mode without a corecrypto entry fails', code == 1, output)
        case('it says the source provider is compiled out',
             'compiled out by -UXNU_SOURCE_CORECRYPTO14' in output, output)
        case('it counts the entries it did see', 'fileset entries: 1' in output, output)

        kernel = work / 'layered.macho'
        macho(kernel)
        code, output = run(work, kernel,
                           ['CONFIG_XNU_CRYPTO_BOOTSTRAP="source"\n',
                            'CONFIG_XNU_CRYPTO_BOOTSTRAP="prelinked"\n'])
        case('the last layer wins', code == 1 and 'mode: prelinked' in output, output)
        case('it names the winning layer and line',
             'XNU_CRYPTO_BOOTSTRAP=prelinked (layer1.config:1)' in output, output)

        code, output = run(work, kernel, ['CONFIG_XNU_CRYPTO_BOOTSTRAP="prelinked"\n'], mode='source')
        case('an override beats the config', code == 0 and 'mode: source' in output, output)

        code, output = run(work, kernel, ['CONFIG_XNU_CRYPTO_BOOTSTRAP="both"\n'])
        case('an unknown mode fails', code == 1 and 'unknown XNU_CRYPTO_BOOTSTRAP=both' in output, output)

        code, output = run(work, kernel, [], mode='source')
        case('the mode defaults to source without any config',
             code == 0 and 'mode: source' in output, output)

        report = work / 'report'
        kernel = work / 'report.macho'
        macho(kernel, ['com.apple.kernel'])
        arguments = [sys.executable, str(CHECKER), '--kernel', str(kernel),
                     '--mode', 'prelinked', '--out', str(report)]
        subprocess.run(arguments, capture_output=True, text=True)
        data = json.loads((report / 'report.json').read_text())
        case('the report carries the fields the gate reads',
             data['mode'] == 'prelinked' and data['fileset_entries'] == ['com.apple.kernel']
             and data['hardware_verified'] is False and data['failures'], data)

        plain = work / 'plain.macho'
        macho(plain, filetype=2, markers=False)
        code, output = run(work, plain, [], mode='prelinked')
        case('a non-fileset kernel is reported as such',
             'not a fileset' in output and code == 1, output)

        missing = work / 'nope.config'
        done = subprocess.run([sys.executable, str(CHECKER), '--kernel', str(kernel),
                               '--layer', str(missing)], capture_output=True, text=True)
        case('a missing layer fails loudly',
             done.returncode == 1 and 'not found' in (done.stdout + done.stderr),
             done.stdout + done.stderr)

    print(f'TESTS {passed + failed} case(s): {passed} passed, {failed} failed')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
