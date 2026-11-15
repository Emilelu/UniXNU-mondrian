# K60 ADSP GLINK handoff publisher

> As of 2026-11-15. Five injected owner stages and offline verification are implemented. No production carrier or hardware backend is installed; PAS1, GLINK, audio, battery and charging remain unverified. No kernel/image build or device operation was performed.

## Contract and board evidence

The external specification was read from E:/hackios/k60-charger/docs/research/battery/HANDOFF-PUBLISH-SPEC.md (SHA-256 b0848254d498003f05d7400aecf86bbad27c8034c874b9d269f8f5db90c1b220). Local consumer details are in [GLINK-HANDOFF.md](GLINK-HANDOFF.md); older missing-producer statements there are historical. Current APIs and callback obligations are in [PAS1-PROVIDER-CONTRACT.md](PAS1-PROVIDER-CONTRACT.md), with the boot timeline in [INTEGRATION-ORDER.md](INTEGRATION-ORDER.md).

The board record remains generated from captured FDT evidence: SMEM 0x80900000/0x200000, ADSP 0x9fd00000/0x3100000, IPCC 0xed18000/0x1000, mutex 0x1f4100c, remote PID2, client3/signal0, desc/TX/RX/SMP2P items 478/479/480/443, protocol1. The staged owner validates this tuple against the supplied configuration. The wire property is exactly 104 little-endian bytes, flags exactly 15 and a nonzero current-boot owner epoch.

## Implementation boundaries

| File | Responsibility |
|---|---|
| [K60AdspOwnerStages.c/.h](../../../drivers/PongPower/K60AdspOwnerStages.h) | Injected claim, stopped preparation, PAS load/authentication orchestration, existing-only build/self-parse and registry publication. Persistent session, bounded callback contract, terminal success and poisoned failure states. |
| [K60AdspOwner.c](../../../drivers/PongPower/K60AdspOwner.c) | Install-once platform seam and persistent production wrapper; serializes acquire/revalidate/abort/publish. Without an installed backend/reader, acquire clears the lease and returns -1000 before mapping. |
| [K60AdspMdt.c](../../../drivers/PongPower/K60AdspMdt.c) | Pure ELF32LE metadata/relocation validation; now invoked by claim and included in the battery archive recipe. It does not authenticate hardware. |
| [K60HandoffRuntime.cpp](../../../drivers/PongPower/K60HandoffRuntime.cpp) | Early startup arbitration, generated-config/RAM-overlap and registry preflight, OSData allocation, stages1–4 acquire/revalidate, stage5 atomic no-clobber commit. It no longer maps SMEM/TCSR or invokes the aggregate publisher. |
| [K60HandoffBuild.c](../../../drivers/PongPower/K60HandoffBuild.c) | Serializer now requires plan.required == 15 exactly; existing-only live build never allocates/clears rings. |
| [K60HandoffPublish.c](../../../drivers/PongPower/K60HandoffPublish.c) | Retained aggregate helper and real SMP2P validation, with separate 49-check host coverage. The staged runtime reuses ready/build/parser primitives instead of wrapping this aggregate under TCSR. |
| [K60AdspStartup.c](../../../drivers/PongPower/K60AdspStartup.c) | Permanent early/late startup claim; a failed enabled early attempt still excludes the unsafe late diagnostic. |
| [0619 patch](../../../patches/xnu/0619-k60-adsp-glink-handoff.patch) | Branch-only early default-off hook and three canonical mirrors. Existing series order and default arguments remain unchanged. |

The archive generator includes OwnerStages and MDT sources, and records owner_orchestration_implemented=true, platform_backend_installed=false and firmware_start_implemented=false. This is recipe/source integration, not an archive build or kernel-link result. No raw legacy PAS backend is silently installed.

## 调用点契约

Lead owns the final main call point and real PAS/backend integration. Keep 0619 on the experimental branch until that joint integration is accepted.

