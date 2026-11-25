# Compiling a GopFramebuffer driver object on Linux

Verified 2026-11-23 against the assembled iOS 27 tree.

`scripts/build-arm-driver.py` defaults to the `IOPlatformExpert.cpo.json` record
(a C kernel file) and never passes `-target`, so clang falls back to its host
triple and the build dies on `-Werror,-Woverriding-option`.

Three changes make it compile, each measured:

1. Set `UNIXNU_DRIVER_RECORD` to a C++ IOKit record:
   `build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/iokit/DEVELOPMENT/IOCommandGate.cpo.json`.
2. Append `-target` followed by `kernel_target.TRIPLE` (`arm64e-apple-ios27.0`).
3. Append `-Wno-missing-designated-field-initializers`: `IOKit/IOLib.h:1033`
   expands `_KALLOC_TYPE_DEFINE` without `kt_zearly`, which modern clang warns
   about and the appended `-Werror` promotes to an error.

Result line: `NativeLegacyDisplay: -Werror build and arm64e-apple-ios27.0 object audit passed`,
with zero `error:` lines in `build/native-legacy-display/compile.log`.

Prerequisites: the component source must be staged at `tree/drivers/GopFramebuffer`,
and the header generator must have written `OriginalLegacyFramebufferABI.h`.
