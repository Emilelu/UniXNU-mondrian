# Agent instructions

This repository owns the Redmi K60 (mondrian, SM8475) device configuration,
peripherals, firmware selection, partition layout, power policy and packaging.
The shared SM8475 resources live in `UniXNU-sm8475-common`; the loader lives in
`uefi-mondrian`; the build driver, the documentation site and the component
catalog live in `UniXNU`.

**Current target: iOS 16.6.1 (20G81) / darwin22.** The darwin24 route is retired
and archived on `chore/archive-darwin24-main-20261103`.

The porting record in `porting.toml` is the authoritative device state. Every
subsystem change updates the record in the same pull request.

## Iron rules

Four rules outrank everything else in this file. They are not style preferences;
a violation costs work that cannot be recovered.

1. **Nothing durable lives in `/tmp`.** Patches, `series` entries, build
   scripts, notes, and any generated artefact a result refers to belong in the
   repository or under the workspace. `/tmp` is wiped without warning: on
   2026-11-07 a cleanup removed `/tmp/usb-cdc-mainline` and took an entire day
   of kernel patches with it, leaving only the compiled `macho` behind.

2. **Source is tracked and pushed before the next step.** A patch, script or
   document is not finished when it is written; it is finished when it is
   committed and pushed. `git status` must not carry source changes across a
   build, and a build tree must never be the only copy of a patch.

3. **Follow the eight-step process; no flashing without step ⑦.** Same model →
   official → reverse engineering → wide search → plan → deep dive → local
   verification → on device. The definition of every step, its required evidence
   and its pass condition live in
   [`docs/engineering/EIGHT-STEP-SPEC.md`](docs/engineering/EIGHT-STEP-SPEC.md).
   Step ⑦ requires all three of a static check, an offline unit test and an
   artefact check. "It compiles" is not verification.

