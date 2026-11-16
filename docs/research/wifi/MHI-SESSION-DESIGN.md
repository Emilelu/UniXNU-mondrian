# Offline MHI session admission design

> **Proposal, not applied. c8 remains HOLD.** This document and its host model do
> not authorize a new image, a rebuild, a boot, or a change to the active MHI
> generator. The preserved c8 image/manifest are unchanged. Review date:
> 2026-11-16. Related audit: [MHI state machine](MHI-STATE-MACHINE.md).

## 0. What this proposal promises — and does not

| Property | Proposed host guarantee | Not established by this work |
|---|---|---|
| Admission | At most one host BHIE transport-function invocation per session generation | At most one physical transfer, or any completed physical transfer |
| Duplicate work | Direct submission and queued SBL converge on the same consumed token | Device EE ordering, real MSI delivery, or device progress |
| Failure | First error survives late EE, queued MISSION and transport return | Which current failure is the primary hardware cause |
| Lifetime | New admission requires old owner/transport quiescence and confirmed reset | A working board reset/abort protocol |
| Completion | Unknown/stale/mismatched abstract completion is rejected | A valid hardware freshness/correlation implementation |

**One admission is a host invocation upper bound, not a physical transaction
count.** One call may perform several register accesses, fail before ringing a
DB, be interrupted after ringing it, or leave device DMA active. A return of
zero is not proof of a fresh completion. A timeout does not prove no transfer
occurred. Neither the model's counters nor its synthetic completion object can
measure those physical outcomes.

The host-only [model](../../../scripts/proposals/wifi_mhi_session_model.py) is not
imported by the active driver or build. Its [tests](../../../scripts/tests/test-wifi-mhi-session-model.py)
exercise a hypothetical serialized owner and deliberately synthetic protocol
contract. Every qualification field defaults to false. These fields are review
obligations, not values to flip in order to obtain a green result.

## 1. Evidence that motivates a shared admission point

The reference is the generated c8 tree associated with manifest source

audit head **dd3154a716e89d0fbcc74058a3de705166fe1a29**; the retained exports below
are current-file consistency evidence, not an immutable build attestation.
They are not code from the different integration checkout.

