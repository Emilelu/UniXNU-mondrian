# UEFI firmware patches

These patches record how the `uefi-mondrian` EDK2 tree was modified for this
board. They are **records**, not part of the kernel build: `patches/xnu/series`
never lists them, and the UEFI tree already carries the applied result.

| File | Files touched | What it does |
|---|---|---|
| `uefi-unixnu-bootstrap.patch` | 3 | Earliest bootstrap: BootShim stack base, `mondrian.dsc`, `pong.fdf`. Superseded by the payload patch below |
| `uefi-payload.patch` | 14 | Full payload support: `PongBootMemoryDxe` (boot memory + initrd handoff), `PongInitrdTest`, `PongPayloadProbe`, Silicium `Sec` changes, BootShim, dsc/fdf |

Apply order if rebuilding the UEFI tree from scratch:

```sh
cd <uefi-mondrian>
git apply <repo>/patches/uefi/uefi-unixnu-bootstrap.patch
git apply <repo>/patches/uefi/uefi-payload.patch
```

The second patch depends on the first: it edits lines the first introduces in
`mondrian.dsc` and `pong.fdf`.
