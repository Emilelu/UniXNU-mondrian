# Toolchain shims for the iOS 27 userspace build

The Bluetooth userland in this branch is built from the QcaBluetooth component
with the target's own `bluetoothd`. Two small files make that build work on a
host that has only the Xcode Command Line Tools:

- `xpc-shim/xpc/xpc.h` — the Command Line Tools `iPhoneOS.sdk` ships
  `libxpc` without its headers. This header declares the 13 libxpc symbols
  `userland/BlueTool.c` uses.
- `qca-bluetooth-extra-flags.diff` — adds `QCA_BT_EXTRA` to
  `tools/build-bluetool.py` so the compiler line can take the include path and
  `-Wl,-undefined,dynamic_lookup`.

Usage on such a host, from the component checkout:

```sh
patch -p1 < <device>/scripts/toolchain/qca-bluetooth-extra-flags.diff
QCA_BT_EXTRA="-I<device>/scripts/toolchain/xpc-shim -Wl,-undefined,dynamic_lookup" \
  <device>/scripts/build-bluetooth-userspace.py OUT ios27 --os-root <os-root> --component .
```

With a full Xcode install neither file is needed: the SDK carries `xpc/xpc.h`
and `build-bluetool.py` links against `libxpc` normally.

Verified 2026-11-19 against the 24A446 root file system (see
`docs/plans/BT-IOS27-PORT.md` section 6.1). The host ran Command Line Tools
16.5-era `iPhoneOS.sdk`; `codesign` was the system tool.
