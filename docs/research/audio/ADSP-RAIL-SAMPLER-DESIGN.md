# ADSP RSC Rail Sampler: Repair Design

**Status:** repair design plus an unintegrated candidate observation core; production unchanged. Canonical host compliance assertions run and fail (58/75 cases); defect reproduction passes (75/75). The candidate core passes its own 37-case host contract check but is not linked into production and is not evidence of compliance. No repair implementation in production or hardware validation.
**Scope:** canonical read-only sampler entry and observation contract. This does not authorize production C changes, patches, callsite changes, PAS/SCM/handoff enablement, boot-argument defaults, or porting-status changes.

## Decision and evidence boundary

The current sampler is not a rail-only bring-up candidate and cannot grant power or SCM authority. Production behavior remains unchanged; the board resource callback remains fail-closed (K60BoardUnsupported, -63), HR-01 remains in force, and no build or device run is authorized by this design. Repair implementation is pending separate Lead review.

The source audit is [ADSP-RAIL-SAMPLER-AUDIT.md](ADSP-RAIL-SAMPLER-AUDIT.md). Its fixed source matrix is:

| Pin | Source and design use | Boundary |
| --- | --- | --- |
| X | [Xiaomi K60 Android S rpmh-rsc.c, 989b27aa8391a2ede9b067b53877c4c3343955fe](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/blob/989b27aa8391a2ede9b067b53877c4c3343955fe/drivers/soc/qcom/rpmh-rsc.c): downstream five-TCS-type model, caps, v2 geometry and request semantics. | Vendor reference semantics, not this XNU boot's live RSC state. |
| XT | [Xiaomi TCS bindings](https://github.com/MiCode/Xiaomi_Kernel_OpenSource/blob/989b27aa8391a2ede9b067b53877c4c3343955fe/include/dt-bindings/soc/qcom%2Crpmh-rsc.h#L9-L13) and internal count: sleep=0, wake=1, active=2, control=3, fast=4. | TCS_TYPE_NR=5 is a type count, not a slot count. |
| U | [Linux rpmh-rsc.c, 458c6079fc1d41d564c37679c8ace02cd83ee817](https://github.com/gregkh/linux/blob/458c6079fc1d41d564c37679c8ace02cd83ee817/drivers/soc/qcom/rpmh-rsc.c#L157-L204): v2/v3 layout cross-check. | Does not authorize another SoC's window or additional mapped range. |
| A | [Linux v6.1 rpmhpd.c](https://github.com/torvalds/linux/blob/v6.1/drivers/soc/qcom/rpmhpd.c#L450-L488): command DATA is a corner; synchronous ACK is requested only when increasing state; active/sleep/wake votes are aggregated separately. | A command record is not the aggregate vote or proof of effective power. |
| D | [Linux v6.1 cmd-db.c](https://github.com/torvalds/linux/blob/v6.1/drivers/soc/qcom/cmd-db.c#L177-L195): resource-name lookup returns an address. | Not a vote, aggregate, or PMIC state query. |
| B | Audit's pinned board DTS evidence: RSC windows drv-0..3=0x17a00000..0x17a30000, each 0x10000; logical drv-id=2; qcom,tcs-offset=0xd00; DT group tuple <2 3 0 2 1 2 3 0 4 1>. | Configuration evidence only. Version, caps, count, and records used together must come from the same attempt. |

Any separately authorized sampler implementation is restricted to the audited DRV-2 window at 0x17a20000, length 0x10000, and cmd-db at 0x80860000, length 0x20000, subject to HR-01 and explicit opt-in. This is not permission to scan every theoretical slot or command. Successful mapping is not proof that every address in the mapping is safe to read.

## 可证明的访问域（只读来源核对结果）

下表把“布局有依据”和“允许读取”分开。默认拒绝；没有依据的地址保持未知，不尝试实机探测。

| 读取对象 | 地址 / 宽度 | 依据 | 当前结论 |
| --- | --- | --- | --- |
| 映射 DRV-2 窗口 | 0x17a20000, 0x10000 | HARD-RULES.md:47 | 仅映射；映射不等于允许读 |
| DRV-2 w[0]（版本/布局） | 0x17a20000 + 0, u32 | HARD-RULES.md:48；K60PmicRail.c:375-376 | 唯一被规则点名的 RSC 读；仍受 HR-01 四条件约束 |
| caps 字 | 0x17a2000c, u32 | DESIGN:37,43（提案）；现行 canonical 采样器并不读它 | 设计意图，不是批文 |
| TCS / command 字段 | 0xd00 + slot*0x2a0 + cmd*stride + 表内偏移, u32 | Xiaomi rpmh-rsc.c:70-83；本文件字段表 | 只证明几何；**没有任何 per-slot/per-command 读取许可**，必须保持 unknown |
| cmd-db 区域 | 0x80860000, 0x20000 | HARD-RULES.md:75；DT reserved-memory | 区域级“普通内存、可读命令 ID” |
| cmd-db header/slave/entry/aux | 144 字节头；8×16 字节 slave；24 字节 entry；aux 由头内偏移派生 | K60PmicRail.c:44-50, 61-116 | 格式几何；entry/aux 地址依赖头内容，静态 span 只能覆盖有界 reviewed block |
| AOP 聚合 / ARC / PMIC 生效 / handoff 保持 | 无 | 本文件:159-170 | 未知；不得用请求记录推断 |

两个未闭合项必须由 Lead 裁决，候选核心与宿主夹具都不能代替：

1. **HR-01 自相矛盾**：HARD-RULES.md:47-48 允许在四条件下映射 DRV-2 并读 w[0]；
   同文件:63-69 的“禁止范围（未变）”仍把 0x17a20000 列为禁止并说映射本身可能挂起。
   在裁决前，“可读 w[0]”只能作为设计输入，不能当作已授权。
2. **TCS 槽号 3 还是 4 未定**：POWER-RPMH-LDOC2.md:33 说 TCS3，
   REFERENCE-INDEX.md:195 说 slot 4，K60PmicRail.c:171-172 记录两者冲突。
   槽号未定 ⇒ 连 TCS_STATUS 的确切地址都不唯一。

因此候选 observation core 的 permit 一律是**显式测试输入**：合成 span 只验证契约，
不为真实启动补许可；真实 LCX/LMX 请求字段在当前证据下应报 PERMISSION_DENIED / unknown。
历史 49 次启动日志、caps=0x800c8104 和不同 boot 的 tcs4_idle 都不能拼接成本次许可。

## Version-pinned field map

Version selection must use the version word read in this same attempt and an explicit supported-version switch. Historical 0x20700 is a version word for 2.7, not logical driver id 2. Record both independently. The audit cross-checks v2.7 and v3.0; unknown versions fail closed rather than falling through a >=3 rule. Existing k60_rsc_layout() selects v3 for any extracted version >=3 and otherwise v2; that is not the required supported-version policy.

| Field | v2 offset | v3 offset | Interpretation and sampling rule |
| --- | ---: | ---: | --- |
| TCS stride | 0x2a0 (672 bytes) | 0x2a0 (672 bytes) | TCS base is tcs_offset + slot*tcs_stride. |
| Command stride | 0x14 (20 bytes) | 0x18 (24 bytes) | Each command index contributes command*cmd_stride; do not inspect command 0 alone. |
| TCS_STATUS | 0x18 | 0x28 | Preserve raw whole value. Pinned X source describes zero as busy and reports whole-value zero/nonzero; do not replace with a bit-0 test. Not command completion. |
| CMD_ENABLE | 0x1c | 0x2c | Per-command enable bit. Disabled entries with stale nonzero ADDR/DATA are not enabled requests. Preserve raw word and decoded bit. |
| CMD_MSGID | 0x30 | 0x34 | Preserve raw word; source format has length 8, write bit 16, response-request bit 8. Requesting a response is not ACK receipt. |
| CMD_ADDR | 0x34 | 0x38 | Address of this command; record slot and command index. |
| CMD_DATA | 0x38 | 0x3c | Raw request value. For LCX/LMX label it ARC corner/level index, never mV. |
| CMD_STATUS | 0x3c | 0x40 | Preserve raw word; source identifies issued bit 8 and complete bit 16. Interpret transaction progress together with TCS type and the response-request bit; do not impose a universal ACK/complete-bit requirement on a request that did not ask for a response. Do not alias to TCS status or infer power. |
| Capability word | selected RSC base + 0x0c | selected RSC base + 0x0c | max_tcs=(caps>>(6*logical_drv_id))&0x3f; ncpt=(caps>>27)&0x1f. Record raw caps and logical id from the same attempt. |

Board DT tuple yields configured groups active slots 0-2, sleep 3-4, wake 5-6, fast 7 (control has zero slots). This describes configured usage, not a license to probe every slot. Separately, a historical touch log reported caps=0x800c8104, max_tcs=8, ncpt=16; it is not the rail boot's snapshot and must not be spliced into it. Neither TCS_TYPE_NR=5 nor a theoretical 8x16 scan limit is justified by itself. The downstream configuration code also checks the configured total against max_tcs; derive the configured candidate slot list from that same-boot validated configuration rather than treating DT tuple positions or caps as a directly readable command list.

## Bounded geometry and outcome taxonomy

Access has two stages, both after strict gates and the once claim. First, an explicitly reviewed minimal bootstrap may read the fixed-width version word at selected base+0 and capability word at base+0x0c, after checking their alignment, mapped spans and permission without trusting their contents. These two reads do not require their as-yet-unknown values to be prevalidated and do not authorize the rest of the window. Before any TCS/command load, validate the captured supported version, aligned offsets/strides, caps and logical driver id, DT group-derived count, explicit reviewed implementation maximums, physical mapping length and permitted read domain. The scan domain is the intersection of those limits. Unknown or inconsistent input stops before the first disallowed load; no fallback to another DRV, guessed count, or wider map is allowed.

For each slot and command, calculate offsets with checked multiplication and addition. Use subtraction-form range checks (offset <= length && field_size <= length - offset) so arithmetic cannot wrap. Check the full field width, alignment, and end against the mapped span before every load, including version, caps, status, enable, msgid, address, data, cmd-db headers, entry arrays, and each aux region. Validate count*entry_size, base-plus-offset, aux length, array bounds, and maximum counts before traversal. A span cut short before the requested domain completes is CoverageIncomplete, not Missing. A complete scan with no matching enabled command is NotFound; neither is a positive power observation.

Every retained command record carries physical window identity, logical driver id, version, slot index, command index, TCS type/group if resolved, raw enable/msgid/TCS status/CMD status/address/data, derived flags and source provenance. Preserve multiple matches. Never stop at the first address match, first zero DATA, or first apparently valid tuple. Build one bounded read schedule: capture a shared version/caps word or slot-level status/enable word once and reuse it for both rail interpretations; do not reread registers merely to print them or wait for status changes. Per-command words are captured once at their checked addresses. This is a sequential observation, not an atomic hardware snapshot; no retry, stabilization loop or completion polling is permitted.

Use distinct outcomes; do not collapse them into valid=false or one Missing. The immutable pass result has an overall outcome and coverage descriptor; each retained record separately has residual/format/status/duplicate annotations. These labels are not all mutually exclusive pass-level enum values: for example, a full scan may report NotFound for enabled requests while retaining DisabledResidual records, or an ObservedRequest may carry DuplicateIdentical annotations. Conflicts and partial coverage remain explicit and cannot become an unqualified complete observation:

| Outcome | Meaning |
| --- | --- |
| Ineligible | Data is not exactly mounted or strict opt-in is absent/invalid; no map or register load and no attempt is consumed. |
| Busy | Another caller owns ATTEMPTING; refuse immediately without waiting, polling, mapping, or reading. |
| MapFailed(db) / MapFailed(drv) | Required map failed. It is a terminal attempt result, not “never tried.” |
| DbMissing / DbCorrupt | Name absent after a complete valid walk versus malformed/truncated/overflowing database geometry. |
| UnsupportedVersion / CapsInvalid / GeometryDenied | Unknown layout, caps/DT disagreement, illegal count, arithmetic failure, bounds failure, or unapproved access. Coverage is not complete. |
| NotFound | Full permitted domain was scanned, but no enabled matching request exists. Not evidence of absent power. |
| DisabledResidual | Matching address/data remains but command enable bit is clear. Preserve as residual only. |
| MalformedRequest | Invalid/zero msgid shape or inconsistent required fields. Keep raw command record and exact slot/index. |
| TcsBusy / CommandNotIssued / CommandIncomplete | Distinct raw status-derived states. TCS idle does not imply command issued/completed; command completion does not imply effective rail power. |
| DuplicateIdentical / DuplicateConflict | Keep every matching slot+command. Identical duplicates remain multiplicity; contradictory fields/data are explicit conflict. Never choose first. |
| ObservedRequest | Complete permitted scan retained one or more correctly decoded enabled request records. Observation only, no power authority. |
| TerminalCacheCorrupt | Cached terminal data fails magic/version/length/state validation. Refuse; never remap or repair by sampling again. |

A partial observation can coexist with an overall CoverageIncomplete result, but must not be upgraded to a complete scan. Diagnostics report coverage, first stop reason, and all records safely captured before that stop.

## One public entry and one-attempt state machine

There must be exactly one public function allowed to begin sampling (proposed name: k60_rail_observe_once). The acquisition workers, including rail_pass or its replacement, are private and reachable only by its CAS winner; traversal workers accept only validated spans. No diagnostic helper or second public wrapper may map or walk independently. Gate checks apply at every public call before using either hardware or cached results.

    UNATTEMPTED
      gate/Data false or malformed -> Ineligible; no map/read; remain UNATTEMPTED
      strict Data==1 and pong_rail_probe parses exactly 1
        CAS UNATTEMPTED -> ATTEMPTING (before first map)

    ATTEMPTING
      concurrent/reentrant caller -> Busy immediately; no spin/wait/poll/map/read
      winner executes one bounded read-only pass
      every recoverable exit (including either map failure) -> TERMINAL(result)

    TERMINAL(result)
      eligible later caller -> validate immutable cache and return/print it only
      corrupt cache -> TerminalCacheCorrupt; no resampling
      no reset/retry in this boot

Initialize a conservative failure result before work; publish a complete immutable terminal result with release semantics, read it with acquire semantics. Compare/exchange is the attempt boundary. Failed DB map, DRV map, command-database parser, unknown layout, range/permission check, or interrupted bounded traversal after the claim consumes the one attempt. A boot-argument parse failure is different: it is an eligibility failure before CAS, so it consumes no attempt. Ineligibility before CAS consumes none, allowing a legitimate post-Data opt-in call later. Process/boot restart is a new lifetime; no runtime API resets state.

| First-attempt exit | State published after the claimed pass | Later eligible call |
| --- | --- | --- |
| DB map failure | TERMINAL(MapFailed(db)) | Read/print validated cache only; no map or load. |
| DRV map failure | TERMINAL(MapFailed(drv)) | Read/print validated cache only; no map or load. |
| Bad cmd-db header/entry/aux bounds | TERMINAL(DbCorrupt) or TERMINAL(CoverageIncomplete), with exact stop reason | Cache only; do not retry malformed data. |
| Unsupported version/caps/DT or denied geometry | TERMINAL(UnsupportedVersion/CapsInvalid/GeometryDenied) | Cache only; do not widen or retry. |
| Bounded pass ends without a matching enabled record | TERMINAL(NotFound) only when coverage is complete; otherwise TERMINAL(CoverageIncomplete) | Cache only. |
| Match(es) retained | Publish all retained records with exact coverage and annotations. ObservedRequest requires a complete permitted pass and well-formed enabled request(s); partial coverage, disabled residuals, malformed records and duplicate conflicts remain qualified outcomes. | Cache only; never turn observation into inherited power. |
| Cache validation fails | Preserve the terminal attempt; report TerminalCacheCorrupt | Refuse; never restart sampling. |
| Caller sees ATTEMPTING | No state change | Return Busy immediately; no map/load/spin/wait. |

rail_pass is an internal worker invoked only by the CAS winner. k60_rail_probe() becomes a strict-gated diagnostic facade: it calls the unique entry and prints that attempt's validated cache, never remaps before checking cache and never performs a second raw cmd-db walk. Legacy k60_rail_inherit() uses the same entry/cache and may report observation details, but a request observation cannot return power-inherited success. k60_adsp_probe_from_handoff() may reach the same sampler only for diagnostics after Data and opt-in gates; it must not translate an observation/verdict into permission to copy, authenticate, reset, publish, or create an owner lease. Its operational path remains refused until a separate valid power-evidence and ownership contract is reviewed. Wrappers share one attempt state; call ordering is not a substitute for CAS.

## Strict gate and cache contract

- **Data:** require current k60_data_mounted == 1 at every public entry, not merely at the known late callsite. Data=0 means no map, load, or attempt. An earlier refusal must not be cached as a sampled rail result.
- **Opt-in:** require PE_parse_boot_argn("pong_rail_probe", ...) success and parsed integer exactly 1. Missing, parse failure, 0, 2, and -1 are off. Initialize the destination to a sentinel before parsing so parse failure cannot reuse a caller-provided 1. Check even on cache hits; disabled opt-in refuses without exposing cache as successful gate.
- **Read-only:** only bounded loads in already-authorized ranges; no TCS writes, trigger, vote, polling, delay loop, or SCM/PAS operation. Do not add a raw dump that bypasses common entry.
- **Cache:** cache only after the once claim; include schema/magic, terminal state, gate and Data snapshot, mapping identities and sizes, logical id, version/caps, validated geometry, scan coverage/stop reason, every raw record and slot+command index, explicit outcome. Cache hit means zero map and zero hardware loads. Integrity failure is terminal failure, never a reason to resample. Cache proves only what was observed in that one bounded pass, not atomicity or continuing state.

## Observation type is not power evidence

The public result must be typed and named as request observation, not inherited/effective rail. For example, a future K60RailRequestObservation may contain coverage, outcome, version/caps provenance, and retained commands. It must not expose a boolean named powered, inherited, ResourcesHeld, or an integer success code legacy PAS can treat as equivalent.

A separate K60RailPowerEvidence type can exist only after a separately reviewed, board-valid source proves required semantics: AOP aggregate vote, ARC effective state, PMIC/rail effect, and required retention/lifetime across handoff. The sampler cannot construct or cast to this type. CMD response-request, CMD_STATUS.complete, nonzero DATA, TCS idle, cmd-db hit, successful map, software complete/valid, or K60RailVerdictInherited is insufficient by itself. ResourcesHeld remains owned by its resource/lease implementation, not by a read-only diagnostic.

## Canonical host-test matrix

The KERNEL entry fixture must compile/link unchanged canonical [K60PmicRail.c](../../../drivers/PongPower/K60PmicRail.c) with KERNEL=1, fake kernel headers and deterministic map/boot-argument-parser stubs over synthetic buffers only. The helper fixture links the same unchanged canonical source to exercise its pure field/parser APIs. Neither fixture may link PAS/SCM, access real MMIO, change production behavior, or treat exit zero as proof of compliance. The integrated runner is [probe-k60-rail-sampler-host.py](../../../scripts/probe-k60-rail-sampler-host.py); its fixtures are [helper.c](../../../package/tests/rail-sampler/helper.c), [entry.c](../../../package/tests/rail-sampler/entry.c), and minimal fake kernel headers. These paths fit the existing diagnostics ownership patterns (`scripts/probe-*`, `package/tests/**`); no porting record or verification status was changed. The intended runner CLI is `--output ABS --mode reproduced-current-behavior|compliance|all`; each fixture binary supports `--list` and `MODE CASE` for an isolated process. Report modes separately: reproduced-current-behavior (defect reproduction) and compliance (current-canonical violations must return nonzero, never pass by substituting a repaired model). Individual field controls or parser-negative cases may pass while the overall compliance mode remains red. Final independent invocations (WSL Ubuntu-24.04; fresh output directories; each case in a separate process):

```sh
python3 scripts/probe-k60-rail-sampler-host.py --output /mnt/e/k60-work/artifacts/adsp-board-20261116/rail-design/reproduced-reviewed --mode reproduced-current-behavior
python3 scripts/probe-k60-rail-sampler-host.py --output /mnt/e/k60-work/artifacts/adsp-board-20261116/rail-design/compliance-reviewed --mode compliance
```

The integrated run directly compiles unchanged canonical C as a separate translation unit: helper with `-std=c11 -O1 -Wall -Wextra -Werror`, entry with `-std=c11 -O0 -Wall -Wextra -Werror -pthread -DKERNEL=1` and fake include paths. No PAS/SCM object is linked. Each binary supports `--list`; the runner records every compile/run command, stdout/stderr, actual return code, per-case JSON, canonical before/after hashes and fixture/runner hashes. The aggregate collection wrapper finishing successfully only means the two actual exit statuses were collected; it does not turn the compliance exit 1 into success.

| Final mode | Helper (18 cases) | KERNEL entry (57 cases) | Total / actual runner exit |
| --- | --- | --- | --- |
| reproduced-current-behavior | 18 PASS | 57 PASS | 75 PASS, 0 FAIL, exit 0 |
| compliance | 9 narrow PASS, 9 FAIL | 8 narrow PASS, 49 FAIL | 17 narrow PASS, 58 FAIL, exit 1 |

Both modes had zero infrastructure errors or timeouts. A narrow PASS checks only that case predicate; it is not sampler compliance. In particular, entry command-0 controls now require valid raw request fields **and refusal of inheritance authority** in compliance mode. The current source returns zero and fails that assertion. A valid request observation need not be marked invalid to refuse power authority.

Final artifacts are [reproduction log](E:/k60-work/artifacts/adsp-board-20261116/rail-design/reproduced-reviewed.log) (SHA-256 `4afac87296776970d7c6cf2c13e7251b8c0bca0b074c53305f715e448c32d750`) and [compliance log](E:/k60-work/artifacts/adsp-board-20261116/rail-design/compliance-reviewed.log) (SHA-256 `edc683846e34aa0454379a35f2b346438b4453617e6b8cf3157f812c3cab72da`). Each corresponding `*-reviewed/` directory retains `summary.json`, `commands.json`, `sha256.txt`, both binaries and per-case logs. Earlier directories without the `-reviewed` suffix predate the authority-assertion correction and are superseded, not final evidence.

Tested base revision: `cd02f1348db6d232f9b705cddf82cd968edb5711`. Canonical hashes are unchanged before/after both runs: C `1a170aacba3d5a26ff48162794720da44451b4567588578c79d848cd5b86c504`, H `cf72a5c9f7f6f46e5124b1bcf58f15e03be50834b5fee9057cdb7bc5d0c3d77b`. Fixture and runner hashes are retained in each manifest to identify the then-uncommitted test additions exactly.

| Case | Reproduced-current-behavior evidence | Compliance assertion after implementation |
| --- | --- | --- |
| command 0 positive control | Existing helper: complete=1, valid=1 for synthetic fixture only. | Typed ObservedRequest, never power/lease success. |
| slot 5 only; last configured slot/command (synthetic slot 7 command 15) | Existing audit helper reports Missing for slot 5 because current scan stops at slots 0-4; last-slot/command case is part of the new test plan, not that old result. | Enumerate only after verified caps/DT/bounds/access intersection; record exact slot and command. Synthetic 8x16 tests do not authorize real 8x16 access. |
| v2 command 1 only / v3 command 1 only | Existing helper reports Missing; stride is not used for a complete walk. | Use v2 0x14 and v3 0x18, preserve command index and selected version. |
| disabled nonzero residual | Existing helper says valid=1. | Preserve raw tuple as DisabledResidual; not an enabled request. |
| zero msgid and zero CMD_STATUS | Existing helper says valid=1 because fields are ignored. | Preserve raw state; classify malformed/not-issued/incomplete per pinned semantics. |
| TCS_STATUS=2 | Existing helper says not idle using bit 0; not a claim hardware emits this value. | Decode whole raw value with pinned zero/busy semantics; do not alias CMD_STATUS. |
| first matching DATA=0 then later DATA=16 | Existing helper returns first invalid match and hides later conflict. | Visit all permitted matches, retain slot+command, report duplicate conflict/multiplicity. |
| truncated synthetic span with later matching field versus fully unmatched span | Existing helper reports Missing for truncated coverage. The size-taking helper API can test this directly; the entry mapper requests fixed lengths and returns no shorter-map length, so this is not an entry-level partial-map result. | Distinguish CoverageIncomplete from NotFound; check every individual field span. A future entry partial-map test needs a separately reviewed size-bearing seam, not an undersized allocation presented as a full map. |
| DB map failure and DRV map failure | Existing KERNEL entry audit retries on subsequent calls because no attempt is recorded. | First caller claims before map; failure is terminal and every later public entry performs zero maps/loads. |
| failure through one entry then another | Existing entry audit shows retry across inherit/probe. | All wrappers use same once state and terminal result. |
| preseed cache then probe | Existing entry audit still maps before cache use. | Strict gate first; cache-only path with no mapping or hardware read. |
| Data/argument gate matrix | Existing entry audit: probe accepts Data=0/arg off, inherit does not check Data, nonzero 2 accepted, cache path bypasses gate. | Missing/parse-false/0/2/-1 and Data=0 refuse before map; only Data=1 plus parsed exact 1 is eligible, including cache hit. Verify Data=0 then Data=1 does not consume attempt early. |
| deterministic CAS contention and re-entry | Not covered by existing entry audit. | Exactly one claimant reaches first map; contender/reentrant caller returns Busy immediately with no map/read/wait. Use failed-map path to avoid ledger write races. |
| v2/v3 multi-command fields | Existing helper has command-1 misses above. | Assert each pinned offset, both status words, per-command enable, msgid and command index; reject unknown version. |
| duplicate identical and contradictory records | Existing helper only demonstrates first-zero then later-nonzero being hidden. | Preserve every identical duplicate; contradictory records get explicit conflict. Never select first. |
| bad DB magic/count/offset/aux, overflow, caps/DT mismatch, short helper span, resource id 0 | Some bounded-parser, field and malformed-input negatives are directly testable with the helper/API and may pass independently. The current entry has no caps/DT contract, and these controls do not prove full traversal or raw-load safety. | Refuse safely with precise corrupt/denied/incomplete/invalid-argument taxonomy and no out-of-span load. Unresolved resource id 0 must not match empty command words. |
| corrupt terminal cache | Existing tests do not establish once-state cache behavior. | Return TerminalCacheCorrupt; no map/read retry or success. |
| read-only and no authority | Prior host audit uses synthetic buffers; not power evidence. | Assert no writes, no PAS/SCM calls, no ResourcesHeld/success authority. |

**Existing evidence only:** audit reports helper reproduction 9/9, AUDIT REPRODUCED ... failures=0, output SHA-256 1e1bca11ae9a340de7ff1ac4c9e5222b4271189cbbe4caace7a153498bf2de89; and ten KERNEL entry cases with PASS_EXPECTED_CURRENT_BEHAVIOR, output SHA-256 734aec89d5765c612f608a3d035bc95ba276e52fb342faa80f63733bd21f10b1. These are defect-reproduction results only. Canonical whole-compliance mode is expected to remain red against the current source even if the bounded helper cases pass. The current K60RailRecord API represents one record per rail and exposes neither a command index nor raw CMD_MSGID/CMD_STATUS fields; it cannot by itself verify retained multi-command records or separate TCS/CMD status. Existing audit entry tests count map/parser stub invocations but do not instrument every volatile load; map counters alone do not prove a cache hit performed zero register loads. Do not claim exact raw-load counts until a test seam/instrumentation supports that claim. The final integrated suite above supersedes interim helper-only counts. Concurrency/reentry tests hold the first failing DB map while invoking a contender, reproducing two maps where the contract permits one; those failures avoid all canonical ledger writes. The legacy integer API cannot distinguish typed Busy from MapFailed, expose the CAS transition, or prove acquire/release publication. Assertions therefore establish counterexamples to one-attempt behavior, not a proof of the proposed state machine. A future blocking contender is reported as a timeout/infrastructure failure, never a passing Busy result. The parser stub models return/output contracts rather than the real textual boot-argument grammar. Legacy valid/complete fields cannot encode every proposed raw annotation, duplicate list, coverage class or power type; fixture predicates against this API are conservative regression checks, not the final typed repair interface. Identical-duplicate retention and the full caps/DT/overflow/access-domain matrix are specified but not established by this suite. Complete raw CMD_MSGID/CMD_STATUS/command-index assertions require the reviewed typed interface; the field fixtures do not manufacture those missing production fields.

## 候选核心（未集成）的宿主验证

本轮按 Lead 18:11 授权，在 `package/tests/rail-sampler/proposed/` 放下一个**不接入生产**的观测核心，并把“候选核心契约验证”与“canonical 缺陷复现”分开报告。

| 项目 | 值 |
| --- | --- |
| 核心 / 头文件 | `package/tests/rail-sampler/proposed/rail_obs.c` / `rail_obs.h` |
| 冻结哈希 | C `b6e51b43676a506690c48756cad5fe7e0a11d6c312cf617ed7c48e859ff00bf2`；H `effe1a112f9ed7acf882ce692df84205b6118b88ffb953ffc318bc9edf3fed93` |
| 契约测试 | `package/tests/rail-sampler/proposed/entry.c`，sha256 `fa117b58d9611b127c38e6bd7edad4a3796c1ae8b0766a441e779d4730e52524`，39 个 case |
| 驱动脚本 | `run-tests.sh` `baf339ad99542627b4b93644e4fe646e97f03c354a1d344cfc128df8f00810e7`；`verify-extra.sh` `36b4dd91170726586d542da7f8aa431c943d524b90ffef4db9ef0c1f6e955f78`；`run-candidate.py` `da628fbaa95808449f1bdd6b4d615d35206afbe01160399cbeee79099e2085f6`（一 case 一进程，绝不做 expected-failure 归一） |
| 结果 | `run-tests.sh`: `CANDIDATE_CORE_RESULT: PASS 39/39 cases`，exit 0；`verify-extra.sh`: `ASAN_UBSAN: CLEAN (0)`、`SYMBOLS: CLEAN (no K60PmicRail symbol)`、`REPEAT: 10/10`，exit 0；`run-candidate.py`: PASS 39/39，exit 0 |
| 证据日志 | [driver-run.log](E:/k60-work/artifacts/adsp-board-20261116/rail-candidate/driver-run.log) `fad73a5588a45199aba78f269b23c14c0934b87090bb92f274a41c29c2bfc26a`；[verify-extra.log](E:/k60-work/artifacts/adsp-board-20261116/rail-candidate/verify-extra.log) `d8f23d84b971b2037f6ad2af41bdf37eaed66a76cf816327cfc5fd17bd644aaf`；[final39.log](E:/k60-work/artifacts/adsp-board-20261116/rail-candidate/final39.log) `b3a80fee1edefbc3ec3ee974a740e291d392cd2a98526900ff74569af9e68952` |

候选核心验证的是**契约**，不是硬件可读性：map/read32 是显式注入的 seam，permit 的每个 span 都是测试输入；核心只经 read32 读，逐字段检查对齐、mapped 长度、reviewed block 边界与显式 span，先过 gate 再 CAS，先 CAS 再第一次 map；失败即 terminal，后续同 plan 调用只读缓存，坏缓存返回 `CACHE_CORRUPT` 且不重采样；返回值全为负，无任何可被旧接口当作 ResourcesHeld 的成功值。v2/v3 两套偏移、slot+command 全扫描、duplicate identical/conflict、disabled/malformed/TCS busy/not-issued/incomplete 都以 qualifier 与 outcome 分开保留。

同时**没有**证明的事情必须一起读：

1. 真实 LCX/LMX 请求字段仍无 per-slot/per-command 读取许可；按本文“可证明的访问域”，真实采样应报 `PERMISSION_DENIED`/unknown，合成 permit 不构成硬件许可。
2. 没有 PAS/SCM/SMEM/lease/资源回调路径；候选核心不产生、也不能产生 `ResourcesHeld`。
3. `command_block` 在核心里的语义是**相对 TCS base 的累计边界**，不是单条命令宽度：v3 的 command 1 末端为 0x18+0x40+4=0x5c，v2 为 0x14+0x3c+4=0x54；用 0x44 只覆盖 command 0。这是契约输入的含义，不是核心缺陷。
4. `parsed_value` 必须恰为 1，**契约要求 `parse_ok` 也恰为 1**；核心当前按 truthy 接受是已观测缺陷，`observed-parse-ok-truthy` 用 gate `{1,2,1}` 把它钉住，已登记进 PITFALLS.md 的“候选缺陷队列（未编号）”。本轮按裁决不改核心，不能把该行为当契约。
5. `OBSERVED_REQUEST` 要求 LCX 与 LMX 两条请求同时存在；只有一条有效请求会落到 `MALFORMED_REQUEST`/`NOT_FOUND`——这说明头文件的 API **无法表达部分请求**，是真信息，不是分类错误；本轮不动头文件。
6. 头文件只有 `k60_rail_observe_once` 一个入口，“跨 facade 标签”用同 plan 重复调用与 terminal replay 表达，不是独立生产入口。
7. 坏缓存注入只在 TERMINAL 之后顺序进行，无 reset hook；每条序列独立进程，因此并发只覆盖“首个 map 失败、未写 ledger”的路径。
8. 未见硬件、未建内核/镜像、未改生产 C/H、patch、callsite 或 boot 参数；canonical 红灯保持原样。

### Lead 19:36 裁决（本轮已执行）

1. **`command_block` 以布局自洽为准**：它是相对 TCS base 的累计边界，v3 command 1 的合法 permit 写 `0x5c`（0x18+0x40+4），v2 写 `0x54`；`command-block-short` 保留 `0x40` 拒绝。新增 `command-block-0x44-geometry` 断言 `0x44` 在 `cmd_address`（0xd50）以 `GEOMETRY_INVALID` 停下——case 名称与注释都写明这是 **observed behaviour，不是契约**；`0x44` 是否应成为契约仍是开放问题。
2. **`db_block=0x90` 得到 `DB_CORRUPT`**：断言观测值，但 case 改名为 `db-block-table-truncated`（144 + 2×24 = 192 > 0x90，表被截断），并明确 `GEOMETRY_INVALID` 分类**尚未建立**。
3. **`parse_ok` 契约是严格 1**：两个输入都保留；`2` 能过 gate 作为核心缺陷登记进 PITFALLS 候选队列，本轮不改核心。
4. **单轨请求落到 `MALFORMED_REQUEST`/`NOT_FOUND`**：登记为“API 无法表达部分请求”，不动头文件。
5. **不接受 facade 包装**：文档写明“跨入口”证据是 terminal replay，不是多个生产入口。
6. **驱动脚本随交付提交**：`run-tests.sh`、`verify-extra.sh`、`run-candidate.py` 都在 `package/tests/rail-sampler/proposed/`，否则结果不可复现。
7. **host-only 范围声明留在文首**：候选核心只做宿主契约验证。
8. **精确编译命令**：Ubuntu 24.04 / cc 13.3.0，`-std=c11 -O1 -Wall -Wextra -Werror -DK60_RAIL_OBS_HOST_TEST -pthread`；旧 libc 可能还需要显式 `-pthread`，不声称到处都能构建。
9. **无 reset hook、每条序列独立进程**被接受为未覆盖边界。

### 仍开的问题

1. `command_block` 是否应把 `0x44` 当作合法契约（当前按布局自洽判为观测行为）。
2. `db_block` 的表截断是否应归入 `GEOMETRY_INVALID` 而不是 `DB_CORRUPT`。
3. 是否要求 `parse_ok == 1` 与 `parsed_value == 1` 同时严格成立（当前核心只对后者严格）。
4. 头文件是否要能表达“只观测到一条轨”的部分请求（当前 API 不能）。

canonical 两模式在同一冻结源上重跑，证明候选文件没有反过来“修绿”旧断言：复现模式 75/75、exit 0；compliance 模式 58 fail / 17 pass、exit 1；两模式 `canonical_unchanged=True`。日志 [reproduced-final.log](E:/k60-work/artifacts/adsp-board-20261116/rail-design/reproduced-final.log)（SHA-256 `4afac87296776970d7c6cf2c13e7251b8c0bca0b074c53305f715e448c32d750`）与 [compliance-final.log](E:/k60-work/artifacts/adsp-board-20261116/rail-design/compliance-final.log)（SHA-256 `edc683846e34aa0454379a35f2b346438b4453617e6b8cf3157f812c3cab72da`）。exit 0 是复现结果，不是合规结论。

## Open blockers and review gate

| Blocker | Required evidence before implementation can be considered complete |
| --- | --- |
| Live field provenance | One same-attempt version/caps/count snapshot; reconcile board DT and caps. Historical logs from different boots are not composable. |
| Range authorization | Explicit approved per-field/per-slot/per-command read domain. Arithmetic fitting in 0x10000 is not access permission. Do not guess a full 8x16 domain. |
| Status/duplicate policy | Confirm retained raw request semantics and classification across concurrent/changed records without claiming atomic snapshot or ACK not observed. |
| Once-state correctness | Host evidence for CAS-before-first-map, terminal failure, immediate contention/re-entry refusal, cross-entry cache-only behavior and corrupt-cache refusal. |
| Test visibility | Add a testable load seam or another reviewed way to establish no subsequent hardware reads; map counters alone do not count volatile loads. |
| Effective power and retention | Find a legal, board-specific AOP/ARC/PMIC and handoff-retention observation contract. Current evidence does not establish one. |
| Consumer authority | Keep resources_cb refused and legacy PAS/handoff disabled until separate power evidence and lease/owner semantics are accepted. Observation is never enough. |

Next review order: pinned source -> version/field table -> access intersection and bounds -> duplicate/error taxonomy -> entry gates/CAS/cache -> observation-vs-power types -> canonical host evidence. This deliverable adds the design, canonical host fixtures and an unintegrated candidate core with its own host contract check. No kernel/image build, device test, production C/H or patch edit, callsite/timing edit, boot-argument change, or porting-state change occurred. The proposed repair remains unimplemented until separately authorized after Lead review.
