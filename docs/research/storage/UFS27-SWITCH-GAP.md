# The two silent `test -f` lines — one page for the Lead

Owner: the Lead (framework copy). Nothing here builds, links or touches a device.

## 1. The gap

`scripts/build-xnu-generic.sh` guards two storage archives behind a switch, and
tests for each archive with a bare `test -f`:

```sh
:728   if [ "$NATIVE_RAM_BLOCK" = 1 ] && [ "${XNU_SOURCE_STORAGE:-0}" != 1 ]; then
:729     RAM_BLOCK_ARCHIVE=$ROOT/build/ram-block/libRamBlock.a
:730     test -f "$RAM_BLOCK_ARCHIVE"          # <-- silent when missing
...
:765   if [ "$OWNER_ROOT_PROBE" = 1 ]; then
:766     VERIFIED_ROOT_ARCHIVE=${XNU_VERIFIED_ROOT_ARCHIVE:-$ROOT/build/verified-root-xnu/libVerifiedRootProbe.a}
:767     test -f "$VERIFIED_ROOT_ARCHIVE"      # <-- silent when missing
```

The script starts with `set -euo pipefail` (`:9`), so a missing archive ends the
build at that line with exit status 1 and **no message at all**. Whoever turns
either switch on sees a build that stopped for no stated reason.

## 2. Proof that it is silent

```sh
$ bash -euc 'A=/nonexistent/libRamBlock.a; test -f "$A"'; echo "exit=$?"
exit=1                     # and nothing on stdout or stderr
```

A stop with no output is exactly what the four-segment failure ladder
(`docs/` boot-progress reading, no serial console on this board) cannot
attribute: it looks like a driver crash, a stall, or a wrong image.

## 3. The fix, as a patch

`docs/research/storage/UFS27-SWITCH-GAP.patch` (22 lines, two hunks, nothing
else touched). Apply from the repository root:

```sh
$ patch -p1 --dry-run < docs/research/storage/UFS27-SWITCH-GAP.patch
checking file scripts/build-xnu-generic.sh
$ patch -p1 < docs/research/storage/UFS27-SWITCH-GAP.patch
```

Each line becomes the same guarded form:

```sh
test -f "$X" || { echo "build-xnu: … is requested (XNU_*_=1) but $X is missing" >&2; exit 1; }
```

The construct, measured in both directions:

```sh
$ bash -euc 'A=/nonexistent/libRamBlock.a; test -f "$A" || { echo "build-xnu: NativeRamBlock is requested (XNU_NATIVE_RAM_BLOCK=1) but $A is missing" >&2; exit 1; }'
build-xnu: NativeRamBlock is requested (XNU_NATIVE_RAM_BLOCK=1) but /nonexistent/libRamBlock.a is missing
exit=1
$ touch /tmp/ok.a; bash -euc 'A=/tmp/ok.a; test -f "$A" || { echo missing; exit 1; }'; echo "exit=$?"
exit=0                     # the successful path stays quiet
```

## 4. Where it lands, and why it is not a device change

`scripts/build-xnu-generic.sh` in this repository is a vendored copy:
`scripts/refresh-xnu-generic.py:15` overwrites it from the framework checkout on
every refresh, because a device file named `build-xnu-4k-baseline.sh` shadows the
framework builder in the assembled tree (P-255). So the change belongs in the
framework copy and arrives here through that refresh; the patch is written
against the vendored file only so it applies and can be read in this tree.

It is also orthogonal to whether the switches are on: the same two lines are
correct code in every state, they simply only matter when the block is entered.

## 5. Third occurrence, same shape, not in the patch

`scripts/build-xnu-generic.sh:699-701` tests `$VIRTIO_ARCHIVE` the same way.
It is dormant on this board (no virtio-mmio node, `CONFIG_XNU_ARMVIRT_PLATFORM=n`)
and its switch also needs `XNU_NATIVE_AES=1`, so it is listed here rather than
patched: three lines of the same defect in one file are one decision, not three.

## 6. How the gate treats it, before and after

`scripts/check-ufs27-storage-switches.py` is state-scoped as of 2026-11-21:

| State | What the gate prints for `:730` / `:767` | Exit |
| --- | --- | --- |
| dormant (today: both switches off) | `NOTE … bare test -f, latent while CONFIG_* is off … a GAP the moment the switch opens`, plus the tail `, 2 dormant (switch off; latent defects reported above)` | 0 |
| open (switch on + a recipe writes the archive) | `GAP … the build exits 1 with no output` | 1 |
| latent fixture (switch on, recipe present, line unpatched) | the same two `GAP`s, which is the proof that dormant scopes the criterion instead of relaxing it | 1 |

So today's honest verdict is `0 gap(s), 2 dormant`, and the two lines stay
visible in every run. After this patch lands, the same run prints
`OK … test -f on $RAM_BLOCK_ARCHIVE reports a message before exiting` and the
`dormant` tail disappears — that is the criterion: **`0 gap(s)`, no `dormant`
count, and both rows `OK`** while the switches are still off.

The gate cannot go green by itself here: it exits 0 only because nothing claims
closure while the switches are off, and it can only stop reporting the defect
when the line says why it failed.

## 7. What this page does not claim

It does not produce `build/ram-block/libRamBlock.a` or
`build/verified-root-xnu/libVerifiedRootProbe.a` — neither has a producer in
this profile (the only producers write `build/native-ram-block/` and
`build/native-ufs/`, which the 16.6.1 builder reads). It does not open either
switch: both are refused earlier by the crypto-bootstrap prerequisite
(`:199-203`, `:221-227`, `:287-291`), which the Lead's stage-0 ruling keeps as an
accepted wall. It only makes the next failure say what it is.
