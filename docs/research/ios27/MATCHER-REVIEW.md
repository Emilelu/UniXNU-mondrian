# Matcher review: the 25 named stubbed targets

Date: 2026-11-21
Branch: feat/cellular-k55
Scope: offline review of the stage-0 prelink report. No build, no device, no
fastboot, no edit to the shared device tree.

## 0. Decision

The 25 named targets are **25 at the "no entry" state, 0 at "entry with a zero
value", and 0 at "entry with a signature mismatch"**.

The three states are counted by the target address key in
kernel.map.json. All 131 unique stubbed target addresses (the 25 named targets
plus the 106 unnamed ones) are absent as keys from both the functions and the
data tables. There is no target-keyed entry to hold a zero or a mismatching
signature. This is not a value-level rejection that can be repaired by changing
an entry; the map never proposed a pairing for these targets.

Two of the 25 candidate names do occur somewhere else in the map:

* _mach_absolute_time is the map name at output key 0xfffffff00ad4d858, native
  0xfffffff00754b108, method reference-order, while the candidate target is
  0xfffffff00ab86b04.
* _ml_get_max_cpu_number is the map name at output key 0xfffffff00ad469c8,
  native 0xfffffff007544354, method reference-order, while the candidate target
  is 0xfffffff00ad3d804.

Those are same-name entries at a different target. They are neither an entry at
our target nor a signature mismatch. The other 23 candidates have no exact-name
entry anywhere in the map.

Evidence labels in this document use only **proven** and **probable**.

* **Proven** means a literal string in the function body, or a caller that names
  the routine, is present in the local artifact. Four candidates meet this:
  _proc_parent, ___memcpy_chk, _pmap_claim_reserved_ppl_page and
  _pmap_free_reserved_ppl_page.
* **Probable** means link order plus size and shape against the iPad 24A446
  fixture. Twenty-one candidates are in this class. They are not proven merely
  because the fixture has a same-sized function; two have a size difference
  (see the table), and match.json only offers a family cross-reference.

Only the four proven candidates may be considered for a reviewed function
record. The probable ones must first acquire a literal or caller artifact. No
candidate may be added to any allowlist from this review alone.

The 139 items and 105 targets that have no candidate name remain the fourth
class. Nothing below attempts to name them or to reduce their count.

## 1. Inputs and counting

The stubbed ledger is the stage-0 kernel.json, not kernel.map.json:

* kernel.json records 205 stubbed items, 131 unique target addresses, 25 owning
  bundles, and missing/stubbed ledgers.
* kernel.json records missing_address_space = "output collection" and
  collection_slide = 0. The target addresses are output-collection addresses.
  The map keys use the same address space; a target must not be looked up as a
  native address.
* unreachable.toml has 205 stanzas, 203 distinct target+bundle records, 131
  unique targets and 25 bundles. The 205/203 difference is the same counting
  distinction recorded in RELEASE-VS-DEVELOPMENT.md, not a new target set.

kernel.map.json is a positive-only pairing table:

* functions: 16,899 entries; data: 797 entries.
* functions_original: 21,692; functions_native: 29,012;
  functions_matched: 16,899.
* data_matched: 781; data entries with an empty name: 72; data entries with a
  zero native value: 0. Functions with a zero native value: 0; functions with an
  empty name: 0.
* functions_by_method: reference-symbol 3,669; reference-order 12,861;
  string 108; pac-checked-shape 13; calls 128; vtable 88; call-sites 16;
  data-users 1; pure-leaf 15. There is no reviewed method.
* data_by_method: reference-data 221; refs 269; vtable-layout 279; slot 5;
  users 3; sysctl 3; fields 1. There is no reviewed method.
* The map has no top-level missing list and no signature field. Missing and
  stubbed are recorded by fileset_emit.emit_images into kernel.json
  (fileset_emit.py:733-741).

The intersection with this review is 25 targets and 61 stubbed items. The sum is
61 + 5 + 139 = 205: 25 named targets, one generic device-tree target, and 105
targets with no candidate name. The 25 named targets are the subject below.

## 2. The 25 targets

