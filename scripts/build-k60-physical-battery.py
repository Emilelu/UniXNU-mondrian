#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
# Copyright (c) 2026, UniXNU contributors.
"""Build the K60 physical PMIC-GLINK/IOPMPowerSource archive for Darwin 22.

No firmware/PAS startup or synthetic handoff is generated. Hardware resources
come from the captured FDT; the vendor module property map is checked. Current
polarity stays unqualified unless actual charging/discharging wire captures
prove it. Subscription stays off unless its exact wire ACK was captured.
"""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys

DEVICE = Path(__file__).resolve().parents[1]
CONFIG_BYTES = 112
OWNER = 32778


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_framework(path):
    scripts = path / 'scripts'
    if not (scripts / 'unixnu' / 'devicetree.py').is_file():
        raise ValueError(f'No existing UniXNU FDT parser at {scripts}')
    sys.path.insert(0, str(scripts))
    return importlib.import_module('unixnu.devicetree')


def board_config(fdt, parser):
    root = parser.read_fdt(fdt.read_bytes())
    nodes = list(root.walk())
    phandles = {n.scalar('phandle'): n for n in nodes if 'phandle' in n.properties}

    def one(compatible):
        found = [n for n in nodes if compatible in n.strings('compatible') and n.enabled()]
        if len(found) != 1:
            raise ValueError(f'Expected one enabled {compatible}, found {len(found)}')
        return found[0]

    def referenced(n, key):
        cells = n.cells(key)
        if not cells or cells[0] not in phandles:
            raise ValueError(f'{n.name}: missing {key} reference')
        return phandles[cells[0]]

    def reg(n):
        ranges = parser.registers(n)
        if len(ranges) != 1:
            raise ValueError(f'{n.name}: expected one physical range')
        return ranges[0]

    adsp = one('qcom,cape-adsp-pas')
    smem = one('qcom,smem')
    ipcc = one('qcom,ipcc')
    battery = one('qcom,battery-charger')
    if battery.parent.strings('qcom,pmic-glink-channel') != ['PMIC_RTR_ADSP_APPS']:
        raise ValueError('K60 battery is not on the observed ADSP PMIC channel')
    edges = [n for n in adsp.children if n.name == 'glink-edge']
    if len(edges) != 1:
        raise ValueError('ADSP native GLINK edge is absent/ambiguous')
    edge = edges[0]
    remote = edge.scalar('qcom,remote-pid')
    mailbox = edge.cells('mboxes')
    if len(mailbox) != 3 or phandles.get(mailbox[0]) is not ipcc or remote != 2 or mailbox[1:] != [3, 0]:
        raise ValueError('Captured native GLINK edge is not host0/ADSP2 IPCC3/0')
    channels = [n for n in edge.children if n.strings('qcom,glink-channels') == ['PMIC_RTR_ADSP_APPS']]
    if len(channels) != 1:
        raise ValueError('The observed PMIC_RTR_ADSP_APPS edge is not described')
    p2p = [n for n in nodes if 'qcom,smp2p' in n.strings('compatible') and
           n.scalar('qcom,remote-pid', -1) == 2 and n.scalar('qcom,local-pid', -1) == 0]
    if len(p2p) != 1 or p2p[0].cells('qcom,smem') != [443, 429]:
        raise ValueError('K60 ADSP SMP2P items do not match captured443/429')
    locks = smem.cells('hwlocks')
    if len(locks) != 2 or locks[1] != 3:
        raise ValueError('K60 SMEM mutex3 is not described')
    lock = referenced(smem, 'hwlocks')
    if lock.strings('compatible') != ['qcom,tcsr-mutex']:
        raise ValueError('Unexpected SMEM mutex transport')
    syscon = lock.cells('syscon')
    if len(syscon) != 3 or syscon[0] not in phandles:
        raise ValueError('SMEM mutex syscon/offset/stride missing')
    mutex_range = reg(phandles[syscon[0]])
    mutex_offset = syscon[1] + locks[1] * syscon[2]
    if mutex_offset + 4 > mutex_range[1]:
        raise ValueError('SMEM mutex falls outside syscon')
    smem_region = referenced(smem, 'memory-region')
    adsp_region = referenced(adsp, 'memory-region')
    if 'no-map' not in smem_region.properties or 'no-map' not in adsp_region.properties:
        raise ValueError('SMEM/ADSP carveouts lack measured no-map reservations')
    sb, sn = reg(smem_region)
    ab, an = reg(adsp_region)
    ib, ins = reg(ipcc)
    if ins != 4096 or sn != 0x200000 or an != 0x3100000:
        raise ValueError('Captured K60 SMEM/ADSP/IPCC resource geometry changed')
    return dict(smem_base=sb, smem_bytes=sn, ipcc_base=ib,
                mutex_base=mutex_range[0] + mutex_offset,
                adsp_base=ab, adsp_bytes=an, remote_pid=remote,
                ipcc_client=mailbox[1], ipcc_signal=mailbox[2],
                desc_item=478, tx_item=479, rx_item=480, smp2p_item=443,
                protocol=1)


