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

7. **Tags mark proven states, not progress.** Only four kinds are allowed:
   - `boot-proven-YYYYMMDD` - an image from this commit reached SpringBoard;
     the tag message carries its path, size, sha256 and the console log.
   - `snap-rN` - the commit registered as the `main` baseline in
     `docs/engineering/MAIN-BASELINE.toml` (iron rule 9).
   - `vX.Y.Z-...` - a release milestone referenced by the READMEs.
   - a **release asset tag** - any tag whose name appears in a
     `releases/download/<tag>/` URL under `.github/workflows/`. Deleting one
     turns its release into a draft and breaks the workflow that fetches it, so
     the gate reads the set out of the files instead of carrying a list (P-252).

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

### Iron rule 9 — `main` carries only registered baselines, and only the Lead writes to the device

   **The Lead owns the device; nobody else boots it.** The user settled this twice:
   on 2026-11-18 the device became first-come-first-served, and on 2026-11-20 it
   went back to a single owner — "手机的上机权限完全由你管理调度 其他agent不允许
   私自上机", with "你每次boot不用问我". So the Lead boots whenever the evidence
   says it is time, and a lane that wants a flight asks for a slot instead of
   taking the cable. This is not a formality: two agents booting at once leave the
   loser's capture attached to a device that already runs a different image, which
   produces evidence that looks real and is wrong.

   The lock is still enforced, because it is what makes a capture attributable.
   `scripts/k60-boot-lock.ps1` takes the claim with an exclusive
   `FileShare.None` handle, and `scripts/boot-and-capture.ps1` acquires it before
   it touches the device — including before `adb reboot bootloader`, which it does
   itself under the claim (`-RebootToFastboot`) — and releases it in `finally`.
   `scripts/flash.sh` neither probes nor reboots: it only requires
   `K60_AGENT_ID` and hands the reboot to the supervisor, because a shell
   `flock` probe lives in a different lock domain and always looks free while the
   Windows handle is held. `K60_AGENT_ID` is mandatory so the claim is
   attributable, and the owner is written to
   `E:\k60-work\state\k60-device-boot.lock.owner.json`. Refused competitors
   exit 6; a missing actor exits 7. The properties are executed by
   `python3 scripts/tests/test-boot-lock.py`.

   **A baseline is one of two states, and both are registered.** `state = "booted"`
   needs the console evidence; `state = "build-only"` needs the reason it was not
   flown. `main` currently builds the iOS 27 stage-0 board (see `board.toml`), which
   stops at `bsd_init` on purpose, so the 16.6.1 board is the one with the boot
   evidence and it stays reachable with `--os ipados-16.6.1-20G81`.

The check before every build: `git status --porcelain` is empty on the source
tree, the branch is level with its remote, and
`python3 scripts/sync-device-input.py --check` reports no drift. The gates below
then run automatically and must all pass.

**Space is part of the check.** `hard-41` (`scripts/check-disk-space.py`) refuses
to build when a filesystem is below its blocking line, but it only measures what
is left — it never reclaims. Every experiment that writes a new `K60_OUT` needs a
deleter, and that is `python3 scripts/k60-janitor.py --apply` (dry run without
`--apply`; keep the newest two outputs of each prefix, never touch a `/tmp`
symlink or the tree one points at, never touch a mirror). On 2026-11-19 the
virtual disk reached 181.8 GB this way: twenty-five stale
`power-conformance-battery-*` outputs (47.6 GB) plus 18.3 GB of old `/tmp`
entries, while every gate stayed green. See `docs/engineering/DISK-HYGIENE.md`
§2.5 and P-246.

## Gates

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

### Iron rule 12 — an agent message tries `steer` first

Every message to another agent is sent with `steer`; `followup` is the fallback
for the one case where `steer` cannot work, which is a session that is not
running (`steer` and `inject` only reach a live turn, `followup` queues a new
one). Send `steer`, and only if it is rejected because the target is idle, send
the same content as `followup`. Never open with `followup`, and never send both
when the `steer` succeeded — a queued duplicate lands after the agent has already
acted on the first copy and reads as a second, contradictory instruction.

Why: on 2026-11-20 four lanes were working from instructions the Lead had
already replaced. The replacements went out as `followup`, sat in the queue
behind each agent's current round, and arrived after the work they were meant to
redirect. `steer` interrupts at the nearest step boundary, which is the only
delivery mode that can stop an agent from spending an hour on an abandoned plan.
Check with `python3 scripts/check-agent-messaging.py` (registered as `iron-12`);
it reads this heading, the `RULES.toml` entry, and the message log — and says so
when the log records no delivery mode, because an absent record is not evidence
that `steer` was tried (P-251).

### Iron rule 13 - every official documentation page is a requirement

`E:/hackios/UniXNU/docs/zh` is the contract we port against. Every page except
`devices/` has an entry in `docs/engineering/OFFICIAL-REQUIREMENTS.toml` with the
page's sha256, a state (`mapped`, `unmapped`, `na`) and, when mapped, the gate
that enforces it. `scripts/check-official-docs.py` fails on a page with no entry,
an entry with no page, a changed sha256, a mapped entry whose gate does not
exist, and an `na` without a reason. Unmapped pages are printed as debt.

### Iron rule 14 - no flight before steps 1-7 each carry their evidence

`scripts/eight-step-gate.py --flash` already refuses a flight until every active
hardware item has steps 1-7 with evidence and a declared `prediction.success` /
`prediction.failure`. This rule states it as policy: one flight buys one answer,
so the criterion is written before the image is built, never after.

### Iron rule 15 - reference and UniXNU repositories are fetched on schedule

`docs/engineering/UPSTREAM-REPOS.toml` lists every clone that feeds porting work
(the Sheng line, the same-SoC t970 and zizhan lines, the framework, the feeds).
`scripts/check-upstream-sync.py --apply` fetches them and records the time and
heads; the gate fails when a fetch is older than the limit, when a recorded head
moved, when a read-only clone is behind the upstream it follows, and when the
official device pages gained an entry naming this SoC. Two days of stale clones
is how the xNekom branch and 622 upstream commits were missed.


### Iron rule 16 - a blocked problem starts with the references, not with a design

Before writing code for a blocker, read what the registered reference sources do about
*that* blocker, and record the readings in `docs/engineering/IOS27-REFERENCE-FIRST.toml`
(source, path, line, what it does, and whether we copied, adapted or rejected it).
`scripts/check-reference-first.py` fails while any open flight blocker has fewer than two
resolvable readings, and it fails again the moment a recorded line stops resolving.

The rule exists because the same mistake kept being paid for: 2026-11-20 spent a day
concluding "the loader cannot take a fileset" while the official pin beside us already
accepted one, and 2026-11-21 nearly repeated it on the prelink residue until the upstream
`prelink-regression.json` showed a booting device living with `missing 2 / stubbed 24`.

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