The target column is a kernel.json output address. "map at target" is always
"absent" here; the separate "map name elsewhere" column records the two
same-name entries described in section 0. The basis column says why the
candidate is a candidate; it does not say the pairing is accepted.

| target | candidate | label | size B | items | map at target | map name elsewhere | basis |
|---|---|---|---:|---:|---|---|---|
| 0xfffffff00abe3554 | _printf | probable | 56 | 11 | absent | none | 44 B after _cons_putc_locked, tail-calls the shared formatter; fixture _printf is 56 B; classify.py:493-497 |
| 0xfffffff00abe36d4 | _vprintf | probable | 36 | 2 | absent | none | 36 B, also branches to the shared formatter; fixture _vprintf is 36 B; classify.py:499-501 |
| 0xfffffff00ab86b04 | _mach_absolute_time | probable | 12 | 7 | absent | 0xfffffff00ad4d858 | 12 B leaf, mrs S3_4_C15_C10_6; fixture has sibling _mach_continuous_time at 12 B, not the same name; classify.py:502-506 |
| 0xfffffff00b0de1d8 | _proc_name | probable | 132 | 7 | absent | none | bzero + proc_find + strlcpy + proc_rele; target is 132 B but fixture _proc_name is 124 B; classify.py:507-510 |
| 0xfffffff00b0de068 | _proc_parent | **proven** | 368 | 1 | absent | none | body references the literal "proc_parent"; target and fixture are both 368 B; classify.py:511-513 |
| 0xfffffff00ad05978 | ___memcpy_chk | **proven** | 68 | 1 | absent | none | body references "__memcpy_chk object size check failed"; fixture is 68 B; classify.py:514-516 |
| 0xfffffff00b416214 | _pmap_claim_reserved_ppl_page | **proven** | 56 | 1 | absent | none | the corecrypto caller references "pmap.c/pmap_claim_reserved_ppl_page"; fixture is 56 B; classify.py:517-520 |
| 0xfffffff00b41624c | _pmap_free_reserved_ppl_page | **proven** | 56 | 1 | absent | none | the caller references "pmap_free_reserved_ppl_page"; fixture is 56 B; classify.py:521-523 |
| 0xfffffff00b11a998 | _code_signing_configuration | probable | 240 | 3 | absent | none | 240 B after _code_signing_deallocate; fixture is 240 B; called from the early AMFI path; classify.py:524-528 |
| 0xfffffff00b11a314 | _check_trust_cache_runtime_for_uuid | probable | 128 | 1 | absent | none | 128 B after _load_legacy_trust_cache; fixture is 128 B; classify.py:529-532 |
| 0xfffffff00b11acd8 | _restricted_execution_mode_state | probable | 44 | 2 | absent | none | 44 B in the _developer_mode_state cluster; fixture is 44 B; classify.py:533-537 |
| 0xfffffff00abdd25c | _lck_rw_gate_destroy | probable | 312 | 1 | absent | none | 312 B after _lck_rw_gate_alloc_init, calls gate_verify_destroy_panic; fixture is 312 B; classify.py:538-541 |
| 0xfffffff00abde90c | _lck_mtx_gate_try_close | probable | 308 | 1 | absent | none | 308 B after _lck_mtx_gate_alloc_init; fixture is 308 B; classify.py:542-544 |
| 0xfffffff00abdea40 | _lck_mtx_gate_close | probable | 284 | 1 | absent | none | 284 B next to _lck_mtx_gate_try_close; fixture is 284 B; classify.py:545-547 |
| 0xfffffff00ac20880 | _task_reference_external | probable | 140 | 5 | absent | none | calls zone_id_require_panic + os_ref_panic_retain; target is 140 B but fixture is 144 B; classify.py:548-552 |
| 0xfffffff00ad3d804 | _ml_get_max_cpu_number | probable | 16 | 2 | absent | 0xfffffff00ad469c8 | 16 B, 56 B after _cpu_to_processor; fixture is 16 B; classify.py:553-555 |
| 0xfffffff00ad46814 | _ml_get_cpu_number | probable | 92 | 2 | absent | none | 92 B, 20 B after _ml_get_boot_cpu_number; fixture is 92 B; classify.py:556-558 |
| 0xfffffff00ad468ec | _ml_get_cpu_number_local | probable | 92 | 1 | absent | none | 92 B, 236 B after _ml_get_boot_cpu_number; fixture is 92 B; classify.py:559-561 |
| 0xfffffff00ad46948 | _ml_get_cluster_number_local | probable | 128 | 1 | absent | none | 128 B, 328 B after _ml_get_boot_cpu_number; fixture is 128 B; classify.py:562-565 |
| 0xfffffff00ada1af4 | _vnode_lookup | probable | 12 | 2 | absent | none | 12 B tail-call to vnode_lookupat, 308 B after _vnode_lookupat; fixture is 12 B; classify.py:566-570 |
| 0xfffffff00ada94d8 | _vnode_authorize | probable | 112 | 2 | absent | none | 112 B after _vn_authorize_unlink, calls vnode_getwithref_noblock; fixture is 112 B; classify.py:571-574 |
| 0xfffffff00add40f8 | _vnode_clearmountedon | probable | 196 | 1 | absent | none | 196 B, 32 B after _vnode_ismountedon; fixture is 196 B; match.json's score-1 candidate is _vnode_setmountedon, not this name; classify.py:578-580 |
| 0xfffffff00add41bc | _vnode_setmountedon | probable | 196 | 1 | absent | none | 196 B, 228 B after _vnode_ismountedon; fixture is 196 B; classify.py:575-577 |
| 0xfffffff00b2a7f90 | IOService::Start_Invoke | probable | 284 | 2 | absent | none | 284 B next to _ClaimSystemWakeEvent_Invoke; fixture C++ entry is 284 B; classify.py:581-585 |
| 0xfffffff00b2a7e74 | IOService::Stop_Invoke | probable | 284 | 2 | absent | none | 284 B, 804 B after _ClaimSystemWakeEvent_Invoke; fixture C++ entry is 284 B; classify.py:586-588 |