| Condition | Required responsibility and failure behavior |
|---|---|
| Ownership facts | Stopped preparation creates fresh host FIFOs; authenticated start, retained resources and exclusive GLINK/reset ownership establish public bits0–3. Their sum must be exactly 15. Internal completed bit1 means build/self-parse; public bit1 remains ResourcesHeld. |
| Epoch | Platform exclusive callback supplies a nonzero current-boot epoch bound to the cookie/configuration/geometry; build, self-parse and publish must agree. A numeric constant or stale epoch is not ownership proof. |
| TCSR/SMEM | Installed backend provides real lock/unlock. Stages own short sections for stopped allocation and discovery; the final section contains only build_existing+self-parse. Builder does not lock. Do not pre-hold the same non-reentrant mutex on stage entry. |
| Startup | All five stages complete or fail synchronously before IOBSD and k60_physical_battery_start(), hence before setconf/IOFindBSDRoot/vfs_mountroot. The carrier must be available before rootfs/Data. |
| Freshness | Allocate only while stopped; never create remote item443. Live build requires real ready/non-reset, matching restart, exact 32/4096/4096 items and the conservative zero descriptor policy. Dirty/live progress is refused rather than cleared. |
| Commit and lifetime | Preflight duplicate /chosen property, allocate OSData before any TCSR section, self-parse 104 bytes and atomically commit outside TCSR. Software ownership covers stages2–4 and stage5 commit; success retains resources/token indefinitely. |

The opt-in hook calls only when PE_parse_boot_argn succeeds and the unsigned result equals 1. It precedes startup claim, provider effects and mapping. This is a parsed-value contract: bare arguments and four-byte truncation are documented in the integration guide. Board defaults and image argument whitelist were not changed.

## Five stages and failure handling

1. k60_owner_claim validates configuration/complete ops, side-effect-free available, pinned image and MDT, exclusive epoch/cookie, resource lease and stopped/live evidence before map/short TCSR probe. Missing carrier/backend returns -1000 without SMEM/TCSR mapping. A null, unaligned or wrong-sized mapping is rejected before typed SMEM reads.
2. k60_owner_prepare_pas1 rechecks stopped/live; under short TCSR it finds the host0/ADSP2 partition, rejects existing host items and allocates fresh 478/479/480 at 32/4096/4096. It never allocates443. Partial allocator effects are not rolled back or retried as fresh state.
3. k60_owner_auth_and_start performs INIT_IMAGE(metadata once) → relocatable MEM_SETUP → COPY/BSS/CACHE for each segment → AUTH_AND_RESET. Only successful AUTH sets public Authenticated bit0. Reader buffers stay pinned through actual copying. The old copy→AUTH→INIT(payload)→MEM diagnostic order is not reused.
4. k60_owner_build_handoff requires exact public facts/required15 and current epoch, waits through backend ready, discovers partition/ready/items under short TCSR, unlocks for owner validation, then enters the final build_existing+self-parse section. It produces a lease only after all checks; required14, missing partition, bad parse or dirty descriptor cannot write /chosen.
5. k60_owner_publish checks registry root/existing property, live ownership, ready/restart and the same blob/epoch; runtime commits under runPropertyAction with TCSR released. Existing property returns -41, unavailable root/ready -43, other commit failure -48. Success is terminal Published.

Core stage logs use K60ADSP owner stage=%d rc=%d and run after TCSR unlock, as does the report observer. API reentry is nonblocking and refused; stale stages do not dismantle Built/Published ownership. Successful property commit and the terminal state transition share one API gate, so concurrent/reentrant abort cannot release a published owner.

Before commit, transactional failures routed through fail()/abort clear the lease. Invalid or missing-callback, busy and stale entry refusals intentionally preserve an existing Built lease/resources; they do not enter cleanup. If AUTH was attempted, shutdown AND independent stopped proof are required before releasing maps/reader/votes/exclusion once. Uncertain shutdown/stopped proof enters Poisoned and retains recovery state/exclusion without retry. Published has no release path. The future platform must uphold pinned ownership across every unlocked interval; TCSR does not stop the DSP or prevent future crashes.

## Offline verification (2026-11-15)

[run-k60-handoff-host.sh](../../../scripts/tests/run-k60-handoff-host.sh) records E:/k60-work/artifacts/adsp-owner-stages-20261115/final-host/host-tests.log. The final run passes 77 named staged scenarios: claim17, prepare11, auth12, build15, publish22. Tests inject fake carrier/PAS/resources/registry around real MDT/SMEM allocator/build-existing/parser and the persistent wrapper; fake callbacks assert they are outside final TCSR. They include AUTH failure/Poisoned cleanup, required14, missing partition, current epoch/token, config lifetime, mapping alignment, duplicate/root/commit failures, reentry/stale entries and no release after success.

