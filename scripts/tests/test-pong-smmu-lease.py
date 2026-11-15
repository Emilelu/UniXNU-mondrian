#!/usr/bin/env python3
"""The Apps SMMU lease must be usable by the first client that wants it.

NativeUfs takes the lease in hostBringUp(), which runs before
ArmDTPlatform::configure() calls pong_wifi_start_optional(), so the lock cannot
be allocated only in pong_rpmh_init(). A source-level assertion is enough here:
the behaviour is one line of allocation order, and a compiled host test would
have to stub IOLockAlloc, IOLockLock and the whole platform header surface to
prove the same thing.
"""
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / 'drivers' / 'PongWifi' / 'PongWifiPlatform.cpp'
SERIES = REPO / 'patches' / 'wifi' / 'series'
PATCH = REPO / 'patches' / 'wifi' / '0012-drivers-PongWifi-lease-lock-lazy-init.patch'


def function_body(text, signature):
    start = text.index(signature)
    end = text.index('\n', start)
    return text[start:end]


def main():
    failures = []
    text = SOURCE.read_text()

    if text.count('extern "C" bool pong_smmu_lease_lock(void)') != 1:
        failures.append('pong_smmu_lease_lock must be defined exactly once')
    else:
        body = function_body(text, 'extern "C" bool pong_smmu_lease_lock(void)')
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

    unlock = function_body(text, 'extern "C" void pong_smmu_lease_unlock(void)')
    if 'if(smmuLeaseLock)IOLockUnlock(smmuLeaseLock)' not in unlock:
        failures.append('pong_smmu_lease_unlock must stay guarded')

    init = function_body(text, 'extern "C" void pong_rpmh_init(void) {')
    init = text[text.index('extern "C" void pong_rpmh_init(void) {'):]
    init = init[:init.index('\n}\n')]
    if 'smmuLeaseLock=IOLockAlloc()' not in init:
        failures.append('pong_rpmh_init must keep its allocation')

    if not PATCH.exists():
        failures.append('%s is missing' % PATCH.name)
    else:
        names = [line.strip() for line in SERIES.read_text().splitlines() if line.strip()]
        if PATCH.name not in names:
            failures.append('%s is not listed in patches/wifi/series' % PATCH.name)
        elif names[-1] != PATCH.name:
            failures.append('the lease patch must be the last series entry')
        if 'if(!smmuLeaseLock)smmuLeaseLock=IOLockAlloc()' not in PATCH.read_text():
            failures.append('the patch does not carry the lazy allocation')

    if failures:
        for failure in failures:
            print('FAIL: ' + failure)
        return 1
    print('TESTS OK: the Apps SMMU lease is allocated on first use')
    return 0


if __name__ == '__main__':
    sys.exit(main())
