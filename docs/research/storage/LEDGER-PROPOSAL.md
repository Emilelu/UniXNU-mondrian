# Proposal: fold the three console-unreachable targets into `prelink-map-unresolved`

Status: proposal only, 2026-11-21. This lane read
`E:/hackios/k60-gates/docs/engineering/IOS27-FLIGHT-BLOCKERS.toml` but did not
edit it. The proposed text lives on `feat/xnu27-data-gate` for the Lead to
review and land.

The exact conclusion requested for the ledger is:

> 三者在 console 前不可达（静态证据），残余=间接构造未证

## What the shared ledger says now

The blocker is `[[blocker]] id = "prelink-map-unresolved"` at
`E:/hackios/k60-gates/docs/engineering/IOS27-FLIGHT-BLOCKERS.toml:23`. Its
`why_open` at `:27-48` currently opens with:

> 205 pointer slots, not 205 calls, and none of them is reachable before the
> console.

and closes with:

> The three addresses that stay unpinned are recorded in
> IOS27-PRELINK-ALLOWLIST.toml with their mechanism instead of a name, so
> check-prelink-hazards.py is green.

## Proposed edits (rows 1 and 4 only)

| # | 现在写的句子 | 建议改成什么 | 依据 文件:行 |
| --- | --- | --- | --- |
| 1 | `205 pointer slots, not 205 calls, and none of them is reachable before the console.` | `205 stubbed pointer slots, not 205 calls; none of the 205 is a call site. Separately, the three remaining missing targets are data, not entry points. 三者在 console 前不可达（静态证据），残余=间接构造未证。` | `docs/research/storage/PRELINK-CONSOLE-REACHABILITY.md:8-29` (short answer and reachability boundary); `:69-93` (data, not entry points); `:141-158` (zero-hit scan) |
| 2 | `osfmk/kern/startup.c brings the console up at :478 and the code-signing window at :526; the first kext start is PE_init_iokit() at :689 inside kernel_bootstrap_thread().` | `osfmk/kern/startup.c brings the console up at :585 and the code-signing window at :630; the first kext start is PE_init_iokit() at :806 inside kernel_bootstrap_thread().` | `E:/hackios/UniXNU/out/mondrian/ios-27.0.1-24A446/mondrian_ios27/tree/.cache/xnu-work/osfmk/kern/startup.c:584-585`, `:629-630`, `:805-806`; also `PRELINK-CONSOLE-REACHABILITY.md:160-174` |
| 3 | `13 of them become reachable from code_signing_init() at :526, which is after console subsystem init but before the USB CDC-ACM console K60 gives a human, so a trap in that group is silent: implement those first.` | `13 of them become reachable from code_signing_init() at :630, which is after console subsystem init but before the USB CDC-ACM console K60 gives a human, so a trap in that group is silent: implement those first.` | `E:/hackios/UniXNU/out/mondrian/ios-27.0.1-24A446/mondrian_ios27/tree/.cache/xnu-work/osfmk/kern/startup.c:629-630`; `PRELINK-CONSOLE-REACHABILITY.md:160-174` |
| 4 | `The three addresses that stay unpinned are recorded in IOS27-PRELINK-ALLOWLIST.toml with their mechanism instead of a name, so check-prelink-hazards.py is green.` | `The three addresses that stay unpinned are recorded in IOS27-PRELINK-ALLOWLIST.toml with their mechanism instead of a name; all three are data, not entry points, and 三者在 console 前不可达（静态证据），残余=间接构造未证 (docs/research/storage/PRELINK-CONSOLE-REACHABILITY.md). check-prelink-hazards.py remains green; the allowlist is a visibility record, not a name or a runtime proof.` | `E:/hackios/k60-gates/docs/engineering/IOS27-PRELINK-ALLOWLIST.toml:184-205`; `PRELINK-CONSOLE-REACHABILITY.md:8-29`, `:199-223` |

## Pasteable `why_open` fragment (rows 1 and 4 only)

Rows 2 and 3 stay in `PRELINK-CONSOLE-REACHABILITY.md` as evidence; the shared
ledger gets conclusion sentences only. The fragment below is a complete
`why_open` value for `[[blocker]] id = "prelink-map-unresolved"`. It contains no
`"""` and no backslash, so the triple-quoted basic string is safe. It is
validated with Python `tomllib` before it is sent.

```toml
why_open = """205 stubbed pointer slots, not 205 calls; none of the 205 is a call site. Separately, the three remaining missing targets are data, not entry points. 三者在 console 前不可达（静态证据），残余=间接构造未证。

The three addresses that stay unpinned are recorded in IOS27-PRELINK-ALLOWLIST.toml with their mechanism instead of a name; all three are data, not entry points. The allowlist is a visibility record, not a name or a runtime proof; check-prelink-hazards.py remains green. Details and scans: E:/hackios/xnekom-ios27/docs/research/storage/PRELINK-CONSOLE-REACHABILITY.md (branch feat/xnu27-data-gate)."""
```

## Why this is not closure

The ledger stays `state = "open"`. This proposal does not say the three are
impossible to call; it says the static scan is zero, they are data, and only
XNU core runs before `console_init`. `loadable = false` and the
indirect-construction residual remain. Closing the blocker still needs the
205 stubs implemented or excluded, or an explicit policy decision.

## Proposed P-294 row (Lead-only file)

`E:/hackios/k60-gates/docs/engineering/PITFALL-IDS.md:10-21` is the shared
allocation table. This lane may not edit `E:/hackios/k60-gates`, so the row is
proposed here for the Lead to land:

| id | line | note |
| --- | --- | --- |
| P-294 | bt | 报告里的 `candidate_sha256` 不是最终 `kernel.macho` 的 sha256：`/opt` 路径会被原地替换，证据只能绑哈希 |

The supporting text is on this branch in `docs/engineering/PITFALLS.md` P-294,
`docs/engineering/RULES.toml` P-294, and README ranges `P-01–P-294`. The
instance evidence is in `PRELINK-CONSOLE-REACHABILITY.md:228-270`.
