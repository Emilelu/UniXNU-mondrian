# F2 diagnostic flight — prediction written before the flight

Image: `/opt/k60/trees/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27/boot/boot.img`
sha256 `5c060f27d7188e0d4cc41c5c6c715e8106871bbf85f5a296292b0117d817a6b6`, 201,895,936 B.
Kernel `652237c6bf54` (0 loader violations), payload transform `8ae0ab4be80a`, FD `46cc97828139`.
Written 2026-11-21 09:14, before the flight. Authorised by the user as a diagnostic flight.

## What I expect, in order

1. `112 B shim -> FD -> DarwinBoot.efi` starts; the loader now accepts the fileset collection, so this
   stage is expected to pass where round-17d was refused.
2. ADT is parsed and handed to XNU; `arm_init` runs; `PE_init_iokit()` at `osfmk/kern/startup.c:689`
   is the first moment any kext code can run.
3. The USB CDC-ACM console appears (this is the moment a human can read anything).
4. The Data gate runs; with the stamped child subtype and 16 folded data pairings, I do not expect a
   prelink trap before this point.
5. Somewhere in the kext start-up order the image hits one of the 205 stubbed slots. The expected
   signature is `_unixnu_fileset_unmapped` panicking and printing `original component called an
   unmapped kernel function from <return address>`.

## What would make this flight worth it

- **PASS (informational)**: a console log of non-zero length that reaches at least `arm_init`, and
  either proceeds past the Data gate or panics with the stub naming a call site. Either outcome
  converts unknown addresses into measured ones.
- **FAIL (real defect)**: a console log that stops before the console comes up, or a panic whose text
  is not the stub (that would be a different, fixable bug).
- **INVALID**: a 0-byte log. That means the capture or the loader failed, and it teaches us nothing
  about the residue.

## What I will not do

No `fastboot flash`, no write to `/dev/block/sda38`, no change to the image after the fact. If the
flight is INVALID I re-run once with the same image before drawing any conclusion.
