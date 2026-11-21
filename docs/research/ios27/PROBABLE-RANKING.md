# Probable function candidates: similarity order

Status: ranking only. This document does not pair, approve, allowlist, or edit
`kernel.map.json` or the kit. The four proven entries remain only in
[`FUNCTION-PAIRING-PROPOSAL.toml`](FUNCTION-PAIRING-PROPOSAL.toml) and are held
under the Lead decision recorded there. All 21 entries below remain
`probable`; none has a target-body literal or a caller that names it.

## Ranking key

The order is lexicographic and uses only the evidence dimensions already
recorded in [`MATCHER-REVIEW.md`](MATCHER-REVIEW.md) and
`E:/k60-work/scratch/stubs/classify.py:493-588`:

1. **Size equality**: target size equals the fixture candidate size. All four
   proven names are equal. Two probable names are not.
2. **Code relation**: direct (`tail-call`, `branch`, `call`, or a unique
   instruction sequence tied to the candidate) is stronger than adjacency
   (`after` or `next to` a named anchor), which is stronger than family
   cluster.
3. **Caller or consumer**: a separate caller path or a known consumer table
   (for example the AMFI early path or the IOHID/IOStorage const tables). This
   is weaker than a literal in the target body and is not proof.
4. **`match.json` score 1**: tie-break only. It is a local heuristic, not a
   matcher result, and it is demonstrably wrong for `_vnode_clearmountedon`.
5. **Ambiguity penalty**: a same-name map entry at another address, or a
   score-1 candidate that names the twin function, moves the row down.

The result is a reading order for the next evidence, not a probability and not
an approval list.

## Ranked 21

