# Offline image-bound wrapper proposal

2026-11-16. **Proposal only; c8 remains HOLD.** Task-6 adds an executable host contract
for the proposed WiFi flash gate. It accepts only an explicitly nonbootable source
fixture and an in-process recorded fake. It cannot execute the device supervisor,
PowerShell, fastboot, a configurable command, or an injected runner callback.

The implementation is [wifi_image_bound_wrapper.py](../../../scripts/proposals/wifi_image_bound_wrapper.py).
The reproducible host matrix is [test-wifi-image-bound-wrapper.py](../../../scripts/tests/test-wifi-image-bound-wrapper.py).
This supplements the [flash-gate proposal](WIFI-FLASH-GATE-PROPOSAL.md) and its
[unapplied patch](../../../scripts/proposals/wifi-eight-step-gate.patch). It changes
neither the [active gate](../../../scripts/eight-step-gate.py) nor the
[active evidence record](../EIGHT-STEPS.toml). Root integration owns indexing and commits.

## Authoritative inputs and historical rejection

The actual [c8 build manifest](E:/k60-work/artifacts/wifi-20261116c8/build-manifest.json)
was read in full alongside [build-strict.sh](../../../scripts/build-strict.sh),
particularly its manifest emission at lines 386–454. The real schema uses flat
components.boot_img, components.payload, components.payload_kernel,
components.wifi_archive, components.wifi_archive_path,
repo.head, repo.dirty_files, frozen.file, frozen.list_sha256,
kernel_args_requested, payload_args and eight_step_items
keys. Paths and the eight_step_items = "all" string do not prove that WiFi was in
the flash gate or that a particular archive was linked into a particular kernel.

| Actual c8 field | Recorded identity |
|---|---|
| Source revision | dd3154a716e89d0fbcc74058a3de705166fe1a29 |
| Outer image SHA256 | f83ea7637b25cbfc87fd43189bb33973495f59c3d89edd7c727c8e00c7a0950c |
| Payload SHA256 | 2e01f473bc1e1c746850b5ba18e02b81aae041134ddccc038e1251fb16a9812e |
| Payload-kernel SHA256 | 6eeb5d682502e2a2edc183cb4296ccf33ae83042694cab8e4df3930bccbc150e |
| WiFi archive SHA256 | 1236996adc8cd8c030ed0f194ae58448db7b01498a2e704036d1e2e62c65d95c |
| Frozen list SHA256 | 76bee9ae31e129991b58fa20703f2cefa11d99da46186e2671aab6556efd7db9 |
| Requested args | pong_wifi=1 k60_wifi_rsc=2 |

The wrapper streamed the existing 201887744-byte image and matched its outer SHA256,
then returned raw **exit 1**, **runner_calls 0**, **gate null**:

~~~text
missing historical proposal_binding; no backfill allowed
~~~

That is an actual read-only c8 rejection, not a successful c8 provenance check.
c8 has no contemporaneously frozen observation/readback/source-compile-link binding
of this proposal's kind. No record was manufactured, no historical manifest was
modified, and no environment variable can supply those missing identities.

The current [verify-boot-image.py](../../../scripts/verify-boot-image.py) checks the
Android v4/gzip shim/firmware/FDT and payload/kernel hashes using its real image
extraction path. Its check(manifest_path, image_override=None) does not compare the
outer components.boot_img hash or exact payload_args readback. This proposal
adds those comparisons only for its fixture format. A usable Android boot-image
adapter remains absent; this proposal cannot authorize any existing real image.

## Checked contract

Inputs are explicit --manifest, --image, --review, --scope CLI arguments. The wrapper
never derives identity or scope from a tag, image basename hint, or a K60 environment
variable. The review JSON pins the exact manifest bytes, full source commit, gate
base/patch digests, trusted active-floor digest, observation identifier, and inert
supervisor plan. This review file is an offline test input, not a signature or
independent evidence that a build happened.

Validation precedes the fake boundary:

1. Hash the actual supplied image; compare it with the manifest's full SHA256.
   Require a full 40-character revision and repo.dirty_files = 0. Require an
   existing historical proposal_binding with the supported schema/format.
2. Verify the review pins and the manifest's frozen-list SHA256. Check every listed
   file against its SHA256; require distinct frozen roles for source, config, archive,
   compiler record, link record, steps, and observation. Reject relative traversal,
   absolute frozen paths and symlinks within those relative paths.
3. Require a checked observation identifier and explicit nonempty, unique, known
   scope. Compare the artifact's hardware set against the trusted checkout record:
   all current active items must exist and remain active. Hash that trusted record
   into the identity so omission/demotion cannot silently remove the active floor.
4. Parse the nonbootable fixture and read its payload, kernel bytes and exact args.
   Compare payload/kernel SHA256, manifest args and requested args. Duplicate or
   conflicting requested-argument keys are refused. Unknown formats are refused.
5. Require that the full source revision names a Git **commit**, not a tree object.
   Compare the frozen WiFi source bytes with that commit's blob. Require those exact
   bytes in the fixture kernel and the fixture archive's explicit member. Compare
   the archive hash/path, fixture compiler record, and fixture link record. Those
   records explicitly say source-fixture-no-compiler and source-fixture-no-linker.
