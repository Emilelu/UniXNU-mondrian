# NativeUfs host tests

These are the verified-root host tests from the reference ShengUfs tree
(`references/ShengUfs@9d527ae`, `BSD-2-Clause-Patent`), copied verbatim except
for one portability line in `RootWindowRead.cpp` (`{0ULL,UINT64_MAX}` cannot
deduce `initializer_list<auto>` on GCC 11; it is now an explicit
`{uint64_t(0), UINT64_MAX}` list).

The headers under `drivers/NativeUfs/` are the corresponding
`VerifiedTableCache.h`, `RootPublication.h` and `RootWindowRead.h` from the
same revision. `tests/support/verified_root.h` and
`tests/support/verified_root.c` now forward to the kernel-side
`drivers/NativeUfs/verified_root.{h,c}` copied from
`UniXNU/VerifiedRoot@974f043d0c71ba2e60331483a41c6c6d35274ee3`; the host tests
compile the kernel source, not a second implementation.

Provenance:

| files | source commit | author |
|---|---|---|
| `VerifiedTableCache.h`, `tests/VerifiedTableCache.cpp` | `57f031c99d7f69ffa611626bebaeab0731e93254` | rponeawa <rponeawa@qq.com> |
| `RootPublication.h`, `RootWindowRead.h`, `tests/RootPublication.cpp`, `tests/RootWindowRead.cpp` | `31155a6db21678df3c89d9d25b5711466d229369` | bluseliu50 <265648257+bluseliu50@users.noreply.github.com> |
| `drivers/NativeUfs/verified_root.h`, `verified_root.c`, `xnu_crypto.c`, `tests/support/openssl_provider.c`, `tests/support/manifest.py` | `974f043d0c71ba2e60331483a41c6c6d35274ee3` (`UniXNU/VerifiedRoot`) | rponeawa <rponeawa@qq.com> |
| `tests/support/verified_root.h`, `tests/support/verified_root.c` | `9dbc8001eea86bd23e47d887dc186a4914b1290a` (`UniXNU/VerifiedRoot`) | bluseliu50 <265648257+bluseliu50@users.noreply.github.com> |
| `drivers/NativeUfs/RootPolicyTable.h`, `tests/RootPolicyTable.cpp`, `tests/check-verified-root.py` | new adaptation of the policy-table flow in `references/ShengUfs@9d527ae1a8d36a7ff210f9f4c9b429549c34c991` `NativeUfs.cpp:2169-2330` | Sharky Wang <rponeawa@qq.com> (reference) |
| `drivers/NativeUfs/RootWindowVerifier.h`, `tests/RootWindowVerifier.cpp` | new wrapper over `VerifiedTableCache.h` + `RootPolicyTable.h`; same `NativeUfs.cpp:2169-2330` reference | Sharky Wang <rponeawa@qq.com> (reference) |
| `tests/RootWindowReadVerified.cpp` | new host test of the transport read shape (`ufsReadWindow` verify-before-copy) over `RootWindowVerifier` | — |

Run (Linux/WSL, OpenSSL development headers required):

```sh
mkdir -p .host-tests
g++ -std=c++17 -I drivers/NativeUfs/tests -I drivers/NativeUfs/tests/support \
    -o .host-tests/RootPublication drivers/NativeUfs/tests/RootPublication.cpp
g++ -std=c++17 -I drivers/NativeUfs/tests -I drivers/NativeUfs/tests/support \
    -o .host-tests/RootWindowRead drivers/NativeUfs/tests/RootWindowRead.cpp
g++ -std=c++17 -I drivers/NativeUfs/tests -I drivers/NativeUfs/tests/support \
    -o .host-tests/VerifiedTableCache drivers/NativeUfs/tests/VerifiedTableCache.cpp \
    drivers/NativeUfs/tests/support/verified_root.c -lcrypto
.host-tests/RootPublication && .host-tests/RootWindowRead && .host-tests/VerifiedTableCache
python3 drivers/NativeUfs/tests/check-verified-root.py
```

`check-verified-root.py` generates owner and wrong-owner RSA-3072 keys with
OpenSSL, builds signed full/header-only manifests, compiles the kernel-side
`verified_root.c` plus the OpenSSL provider, and exercises policy selection,
LUN-0 `<window>.vroot` reads, wrong anchor, wrong table, truncation and
signature mutation. It also builds `tests/RootWindowVerifier.cpp`, which keeps
the full-envelope and header-only paths behind one per-window object and checks
that the page cache serves block digests without keeping the whole table.
`RootWindowReadVerified.cpp` feeds the same verifier through `ufsReadWindow`
with a mock transport, so the verify-before-copy order is exercised without
IOKit. `PongUfsTransport.cpp` now calls the verifier under
`NATIVE_VERIFIED_BLOCK` (default off); `build-pong-ufs-probe-macos.py --verified-root`
also compiles `verified_root.c` and `xnu_crypto.c` into the archive, while the kernel
link must still supply the generated policy bundle (`verified_root_policies` and
`verified_root_key`) when that switch is enabled. See step 2b in
`docs/plans/SHENGUFS-VERIFIED-TABLE-PORT.md`.
