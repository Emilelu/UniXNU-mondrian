# UEFI firmware patches

These patches record how the `uefi-mondrian` EDK2 tree was modified for this
board. They are **records**, not part of the kernel build: `patches/xnu/series`
never lists them, and the UEFI tree already carries the applied result.

| File | Files touched | What it does |
|---|---|---|
| `uefi-unixnu-bootstrap.patch` | 3 | Earliest bootstrap: BootShim stack base, `mondrian.dsc`, `pong.fdf`. Superseded by the payload patch below |
| `uefi-payload.patch` | 14 | Full payload support: `PongBootMemoryDxe` (boot memory + initrd handoff), `PongInitrdTest`, `PongPayloadProbe`, Silicium `Sec` changes, BootShim, dsc/fdf |
| `uefi-darwinboot-fileset.patch` | 2 | `DarwinBoot`: accepts the arm64e `cpusubtype` and an `MH_FILESET` kernel collection by loading its `com.apple.kernel` entry, lets the driver replace the older loader in the FD, and publishes the Darwin 26 `boot_args` layout (1024-byte command line, `bootFlags` at `0x470`, `memSizeActual` at `0x478`) with the structure zeroed. The window starts at `VM_KERNEL_LINK_ADDRESS` and receives the whole collection image, because XNU reads the outer fileset header there when the inner kernel carries `MH_DYLIB_IN_CACHE` |

Apply order if rebuilding the UEFI tree from scratch:

```sh
cd <uefi-mondrian>
git apply <repo>/patches/uefi/uefi-unixnu-bootstrap.patch
git apply <repo>/patches/uefi/uefi-payload.patch
git apply <repo>/patches/uefi/uefi-darwinboot-fileset.patch
```

The second patch depends on the first: it edits lines the first introduces in
`mondrian.dsc` and `pong.fdf`.