The same run passes publisher49, builder10, absent-owner, early/late startup in separate processes, MDT16 methods (including captured firmware), notification21 and battery-units27. The exact patched IOKitBSDInit body passes 14 parser-stub dispatch cases across battery macro0/1; disabled cases have zero downstream SMEM/TCSR/PAS/claim spies, enabled cases are non-vacuous and preserve publisher→IOBSD→battery order on failure. Five scoped predecessor-fixture sections apply with fuzz0 and three canonical mirrors match. These are neither complete series replay nor raw boot-string or hardware tracer tests.

Runtime C++ and owner C sources pass arm64 Apple kernel SDK syntax checks; the two existing framework private-header warnings in the runtime check remain. E:/k60-work/artifacts/adsp-owner-stages-20261115/owner-sdk-syntax.log records owner C syntax. No object archive, kernel or image was built or linked. Read-only core review resolved persistent-config, commit/abort serialization and SMEM alignment findings; no concrete blocker remained in that reviewed core.

## Firmware preparation and production backend gaps

Captured E:/k60-work/firmware/adsp/adsp.mdt is 5404 bytes, SHA-256 1238098817957c4d3cd0995fd413332751ac8082ea315e6e1d9bdb247cadc694: 26 program headers, 24 loads, metadata prefix884+hash4520, pure-BSS header24 with no .b24 needed. All load segments are relocatable; linked [0x86300000,0x89400000) maps into board [0x9fd00000,0xa2e00000), span0x3100000. Different linked/board bases alone are not a fixed-address conflict.

MDT parser inputs and piece buffers must be immutable and pinned through load; metadata/plan are writable and disjoint from inputs/one another. Callback load must actually write the relocated ADSP physical memory and synchronize caches before AUTH. Pure parser success or host callback traces do not prove this on hardware. The existing raw SMC wrapper lacks the audited serialization/resume/busy/coherence/resource/stopped backend contract and is not selected automatically.

Lead-owned early carrier/reader and audited SCM, resource/reset/exclusive, real TCSR/mapping and ready backends remain to be installed before the first runtime attempt. No RSC/SPMI vote guessing was added. Missing backend still returns -1000 before mapping, mapped by runtime to -42; a missing property leaves the one-shot consumer blocked at -4. Success requires independent PAS1/retained-resource/SMP2P/104-byte property/consumer adoption and real GLINK transaction evidence.

## Bounded image reader (Lead reply, 2026-11-15)

Lead selected embedded carrier B and retains generator/build-strict/assembly ownership. This branch adds [K60AdspImageReader.c/.h](../../../drivers/PongPower/K60AdspImageReader.h): explicit validated K60A blob source, linked-symbol entry, exact named-copy callback and immutable owner-image adapter; DT/FAT fallback accepts only an explicitly supplied, already mapped pinned image, checks BPB before k60_fat_open, bounds directory/FAT chains and rejects fragmented borrowed files. No physical mapping or silent source fallback is added. Reader -5/-6/-7 mean exact-size/partial failure, missing source/part, and corrupt/bounds, respectively; they are not raw MDT/SMEM codes.

Stage3 auth_and_start now uses k60_adsp_image_segment for bounded contained or piece reborrow. It still calls INIT/MEM/load/BSS/cache/AUTH in order, zero-only b24 never asks for a file, and stage4's final TCSR window is unchanged. The named K60AdspRead ABI is preserved with a typedef guard. The archive recipe includes reader code, while K60Fat remains a kernel symbol from0613; host tests link the real implementation explicitly. No backend install, default parameter, blob generator/link switch or series order changed.

