# Archived: the Darwin 22/24 ArmDTPlatform

The iOS 16.6.1 line built this copy: it calls `pong_cpu_start()` at the end of
`configure()`, starts the Adreno platform driver behind
`XNU_PONG_ADRENO_PLATFORM`, logs every published DT nub, and anchors the
calendar to a `boot-epoch` property in `/chosen`.

The iOS 27 branch does **not** build it. Two reasons:

- A directory under the device repository's `drivers/` resolves with origin
  `device` and outranks the catalog component of the same name, so this copy
  silently replaced `UniXNU/ArmDTPlatform` at every build.
- The Darwin 26 pair is different: the catalog `ArmCpu` registers CPUs and
  starts them itself, so there is no `pong_cpu_start()` to call, and the
  catalog `ArmDTPlatform` has a clock-registration hook
  (`armdt_platform_clock_register`) that replaces the `boot-epoch` sample.

What was real here and still matters:

- the software calendar anchored to a firmware UTC sample. The catalog
  component now has the hook, but no K60 clock driver registers with it yet.
  When userland needs a real wall clock (F4), write that driver against
  `armdt_platform_clock_register`; do not restore this file.
- the `platform-stage` / `platform-panic` probes: the catalog component keeps
  them (boot arguments without the old `sheng-` prefix).

If a K60-specific fix is still needed on the 27 line, it belongs in a patch
against the catalog component (or the SoC series), not in a second copy under
`drivers/`.