The four proven candidates do not have a map entry, a zero entry, or a
mismatching entry. They are simply unpaired. The two same-name entries at other
keys are not evidence that the matcher "almost" bound the target: the map's
reference-order method can attach a name to a different function, and the target
address remains unpaired.

## 3. Why match.json is not a matcher result

match.json is a local cross-reference, not the kit's pairing map:

* _match.py:9-36 reads the iPad 24A446 fixture, groups its functions by
  original_size, scores each target by shared tokens with the preceding
  function and the fixture evidence, and writes match.json. It does not run
  fileset_match.match_images and it does not read kernel.map.json.
* match.json has 131 records. Twenty records have at least one score-1
  candidate; 111 have no positive-scoring candidate. Seven of the 25 named
  targets have a score-1 candidate: 0xfffffff00abe3554 (_printf),
  0xfffffff00b11a998 (_code_signing_configuration),
  0xfffffff00ada1af4 (_vnode_lookup),
  0xfffffff00abde90c (_lck_mtx_gate_try_close),
  0xfffffff00abdd25c (_lck_rw_gate_destroy),
  0xfffffff00add41bc (_vnode_setmountedon) and
  0xfffffff00add40f8 (_vnode_setmountedon).
* A score-1 candidate is still a candidate. The clearmountedon target's top
  candidate is the setmountedon name; the two names are adjacent 196-byte
  functions. The score must not be used as proof or as an allowlist entry.
* For the four proven names, match.json is silent or has only score-0
  neighbours. The literal/caller evidence, not match.json, is what makes them
  proven.

The fixture is not for our kernelcache:

* fixtures/fileset-24A446-symbols.json has inputs.kernelcache_sha256 =
  38e6d9fa5f789b8228f4617ef4c6d2a3fd8ab564abdc9b62920f1db53fc1780a,
  156 functions, 29 data entries and one site. Our kernelcache is
  fa07057b...; no fixture record carries that hash.
* fixtures/fileset-23F84-symbols.json has input 0f7d50ac..., 108 functions and
  one data entry; fixtures/fileset-26C5035r-symbols.json has input d1003b51...,
  zero functions and one site. Neither contains any of the 25 targets.
