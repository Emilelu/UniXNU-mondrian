# Agent instructions

This repository owns the Redmi K60 (mondrian, SM8475) device configuration:
peripherals, firmware selection, partition layout, power policy and packaging.
Shared SM8475 resources live in `UniXNU-sm8475-common`, the loader in
`uefi-mondrian`, and the build driver, the documentation site and the component
catalog in `UniXNU`.

**`feat/ios27` targets iOS 27.0.1 (24A446) as an iPhone 16 Pro Max (iPhone17,2),
arm64e, on xnu-12377 with the Darwin 26 calls.** `main` remains the iOS 16.6.1
(20G81) / darwin22 port; the darwin24 route is retired and archived on
`chore/archive-darwin24-main-20261103`. Read `docs/engineering/IOS27.md` before
changing this branch: the profile, the inputs and the phase gates are there.
`porting.toml` is the authoritative device state, and every subsystem change
updates the record in the same pull request.

## Commands

```sh
# build driver, from the UniXNU checkout; --device is mandatory everywhere
./unixnu defconfig mondrian_defconfig --device ../UniXNU-mondrian
./unixnu fetch   --device ../UniXNU-mondrian
./unixnu status  --device ../UniXNU-mondrian --json
./unixnu build kernel --device ../UniXNU-mondrian

bash scripts/k60-device.sh state          # adb | fastboot | none
bash scripts/k60-device.sh boot <image>   # never flashes
```

Every gate: `python3 scripts/check-rules.py` (the list is
`docs/engineering/RULES.toml`; it fails when an iron rule or a pitfall after
P-151 has no executable check or written waiver). Before a build: clean
`git status --porcelain`, branch level with its remote,
`python3 scripts/sync-device-input.py --check` reporting no drift.

## Iron rules

1. **Nothing durable lives in `/tmp`.** Patches, `series` entries, build
   scripts, notes and any generated artefact a result refers to belong in the
   repository or under the workspace. `/tmp` is wiped without warning: a
   cleanup on 2026-11-07 took a day of kernel patches with it.

2. **Source is tracked and pushed before the next step.** A patch, script or
   document is finished when it is committed and pushed, not when it is
   written. `git status` must not carry source changes across a build, and a
   build tree must never be the only copy of a patch.

3. **Follow the eight-step process; no flashing without step ⑦.** Same model →
   official → reverse engineering → wide search → plan → deep dive → local
   verification → on device. Definitions and pass conditions live in
   `docs/engineering/EIGHT-STEP-SPEC.md`. Step ⑦ needs all three of a static
   check, an offline unit test and an artefact check; "it compiles" is not
   verification.

