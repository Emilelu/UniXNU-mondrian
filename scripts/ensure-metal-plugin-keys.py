#!/usr/bin/env python3
"""Ensure a staged PongAdrenoMetal Info.plist declares the keys Metal reads.

Metal resolves the accelerator's MetalPluginName to <name>.bundle and then asks
that bundle for MetalPluginClassName.  The macOS build only declared
NSPrincipalClass, so the bundle was dyld-loaded and never instantiated
(measured 2026-11-17: the constructor ran, nothing else ever printed).
"""
import pathlib
import sys

KEYS = (
    (b'MetalPluginName', b'PongAdrenoMetal'),
    (b'MetalPluginClassName', b'PongAdrenoMetalDevice'),
)


def ensure(path: pathlib.Path) -> bool:
    data = path.read_bytes()
    if b'MetalPluginClassName' in data:
        return False
    marker = b'</dict>'
    if marker not in data:
        raise SystemExit(f'{path}: not a plist with a </dict>')
    extra = b''.join(b'\t<key>' + key + b'</key><string>' + value + b'</string>\n'
                     for key, value in KEYS)
    path.write_bytes(data.replace(marker, extra + marker, 1))
    return True


def main(argv) -> int:
    if len(argv) != 2:
        print('usage: ensure-metal-plugin-keys.py <Info.plist>', file=sys.stderr)
        return 2
    path = pathlib.Path(argv[1])
    if not path.is_file():
        print(f'{path}: missing', file=sys.stderr)
        return 1
    changed = ensure(path)
    print(f'{"added" if changed else "kept"} metal plugin keys in {path}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