* fileset_match.reviewed_records (fileset_match.py:339-346) yields only a
  fixture whose (kernelcache_sha256, entry) equals the input. Because no fixture
  matches fa07057b..., anchor_reviewed (fileset_match.py:451-467) adds nothing,
  and the map's functions_by_method has no reviewed method. The fixture's 156
  named iPad functions are useful candidates but are not a reviewed pairing for
  this cache.

The data allowlist is also not a function allowlist:

* IOS27-PRELINK-ALLOWLIST.toml has 19 [[pairing]] records: 16 data identities
  and three target = "unpaired" data records (AppleARMWatchdogTimer __const leaf,
  IOHIDFamily __common zero fill, security.sandbox __common zero fill). It has
  no entry for any of the 25 targets, their addresses, or their names.
* k60-fileset-pair.py:79 uses payload.setdefault("data", {}) and only writes
  data keys. It never touches payload["functions"], so it cannot pair a function
  target by itself. It can recompute the map signature, but a data entry does
  not turn a function target into a paired function.

## 4. What "no entry" means mechanically

fileset_match.match_images (fileset_match.py:1014-1077) starts with no pairs.
It adds reviewed anchors, optional reference anchors and reference-order
anchors, unique-string anchors, PAC-checked shapes, repeated shape/propagation
rounds, data pairings and pure leaves. A function target that no anchor reaches
simply stays out of matcher.pairs. There is no rejected-candidate list and no
zero-valued placeholder for it.

fileset_emit.emit_images (fileset_emit.py:688-743) builds pairs from the map's
functions and data tables, rebases them, and lets the segmented emitter count
missing and stubbed references. It reports missing_address_space =
"output collection", sets mapping_complete to not missing, and writes the
stubbed ledger. That is why kernel.json has 205 stubbed items while
kernel.map.json has no entry for those targets.

Therefore the three requested states decompose as follows for the 25 named
targets:

| state | count | evidence |
|---|---:|---|
| no entry at target | 25 | 25 target keys absent from map.functions and map.data |
| entry with native = 0 | 0 | no map function or data value is 0x0 |
| entry with signature mismatch | 0 | no target-keyed entry; the map has no signature field to mismatch |

The two same-name-elsewhere records do not change these counts. If the required
question is instead "does a same-name map entry exist anywhere", the answer is
2, not 25; that is a different question and is not an allowlist decision.

## 5. Minimal fix options

No configuration key can repair these targets. CONFIG_XNU_* keys change make
variables, source selection or object CFLAGS; they do not create a reviewed
function pairing. EXTRA_LD_ARCHIVES can add our source to the link, but it does
not name an Apple output address or make the matcher bind it. The fourth class
is not a missing CONFIG switch.

### Option A: a reviewed function record pinned to our cache (preferred for the four proven names)

Add a new fixture JSON under the kit's fixtures directory, with inputs
kernelcache_sha256 = fa07057b..., entry = com.apple.kernel, and a functions
entry for each proven target. The fields that anchor_reviewed actually consumes
are:

* original: the target address, e.g. 0xfffffff00b0de068;
* original_sha256: sha256 of the original function bytes from the pinned cache;
* original_size: the size in facts2.json (368 for _proc_parent);
* native_symbol: the exact native symbol, e.g. _proc_parent;
* evidence: the literal string or caller text that makes the identity proven.

fileset_match.anchor_reviewed rejects a function whose original address is not in
original.functions, rejects a byte hash that does not match, and binds only when
the native symbol is unique in the native image. A record for the four proven
names is the smallest reviewable change. It must not include the 21 probable
names: a same-size fixture function is not proof, and _proc_name and
_task_reference_external do not even have equal size.

The fixture is under /opt/.../kits/XnuPrelink/fixtures; changing it is a shared
kit change, not a change to this branch. The implementation was not attempted
here.

### Option B: our own reviewed function pairing file

If the kit's fixture is not to be edited, an own pairing step can merge
reviewed function entries into the emitted map's functions table, preserve the
inputs and recompute the signature. That is a code change to the pairing tool;
the current k60-fileset-pair.py only merges data (line 79), so it is not enough
as it stands. Option B has more moving parts than Option A and should not be
used to smuggle a probable candidate into a map.

