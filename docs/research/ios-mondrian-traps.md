# Traps measured by the ios-mondrian line

`xNekom/ios-mondrian` (fork of `dipa-studio/ios-sweet`, branch `mondrian`) is a
second port of the same phone: POCO F5 Pro / Redmi K60, SM8475, iOS 16
(xnu-8796) with the userland of an iPhone X. It boots through a bare-metal
*shim* and a payload, not through UniXNU and Mu, so the boot path differs. The
hardware does not. Everything below was measured on the device by that line and
is worth reading before rediscovering it here.

Examined 2026-11-18. Only the facts this branch can use are copied; the shim's
own machinery is not.

## Page size

`ID_AA64MMFR0_EL1` reports `TGran16=1` (measured 2026-10-23 there). The port
runs 16 KiB pages because the iOS dyld cache is hashed in 16 KiB pages: a 4 KiB
kernel panics in `cs_validate_hash` on an offset that is not 16 KiB aligned.
The Android tree's `PAGE_SIZE=4096` is therefore the wrong number to trust; the
SoC granule and the userland are the sources.

## The window of RAM

The live device tree describes six memory regions: `0x80000000+0x6a000000`,
then a hole, `0xf4600000+0x0ba00000`, and four above 4 GiB. The kernel takes one
contiguous window and that window must satisfy four rules, each learned there
with a reset or a panic:

- start above the firmware's own memory and above the loader image **including
  the appended payload** (the loader wipes the window before unpacking it);
- base aligned to 32 MiB;
- end in memory that exists - XNU takes its first heap pages from the **end**,
  so a window ending in the hole hands them to nothing;
- contain no carve-out or hole in the middle. The VM hands out pages across the
  whole window, so the first access to a page taken from a firmware island is a
  synchronous external abort (`Kernel data abort`, `far` inside the physmap).

The one that works is `0x840000000+0x240000000` (9 GiB): the tree's 3 GiB and
6 GiB regions are adjacent with no carve-out inside. The 12 GiB are not
addable - the low 1.66 GiB hold the firmware islands and the splash, 885 MiB sit
behind a 139 MiB hole, and 30 MiB are loose.

Our handoff arena is `0x140000000` (5 GiB, `board.toml`), not that 9 GiB bank,
so the four rules are what to check against our own window: start above the
loader image and its payload, 32 MiB aligned, end in memory that exists, no
carve-out or hole inside.

## The physmap slide

The slide comes from `/chosen/random-seed`. With a random seed the boot is a
coin flip (about one in three dies in `pmap_map_bd`), because the physmap has to
fit next to the kernel image. Their board table pins 64 bytes of `0x11` and
passes the same seed to every build. If our DT builder still writes a random
seed, that is a one-in-three boot failure that looks like memory corruption.

## The splash framebuffer

`cont_splash_region` is `0xb8000000`, 43 MiB (`0x2b00000`), 1440x3200 - outside
the 9 GiB window. Their kernel installed an explicit VA alias for it in
`arm_vm_init` (patch 0295) instead of mapping it VA=PA; a VA=PA map only works
when the framebuffer happens to fall inside the window, which it does not here.

## Boot arguments, 607 bytes

With `fastboot boot`, ABL fills `/chosen/bootargs` with an Android line of about
1 KiB and `BOOT_LINE_LENGTH` is 1024; a loader that copies that line first
loses `rd=ufsroot0`. That is their shim's problem.

The part that transfers: iOS userland asks for `kern.bootargs` with a 608-byte
buffer and the handler copies the whole string, so **one byte over 607 is
`ENOMEM` for every reader**. `watchdogd` reads it on each launch and aborts, and
launchd answers with a respawn loop (about 28 aborts in ten minutes, measured
there). Keep the command line under 607 bytes; `tools/mkpayload.py` refuses past
it on that line and ours should refuse too.

## SPMI: the PPID is not the address

A peripheral's PPID is `(sid << 8) | peripheral`. pm8350b's haptics sit at
`0xf000` and answer at `0x3f0`; the SID-0 VADC is `0x031`. Their `usb-ring.py
spmimap` dumps the 540 entries the bootloader leaves behind. Reading a
peripheral another processor owns wedges the arbiter and costs the boot - check
the owner bits first.

## A failed boot deactivates the slot

After a boot that dies, ABL marks the active slot unbootable and then refuses
**every** `fastboot boot` with `Failed to load/authenticate boot image: Not
Found`, including a 4 KB stub and an image that booted an hour earlier.
`fastboot --set-active=<current-slot>` clears it. Without that step the refusal
reads as a kernel crash, and a USB log answering with the previous kernel's
banner "confirms" the wrong diagnosis. Any script that boots from RAM on this
phone needs the re-activation first.

## The firmware core cannot be switched off

PSCI `CPU_OFF` from EL2 returns on this TZ and leaves the core running at EL2:
the next interrupt goes to the loader's vectors, and the kernel later finds a
core inside its own scheduler with no state behind it, or panics with
`cpu=4 startup timeout`. Their shim parks the core and leaves it out of the
device tree; the kernel runs on the seven cores it is told about. The firmware
runs on Aff1 0 (an A510); the kernel is started on the X2, Aff1 7.

## Not transferable

- The shim, its LZ4 payload and its `usb=2` probe flag are theirs; our loader
  and Mu take a different route to the same place.
- `mondrianfb_*` and `mondrian_ui_hook` boot arguments belong to their frame
  buffer and their userland hook.
- Their patch numbering is per series; nothing here maps to a number in
  `patches/xnu/series`.
