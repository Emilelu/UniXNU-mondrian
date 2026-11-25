# GopFramebuffer board archive: first successful build

Date: 2026-11-24. Offline only: no kernel build, no boot.

Produced on Linux with `scripts/build-k60-driver.sh` plus the header generator,
using the component staged at `tree/drivers/GopFramebuffer` and the C++ record
`IOCommandGate.cpo.json`.

| File | Bytes | sha256 |
| --- | --- | --- |
| `OriginalLegacyFramebufferABI.h` | 31,556 | `5dd3f91702e7d51132489ec99c7e384832950b25a25fe7845e52dabdab7d9b70` |
| `original-bindings.S` | 38,543 | `476c36494790452a201a8cb660813e93abdb19fb6c40dd5844ccd996f8accbab` |
| `original-addresses.S` | 32,720 | `7ddbba4e3da22ccc2ba6087572eb8139cfddda38e09634190a1665c52a179b4e` |
| `libNativeLegacyDisplay.a` | 408,672 | `e3c54c1284f671faa1f1928092142063fe80d1736750d42f683d9cc797b0fca5` |

Also produced: `NativeLegacyDisplay.o` 408,520 B, `original-bindings.o` 34,328 B,
`original-addresses.o` 16,696 B. Compile audit line:
`NativeLegacyDisplay: -Werror build and arm64e-apple-ios27.0 object audit passed`,
`compile.log` empty.

Archived at `E:\iOS Port\Work\artifacts\display-abi\`.

Open: wiring the archive into `board.toml` `kernel.archives` and enabling
`CONFIG_XNU_NATIVE_LEGACY_DISPLAY` still has to be done together with the
`build-report.json` that the kernel builder verifies; neither is done yet.
