# Audit against ios-sweet-k60's proven walls (2026-11-02T18:26:27+08:00)

> Status (2026-11-07): the `ns=2` self-abort reading below is still current. Window numbers in "Ceiling note" are superseded by [MEASURED-HIGH-WINDOW-2026-11-02.md](MEASURED-HIGH-WINDOW-2026-11-02.md) and `board.toml`; see [STATE-2026-11-07.md](../state/STATE-2026-11-07.md).

`ios-sweet-k60` runs the same SoC (Redmond K60 / mondrian / SM8475) and reached the
iOS lockscreen and home screen. Its NOTES.md lists the walls in the order it broke
them. This records whether OUR kernel already covers each, checked in our built
`kernel.macho` and its sources rather than re-derived by experiment.

## Display prerequisites for CoreAnimation (its LOCKSCREEN-2026-10-28.md)

| # | Prerequisite | Ours | Evidence |
|---|---|---|---|
| 1 | canvas is the panel's native 1440x3200, not a faked logical size | PRESENT | `MiniIOMobileFramebuffer.cpp:455-461`, `K60 DISPLAY: panel ... DSC video mode` |
| 2 | AppleCLCD publishes TimingElements | PRESENT | same file, `setProperty("TimingElements", ...)` |
| 3 | AppleCLCD publishes ColorElements | PRESENT | `setProperty("ColorElements", ...)` |
| 4 | GetID returns 1 (0 means "no display" to CA) | PRESENT | `#define kFBDisplayID 1`, `out[0] = kFBDisplayID` |
| 5 | an empty IOAcceleratorES is published | PRESENT | 0212 patch, `IOAcceleratorES` strings in the binary |
| 6 | a first frame actually reaches the panel | PRESENT | `K60 DISPLAY: first frame presented` |

## Crash walls it hit, and whether ours can still hit them

| Wall (its number) | Root cause it proved | Ours |
|---|---|---|
| PRIV_WORK_INTERVAL deny (0064) | UIKit aborts "Failed to create work interval" | FIXED: `kern_priv.c:91` grants it unconditionally, before MAC policies |
| pid_hibernate is nosys (0070) | SpringBoard SIGSYS leaving an app | FIXED: `pid_hibernate` is compiled in (CONFIG_EMBEDDED on) |
| IOSurface re-mapping (0068) | backboardd snapshot crash | PRESENT: IOCoreSurfaceRoot + dup handling |
| display mode assert | canvas faked as iPhone X -> NSAssert -> SIGABRT | AVOIDED: we report the native panel |
| container path NULL | `container_system_path_for_identifier` returned NULL -> backboardd NSException | **OPEN** - our daemons still abort |
| Sandbox ENOPOLICY(159) | `__mac_syscall("Sandbox")` found no policy | policy is in the prelinked kernel; our exits show ns=2, not sandbox |

## What our current failure actually is

Console on the 4 GiB diagnostic boot:

    K60 ex=832 kx=283 abn=219 | mem=4096 actual=4096 managed=4096 free_pages=105012
    K60 last bad : 409 'accounts'  exit=0 sig=6 ns=2 code=0x6
    K60 last bad : 429 'financed'  exit=0 sig=5 ns=2 code=0x5
    K60 last bad : 420 'suggestd'  exit=163 sig=0 ns=0 code=0x0

`ns=2` is OS_REASON_SIGNAL, and `code` is the signal: SIGABRT(6) and SIGTRAP(5) mean
the programs killed THEMSELVES (assert / NSException / _os_crash), not jetsam and
not a sandbox refusal. ~1.6 GiB of free pages rules memory out. That is the same
shape as the reference project's NSException walls, whose reason text lives in the
dying task's address space.

## Diagnostic now built for that

The kernel at sha256 a945a2f2... adds: on a fatal-signal exit, copy the printable
runs from the low 4 MiB of that task's map (via `copyinmap`, no map internals,
no writes) and print them as

    STR <pid> '<comm>' <text>

so the console carries the NSException/assert text itself. This is the same
technique the reference project used (its sweep 0051) to find the reason.

## Ceiling note

12 GiB is not reachable as one XNU window on this unit: the only contiguous
unreserved high run is 8.65 GiB, 4..32 GiB holds no DRAM, and the loader caps a
window at 8 GiB. A window equal to the whole arena failed (DXE occupies part of
it); 7 GiB was accepted by the loader but XNU did not start, so 4 GiB remains the
proven configuration while the userland wall is worked.
