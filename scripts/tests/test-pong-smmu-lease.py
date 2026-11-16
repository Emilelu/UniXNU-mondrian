#!/usr/bin/env python3
"""The Apps SMMU lease must be usable by the first client that wants it (P-215).

NativeUfs takes the lease in hostBringUp(), which runs before
ArmDTPlatform::configure() calls pong_wifi_start_optional(), so the lock cannot
be allocated only in pong_rpmh_init().  That defect cost seven zero-byte images
and three days; this gate pins the whole causal chain.

The chain lives in three patch files, and on `main` the drivers do not exist
until those patches are applied -- so the assertions read the patches, which are
what main actually carries, and additionally check the applied source when a
patched checkout happens to be present.  A gate that only works in one of the two
environments would either be skipped on main or lie about the branch.
"""
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
PATCHES = REPO / 'patches' / 'wifi'
SERIES = PATCHES / 'series'
SOURCE = REPO / 'drivers' / 'PongWifi' / 'PongWifiPlatform.cpp'

LEASE_PATCH = '0012-drivers-PongWifi-lease-lock-lazy-init.patch'
REFUSING_LOCK = 'if(!smmuLeaseLock)return false;'
LAZY_LOCK = 'if(!smmuLeaseLock)smmuLeaseLock=IOLockAlloc();if(!smmuLeaseLock)return false;'


def read(path):
    return path.read_text(encoding='utf-8', errors='replace')


def patch_text(name):
    path = PATCHES / name
    if not path.exists():
        return None
    return read(path)


def series_entries():
    return [line.strip() for line in read(SERIES).splitlines()
            if line.strip() and not line.strip().startswith('#')]


def main():
    failures = []
    entries = series_entries()

    # 1. The lease segment exists at all: without 0004 asking for the lease, the
    #    ordering defect has no way to bite and this gate would be vacuous.
    lease_client = patch_text('0004-drivers-NativeUfs-pong-ufs-ready.patch')
    if lease_client is None:
        failures.append('0004 (the UFS lease client) is missing')
    elif 'pong_smmu_lease_lock' not in lease_client:
        failures.append('0004 no longer takes the Apps SMMU lease; '
                        'this gate would be vacuous')

    # 2. The refusing implementation is the pre-image: if 0001 stops carrying it,
    #    the story changed and this gate needs rewriting rather than passing.
    vendor = patch_text('0001-drivers-PongWifi-vendor-zizhan-087416a.patch')
    if vendor is None:
        failures.append('0001 (the vendor driver) is missing')
    elif REFUSING_LOCK not in vendor:
        failures.append('0001 no longer carries the refusing lock implementation; '
                        're-derive the P-215 assertion from the current source')

    # 3. The fix: lazy allocation inside lock(), listed last in the series.
    fix = patch_text(LEASE_PATCH)
    if fix is None:
        failures.append('%s is missing' % LEASE_PATCH)
    else:
        if LAZY_LOCK not in fix:
            failures.append('the lease patch does not allocate the lock on first use')
        if 'IOLockLock(smmuLeaseLock)' not in fix:
            failures.append('the lease patch dropped IOLockLock')
        if LEASE_PATCH not in entries:
            failures.append('%s is not listed in patches/wifi/series' % LEASE_PATCH)
        elif entries[-1] != LEASE_PATCH:
            failures.append('the lease patch must be the last series entry, so it '
                            'applies after every other edit to the same function')

    # 4. When a patched checkout is present, hold the applied source to the same
    #    standard.  On main the directory does not exist until the patches run.
    if SOURCE.exists():
        text = read(SOURCE)
        if text.count('extern "C" bool pong_smmu_lease_lock(void)') != 1:
            failures.append('pong_smmu_lease_lock must be defined exactly once')
        else:
            start = text.index('extern "C" bool pong_smmu_lease_lock(void)')
            body = text[start:text.index('\n', start)]
            alloc = body.find('smmuLeaseLock=IOLockAlloc()')
            guard = body.find('if(!smmuLeaseLock)return false')
            if alloc < 0:
                failures.append('pong_smmu_lease_lock must allocate the lock on first use')
            elif guard < 0:
                failures.append('pong_smmu_lease_lock must still fail when allocation fails')
            elif alloc > guard:
                failures.append('allocation must precede the null check')
            if 'IOLockLock(smmuLeaseLock)' not in body:
                failures.append('pong_smmu_lease_lock must take the lock')

        unlock = text[text.index('extern "C" void pong_smmu_lease_unlock(void)'):]
        unlock = unlock[:unlock.index('\n')]
        if 'if(smmuLeaseLock)IOLockUnlock(smmuLeaseLock)' not in unlock:
            failures.append('pong_smmu_lease_unlock must stay guarded')

        init = text[text.index('extern "C" void pong_rpmh_init(void) {'):]
        init = init[:init.index('\n}\n')]
        if 'smmuLeaseLock=IOLockAlloc()' not in init:
            failures.append('pong_rpmh_init must keep its allocation')

    if failures:
        for failure in failures:
            print('FAIL: ' + failure)
        return 1
    print('TESTS OK: the Apps SMMU lease is allocated on first use (P-215)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