4. **Check the official component catalog before writing a driver.** Read
   `UniXNU/components.toml` and the
   [driver repository list](https://unixnu.com/zh/drivers/repositories) first.
   Reimplementing an existing wheel is a defect, not initiative: the catalog
   already carries `QcomGeniSpi`, `AdrenoMetal` and `Adreno740`, and
   equivalents had been hand-written before someone looked.

5. **The repository is the only source of truth; the build input is its
   mirror.** `E:\hackios\UniXNU-mondrian` and
   `/opt/k60/trees/usb-cdc-mainline/device` hold the same files, and copying
   runs one way only: repository → build input, through
   `scripts/sync-device-input.py`. Editing under `/opt` is lost on the next
   clone, and a file in only one of the two is invisible to whoever reads the
   other.
   - **`git reset --hard` before `git status` is data loss.** Uncommitted work
     does not survive it and nothing warns. Commit or stash first.
   - **`git pull --rebase` replays every commit after the reset point**, so a
     local revert is an opinion until it is pushed.
   - **Scratch is for drafts, not deliverables.** A script that passes a check
     belongs in `scripts/` in the same turn.

6. **Following upstream means judging every commit, not reporting that one
   exists.** `scripts/track-upstream-branches.py` says what changed; each
   branch carries a watermark in `docs/research/UPSTREAM-TRIAGE.toml` and every
   commit past it gets a verdict - `picked` (with how), `not-applicable` (with
   why) or `deferred` (with why and a date to look again);
   `scripts/check-upstream-triage.py` fails while anything is unjudged. The
   default verdict is `picked`: a commit earns `not-applicable` only by being
   documentation, and `deferred` only by physically not applying to our tree.
   Where the divergence is too broad for cherry-picking, rebase onto the
   upstream branch and re-apply our additions on top.

7. **Tags mark proven states, not progress.** Only three kinds are allowed:
   - `boot-proven-YYYYMMDD` - an image from this commit reached SpringBoard;
     the tag message carries its path, size, sha256 and the console log.
   - `snap-rN` - the commit registered as the `main` baseline in
     `docs/engineering/MAIN-BASELINE.toml` (iron rule 9).
   - `vX.Y.Z-...` - a release milestone referenced by the READMEs.

   The rollback anchor for daily work is the pushed commit, not a tag;
   `scripts/check-snapshot-tag.py` refuses to create anything unless the tree
   is clean and `MAIN-BASELINE.toml` lists HEAD with `state = "booted"`.

8. **A boot without the serial console is a blind experiment.** Every
   `fastboot boot` runs with the CDC-ACM capture attached **before** the boot
   starts. The console is `VID_1209&PID_0001`, it binds `usbser.sys`, and its
   COM number exists only under `HKLM\HARDWARE\DEVICEMAP\SERIALCOMM` as
   `\Device\USBSER000`; picking a port by FriendlyName silently selects a
   Bluetooth modem. DTR must be raised or the kernel never drains the console
   ring. `bash /mnt/e/k60-work/scripts/flash.sh <img> <secs>` does this
   unconditionally and reports whether the console ever appeared;
   `scripts/check-boot-procedure.py` fails the run when the wrapper stops
   attaching the capture. "K60 console never appeared" is evidence that the
   kernel died before USB gadget init - investigate the early-boot path, do
   not guess at UI symptoms. Procedure, evidence layout and bisect recipe:
   `docs/engineering/BOOT-PROCEDURE.md`.

### Iron rule 9 — `main` carries only bootable baselines, experiments go on a branch

`main` is the stable bootable baseline, not a workbench. Any change not yet
verified on the device (kernel patch series, build scripts, `board.toml`,
configs, `drivers/` sources) lands on a branch (`feat/`, `fix/`, `test/`,
`chore/`). A merge back to `main` requires `BUILD OK` **and** an on-device pass
(step ⑧), or an explicit `build-only` entry with its debt written down in
`docs/engineering/MAIN-BASELINE.toml`. Every commit that lands on `main` is
registered there with `sha`, `tag`, `kernel_sha256` and `state`. Gate:
`scripts/check-main-baseline.py` (registered as `iron-9`). Already violated by
`bf487cc`, `c2fa573`, `234574a`, `d1843c2`, `20ce047` and `8206fb4` - several
reached only `BUILD OK` (P-174).

### Iron rule 10 — the environment stays out of the repository

Addresses and passwords of external machines (a LAN Mac, a build server, a
router) are not part of the project: the repository is public and history is
permanent, so one push publishes the whole history and deleting the file later
cannot recall the clones. Documents carry placeholders only
(`<user>@<mac-host>`, `sshpass -p <password>`, `<local-dir>`); real values live
outside the repository (`E:\k60-work\` or `~/.k60-env`) and are `source`d,
never written into `docs/`, `scripts/` or `board.toml`. Check before committing:
`python3 scripts/check-secrets.py` (registered as `iron-10`). Already violated
once: the ★7 probe command reached public history in `2e44f46`.

### Iron rule 11 — one checkout, one owner

One checkout has exactly one owner, registered in
`docs/engineering/TREE-OWNERS.toml`; the Lead uses `E:/hackios/k60-lead`
(a `git worktree`) and never writes the shared tree. Destructive commands
(`checkout -- <path>`, `restore`, `reset --hard`, `clean -f`, `stash`) go
through `scripts/git-safe.sh`: it snapshots first
(`scripts/snapshot-worktree.py` → `E:/k60-work/scratch/snapshots/<stamp>-<tree>/`
with `tracked.patch`, `staged.patch`, `untracked/` and `restore.sh`), then
refuses on a tree you do not own unless `K60_I_OWN_THIS_TREE=1` is set. A build
that needs a clean tree gets its own worktree or a narrowed gate scope
(`K60_EIGHT_STEP_ITEMS`), never a cleanup of the shared one. Run
`python3 scripts/check-tree-owner.py` before committing. Why: on 2026-11-14 a
Lead ran `git checkout -- <8 files>` in the shared checkout to turn a gate
green and destroyed the touch agent's work, seven files of it unrecoverable.

## Gotchas & landmines

- **This file is parsed.** `check-rules.py` collects iron rules from headings
  shaped `### 铁则 N` or `### Iron rule N` and requires each id in
  `RULES.toml`; it fails instead of passing vacuously when it finds none.
  `check-boot-procedure.py` greps `^8\. **...串口|console|serial`. Renaming or
  renumbering a heading still disables that item's coverage on its own, so the
  regex and the heading change in the same commit.
- **LF only.** An edit from Windows converts this file to CRLF and a 37-line
  change shows as 366 insertions and 366 deletions
  (`check-line-endings.py`, `--fix` rewrites).
- **A zero-byte log is not a hang.** Check `debug=0x140 applog=1` in boot-args
  before concluding anything (P-118).
- **`wsl.exe` rebuilds its command line from argv**, so quotes around a
  `bash -lc "..."` payload are lost and semicolons become outer-shell
  separators. Two safe forms - a script on the Windows side fed on stdin, or a
  script inside WSL with path conversion off:

  ```sh
  wsl.exe -d Ubuntu-24.04 -- bash -s < /c/Users/<user>/AppData/Local/Temp/step.sh
  MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu-24.04 -- bash /tmp/step.sh
  ```

  Anything longer than one line belongs in a script file.
- **`sync-device-input.py` refuses to run without `K60_DEVICE_INPUT`.** Export
  your own mirror; an unset variable once produced five false reds (P-184).
- **`check-data-identity.py` walks every `configs/*defconfig`**, not just
  `mondrian_defconfig`. The wifi board's own defconfig carried a seed volume
  UUID into a shipped build (P-210), and the UFS size ceiling is checked
  against the newest manifest, not the seed (P-152, P-153).
- **Only `fastboot boot`.** Never `fastboot flash` an Android partition:
  `persist` holds the KeyMint database and a rollback destroys every key.
- **Reports between agents travel through one scratch file per line**,
  `E:\k60-work\scratch\reply-<line>-<YYYYMMDD>.md` (adsp, audio, bt, cellular,
  display, refmine, springboard, thermal, usb, wifi). Bidirectional and
  overwrite-based: read a newer report before overwriting the file with the
  reply, announce in chat that the reply is written, and keep the payload in
  the file. Substantive findings still land in `docs/research/` before a line
  is done.

## Research before writing code

0. **Local patches first.** `patches/xnu/` carries 245 patch files with 211
   entries in `series`. The problem being solved "new" may already carry a
   proven answer, or a constraint explaining why the obvious fix is wrong.
1. **Official catalog**, as in iron rule 4: record per candidate whether it is
   usable as-is, adaptable, or why not.
2. **Same-SoC siblings**, in a fixed priority: same model → same SoC → same
   peripheral chip → official generic driver. Read
   `docs/phk110/waves/wave12c-electrical.md` (touch PASS) and
   `wave20-launchd.md` (`hw.target` root cause) in `Seanding1998/hakios-xnu-kernel`
   before touching touch or launchd; `yibiya/UniXNU-mondrian` carries the UI
   library, the launchd cache and the touch/GPU line.
3. **Sync before quoting.** `bash scripts/k60-sync-refs.sh` fetches every
   reference tree; never quote code from a repository you have not fetched.
   For upstream forks, `scripts/track-upstream-branches.py` reports every
   branch - a single-branch refspec silently hides work.
4. **Record the finding before coding**: repository, branch, file:line,
   whether it fits this board, licence status, and the reuse/adapt/build
   decision. `docs/research/SOURCES.toml` must be `examined` with a written
   `finding` (`scripts/research-gate.py`).
5. **Licence rule**: hardware facts and register maps are free to reference;
   code, patches and scripts need a licence. A repository without a licence
   keeps all rights - read the idea, write your own.

## Conventions

- One branch per change: `feat/`, `fix/`, `refactor/`, `docs/`, `chore/`,
  `perf/`, `wip/`. Merge to `main` only after verification and the record
  update.
- Commit messages are English, `type(scope): lowercase summary`, no trailing
  period. Code and documentation are separate commits. Do not rewrite
  published history.
- When importing code, preserve attribution: `git cherry-pick -x <sha>`, or
  `Co-authored-by: Name <email>` when copying by hand (P-130, `CREDITS.md`).
- `porting.toml` uses schema version 1 and needs 14 areas; every `evidence`
  element is a table with `kind`, `reference` and `result` - a bare string
  makes the site renderer fail with `'str' object has no attribute 'get'`
  (P-128). Check with `python3 scripts/check-porting-paths.py --quiet` and
  `python3 scripts/porting-gate.py --quick`.
- Probe the device before acting (`scripts/k60-device.sh state`); never ask for
  a power cycle while a software path exists. After every boot update
  `porting.toml`. Completion levels follow `EIGHT-STEP-SPEC.md`:
  `implemented` is not `device-verified`. Record the observation, the command,
  the full 40-character revision and the result.

### Documentation

The `.md` files are for the next reader, not for the session that wrote them. A
fact that only mattered while debugging is not documentation.

- **Edit in place, never append.** `STATUS.md` and `porting.toml` describe the
  current state; rewrite the section that changed and delete what it replaces.
  A new dated entry is justified only when the date itself carries meaning (a
  policy decision, the first boot of a subsystem).
- **Dates only, never times.** `2026-10-23`, not `2026-10-23 14:05 CEST`.
  Durations are fine ("about four minutes").
- **No session ephemera.** CI run ids, image or kernel hashes, byte sizes,
  `/tmp` paths, `adb`/`fastboot` transcripts, "waiting for the user" and
  narration of what you tried belong in neither a doc nor a commit. A number
  needed to reproduce something goes into `porting.toml` or `scripts/`, and the
  doc points there.
- **One home per fact.** Cross-link instead of repeating; when two files
  disagree, fix the wrong one rather than adding a third statement.
- **Every paragraph answers "what do I do with this?"** Keep measured values,
  invariants that break silently, symptom → cause → fix, and the command a
  newcomer needs. Drop reasoning that only justifies a decision already made.

## Reading a failure

The board has no serial console; the screen and the USB log are the evidence.

| Segment | Symptom | Evidence |
|---|---|---|
| Before UEFI | black screen, no UniXNU trace | boot image header, firmware base and size |
| Inside UEFI | menu or entry dies | Tools → Advanced Logger |
| Inside DarwinBoot | loader progress stops | last drawn line, refusal message |
| Inside XNU | scroll starts then dies | last lines, panic screen, `boot-progress` page |