| rank | candidate | target | size target / fixture | relation | caller or consumer | score 1 | ambiguity | why this rank |
|---:|---|---|---|---|---|---|---|---|
| 1 | `_printf` | `0xfffffff00abe3554` | 56 / 56 | direct: tail-calls the shared formatter at `0xfffffff00abe358c`; 44 B after `_cons_putc_locked` | none | yes | none | exact size plus the strongest direct code relation |
| 2 | `_code_signing_configuration` | `0xfffffff00b11a998` | 240 / 240 | adjacency: after `_code_signing_deallocate` | AMFI `initializeAppleMobileFileIntegrity` early path | yes | none | exact size, named caller path, score 1 |
| 3 | `_lck_rw_gate_destroy` | `0xfffffff00abdd25c` | 312 / 312 | direct: calls `gate_verify_destroy_panic`; after `_lck_rw_gate_alloc_init` | none | yes | none | exact size plus a direct call and score 1 |
| 4 | `_vnode_lookup` | `0xfffffff00ada1af4` | 12 / 12 | direct: tail-call to `vnode_lookupat`; 308 B after `_vnode_lookupat` | none | yes | none | exact size plus a tail-call and score 1 |
| 5 | `_vprintf` | `0xfffffff00abe36d4` | 36 / 36 | direct: branches to the shared formatter | none | no | none | exact size plus a direct branch; score 1 is not necessary |
| 6 | `_lck_mtx_gate_try_close` | `0xfffffff00abde90c` | 308 / 308 | adjacency: after `_lck_mtx_gate_alloc_init` | none | yes | none | exact size and score 1, but no direct body call recorded |
| 7 | `_vnode_authorize` | `0xfffffff00ada94d8` | 112 / 112 | direct: calls `vnode_getwithref_noblock`; after `_vn_authorize_unlink` | none | no | none | exact size plus a direct call |
| 8 | `IOService::Start_Invoke` | `0xfffffff00b2a7f90` | 284 / 284 | adjacency: next to `IOService::_ClaimSystemWakeEvent_Invoke` | IOHIDFamily and IOStorageFamily const tables | no | none | exact size plus a known consumer table |
| 9 | `_vnode_setmountedon` | `0xfffffff00add41bc` | 196 / 196 | adjacency: after `_vnode_ismountedon` | none | yes | twin `_vnode_clearmountedon` at 196 B | exact size and score 1, but the twin makes the name choice risky |
| 10 | `_mach_absolute_time` | `0xfffffff00ab86b04` | 12 / 12 | direct shape: `bti c; mrs x0, S3_4_C15_C10_6; ret` | none | no | same name already at `0xfffffff00ad4d858` | unique instruction sequence, but the existing map entry must be resolved first |
| 11 | `_lck_mtx_gate_close` | `0xfffffff00abdea40` | 284 / 284 | adjacency: next to `_lck_mtx_gate_try_close` | none | no | none | exact size, adjacency only |
| 12 | `_check_trust_cache_runtime_for_uuid` | `0xfffffff00b11a314` | 128 / 128 | adjacency: after `_load_legacy_trust_cache` | none | no | none | exact size, one anchor, no direct body evidence |
| 13 | `_ml_get_cpu_number` | `0xfffffff00ad46814` | 92 / 92 | adjacency: 20 B after `_ml_get_boot_cpu_number` | none | no | none | exact size, family adjacency only |
| 14 | `_ml_get_cpu_number_local` | `0xfffffff00ad468ec` | 92 / 92 | adjacency: 236 B after `_ml_get_boot_cpu_number` | none | no | none | exact size, same family, weaker distance than rank 13 |
| 15 | `_ml_get_cluster_number_local` | `0xfffffff00ad46948` | 128 / 128 | adjacency: 328 B after `_ml_get_boot_cpu_number` | none | no | none | exact size, family adjacency only |
| 16 | `IOService::Stop_Invoke` | `0xfffffff00b2a7e74` | 284 / 284 | adjacency: 804 B after `_ClaimSystemWakeEvent_Invoke` | none recorded | no | none | exact size, weak distance, no consumer evidence |
| 17 | `_ml_get_max_cpu_number` | `0xfffffff00ad3d804` | 16 / 16 | adjacency: 56 B after `_cpu_to_processor` | none | no | same name already at `0xfffffff00ad469c8` | exact size, but the existing map entry is unresolved |
| 18 | `_vnode_clearmountedon` | `0xfffffff00add40f8` | 196 / 196 | adjacency: 32 B after `_vnode_ismountedon` | none | yes, but the top candidate is `_vnode_setmountedon` | twin name and contradictory score-1 candidate | exact size, but the score is evidence against this name, not for it |
| 19 | `_restricted_execution_mode_state` | `0xfffffff00b11acd8` | 44 / 44 | cluster: `_developer_mode_state` family only | none | no | none | exact size, no direct anchor |
| 20 | `_proc_name` | `0xfffffff00b0de1d8` | 132 / 124 | body semantics: `bzero` + `proc_find` + `strlcpy` + `proc_rele`; order `_proc_setplatformdata` -> `_proc_name` | none | no | 8 B larger than fixture | same proc family as proven `_proc_parent`, but size equality fails |
| 21 | `_task_reference_external` | `0xfffffff00ac20880` | 140 / 144 | body semantics: calls `zone_id_require_panic` + `os_ref_panic_retain`; order `_task_deallocate_grp` -> `_task_reference_external` | none | no | 4 B smaller than fixture | strongest remaining body semantics, but size equality fails |

## Tiers and next evidence

- **Ranks 1-10** have exact size plus either a direct code relation or a named
  caller/consumer. `_mach_absolute_time` is in this tier on instruction shape,
  but its same-name map entry is an unresolved ambiguity.
- **Ranks 11-19** have exact size but only adjacency, cluster, or a name
  contradiction. They need a body literal or a caller that names them before
  they can move into the proven class.
- **Ranks 20-21** have the strongest body semantics among the remainder, but
  their size differs from the fixture. A future fixture with the same source
  revision could move them up; the current evidence does not.

No row moves to `proven` from this ranking. The next evidence for every row is
still a literal in the target body or a caller that names the candidate; a
same-size fixture function, a neighbour, or a `match.json` score is not enough.

## Reproduction

The row data comes from `MATCHER-REVIEW.md` section 2 and
`E:/k60-work/scratch/stubs/classify.py:493-588`. The target sizes, items, and
neighbours are from `E:/k60-work/scratch/stubs/facts2.json`; the score-1
column is the local `match.json` heuristic and is not a kit result.
