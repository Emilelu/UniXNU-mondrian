# Ring 5 — the minimal interface contract for adding a prelink entry

Status: 2026-11-21, **contract only, no code**. Ring 5 is owned by the fileset-entry
design owner + the Lead (m00999, m01201 ③): the change moves every kext's
placement, which is beyond one storage lane. This file describes what the storage
line needs from that ring so it can be handed over as-is.

Scope: `kits/XnuPrelink/native_prelink.py` and `kits/XnuPrelink/emit_prelink_orig.py`
in `E:/hackios/UniXNU`. Everything below is derived from those two files and from
`UniXNU/profiles/os/ios-27.0.1-24A446/profile.toml`; the line numbers are measured,
not remembered.

## Why the ring exists (measured)

- `native_prelink.py:147-154` walks the `roots` list and raises
  `Missing declared dependency {identifier}` for any identifier absent from the
  original `_PrelinkInfoDictionary`.
- `native_prelink.py:160-171` then iterates **only the entries that already exist**
  in that dictionary, and requires each to be filetype 11
  (`Expected MH_KEXT_BUNDLE component`).
- `emit_prelink_orig.py:131-134` builds its output from that same metadata and
  reads `entries[identifier]['_PrelinkExecutableLoadAddr']` to place the entry.
- Consequence: the two tools **re-address Apple's own entries**. There is no
  code path that appends one, so a driver that ships as a new kext bundle has no
  way in — the profile's `[kernel.prelink] roots` (`profile.toml:43`, 30
  identifiers) can only name entries that Apple already put there.

The storage line's ring 4 (`drivers/NativeUfs/Info.plist` + the `ld -kext`
recipe) produces a bundle that ring 5 must place. That is the only reason this
contract exists.

## Input

| Input | Shape | Who supplies it | Constraint |
| --- | --- | --- | --- |
| `entries` | the parsed `_PrelinkInfoDictionary` as the emitter reads it today (identifier → `{module, info plist, `_PrelinkExecutableLoadAddr`, filetype}`) | the existing emitter path, unchanged | must be treated as read-only input; the ring must not mutate it |
| `identifier` | `str`, the bundle's `CFBundleIdentifier` | the caller (profile / builder) | must not collide with an existing key; a collision is an error, never an override |
| bundle | path to the linked `MH_KEXT_BUNDLE` (filetype 11) | the device line's kext recipe | the ring does not link or sign anything; the file is given |
| `budget` | the `__PRELINK_TEXT` section: `vaddr`, `size`, `used`, `alignment` | the emitter's own segment accounting | the new entry must fit in `size - used` with the section's alignment; the ring reports the arithmetic it used, so a later failure is not "somewhere in 800 bytes" |

The budget is the only new concept: today nothing asks for space, because nothing
is ever added. It is an input rather than an output because the caller owns the
segment layout decision.

## Output

| Output | Shape | Meaning |
| --- | --- | --- |
| `load_address` | `UInt64` | the address the entry was placed at; written into the entry's `_PrelinkExecutableLoadAddr` |
| `size` | `UInt64` | bytes consumed in `__PRELINK_TEXT`: Mach-O header + load commands + segments + the `kmod_info` block, padded to the alignment |
| `kmod_info.name` | `str` | must equal the bundle's `CFBundleIdentifier`; the consumer compares it as identity, not decoration |
| `kmod_info.start` | `UInt64` | non-zero, inside an executable segment of the placed entry |
| `kmod_info.stop` | `UInt64` | non-zero, strictly greater than `start` |
| placement record | one structured line (identifier, address, size, remaining budget) | so the caller can log what happened and a checker can re-derive it |

These six are what `scripts/check-ufs27-storage-entry.py` already grades on the
receiving side: `name` is confirmed by content (the bytes at `_kmod_info + 0x10`
must start with the plist identifier), `start`/`stop` are read at `+0xA8`/`+0xB0`
and required non-zero and inside executable segments. The ring and that checker
must agree on the same three fields, or a green checker proves nothing.

## Failure semantics

1. **No partial insertion.** If any step fails, the emitted image must be
   byte-identical to the input: validate the identifier, the filetype 11, the
   budget, and all three `kmod_info` fields **before** writing anything.
2. **Error, not silence.** A refusal returns non-zero with a message naming the
   identifier and the reason (`no budget`, `collision`, `not a MH_KEXT_BUNDLE`,
   `kmod_info field unconfirmed`). An insertion that cannot be confirmed is a
   failure, not a warning: a kext placed at a wrong address is read as garbage
   with no diagnostic anywhere else.
3. **No synthesis of fields.** If `start`/`stop` cannot be derived from the real
   placement, the ring must refuse. (This is the same rule the Lead set for the
   bundle's `__kmod_info` at m01070 ②: `ld -kext`, never a hand-written section.)
4. **Determinism.** The same inputs must produce the same address and size, so the
   acceptance check can be re-run offline and give the same answer.

## What the storage line promises the ring

- the bundle is filetype 11 with `CFBundleIdentifier` == `org.blu-sharky.NativeUfs.Pong`
  (the kext recipe copies `drivers/NativeUfs/Info.plist`; `scripts/build-native-ufs-kext.sh`
  links it with `ld -kext`);
- the identifier does not collide with any of the 30 profile roots
  (`profile.toml:43`), verified by name;
- the driver does not need a load address of its own choosing — anything the
  budget allows is acceptable, so the ring owns the layout decision outright.

## What is still open, and who answers it

- Whether the added entry goes into the **original** `_PrelinkInfoDictionary`
  (so `emit_prelink_orig.py` writes it out) or is appended at emit time. Both work
  for the consumer; the first keeps one source of truth, the second keeps Apple's
  metadata untouched. Ring 5's owner decides.
- Whether the budget is taken from the profile or from the input kernel's
  `__PRELINK_TEXT` header. The storage line has no opinion; the contract only
  requires that the number used is reported.
- The `--fileset-reference` / `--allow-missing` arguments `profile.toml:40` passes
  to `kits/XnuPrelink/emit_prelink.py` are rejected by its parser
  (`emit_prelink.py:181-190`, executed: exit 2, `unrecognized arguments`). That is
  the same ring's front door and is recorded by the Lead as "27 prelink never ran"
  (m01070 ④) — it is not a storage-line fix.