def elf_symbols(path):
    raw = path.read_bytes()
    if raw[:7] != b'\x7fELF\x02\x01\x01' or struct.unpack_from('<H', raw, 18)[0] != 183:
        raise ValueError('Expected the actual AArch64 ELF battery-charger module')
    off = struct.unpack_from('<Q', raw, 40)[0]
    size, count, names = struct.unpack_from('<HHH', raw, 58)
    if size != 64 or off + size * count > len(raw) or names >= count:
        raise ValueError('Module section table is invalid')
    sections = [struct.unpack_from('<IIQQQQIIQQ', raw, off + size * i) for i in range(count)]

    def string(data, at):
        end = data.find(b'\0', at)
        if at >= len(data) or end < 0:
            raise ValueError('Invalid module string table')
        return data[at:end].decode()

    found = {}
    for sec in sections:
        if sec[1] != 2:
            continue
        if sec[6] >= count or sec[9] != 24 or sec[4] + sec[5] > len(raw):
            raise ValueError('Module symbol table is invalid')
        strings = sections[sec[6]]
        strings = raw[strings[4]:strings[4] + strings[5]]
        for at in range(sec[4], sec[4] + sec[5], 24):
            name, _, _, index, value, nbytes = struct.unpack_from('<IBBHQQ', raw, at)
            label = string(strings, name)
            if label not in ('battery_prop_map', 'usb_prop_map', 'wls_prop_map'):
                continue
            if index >= count:
                raise ValueError(f'Module map {label} is not a defined section symbol')
            target = sections[index]
            begin = target[4] + value - target[3]
            if nbytes % 4 or begin + nbytes > target[4] + target[5]:
                raise ValueError(f'Module map {label} falls outside its section')
            found[label] = list(struct.unpack_from(f'<{nbytes // 4}I', raw, begin))
    expected = {
        'battery_prop_map': [0, 2, 3, 1, 46, 0, 14, 12, 8, 17, 33, 34, 29, 51, 6, 28, 7, 22, 24, 72, 62, 60, 0, 20, 21],
        'usb_prop_map': [4, 12, 8, 17, 16, 37, 0, 64, 0, 0, 51, 0, 0],
        'wls_prop_map': [4, 12, 8, 17, 16, 0, 3],
    }
    if found != expected:
        raise ValueError(f'Actual battery-charger property maps changed; requalify protocol: {found}')
    return found


def wire_messages(path):
    if path is None:
        return []
    result = []
    for line in path.read_text(errors='strict').splitlines():
        match = re.search(r'\b(Tx|Rx) data:\s*((?:[0-9a-fA-F]{2}(?:\s+|$))+)', line)
        if not match:
            continue
        data = bytes.fromhex(match.group(2))
        if len(data) < 12 or struct.unpack_from('<I', data)[0] != OWNER:
            continue
        result.append((match.group(1), data))
    return result


def current_pair(messages, expected_status):
    current = None
    currents, statuses = [], []
    pending = None
    for direction, data in messages:
        _, kind, opcode = struct.unpack_from('<III', data)
        if direction == 'Tx' and len(data) == 24 and kind == 1 and opcode == 0x30:
            battery_id, property_id, value = struct.unpack_from('<III', data, 12)
            if battery_id or value:
                continue
            pending = property_id
        if direction == 'Rx' and len(data) == 24 and kind == 1 and opcode == 0x30:
            prop, value, rc = struct.unpack_from('<III', data, 12)
            if rc or pending != prop:
                continue
            if prop == 0:
                statuses.append(value)
            elif prop == 9:
                current = struct.unpack_from('<i', data, 16)[0]
                currents.append(current)
            pending = None
    if (not statuses or any(s != expected_status for s in statuses) or not currents or
            any(not c or abs(c) > 20000000 or (c > 0) != (currents[0] > 0) for c in currents)):
        raise ValueError(f'Wire capture lacks stable status{expected_status}/signed-current9 evidence: statuses={statuses} currents={currents}')
    return current