### Option C: a different kit input or reference kernel

--fileset-reference can add a symbol-bearing comparison kernel, but the map
already has 3,669 reference-symbol and 12,861 reference-order functions from
the current reference, and none of the 25 targets acquired a key. The original
cache has no kernel symbol table; match_by_names (fileset_names.py:92-155) is
selected only when symbol_bearing() is true (fileset_names.py:41-47), so
changing the command line alone does not switch this cache to name matching.
A symbol-bearing artifact of the same Apple 24A446 cache would be new evidence,
not an argument to relax the matcher.

--allow-missing only controls whether an incomplete image is written and
whether unmatched functions jump to _unixnu_fileset_unmapped. It is not a
pairing fix.

### Option selection by group

| group | count | smallest next step |
|---|---:|---|
| proven candidates | 4 | Option A: add a reviewed function record for each, only after hashing the exact original bytes; this is the only group eligible for a reviewed pairing now |
| same-name entries elsewhere | 2 | resolve whether the existing reference-order entry is a different function or a bad bind; then use Option A only if the target identity is proven |
| probable candidates | 21 | no pairing yet; obtain a literal string or caller artifact first, then Option A; do not use match.json score as proof |
| no candidate name | 105 targets / 139 items | fourth class; do not name or pair from this review |

### The two same-name-elsewhere targets

For _mach_absolute_time and _ml_get_max_cpu_number, first decide whether the
existing map entry at 0xfffffff00ad4d858 or 0xfffffff00ad469c8 is a different
function or a bad reference-order bind. Do not add a duplicate name for the
candidate target until that is resolved. The reviewed-record route, if the
identity is proven, is still by target address, not by name alone.

## 6. The 139 items / 105 targets

The fourth class is unchanged. RELEASE-VS-DEVELOPMENT.md accounts for
205 = 61 + 5 + 139. The 61 items are the 25 named targets above; the 5 items are
the generic device-tree target; the 139 items/105 targets have no candidate name
in either the release or development nm table. They need a same-family artifact
with symbols, not another candidate heuristic. This review spends no further
time naming them and does not move them into an allowlist.

## 7. Checks and reproduction

The exact counts in this document were reproduced offline from:

* /opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/kernel/kernel.json
* /opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/kernel/kernel.map.json
* E:/k60-work/scratch/stubs/facts2.json and match.json
* E:/k60-work/scratch/stubs/unreachable.toml
* /opt/k60/trees/ios27-fw/kits/XnuPrelink/fixtures/fileset-*-symbols.json
* E:/hackios/k60-gates/docs/engineering/IOS27-PRELINK-ALLOWLIST.toml

The checks used in this review:

* parse kernel.map.json, assert 16,899 functions and 797 data entries, assert no
  native value is 0x0, and assert all 131 stubbed target keys are absent;
* for each of the 25 named addresses, look up the exact address and then the
  candidate name in functions and data; record the two same-name-elsewhere
  keys separately;
* parse the three fixture files, assert none has input fa07057b..., and count
  target hits in functions, data and sites;
* parse the allowlist, assert 19 [[pairing]] records, 16 data identities, three
  target = "unpaired" records, and zero hits for the 25 targets;
* parse match.json, assert 131 records, 20 with a score-1 candidate and 111
  without a positive candidate.

The repository checks for this branch are the normal documentation and secret
checks; they do not build or execute the prelink kit.

## 8. Limits

* This review is a map and artifact review. It does not prove that any target is
  unreachable at runtime and it does not authorize an allowlist relaxation.
* The four proven names are proven identities, not proven safe targets. The
  prelink still needs the exact original bytes and a unique native symbol.
* The two same-name entries elsewhere are not evidence of a near match; the map
  has no candidate list and no per-target rejection record.
* The expected function sizes for _proc_name (132 vs 124) and
  _task_reference_external (140 vs 144) are recorded as differences, not as
  reasons to force a pairing.
* The 139/105 fourth class remains open; no config experiment in this branch
  changes it.
