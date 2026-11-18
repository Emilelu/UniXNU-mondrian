# Archived: the Darwin 22/24 ArmCpu driver

This is the hand-written `ArmCpu` the iOS 16.6.1 line (and the retired darwin24
route) built: `pong_cpu_first_boot`, the flat SM8475 MPIDR handling and the
Darwin 22 start order described in `porting.toml` (area `cpu`).

The iOS 27 branch does **not** build it. It shadows the catalog component of the
same name, and the arm64e build needs `ArmCpuSleep.h` and the 17/27 ABI that the
catalog `UniXNU/ArmCpu` revision carries. Keeping the directory under a
different name preserves the device evidence without selecting the stale
driver.

If a fix from here is still needed on the 27 line, it belongs in the catalog
component (or a patch against it), not in a second copy under `drivers/`.
