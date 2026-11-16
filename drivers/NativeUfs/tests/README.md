# NativeUfs host tests

These are the verified-root host tests from the reference ShengUfs tree
(`references/ShengUfs@9d527ae`, `BSD-2-Clause-Patent`), copied verbatim except
for one portability line in `RootWindowRead.cpp` (`{0ULL,UINT64_MAX}` cannot
deduce `initializer_list<auto>` on GCC 11; it is now an explicit
`{uint64_t(0), UINT64_MAX}` list).

The headers under `drivers/NativeUfs/` are the corresponding
`VerifiedTableCache.h`, `RootPublication.h` and `RootWindowRead.h` from the
same revision. `tests/support/verified_root.h` and
`tests/support/verified_root.c` are the `UniXNU/VerifiedRoot` kit files the
cache header needs; they are vendored only for these host tests.

Provenance:

| files | source commit | author |
|---|---|---|
| `VerifiedTableCache.h`, `tests/VerifiedTableCache.cpp` | `57f031c99d7f69ffa611626bebaeab0731e93254` | rponeawa <rponeawa@qq.com> |
| `RootPublication.h`, `RootWindowRead.h`, `tests/RootPublication.cpp`, `tests/RootWindowRead.cpp` | `31155a6db21678df3c89d9d25b5711466d229369` | bluseliu50 <265648257+bluseliu50@users.noreply.github.com> |
| `tests/support/verified_root.h`, `tests/support/verified_root.c` | `9dbc8001eea86bd23e47d887dc186a4914b1290a` (`UniXNU/VerifiedRoot`) | bluseliu50 <265648257+bluseliu50@users.noreply.github.com> |

Run (Linux/WSL, OpenSSL headers required):

```sh
g++ -std=c++17 -I drivers/NativeUfs/tests -I drivers/NativeUfs/tests/support \
    -o /tmp/RootPublication drivers/NativeUfs/tests/RootPublication.cpp
g++ -std=c++17 -I drivers/NativeUfs/tests -I drivers/NativeUfs/tests/support \
    -o /tmp/RootWindowRead drivers/NativeUfs/tests/RootWindowRead.cpp
g++ -std=c++17 -I drivers/NativeUfs/tests -I drivers/NativeUfs/tests/support \
    -o /tmp/VerifiedTableCache drivers/NativeUfs/tests/VerifiedTableCache.cpp \
    drivers/NativeUfs/tests/support/verified_root.c -lcrypto
/tmp/RootPublication && /tmp/RootWindowRead && /tmp/VerifiedTableCache
```

This import changes no running code path: the headers are not included by
`NativeUfs.cpp` or `PongUfsTransport.cpp` yet. Wiring is planned in
`docs/plans/SHENGUFS-VERIFIED-TABLE-PORT.md` (step 2/3).
