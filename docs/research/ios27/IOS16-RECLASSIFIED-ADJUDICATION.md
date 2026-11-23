# Adjudication of the eight reclassified patches

P-311 moved eight patches out of `anchor-drift` because no context line of theirs exists in
the 27 feed. That only proves the *anchor* is absent; this file records what each patch
actually needed and where it stands. Evidence commands are in the table footer.

| patch | what it needs | in 27 feed | in our series | verdict |
| --- | --- | --- | --- | --- |
| `0327-k60-persona-proxy-bootstrap.patch` | `k60_persona_proxy_bootstrap` | 0 | 0 | `not-applicable (mechanism absent)` |
| `0334-k60-panic-reset-fastboot.patch` | `k60_usblog_reset_to_fastboot`, `k60_prime_restart`, `k60_panic_reset_to_fastboot` | 0 | **3**（`0549`、`0550`） | `covered`（复位已由 0549/0550 提供；只剩「panic 时触发」未接，记 deferred） |
| `0399-k60-shared-cache-root-layout.patch` | `native_owner_cache_mounted_device`, `native_owner_cache_selected_device` | 0 | 0 | `not-applicable (mechanism absent)` |
| `ios16-clang-uio-driverkit-compat.patch` | no project symbol; 19 files of `UIO_SIZEOF`/DriverKit type compat | 0 | 0 | `deferred`（16 线编译器兼容层，27 无对应编译错误） |
| `ios16-disabled-perf-link.patch` | `_pmap_pending_preemption_real` | 0 | 0 | `not-applicable (mechanism absent)` |
| `pong-development-amfi-call-guards.patch` | `csblob_os_entitlements_get` | 0 | 0 | `not-applicable (mechanism absent)` |
| `k60-panic-report.patch` | `k60_psci_uses_hvc` | 0 | 0 | `not-applicable (mechanism absent)` |
| `architectural-timer-entry.patch` | no project symbol; ARM generic timer entry | 0 | 0 | `deferred`（27 的入口由 `0541` 处理 `CNTP_CTL_EL0` 跳过，机制不同） |

## How each count was taken

```
grep -rF -c '<symbol>' /opt/k60/trees/ios27-out/feeds/xnu-3199e8bc
grep -rF -c '<symbol>' patches/xnu-12377
```

Symbols are the `k60_*` / `native_*` identifiers that appear **in the patch itself**, not the
longest identifier on any added line (that was the earlier mistake: it picked
`CleanPoC_DcacheRegion_Force` for `k60-panic-report`, a symbol the patch merely calls).

## What still needs work

- `0334` panic path: the reset primitive exists (`0549`), the "call it from the panic handler"
  trigger does not. That is the remaining item from the original four-step chain
  (`0300` → `0308` → `0334b`), recorded in `CARRY-OVER-INVENTORY.md`.
