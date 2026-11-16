# Offline image-bound wrapper: advisory-only revalidation

2026-11-16. Status: **advisory-only, non-executable offline diagnostic**. This
document supersedes the pre-pivot admission proposal that previously occupied this
file. The old text is preserved as history in [Superseded claim](#superseded-claim-historical-not-current);
it is no longer the contract.

The wrapper is [`wifi_image_bound_wrapper.py`](../../../scripts/proposals/wifi_image_bound_wrapper.py).
Its default API and CLI never call a device runner, never execute the proposed
flash gate, and never produce a bootable/authorized/atomic/safe-to-flash
conclusion. A positive result means only that the bytes captured once by this
offline tool satisfy the listed consistency checks.

This supplements the [flash-gate proposal](WIFI-FLASH-GATE-PROPOSAL.md) and its
[unapplied patch](../../../scripts/proposals/wifi-eight-step-gate.patch). It
changes neither the [active gate](../../../scripts/eight-step-gate.py) nor the
session model, supervisor, build driver, board files or series.

## Superseded claim (historical, not current)

The pre-pivot wrapper was 20,250 bytes with SHA256
`2e4f6273c24c7aa4893c6e66981043e43b52f4ae90c51c0bc5006c95da6abb4e`.
Its checked contract contained this sequence:

> 8. Revalidate bound inputs after the gate; only then append one inert plan to
>    RecordedFakeRunner.calls. A failing validation or gate yields exit 1 and zero
>    recorder calls; fake exit 7 is propagated as 7 after one recorded call.

It treated the resulting gap as a caveat:

> A deterministic disposable probe temporarily made trusted evidence pass during
> the gate, then restored the failing evidence before the second validation; the
> recorder still ran once. This demonstrates the quiescent-input assumption rather
> than an atomic guarantee.

That claim is false for path-bound evidence and is **not** accepted by this
design. Byte-review reproduced the defect independently. The probe
`E:/k60-work/scratch/wifi-byte-binding-review/probe_known_defect_floor_restore.py`
monkeypatched the first read of the trusted DATA active floor to all-parked,
restored the real floor for the second validation, and observed the old wrapper
return `exit_code 0`, `gate_exit_code 0`, `runner_calls 1`,
`defect_reproduced true`. Re-reading a path cannot prove that a later consumer
will see the same bytes.

The current wrapper therefore has no gate execution and no fake acceptance in its
default path. The defect remains visible only through an explicit, clearly
labelled legacy diagnostic described below.

## Current contract

The single rule is: **every decision is computed from bytes captured once, and
the default path calls no runner.**

| API | Behaviour |
|---|---|
| `capture(path, label)` | Opens once, reads once, stores `data`, `sha256` and the path locator. No pre-hash and no path stat. |
| `capture_inputs(manifest_path, image_path, review_path=None)` | Resolves paths once and captures manifest first. Requires a historical `proposal_binding` object before it captures the review, frozen list or image. Then captures the review, frozen list, every listed frozen file, image, trusted GATE/PATCH/DATA/SUPERVISOR bytes, and the recorded Git source blob. |
| `evaluate(captured, scope)` | Recomputes each snapshot digest in memory, then performs every parse/hash/compare against captured bytes. Re-checks the captured frozen listing and hashes through `role_files`; does not read paths for a decision. |
| `advisory_from_inputs(captured, scope)` | Returns the advisory result and a post-decision `boundaries` report. Never calls a runner. |
| `advisory(manifest_path, image_path, review_path=None, scope=None)` | Default API: one capture, then `advisory_from_inputs`. Never calls a runner. |
| `execute(..., runner=None)` | Compatibility alias for `advisory`. Any non-`None` `runner` is refused before it can be called; only the isolated legacy probe accepts the exact in-process recorder. |
| `legacy_vulnerable_probe(..., window_open=None, during_gate=None, window_close=None)` | Explicit red-team reproduction of the old once-fake defect. Not a product path and not acceptance. |

Every default result carries:

```json
{
  "mode": "advisory-only",
  "advisory": true,
  "diagnostic": true,
  "checks": "passed",
  "advisory_exit_code": 0,
  "flash_authorized": false,
  "flash_authorization": "none",
  "device_runner_calls": 0,
  "device_paths_invoked": false
}
```

`advisory_exit_code 0` means "the captured inputs passed these checks". It is
not an authorization, not an admission decision, and not evidence that a device
can boot the image. `flash_authorized` is hard-coded false, and
`device_runner_calls` is hard-coded zero, including on every failure path.

The CLI has the same default. `main()` reads `--manifest`, `--image`,
optional `--review`, optional `--scope`, and optional `--legacy-diagnostic`.
Without that last flag it prints the advisory result and returns
`advisory_exit_code`: 0 for checks passed, 1 for refused. It never invokes a
gate, PowerShell, supervisor, fastboot or a fake runner.

## What is checked

All checks below read only the captured bytes:

- Manifest shape, schema-1 `proposal_binding`, declared format
  `wifi-source-fixture-v1`, review/observation/gate/patch/floor/supervisor pins,
  repository revision and clean-tree declaration.
- Image outer SHA256, boot-image format, exact payload arguments, payload hash,
  payload kernel hash, archive hash and archive membership of the recorded WiFi
  source.
- Frozen listing and every frozen role: config, `compile_commands.json`,
  link record, archive, observation, source and steps. A rehashed archive must
  still contain the source member; a rehashed kernel must still contain the
  actual WiFi source; compiler/linker records must match.
- Active floor and its trusted digest, explicit WiFi scope, observation identity
  and activation, source revision, and observation reference/prediction
  agreement including the observation identifier on both sides.
- Source blob equality against the fixed Git object named by the manifest
  revision. Invalid or missing Git objects are reported as an error, not
  backfilled from the working tree.

A refusal returns `advisory_exit_code 1`, a non-empty `error`, `checks
failed`, zero runner calls and no flash authorization.

## Boundaries and deterministic seams

The test suite models the three boundary questions byte-review asked for without
monkeypatching wrapper internals. Each is reproducible from the public capture
and advisory APIs.

| Boundary | Deterministic seam | Raw observation |
|---|---|---|
| Path replacement before a final consumer | Capture the fixture, replace the image path with different bytes, then call `advisory_from_inputs` on the held capture. | Decision stayed at captured image `4bac4070dbee20e7250dc514eac6b2f4b4ad2b7ebd2d8db99c6d35bcca0b9798`; `path_now_sha256` `b5975459b17b80fc734bee487f2b6c1ba8ae2ad7383a241a33a32b170742fc8d`; `same false`. |
| Same-inode overwrite after capture | Capture, then open the same inode `r+b` and overwrite its bytes. The test asserts the two path states share `st_ino`. | `same_inode true`; captured hash `4bac...b9798`; path-now `f5321e5425d4e5461f8163cede60767f547d0ed77045a410116daf176fe9ff1a`; `same false`. The captured decision did not change. |
| Downstream consumer reopens a path | After the decision, read the path again with `diagnostic_path_digest`. | Reopened SHA256 `cdacee9be7dc42f6231c873fa740643d33b6f95ecbc744c8c40dcfcac384b188`, different from the captured bytes. |
| Restored failing input | Capture while the fixture fails, repair the path, evaluate the held capture again. | `captured_bad_exit 1`, error `gate prediction observation mismatch`; `repaired_path_exit 0`. The held capture never resurrects the repaired bytes. |

`boundary_report` is explicit that these reads are diagnostic only:
`captured_once true`, `decision_reopened_path false`,
`post_capture_path_reads "diagnostic-only; never consulted by a check"`. It also
records three limits verbatim:

- `same_inode_limit`: an in-place write changes the path's current bytes but
  cannot change a captured snapshot or any advisory decision.
- `downstream_limit`: a final consumer that reopens a path is not bound to the
  captured bytes; this wrapper cannot prove or provide that handoff.
- `cross_process_limit`: supervisor/fastboot atomic handoff is outside this
  offline proof and is not claimed.

The wrapper does not close the downstream gap. It makes it visible and refuses
to claim it away. A future consumer must accept the validated bytes or an
equivalent handle, not a path.

## Legacy expected-defect regression

The old once-fake defect is not deleted or hidden. It is kept as an explicit,
clearly labelled regression that demonstrates the failure:

1. The fixture starts with an image whose bytes fail the stale-prediction check.
2. `window_open` writes the temporary-good image at the path.
3. The probe runs the historical before/after path validations with
   `capture_inputs` + `evaluate`; `during_gate` runs between them.
4. `window_close` restores the original failing image at the path.
5. The probe reaches one `RecordedFakeRunner.run` plan containing the **path**
   and the earlier validated hash, then records `runner_calls 1` and
   `path_matches_validated false`.

The raw expected-defect row is:

```json
{"case": "legacy-vulnerable probe: expected once-fake acceptance after temp-good window",
 "pass": true, "checks_exit": null, "device_runner_calls": 0,
 "flash_authorized": false, "error": null, "runner_calls": 1,
 "legacy_fake_accepted": true, "path_matches_validated": false,
 "detail": {"expected_defect": true}}
```

The test passes when the defect reproduces and fails if it stops reproducing.
"Expected defect" is not acceptance: the fake is in-process and test-only, its
plan has no external effect, `device_runner_calls` stays zero, and only the
explicit `--legacy-diagnostic` CLI or direct call can reach it. No production
caller may use `legacy_vulnerable_probe`.

The supported legacy invocation is:

```sh
python3 scripts/proposals/wifi_image_bound_wrapper.py --legacy-diagnostic \
  --manifest <fixture-manifest.json> --image <fixture-image.json> \
  --review <fixture-review.json> --scope wifi
```

It returns 0 only when the defect was reproduced; 1 means the regression no
longer demonstrates the old defect.

## Real c8 manifest rejection

The real c8 build manifest contains no historical `proposal_binding`. It is
rejected without backfilling one from the current environment or files:

| Field | Value |
|---|---|
| Manifest | `E:/k60-work/artifacts/wifi-20261116c8/build-manifest.json` |
| Image | `E:/k60-work/artifacts/wifi-20261116c8/boot.img` (201,887,744 bytes) |
| Build time | `2026-11-16T13:27:45+08:00` |
| Repository HEAD | `dd3154a716e89d0fbcc74058a3de705166fe1a29` |
| Branch / dirty | `feat/wifi-bringup` / 0 |
| Boot image SHA256 | `f83ea7637b25cbfc87fd43189bb33973495f59c3d89edd7c727c8e00c7a0950c` |
| Payload SHA256 | `2e01f473bc1e1c746850b5ba18e02b81aae041134ddccc038e1251fb16a9812e` |
| Payload kernel SHA256 | `6eeb5d682502e2a2edc183cb4296ccf33ae83042694cab8e4df3930bccbc150e` |
| WiFi archive SHA256 | `1236996adc8cd8c030ed0f194ae58448db7b01498a2e704036d1e2e62c65d95c` |
| Frozen list SHA256 | `76bee9ae31e129991b58fa20703f2cefa11d99da46186e2671aab6556efd7db9` |
| Eight-step items | all present |
| Proposal binding | absent (historical record was never produced) |

`capture_inputs` captures the manifest at
`scripts/proposals/wifi_image_bound_wrapper.py:230` and requires
`proposal_binding` at line 234, before it captures the review at line 236,
the frozen list at line 239, or the image at line 241. The 201,887,744-byte c8
image therefore cannot have been opened on this rejection path.

Raw result: CLI exit 1, `advisory_exit_code 1`, `error`
`"missing historical proposal_binding; no backfill allowed"`,
`device_runner_calls 0`, `flash_authorized false`, no gate or supervisor
call. No binding, manifest, image or artifact was modified.

## Test matrix and raw output

The suite is [`test-wifi-image-bound-wrapper.py`](../../../scripts/tests/test-wifi-image-bound-wrapper.py).
Run from the repository root:

```sh
'/c/Users/Emilelu/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/python/python.exe' \
  -B scripts/tests/test-wifi-image-bound-wrapper.py \
  --c8-manifest E:/k60-work/artifacts/wifi-20261116c8/build-manifest.json \
  --c8-image E:/k60-work/artifacts/wifi-20261116c8/boot.img
```

Raw exit: **0**. Raw final summary line:

```json
{"cases": 72, "failures": [], "diagnostics": 5, "active_inputs_unchanged": true,
 "fixed_subprocess_calls": 174,
 "source_revision": "3cf1a08c8a7c60656c9682fb53d1c1b3bf74a185",
 "source_path": "drivers/PongWifi/PongWifiPci.cpp"}
```

The 72 rows are: one primary positive fixture, three additional expected-pass
cases (disabled activation with checked WiFi scope, unknown activation with
checked WiFi scope, ambient-environment spoof), one `execute(runner=None)`
positive, 60 refusal cases with `checks_exit 1`, four boundary rows, one legacy
expected-defect row, one positive CLI row and one real-c8 rejection. Every row
reports `device_runner_calls 0` and `flash_authorized false`; the five
diagnostics are the four boundary rows plus the legacy row.

The guard counts 174 fixed Git inspection calls (`git cat-file` only). It does
not allow a proposed gate, PowerShell, supervisor, shell or device invocation.
Active GATE/DATA/PATCH/SUPERVISOR bytes are hashed before and after and reported
`active_inputs_unchanged true`. The full 74-line raw log is at
`E:/k60-work/scratch/wifi-bound-final.log`.

## Positive fixture identity

The passing fixture is an explicitly nonbootable offline JSON fixture. Its
identity is:

| Input | SHA256 / value |
|---|---|
| Image | `4bac4070dbee20e7250dc514eac6b2f4b4ad2b7ebd2d8db99c6d35bcca0b9798` |
| Source revision | `3cf1a08c8a7c60656c9682fb53d1c1b3bf74a185` |
| Source path | `drivers/PongWifi/PongWifiPci.cpp` |
| Payload arguments | `-v applog=1 pong_wifi=1 k60_wifi_rsc=2` |
| Requested kernel args | `["pong_wifi=1", "k60_wifi_rsc=2"]` |
| Payload | `5160a1647334c9640a99c019fd81384b971ab748a49a2610452dc6bd615b9a26` |
| Payload kernel | `d30af4117bc98b61b276431f96eb6bbbb056c129b22d37a93c8930826f65c8fa` |
| WiFi archive | `ca82d20095a44785830279f028fc92c0d6bdba1e782628a707aefe96a9b5c9dc` |
| Source | `379394cd9c01c116c119898326f97945712365f3053dc3715917036ec76d7719` |
| Config | `441485734148e35747fa4a41f1857e1eae455d6cec75709008cce890214ae6ea` |
| Compile commands | `517f1cafa98faaad59a4a2163ecf87d0e541c3ad3685c9ae9759689cf930f731` |
| Link record | `f50dd251bb98819249b41c90a1104d440596fd3d53f39859ca7ece1a4e8aeb28` |
| Steps | `d868dea8f2790839a4140b746a4eb5585cddee4d016964c67ba63fd04475dba5` |
| Gate base | `6b64c711a00148bfebb1fd1cb71dd4e1af61ab51450dc36a33edbea129b83ab8` |
| Gate patch | `6257bd3ece2c8574626328e8fb6ea6e276ee84d9d078b4ad2f3afb200a775acd` |
| Active floor | `c1ed3d0bcc8324b00199c1a6406482f87283ac79ad408b545f48ced84e06b26a` |
| Manifest | `228d0f5a2b988c67569ecb065396ed0e876e5c5a6a1d9927aa78e1a2c7e74cea` |
| Supervisor script | `5205b5ba7f08bf989b216501e0a3c0dc6eec4d362153a64be34179026726eca4` |

The supervisor fixture is non-executable and carries argv
`[-Image fixture-image.json, -Seconds 300, -WaitFastboot 0, -OutDir fixture-evidence, -Serial fixture-no-device]`.

## Limits and trust

- The artifact root and its ancestors, the checkout, the fixed Git installation
  and the process are assumed trusted and quiescent. Relative frozen-path
  symlinks are refused, but there is no filesystem lock, no atomic handoff, and
  no protection against a hostile process rewriting files while they are being
  captured.
- The capture protects decisions taken after it: path replacement, same-inode
  overwrite and restored failing bytes cannot change a held snapshot. It does
  not protect a downstream consumer that reopens the path. That handoff remains
  unimplemented and unclaimed.
- This is an offline consistency proof over declared JSON fixtures. It does not
  prove that the image boots, that the WiFi driver is loaded, that a device
  partition is safe, or that the archive was produced by the named compiler.
- The real c8 artifact is rejected because its historical binding is absent.
  No backfill was attempted and none is authorized.

## Stable hashes and handoff

| File | SHA256 |
|---|---|
| `scripts/proposals/wifi_image_bound_wrapper.py` | `d333402fbea562744ba71b27da16ba8372b5043c9854222a3902693a113ea753` |
| `scripts/tests/test-wifi-image-bound-wrapper.py` | `dfb48649d270e34ccd85108ffd516d301fc7d20e6e9e973a232dacfe4526049e` |

This document's own SHA256 is reported in the handoff message rather than
embedded here, because embedding it would change the hash.

No active gate, supervisor, driver, state machine, board file, session model or
series was edited. No C build, image build, boot, flash, tag or commit was
performed by this task.
