# iOS 16 patches reclassified as missing-file: the evidence

> **WARNING — read the counts, not the verdict column.** The symbol is picked mechanically
> (longest identifier on an added line). It can pick a symbol our own series defines in a
> *different* patch: 0334 is in fact covered by 0549-k60-usblog-reset.patch, so its row
> below is wrong. Each row needs a human decision before it closes anything.

Each row names a symbol the patch adds or calls, and the count of that symbol in the
entire 27 base feed. Zero means the mechanism the patch needs does not exist here,
which is what `missing-file` claims (P-311).

| patch | symbol | in 27 base feed | in our 27 series | verdict |
| --- | --- | --- | --- | --- |
| `0327-k60-persona-proxy-bootstrap.patch` | `k60_persona_proxy_bootstrap` | **0** | 0 | mechanism absent |
| `0334-k60-panic-reset-fastboot.patch` | `k60_usblog_reset_to_fastboot` | **0** | 0 | mechanism absent |
| `0399-k60-shared-cache-root-layout.patch` | `vm_shared_region_start_address` | **0** | 0 | mechanism absent |
| `ios16-clang-uio-driverkit-compat.patch` | `UIO_SIZEOF` | **0** | 0 | mechanism absent |
| `ios16-disabled-perf-link.patch` | `_pmap_pending_preemption_real` | **0** | 0 | mechanism absent |
| `zzzzzzzzzzzz-pong-development-amfi-call-guards.patch` | `csblob_os_entitlements_get` | **0** | 0 | mechanism absent |
| `zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-k60-panic-report.patch` | `CleanPoC_DcacheRegion_Force` | **0** | 0 | mechanism absent |
