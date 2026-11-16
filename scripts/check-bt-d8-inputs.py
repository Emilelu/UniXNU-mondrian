#!/usr/bin/env python3
"""Read-only identity check for the recorded bt-d8-tlv inputs, not a flash gate.

All paths are explicit. No fallback to the newest build or another checkout.
Checks the saved manifest, frozen lists, all series patch bytes, selected source
commit blobs, application log and boot image. Does not unpack the payload, prove
compiler output correspondence, validate a flash preflight, or test hardware.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

D8_PROFILE = {
    'manifest': '3dad0a5284896e7fe1cd649db67c604339ef7ec2c3baf17805a5804fe2f91db0',
    'kernel_log': '27c0c59caafd659bd9d0797ac354691e13a278eccb6edb3fac1e6d975174c6d3',
    'head': '91dcd0761aeb035c15de743478851fb8ce0c0417',
    'patches': {
        '0500-k60-bt-qbt-new-files.patch': '4e6f58d96f1ba06cd8d440feaa7546e3df05519631a8550b96a6441ba69bc0b0',
        '0514-k60-bt-boot-observability.patch': 'e6d5296b0b9e7e137c0f12271670aa485ebfa4e649b090101e258faef418a73c',
        '0515-k60-bt-tlv-counters.patch': '120c4d57d1bf72bdee18770a520367bd68d46c1c96ffb185c5bbf51ec46c4cd6',
    },
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def parse_frozen(data: bytes) -> dict[str, str]:
    result = {}
    for line in data.decode('utf-8').splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  (.+)', line)
        if not match:
            raise ValueError('malformed frozen entry')
        digest, name = match.groups()
        if name in result:
            raise ValueError('duplicate frozen entry: ' + name)
        result[name] = digest
    return result


def patch_names(data: bytes) -> list[str]:
    names = [line.strip() for line in data.decode('utf-8').splitlines() if line.strip()]
    if not names or len(names) != len(set(names)):
        raise ValueError('empty or duplicate series')
    if any('/' in name or '\\' in name or name in ('.', '..') for name in names):
        raise ValueError('series must contain plain patch basenames')
    return names


def committed(repo: Path, head: str, relative: str) -> bytes:
    proc = subprocess.run(['git', '-C', str(repo), 'show', f'{head}:{relative}'],
                          capture_output=True, check=False)
    if proc.returncode:
        raise ValueError(f'cannot read committed source: {head}:{relative}')
    return proc.stdout


def check(repo: Path, artifact: Path, profile: dict | None = None) -> dict:
    """Return structured failure, never a successful skip on absent inputs.

    profile is injected only by synthetic unit fixtures; CLI always pins D8.
    """
    profile = D8_PROFILE if profile is None else profile
    errors = []

    def require(condition, message):
        if not condition:
            errors.append(message)

    try:
        manifest_bytes = (artifact / 'build-manifest.json').read_bytes()
        require(sha(manifest_bytes) == profile['manifest'], 'manifest sha256 differs from reviewed profile')
        manifest = json.loads(manifest_bytes)
        require(manifest['repo']['head'] == profile['head'], 'manifest source head differs')
        require(manifest['repo']['dirty_files'] == 0, 'manifest records dirty source')
        before = (artifact / 'frozen-before.txt').read_bytes()
        after = (artifact / 'frozen-after.txt').read_bytes()
        require(before == after, 'frozen before/after differ')
        require(manifest['frozen']['file'] == 'frozen-before.txt', 'unexpected frozen list filename')
        require(sha(before) == manifest['frozen']['list_sha256'], 'frozen list sha256 differs')
        frozen = parse_frozen(before)
        series = repo / 'patches/xnu/series'
        series_bytes = series.read_bytes()
        names = patch_names(series_bytes)
        require(sha(series_bytes) == manifest['series']['file_sha256'], 'series file sha256 differs')
        require(len(names) == manifest['series']['count'], 'series count differs')
        require(manifest['series']['namespace'] == 'names+sizes', 'unknown series fingerprint namespace')
        require(committed(repo, profile['head'], 'patches/xnu/series') == series_bytes,
                'series differs from recorded commit')
        # Reuse the project's sole names+sizes implementation (P-214).
        spec = importlib.util.spec_from_file_location('bt_d8_fingerprint',
                    Path(__file__).with_name('series-fingerprint.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        value, count = module.fingerprint(series, series.parent)
        require(value == manifest['series']['sha256'] and count == len(names),
                'names+sizes fingerprint differs')
        for name in names:
            relative = 'patches/xnu/' + name
            require(relative in frozen, 'series patch not frozen: ' + name)
            require(file_sha(repo / relative) == frozen.get(relative), 'patch bytes differ: ' + name)
        log_bytes = (artifact / 'logs/kernel.log').read_bytes()
        require(sha(log_bytes) == profile['kernel_log'], 'kernel application log sha256 differs')
        applied = re.findall(r'^== kernel: patch (.+)$', log_bytes.decode('utf-8'), flags=re.M)
        # Check membership/order, not just a substring in a comment or error.
        last_position = -1
        for name, expected in profile['patches'].items():
            relative = 'patches/xnu/' + name
            require(name in names, 'selected patch absent from series: ' + name)
            require(frozen.get(relative) == expected, 'selected frozen sha256 differs: ' + name)
            require(sha(committed(repo, profile['head'], relative)) == expected,
                    'selected committed patch differs: ' + name)
            require(applied.count(name) == 1, 'application log must name patch exactly once: ' + name)
            position = applied.index(name) if name in applied else -1
            require(position > last_position, 'selected application order differs: ' + name)
            last_position = position
        require(file_sha(artifact / 'boot.img') == manifest['components']['boot_img'], 'boot image sha256 differs')
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        errors.append(f'input unavailable or malformed: {exc}')
    return {
        'state': 'FAIL' if errors else 'RECORDED_INPUTS_MATCH',
        'errors': errors,
        'scope': 'recorded build inputs only',
        'not_proven': ['payload/compiler correspondence', 'flash-gate coverage', 'controller acceptance', 'hardware function'],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True, type=Path, help='read-only source checkout containing recorded commit')
    parser.add_argument('--artifact', required=True, type=Path, help='exact bt-d8-tlv artifact directory')
    args = parser.parse_args(argv)
    result = check(args.repo, args.artifact)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 1 if result['errors'] else 0


if __name__ == '__main__':
    sys.exit(main())
