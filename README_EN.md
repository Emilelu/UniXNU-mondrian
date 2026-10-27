# UniXNU-mondrian

UniXNU device support for the Redmi K60 (**mondrian**, Qualcomm **SM8475**).

- Firmware: [uefi-mondrian](https://github.com/Emilelu/uefi-mondrian)
- Core: [UniXNU](https://github.com/UniXNU/UniXNU)

## Status (2026-10-27)

| Area | State | Notes |
| --- | --- | --- |
| UEFI boot chain | OK | ABL -> `fastboot boot` -> BootShim -> UEFI -> UniXNU menu |
| Display | OK | ABL splash framebuffer + SimpleFbDxe GOP; no GPU acceleration |
| Buttons | OK | Official KeypadDevice chain + `K60KeypadDeviceLib` (SPMI PON/GPIO) |
| Tools -> Advanced Logger | OK | 4 MB Advanced Logger + QR frames; OneSend captures the DXE log |
| XNU kernel | TODO | no `kernel.macho` yet; build with the Linux toolchain |
| Touch / GPU / audio / network / camera | TODO | not started |
| UFS / Data / root | TODO | planned dedicated `unixnu` partition, Android `userdata` stays intact |

## Build

Three sibling trees are required. Apply the core patch first:

```sh
git clone --recurse-submodules https://github.com/UniXNU/UniXNU
git clone https://github.com/Emilelu/UniXNU-mondrian
git clone --recurse-submodules https://github.com/Emilelu/uefi-mondrian
cd UniXNU
git checkout ae68700
../UniXNU-mondrian/scripts/apply-core-patches.sh .
./unixnu defconfig mondrian_defconfig -D ../UniXNU-mondrian
./unixnu fetch
./unixnu build firmware --uefi ../uefi-mondrian -D ../UniXNU-mondrian
./unixnu bootimg --uefi ../uefi-mondrian --dtb ../uefi-mondrian/Platforms/Xiaomi/mondrianPkg/FdtBlob/sm8475-xiaomi-mondrian.dtb --ramdisk none -D ../UniXNU-mondrian --output mondrian-boot.img
```

## Data safety

- Bring-up uses `fastboot boot` only: no partition is written.
- XNU root/Data will use a dedicated `unixnu` partition (dual-system layout),
  never Android `userdata`; see `docs/DUAL-SYSTEM.md`.
- Never flash `persist` or run `flash all`.
- Back up and verify the target before any partition write.

## License

Device code is BSD-2-Clause-Patent; imported components keep their own SPDX
headers and licenses. See `THIRD_PARTY_NOTICES.md`.
