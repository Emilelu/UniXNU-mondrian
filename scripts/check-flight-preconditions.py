#!/usr/bin/env python3
"""飞行前置条件：设备在 fastboot、控制台已 armed、镜像已归档、冻结已解除。

2026-11-22 我（lead）在设备还停在 Android 时直接发了 `fastboot boot`，抓包器因为没有
`VID_1209&PID_0001` 的串口枚举而根本没 armed —— 那一次即使内核起来了也读不到日志，
和前两次 0 字节是同一个坑。这个门禁把那四件事变成「发不出去」。

退出码：0 全部满足；2 有前置没满足（带逐条读数）；3 工具缺失，无法判定（不是通过）。
"""
import argparse
import hashlib
import os
import pathlib
import shutil
import subprocess
import sys

CONSOLE_VID_PID = 'VID_1209&PID_0001'


def run(cmd):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f'{exc}'
    return out, (out.stdout or '') + (out.stderr or '')


def devices(tool):
    """返回 'fastboot'/'adb'/None，以及可读的理由。"""
    path = shutil.which(tool)
    if not path:
        for root in ('/mnt/d/Android/platform-tools', '/mnt/c/Android/platform-tools',
                     os.environ.get('K60_PLATFORM_TOOLS', '')):
            if not root:
                continue
            for name in (tool + '.exe', tool):
                candidate = pathlib.Path(root) / name
                if candidate.is_file():
                    path = str(candidate)
                    break
            if path:
                break
    if not path:
        return None, f'{tool} is not on PATH'
    out, text = run([path, 'devices'])
    if out is None:
        return None, f'{tool} could not run: {text}'
    lines = [l for l in text.splitlines()[1:] if l.strip()]
    serials = [l.split()[0] for l in lines]
    return (serials, None) if serials else ([], f'{tool} sees no device')


def state(tool_reports):
    fastboot_serials, fastboot_note = tool_reports['fastboot']
    adb_serials, adb_note = tool_reports['adb']
    if fastboot_serials:
        return 'fastboot', fastboot_serials
    if adb_serials:
        return 'android', adb_serials
    return None, [fastboot_note, adb_note]


def console_arming(ps='powershell.exe'):
    """Windows 侧看 usbser 枚举出来的控制台串口。"""
    if not shutil.which(ps):
        return None, f'{ps} is not available, so the console cannot be seen'
    script = (
        "Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match '"
        + CONSOLE_VID_PID.replace('&', '\\&')
        + "' } | Select-Object -ExpandProperty Status"
    )
    out, text = run([ps, '-NoProfile', '-Command', script])
    if out is None:
        return None, text
    status = [l.strip() for l in text.splitlines() if l.strip()]
    if not status:
        return False, f'no {CONSOLE_VID_PID} device: the capture port is not enumerated'
    return all(s.lower() == 'ok' for s in status), f'{CONSOLE_VID_PID}: {",".join(status)}'


def digest(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()[:12]


def judge(image, mode, console_ok, frozen):
    problems = []
    if frozen:
        problems.append('BOOT-FREEZE still says state = "frozen"')
    if mode != 'fastboot':
        problems.append(f'device is in {mode or "no known mode"}, not fastboot; '
                        'a boot image can only be sent from fastboot')
    if console_ok is not True:
        problems.append('the console port is not armed, so a silent boot cannot be read '
                        '(this is the 2026-11-22 mistake)')
    if image is None:
        problems.append('no image given')
    elif not pathlib.Path(image).is_file():
        problems.append(f'image does not exist: {image}')
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--image')
    ap.add_argument('--freeze', default='docs/engineering/BOOT-FREEZE.md')
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()

    if args.self_test:
        cases = [
            ('fastboot', True, False, 0, 'all preconditions met'),
            ('android', True, False, 2, 'device is in android'),
            ('fastboot', False, False, 2, 'console not armed'),
            ('fastboot', True, True, 2, 'freeze still applies'),
            (None, True, False, 2, 'no device'),
        ]
        ok = True
        for mode, console, frozen, want, why in cases:
            got = 2 if judge(__file__, mode, console, frozen) else 0
            if got != want:
                ok = False
                print(f'FAIL selftest {why}: want {want}, got {got}')
        print('SELFTEST OK' if ok else 'SELFTEST FAILED')
        return 0 if ok else 1

    reports = {tool: devices(tool) for tool in ('fastboot', 'adb')}
    mode, serials = state(reports)
    console_ok, console_note = console_arming()
    frozen = False
    fp = pathlib.Path(args.freeze)
    if fp.is_file():
        frozen = 'state = "frozen"' in fp.read_text(encoding='utf-8')

    print(f'note device: mode={mode} serials={serials}')
    print(f'note console: {console_note}')
    if args.image and pathlib.Path(args.image).is_file():
        print(f'note image: {pathlib.Path(args.image).resolve()} sha256={digest(args.image)} '
              f'{pathlib.Path(args.image).stat().st_size} bytes')
    print(f'note freeze: {"frozen" if frozen else "unfrozen"} ({fp})')

    if mode is None and console_ok is None:
        print('FAIL: neither the device mode nor the console state could be read, '
              'so this gate has no opinion. Tools missing is not a pass.')
        return 3

    problems = judge(args.image, mode, console_ok, frozen)
    if problems:
        for problem in problems:
            print(f'FAIL {problem}')
        print('结论: ❌ 前件未满足，不发 fastboot boot')
        return 2
    print('结论: ✅ 前件满足，可以发 fastboot boot')
    return 0


if __name__ == '__main__':
    sys.exit(main())
