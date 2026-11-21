# One question for the crypto/framework owner

**The question.** For iOS 27.0.1 (24A446) on this board, is the crypto bootstrap `source`
or `prelinked` — and who decides it?

Two measured premises, both from this tree:

1. `XNU_NATIVE_AES=1` is refused unless `CRYPTO_BOOTSTRAP_MODE == prelinked` **and**
   `XNU_SOURCE_CORECRYPTO14 == 1` — `scripts/build-xnu-generic.sh:199-203`. The two
   platform-page switches that need AES (`NATIVE_RAM_BLOCK` at `:221-227`,
   `OWNER_ROOT_PROBE` at `:287-291`) inherit that refusal, so they abort before any archive
   lookup.
2. `configs/mondrian_ios27_defconfig:12` sets `CONFIG_XNU_CRYPTO_BOOTSTRAP="source"`, and
   the file does not set `CONFIG_XNU_SOURCE_CORECRYPTO14` at all. The 16.6.1 file sets the
   pair (`:12` `prelinked`, `:73` `SOURCE_CORECRYPTO14=n`), so 27 is not a copy of the
   16.6.1 answer by accident — it is a different bootstrap mode.

What the answer changes, and why it is not a storage decision:

- if **source** is the 27 answer, then `NATIVE_AES`, `NATIVE_RAM_BLOCK` and
  `OWNER_ROOT_PROBE` are unreachable by construction on this profile, and the storage row's
  two remaining switches need a different design (or a different stage), not a config flip;
- if **prelinked** is the answer, then `CONFIG_XNU_CRYPTO_BOOTSTRAP` and
  `CONFIG_XNU_SOURCE_CORECRYPTO14` have to change together with whoever produces the
  prelinked crypto closure, and the storage row can then be planned against that baseline.

One sentence is enough as an answer: `source`, `prelinked`, or "decided later, here is the
condition". The storage line does not implement either choice; it only needs to know which
wall it is standing in front of.
