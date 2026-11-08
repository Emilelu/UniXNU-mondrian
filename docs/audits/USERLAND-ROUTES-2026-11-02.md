# Userland routes compared: UniXNU vs hackios vs pong (2026-11-02T19:11:15+08:00)

Three working trees exist locally and they do NOT share a userland model.
Copying a recipe across them is wrong unless the layer it edits exists in the
target. This records the difference so the mistake is not repeated.

## The three models

| | **UniXNU-mondrian (ours)** | **ios-sweet-k60 (hackios)** | **UniXNU-pong** |
|---|---|---|---|
| Root lives in | unixnu partition, SHNGROOT | RAM image / HFSX image on userdata | cloned APFS images |
| Root format | **OS + SystemOS APFS, read-only union on /** | HFSX, single volume, writable | APFS copies, writable at build time |
| Can the root be edited | **no** (sealed read-only union) | yes, at build time | yes, at build time |
| PID 1 | stock launchd | stock launchd | **own static init, then execs `launchd.ios`** |
| Where preparation happens | kernel patches + boot args | build-time root tweaks | **run time, inside init (PID 1)** |
| Survives reboot | yes (persistent partition) | no (RAM image) | yes |

## What each one actually does

### hackios (ios-sweet-k60)
Preparation is a build-time rewrite of a writable HFSX image:
`tools/sweet-root-tweaks.py` renames `_PanicOnCrash`, creates
`/private/var/containers/...`, writes the migration/Setup preferences, and
disables the audio plug-ins. Its own notes state the pong userland route is
**not needed for it** because it already has "shim + HFSX real root + launchd
running" (`docs/GPU-PORT-NOTES.md:31`).

That reasoning does NOT transfer to us: our root is a sealed read-only APFS
union, so there is no file to rename at build time.

### pong (UniXNU-pong/userland)
Preparation happens at **run time**, inside a static init that becomes PID 1:

- `prepare_var()` builds the whole `/private/var` tree from `var.skel`
- `prepare_runtime_paths()` creates containers/installd/logs with uid/gid/mode
- `prepare_setup_bypass()` seeds the Setup-complete preferences once, with a marker
- `prepare_device_identity()` drops the MobileGestalt cache after an identity change
- `prepare_boot_services()` bindfs-hides the audio HAL plug-ins
- `configure_ui_library()` calls `sysctlbyname("kern.exec_inject", ...)` to inject
  a compatibility library into SpringBoard/backboardd/containermanagerd
- finally `execve("/sbin/launchd.ios", ...)` runs the stock launchd

`ui_compat18.c` (1788 lines) is the injected adapter. It is written against
**iPadOS 18 / Darwin 24** classes and methods.

## Does the kernel already support it?

Yes, in our built `kernel.macho`:

| primitive | occurrences |
|---|---|
| `kern.exec_inject` | 13 |
| `bindfs` | 80 |
| `PONG APFS: SystemOS mounted` union path | 1 |

So the kernel side of the pong model is present. The gap is the userland
adapter, which is Darwin 24-specific.

## Decision taken

**Diagnose first; do not replace PID 1 yet.**

Reasons:
1. Our launchd root chain is already verified end to end; replacing PID 1
   risks losing it before the failing contract is even named.
2. The failing programs (`accounts`, `financed`, `suggestd`, `cloudd`, `dmd`,
   `mmaintenanced`, `mobileactivation`, `liveactivitiesd`, `ScreenTimeAgent`)
   appear **nowhere in the reference record as solved**, so there is no proven
   cause to port.
3. The pong adapter cannot be reused as-is: it targets Darwin 24 ABI.

If, after diagnosis, the blocker turns out to be a preparation step that only
init can perform (non-writable root), then porting `init.c` becomes the
justified next step, and this document is the record of why.

## Already done on the diagnosis side

- kernel prints one line per distinct failing program with `ns/code`
- kernel dumps the dying task`s heap strings as `STR <pid> '<comm>' <text>`
- the five-second frame-statistics block is collapsed to one line and the
  repeated `Too many corpses being created` line is silenced, because this
  boot has no GUI yet -- the panel cannot be scrolled, so any extra line
  pushes the diagnostic off the screen permanently