4. **Check the official component catalog before writing a driver.** Read
   `UniXNU/components.toml` and the
   [driver repository list](https://unixnu.com/zh/drivers/repositories) first.
   Reimplementing an existing wheel is a defect, not initiative. The catalog
   already contains a GENI SPI controller (`QcomGeniSpi`), a Metal frontend
   (`AdrenoMetal`) and an A740 kernel driver (`Adreno740`); we hand-wrote
   equivalents before discovering them.

5. **The repository is the only source of truth; the build input is its mirror.**
   `E:\hackios\UniXNU-mondrian` and `/opt/k60/trees/usb-cdc-mainline/device`
   hold the same files, and only one direction of copying is allowed:
   repository → build input, through `scripts/sync-device-input.py`. Editing
   under `/opt` is lost on the next clone, and a file that exists in only one of
   the two places is invisible to whoever reads the other. This has cost real
   work three times: the `0403` firmware patch lived only in the build input, the
   `pong-touch`/`pong-buttons` DT nodes existed in the build input while the
   repository's `mondrian.dts` was a 2,364-byte stub, and the eight-step table
   deduplication was written, verified in the rendered README, and then destroyed
   by a `git reset --hard`.

   Three corollaries, each learned the hard way:

   - **`git reset --hard` before `git status` is data loss.** Uncommitted work
     does not survive it, and nothing warns. Run `git status --porcelain` and
     commit or stash first.
   - **`git pull --rebase` replays every commit after the reset point**, so a
     local revert is an opinion until it is pushed. The `0403` revert was undone
     this way one round after it was made.
   - **Scratch is for drafts, not deliverables.** A script that passes a check
     belongs in `scripts/` in the same turn; `check-dt-asserts.py` sat in the
     workspace for hours while every build ran without it.

6. **Following upstream means judging every commit, not reporting that one
   exists.** `scripts/track-upstream-branches.py` says what changed; that is not
   the end of the job. Each branch carries a watermark in
   [`docs/research/UPSTREAM-TRIAGE.toml`](docs/research/UPSTREAM-TRIAGE.toml),
   and every commit after it gets a verdict - `picked` (with how), or
   `not-applicable` (with why), or `deferred` (with why and when to look again).
   `scripts/check-upstream-triage.py` fails the build while anything past a
   watermark is unjudged.

   This rule exists because the alternative already happened: the same commits
   were rediscovered round after round, discussed each time, and adopted zero
   times. Reporting is not following. A deferred commit without a date is a
   forgotten commit.

   **The default verdict is `picked`.** Upstream is fixing real K60 problems and
   every one of those fixes is worth having; a commit earns `not-applicable`
   only by being documentation, and `deferred` only by physically not applying
   to our tree. "I would have written it differently" is not a reason. Where the
   divergence is broad enough that cherry-picking commit by commit stops making
   sense, rebase onto the upstream branch and re-apply our additions on top -
   that is the same rule followed at the right granularity, not an exception to
   it.

7. **Tags mark proven states, not progress.** A tag is a rollback anchor, so
   it is only worth having when it points at something we verified. Three kinds
   of tag are allowed, and nothing else:

   - `boot-proven-YYYYMMDD` - an image built from this commit reached
     SpringBoard on the device. The tag message must carry the image path,
     size and sha256 plus the console log it was proven with.
   - `snap-rN` - the commit registered as the `main` baseline in
     `docs/engineering/MAIN-BASELINE.toml` (iron rule 9).
   - `vX.Y.Z-...` - a release milestone referenced by the READMEs.

   Per-commit and per-round snapshot tags are forbidden: on 2026-11-13 the repo
   had 134 tags of which 126 were noise, which makes the useful ones unfindable
   (user: "打了一堆tag 到底哪些有用的？没用的就删掉 后面也不要乱加 只加有用的").
   The rollback anchor for day-to-day work is the pushed commit (iron rule 2),
   not a tag - `python3 scripts/check-snapshot-tag.py --tag` now refuses to
   create anything unless the tree is clean and `MAIN-BASELINE.toml` lists HEAD
   with `state = "booted"`.

8. **A boot without the serial console is a blind experiment.** Every
   `fastboot boot` must run with the CDC-ACM capture already attached, before
   the boot starts - not after. The console is `VID_1209&PID_0001`, it binds
   `usbser.sys`, and its COM number exists only under
   `HKLM\HARDWARE\DEVICEMAP\SERIALCOMM` as `\Device\USBSER000`; picking a port by
   FriendlyName silently selects a Bluetooth modem instead. DTR must be raised or
   the kernel never drains the console ring.

   `bash /mnt/e/k60-work/scripts/flash.sh <img> <secs>` does this unconditionally
   and reports whether the console ever appeared. `K60 console never appeared`
   is not a broken script: it is proof that the kernel died before USB gadget
   init, and the investigation must follow the early-boot path instead of
   guessing at UI symptoms. The full procedure, the evidence layout and the
   bisect recipe are in
   [`docs/engineering/BOOT-PROCEDURE.md`](docs/engineering/BOOT-PROCEDURE.md);
   `scripts/check-boot-procedure.py` fails the run when the wrapper stops
   attaching the capture.

   This rule exists because a boot hung early on 2026-11-12 and left no log at
   all - the failure was diagnosed by guessing ("maybe it cannot find the unixnu
   partition") instead of reading it. Anything that depends on being remembered
   is not a process.

The check before every build: `git status --porcelain` is empty on the source
tree, the branch is level with its remote, and
`python3 scripts/sync-device-input.py --check` reports no drift. The gates below
then run automatically and must all pass.

## Gates

`python3 scripts/check-rules.py` is the registry: it runs every check below and
also fails when an iron rule or a new pitfall has no check registered at all.
The list itself lives in `docs/engineering/RULES.toml`, so a rule that is only
prose is a red build, not a wish.

| Gate | Command | Checks |
|---|---|---|
| Registry | `python3 scripts/check-rules.py` | Every iron rule and every pitfall after P-151 has an executable check or a written waiver |
| Temp artefacts | `python3 scripts/check-tmp-artifacts.py` | No `/tmp` path is read as a durable source without an entry in `docs/engineering/TMP-ALLOWLIST.toml` (iron rule 1) |
| Tree clean | `python3 scripts/check-tree-clean.py` | No tracked file is modified but uncommitted, and `HEAD` is not behind its upstream (iron rule 2) |
| Data identity | `python3 scripts/check-data-identity.py` | The compiled Data volume UUID exists in the newest console log, and the UFS size ceiling covers the real window (P-152, P-153) |
| Patch budget | `python3 scripts/check-patch-series.py` | The net line delta every series patch applies to `bsd/kern/kern_exec.c` still matches the recorded baseline (P-155) |
| Pick shrink | `python3 scripts/check-pick-shrink.py` | A file-level upstream pick cannot silently replace a larger local file (P-151) |
| Research | `python3 scripts/research-gate.py` | Every source in `docs/research/SOURCES.toml` has `examined` plus a written `finding` |
| Eight-step | `python3 scripts/eight-step-gate.py --build` / `--flash` | ①–⑥ for build, ①–⑦ plus the ⑧ prediction for flash |
| Porting | `python3 scripts/porting-gate.py --quick` | `porting.toml` matches the official schema; the README table matches the data |
| Docs | `python3 scripts/check-docs.py` | Link integrity, INDEX coverage, root-doc links, section order, bilingual |
| Scope freeze | `python3 scripts/check-scope-freeze.py` | Nothing under a frozen path in `docs/SCOPE-FREEZE.toml` changed since its baseline; frozen areas warn instead of fail |
| DT asserts | `python3 scripts/check-dt-asserts.py` | Every `property(entry,"X",...)` a driver patch reads exists in `dts/mondrian.dts`; a missing one means the driver returns false and its diagnostics never run (P-147) |
| Input sync | `python3 scripts/sync-device-input.py --check` | The build input matches the repository; nothing exists in only one of them (iron rule 5) |
| Boot procedure | `python3 scripts/check-boot-procedure.py` | Every boot captures the serial console first and never `fastboot flash`es a partition (iron rule 8) |

`scripts/porting-gate.py` hosts sections `[T]` (docs), `[R]` (porting schema),
`[Q]` (patch structure), `[P]` (protocol assertion) and `[S]` (series fingerprint).

## Required reading

| Task | Required reading |
|---|---|
| **Everything** | [`README.md`](README.md) → [`docs/engineering/STATUS.md`](docs/engineering/STATUS.md) → [`docs/engineering/EIGHT-STEP-SPEC.md`](docs/engineering/EIGHT-STEP-SPEC.md) |
| Every port | [Porting](https://unixnu.com/zh/porting/), [device repository](https://unixnu.com/zh/porting/device-repository), [component catalog](https://unixnu.com/zh/reference/components), [porting records](https://unixnu.com/zh/porting/records) |
| Bring-up order | [Bring-up order](https://unixnu.com/zh/porting/bring-up) |
| Touch | [Input](https://unixnu.com/zh/porting/input) plus [`docs/engineering/K60-TOUCH-CHECKLIST.md`](docs/engineering/K60-TOUCH-CHECKLIST.md) and [`docs/engineering/TOUCH-STATEMACHINE.md`](docs/engineering/TOUCH-STATEMACHINE.md) |
| GPU | [GPU and Metal](https://unixnu.com/zh/porting/gpu) plus [`docs/plans/GPU-ENABLE-PLAN.md`](docs/plans/GPU-ENABLE-PLAN.md) |
| Kernel | [XNU source and patches](https://unixnu.com/zh/xnu/source-and-patches), `patches/xnu/series` |
| Images | [Prelink](https://unixnu.com/zh/concepts/prelink), [payload](https://unixnu.com/zh/concepts/payload), [UEFI firmware](https://unixnu.com/zh/porting/uefi-firmware) |
| Prior art | [`docs/audits/FORK-REVIEW.md`](docs/audits/FORK-REVIEW.md), [`CREDITS.md`](CREDITS.md) |
| Pitfalls | [`docs/engineering/PITFALLS.md`](docs/engineering/PITFALLS.md), [`docs/engineering/HARD-RULES.md`](docs/engineering/HARD-RULES.md) |

## Research before writing code

0. **Local patches first.** `patches/xnu/` carries 245 patch files with 211
   entries in `series`. Before adding a patch, read what the series already does
   — a problem being solved "new" may already carry a proven answer, or a
   constraint that explains why the obvious fix is wrong.

1. **Official component catalog.** See iron rule 4. Record for each candidate
   whether it can be used as-is, adapted, or why not.

2. **Same-SoC sibling ports.** The priority order is fixed: same model → same
   SoC → same peripheral chip → official generic driver.
   - `Seanding1998/hakios-xnu-kernel` (`phk110-port`) — OnePlus Ace 2, SM8475.
     `docs/phk110/waves/wave12c-electrical.md` documents the touch PASS in full
     (20 ms cadence, chunk harvesting); `wave20-launchd.md` documents the
     `hw.target` root cause. **Read these before touching touch or launchd.**
   - `yibiya/UniXNU-mondrian` — fork carrying the UI library, the launchd cache
     and the `fix/touch-gpu-bringup` touch/GPU line.
   - `XTOM0706/ios-sweet-k60` — HackiOS iOS 16 userland precedents.
   - `Chengdong-Yu/UniXNU-pong` and its `pong-*` submodules — the original Pong
     port.

3. **Sync before quoting.** `bash scripts/k60-sync-refs.sh` fetches every
   reference repository. Never quote code from a repository you have not fetched.
   For upstream forks, `python3 scripts/track-upstream-branches.py` reports every
   branch and every new commit; a single-branch refspec silently hides work.

4. **Record the finding before coding**: repository, branch, file:line, whether
   it fits this board, licence status, and the reuse/adapt/build decision.

5. **Licence rule**: hardware facts and register maps are free to reference;
   code, patches and scripts need a licence. A repository without a licence keeps
   all rights — read the idea, write your own.

## Branches and commits

- One branch per change: `feat/<topic>`, `fix/<topic>`, `refactor/<topic>`,
  `docs/<topic>`, `chore/<topic>`, `perf/<topic>`, `wip/<topic>`.
- A branch merges into `main` only after the change is verified and the record
  updated.
- **Commit messages are in English**: `type(scope): lowercase summary`, no
  trailing period. Example: `fix(cpu): the SM8475 cluster count is three`.
- Submit code and documentation as separate commits.
- Do not rewrite published history.
- **When importing code from another repository, preserve attribution**: use
  `git cherry-pick -x <sha>`; if you copy by hand, add
  `Co-authored-by: Name <email>` to the commit message. Otherwise GitHub's
  contributor graph credits the wrong person. See `CREDITS.md` and P-130.

## Device rules

- Probe the device before acting: `bash scripts/k60-device.sh state` reports
  `adb`, `fastboot` or `none`, and performs the matching transition (`android`,
  `bootloader`, `boot <image>`). Do not ask for a manual power cycle while a
  software path exists.
- Only `fastboot boot`. Never `fastboot flash` an Android partition. `persist`
  holds the KeyMint database and a rollback destroys every key.
- After every boot, update `porting.toml` and keep
  `python3 scripts/check-porting-paths.py --quiet` at zero errors.
- Completion levels follow the criteria in
  [`docs/engineering/EIGHT-STEP-SPEC.md`](docs/engineering/EIGHT-STEP-SPEC.md),
  not the fact that hardware was touched. `implemented` is not `device-verified`.
- Record the device observation, the command, the full 40-character revision and
  the result.

## Reading a failure

The board has no serial console; the screen and the USB log are the evidence.

| Segment | Symptom | Evidence |
|---|---|---|
| Before UEFI | black screen, no UniXNU trace | boot image header, firmware base and size |
| Inside UEFI | menu or entry dies | Tools → Advanced Logger |
| Inside DarwinBoot | loader progress line stops | last drawn line, refusal message |
| Inside XNU | scroll starts then dies | last lines, panic screen, `boot-progress` page |

**A zero-byte log is not a hang.** Check that boot-args carry `debug=0x140` and
`applog=1` before concluding anything (P-118).

## Commands

Run from the UniXNU checkout:

```sh
./unixnu defconfig mondrian_defconfig --device ../UniXNU-mondrian
./unixnu fetch --device ../UniXNU-mondrian
./unixnu status --device ../UniXNU-mondrian --json
./unixnu build kernel --device ../UniXNU-mondrian
```

Device state, boot and log capture:

```sh
bash scripts/k60-device.sh state
bash scripts/k60-device.sh boot <image>
```

## Calling WSL from the host shell

`wsl.exe` rebuilds its command line from argv, so quotes around a
`bash -lc "..."` payload are lost and semicolons become outer-shell separators.
Two safe forms:

```sh
# a script on the Windows side, fed on stdin
wsl.exe -d Ubuntu-24.04 -- bash -s < /c/Users/Emilelu/AppData/Local/Temp/step.sh

# a script inside WSL, with MSYS path conversion turned off
MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu-24.04 -- bash /tmp/step.sh
```

Anything longer than one line belongs in a script file.

## Porting record

Read `porting.toml` and the
[record guide](https://unixnu.com/zh/porting/records) before implementation.
Update each affected area's findings or evidence with its code change. The record
uses schema version 1 and needs 14 areas; every `evidence` element must be a table
with `kind`, `reference` and `result` — a bare string makes the site renderer fail
with `'str' object has no attribute 'get'` (P-128).

```sh
python3 scripts/check-porting-paths.py --quiet
python3 scripts/porting-gate.py --quick
```

## Reference repositories

`scripts/k60-sync-refs.sh` covers the reference trees. `CREDITS.md` lists every
external source and what was taken from it. `docs/audits/FORK-REVIEW.md` records
their branches and the reasoning behind every adopted change.

### 铁则 9 — main 只放可启动基线，实验走分支

`main` 是**稳定可启动基线**，不是工作区。任何未经过上机验证的改动（内核补丁序列、
构建脚本、`board.toml`/configs、`drivers/` 源码）都必须先落在分支上：

- 分支命名沿用上游习惯：`feat/…`、`fix/…`、`test/…`、`chore/…`
- 合回 `main` 的条件：`BUILD OK` **且**上机通过（八步流程 ⑧），或该条目在
  `docs/engineering/MAIN-BASELINE.toml` 里显式登记为 `build-only` 并写明欠账
- 每个落在 `main` 的提交必须在 `MAIN-BASELINE.toml` 登记，且只有「上机验证过」或「main 基线」两种状态才打 tag（铁则 7），并在
  `MAIN-BASELINE.toml` 登记：`sha`、`tag`、`kernel_sha256`、`state`
- 门禁：`scripts/check-main-baseline.py`（注册为 `iron-9`）

违反实例（本次自查）：`bf487cc`、`c2fa573`、`234574a`、`d1843c2`、`20ce047`、
`8206fb4` 直接把补丁序列与驱动源码的改动提交到 `main`，其中多轮只做到 `BUILD OK`，
没有一次上机。见 P-174。