def qualification(charging, discharging, notify):
    sign = 0
    current_evidence = None
    if bool(charging) != bool(discharging):
        raise ValueError('Qualify current with both --charging-wire and --discharging-wire')
    if charging and discharging:
        charge = current_pair(wire_messages(charging), 1)
        drain = current_pair(wire_messages(discharging), 2)
        if (charge > 0) == (drain > 0):
            raise ValueError('Captured charge/discharge currents have the same sign; do not infer polarity')
        sign = 1 if charge > 0 else -1
        current_evidence = dict(charging_ua=charge, discharging_ua=drain,
            charging_capture=str(charging), charging_sha256=sha256(charging),
            discharging_capture=str(discharging), discharging_sha256=sha256(discharging))
    reply_type, reply_bytes = 0, 0
    notify_evidence = None
    if notify:
        pending = False
        replies = []
        for direction, data in wire_messages(notify):
            _, kind, opcode = struct.unpack_from('<III', data)
            if opcode != 4:
                continue
            if direction == 'Tx' and kind == 2 and len(data) == 28 and not any(data[12:]):
                pending = True
            elif direction == 'Rx' and pending:
                if kind not in (1, 2) or len(data) not in (12, 16, 24, 28) or any(data[12:]):
                    raise ValueError(f'Unqualified subscription ACK type/length/payload: {data.hex()}')
                replies.append((kind, len(data)))
                pending = False
        if not replies or len(set(replies)) != 1:
            raise ValueError('Wire capture lacks one unambiguous measured opcode4 subscription response')
        reply_type, reply_bytes = replies[0]
        notify_evidence = dict(capture=str(notify), sha256=sha256(notify),
                               type=reply_type, bytes=reply_bytes)
    return sign, reply_type, reply_bytes, current_evidence, notify_evidence


