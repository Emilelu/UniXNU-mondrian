# SA: defconfig / generated configuration consistency

Date: 2026-11-12. Scope: one read-only checker, its offline tests, and this evidence file. Lead integrates the check; no registry, build, source configuration, generated configuration, commits, tags, sync, or device operation is part of this change.

## Sources inspected before implementation

- `E:\hackios\UniXNU-mondrian\AGENTS.md:20-37,47-50,100-104,161-173`: durable results belong in the repository, verification needs offline evidence, and the repository owns configuration truth. The direct task limits changes to the three new files and forbids commit/push/tag/build/sync, so those actions are intentionally absent.
- `E:\hackios\UniXNU-mondrian\README.md:5,40-49,133-135`, `E:\hackios\UniXNU-mondrian\docs\engineering\STATUS.md:6,44-57`, and `E:\hackios\UniXNU-mondrian\docs\engineering\EIGHT-STEP-SPEC.md:193-218`: current target, repository licence, and the local verification requirement were read.
- `E:\hackios\UniXNU\scripts\unixnu\config.py:82-107`: source grammar strips each line, handles `CONFIG_X=y/n`, quoted strings without escape decoding, decimal or lowercase-`0x` integers (including negative values), and `# CONFIG_X is not set`. Unrelated comments and blanks are ignored. Source parser stores the final assignment.
- `E:\hackios\UniXNU\scripts\unixnu\config.py:117,146-167`: schema-2 output is `OUT / board.name / os_profile / selected.removesuffix('_defconfig') / '.config'`.
- `E:\hackios\UniXNU\scripts\unixnu\cli.py:17-24,114-137`: `--out` selects the output root; only the explicit defconfig command writes the generated file, by concatenating profile fragments before the selected device defconfig.
- `E:\hackios\UniXNU-mondrian\board.toml:1-18`: schema 2, board `mondrian`, OS profile `ipados-16.6.1-20G81`, selected `mondrian_defconfig`. Together with the specified K60 output root this derives `/opt/k60/trees/k60build/out-baseline/mondrian/ipados-16.6.1-20G81/mondrian/.config`.
- `E:\hackios\UniXNU-mondrian\configs\mondrian_defconfig:42-49,72`: old seed UUID occurs in a comment; the explicit Data UUID is `1BCD69FF-24A5-48B1-94B6-8FE592B2F597`, and a disabled symbol uses the unset-comment form.
- `E:\hackios\UniXNU\profiles\arch\arm64\configs\common.config:1-8`: fragments enable `XNU_SOURCE_CORECRYPTO14`, `XNU_SOURCE_PTHREAD`, and `XNU_NATIVE_AES`; the current device defconfig explicitly disables them. This matters for the strict duplicate policy below.
- `E:\hackios\UniXNU-mondrian\scripts\sync-device-input.py:18-19,24-33`: the existing K60 defaults use the same device mirror and framework/output tree. This script was read, never run.

## Decisions before coding

Implement a standalone Python standard-library CLI (no UniXNU import or Context construction: Context can write state and resolve/fetch feeds). Explicit `--defconfig` and `--config` must work with arbitrary independent fixture paths and without board metadata. Defaults use this checkout's `configs/mondrian_defconfig` and the derived K60 generated-config location; a separate `--out` allows an alternate root with the same known K60 layout.

Compare every explicit defconfig symbol, including disabled symbols, by both semantic type and value. Decimal/hex numbers normalize to integers; booleans remain distinct from integers; quoted strings retain literal backslashes as in the source parser. Extra generated-only symbols are permitted because fragments add settings. Missing symbols, malformed input, empty input, unreadable/missing paths, and conflicting duplicates in either input fail closed. Identical or semantically equivalent duplicate values are permitted. No regeneration or automatic repair occurs.

Integration concern reported to Lead before coding: UniXNU currently concatenates fragments with legitimate device overrides. Strictly rejecting conflicting duplicates in the generated file therefore also rejects those fresh outputs. This is deliberate under the requested fail-closed duplicate rule; the checker must not silently treat ambiguity as success. Any provenance-aware relaxation is a separate integration decision, not an implicit last-assignment-wins shortcut.

## Commands and results

Initial read-only checks from `E:\hackios\UniXNU-mondrian`: the first `git status --porcelain` produced no output; `python3 --version` reported `Python 3.14.5`. An initial combined tool-discovery command exited 1 because optional `py` and `rg` commands were absent; a focused Python/status check exited 0. No build command was invoked.

Offline tests, run from `E:\hackios\UniXNU-mondrian`:

```text
python3 -B scripts\tests\test-config-consistency.py -v
...
Ran 18 tests in 3.557s
OK

# separate quiet rerun, capturing only the process status
python3 -B scripts\tests\test-config-consistency.py
unittest exit code: 0
```