The Lead-facing K60A proposal and immutable-lifetime/error contract are in [PAS1-PROVIDER-CARRIER.md](PAS1-PROVIDER-CARRIER.md#implemented-reader-boundary). Captured host tests [test-k60-adsp-reader.c](../../../scripts/tests/test-k60-adsp-reader.c) construct blob/FAT fixtures only in memory; real captured MDT/bNN remain input data. Copy23,494,284 plus BSS25,925,684 equals49,419,968 bytes written, not the51,380,224-byte mapped span (1,960,256 intersegment gap bytes are untouched). These checks do not prove carrier physical availability, PAS authentication, cache effects or GLINK.

Final reader run: both the absent-weak-symbol and -DK60_ADSP_TEST_LINKED positive-link variants pass 19 scenario groups each using 26 captured entries. The unchanged five owner counts remain claim17/prepare11/auth12/build15/publish22=77; publisher49, builder10, MDT16, notification21, battery27, dispatch14 and the five-section/three-mirror integration fixture also pass. E:/k60-work/artifacts/adsp-reader-20261115/final/host-tests.log has SHA-256 9845afd556d9004de0709f2f393f7c9c4e0ad6d4160031d5bd65805af844547e. Reader/stage C arm64 SDK syntax and runtime C++ syntax pass with existing private-header warnings; the C syntax log SHA-256 is 79a0ff146352e4074a5b3e5a8fb4b1586b9e07bbd3d8a18f5831d505950efdb8. These are syntax/host tests, not an archive build, full kernel link or image.

Reader checkpoint scoped gates pass docs192, README table consistency, ownership, secrets957, six battery research checks and whitespace; changed-patch parsing reports no changed patch. The unchanged porting checker reports 54 errors both with the pre-reader HEAD record/tracked paths and with this candidate, with no introduced or resolved error. See final/porting.log and final/porting-baseline.log in the reader evidence directory. Those existing input-revision/unclaimed-path failures remain open: this is not an all-green release gate. Source and docs are kept separate from carrier implementation, and hardware verification remains false.

## Notification qualification

The paired TX/RX qualifier remains unchanged: vendor charger evidence shows state/debug-board/block-TX paths can return zero without transmitting; subscription TX is owner0x800a/type2/op4 with16 zero payload bytes, total28. A 24-byte property request or16-byte opcode7 notification is not an ACK. Malformed/ambiguous/orphan captures are refused; absent real qualifying capture leaves reply type/length0/0, subscription disabled and current sign unqualified. Owner host tests do not qualify wire traffic.

## Numbering, historical checkpoints and release boundary

Thermal's archived thermal-20261115a retains0617, springboard0618, this handoff0619 at existing series line225. The prior rename preserved patch SHA b7eb981351f828023af827a649dc77a93146ac26ac14117de43e9482fcf3508b. This stage change tightens builder required to15 in canonical source and mirror; current patch SHA is 2ba6d02d861a6800e76e5595f525ae01c849f8a1d9d2f6b313af90c3485d6437. It does not import or renumber other lines.

The branch is isolated at E:/hackios/k60-adsp-handoff, owner adsp-handoff-agent. Prior private DEV/OUT at /opt/k60/trees/adsp-handoff-20261114t2145-device and /opt/k60/trees/adsp-handoff-20261114t2145-out were configured with canonical feeds/lock and SDK-only seed. Their earlier730-file mirror result is historical, not a claim that today's new stage files were synced or built. No stale kernel/applied stamp/DTB/image was copied.

Historical registry evidence after rebase onto97258d2 is E:/k60-work/artifacts/adsp-handoff-contract-97258d2-20261115t0003/registry.log:78 rules,31 commands,0 failures,37 existing waivers. P190 configured-not-built and P194 no-branch-manifest comparisons skipped; P165/166 unrelated-log skips were not provenance. That checkpoint is not a full registry result for this new stage change. Current scoped source/docs checks are recorded separately; assertions/waivers are unchanged.

Source checkpoint 8da7b1e427a59b3436bfd0fdd441b9907e540c4a passes the scoped checks: docs192, README table consistency, tree ownership, secrets953, the six battery research checks and changed-patch syntax parsing. The unchanged porting checker still fails: a diagnostic using the pre-change 82bf9e9cb49f532310fb264edac061b8853ae42a record/tracked paths reports 55 existing errors; the candidate reports 54, with no introduced error and the existing host-runner coverage error resolved. The six new stage-test files are now claimed by the power area. Remaining failures include the existing input evidence revision and unrelated unclaimed paths; see E:/k60-work/artifacts/adsp-owner-stages-20261115/porting-baseline.log and porting-current.log. These failures remain open; this is a branch source checkpoint, not an all-green release gate. Final host log SHA-256 is 0052eeaab8919c426d6e5ef42826102c340c205fbbd4c583925af01dd766de8f.

Eight-step verify/local_verified/device remain false pending full clean-series compile/link, artifact validation and separately authorized hardware proof. No kernel/image build, boot, device or serial operation was performed in this task.
