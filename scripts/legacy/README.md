# Archived scripts from the iOS 16 (PONG) line

The build tree copies every `scripts/` entry from the framework, then the SoC,
then this repository, last writer wins. A device script with the same name as a
framework script therefore replaces it silently - the same trap that put the
Darwin 22 drivers in front of the catalog ones.

These two did exactly that on the first iOS 27 kernel build:

- `build-xnu-4k-baseline-pong.sh` still passed `MACHINE_CONFIGS=PONG`, which
  xnu-12377 rejects (`Unsupported CURRENT_MACHINE_CONFIG PONG`) and which points
  the prelink at an object tree this branch never produces. The framework's
  script builds `DEVELOPMENT_ARM64_BCM2837`, the target the OS profile pins.
- `prepare-xnu-source-pong.py` is the 16.6.1 header preparation. The framework's
  copy is what `patches.py` runs before the series on 12377.

Kept, not deleted: `main` still carries the originals at their old paths, and
the comparison is the evidence for why the 27 line must not.
`build-ios16-pong-macos.py` in `scripts/` names the old filenames and is dead on
this branch for the same reason.

`save-xnu-patch.py` still shadows the framework copy. It does not run in the
stage-0 kernel build; move it here the moment a 27-line step calls it.