The `-v` run wrote progress to stderr, which Windows PowerShell surfaces as `RemoteException`; a second run captured `$LASTEXITCODE` and confirmed the test process itself exits 0. The cases cover the stale Data UUID with a misleading live-UUID comment, missing generated config without creation, missing defconfig, `n` versus `# CONFIG_X is not set` equivalence in both directions, strings/empty strings/hex/decimal/negative numbers/comments, missing disabled symbols, conflicting duplicates in the defconfig, conflicting generated duplicates whose final value matches, conflicting generated-only symbols, semantically equivalent duplicates, bool/number/string type separation, literal backslashes, five malformed line forms in both inputs, empty/comment-only inputs, invalid UTF-8, a directory in place of the config, the K60 `--out` layout with a space in the root, and `--config`/`--out` mutual exclusion. Each invocation snapshots fixture bytes, mtimes, and file set to prove the checker writes nothing; fixtures are removed by `TemporaryDirectory`. `Get-ChildItem scripts\tests -Force` after the suite showed no leftover fixture directory.

CLI smoke check:

```text
python3 -B scripts\check-config-consistency.py --help
...
usage: check-config-consistency.py [-h] [--defconfig DEFCONFIG]
                                   [--config CONFIG | --out OUT]
...
help exit code: 0
```

The help text renders the POSIX default as `\opt\...` under Windows PowerShell because a Windows `Path` is used; the same default is `/opt/k60/...` when the checker runs under WSL/Linux, as intended. Explicit `--config` removes any dependence on that location.

Read-only live check under WSL, with no `defconfig` or build invocation:

```text
wsl.exe -d Ubuntu-24.04 -- stat --format=%s -- /opt/k60/trees/k60build/out-baseline/mondrian/ipados-16.6.1-20G81/mondrian/.config
3970

wsl.exe -d Ubuntu-24.04 -- python3 -B /mnt/e/hackios/UniXNU-mondrian/scripts/check-config-consistency.py
checker exit code: 1
FAIL: configuration consistency
  - .../.config:17: conflicting duplicate CONFIG_XNU_NATIVE_AES: line 6 has y; line 17 has n
  - .../.config:88: conflicting duplicate CONFIG_XNU_SOURCE_CORECRYPTO14: line 2 has y; line 88 has n
  - .../.config:90: conflicting duplicate CONFIG_XNU_SOURCE_PTHREAD: line 3 has y; line 90 has n
Inputs were not changed; regenerate explicitly after review.
```

The live file's Data UUID at line 75 is already `1BCD69FF-24A5-48B1-94B6-8FE592B2F597` (the seed UUID is absent), so the reported stale-UUID symptom was no longer present at observation time. The live file nevertheless fails the strict duplicate rule for the three legitimate fragment overrides documented above. The exit status is 1, not an assertion that the Data UUID is wrong.

`git status --porcelain` immediately after implementation listed only the three files below from this task, alongside `scripts/capture-k60-usblog.ps1` and `scripts/k60-capture-state.ps1`, which were already untracked before work and belong to the Lead's console repair. A later final status check showed the Lead's concurrent console work had also produced `M scripts/check-boot-procedure.py` and new `scripts/boot-and-capture.ps1`, `scripts/flash.sh`, and `scripts/tests/test-k60-capture-verdict.ps1`; this task neither created nor edited those files and did not inspect their contents after they appeared. No existing file, registry, build script, generated config, git state, or device was modified by this task. No sync, build, boot, or regeneration command ran. The pre-existing `scripts/__pycache__` entries predate this task and were not touched.

Artifacts:

- `E:\hackios\UniXNU-mondrian\scripts\check-config-consistency.py` — 6,708 bytes, 176 lines, SHA256 `EF59B1EF61315360C17390B733A59A6423D98E1687A1BB0CD34C915EBA27193A`.
- `E:\hackios\UniXNU-mondrian\scripts\tests\test-config-consistency.py` — 9,335 bytes, 204 lines, SHA256 `F72A8B4665233D3CFF0A893E40B6C27324DA412184311DBC62B2DCDE94EFE720`.

## Unresolved design concern

Strict generated-file duplicate rejection is correct for fail-closed ambiguity, but it conflicts with the generator's current normal output, which concatenates fragments then device overrides. A fresh explicit regeneration of `mondrian_defconfig` would still fail this checker on the three observed fragment overrides unless integration either changes generation to emit each symbol once or gives the checker provenance-aware allowance for documented fragment overrides. The latter cannot be inferred from a flattened `.config` alone. This checker deliberately does not choose last-assignment-wins, because that would hide exactly the class of silent drift the task is about.

A second, smaller integration note: the default output path is WSL/Linux-specific. Host-side Windows callers must pass `--config` (or run under WSL); they should not read the help-rendered `\opt\...` as a Windows absolute path.
