# K60 iOS Port — Pitfall Log (PITFALLS)

> **Purpose**: the pitfall log — **one of the authoritative sources for "what not to step in twice"**, numbered `P-NN`.
> **Who should read it**: one of the three documents every incoming agent must read; before doing anything, flip to the 30-second check column.
> **Boundary**: this volume collects pitfalls of the **current tree/process**; commit history and the per-round compilation live in `PITFALLS-FROM-HISTORY.md` (entry N), and the two volumes cross-reference each other without repeating the detail.
> Every entry has fixed fields: **symptom / trigger / why it went wrong / correct approach / evidence / the 30-second check next time**.
> Purpose: let the same pitfall cost at most one burn. New pitfalls are appended at the end, numbering continuous.
> The batch compilation of historical pitfalls is in `PITFALLS-FROM-HISTORY.md` (produced by another agent).

---

### P-01 arm64's 4 GiB pagezero: `[4K, 4MiB)` never contains anything

- **Symptom**: the kernel probe reads the low-address memory of a user process expecting to find an exception string, and everything comes back empty.
- **Trigger**: any forensic code that tries to `copyinmap` the low 4 MiB of a process address space.
- **Why it went wrong**: following x86/other-platform intuition, assuming "low address = program headers/heap start, so there is content there". arm64's pagezero is a full **4 GiB**, `[0, 4GiB)` is never mapped, the low 4 MiB falls inside it, and `copyinmap` fails everywhere.
- **Correct approach**: do not blind-scan the address space; read the exit_reason kcdata (`KCDATA_TYPE_PID` / `KCDATA_TYPE_PROCNAME` / `EXIT_REASON_USER_DESC`) — the exception text is attached by userland itself at abort/terminate time.
- **Evidence**: `xnu-work/bsd/kern/kern_exit.c` lines 162–168 comments (written after the measurement); D-2026-11-02-07.
- **30-second check**: any proposal to "scan `[0x1000, 0x400000)`" or "read the low 4 MiB" → reject it outright and point at this entry.

### P-02 STR probe (old address-scan version) measured all empty ✅ resolved: pagezero scan → kcdata approach works

- **Symptom**: `STR <pid> '<comm>' <text>` does not print a single line.
- **Trigger**: on-device forensics with the 4g-str candidate image.
- **Why it went wrong**: same as P-01, wrong range; the printing logic was not broken, the source could never be read.
- **Correct approach**: use the kcdata version (the new STR output carries the three fields `sender=` / `from=` / `desc=`, kernel from `64ae6488…` on).
- **Evidence**: ISSUES I-20261102-09; `logs/kernel-exit-summary.log`.
- **30-second check**: when the probe prints 0 lines, first ask "is the source address actually mapped on this platform", then suspect the code.
- **Closure (evening of 2026-11-02)**: the kcdata STR **has been verified on device** (user photo `IMG_0180.JPG`, boot image `6153c2aa…` / kernel `64ae6488…`): it successfully distinguishes suicide (`sender==own pid`, `from='<own name>'`, `sig=6`) from being killed (`from='exc_handler'`, `sig=5`). This entry is archived to prevent a repeat.

### P-03 `mcopy` interactive overwrite confirmation deadlocks the packaging flow

- **Symptom**: the packaging/file-extraction script runs halfway with no output at all and never returns.
- **Trigger**: the script does `mcopy -i payload.img ::/path dest` and dest already exists.
- **Why it went wrong**: mcopy confirms interactively before overwriting by default; in an unattended environment stdin has no input, so it waits forever.
- **Correct approach**: **always** pass `-o` (overwrite) on every mcopy call.
- **Evidence**: `tools/package-textonly.py` lines 33–34 all carry `-o` now; ISSUES I-20261102-04.
- **30-second check**: script hangs silently → `ps aux | grep mcopy`; a resident process means this pitfall; kill it and add `-o` to the command.

### P-04 A `\\n` escaping typo in the probe needle → the fake appearance of a count stuck at 0

- **Symptom**: `handoff-probes.py` reports "KX! dedup does not exist (count=0)", yet the change is clearly in the kernel.
- **Trigger**: the probe byte string contains a literal `\\n` (backslash+n, two characters), while what actually exists in the binary is the newline character `0x0A`.
- **Why it went wrong**: one extra level of escaping when copying a format string out of a shell/doc.
- **Correct approach**: the needle uses real bytes (`b'...\n'`); on a count of 0, **suspect the probe first, the kernel second**.
- **Evidence**: ISSUES I-20261102-11; fixed 2026-11-02 20:41, count=1 on the same kernel afterwards.
- **30-second check**: probe count=0 but the person who made the change is sure it compiled → print the needle's `repr()` and check for a literal backslash.

### P-05 "the string should appear N times" empirical assertion went stale (the count==2 event)

- **Symptom**: packaging verification/probes assert the occurrence count of a string from an old empirical value and report a false FAIL.
- **Trigger**: a kernel change altered the number of printf sites (KX! dedup merged two into one).
- **Why it went wrong**: "appears 2 times" was hardcoded as a permanently true fingerprint; it belongs to the previous kernel generation.
- **Correct approach**: count assertions must be updated together with the kernel change, and the comment must say **why that number** (`package-textonly.py` lines 38–42 already demonstrate it).
- **Evidence**: ISSUES I-20261102-10.
- **30-second check**: verification FAILs and the failing item is a count → run `count()` by hand on the current kernel.macho and update the script to the measured value; do not bend the kernel to fit the number.

### P-06 Forensic sheet/handoff quotes an old sha, mismatched attribution

- **Symptom**: the document says "current kernel sha X", but what was actually produced/booted is Y.
- **Trigger**: multiple rebuilds in one day; HANDOFF §4 was written at 19:30, followed by two more rebuild rounds (19:54's `65fbe51e…`, 20:42's `64ae6488…`).
- **Why it went wrong**: quoting sha from memory; not refreshing after the handoff was written.
- **Correct approach**: **always copy the sha from `candidates/<dir>/build-verification.json` on the spot**; cross-check documents against DECISIONS' "image identity chain" table; refresh INDEX before a handoff (a hard requirement of RECORDING-RULES).
- **Evidence**: ISSUES I-20261102-05; three places in `logs/boot-attempt-20261102-200610.log` agree on the sha (snapshot/source/expected).
- **30-second check**: before quoting any sha → open the corresponding candidate directory's `build-verification.json`, never from memory.

### P-07 `desc='-'` in STR does not mean "there is no crash reason"

- **Symptom**: in the kcdata STR output `desc` is always `-`, easily misread as "log missing / probe read nothing / another probe is needed".
- **Trigger**: the crashing process killed itself **without going through** `abort_with_reason()` / `terminate_with_reason()` to attach a description (e.g. a direct `abort()`, or the NSException reason never reaching exit_reason).
- **Why it went wrong**: (registered preventively, not yet stepped in) the first reaction to `-` is to suspect the probe chain.
- **Correct approach**: `desc='-'` only says userland attached no reason (**silent crash**), it does not mean there is no reason; first look at `from=` / `sender=` to separate "suicide" from "killed", then decide the next forensic direction.
- **Evidence**: the evening of 2026-11-02, user photo `IMG_0180.JPG` (boot image `6153c2aa…` / kernel `64ae6488…`): subproblem A (`accountsd`/`dad`/`aggregated`/`ScreenTimeAgent`) had desc always `-`, but `from='<own name>'` was already enough to complete the suicide/killed classification (ISSUES I-20261102-01).
- **30-second check**: `desc='-'` and `from='<own name>'` → silent crash, not a probe problem; `from='exc_handler'` → killed, go look at the intermediary (I-20261102-13).

---

### P-08 The K60 screen's punch-hole cuts long lines: a "truncated string" in a screen photo is not data evidence

- **Symptom**: in a screen photo a long string in some line is "missing 3–5 characters" in the middle, looking like malformed data (the exec path on the `KE` line was once misread as `/usr/bin/[0]=?FDR_Loader`, and an investigation into "malformed paths" was started on that basis).
- **Trigger**: any long line of text that passes through the front camera punch-hole position.
- **Why it went wrong**: physical occlusion of the screen was taken as the real string content in kernel/userland, without first checking whether other lines on the same code path were intact.
- **Correct approach**: ① key long fields (paths, address strings, register values) **must be checked character by character by the user** before being treated as hard fact; ② new print design **prefers short lines** (split fields across lines, line width ≤ the visible width before the punch-hole), so that decisive evidence is never placed in a long line; ③ on "missing characters in the middle", suspect the punch-hole first, the data second.
- **Evidence**: 2026-11-03 argfix2 screen-photo review (the user verbally confirmed both "malformed" paths were punch-hole truncation); other long lines on the same screen were intact for comparison.
- **30-second check**: a screen-photo string is missing 3–5 characters in the middle and the missing position coincides with the punch-hole → always treat it as visual truncation, never as evidence of data integrity; reprint as short lines or have the user verify before starting a work item.

### P-09 Hex block number treated as decimal + large binaries over adb stdin: the incident where 1.19 MiB went to the wrong place in the OS window

- **Symptom**: dd landed in the wrong place when writing the Data window (1,327,499 bytes written to OS window 0x26510000), and the content was a distorted stream; the OS window digest mismatched.
- **Trigger**: manually treating `0x26110` as decimal block number 156944 (correct: `0x261100000/4096 = 0x261100 = 2494720`); transport over `adb shell` stdin (large stream breaks the pipe) and `adb exec-in` (Windows adb 37.0.1 processes stdin in text mode: a UTF-8 BOM `EF BB BF` is prepended to the file header, LF→CRLF).
- **Why it went wrong**: block number conversion was computed across bases by hand and the landing offset was not read back before writing; adb's stdin was assumed to be a binary channel (measured: two of the three distort, the only trustworthy one is the adb push file protocol).
- **Correct approach**: ① block numbers always come from `byte_offset/4096` computed directly inside the script and printed (no hand math, no intermediate values); ② before writing, always read the landing 4 KiB and compare with the expectation (including the reverse sanity "must not equal the source image header"); ③ large binary transfers use **adb push + device-side dd** only (verified complete for restore/20 GiB); ④ run a 64 MiB probe first (write + read-back sha) before the full volume; ⑤ after writing always do a full-window sha256 read-back (device side, UFS speed is free).
- **Evidence**: `archive/unixnu-rollback-20261103-0330/` (restore-seg.bin sha `5db74a2d…` written back, OS digest re-verified matching `bc4c5670…`, the incident entry in ROLLBACK.json); corruption analysis (BOM+CRLF, 138 differing bytes).
- **30-second check**: any hand-converted seek/count appears in a command → stop and print it with the script formula; any binary stream >1 MiB through `adb shell/exec-in` stdin → reject outright, switch to adb push.
- **Recovery closure (2026-11-03)**: rollback segment written back → segment sha matches → OS window digest re-verified against the manifest → Data window rewritten to the correct offset (readback `adbbf0dd…`) → manifest rewritten (`33626441…`).

### P-10 The XNU stage has no log channel at all; the screen photo is the only evidence source

- **Symptom**: analysis repeatedly assumes "there is a log on the device to read", "read the text source first"; screen-photo readings are used directly as high confidence, producing `0↔8`/`3↔8` (`abn=382` misread as 302), digit-count (7 `f`s read as 6) and other misreadings cited as evidence.
- **Trigger**: any forensic/reading step after XNU takes over.
- **Why it went wrong**: Android/Linux-side habits (dmesg/logcat/serial port) carried into the XNU stage — USB is entirely down once XNU takes over; the ramoops channel is cut immediately, DRAM does not survive a reboot and it belongs only to the loader/DXE side (I-20261103-02); the USB log channel (apps_smmu stream 0) is not yet working (I-20261103-04); serial COM3/COM4 are Bluetooth virtual ports that cannot read kernel output.
- **Correct approach**: the screen photo is the only evidence source → every reading is marked "screen-photo reading, low confidence", and [RECORDING-RULES.md](RECORDING-RULES.md) §7 is applied (triple consistency check, last digits of confusable pairs pending review, hex width check, crop and zoom, only yes/no questions to the user); it is forbidden to write "prefer reading text/logs" into a process, and forbidden to ask the user for XNU-stage logs.
- **Evidence**: ISSUES I-20261103-02 (ramoops settled), I-20261103-04 (USB channel not working); HANDOFF-2026-11-02 §6.6 ("screen does not scroll + take a photo" is the only forensic channel, D-2026-11-02-01); the user corrected on the spot on 2026-11-03 that "you cannot capture logs inside XNU". **2026-11-04 escalation, settled: ramoops is structurally unusable (lost on reboot, neither TWRP nor Android can read it) — authoritative entries D-2026-11-04-01 / I-20261104-01 / PITFALLS-FROM-HISTORY entry 16; this entry is not expanded further.**
- **30-second check**: any plan/report containing "read the log", "if there is a log", "look at the text source first", "read ramoops" → delete it, replace with "screen-photo reading, low confidence" and verify per RECORDING-RULES §7.

---


## mcopy (mtools) opens /dev/tty and asks for confirmation when overwriting an existing file, which shows up as a zero-I/O hang

- **Symptom**: `package-datafix.py`'s `mcopy -o -i payload.img ::/EFI/UniXNU/Payloads/kernel.macho extracted/kernel.macho` does not go through stdin when the target exists, it directly `open("/dev/tty")` and waits for manual confirmation; the process is in S state, `/proc/<pid>/io` shows no read or write growth, and the script hangs forever (the 13:05 round "interrupted after copying the payload" is this; 2026-11-03 v1 packaging reproduced it twice).
- **Why it went wrong**: `-o` (overwrite) was taken to mean "never asks"; in fact mtools may still confirm via `/dev/tty` for an "existing on-disk target", and redirecting stdin has no effect (it does not read stdin at all).
- **Correct approach**: before rerunning, `rm -f extracted/kernel.macho extracted/kernel.macho.adt extracted/unixnu.toml extracted/verify.adt`; and use `setsid python3 <workspace>\tools\package-datafix.py < /dev/null` (a new session has no controlling terminal, so `/dev/tty` cannot open and there is no wait). Judging a hang: `ls -l /proc/<mcopy_pid>/fd`, if fd 4 points at `/dev/tty` you are in it.
- **Evidence**: `/proc/388/fd` recorded fd 4 → `/dev/tty`, wchan=`wait_woken` (2026-11-03 14:27); `<workspace>\usb-a-stage\DIFF-AMFI-PRELINK.md` §5.1.
- **30-second check**: the packaging script contains `mcopy` and `extracted/` is non-empty → delete the target first and then run; packaging produces no artefact for 5 minutes → check whether an fd is on `/dev/tty`, if so kill and rerun per the correct approach.

---

### P-11 Ignoring a whole directory by mistake hits build dependencies: check whether scripts/ is a build input before tidying a "reference directory"

- **Symptom**: `unixnu build kernel` stops at `build-pong-platform-macos.py: [Errno 2] No such file or directory`; then a chain of missing `build-pong-adreno-platform.py` / `bind-ios16-storage.py` / `bindings.json` / GMU firmware, the same build blowing up four times in a row.
- **Trigger**: any action that "tidies repository directories, adds .gitignore entries, deletes a reference copy".
- **Why it went wrong**: all of `pong-driver/` was treated as a "reference copy" and added to `.gitignore` (one line `/pong-driver/`), but inside it `scripts/build-pong-*.py`, `bind-ios16-storage.py` and `shim-bin/` are the **build scripts** that `build-xnu-4k-baseline.sh` actually executes through `PONG_NATIVE_DRIVER_SOURCE` (board.toml `pong_native_driver_source` points at it); after the tidy-up the build chain broke. Also: the GMU firmware the adreno script needs, `--firmware-dir`, defaults to `/mnt/d/Android/k60-ios/firmware/k60-gpu` (the script says so itself after recovery), is not in the repository, and was lost along with the cleanup.
- **Correct approach**:
  1. **Before tidying any directory, check whether its `scripts/` is referenced by the build chain** (grep the build scripts, board.toml, CI workflows); anything that is a build input is never deleted and never ignored.
  2. **`.gitignore` may only ignore artefacts** (`*.a` / `*.o` / `*.log` / `build/` / `build-report.json`); **ignoring a whole directory that contains scripts is forbidden**; after the change `git check-ignore -v` must prove the scripts are no longer ignored.
  3. Restore dependencies from the deterministic object store first (`git ls-tree -r <commit> --name-only` to identify → `git checkout <commit> -- <path>`); do not scrape something together by searching.
- **Evidence**: v2 build, four consecutive failure logs (`logs/kernel-v2.log`); recovery commit `cafab71 fix(vendor): restore pong platform build scripts` (315cf99 → 7 scripts + bindings.json); `.gitignore` before and after the fix (`/pong-driver/` → 5 artefact rules) plus the `check-ignore -v` output; the firmware's real location `D:\Android\k60-ios\firmware\k60-gpu` (its 5 files byte-for-byte identical to the reverse-embedded bytes of the 13:55 build artefact `PongAdrenoFirmware.generated.c`).
- **30-second check**: before adding an ignore/delete for any directory → first `grep -rn 'directory-name' build-*.sh board.toml .github/workflows`; a hit means stop; whenever `.gitignore` contains a whole directory (not an artefact pattern like `*.a`) → reject it outright and fix per this entry.

---

### P-12 Sending an Explore subagent to do "full-text extraction" only returns fragments: core research documents must be read by the main agent itself

- **Symptom**: in the 2026-11-04 GAP research round, 3 Explore subagents were sent to closely read 4/25/9 references documents respectively and asked for structured reports; the returned results were only "Relevant Code Snippets" pointers (1-2 line-number excerpts per document), no extraction report, and the evidence granularity did not satisfy the research-driven requirement, forcing the main agent to re-read each document itself.
- **Trigger**: using Explore subagents for tasks of the "read N specified documents and give a detailed fact-extraction report" kind.
- **Why it went wrong**: Explore's role is "codebase concept search/location" (returning file+line snippets), not "digest multiple documents in full + write a report"; assigning a report-type task to it naturally produces only snippets.
- **Correct approach**: ① for close-reading tasks with a fixed file list, the main agent reads directly (small files batched in parallel); ② subagents are only for open-domain search (when you do not know which file holds the answer); ③ report-type tasks must use general-purpose rather than Explore, and the report length cap goes into the prompt.
- **Evidence**: GAP-TO-SPRINGBOARD.md research round record (2026-11-04); all 3 subagents returned snippets format.
- **30-second check**: a task for a subagent containing "read through these documents and report" → read them yourself instead; only "find where X is" goes to Explore.

---

### P-13 A "new file" section in a patch must carry the `@@ -0,0 +1,N @@ hunk` header, or git apply silently creates a 0-byte file

- **Symptom**: after `patches/xnu/0391-k60-embedded-init.patch` is applied the chain says "success", but `bsd/kern/k60_init_blob.h` is **0 bytes**; compilation reports `kern_exec.c:8096: use of undeclared identifier 'k60_init_blob'` / `'K60_INIT_BLOB_LEN'`. Four consecutive rounds misdiagnosed it as "patch ordering problem / dirty tree".
- **Trigger**: generating a `diff --git ... new file mode` section by hand/script with only `--- /dev/null` / `+++ b/path` and `+` content lines, omitting `@@ -0,0 +1,N @@`.
- **Why it went wrong**: `git apply` **does not report an error for a new-file section missing its hunk header**, treats it as "no content" and creates an empty file; `git apply --check` passes too, so "I checked it" was false security.
- **Correct approach**: after generating, verify twice: (1) `git apply --check`; (2) `stat -c%s <new file>` confirms **non-zero** and `head -2` shows the expected content. If the hunk header is missing, add `@@ -0,0 +1,<lines> @@`.
- **Evidence**: `scratch/HDR2.txt` (in-tree header `-rw-r--r-- 0 bytes`, while the patch's `+#define K60_INIT_BLOB_LEN` counts as 1 yet the file is empty); after the fix `scratch/TEST391.txt` (`git apply --check` OK, `header size 262784`); generator `scratch/gen391d.py`.
- **30-second check**: any change of the "add a file in a patch" kind → `stat -c%s` the new file immediately after applying; zero means this entry, no need to look at compile errors.

### P-14 `diff -u` against the golden script before editing a build script; deleting two `LD_KERNEL_ARCHIVES` lines makes the whole platform driver layer fail to link

- **Symptom**: the kernel boots but `panic: Unable to find driver for this platform: "J120AP". @IOPlatformExpert.cpp:2319`, and `strings kernel.macho | grep -c ArmDTPlatform` = **1** (golden is **38**).
- **Trigger**: editing `scripts/build-xnu-4k-baseline.sh` to "clean up the GPU injection", deleting
  `EXTRA_MAKE_ARGS+=("LD_KERNEL_ARCHIVES=$KERNEL_EXTRA_ARCHIVES")` and
  `EXTRA_MAKE_ARGS+=("LD_KERNEL_ARCHIVES=$PLATFORM_ARCHIVES")` together.
- **Why it went wrong**: seeing only that "injecting Adreno leaves `armcpu_spi_attach` undefined", the injection logic was deleted wholesale; these two lines are the **only transport channel for all platform archives**, not GPU-specific.
- **Correct approach**: before editing the script, `diff -u /opt/k60/trees/usb-cdc-mainline/out3/.../tree/scripts/build-xnu-4k-baseline.sh <this repo's script>`; after editing re-check that
  `grep -c 'LD_KERNEL_ARCHIVES'` must be = **2**, and after the build `strings kernel.macho | grep -c ArmDTPlatform` = **38**, `pong_cpu_startup_finished` = 2.
- **Evidence**: `scratch/SCRIPTDIFF2.txt` (the 2 removed lines are these two); `scratch/STRINGS.txt` (golden ArmDTPlatform=38 / ours=1 before the fix); `scratch/ARMIO.txt` (the personality table has `IOClass=ArmDTPlatform` but the driver has 0 symbols → falls through to `IOPanicPlatform`).
- **30-second check**: `Unable to find driver for this platform` in a panic → first count the `ArmDTPlatform` strings and the `LD_KERNEL_ARCHIVES` lines; if either number is wrong it is this entry.

### P-15 `cp -a` over an existing `tree/` makes unixnu skip the entire patch application (the `== kernel: patch` count in the log is 0)

- **Symptom**: inexplicable undefined symbols at link time (`_pong_cpu_startup_finished` etc.), while the patch files are clearly all in the series; `grep pong_cpu_startup_finished` in `IOCPU.cpp` = MISSING.
- **Trigger**: after `cp -a`-ing a previously successful build's `.cache/xnu-work` into a new out directory, running `unixnu build`.
- **Why it went wrong**: `tree/` was assumed to be just a source cache, but it is actually the "patches already applied" state marker; `unixnu` sees that `tree/` exists and skips unpacking + patching.
- **Correct approach**: to rebuild, **delete `tree/` and `build/` so unixnu unpacks from scratch**; or keep the tree but patch it by hand before building. After every build `grep -c '== kernel: patch' build.log` must be = **192**.
- **Evidence**: `scratch/FULLREBUILD.txt` (`D series: 192`, `patches applied: 192`); `scratch/COPYOUT.txt`/`FUNCDIFF.txt` (the round where the `== kernel: patch` count was 0); `scratch/IOCPU.txt` (`our IOCPU.cpp MISSING` / `golden :69` has the definition).
- **30-second check**: the build log's `grep -c '== kernel: patch'` is not 192 (or 191) → the tree state is wrong, do not go looking at symbols.

### P-16 Cleaning `tree/` deletes `.cache/fakeroot` and `.cache/sources` along with it: the SDK headers + DriverKit cache must be backfilled

- **Symptom**: `fatal error: 'Availability.h' file not found` (pulled in by `mach/arm/vm_types.h:76`); or `prepare-xnu-source.py` reports `HTTPError: HTTP Error 403: rate limit exceeded`.
- **Trigger**: `rm -rf tree` for a clean rebuild.
- **Why it went wrong**: `.cache/` was treated as disposable derived data; in fact `fakeroot` (containing `usr/include/Availability.h`) and `sources/xnu-driverkit-*.json` are **externally obtained** inputs that a rebuild does not restore automatically.
- **Correct approach**: back up before cleaning the tree, backfill immediately after:
  `cp -a <old tree>/.cache/fakeroot <new tree>/.cache/`;
  `cp -a <old tree>/.cache/sources <new tree>/.cache/` (`xnu-driverkit-10063.121.3.json` and 5 others).
- **Evidence**: `scratch/FIX403.txt` (`old sources caches` 5 jsons copied, `DriverKit: 36 files`); `scratch/FULLREBUILD.txt` (`headers: 16193` = `Availability.h`); `scratch/L1ERR.txt` (the 403 stack).
- **30-second check**: compilation reports `Availability.h` not found or `HTTPError 403` → go straight to whether `.cache/fakeroot/usr/include/Availability.h` and `.cache/sources/` are empty.

### P-17 The boot image layout produced by `unixnu bootimg` is wrong: `ksize` written as 1,027,600, payload lands at an offset UEFI cannot find

- **Symptom**: `fastboot boot` reports `Booting OKAY` but the device is **completely silent** (no CDC enumeration, no fastboot, no adb).
- **Trigger**: producing the image directly with `unixnu bootimg ... -o out.img`.
- **Why it went wrong**: assuming `bootimg` is the official image-producing step so it must be correct; in fact it puts the payload at an offset the header does not declare.
- **Correct approach**: splice using `boot-0461-20261107.img` as the template: keep the `[0,4096)` header (`u32@8 = kernel_size = 548,774`, `u32@16 = ramdisk_size = 0`), leave the `[4096,552960)` kernel region untouched, and replace the **payload starting at offset 552,960**.
- **Evidence**: `scratch/STRUCT.txt` (0461: ksize=548774 / 0602: ksize=1027600, rsize=0, `extra=201330688`); `scratch/SPLICE4.txt` (spliced 201,879,552, payload head byte-for-byte identical to 0461).
- **30-second check**: the new image's `u32@8` is not 548,774 → the layout is wrong, do not boot it.

### P-18 Kernel file writes must use `vnode_close(vp, 0, ctx)`; passing `FWRITE` triggers a `vnode_rele_ext kusecount` panic

- **Symptom**: `panic(cpu 0): vnode_rele_ext: vp ... kusecount(%d) out of balance with usecount(%d)` (`vfs_subr.c:2693-2694`), followed by a nested panic stall at `lock_mtx.c:194`. The log stops after `K60DATA attempt returned error=0 stage=4` and before the init helper.
- **Trigger**: picking the arguments yourself when newly writing "write a file" logic in the kernel (I used `vnode_close(vp, FWRITE, ctx)` + `IO_SYNC|IO_NOCACHE` + `NOCRED`, no resid).
- **Why it went wrong**: the name `FWRITE` makes "I am writing so I pass FWRITE" look natural; in fact `vnode_rele_internal` then decrements a `v_writecount` that was **never acquired**.
- **Correct approach**: copy the **already device-verified** form inside the repo, `patches/xnu/0340-k60-uilib-deploy.patch:7001-7013`:
  `vnode_open(path, O_CREAT|O_WRONLY|O_TRUNC, 0644, 0, &vp, ctx)` →
  `vn_rdwr(UIO_WRITE, vp, ..., 0, UIO_SYSSPACE, IO_SYNC, vfs_context_ucred(ctx), &resid, current_proc())` →
  **`vnode_close(vp, 0, ctx)`**.
- **Evidence**: `scratch/VNC0391.txt` (item-by-item diff of the 0340 original against 0391); `scratch/BUILD_FIX.txt` (after switching to the 0340 form, `CHECK OK / APPLIED`); `scratch/VERIFY_PB.txt` (afterwards `K60INIT: embedded helper write=0 resid=0`, `vnode_rele` count 0).
- **30-second check**: `grep -n 'vnode_close' <new patch>` shows `FWRITE` → change it per this entry, no need to investigate anything else.

### P-19 Do not build init by hand: `ld64.lld 18`'s `-static` is not implemented, the artefact is dynamically linked → `EXEC_EXIT_REASON_BAD_MACHO`

- **Symptom**: `initproc failed to start -- exit reason namespace 9 subcode 0x1`; `namespace 9 = OS_REASON_EXEC`, `code 0x1 = EXEC_EXIT_REASON_BAD_MACHO` (`reason.h:96,244`).
- **Trigger**: compiling the init stub in WSL with `clang -static -nostdlib ...`.
- **Why it went wrong**: `clang` only gave `warning: Option '-static' is not yet implemented`, the link "succeeded", but the artefact had `flags=0x200085` (including `DYLDLINK`) and carried `LC_LOAD_DYLINKER`, so the kernel's `load_machfile` judged BAD_MACHO. It was also misdiagnosed as AMFI refusing the signature (`namespace 9` is not CODESIGNING(3)).
- **Correct approach**: **do not build init yourself**. The on-device `/private/var/pong/init` is a ready-made static binary written by `write-pong-init-*.ps1` through four gates with dd (34,8xx B, already `/sbin/launchd` at source level).
- **Evidence**: `scratch/STUBFORM.txt` (`flags=0x200085 DYLDLINK=True LC_LOAD_DYLINKER`, `ld64.lld: warning: -static not yet implemented`); `scratch/PAGEZERO.txt` (against pong init `flags=0x1`, `__PAGEZERO 0x100000000`); `scratch/EXECCODE.txt` (`EXEC_EXIT_REASON_BAD_MACHO 1`).
- **30-second check**: panic `namespace 9 code 1` → go straight to `file <that init>`; `DYLDLINK` appearing means this entry.

### P-20 The golden image `boot-0461` already reached SpringBoard; the real blocker is launchd(PID 1) crashing, not missing kernel pieces

- **Symptom**: `boot-0461-20261107.img` was long treated as a "failed image", with several rounds spent "fixing so launchd comes up"; in fact that image **already enters the system**.
- **Trigger**: looking only at the tail of the crash, not at the SpringBoard loading sequence printed before it.
- **Why it went wrong**: the end of the `boot-0461` log is an `initproc exited` panic, easily taken as "it never got in"; in fact the earlier part of the same log has
  `Pong UI: 20G81 compatibility library entered SpringBoard` /
  `[SpringBoard] [backboardd] Pong UI: UIApplication -_run hooked`,
  and the crash happens after launchd reads `/System/Cryptexes/App/usr/libexec/webbookmarksd` (`errno 2`).
- **Correct approach**: judging "did it enter the system" requires looking at **both the early part** (SpringBoard/UIApplication lines) and **the late part** (`initproc exited`); the latter is launchd(PID 1) crashing, a consequence of `apply()` being missing so that the job set and the filesystem disagree.
- **Evidence**: `evidence/bootcap-20261107-212612/console.log` lines 1966/2055/2073 (SpringBoard Pong UI img), line 3550 (`webbookmarksd ... errno 2` + `KX! 18 1 launchd sig=11`), line 3555 (`initproc exited namespace 2 subcode 0xb`).
- **30-second check**: any judgement that "some image did not enter the system" → first `grep -ac 'SpringBoard\|UIApplication' <log>`; >0 means it did enter the system, so go look at the launchd crash instead.

---

### P-21 Identifying the init version must match on a "combination of log strings", never on the filename or a single marker

- **Symptom**: I wrote `init-v10guard` and then `init-v11drain` back to the device, assuming both times that "the baseline is restored", but the boot still failed; in fact the successful 11-07 run was **`init-v11drain`**, and `init-v10guard` lacks the `console drainer`.
- **Trigger**: relying on a single marker in the log such as `[v10guard]`, or comparing only by filename `init`/`init-v2`.
- **Why it went wrong**: `init-v11drain`'s banner still prints `HackiOS adapter [v10guard]` (the version name was carried over), so `[v10guard]` cannot distinguish v10guard from v11drain; and `init-v10guard` contains no `console drainer` string at all.
- **Correct approach**: decide from a **combination of two or more feature strings**:
  `alive, console ready` + `[v10guard]` + **`console drainer pid=%d`** + `var: write-check`
  → uniquely matches `init-v11drain` (34,912 B, sha `12b9df42cb76c2ffe21a1326215abe2021ad02ce332b9215e7c2b0fe1ac26b94`).
  After writing to disk both Gate3 (whole 36,864 sha `eceb785e…`) and Gate3b (bare 34,912 sha `12b9df42…`) must pass.
- **Evidence**: `scratch/V11CHK.txt` (all v11drain strings hit), `scratch/VER11.txt` (v10guard drainer=0 / v11drain drainer=2, 11-07 log drainer=1), the `scratch/WRITEV11.txt` walkthrough, the Gate3 PASS output of `scratch/writev11.ps1`.
- **30-second check**: to restore init → first `grep -a 'Pong init:' <11-07 log> | head -25` to collect all marker strings, then `strings | grep -c` each candidate under `deliverables/pong-init/init-v*` and intersect; only the unique hit is the target version.

### P-22 Same image, same kernel, same args yet dyld fails ⇒ check dyld shared cache visibility first, do not suspect init/kernel

- **Symptom**: `boot-0461-20261107.img` (sha `5df3a070…`, kernel `d56edb6f…`) went all the way to SpringBoard on the 11-07 21:26 boot; today, booting **the same file**, right after `KE 2 1 init /sbin/launchd` comes `dyld[1]: Library not loaded: /usr/lib/libSystem.B.dylib ... (no such file, no dyld cache)` and `KX! 1 1 launchd ... ns=6 code=0x1`.
- **Key comparison (must remember)**: the 11-07 log has `shared_region ... vm_shared_region_start_address() failed` **appearing twice as well** (:529/:539), yet **no dyld error at all**, and launchd then loads `/usr/lib/system/libdyld.dylib` from the cache (:977/:1179/:1482/:1972). The new log fails in dyld right after the same two shared_region lines (:563).
  ⇒ **those two shared_region lines are noise, not the criterion; the criterion is "is there a dyld error".**
- **Conclusion**: the difference is only **whether the dyld shared cache is visible**. `PATHS p0..p7` are `vnode_lookup` calls made in the panic exception context; the values are identical in both runs (`p0=0 p1=2 p2=2 p3=2 p4=2 p5=2 p6=0 p7=2`), and **they must not be treated as boot-time truth**; do not draw conclusions from them.
- **Correct approach**: ① add a probe **at boot time, before init** that prints the `vnode_lookup` result (panic-time probes are useless); ② or use `tools/apfs` against the OS/SystemOS image to confirm whether `System/Library/Caches/com.apple.dyld/dyld_shared_cache_arm64` really exists, then decide whether a copy must be added on the Data side and bindfs'ed to that path.
- **Evidence**: `scratch/CENSUS.txt` (old/new log dyld line comparison), `scratch/IMGKERNELS.txt` (the kernels of the 11-07 images all differ: 0458 `77a2ca32` / 0459 `62135cde` / 0460 `a00ea847` / 0461 `d56edb6f`; out3 is `78a0951a`, **none of them the same**), `scratch/KERNELSHA.txt`.
- **30-second check**: seeing `dyld[1]: Library not loaded ... no dyld cache` → go straight to dyld shared cache visibility; **do not** touch init, do not suspect boot args, do not look at `PATHS p*`.

---

### P-23 Same name, different object: `scratch/payload-0461.img` is not the payload inside `boot-0461-20261107.img`

- **Symptom**: I used `<workspace>/scratch/payload-0461.img` as the "golden payload" for packaging, but its `unixnu.toml` had only **16 args** (`debug=0x144`, no `k60_usblog=2`, no `k60_skip_firmware_mount=1`, no `amfi_get_out_of_my_way=1`), and it could not possibly have produced the 11-07 boot that has serial log output.
- **Root cause**: the filenames are both `payload-0461`, but `scratch/payload-0461.img` and the payload embedded in `boot-0461-20261107.img` are **not the same file** (the former is an intermediate product of another iteration that same day). Which args an image uses **can only be learned by extracting from that image**.
- **Correct approach**: get the payload from the image:
  `ksize=u32@8` → `off = 4096 + ceil(ksize/4096)*4096` → read 201,326,592 B → `mcopy -i <payload> ::/EFI/UniXNU/unixnu.toml`.
  `boot-0461-20261107.img`'s real args = **28 items**, containing `debug=0x140`, `k60_skip_firmware_mount=1`, `k60_tolerate_cache_loader=1`, `k60_usblog=2`, `amfi_get_out_of_my_way=1` — item for item identical to the `boot-args =` line in the 11-07 log (`scratch/FINDREAL2.txt`: MATCH=28/0).
- **Correction alongside**: the kernels of the 11-07 images all differ (0458 `77a2ca32`, 0459 `62135cde`, 0460 `a00ea847`, 0461 `d56edb6f`), and out3's `78a0951a` is none of them; **stop using "the out3 golden kernel" as the reproduction baseline**.
- **Evidence**: `scratch/PACKPROBE.txt` (16 args, a pile of MISSING), `scratch/PACKPROBE2.txt` (28 items all OK), `scratch/FINDREAL2.txt` (scanned 40 images, only the 0450–0461 series hits 28/0).
- **30-second check**: to confirm an image's args → **extract from that .img right now**, do not read `scratch/payload-*.img`; after extracting, count the args first, and stop immediately if it does not match the expectation.

---

### P-24 (= recurrence of historical pitfall 64-2) Swapping the kernel requires re-running `patch-armcpu-validate.py --apply`

- **Symptom**: `panic: "CPU configuration in device tree is invalid" @AppleARMCPU.cpp:111`, USB does not enumerate, no serial log, and no automatic reset either.
- **How it recurred (2026-11-08)**: I swapped the kernel directly with `mcopy -o -i payload ::/EFI/UniXNU/Payloads/kernel.macho <new kernel>`, **bypassing the `tree/scripts/patch-armcpu-validate.py --apply` that the payload step would have run**. This is not a new pitfall; `PITFALLS-FROM-HISTORY.md` entry 64 "pitfall 2" says it word for word.
- **Correct approach (four fixed steps on every kernel swap)**:
  1. `python3 <tree>/scripts/patch-armcpu-validate.py --check <kernel>` → if it prints `original bytes match` then `--apply` is mandatory;
  2. after `--apply` run `--check` again and expect **`already patched`**, and confirm the bytes `ff8304d1fc6f0ca9 → 20008052c0035fd6` (`mov w0,#1 ; ret`);
  3. after writing the payload do the **three-part self-check**: `header+kernel == template[0:552960]`, `ramdisk == payload` byte for byte, `trailer == template[201879552:]`;
  4. verify `ksize == 548774`, `ramdisk_size == 0`.
- **Evidence**: `scratch/ARMCPUFIX.txt` (the `--check` original text, `patched: mov w0,#1 ; ret`, `already patched`, all three self-checks True); historical entry `docs/PITFALLS-FROM-HISTORY.md:613` entry 64; `docs/references/USB-SERIAL-AND-AMFI-CHANNEL-20261105.md:28`.
- **30-second check**: seeing `AppleARMCPU.cpp:111` → **do not read kernel code, do not look at the ADT**; first run `patch-armcpu-validate.py --check` on the kernel used for packaging; if it is not `already patched`, it is this entry.

---

### P-22 correction (measured 2026-11-08): it is not "the cache disappeared", it is init's `DYLD_SHARED_CACHE_DIR` pointing at the wrong path

The original P-22 conclusion is void. **Measured by the boot-time probe (0392)**:
```
K60DYLD /System/Library/Caches/com.apple.dyld                          rc=0
K60DYLD /System/Library/Caches/com.apple.dyld/dyld_shared_cache_arm64 rc=0   ← the cache was there all along
K60DYLD /private/preboot/System/Library/Caches/com.apple.dyld          rc=2   ← does not exist
K60DYLD /usr/lib/libSystem.B.dylib                                     rc=2   ← normal (it is inside the cache)
```
init's `env[]` copied `DYLD_SHARED_CACHE_DIR=/private/preboot/System/Library/Caches/com.apple.dyld/`
(the path on a real pong device's preboot volume) verbatim into this port, but this port's cache is at `/System/Library/Caches/com.apple.dyld/`.
dyld therefore reports `(no such file, no dyld cache)`, then the fallback lookup of `/private/preboot/usr/lib/libSystem.B.dylib` fails too → `ns=6 code=0x1`.

**Fix**: the two environment variables in init become
```
DYLD_SHARED_CACHE_DIR=/System/Library/Caches/com.apple.dyld/
DYLD_FALLBACK_LIBRARY_PATH=/usr/lib
```
Measured result (`evidence/usblog-20261108-135117/console.log`):
`launchd_cache_loader reported as clean exit (was 0x0)`,
`K60PSX pid=24/45/79/44 err=0`, `assistantd/locationd/mediaserverd/tccd` all running,
**`Pong UI: 20G81 compatibility library entered SpringBoard` + `UIApplication -_run hooked`**.

- **Evidence**: `scratch/INITV13.txt` (compilation and self-check), the Gate3/Gate3b output of `scratch/writev13.ps1`, the logs above.
- **30-second check**: `dyld[1]: Library not loaded ... (no such file, no dyld cache)` → go straight to whether the directory `DYLD_SHARED_CACHE_DIR` in init points at exists on the device (with the 0392 probe or `ls`); do not suspect a lost cache.

---

### P-26 The exact scope of the launchd(PID 1) crash: only 8 App-cryptex jobs; and `bindfs` over the read-only root returns EPERM

- **Measured (2026-11-08, OS image parsing)**: `/System/Cryptexes/App` and `/System/Cryptexes/OS` are both **symlinks**, pointing at
  `../../private/preboot/Cryptexes/App` and `../../private/preboot/Cryptexes/OS` respectively; this port has no preboot volume → all these paths dangle.
  **Only 8** LaunchDaemons reference the App cryptex:
  `Safari.passwordbreachd`, `SafariBookmarksSyncAgent`, `webinspectord`, `Safari.History`,
  `safarifetcherd`, **`WebBookmarks.webbookmarksd` (the crash trigger)**, `AuthenticationServicesAgent`, `webkit.webpushd`.
- **Crash mechanism**: `launchd` does `access(path, X_OK)` on the missing program, gets `ENOENT`, then **SIGSEGV** (`KX! n 1 launchd sig=11 ns=2 code=0xb`) → the kernel's `initproc exited` panic.
- **Fix already tried (failed)**: embedding the filtered `launchd.plist` in the kernel (22 CORE jobs, 9,799 B) and writing it to `/private/var/pong/launchd.plist` (`K60LC: write=0 resid=0`, success), then init `mkdir`+`rename` to `/private/var/pong/xpc/launchd.plist` (`Pong init: curated launchd cache installed`, success), and finally `mount("bindfs", "/System/Library/xpc", MNT_RDONLY, ...)` — **failed: `result=-1 errno=1` (EPERM)**. A directory on the read-only root cannot be covered by bindfs.
- **Next candidates (not executed, risk must be assessed)**:
  1. **Same-size in-place overwrite**: pad the curated plist to **exactly the same 1,384,579 B** as the original file, and `dd` over the same range in TWRP using the physical block number of the extent from `apfs.py stat` — no inode change, no APFS metadata change, lowest risk; back up the original 1.38 MB range first.
  2. Rewrite the whole OS window (5.09 GB) — high risk, needs a full backup, not recommended for now.
- **Evidence**: `scratch/CRYPTEX.txt` (the 8 jobs + symlink targets), `scratch/COREPROG.txt` (the 22 CORE programs **MISSING COUNT: 0** in the OS image), `evidence/usblog-20261108-143838/console.log` (`boot view ... result=-1 errno=1`, `webbookmarksd`, `initproc exited`).
- **30-second check**: `initproc exited` + `webbookmarksd` → follow this entry; stop suspecting dyld/init/kernel.

---

### P-27 `bindfs` is always EPERM on the sealed root; the `access`/`faccessat` hooks do not work for launchd; APFS remount is needed

- **Measured (2026-11-08)**:
  - `mount("bindfs", "/System/Library/xpc", MNT_RDONLY, ...)` → `result=-1 errno=1`
  - `mount("bindfs", "/private/preboot", MNT_RDONLY, ...)` → also `-1 errno=1`
  - changing to `flags=0` still gives `-1 errno=1`
  ⇒ **directories on the read-only sealed root (OS volume `incompatible 0x8` = sealed) cannot be covered by bindfs**; pong's five bindfs views are all unusable in this port, and everything after the `optional boot view SKIP` in the log would EPERM even if it ran.
- **Secondary measurement**: in the kernel both `0390` (`access()` prefix fake success) and `0396` (same logic for `faccessat_internal`) **are compiled in** (`strings` hits each once), yet **neither print appears** before launchd crashes ⇒ launchd's `access(path, X_OK)` check goes through neither the `access` nor the `faccessat` syscall (it is libSystem userland/another path resolution), so intercepting at the syscall layer is useless.
- **Correct next step**: use a **real APFS mount** to mount the Data volume a second time at `/private/preboot` (macOS's `/Volumes` mounts normally on the sealed root, which shows the mount itself is not blocked by sealing; only bindfs's vnode covering is refused).
  Device-measured volume numbers: **Data = `/dev/disk2s1`** (5,210,112 blocks × 4096 = 21,342,715,904 B, matching the Data window `0x4f8200000` exactly); OS = `disk1s1` (1,244,160 blocks).
  After mounting, `/private/preboot/Cryptexes/App/...` is the same source as `Cryptexes/App/...` at the Data root, so 8 **0755 empty files** under `/private/var/Cryptexes/App/...` are enough to make launchd's `access(X_OK)` succeed.
- **Evidence**: `scratch/INITV16.txt`/`INITV17.txt` (`app-cryptex stubs ready` and the EPERM print), `scratch/HOOKCHK.txt` (both hooks are in the kernel but never fire), `scratch/NAMEI.txt`, `evidence/usblog-20261108-155056/console.log` (`webbookmarksd` + `initproc exited`).
- **30-second check**: seeing `boot view ... result=-1 errno=1` → stop trying any variant of bindfs (RDONLY and 0 both fail), go straight to the APFS remount.

---

### P-28 `mount("apfs", "/private/preboot", MNT_RDONLY, payload)` → **errno 79 = ENEEDAUTH**

- **Measured (2026-11-08, init-v18)**: after init created the 8 0755 empty files for `Cryptexes/App/...` at the Data volume root
  (the log's `Pong init: app-cryptex stubs ready` is normal), it called, with the same APFS 2142 payload as for `/private/var`,
  `mount("apfs", "/private/preboot", MNT_RDONLY, payload)` with device `/dev/disk2s1`:
  `Pong init: preboot remount result=-1 errno=79`. Darwin errno 79 = **ENEEDAUTH**.
- **Meaning**: APFS requires authentication for a second mount of the same container (it is not sealing, and not EPERM). **"Remount Data at /private/preboot" is not a viable route**; do not try other flag variants.
- **Also already ruled out**: bindfs to `/private/preboot` (both MNT_RDONLY and flags=0 give EPERM), bindfs to `/System/Library/xpc` (EPERM), kernel `access`/`faccessat` hooks (never fire). See P-27.
- **The only remaining viable direction**: replace `/System/Library/xpc/launchd.plist` in the OS window directly (same-size in-place overwrite, no inode/metadata change).
  **The key offset is still unconfirmed**: the first 1 MB of the window is very likely reserved; if the APFS container starts at `window + 0x100000`,
  then the file position = `0x100000(OS window) + 0x100000(before container) + 1062050×4096`, i.e. **`bs=4096 skip=1062562`**.
  The **first step** next time the device is available is a read-only 32-byte read to verify it is `bplist00`; only then discuss writing.
- **Evidence**: `evidence/usblog-20261108-160004/console.log` (`preboot remount result=-1 errno=79`), `scratch/INITV18.txt` (sha `e8c65936…`).
- **30-second check**: `preboot remount ... errno=79` → give up the second mount outright and switch to the same-size overwrite in the OS window; seeing `errno=1` → that is bindfs, stop trying.

---

### P-29 The device's OS window content ≠ the local `096-57366-083.dmg`: block numbers/content from the dmg cannot be used to infer it

- **Measured (2026-11-08)**: taking the first 64 bytes of the `launchd.plist` extracted from `096-57366-083.dmg` as a fingerprint
  (`62706c6973743030d6000100…417070457874656e73696f6e735d4c61756e63684461656d6f6e735f1012`),
  a block-by-block search of the device's unixnu partition **full OS window of 4.75 GB (0x12fc08600, 19 chunks of 256 MB)**:
  **19/19 all hit=-1, RESULT_NOT_FOUND**.
- **Meaning**: the OS content on the device is **not the same image** as the local dmg; `NXSB` distribution inside the device's 64 MB header differs completely from the dmg
  (the device has one every 0x2000 at 0x104420/0x10c420/0x10e420…; the dmg's container superblock is at block 0).
  ⇒ **it is forbidden** to use the dmg's APFS block numbers + window offset to locate or rewrite OS files on the device (it would write over unrelated regions).
- **Facts that still hold**: the window offsets in the SHNGROOT manifest are **byte offsets inside the partition** (Data window `0x261100000` + `0x100000` content start,
  consistent with the init write formula, verified by Gate3 several times); OS window = `0x100000`, SystemOS = `0x12fe00000`, Data = `0x261100000`.
  Each window's **first 1 MB is a reserved region**, content starts at `+0x100000`.
- **Therefore**: changing a file in the OS can only be done **in the running system** (the ro mount blocks it) or by changing kernel behaviour; offline rewriting is not viable.
- **Evidence**: `scratch/scanlp*` (scan scripts), `scratch/PREP_PLANA.txt`, `scratch/LBA2.txt`, `scratch/PLAN_A.txt`.
- **30-second check**: before changing a file inside the OS window, first do a full-window scan with the 64-byte fingerprint to confirm it can be located; if it cannot, **abandon the offline rewrite immediately**.

---

### P-30 Path redirection at the `namei()` layer does not fire either ⇒ launchd's "access(...)" line is very likely a log line it composes itself, not real path resolution

- **Measured (2026-11-08, kernel `dea5e777` / in-image `50d1b6c6`)**: at the `namei()` entry, `strncmp(path, "/System/Cryptexes/App", 21)` on `cn_pnbuf`
  and rewriting it to the shorter `/private/var/pong...` (theoretically it must fit,
  since the replacement string is 4 bytes shorter than the original). The patch is confirmed compiled into the kernel (`strings kernel.macho | grep -c 'K60 redirect'` = 1,
  and the in-image kernel sha matches), and init also created the 8 0755 empty files under `/private/var/pong`
  (`Pong init: app-cryptex stubs ready at /private/var/pong`).
  **Yet `K60 redirect:` is not printed once** during the whole boot, and launchd still SIGSEGVs at the same place.
- **On top of the earlier conclusions**: `access()` (0390), `faccessat_internal` (0396), `namei()` (0397) — **all three hook layers never fire**.
  ⇒ Conclusion: the line `access(/System/Cryptexes/App/usr/libexec/webbookmarksd, X_OK) failed with errno 2` **is not printed by the kernel during
  path resolution**; it is a description launchd composes itself after `posix_spawn`/exec fails (the errno it gets comes from exec, not from
  access(2)). So **intercepting at the syscall/path layer is useless**; that program file must actually exist, or the service cache must be changed.
- **Dead ends (do not try again)**: bindfs over the sealed root (EPERM), APFS second mount (ENEEDAUTH 79), offline OS window editing (device OS content
  differs from the dmg, fingerprint full-window 4.75 GB scan 0 hits), the three kernel hooks access/faccessat/namei (none fire).
- **Directions that may still work**: ① make `/private/preboot` writable **in the running system** (needs a preboot volume or mountable medium);
  ② change launchd's service cache (needs write access to `/System/Library/xpc`); ③ switch to a boot path that brings up SpringBoard without launchd (needs research into whether pong has one).
- **Evidence**: `scratch/CHK397.txt` (kernel contains 0397), `scratch/CHKIMG.txt` (in-image kernel `50d1b6c6` contains `K60 redirect`),
  `evidence/usblog-20261108-163128/console.log` (no `K60 redirect`, still `webbookmarksd` + `initproc exited`).
- **30-second check**: to bypass the App cryptex with a kernel hook → **first confirm the hook prints**; if it does not print, stop immediately and stop editing hooks.

---

### P-31 pong's Goodix touch driver compiles into the 20G81 kernel, but the HID publishing layer ABI does not match: `IOHIDEventSystemClientCreateWithType` does not exist

- **Measured (2026-11-08, kernel `a1973538`, 198 patches)**: adding the pong ios16 branch's
  `zzzz…-pong-touch-console.patch` (36.6 KB: `bsd/dev/pong_goodix.c` + `pong_input.c` + `pong_input.h` + `conf/files` + `bsd_init.c` + `MiniIOMobileFramebuffer.cpp`)
  and `zzzz…-pong-physical-keys.patch` (12.0 KB: `pong_buttons.c`) to the series in order, **the build passes** (kernel 54,001,664 B, containing `Pong Goodix Berlin-D` and all the goodix diagnostic strings).
  The log after boot: **`Pong touch HID: unavailable IOHIDEventSystemClientCreateWithType; SKIP`** — the touch protocol layer runs, but **the IOHID API called by the event publishing layer does not exist in the 20G81 kernel**, so the driver skips itself.
- **Meaning**: pong's `pong_input.c` targets a newer IOHIDFamily (iPadOS 17/18); 20G81 needs the publishing layer rewritten against `ShengHidInput`'s old ABI (`OFFICIAL-DRIVER-MAP.md` item 6 already says "`ShengHidInput` must be re-aligned with the 20G81 IOHIDFamily").
- **ADT is already in place (important)**: `scripts/make-pong-adt.py` **already generates** `/arm-io/pong-touch` (spi-base `0x990000`, tlmm-base `0x0f000000`, gcc-base `0x00100000`, rsc-base `0x17a20000`, cmd-db-base `0x80860000`, gpio-offset `0x00100000`, pins `<16 17 18 19 21 20>`) and `/arm-io/pong-buttons` (core-base `0x0c400000`, cnfg-base `0x0c42d000`, observer-base `0x0c440000`, ee `0`, pon-ppid `0x013`, volume-up-ppid `0x18d`). This round only changed `max-x/max-y` from pong's `1080/2412` to the K60's `14400/32000`.
- **Evidence**: `scratch/WIRE_DRIVERS.txt` (series 196→198), `scratch/DRVCHK.txt` (kernel contains the driver), `evidence/usblog-20261108-165317/console.log` (`Pong touch HID: unavailable ...`).
- **30-second check**: seeing `IOHIDEventSystemClientCreateWithType` unavailable → go straight to changing the publishing layer ABI, stop tuning SPI/ADT parameters.

### P-32 The system can run for a long time, but `watchdogd` crashes repeatedly and finally causes a reset (not a launchd crash)

- **Measured (2026-11-08)**: after `disabled.plist` fixed launchd's App-cryptex crash, the system could run continuously to the lock screen (log 342 KB, `home request returned locked=1 screen=1 dim=0`),
  but then came `Process[324] crashed: watchdogd. Too many corpses being created.`, `KX! 5 51 watchdogd exit=0 sig=5`, and finally the device reset itself back to fastboot.
  **No** `initproc exited` / `webbookmarksd` — the launchd side is fixed, the reset comes from the watchdogd crash chain (possibly compounded by a hardware watchdog enabled by ABL).
- **Meaning**: a PMIC/watchdog driver is needed (`pong_buttons.c` already provides the PMIC-arbiter read-only access framework), or `com.apple.watchdogd` must be disabled first (one more entry in `disabled.plist`) to lengthen the stable run time.
- **Evidence**: end of `evidence/usblog-20261108-163843/console.log`; `evidence/usblog-20261108-165317/console.log`.
- **30-second check**: a reset but the log has no `initproc exited` → look at `watchdogd`, do not suspect launchd.

---

### P-33 The touch/button drivers default to **off** (they need a boot-arg), and the userland HID publishing layer cannot be rebuilt in WSL

- **Symptom**: the drivers are compiled into the kernel, yet after boot there are no `Pong keys:` / `goodix:` log lines at all, and power/volume/touch do nothing.
- **Root cause 1 (gating)**: both pong driver entries require a boot-arg:
  `pong_goodix_init()`: `if (!PE_parse_boot_argn("pong_touch",&enabled,...) || !enabled) return;`
  `pong_buttons_init()`: `if (!PE_parse_boot_argn("pong_buttons",&enabled,...) || !enabled) return;`
  Not passed → it returns immediately, as good as not compiled. **Fix = patch 0399**: change both `enabled=0` to `enabled=1` and ignore the missing argument (on by default).
- **Root cause 2 (userland)**: even with the kernel driver working, the events still have to be published by the userland `userland/touch.c` through
  `IOHIDEventSystemClientCreateWithType`; 20G81 has no such variant (log `Pong touch HID: unavailable ...`).
  `touch.c` has been given a fallback to `IOHIDEventSystemClientCreate` (the old API), but **`libpong-ui.dylib` is compiled by `userland/build.py:compile_ui` with macOS `xcrun` + the iPhoneOS SDK**, and WSL cannot rebuild it; there is no prebuilt artefact in the repo/deliverables either.
- **Viable way out**: ① run `userland/build.py` on macOS to regenerate `libpong-ui.dylib` and re-pack 0340's blob; ② move HID publishing into the kernel (20G81 ships `IOHIDEventService` / `IOHIDEventCreateKeyboardEvent`), dropping the macOS dependency entirely (recommended).
- **Side conclusion**: **do not** use a "re-send DCS 0x29/0x51 every 2 seconds" keep-alive thread to hold the screen on — after the power key blanks the screen it would be forced back on, fighting iOS's sleep logic; the correct approach is to get power-key events into SpringBoard.
- **Evidence**: `scratch/KEYSHOOK.txt` (the gating source text), `scratch/INITV21.txt`, `scratch/UILIB.txt` (build.py needs xcrun), `evidence/usblog-20261108-165317/console.log`.
- **30-second check**: driver compiled but no driver log at all → check the `PE_parse_boot_argn` gating first; `unavailable IOHID...` → it is the userland library ABI.

---

### P-34 schema-v2 ADT: `/arm-io` child nodes come only from the DTS's `unixnu,adt-name`, and properties must hit the whitelist

- **Symptom**: `pong_goodix` / `pong_buttons` print `missing/incompatible DT; SKIP`, even though the kernel driver is compiled in and the boot-arg gating is already on by default.
- **Root cause (two layers)**:
  1. In `scripts/unixnu/devicetree.py:generate()` the `/arm-io` child nodes do **not** come from the profile's `["adt"]`, but from
     `hardware = [entry for entry in root.walk() if 'unixnu,adt-name' in entry.properties]` — only nodes in `dts/mondrian.dts` that carry
     `unixnu,adt-name = "..."` are exported.
  2. `hardware_properties()` only exports property names in the **whitelist**:
     `STRINGS = {compatible, device_type, reg-names, interrupt-names, clock-names, method}`
     `U32 = {phandle, …, pong,smmu-stream-id, pong,ufs-spi, …}`
     `U64 = {redistributor-stride, pong,ufs-hc-base, …}`
     **`spi-base / tlmm-base / gcc-base / rsc-base / cmd-db-base / gpio-offset / pins / max-x / max-y / core-base / cnfg-base / observer-base / ee / pon-ppid / volume-up-ppid` are all absent from the whitelist → they are silently dropped.**
- **Correct approach (three steps)**:
  1. add the two nodes to `dts/mondrian.dts` with `unixnu,adt-name = "pong-touch"` / `"pong-buttons"` and write all properties using pong's naming;
  2. in the **UniXNU framework repo**'s `scripts/unixnu/devicetree.py`, add the 15 property names above to the `U32`/`U64` whitelists (note: `tree/scripts` is re-copied from the framework repo on every build, so edits inside tree get overwritten);
  3. re-run `unixnu payload` → `unixnu bootimg`/splice → on device.
- **Evidence**: `scratch/ADTNEW.txt` (in the ADT `pong-touch`/`pong-buttons`/`spi-base` are all `-1`), `scratch/WHITELIST.txt` (the whitelist source text, hit count 0 for all 15 properties), `scratch/DTSNODE.txt` (`ufs@1d84000`'s `unixnu,adt-name = "ufshc"` as an example).
- **30-second check**: the driver reports `missing/incompatible DT` → first `strings kernel.macho.adt | grep <node name>`; not present means check the DTS + whitelist per this entry, do not change the driver's assertion value.

---

### P-35 Disabling daemons must follow pong's DENY policy, and it must be data that can be **undone at runtime**, never hardcoded

- **Background**: before `boot-0461`, `launchd` crashed on the App-cryptex `webbookmarksd`; after using `disabled.plist` to disable the 8 App-cryptex jobs, launchd was stable and the system ran to the lock screen.
- **pong's authoritative approach**: the `DENY` tuple in `userland/mkjobs.py:216` contains
  `'watchdog', 'CommCenter', 'wifi', 'WiFi', 'bluetooth', 'BTServer', 'locationd', 'softwareupdate',
  'datamigrator', 'backupd', 'thermalmonitord', 'keybagd', 'nfcd', ... 'syncdefaultsd', 'photoanalysisd', 'avconferenced'`
  — the comment reads: "these start, crash and are asked for again, over and over".
  **So having `watchdogd`/`syncdefaultsd` and the like disabled is pong's established policy, not symptom masking.**
- **But**: `wifi`/`bluetooth`/`locationd` are in pong's DENY too — that is because **pong had no corresponding driver at the time**. Once we have WiFi/BT/location drivers they must be re-enableable, **so the disable list must never be hardcoded into init**.
- **Implementation (init-v24, 34,904 B, sha `1671eb78…`)**: at runtime init reads `/private/var/pong/disabled-labels.txt` (one label per line, `#` comments), generates the XML `disabled.plist` and writes it to
  `/private/var/db/com.apple.xpc.launchd/disabled.plist`; when the file is absent it uses the built-in default (**only the 8 App-cryptex jobs + `com.apple.watchdogd`, 9 entries total, excluding wifi/bt/location**).
  Log criterion: `Pong init: disabled.plist wrote %u labels`.
- **Note**: `/private/var` is the APFS Data volume, unwritable under TWRP; changing the list can only go through a kernel blob (same mechanism as 0394) or, once the system is up, through a channel that can write Data.
- **Evidence**: `scratch/PONGDENY.txt` (the DENY source text), `scratch/INITV24.txt` (compilation and strings), `scratch/disabled-labels.txt` (the default list).
- **30-second check**: before disabling a daemon, check whether pong's `DENY` has it; if not, we are inventing policy — stop and look at what driver is missing.

---

### P-36 Gating default `enabled=0`: the driver returns on its first line, silently and with no log

- **Symptom**: physical keys/touch produce no kernel log and no `/dev/pong-*` node, userland reports
  `verified PMIC input unavailable` / `real touch device unavailable`; everything looks like "the driver did not run".
- **Root cause**: the original pong patch has `uint32_t enabled=0;` and the boot-arg gate `if (!enabled) return;`.
  An earlier gating fix only changed it to `(void)PE_parse_boot_argn(...)` (ignoring the return value), **without changing the default 0** →
  with no boot-arg passed, `enabled` is always 0 → it returns on the first line. The 2026-11-08 18:02 run where physical keys
  worked (log `Pong keys: arbiter v7 …`) was during the `enabled=1` period; later the original pong patch overwrote it and brought
  the default back to 0, and the physical keys blew up with it.
- **Fix**: `uint32_t enabled=1;` (touch patch line 920, keys patch line 271, commit `7da999e`).
- **30-second check**: for any "driver silently not running", first `grep 'uint32_t enabled='` to see the default; if it is 0, change it to 1.

### P-37 `devfs_make_node(...,"%s",name)`: the device is created as the literal `/dev/%s`

- **Symptom**: `input_ready()` returns true, but userland can never open `/dev/pong-buttons`.
- **Root cause**: `devfs_make_node` **does not accept a printf format string**; `"%s", name` makes the literal `%s` the node name.
- **Fix**: pass `name` directly.
- **30-second check**: any devfs node that cannot be opened, first `grep devfs_make_node` and look for a `%`.

### P-38 K60 touch GENI SE is **SE4**, not SE1; the clock blockage is the S_AHB HWCG bit

- **Symptom**: original SE4 log `s_ahb=0x80000002` (bit31 halt + **bit1 HWCG**), se4=0x4220 (already on).
- **Root cause**: `K60-TOUCH-PARAMS.md:90` states plainly that `spi@990000` = QUP0 **SE4** (pinctrl function `qup4`).
  I once wrongly changed 7 GCC offsets to SE1 and reverted it (commit `7da999e`). The real blockage is the S_AHB HWCG bit;
  Linux's `clk_branch2_enable` clears bit1 first.
- **Fix**: keep the SE4 constants (the `0x274dc` family) + clear bit1 of the three CBCRs after the vote.
- **30-second check**: with `s_ahb=0x80000002` clear bit1 first, do not go changing SE numbers.

### P-39 **Patches have a hard dependency order**: GPU scanout must come before touch, or the hunk context does not match

- **Symptom**: `git apply` reports `error: patch failed: iokit/Kernel/MiniIOMobileFramebuffer.cpp:1032`,
  saying the touch patch does not apply, yet the patch content itself is completely correct.
- **Root cause**: the context of the touch patch's last hunk contains `if (!gpuFrame) drawLayer(s, src, dst);`,
  and **`gpuFrame` is a variable introduced by the GPU scanout patch** (`pong-gpu-scanout.patch:42` defines `bool gpuFrame=false`,
  `:71` uses it). If the GPU patch is not applied before touch, the target tree has no `gpuFrame` and the context never matches.
- **A deeper pitfall**: the hunk header says `@@ -1032,6 +1032,10 @@`, but `kPEGraphicsMode` actually sits at
  **line 989** in every historical tree (the `show()` in all three trees `out/out2/out3` is at line 885). **The line number itself is off by 43 lines** —
  so even with the right order, the line number cannot locate it; only context can.
- **Diagnostic method**: `git apply --check -C1 <patch>` prints `Context reduced to (1/1) to apply fragment at 989`
  —**that sentence hands you the real line number**, the fastest entry point for troubleshooting.
- **Fix**: the series order must be **GPU three patches → touch → keys** (the last 5 lines of the current `SERIES-FINAL.txt`).
- **30-second check**: touch/keys patch failing to apply, first check where `grep -n 'gpuFrame'` sits in the series; if GPU is not before it, the order is wrong.

### P-40 The build reads `$B/tree/.cache/xnu-work`, not the device repo's `iokit/`

- **Symptom**: editing `iokit/Kernel/MiniIOMobileFramebuffer.cpp` in the device repo (`/tmp/usb-cdc-mainline/device`)
  has no effect at all; line-number lookups also get misled by this "already-patched artefact copy" (`show()` at line 899 vs line 885 in the real tree).
- **Root cause**: `build-xnu-4k-baseline.sh` clones xnu from `feeds/xnu-<sha>` (**plain apple-oss xnu, with no iokit/Kernel/MiniIOMobileFramebuffer.cpp**)
  into `$B/tree/.cache/xnu-work`, and then the UniXNU framework's overlay injects that file.
  The real compilation target is **`/opt/k60/trees/k60build/out-baseline/mondrian/ipados-16.6.1-20G81/mondrian/tree/.cache/xnu-work/`**.
- **Key fact**: `feeds/xnu-c465a9f8` **does not contain** `iokit/Kernel/MiniIOMobileFramebuffer.cpp` at all (verified with find);
  this file comes from the UniXNU framework's `iokit/` overlay.
- **Diagnostic method**: `grep -a 'prepare XNU' /tmp/build-v15.log` prints `git clone --shared ... /opt/.../tree/.cache/xnu-work`,
  plus the real path of `feeds/xnu-<sha>`.
- **30-second check**: to change/find a file in xnu, first `find /opt/k60/trees/k60build/out-baseline -name '<file>' -path '*.cache/xnu-work*'`
  —**editing the iokit/ copy in the device repo is useless**.

### P-41 A 0-byte boot log ≠ a broken device: use a historical image as the control first

- **Symptom**: after `fastboot boot` the console log is 0 bytes and the device returns to fastboot by itself, looking like the device/UEFI is broken.
- **Correct diagnostic order** (measured to work this round):
  1. flash **a historical image confirmed to boot** (e.g. `boot-0442-20261107.img`, 11-07 15:24)
  2. if it boots normally and captures a log (204,641 B this round), then **the device, UEFI, packaging flow and fastboot are all fine**
  3. the problem is definitely in **the new kernel itself**
  4. **this round's proof**: `boot-0442-20261107.img` booted successfully (log 204,641 B, Darwin 22.6.0 Sat Nov 7 15:03:08),
     while all 199/207 versions gave 0 logs and a reset → localised to a patch ordering problem (P-39).
- **30-second check**: on a 0-log reset **do not say the device is broken first**; flash a historical image as the control — 30 seconds rules out the device.

### P-42 `out`/`out2`/`out3` are historical build trees, usable directly as controls

- **Value**: `/opt/k60/trees/usb-cdc-mainline/out{,2,3}/mondrian/ipados-16.6.1-20G81/mondrian/tree/.cache/xnu-work/`
  all three **complete, already-patched xnu work trees** are still there (1537/1537/1558 lines each, `show()` at line 885 in all).
- **Use**: verify whether a patch applies, look up real line numbers, compare patch state across periods, **without rebuilding**.
- **30-second check**: to judge whether a hunk really applies, just `git apply --check` it against one of those trees; far faster than creating a new tree.

### P-43 `#if defined(PONG)` is always false in `bsd_init.c` → the input driver calls are deleted by the preprocessor

- **Symptom**: `bsd_init.c` plainly contains `pong_goodix_init(); pong_buttons_init();`, but
  `llvm-nm | grep pong_` on `bsd_init.o` shows **not one symbol**, and the kernel has no input driver log either.
- **Root cause**: `bsd_init.c` **does not include `<pexpert/arm64/board_config.h>`**, so the `PONG` macro is **undefined** in that
  translation unit and the whole `#if defined(PONG)` block is deleted by the preprocessor.
  (`pong_buttons.c` / `pong_goodix.c` include it themselves, so the driver code compiles fine.)
- **Fix**: change that block's `#if defined(PONG)` to `#if 1` (or add an explicit `#include <pexpert/arm64/board_config.h>`).
- **Verification**: `llvm-nm bsd_init.o | grep pong_` must show `U _pong_goodix_init` / `U _pong_buttons_init`.
  **Not seeing them means the preprocessor deleted them; it has nothing to do with the patch content.**
- **30-second check**: when a driver "is compiled in but does not run", first `llvm-nm <the .o containing the calls> | grep <symbol>`; no U reference means an `#if` gating problem.

### P-44 Editing a patch means editing **three places** (repo patch / device patch / build tree); changing only one gets overwritten

- **The three places**:
  1. `E:\hackios\UniXNU-mondrian\patches\xnu\<patch>` (the real git source)
  2. `/tmp/usb-cdc-mainline/device/patches/xnu/<patch>` (buildv15 overwrites this from the repo)
  3. `$B/tree/.cache/xnu-work/...` (**the tree the build actually compiles**, cleared and rebuilt every time)
- **The chain of burns proven this round**:
  - only the tree → lost as soon as the next build clears the tree
  - only the repo → no effect until the device side/buildv15 syncs
  - only the device → the repo overwrites it back to the old version next time
  - `buildv15.sh` lines 15-19 sync only **5 fixed patches**; the rest are read from the device via the series
- **Correct flow**: edit the repo patch first → `cp` to the device → edit the file in the tree (or rebuild so it re-applies) → build → verify the value in the tree.
- **30-second check**: after editing, `grep` all three places to confirm they hold the new value, then press the build key; changing only one is wasted effort, guaranteed.

### P-45 When the build artefact's sha does not match, first confirm which tree you are reading

- **Burn this round**: `/tmp/k60build` is the UniXNU framework checkout (not the build working directory);
  the real build tree is `/opt/k60/trees/k60build/out-baseline/mondrian/ipados-16.6.1-20G81/mondrian/tree/.cache/xnu-work`.
  I once compared against the wrong tree and concluded "none of the shas match", wrongly.
- **30-second check**: `grep -a 'prepare XNU' /tmp/build-v15.log` prints the real clone path; judge by that.

### P-46 Repeated hunk header mismatches → **fixed at the root: recomputed automatically before the build**

- **Symptom**: after hand-editing a patch body (adding comments, adding code) you forget to sync the `@@ -a,b +c,d @@` numbers, so
  `git apply` reports `corrupt patch at line N` or the compiler reports `unterminated conditional directive` (because
  `git apply` truncates by the header's line count and drops the `#endif` at the end of the file).
- **Times burned this round**: at least 4 (`pong_buttons.c` 149→150, 143→147, `bsd_init.c` 6,10→6,12→6,16 etc).
- **Root fix**: `<workspace>/scratch/fix-patch-hunks.py` scans all `.patch` files and recomputes every
  `@@` header from the actual body line count (including the `-0,0 +1,N` new-file form); it has been **integrated into step 2b of `buildv15.sh`** —
  it runs automatically before every build, so hand-editing a body can no longer break the build.
- **30-second check**: any `corrupt patch` / `unterminated` error, first run
  `python3 E:/k60-work/scratch/fix-patch-hunks.py`; that usually solves it outright.

### P-47 `if (!PE_parse_boot_argn(...) || !enabled) return;` — the real gating killer

- **Symptom**: `enabled=1` is set, `#if defined(PONG)` is fixed, `llvm-nm` shows the call, **and the driver still does not run**.
- **Root cause**: `PE_parse_boot_argn` **returns FALSE when the boot-arg does not exist**, so
  `!PE_parse_boot_argn(...)` = `true`, `||` short-circuits, and it **returns immediately**. The `enabled=1` default is **never evaluated at all**.
- **Fix**: split it into two statements —
  ```c
  (void)PE_parse_boot_argn("pong_buttons",&enabled,sizeof(enabled));
  if (!enabled) return;
  ```
- **Verification (measured on this machine, kernel `7f99d2fa`, log `usblog-20261109-122746`)**:
  ```
  Pong keys: arbiter v7 channels=768 PON=407 GPIO6=434; power=1 up=1 down=1
  ```
- **30-second check**: when a driver "meets every condition and still does not run", look at whether the gating line has an `||` — `|| !PE_parse_...` means it is this one.

### P-48 The real error behind the touch `configuration()` failure (finally visible)

- Once the driver runs, the first real error appears: `Pong touch: missing/incompatible Pong DT; SKIP`
- **Meaning**: `SecureDTLookupEntry` or a property read inside `configuration()` fails.
- **Confirmed working**: the ADT nub is published (`ArmDTPlatform: published DT nub pong-touch`),
  the ADT node properties are complete (`pong-touch@13296`: spi-base/tlmm-base/gcc-base/rsc-base/cmd-db-base/gpio-offset).
- **Next debugging point**: whether the **node path** looked up in `configuration()` matches the actual ADT path (`/arm-io/pong-touch` vs something else).

### P-49 **Fixing touch so it "passes configuration()" is a disaster: accessing an SE with no clock enabled hangs the whole machine**

- **Symptom**: when the `configuration()` assertion fails it prints `missing/incompatible Pong DT; SKIP` and
  **returns safely, the system boots normally**; as soon as the assertion is corrected to pass, `touch_thread` starts and
  **after boot the console has 0 bytes, the whole machine is dead, and it resets itself back to fastboot**.
- **Root cause**: once `configuration()` passes it runs `touch_thread` → `bring_up()` → `clocks_on()` →
  `geni_spi_init()` → **accessing the QUP0 SE4 registers**. But `clocks_on()` only checks that the vote was written,
  it does not guarantee the SE branch really has a clock. **A register access to an SE with no clock hangs the interconnect**,
  the machine dies early, before `K60 USBLOG` can even get output out — which is why it shows as 0 logs.
- **This round's proof (2026-11-09)**:
  - kernels `7f99d2fa` / `a1494b2a` (assertion still requires 14400×32000 → fails → skipped): **boots**,
    log 60-217 KB, physical-key HID fully working
  - kernels `8a5595f1` / `fb147b79` (assertion loosened/corrected → passes → thread starts): **0 logs, machine dead**
  - repeated 4+ times, all consistent
- **Fix**: add a boot-arg gate `k60_touch_se=1` (**off by default**). After `configuration()` passes it only prints
  the verified DT values (`Pong touch: DT ok (...)`), then returns; only an explicit boot-arg starts
  `touch_thread` to touch the SE.
- **30-second check**: after a touch change, if **boot gives 0 logs but a historical image boots**, roll back that "make configuration pass" change immediately
  —the device is not broken, the SE access hung the interconnect. For the historical-image control method see P-41.

### P-51 `make -j8` buffers output: a log that stops updating ≠ a stuck build

- **Symptom**: `/tmp/build-v15.log`'s mtime sits at 16:06:57 for 4 minutes straight, looking like a freeze.
- **Truth**: XNU's `make -r -j8` **buffers** subprocess output and flushes at the end; compilation is actually progressing the whole time.
  Evidence: `pgrep -af 'make.*build_all'` shows `make -r -j8 -f MakeInc.top build` running,
  with 3 levels of make nesting (25800/25854/29329/29330).
- **Criterion**:
  ```bash
  pgrep -af 'make.*build_all' | head -2    # a process means it is compiling
  ```
  **Do not** judge progress with `tail -f` or the log mtime.
- **30-second check**: when the log stops moving, first `pgrep -af 'make.*build_all'`; a process means it is normal.

### P-52 Patch anchors depend on "the real state after all preceding patches": they cannot be generated from memory

- **Symptom**: BT's `0502-k60-bt-qbt-bsd-init.patch` fails to apply in a 209-entry series,
  reporting `patch failed: bsd/kern/bsd_init.c:1337`.
- **Root cause**: that patch's anchor assumes `pong_goodix_init()` comes **after** `k60_usblog_start()`.
  But after the 201-entry series, the real structure of `bsd_init.c` is:
  ```
  1160: extern void pong_goodix_init(void);
  1161: pong_goodix_init();
  1162:     extern void pong_buttons_init(void);
  1163:     pong_buttons_init();
  ...
  1340:     extern void k60_usblog_start(void);
  1341:     k60_usblog_start();
  ```
  **touch/keys are at line 1160, 180 lines before usblog** — the opposite of the earlier assumption.
- **Correct approach**: do not hand-write anchors. Instead:
  1. `git clone --shared` a feed to `/tmp/xxx-regen`
  2. apply in series order **up to the entry before the target patch**
  3. edit the real file
  4. `diff -u` to generate the patch
  5. `git apply --check` to verify
- **30-second check**: when a patch fails inside the series, first look at what the file it depends on actually looks like **in the real tree**;
  do not edit from memory or an old version.

### P-53 A new patch must go at the **end** of the series (never in the middle)

- **Symptom**: inserting `0334b-k60-autoreset.patch` after `0334` and before `0387` made
  `0339-k60-xpc-report.patch` fail to apply (`patch failed: bsd/dev/k60_usblog.c:1510`).
- **Root cause**: patches 0339/0341 etc. also modify `k60_usblog.c`, and the inserted code changed the context.
- **Fix**: put the new patch **last** in the series (entry 201/209), because they are generated against the state
  "after all patches are applied".
- **30-second check**: a new patch failing to apply with "later patch context mismatch" → move it to the end of the series.

### P-54 Image args are read from the payload's `unixnu.toml`, not guessed from `packv15.sh`

- **Symptom**: I once grepped `args = "` in `/mnt/e/.../boot-v15.img` and got 10 items of `0x144`,
  and thought the args replacement had failed.
- **Root cause**: what I read was a **leftover string elsewhere**. The correct approach is:
  1. `ksize = struct.unpack_from('<I', d, 8)[0]`
  2. `rat = 4096 + ((ksize + 4095) & ~4095)`
  3. `payload = d[rat : rat+201326592]`
  4. `mcopy -n -i payload ::/EFI/UniXNU/unixnu.toml`
  5. regex `args = "..."` out of the toml and `split()`
- **Measured comparison**: `boot-0461`/`boot-0442` = 972 B / 28 items / `0x140`;
  `boot-v15` (old version) = 896 B / 25 items including `k60_touch_se=1` (dangerous!); the new safe version = 490 characters / 24 items.
- **30-second check**: verifying image args always goes through payload extraction, never by guessing from `packv15.sh` source.

### P-55 `packed_data_ramdisk` writes the ADT's `ephemeral-storage = 1`

- **Location**: `scripts/make-pong-adt.py:146` and `:233`
  ```python
  *([('ephemeral-storage', struct.pack('<I', 1))] if args.packed_data_ramdisk else []),
  ...
  [('PackedRAMDisk', bytes(16))] if args.packed_data_ramdisk else []),
  ```
- **Meaning**: if enabled, the ADT declares `ephemeral-storage = 1` and carries a `PackedRAMDisk` placeholder.
  That **may mean the Data volume comes from an image-embedded ramdisk and does not depend on on-disk data** — a positive for "can someone else reproduce this".
- **Pending verification**: `board.toml` currently **does not set** `packed_data_ramdisk` (grep finds nothing),
  so the current state is "depends on the on-disk Data volume". Improving reproducibility needs it explicitly enabled and verified.
- **30-second check**: when discussing reproducibility, first `grep -n 'packed_data_ramdisk' board.toml`;
  absent means it depends on disk.

### P-56 "No output from some driver in the log" does not mean "the driver did not run"

- **Two reasons**:
  1. **The printf happens before the USB console enumerates**: `usblog-20261108-213652` proves the touch driver's
     `goodix: clocks stay off` appears before `K60 USBLOG: st=2` (USB not enumerated),
     and is replayed later from the ring buffer.
  2. **Driver init in `bsd_init.c` is at line 1160**, 180 lines before `k60_usblog_start()` (line 1340).
- **So the reasoning chain "0 logs means it hung" needs care**: it may be
  (a) it really hung very early, or
  (b) it hung before USB enumeration but the ring actually holds content (the replay just did not succeed).
- **Criterion**: distinguish by adding an unconditional printf **at the very front of the driver entry** (`K60T: 1 init entry`),
  then check on device whether that line appears. If it appears → the ring works and the hang is after it; if not → the hang is earlier.
- **30-second check**: do not treat "no log output" as "the code did not execute"; first add the earliest possible instrumentation point and verify.

### P-57 `NativeMetal` was a dangling submodule declaration (already cleaned up)

- **Symptom**: `.gitmodules` declared `[submodule "drivers/NativeMetal"]`, but
  `git ls-tree HEAD drivers/NativeMetal` had **no entry**, the directory was empty, and `git submodule update --init` reported
  `pathspec did not match any file(s) known to git`.
- **Root cause**: historical leftover; the gitlink was never committed.
- **Already handled**: deleted `.gitmodules` (it was the only entry, deleting it left the file empty → deleted as well) and the empty directory.
- **30-second check**: `git submodule status` errors or is empty but `.gitmodules` has entries → check whether the gitlink exists.

---

### P-58 Audio has **two gates**; setting only one does not execute, passing both hangs

- **Symptom**: passing `pong_aw882xx=1` but not `pong_audio=1` gives **no `AW882xx` output at all** in the log.
- **Root cause**: the call chain has two independent gates
  ```
  bsd_init.c
    └─ pong_audio_bootstrap()                    [integrated by 0505]
         ├─ gate 1: PE_parse_boot_argn("pong_audio") || mode == 0 → return 0   ← stuck here
         └─ aw882xx_bootstrap()                  [called internally by 0504]
              └─ gate 2: pong_aw882xx
                   └─ aw882xx_worker → aw882xx_probe()
  ```
  Evidence: `0504-k60-audio-pong-audio.patch:870` `if (!PE_parse_boot_argn("pong_audio", &mode, ...) || mode == 0) return 0;`
- **Fix**: **both must be passed**: `pong_audio=1 pong_aw882xx=1`
- **But**: with both passed (kernel `6419fe95`, 26 tokens) there were **0 logs, the machine died and reset itself**.
  This means `aw882xx_probe()` → `aw882xx_bus_init()` hangs when accessing **GENI I2C `0x880000`**
  —the same class of problem as touch SE4 (accessing a GENI controller that is not properly clocked/uninitialised).
- **Current state**: both args have been removed from boot-args, back to the safe state (24 tokens / 490 characters).
- **30-second check**: no audio output, first check **whether both gates are passed**; both passed and 0 logs → it is the GENI I2C hang, not a gating problem.

### P-59 GENI controller (SPI SE4 / I2C SE) access needs stronger pre-checks

- **Two independent reproductions**:
  1. **touch**: `k60_touch_se=1` → `clocks_on()` → `geni_spi_init()` → 0 logs, hang
  2. **audio**: `pong_audio=1 pong_aw882xx=1` → `aw882xx_bus_init()` accesses GENI I2C `0x880000` → 0 logs, hang
- **Common factor**: both kill the machine with zero output on the **first access to the GENI SE registers**.
- **Meaning**: this is not a bug in one driver, it is **the GENI controller preconditions on the K60 that we have not satisfied**.
  Possibly missing: GDSC power domain, NoC path, SE clock really enabled, TLMM pin muxing.
- **Official solution**: the `QcomGeniSpi` component (`GeniSpi.h:211-212` states plainly "caller must know that" the SE clock is already running),
  and sheng's `TouchProbe.cpp:399-424` has the complete precondition sequence (GPLL0 vote + wait for lock + 5 branch votes + pin configuration).
- **30-second check**: before booting any GENI driver (SPI/I2C), first confirm the precondition sequence is complete;
  otherwise you get a 0-log hang and **cannot localise it from the log** (because output never starts).

### P-60 "120Hz is in effect" is the wrong wording: software frame pacing ≠ panel mode switch

- **What I previously wrote (and what `HANDOFF.md` says)**: "120Hz is in effect", "raised from 60Hz to 120Hz".
- **The accurate facts** (corrected by subagent `7fe96011`, with evidence line numbers):
  - the log `K60 DISPLAY: TimingElements 1440x3200 at 120 Hz` did indeed change from 60 to 120 ✅
  - but that is **patch `0506` making `refreshHz()` return 120** — **the software layer pacing frames at 120**
  - `PongDsiPanel.cpp` only sends `0x11` (sleep out)/`0x29` (display on)/`0x51` (brightness)
    (`:220/228/236`), **with no DSI mode-switch command at all**
  - `grep -rn 'panelHz|dsiSet' drivers/` → **empty** (zizhan has it, we do not)
- **Conclusion**: **the panel's actual scan rate is unverified**. The correct wording is:
  > "the software layer paces frames at 120Hz (`refreshHz()`=120), the hardware scan rate is unverified"
- **Real verification needs**:
  1. sending DSI mode-switch commands (zizhan has an implementation to reference)
  2. or measuring on the panel side (oscilloscope / panel self-report)
- **30-second check**: for any claim of a "refresh rate increase", first ask "was a DSI switch command sent";
  if not, it is software frame pacing, not a hardware mode switch.

### P-61 Subagent conclusions must be cross-checked: this round's 3 "premise corrections"

- Of the 5 subagents this round, **3 overturned the premise in the task brief**. This is not the agent erring, it is **the brief resting on outdated/wrong assumptions**.

| Subagent | Brief's assumption | Reality |
|---|---|---|
| `5898cb8e` (OS/power) | "DarwinBoot is 129 lines behind upstream" | 2539/2829 are **bytes**; our `DarwinBoot.c` **has 28 lines more** |
| `7fe96011` (SMMU/display) | "we have three hand-written SMMUs" | `pong_goodix.c` has **zero lines of SMMU**; the official `ArmSmmu4K` **is already in use** |
| `7fe96011` | "the K60 has no GOP" | **it does** (`SimpleFbDxe` is compiled into the firmware), but the reasons it does not apply differ |
| `77f4d518` (USB/baseband) | "the K60 has no GLINK/QRTR/SMEM" | **the DT layer has all of it**, what is missing is the code |

- **Lessons**:
  1. **Verify the premises yourself before assigning the task**, or the agent spends most of its time correcting instead of advancing
  2. **When an agent says "the task premise is wrong", take it seriously** — this round 3/5 were that case
  3. When a brief says "X is known", it must carry **the evidence source and the date**
- **30-second check**: before assigning an agent, ask of every "known premise" "where is the evidence, and from when".

### P-62 The brightness function is not exposed to iOS at all (found, not fixed)

- **Fact**: `pong_panel_set_brightness()` (`PongDsiPanel.cpp:247`) has **0 callers in the whole tree**.
- Verification: `grep -rn 'brightness|backlight|IODisplayParameters' iokit/Kernel/MiniIOMobileFramebuffer.cpp` → **0 hits**
- The 24 selectors (`PongDsiPanel.cpp:48-72`) have **no brightness**
- **Consequence**: moving the brightness slider in iOS **has no effect at all** (the screen stays at the 255 hardcoded by boot-arg).
- **Correct fix** (from `AppleARMBacklight`'s **OS contract**, not its hardware layer):
  - but **two recorded pitfalls must be avoided**:
    - `AppleARMBacklight.cpp:350-355` **int-236**: publishing only `backlight-control` does not satisfy class consistency → **the screen stops updating**
    - `:11-12` **int-229**: duplicate name → **panic**
  - so `backlight-proposed.patch` **deliberately does not publish** `backlight-control`,
    and only adds the `k60_panel_brightness=0..255` boot-arg (default 255, unchanged) as a safe debugging knob
- **30-second check**: before discussing "screen brightness", confirm the panel IC type;
  the K60 is **DCS** (`PongDsiPanel.cpp:6-7`), not an I2C backlight IC (sheng is KTZ8866×2).

### P-63 **The real root cause of every "0-log hang": `io_submap` is only 8 MiB, and a full `ml_io_map` panics**

- **Hard evidence** (real device panic, `evidence/usblog-20261108-192302/console.log`):
  ```
  K60PANICFMT caller=0xfffffff007a5365c fmt=kmem_%s(%p, %zd, 0x%x): failed with %d @%s:%d
  kmem_alloc(0xfffffff16796ab00, 458752, 0x100021): failed with 3 @vm_kern.c:178
  K60PANIC: ring kept; restart reason -> bootloader
  ```
  `458752 = 0x70000` = `GCC_SIZE`; `failed with 3` = `KERN_NO_SPACE`.

- **Causal chain** (all backed by source):
  1. `touch_thread` in `pong_goodix.c` wants 4 windows at once:
     `TLMM 0x200000(2 MiB)` + `GCC 0x70000(448 KiB)` + `SE 0x4000` + `cmd_db 0x20000` ≈ **2.56 MiB**
  2. `osfmk/arm/io_map.c:65`: `#define IO_MAP_SIZE (8ul << 20)` — **8 MiB shared by the whole kernel**
  3. `io_map.c:128`: `kmem_alloc(io_submap, ..., KMA_NOFAIL)` — **ignores the return value**
  4. full → `KERN_NO_SPACE` → `KMA_NOFAIL` → `__kmem_failed_panic` (`vm_kern.c:1002`)
  5. **the panic happens before `clocks_on()`, before `geni_spi_init()`**

- **This explains every symptom this round**:
  | Symptom | Real cause |
  |---|---|
  | `k60_touch_se=0` system normal | the thread does not start, no windows requested |
  | `k60_touch_se=1` 0 logs | **`ml_io_map` panics, earlier than any register access** |
  | `pong_audio=1 pong_aw882xx=1` 0 logs | same cause (audio has another 4 `ml_io_map` sites) |
  | all register-level fixes in the previous 3 rounds ineffective | **it never got as far as the registers** |

- **Also sharing the 8 MiB**: `0300-k60-usblog-ep0.patch` (10 sites), `0334` (7 sites),
  `0402` (8 sites), `0500` (4 sites), `0503` (4 sites), `0504` (5 sites) and others.

- **Fix** (conservative version, TLMM only):
  ```c
  // before: TLMM_SIZE = 0x200000 (2 MiB)
  // after:  TLMM_SIZE = 0x10000 (64 KiB), and rebase the base address to gpio_offset
  tlmm = ml_io_map(TLMM_PHYS + gpio_offset, TLMM_SIZE) - gpio_offset;
  ```
  Saves **1.94 MiB**. `GPIO_CFG(n) = tlmm + gpio_offset + 0x1000*n` is unchanged.

- **Why not shrink GCC**: the GCC offsets are spread over `0x0~0x27580` + `0x33000` + `0x62018`,
  **a span of 0x70000 that cannot be reduced to a single window**. Shrinking it needs splitting into 2 windows (`0x0~0x2000` and `0x12000~0x14000`),
  a large surface with high risk. Shrink TLMM first (saves 1.94 MiB, zero semantic change).

- **30-second check**: before any driver adds `ml_io_map`, compute the total budget.
  **Once the cumulative total approaches 8 MiB a panic is guaranteed, and it shows up as a "0-log hang" that will be misdiagnosed as a register access problem.**
  How to check: `grep -c ml_io_map` on each patch + add up SIZE by hand.

### P-64 Shrinking an MMIO window **must cover the largest pin offset**: a 64 KiB TLMM puts pin 20 out of bounds

- **Symptom**: after P-63 shrank `TLMM_SIZE` from 2 MiB to 64 KiB, `k60_touch_se=2`
  reached the GPIO part of `bring_up()` and hit a **kernel data abort**:
  ```
  K60KEXC msg=Kernel data abort. pc=0xfffffff00774e78c ... esr=0x96000010
          far=0xfffffff8c6f4a004
  x9:  0xfffffff8c6f4a000   x10: 0x0000000000000002
  Pong touch: DIAG mapped tlmm=0xfffffff8c6f4a000 ... (before rebase)
  ```
  `x10=2` is exactly the value `gpio_set(pin, true)` writes (GPIO_IO bit1 = output high).

- **Root cause**: the TLMM access offset is `gpio_offset + 0x1000*n`.
  The K60 touch pins `pins[] = {16,17,18,19,21,20}`, **max n = 21** →
  it has to reach `0x15000 + 4 = 0x15004`. But the 64 KiB window only goes to `0x10000`
  → **pin 20's `GPIO_IO(20) = 0x14004` falls outside the window** → data abort.

- **Exact recomputation**:
  ```
  mapped_base = tlmm + gpio_offset = 0xfffffff8c6f36000
  window range = [0xfffffff8c6f36000, +0x10000) i.e. upper bound 0xfffffff8c6f46000
  GPIO_IO(20) = reported_tlmm + 0x100000 + 0x1000*20 + 4
              = 0xfffffff8c6e36000 + 0x24004 = 0xfffffff8c6f4a004
  0x4004 bytes past the window
  ```

- **Fix**: `TLMM_SIZE` 64 KiB → **128 KiB (0x20000)**.
  Covers `0x15004` (pin 21) with 0xAFB4 to spare; still **16× smaller** than the original 2 MiB.

- **General lesson (more important than this bug)**:
  **Before shrinking an MMIO window, enumerate every access offset inside that window and take the maximum.**
  Formula: `size needed = max(offset) + access_width`, not "it looks big enough".
  ```bash
  # how to check: list every access offset
  grep -oE '(tlmm|gcc|se) \+ 0x[0-9a-f]+' <file> | sort -t+ -k2 -u
  ```

- **30-second check**: the `far` value of a data abort minus the mapping base is **the offset that went out of bounds**.
  Find it and work out which `#define X(n)` produced it.

### P-65 **The real break in the GENI clock chain: `CMD_ROOT_OFF` (bit31) is asserted, not DFS_EN**

- **Diagnosis trail (two wrong registers, both recorded)**:
  1. First assumed `DFS_EN` lived in the `CMD` register → wrote `CMD |= 1` → `cmd` still read back `0x80000000`, no effect
  2. Only then found the Linux definitions (`clk-rcg2.c:24-31`):
     ```c
     #define CMD_REG          0x0
     #define CMD_UPDATE       BIT(0)      ← CMD bit0 is "commit the config", not DFS_EN
     #define CMD_ROOT_OFF     BIT(31)     ← CMD bit31 = root off
     #define SE_CMD_DFSR_OFFSET 0x14
     #define SE_CMD_DFS_EN    BIT(0)      ← DFS_EN is in DFSR, not in CMD
     ```
  3. Our `dfsr = 0x21` → **bit0 had been 1 all along, DFS was enabled the whole time**

- **Real root cause**: `cmd = 0x80000000` → **`CMD_ROOT_OFF` bit31 = 1**
  Linux `clk-rcg2.c:74`:
  ```c
  return (cmd & CMD_ROOT_OFF) == 0;   // bit31=1 → root off → no clock out
  ```
  **While the RCG root is turned off, no frequency configuration (DFS or plain) produces a clock.**

- **Measured evidence (the key breakthrough)**:
  ```
  DFSEN post cmd=0x80000000 cbcr=0x80004220   ← after writing CMD, cbcr briefly goes ON (bit31=1)
  CLKPROOF se4_cbcr=0x4220                    ← but then flips back to OFF
  ```
  `cbcr` reaching `0x80004220` shows the **clock hardware itself works**, it just is not held properly.

- **Fix**:
  ```c
  /* 1. clear CMD_ROOT_OFF */
  wr(GCC_QUP0_SE4_CMD, rd(GCC_QUP0_SE4_CMD) & ~(1u << 31));
  /* 2. commit (CMD_UPDATE) */
  wr(GCC_QUP0_SE4_CMD, rd(GCC_QUP0_SE4_CMD) | 1u);
  for (500 iterations) { wait for bit0 to clear }
  ```

- **General lesson**:
  **Before changing an RCG, read the `CMD` register and check whether the root is on.** Only continue if `cmd & BIT(31)` = 0.
  That comes before checking the frequency table, the divider or the DFS gear.

- **30-second check**: when a clock produces nothing, the first step is to read `CMD` and look at bit31; if it is 1, clear it first,
  and only then talk about frequency configuration. Wrong order burns several rounds on the wrong register.

### P-66 **`CMD_ROOT_OFF` will not take a write: the RCG root is controlled by hardware authorisation, software cannot force it on**

- **Measured** (`evidence/usblog-20261109-190657`, kernel `09b0d5d0`):
  ```
  ROOT_ON pre  cmd=0x80000000 cbcr=0x80004220
  ROOT_ON post cmd=0x80000000 cbcr=0x80004220     ← cmd completely unchanged after the write
  CLKPROOF se4_cbcr=0x4220                        ← then it changed again
  ```

- **Fact 1: `CMD` bit31 (`CMD_ROOT_OFF`) will not take a write**
  after `wr(cmd, rd(cmd) & ~(1u<<31))` it still reads back `0x80000000`.
  → **this is a read-only status bit**; root enable is granted by hardware/firmware, not by software writing CMD.

- **Fact 2: CBCR bit31 semantics confirmed as CLK_OFF=1**
  | value | bit31 | meaning |
  |---|---|---|
  | `0x80004220` | 1 | **OFF** |
  | `0x4220` | 0 | **not OFF** |

  **Note**: at one point I read `0x80004220` as "ON", the direction was backwards, now corrected.

- **Fact 3: the clock state flips between two reads**
  during `clocks_on()` it is `0x80004220`(OFF), by the time of `geni_transfer()` it is `0x4220`(not OFF).
  So some other mechanism (HWCG gating / GCC vote / power domain) is controlling it dynamically.

- **Conclusion**: **enabling the RCG root is not under XNU software control.**
  To really turn the SE4 clock on you need:
  1. an **RPMh/RSC vote** (we are forbidden access, HR-01)
  2. or a **GDSC/power domain** (QUP has no GDSC, see the P-63 note)
  3. or **reliance on ABL having turned it on at Android boot** (requires verifying the Android-side clock state)

- **What this means for the touch fix**:
  even with every GENI register configured correctly, the FIFO escape opened and the right DFS gear selected,
  **as long as SE4's RCG root is not authorised, the SPI transfer will never complete**.
  This is an **architectural blocker**, not a driver bug.

- **30-second check**: write `CMD`, read back, unchanged → the bit is read-only.
  Stop trying writes on CMD/CBCR and go look at the authorisation path (RPMh / power domain / firmware).
### P-67 **The clock was running all along: `cbcr=0x4220` with bit31=0 means "not off"**

- **I read the CBCR semantics backwards two rounds in a row**; the correction in one place:

  | `CLOCK_OFF = (1u<<31)` | meaning |
  |---|---|
  | `0x80004220` | **bit31=1 → clock OFF** |
  | **`0x4220`** | **bit31=0 → clock running (not off)** |

- **Measured timeline** (`evidence/usblog-20261109-190657`, kernel `09b0d5d0`):
  ```
  during clocks_on():  se4_cbcr = 0x80004220   ← OFF
  at geni_transfer():  CLKPROOF se4_cbcr = 0x4220   ← not OFF = running
  ```
  **The clock turned itself on after `clocks_on()`** (very likely woken by `wr(GCC_QUP0_SE4_CFG...)` or by the GENI access).

- **Therefore**:
  - ❌ "the SE4 clock is not running" — **wrong**
  - ❌ "`CMD_ROOT_OFF` needs clearing" — **wrong** (the bit is read-only and the clock is already on)
  - ❌ "this is an architectural blocker" — **wrong**

- **The real blocker is back at the GENI engine**:
  ```
  GENI pre  status=0 clk_cfg=0x51 trans_cfg=0 word_len=0x4   ← config all correct
  GENI cmd0 readback=0x18000000                              ← command was accepted
  SPI transfer: status=0, sent=36, received=0                ← but never completes
  ```
  `status & M_CMD_DONE` never sets → `M_CMD_DONE` is not bit0!

- **The next step that must be verified**: whether the `M_CMD_DONE` bit definition in `GENI_M_IRQ_STATUS` (`se+0x610`)
  matches how we interpret `status`. We used `M_CMD_DONE = (1u<<0)`,
  yet `status=0x41` with bit0=1 was not recognised as DONE — **so the bit definition is probably wrong**.

- **30-second check**: to decide whether the clock is running, look only at `cbcr & (1u<<31)`.
  **bit31=0 = running**. Stop looking at bit30 (that is not an ON flag) or at any other bit.
### P-69 **A stage gate must be inserted before the dangerous call, not after it**

- **Symptom**: the newly added `k60_touch_se=7` (meant to be "bitbang only, never touch GENI/RPMh")
  **died with 0 logs** on device (`evidence/usblog-20261109-192255`, 0 B).

- **Root cause**: the gate was inserted **after** `io_supply_on()`:
  ```c
  if (!problem) {
      spi_transfer=geni_transfer;
      if (goodix_probe(false)) return true;
      if (touch_stage < 6) return false;      // stage 5 stops here
      if (io_supply_on()) { ... }             // ← stage 7 runs this too!
  }
  ...
  if (touch_stage < 7) return false;          // ← the gate is here, too late
  spi_transfer = bitbang_transfer;
  ```
  with `touch_stage=7`, `7 < 6` is false → execution continues into `io_supply_on()`
  → `rpmh_write()` → `wr(TCS(rsc+0xd00))` with `rsc=0` → **data abort on an invalid address**.

- **Fix (two places)**:
  1. `if (touch_stage == 6 && io_supply_on())` — only stage 6 is allowed to touch RPMh
  2. `if (attempt==0 && touch_stage == 6 && io_supply_on())` inside the bitbang loop
  3. **and at the very top of `bring_up()`** add `if (touch_stage >= 7) goto bitbang_only;`
     — so stage 7 skips `clocks_on()` / `geni_spi_init()` / the 200ms failing transfer entirely

- **General lesson**:
  **When adding a gate for a new stage you must confirm that, along the whole call chain, it sits before every dangerous call.**
  Adding `if (stage < N) return` in one place is not enough — if there is another
  `if (stage < M)` branch in between (M < N), the new stage "leaks" through those branches.

- **How to check**: after adding a stage, run `grep -n 'touch_stage'` over the whole file to list every gate,
  then walk them in execution order and confirm which path the new stage takes.

- **30-second check**: a new stage that dies with 0 logs on its first device boot → first check whether it slipped past some dangerous call,
  rather than suspecting the new feature itself.

### P-70 **K60 touch SPI pin roles: MISO is GPIO 17, not 16**

- **Background**: the FDT's `qupv3_se4_spi_active` only gives the pin **set**
  `pins = "gpio16\0gpio17\0gpio18\0gpio19"` (function `qup4`),
  and **does not say** which one is MISO / MOSI / CLK / CS.

- **Our original assumption (taken from the pong reference implementation, never checked)**:
  `MISO=16, MOSI=17, CLK=18, CS=19`

- **Measured (one sweep over 24 permutations, `evidence/usblog-20261109-195627`, kernel `7bfc16a4`)**:
  ```
  PERM0  miso=16 mosi=17 clk=18 cs=19  -> 00 00 00 00
  PERM7  miso=17 mosi=16 clk=19 cs=18  -> ff ff ff ff   ★
  PERM8  miso=17 mosi=18 clk=16 cs=19  -> ff ff ff ff   ★
  the other 22                         -> 00 00 00 00
  ```
  **What the two `ff` results share is `miso=17`** → **MISO is actually on GPIO 17**.

- **What `ff ff ff ff` means**: MISO is pulled high. The SPI idle state (CS not selected or the chip not driving)
  is usually **high**, so this line is **finally connected to the chip side**; whereas `00` means that line is not MISO at all
  (floating and pulled low, or wired wrong).

- **Correction**: the MISO/MOSI positions in `pins[]` have to be swapped:
  ```c
  // old (wrong): MISO=pins[0]=16, MOSI=pins[1]=17
  // new (right):  MISO=pins[1]=17, MOSI=pins[0]=16
  ```
  The remaining CLK/CS still have to be confirmed among the 6 combinations with `miso=17` (PERM6 `mosi=16 clk=18 cs=19`
  matches the Qualcomm standard order best).

- **General lesson**:
  **The FDT pinctrl `pins` property only guarantees "these four lines belong to this SE", not their order.**
  Before writing bitbang or hand-rolled SPI you must determine the roles by a measured permutation sweep (24 of them);
  you cannot copy them from another board. One sweep saves several rounds of guessing.

- **30-second check**: bitbang reads all `00` → MISO is wrong; reads all `ff` → MISO is very likely right,
  but the chip is not responding (check CS/CLK or the supply).

### P-71 **Do not judge completeness from the `status` field alone — read the measured records in `services.md`**

- **The mistake I made (2026-11-09 20:40)**:
  I looked at the input section of `pong.toml`, saw `status = "implemented"` and
  `completion = ["observe the interface actually working on device and save the corresponding log"]`,
  and concluded "pong itself never verified Goodix touch either". **That was wrong.**

- **Hard evidence** (`/mnt/e/hackios/UniXNU-pong/migration/ipados18/services.md`):
  | line | text |
  |---|---|
  | 296 | `touch/key HID events keep arriving` |
  | 315 | `touch HID events have reached the kernel` |
  | 321 | `backboardd and SpringBoard both reach running, with touch events` |

  **pong's Goodix Berlin-D touch was verified on real hardware.**

- **Why `status` misleads**:
  `status` is a **summary field of the record** and can lag behind the round-by-round measurements in `services.md`;
  and `completion` is the to-do list of **that record itself**, not the overall state of the project.
  **To decide whether a capability holds, you must read the REC (recorded) results in `services*.md`.**

- **Knock-on effects of that correction**:
  1. `pong_goodix.c`'s **Goodix protocol implementation is correct** (measured on pong)
  2. **the SPI pin mapping 16,17,18,19 is correct**
  3. the frame format of `goodix_read(0x10014)` is correct
  4. **the code ported to the K60 is fine in itself**
  5. **the only K60 difference is that RSC is unavailable → touch VDD cannot be powered**
  → the fix path collapses to one thing: "write PM8350C LDO2 directly over SPMI"

- **General lesson**:
  **When checking a project's capabilities, the `status` field is only an index; the evidence must come from `services*.md` / logs / screenshots.**
  Looking only at the toml fields leads to exactly the opposite conclusion.

- **30-second check**: to decide whether some capability "has been verified", first `grep -i '<capability>' migration/*/services*.md`,
  then look for `REC` plus a concrete symptom description. Do not look at `status =`.

### P-72 **A deliverable directory existing ≠ the subagent has delivered**

- **Time**: 2026-11-09 21:33
- **Symptom**: I saw that `impl/touch-power/` held `PMIC-RESEARCH.md`(26,933B),
  `SPMI-PROBE-PLAN.md`(22,024B), `SPMI-WRITE-PLAN.md`(18,936B) — 5 files in all —
  took it as "the PMIC power plan has been delivered", and reported conclusions like SID=2 / LDO2 base=0x4100 to the user.
- **Reality**: `EVIDENCE.md` was still being updated at 21:32:41 (my report was at 21:32:47, **6 seconds apart**),
  the subagent **was still working**, and those files were half-finished.
- **Lesson**:
  1. **Only a `finished` / `完成` message counts as delivered**
  2. how to tell: `ls -l --time-style=+%H:%M:%S` to see the newest file mtime,
     compare with `date +%H:%M:%S`; **a change within 2 minutes = still writing**
  3. half-finished work is only "reference material"; **it must not be used as a conclusion, and code must not be changed on the strength of it**
- **Why it happens**: the directory structure appears a few minutes into the task, and the files existing creates the illusion of "done".
- **Relation to HR-11**: HR-11 is "build artifact ≠ on-device state";
  this entry is the same cognitive error reappearing in the subagent setting: **treating "exists" as "done"**.

## Ledger maintenance rules

1. Once a new pitfall is confirmed, **append it on the spot** (in sync with ISSUES, do not wait for wrap-up).
2. The "30-second check" must be written as an action you can execute immediately or as a rejection rule, not a vague slogan.
3. The evidence column must hold something physical: file+line, log path, sha, commit. Where there is none, mark it "to be verified".

---

## Known issues in the ledger numbering (2026-11-09 audit)

| issue | explanation | handling |
|---|---|---|
| P-22 appears twice | the second one is "P-22 correction", a legitimate correction record | keep |
| P-25 missing | number skipped, possibly merged/deleted early on | keep the gap, do not renumber (renumbering breaks every external reference)|
| P-01~P-09 zero padding | early entries used `P-01`, later ones `P-10+` | nothing to do, match both forms when grepping |

**Maintenance rule addendum**: new entries keep using `P-NN` (two digits); **do not renumber history** — every document,
commit message and issue reply carries `P-NN` references.

### P-73 D/E two-tree drift: build from the D tree, edit code in the E tree → UFS S3 wasted (2026-11-10)

- **Symptom**: the UFS S1/S2/S3 patches were rebased and applied to `<repo>/drivers/NativeUfs/` (E tree),
  but `buildv15.sh` builds from `/tmp/usb-cdc-mainline/device` (D tree).
  D's `PongUfsTransport.cpp` is stuck at 30,473 B (pre-S1), E is already 44,096 B (final S3 state).
  → **none of the earlier boot images had UFS S1 compiled in at all!**
- **Root cause**: for historical reasons the plan was to "move D to E", then E's disk had enough space so it was never done, leaving two trees;
  buildv15.sh only syncs 5 patches + 3 PongAdreno drivers and **never syncs `drivers/NativeUfs/`**.
- **User ruling (2026-11-10 02:25)**: "the D tree and the E tree — the original idea was to move D onto E, later the D disk had plenty of space so there was no need
  now, to avoid stepping on the same pitfall over and over, only one of them should be kept"
- **Correct approach (2026-11-10 02:40, user's final ruling: `keep only the most stable one`)**: **keep D as the only build tree** (every successful build used it, and it has the firehose/libfirehose_kernel.a cache; making `D=E` triggers a missing `xcodebuild`). Keep E as a git repository and sync E→D by hand after changing code.
  - **`D=E` is forbidden**: it triggers `xcodebuild: command not found` from `scripts/build-firehose.sh` (WSL has no xcodebuild).
- **30-second check**: after editing sources under `drivers/`, first `grep` the build script for which directory its `-D` points at, then confirm the file you changed is in that directory.

### P-74 Build reports `xcodebuild: command not found` (firehose library not seeded) (2026-11-10)

- **Symptom**: the build fails at `scripts/build-firehose.sh: line 24: xcodebuild: command not found`,
  `build-xnu-4k-baseline.sh:348: bash scripts/build-firehose.sh failed`.
- **Root cause**: the guard at `build-xnu-4k-baseline.sh:280` is
  `if [ ! -f "$KERNEL_SDKROOT/usr/local/lib/kernel/libfirehose_kernel.a" ]`,
  and `KERNEL_SDKROOT=$ROOT/.cache/fakeroot`. The seeding loop in `buildv15.sh` only copies
  `OLDFR/usr/include`, `OLDFR/usr/local/include`, `OLDSRC`, and **misses `OLDFR/usr/local/lib`**
  → the guard decides the library does not exist → `build-firehose.sh` runs → WSL has no `xcodebuild` → failure.
- **Why it used to work**: an earlier version of the seeding did copy `usr/local/lib`, and it was deleted by accident when the script was changed later.
- **Correct approach**: the seeding loop must add:
  ```bash
  mkdir -p "$B/tree/.cache/fakeroot/usr/local/lib"
  [ -d "$OLDFR" ] && cp -a -n "$OLDFR/usr/local/lib/." "$B/tree/.cache/fakeroot/usr/local/lib/"
  ```
  `libfirehose_kernel.a` lives in `out3/.../tree/.cache/fakeroot/usr/local/lib/kernel/` (40,480 B).
- **30-second check**: `xcodebuild: command not found` in the build log → check whether
  `$B/tree/.cache/fakeroot/usr/local/lib/kernel/libfirehose_kernel.a` exists; if not, this is the entry.

### P-75 Skipping eight-step ③ (Android decompilation) → wrong touch protocol, stages 8-15 all wasted (2026-11-10)

- **Symptom**: touch from stage 8 to 15 was all built on the Berlin-D (BRL) protocol (`dev_confirm` writing 0x10000),
  and the chip did not respond at all. In the end, 10 minutes in Android root adb found: `compatible = xiaomi,m11a-spi`,
  driver `goodix_ts` (GTP protocol), and disassembling `goodix_core.ko` confirmed the GTP SPI frame 0xF1+4-byte BE address.
- **Root cause**: **③ (decompilation/forensics) of the eight-step process was skipped**. ①② (pong same model + official goodix_brl_hw.c)
  were done, but **the Android-side driver was never disassembled before writing code** to confirm the K60 chip's real protocol.
  K60 = M11A (GTP), pong = Berlin-D — the ① same-model premise was wrong to begin with, and ③ should have exposed it immediately.
- **Correct approach (iron rule HR-19)**: **for any hardware, ③ (Android-side forensics) must be completed before writing a driver**:
  1. `adb shell cat /proc/device-tree/.../compatible` — get the chip model
  2. `adb shell ls /sys/class/input/event*/device/name` — get the driver name
  3. `adb pull /vendor/lib/modules/<driver>.ko` + `llvm-objdump -d` — get the protocol frame format
  4. only after ③ is done can you move to ⑤ plan
- **30-second check**: before any "I'm starting on the <hardware> driver", first ask "has the Android-side .ko for that hardware been disassembled?"
  No → this entry; stop writing code and do ③ first.

---

### P-76 Not checking `UniXNU-zizhan` before starting = guaranteed wheel reinvention (2026-11-10)

**Symptom**: burned 20+ rounds on the touch SE4 GENI DMA problem, changed 15 config items, flashed a dozen times,
and finally found `E:\hackios\UniXNU-zizhan\patches\xnu-ipados18\0002-zizhan-fts.patch`
had the answer written long ago.

**Root cause**: `UniXNU-zizhan` is a **superset of pong**: same SM8475, same QUP0 SE4, same GPIO16-19 /
IRQ21 / RESET20. Its `bring_up()` says plainly:

```c
/* zizhan's SE4 firmware is loaded in GSI (DMA-only) mode: FIFO access is disabled,
 * so drive the same four pins as GPIOs */
printf("zizhan touch: GENI unavailable: %s; SPI by GPIO\n", problem);
spi_transfer = bitbang_transfer;
```

**Correct approach**: before any hardware work, run `<workspace>\scratch\hw-preflight.sh <hardware name>`;
it force-lists the artefacts that already exist for that hardware in zizhan/pong/sheng. If the list is not empty you must read it first.

**Recurrence count**: at least 3 times this session (touch GENI, Bluetooth `qbt_geni.c`, the official Chinese docs).

---

### P-77 Only `git fetch`, never `git pull`, so you judge from stale code (2026-11-10)

**Symptom**: `sync-upstream.sh` reported "behind: 32" but I kept judging from the old content.

**Measured gap** (2026-11-10 11:10):
| repository | before pull | behind |
|---|---|---|
| UniXNU | `75ae626` | 12 |
| **UniXNU-zizhan** | **`087416a`** | **32** |

**Correct approach**: the `hr` layer requires "verify the lag", but **verifying ≠ pulling**.
`hw-preflight.sh` now **forces `git pull --ff-only`** on every repository, and stops with an error if it cannot pull.

---

### P-78 Calling `rd()/wr()` with a physical address → data abort (2026-11-10, twice)

**Symptom**:
```
K60KEXC: far=0x0000000000990000   ← se_phys
K60KEXC: far=se + 0x1010          ← se_phys+0x1010 written as rd(se_phys+...)
```

**Root cause**: `rd()/wr()` take a **mapped virtual address**. `se_phys` (0x990000) is a physical address,
dereferencing it directly always crashes. Only `se`, as returned by `ml_io_map()`, is usable.

**Correct approach**:
- physical address constants always end in `_PHYS` and **appear only as `ml_io_map()` arguments**
- every register access uses only the mapped globals (`se`, `tlmm`, `gcc`…)
- before adding a register access, `grep` to confirm it uses the virtual variable

---

### P-79 Blindly probing "vendor private registers" resets the whole machine (2026-11-08/10, twice)

**Symptom**: after deleting the `IF_DISABLE_RO` check the machine went back to Android with no logs; writing `SE_DMA_IF_EN(0x2004)` panicked outright.

**Root cause**: on the K60, **a data abort is the expected behaviour** for `0x2004 / 0x2008 / 0x1010` —
they only appear in Linux 7.0.14's `geni_load_se_fw()`, and that function's entry requires the wrapper to have a
`firmware-name` property (`qcom-geni-se.c:1324-1328`), which K60's `qupv3_0_geni-se@9c0000` **does not have**.
Upstream Linux never writes them on the K60 either.

**Correct approach**:
- before writing any "register upstream does not have", first prove there is **a working instance on the same SoC**
  (Android disassembly / same-family device patch / vendor driver)
- `rd()` once before writing; if the `rd()` itself aborts, **never `wr()`**
- keeping an `if (0) { ... }` dead code block in the patch as documentation is right, do not delete it

---

### P-80 Doing only "protocol-layer decompilation" and not "controller-layer decompilation" (2026-11-10)

**Symptom**: I disassembled `goodix_core.ko` (protocol layer, confirmed the GTP frame),
but **never disassembled `spi-msm-geni.ko` (controller layer)**, so I kept guessing which DMA mode GENI uses.

**Correct approach**: ③ decompilation must be done **completely, layer by layer**:
| layer | target | K60 file |
|---|---|---|
| chip protocol layer | frame format/register addresses | `goodix_core.ko`, `xiaomi_touch.ko` |
| **controller layer** | **how the bus initialises/transfers** | **`spi-msm-geni.ko`**, `i2c-msm-geni.ko` |
| power/clock layer | regulator/clock ID | `dts`, `regulator` nodes |
| board layer | pins/interrupts | live FDT |

**Protocol layer only = the right language, but unable to speak.**

---

### P-81 Inferring zizhan's coverage from a one-line `summary` → serious misjudgement (2026-11-10)

**Symptom**: I read
`summary = "... thermal control, sleep/wake and daily-use qualification remain open"`
and
`limits = ["Outer display and audio remain disabled..."]`
in `porting.toml` and concluded "zizhan does not cover WiFi/Bluetooth/USB/baseband".

**Reality**: zizhan's `porting.toml` has **14 `[[area]]`** entries, each with its own `status`:

| area | status |
|---|---|
| configuration | host-verified |
| firmware | implemented |
| cpu | implemented |
| memory | implemented |
| storage | implemented |
| display | **implemented** |
| input | **implemented** |
| gpu | **implemented** |
| **network (WiFi)** | **device-verified** ← I said it was not covered, badly wrong |
| cellular | planned (genuinely not done)|
| audio | planned (genuinely not done)|
| power | implemented |
| packaging | host-verified |
| diagnostics | implemented |

**On-device evidence for `network` (the `findings` field of the same file):**
- g275: station-ready, 102 channels, 42 channels scanned, 15 networks
- g278: **real WPA2 association + key installation**
- g279: **native IPConfiguration gets DHCP**
- g290: default path initial HTTPS + renewal + disconnect cleanup + reconnect, **three HTTPS 200**
- g304/g306: **5220↔2452 MHz bidirectional cross-band reconnect**, three 200s each, no RDDM
- g309: **join from the native Settings UI**, WPA2 + DHCP + HTTPS 200
- g337: raw wifid + 64 MiB arena, one native association, HTTPS 200, **309 seconds without loss**
- g341: two independent DHCP REQUEST/ACK + two HTTPS 200

**`gpu` also has photo-level verification**:
- "User photos confirm GPU-rendered Home Screen and animations"
- g298: **95.3 moving fps** (baseline 56.7–58.4)
- g253/g254: **592/592, 403/403** GPU submits completed
- Weather/Clock/Settings/Photos screenshots complete, ASTC 135/135 columns

**Only 2 items are genuinely unimplemented**: `cellular` (components=[]), `audio` (planned).

**Correct approach (mandatory)**:
1. **To judge zizhan's coverage you must read every `[[area]]` + `status` in `porting.toml`**
2. **`summary` and `limits` only state the "remaining limitations", they do not mean "unimplemented"**
3. **each area's `findings` holds round-by-round on-device evidence (g2xx–g3xx numbering) and must be read**
4. when citing zizhan, give `porting.toml:line` + the `status` value

**Complication**: because I misjudged "zizhan hasn't done this", I once suggested "skip these pieces of hardware for now", which amounted to voluntarily
giving up 12 already-implemented reference implementations. That is the most serious misjudgement of this session.

---

### P-82 TLMM mapping window too small, every write to gpio71 (AVDD) lands outside it (2026-11-10)

**Symptom**: the touch AVDD power switch was "toggled but had no effect", and the chip never worked.

```
K60S19: gpio71(AVDD)  cfg=0        io=0x80000002 -> out_en=0 level=1
K60S19: gpio20(RESET) cfg=0x283    io=0x3        -> out_en=1 level=1
K60S19: gpio21(INT)   cfg=0x83     io=0      -> in=0
```

**The CFG of `gpio20/21` reads back normally, only `gpio71` is 0.**

**Root cause**: the address computation

```c
#define GPIO_CFG(n)  (tlmm + gpio_offset + 0x1000UL * (n))
tlmm = ml_io_map(TLMM_PHYS + gpio_offset, TLMM_SIZE) - gpio_offset;
```

physical address = `TLMM_PHYS + gpio_offset + 0x1000*n`, while the window is only `[0x100000, 0x120000)`:

| pin | physical address | old window |
|---|---|---|
| gpio20 | `0x114000` | ✅ inside |
| gpio21 | `0x115000` | ✅ inside |
| **gpio71** | **`0x147000`** | **❌ 0x27000 out of bounds** |

**`TLMM_SIZE = 0x20000` only covers up to gpio32, while AVDD is on gpio71.**

**Consequence**: `gpio_configure(71, ...)` writes to an unmapped address, **the write is dropped (or lands elsewhere), the CFG never takes effect**,
the AVDD power switch never opens → the chip is unpowered → `int=0`, MISO FLOATING, `dev_confirm 00 00 00 00`.

**Fix**:
```c
#define TLMM_SIZE  0x80000UL   /* covers pin 71 (needs 0x58000), still inside the 8 MiB io_submap */
```

**Lesson (same origin as P-81)**:
**read-back is what catches this class of "write succeeded but had no effect" problem.**
This session only saw the `cfg=0` evidence for the first time after 20+ rounds, and only because it adopted
ruby's P0 probe method (reading the GPIO CFG/IO registers back).

**General checklist (mandatory before writing GPIO)**:
1. compute the target pin's physical address: `base + offset + 0x1000*n`
2. confirm it is inside the `ml_io_map` window: `addr + 4 < base + size`
3. **after writing, read the CFG back and confirm `bit9` (output enable) really became 1**

### P-83 [TOUCH] k60_spmi_read reads at most 8 bytes at a time, big-window reads are fake data (2026-11-10)

**Assumption**: `k60_spmi_read(apid, 0x30, r, 48)` could read a 48-byte register window in one go.

**Measured**: what came back was the same 4 bytes repeated 12 times:
```
0x29b: +40 03 00 40 30 03 00 40  30 03 00 40 30 03 00 40
0x3f1: +40 00 00 ff 01 00 00 ff  01 00 00 ff 01 00 00 ff
```

**Cause** (source `k60_spmi_read`):
```c
wr(ch, (1u << 27) | (reg << 4) | ((len - 1u) & 7u));   /* len squeezed into 3 bits → 8 max */
uint32_t d0 = rd(ch + 0x18), d1 = (len > 4u) ? rd(ch + 0x1c) : 0;
for (i = 0; i < len; i++) buf[i] = ((i < 4u) ? d0 : d1) >> (8 * (i & 3));  /* i & 3 wraps */
```

**Conclusion**: at most 8 bytes of real data per read, and you must read register by register in small chunks.
**Stop trying**: 48/64-byte window dumps.

### P-84 [TOUCH] SPMI PPID is 12 bits, anything at 0x4000 and above never matches (2026-11-10)

**Assumption**: PMIC5 LDOs sit at PPID 0x4000-0x4FFF.

**Measured**: scanning that range gave zero output.

**Cause** (source `k60_spmi_find`):
```c
if (!map || ((map >> 8) & 0xfffu) != ppid) continue;   /* 12-bit mask */
```

**Conclusion**: PPID tops out at 0xFFF. PMIC peripherals in `(sid<<8)|pid` form:
- SID 2 (pm8350): 0x201..0x2ff
- SID 3 (pm8350c): 0x301..0x3fe
**Stop trying**: ranges at 0x4000 and above.

### P-85 [TOUCH] Applying ruby's MT6360 register offsets to pm8350c (2026-11-10)

**Assumption**: PMIC5 LDO `+0x40`=range, `+0x41`=vset, `+0x46`=EN.

**Measured** (usblog-20261110-185544, full 477-peripheral scan):
```
ppid=0x10f apid=85   en=e1 range=00 vset=01     ← SID1 PID 0x0f
ppid=0x20f apid=148  en=e1 range=00 vset=01     ← SID2 PID 0x0f
ppid=0x40f apid=230  en=e1 range=00 vset=01     ← SID4 PID 0x0f
ppid=0x70f apid=293  en=e1 range=00 vset=01     ← SID7 PID 0x0f

ppid=0x139 apid=92   en=c0 range=02 vset=00
ppid=0x339 apid=389  en=c0 range=02 vset=00
ppid=0x439 apid=234  en=c0 range=02 vset=00
```
**The same PID on different SIDs reads exactly the same value — we were reading common registers, not LDO voltages.**
**1.8V MATCH (range=0/vset=0x25) hit 0.**

**Root cause**: the `+0x40/+0x41/+0x46` offset group comes from
`references/ruby-bringup/docs/touch-goodix-9916r.md`, from an **MT6360** (MediaTek),
while the K60 is **pm8350c** (Qualcomm PMIC5). **The two register layouts are completely different and cannot be copied from one another.**

**Lesson**:
1. register addresses in a reference document are valid only for **the chip that document is about**
2. when copying a driver across platforms you can only copy the **architecture and flow**; register offsets must be re-found from that chip's datasheet or kernel driver
3. the tell-tale sign that "the offsets are wrong": **the value read is identical for the same PID on different SIDs**

**Next step**: find pm8350c's real PMIC5 LDO register layout (Linux
`qcom-spmi-regulator.c` / `pm8350c-regulator`, or zizhan's
`drivers/PongPower/PongRpmh.cpp`); ruby's MT6360 offsets cannot be used.

### P-86 [TOUCH] Wrong RPMh TCS slot: we used slot0, zizhan uses ACTIVE TCS4 (2026-11-10)

**Compared facts** (`UniXNU-zizhan/drivers/PongPower/PongRpmh.cpp` read in full, 55 lines):
```cpp
// zizhan
constexpr unsigned b = 0xd00 + 4*0x2a0;      // ACTIVE TCS4
constexpr unsigned other = 0xd00 + 3*0x2a0;  // ACTIVE TCS3 (leased by the GPU)
rsc.w(b+0x30, 0x10108);   // msgid
rsc.w(b+0x34, addr);
rsc.w(b+0x38, value);
rsc.w(b+0x10, 1);         // WAIT_FOR_COMPLETION
rsc.w(b+0x1c, 1);         // CMD_ENABLE
rsc.w(b+0x14, 1u<<16);    // ENABLE
rsc.w(b+0x14, (1u<<16)|(1u<<24));  // ENABLE|TRIGGER
```

```c
// ours
#define TCS(reg) (rsc + 0xd00 + (reg))    /* slot 0, not ACTIVE TCS4 */
```

**zizhan's comments state the slot allocation plainly**:
> "the vote is PongWifiPlatform.cpp's rawVote unchanged: APSS DRV2
> (0x17a20000), SLEEP0..2, ACTIVE3..4, WAKE5..6; **the GPU leases active TCS3,
> these clients share active TCS4** under one sleeping lock"

**The RSC base address is checked and matches** (`rsc_phys == 0x17a20000`, patch:82 has the DT check).
**MSGID matches too** (`0x10008 | 0x100 == 0x10108`).

**The only difference is the TCS slot.**

**Conclusion**: `io_supply_on()` writes to slot0, which may never be processed by RPMh at all,
so the ldoc2 voltage/enable was never actually issued — which matches the "wrote it but nothing happened" symptom exactly.

**The correct slot**: `0xd00 + 4 * 0x2a0 = 0x1780` (ACTIVE TCS4)

**zizhan also has precondition checks (we do not)**:
```cpp
unsigned caps = rsc.r(0xc), count = (caps>>12)&63, ncpt = (caps>>27)&31;
if (((rsc.r(0)>>16)&255) >= 3 || count < 8 || ncpt < 1 || !rsc.r(b+0x18))
    return fail("active TCS4 unavailable");
```
You must first confirm TCS4 is available, otherwise the write is void.

### P-87 [TOUCH] Wrong RPMh completion criterion: checking IRQ_STATUS instead of CMD_STATUS (2026-11-10)

**Measured** (usblog-20261110-190459, first round after the TCS4 fix):
```
goodix: RPMh caps=0x800c8104 count=8 ncpt=16 ver=0x20700 tcs4_idle=1
goodix: RPMh: timeout waiting for the request (register 0x4 = 0)
goodix: RPMh ldoc2 write failed
```

**All four precondition checks PASS** (TCS4 present, idle, ver 2<3, count 8>=8, ncpt 16>=1),
but `IRQ_STATUS` stayed 0 and the request timed out.

**zizhan's completion criterion (`PongRpmh.cpp`) is completely different:**
```cpp
unsigned st = rsc.r(b+0x3c),   // CMD_STATUS, not IRQ_STATUS
         idle = rsc.r(b+0x18);  // TCS_STATUS
if ((st & 0x10100) != 0x10100 || !idle) progressed = true;
if ((st & 0x10100) == 0x10100 && idle &&
    (progressed || (rsc.r(0xd04) & (1u<<4)))) { done = true; break; }
```

**Three differences:**
1. completion criterion = `CMD_STATUS(&0x10100)==0x10100 && TCS_STATUS(idle)`, not IRQ_STATUS
2. IRQ clearing uses the **RSC-level `0xd08` bit4**, not the TCS-level `0x08`
3. it needs a `progressed` flag to tolerate the race of "already idle before it ever started"

**Lesson**: RPMh has two sets of completion signals (TCS-level interrupt vs command status);
whichever the reference implementation picked must be copied, not guessed.

### P-88 The "0x10308 is not the report address" judgement is void; it becomes "the address is right but the chip produces nothing"

- **Symptom**: several external references (ruby §5.3, a PHK110 subagent) reached opposite conclusions on whether `0x10308` is
  the touch report address, which led to repeated address swaps.
- **Authoritative ruling** (2026-11-11, `docs/K60-TOUCH-DT-EVIDENCE.md`):
  - K60 DT `goodix,panel-max-x/y` = **14400 / 32000**
  - after walking the five tables with the vendor formula (`off=49`), IC_INFO `+138/+140` reads back
    **14400 / 32000**, exactly matching the DT
  - → **the walk is correct, `touch_address = 0x10308` is a valid address**
- **Corrected conclusion**: the address is not wrong, **the chip simply produces no data**
  (`0x10308` and `0x30084` both measured changed=0/12; only the `0x10400` diagnostic counter moves)
- **Lesson**: to decide whether an address is right, cross-check against the DT's authoritative value, not against external documents or
  an indirect symptom like "does the data change". **If the DT has panel-max, use it as the criterion.**

### P-89 "git push hangs" is not a network problem, it is WSL with no GitHub credentials waiting for a password

- **Symptom**: inside WSL `git push` gives no output and never returns; after `timeout` kills it, it is still "not pushed".
  It looks like "slow network" or "big files won't upload".
- **Real cause** (measured 2026-11-11):
  ```
  $ GIT_TERMINAL_PROMPT=0 git push --force origin main
  remote: No anonymous write access.
  fatal: Authentication failed
  ```
  WSL's git has **no credential helper at all**, so it tries to ask for a password interactively;
  run in the background there is no TTY → **blocked forever on HTTP 401**.
- **Fix**: **run the push on the Windows side** (Windows has gh credentials + the credential manager).
  ```powershell
  Set-Location 'E:\hackios\UniXNU-mondrian'
  $env:GIT_TERMINAL_PROMPT='0'
  git push --force --progress origin main
  ```
- **Diagnostic trick (the most important one)**:
  `ls-remote` / `fetch` go over **GET** (anonymous read → instant reply),
  `push` goes over **POST + auth**.
  **"ls-remote works but push hangs" = an authentication problem, not a network problem.**
- **Cost**: fiddling with postBuffer, changing the HTTP version, rewriting history with filter-repo (the last one was
  necessary in itself but unrelated to the hang) — over 1 hour wasted.
- **After switching to Windows**: 21.77 MB / 8497 objects pushed in one go, in under a minute.
- **Registered iron rule**: HR-48

### P-90 Editing `patches/xnu/series` has no effect — the build overwrites it with `SERIES-FINAL.txt`

- **Symptom**: I added a patch name to `patches/xnu/series`, but the patch never appears in the build log,
  and the `patches applied` count does not change either.
- **Real cause**: `buildv15.sh:12` (and the packaging script chain) runs every time
  ```bash
  cp -f <workspace>/scratch/SERIES-FINAL.txt \
        <repo>/patches/xnu/series
  ```
  **the repo's `series` is an artefact, not the source.**
- **Fix**: edit `<workspace>/scratch/SERIES-FINAL.txt`.
- **How to verify**: after adding it, first `grep <name> SERIES-FINAL.txt`, then build,
  and confirm `== kernel: patch <name>` shows up in the log.
- **Lesson**: in this project the source of truth for patch order is `scratch/SERIES-FINAL.txt`,
  not the repo's `patches/xnu/series`. In the same way `buildv15.sh` overwrites other files from elsewhere;
  before changing any build-related file, `grep` `buildv15.sh` for a `cp -f` onto it.

### P-92 Two patches inserting at the same hunk anchor, the second one always fails

- **Symptom**: after adding `0391-k60-embedded-init.patch` to the series,
  `0394-k60-launchd-cache.patch` immediately reported
  `error: patch failed: bsd/kern/kern_exec.c:8078 / patch does not apply`.
  Adjusting the hunk line number (+37) still failed, only the number changed (8115).
- **Real cause**: the two patches' **context is identical**:
  ```
  0391 hunk1:  @@ -8078,6 +8078,43 @@
   }
   #endif
   <blank line>
  +（0391 inserts 37 lines）

  0394 hunk1:  @@ -8078,6 +8078,44 @@
   }
   #endif
   <blank line>
  +（0394 inserts 44 lines）
  ```
  after 0391 is applied, that `}\n#endif\n\n` position is already occupied by 0391's content,
  and 0394's context can never match again. **Changing line numbers alone does not help, because the content changed.**
- **Correct solutions (ordered by reliability)**:
  1. **Merge the later patch into the earlier one** (insert at the same place, the two become one patch)
  2. Change the later patch's context to "the last few lines the earlier patch inserts"
     (workable but fragile; it breaks the moment the earlier patch changes)
  3. Move the later patch to a different insertion point (find another `}\n#endif\n\n` in the same file)
  4. Remove the later patch for now, get the build green, merge afterwards
- **What was done here**: option 4 (removed 0394 for now, launchd cache deferred),
  because touch is the current priority and 0391 (init embedded) is the prerequisite for the Metal deployment.
- **How to tell**:
  ```bash
  # the two patches' hunk header line numbers are identical or close → highly suspect
  grep -n '^@@' <patchA> | head -3
  grep -n '^@@' <patchB> | head -3
  ```

### P-93 Union-mounting /private/var/pong onto /System/Library/Extensions panics pid 1

- **Symptom**: after adding
  ```c
  {"/private/var/pong", "/System/Library/Extensions"},   // MNT_RDONLY|MNT_UNION
  ```
  it panics on boot, and **does not auto-reset**:
  ```
  dyld[1]: Library not loaded: /usr/lib/libSystem.B.dylib
  Reason: tried: '/usr/lib/libSystem.B.dylib' (no such file, no dyld cache)
           '/private/preboot/usr/lib/libSystem.B.dylib' (no such file)
  K60PANICARGS initproc failed to start -- exit reason namespace 6 subcode 0x1
  CACHE st=6 err=0 mnt=0 ro=1 un=1 rr=1 ca=1
  ```
- **Real cause**: the union on `/System/Library/Extensions` breaks the shared cache's path resolution.
  launchd (the real init) fails to load `libSystem.B.dylib` → pid 1 exits → panic.
- **Why it was not caught earlier**: `prepare_metal_bundle()` and the union view went in as one change,
  and `0391` never made it into the series, so this init version panicked the first time it actually ran.
- **Lesson**:
  1. **Anything mounted onto `/System/Library/*` must be verified in isolation** — these paths take part in
     dyld shared cache resolution; breaking them breaks the whole userland boot.
  2. `prepare_metal_bundle()` (file copy only) and the union view (changes the mount layout) **must be verified in two separate steps**,
     so that when something breaks you can tell which one did it.
  3. `st=6` in this panic is a **result**, not the cause (cache load failure);
     earlier debugging experience will mislead you toward a cache patch.
- **Current handling**: remove the union view, keep the file copy; once boot is stable, study separately
  the correct way to mount `/System/Library/Extensions` (probably first confirm the coupling between the dyld cache and the
  Extensions directory, or point MetalPluginName at another path).

### P-94 The init blob must be the 35160 version, not the 53728 built by hand against the MacOSX SDK

- **Symptom**: an init (53,728 B) built on the Mac with `clang -target arm64-apple-ios16.6.1` (**no -isysroot,
  only the MacOSX SDK**) and pushed into 0391 gave
  `dyld[1]: Library not loaded: /usr/lib/libSystem.B.dylib` on boot, and a panic.
- **Comparison evidence**:
  ```
  35160 version (historical, boots):
      ncmds=9,  sizeofcmds=0x470
      strings include: "Pong init: exec original 20G81 launchd; stdin/stdout ->
                 /dev/null, stderr -> /dev/console"
               "Pong init: non-interactive launchd descriptors failed: errno=%d"
  53728 version (built by hand):
      ncmds=10, sizeofcmds=0x450      <- one load command more
      missing the two launchd redirect log lines
  the shared prefix is only 16 bytes, a completely different binary
  ```
- **Real cause**: `build.py:compile_init` uses
  `xcrun --sdk iphoneos clang ... -isysroot <iPhoneOS SDK>`
  to build the 35160 version. **The Mac only has CommandLineTools, no iPhoneOS SDK**,
  so when building by hand I dropped `-isysroot` and clang fell back to the MacOSX SDK
  (warning: `using sysroot for 'MacOSX' but targeting 'iPhone'`).
  The resulting Mach-O has a **different load command layout**, and
  **the code that redirects stderr to /dev/console behaves differently**, so launchd comes up and cannot find libSystem.
- **Lesson**:
  1. **"it looks like it compiles" is no substitute for "it runs"**. Both inits are valid
     arm64 Mach-O, both pass `codesign`, yet one boots and one panics.
  2. **after changing init.c you must confirm the produced blob's `ncmds`/`sizeofcmds` match the
     version known to boot**:
     ```bash
     python3 -c "
     import struct
     d=open('init','rb').read()
     print('ncmds=%d sizeofcmds=%d' % (struct.unpack_from('<I',d,16)[0],
                                        struct.unpack_from('<I',d,20)[0]))"
     ```
  3. **Correct approach**: either install the iPhoneOS SDK on the Mac (full Xcode),
     or point `-isysroot` at a real SDK; **it cannot be omitted**.
  4. 0391's blob stays at **35160** until a structurally identical binary can be rebuilt under the correct SDK.

### P-95 The iPhoneOS SDK sits at a custom path on the Mac, so `xcrun --sdk iphoneos` cannot find it

- **Symptom**: `xcrun --sdk iphoneos --show-sdk-path` reports
  `SDK "iphoneos" cannot be located`, so we concluded "the Mac has no iOS SDK",
  and went off to research how to install Xcode (needs an Apple ID, a 15 GB
  download, and is not needed at all).
- **True cause**: the SDK is at **`/Users/emilelu/ios-sdk/iPhoneOS16.5.sdk`**,
  while `xcrun` only searches `/Library/Developer/CommandLineTools/SDKs/` and
  `/Applications/Xcode*/Contents/Developer/Platforms/*/Developer/SDKs/`.
  **xcrun never finds an SDK at a custom path, but clang works fine with `-isysroot`.**
- **Correct approach**:
  ```bash
  SDK=/Users/emilelu/ios-sdk/iPhoneOS16.5.sdk
  clang -target arm64-apple-ios16.6.1 -isysroot "$SDK" ...
  ```
- **Consequence of not using `-isysroot`** (this is what actually caused the panic, see P-94):
  clang falls back to the MacOSX SDK and produces a Mach-O with `ncmds=10`
  and `DYLD_INFO_ONLY`; the correct SDK produces `ncmds=9` with no
  `DYLD_INFO_ONLY`.
  | version | size | ncmds | has DYLD_INFO_ONLY | boots |
  |---|---|---|---|---|
  | **35160 blob (correct)** | 35160 | **9** | no | ✅ |
  | has SDK, unsigned | 34704 | 9 | — | (to be verified) |
  | no SDK (MacOSX), after signing | 53728 | **10** | **yes** | ❌ panic |
- **Diagnostic command (must run after any init change)**:
  ```bash
  python3 -c "
  import struct
  d=open('init','rb').read()
  n=struct.unpack_from('<I',d,16)[0]
  print('ncmds=%d size=%d' % (n, len(d)))
  # walk the load commands looking for DYLD_INFO_ONLY(0x80000022)
  off=32
  for i in range(n):
      cmd,sz=struct.unpack_from('<II',d,off)
      if cmd==0x80000022: print('  !! DYLD_INFO_ONLY present - wrong SDK')
      off+=sz"
  ```
- **Lessons (both HR-44/HR-49 hit this)**:
  1. **`xcrun` cannot find it ≠ the machine does not have it**. Run
     `find / -name 'iPhoneOS*.sdk'` before concluding.
  2. This session went a whole lap on it: checking the CDN, checking direct
     Xcode links, discussing whether an Apple ID was needed,
     **while the SDK had been lying on the Mac all along**.
  3. **Any conclusion of the form "tool/resource X does not exist" must first be
     confirmed machine-wide with `find`**, not from the failure of one query
     command.

### P-96 Three hard git apply requirements every hand-written patch hits (0404 was reworked 4 times over this)

- **Symptom**: the newly written `0404-k60-metal-deploy.patch` reported over and
  over at build time:
  ```
  /patches/xnu/0404-...patch:250: new blank line at EOF.
  error: patch failed: bsd/conf/files:106
  error: bsd/conf/files: patch does not apply
  error: corrupt patch at line 250
  ```
  Fix one place, another reports; 4 rounds back and forth.
- **Three independent causes**:
  1. **`new blank line at EOF`**
     If the last line of a new-file hunk (`@@ -0,0 +1,N @@`) is a bare `+`
     (meaning an empty line), `git apply` rejects it. **The last line of a new
     file must be a real content line.**
  2. **N in `@@ -0,0 +1,N @@` must equal the actual number of `+` lines**
     Deleting a blank line without updating N → `corrupt patch at line <line
     number of the next diff>`. `patch -p1` also reports `malformed patch`.
  3. **For large files like `conf/files` the hunk context must match word for word**
     The context I wrote was "memdev.c / mem.c / +new",
     but in the real file there is also `k60_usblog.c` between the two.
     **You must read the real content from the build tree first**:
     ```bash
     sed -n '104,116p' <xnu-work>/bsd/conf/files | cat -A
     ```
- **Correct procedure (mandatory after every hand-written patch)**:
  ```bash
  # 1) auto-fix hunk line counts and bare blank lines (generic scripts, see TOOLBOX)
  python3 <workspace>/scratch/fix_hunk_counts.py
  python3 <workspace>/scratch/fix_bare_lines.py

  # 2) verify with the same judgement the build uses (git apply, not patch)
  cd <xnu-work> && git apply --check <patch>
  # it must print nothing to pass; patch --dry-run passing ≠ git apply passing

  # 3) when the context is uncertain, read the real file first
  sed -n '<line>,<line>p' <xnu-work>/<target> | cat -A
  ```
- **Lessons**:
  1. **`patch --dry-run` and `git apply --check` judge differently**: the former
     tolerates fuzz, the latter is strict. **If the build uses git apply, you
     must verify with git apply.**
  2. The existing `fix_hunk_counts.py` / `fix_bare_lines.py` **originally only
     knew two or three hard-coded touch patch paths**, so new patches were never
     processed at all → changed to **scan `patches/xnu/*.patch` by default, and
     also accept a path argument**.
     **A tool that only works on specific files is no tool at all.**
  3. When writing a new-file hunk, **do not leave a bare `+` as the last line**;
     compute N in the hunk header with a script, do not count it by hand.

### P-97 `k60_panic_reset` was never passed, so the device never resets after a panic

- **Symptom**: after a kernel panic the device sits on the panic screen and never
  returns to fastboot, no matter how long you wait; yet `k60_autoreset=300` was set.
- **True cause**: the entry point at `0334-k60-panic-reset-fastboot.patch:371-392`
  is separate:
  ```c
  void k60_panic_reset_to_fastboot(void)
  {
      if (!k60_usblog_running) return;
      if (!PE_parse_boot_argn("k60_panic_reset", &enabled, sizeof(enabled)) ||
          !enabled) {
          return;                       /* not passed, return immediately */
      }
      printf("K60PANIC: ring kept; restart reason -> bootloader\n");
      k60_usblog_reset_to_fastboot();
  }
  ```
  **`k60_panic_reset` and `k60_autoreset` are two different switches**:
  the former is "reset after a panic", the latter is "reset after running N
  seconds normally". Our boot-args only ever had the latter.
- **Discriminator**: the panic log has `K60PANIC: restart windows ready` (0334 is
  loaded), but **no** `K60PANIC: ring kept; restart reason -> bootloader` (blocked
  by the boot-arg).
- **Correct approach**: add `k60_panic_reset=1` (18 characters) to boot-args; for
  freeing space see P-98.
- **Lesson**: **for panic/reset switches, first check which function reads which
  arg**, do not assume `k60_autoreset` covers the panic path.

### P-98 After deleting `k60_skip_iosurface=1` the kernel no longer brings up even a console

- **Symptom**: to free characters for `k60_panic_reset=1` I deleted
  `k60_skip_iosurface=1`; after flashing **COM5 does not even enumerate**,
  the log is 0 bytes, it dies earlier than a panic.
- **Conclusion**: **`k60_skip_iosurface=1` is currently required**, it cannot be
  deleted to free characters.
- **Priority for freeing characters correctly** (low risk → high risk):
  1. ~~`epoch=1793709100` (16) — there is a default in init.c~~
     **⚠️ Disproved (P-106)**: after deleting epoch the launchd timestamp became
     1970, which affects its event scheduling. **Do not delete epoch.**
  2. `k60_touch_delay=12000` (21) — the source default is already 12000
  3. `k60_touch_diag=0` (17) — the source default is 0 already (completely redundant)
  4. `k60_touch_bb_us=2` (17) — the source default is already 2
  **Never touch** (missing them causes the "0-byte log" false hang, see P-118):
  `debug=0x140`, `applog=1`, `k60_console_export`, `k60_usblog`, `epoch`.
  **Do not touch**: `k60_skip_iosurface`, `pong_software_keybag`,
  `amfi_get_out_of_my_way`, `cs_enforcement_disable`.

### P-99 codesign produces a 19 KB signature while the bootable init has only 408 B (use ldid-lite)

- **Symptom**: signing init with the Mac's own
  `codesign --force --sign - --pagesize=4096`, the file grew from 34,704 B to
  53,248 B (18,544 B signature) and the boot panicked; the bootable init blob is
  only 35,160 B (408 B signature).
- **True cause**: parse the CodeDirectory of both:
  ```
  bootable (35160): version=0x00020400  nCodeSlots=9  hashSize=32
                    pageSize=12 (4096)  total signature 408 B
  macOS 26 codesign: newer version, more slots → 18,544 B (45x)
  ```
- **Correct tool**: **`<workspace>/scratch/ldid-lite.py`** (already local)
  ```python
  """CodeDirectory 0xfade0c02, version 0x20400, ... PAGE = 4096"""
  ```
  Usage: `python3 ldid-lite.py <macho> [identifier]`
- **Another necessary precondition** (see P-100): `-sectcreate __TEXT __entitlements`.
  The `__TEXT` segment of 35160 has an `__entitlements` section (237 B),
  put there by the **linker**, not by the codesign blob.
- **Diagnostic command**:
  ```bash
  python3 -c "
  import struct
  d=open('init','rb').read()
  n=struct.unpack_from('<I',d,16)[0]
  off=32;cs=None
  for i in range(n):
      c,s=struct.unpack_from('<II',d,off)
      if c==0x1d: cs=struct.unpack_from('<II',d,off+8)[1]
      off+=s
  print('ncmds=%d cs=%s (expected 9 / ~408)' % (n,cs))"
  ```

### P-100 ldid-lite needs free space at the end of load commands, and `-headerpad` has no effect on static links

- **Symptom**: `ldid-lite.py` reports `no room in load commands for LC_CODE_SIGNATURE; abort`.
- **True cause**: it requires `end_cmds + 16 <= 32 + sizeofcmds`.
  After a normal clang compile `sizeofcmds` equals the actual usage exactly,
  with no 16-byte slack.
- **Tried and ineffective**: `-Wl,-headerpad_max_install_names`, `-Wl,-headerpad,0x400`
  — **ld64 ignores headerpad on static freestanding links**, `sizeofcmds` does not change.
- **How 35160 did it**: its `sizeofcmds=1136`, 32 B smaller than the 1168 of a
  comparable build, meaning some load command was dropped, so there was room.
- **Current state**: **unresolved**. Options:
  1. Find which clang/ld version and flags 35160 was built with back then
  2. Change `ldid-lite.py` so it extends the `__TEXT` header page and rewrites the
     offsets (what codesign_allocate does)
  3. **Work around it**: the 35160 init is functional enough (see P-101)

### P-101 The 35160 init is already good enough; init does not need rebuilding for the Metal deploy

- **Background**: I had always assumed init had to be rebuilt to deploy the Metal
  bundle. In fact:
- **The 35160 blob already has** (verified from 22 `Pong init:` log lines):
  ```
  Data mount / var seed / calendar
  boot view <source> -> <target> result=%d     ← generic bindfs mount loop
  /private/var/pong/boot-jobs -> /pong/LaunchDaemons
  /private/var/pong/libpong-ui.dylib
  exec original 20G81 launchd; stdin/stdout -> /dev/null, stderr -> /dev/console
  ```
  **It has a generic boot view mechanism, and it sets launchd's stdio correctly.**
- **What it does not have** (the two things I added, both optional):
  - `unpack_boot_jobs` — the 350 build uses the `/pong/LaunchDaemons` path
  - `prepare_metal_bundle` — **replaced by the kernel-side 0404 patch**
- **Conclusion**: **the Metal bundle goes through the kernel-side `0404-k60-metal-deploy.patch`**,
  init stays at 35160. That avoids the whole "rebuild init → SDK → codesign →
  ldid-lite → headerpad" pitfall chain.
- **Lesson**: **before rebuilding a "working binary", verify that the new feature
  really cannot do without it.**
  The kernel side can often do the same thing (0340 deploying libpong-ui is the precedent).

### P-102 "Generalising" the fix tool instead corrupted 10 patches that were fine

- **Symptom**: after changing `fix_hunk_counts.py` from "only handle the three
  hard-coded touch patches" to "scan `patches/xnu/*.patch` by default", one run
  printed:
  ```
  0300-k60-usblog-ep0.patch:       1 hunk(s) fixed
  0340-k60-uilib-deploy.patch:     1 hunk(s) fixed
  0500-k60-bt-qbt-new-files.patch: 17 hunk(s) fixed
  zzz-boot-progress.patch:         1 hunk(s) fixed
  ...(10 patches changed in total)
  ```
  Those patches **all applied fine before**; the tool "fixed" them into breakage.
- **True cause**: the script recomputed N of every `@@ -0,0 +1,N @@` from "the
  number of lines that follow", but those patches' N values were already correct;
  the script's recomputation logic disagrees with the intent at boundaries such as
  **across hunks / trailing blank lines**, so it turned correct values into wrong ones.
- **Immediate handling**:
  ```bash
  cd <repo> && git checkout -- patches/xnu/     # roll everything back
  # then redo only the target patch, passing its path explicitly
  python3 fix_hunk_counts.py <target patch>
  ```
  **Note**: `git checkout -- patches/xnu/` also restores **already-committed**
  target patches to the old version, so those edits have to be redone.
- **Correct design (already changed)**: `fix_hunk_counts.py`'s default behaviour is
  now **to process no file when no path is given**; a path must be passed explicitly.
- **Lessons (additions to ★15)**:
  1. **A bulk-modifying tool must default to "do nothing"**, not "scan everything".
     The blast radius of scanning everything is unbounded.
  2. **Before any bulk modification record the baseline with `git status`**, and
     compare with `git status` right after, keeping only the files you expected.
  3. **The fix tool itself must be verifiable**: after running, `git apply --check`
     every patch and confirm nothing got worse.

### P-103 Using mount/mkdir/kalloc in the kernel needs three specific headers

- **Symptom**: `0404-k60-metal-deploy.patch` compiled with 6 errors:
  ```
  error: call to undeclared function 'kalloc'
  error: call to undeclared function 'kfree'
  error: variable has incomplete type 'struct mount_args'
  error: call to undeclared function 'mount'
  error: variable has incomplete type 'struct mkdir_args'
  error: call to undeclared function 'mkdir'
  ```
- **True cause**: incomplete headers. `<sys/mount.h>` is not enough.
- **Correct answer**:
  ```c
  #include <sys/mount.h>
  #include <sys/mount_internal.h>   /* struct mount_args / mkdir_args, mount(), mkdir() */
  #include <sys/vfs_context.h>
  #include <kern/kalloc.h>          /* kalloc() / kfree() */
  ```
  `struct mount_args`, `struct mkdir_args`, `mount()`, `mkdir()` are all in
  `<sys/mount_internal.h>` (basis: `bsd/vfs/vfs_syscalls.c:86`).
- **Diagnostic commands**:
  ```bash
  grep -rn 'struct mount_args' <xnu-work>/bsd/sys/*.h
  grep -rn 'struct mkdir_args' <xnu-work>/bsd/sys/*.h
  grep -n 'include' <xnu-work>/bsd/vfs/vfs_syscalls.c | grep mount_internal
  ```
- **Lesson**: when writing a new kernel file, **first find the existing
  implementation of the same kind of function and copy its include list**
  (here `vfs_syscalls.c`); far faster than guessing yourself.

### P-104 The init that always ran on the device is not in git, it is in `/tmp/init-v10guard/` and `/tmp/initbuild/`

- **Symptom**: after enabling `0391-k60-embedded-init.patch` the device went from
  "runs to launchd pid 282" to "panics every time:
  `Library not loaded: /usr/lib/libSystem.B.dylib`".
  Swapping the blob back and forth between `35160` / `53728` made no difference,
  and for a while I suspected the dyld cache was broken.
- **True cause**: **every historical version of 0391 in git is the other branch's init**,
  whose log signature is `Pong init: static 20G81 helper entered` +
  `Pong init: HackiOS userland adapter / iOS 16.6.1 20G81 / static arm64`.
  The init that actually ran on the device logs `Pong init: HackiOS adapter [v10guard]`,
  and its binary **was never committed**; it only existed in:
  ```
  /tmp/init-v10guard/init-v10guard   34,880 B  ncmds=9  cs=416   ← this one ran
  /tmp/init-v10guard/init.c          15,683 B  ← source
  /tmp/initbuild/init-v13dylc ~ init-v24dp   (24 iteration versions)
  ```
  Once `0391` took effect (`k60_init_blob=1` really started executing), it
  overwrote `/private/var/pong/init` with the broken init from git, and the
  working copy was lost from then on.
- **Diagnostic command (30 seconds)**:
  ```bash
  # which branch is in the log
  grep -a 'Pong init: HackiOS' <console.log>
  #   "HackiOS adapter [v10guard]"              → the line that runs
  #   "HackiOS userland adapter / ... static"   → the one from git, panics
  ```
- **Correct answer**: use **`/tmp/initbuild/init-v24dp`** (the last version of the `v10guard` line)
  - 34,904 B, `ncmds=9`, `cs=408` (consistent with the working shape)
  - 28 log lines = `v10guard`'s 26 + 2 (`disabled.plist`), a **strict superset**
  - contains `Pong init: native Metal entry enabled for backboardd`
  Already written into the `0391` blob (`K60_INIT_BLOB_LEN 34904`).
- **Lessons (the strongest case of ★25 "compiles ≠ runs")**:
  1. **A "binary that boots" must land in the repository first**, otherwise one
     effective patch loses it forever.
     `/tmp` is not storage.
  2. **Do not judge an init version by filename or size**, look at the
     **combination of signature strings** in the log (P-21).
  3. **When `k60_init_blob=1` goes from a no-op to actually taking effect**, you
     must realise it **overwrites** the file currently on the device — that is a
     destructive operation, not a harmless switch.
  4. `find / -name 'init*' | strings | grep <signature>` is far faster than
     flashing one build at a time.

### P-105 `/System/Library/Extensions` is neither writable nor necessary (where the Metal seeds really go)

- **Symptom**: 0404 tried `mkdir("/System/Library/Extensions/PongAdrenoMetal.bundle")`
  → `error=30` (**EROFS**), then bindfs was not done either, and the boot panicked.
- **True cause**:
  1. On the sealed root (OS volume `incompatible 0x8`) `mkdir` returns `EROFS`,
     and `bindfs` returns `EPERM` — **P-27 measured every variant on 2026-11-08**,
     and wrote "30-second check: on result=-1 errno=1, stop trying bindfs".
  2. **More to the point: this path was never needed at all.**
     `drivers/PongMetal/PongMetalPlugin.mm:174`:
     ```objc
     for (const char *directory : {"/System/Library/Extensions",
                                    "/private/var/pong"}) {
     ```
     `selectedClient()` **already searches two directories**, `/private/var/pong` is
     the fallback. The two seed files (`PongAdrenoMetal.publish` / `.clients`,
     0644, root) just have to sit in `/private/var/pong/` to pass.
- **Correct answer**: the Metal deploy only **copies files** into
  `/private/var/pong/`, **it does not mount anything**.
- **Lessons**:
  1. **Read the consumer's code before mounting anything**, and confirm which
     paths it actually reads. This cost a whole extra round doing something the
     consumer never required.
  2. **Treat a conclusion already written in P-27 as an iron rule**, do not retry
     bindfs (this was the second time on the same rake).

### P-106 With init fixed the whole userland came up (the biggest breakthrough of this round)

- **What was fixed**: the `0391` blob was replaced with `/tmp/initbuild/init-v24dp`
  (the `v10guard` line, 34,904 B, `ncmds=9`, `cs=408`), and the contents of
  `0394-k60-launchd-cache` were merged into `0391`'s hunk1 (P-92 option 1: the same
  anchor must be merged), while `epoch=1793709100` was restored (it had been
  deleted to free boot-args, which turned the launchd timestamp into 1970).
- **Result (`usblog-20261111-115745`)**:
  ```
  log 120,907 B / 1879 lines         (a panic run had only 41-50 KB before)
  PANICARGS = 0                     (no panic)
  max pid = 234
  SpringBoard: up
  backboardd: up
  MiniIOMobileFramebuffer: 301 frames in 5001 ms (60 a second), 2492 us each
  K60 ex=504 kx=74 abn=24 | mem=4864 free_pages=435130
  ```
  **Real 60fps rendering is running, the whole iOS userland is up.**
- **PONG ADRENO full chain result=0** (the GPU really started):
  ```
  GPU SMMU actual IDs          result=0
  GMU firmware/HFI             result=0
  GMU power handshake          result=0
  CP ME_INIT drained           result=0
  PAS13 ZAP auth               result=0
  CP ready; authenticated nonsecure fence result=0
  CP/user-client startup       result=0
  PONG METAL: real IOAcceleratorES provider published for20G81 discovery
  ```
- **Note**: `PONG ADRENO: startup requested; no accelerator published` is the
  **first breadcrumb** from `PongAdrenoPlatform.cpp:334` (`record()` at the top of
  `run()`), not an error. The whole of `run()` from line 334 down succeeds.
  **Do not be misled by that line.**
- **Lesson**: `epoch` is not optional — delete it and launchd's time base becomes
  1970, which affects its event scheduling. **When freeing boot-args, delete the
  genuinely redundant items first** (in P-98's list `epoch` was labelled "low
  risk", and that judgement was wrong).

### P-107 The Metal seed files never made it into the payload, and 0404's short-circuit criterion hid it

- **Symptom**: the GPU chain was all `result=0`, `PONG METAL: real IOAcceleratorES provider published`
  appeared too, but the Metal plugin was not loaded and the dock had no blur.
- **Root cause chain (two independent errors compounding)**:
  1. **`docs/DATA-VOLUME-DEPLOY.md:49-50` claims the payload already carries the two
     seed files. It does not**:
     ```
     mdir -i payload.img ::/METAL
       PONGAD~1 BUN  <DIR>   ← only the bundle
       (no PONGAD~1.PUB / PONGAD~1.CLI)
     ```
  2. **0404's short-circuit criterion checked the wrong object**: it `vnode_lookup`ed
     `PongAdrenoMetal.bundle/PongAdrenoMetal` (the bundle binary), which already
     existed → straight to `bundle already present` → the whole deploy skipped →
     **the two seed files are never written**.
- **And `selectedClient()` requires exactly those two seeds** (`PongMetalPlugin.mm:174-192`):
  ```objc
  if(lstat(marker,&st) || !S_ISREG(st.st_mode) || st.st_uid || (st.st_mode&022))continue;
  FILE *file=fopen(marker,"r");if(!file)continue;
  const bool publish=fgetc(file)=='1';fclose(file);if(!publish)return false;
  if(lstat(clients,&st) || ... )continue;      // must contain the process name (backboardd)
  ```
  → seeds missing ⇒ `selectedClient()` returns `false` ⇒
  `initWithAcceleratorPort` returns `nil` ⇒ it looks like "the plugin was never loaded at all".
- **Fix**:
  1. Use `mcopy` to inject `PongAdrenoMetal.publish` (2 B, "1") and
     `PongAdrenoMetal.clients` (122 B, contains backboardd/SpringBoard/… ) into
     `payload.img`'s `::/METAL`
  2. Change 0404's short-circuit criterion to **check the two seed files**, no
     longer the bundle binary
- **Diagnostic commands**:
  ```bash
  mdir -i payload.img ::/METAL | grep -E 'PUB|CLI'
  mtype -i payload.img "::/METAL/PongAdrenoMetal.publish"    # must be 1
  mtype -i payload.img "::/METAL/PongAdrenoMetal.clients"    # must contain backboardd
  ```
- **Lessons (★19 "evidence criteria" + ★25 "compiles ≠ runs")**:
  1. **A list marked "verified" in a document must be re-checkable with one
     command**, otherwise it goes stale and misleads (here `DATA-VOLUME-DEPLOY.md`'s
     list is wrong).
  2. **An idempotency criterion ("already present") must check the files the gate
     actually requires**, not just one file that "looks like it represents the whole".
  3. **"The plugin was not loaded" and "the plugin loaded but refuses to serve"
     look almost identical in the log**; you must go read the gate function's
     actual criteria and check them one by one.

### P-108 Copying 51 MB synchronously inside native_owner_data_prepare → 0-byte log

> **⚠️ Attribution void, see P-117**: the real cause of death is the init binary's
> `__TEXT` exceeding one page, unrelated to "synchronous large IO". This entry is
> kept as a process record.

- **Symptom**: after flashing, the device reset and the log was **completely 0
  bytes** (`usblog-20261111-121831  0 B`), COM5 never enumerated at all. It died
  earlier than any previous panic.
- **Comparison**: the previous successful boot (`usblog-20261111-115745`) had a
  120,907 B log and reached pid 234. The only difference between the two was
  **that I changed 0404's short-circuit criterion from "check the bundle binary"
  to "check the two seed files"**.
- **True cause**: with the criterion changed, the seeds missing on the device ⇒
  the full deploy branch is entered ⇒ `k60_metal_copy()` copies 6 files
  (PongMetalBridge.dylib **33 MB** + libvulkan_freedreno.dylib **18 MB**, 51 MB
  total) into the Data volume in 16 KiB chunks, synchronously
  ⇒ **`native_owner_data_prepare` stalls for tens of seconds on the boot thread**
  ⇒ USB gadget does not get to enumerate in time ⇒ watchdog reset (beyond
  `k60_autoreset=300`, more likely a boot timeout / hardware watchdog).
- **Correct answer: supply exactly what is missing (incremental deploy)**
  ```c
  if (vnode_lookup(K60_METAL_SRC "/PongAdrenoMetal", ...) != 0) need_bundle = 1;
  if (missing publish or clients)                                 need_seeds  = 1;
  if (!need_bundle && !need_seeds) return;          // do nothing at all
  ...
  if (need_seeds)  { write publish + clients }       // 124 bytes, write first
  if (need_bundle) { write the 6 bundle files }      // 51 MB, write last
  ```
  Two key points:
  1. **Write the seeds first** (124 bytes, instantaneous, the gate passes immediately)
  2. **Write the bundle only when it is genuinely missing** (it almost never
     changes, it should not be copied on every boot)
- **Diagnostic commands**:
  ```bash
  # 0-byte log + fastboot available + COM5 not enumerated ⇒ suspect synchronous large IO on the boot path
  ls -la evidence/usblog-<latest>/console.log     # 0 B
  [System.IO.Ports.SerialPort]::GetPortNames()  # no COM5
  ```
- **Lessons (another case of ★25 "compiles ≠ runs")**:
  1. **Synchronous large IO is forbidden on the boot path (`native_owner_data_prepare` /
     `bsd_init` stage).**
     A 51 MB copy must happen after init, or asynchronously, or only once.
  2. **Idempotency logic is neither "check one file and skip" nor "do everything
     every time"**; it must **decide item by item what is missing**. The earlier
     "check the bundle binary" missed the seeds; changing it to "check the seeds"
     became a full copy every time — both extremes are wrong.
  3. **A 0-byte log ≠ a broken device** (P-41). But it is not necessarily a kernel
     panic either — it may just be a boot that is too slow. Compare against the
     log size of the most recent successful boot first.

### P-109 Hand-computed hunk line numbers will be wrong 6 times in a row — generate patches with difflib, do not write them by hand

- **Symptom**: adding one new function + one call site to `0404`, 6 consecutive
  build failures:
  ```
  error: corrupt patch at line 250
  error: patch failed: bsd/kern/kern_exec.c:7678
  error: patch failed: bsd/kern/kern_exec.c:7772
  error: patch failed: bsd/kern/kern_exec.c:7774
  Hunk #2 FAILED at 7869
  ```
  Every time I was "fixing" the line numbers, and every time it was wrong again.
  Change the `-` side, change the `+` side, change the context line count, count
  the `+` lines by hand, add a trailing newline — 6 rounds, all failed.
- **True cause**: **hand-computing `@@ -old,count +new,count @@` means four numbers
  must be right at once**, and the `+` side start depends on the net delta of all
  preceding hunks. Off by one anywhere and the whole thing fails.
  My last "correct" guess was `-7678` / `-7772`,
  while **difflib generated `-7677` / `-7778`** — both differ from what I computed,
  which shows the previous 6 rounds were all spinning on wrong numbers.
- **Correct answer: let a tool generate the diff, do not write it by hand**
  ```python
  import io, difflib

  src = '<original file path>'     # copied out of the build tree, without this patch applied
  orig = io.open(src, encoding='utf-8', errors='ignore').read().split('\n')

  new = list(orig)
  # 1) find the insertion point (locate by content, not by line number)
  i = next(i for i, l in enumerate(orig) if l.strip() == 'target line content')
  new = new[:i] + NEW_LINES + new[i:]        # or replace

  d = list(difflib.unified_diff(orig, new,
                                fromfile='a/<path>', tofile='b/<path>',
                                lineterm='', n=3))
  out = ['diff --git a/<path> b/<path>'] + d
  io.open(PATCH, 'w', encoding='utf-8', newline='\n').write('\n'.join(out) + '\n')
  ```
  **The four line numbers, the context line count and the trailing newline are all
  guaranteed correct by difflib.**
- **Precondition: the source file must be the real state "before this patch is applied"**
  Copy it from the build tree (`<xnu-work>/bsd/kern/kern_exec.c`),
  and **confirm this tree contains all prerequisite patches** (for instance 0340's
  libpong-ui block).
  This session had been using `usb-cdc-mainline/out3` (9236 lines) all along,
  while what is actually built is `k60build` (9322 lines) — **two different trees,
  every anchor wrong**.
- **Verification (mandatory, and using the same judgement as the build)**:
  ```bash
  T=/tmp/diff-test; rm -rf "$T"; mkdir -p "$T/<dir>"
  cp <original file> "$T/<dir>/"
  cd "$T" && git init -q . && git add -A && git commit -qm init
  git apply --check <patch>     # must print nothing
  ```
  `patch --dry-run` passing does not count (P-96).
- **Lessons**:
  1. **The `@@` line numbers are for a machine to compute; a human computing them
     will be wrong.** I have seen people get it right by hand, but that is because
     they only changed the `+` side; as soon as the insertion point is mid-file and
     other hunks follow, it is guaranteed to fail.
  2. **If two consecutive attempts to fix the same patch format fail, change tools,
     not "fix it once more".**
     Here the third failure should have brought in difflib; instead it dragged to
     the seventh.
  3. **The "source file" must be the same one the build uses**. Every derivation
     from the wrong tree is wrong, and the failure message looks like "line number
     off by 1", which is extremely misleading.

### P-110 There are three different kern_exec.c files; confirm which one is the build input first

- **Measured (2026-11-11)**:
  ```
  /opt/k60/trees/k60build/.../xnu-work/bsd/kern/kern_exec.c        9322 lines  ← actually built
  /opt/k60/trees/usb-cdc-mainline/out3/.../xnu-work/bsd/kern/kern_exec.c  9236 lines  ← historical tree
  ```
  `B=` in `buildv15.sh:6` points at `k60build`; `out3` only contributes `fakeroot`
  and `sources`.
- **Consequence**: generating patches from the `out3` copy → every anchor line
  number wrong → 6 rounds of rework (P-109).
- **Diagnostic commands**:
  ```bash
  grep -n '^B=\|^D=\|^OLDSRC=' <workspace>/scratch/buildv15.sh
  # B= is the build tree; D= is the device repo (patch input); OLDSRC only supplies fakeroot/sources
  wc -l <each tree>/bsd/kern/kern_exec.c     # different counts mean they are not the same copy
  ```
- **Lesson**: **before changing any file in the build tree, confirm which tree it
  is using `buildv15.sh`'s variables.**
  This is the third recurrence of the same class of problem as P-40/P-42/P-73.

### P-111 A Mach-O signature XNU can load: deleting DYLD_INFO_ONLY is what makes room

- **Symptom**: `ldid-lite.py` reports `no room in load commands for LC_CODE_SIGNATURE`;
  `codesign` with any arguments at all produces a 19 KB signature + `ncmds=10`
  (boot panic).
- **Root cause (measured comparison)**:
  ```
  bootable v24dp:  34,904 B  ncmds=9  sizeofcmds=1216  has CODE_SIGNATURE(16)
                             ★ no LC_DYLD_INFO_ONLY
  my build:        35,088 B  ncmds=9  sizeofcmds=1248  has DYLD_INFO_ONLY(48)
                             ★ no CODE_SIGNATURE
  ```
  **`LC_DYLD_INFO_ONLY` in a static executable is meaningless** (48 bytes);
  deleting it frees exactly enough room for `LC_CODE_SIGNATURE` (16 bytes).
  But deleting alone is not enough — `sizeofcmds` must also be **grown by 16**,
  otherwise `end_cmds == 32 + sizeofcmds` and there is still no slack.
- **Full procedure (already packaged as `scripts/sign-macho.py`)**:
  1. Delete `LC_DYLD_INFO_ONLY`, shift the following load commands forward
  2. `sizeofcmds += 16` to leave an empty slot for `LC_CODE_SIGNATURE`
  3. Hand-write the `CodeDirectory` (version `0x20400`, flags `0x2` adhoc,
     SHA256, pageSize log2=12) + `SuperBlob` (`0xFADE0CC0`), append to the end of the file
  4. Fill the `dataoff/datasize` of `LC_CODE_SIGNATURE`, `ncmds += 1`
- **Verification criteria**:
  ```bash
  python3 <workspace>/scratch/sign-macho.py <macho>
  # expect: ncmds=9, signature ≈ 400-450 B, magic OK
  ```
  `datasize ≈ header(88) + identifier(16) + pages×32`.
  A 35 KB file = 9 pages → 88+16+288 = 392 B CodeDirectory,
  +12+8 SuperBlob header = **412 B** (against v24dp's 401 B, same order).
- **Diagnostic command**:
  ```bash
  python3 -c "
  import struct
  d=open('init','rb').read()
  n=struct.unpack_from('<I',d,16)[0]; off=32; cs=None; has_di=False
  for i in range(n):
      c,s=struct.unpack_from('<II',d,off)
      if c==0x1d: cs=struct.unpack_from('<II',d,off+8)[1]
      if c==0x80000022: has_di=True
      off+=s
  print('ncmds=%d cs=%s DYLD_INFO=%s  (correct: 9 / ~400 / False)' % (n,cs,has_di))"
  ```
- **Lessons**:
  1. **When there is "no slack", ask "which load command is superfluous"**, rather
     than asking the linker for more space
     (`-headerpad` has no effect on static links, P-100 has already shown this).
  2. **`sizeofcmds` is writable metadata**; growing it amounts to declaring "this
     whole region counts as load commands", and it is safe as long as it does not
     overwrite the offset of the first section (in this case the gap is 64 bytes).
  3. Compare the signature size **by order of magnitude** against a sample known to
     run (408 vs 412 ✓, 408 vs 19024 ✗).

### P-112 The kernel boot path cannot create new files — move all of it to userland init

> **⚠️ Attribution void, see P-117**: the real cause of death is `__TEXT` crossing
> a page boundary.
> The kernel-side file writes that crashed did so because they carried the init
> changes at the same time.

> **⚠️ Conclusion corrected by P-114**: the real cause is "synchronous large IO on
> the boot-critical path", not merely "kernel vs userland" or "create vs overwrite".
> Writing 124 B in init is safe; copying 51 MB at the same location still dies.

- **Six controlled experiments (2026-11-11, all at the same `native_owner_data_prepare` location)**:
  | version | action | result |
  |---|---|---|
  | `115745` | short-circuit, **do nothing at all** | ✅ 60fps / pid 234 |
  | `121831` | kernel mount md0 + copy 51 MB | ❌ log 0 B |
  | `122726` | kernel mount md0 + copy 124 B | ❌ no log |
  | `123506` | kernel embeds 124 B + `vnode_open` write | ❌ no log |
  | `125436` | kernel writes 124 B in the same style as 0340 | ❌ no log |
  | **`130708`** | **init (userland) `open`/`write` 124 B** | **✅ pid 276, write succeeded** |
- **Conclusion**: **creating any new file** inside `native_owner_data_prepare` makes
  the device reset before USB gadget enumeration (0-byte log). This is independent
  of the copy volume (124 B dies too), and independent of mount (no mount, pure
  `vnode_open`, also dies).
- **Why 0340 can write**: it writes `/private/var/pong/libpong-ui.dylib`,
  and that inode **already existed** (deployed earlier), so it is an "overwrite",
  not a "create".
  **Overwriting an existing file is safe, creating a new file is not.**
- **Correct answer: do it in userland init**
  ```c
  /* init.c, after the Data volume is mounted writable and APFS has completed one full transaction */
  static void prepare_metal_bundle(void) {
      mount("msdos", "/private/var/pong/md0", MNT_RDONLY, "/dev/md0");
      /* open/read/write one by one into /private/var/pong/PongAdrenoMetal.bundle/ */
  }
  static void prepare_metal_seeds(void) {
      /* write PongAdrenoMetal.publish / .clients */
  }
  ```
  Measured log:
  ```
  K60SEED publish bytes=2 resid=0 error=0
  K60SEED clients bytes=122 resid=0 error=0
  Pong init: Metal seeds ready=2 failed=0
  ```
- **Call site** (in `init-v24dp.c` main):
  ```
  prepare_boot_services();
  prepare_metal_bundle();     ← copy 51 MB out of /dev/md0
  prepare_metal_seeds();      ← 124 B of seeds
  configure_ui_library();     ← bundle and seeds are both present by now, so Metal gets injected
  ```
- **Lessons (the strengthened version of ★20 / ★25)**:
  1. **The kernel boot path = read-only phase**. Any operation that "creates an
     inode" (new file, mounting a new filesystem) is unsafe; overwriting an
     existing file is fine.
  2. **The same operation dies on the kernel side and is fine in userland** — do
     not assume an API is usable on the boot path just because the kernel API exists.
  3. `mini.h` only has `strlen/strcmp/strncmp/strcpy/strchr/memcpy`,
     **no `snprintf`/`strcat`/`sprintf`**; composing paths needs your own
     `join_path` (`strcpy` + `memcpy` piece by piece).

### P-113 `PongAdrenoMetal.bundle` was never deployed to the device; `bundle already present` was a false report

- **Symptom**: `boot-args` has `pong_metal=1`, the seed files were written
  successfully, `PONG METAL: real IOAcceleratorES provider published` also appeared,
  but `configure_ui_library()` only printed `UI library configuration result=0`,
  with **no** `native Metal entry enabled for backboardd`.
- **True cause**: the condition in `configure_ui_library()` is
  ```c
  if (strncmp(p,"pong_metal=1",12)==0 && ...) {
      if (stat("/private/var/pong/PongAdrenoMetal.bundle/PongAdrenoMetal",&st)==0 &&
          (st.st_mode&S_IFMT)==S_IFREG && st.st_uid==0 && !(st.st_mode&022)) {
          ... puts("Pong init: native Metal entry enabled for backboardd");
      }
  }
  ```
  **The bundle binary is simply not on the device**. The earlier 0404 criterion
  `vnode_lookup(bundle/PongAdrenoMetal)` returning success was a **false report** —
  that path may have matched a directory or an incomplete state.
- **Discriminator**:
  ```bash
  grep -c 'K60METAL' <console.log>     # 0 = the deploy code was removed / never ran
  grep -a 'Metal bundle copied' <console.log>   # should show "copied 4/4 member(s)"
  grep -a 'native Metal entry enabled' <console.log>  # the final criterion
  ```
- **Correct answer**: in init copy the 4 members out of `/dev/md0`
  (`Info.plist` / `PongAdrenoMetal` / `PongMetalBridge.dylib` /
  `libvulkan_freedreno.dylib`, 51,278,327 B in total) into `/private/var/pong/PongAdrenoMetal.bundle/`.
- **Lesson**: **`vnode_lookup()` succeeding does not mean "that file is the file I
  want"**.
  The criterion must check `st_mode & S_IFMT == S_IFREG`, `st_uid`, `st_size`,
  and ideally verify the file size or contents as well. This is again the same class
  of problem as P-107 (the idempotency criterion checked the wrong object).

### P-114 init's boot path fears "synchronous large IO" as well

> **⚠️ Attribution void, see P-117**: the real cause of death is `__TEXT` going from
> 1 page to 2 pages.
> In the 6th/7th comparison, "it dies from nothing but the extra bundle copy" is
> because that change also made init bigger.

- **Seven comparisons (2026-11-11, bisecting step by step)**:
  | # | location | action | result |
  |---|---|---|---|
  | 1 | kernel `native_owner_data_prepare` | short-circuit, do nothing | ✅ 60fps / pid 234 |
  | 2 | kernel | mount md0 + copy 51 MB | ❌ 0 B |
  | 3 | kernel | mount md0 + copy 124 B | ❌ no log |
  | 4 | kernel | embed 124 B + `vnode_open` write | ❌ no log |
  | 5 | kernel | write 124 B in the same style as 0340 | ❌ no log |
  | 6 | **init (userland)** | **write 124 B of seeds** | **✅ pid 276** |
  | 7 | **init (userland)** | **write 124 B of seeds + copy 51 MB bundle** | **❌ no log** |
- **Corrected conclusion**:
  - P-112 said "the kernel boot path cannot create new files" — **true, but incomplete**.
  - **Comparisons 6/7 prove: writing 124 B in init is completely safe, but copying
    51 MB at the same place dies.**
  - The real criterion is that **doing synchronous large IO at this stage
    (51 MB / tens of seconds) drags the boot to death**, not merely "kernel vs
    userland" or "create vs overwrite".
- **Why 51 MB dies and 124 B does not**:
  init runs in the `prepare_*` stage, at which point the USB gadget needs to
  enumerate as fast as possible and `exec launchd` needs to happen as fast as
  possible. A 51 MB chunked copy (16-64 KiB at a time, roughly 800-3200
  read+write syscalls + APFS allocation) stretches that window to tens of seconds,
  and the hardware watchdog or boot timeout resets before USB enumeration — hence
  the 0-byte log.
- **Correct answer: move large-file deployment off the boot-critical path**
  1. **init writes only small files** (124 B of seeds, measured safe)
  2. **The 51 MB bundle is copied by a LaunchDaemon** after launchd is up
     (by then the system is fully ready, tens of seconds does not affect the boot)
  3. Or init forks a background child process to do the copy and the main flow
     execs launchd immediately
- **Discriminator**:
  ```bash
  ls -la evidence/usblog-<latest>/console.log   # 0 B / missing = boot timeout
  # compare: the same code writing only 124 B gives a 116 KB log, pid up to 276
  ```
- **Lessons (the final form of ★20 items 4/5)**:
  1. **Boot-critical path = from kernel init to `exec launchd`.**
     Forbidden during that window: creating new files (kernel side), synchronously
     copying large files (any side), mounting new filesystems (kernel side).
  2. **Small file writes (<1 KB) are safe** and can serve as a "probe" to verify the
     path works, but do not put a 51 MB order of magnitude in with them —
     **a difference in quantity changes the conclusion**.
  3. **When bisecting, control the variables down to "change one dimension only"**:
     between comparison 6 and comparison 7 only the bundle copy was added, and that
     pair pinned the cause directly.

### P-115 `var.skel` supports three line kinds `d`/`l`/`f` — this is the official mechanism for presetting files on the Data volume

- **The mistake I made**: I read only the `d` (directory) branch of the init parser
  and asserted "`var.skel` can only create directories, it cannot hold files", then
  switched to hard-writing files at runtime, wasting 7 crash experiments for nothing.
- **The actual format (`init-v24dp.c` `prepare_var()` parsing)**:
  ```
  d\t<octal mode>\t<uid>\t<gid>\t<target directory path>
  l\t<symlink target>\t<target link path>
  f\t<octal mode>\t<uid>\t<gid>\t<target file path>\t<source file path>
  ```
  Code:
  ```c
  if (count == 5 && field[0][0] == 'd') { mkdir + chmod + chown }
  else if (count == 3 && field[0][0] == 'l') { symlink(field[1], field[2]); }
  else if (count == 6 && field[0][0] == 'f') {
      result = copy_new(field[5], field[4], mode, uid, gid);   /* source → target */
  }
  ```
- **The implementation of `copy_new()` (`init-v24dp.c:44`)**:
  ```c
  static int copy_new(const char *source, const char *dest, int mode, int uid, int gid)
  {
      char buf[4096];                                   /* 4 KiB chunks */
      out = open(dest, O_WRONLY | O_CREAT | O_EXCL, mode);
      if (out < 0) { ... return errno == 17 ? 0 : -1; } /* already exists = success (idempotent) */
      while ((n = read(in, buf, sizeof(buf))) > 0) { write loop }
      chmod(dest, mode); chown(dest, uid, gid);
  }
  ```
  **`O_EXCL` + `errno==17 → return 0`** means: if the file already exists, treat it
  as success and do not overwrite user data.
- **The producer (`userland/build.py:250 data_seed()`)**:
  ```python
  for rel, (mode, uid, gid) in sorted(metadata.items()):
      path = '/private/var/' + rel
      if stat.S_ISLNK(mode):   lines.append(f'l\t{os.readlink(...)}\t{path}')
      elif stat.S_ISREG(mode): lines.append(f'f\t{mode:o}\t{uid}\t{gid}\t{path}\t/pong/var-seed/{rel}')
  skeleton = '\n'.join(lines) + '\n'
  if len(skeleton.encode()) >= 65536: raise RuntimeError('var.skel exceeds init buffer')
  (overlay / 'pong/etc/var.skel').write_text(skeleton)
  ```
  At the same time `shutil.copytree(data, seed)` puts the contents into
  `overlay/pong/var-seed/`.
- **Key constraint**: `var.skel` as a whole is **< 64 KiB** (`buf[65536]`), so the
  number of entries it can list is limited.
  Directories can be listed in the thousands; the number of files must be kept in
  check (each entry is ~100-200 bytes).
- **Discriminator**:
  ```bash
  grep -c '^f	' <workspace>/deliverables/pong-varskel-*/pong/etc/var.skel   # how many f lines
  grep -c '^d	' same file    # directory lines
  awk -F'\t' '$1=="f"' var.skel | head     # sample f lines
  ```
- **Lessons (★23 strengthened)**:
  1. **Before reading a parser, list every `field[0][0] == '?'` branch.**
     I saw only `d` and concluded, missing `l` and `f`.
  2. **Whatever `build.py` generates, init must consume.** The producer writes
     `f` lines + `var-seed/`, so the consumer necessarily handles them — follow that thread
     and you find the mechanism directly.
  3. **The official porting project certainly already has the answer to "how do I
     get a file onto the Data volume"**, and it solves it **at build time**, not at
     runtime.

### P-116 Seven crash experiments were all wasted — because `build.py`'s `data_seed()` was not read first

- **Timeline** (2026-11-11, the same day):
  | attempt | approach | result |
  |---|---|---|
  | 1 | kernel mount + copy 51 MB | ❌ 0 B |
  | 2 | kernel mount + copy 124 B | ❌ no log |
  | 3 | kernel embed + `vnode_open` | ❌ no log |
  | 4 | kernel write in 0340 style | ❌ no log |
  | 5 | **init writes 124 B** | ✅ pid 276 |
  | 6 | init writes 124 B + copy 51 MB | ❌ no log |
  | 7 | init only mounts a probe | (not finished) |
- **The user broke the whole thing open with three sentences**:
  > "Could it be that it simply cannot be copied at all"
  > "Didn't this all use twrp dd to write the unixnu partition before?"
  > "**How do the other repositories solve writing files? Do they write it when the
  > system image is built in the first place?**"
- **Answer**: `build.py:250 data_seed()` + `scripts/install-pong-ufs-data.py`
  — **the Data volume contents are generated at build time and installed offline
  with dd into the unixnu partition.**
  At runtime there is no need to write 51 MB files at all.
- **Lessons (the strongest case of ★1 "read the whole thing first, grep is
  forbidden first")**:
  1. **When you hit "I want to put a file on volume X", the first step is to check
     how this project's build scripts do it**, not to write runtime copy code.
     `grep -n 'data_seed\|var.seed\|userdata' userland/build.py`
     finds the answer in one line, yet I went and changed C code 7 times first.
  2. **The user's domain intuition is often faster than my experiments**. "It used
     to be dd" pointed straight at "the official mechanism is offline presetting",
     and was worth stopping immediately to verify.
  3. **Every crash is 2-3 minutes of flashing + 4 minutes of building**; 7 of them
     ≈ 40 minutes.
     Reading `build.py`'s `data_seed()` took 2 minutes.
     **Reading the code first is always faster than trying first.**

### P-117 ★★★ an init binary whose `__TEXT` segment exceeds 1 page (16,384 B) cannot boot

- **Symptom**: after flashing the log is **0 bytes**, COM5 does not enumerate, the
  device resets itself.
  It happened both from the kernel side (`native_owner_data_prepare`) and from the
  init side, and for a while it was misdiagnosed as "mount / copying large files on
  the boot path", which is why those 7 crash experiments were run (P-108/P-112/P-114).
- **True cause (measured segment layout)**:
  ```
  init size     __TEXT filesize   result
  34,880 B      16,384 (1 page)   ✅ runs (v10guard, 60fps)
  34,904 B      16,384 (1 page)   ✅ runs (v24dp original)
  35,088 B      16,384 (1 page)   ✅ runs
  35,500 B      16,384 (1 page)   ✅ runs (writes seeds, pid 276)
  52,044 B      32,768 (2 pages)  ❌ crash (with BUNDLE_FIXUP)
  52,068 B      32,768 (2 pages)  ❌ crash (with bundle copy)
  53,728 B      —                 ❌ panic (MacOSX SDK / P-94)
  ```
  **The criterion is not the file size, it is whether the `__TEXT` segment's
  `filesize` is still within 1 page.**
  With the link flags `-Wl,-pagezero_size,0x100000000` + `-Wl,-e,_start`, once
  `__TEXT` crosses into the 2nd page the LOAD command's segment mapping exceeds a
  single page and init cannot be exec'd correctly.
- **Diagnostic command (must run after changing init)**:
  ```bash
  python3 - init <<'PY'
  import struct, sys
  d = open(sys.argv[1],'rb').read()
  n = struct.unpack_from('<I', d, 16)[0]
  off = 32
  for _ in range(n):
      c, s = struct.unpack_from('<II', d, off)
      if c == 0x19:
          seg = d[off+8:off+24].split(b'\x00')[0].decode()
          if seg in ('__TEXT', '__DATA'):
              fo, fs = struct.unpack_from('<QQ', d, off+40)
              print('%s filesize=%d %s' % (seg, fs,
                    'OK' if seg != '__TEXT' or fs <= 16384 else '!! OVER 1 PAGE'))
      off += s
  PY
  # expect: __TEXT filesize=16384 and OK
  ```
- **What is inside `__TEXT`** (measured on the 35,500 B version, filled up):
  ```
  __text              9,692 B   (code)
  __cstring           4,141 B   (strings)
  __const               337 B   (constants)
  __entitlements        237 B   (plist for signing)
  ─────────────────────────
  total              14,407 B   + header 1,344 B = 15,751 B (limit 16,384)
  ```
  **The headroom is only ~630 B.** Adding any function with real code volume
  overflows it.
- **Wrong approaches (I did all of them)**:
  1. Add a function directly → `__TEXT` overflows → crash, but assume "mount is
     poisonous"
  2. Add `probe_md0_mount` to bisect the location → pushes `__TEXT` past the page
     again → keeps crashing
  3. Leave a mass of dead code (`prepare_metal_bundle`/`copy_one_file`/`join_path`/
     `k60_metal_members[]`) in place → functions that are never called **still get
     compiled and still occupy `__TEXT`**
  4. Use "file size" as the metric → 35.5 KB sits exactly on the boundary, so
     assume there is headroom left
- **Correct approach**:
  1. **After every init change, check `__TEXT filesize`**, not the total file size
  2. **Before adding new features, delete an equal amount of dead code** (static
     functions that are never called still occupy `__TEXT`)
  3. Large constant arrays (`static const char xxx[]`) go into `__TEXT __const`;
     putting them in `__DATA` needs explicit handling, or dropping `const` so the
     compiler puts them in `__DATA`
  4. When it genuinely does not fit: **split into multiple init stages**
     (`/private/var/pong/init2` called by init),
     or move the logic back to the kernel side (the kernel has no such limit)
- **Lessons**:
  1. **I misattributed the "0-byte log" symptom 3 times** (P-108 blamed synchronous
     large IO, P-112 blamed the kernel not being able to create files, P-114 blamed
     the boot path fearing large IO).
     The truth is **it fails at the exec stage, completely unrelated to file I/O**.
  2. **After changing a binary, look at the structure (segment table), not just the
     size.**
     Two files with the same `size()` can have segment layouts where one runs and
     the other does not.
  3. **Dead code is not "harmless"** — it takes part in linking, occupies segment
     space, and pushes `__TEXT` past the page.
     Deleting code is as necessary a job as writing code.

### P-118 ★★★ boot-args missing `debug=0x140` → 0-byte log, looks like the kernel crashed

- **Symptom**: after flashing the log is **0 bytes**, COM5 does not enumerate,
  automatic reset. Over one whole day (2026-11-11) this happened **8 times**, and I
  blamed it on "init `__TEXT` crossing pages", "kernel writing files", "mount is toxic",
  "patch set changed" — **all wrong**.
- **Real cause (decisive experiment)**:
  ```
  Experiment A: Nov9 args (with debug=0x140 applog=1) + current kernel
         → 193,113 B log, normal boot  ✅
  Current:  current args (without debug=0x140 applog=1)
         → 0 B                        ❌
  ```
  **Same kernel, only the args swapped, one runs and one dies.**
- **Why it behaves like this**: `k60_usblog`'s log channel depends on XNU's debug
  output infrastructure. `debug=0x140` turns on early debug output (`DB_KPRT`/`DB_LOG`
  and the like), `applog=1` lets application logs into the same channel. Without them,
  `k60_usblog` still brings the USB gadget up, but **nothing is written into the ring**,
  so what the host side sees is "0 bytes".
  **It is not dead, it is silent.**
- **Where the two args came from**: `docs/` mentions the "golden 28 items" in several
  places, but `packv15.sh`, to squeeze into the 600-character budget (HR-45),
  deleted `debug=0x140` and `applog=1` during one of the trims (they should not have
  been on P-98's "low risk, deletable" list either). Every build after that was a mute
  kernel.
- **Check (30 seconds)**:
  ```bash
  # extract args from the device image
  mcopy -n -i <payload.img> ::/EFI/UniXNU/unixnu.toml /tmp/x.toml
  grep -o 'args = "[^"]*"' /tmp/x.toml | grep -c 'debug=0x140'
  # 0 => you will certainly see a 0-byte log, no matter what the kernel/init is
  ```
- **Correct args baseline (at minimum these must not be missing)**:
  ```
  debug=0x140 applog=1 k60_console_export=1 k60_usblog=2 epoch=1793709100
  ```
- **Lesson (the most expensive one in this project)**:
  1. **The first suspect for a "0-byte log" is always "logging is off", never "the
     kernel crashed".** I wasted a whole day on it, changing the init binary, kernel
     patches, mount, copy logic.
  2. **When cutting the boot-args budget, never delete the debug/applog/console
     three** — they do not change functionality, but they decide whether you can see
     what happens. P-98's "low risk, deletable" list had `debug=0x140` mixed into it;
     that was a mistake, now corrected.
  3. **Before suspecting "the code broke", diff the args against the last image that
     ran.** One line of `diff` saves 8 flashes.

### P-119 ★★ Files written to APFS from a Mac read back as uid=99 on the device, not 0

- **Symptom**: the bundle is plainly on the device (`stat()` succeeds), but
  `configure_ui_library()`'s `st_uid == 0` check fails, `native Metal entry enabled`
  never appears, and the dock blur stays missing.
- **Real cause**: the file was written into APFS through Mac `hdiutil attach`, so the
  recorded owner is the Mac account. On the device it reads back as
  **uid=99 = `_unknown`** (that uid has no matching account on iOS).
- **Check (one boot)**:
  ```c
  stat(path, &st);
  printf("uid=%u gid=%u mode=%o\n", st.st_uid, st.st_gid, st.st_mode & 07777);
  // uid=99 => this is the pitfall
  ```
- **Fix**: `chown(path, 0, 0)` + `chmod(path, 0755)`.
  **Pure inode metadata operations, no data blocks allocated**, completely unrelated to
  the "large IO" of P-114. It must be done for **the directory + every member**
  (chowning the directory alone is not enough).
- **Lessons**:
  1. **"The file is not on the device" and "the file is there but the owner is wrong"
     are two different things.** I once concluded from this that the bundle had "never
     been deployed" (P-113), which was wrong — `Metal seeds ready=2` had already proven
     `stat()` succeeded, I just did not read the log I wrote myself.
  2. **The probe must print the before and after of chown plus errno.** Printing only
     the "before" value cannot tell "chown succeeded" from "chown failed" — this time
     only the post value confirmed success.
  3. **mini libc does not support `%#o`**, it prints the literal `%#o`. Use `%o`.

### P-120 ★★★ Injecting the PongAdrenoMetal plugin crashes backboardd, the screen stays on the scrolling text forever

- **Symptom**: `native Metal entry enabled for backboardd` printed, but the screen keeps
  scrolling kernel logs, the dock blur never appears, and the largest pid is only 26.
- **Real cause (historical comparison, indisputable)**:
  ```
  log                   metalEntry  backboardd crash  maxpid
  usblog-...-172509         1           13          26
  usblog-...-170258         1           10          26
  usblog-...-163626         0            0         179
  usblog-...-160923         0            0         192
  usblog-...-152553         0            0         183
  usblog-...-130708         0            0         182
  ```
  `metalEntry=1` → backboardd crashes → the compositor dies → verbose kernel output
  keeps flooding the screen → the UI is never visible.
- **Crash point**:
  ```
  backboardd[55] *** Terminating app due to uncaught exception
    'NSInvalidArgumentException', reason:
    '*** -[NSURL initFileURLWithPath:]: nil string parameter'
  Process[55] crashed: backboardd. Too many corpses being created.
  ```
- **Key check: not one log line from the plugin itself**
  ```c
  static void report(const char *phase,int status)
  { snprintf(line,...,"Pong Metal: %s status=0x%x\n",...); write(2,line,...); }
  ```
  `Pong Metal` matches in the log = **0**.
  And `pong_gpu_scanout=0` would make the first statement of `pongscanout::start()`
  call `report("GPU scanout disabled by boot policy; CPU display active",0)`;
  not even that line showed up ⇒ **the plugin code never executed** ⇒ it crashed in
  dyld loading / initialisation, not in the `openDevice`/`startPresentation`/
  `pongscanout` business logic.
- **Injection mechanism (init-v24dp.c:579-580)**:
  ```c
  base  = "/private/var/pong/libpong-ui.dylib SpringBoard backboardd ...";
  metal = "; /private/var/pong/PongAdrenoMetal.bundle/PongAdrenoMetal backboardd";
  if(strncmp(p,"pong_metal=1",12)==0 && ...) { ... }
  sysctlbyname("kern.exec_inject",NULL,NULL,conf,strlen(conf)+1);
  ```
  It goes through `kern.exec_inject` → the kernel stuffs those paths into the target
  process's `DYLD_INSERT_LIBRARIES`.
- **Ruled out**: `pong_gpu_scanout=0` makes no difference (still crashes 10-12 times).
- **Zero-rebuild switch (key trick)**: init's criterion is an **exact match on
  `pong_metal=1`**. Change boot-args to `pong_metal=2`:
  - `strncmp("pong_metal=2","pong_metal=1",12) != 0` → no injection → backboardd survives
  - the kernel patch contains **no `pong_metal` string at all** (confirmed by grep),
    so the kernel Metal publication is unaffected
  - measured: backboardd crashes 0 times, maxpid 191 ✅
- **To investigate**: the binaries on the device and the locally compiled artefacts
  **are not the same set**:
  ```
  local  PongAdrenoMetal          94,896 B  signature 18,880 B
  device PongAdrenoMetal          91,648 B
  local  PongMetalBridge.dylib    33,146,048 B
  device PongMetalBridge.dylib    23,536,464 B
  ```
  The device set has been modified. Actually fixing Metal needs this local, correct
  bundle deployed (through the 24 GB dd flow in `OPS-DATA-REBUILD.md`).
- **Lessons**:
  1. **"A success log printed" is not "the feature works".** `native Metal entry enabled`
     only means init passed the stat check; whether the plugin can actually survive in
     the process is a separate question.
  2. **A reliable way to locate the crash stage: make the first statement of the target
     code print unconditionally.** If not even the first statement appears, stop
     looking at its business logic and suspect the load stage directly.
  3. **Changing the match value in boot-args works as a switch**, as long as the kernel
     side uses `PE_parse_boot_argn` (takes the value) while the init side uses
     `strncmp` (compares the string). The two have different semantics, which lets you
     turn off userland injection while keeping the kernel feature.

### P-121 ★★★ The goodix misc struct is packed, so the natural-alignment offsets are all wrong

- **Symptom**: config download "succeeds" (`wrote=1488/1488 bad=0`) but there are no
  touch reports; `frame_data` decodes to `0x30084` (a static block that never changes).
- **Real cause**: `goodix_ts_core.h:185 goodix_ic_info_misc` is a field table of
  alternating u32/u16, but `goodix_ts_core.h:121` has `#pragma pack(1)`, and
  `goodix_brl_hw.c:780` uses `memcpy` to copy the IC_INFO blob **verbatim** into the
  struct — **the wire layout is packed, not naturally aligned**.
- **Correct offsets vs wrong offsets** (back-solved from the chip's own dump):
  ```
  field                 natural   packed   value
  cmd_addr             +0        +0      0x10174
  cmd_reply_addr       +8        +6      0x10184
  fw_state_addr        +16       +12     0x10218
  fw_buffer_addr       +24       +18     0x1205c   ← config must be written here
  frame_data_addr      +32       +24     0x10400   ← read-only frame area
  touch_data_addr      +56       +44     0x10308   ← report area
  touch_data_head_len  +60       +48     8
  point_struct_len     +62       +50     8
  ```
  **Cross-check**: `head=8`, `point=8` independently hit `IRQ_EVENT_HEAD_LEN` and
  `BYTES_PER_POINT` at `goodix_brl_hw.c:994-995`. Two macros matching at once ⇒ the
  offset chain is right.
- **Worst failure mode**: the old code wrote the 1488-byte config into `0x10400` (the
  frame area) and read back `bad=0`, because that is ordinary RAM — **silent success**.
  In the official `goodix_brl_hw.c:519-520` the only config write target is
  `fw_buffer_addr`.
- **Log after the fix** (measured):
  ```
  goodix: MISC packed fwstate=0x10218 fwbuf=0x1205c/4200 frame=0x10400 touch=0x10308
  goodix: MISC reply=0x10184 head=8 point=8
  goodix: CFG-DL start, 1488 bytes -> fwbuf 0x1205c (max 4200)
  goodix: CFG-DL wrote=1488/1488 bad=0 -> DATA-OK
  ```
- **Lessons**:
  1. **Always suspect packed first on firmware structs.** `#pragma pack(1)` is very
     common in Apple/Qualcomm IC descriptions.
  2. **"Write and read back match" does not prove you wrote to the right place.** You
     must compare against the write target in the official driver.
  3. **Cross-check with two independent known constants** (the 8/8 here) is far more
     reliable than staring at one address and retrying.

### P-122 ★★★ The chip really is scanning (INT does go low), stop treating "no reports" as "the chip is not working"

- **Mistakes I made** (2026-11-11, twice):
  1. Seeing 22 heartbeats all with `int=1`, I declared "the chip is stuck in ROM not
     scanning, the firmware must be flashed".
  2. Earlier I had also declared "`reports=0` is because nobody touched the screen".
  Both conclusions were incomplete.
- **The truth**: full capture (`usblog-20261111-181651`, 216,921 B) counts:
  ```
  int=1 reports=0  x21
  int=0 reports=0   x2      ← INT really does go low
  ```
  `int=0` can only come from a real touch (INT is active-low, the chip pulls it low
  only when it has an event).
  **The scan engine is alive, the chip is working.**
- **The new contradiction**: INT arrives, but `reports` is still 0.
  Because the first check in `goodix_poll()` is
  `if (!goodix_read(touch_address, report, first) || report[0] == 0) return;`
  — `report[0] == 0` returns immediately, no count.
- **The value of `touch_address` is suspicious**:
  ```
  0x10308 returns the same 8 bytes every time, only the last byte changes across boots:
    00 94 b7 56 4b b4 ce ba   (one boot)
    00 94 b7 56 4b b4 ce bc   (next)
    00 94 b7 56 4b b4 ce be   (again)
  ```
  The last byte is +2 each time ⇒ **this is a counter/timestamp, not the report area**.
  So the packed-decode conclusion `misc.touch_data_addr = 0x10308`, even though the two
  length fields `head=8`/`point=8` do line up, **still has the report area wrong**.
- **The correct next step (stop guessing offsets)**:
  Do a **touch differential scan** — sample an address window periodically and print
  only "the addresses whose value changed". Idle background updates and a finger touch
  will hit different bytes, and the report area will expose itself. Candidate windows:
  ```
  0x10000 + k*0x10   (k=0..15)
  0x10200 + k*0x10
  0x10400 + k*0x10
  0x30000 + k*0x10
  ```
- **Lessons**:
  1. **`reports` in the heartbeat print is "number of reports successfully parsed",
     not "whether the chip works".** Whether the chip works is decided by **INT level
     changes**; these are two completely independent signals.
  2. **Concluding from part of the log was the biggest time waste this time.**
     The first log I looked at only went to 13 heartbeats (all int=1);
     the full log has 23 heartbeats, 2 of them int=0.
     **When reading a log you must read the whole file, never truncate** (another ★1
     violation).
  3. **A pattern like "last byte +2 each boot" is an important clue**:
     it says the firmware is writing that memory as a counter, so it is definitely not
     the report area. When hunting the report area, look for an address that changes
     **with touch**, not one that changes **with boot**.

### P-123 ★★★ The three real root causes of touch (extracted from the official state machine, 2026-11-11 evening)

After a whole day of wrong hypotheses (address, offsets, firmware, INT polarity, config
target, minimal mode), the state machine was finally extracted line by line from the
official Linux driver, and it located three real defects.

#### Root cause 1: CFG-RESET discards the config just written into RAM

The official `goodix_send_ic_config()` (`goodix_ts_core.c:2088`) calls
`brl_send_config()` (`goodix_brl_hw.c:493`) and then **does exactly one thing**:
```
goodix_brl_hw.c:553-559
    msleep(100);
    return 0;
```
**No reset, no work-mode command, no COORD-MODE switch.**

Our `patch:4438-4455` does a hard reset after the config download
(`gpio_set(PIN_RESET,false); sleep_ms(2); gpio_set(PIN_RESET,true); sleep_ms(100);`),
plus a fresh `0xc900` SPI handshake. That block was copied from
`goodix_update_finish()` (`goodix_brl_fwupdate.c:924`) —
which is the tail of the **flash firmware** path; `brl_send_config()` never goes
through it.

And the config write target `fw_buffer_addr = 0x1205c` is **RAM**
(`goodix_brl_hw.c:520`). After a hard reset the RAM contents are gone,
**so the 1488-byte config was never written**.

#### Root cause 2: it enters rawdata at boot, and minimal mode only ever goes in

`0x90/0x81` is the "read rawdata" command. The official driver only uses it in the
**capacitance test** (`goodix_brl_hw.c:1313`), and the `exit:` label **unconditionally**
sends `0x90/0x00` to leave (`goodix_brl_hw.c:1348-1351`).

Our implementation: `patch:4100-4152` unconditionally sends `0x90/0x81` at boot
(cannot be disabled), while the exit command `0x90/0x00` sits inside a
`!k60_touch_minimal` guard (`patch:4487`).
Result: **every minimal boot entered rawdata and never came out**,
so the scan engine never sees a normal frame.

#### Root cause 3: only ack is checked, not state

The official `wait_cmd_status()` (`goodix_brl_hw.c:448,461,466`) reads
`cmd_ack.state == 0x80`, and waits once after START / WRITE / EXIT each, up to 400 ms.

Our five checks (`patch:4144/4189/4397/4410/4500`) are all `ack[1] == 0x80`.
The `OK-config-applied` line in the log is a string **we wrote ourselves** at
`patch:4411`; it only proves the ack byte is 0x80, **not that the chip applied the
config**.

### Hypotheses also refuted (do not retry)

| Hypothesis | Why it is wrong |
|---|---|
| "config must be sent before it scans" | the mainline driver `goodix_berlin_core.c:728-805` works through the whole probe with zero commands and zero config |
| "INT level is the report criterion" | the real criterion is the first byte of `0x10308` (`goodix_brl_hw.c:1188`). In the three minimal runs INT appeared 0/1/2 times, reports were all 0 |
| "`k60_touch_minimal=1` skips every command" | the guard only wraps 4 places (`patch:2866/2888/4345/4487`), `CMD-FIX 0x90/0x81` and `CFG-START` are both outside it |
| "`0xC900` needs writing" | that is a **Berlin-A only** register, `goodix_brl_hw.c:19-21,59-61` return immediately on Berlin-D |
| "the config contents are wrong" | parsing the local bin gives head=121, body=139, length 1488, `fw_pid=9916R`, `fw_vid=05 80 02 63`, `cfg_id=0x640fdf7d`, checksum 0x08d3, all self-checks pass |

### Criterion (the only one)

**Look only at whether the first byte of `0x10308` is something other than `0x00`.**
Do not use the INT level.

### P-124 ★★★ INT went low 16 times, and the 64 bytes read from 0x10308 were identical all sixteen times

- **Measurement method**: `usblog-20261111-195825`, minimal mode (reset → probe → pure
  polling), whenever `gpio_get(PIN_INT) == 0` dump 64 bytes from `0x10308`, capped at
  16 times.
- **Result**:
  ```
  goodix: INTLOW#1 .. #16  all identical
  00 94 b7 56 4b b4 ce ba 06 e2 89 51 14 56 76 c9
  b2 c0 6f f9 95 d2 87 96 81 11 4a e7 6a 9b 73 45
  52 81 f2 cf c2 84 5f c2 b6 0b 0a 6d 9d 17 32 e8 4e 67
  ```
- **Two conclusions**:
  1. **INT really does go low 16 times with touch** ⇒ the chip reacts, the interrupt is
     real, it is not noise and not floating. The earlier "INT is always high"
     observation was because rate-limited printing only showed the first 2.
  2. **The contents of `0x10308` were byte-for-byte identical 16 times** ⇒ it is **not
     the report area**. The first byte is always `0x00`, so `goodix_poll` always returns
     at the first check and `reports` is always 0.
- **Why the packed decode gave 0x10308**:
  `touch_data_addr` is at `+44` in the packed layout, with `+48 head=8` and
  `+50 point=8`, and the two length fields cross-hit the official
  `IRQ_EVENT_HEAD_LEN` / `BYTES_PER_POINT`.
  **Two lengths matching does not mean the address matches** — this was the biggest
  reasoning error of this round: I used the correctness of the length fields to infer
  the correctness of the address field, but they are independent pieces of information.
- **The correct approach (stop guessing offsets)**:
  At the moment INT goes low, **snapshot a large address range and compare before and
  after**. When idle the firmware only moves counters; when a finger presses it moves
  the report area; the two hit different bytes and the report area exposes itself.
  Take the window `0x10000..0x107FF` (2 KiB), covering both candidates
  `touch_data 0x10308` and `frame_data 0x10400`.
- **Lessons**:
  1. **"The chip has interrupts" and "the data is at the expected address" are two
     independent propositions**, each must be proven separately.
  2. **Inferring field B is correct because field A in the same struct is correct does
     not hold.** The length fields matching (8/8) says nothing about the address field
     matching (0x10308).
  3. **Rate-limited printing hides the key samples.** `header_zero++ < 2` made me miss a
     whole day of INT-low data; a probe must **not** be rate-limited on the key quantity,
     or it must be triggerable by condition.

### P-125 ★★★ The chip really is scanning, but it produces no coordinate reports (0x10308 always 0)

- **Measurement method** (`usblog-20261111-202056`): minimal mode, snapshot
  `0x10000..0x107FF` (2 KiB, read as two 1024-byte blocks) every time INT goes low,
  compare byte by byte against the previous snapshot, print only the changed addresses.
- **Result**:
  ```
  WDIFF baseline 58 7b 05 f0 @10308=00
  WDIFF 0x10218 1a->73        <- fw_state_addr（misc+12）
  WDIFF 0x10401 2f->44        <- frame_data_addr（misc+24）region
  WDIFF 0x1040e c6->f0
  WDIFF 0x10472 2b->29
  WDIFF#2 changed=551         <- 551 bytes changed between two snapshots
  ```
- **Three hard conclusions**:
  1. **The chip is actively working**: 551 bytes changed between two snapshots, the
     `fw_state` state machine is advancing.
  2. **The raw frame area `0x10400` is alive** ⇒ the scan engine (AFE + ADC) really is
     sampling.
  3. **The first byte of `0x10308` is always `0x00`** ⇒ coordinate reports really are
     not being produced.
- **Inference**: the chip can scan and can produce raw frames, but **produces no
  coordinate points**. This is exactly what "missing config" looks like — the config
  holds the sensor mapping parameters and the point-count mapping; without it the chip
  can only output raw capacitance data and cannot compute touch coordinates.
- **And the real cause of the earlier config download failure** (see P-123):
  `CFG-RESET` hard-resets the chip right after the config is written into
  `fw_buffer_addr = 0x1205c` (RAM), voiding the whole config.
  The official `brl_send_config()` **only msleep(100)** afterwards, nothing else.
- **To verify**: `CFG-RESET` is disabled now (`if (0 && la == 0x80)`);
  after turning off `k60_touch_minimal` and running the full config flow,
  does the first byte of `0x10308` become non-zero.
- **Lessons**:
  1. **"Is there an interrupt" and "is there a report" are two independent
     propositions.** INT going low only proves the chip reacts; reports are decided by
     the first byte of `0x10308`.
  2. **Window diffing is an effective way to locate "live memory".** No offset guessing
     needed: let the addresses that move expose themselves: `0x10400` moved = the frame
     area is alive, `0x10308` did not move = no report produced.
  3. **`goodix_read` has a per-call cap of `GOODIX_MAX_READ = 1024`**
     (`zzzz...-pong-touch-console.patch:2118`, the check is at `:2145`).
     Reading 2048 bytes must be split into two blocks, otherwise it returns false
     outright, and the first version of the probe therefore printed `read failed` 16
     times.

### P-126 ★★★ When Python writes a patch, a backslash-n becomes a real newline and the patch is silently broken

- **Symptom**: the build reports `git failed (128)`, the error message is empty,
  `patches applied` drops from 211 to 198, but `kernel.log` has not a single error
  (that log was actually left over from the **previous successful build**; the
  `kernel.macho` timestamp did not change).
- **Real cause**: when assembling patch content with a Python triple-quoted string, the
  backslash-n inside a printf format string in C got interpreted by Python as a **real
  newline**, so one C line was written as two, the second line had **no `+` prefix**, and
  `git apply` immediately judged the patch corrupt.
- **Check (3 seconds)**: walk every line inside the hunk; the first character must be
  a space / `+` / `-` / backslash. Anything else is structural corruption.
- **Correct way**:
  1. Assemble patch content with a raw string (prefix r), or write backslash-n as two
     backslashes plus n
  2. **Run the structure validation immediately** after generating (the [Q] item of
     gate.py already does this automatically)
  3. Do not trust a drop in `patches applied: N` — that is the symptom, not the cause
- **Failed four times over this today**: 4 builds (about 8 minutes each, roughly 32
  minutes pure waste), and the first two times I misjudged it as "the patch set was
  changed by the sync script".
- **Lessons**:
  1. **Whenever a script generates a patch there must be a "structural validity"
     assertion**, you cannot eyeball the generated result — split lines do not show up in
     an ordinary grep.
  2. **When `kernel.log` has no error, look at the `kernel.macho` timestamp first.**
     Timestamp unchanged = this build never compiled, the failure is at an earlier stage
     (patch/config).

### P-127 ★★★ launchd crash / initproc exited / reset = the 0394 patch is missing

- **Symptom**: the system crashes or resets after reaching the launchd stage; the log
  shows `initproc exited`, `K60PANICARGS`, or the screen scrolls text and then reboots on
  its own.
- **Real cause** (verbatim from the comment in yibiya's 0394 patch):
  > replace launchd's service cache with a curated one carrying only the 22
  > CORE jobs. The stock cache references App-cryptex programs this port does
  > not ship (first hit: /System/Cryptexes/App/usr/libexec/webbookmarksd);
  > launchd SIGSEGVs on the failed access() and the kernel panics with
  > "initproc exited".
- **Key**: our repository does contain `0394-k60-launchd-cache.patch` (56,839 B),
  but **it is referenced 0 times in series** — it was never applied.
  yibiya's version is 59,315 B (newer), and it sits at line 193 of series (after 0392).
- **Fix**: copy yibiya's 0394 over and add it to series.
  Note it touches two files: `bsd/kern/kern_exec.c` + `bsd/kern/k60_launchd_cache.h`,
  and the write discipline is the same as 0340/0391 (IO_SYNC, context ucred, resid,
  vnode_close).
- **Lessons**:
  1. **A patch in the repository ≠ the patch in effect.** You must
     `grep <number> patches/xnu/series` to confirm. Today at least 3 of our patches
     (0391, 0394, 0404) were "file present, not in series".
  2. **A change in the series count must be explainable.** The difference between 211
     and 212 is whether one patch took effect.

### P-128 ★★★ A porting.toml format error breaks rendering of the device page on the site

- **Symptom**: `https://unixnu.com/devices/mondrian` shows
  `'str' object has no attribute 'get'`, the whole device page is blank,
  with only the hint "Complete and validate porting.toml".
- **Real cause**: the `evidence` array elements of `[[area]]` **must be tables**
  (with `kind`/`reference`/`result`), and we wrote 12 bare strings:
  ```toml
  # wrong
  evidence = ["usblog-20261110-234429: PONG ADRENO 22 steps all result=0"]
  # right
  evidence = [{ kind = "device", reference = "evidence/usblog-.../console.log",
                result = "PONG ADRENO 22 steps all result=0" }]
  ```
  The site reads each element with `e.get('kind')` and throws on a string.
- **Also**: the `cellular` section is missing. The spec requires "a device without a
  baseband fills in `not-applicable`"; the K60 has a baseband, so it must say `planned`
  and describe the gap.
- **Check (10 seconds)**:
  ```python
  import tomllib
  d = tomllib.load(open('porting.toml','rb'))
  for a in d.get('area', []):
      for e in a.get('evidence', []):
          assert isinstance(e, dict), '%s evidence has a bare string' % a.get('id')
  ```
  **Note**: valid TOML syntax does not mean a compliant format — a bare string is a
  legal TOML value, but it violates the record schema.
- **Where the spec is**: `https://unixnu.com/zh/porting/records`
  - required sections: configuration / firmware / cpu / memory / storage / display /
    input / gpu / network / cellular / audio / power / packaging / diagnostics
  - fields per area: id / status / components / paths / inputs / configuration /
    procedure / findings / completion / limits / next_action / evidence
  - `status` may only be planned / implemented / host-verified / device-verified / not-applicable
  - each evidence entry has kind / reference / result; host and device evidence also
    need command and the full 40-character revision
- **Lessons**:
  1. **A format spec document must be read as a protocol, not as a suggestion.**
     We never read `/zh/porting/records`, wrote TOML from intuition, and ended up with
     12 wrong evidence entries and 1 missing required section.
  2. **"Valid TOML syntax" ≠ "compliant record".** The former is the parser's business,
     the latter the schema's. Use the official checker:
     `python3 scripts/porting-record.py check --device <path>`.
  3. **The site is the only acceptance criterion.** After changing porting.toml you must
     confirm the device page renders, not just look at the local file.

### P-129 ★★★ Inferring the chip protocol from the driver filename points the wrong way; a same-SoC sibling port record is the highest-value reference

- **Symptom chain** (2026-11-11, the conclusion flipped twice in one day):
  1. First believed the chip was Berlin-D (BRL), did 40+ flashes
  2. Found `ANDROID-HW-TRUTH.md` saying "the driver is `goodix_ts` (GTP protocol)",
     concluded "the protocol is wrong", and switched to a GTP probe
  3. GTP probe measured: `0x8140/0x8047/0x804E/0x814E` **all return 0x00**,
     while in the same boot BRL `0x10000` stably reads `BERLIN 9916R 05.80.02.63`
  4. **Conclusion: BRL is right, GTP is wrong. `goodix_ts` is just the module name.**

- **Real cause**: Goodix's Berlin family in the vendor kernel **is also loaded as
  `goodix_ts.ko`** (the source goes through `goodix_brl_hw.c`). Module name and protocol
  name are not the same thing. `ANDROID-HW-TRUTH.md:14`'s "it is GTP not BRL" was
  inferred from the driver name, without measuring any register.

- **Check (the only credible one)**: read both register sets and see which one responds
  | Protocol | Version register | Expected |
  |---|---|---|
  | BRL | `0x10000` | chip model string (e.g. `BERLIN 9916R`) |
  | GTP | `0x8140` | product ID 4 bytes + firmware version 2 bytes |
  Measured result (`usblog-20261111-233246`): BRL has data, GTP is all 0 → BRL.

- **Sidelight lesson (same-SoC sibling port)**:
  `Seanding1998/hakios-xnu-kernel` (OnePlus Ace 2 / PHK110 / **SM8475**) documents the
  same-SoC touch PASS experience in `docs/phk110/waves/wave12c-electrical.md`:
  > Each CS frame emits only one 9-byte block, and the block is re-armed on a
  > **~20 ms beat**.
  > A continuation read that hugs the header frame (µs scale) → lands in the un-armed
  > window → reads back misaligned padding.
  > Switching to "20 ms beat + 9-byte framed harvest" PASSed on the first round.

  Our poll loop `sleep_ms(2)` + `++idle >= 1` always true → **unconditional read every
  2 ms**, 10× faster than the sibling port's beat, sampling forever inside the un-armed
  window.
  **That explains why `0x10308` returns the same bytes across dozens of reads.**

- **Lessons**:
  1. **You cannot infer the protocol from the driver filename**, only measure registers.
  2. **"The chip reacts" and "valid data is read" are two things** — INT toggling and
     being able to read fixed bytes does not mean the read timing is right.
  3. **A sibling port on the same SoC is the cheapest reference**, higher priority than
     the official generic driver. The road they walked in three Boot rounds of
     `wave12c` (#19 gather evidence / #20 beat / #21 PASS) we would not have had to
     repeat if we had read it earlier.
  4. **When a conclusion flips, fix the document immediately**, never let a wrong
     conclusion keep steering the work.

### P-131 ★★★ CRLF line endings from a Windows checkout make a whole reference repository "dirty"

- **Symptom**: `sync-all-repos-v2.sh` reports 5 Pong repositories as "too many dirty files
  (>50), violates HR-40" and skips syncing: `UniXNU-pong(143)`, `pong-adreno(116)`,
  `pong-adreno-metal(106)`, `uefi-pong(62)`, `ios-sweet(140)`. It looks like a pile of
  local changes.
- **Real cause**: `git diff --stat` shows
  `116 files changed, 15175 insertions(+), 15175 deletions(-)`
  — **insertions and deletions exactly equal**. That is the fingerprint of a CRLF/LF
  line-ending conversion. Spot check:
  ```
  HEAD version:     # Agent instructions$
  worktree version: # Agent instructions^M$      ← extra ^M（CR）
  ```
  After `git diff -w` (ignore whitespace) the **number of differing files is 0**,
  confirming zero content change.
- **Why it happens**: git on the Windows side has `core.autocrlf` converting LF to CRLF
  at checkout, and these repositories have no `.gitattributes` to constrain it.
- **Fix**:
  ```bash
  git -C <repo> config core.autocrlf false
  git -C <repo> config core.eol lf
  git -C <repo> checkout -- .
  ```
  After that the dirty files in all 13 repositories went to zero.
- **Check (3 seconds)**:
  ```bash
  git -C <repo> diff --numstat | awk '{if ($1==$2) n++} END {print n" symmetric differences"}'
  # or
  git -C <repo> diff -w --numstat | wc -l    # 0 = pure line-ending problem
  ```
- **Lessons**:
  1. **"Dirty file count" cannot be used as evidence of "local changes".** You must run
     `git diff -w` first.
  2. **Git repositories on Windows must have `.gitattributes` or `core.autocrlf=false`**,
     otherwise every checkout turns the whole repository "dirty".
  3. **The sync script's HR-40 check should use `git diff -w --numstat | wc -l` instead of
     `git status --porcelain | wc -l`** — the latter counts line-ending differences too.
- **Along the way**: cleaned out the leftover `README-K60-NOTES.md` from 7 reference
  repositories (our own repository notes, whose content is already in
  `docs/engineering/REPO-INVENTORY.md`).

### P-132 ★★★ Editing defconfig has no effect: `unixnu build` reads the cached `.config`

- **Symptom**: changed `CONFIG_XNU_PONG_ADRENO_PLATFORM` in
  `configs/mondrian_defconfig` from `y` to `n`, confirmed all three copies (repository /
  `/tmp/usb-cdc-mainline/device` / `/opt/k60/trees/usb-cdc-mainline/device`) say `n`,
  but the build still fails at `build-pong-adreno-platform.py` for missing GPU firmware.
- **Real cause**: `unixnu build kernel` reads
  `out-baseline/mondrian/<profile>/.config`, **not** `configs/*_defconfig`.
  `.config` is a snapshot generated by `unixnu defconfig NAME`, timestamped 2026-11-08.
  `config.py:159` defines `self.config_path = self.work / '.config'`,
  and `need_config()` reads only that.
- **Fix**:
  ```bash
  cd /opt/k60/trees/k60build
  ./unixnu defconfig mondrian_defconfig -D <device> --out <out-baseline>
  ```
  After refreshing, the Adreno value in `.config` immediately flips from `y` to `n`.
- **Check (3 seconds)**:
  ```bash
  grep PONG_ADRENO <out>/mondrian/<profile>/.config
  stat -c%y <out>/mondrian/<profile>/.config     # old timestamp = cache
  ```
- **Lessons**:
  1. **After editing defconfig you must run `unixnu defconfig`**, otherwise the change
     does not take effect.
  2. **Three copies agreeing does not mean it is in effect** — what actually takes effect
     is a fourth copy, `.config`.
  3. When a build fails, look at the `.config` timestamp first, do not suspect the
     configuration contents.

### P-133 ★★★ A double plus `++` in the patch body becomes an illegal character in the C source

- **Symptom**: the build fails while compiling `bsd/dev/k60_uilib.c`:
  ```
  k60_uilib.c:21:1: error: expected external declaration
  ```
  Line 21 is `+static const unsigned char k60_uilib_blob[] = {`.
- **Real cause**: in the `patch` format `+` is the "added line" prefix and **is not part
  of the source content**. When rebuilding the blob array with a script, I concatenated
  the `+` prefix with the C source and wrote both into the patch body, so the file
  `git apply` produced really did contain an extra `+`.
- **Correct way**: add exactly **one** `+` per line in the patch body:
  ```
  +static const unsigned char k60_uilib_blob[] = {
  +    0xcf,0xfa,0xed,0xfe,...
  +};
  ```
  not:
  ```
  ++static const unsigned char ...   ← wrong, the source gets an extra +
  ```
- **Check (3 seconds)**:
  ```python
  # no body line inside the hunk may start with '++' (except the '+++ b/' file header)
  for l in hunk_lines:
      if l.startswith('++') and not l.startswith('+++ b/'):
          print('double plus:', l)
  ```
- **Lessons**:
  1. **"The patch structure is valid" and "the generated source is valid" are two
     things.** `git apply` happily applies a patch whose content contains a `+`, and the
     compile then fails.
  2. When a script generates patches, **prefix logic must be independent of content
     logic**: write the pure content first, add prefixes uniformly at the end, never mix
     prefix characters into the content.
  3. The `[Q]` item of `gate.py` should also check "no double plus inside the hunk".

### P-134 ★★★ Misreading the touch config download format: the official driver wants the converted result of the `.cfg` text

- **Background**: the touch chip is identifiable (reads `BERLIN 9916R 05.80.02.63`),
  config download "succeeds" (`CFG-START state=80`, `CFG-DL 1488 bytes`,
  `CFG-EXIT ack=80`), but the first byte of `0x10308` (`touch_data_addr`) is always
  `0x00` and the chip produces no touch reports.
- **Official flow** (`goodix_ts_core.c:428-465, 483-502`):
  ```c
  ret = request_firmware(&cfg_img, GOODIX_DEFAULT_CFG_NAME, dev);
      // GOODIX_DEFAULT_CFG_NAME = "goodix_cfg_group.cfg"

  goodix_ts_convert_0x_data(cfg_img->data, cfg_img->size,
                            config->data, &config->len);
      // .cfg is ASCII text, shaped like "x00 x00 ... x39 x39 x31 x36 x52"
      // each 'x' is followed by two hex ASCII characters -> 1 byte
      // output length = number of 'x'/'X' characters

  hw_ops->send_config(core_data, config->data, config->len);
      // brl_send_config writes it verbatim to fw_buffer_addr, reads back and memcmps
  ```
- **What we do**: write the binary `.bin` straight into `fw_buffer_addr`, never through
  `convert_0x_data`. If our `.bin` already is the converted result, fine;
  if it is a sub-package stripped out of `goodix_cfg_group_m11a.bin` (a 1627 B
  container), the boundaries may be wrong.
- **Facts already verified**:
  - `bin_len` (u32@0) of `goodix_cfg_group_m11a.bin` (1627 B) = 1627 ✅ equal to the file length
  - `checksum` (u8@4) = 0xdc, and `sum(d[5:]) & 0xFF == 0xdc` ✅
  - but back-solving with the official `goodix_cfg_bin_head` layout
    (`bin_len(4) + checksum(1) + bin_version[N] + pkg_num(1)`),
    `bin_version` length comes out 0 and `pkg_num` = 54, **plainly unreasonable**
  - so this file uses a **vendor variant format**, not mainline `goodix_cfg_bin_head`
  - actual header shape (observed): `5b 06 00 00 | dc 36 00 00 | 00 01 00 00 | 00 00 00 00 | 12 00 | 49 06 00 00 | "Berlin"`
    where `0x065b`=1627 (total length), `0x0649`=1609 (sub-package length), `0x0012`=18 (some offset)
- **Next measurements**:
  1. Extract the real `goodix_cfg_group.cfg` (ASCII text) from Android,
     run `convert_0x_data` to get the reference byte sequence
  2. Compare byte by byte against our 1486 bytes
  3. Check whether `goodix_ts_core_vendor.c` has another cfg parser (vendor variant)
- **Lessons**:
  1. **"config download succeeded" is not "config is in effect".** Our
     `CFG-START state=80`, `CFG-DL 1488 bytes`, `CFG-EXIT ack=80` all pass, and the chip
     still reports nothing. A read-back memcmp only proves "the bytes landed", not "the
     chip accepted this config".
  2. **Config files come in two forms, ASCII and binary**, and the official default is
     ASCII + conversion. Before sending binary directly you must confirm it already is
     the converted result.
  3. **The container format comes in mainline and vendor variants**;
     `bin_len`/`checksum` matching does not mean the layout is mainline's.

#### P-134 addendum (2026-11-12, decisive evidence)

The container structure is now fully decoded (`goodix_cfg_group_m11a.bin`, 1627 B):

| Offset | Field | Value |
|---|---|---|
| 0 | `total_len` (u32) | 1627 ✅ equals the file length |
| 4 | `checksum` (u32) | 14044 |
| 8 | `version` (u32) | 256 |
| 12 | `reserved` (u32) | 0 |
| 16 | `sub_offset` (u16) | **18** |
| 18 | `sub_len` (u32) | **1609** = 1627 - 18 ✅ |
| 22 | chip name (16 B) | `"Berlin"` |
| 38 | sensor id | `0xff` = 255 |
| 39 | fw_pid (16 B) | `"9916R"` |
| **141** | **our slice start** | |

**Proven**: `container[141:1627] == our 1486 bytes`, byte for byte identical.
So our config is cut from container offset 141 to the end, **missing the 123 bytes of
[18:141]**.

Two possibilities, needs a device verdict:
- **A**: the official sends the whole sub-package (1609 B), we send 123 bytes less of
  header → the chip reads fields from the wrong offset
- **B**: the chip only wants the bare config area (1486 B) → our slice is correct

**Decisive criterion**: extract `goodix_cfg_group.cfg` (ASCII text) from Android and see
whether the length after `convert_0x_data` is 1486 or 1609.

#### P-134 again corrected (2026-11-12): the current driver does not send config at all

Checked every function definition in `patches/xnu/zzzz...-pong-touch-console.patch`
(1212 lines):

```
goodix_read / goodix_write / goodix_checksum_ok / goodix_dummy_data
touch_reset / goodix_probe / goodix_contacts_valid / goodix_release
goodix_report / goodix_poll / bring_up / touch_thread / pong_goodix_init
```

**There is no config download function.** `goodix_probe` does only three things:
1. Read `GOODIX_FW_VERSION` (28 bytes) to verify chip identity and checksum
2. Read `GOODIX_IC_INFO` and parse the ABI (length + version(16) + features(10) + 4 counts + 5 u16 frequency tables + misc(52))
3. Extract `touch_address = le32(info+offset+44)` and `command_address = le32(info+offset)` from misc

**Conclusion: `CFG-START` / `CFG-DL 1488 bytes` / `CFG-EXIT` are logs from an older
driver version; the code behind them has been deleted. The current driver sends no
config.**

This changes the whole premise of P-134:
- previously assumed "we sent a 1486-byte config but in the wrong format"
- actually "we never sent a config at all"

**New question**: does a Goodix chip need config before it produces touch reports?
- official Linux driver: `brl_send_config` is **optional** (`hw_ops->send_config` is only
  called if present), and `brl_event_handler` does not depend on whether config was ever
  sent
- but config determines the scan parameters (frequency, gain, noise threshold); without
  config it may not be able to detect capacitance changes

**Next measurement**: confirm from Android whether `goodix_ts` really sends config, and
whether the chip still reports when it does not. Criterion: whether the Android boot log
contains `success send config`.

### P-135 ★★★ The chip asks for config on its own (code 0x01), and we only handled reset (0x03)

- **Official implementation** (`goodix_brl_hw.c:1204-1212`):
  ```c
  if (event_status & GOODIX_REQUEST_EVENT) {
      if (pre_buf[2] == BRL_REQUEST_CODE_CONFIG)      // 0x01
          ts_event->request_code = REQUEST_TYPE_CONFIG;
      else if (pre_buf[2] == BRL_REQUEST_CODE_RESET)  // 0x03
          ts_event->request_code = REQUEST_TYPE_RESET;
  }
  ```
  then `goodix_ts_request_handle` (`goodix_ts_core.c:1216-1219`):
  ```c
  if (request_code == REQUEST_TYPE_CONFIG)
      ret = goodix_send_ic_config(cd, CONFIG_TYPE_NORMAL);
  else if (request_code == REQUEST_TYPE_RESET)
      ret = hw_ops->reset(cd, GOODIX_NORMAL_RESET_DELAY_MS);
  ```
- **Our implementation**: only `reset = report[2] == GOODIX_REQUEST_RESET;`
  **The config request (0x01) is silently dropped.**
- **Why this is the key**: after a reset the chip actively asks the host to send config.
  No answer = the chip sits in the "waiting for config" state = no touch reports. This
  matches the observed "first byte of 0x10308 always 0x00" exactly.
- **This round's action**: add a **diagnostic probe** first (no implementation
  guessing):
  ```c
  if (report[2] == GOODIX_REQUEST_CONFIG && configRequests++ < 8)
      printf("goodix: chip requested a config (code %#x); none available yet\n", report[2]);
  ```
  If that log line shows up on device, it proves the chip really is asking for config;
  only then is `send_config` the next step.
- **Lessons**:
  1. **The "sub-type" inside the event status bits must be handled one by one.** We
     handled the broad classes `GOODIX_STATUS_TOUCH`(0x80) and
     `GOODIX_STATUS_REQUEST`(0x40), but of the REQUEST sub-codes 0x01/0x03 only one.
  2. **"Silently dropped" is the hardest bug class to find.** No log, no error code, and
     the symptom is just "the chip does not move".
     The right move is to add counters and logs first, making the silent visible.
  3. **The eight-step process requires step ⑥ to resolve every uncertainty.** Treating
     REQUEST as "only reset" was the result of not checking the official
     `brl_event_handler` line by line.

### P-136 ★★★ Berlin-D answers no register until the boot-option handshake has completed

- **Official comment** (`goodix_brl_hw.c:78-106` `brl_dev_confirm`):
  > Berlin-D answers no register until the boot-option handshake has run:
  > write 8 x 0xAA to 0x10000 and require the same eight bytes back.
  > It is also the only independent proof of the MISO/MOSI/CLK/CS assignment.
- **Constants**: `BOOTOPTION_ADDR = 0x10000`, `DEV_CONFIRM_VAL = 0xAA`
- **Our implementation**: `goodix_probe` reads `GOODIX_FW_VERSION` straight away,
  **with no handshake**.
- **Why this omission is so deceptive**: our log plainly printed
  `goodix: chip "BERLIN", firmware "9916R" 05.80.02.63, sensor 255`,
  which looks like perfectly normal chip communication. But the official comment says the
  chip **answers no register** before the handshake — which means that successful read
  should itself have been suspect.
- **Fix** (this round): port `goodix_dev_confirm` and call it at the very start of
  `goodix_probe`:
  ```c
  if (!goodix_dev_confirm()) return false;
  ```
  Three attempts, 5 ms apart, printing
  `device confirm FAILED; check AVDD(GPIO71)/IOVDD/RESET/SPI` on failure.
- **Source**: yibiya's `81dd415e5` (`fix(board): run the touch driver at its
  publishing stage`) and `04bda86` (`fix(touch,power): land the handshake,
  config download and battery link`). He also found the 1488-byte
  `k60_cfg[]` array (starting with `4e 4d`, ASCII "NM", unlike the
  `00 00 00 00 00 00 39 39...` we stripped out of the container).
- **Lessons**:
  1. **"I can read the chip ID" is not "communication is normal".** Some chips answer a
     few read-only registers in default mode, but full function needs the handshake
     first.
  2. **When the official comment states a precondition, treat it as a hard constraint.**
     The first sentence of the `brl_dev_confirm` comment is "answers no register
     until...", which is the most direct clue there is.
  3. **Reading someone else's implementation saves several rounds on device.** yibiya's
     two commits hit exactly the two hypotheses we were pushing (handshake + config);
     that is the value of tracking upstream.

### P-137 ★★★ The config download must go through vendor command blocks, and must end by switching to coordinate mode (0x90)

- **Full flow** (yibiya 04bda86's `goodix_apply_config`, aligned with the official
  `brl_send_config` + `goodix_send_ic_config`):
  ```
  1. goodix_command(4, 0x04, NULL, 0, "CFG-START")     prepare
  2. write k60_cfg[] in blocks (64 bytes/block) + read back and compare
  3. goodix_command(4, 0x05, NULL, 0, "CFG-WRITE")     commit
  4. goodix_command(4, 0x06, NULL, 0, "CFG-EXIT")      finish
  5. reset (PIN_RESET low 2ms -> high 100ms)
  6. goodix_command(5, 0x90, &coord, 1, "COORD-MODE")  ★ switch to coordinate reporting
  7. sleep_ms(50)
  ```
- **Command frame format** (vendor block):
  ```
  frame[2] = len        (4 or 5)
  frame[3] = cmd        (0x04/0x05/0x06/0x90)
  frame[4..] = data
  sum = len + cmd + data bytes
  frame[len]   = sum & 0xff
  frame[len+1] = sum >> 8
  write 8 bytes to command_address, read ack[1], wait for 0x80
  ```
- **Step 6, 0x90, is the dividing line between raw frames and touch points.** Without it
  the chip stays in rawdata mode and `0x10308` is forever 0x00 — exactly what we observed.
- **The exact source of the config data**:
  ```
  container goodix_cfg_group_m11a.bin（1627 B）
    container[139:141] = 4e 4d          <- vendor block marker (ASCII "NM")
    container[141:1627] = 1486 bytes    <- what we stripped before
    yibiya's k60_cfg[1488] = container[139:1627]  <- includes the 4e 4d prefix
  ```
  We are missing those two bytes `4e 4d`, so the command block header lands misaligned.
- **misc offset**: `fw_buffer_addr` is at `misc+18` (not the `+24` of frame_data_addr).
  Without it `goodix_apply_config` cannot run at all.
- **Lessons**:
  1. **"Written in" ≠ "in effect".** Block writes + read-back compare only prove the
     bytes landed; what actually switches the chip's mode is the 0x90 command at the end.
  2. **The boundaries of the config array must be exact to the byte.** Being 2 bytes off
     on the `4e 4d` prefix misaligns the whole command block.
  3. **Looking at the upstream implementation again saves a whole round on device.**
     yibiya's `goodix_apply_config` is 30 lines that take us straight from "guessing the
     config format" to "copying a verified flow".

### P-138 ★★★ A missing `pong_native_driver_source` stops the ArmDT archive from being built

- **Symptom**: the build fails at `build-xnu-4k-baseline.sh:986`:
  ```
  test -f "$ARM_DT_ARCHIVE" failed
  ```
  and `$ROOT/build/` only contains `generated/ storage-abi/ xnu/`, no `armdt-platform/`.
- **Real cause**: the `[kernel]` section of `board.toml` is missing
  `pong_native_driver_source`. The unixnu framework at
  `scripts/unixnu/kernel.py:191` reads that key and assigns it to the environment
  variable `PONG_NATIVE_DRIVER_SOURCE`; and `build-xnu-4k-baseline.sh:250` conditions on
  ```
  if [ "${XNU_ARM_DT_PLATFORM:-0}" = 1 ] && [ -n "${PONG_NATIVE_DRIVER_SOURCE:-}" ]; then
      python3 "$PONG_NATIVE_DRIVER_SOURCE/scripts/build-pong-platform-macos.py" ...
  ```
  Empty variable -> the whole ArmDT/ArmCpu provider build is skipped -> line 986 cannot
  find the archive.
- **Trigger**: the repo version of `board.toml` had deleted that key, and the comment even
  said "no repository code reads a [kernel] pong_native_driver_source key".
  That statement **holds only for the repository itself** (repository code really does
  not read it), but the unixnu framework does. Syncing the repo version into the device
  directory (the build input) broke the build immediately.
- **Fix**:
  1. Add it back in both the repo version and the device version:
     `pong_native_driver_source = "/tmp/k60build/pong-driver"`
  2. Rewrite the misleading comment to state "unixnu's kernel.py:191 reads it" and record
     the line 986 symptom
- **Lessons**:
  1. **"Nobody in the repository reads it" ≠ "nobody reads it".** The build framework
     (unixnu) is an external dependency; which keys it reads must be checked separately,
     never only this repository.
  2. **When syncing repo → build input, check for key-set differences, not just which
     side is newer.**
  3. When a build fails on an uninformative check like `test -f`, first look at **what is
     missing from the artefact directory**, then work back to which build step got
     skipped by a condition.

### P-139 ★★★ Changing boot-args requires computing the 608-byte limit first

- **Symptom**: wanted to add `k60_touch_se=6`, found it went over the limit.
- **Measured**: before the change it was already 617 bytes, **already 9 bytes over the
  608 limit**.
- **yibiya's approach** (81dd415 commit message):
  > The applog pair is dropped to stay inside the 608-byte arm64 boot-args
  > limit, which the touch argument would otherwise exceed.
  > SpringBoard's own os_log output is unaffected.
- **What we did**: dropped `applog=1` (8 B) + `applog_name=runningboardd,backboardd,lsd`
  (46 B), added `k60_touch_se=6` (17 B), ending at 29 items, 582 bytes, 26 spare.
- **Criterion**: `k60_console_export=1` + `k60_usblog=2` already provide the kernel log
  and the USB log, and the touch driver's `printf` goes to the kernel log, so it does not
  depend on applog (userland os_log capture).
- **Lesson**: **every time you touch boot-args, print the current total length and the
  spare first**, do not discover the overflow at build or flash time.

### P-140 ★★ One driver must not have two reset paths

- **Symptom**: `goodix_apply_config` uses an inline GPIO toggle reset
  ```c
  gpio_set(PIN_RESET, false); sleep_ms(2);
  gpio_set(PIN_RESET, true);  sleep_ms(100);
  ```
  while `touch_reset()` does the same three steps and then calls `spi_mode_select()`.
  The two paths behave differently: the reset taken through apply_config **skipped the
  SPI mode confirmation**.
- **Official basis**: `brl_select_spi_mode` has three call sites —
  `goodix_brl_hw.c:120` (`brl_reset_after`), `:197`, `:322` (the return point of
  `brl_reset`). The official driver re-confirms the mode at every reset exit.
- **Fix**: switch `goodix_apply_config` to `touch_reset()`, and add the forward
  declaration `static void touch_reset(void);` (`apply_config` is defined before
  `touch_reset`).
- **Lessons**:
  1. **A reset is a "protocol restarts" action; every reset must go through the same
     function.** Scattered GPIO toggles leave later steps running against an
     undetermined chip state.
  2. **When porting code with a script, watch definition order.** Pasting a function
     body earlier without the forward declaration makes C99+ report an implicit
     declaration.

### P-141 ★★★ The eight-step record covers only 2 pieces of hardware, while STATUS.md lists 10

- **Symptom**: `docs/research/EIGHT-STEPS.toml` has only `touch` and `gpu`;
  the hardware table in `docs/engineering/STATUS.md` has 10 entries, 6 of them ✅ device-verified
  (Boot chain / UFS-APFS / display first frame / backlight / lock screen-SpringBoard / launchd stable).
- **Consequence**:
  1. Six pieces of working hardware have no eight-step evidence chain, so when the person or the machine changes you cannot tell "what it was verified with back then"
  2. The gate's flash check sees only 2 pieces of hardware; the other 8 are completely unconstrained
  3. This is exactly the root of "stepping on the same pitfall over and over, building the same wheel over and over" — the record and the facts disagree
- **Fix (2026-11-12)**:
  1. Fill in storage / display / bootchain / buttons / wifi / audio / battery, seven items,
     with every evidence entry citing a raw log line from STATUS.md or a specific file in patches
  2. Give every piece of hardware `status = "active" | "parked" | "planned"`
  3. The gate hard-checks only `active`: the eight-step process constrains **the fix being worked on**,
     not a historical list. parked/planned are recorded truthfully but do not block the build
  4. The gate gains a [W] check: every piece of hardware appearing in STATUS.md must have a record in EIGHT-STEPS.toml
  5. Items already device-verified get `prediction.success/failure`,
     so a reflash or a machine swap can tell at once whether something regressed
- **Result**:
  ```
  build mode -> 0 problems, 5 active hardware, 30 checks
  flash mode -> only 1 problem: touch ⑦ verification incomplete
  ```
- **Lessons**:
  1. **"Did it" and "recorded it" are two different things.** Work with no eight-step record cannot be reused
     next time, and cannot be judged trustworthy.
  2. **A gate should only constrain what is being done now.** Hard-blocking everything touched in the past
     and never finished makes people write fake evidence to get through the gate — that is worse than no record.
  3. **STATUS.md and EIGHT-STEPS.toml must agree in both directions.** The [W] check leaves drift nowhere to hide.

### P-142 ★★★ Seven conditions OR'd together returning false silently is the same as writing no diagnostics

- **Symptom**: the physical-button driver's `configuration()` looks like this
  ```c
  if (SecureDTLookupEntry(NULL,"/arm-io/pong-buttons",&e)!=kSuccess ||
      !property(e,"core-base",&c,8) || !property(e,"cnfg-base",&n,8) ||
      ... || c!=0xc400000 || n!=0xc42d000 || ... )
      return false;
  ```
  Any one failing condition yields only `false`, with nothing in the log.
  So "the driver is compiled/linked/called" and "the driver actually ran" cannot be told apart —
  STATUS.md could only mark 🔄 with the note "`configuration()` result is unobservable".
- **Fix**: split it into per-condition checks, each failure branch printing itself:
  ```
  Pong keys: DT node /arm-io/pong-buttons not found
  Pong keys: missing core-base            (one line per property, 7 of them)
  Pong keys: unexpected bases core=... cnfg=... observer=... ee=...
  Pong keys: ppid mismatch pon=... (want ...) volume-up=... (want ...)
  Pong keys: PMIC windows mapping failed core=... cnfg=... observer=...
  Pong keys: PMIC windows mapped, pon-ppid=... volume-up-ppid=...
  ```
  The success path logs too (the last line), so "no log" is no longer ambiguous.
- **Artefact verification**: in kernel.macho sha256 345d44c4, `Pong keys: missing` hits 7 times,
  every other string once.
- **Lessons**:
  1. **An OR chain is the opposite of diagnostics.** The more conditions, the more information a silent false throws away.
     Better to write a few extra ifs than one long OR.
  2. **The success path must log too.** When only failures log, "no log" can mean two things:
     success, or never reached. Log one line on success and the ambiguity disappears.
  3. **"Unobservable" is fixable.** When you hit an item you can only mark "to observe", ask first:
     can one log line make it observable? Usually yes.

### P-143 ★★★ "The files are lost" was really a search scope too narrow: the firmware had been on the D drive all along

- **Symptom**: `.cache/firmware/k60-gpu/` was empty and the build reported
  `FileNotFoundError: gmu_gen70000.bin` at `build-pong-adreno-platform.py:64`.
  So `CONFIG_XNU_PONG_ADRENO_PLATFORM` was set to `n` and the GPU dropped out of the build for six rounds.
- **Real cause**: the five firmware files had been in `/mnt/d/Android/k60-ios/firmware/k60-gpu/` all along
  ```
  74,676 B  a730_sqe.fw
  57,272 B  gmu_gen70000.bin
   3,564 B  a730_zap.mdt
   2,236 B  a730_zap.b01
   3,416 B  a730_zap.b02
  ```
  and `porting.toml:248` had said so for a long time:
  > The GPU firmware set is complete under D:/Android/k60-ios/firmware/k60-gpu
- **The scope I searched**: `<workspace>`, `/mnt/e/hackios`, `/opt/k60`
  — **`/mnt/d` was missing**. And REPO-INVENTORY.md states plainly that `D:\Android\k60-ios` is
  one of the locations where the 48 repositories are distributed.
- **Recovery**: copied back into `.cache/firmware/k60-gpu/`, SHA256 verified identical,
  `CONFIG_XNU_PONG_ADRENO_PLATFORM=y` set back. Build artefact 54,243,328 B (270 KB more than with it off),
  `libPongAdrenoPlatform.a` 406,464 B, all GPU symbols in the kernel.
- **Lessons**:
  1. **Read the repository inventory before searching for files.** `REPO-INVENTORY.md` and `porting.toml`
     already state where the assets are, which is more reliable and faster than a whole-disk `find`.
  2. **"Lost" must first be split into "deleted" and "not where I looked".** This was the latter,
     and it cost the GPU line six rounds.
  3. **porting.toml's findings are an asset inventory, not just conclusions.**
     It records the firmware paths, the sizes, and which scripts consume them.

### P-144 ★★★ `pong_metal=2` never publishes an accelerator — this is not a bug, it is by design

- **Symptom**: the `IOAcceleratorES provider published` count is always 0, `native Metal entry`
  never appears, frame rate 0.
- **Code fact** (`drivers/PongAdreno/PongAdrenoNativeGlue.cpp:30, 44`):
  ```c
  const bool enabled = PE_parse_boot_argn("pong_metal",&metal,sizeof(metal)) && metal == 1;
  ...
  if (PE_parse_boot_argn("pong_metal",&metal,sizeof(metal)) && metal == 1) {
      const IOReturn status = PongAdrenoPublishMetalAccelerator();
  ```
  **It only publishes when the value is exactly 1.** `pong_metal=2` takes the "do not publish" branch,
  so judging the Metal provider by a `pong_metal=2` log means nothing was tested at all.
- **The diagnostic defect that coexists with it**: `PongAdrenoPublishClient`'s four `return false`
  branches all log nothing, so "published = 0" cannot distinguish:
  1. `backend` already exists (duplicate publish)
  2. `device` is null
  3. `device->healthy()` is false (CP backend unhealthy)
  4. `native_adreno_publish()` returned an error
  5. `native_adreno_published_service()` returned null
  6. `PongAdrenoConfigureService()` failed
  7. `pong_metal != 1` (not published by design)
- **Fix (2026-11-12)**: every branch prints `PONG METAL: <reason> (<value>)`,
  and "failed" is explicitly separated from "not published by design":
  ```
  publish skipped: already published (1)
  publish skipped: null backend (0)
  publish skipped: CP backend unhealthy (0)
  native_adreno_publish failed (<IOReturn>)
  native_adreno_published_service returned null (0)
  configure service failed; native healthy = 0|1
  accelerator not published: pong_metal is not 1, value=<n>
  accelerator not published: pong_metal absent, value=0
  ```
- **Artefact verification**: kernel.macho sha256 1583b632, all seven strings present,
  the pre-existing GPU symbols (PongAdrenoGmuFirmware / IOAcceleratorES / K60METALPLUGIN)
  and the other hardware markers did not regress.
- **Lessons**:
  1. **Judging by the log of the wrong setting is worse than having no log.** `pong_metal=2` is stable but
     publishes nothing; its stability does not prove the Metal path works. Confirm which branch the parameter
     lands in before running.
  2. **"Not published by design" is also a failure mode and must be separated from "error".** Both look like
     "nothing published", but one needs a parameter change and the other needs a code fix.
  3. **P-142's lesson holds here too**: a string of bare `return false` equals no diagnostics.

### P-145 ★★★ `pong_adreno_start` never appeared in board.toml, so the GPU platform never started

- **What the code requires** (`drivers/PongAdreno/PongAdrenoPlatform.cpp:479`):
  ```c
  if(!PE_parse_boot_argn("pong_adreno_start",&requested,sizeof(requested)) || requested!=1) return;
  ```
  Without this argument `pong_adreno_start_optional()` returns immediately and **the whole Adreno platform
  never starts**.
- **Measured**:
  ```
  git log -S'pong_adreno_start' -- board.toml   -> no output (never added)
  board.toml kernel_args: pong_adreno_start / pong_metal / pong_gpu_scanout all missing
  ```
  **Not one** of the three GPU switches was set.
- **Consequence**: `IOAcceleratorES provider published = 0` and the missing `native Metal entry`
  need no bug to explain them — the platform never ran.
- **Fix (2026-11-12)**: add `pong_adreno_start=1` (582 → 602 bytes, 6 left).
  Only this one this round, no `pong_metal`: one variable at a time.
- **Byte budget** (608 limit):
  ```
  now 30 items, 602 bytes, 6 left
  pong_metal=1 needs 13 bytes (12 + 1 space) -> over by 7
  ```
  Turning on `pong_metal` next time means freeing space first. Candidate: `k60_selftest_reboot=300` (23 B,
  unattended self-test reboot, not needed for manual testing).
- **Lessons**:
  1. **"The feature is not taking effect" — check the switch before the code.** All three GPU switches were
     missing, which happens earlier than any driver bug.
  2. **next_action in a document does not mean the config has it.** `porting.toml:240` says
     "Boot with pong_adreno_start=1", but board.toml never had it — document and config out of step.
  3. **`git log -S<key> -- board.toml` is the fastest way to tell whether a switch was ever configured.**

### P-146 ★★★ A 1.2 MB firmware patch existed but never entered series, and was never referenced

- **Symptom**: `/opt/k60/trees/usb-cdc-mainline/device/patches/xnu/0403-k60-goodix-fw.patch`
  1,211,985 B, containing the complete K60 touch firmware and config:
  ```
  k60_goodix_fw[]    223,744 B   sha256 1e647510...   = goodix_firmware_m11a.bin
  k60_goodix_cfg[]     1,627 B   sha256 a730e3f1...   = goodix_cfg_group_m11a.bin (full container)
  #define K60_GOODIX_FW_LEN   223744
  #define K60_GOODIX_CFG_LEN  1627
  ```
  But: **it is not in `patches/xnu/series`, the file is not in the repository at all, and the patch declares
  no function or extern — both arrays are `static` and referenced by nobody, so the compiler drops them.**
- **Why this is a big deal**:
  1. We spent several rounds arguing about "how many config bytes to send" (P-134, corrected repeatedly),
     while the answer had been sitting in this file all along as the full 1,627-byte container
  2. It existed only in the `/opt` build input, not in version control — the same loss mode as the GPU firmware and the DT nodes
  3. Even in series, unreferenced equals not added: 1.2 MB of dead data
- **Done**: synced into the repository at `patches/xnu/0403-k60-goodix-fw.patch`.
- **To do**: decide who references it. Two candidates:
  - the touch driver (`pong_goodix.c`) using `k60_goodix_cfg` in `goodix_apply_config`
    instead of the embedded `k60_cfg[1488]`
  - the firmware download path (ISP) using `k60_goodix_fw`
- **The final answer on config length**:
  ```
  Full container goodix_cfg_group_m11a.bin   1,627 B  = container[0:1627]
    ├─ [0:18]    header (total_len/checksum/version/sub_len)
    ├─ [18:22]   sub_len = 1609
    ├─ [22:38]   "Berlin" + padding
    ├─ [38]      sensor id 0xff
    ├─ [39:55]   "9916R" + padding
    ├─ [139:141] 4e 4d (ASCII "NM", vendor block marker)
    └─ [141:1627] 1,486 B (the stretch we originally stripped out)

  yibiya's k60_cfg[1488] = container[139:1627]
  ```
  **All three candidates now have an explicit source; it is no longer guesswork.**
- **Lessons**:
  1. **"The file exists" and "the file takes effect" are two different things.** A 1.2 MB data file that is not
     in series and not referenced might as well not exist.
  2. **The build input directory is volatile.** Patches, DT nodes and firmware that exist only under `/opt`
     must be synced into the repository, or one clean wipes them.
  3. **When you have been stuck on something for a long time, search the whole repository and build input first.** P-134's answer had been lying in 0403 for a long while.

#### P-134 final conclusion (2026-11-12)

Every candidate for the config length now has an explicit source; it is no longer guesswork:

```
Full container goodix_cfg_group_m11a.bin   1,627 B   = container[0:1627]
  [0:18]     header total_len=1627 / checksum / version / sub_len=1609
  [18:22]    sub_len
  [22:38]    "Berlin" + padding
  [38]       sensor id 0xff
  [39:55]    "9916R" + padding
  [139:141]  4e 4d (ASCII "NM", vendor block marker)
  [141:1627] 1,486 B (the stretch originally stripped out)

yibiya's k60_cfg[1488] = container[139:1627]
the repository's 0403 embedded k60_goodix_cfg[1627] = container[0:1627]
```

**These numbers (1627 / 1609 / 1488 / 1486) can all now be mapped to a concrete range of the container.**
The next step is only to decide which range to send; it is no longer "we do not know whether this is right".

#### P-146 measured (2026-11-12): entering series is not enough — with nobody referencing it, not one byte survives

After adding 0403 to series and committing, the build gave:

```
kernel size: 54,243,328 B  ->  54,243,328 B   diff +0 B
k60_goodix_fw / k60_goodix_cfg symbols in nm:  0
"BERLIN" in strings:  MISSING      <- magic of the 223,744 B firmware header, not in the kernel
"9916R" in strings :  present      <- this one comes from the 1488 bytes embedded in the touch driver
"M11HTC" in strings:  present      <- same as above
```

**Conclusion: with no reference to a `static` array, the compiler throws away all 1.2 MB and the kernel size does not change by a byte.**

This is the strongest proof of "the file exists ≠ the file takes effect": the patch entered series, `git apply` succeeded, the build passed, the kernel was produced — every step "succeeded", but the data is simply not in there.

**For it to take effect, code must reference it.** Two reference points to do:
1. the touch driver, in `goodix_apply_config`, switching to `k60_goodix_cfg` (1627 B full container)
2. the firmware download path using `k60_goodix_fw` (223,744 B, for ISP)

**How to judge**: only after a reference appears do the kernel size change and the `nm` symbols appear. Those two are the only reliable criteria — build success alone proves nothing.

### P-147 ★★★ The diagnostics went into the kernel, but the function holding them never ran

- **Symptom**: a dozen rounds of adding diagnostics to the touch driver (device confirm, SPI mode select, CFG-DL,
  COORD-MODE, touch point parsing); the build succeeded and `strings` found these strings in the kernel,
  **but not one line appeared in the on-device log**.
- **Root cause**: the first thing `pong_goodix_init()` does is `configuration()`, which asserts DT properties
  with a chain of short-circuiting `&&`:
  ```c
  property(entry,"avdd-gpio",&avdd_gpio,4) &&
  property(entry,"max-x",&max_x,4) && property(entry,"max-y",&max_y,4) &&
  ...
  avdd_gpio==71 && max_x==14400 && max_y==32000;
  ```
  But the built ADT has **no `avdd-gpio` at all**, `max-x` is 1080 (panel pixels) and `max-y` is 2412.
  `configuration()` returns false every time → `pong_goodix_init()` prints
  `Pong touch: missing/incompatible K60 DT` and returns →
  **not one of the diagnostics in `bring_up()` / `touch_thread()` ever ran.**
- **Why it was hard to spot**:
  1. Build succeeded, symbols present, strings present — every step "looked right"
  2. Unless that `missing/incompatible K60 DT` line was captured, the early exit was completely invisible
  3. The more diagnostics you add, the easier it is to assume "added means printed"
- **Lessons**:
  > **Before adding diagnostics, confirm the function holding them will be executed.**
  > **One `if (!configuration()) return;` can turn the next few hundred lines into dead code, and the build knows nothing about it.**
- **Gate added**: `scripts/check-dt-asserts.py`
  - parses the `property(entry,"X",...)` calls in the driver patches
  - compares them against the properties of the corresponding node in `dts/mondrian.dts`
  - fails when one is missing (frozen zone warns only)
  - wired into `clean_build.sh`, ahead of `check-scope-freeze.py`
- **It immediately caught a second problem**: `pong-touch` is missing not only `avdd-gpio` but also `bitbang-pins`
  — the latter is required by the GPIO fallback path.

#### Same-class risk list (not checked yet)

Any other `configuration()`-style "assert everything, exit on one miss" code silently disables diagnostics the same way:

- [ ] `pong_buttons`' `configuration()` — confirmed all 6 properties present
- [ ] `PongAdrenoPlatform`'s `start()` precondition checks
- [ ] `NativeUfs`' `configuration()`
- [ ] `PongAudio` (when implemented)

**Every new driver that writes a `configuration()` must add the matching rule to `check-dt-asserts.py` at the same time.**

### P-148 ★★★ Three copies + reset/rebase = repeated data loss, and no gate

- **Symptom**: the same file exists in three places, synced by hand with `cp`:
  ```
  E:\hackios\UniXNU-mondrian          repository (version control)
  /opt/k60/trees/usb-cdc-mainline/device  build input (what the build actually reads)
  <workspace>/scratch                    drafts
  ```
  Any "I changed one place and forgot the other" produces silent divergence.
- **What was actually lost**:
  1. `0403-k60-goodix-fw.patch` (1.2 MB touch firmware) exists only in the build input, not in the repository
  2. the `pong-touch` / `pong-buttons` DT nodes exist only in the build input; the repository's `mondrian.dts` is
     a 2,364-byte shell, and one clean takes all the nodes with it
  3. the eight-step table was deduplicated, the README regenerated and verified, **and then one `git reset --hard` erased it**
  4. `check-dt-asserts.py` sat in scratch for hours, and no build ran it during that time
- **Three independent mechanisms, each lethal on its own**:
  | Mechanism | Consequence |
  |---|---|
  | manual `cp` both ways | divergence accumulates silently, with no warning |
  | `git reset --hard` | uncommitted work vanishes, no warning |
  | `git pull --rebase` | replays the local revert back in — that is how the 0403 revert was undone |
- **Lessons**:
  > **One file in two places will always diverge.**
  > **A revert only counts once it is pushed.**
  > **Whatever passes in scratch must move into `scripts/` in the same round.**
- **Iron rule added**: `AGENTS.md` iron rule 5 — the repository is the only source of truth, the build input is its mirror,
  one direction only (repository → build input), and the only permitted mover is
  `scripts/sync-device-input.py`. Plus three corollaries: `git status` before a reset;
  `pull --rebase` replays the commits from before the revert; scratch holds drafts only.
- **Gate added**: `scripts/sync-device-input.py --check`
  - compares repository and build input file by file
  - deletes patches that exist only in the build input (the repository is the source of truth)
  - fails on any difference; wired into `clean_build.sh` ahead of the other gates
  - syncs automatically once before checking, so a failure means "even the automatic sync could not save it"

### P-149 ★★★ Wrong DTB: the image grew 478 KB and would not boot

- **Symptom**: `fastboot boot` returned OKAY, the device blinked, reset back to fastboot, and COM5 never enumerated.
  No log at all, because it died before UEFI read the kernel.
- **Root cause**: `./unixnu bootimg --dtb` was handed the full DTB from the UEFI repository:
  ```
  ❌ uefi-mondrian/Platforms/Xiaomi/mondrianPkg/FdtBlob/sm8475-xiaomi-mondrian.dtb   480,692 B
  ✅ out-baseline/.../device-tree/hardware.dtb                                         2,925 B
  ```
  What goes into the boot.img kernel region is `gzip(shim + firmware) + dtb`, with the DTB hung directly on the tail.
  A 480 KB DTB grows the kernel region from 548,774 B to 1,027,600 B.
- **How to see it at a glance**:
  ```python
  # decompress gzip ignoring the tail, compare the gzip part and the tail of the two images
  keep: gzip 546,908 B (same sha256) + tail 1,866 B
  r52 : gzip 546,908 B (same sha256) + tail 480,692 B
                                              ↑ the whole difference is here
  ```
  **The firmware is identical; the entire difference is the DTB.** That one line rules out
  "the firmware changed / the kernel changed / the boot-arg changed" in one go.
- **Lessons**:
  > **When an image will not boot, split the boot.img and compare it segment by segment; do not guess at kernel / boot-arg / driver.**
  > **Both component repositories have files whose names look like a DTB; picking the wrong one is a 478 KB difference.**
- **Written down in**: `docs/engineering/REPO-MAP.md` section 4, stating which DTB to use and the criterion.

### P-151 ★★ Picking a single upstream file overwrites our changes to the same file

- **Symptom**: `pick-upstream.py --apply` took yibiya's `9269d7728` (wallpaper native stock restore),
  and the `patches/xnu/0340-k60-uilib-deploy.patch` it carried overwrote our version.
  Change volume **12,438 lines, 9,500 deletions**, after which `git apply --check` failed in the kernel:
  ```
  error: patch failed: bsd/dev/k60_uilib.c:0
  error: patch failed: bsd/kern/kern_exec.c:7772
  ```
- **Root cause**: a file-level pick is "replace the whole file", with no three-way merge. When both we and upstream
  **have modified the same file**, taking upstream means losing our changes. These two files happened to be
  1,052,856 B (ours) against 626,395 B (upstream), a huge difference.
- **Fix**: `git checkout <previous tag> -- <that file>` for a precise rollback, then **hand-merge the intent of that
  upstream commit in**, instead of replacing the whole file.
- **Lessons**:
  > **The unit of a pick is a change, not a file.** When both sides have touched the same file, whole-file replacement always loses something.
  > Criterion: the size change of the file across the pick — a 40% drop almost certainly overwrote local work.
- **Check added**: `pick-upstream.py` should compare file sizes before overwriting and warn instead of silently overwriting
  when the drop exceeds a threshold. (Not implemented yet; recorded here.)

### P-152 ★★★ The Data volume UUID must be the real volume on the device, not the one in the seed

- **Symptom**: the kernel panics by itself after booting as far as the owner mount:
  ```
  PONG APFS: wait for Data UUID 6DCCF70A-6FD6-403E-ACED-95313CD7CBB8, timeout=5s
  PONG APFS: Data UUID wait timed out
  PONG APFS: window media uuid=1BCD69FF-24A5-48B1-94B6-8FE592B2F597 bsd=disk5s1 depth=8
  K60DATA UFS Data window not published for 6DCCF70A-...
  K60PANICARGS K60SELF novar ... datastage=0 dataerr=2 @kern_exec.c:8463
  ```
- **Root cause**: `CONFIG_XNU_OWNER_DATA_VOLUME_UUID` was set to the volume UUID `6DCCF70A-…` from
  `seed/k60-data-seed.dbr` (32 MiB). The 19.87 GiB Data window on the device is a different volume that grew later,
  with UUID `1BCD69FF-24A5-48B1-94B6-8FE592B2F597` and container `068446EE-…`.
  The Data window itself published fine and the APFS container mounted — the kernel simply waited 5 seconds
  on a UUID that does not exist.
- **Criterion**: in the console, `PONG APFS: window media count=N window=PongDataWindow` and the following
  `window media uuid=…` lines are the volumes that really exist in that window. The UUID must be copied from there,
  never derived from the seed.
- **Fix**: `configs/mondrian_defconfig` changed to the real volume UUID, with the log source written into the comment.
- **Gate**: `scripts/check-data-identity.py` (cross-checks the defconfig UUID against the Data window volume UUID
  observed in the newest console log).

### P-153 ★★★ The UFS Data branch's size ceiling is 2 GiB, so a 19.87 GiB window is silently dropped

- **Symptom**: with the UUID fixed it still ends in `goto done`, and `/private/var` does not mount.
- **Root cause**: the UFS branch of `patches/xnu/offline-owner-systemos-mount.patch` kept the scratch-seed era
  `if (!size || size > UINT64_C(0x80000000) || (size & 4095)) goto done;`.
  2 GiB is right for a 32 MiB seed and is a rejection for the real 19.87 GiB window.
- **Fix**: raise the UFS branch ceiling to `0x800000000` (32 GiB = the whole unixnu partition).
  The scratch-seed branch (`XNU_NATIVE_RAM_BLOCK`) stays at 2 GiB, unchanged.
- **Gate**: `scripts/check-data-identity.py` also checks that the ceiling is greater than the actual byte count of the
  Data window in the manifest.

### P-154 ★★ The rebuilt firmware volume cannot find the payload volume; `cf448571…` still boots

- **Symptom**: `fastboot boot` passes, the screen shows "failed to find an operating system", the serial port shows:
  ```
  UNIXNURAMDISK: initrd block device 0xAA961000 size 0xD69DE00 Success
  UNIXNU: config: no boot entry found
  UNIXNU: config: none found, using built-in configuration
  UNIXNU: menu: shown 4 entries, default 0 'exit'
  ```
- **Ruled out**: `Platforms/` shows zero difference against the yibiya repository, the six Mu patches are byte-identical,
  the submodule pins are the same, the payload FAT is at `0x87000` and `EFI/UNIXNU/unixnu.toml` is readable
  (verified with `mtype`), and rebuilding with the Mu patches removed (`patches = []`) still fails.
- **Current state**: not localised. The workaround is `unixnu bootimg --fd /tmp/old-fd.fd` with the firmware volume
  `cf4485712c2999c1fb7c1937a5b1f836dd3e9150073fb9b151b581d375195d0f` (extracted from
  `keep-a6165f2404568c1d.img`) to get the kernel line running first.
- **Known baseline**: `cf448571…` boots; the three pins rebuilt from source (`3c9c7b2`+six patches →`f50b7e3c…`,
  `3d2a9fa`/`6f805f2`+six patches → immediate conflict) cannot reproduce it.
- **Gate**: beyond `scripts/check-boot-procedure.py`, add `check-fd-identity.py`:
  if the firmware volume sha256 is not `cf448571…` at packaging time and `--allow-unverified-fd` is absent,
  refuse to emit an image.

### P-155 ★★ Adding lines to an early patch to kern_exec.c breaks every patch after it

- **Symptom**: `0302-data-cap-execerr-kxp.patch` fails to match at `bsd/kern/kern_exec.c:7434`,
  wasting a whole 15-minute build round:
  ```
  unixnu: XNU patch .../0302-data-cap-execerr-kxp.patch: git failed (1):
  error: patch failed: bsd/kern/kern_exec.c:7434
  ```
- **Root cause**: `offline-owner-systemos-mount.patch` added 2 comment lines in `kern_exec.c`,
  shifting the context of every later patch down, which `git apply` will not accept.
- **Fix**: when editing this kind of early patch, **keep the net line count unchanged** — either fold the comment
  into an existing comment block, or delete the same number of lines. `fix-patch-hunks.py` only recomputes hunk
  counts; it will not find offsets for later patches.
- **Gate**: the `[S]` series fingerprint in `porting-gate.py` demands an explicit `--force-new-series` when patch
  content changes; the real criterion is still a full build.

### P-156 ★★ When a boot-arg value goes outside the driver's accepted range, the hardware is switched off by its own parameter

- **Symptom**: one line on the serial port,
  `Pong touch: unsupported k60_touch_se=19; normal UI boot continues`,
  then no touch log at all, polls/reports all 0. It looks like a broken driver.
- **Root cause**: `board.toml` said `k60_touch_se=19` (a leftover from an old numbering), while the driver
  `pong_goodix_init()` accepts only `1..7`:
  ```
  (void)PE_parse_boot_argn("k60_touch_se", &stage, sizeof(stage));
  if (!enabled || !stage) return;
  if (stage > 7) { printf("Pong touch: unsupported k60_touch_se=%u; ..."); return; }
  ```
  Out of range it `return`s and the whole touch thread never starts; while the table in
  `docs/engineering/BOOT-ARGS.md` had said "0..7" all along — the document right, the config wrong, and nothing
  comparing them.
- **Fix**: `board.toml` back to `k60_touch_se=6`.
- **Gate**: `check-boot-args.py` gains range validation — the `A..B` / `≤ N` entries in the "range" column of the
  `BOOT-ARGS.md` table are parsed into criteria and compared one by one with the actual arguments in `board.toml`;
  out of range fails.
  The document thus becomes executable: a range that is written down gets checked.

### P-157 ★★ The config is on, but the build script never linked the library in

- **Symptom**: `configs/mondrian_defconfig` has `CONFIG_XNU_K60_PHYSICAL_BATTERY=y`,
  `.config` has `y` too, but the kernel has neither a `K60Battery` object file nor a single string,
  and the serial log has zero `K60Battery` lines — it looks like "the battery driver does not work".
- **Root cause**: `E:\hackios\UniXNU\scripts\unixnu\kernel.py:17-26` only exports
  `XNU_K60_PHYSICAL_BATTERY=1`; what actually links `libK60PhysicalBattery.a` in is
  `tree/scripts/build-xnu-4k-baseline.sh`, and that script **neither reads this environment variable nor has
  `-Wl,-force_load`**. `patches/xnu/0602-physical-battery.patch:10-12` states plainly that "the parent process
  must do these two steps itself". So the config is pure decoration.
- **Evidence**: `llvm-nm kernel.macho` has `IOKitBSDInit.cpo` and no K60Battery/PongPower object or symbol;
  `scripts/build-k60-physical-battery.py` is never called;
  `libK60PhysicalBattery.a` does not exist under `/opt/k60`.
- **Fix (not done)**: in `build-xnu-4k-baseline.sh`, mirror the UFS archive block
  (`test -f` + `-Wl,-force_load` at `:927-929`) for the battery archive, and the step that generates the archive
  has to enter the build chain.
- **Gate (not done)**: any switch of the `CONFIG_XNU_*_MOUNT`/`_BATTERY` kind that "links an external archive"
  should have a check: when the switch is `y`, `build-xnu-4k-baseline.sh` must contain the corresponding
  `-force_load`, or it fails. Today's `check-rules.py` has no such class.

## P-159 The boot image's args have two sources; the copy inside the kernel is not the one the firmware passes

Scanning `-v native-ufs=1` out of the boot image gives the kernel's embedded default; what the firmware actually passes to the kernel is the `args` in `EFI/UniXNU/unixnu.toml` on the payload volume. On 2026-11-12 three rounds of A/B used the former as the baseline, and all were invalid. How to read it: `mtype -i IMG@@552960 ::/EFI/UniXNU/unixnu.toml` (the offset is a decimal byte count; `@@0x87000` reports `init :: non DOS media`).

**Lesson**: read the payload's unixnu.toml with mtype; do not guess it from kernel strings.

## P-160 The only differences in the keep image that boots are pong_metal=2 and k60_touch_se being unset

The bootable image of 2026-11-11 had 28 args, including `pong_metal=2`, `k60_autoreset=300`, `applog=1`, and not including `fb_threads`/`k60_textonly`/`k60_touch_se`. The 2026-11-12 image changed `pong_metal` to 1 and set `k60_touch_se` to 6, and SpringBoard survived only 4 lines before exit=255, `cs_invalid_page` went from 1 to 11 and corpse from 4 to 27; pairing the keep kernel with the same bad args crashed the same way, so it is not a kernel version problem.

**Lesson**: board.toml's kernel_args are governed by the bootable set; a change must come with a real boot comparison.

## P-161 Neither the shared_region boot failure nor K60DYLD rc=2 is the cause of the crash

The log of the crashing run has `shared_region ... vm_shared_region_start_address() failed` and `K60DYLD .../dyld_shared_cache_arm64e rc=2`, but the bootable keep image has both lines as well. The image never contained `dyld_shared_cache_arm64e` anyway (the whole image has only `_arm64` and its sub-caches .01–.42), so rc=2 is normal.

**Lesson**: before calling something a regression, find the same log line in a bootable image.

## P-162 · a patch must be a diff git can parse

Four independent pitfalls pointing at the same consequence: `git apply` rejects the patch only after the compile is already running.

1. hunk counts disagree with the number of body lines (after adding or deleting lines `@@ -a,b +c,d @@` was not recomputed).
2. the file lacks a trailing `\n`, git counts one line short and reports `corrupt patch at line <last line + 1>`.
3. a blank context line was left at the end, and the counter counted it into the body.
4. a net-deletion edit: more `+` lines removed than added, and after recomputation it still does not match.

Instance from 2026-11-12: `patches/xnu-ipados18/0245-k60-cpu-clusters.patch` was missing its trailing newline and lay in the tree for a long time; only whoever edited it would find out. After adding one byte `git apply --numstat` passed.

Check: `python3 scripts/check-patch-apply.py` (by default it only checks patches changed relative to HEAD).

Fix priority: **try adding the trailing newline first** → then `scripts/recount_hunks.py` → if neither works, stop adding and deleting in place and **write a new standalone patch**, leaving the old one as it is.

## P-163 An SPI line's level only means something after you bias it both ways

A single read of all ones or all zeros cannot tell you whether the chip is answering: that line may be floating. The test is to read the same line once with a pull-up and once with a pull-down — if the reading follows the bias it is floating, if it does not there really is a driver on it.

Measured on this project (the "two or three biases" table in `docs/research/touch/GROUND-TRUTH.md`): pull-up all 1, pull-down all 0, which ruled out the whole class of guesses "clock too fast / wrong mode / wrong chip select / reset never released" in one go and pointed straight at a missing supply. How to check: `grep 'K60BB frame' <usblog>/console.log` and see whether the `miso` counts under the two biases equal all ones and zeros for the bit count.

## P-164 A banner printed at the start of boot gets read as the conclusion

`drivers/PongAdreno/PongAdrenoPlatform.cpp:411` used to print `PONG ADRENO: startup requested; no accelerator published`, and that line appeared at the **start** of `run()` — all 22 boot stages after it returned `result=0` (PAS13 ZAP authentication, CP ME_INIT, nonsecure switch, authentication fence, IRQ 332 ownership, BO pool all passed). Readers of the log (including several internal conclusions in this project) took it as the result, so the wrong judgement "the GPU did not start" was inherited over and over.

How to decide: `grep -an 'PONG ADRENO' <usblog>/console.log | tail` and look at the **last** stage record, not `sort -u` or the first few lines. The last line in the current log is `CP/user-client startup result=0 a=0x40000007 b=0x20010000`.

Rule: a banner only describes "what is starting now"; the conclusion must come from the last stage's result or an explicit "published/failed" line.

## P-165 One mismatched patch in the series takes itself and everything after it out

`git apply --numstat` only proves the diff is structurally valid, not that the context still matches the current tree. With hand-written hunks (especially for a file like `kern_exec.c` that several patches keep modifying), the source has already changed once the previous patch applied, and if even one of the three context lines of the new patch does not match, `git apply` drops the whole thing — **and skips every patch after it too**, while the compile errors that follow often show up in a completely unrelated file.

Instance from 2026-11-13: the hand-written `0341-k60-metal-seeds.patch` passed syntax validation; after it entered the series, `patches applied: 210` (series has 222), the new file's name never even appeared in the log, the build failed, at a cost of 13 minutes.

Rule: **always generate patches from "already-applied source + `diff -u`"**; never hand-write hunk context and line numbers.
Right after a build run `python3 scripts/check-build-applied.py`; it compares the `patches applied: N` in the log with the line count of `patches/xnu/series`.

## P-166 The build script must not write the patch list

`buildv15.sh` used to overwrite `patches/xnu/series` with `/mnt/e/k60-work/scratch/SERIES-FINAL.txt` at the start of every build. The consequences run both ways: editing the series in the repository had no effect, while editing the copy in scratch silently changed the entire patch set. One accidental deletion on 2026-11-13 happened exactly that way — two `0341` entries were removed by number prefix, one of them someone else's `0341-k60-setprop-probe.patch`, so `0342` could not find the `printf` it was supposed to change, the build stopped at 157/222, and the error said only `iorkit/Kernel/IORegistryEntry.cpp: patch does not apply`, giving no hint at all of the missing prerequisite.

Rule: the repository is the only source of truth; the build may only **read** it, then copy it to the build input. `scripts/check-build-applied.py` now compares both, and any disagreement goes red (P-166).
## P-167 The UI library changed but cannot be built: no iOS SDK on this machine

`userland/build.py ui` needs `--sdk <iPhoneOS.sdk>` or `--developer <Xcode>` (`xcrun --sdk iphoneos --show-sdk-path` in `compile_ui()`). This machine has only `/opt/unixnu-linux/CommandLineTools/SDKs/MacOSX.sdk`; there is no `iPhoneOS*.sdk` anywhere under `/opt` or `/mnt/e`. Any change to `userland/*.c` therefore cannot produce a new `libpong-ui.dylib`, and the blob embedded in `0340-k60-uilib-deploy.patch` cannot be refreshed.

Rule: **do not edit userland source without the SDK**. Editing it and not being able to build it forks the source from the blob actually flashed onto the device, which is the entire class of "looks fixed, unchanged on device".
Either bring in the SDK first (and write its path into `docs/engineering/`), or do the fix on the kernel side (a dlopen after the Data mount from the kernel is not viable; it has to run in process context).
## P-168 The battery archive is still missing Kernel.framework private headers

Before compiling the archive, `scripts/build-k60-physical-battery.py:294-296` insists on:

```python
framework = tree / '.cache/fakeroot/System/Library/Frameworks/Kernel.framework/Versions/A'
if not (framework / 'PrivateHeaders/IOKit/pwr_mgt/IOPMPowerSource.h').exists() and \
   not (framework / 'Headers/IOKit/pwr_mgt/IOPMPowerSource.h').exists():
    raise ValueError('Build the real Darwin22 Kernel SDK before this archive')
```

Measured: there is no `Kernel.framework` under `tree/.cache/fakeroot`, and `find -name IOPMPowerSource.h` across the whole tree gives **zero hits** — `IOPMPowerSource.h` belongs to Apple's Kernel.framework private headers, is not in the XNU source, so it neither appears from `installhdrs` nor can we derive it from source.

Conclusion: `libK60PhysicalBattery.a` cannot be generated on this machine, and `-force_load` has nothing to work with. This is the same class of external dependency as P-167 (userland needs iPhoneOS.sdk), not an implementation defect.

There is exactly one workable alternative, and it must be argued in the docs first: do not depend on Kernel.framework; use XNU's own `iokit/IOKit/*` and `osfmk/*` headers instead, and build the battery driver into the kernel as a source patch under `patches/xnu/` (the direction of `0602-physical-battery.patch`), rather than as an external archive. Taking that route requires first proving every symbol it needs has a definition in the kernel.

### P-168 follow-up measurement (2026-11-13)

The header of `patches/xnu/0602-k60-physical-battery.patch` says in its own words "The builtin archive inherits XNU's real IOPMPowerSource". That sentence does not hold on this tree: `grep -rl 'IOPMPowerSource\|IOPowerSource\|AppleSmartBattery' iokit/ bsd/` returns **zero files**, and `iokit/IOKit/pwr_mgt/IOPM.h` has no such class either. That is, the class exists only in Apple's Kernel.framework, not in the XNU source.

So the real cost of the two routes is:
- archive route: needs Kernel.framework (the body of P-168), not present on this machine.
- source route: needs a **newly written** IOService nub in the tree to publish the battery properties; you cannot "inherit" a class that does not exist. That is not a patch, it is a driver.
## P-169 Your own constants don't count: the producer must pass the consumer's parser

The first version of `K60HandoffBuild` used a self-invented magic `0x6b363068` ("k60h"), wrote flags `0x7`, and laid out `epoch`/`smem_bytes`/`adsp_bytes` as `u32 + pad`. All of that passed my own field-table assertions — because that table was written from the same understanding.

Wired up to the only consumer, `K60BatteryConfig.c:54 k60_adsp_handoff_parse()`, it exposed immediately:
- magic must be `K60_ADSP_HANDOFF_MAGIC 0x4842364b` ("K6BH");
- flags must equal `K60AdspHandoffRequired` (measured **0xf**, all four bits set, not 0x7);
- `epoch`(`+16`), `smem_bytes`(`+32`), `adsp_bytes`(`+48`) are all read as **64-bit**, and `u32 + 0` only matches by numeric luck; past 4 GiB it truncates silently.

Rule: **code that generates any binary structure must have a test that hands the artefact to the real parser**. A self-certifying field table catches offset errors, not "my constant is not their constant".

Landed as: `scripts/tests/test-k60-handoff-build.c` now links the real `K60BatteryConfig.c` (a separate compilation unit, to avoid the `fits`/`le32` name clash), and asserts `k60_adsp_handoff_parse(out, 104, &cfg, &parsed) == K60ConfigOk` with the read-back offsets matching the epoch.
## P-170 Newly written driver source is not referenced by any build step

`drivers/PongPower/K60Smem.c`, `K60HandoffBuild.c` and `K60BatteryConfig.c` all pass the host-side tests (`TESTS OK 10`), but:

```
grep -n 'PongPower\|K60Smem\|K60Handoff' scripts/build-xnu-4k-baseline.sh \
    patches/xnu/0602-k60-physical-battery.patch
→ zero hits
```

That is, these three files **were never compiled into the kernel**. The kernel link only takes archives of the `$ROOT/build/<name>/lib<Name>.a` kind (`KERNEL_EXTRA_ARCHIVES` + `-Wl,-force_load`), and `build/smem-handoff/` does not exist at all. A passing test only proves the logic is right, not that it runs on the device.

Rule: **host tests passing ≠ in the kernel**. New driver source must land three things at once:
① produce an archive in `scripts/build-xnu-4k-baseline.sh`; ② add it to `KERNEL_EXTRA_ARCHIVES` and `-force_load` it; ③ have a marker string that `strings kernel.macho` or the on-device log can verify.
Without ③, "no log seen" cannot distinguish "did not run" from "ran and printed nothing".

### P-170 follow-up: the archive route does not work on this machine; the right route is a patch into bsd/dev

The compile command at `E:\hackios\UniXNU-mondrian\scripts\build-pong-ram-block-macos.py:32-38` is

```python
subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], ...)
command = ['xcrun', '--sdk', 'iphoneos', 'clang++', '-target', 'arm64-apple-ios16.0', ...]
```

which means **every `KERNEL_EXTRA_ARCHIVES` archive needs the iPhoneOS SDK**, and this machine does not have it (P-167). Archives like `device/mac-build/native-ufs/libNativeUfs.a` were compiled on another machine and committed to the repository, which is why they link, while any `.c` we write here can never enter an archive.

The correct path is not to build an archive but to take the already-proven one: **put the source file into `bsd/dev/` with a patch, and add a line to `bsd/conf/files`** — that is how `zzzz…-pong-touch-console.patch` adds `bsd/dev/pong_goodix.c`, and the kernel compiles with the same CLT clang, no iOS SDK needed.
So the landing plan for `K60Smem.c` / `K60HandoffBuild.c` is:
① added by patch as `bsd/dev/pong_smem.c` / `bsd/dev/pong_handoff.c`;
② `bsd/conf/files` gains `dev/pong_smem.c   optional pong_touch` (or a new config dependency);
③ keep the short `K60HO ` prefix marker, `strings kernel.macho` must find it.
## P-171 Inferring build-time intermediate state from post-build artefacts is an infinite loop

`0611-k60-smem-handoff.patch` needs two lines added to `bsd/conf/files`. Three attempts, all `error: patch failed: bsd/conf/files:399`:

1. anchor the three lines before `bsd/dev/pong_buttons.c` (3 lines of context) → fails at 402;
2. same anchor, single line of context → fails at 402;
3. regenerate byte for byte from "the tree after a successful build" (`repr()` comparison confirming tabs match and no CRLF) → fails at 399.

The reason is that every failed build does `rm -rf tree/`, so what I can read is always the tree of the **last success**, while what has to be fixed is the tree **during the next build**. Patching a hole at time B with bytes from time A never matches.

Rule: **for a patch that edits a build-time file, the anchor must come from a stable source in the repository** (for example `bsd/dev/pong_goodix.c`, a source the patches deterministically generate), never from `.cache/xnu-work`.

Landing method (verified `BUILD OK`): take this kind of insertion out of the series patches and let the build driver do it after the patch stage, **polling until the anchor appears** — when the tree has just been unpacked that `pong_buttons.c` line does not exist yet, and either a fixed wait or an immediate execution ends in `anchor missing`.

`E:\k60-work\scratch\append_conffiles.py` is that pattern: re-read every second, insert `pong_smem.c` / `pong_handoff.c` only once `bsd/dev/pong_buttons.c\t\t\tstandard` is visible, and return at once if already inserted.

### P-172 Upstream commits cannot be picked file-wise into a local K60 fork's build script

- Symptom: `8cdfcffa0 feat(gpu): decouple the GPU addon mount from the offline broker` touches only three places: `patches/xnu/series`, `patches/xnu/zzy-native-gpu-addon-mount.patch`, `scripts/build-xnu-4k-baseline.sh` (turning the `XNU_NATIVE_OFFLINE_GPU` gate into `XNU_GPU_ADDON`).
- Why it cannot be picked: the local `scripts/build-xnu-4k-baseline.sh` is a 67,777 B K60 fork (with `HOST_CC` and conf/files hooks), upstream's is 44,810 B; `patches/` is inside `SKIP_PATHS`, so a file-level pick takes only the script and leaves a "half-merged" state — script swapped, patches not.
- Handling: judged **unmergeable (file level)**. The semantics (gate variable rename + 0398 adding the `/private/var/ngpu` directory) are ported by hand separately, and must stay in sync with `patches/`.
- Criterion: look at `git show --stat` before picking; if it hits both a `SKIP_PATHS` file and a file outside it, that is a half merge and must be refused.

### P-173 Overturning a correct implementation using the wrong artefact path

- Symptom: `pong_adsp_image.o` obviously existed, yet two rounds in a row judged it "not compiled", because the path checked was
  `build/xnu/ios-obj/DEVELOPMENT_ARM64_PONG/pong_adsp_image.o` while the actual artefact is in
  `build/xnu/ios-obj/DEVELOPMENT_ARM64_PONG/bsd/DEVELOPMENT/pong_adsp_image.o`.
- Cost: on that basis a `conf/files` hook that was actually correct was declared broken, the hunk was deleted from the patch, the script changed, and the build rerun three times.
- Rule: before concluding "the artefact does not exist", confirm the path shape with `find … -name <artifact>`; compound commands like
  `ls | grep` called from an inline shell must first be proven to actually expand their variables (PowerShell on this machine eats `$`).
- Same family: P-163 (a single reading is not enough to decide). The observation method itself must be verified first.

### P-174 main treated as a workbench: experimental changes pressed straight onto the stable baseline

- Symptom: `bf487cc`, `c2fa573`, `234574a`, `d1843c2`, `20ce047`, `8206fb4` were committed straight to `main`,
  and the patch series (`patches/xnu/`), the build script (`scripts/build-xnu-4k-baseline.sh`) and driver source
  (`drivers/PongPower/`) among them are all changes not yet verified on device.
- Cost: the "Docker baseline" meaning of `main` stops holding — no `snap-r*` can answer "does this one boot the system".
- Rule: see iron rule 9. Branch names `feat/…`/`fix/…`/`test/…`/`chore/…`; merging back to `main` needs `BUILD OK` +
  on device, or `state = "build-only"` registered in `docs/engineering/MAIN-BASELINE.toml` with the visible debt accepted.
- Gate: `scripts/check-main-baseline.py` (`iron-9`).
## P-175 The kernel command line is swapped during boot — `pmd0` must be read before md0 is created

Symptom: `memdev.c:499` uses only the first 256 bytes of `PE_boot_args()` and still successfully creates
`Added memory device md0/rmd0 (02000000/0E000000) at FFFFFFF0083B5000 for 0000000002000000`; while the whole argument string printed by the same function after the Data mount (after `kern_exec.c:7818`) contains
**no `pmd0`, not even `pong_adsp=1`**.

These are two reads returning two different contents, not a parse error. Reproducible evidence:

```
usblog-20261113-112128   K60ARGS 0..8  → "-v native-ufs=1 … k60_autoreset=300 applog=1 "
usblog-20261113-113932   K60PAS no md boot argument (same position, all three PE_parse_boot_argn keys empty)
usblog-20261113-113932   Added memory device md0/rmd0 … at FFFFFFF0083B5000 for 0x2000000
```

Conclusion: what `PE_boot_args()` reads late in bsd is the **already replaced** command line (the NVRAM / launchd boot-args layer); the original string from md0 creation is no longer there.

Rule: any parsing that depends on the firmware command line (`pmd0`, `vmd0`, `initrd` and the like) must happen
**before device initialisation** (inside `bsd_init` before the md device is created, or earlier in `kernel_bootstrap`),
never after the Data mount. To verify, print it once at the earliest point and line it up with the `md0` line.

Troubleshooting order (so this is not walked again next time):
1. First confirm the target token is actually in the **original command line string** - `grep -a pmd0` on the boot log: the `Added memory device` line is the proof of existence; do not try to disprove it with a late print.
2. Then confirm the read position is right — the same function returning different contents at different times is easily taken for a parse bug without empirical proof (this cost three builds already).
3. The parser itself can be proven with host tests (`scripts/tests/test-k60-fat.c`, 8 cases); do not keep retrying on device.

## P-176 The built FD cannot find the payload: the stale UniXNUPkg in `{tree}/package` overrides the vendored copy

Symptom: any rebuilt `SILICIUM_UEFI.fd` stops after boot at the firmware's `UNIXNU: config: no boot entry found` /
`menu: default 0 'exit'`, while the old FD from 2026-11-11 works.

The root cause is not the Mu_Basecore pin and not MuPatches: in `board.toml [firmware].packages`,
`{tree}/package` comes before `{uefi}/Platforms/Xiaomi`, and the `UniXNUPkg` in the tree is a stale copy taken from
`E:\hackios\UniXNU\package`. EDK II resolves `UniXNUPkg/Driver/UniXNURamDiskDxe/UniXNURamDiskDxe.inf` following PACKAGES_PATH order, so the whole FD's UniXNUPkg drivers are compiled from the framework repository's old source — including
`UniXNURamDiskDxe`, the one responsible for publishing the initrd as a block device.
The stale copy lacks the initrd tracking/mapping checks of this repository's version, so the publish path differs and the firmware never gets the payload FAT.

How to prove it (do this next time instead of burning builds):
1. Take the old FD and any new FD, decompress the LZMA DXE volume (`lzma.decompress(body, format=lzma.FORMAT_ALONE)`,
   the section body starts at `section+24`), and walk the 98 files by FFS; same file count, same GUIDs,
   only 5 changed size.
2. Compare `75CA63AD-FBAE-4A06-92A0-F937C671251D` (UniXNURamDiskDxe) with `strings`:
   the new FD has `rounded to 0x%lx bytes`, no `selfread`, no `not inside mapped memory` —
   which does not match this repository's `Platforms/Xiaomi/UniXNUPkg/.../UniXNURamDiskDxe.c` but matches
   `E:\hackios\UniXNU\package\UniXNUPkg\...` exactly. That is hard proof of "what was compiled is not this source".
3. The `tree` printed by `--dry-run` is `out-baseline/.../tree`, and `{tree}/package/UniXNUPkg` is exactly that stale copy.

Fix: move `"{uefi}/Platforms/Xiaomi"` before `"{tree}/package"` (`board.toml [firmware].packages`),
sync to the device input, rebuild. Verification: the decompiled new FD shows `selfread`; after `fastboot boot` the kernel runs
(no longer the firmware menu), and the UniXNURamDiskDxe/UniXNU sizes in the old and new FD are identical.

Rule: when `PACKAGES_PATH` has two packages with the same name, the earlier one wins, with no warning at all;
every platform package vendored in this repository must come before `{tree}/package`.

### P-176 addendum: the panic after the FD is fixed is not the FD

Same kernel (the keep `kernel.macho`), same set of arguments, packaged and booted once with the old FD and once with the new one; the console statistics are identical:

- `usblog-20261113-oldfd2` (old FD): `lines=2185 KX=9 SB=7`
- `usblog-20261113-orderfd2` (new FD): `lines=2145 KX=8 SB=7`
- `usblog-20261113-orderfd-keepk` (new FD + keep kernel): `lines=2071 KX=8 SB=7`

All three panic with `initproc exited -- exit reason namespace 2 subcode 0xb description: none`.
Every image on 2026-11-13 (including the keep kernel and the `boot-noseed.img` without a Data seed) has the same panic with SB=7, while the keep image of 11-11 23:32 has SB=129 — so what remains blocking is in the payload's ADT/DTB or in userland, unrelated to the firmware volume.

Rule: to judge whether the FD is fixed, look only at "was the kernel loaded" (the kernel's own prints appearing on the console); do not use SpringBoard line counts as an FD metric; the two chains are recorded and verified separately.

### P-177 `--kernelcache` does not swap the kernel, `--kernel` does

Symptom: swapping the "known bootable kernel" into our own packaging as a control, three times in a row it still panicked, which wrongly produced "the kernel is innocent". The real reason is that `unixnu build payload` accepted `--kernelcache` and still packed the build directory's `kernel.macho` into the payload.

Basis: `unixnu build payload --help` has both `--kernelcache FILE` (a raw decompressed kernelcache, for prelink / trust cache) and `--kernel FILE` (the kernel actually packed into the payload).

Rule: whenever a kernel is swapped in as a control, `--kernel` must be used; after packaging, extract the kernel from the image and check it:

```
mdir  -i <img>@@<fat> ::/EFI/UniXNU/PAYLOADS/
mcopy -o -i <img>@@<fat> ::/EFI/UniXNU/PAYLOADS/kernel.macho /tmp/k.bin
sha256sum /tmp/k.bin
```

Only when size/hash match the source file did the swap succeed. Measured this time: the keep kernel 54,280,192 B (`ce97b50a…`), our built kernel 54,525,952 B — watching only `unixnu`'s exit code misses this difference.

### P-178 On-device comparison: swap one artefact at a time, and every artefact needs a verifiable swap entry point

This time the "11-11 keep image that reaches the system" was moved into the current build item by item, giving the matrix below (every row is a real boot):

| Swapped item | Entry point | Result |
|---|---|---|
| firmware volume FD `cf448571…` | `bootimg --fd FILE` | still `initproc exited` panic |
| ADT 15,304 B | `mcopy` over `EFI/UniXNU/PAYLOADS/kernel.macho.adt` inside the payload after packaging | still panic |
| DTB 1,866 B | `bootimg --dtb FILE` | still panic (image size back to 201,883,648) |
| `METAL/` directory | `mdeltree` it out of the keep image | still reaches the system, SB=133 |
| kernel `ce97b50a…` | `build payload --kernel FILE` (see P-177) | **reaches the system, SB=133** |

Rule: any conclusion that "some component is innocent" must carry evidence that the component really was swapped (size or sha256 or a unique string), otherwise record it as untested. Logs like `cs_invalid_page`, `shared_region`, `K60DYLD` also appear in images that reach the system, so they cannot be regression criteria; the only criterion is the SpringBoard line count after boot and whether it panics.

### P-179 `initproc exited … ns=2 code=0xb` is SIGSEGV, not AMFI refusing exec

The namespace table in `bsd/sys/reason.h`: `OS_REASON_SIGNAL = 2`, `OS_REASON_CODESIGNING = 3`,
`OS_REASON_EXEC = 9`, and `EXEC_EXIT_REASON_SECURITY_POLICY = 8`.

- `KX! 18 1 launchd exit=0 sig=11 r=1 ns=2 code=0xb` → signal namespace + signal 11 = SIGSEGV,
  that is launchd segfaulted itself, and the initproc death is what triggered the panic;
- AMFI refusing exec would be `ns=9 code=0x8`, or `ns=3` (codesigning), not `ns=2`.

It is still on the codesign chain: the same log has `CODE SIGNING: cs_invalid_page(0x10086b000): p=1[launchd] …
allowing (remove VALID) page`, and `KXPC 1 launchd pc=0x10086b158` lands exactly on that page.
But the keep kernel also reports one cs_invalid page on every boot (`0x1003a5000` / `0x1009a8000`, varying with the load address) and still reaches the system — so "one page had VALID removed" is not fatal by itself; what is fatal is the process later executing that page.

Rule: on seeing `ns=2`, decode it as a signal first (the `sig=` field); do not attribute it to AMFI straight away. To judge whether AMFI refused, look for `ns=9 code=8`.

### P-180 The embedded blob in a patch is code: the line count can stay the same while a whole binary is swapped

`patches/xnu/0340-k60-uilib-deploy.patch` grew from 629,034 B to 1,052,856 B after 11-11; the deployment hook in
`kern_exec.c` is byte-identical, and the only thing that changed is the `libpong-ui.dylib` embedded in `bsd/dev/k60_uilib.c`. Bisecting the whole directory proves it: the old version reaches the system (SpringBoard 133 lines), the new one gives `initproc exited … ns=2 code=0xb` at the launchd stage (7 lines); **reverting only 0340** restores 129 lines.

Rules:

- for patches with C arrays like `0340/0391/0401`, **diff size, hunk count and `check-patch-apply` all passing is not verification**;
  the only criterion is a boot image that reaches the system;
- any change to these three patches must update `docs/engineering/MAIN-BASELINE.toml`'s `[entry.blob_sha256]` before merging back to `main`;
  the gate `scripts/check-blob-patches.py` compares them;
- when you suspect such a patch, do not read hunk by hunk: `git show <boot-proven>:<patch> > current file` to revert the whole file,
  and one boot settles it (this time it saved trying 27 files one by one).

### P-181 When a build fails the old kernel.macho is still there, and a one-line grep treats it as the new artefact

`./unixnu build kernel … | grep '== kernel:' || exit 1` in `mk_cut.sh` is a fake gate: the bootstrap stage prints `== kernel: bootstrap pass for the compile records` anyway, so even when the later link fails and `kernel.macho` is still the old file from the previous build, the script goes on to package and "successfully" produces an image.
Cost: the five consecutive "bisect results" on the afternoon of 11-13 were all actually the same 11-11 allold kernel, producing the wrong conclusion that "0340 is the culprit".

The real root cause was masked at the same time: `bsd/dev/pong_adsp_*.c` was not listed in `bsd/conf/files`, and the link reported
`Undefined symbols for architecture arm64: "_k60_adsp_note_window" … "_k60_adsp_probe_from_handoff"`.

The rules now:

- `scripts/build-xnu-4k-baseline.sh` calls `scripts/append-conffiles.py` before the final `make`, adding the in-tree driver to the generated `conf/files`, and exits on failure;
- every build script must check `unixnu`'s **exit code**, and compare the mtime of `kernel.macho` against "a marker file touched before the build started" (`test "$M/kernel/kernel.macho" -nt "$MARK"`), not merely whether the file exists;
- to decide whether the new kernel made it into the image, use `strings -a kernel.macho | grep -c '<string added this round>'`, then `mdir`/`mcopy` the kernel out of boot.img and compare sha256 (the recipe from P-177).

### P-182 The kernel writes persistent files to the Data volume before launchd, so going back to the old kernel is still poisoned by the new files

Before exec'ing `/private/var/pong/init`, `load_init_program_at_path()` in `kern_exec.c` takes the embedded blobs out of the kernel image and writes them to the Data volume:

- `/private/var/pong/init` (the PID 1 helper, `k60_init_blob.h`)
- `/private/var/pong/boot-jobs.pack` (`k60_bootjobs_blob.h`)
- `/private/var/pong/var.pack` (`k60_varpack_blob.h`)
- `/private/var/pong/xpc/launchd.plist` (`k60_launchd_cache.h`, 0394)

These writes happen before userland comes up, and they **overwrite**. The measured cost on 2026-11-13:

1. The 11-11 `keep` image kept reaching SpringBoard (SB=133).
2. The 11-12/13 new kernels wrote 0401's new helper (52,320 B, larger than 11-11's 35,160 B) into Data.
3. Afterwards **any** image boot gave `initproc exited -- exit reason namespace 2 subcode 0xb`, SB=7,
   including images that reverted 0340/0394/0401/0398 one at a time — because the poison was on the disk, not in the kernel.
4. Booting the 11-11 allold image once more (the old kernel rewrites init back to the 35,160 B old version) → fine again.
5. Immediately after, booting the previously failing `boot-cut0401.img` (which contains no 0401 write) → **SB=133, fine**.
6. Current kernel + `--kernel-arg k60_init_blob=0` (no init rewrite) → **SB=129, fine**.

So when deciding "did patch X cause a boot regression", you must first normalise these four files to a known-good version,
otherwise every single-variable revert conclusion is invalid (one more layer on top of the P-177/P-178 stand-in trap).

The rules now:

- record the sha256 of these four files before and after every on-device run; boot results taken in two different states are not comparable;
- normalisation: boot the 11-11 `keep-a6165f2404568c1d.img` once (old kernel rewrites the old init),
  or have this round's image explicitly set `k60_init_blob=0` and confirm the helper on disk is already the good one;
- changing these blobs (0401/0394) must state "will rewrite persistent files on the Data side" in the commit message,
  with the length and sha256 of the old and new blob;
- a new helper must first be verified over two boots on an **existing Data state**, not only on empty Data.

**Fix (2026-11-13)**: `0401` stays as it is; a new `patches/xnu/0616-k60-init-legacy-helper.patch`
replaces the installer call after 0401 with the legacy helper version that writes only `/private/var/pong/init`
(`k60_init_legacy.h`, 34,904 B; measured log `K60INIT legacy bytes=34904 resid=0 error=0`),
the gate stays `k60_init_blob`; `boot-jobs.pack` / `var.pack` stay in the **preserved state** and are no longer rewritten.
Reverting by dropping the old patch wholesale is not viable: `git show 29827f5:patches/xnu/0391-k60-embedded-init.patch`
applied over 0401 finds that `kern_exec.c`'s context has been changed by 0394/0398, `patch does not apply`.

Evidence: `E:\k60-work\evidence\usblog-20261113-allold2` (SB=129),
`usblog-20261113-cut0401b` (SB=133), `usblog-20261113-noinitblob` (SB=129),
control `usblog-20261113-rev0340` (SB=7).

### P-183 Network probe failure ≠ not pushed: the gate reads "cannot verify" as "not done"

`is_pushed()` in `check-snapshot-tag.py` looks only at the exit code of `git ls-remote`. During the two hours the proxy was down
(`schannel: failed to receive handshake`, `gnutls_handshake() failed`, `curl github.com` = 000,
`getent hosts github.com` = `198.18.2.110`) it reported every tag as "not pushed to the remote", while
`boot-proven-20261113` had in fact been pushed hours earlier — one network failure is enough for the gate to reach the opposite conclusion.

Fix: three states. `returncode != 0` returns `None` (cannot verify); at that point read the
`tag_commit` / `tag_pushed` record in `docs/engineering/MAIN-BASELINE.toml`: if the commit matches the current tag
it is reused, otherwise it counts as a failure; on a successful network call the record is backfilled (`note_push()`).

Lesson: every check that hinges on "do we need the network" must have a third return value. A two-state check is not checking when the network is down,
it is guessing.

### P-184 There is only one shared checkout: the Lead and a subagent editing the same tree eat each other's uncommitted changes

2026-11-14 02:03, to get my own strict build through the eight-step gate, I ran
`git checkout -- <8 documents>` in `E:/hackios/UniXNU-mondrian` (then in use by the touch agent to write docs),
wiping all of its uncommitted changes: the honest correction in `EIGHT-STEPS.toml` that set touch ④⑤⑥ from `done=true` to `false`, and the edits to `GROUND-TRUTH.md`,
`TOUCH-STATEMACHINE.md`, `03-reverse-and-device-data.md`, `PITFALLS.md`, `INDEX.md`,
`README.md`, `README_EN.md` — all lost; only the untracked
`docs/research/touch/13-STAGE-ONE-ROOT-CAUSE-MATRIX.md` survived (saved separately to
`E:/k60-work/scratch/SALVAGE-touch-agent-edits-20261114.md`).

The root cause is not `git checkout`, it is **two people sharing one checkout tree**. The fix:

- the Lead uses its own worktree: `git worktree add E:/hackios/k60-lead <branch>`,
  doing its own builds and commits in `E:/hackios/k60-lead`; `E:/hackios/UniXNU-mondrian`
  belongs to the touch agent.
- never run `git checkout --` / `git restore` on uncommitted files that belong to **someone else's branch**.
  To make a gate pass, narrow the gate's scope (see the next entry), do not touch another person's working tree.
- a real defect found along the way: the eight-step gate's build mode validated **every** hardware item with `status = "active"`,
  so nobody could build while the touch research was unfinished, and touch could not build while other hardware was unfinished. The gate's semantics should be
  "the hardware items touched by this change" must pass ①②③④⑤⑥, so build mode narrows by changed paths,
  while flash mode keeps whole-machine validation.

Evidence: `git branch -f feat/touch-power 3330e1c` restored the branch; `git worktree list` shows
`E:/hackios/k60-lead 84523c0 [feat/pmic-rail]`.

### P-185 A fresh checkout is not missing code, it is missing the toolchain and fakeroot that exist only in the build copy

Cut a `git worktree` off `main` and the code is all there, yet the build dies in step three with an inexplicable 127 / missing header:

- `scripts/build-firehose.sh:24` calls `xcodebuild`. On Linux the Darwin tools `xcodebuild` / `xcrun` / `clang` are stood in for by
  the 13 shims in `scripts/linux/`. Those shims **are tracked in the framework repository `E:/hackios/UniXNU`**,
  but the device repository does not have them; the build copy `/opt/k60/trees/k60build/scripts/linux/` was synced from the framework.
  A new worktree with only the device repository therefore has no shims at all → `xcodebuild: command not found` → `bash failed (127)`.
- On the first build in that same new tree, `tree/.cache/fakeroot/` is empty. `libfirehose_kernel.a` (40,480 B),
  the 42 headers under `usr/include/` (including `Availability.h`) and `usr/local/include/kernel/os/` are all missing,
  so `build-pong-platform-macos.py` fails compiling `ArmDTPlatform.cpp` with
  `mach/arm/vm_types.h:76:10: fatal error: 'Availability.h' file not found`.

Neither is a code problem, **it is "a worktree ≠ a build environment"**. The diagnostic order is fixed:

```bash
# 1) are the shims there
ls "$BUILD/scripts/linux" | wc -l        # expect 13
# 2) is fakeroot complete (use a known-good out directory as the baseline)
diff -rq "$GOOD_OUT/.../tree/.cache/fakeroot" "$NEW_OUT/.../tree/.cache/fakeroot"
```

Fix: sync the shims from the framework (`sync-device-input.py`'s `FRAMEWORK_PAIRS` covers `scripts/linux`);
fill fakeroot in with `cp -a` from a known-good output tree (it is a pure build artefact and can be copied directly).

Lesson: `git worktree` gives you **code isolation**, not **environment isolation**. Before the first build in a new tree,
run an "environment completeness check", otherwise a missing environment is misdiagnosed as a code bug and a whole build round is wasted.

## P-186 — Editing from Windows flips the line endings of the whole file

**Symptom**: a 37-line change to `AGENTS.md`, and `git show --stat` reports `366 insertions(+), 366 deletions(-)`.
`grep -c $'\r'` is 0 on the old version and 366 on the new one — the whole file went from LF to CRLF.

**Cause**: the file was written on the Windows side (editor/PowerShell redirection default to CRLF), while in the repository this file is LF.
git compares bytes, so every line "changed". The real 37-line change is buried in 700-odd lines of noise, and every future merge
will conflict on the whole file.

**Disposition**: `scripts/check-line-endings.py` reports only **flips** (HEAD is pure LF, the working tree shows CRLF),
and leaves alone the 73 files that were already CRLF historically — those need one separate commit to unify, and must not be mixed into a feature commit.
`.gitattributes` gained `* text=auto eol=lf` and the common text extensions, so it is unified at checkout time.

**Lesson**: write files with the `write` tool (UTF-8 LF), not with PowerShell redirection;
before committing, check that `git diff --stat`'s added/removed line counts match the size of the change — if they do not, it is a line-ending or encoding flip.

### P-190 — The archive was added to `KERNEL_EXTRA_ARCHIVES` but never reached the kernel: that block lives in a dead branch

**Symptom**: `configs/mondrian_defconfig` turns on `CONFIG_XNU_K60_PHYSICAL_BATTERY=y`,
both wiring points in `scripts/build-xnu-4k-baseline.sh` were written (`PERSONALITY_CFLAGS` got
`-DXNU_K60_PHYSICAL_BATTERY=1`, `KERNEL_EXTRA_ARCHIVES` got
`-Wl,-force_load,$BATTERY_ARCHIVE`), the build succeeded and `verify-boot-image.py` passed,
yet in the kernel `strings kernel.macho | grep -c K60Battery` = **0** and `nm | grep k60_physical_battery_start` = **0**.
The archive itself is fine (`llvm-ar t` lists seven members, `strings` has 114 occurrences of `K60Battery`).

**Cause**: the **whole block** of `KERNEL_EXTRA_ARCHIVES` (lines 898–1092) is nested inside
`if [ "${XNU_SOURCE_CORECRYPTO14:-0}" = 1 ]; then … fi`. And the generated
`.config` has `CONFIG_XNU_SOURCE_CORECRYPTO14=y` on line 2 and
`=n` on line 88 — `parse_config()` in `unixnu/scripts/unixnu/config.py:82-107` lets **the later assignment override the earlier one**
(that is the normal semantics of concatenating defconfig fragments), so `xnu_env()` hands the build script `XNU_SOURCE_CORECRYPTO14=0`
and the whole block is skipped. **The link list that actually takes effect on this board is `PLATFORM_ARCHIVES`** (from line 1150,
condition `[ -z "${XNU_BOOTSTRAP:-}" ] && [ "$ARM_DT_PLATFORM" = 1 ] && [ "${XNU_SOURCE_CORECRYPTO14:-0}" != 1 ]`),
which is where `ArmDTPlatform`, `ArmCpu`, `NativeUfs`, `NativeRamBlock` are added.
So "add the archive to `KERNEL_EXTRA_ARCHIVES`" is a **no-op** on this board.

**Fix**: add the battery archive to `PLATFORM_ARCHIVES` (and update `PLATFORM_DEPENDENCIES` at the same time),
keeping the `KERNEL_EXTRA_ARCHIVES` copy for a future configuration that re-enables source-corecrypto.

**How to avoid it next time**:
1. After adding any `-Wl,-force_load` archive, **you must verify the symbol actually reached the kernel**:
   `llvm-nm-18 $M/kernel/kernel.macho | grep -c <symbol>`, not just that `test -f` passes and the build succeeded.
2. To judge "will this line I added actually execute" you read the **enclosing condition**, not just the neighbouring lines — use
   `awk` to print the `if`/`fi` skeleton of the whole block (`awk 'NR>=898 && NR<=1100 && (/^if /||/^  if /||/^fi$/)'`).
3. When the same `CONFIG_` name appears twice in one `.config`, **the last one wins**; `check-config-consistency.py`
   prints such duplicates as a note (`duplicate CONFIG_XNU_SOURCE_CORECRYPTO14: line 2 has y; line 88 has n`),
   and seeing such a note should make you think "code in the build script branching on this symbol may never execute at all".

**The second shape of the same bug (2026-11-14, caught by the gate's own self-test)**: the first version of `scripts/check-kernel-archives.py`
wrote the two keys as `ARM_DT_PLATFORM` / `XNU_ARMCPU`, while the generated keys are
`CONFIG_XNU_ARM_DT_PLATFORM` / `CONFIG_XNU_ARMCPU`. `enabled()` returns False for any name it does not recognise,
so the gate **silently skipped** two of the four archives it was supposed to guard, while printing `✅ … 2 enabled archive(s)`.
A gate that skips names it does not recognise is worse than no gate. Fix: every key is copied from a real `.config` line;
on a skip it prints `skip: CONFIG_… is not enabled`; and a new
`scripts/tests/test-check-kernel-archives.py` (5 cases) whose first case asserts that
every key in `EXPECTED` really exists in `configs/mondrian_defconfig`.

## P-191 — A table-lookup function returned success when it found nothing

**Symptom**: `k60_rpmh_level_index(&res, 9999, &index)` returns `K60RpmhOk` and `index` is the last rung of the table.
The caller believed "1800 mV is selected" when what was actually selected is the highest rung this table can express. The host test even wrote that behaviour down as an assertion
(`CHECK(... 9999 ... == K60RpmhOk && index == 3)`), so the test endorsed the bug.

**Root cause**: when the loop misses it takes the fallback branch, which sets `*index` to the last rung to "give a sensible value"
and reused the success return code along the way.

**Why it is dangerous**: this is a **voting-class** interface. Once an RPMh voltage/mode request is issued it cannot be withdrawn from the software side,
a wrong rung persists in the shape of "success", and it is invisible in the log — you only notice by comparing the observer's
`valid`/`enable`.

**Fix** (`drivers/PongPower/K60PmicRail.c`): the fallback still supplies the last rung (the caller may want to print it),
but returns `K60RpmhNoLevel`; the host test is changed in step to `CHECK(... 9999 ... == K60RpmhNoLevel); CHECK(index == 3);`
plus a hit case `1400 -> Ok, index 0`.

**Prevention**:
1. For every table-lookup function returning `Ok`/`Success`, ask line by line "what do I return when the input is outside the table".
2. Host tests must not test only the normal path — boundary inputs (0, over the maximum, empty table) each need a case.
3. Seeing the combination `*out = count - 1; return OK;` is this pitfall.

**Found by**: the touch line agent's review (`docs/research/touch/13-STAGE-ONE-ROOT-CAUSE-MATRIX.md`, 2026-11-14).

## P-192 — The gate used a "whole-machine scope" as "everybody waits together"

**Symptom**: on 2026-11-14 the agents on the wifi and bt lines could not build through `build-strict.sh`. The reason: the eight-step gate's
**flash mode** requires every hardware item with `status = "active"` to be green on all eight steps, while the touch line was being heavily reworked by an external agent
(④⑤⑥ set to `done = false`). Both lines therefore bypassed the builder with a manual `unixnu build` + `bootimg`, and the result:

- the `bt-s1-20261114b` command line was **610 bytes**, over DarwinBoot's 607-byte limit (`BootArgs.h:8`'s
  `DARWIN_BOOT_LINE_LENGTH 608`, `DarwinBoot.c:681` tests `Index >= sizeof(CommandLine) - 1`),
  so the firmware returned `EFI_BAD_BUFFER_SIZE` outright and the kernel was never invoked;
- `wifi-20261115a` replaced `debug=0x140` with `debug=1` (`DB_HALT` in `debug.h:513`), so any debug trap halts,
  and also replaced `epoch` with 1 — presenting as "boot is stuck somewhere".

Both were **0-byte logs**, looking like a kernel fault, when in fact nobody in the packaging step looked at the command line.

**Root cause**: the gate itself is not wrong (it really should block unverified hardware items), what is wrong is that it **can only declare whole-machine**:
`K60_EIGHT_STEP_ITEMS` picks only among `status = "active"` items, so "I want to build the buttons/wifi/bt line"
cannot be expressed at all, and any build not on the touch line is held up by the touch line.

**Fix** (`scripts/eight-step-gate.py`):
- `declared_items(hw, all_items)` now takes names from **all** hardware items, so parked/planned can be declared too;
- declared items are still checked under the same evidence rules (`done=true`, rationale ≥30 characters, must have `file:line`/URL/`usblog-…`/`0x…`/`P-xx`/`★xx`),
  so this **narrows the scope** rather than loosening the requirements;
- no declaration = whole-machine scope, behaviour identical to before, word for word;
- `--flash` mode never looks at declarations, flashing is still a whole-machine gate;
- the printout carries the state: `declared scope: buttons[parked]`, so whoever narrowed the scope is visible in the log.

**Supporting work**: a new `scripts/check-image-args.py`, wired into `build-strict.sh` — even if someone packages by hand,
the same command can audit over-limit lines, `debug=1`, `epoch=1`, replaced board values and undeclared appended arguments.

**Lessons**:
1. A gate's "scope" and its "strength" are two different things. Blocking uninvolved people is not strictness, it is forcing them to bypass.
2. For any gate that can "only be whole-machine", ask "how does someone else build while working on different hardware".
3. Artefacts that bypassed a gate must be independently auditable — the audit tool has to be usable on its own, not only hooked into the builder.

### P-193 — The gate hardcoded the repository root and searched references with two fixed prefixes: it validated another worktree's files, and permanently rejected legitimate reference repositories

**Symptom**: the refmine line needed `QcaBluetooth` and `UniXNU-liuqin` written into
`docs/research/SOURCES.toml`'s `required`, and `scripts/research-gate.py` always reported
`file does not exist`, so the conclusion could only stay in prose and never got into the gate. At the same time, every worktree running this gate
validated the files of the tree at `/mnt/e/hackios/UniXNU-mondrian`, not its own.

**Root cause** (two places, one shape):

```python
REPO = '/mnt/e/hackios/UniXNU-mondrian'          # 字面路径
full = os.path.join(REPO, path)
alt = os.path.join('/mnt/e/k60-work', path)       # 只有两个前缀
exists = os.path.exists(full) or os.path.exists(alt)
```

1. `REPO` is a hardcoded shared checkout. Of eleven worktrees only one is at that path, all the others
   validate someone else's files — a green gate does not mean your own tree is fine.
2. Reference sources were recognised only as "this repository's checkout" and `/mnt/e/k60-work`. Repositories cloned directly under `/mnt/e/hackios`
   (`QcaBluetooth`, `UniXNU-liuqin`) never resolved, so **legitimate reference sources were rejected by the gate**
   instead of being recorded.

**Fix**:

```python
REPO = os.environ.get('K60_REPO') or str(Path(__file__).resolve().parents[1])
REFERENCE_PREFIXES = (str(REPO), '/mnt/e/k60-work', '/mnt/e/hackios')
...
tried = [os.path.join(prefix, path) for prefix in REFERENCE_PREFIXES]
if not any(os.path.exists(candidate) for candidate in tried):
    problems.append('%s 文件不存在: %s（已试 %d 个前缀）' % (label, path, len(tried)))
```

The failure message carries "how many prefixes were tried", so the next time a reference repository is added you can see at a glance whether a prefix is missing or the file is really gone.

**How to avoid it next time**:

1. Any literal checkout path like `/mnt/e/hackios/…` inside a gate script is a bug.
   `scripts/check-repo-paths.py` (the hygiene line) now reports it as ERROR.
2. Resolve reference sources as a **tuple of prefixes**, not as two `os.path.exists` calls joined by `or`. Adding a reference repository
   only changes the tuple, not the lookup logic.
3. A gate's failure message must say **what was tried**. An error that only says "file does not exist" makes people think
   the file is the problem rather than the gate — this is the same lesson as P-190's "silently skip what you cannot recognise",
   in two shapes.
4. Every gate needs a test case that runs from **another worktree**, otherwise the literal-path bug never surfaces.
   See `scripts/tests/test-research-gate-prefixes.py` (5 cases).

## P-194 — The patch-set fingerprint measured a scratch copy, not the series actually built

- **Symptom**: section S of `porting-gate.py` reports `series fingerprint 23131cd07c1cb63e (227 entries)`, while this build's
  `build-manifest.json` says `series 223`. Both numbers claim to be the "patch-set fingerprint" yet describe different series.
- **Root cause**: `board.toml`'s `patch_series = ["device:patches/xnu/series"]` is the order list the build really applies
  (`scripts/unixnu/patches.py:12-28` applies it entry by entry and errors outright on duplicates). But
  `porting-gate.py:35` and `record-boot.py:24` both hardcode `WORK + '/scratch/SERIES-FINAL.txt'`.
  That scratch copy was the source of truth in P-90's day and has drifted since to 227 entries: four extra bluetooth patches
  (`0507`–`0510`), still containing the replaced `0610-k60-metal-seeds.patch`.
- **Consequence**: section S treats "the patch set changed" as requiring explicit confirmation, yet it compares two copies, neither of which takes part in the build;
  the fingerprint `record-boot.py` writes into the ledger is wrong in the same way, so the "patch set of the last successful boot" baseline keeps pointing at
  a series that does not exist. This is the exact inverse of P-90: back then editing the repository series had no effect; today it does take effect,
  but the gate still looks at scratch.
- **Fix**: both scripts now use `SERIES = <repo>/patches/xnu/series`, falling back to
  `scratch/SERIES-FINAL.txt` only when the file does not exist (for old trees without it). Afterwards `record-boot.py --dry-run` reports
  `series 932e0cb51d39fb60 (223 patches)`, matching the manifest's 223.
- **Verification**: the entry count from `python3 scripts/record-boot.py --image … --log … --dry-run` must equal
  `build-manifest.json`'s `series.count`; if not, the two "sources of truth" have diverged again.
- **Lessons**:
  1. Any "fingerprint/baseline" must come from **the file the build actually reads**, not from a copy of the same name. The criterion is simple:
     compare it once against the same field in the manifest; if they disagree it is a bug.
  2. When one file's path is hardcoded in two scripts, changing the source of truth only changes half of it. A source-of-truth change must change every reader at once,
     and leave a fallback that degrades when the file is absent.
  3. P-90's conclusion ("editing the repository series has no effect") has been reversed since format 2. Pitfalls expire too:
     before citing an old pitfall as evidence, confirm the world it describes still exists.

## P-195 — `vnode_open(path, O_CREAT, …)` creates a file, not a directory

**Symptom.** The Adreno Metal plugin never reached the Data volume. Every boot
printed, and nothing else:

```
K60METAL open /private/var/ngpu/addons/PongAdrenoMetal.bundle/Info.plist error=20
K60METAL deploy files=0/6 error=20
```

**Cause.** `patches/xnu/0610-k60-metal-plugin-deploy.patch` had

```c
error = vnode_open(path, O_CREAT, 0755, 0, &vp, ctx);
vnode_close(vp, 0, ctx);
```

in `k60_metal_mkdir()`. `vnode_open` with `O_CREAT` creates a **regular file**;
there is no "directory" flag to pass it. So the first call created
`/private/var/ngpu/addons/PongAdrenoMetal.bundle` as a plain file, and every
later `vnode_open("…/PongAdrenoMetal.bundle/Info.plist")` failed with
`ENOTDIR` (20). The bundle — including `PongMetalBridge.dylib` (33 MB) and
`libvulkan_freedreno.dylib` (18 MB) — therefore never landed, `zzy-native-gpu-addon-mount`
had no source directory to union, and Metal stayed on the software path
(`Pong UI: optional camera-filter GPU prewarm skipped (software-only platform)`).

**Fix.** Call the `mkdir` syscall, which the tree already does in four places
(`0215`, `0222`, `0234`, and `0398`'s `k60_mkdir_paths` loop):

```c
copyout(path, name, strlen(path) + 1);       /* name = scratch + 0x400 */
args.path = name;
args.mode = 0755;
error = mkdir(p, &args, &ret);
if (error == EEXIST) return 0;
```

`struct mkdir_args` comes from `<sys/sysproto.h>`; `copyout` from
`<libkern/copyio.h>`, which `<sys/systm.h>` already pulls in.

**Why it went unnoticed.** `0610`'s own log line reports the failure
(`error=20`, `files=0/6`), but no gate compared "files written" against
"entries in the blob", and the deploy prints a summary rather than a verdict.
The GPU bring-up line right before it (`PONG ADRENO: startup COMPLETE;
hardware armed result=0`) reads like success, so the deploy's zero looked like
a cosmetic warning.

**Lessons.**
1. A "mkdir" helper that only calls `vnode_lookup` then `vnode_open(O_CREAT)`
   is wrong by construction. Search the tree for an existing `mkdir(p, …)`
   call before inventing one.
2. `scratch + 0x400` is a shared page: check who else claims the offset
   (`+0x100..+0x300` mount args, `+0x400` 0398 mkdir paths, `+0x600/+0x700`
   0340 uilib, `+0x800/+0x900` 0394 launchd cache) before reusing it.
3. A deploy function must report a verdict, not a summary: `files=0/N` should
   be an error the caller prints as failure.

**Check.** `python3 scripts/check-blob-patches.py` (P-180) plus the boot-time
criterion "no `K60METAL … error=20` and `deploy files=6/6`".

## P-196 — In a generated container the length constant must include the alignment padding between bodies

**Symptom.** On the device the Metal plugin deploy was always `deploy files=5/6 error=22`,
log `K60METAL entry 5 body out of range`. The first 5 files were written, the last one
(the 2-byte `PongAdrenoMetal.publish`) was judged out of range.

**Root cause.** In `emit_source()` of `scripts/gen-k60-metal-blob.py`:

```python
total = len(head) + sum(size for _, size, _ in files)
```

It adds only the raw size of each body, **it does not count the padding `.p2align 3` inserts between bodies**.
Measured (decoding the table in `/tmp/k60metal-probe.s`): entry 4 ends at 51278762, entry 5 starts at
51278768 (6 bytes of alignment padding), while `k60_metal_blob_len` reports 51278763 —
5 bytes smaller than the start of entry 5, so the kernel's
`field.offset > len || field.size > len - field.offset` has to reject it.
`cursor` in the loop already is the true byte count of "header + every body aligned upward",
so the fix is to change `total` to `cursor`.

**Why no gate caught it.** This table is **generated in assembly**: no compiler, no linker,
and not one C-side type check ever looked at it. `check-kernel-archives.py` only checks whether the symbol is
in the kernel (`_k60_metal_blob` is), `verify-boot-image.py` only compares the sha256 of each component in the image against the manifest — both answer only
"did the bytes arrive", not "is this table self-consistent". Any format where **the generator writes its own header** (containers, indices, directory tables)
needs a self-consistency check that only reads that table.

**Fix.**
1. `scripts/gen-k60-metal-blob.py`: `total = cursor`.
2. New gate `scripts/check-metal-blob.py`: decode the `.byte` header, assert magic,
   entry count matches the `.incbin` line count, every `[offset, offset+size)` falls inside
   `k60_metal_blob_len`, offsets are 8-byte aligned, do not overlap, names are non-empty and <200 bytes.
3. `scripts/build-strict.sh` calls it after `check-kernel-archives.py`.
4. `scripts/tests/test-check-metal-blob.py`, six cases, one of which **must** be
   "after changing the length back to 51278763 the gate reports P-196", otherwise this gate does not guard what it is supposed to.

**Lessons.**
- The "length" in a generator and "the bytes actually written" must be computed from the same cursor; you cannot compute them twice with two
  different algorithms.
- Table self-consistency is a third class of check, **independent of** "is the symbol there" and "is the hash right";
  do not expect the first two to cover it.
- A 2-byte file exposed the bug in a 33 MB deploy chain: the range check fires on the last entry,
  so do not assume small files cannot go wrong.

**Check.** `python3 scripts/check-metal-blob.py` and
`python3 scripts/tests/test-check-metal-blob.py`; the on-device criterion is
`K60METAL deploy files=6/6`.

## P-197 — A capability the firmware does not implement cannot be written up as "already done"

**Symptom.** The bluetooth S4 plan (have the firmware copy `<kernel>.gpuaddon` into the boot window and publish the run address at
`/chosen/memory-map/GpuAddon`) failed two flashes in a row, with a single log line
`[bluetooth] addon: unusable range 0 0`
(`usblog-20261115-012913/console.log:192`). The container really was in the payload:
`mdir -i boot.img@@557056 -/ ::/EFI/UniXNU/PAYLOADS` lists
`kernel.macho.gpuaddon 1027584`, and the ADT really does carry the `GpuAddon` property name. So three rounds of
investigation went into parameters, container format and the kernel reader.

**Root cause.** The sentence "DarwinBoot already copies … into the boot window (DarwinBoot.c:588-651)"
was **an assumption, not a measurement**. Measured:

```
$ cd /mnt/e/hackios/uefi-mondrian && git grep -ci 'addon' HEAD -- .
（零命中）
```

`Platforms/Xiaomi/DarwinBootPkg/Driver/DarwinBoot.c`'s ADT scanner handles only eight
properties: `name`, `RAMDisk`, `PackedRAMDisk`, `darwinboot-memory-ranges`,
`pong-allocatable-ram`, `pong-audio-dma`, `TrustCache`,
`darwinboot-memory-size` — no `GpuAddon`. Lines 588-651 are
the start of `WritePongRam`/`Boot` and have nothing to do with addon. And
`scripts/unixnu/devicetree.py:339`'s
`mappings += [('GpuAddon', bytes(16))] if addon else []`
writes only a 16-byte placeholder, expecting the firmware to fill in paddr/length. The firmware does not recognise it → all zeros → the kernel's
`range->paddr == 0` → `k60_addon_note("unusable range", 0, 0)`.

**Why no gate caught it.** In the framework-generated ADT the property name is correct, `verify-boot-image.py`
only compares file hashes, and `mdir` only proves the container is in the payload. All three are true, yet together they are not enough for the
kernel to see it — **between "the file is in the image" and "the kernel can read it" sits the firmware step**, and no
gate checks the firmware side.

**Fix.** ① change the docstring of `scripts/make-bt-firmware-addon.py` to the measured conclusion
(the packer is still correct, but state plainly "the current firmware does not publish this range"); ② to make S4 really
usable, add a `GpuAddon` branch to the ADT scanner in `uefi-mondrian`'s `DarwinBoot.c`
(read `<kernel>.gpuaddon` from the payload FAT → allocate pages → fill in the 16 bytes), or switch to
a different carrier (Data seed / kernel-embedded blob, the latter has the `k60_metal_blob.s` precedent).

**Lessons.**
- A cross-repository capability must be verified across repositories: before writing "the firmware already does X", `git grep` X once
  in **the firmware repository**. The same word appearing in three repositories does not mean all three implement it.
- Three true facts do not add up to one true conclusion: the property name is right, the container is there, the hash matches — none of which implies "the kernel can read it".
  The step in between (the firmware filling it in) needs its own observable evidence.
- A zero value is the most expensive failure shape: `unusable range 0 0` only says "the value is zero", not "who failed to fill it".
  On seeing a zero, first ask "who is supposed to fill this step", then ask "does that code exist".
- One wrong comment is contagious: the patch comments in `patches/bt/0004` and `patches/xnu/0510` copied
  the same assumption, and the two patches together turned the false premise into a "design basis".

**Check.** `git -C /mnt/e/hackios/uefi-mondrian grep -ci 'addon' HEAD -- .`
being 0 voids any statement that "the firmware publishes GpuAddon";
the on-device criterion therefore becomes the kernel-embedded blob line: `[bluetooth] addon: linked blob bytes=1027584 records=106`
(the old channel's `addon: loaded bytes records …` will never appear; `addon: unusable range 0 0` is the measured symptom of P-197).
The carrier implementation is `scripts/gen-k60-bt-blob.py` + `patches/xnu/0510`'s `k60_bt_addon_load_blob()`.

## P-200 — `boot.json`'s `kernel_sha256` measures the firmware volume, not the kernel

**Symptom.** On 2026-11-15 two agents compared images using `boot.json` and reached contradictory conclusions:
one said "the kernels of mhi3/mhi4 are byte-identical, so the only variable is the memory window", the other said "the kernels
differ". Neither measured the wrong file; **the field name is wrong**.

**Measured.** For 11 completely different images under `E:\k60-work\artifacts\`, `boot.json`'s
`kernel_sha256` is **all** `83b52b566b9cd0e0a2f13854f7da4c67…`:

```
wifi-20261116a2        83b52b56…   manifest.payload_kernel e273b649…
wifi-20261116mhi4      83b52b56…   manifest.payload_kernel e24a58f1…
wifi-20261116mhi5      83b52b56…   manifest.payload_kernel ac7a152f…
springboard-20261115a  83b52b56…   manifest.payload_kernel 50a81744…
thermal-20261115a      83b52b56…   manifest.payload_kernel 7bb198a0…
brightness-9           83b52b56…   manifest.payload_kernel 1c5ca5d4…
gpu-20261114t          83b52b56…   manifest.payload_kernel cafdb5df…
touch-20261114a        83b52b56…   manifest.payload_kernel e849ae6b…
```

**Root cause.** The framework's `scripts/unixnu/bootimg.py:161` says

```python
return {'kernel_sha256': hashlib.sha256(kernel).hexdigest(), ...}
```

where `kernel` is **the boot image's kernel slot** = `gzip(112-byte shim + 3,145,728-byte firmware volume) + 4,024-byte DTB`.
The firmware volume is always `cf448571…` and the shim is deterministic, so this hash is identical for every image using the same firmware volume.
**The real XNU kernel is in the ramdisk FAT at `EFI/UniXNU/Payloads/kernel.macho`**,
and its hash is `build-manifest.json`'s `components.payload_kernel`.

**Why no gate caught it.** The field name `kernel_sha256` looks like the kernel; `verify-boot-image.py`
compares the correct key in the manifest, so the gate stayed green. Both sides are right, but humans read the field name.

**Fix.** ① always compare kernel identity using `build-manifest.json`'s `components.payload_kernel`
(or `mcopy` the `kernel.macho` out of the payload and `sha256sum` it directly), **not `boot.json`'s
`kernel_sha256`**; ② the field in `boot.json` should be understood as "firmware slot hash", which is useful
(it proves two images use the same FD) but unrelated to the kernel; ③ when kernel identity is needed, add a
`payload_kernel_sha256` field instead of expecting the reader to sort it out.

**Lessons.**
- A field name is an assertion. Calling it `kernel_sha256` while measuring the firmware volume misleads every reader
  and no gate will ever report it.
- When two agents reach contradictory conclusions, first check "which file each of them actually measured", then argue about who is right —
  this time neither was wrong, the naming was.
- "This value is the same for all images" is itself a suspicious signal: the images plainly differ, so how could the hash be the same.
  The first reaction to a hash identical across images should be "this measures the common part".
- Three-way reconciliation: `boot.json` (slot hash) × `build-manifest.json` (payload kernel hash) ×
  the actual file `mcopy`'d out (ground truth). When the three disagree, ground truth wins.

**Check.** For kernel identity, `python3 -c "import json;print(json.load(open('<tag>/build-manifest.json'))['components']['payload_kernel'])"`,
or directly `mcopy -o -i boot.img@@557056 ::/EFI/UniXNU/Payloads/kernel.macho k && sha256sum k`.

## P-201 — A control image built by bypassing build-strict.sh is automatically one evidence level lower

**Symptom.** The wifi line's `wifi-20261116a2` is a "control image": 65,978,368 B kernel,
`pong_wifi=0`, no MHI injection, originally a clean control with the wifi driver variable removed. But its
`build-manifest.json` has only four keys (tag / note / components / kernel_args),
**no series / repo / frozen / gates**, and the note says
`trial build outside build-strict.sh (flash gate blocked by the touch line)`.

**Why this is a problem.** Without a series fingerprint there is no way to prove which patch set this image used;
without a gates record there is no way to know whether the eight-step gate passed or was bypassed at the time. If it dies on device,
you cannot rule out "it is actually different source", so the control proves nothing — one window burned for free.

**Background (the justification at the time).** When a2 was built the eight-step `--flash` gate was blocked by the touch line (touch ⑦⑧
unfinished) and `build-strict.sh` refused outright, so packaging was manual. That reason held **at the time**,
but the artefact must be marked as low-grade evidence rather than used as a normal image.

**Fix.**
- manually packaged images always carry `-trial` in the tag, and the note states what was bypassed and why;
- when a judge/reconciliation script sees a manifest without a `series` key, it downgrades the conclusion to
  "structural observation" and must not accept it as evidence that "the variable was isolated";
- once the gate is restored, the same control must be rebuilt with `build-strict.sh` and the verdict taken from the new image;
- once the line blocking the gate (touch, this time) is fixed, go back and reissue the trial image as a proper image.

**Lessons.**
- "Evidence level" is not an abstraction: the keys missing from the manifest are exactly the refutations you no longer have.
  No series fingerprint = cannot refute "the source may differ".
- The note left when bypassing a gate saves you once, but it explains only "why it was bypassed", not "the result is trustworthy".
- The cost of a controlled experiment is a window, not build time; trading a window for an image whose identity cannot be re-verified
  is a loss.

**Check.** `python3 -c "import json;print(sorted(json.load(open('<tag>/build-manifest.json'))))"`
— missing `series` means trial grade.

## P-202 — Features silently dropped at build time, and a gate judging an old file

Both were reported by the thermal line on 2026-11-15 as "environment pitfalls"; on inspection they are main's own bugs.

**Symptom A: `build-strict.sh` silently turns off two features when there is no `.config`.**
The Guarantees at the top of the script say "no silent fallbacks", but lines 106 and 124 are
`GPU_ADDON=$(sed -n 's/^CONFIG_XNU_GPU_ADDON=y$/1/p' "$M/.config" | head -1)` and
`BATTERY_ON=$(sed -n ... CONFIG_XNU_K60_PHYSICAL_BATTERY ...)`. When `.config` does not exist
`sed` only writes `sed: can't read …/.config` to stderr and both commands return an empty string → neither `if`
is entered → the kernel has neither the Metal plugin nor the battery archive, and the script still walks all the way to `verify-boot-image: OK`.
`build-strict.sh` never generates `.config` itself (`grep defconfig` finds only two comment/echo lines),
so the normal path "fresh `K60_OUT`" is bound to hit it. Measured symptom: the thermal line's first build after rebase
was rejected by hard-38 (`CONFIG_XNU_GPU_ADDON missing from generated config …; expected y`),
and the audio line's `audio-probe-20261115l` had a `payload_kernel` of only 54,181,888 B where one with
GPU_ADDON should be in the 105 MB range — it is the product of this pitfall, and its manifest does not even have a
`kernel_args_requested` key (old script).

Fix: after `M=`/`KERNEL=` add a hard failure
`[ -f "$M/.config" ] || die "no $M/.config; generate it first: …unixnu defconfig …"`.

**Symptom B: `find_kernel()` in `check-kernel-archives.py` takes "the first path in sort order" as this round's kernel.**
`for board in sorted(base.glob("*/")): for candidate in sorted(board.glob("*/kernel/kernel.macho"))`
— a `kernel.macho` left behind by the previous build is taken as this round's, so P-190 reports
`CONFIG_XNU_K60_PHYSICAL_BATTERY=y but no k60_physical_battery_start symbol is in kernel.macho`
(measured on brightness-1), when the real reason is that it is judging an old file. `build-strict.sh:259` passes
`--kernel "$KERNEL"` explicitly so the main path is unaffected, but **running the gate on its own judges a file you did not think it was judging**.
The thermal line's workaround at the time was `mv $KERNEL $KERNEL.bak-<tag>` to push the script into the skip branch —
a gate that drives someone to "move the file away so it skips" has the wrong criterion.

Fix: take the newest by `st_mtime`, and when there is more than one print a warning line to stderr naming them, reminding the caller to use
`--kernel` to be explicit.

**Lessons.**
- "Silent fallback" is not banned by a comment: as long as one `sed` that cannot read the file returns an empty string,
  the feature silently disappears. Whenever a file is read to decide "do this or not", a missing file must be a hard failure.
- A gate's input must be more trustworthy than what it checks. Guessing which file is this round's with `sorted()`
  means basing the gate's verdict on filename order.
- A "workaround" the gate forces out of people (move the file away so it skips) is a strong signal that the gate is designed wrong,
  not a discipline problem on the user's side.

**Check.** `bash -n scripts/build-strict.sh && grep -c 'no \$M/.config' scripts/build-strict.sh`
— must be 1; `python3 -c "import ast,sys;src=open('scripts/check-kernel-archives.py').read();print('st_mtime' in src)"`
— must be True.

## P-203 — Never run `git worktree prune` inside a linked worktree

**Symptom**: to get a "clean environment" baseline, the refmine line ran
`git worktree prune` inside a linked worktree. The main repository's `E:/hackios/UniXNU-mondrian/.git/worktrees/` had the
administration directories of 19 linked worktrees deleted in one go (only `d-main` left), and immediately afterwards all of `/e/hackios/k60-*` reported
`fatal: gitfile does not point to a valid repository` — twenty lines lost their worktrees at the same time.

**Root cause**: `git worktree prune`'s criterion is "does this worktree's administration directory still exist, and is the gitfile target resolvable".
It starts from **the repository it is currently in** and deletes every admin directory it considers "invalid". Run inside a linked worktree,
it sees the whole of the main repository's `.git/worktrees/`, and the only thing it judges by is whether the gitfile is resolvable;
the moment any one tree is briefly unresolvable (or the worktree directory is moved, or the drive letter changes), it deletes that tree's admin directory as garbage.
**The deletion is irreversible and there is no backup**, and `git worktree add` will not rebuild it automatically.

**Recovery method** (`E:/k60-work/scratch/refmine/{repair-wts,fix6,infer2}.py` already implements it):
1. For each worktree directory that lost its admin directory, infer which branch it was on by "scoring branch blobs against the worktree's files" —
   a worktree with uncommitted file content scores differently against each candidate branch; take the highest.
2. Rebuild the three admin pieces: `.git/worktrees/<name>/{HEAD,gitdir,commondir}`, with `HEAD` holding
   `ref: refs/heads/<branch>`, `gitdir` holding that worktree's `.git` file path, and `commondir` holding `../..`.
3. In the worktree run `git read-tree HEAD` to fill in the index (**do not** `git checkout`, that would overwrite uncommitted content).
4. Verify: `git worktree list` shows nothing prunable, `git rev-parse` runs on both the MSYS and WSL sides,
   `git status --porcelain` shows dirty=0 in every tree.

**Why no gate caught it**: `git worktree prune` is a native command, and at the time `/usr/local/bin/git`'s guard blocked only
content-losing verbs like `checkout`/`reset`/`clean`/`stash`; `prune` was not on the list — yet what it loses is **administration metadata**,
with heavier consequences than `checkout` (one command affecting every worktree).

**Fix (four items)**:
1. add `worktree prune` to `git-guard`'s dangerous-verb table, at the same level as `checkout --`;
2. allow it only at the root of the main worktree with an explicit `K60_I_OWN_ALL_TREES=1`;
3. the correct way to get a "clean environment" is `git -C <other directory> archive` or `git clone --shared` into a temporary repository,
   never any cleanup action inside the shared repository;
4. before each build round run only `sync-device-input.py`, and perform no `git` cleanup at all.

**Lesson**: every `git` command carrying `prune`, `gc`, `repack` or `fsck --lost-found` changes shared state under the premise of "looking harmless"; only read-only verbs are allowed on a shared repository.

## P-204 — Using counts instead of semantics

The same mistake happened three times in one day, each time "string X appears N times in the log" taken as a conclusion:

1. **springboard line** (my mistake): `chronod` appeared only 2 times in three healthy logs, and on that basis I concluded
   "chronod never started". Measured: `usblog-20261115-003207:1230`
   `KE 107 109 xpcproxy …/ChronoCore.framework/Support/chronod` + `:2364`
   `K60RV 4 chronod[109]` — it was launched. It appears seldom because it is quiet, not because it is not running.
2. **thermal line** (agent's mistake): `Too many corpses` taken as the criterion for backboardd crashing.
   Measured: the pure-thermal `usblog-20261115-003922` has 6 corpses of its own (syncdefaultsd,
   mmaintenanced), while `crashed:.*backboardd` is 0. corpses is a global counter and does not point at any process.
3. **cellular line** (wrong format string): the judge command matched with `svc=$s`, while the driver's format string is
   `K60MODEM qrtr: service %u (%#x) instance %u node %u port %u`
   (`drivers/PongCellular/K60ModemLink.c:104`, `patches/xnu/0622-k60-modem-qrtr.patch:1023`)
   — `svc=` can never match, all five criteria were false negatives.

The common shape of all three: **first invent a string you can grep, then treat it as the criterion**, without first asking "what does it mean
when this string appears, and what does it mean when it does not". A count answers only "how many", not "what".

The correct shape of a criterion:
- Point at **lifecycle**, not at occurrence count: whether a process started is read from paired lines like `KE … <program>` and
  `K60RV <name>[pid]`, not from how many times the name appears.
- Point at **a specific object**, not at a global counter: whether backboardd crashes is read from `crashed:.*backboardd` and
  `KX! … backboardd exit=… sig=…`, not from `Too many corpses`.
- Copy the format string **from the source**, do not write it from memory: `grep -n 'printf' <driver>.c` to get the original, then write the regex from that;
  make word boundaries explicit (`service 1 \(` so that 1 does not match 11).
- A criterion must be **self-evidencing** in the log: the verdict line carries the field values it was based on (e.g. backlight's
  `conformance=%d control=%d stats=…`), so nobody has to re-run it to review it.

Check: `python3 scripts/check-docs.py` (this entry constrains only how criteria are written; the machine checking is carried by the per-line
`judge-*.py` self-tests, and `docs/engineering/JUDGE-CONTRACT.md` writes "criteria must be self-evidencing and negative samples must come from real logs" down as a contract)

## P-205 — Dates, numbers and gate listings drift in the docs, and check-docs cannot see it

On 2026-11-15 the user pointed at the README and asked "why is the information in the README not updated in time every time we merge to main, including but not limited to the eight-step diagram". On inspection three kinds of drift existed at once, and `check-docs.py` (★36's backstop gate) caught none of them:

1. **Date drift**: the README says "last updated: 2026-11-12", STATUS says "this round's update time:
   2026-11-14", while main has four more commits on 11-15, identity seed among them.
2. **Number drift**: the README's document table says "iron rules ★1–★35 / pitfalls P-01–P-130", when
   HARD-RULES.md's highest heading is actually ★37 and PITFALLS.md's is P-204 — exactly the historical scene cited in ★36's own
   verdict (★32/P-127), committed a second time.
3. **Listing drift**: the README's "gates" says "four checks" and lists research-gate / porting-gate /
   render --check, while the nine checks embedded in build-strict.sh (build-env / eight-step /
   kernel-archives / metal-blob / image-args / verify-boot-image / render / docs /
   readme) are mostly missing from the table, and the table lists two that do not run in the build at all.

Root cause: check-docs only checks "the link exists, the file is registered, the marker block is there" — it checks **structure**, while drift
happens in **content** (dates, numbers, the set of names). Content cannot be checked with fixed values, only by **reconciliation**:
against another file's date, against the real heading number, against build-strict.sh's marker region.

Fix: `scripts/check-readme.py` (★36 item 7) —
- the README's "last updated" ≥ STATUS's "this round's update time", and the EN date == the Chinese date;
- the ★N / P-M range statements in both READMEs == the real highest heading number in HARD-RULES/PITFALLS;
- both READMEs' gate tables name the same set of scripts, must include every gate in build-strict.sh's
  `# --- gate-table:BEGIN/END ---` marked region, and every named script must really exist;
- both READMEs' `EIGHT-STEP-TABLE` block == what `render-eight-step-table.py` renders live from
  EIGHT-STEPS.toml — merge a branch that adds a `[hardware.*]` row without
  regenerating the eight-step table and check-readme reports "inconsistent" on the spot.

Lesson: **names, dates and numbers are the three kinds of content that lie most in documentation** — they change daily, and nobody remembers to edit hand-written paragraphs. Any such "listing/count/date" written into a document must come with a machine check that can reconcile it, otherwise it will go stale in the next merge (same root as P-204's "using counts instead of semantics": numbers and names written into documents must be self-evidencing too).

Check: `python3 scripts/check-readme.py` (registry `id = "P-205"`)

## P-206 — A hardcoded board directory name in a gate script validates the old tree on a different board

The scene: the wifi line's board directory is called `mondrian_wifi` (named after the defconfig), while
`scripts/check-build-env.py` hardcodes `M` as `OUT/mondrian/ipados-16.6.1-20G81/mondrian`.
On that line's first build in the new tree the real gap was fakeroot missing
`Availability.h`/`AvailabilityInternal.h`/`TargetConditionals.h`
(`build-xnu-4k-baseline.sh`'s AvailabilityVersions install does not install these three headers,
and their real owner, `prepare-xnu.py`'s source mode, does not enter the ios16 path), and the kernel died 13 minutes later on
`fatal error: 'Availability.h' file not found`. P-185's gate kept validating the old mondrian
tree the whole time, green throughout — **the gate was not validating the tree the build was going to use**.

Lessons:

1. A hardcoded board directory path in a gate script is a bug (the same shape as P-193's "a literal checkout
   path in a gate is a bug"). The board directory name changes with the defconfig and must be derived live from the out tree.
2. "The gate is green" does not mean "the build will be green", unless the gate judges the tree the build is going to use. P-185's
   lesson was not fully absorbed the first time: it fixed only "what the name is", not "where the path comes from".
3. The gap list must be complete: the fakeroot required-file check originally looked at only 2 files, the two firehose ones
   are self-healing in the build, and the genuinely fatal ones are the three Availability headers — an incomplete list means the gate cannot see
   the fatal one.

Fix: `find_board_dir(out)` in `scripts/check-build-env.py` derives from
`out/*/ipados-16.6.1-20G81/*` by mtime (the newest with `tree/` or `.config` wins,
the literal is only a fallback), and `FAKEROOT_FILES` grows to 5 (adding `AvailabilityInternal.h`,
`TargetConditionals.h`, `firehose_buffer_private.h`).

Check: `K60_OUT=<out> python3 scripts/check-build-env.py` (registry `id = "P-206"`)

## P-207 — The gate draws conclusions about a stale artefact it itself blocks, and the build never starts

The scene: after the ADSP carrier merged into main, the shared baseline `baseline-20261115a` was rebuilt.
`build-strict.sh` ran the eight-step gate first (36 items passed), then `unixnu build kernel` ran the compliance registry and
`P-190` reported `CONFIG_XNU_K60_PHYSICAL_BATTERY=y but no k60_physical_battery_start symbol
is in kernel.macho` and refused the build. But the reason that symbol is missing is exactly "`out-baseline`'s `.config`
has been regenerated by `defconfig` (`PHYSICAL_BATTERY=y`) while the kernel is still the old one" — **the build needed to refresh it
is the very build this gate is blocking**. The same shape has now happened three times in this repository: P-194 (`porting-gate`
compares series against manifest, and the manifest can only be produced by the blocked build), P-165 (the build stamp can only be refreshed by
a build, which forced `K60_BUILD_IN_PROGRESS=1`).

Lessons:

1. A gate must measure "the artefact this round's build is about to produce", not "the artefact the previous build left behind". When the two
   cannot be distinguished (different timestamp/fingerprint), the gate's correct conclusion is **skip and say so**, not fail.
2. The criterion shape: `kernel.mtime < .config.mtime` ⇒ this pair is not comparable, print skip (with the reason and
   how to refresh), return 0; after the build ends build-strict runs the same gate again, when the kernel is newer, and that is
   the real criterion.
3. Such a skip is not a loosening: when `--kernel` is given explicitly (the post-build check) it is still a hard criterion; it skips only in
   the one state "the out tree was configured but not rebuilt".

Check: `python3 scripts/tests/test-check-kernel-archives.py` (8 cases, including
`a_stale_kernel_pair_is_skipped_not_failed`) and registry `id = "P-207"`.

## P-208 — `-D` attached to only one object left the same guard elsewhere compiled away to nothing

The scene: after `feat/adsp-carrier` merged into main, the feature image `adsp-20261115d` (`pong_handoff_publish=1`,
last payload args entry confirmed present) booted cleanly on device (SpringBoard 132, panic 0), but
`K60Handoff:` / `K60PAS` matched **0 times** — the publisher never ran once. `llvm-nm -18` on
`ios-obj/DEVELOPMENT_ARM64_PONG/iokit/DEVELOPMENT/IOKitBSDInit.cpo` shows:
**no** undefined references at all to `k60_adsp_handoff_publish` / `k60_physical_battery_start`.
Root cause: `scripts/build-xnu-4k-baseline.sh` puts `-DXNU_K60_PHYSICAL_BATTERY=1` only into
`PERSONALITY_CFLAGS`, which attaches only to `KernelConfigTables.cpo_CFLAGS_ADD`; the
`#if defined(XNU_K60_PHYSICAL_BATTERY) && XNU_K60_PHYSICAL_BATTERY` block of `0602`/`0619` lives in
`iokit/bsddev/IOKitBSDInit.cpp` → that define never reached this TU → the whole block compiled to nothing.
**And the link does not complain**: `-Wl,-force_load` had already pulled in all archive members,
so P-190's "is the symbol in the kernel" stayed green the whole time. That is to say the battery line's entry point and the ADSP publisher
have been dead code since the merge day, and so has `charging ⑧`.

Lessons:

1. The scope of a `-D` must equal the scope of "all TUs that use it". XNU's `<obj>_CFLAGS_ADD` attaches
   per object, so a define attached only to `KernelConfigTables.cpo` cannot possibly affect
   `iokit/bsddev/*.cpp` — any switch judged by `#if` in several places belongs in the global `EXTRA_CFLAGS`.
2. "The symbol is in the kernel" does not prove "the code will be called": force_load makes the symbol permanent. To prove
   a call site is alive you can only look at **references** (the symbol is in `nm -u <TU>.o`) or the on-device log.
3. A silent early return is the most expensive: `k60_adsp_handoff_publish()` has six `return`s (claim failure, board config
   parse failure, four-segment address overlap, `/chosen` missing, already exists) and none of them prints anything. The criterion must
   distinguish "not called" from "called but returned early" — this entry's criterion is "`K60Handoff:` matches 0 times"
   together with the nm reference check.

Addendum (hit a second time in the same round, exactly the same shape as P-207): the newly added gate in
`check-kernel-archives.py` reads `IOKitBSDInit.cpo`, while the registry calls it **without `--kernel`**
and **before** the build — so it read the object left by the previous build, which was already sick, and thereby shut out
the one build that could have fixed it (`❌ P-190 … the guarded block compiled away`). Fix:
P-208's verdict holds only when `--kernel` is given explicitly (the post-build call from `build-strict.sh`);
without `--kernel` it prints `skip:` and lets the build through; it also prints skip when the tree's compile has not reached that step.

4. A gate can only judge "the material evidence produced this round". A call with `--kernel`/`--out` is a post-build verdict; a registry
   call without arguments is a pre-build health check — one script in two roles, and the criteria must be written separately, otherwise it is P-207.

Check: `python3 scripts/tests/test-check-kernel-archives.py` (10 cases, including
`a_guarded_call_site_that_compiled_away_fails` /
`a_guarded_call_site_that_compiled_in_passes`) and registry `id = "P-208"`.

## P-209 — The defconfig named the 32 MiB seed's Data UUID: a panic at the root-mount stage with not one byte in the log

The scene: on 2026-11-15 five images from the wifi line (`wifi-20261116mhi3` / `mhi4` / `wifi-20261115z0` /
`wifi-20261116t2` / `wifi-20261116c0`) all presented as "0 bytes + port-not-observed + autoreset
back to fastboot". Four theories grew around that empty log: image size, 11.77 MB extra in
`__TEXT,__const`, firmware residency (`__TEXT` vs `__DATA`), the DarwinBoot pool window.

Among them, **c0** had one definite defect in its build configuration (the refmine line scanned 53 wifi/bt images,
`scratch/refmine/uuid-scan.py`, only c0 matched; the other four are all the device volume `1BCD69FF-…`,
still unexplained) —

```
configs/mondrian_wifi_defconfig:
  CONFIG_XNU_OWNER_DATA_VOLUME_UUID="6DCCF70A-6FD6-403E-ACED-95313CD7CBB8"
```

`6DCCF70A-…` is the OwnerData volume inside the repository's `seed/k60-data-seed.dbr`, that 32 MiB RAM disk;
the device's Data volume is `1BCD69FF-24A5-48B1-94B6-8FE592B2F597`
(`docs/plans/MONDRIAN-OFFICIAL-PAGES.md:564`: "the repository's actual Data UUID is 1BCD69FF-…").

The consequence of naming the seed UUID was measured on 2026-11-12 and recorded in PITFALLS 3811-3818:
`PONG APFS: wait for Data UUID 6DCCF70A…, timeout=5s` →
`K60DATA UFS Data window not published` → `dataerr=2` panics itself at `kern_exec.c:8463`.
`mondrian_wifi_defconfig` differs from the bootable `mondrian_defconfig` by only four lines (missing `GPU_ADDON`,
missing `K60_PHYSICAL_BATTERY`, this UUID line, extra `PONG_WIFI`), and the UUID is the only line that makes the kernel die at
**the root-mount stage** — though its causality still owes one single-variable confirmation (see the addendum).

Why it presents as "zero bytes" rather than a log with a panic: the USB console only comes up after `vfs_mountroot`.
For comparison the bootable `adsp-20261115e` (3,312 lines): the first `K60 USBLOG` is at ~line 470 and `K60DATA mounted`
at ~line 484. Any image that dies before root mount has no USB output at all — indistinguishable from "the kernel never ran".

Lessons:

1. When **several** images on one line are all silent, the first action is to diff the **build configuration** (defconfig, `board.toml`,
   `build-manifest.json`'s `payload_args`), not to diff kernel layout. All four hypotheses were built on the same
   empty log, which is zero information; once `payload_args` was aligned image by image, "missing arguments" was out on the spot.
2. "Zero bytes" is not evidence, it is the absence of evidence. Any defect that can kill before root mount (volume UUID, owner mount,
   Data window, UFS window) can only present as zero bytes under USB-only capture; the criterion must state
   "this entry cannot be judged from a 0-byte log; fix the capture first or diff the configuration first".
3. Alias-type constants must be recognisable to a gate: the seed UUID and the device UUID are both 36 characters, and the eye cannot tell right from wrong.
   Gate `scripts/check-defconfig-uuid.py`: a seed UUID in a defconfig must carry
   the `# SEED-UUID: intentional` marker (an experimental build trying the seed really should name it), otherwise hard failure;
   an unknown UUID only warns and does not fail (P-194 shape: a gate must not invent a verdict about something it does not understand).
4. Count-type corroboration (`grep -c`, `strings | grep -c`) is pure noise on this class of problem: all five images had "no
   wifi log at all", because they all died before the console. The criterion must point at the lifecycle line of a specific object (P-204).

Check: `python3 scripts/tests/test-check-defconfig-uuid.py` (8 cases) and registry `id = "P-209"`.

Addendum (half of it overturned in the same round): the first version of this entry attributed all five images to this one line, and refmine's 53-image scan disproved four of them
(only c0 matched). One more lesson on top: **attribution must be verified image by image**, you must not assume the same
cause because "they all look equally silent" — silence is the weakest observation, it smears different faults into one face. c0's causality itself also owes one single-variable confirmation:
the 2026-11-07 captures **with** the seed UUID (`bootcap-20261107-113650`) do have console output,
so "seed UUID ⇒ zero bytes" is not yet established, and waits for the c1 verdict (changing only this line). Until then c0 is recorded as
`invalid-measurement`, and the other four as "unexplained"; neither may be taken as "the kernel did not run".

## P-210 — The gate measures one defconfig only: the wifi board's Data volume UUID was never scored

Scene: line 31 of `scripts/check-data-identity.py` is `CONFIG = REPO / "configs" /
"mondrian_defconfig"`. It does two things — reconcile `CONFIG_XNU_OWNER_DATA_VOLUME_UUID`
against the volume UUIDs that have shown up in the device console, and reconcile the UFS
Data window ceiling against the manifest — and both only apply to **one** defconfig. The
wifi board has its own `configs/mondrian_wifi_defconfig`, which also carries
`CONFIG_XNU_OWNER_DATA_MOUNT=y`, so from beginning to end this gate never looked at it
once. That is how the seed UUID got into a shipped build (c0 in P-209):
`check-defconfig-uuid.py` is a structural gate added only after P-209, and the other half
of the evidence reconciliation — "has the configured UUID actually ever appeared on the
device" — was always empty.

Fix: `data_configs(config_dir)` iterates every file under `configs/*defconfig` that carries
`CONFIG_XNU_OWNER_DATA_MOUNT=y` (falling back to `mondrian_defconfig` only when there is
none), judges file by file and names file by file (failure messages carry a
`mondrian_wifi_defconfig:` prefix); `check_uuid` / `check_ceiling` accept an injectable
path, `run()` returns `(problems, notes)` for the tests;
`scripts/tests/test-check-data-identity.py` covers 9 cases including "the second defconfig
gets scored", "a file without the mount key does not count as a failure", "skip when there
is no console", "skip when the log has no window line", "fail when the ceiling is
insufficient", "skip the ceiling when there is no manifest".

Verdict (obtained in the same round, shaving another layer off P-209's causality): c1 is a
single-variable image that changes exactly one line of the c0 recipe, the Data UUID; on
device 2026-11-15 `usblog-20261115-231707` = port-not-observed / 0 bytes /
returnedToFastboot=True. **Getting the UUID right still does not boot**, so the seed UUID
can only explain one dimension of c0; silent has at least two independent causes, and c1's
cause of death is still unexplained.

Three lessons:

1. Finding "the second copy the gate does not cover" is worth more than finding a bug: a
   `CONFIG = …/mondrian_defconfig` constant is one coverage hole, and it looks exactly like
   normal code.
2. A successful single-variable fix ≠ the original hypothesis holding. c1 shrank the
   difference to one line and the result was still 0 bytes — that is precisely the only way
   to demote "seed UUID ⇒ zero bytes" to "one dimension".
3. Every verdict line must be able to answer "which file was read". When gate output
   carries no filename, "pass" may just mean "not measured"; that is also why every failure
   message in this gate carries a `filename:` prefix (same family as P-204).

Check: `python3 scripts/tests/test-check-data-identity.py` (9 cases) and registry `id = "P-210"`.

## P-211 — The bookkeeping tool writes "the series in the repository at the moment of registration", not the image's own series

Scene: `series_fingerprint()` in `scripts/record-boot.py` has always read
`REPO/patches/xnu/series`. Late on 2026-11-15, when I registered the `bt-bisect-h12` image
(boot.img `0eb30032…`), what went into the ledger was
`series 9688ad85…(226)` — main's current series; but that image was actually built by the
bt line with a 229-entry series. Neither side matches, yet the ledger looked intact:
`record-boot.py` printed `✅ recorded`, and `porting-gate.py` when reading the ledger only
compared it against a fingerprint it computed itself.

This is the fourth member of the "measured the wrong object" family, and the previous three
each had a different shape:
P-194 measured the wrong **file** (`SERIES-FINAL.txt` instead of `patches/xnu/series`),
P-200 measured the wrong **slot** (`kernel_sha256` in `boot.json` measured the boot image's
kernel slot instead of the kernel),
P-201 measured the wrong **presence** (a trial image with no series fingerprint was still
treated as evidence),
P-211 measures the wrong **version** (describing last week's image with today's repository).

Fix: `image_series(image)` first reads `build-manifest.json` from the image's own directory
(`build-strict.sh` already writes it there; `series.sha256` + `series.count` are the values
it recorded, produced at the same time as the image); only when it cannot be read or the
fields are incomplete does it fall back to the repository series, and **it leaves the
source in the ledger line**: `"series-source": "manifest:<path>" | "repo-series"`,
`"series-count"`, `"repo-series"`. When the two disagree it prints a warning first ("what
is recorded is the image's series, so the ledger cannot claim this repository's series
ever ran"). Test `scripts/tests/test-record-boot.py` has 4 cases: manifest preferred, no
manifest falls back, short sha falls back, bad JSON falls back.

Three lessons:

1. Before recording anything, ask "who does this field describe". If it is "this artefact",
   read it from the artefact itself; anything read from the repository's current state is
   only **today's guess**.
2. A fallback path must leave a marker in the data (`series-source`), otherwise "fallback"
   and "the real answer" look identical in the ledger and downstream cannot tell them
   apart — the same shape as P-190/P-192.
3. A `✅` print only proves the flow finished, not that the recorded value belongs to the
   recorded object. A verdict either carries its source or carries a cross-check; with
   neither it is just a ritual.

Check: `python3 scripts/tests/test-record-boot.py` (4 cases) and registry `id = "P-211"`.

## P-212

A log that prints configuration as evidence looks more like evidence than no log at all.

Scene: the criteria in `docs/research/charger/07-DEVICE-CRITERIA.md` were originally
written as "a subscription line appearing counts as subscription success". When the charger
line handed back `scripts/judge-battery.py` on 2026-11-15 it brought three same-shaped
defects, each of them "there is a line in the log, therefore the thing happened":

1. `subscription-ack=0 0` — both captured fields are 0, and the script used to judge PASS.
   0 means "not measured", not "measured as 0"; judge INVALID.
2. `temp=0.00C` — the sensor returns 0 when unpowered, which used to fall inside the lower
   bound. 0.00 degrees Celsius is an impossible reading on an SoC; judge FAIL, and change
   the legal range to an **open interval** `(0, 60]`.
3. A single `sample` line — concluding from one line. One sample cannot distinguish
   "steady state" from "transient"; fewer than two lines judge INVALID.

This one and P-204 "using a count instead of semantics" are two directions of the same
family: P-204 **treats a count as a conclusion** (appeared twice, so it did not start),
P-212 **treats configuration as a result** (the subscribe parameters were printed, so
subscription succeeded). The shared mistake: the criterion answers "I saw a line of text",
not "the observed system entered that state".

Fix: criteria must be three-state (PASS / FAIL / INVALID), INVALID specifically absorbs "not
measured" and "measured an impossible value"; each criterion prints its hit count and line
numbers, and the last line must give `TOTAL: n PASS / n FAIL / n INVALID`; the exit code
distinguishes the three states (0/1/2), and the script may not return 0 when it could not
read a single piece of evidence. Landed: `scripts/judge-battery.py` (400 lines, 16 tests,
with `docs/research/charger/07-DEVICE-CRITERIA.md` as its criteria document).

Three lessons:

1. Between "printed the configuration" and "the configuration took effect" sits a real
   state transition. The criterion must watch the quantity after the transition (four
   attributes non-zero), not the text written before it.
2. 0 and "not measured" must be separated. For any sensor/counter that may return 0, the
   criterion must be able to express "is this 0 a reading or an absence"; if it cannot, that
   is INVALID.
3. Three states cost more than two, but two states quietly record "not tested" as "pass" —
   which is the most expensive kind of false green.

Check: `python3 scripts/tests/test-judge-battery.py` (16 cases) and registry `id = "P-212"`.

## P-213

A gate also commits the very error it exists to prevent: reading literals instead of
following variable propagation.

Scene: after P-208 I wrote `scripts/check-define-scope.py` to answer structurally "does the
object the guard lives in receive this `-D`". The first version only parsed literal
assignments of the `<obj>_CFLAGS_ADD=-DXNU_x` form, so it judged
`XNU_NATIVE_RAM_BLOCK` as "only reaches `kern_exec.o`" — while it actually is

```sh
PERSONALITY_CFLAGS="-DXNU_NATIVE_RAM_BLOCK=1"
PERSONALITY_CFLAGS="$PERSONALITY_CFLAGS -DXNU_OTHER=1"
EXTRA_MAKE_ARGS+=("KernelConfigTables.cpo_CFLAGS_ADD=$PERSONALITY_CFLAGS")
```

accumulated into a variable and then handed to an object as a whole. A gate that cannot read
variables reports an error on a **legitimate** guard — which is exactly P-208's mirror
image: P-208 is "the define did not reach the object it should", P-213 is "the gate thinks
it did not".

Fix: `read_variables()` builds a shell variable table line by line (both the `VAR=-DXNU_A`
and the `VAR="$VAR -DXNU_B"` shapes), `VAR_REF` expands `${VAR}`/`$VAR` references,
`_strip_comment()` strips end-of-line comments (otherwise a commented-out `-DXNU_FOO` counts
as effective), and `read_object_defines()` also expands variables on the right-hand side of
`_CFLAGS_ADD=`. After the change, `✅ define scope: 81 guard(s) all reachable`, with all 12
skips being defines that come from config headers rather than the build script
(`XNU_MONITOR`/`XNU_TARGET_OS_OSX`/`XNU_NATIVE_UFS` etc.).

Three lessons:

1. A gate must model **the tool's real behaviour**, not the spelling that is most obvious to
   you. The shell expands variables, so the gate has to expand variables; reading literals
   means writing a wrong implementation of the shell.
2. The first thing a new gate does is run against a known-legitimate sample. Had I run
   `XNU_NATIVE_RAM_BLOCK` (a guard known to work) first, version one would have been
   rejected on the spot instead of waiting for a false report.
3. "Don't know" must be its own tier (`skip:`), not folded into PASS or FAIL. If those 12
   config-header defines were judged FAIL, the gate would instantly become a noise source
   and then be bypassed — worse than no gate.

Check: `python3 scripts/tests/test-check-define-scope.py` (9 cases) and registry `id = "P-213"`.

## P-214 — Both hashes called "series fingerprint" live in different namespaces and can never be equal

Scene: after every merge on main, `check-rules.py` reported `iron-4` / `hard-33` with the
content "the series of the last successful boot does not match the current repository".
Digging in showed the series **had not changed at all**:

- `SERIES_SHA=$(sha256sum "$REPO/patches/xnu/series" | cut -d' ' -f1)` in
  `scripts/build-strict.sh` measures **the series file's bytes**, 64 hex, written into
  `build-manifest.json` as `series.sha256`;
- `series_fingerprint()` in `scripts/porting-gate.py` and `scripts/record-boot.py` measures
  **each entry's name + size**, `sha256(name + str(size) for each entry)[:16]`, 16 hex.

Both are stable, both look like fingerprints, both are called `sha256`, and they are
**never equal**. After P-211 made `record-boot.py` trust the image's own manifest first, the
ledger began recording the 64-hex manifest value (`bt-bisect-h23` as `88faf6c25de1e77c`,
`bt-bisect-h124` as `21eda89a147c9653`), while porting-gate still computed
`9688ad85833d7dd2` from names+sizes — so "last success ≠ now" was permanently true on main,
and the gate correctly reported a difference that did not exist, every day.

The shape of this pitfall is **comparing a same-named field across namespaces**: both values
are 64/16 hex, both pass the "looks like a sha" check, and the length check is not wrong
either (16 hex is a prefix length of 64 hex), so any "is the format right" gate lets them
through. Only "who computed this number" can separate them.

Fix (all three together, none alone suffices):

1. **One implementation**: new `scripts/series-fingerprint.py` with `fingerprint()` as the
   only algorithm; `build-strict.sh` now calls it (both `SERIES_SHA` / `SERIES_COUNT` come
   from it) instead of computing its own. The file-byte hash is renamed `file_sha256` and
   kept (it is sensitive to "the patch content changed", a useful second quantity).
2. **Self-description**: add `"namespace": "names+sizes"` to the manifest's `series`, so
   readers can decide comparability from that instead of guessing from the length.
3. **Refuse cross-namespace comparison**: `image_series()` in `record-boot.py` prints and
   falls back to the repository series when `namespace` is not `names+sizes`; manifests
   lacking `namespace` with a hash longer than 16 (pre-P-214 old manifests) also fall back;
   only old manifests with 16 hex and no namespace remain usable.

Three lessons:

1. **A same-named field must carry a namespace.** Both hashes being called `sha256` is the
   root cause; had the manifest called them `series.file_sha256` and `series.entry_sha256`
   from the start, this pitfall would not exist.
2. **When a gate goes red, first ask "who computed this quantity"**, then ask "is the value
   right". I spent half a day investigating where the series changed, while the series had
   been `9688ad85833d7dd2` all along.
3. **Format validation cannot replace provenance validation.** 16 hex and 64 hex are both
   legal hexadecimal; the length check, the character-set check and the non-empty check all
   pass. The only thing that separates them is their producer.

Check: `python3 scripts/tests/test-series-fingerprint.py` (8 cases, including
`the_gate_and_the_recorder_still_agree`, which directly compares the three embedded
implementations against the tool's output) and registry `id = "P-214"`.

## P-215 — A lazily allocated lock returns failure "before anyone allocated it", which is denial of service; and a 0-byte log hid that refusal for three days

Scene: all seven wifi-family images (c0/c1/c2/z0/t2/mhi3/mhi4, kernels 66–117 MB) were
`port-not-observed` / 0 bytes. The axes ruled out one by one (each with a measurement):

| Axis | How it was falsified |
|---|---|
| total kernel size | 117 MB was silent, but 129 MB (`adsp-20261115c/d/e`) and 105 MB all reached the desktop |
| segment span / 254 MiB window | `darwinboot_parsekernel.py` reproduces every firmware rejection condition, all five PASS; the 129 MB span of 141,111,296 is larger than c2's 129,642,496 yet it boots |
| segment the container lives in | PWF2 placed in `__TEXT,__const` (c0/c1/z0) and in `__DATA_CONST,__const` (c2) are both silent |
| firmware volume / DTB | `bootimg_slots.py` compared item by item: `gzip_sha256`, `shim_sha256`, `fd_sha256`, DTB all identical, the only difference is the ramdisk |
| ADT | `darwinboot_adt.py` reproduces `AdtNode()`, all five ACCEPTED/exact, 25 nodes, window `0x120000000` |
| console args | the 29 `payload_args` items are identical character by character across all five, only the last item differs |
| Data volume UUID | c1 corrected the seed UUID in `mondrian_wifi_defconfig`, still silent |
| C++ global constructors | `macho_initfunc.py`: `__mod_init_func` is 102 on both sides, +0/−0; `__pong_init` has no consumer in the kernel and by design does not execute |
| `__init_entry_set` | the `__startup_` symbol count is 4,980 on all three, +5/−5 is just renaming |

Real cause (`patches/wifi/0004-drivers-NativeUfs-pong-ufs-ready.patch` + `0001`):

```c
// the lease block that 0004 inserted into hostBringUp() of PongUfsTransport.cpp
if (pong_smmu_lease_lock && pong_smmu_lease_unlock) {
    lease.held = pong_smmu_lease_lock();
    if (!lease.held) return transportFailure("Apps SMMU lease unavailable");
}
// how 0001 does it: return false when the lock was never allocated
extern "C" bool pong_smmu_lease_lock(void){
    if(!smmuLeaseLock) return false;      // <- deny service
    IOLockLock(smmuLeaseLock); return true;
}
```

`smmuLeaseLock` is only `IOLockAlloc()`ed inside `pong_rpmh_init()`, and the only call site
of `pong_rpmh_init()` is `pong_wifi_start_optional()`, which `patches/wifi/0005` calls after
`registerService()` in `ArmDTPlatform::configure()`. **UFS is the root device and
necessarily starts first** (measured: in a log that does boot, `PONG_UFS` is at line 115 and
`ArmDTPlatform: registered platform` at line 147). So when UFS calls lock(), the lock must
be NULL → false → `transportFailure` → the entire UFS transport gives up → no root device →
the kernel dies before the console worker comes up → **0 bytes**.

Fix (`patches/wifi/0012`, 20,480 B of code, single variable): move the allocation into
lock() itself —

```c
extern "C" bool pong_smmu_lease_lock(void){
    if(!smmuLeaseLock) smmuLeaseLock = IOLockAlloc();
    if(!smmuLeaseLock) return false;
    IOLockLock(smmuLeaseLock); return true;
}
```

On-device verification: `wifi-20261116c3` (`boot.img 5a19e110…`, 117,325,824 B, carrying a
real PWF2 container of 11,189,974 B), evidence `usblog-20261116-015128`: console 221,429 B /
3,202 lines / **SpringBoard 132** / panic 0 / `:482 K60DATA mounted ro=0 fstype=apfs` /
`:972 Early boot complete. Continuing system boot.`

**Why this accident cost three days**: a 0-byte log erases both "did not execute" and
"executed and failed halfway" at once. The console is a ramoops ring buffer;
`k60_usblog_init()` in `patches/xnu/0300` (`osfmk/arm/arm_init.c`) only does read-only
probing, and the real drain worker is started by `k60_usblog_start()` inside `if (result ==
KERN_SUCCESS)` in `bsd/kern/bsd_init.c`. So "the first log line is `K60 USBLOG: GDSC
usb30_prim`" **cannot** prove it executed before UFS — that is just the write order into
the ring buffer. Any early failure that makes `IOKitBSDInit()` return something other than
`KERN_SUCCESS` skips the console worker outright, which matches 0 bytes exactly. This was
corrected only after user m27494 pointed out the flaw in my argument directly: I had used
"line 1 was output before UFS" to reject the UFS hypothesis, excluding the real culprit for
a full round.

Four lessons:

1. **A `lock()` that returns bool and returns false when the lock is not ready is
   semantically denial of service**. A lazily allocated lock must guarantee its own
   allocation; making the caller carry the knowledge of "who initialises first" disguises an
   initialisation-order defect as a normal error return. The correct shape is "either it
   succeeds or it panics", not "quietly return false and let the first caller die".
2. **A weak reference only solves "the symbol may not exist", not "the symbol exists but
   refuses service"**. `if (pong_smmu_lease_lock && pong_smmu_lease_unlock)` looks like a
   complete guard, but it only covers the `weak_import` resolution-failure tier, missing
   "resolved fine, the call returns false". A weak-reference guard must be written as "the
   symbol is present && the call succeeded", and call failure needs its own log, independent
   of symbol absence.
3. **Ownership of a resource shared across subsystems must fix the startup order at design
   time, not rely on "whoever gets there first"**. Apps SMMU is shared by UFS and Wifi; UFS
   starting first is **inevitable** (it is the root device), so the lock's allocation point
   must be earlier than UFS, or lock() must do it lazily itself. The assumption "wifi will
   initialise first anyway" is worthless in the face of startup order.
4. **A 0-byte log is the weakest observation; it smears different faults into one face**.
   This time it erased "the kernel was not loaded", "the kernel crashed before line one" and
   "the kernel got as far as root mount failure" at once. Determining "who executes first"
   can only rely on **the call chain in the code**, not on log line numbers — the ring
   buffer robs line numbers of temporal meaning. Any argument of the form "A's log precedes
   B's, so A executed first" must first ask whether the log is direct-write or buffered.

One engineering lesson attached (same batch of accidents, from wifi line `3207bd3`): **after
resolving a merge conflict, verify whether functional blocks in non-conflicting regions were
replaced wholesale by the main side**. That merge's `build-strict.sh` conflict preserved only
two manifest fields and dropped the entire `XNU_PONG_WIFI_ARCHIVE` definition block and the
P-190 guard — invisible statically, because the manifest still held a reference; the result
was "it links but the ledger cannot record it and the guard does not run".

Check: `python3 scripts/tests/test-pong-smmu-lease.py` (delivered by the wifi line; pins the
function being unique, allocation preceding the null check, still `IOLockLock`, and the patch
being the last entry in the series) and registry `id = "P-215"`.

## P-216 — Firmware volume builds are not deterministic: three rebuilds give three hashes, while the manual says "same source ⇒ same bytes"

Scene (2026-11-16 02:31–02:47, same checkout, same pin, no uncommitted changes):

| Run | SOURCE_DATE_EPOCH | FD sha256 (first 12) |
| --- | --- | --- |
| baseline (device-verified) | natural value | `4bbe76017eb4` |
| rebuild 1 | natural value (uefi HEAD already one commit ahead) | `ce12d145a71e` |
| rebuild 2 | explicitly pinned to `1794541119` | `77ad2474a468` |
| rebuild 3 | natural value | `9f20de15388a` |

`docs/engineering/FIRMWARE-REBUILD.md` §2 says "`firmware.py:85` pins `SOURCE_DATE_EPOCH`
to the uefi repository's last commit time, so the same source + the same pin ⇒ the same FD"
— **that sentence is wrong**.

Measured root cause: both volumes have a CodeView record at the same offset `0xc8b8`, but
the 16-byte build-id after `RSDS` differs (`c61b6000b5826a234c4c44205044422e` vs
`0b5c83d97f72b6714c4c44205044422e`, the last 8 bytes `4c4c44205044422e` = `"LLD PDB."` are
the same). LLD's build-id is derived from the set of input files and the link order, and is
not affected by `SOURCE_DATE_EPOCH`; and the firmware volume is **compressed**, so one
changed GUID changes the whole compressed segment — 453,604 B of 3,145,728 B differ (1,739
disjoint intervals).

Two consequences:

1. **The FD's sha256 cannot be used as an "identity".** It can only be "this build's
   identifier". Any inference of the form "two volumes hash differently ⇒ different source"
   is wrong (I made it once, and nearly attributed `ce12d145` to a cellular line commit).
2. **Deciding whether a rebuilt volume is usable can only be done on device.** That is
   exactly what `FIRMWARE-REBUILD.md` §5 step 4 says, except §2 overrode it.

**Verified conclusion** (same payload, only the FD replaced):

- The payload of `baseline-20261115d` reused byte for byte
  (`fbc87102d1cb10df080d7dc6135e9e5b995e1f791ab5d2aa0a8e37a872271e3f`), with only the FD
  swapped for the rebuilt `9f20de15388a`, and `boot.img` repacked
  (`51d2053891569eeeb33a9f78989de6d66a111aa594541d9c7c5fb89622b3f3ce`).
- On device (`E:\k60-work\evidence\usblog-20261116-025525`): 3384 lines / 230,107 B /
  **SpringBoard 129** / `Early boot complete` once / `K60DATA mounted` once / panic markers 0
  / `menu:` and `config: no boot entry` **0 times**.
- ⇒ **P-154 formally closed**: a firmware volume rebuilt from the current pin can find the
  payload.

**Four lessons**

1. "Determinism" must be proven by two measured runs with identical inputs, not deduced from
   "I saw a fixed timestamp". `SOURCE_DATE_EPOCH` only affects the fields that actually use
   it (`__DATE__`/`__TIME__`, the PE header timestamp); it has no effect on a build-id the
   linker generates itself.
2. Small differences inside a compressed container are amplified into big ones: do not infer
   "different source" from "different hash"; first look at which class of bytes the
   difference concentrates in (here CodeView/RSDS).
3. When an output's hash is unstable between builds, it cannot go into the manifest's
   `components` (fields there imply "comparable" semantics); it needs its own "this build's
   identifier" field instead. This and P-214 (fingerprints from two namespaces are
   incomparable) are two directions of one class of error: there the names were the same and
   the meanings differed, here the names are the same and the stability differs.
4. The "why this matters" section of a manual makes it very easy to take a premise for a
   conclusion. That §2 sentence existed to argue "no need to rebuild", while it can in fact
   only argue "no need to rebuild for reproducibility".

Check: `python3 scripts/check-firmware-volume.py` (new) — it measures no hashes, only two
things: ① `FIRMWARE-REBUILD.md` must no longer contain an assertion of the form "same source
⇒ same bytes"; ② any document citing an FD hash must also state that it is "an identifier
for one build" rather than an "identity".

## P-217 — The build depends on a commit that exists only on this machine, while the config file claims it is already in the pin

Scene (2026-11-16 03:14): `board.toml`'s `[firmware].patches` says

> Mu_Basecore 6f805f2 already carries all six K60 fixes (3d2a9fa, "local patches for k60
> firmware build", is an ancestor).

Two of those three sentences are wrong, and they are wrong in exactly the "no work needed"
direction:

1. **`3d2a9fa` is not an ancestor of `6f805f2`.** `git merge-base 3d2a9fa 6f805f2` returns
   nothing — the two histories have no common ancestor. `3d2a9fa`'s parent is `3c9c7b2`
   (`[DROP on REBASE]`), which is not on any remote branch; `3d2a9fa` itself is also only
   local (`git branch -r --contains` returns nothing for both).
2. **`6f805f2` does not carry those five fixes.** Comparing the 11 files one by one: on
   `6f805f2` only `AsmMacroLib.h` was fixed upstream by another method (`#ifdef __ELF__`
   branch, PE side uses `.text$ ## Name`); the other 10 files are **original** on `6f805f2`.

Why it went unnoticed for so long: the build uses the `Mu_Basecore` worktree's **current
content**, not the submodule pointer. `Mu_Basecore/.git` is a **directory** (a nested
repository), not a submodule registered under `.git/modules/`, so the `-` prefix from
`git submodule status` and the ` M Mu_Basecore` from `git status` only ever report "pointer
and worktree disagree", and nobody looked at what that disagreement actually meant. The
build kept succeeding because the worktree really did contain those fixes.

**The fix is already verified to exist**: all five fixes already have patch files in the
repository (`Resources/MuPatches/{Auth-Service,Boot-Manager,K60-Exception-Image,Timer,Usb-Bus}.patch`);
they all pass `git apply --check` on `6f805f2`, and after applying, 10 of the 11 files are
**byte-identical** to `3d2a9fa`'s content, the only difference being `AsmMacroLib.h`, which
upstream had already fixed itself. `scripts/unixnu/firmware.py:73-78` already supports
`[firmware].patches` (apply at build time, reverse in `finally`), so all that is needed is
writing the five patches into `board.toml` and moving the worktree to `6f805f2`.

**Four lessons**

1. "The submodule pointer" and "what the build actually uses" are two different things. When
   the submodule is a nested repository, the pointer is just a number and nothing forces the
   worktree to agree with it.
2. "Upstream already fixed it, so no patch needed" must be verified file by file, not
   inferred from an ancestry relation. Here it was wrong on two levels: the ancestry does not
   hold, and even if it did it would not show those lines were not reverted.
3. "Already included" in a config file must have an executable criterion (such as
   `git merge-base --is-ancestor` or a file-by-file comparison), otherwise it is just a
   comment that cannot be falsified.
4. "It builds on this machine" does not equal "the repository builds". The criterion is
   "reproduce this build from what is visible in the repository" — the same theme as
   P-216 (firmware volumes are not reproducible) and P-154 (a rebuilt volume cannot find the
   payload), seen from three sides.

Check: `python3 scripts/check-basecore-pin.py` (new) — it measures three things: ① the
`Mu_Basecore` worktree's HEAD must equal the pin recorded by the main repository's
`git ls-tree`; ② every file in `board.toml`'s `[firmware].patches` must exist and pass
`git apply --check`; ③ if the worktree differs from the pin, there must be an explicit
record in `docs/engineering/FIRMWARE-REBUILD.md` saying why (otherwise it is this pitfall).

## P-218 — The bisect only flew "the next one", and the missing cell was exactly the decisive one

**Scene (2026-11-16, bluetooth 0005 four-hunk bisect)**

`patches/bt/0005` has four independent hunks (h1–h4); the full recipe is silent (0 bytes,
port never enumerated). The four hunks have 15 non-empty subsets, of which 9 were actually
flown:

| Recipe | SpringBoard | getBytes | Result |
|---|---|---|---|
| h1 | 13 | 36 | boots |
| h13 | 13 | 36 | boots |
| h4 | 13 | 36 | boots |
| h12 | 132 | 0 | boots |
| h23 | 128 | 0 | boots |
| h124 | 132 | 0 | boots |
| h34 | 128 | 0 | boots |
| **h123** | **0** | — | **silent** |
| full 0005 | 0 | — | silent |

`h123` was built at 23:18, but nobody flew it for four hours — because each round I picked
images by "what should be verified next", never going back to fly the one "already sitting
there and never flown". That cell was exactly the only decisive one:

- The lethal set is exactly **{h1, h2, h3} all present**, with `h4` irrelevant.
- Verification: removing any one of them from h123 still boots (remove h1 = h23 boots, remove
  h2 = h13 boots, remove h3 = h12 boots), so all three are necessary; the full 0005 is also
  silent, consistent with "it contains h1+h2+h3".

**That cell overturned my conclusions from the previous two rounds**: first "h2 is a
necessary condition for 'no longer silent'" (h23 and h34 both lack h2 yet both boot), then
"the lethal set is the h3×h4 pairwise interaction" (h34 is h3+h4 and boots).

**Why this error was expensive**: every wrong conclusion becomes an instruction to an agent.
Acting on "h2 is necessary" I had it build h12; acting on "h3×h4" I had it build h34; both
were wasted runs. And the image the right answer needed had been built long before.

**Fix**

1. **A bisect either flies the full set or explicitly lists "built but not flown"**. The
   matrix is not "which ones I flew" but "which ones in the full set have not been flown" —
   only the latter can answer "is the conclusion settled".
2. **Each round, scan the artefact directory first**: list existing images by mtime, compare
   against the flown list, fill the gaps before producing new ones. Measured practice:
   `ls -dt /mnt/e/k60-work/artifacts/*/` plus each `build-manifest.json`'s
   `components.boot_img`, differenced against the image hashes in
   `/mnt/e/k60-work/ledger.jsonl`.
3. **When the subset count is ≥ 8, work out how many cells must be flown before starting**.
   Among the 15 subsets of four hunks, the single cell {h1,h2,h3} settles it — but only if
   you know you are looking for "the minimal lethal set" rather than "eliminating one by
   one".

**Check**: `python3 scripts/check-bisect-coverage.py` (registry `id = "P-218"`)

**Related**: P-201 (trial images carry no series fingerprint, so they only count as
structural observation), P-204 (using a count instead of semantics), P-211 (the bookkeeping
tool describes the repository, not the image). All four belong to the "evidence does not
correspond to the object" family.


## P-219 — `ml_io_map`'s 8 MiB budget is shared kernel-wide, and the bluetooth ladder is the one that punched through it

- **Hard evidence** (on device, `evidence/usblog-20261116-055237/console.log`, `bt-d4-late`):
  ```
  :484 [bluetooth] power: cold boot, rails not voted (k60bt_warm=0)
  :485 K60PANICFMT caller=0xfffffff007b83384 fmt=kmem_%s(%p, %zd, 0x%x): failed with %d @%s:%d
  :486 K60PANICARGS kmem_alloc(0xfffffff3447b1240, 1048576, 0x100021): failed with 3 @vm_kern.c:178
  :487 K60PANIC: ring kept; restart reason -> bootloader
  ```
  `1048576 = 0x100000` is the `K60_TLMM_SIZE` the fourth `k60_map()` in `k60_bt_power_on()`
  asks for; `0x100021 = KMA_NOFAIL(0x1) | KMA_PAGEABLE(0x20) | KMA_PERMANENT(0x100000)` is
  exactly the flag combination used by `osfmk/arm/io_map.c:120` in the
  `startup_phase >= STARTUP_SUB_KMEM` branch; `failed with 3` = `KERN_NO_SPACE`.

- **Causal chain**: `io_map.c:65` `#define IO_MAP_SIZE (8ul << 20)` is the **only** IO submap
  in the whole kernel; every `ml_io_map()` goes through `kmem_alloc(io_submap, ...,
  KMA_NOFAIL)` at `:128` **without looking at the return value**; when full it calls
  `__kmem_failed_panic` (`vm_kern.c:1002`, only when `KMA_NOFAIL` is set).

- **Measured budget** (`scripts/check-io-map-budget.py`, run on the `bt-out-s1c` applied
  tree): the 37 resolvable call sites total **`0x73a900` = 7.23 MiB / 8 MiB** (another 7
  sizes come from runtime variables). That is, `k60_usblog` + `qbt_k60` + `pong_goodix` +
  `pong_buttons` + `pong_audio` + `aw882xx` had already eaten 90% of the submap, so the
  bluetooth ladder asking for another 1 MiB TLMM window had to fail.

- **Why this pitfall fooled us for three days**: the `kmem_alloc` panic kills the kernel
  before the console is up. The only surviving record is the `d4` run, where
  `pong_bt_late=1` moved the ladder after Data mount — the console came up first, so the
  panic got written into the ring. **Every wifi/bt image without `pong_bt_late=1` leaves only
  0 bytes**, indistinguishable from "the driver never ran" (P-63 already recorded the same
  shape for touch).

- **Fix**: `patches/xnu/0621-k60-io-submap-budget.patch` raises `IO_MAP_SIZE` from
  `8ul << 20` to `32ul << 20`. The submap is a **virtual address space** reservation;
  `kmem_suballoc` only consumes VA, and the parts that are never mapped cost not one
  physical page. 32 MiB leaves 4× headroom over the measured 7.23 MiB, and also covers the
  windows of the 7 runtime sizes.

- **On-device verification** (`evidence/usblog-20261116-064150/console.log`, `bt-d5-iomap`,
  series 233, `kernel 2c8d92c6…` 106,598,400 B, `boot.img 491c62de…`): the same bt recipe with
  only this one patch added, `kmem_alloc(... 0x100021): failed with 3` no longer appears, and
  the ladder runs all the way to firmware download —
  ```
  :484 [bluetooth] full: power_on enter
  :486 [bluetooth] smmu plan sid 0x483 slot 110 bank 72 … action install dma 0x90bc20000
  :488 [bluetooth] full: dma buffer and smmu bypass ready
  :494 [bluetooth] full: qbt_boot enter
  :707 [bluetooth] QCA controller version 0x12110201
  :708 [bluetooth] addon: serving 146068 0
  :724 [bluetooth] addon: serving 6442 0
  ```
  `:707` is the version register read back from the QCA6490, and `:708`/`:724` are firmware
  fragments the controller fetched on demand — **a readable version and fetched fragments
  mean the SMMU bypass, the clock votes and the GENI transfers after power_on all hold**.
  SpringBoard 132 lines, panic markers 0.

- **Four lessons**:
  1. **A global budget-type resource requires summing when adding a window**, not just
     looking at what this call needs. P-63's "30-second check" said "add them up manually";
     the result of "manually" was that nobody added them up — now there is a gate.
  2. **`KMA_NOFAIL` turns "allocation failed" into "panic"**, and the panic happens before
     the console is up, so the symptom is 0 bytes rather than a crash log. Any `KMA_NOFAIL`
     allocation on an early path deserves suspicion.
  3. **The criterion must be able to read out "which window this one wanted"**: the size in
     the panic line is the window size, and mapping `0x100000` back to `K60_TLMM_SIZE` took
     a single `grep`. All the earlier guesses (SMMU, RCG, qbt_boot, recipe drift) skipped
     that step.
  4. **The gate measures the "applied tree", not the repository**: the sizes live in
     `#define`s, which only a patched tree has; measuring the repository yields the previous
     round's budget (same shape as P-207), so `check-io-map-budget.py` explicitly skips
     rather than guessing when there is no `--tree`.

- **Related**: P-63 (same submap, first punched through by touch), P-207 (a gate may not
  judge stale artefacts), P-204 (a count is not semantics — here it is "the total" rather
  than "a single measurement").

- Check: `python3 scripts/check-io-map-budget.py --tree <applied xnu-work>`
  (registry `id = "P-219"`).

## P-220 — The gate's "fall back to the newest one" judged this tree with another branch's artefact

- **Scene** (2026-11-16, `check-rules.py` on main):
  ```
  ❌ P-165 构建应用了 232 个补丁，但 series 列了 227 个
     构建记录 /opt/k60/trees/k60build/bt-out-s1c/mondrian/ipados-16.6.1-20G81/mondrian/xnu-inputs.json
     说明序列里有补丁的上下文对不上；它和它之后的补丁都没有进树（P-165）。
  ```
  main's series is 227 entries (including 0621); the 232 belongs to the bt line's
  `feat/bt-research` series. That `xnu-inputs.json` belongs to another output tree of
  another branch and **has nothing to do with main**, yet the gate judged main by it and
  produced a completely plausible wrong conclusion.

- **Cause**: `stamp_path()` in `scripts/check-build-applied.py` originally meant "first find
  a stamp that matches the current series byte for byte; if none, `return stamps[0]` (the
  newest)". The second half existed to "make the caller report a real mismatch instead of
  staying silent" (P-189's fix), but there are two kinds of "mismatch" and it modelled only
  one:
  1. the same patch **names**, changed content → this tree's series was edited after the
     build, the build can no longer prove anything → **should go red**;
  2. the patch **names** all differ → this is another branch's or another board's series,
     nothing can be concluded about this tree from it → **should not judge**.
  The old code reported kind 2 as kind 1, so "no build on this machine represents the current
  branch" was translated into "your series has patches with mismatched context".

- **Fix**:
  - New `_stamp_names()` / `_same_series_names()`: only stamps whose **set of patch names is
    identical** are eligible to judge (same names, different bytes → genuine red; different
    names → move on to the next one).
  - The second pass of `stamp_path()` only picks among stamps where `_same_series_names()`
    is true; if there are none it returns `None`.
  - When `main()` gets `None` and the user did not pass `--stamp` explicitly, it prints "no
    build record on this machine has the same patch names as the current series, so no build
    can prove this tree came from the current patch set" and **skips**, instead of falling
    back to a log regex to judge another tree (that is P-207's shape: a gate may not judge
    stale or foreign artefacts).
  - `scripts/tests/test-check-build-applied.py` has 7 cases locking down this boundary, of
    which `test_another_branchs_stamp_is_not_graded` reproduces the scene above directly.

- **Four lessons**:
  1. **A fallback must know "who it fell back to"**. `stamps[0]` is an object, not "an older
     version of myself"; any fallback must also state under what conditions its result does
     not apply.
  2. **"Mismatch" must be classified before it is reported.** One word covers "this object
     changed" and "this is not this object", two completely different situations; the code
     must split them into two criteria.
  3. **A false red costs as much as a false green**: a false red sends people to fix a patch
     series that was never broken, or, as here, makes people believe main's 227-entry series
     is missing 5.
  4. **A test must reproduce the scene's own words**: this case asserts "`跳过 P-165` must
     appear and 232 must not", not "returns 0" — asserting only the exit code would let the
     log-regex path also return 0.
  5. **A gate's own tests must not inherit the gate's escape hatch**. `build-strict.sh:68`
     does `export K60_BUILD_IN_PROGRESS=1` (P-165's deadlock fix), and the registry inherits
     it when invoked from inside a build; so cases like
     `test_a_changed_patch_is_still_graded` that must judge red all downgrade to warnings and
     quietly turn green when run inside a build — that is what blocked `baseline-20261116a`
     on 2026-11-16 (running the same test by hand in a shell is fine, because the variable
     is not there). Fix: `setUp` explicitly does `self.gate.IN_PROGRESS = False` and
     `os.environ.pop("K60_BUILD_IN_PROGRESS", None)`, with `tearDown` restoring them.

- **Related**: P-189 (several output trees share the machine; taking the newest stamp caused
  false reds — this pitfall is its patch), P-207 (a gate may only judge physical evidence
  produced in this round), P-201/P-204/P-211 (the evidence-does-not-correspond-to-object
  family).

- Check: `python3 scripts/tests/test-check-build-applied.py`
  (registry `id = "P-220"`).

## P-221

**The upstream scanner did a per-file `git show` plus a dirty watermark, so every run redid the full comparison (900 s timeout → 7.4 s)**

### Symptom

The 2026-11-16 09:00 "upstream follow-up" scheduled job timed out three times in a row:
`pick-upstream.py --plan` returned rc=124 at 600 s, 900 s and 300 s (`--no-fetch`), with the
output file always 0 lines. It looked like a deadlock; it was actually **performance**: each
run compared about 5,080 files for each of three "new branches".

### Two independent defects, stacked

1. **`discover_branches()` treated bare `origin` as a branch**. It only filtered
   `endswith('/HEAD')`, so `refs/remotes/origin/` itself (short name `origin`) was kept, and
   the output of `git rev-parse origin` is the literal `origin/origin`, which was written
   into the seen watermark file. That string never equals any real sha, so **every run judged
   it a "new branch"**. Scene evidence: `/mnt/e/k60-work/.pick-upstream-seen.json` holds
   three dirty records `"UniXNU-mondrian/origin": "origin/origin"`,
   `"UniXNU/origin": "origin/origin"`, `"uefi-mondrian/origin": "origin/origin"`.
2. **Comparing a new branch was a per-file subprocess**. `collect()` first got the path list
   with `git ls-tree -r`, then ran `subprocess.run(['git', 'show', f'{ref}:{path}'])` for
   every path. Three branches × 5,080 files ≈ 15,000 process launches, each with the full git
   startup cost.

### Fix

- `discover_branches()`: `if not ref or ref == 'origin' or ref.endswith('/HEAD'): continue`.
- `load_seen()` actively drops historical dirty watermarks: `{k: v for k, v in raw.items()
  if not (k.endswith('/origin') or v == 'origin/origin')}`.
- New `blob_sha(data)` (`sha1(b'blob %d\0' % len(data) + data)`), `file_blob_sha(path)`,
  `tree_blobs(d, ref)` (one `git ls-tree -r -z`, parsed as
  `<mode> SP <type> SP <object> TAB <path>`, keeping only `fields[1] == b'blob'`, which
  automatically excludes gitlinks). Both the new-branch comparison and step 3 of `converge()`
  now compare **blob ids table against table**, fetching content with `git show` only when
  the ids really differ.
- A new branch must also pass the ancestry test `is_ancestor(d, ref, 'origin/main')` first:
  yibiya repeatedly pulls `fix/*` branches from main, so their tips are already in main's
  history; running "file convergence" on such a branch reports 5,000+ differences while the
  actually pickable content is zero.

### Four lessons

1. **"It does not finish" — suspect complexity first, not deadlock**. Three different timeout
   tiers all gave rc=124 and always 0 output lines; that shape looks both like a deadlock and
   like O(n) subprocesses. The way to tell them apart is to count "how many process launches
   per input".
2. **A literal ref name in a watermark/cursor is a bug**. A watermark must store an immutable
   object id (commit sha, blob id); storing a moving name like `origin/main` means never
   having a watermark at all. This is the same family as P-214 (both hashes called "series
   fingerprint" living in different namespaces): **the same name does not mean the same
   object**.
3. **Compare files by blob id, not by content**. `git ls-tree -r` already gives each file's
   blob sha; computing `sha1("blob <len>\0" + data)` locally matches it with zero subprocesses,
   and content is fetched only on confirmed difference.
4. **A "new branch"'s differences must be computed against its own baseline, not against our
   tree**. A never-seen branch naturally differs from our device repository by 5,077 files
   (those XNU headers we simply do not have); that number carries no information.

- **Related**: P-214 (same name, different namespace), P-207 (a gate may only judge physical
  evidence produced in this round), P-189 (several output trees share the machine), P-220
  (a fallback does not know who it fell back to).

- Check: `python3 scripts/tests/test-pick-upstream-scan.py`
  (registry `id = "P-221"`).

## P-222

**The global ledger treated another branch's successful boot as evidence for this tree, so main was told "the patch set changed"**

### Symptom

On 2026-11-16 the upstream follow-up ran review, commit and a real build on schedule
(`upstream-20261116a`, `kernel 092363c1…`, `boot.img 0226f0e6…`, `build-strict` rc=0
throughout), and afterwards `porting-gate.py --quick` still blocked:

```
❌ 1 项阻断 —— 禁止刷机
   [S] 补丁集变了 —— 必须显式确认
       上次成功 4305c6cc2821bcb7 (2026-11-16T08:59:35) != 现在 59d8037521a5b07b
```

`59d8037521a5b07b` is main's 227-entry series, which **had already booted on device at
2026-11-16 07:36** (`baseline-20261116a`, SpringBoard 132, 3,061 lines). The only reason it
was called "changed" is that at 08:59 the bluetooth line flew `bt-d6-iowin` with a 234-entry
series.

### Root cause

`/mnt/e/k60-work/ledger.jsonl` is a **cross-worktree global** ledger, and the `[S]` check
only looks for "the last record with `result == ok`" in it. Any line flying an image rewrites
"last success" with its own fingerprint, so:

- another branch flew → main's fingerprint "changed"
- main really changed → it may also be masked by the next other-branch flight

At the same time **every booted baseline in `docs/engineering/MAIN-BASELINE.toml` records
`series_sha256`**, but no tool anywhere in the tree reads that field
(`grep -rn series_sha256 scripts/*.py` has zero hits). That is, the fact "which patch set
actually booted" was recorded and nobody used it.

### Fix

`porting-gate.py` gains `booted_series()`: it parses the `state = "booted"` entries in
`MAIN-BASELINE.toml` and returns `series_sha256 -> (sha, image, console)`. The `[S]` verdict
becomes three-tiered:

1. Identical to the last successful record in the global ledger → PASS (original logic).
2. Identical to some **booted** baseline in the book → PASS, with the detail printing the
   `sha` + `image` + `console` paths, e.g.
   `b48613d baseline-20261116a E:/k60-work/evidence/usblog-20261116-073639/console.log`.
3. Neither matches → only then go through the `--force-new-series` / feature branch / main
   three tiers.

Entries with `state = "build-only"` can **never** vouch for a series: they have never been on
a device.

### Three lessons

1. **"Last success" must bind to the object, not to the machine**. The global ledger records
   "the last series that flew successfully on this machine", while the gate must answer "has
   **this** patch set flown successfully". Different questions; the former cannot answer the
   latter. Same family as P-220 (a fallback does not know who it fell back to).
2. **A recorded field nobody reads is a field that was never recorded**. `series_sha256` sat
   in `MAIN-BASELINE.toml` for several rounds while `grep -rn series_sha256 scripts/*.py`
   stayed at zero hits — an evidence field that is only ever written and never read does not
   exist as far as a gate is concerned. Adding a field means adding a read site at the same
   time.
3. **A fix must be verified in both directions**. Besides confirming "a booted series is
   accepted", this time I also deliberately synthesised a series that never booted (appending
   a fake patch name to series) to confirm it still says `❌ 补丁集变了 —— 必须显式确认`;
   otherwise it amounts to switching the whole `[S]` check off.

- **Related**: P-220 (falling back to another branch's artefact), P-214 (same name, different
  namespace), P-211 (`record-boot.py` measures the repository series instead of the image
  manifest), P-207 (a gate may only judge this round's physical evidence).

- Check: `python3 scripts/tests/test-porting-gate-book.py`
  (registry `id = "P-222"`).

## P-224

**Title: the build's frozen inputs counted the bytecode python writes itself**

`freeze()` in `scripts/build-strict.sh` is the only criterion for "was this tree touched
during this window": it hashes the same file list before and after the build, and if `cmp`
differs it does `die "frozen inputs changed during the build; this run is void"`. The list
used to be

```sh
find board.toml dts patches/xnu scripts -type f -print0
```

Under `scripts` there is `__pycache__/`. It is ignored by `.gitignore:40`, untracked by git,
and needs nobody to edit it — as soon as the build imports a repository script once, python
rewrites the corresponding `.pyc`. So **the build counted its own written files as "inputs
changed"**, and a build that changed nothing was declared void.

Measured (main `5db4414`, 2026-11-16 11:19): `freeze()`'s list had 522 entries, of which
**21 were `scripts/__pycache__/*.pyc`**. Touch `scripts/pong_paths.py` and import it once
more, and the list gains

```
b6e369d7c83f675168ac931fe7d3a89c39e4f3ab951ea656a26b58e165b3d296  scripts/__pycache__/pong_paths.cpython-312.pyc
```

— one entry, exactly the shape of a voiding.

Scene cost: the wifi line's `wifi-20261116c7` was declared void by itself at 2026-11-16
10:08, and `c05ebb7`'s commit message reads "wifi-20261116c7 was declared void for nine new
.pyc files". It added an exclusion rule on its own branch, but that rule never came back to
main, so this defect stayed alive on main.

Fix: exclude bytecode from the list.

```sh
find board.toml dts patches/xnu scripts -type f \
    ! -path '*/__pycache__/*' ! -name '*.pyc' -print0
```

After the fix 522 → 501 entries, 0 `__pycache__` entries; force python to rewrite a `.pyc`
again and the two lists `cmp` equal (`STABLE: a pyc rewrite no longer changes the frozen
hash`).

**Four lessons**

1. **The definition of "input" must exclude "the intermediate products I write myself".** The
   frozen list exists to catch people editing files, and `__pycache__` is a by-product of the
   build process. Counting a by-product as input lets the gate chase its own footprints. The
   criterion: for every file in the list, you must be able to answer "who edits it and why";
   anything answered "the build itself" gets excluded.
2. **A correct fix on a branch that never returns to main equals no fix.** The wifi line fixed
   this at 11-16 10:08; main was still broken at 11:19, and main is the tree everybody builds
   from. Anyone who edits `scripts/build-strict.sh` / `build-xnu-4k-baseline.sh` / any
   `check-*.py` on their own branch must write "this needs to go back to main" in the commit
   message, otherwise the fix only protects the person who wrote it.
3. **A voiding message must name the file.** This time `die` was preceded by `diff -u
   frozen-before.txt frozen-after.txt >&2`, so the wifi line saw at a glance it was `.pyc`;
   without that line the symptom is "the build succeeded but was declared void", which is
   most easily taken for a flake. Any "before/after comparison" gate must print the
   difference on failure (same family as P-190 "skip silently when the name is not
   recognised" and P-220 "fall back to another branch").
4. **"I edited this file" and "this file changed" are two different things, and neither
   `find -newer` nor a hash can tell them apart.** Separating them requires knowing "who has
   permission to change it": humans/tools edit source, the runtime only edits caches and
   logs. So the frozen list must be classified by **producer**, not by "is it under
   scripts/".

Related: P-165 (the build was blocked by itself mid-flight), P-202 (`sed` silently returns
empty when `.config` is missing), P-207 (a gate may not judge stale artefacts), P-220 (a gate
falling back to another branch's artefact).

## P-225

**Title: the board directory was guessed by mtime, and a wrong guess silently dropped the Metal plug-in and the battery archive**

`scripts/build-strict.sh` locates the board directory with
`M=$OUT/mondrian/ipados-16.6.1-20G81/mondrian`; hanging off `M` are `.config`,
`kernel/kernel.macho`, `payload/payload.img`, `device-tree/hardware.dtb`,
`tree/.cache/xnu-work/.../k60_metal_blob.s` — guess wrong once and all five are wrong.

The board directory name follows the **defconfig name**, not the board name: the default
config builds into `mondrian/`, the wifi config into `mondrian_wifi/`. Under one `OUT` both
can exist at once (`out-wifi` has both right now), so "which one is the one this build wants"
became a question every build had to answer. The wifi line added a `board_dir()` on its own
branch that picks the newest by `.config` mtime — right direction (it must not be hardcoded),
wrong criterion.

**Why mtime picks wrong**: `mondrian_wifi/.config` has only 100 lines and 70 `CONFIG_`, and
**neither `CONFIG_XNU_GPU_ADDON` nor `CONFIG_XNU_K60_PHYSICAL_BATTERY`** (those two keys are
only written in `configs/mondrian_defconfig:27` and `:78`). And the two reads later in
`build-strict.sh` are

```sh
GPU_ADDON=$(sed -n 's/^CONFIG_XNU_GPU_ADDON=y$/1/p' "$M/.config" | head -1)
BATTERY_ON=$(sed -n 's/^CONFIG_XNU_K60_PHYSICAL_BATTERY=y$/1/p' "$M/.config" | head -1)
```

Key absent ⇒ variable empty ⇒ neither `if` is entered ⇒ **the Metal plug-in and the battery
archive are silently skipped while the build still reports `BUILD OK`**. That is exactly
P-202's shape, with the trigger changed from "`.config` does not exist" to "`.config` exists
but it is not that one". Measured on both directories: `mondrian/.config` has `GPU=y BAT=y`,
`mondrian_wifi/.config` has neither key; `mondrian`'s kernel is 117,342,208 B,
`mondrian_wifi`'s is 66,002,944 B — a 51 MB difference, exactly the order of magnitude of the
Metal plug-in.

Fix: sort by "does this `.config` actually write those two keys", not by time. The config the
full defconfig produces has both keys, a truncated config has neither, so this is a
**discriminating** criterion; within the same tier, mtime breaks the tie. `K60_BOARD_DIR`
explicitly overrides with the highest priority; an override pointing at a non-existent
`.config` fails outright rather than being silently ignored. With several candidates it
states on stderr which one was chosen and why (naming `K60_BOARD_DIR`); when neither
candidate has those two keys it additionally warns "the Metal plug-in and the battery
archive will be silently skipped (P-202)".

Measured after the fix: `out-wifi` (two candidates) → picks `mondrian`;
`out-baseline`/`gates-out`/`lead-out` (single candidate) → unchanged;
`K60_BOARD_DIR=.../mondrian_wifi` → really returns it.

**Four lessons**

1. **The sort key must relate to the object being protected.** mtime only says "who wrote
   last", not "which is correct". What is being protected here is "are the two config options
   that change the kernel present", so the sort key should be those two keys themselves. The
   general criterion: **first ask "what error am I preventing", then pick a feature that
   discriminates that error**; mtime almost never qualifies.
2. **`sed -n 's/^KEY=y$/1/p'` merges "key missing" and "key is n" into the same empty value.**
   So "this feature is not in the config" and "I read the wrong file" cannot be distinguished
   in the code. Every place that reads config should be able to answer "is this key absent, or
   present but not y" — the former is a wrong file, the latter is a config decision. (Same
   family as P-190 "skip silently when the name is not recognised" and P-204 "using a count
   instead of semantics".)
3. **Moving a function into main when it is "right in direction but wrong in criterion" on a
   branch is more dangerous than not moving it.** Not moved, main hardcodes the path and is
   obviously wrong (die if not found); moved with the wrong criterion, main quietly picks the
   wrong one and produces images missing features. **Move the "why" when moving a fix, not
   the "code".**
4. **When there is more than one candidate, the selection must be visible.** Picking one
   silently is right (a build should not stop because an irrelevant directory exists), but it
   must print "chose X among N candidates, override with K60_BOARD_DIR". Otherwise the next
   person who sees the kernel is 51 MB smaller has to re-derive this whole chain.

Related: P-202 (`sed` silently returns empty when `.config` is missing), P-224 (frozen inputs
counting the build's own products), P-207 (a gate may not judge stale artefacts).

**A second place with the same criterion: `resolve_generated()` in `check-config-consistency.py`.**
It too picks one of several board directories, and its way of picking is `return found[0]` —
the first after sorting, not the one this build used. On `out-wifi`, `mondrian_wifi` sorts
first alphabetically, so hard-38 would judge the full defconfig with a truncated config. It
now shares the same criterion as `build-strict.sh` (prefer the one with both keys, break ties
by mtime within a tier, configs that cannot be read do not participate), guarded by the 8
cases in `scripts/tests/test-config-consistency-board-dir.py`; reverse verification: changing
`max(found, key=rank)` back to `found[0]` turns 2 of them red.

While there, two `P-187` references were cleared out of `scripts/check-config-consistency.py` —
that id never existed in `PITFALLS.md` (`git log --all -S "P-187"` has zero hits); it was a
dangling reference and the right one is P-225.

## P-228

**Title: the compatibility layer replays IRQs unconditionally, so "the handler was called" was taken for "a hardware interrupt arrived"**

In the diagnostic image of wifi c7 I added a
`Pong MHI: irq entered er_index=0 dev rp=... host rp=...` trace point at the entry of
`mhi_irq_handler()`. On device it appeared once, and on that basis I wrote in that section
"the MSI really was delivered from the GIC to our handler, only every read of `MsiStatus`
returns 0 (spurious interrupt)".

**That reading is wrong.** The layer at `drivers/PongWifi/ath11k/compat/` is not a real
interrupt: each round `lx_pump()` first runs `lx_plat->poll()`, then, when `g_irq_polling`
(default 1) is true, calls `lx_irq_raise_all()`, and the latter is

```c
/* /mnt/e/k60-work/impl/wifi/work/build/ath11k/lx_rt_pong.c:597 */
void lx_irq_raise_all(void) { for (int i = 0; i < 64; i++) if (g_irq[i].used) g_irq[i].pending = 1; }
```

**Unconditionally.** Every millisecond it marks all 64 registered IRQs pending, entirely
regardless of whether the hardware ever pulled an interrupt line. So one occurrence of
`irq entered` only proves "the scheduler ran this handler once"; it does not prove an MSI
arrived.

The real hardware criterion is a different trace point: `PongWifiPlatform.cpp:682`'s
`if (!irqSeen && __atomic_load_n(&msiArrivals, ...)) { ... log(6, "QCA6490 MSI delivered by GIC"); }`,
and `msiArrivals` is only incremented inside `irq()` when `dbi.r(MsiStatus)` reads non-zero.
For c7, `grep -ac "MSI delivered"` = **0** — that is the evidence that "the MSI did not
arrive", and it was valid all along. I first took an invalid criterion as a conclusion, then
turned around and used "irq entered appeared" to falsify a valid criterion; wrong in
direction twice.

**Four lessons**

1. **"It was called" is a software fact, not a hardware fact.** A criterion must point at a
   state change only the hardware can cause: a register reading back non-zero, DMA memory
   modified by the device, a pointer/counter incremented on the device side. A function being
   called, a log being printed, an interrupt number being handled — all three can be produced
   out of thin air by software in a simulated/compatibility layer.
2. **Before a criterion holds, check "who would make it hold".** The name
   `lx_irq_raise_all` literally contains `raise_all`; one `grep -rn "irq_raise_all"` shows its
   call sites and `g_irq_polling`'s default. That step is much cheaper than explaining
   afterwards "why the read-back is 0".
3. **A criterion must pass the "what would the opposite case look like" test.** If "the MSI
   arrived" and "the MSI did not arrive" produce the same observation, the criterion is
   invalid no matter how direct it looks. `irq entered` is exactly such a criterion.
4. **A wrong criterion contaminates downstream documents.** The wifi line had already written
   a version of the conclusion based on "the MSI arrived" and needs a dedicated rollback; and
   had I not self-checked within the section, this misjudgement would have travelled through
   §11 into main's wifi research document.

**Related**: P-204 (using a count instead of semantics), P-190 (skipping silently when the
name is not recognised), P-197 (a capability the firmware does not have cannot be written up
as done). All three are "a check is missing between observation and conclusion", and P-228 is
its form in hardware evidence.

## P-229

**Title: a gate's test asserts "this checkout happens to be the booted baseline", so any branch that changed a patch cannot build**

The build of the `adsp-20261116a` probe image stopped after
`unixnu: build: running the compliance registry` with

```
❌ P-222    FAILED (failures=1)
build-strict: FATAL: kernel build failed
```

`P-222`'s test is `scripts/tests/test-porting-gate-book.py`, one case of which originally read

```python
def test_the_current_series_is_proven_by_the_book(self):
    """The exact 2026-11-16 situation: main's series is in the book."""
    fp, count = self.gate['series_fingerprint']()
    table = self.gate['booted_series']()
    self.assertIn(fp, table,
                  'main series %s (%d patches) should match a booted baseline' % (fp, count))
```

`series_fingerprint()` measures **the current checkout tree**'s `patches/xnu/series`. The adsp
branch changed `0613-k60-adsp-pas.patch` to keep up with `main`, so the fingerprint became
`86a6e0ed295d56b6` (227 entries), while the only booted entry in `MAIN-BASELINE.toml` is
`59d8037521a5b07b` (`baseline-20261116a`). So the assertion failed, the registry failed, and
the build was rejected.

**This is not "the gate correctly rejecting a branch that never booted"; it is the gate's own
test being broken.** A branch that never booted indeed should be rejected, but that judgement
belongs to `porting-gate.py`'s `[S]` verdict — it is the gate proper, by design it prints
`❌ [S] 补丁集变了 —— 必须显式确认` for any patch set without booted backing, and
`build-strict.sh` explicitly lets it through with `K60_FORCE_NEW=1`. The test's job is to
prove the `booted_series()` function behaves correctly; once it writes "the identity of the
current checkout" into an assertion, its pass condition becomes "this checkout is main".

**Same shape as P-165**: there the registry inherited the escape hatch
`K60_BUILD_IN_PROGRESS=1` during the build; here a test inside the registry asserted the
branch identity. Same consequence both times — **the build is blocked by the very thing it is
supposed to protect**.

**Fix: split one test into three, the state-dependent one may skip.**

1. `test_the_current_series_is_proven_by_the_book`: if it is in the book, assert the `sha` is
   7–40 hex digits; if not, `self.skipTest('this checkout is a feature branch: series %s (%d patches) is '
   'not a booted baseline, which is the correct refusal (P-229)')`.
2. `test_a_feature_branch_series_is_not_an_error`: synthesise a book that does **not** contain
   the current fingerprint, then assert `booted_series()` returns a table, the current
   fingerprint is not in it, and no exception is raised. This one is independent of the
   checkout's identity.
3. `test_only_a_booted_entry_vouches_for_one_exact_series`: the same fingerprint is vouched
   for when `state = "booted"` and not vouched for when `state = "build-only"`, both times
   with a temporary book.

After the change, ran it on both trees `k60-gates` (main) and `k60-adsp-handoff` (feature
branch), each giving `Ran 7 tests ... OK` — which is exactly the self-check for "moving it to
any branch still holds".

**Four lessons**

1. **A test may not assert "the current environment is in a particular state".** The criterion
   is simple: move that test unchanged onto another branch and it must still hold. The part
   that only holds on this branch is "observation of the scene" and must either be written as
   a skip with a reason, or replaced with a synthetic fixture. The `fp` in
   `assertIn(fp, table)` is scene state.
2. **"The gate rejects" and "the gate's test fails" are two different rejections, and
   conflating them leaves a branch unable to start work.** The former is design (fail-closed
   working correctly), the latter is a regression (the test itself broke). Builds go through
   the former; verifying a function uses the latter.
3. **For any test invoked by the build flow, ask "what happens on a feature branch".** The
   build runs on branches and the registry runs inside the build. P-165 and P-229 are two
   ends of the same problem domain: **the gate's runtime environment and the object it judges
   must be separated** — the escape hatch must not leak into tests, and the branch identity
   must not leak into assertions.
4. **A synthetic fixture must supply every field.** In `booted_series()`,
   `fields.get('sha', '')` defaults to an empty string, while another test in the same file
   asserts `^[0-9a-f]{7,40}$`; a temporary book without `sha = "abc1234"` will "fix one and
   redden another". After changing a fixture, run the whole file, not just the case you
   changed.

**Related**: P-165 (the registry inherits the escape hatch during a build), P-222 (the global
ledger takes success elsewhere as evidence for this tree), P-207 (a gate may not judge stale
artefacts), P-218 (one variable at a time), P-194 (evidence does not correspond to the
object).

## P-230

**When a criterion lacks its input, substituting a "default" image is not allowed: three gates turned "you did not give it" into "judge yours with somebody else's"**

Measured 2026-11-16: running `python3 scripts/check-rules.py` directly on `k60-gates` main
(`cf550a93`) without setting `K60_DEVICE_INPUT` gives **five reds: iron-4 / iron-5 / hard-33 /
P-165 / P-166**; the same command with `K60_DEVICE_INPUT=/opt/k60/trees/gates-device` gives
**106 registered, 0 failures, 37 waivers, all green**. That is, those five reds had nothing to
do with the repository state, only with "the operator forgot to set the variable".

The root cause is three silent fallbacks, each written slightly differently but the same
shape:

- `scripts/sync-device-input.py:24-27` allows `DEV = DEV or '/opt/k60/trees/usb-cdc-mainline/device'` as soon as `--check` is passed, and the comment even says "registry's iron-5 has no caller image available" — that is precisely a defect written up as a design.
- `scripts/porting-gate.py:48` `DEV = (os.environ.get('K60_DEVICE_INPUT') or '/opt/...') + '/patches/xnu'`.
- `scripts/check-build-applied.py:29` `pathlib.Path(os.environ.get("K60_DEVICE_INPUT", "/opt/..."))`.

All three follow "input missing ⇒ swap in another input", so the object of the criterion
drifts from "the caller's image" to "the one somebody else synced last". This is the same
family as P-190 (a missing input turned into a trustworthy value), P-207 (the gate going off
to judge a stale artefact) and P-220 (falling back to another branch's stamp), except this
time the fallback lands on a **path** rather than an artefact or a timestamp.

Four lessons:

1. **A criterion's input must be named by the caller.** When it is missing, refuse and say how
   to supply it; substitution makes both "red" and "green" meaningless (this time it was a
   false red; if the shared image happened to match it would become a false green, which is
   worse).
2. **A "why a fallback is acceptable" comment must be read as a defect.** The comment letting
   `--check` use the shared directory froze a stopgap into a contract, and everyone afterwards
   understood it that way.
3. **When one variable produces five reds, suspect the variable first.** Five reds across four
   different criteria appearing at once is itself a signal that "the common input is wrong"; my
   first instinct was to go check the sync, which wasted a round.
4. **The fix must also delete the "default value" from the code**, otherwise the next person
   can still write `os.environ.get(..., '/opt/...')` back in. The new test
   `scripts/tests/test-device-input-must-be-named.py` greps the three scripts one by one,
   asserting both the refusal behaviour and that the shared default path no longer appears.

## P-231

**The payload's memory window is checked against `board.toml` and its own DTS, never against the RAM the phone reports: an arena that crosses a hole builds, passes the artefact check and boots into nothing**

Noticed 2026-11-20 while reading the iOS 27 payload geometry. `build payload`
refuses when `[payload].dram_size` disagrees with the DTS `/memory` node, and
`check-ios27-artifacts.py` re-reads the ADT afterwards, so the two numbers cannot
drift from each other — but neither compares them with the device tree the phone
actually passes. `arm_init.c:562-583` trusts `/chosen/dram-base` and
`/chosen/dram-size` as the DRAM iBoot reported and builds the physmap over all
of it, so an arena based at `0x800000000` — the base the iOS 16 line used for
its first window — crosses the 6 MiB gap at `0x837500000` and the 144 MiB gap at
`0x839700000`. It still builds; the boot dies after the loader, and no message
names memory.

What to do: run `python3 scripts/check-ios27-geometry.py` (the build script runs
it first). It holds the six `/memory` regions the phone reported on 2026-10-20,
checks the arena against the merged runs, the managed window against the arena,
the 2 MiB alignment and the pinned seed. A new reading of
`/proc/device-tree/memory` updates `BANKS` in the same commit as the DTS.