def encode_config(config, sign):
    data = bytearray(CONFIG_BYTES)
    struct.pack_into('<4I', data, 0, 0x4342364b, 1, CONFIG_BYTES, 0)
    struct.pack_into('<6Q', data, 16, *(config[k] for k in
        ('smem_base', 'smem_bytes', 'ipcc_base', 'mutex_base', 'adsp_base', 'adsp_bytes')))
    struct.pack_into('<8I', data, 64, *(config[k] for k in
        ('remote_pid', 'ipcc_client', 'ipcc_signal', 'desc_item', 'tx_item', 'rx_item', 'smp2p_item', 'protocol')))
    struct.pack_into('<i', data, 96, sign)
    return bytes(data)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--tree', type=Path, default=Path.cwd())
    ap.add_argument('--output-dir', required=True, type=Path)
    ap.add_argument('--framework', type=Path, default=Path(os.environ.get('UNIXNU_FRAMEWORK', DEVICE.parents[1] / 'core')))
    ap.add_argument('--hardware-dtb', required=True, type=Path)
    ap.add_argument('--battery-module', required=True, type=Path)
    ap.add_argument('--charging-wire', type=Path)
    ap.add_argument('--discharging-wire', type=Path)
    ap.add_argument('--notification-wire', type=Path)
    ap.add_argument('--sdk-root', type=Path)
    ap.add_argument('--emit-config-only', action='store_true', help='Generate captured resource config and prerequisite report, no compiler invocation')
    args = ap.parse_args()
    tree, out = args.tree.resolve(), args.output_dir.resolve()
    parser = load_framework(args.framework.resolve())
    config = board_config(args.hardware_dtb.resolve(), parser)
    maps = elf_symbols(args.battery_module.resolve())
    sign, notify_type, notify_bytes, current_evidence, notify_evidence = qualification(
        args.charging_wire, args.discharging_wire, args.notification_wire)
    config['charging_current_sign'] = sign
    out.mkdir(parents=True, exist_ok=True)
    encoded = encode_config(config, sign)
    generated = out / 'K60BatteryConfig.generated.c'
    rows = ''.join(','.join(str(n) for n in encoded[i:i + 16]) + ',\n' for i in range(0, len(encoded), 16))
    generated.write_text('/* Captured K60 hardware resource record, not a battery sample. */\n'
        '#include "K60BatteryConfig.h"\nconst uint8_t K60BatteryBoardConfig[K60_BATTERY_CONFIG_BYTES]={\n' +
        rows + '};\nconst size_t K60BatteryBoardConfigBytes=sizeof(K60BatteryBoardConfig);\n')
    (out / 'K60BatteryProtocol.generated.h').write_text(
        '/* Zero until exact subscription ACK wire capture qualifies it. */\n'
        f'#define K60_BATTERY_NOTIFY_REPLY_TYPE {notify_type}u\n'
        f'#define K60_BATTERY_NOTIFY_REPLY_BYTES {notify_bytes}u\n')
    (out / 'captured-board-config.bin').write_bytes(encoded)
    report = dict(target='arm64-apple-ios16.0', config=config,
        hardware_dtb=str(args.hardware_dtb.resolve()), hardware_dtb_sha256=sha256(args.hardware_dtb),
        battery_module=str(args.battery_module.resolve()), battery_module_sha256=sha256(args.battery_module),
        checked_module_maps=maps, current_qualification=current_evidence, notification_qualification=notify_evidence,
        required_platform_handoff='K60BatteryConfig.h K6BH v1, authenticated PAS1 owner and exclusive fresh APSS GLINK epoch',
        firmware_start_implemented=False, synthetic_handoff=False, battery_readings_embedded=False,
        current_sign_qualified=sign != 0, subscription_qualified=notify_bytes != 0,
        hardware_qualified=False, archive_built=False, commands=[])
    if not args.emit_config_only:
        framework = tree / '.cache/fakeroot/System/Library/Frameworks/Kernel.framework/Versions/A'
        if not (framework / 'PrivateHeaders/IOKit/pwr_mgt/IOPMPowerSource.h').exists() and not (framework / 'Headers/IOKit/pwr_mgt/IOPMPowerSource.h').exists():
            raise ValueError('Build the real Darwin22 Kernel SDK before this archive')
        sdk = str(args.sdk_root.resolve()) if args.sdk_root else os.environ.get('UNIXNU_SDKROOT')
        if not sdk:
            sdk = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], text=True).strip()
        source = DEVICE / 'drivers/PongPower'
        common = ['-target', 'arm64-apple-ios16.0', '-isysroot', sdk,
            '-mkernel', '-ffreestanding', '-fno-builtin', '-fno-stack-protector', '-mgeneral-regs-only', '-Os',
            '-DKERNEL=1', '-DKERNEL_PRIVATE=1', '-DXNU_KERNEL_PRIVATE=1', '-DARM64_BOARD_CONFIG_PONG=1',
            # Public headers first: PrivateHeaders/IOKit/IOLib.h expands
            # IOTypedOperatorsMixin in a way this host compiler rejects, while the
            # public IOLib.h plus the private IOPMPowerSource.h compile cleanly.
            '-I' + str(framework / 'Headers'), '-I' + str(framework / 'PrivateHeaders'),
            '-I' + str(out), '-I' + str(source)]
        objects = []
        for file in ('K60BatteryConfig.c', 'K60Smem.c', 'QcomGlink.c', 'K60Battmgr.c',
                     'K60PmicGlink.cpp', 'K60Battery.cpp', str(generated)):
            path = Path(file) if Path(file).is_absolute() else source / file
            obj = out / (path.stem + '.o')
            cpp = path.suffix == '.cpp'
            command = ['xcrun', 'clang++' if cpp else 'clang', *common]
            # The kernel has no C++ runtime, so a static destructor must not
            # lower to __cxa_atexit. The kernel build uses the same flag.
            command += ['-fno-exceptions', '-fno-rtti', '-fno-stack-check', '-std=gnu++17', '-fblocks',
                        '-mllvm', '-disable-atexit-based-global-dtor-lowering',
                        '-Wno-deprecated-declarations'] if cpp else ['-std=gnu11', '-Wall', '-Wextra', '-Werror']
            command += ['-c', str(path), '-o', str(obj)]
            report['commands'].append(command)
            result = subprocess.run(command, capture_output=True, text=True)
            (out / (path.stem + '.build.log')).write_text(result.stdout + result.stderr)
            if result.returncode:
                report.update(failed_source=str(path), compiler_returncode=result.returncode)
                (out / 'build-report.json').write_text(json.dumps(report, indent=2) + '\n')
                raise ValueError(f'{path.name}: compiler failed; see {out / (path.stem + ".build.log")}')
            objects.append(obj)
        # The parent IOPMPowerSource is builtin XNU, so ordinary kernel static
        # constructors are correct. No prelinked-Apple ABI address or bypass.
        archive = out / 'libK60PhysicalBattery.a'
        archive.unlink(missing_ok=True)
        # ld64 needs BSD/Darwin member names; a GNU '//' long-name table is
        # rejected as an unsupported file format, which silently drops the
        # whole archive from the link.
        command = ['xcrun', 'llvm-ar', '--format=darwin', 'rcs', str(archive), *map(str, objects)]
        subprocess.run(command, check=True); report['commands'].append(command)
        report.update(archive=str(archive), archive_built=True)
    (out / 'build-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(str(out / 'build-report.json') if args.emit_config_only else str(archive))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(str(exc)) from exc
