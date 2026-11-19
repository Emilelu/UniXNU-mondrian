# Scripts the 27 line must not let shadow the framework's

The build tree copies every `scripts/` entry from the framework, then the SoC,
then this repository, and the last writer wins. A device script with the same
name as a framework script therefore replaces it silently - the same trap that
put the Darwin 22 drivers in front of the catalog ones.

On the iOS 27 line that cost the first stage-0 kernel build. `MACHINE_CONFIGS=PONG`
is rejected by xnu-12377 (`Unsupported CURRENT_MACHINE_CONFIG PONG`) and points
the prelink at an object tree that line never produces; the framework's script
builds `DEVELOPMENT_ARM64_BCM2837`, which is what the 27 OS profile pins. The
header preparation is the same story: the framework's `prepare-xnu-source.py` is
what `patches.py` runs before the series on 12377.

**Three of the four stay at their original paths, and one does not.**
`main` is the 16.6.1 line and that line boots: `scripts/unixnu/kernel.py:172`
runs `ctx.tree / 'scripts/build-xnu-4k-baseline.sh'`, and the device copy is the
whole K60 kernel build (SDKROOT, the platform archive list, the wifi and thermal
force-loads). The framework copy is half its size and has none of it;
`scripts/check-define-scope.py` reads the device file by name and fails without
it. Archiving any of those three would leave main unable to build a kernel.

`patches/unixnu-core/k60-unixnu-core.patch` is the exception and does live under
`legacy/`. It is not a shadowing problem but a glob problem:
`scripts/apply-core-patches.sh` applies every top-level
`patches/unixnu-core/*.patch` and sets `status=1` when one neither applies nor
reverse-applies. This one no longer applies to the framework - it fails on
`UniXNURamDiskDxe.c:161`, `UniXNURamDiskDxe.inf:11` and `Config.c:35` - so
leaving it at the top level would fail the 27 line's first
`build-ios27-linux.sh` step. Its content is upstream or superseded anyway, and
`main`'s build never applies it: the 16.6.1 kernel path runs
`build-xnu-4k-baseline.sh` directly, not `apply-core-patches.sh`.

So the rule for a 27-line build is a step, not a file move: delete the shadowing
copies from the **build tree** before the kernel step, or build from a checkout
that does not carry them. Remember that deleting a device script does not delete
its copy in the build tree (`out/<board>/<profile>/<config>/tree/scripts/<name>`),
or the next build keeps running the removed version.

Files covered:

| device path | why it shadows | what the 27 line needs |
|---|---|---|
| `scripts/build-xnu-4k-baseline.sh` | passes `MACHINE_CONFIGS=PONG` | framework's, `DEVELOPMENT_ARM64_BCM2837` |
| `scripts/prepare-xnu-source.py` | 16.6.1 header preparation | framework's, run by `patches.py` on 12377 |
| `scripts/build-firehose.sh` | writes the PONG build tree | framework's |
| `patches/unixnu-core/k60-unixnu-core.patch` | kept under `legacy/`; `apply-core-patches.sh` globs the top level and this one no longer applies | nothing; the 27 profile carries its own series |

`save-xnu-patch.py` is the next one to watch: it still shadows the framework
copy. It does not run in the stage-0 kernel build; move it out the moment a
27-line step calls it.