6. Classify code membership independently from activation. Every supported fixture
   contains checked WiFi source and therefore requires explicit wifi scope, even
   with pong_wifi=0 or no activation flag. Exactly one pong_wifi=1 is enabled;
   exactly one pong_wifi=0 is disabled; missing/ambiguous values are unknown. Neither
   disabled nor unknown classification allows a display-only request to bypass WiFi.
7. Compare the observation's complete identity, activation, scope, success/failure
   predictions and references with the checked manifest/artifacts/steps. Invoke the
   real proposed gate in an ephemeral tree and retain its raw exit/stdout/stderr.
8. Revalidate bound inputs after the gate; only then append one inert plan to
   RecordedFakeRunner.calls. A failing validation or gate yields exit 1 and zero
   recorder calls; fake exit 7 is propagated as 7 after one recorded call.

JSON root lists/scalars and duplicate keys fail closed. The wrapper supports only
its exact recorder class; an arbitrary callable is refused. Git uses a fixed native
executable on Windows (C:/Program Files/Git/cmd/git.exe), scrubs ambient GIT_*
and K60/Python hints, disables global/system config and replacement objects, and never
uses a shell. Isolated Python is launched with -I -X utf8. The host installation,
repository and in-process Python runtime remain trusted; hostile code able to rewrite
those files or monkeypatch modules is outside this offline contract.

## Actual supervisor interface, represented without execution

The existing supervisor is [boot-and-capture.ps1](../../../scripts/boot-and-capture.ps1).
Its actual parameters are Image, Seconds, IdleSeconds, ReopenSeconds,
PanicGraceSeconds, WaitFastboot, OutDir, Fastboot, Serial. It checks capture readiness
before its boot command. This wrapper reads/hashes that script but never invokes it.

The manifest binding, review input and observation identity all include the following
fixed inert plan; the recorded fake output includes the same plan:

~~~json
{
  "script": "scripts/boot-and-capture.ps1",
  "script_sha256": "5205b5ba7f08bf989b216501e0a3c0dc6eec4d362153a64be34179026726eca4",
  "executable": false,
  "argv": [
    "-Image", "fixture-image.json", "-Seconds", "300",
    "-WaitFastboot", "0", "-OutDir", "fixture-evidence",
    "-Serial", "fixture-no-device"
  ]
}
~~~

The image is nonbootable, the serial deliberately names no device, and the output
path is merely a string. No output evidence directory is created by this plan. This
is parameter-shape and identity coverage, not a production supervisor integration.

## Exact source fixture and test inputs

The test creates temporary, disposable JSON/TOML fixtures; the test source and this
record are durable. It compiles no C/C++, generates no Android image, and performs no
boot or device probe. Exact source is read with Git from the BSD-2-Clause-Patent
[drivers/PongWifi/PongWifiPci.cpp](../../../drivers/PongWifi/PongWifiPci.cpp), pinned at
3cf1a08c8a7c60656c9682fb53d1c1b3bf74a185. The fixture kernel consists of the ASCII
prefix NONBOOTABLE SOURCE FIXTURE ONLY\n followed by that whole blob. The fixture
archive is canonical JSON containing base64 of that same whole blob and its digest.
The outer fixture is canonical JSON; canonical encoding is sorted keys, compact
separators, UTF-8. The supported outer/binding format is wifi-source-fixture-v1.

The positive uses -v applog=1 pong_wifi=1 k60_wifi_rsc=2, observation
wifi-pci-source-fixture, and explicit scope wifi. Its tag deliberately says
display-only-name-is-irrelevant and eight_step_items says display. The checked
source membership still selects WiFi. The fixture supplies synthetic passing evidence
for trusted active items and parked WiFi; it does not claim the real records passed.
The actual proposed gate prints the active floor:

~~~text
Flash scope: touch[active], gpu[active], storage[active], display[active], bootchain[active], battery[active], wifi[parked] (K60_FLASH_ITEMS + active floor)
~~~

| Positive fixture identity | SHA256 |
|---|---|
| Image | 4bac4070dbee20e7250dc514eac6b2f4b4ad2b7ebd2d8db99c6d35bcca0b9798 |
| Payload | 5160a1647334c9640a99c019fd81384b971ab748a49a2610452dc6bd615b9a26 |
| Fixture kernel | d30af4117bc98b61b276431f96eb6bbbb056c129b22d37a93c8930826f65c8fa |
| Source blob | 379394cd9c01c116c119898326f97945712365f3053dc3715917036ec76d7719 |
| Fixture archive | ca82d20095a44785830279f028fc92c0d6bdba1e782628a707aefe96a9b5c9dc |
| Config | 441485734148e35747fa4a41f1857e1eae455d6cec75709008cce890214ae6ea |
| No-compiler record | 517f1cafa98faaad59a4a2163ecf87d0e541c3ad3685c9ae9759689cf930f731 |
| No-linker record | f50dd251bb98819249b41c90a1104d440596fd3d53f39859ca7ece1a4e8aeb28 |
| Synthetic steps | d868dea8f2790839a4140b746a4eb5585cddee4d016964c67ba63fd04475dba5 |
| Fixture manifest | 228d0f5a2b988c67569ecb065396ed0e876e5c5a6a1d9927aa78e1a2c7e74cea |
| Active gate | 6b64c711a00148bfebb1fd1cb71dd4e1af61ab51450dc36a33edbea129b83ab8 |
| Unapplied gate patch | 6257bd3ece2c8574626328e8fb6ea6e276ee84d9d078b4ad2f3afb200a775acd |
| Trusted active evidence record | c1ed3d0bcc8324b00199c1a6406482f87283ac79ad408b545f48ced84e06b26a |

