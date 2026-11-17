# QcomBaseband device patches

`0001-coachz-defer-publication.patch` applies to the upstream
`UniXNU/QcomBaseband` source at `dd0199cf3300764ed52b23f4a47761f91fab21a2`.
It is BSD-2-Clause code; the patch is kept here because the K60 build must not
depend on a private QcomBaseband branch.

`scripts/build-qcom-baseband.py` stages `baseband/coachz_baseband.cpp` and
applies this patch before compiling. The fix makes `coachz_baseband_configure()`
return without latching `bb_published` when `IOService::getResourceService()`
is still NULL, and only sets the latch after at least one service was made.