| Exact exported source | Observation |
|---|---|
| [boot.c:622–644](<E:/k60-work/scratch/c8-scheduling-review/opt__k60__trees__k60build__wifi__ath11k-c8__mhi__boot.c#L622-L644>) | Direct path reads SBL, writes cached EE, calls AMSS and ignores its return |
| [boot.c:675–714](<E:/k60-work/scratch/c8-scheduling-review/opt__k60__trees__k60build__wifi__ath11k-c8__mhi__boot.c#L675-L714>) | AMSS calls BHIE, attempts FW_DL_ERR/wakeup on error, and returns ret |
| [pm.c:800–868](<E:/k60-work/scratch/c8-scheduling-review/opt__k60__trees__k60build__wifi__ath11k-c8__mhi__pm.c#L800-L868>) | State worker splices a local transition list; queued SBL can separately call AMSS; READY/MISSION return values are not propagated by this dispatcher |
| [runtime:206–210](<E:/k60-work/scratch/c8-scheduling-review/opt__k60__trees__k60build__wifi__ath11k-c8__lx_rt_pong.c#L206-L210>) and [runtime:402–418](<E:/k60-work/scratch/c8-scheduling-review/opt__k60__trees__k60build__wifi__ath11k-c8__lx_rt_pong.c#L402-L418>) | A running work item can be queued; running-owner exclusion prevents recursive dispatch of that same item, not its later execution |
| [runtime:350–364](<E:/k60-work/scratch/c8-scheduling-review/opt__k60__trees__k60build__wifi__ath11k-c8__lx_rt_pong.c#L350-L364>) | A wait can pump callbacks that enqueue more transition work |
| [pm.c:396–471](<E:/k60-work/scratch/c8-scheduling-review/opt__k60__trees__k60build__wifi__ath11k-c8__mhi__pm.c#L396-L471>) | MISSION publishes cached EE/wakeup before a later operation can fail |
| [pm.c:1293–1298](<E:/k60-work/scratch/c8-scheduling-review/opt__k60__trees__k60build__wifi__ath11k-c8__mhi__pm.c#L1293-L1298>) | Power-up waits for mission or fatal state but derives its return from mission EE alone |

The failure scenario is **sequential deferred duplication**, not proven nested
self-recursion: a BHIE wait pumps an SBL observation; original PBL/direct path
returns; its state owner later drains that queued SBL and can enter AMSS again.
Cached EE is an observation/cache and cannot be the exclusion primitive.

## 2. Session identity and ownership

A session is one power-up attempt with fixed DMA/image ownership, from creation
until shutdown has quiesced old work and device access. It is not a call to
AMSS, an EE value, an IRQ count, or a READY event. Reset and a new power-up create
a new monotonically increasing host generation. Never clear admission merely
because a timeout occurred, a duplicate PBL arrived, or cached EE changed.

One serialized owner alone mutates the transition state, PBL/READY latches,
image lifetime and admission. Producers attach generation to every observation
when it is captured and enqueue it. They must not relabel old observations with
the current generation when dequeued. In an eventual multiprocessor port the
queue, generation publication, failure mailbox and shutdown fence require a
reviewed lock/atomic design; the Python model is not that implementation.

The proposed ingress rules:

1. Validate the captured generation **before any side effect**, including
   modifying cached EE or creating devices.
2. If failed/stopping/closed, discard all progress events; if already succeeded,
   do not perform more startup work. Runtime recovery after success is a
   separate lifecycle, not implicit rearming.
3. Set PBL-started before firmware allocation/preparation can pump. Propagate
   errors from preparation and READY; do not allocate/download again on PBL.
4. Set READY-started before its callback. Repeated READY must not reset contexts,
   ring pointers or doorbells while a download is in progress or after failure.
5. Both a future approved direct path and a real queued SBL path call the same
   admission function. No caller bypasses it or treats a duplicate as success.
6. Consume the single token before calling BHIE. Never retry within that
   session on timeout, I/O error, exception, late SBL or unknown completion.

The model's early SBL-before-image case fails closed with -EPROTO. It does not
reproduce or qualify a warm attach path where a device is already running SBL.
The model's READY-before-PBL event alone does nothing; PBL's preparation performs
its one READY transition. Supporting other legitimate orderings requires an
explicit protocol decision, not weaker admission guards.

## 3. Proposed state and return contract

| State | Entry/action | Permitted progress |
|---|---|---|
| NEW | New generation, no token | PBL enters PREPARING once |
| PREPARING | PBL latch already set; allocate/copy image once | READY callback once; any error -> FAILED |
| READY | Image and READY callback valid | Qualified SBL/direct request consumes token |
| IN_FLIGHT | Token consumed; exactly one host invocation attempted | Error -> FAILED; qualified completion -> WAIT_MISSION |
| WAIT_MISSION | Transfer callback returned fresh qualified completion | Fresh current-generation MISSION + successful transition -> SUCCEEDED |
| SUCCEEDED | Startup success published after transition returns | No further startup submission |
| FAILED | First error retained; consumed token stays consumed | Only shutdown/reset lifecycle |
| STOPPING | Ingress fenced, cancellation/error published | Outside-owner quiescence -> CLOSED |
| CLOSED | No old work/transport/device access permitted | Confirmed reset -> new generation NEW |

The admission linearization point in a real implementation is a protected
UNUSED -> IN_FLIGHT transition, **before** entering the transport. A model token
is (generation, admission=1). No physical hardware meaning is assigned to it.
A C implementation must use a protected state transition, not a cached EE test
or an unsynchronized bool. Do not hold an IRQ spinlock across a sleeping/pumping
BHIE wait; serialize state with an owner and separately publish cancellation
and the first failure so the owner can observe them before publishing success.

The abstract predicate is:

~~~text
submit = current_generation && image_ready && ready_done
      && !terminal && admission_unused
      && protocol_qualified && completion_freshness_qualified
      && (!direct || direct_path_qualified)
~~~

Before a physical implementation, every true term needs an explicit source of
authority. In particular, register accessibility and protocol permission are
different predicates. A sampled SBL EE is not by itself the missing proof for
READY/POR direct BHIE, DMA visibility, or valid doorbells.

## 4. First error, late EE, and nested pumping

The first negative error is stored with phase and generation. Preparation,
READY, AMSS/BHIE and MISSION return values all reach this same result. The
outer power-up result reads first_error **before** any cached EE test. -EIO,
-ETIMEDOUT, -ENOMEM and cancellation must not silently become a second download
or a successful mission result. A MISSION transition's later failure must not
be masked by an earlier assignment of cached EE=AMSS.

During a nested transport wait, another callback may report an error or request
power-down even though the state worker itself cannot recursively execute.
A failure mailbox must become visible before a queued MISSION can publish
success. Simply queueing FAIL behind MISSION is not a sufficient real-world
ordering guarantee. The model's report_failure() is a same-thread, generation-
checked publication that demonstrates this ordering; it is not an ISR-safe or
multiprocessor API. A future implementation must specify the atomic first-error
publication and memory ordering. No ISR logging/allocation/wait is proposed.

After transport returns, check cancellation/first_error again **before**
accepting ret or inspecting completion. In the local spliced transition list,
all remaining items must also recheck terminal state. Clearing only the shared
queue is insufficient: the worker may already hold a local SBL or MISSION.
There is no retry/rearm after failure, even if a later EE looks encouraging.

## 5. Completion freshness is a blocking protocol question

[Audited BHIE code:210–255](<E:/k60-work/scratch/c8-scheduling-review/opt__k60__trees__k60build__wifi__ath11k-c8__mhi__boot.c#L210-L255>) generates a random nonzero sequence,
writes vector address/size and rings DB, then tests STATUS and XFER_COMPL. The
review did not find a sequence-match check or explicit stale-status clear in
that path. This is a risk to investigate, not a finding that a specific clear
write is required or safe. This proposal adds **no register-clear recipe**.

Before adapting the admission design to hardware, resolve:

- Does this BHIE version echo the doorbell sequence in status? What mask,
  latching rule and matching condition are documented for this device?
- How are completion/status state and DB sequence reset across failed attempts
  and power cycles? Is status sticky, W1C, read-only, or overwritten? What is
  the documented ordering, and what can be read without side effects?
- How does a completion demonstrably belong to the current transfer rather
  than a previous session, random sequence collision, or stale host read?
- What makes memory/doorbells visible to the device, and how are late DMA and
  old EE observations excluded before reusing the arena or starting a session?

The model's Completion(token, fresh=True, transfer_complete=True) is a
**synthetic contract supplied by a test**, not a decoder of BHIE status. Token
is not a hardware cookie. The hardware correlation is currently unknown; fresh
cannot be computed merely from ret==0, nonzero STATUS, XFER_COMPL, or a host
generation counter. The model rejects stale/unknown/mismatched completion, but
passing its test supplies none of the missing hardware semantics.

Similarly, a current-generation MISSION item needs protocol-qualified freshness
and a successful transition; reading cached EE is not sufficient. The model
requires a second synthetic mission_fresh input. This extra condition does not
claim a real method for disambiguating an old physical event.

## 6. Shutdown, reset and lifetime barriers

[Audited shutdown:1230–1262](<E:/k60-work/scratch/c8-scheduling-review/opt__k60__trees__k60build__wifi__ath11k-c8__mhi__pm.c#L1230-L1262>) queues a disable and flushes the worker;
[runtime:237–249](<E:/k60-work/scratch/c8-scheduling-review/opt__k60__trees__k60build__wifi__ath11k-c8__lx_rt_pong.c#L237-L249>) rejects flushing/cancel-sync of a running ancestor.
Therefore shutdown requested from a nested callback must not synchronously flush
its own running owner. Proposed ordering:

1. Publish stopping/cancellation against the old generation; retain an earlier
   causal error if one exists. Fence new progress ingress immediately.
2. Let the active BHIE call unwind, or use a separately proven abort mechanism.
   Do not free/reuse image/vector/context/DMA storage because a host timeout
   returned. Device ownership must actually have ended.
3. From a non-owner context, cancel/drain pending producers and work, wait for
   owner/transport exit, and verify device/DMA quiescence. Local-list items
   remain harmless because each tests stopping/error again.
4. Only after documented reset completion and old-event fencing may generation
   advance and the latches/token/error be initialized for a new session.
5. Reject old-generation SBL/READY/MISSION/PBL/POWER_DOWN and completion tokens.
   A host tag does not magically label an uncorrelated late device event; the
   hardware-side fence remains an unresolved prerequisite.

finish_power_down(quiesced=True) and new_session_after_reset(reset_confirmed=True)
are external assertions in tests, not implementations or evidence of those
barriers. They refuse to run while the owner/transport is active. A new session
may make one new host call; the previous session may never retry.

## 7. Host checks and integration boundary

~~~sh
python3 -B scripts/tests/test-wifi-mhi-session-model.py
~~~

The host suite covers:

- Direct plus queued SBL in the same local list and a list queued by a nested
  pump; nested owner dispatch is blocked but later queued work still runs.
- All 24 permutations of SBL/DIRECT/PBL/READY after preparation, duplicate
  preparation/READY callbacks, and cached EE being overwritten back to PBL.
- Preparation, READY, BHIE, nested callback and mission-transition failures;
  -EIO/-ETIMEDOUT/-ENOMEM propagation; late EE/MISSION cannot undo failure.
- Nested error publication followed by a successful transport return, plus
  cancellation during transport; neither can publish a completion/success.
- Unknown/stale/mismatched/incomplete completion and unqualified protocol,
  freshness or direct path; defaults issue zero host BHIE calls.
- Shutdown cannot self-flush/rearm; explicit quiescence+reset creates a new
  generation, rejects old progress/shutdown events, and rejects an old
  completion returned by a new transport call.

These are software safety tests under the stated single-owner and synthetic
contract assumptions, **not proof of hardware liveness or a corrected c8**.
They do not emulate PCIe/MSI/SMMU/cache behavior, assert physical transfer count,
resolve BHIE status semantics, or authorize enabling the direct READY/POR path.
No active generator, driver, series, status record, defconfig, image or manifest
is changed. A future implementation requires protocol evidence, an explicit
concurrency/lifecycle mapping and Lead approval before any build or boot.