The identities depend on the checked gate/patch/active floor/supervisor versions.
A later reviewed edit requires new fixture identity output; these are this test run's
identifiers, not universal or reproducible native build claims.

## Verification and raw exits

Executed on the Windows host with the bundled Python:

~~~bash
'/c/Users/Emilelu/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/python/python.exe' -B scripts/tests/test-wifi-image-bound-wrapper.py --c8-manifest E:/k60-work/artifacts/wifi-20261116c8/build-manifest.json --c8-image E:/k60-work/artifacts/wifi-20261116c8/boot.img
~~~

Final result: **raw suite exit 0**, **70 cases**, **0 failures**, **active inputs
unchanged**. No background jobs or device commands were started. The matrix prints
one JSON result per case with the wrapper exit, gate exit if reached, and runner count.

| Cases | Raw result | Recorder calls |
|---|---|---|
| Positive fixture; disabled/unknown activation with checked WiFi scope; ambient spoof variables; positive CLI | wrapper/CLI 0; gate 0 | 1 per case, in process only |
| Deliberate fake exit propagation | wrapper 7; gate 0 | 1 |
| WiFi bytes + display scope; missing/duplicate/unknown scope; missing review/observation; malformed root/nested JSON; unknown format/schema (including boolean, float and string schema versions) | wrapper 1 | 0 |
| Wrong image/payload/kernel/archive hash; source/review/compile/link revision mismatch; nonexistent or tree revision; wrong args; rehashed archive lacking member; rehashed kernel lacking source | wrapper 1 | 0 |
| Missing and corrupt source/config/archive/compiler/link/steps/observation roles; missing frozen role; changed config; stale observation/activation; stale supervisor plan or gate digest | wrapper 1 | 0 |
| Omitted/demoted trusted active item | wrapper 1 | 0 |
| Failing active touch, failing parked WiFi verify, stale WiFi prediction | wrapper 1; actual proposed gate 1 | 0 |
| Actual c8 image + historical manifest | CLI 1; gate not reached | 0 |

The suite guards its in-process subprocess surface to fixed Git inspection/patching
and isolated Python gate/CLI runs. It hashes active gate/TOML/patch before and after.
Only disposable copies receive the unapplied patch. The unrelated README renderer
is stubbed, and its copied invocation uses the current isolated Python executable
instead of a PATH python3. Scope/evidence/prediction/active-floor logic is the real
proposed gate. The first trial exposed a Windows encoding issue because -I ignores
PYTHONIOENCODING; -X utf8 corrected it. Later trial corrections concerned the
expected commit-type error string and fixture setup's inherited Git environment;
the final matrix above passes. Review caught Python equality accepting JSON true and
1.0 as schema version 1; exact integer-type validation refuses those and string "1"
with zero recorder calls. Fixed source/commit reads pass only a per-call
`-c safe.directory=<exact resolved trusted ROOT>` to Git; no wildcard/global trust is
configured. The first independent WSL run preceded this fix and failed Git ownership.

## Limits and remaining integration debt

A hash equality and a self-authored review file cannot establish trustworthy build
history. A future real-image adapter needs contemporaneously frozen authoritative
config/source/compiler/object/archive/link evidence, verified real payload/kernel and
argument extraction, archive-member inclusion, and review of the exact observation
specification. Native compilation/link inclusion and absence of hidden WiFi code are
not proved here. Every admitted fixture is positively WiFi-source-bearing; the
wrapper refuses unsupported formats rather than claiming they are WiFi-free.

The artifact root and its ancestors, the checkout, fixed tool installations and the
process are trusted and quiescent. Relative frozen-path symlinks are refused, and all
bound inputs are checked again after the gate, but there is no filesystem lock or
atomic handoff to a device. Root/ancestor junction replacement and hostile concurrent
rewrites are not fully prevented. A deterministic disposable probe temporarily made
trusted evidence pass during the gate, then restored the failing evidence before the
second validation; the recorder still ran once. This demonstrates the quiescent-input
assumption rather than an atomic guarantee. The recorder has no external effects, so
these limits do not open a boot path. They must be addressed/reviewed before any production
adapter or supervisor execution is considered.

The real c8 binding is absent and remains absent. All active files, driver behavior,
porting state and session model remain unchanged. No C build, image build, boot,
flash, tag or commit was performed by this task.
