# Function pairing consumption: four reviewed entries

Date: 2026-11-21
Branch: feat/cellular-k55
Scope: offline review of `fileset_emit.py` and the stage-0 prelink map. No map
write, no tool change, no build, no device, no fastboot. Kit root:
`/opt/k60/trees/ios27-fw/kits/XnuPrelink`.

Inputs: `kernelcache.decompressed` sha256
`fa07057b...`, native `mach.development.bcm2837.unstripped.noctf` sha256
`b13875da...`, and the existing
`/opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/kernel/kernel.map.json`
(16,899 functions, 797 data). The existing report is 3 missing and 205 stubbed
items. The four proposed targets are absent from both map tables, so this is an
additive test, not an edit of an existing row.

## 1. Does the later data update overwrite the four function pairs?

No. `fileset_emit.py:697` builds the pair table from `payload['functions']`,
then `fileset_emit.py:698` applies `payload['data']` with `pairs.update(...)`.
The update order matters: on an identical target key the data value would win,
because it is written last. But the four target keys
(`0xfffffff00b0de068`, `0xfffffff00ad05978`, `0xfffffff00b416214`,
`0xfffffff00b41624c`) are present in neither the 797-entry data table nor the
16,899-entry functions table. There is therefore no duplicate for the data
update to touch. `fileset_emit.py:706` then adds `collection_slide` to every
key; the stage-0 report has `collection_slide=0`, so the keys remain the four
output addresses. Existing function keys are not deleted, renamed, or merged;
the only overwrite path is a data row with the same key, and none of the four
has one. This is an additive change at the only point where the emit path
composes its input pairs.

## 2. Does a changed matcher signature force a rebuild or reject the map?

The signature is not a hash of the map contents. `fileset_match.py:19-25`
hashes `fileset_match.py`, `kc_image.py`, `fileset_shape.py` and the
`fileset-*-symbols.json` fixtures. `fileset_names.py:35-38` selects that
matcher signature for this map (the map is not a `method="symbol-names"` map).
Adding four function entries therefore does not change
`expected_signature(payload)` and does not invalidate the map. The two read
paths differ:

* With `--fileset-map`, `emit_prelink.py:338-345` loads that exact file,
  runs `validate_map`, and checks `matcher_version` plus
  `matcher_signature == expected_signature(pairing)`; a mismatch is
  `parser.error(...)`, not a silent rebuild.
* Without `--fileset-map`, `emit_prelink.py:348-357` reuses the cached
  `<output>.map.json` only when validation, version, signature and
  `reference_sha256` all match. If any check fails, `pairing` stays `None`
  and `emit_prelink.py:358-365` regenerates with `match_by_names` or
  `match_images` and overwrites the map. `fileset_emit.py:692-693` repeats
  the version/signature guard inside `emit_images`.

So changing the four map rows does **not** force a rebuild. Changing the
matcher code or fixtures does: an explicit map is rejected, while the
cache path regenerates. Editing only the `matcher_signature` field to a value
that does not match the code/fixtures is rejected by both paths; it is never
silently mixed with the old pairs.

## 3. Does the four-entry addition change missing=3 or the 205 stubs?

It leaves `missing` at 3 and **does change** the stubbed set. In
`fileset_segmented.py:18-32`, `rebind` first takes a site override, then
`self.pairs.get(target)`. If a pair exists, it returns the native address and
neither counter is touched. Only when no pair exists does it test
`target in self.old_starts`: a function start becomes `stubbed` and gets the
panic stub; anything else becomes `missing`. `stubbed` and `missing` are
mutually exclusive branches; a stubbed target is not a missing target.

I ran `emit_images` twice in memory with the same 30 roots and AMFI
initializer, once with the map as-is and once with exactly the four pairs added
to a copy of the payload (no map file written). The first run reproduces the
existing missing/stubbed counts (3/205), which is the control:

| map | missing | stubbed items | owner-target pairs |
|---|---:|---:|---:|
| as-is | 3 | 205 | 203 |
| + four function pairs | 3 | 201 | 199 |
| delta | 0 | -4 | -4 |

Each of the four targets had one stubbed item; after the addition each is 0
stubbed and 0 missing. The 203 is the sum of `len(targets)` over the
owner-keyed `stubbed` report, not the 131 unique target addresses: several
targets are shared by multiple bundles. The three missing entries are the two
`__DATA` zero-fill references and the `__PRELINK_TEXT` leaf, none of which is
a function start reached by this branch; adding function pairs cannot move
them. The change is therefore not inert: it removes four panic-stub sites and
changes the candidate image hash, while the 3 missing references remain.

## Conclusion

**结论：接入是安全的。**

It is safe at the map-consumption layer: no existing key is overwritten, the
signature stays valid, and the emit path accepts the four native symbols. It is
not "no effect": the stubbed count becomes 201, the owner-target count becomes
199, and `missing` stays 3. It does not close `prelink-map-unresolved`;
201 stubbed items and the same three missing references remain.
