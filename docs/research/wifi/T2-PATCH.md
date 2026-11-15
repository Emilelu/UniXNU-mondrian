# T2 patch: put the PWF2 firmware container in `__DATA` instead of `__TEXT`

**Status: prepared, not applied, not built.** Written 2026-11-15 at the Lead's
request (reply of 2026-11-15, item 2) so the fix is ready if the T0 control
image `wifi-20261115z0` comes back silent. Applying it is a decision for the
Lead after T0 reports; nothing here runs on its own and it is deliberately
**not** part of `patches/wifi/series`.

Rationale, measurements and the falsification logic live in
`docs/research/wifi/BOOT-DEATH-SUSPECT.md` §2 (S1) and §4.

## 1. What it changes

One line in `scripts/build-k60-wifi-native.py`: the assembler emission for
`PongWifiFirmware.s` declares the 11,189,974-byte PWF2 container in
`__TEXT,__const`; T2 declares it in `__DATA,__const`. Nothing else changes —
no C code, no linker script, no board file, no boot argument.

| | before (z0 / mhi5) | after (t2) |
|---|---|---|
| section in the emitted `.s` | `__TEXT,__const` | `__DATA,__const` |
| `__TEXT` vmsize | 0xc64000 (12.4 MiB) | ≈ 0x1a8f00 (1.7 MiB, matches the images that boot) |
| `__TEXT,__const` | 0xb38ed6 (11.2 MiB) | ≈ 0x8d000 (the kernel's own constants) |
| `__DATA` filesize | 0x3130000 (49.2 MiB) | ≈ 0x3c68ed6 (60.4 MiB) |
| kernel file bytes | 117,305,344 | same ± segment padding (well under the 128 MiB read cap) |
| image span | 123.6 MB | unchanged (bytes move between segments) |

The consumer needs no change: `drivers/PongWifi/PongWifiPlatform.cpp:35`
declares `extern const uint8_t pong_wifi_firmware[]` and `fwGet()`
(`:554-556`) only does `*data = pong_wifi_firmware + off`. Section
placement is invisible to it.

## 2. The patch (applies to `feat/wifi-bringup`; last re-checked at 79a8f06)

```diff
diff --git a/scripts/build-k60-wifi-native.py b/scripts/build-k60-wifi-native.py
index cbd2eb6..6a1b84f 100644
--- a/scripts/build-k60-wifi-native.py
+++ b/scripts/build-k60-wifi-native.py
@@ -99,7 +99,7 @@ def main():
   for name,off,size,_ in entries:f.write(struct.pack('<32sII',name,off,size))
   for _,off,size,path in entries:
    f.seek(off);f.write(path.read_bytes())
- asm=out/'PongWifiFirmware.s';asm.write_text('.section __TEXT,__const\n.p2align 12\n.globl _pong_wifi_firmware\n_pong_wifi_firmware:\n.incbin "'+str(pack)+'"\n.globl _pong_wifi_firmware_end\n_pong_wifi_firmware_end:\n')
+ asm=out/'PongWifiFirmware.s';asm.write_text('.section __DATA,__const\n.p2align 12\n.globl _pong_wifi_firmware\n_pong_wifi_firmware:\n.incbin "'+str(pack)+'"\n.globl _pong_wifi_firmware_end\n_pong_wifi_firmware_end:\n')
  framework=a.tree/'.cache/fakeroot/System/Library/Frameworks/Kernel.framework/Versions/A'
  env=dict(os.environ,DEVELOPER_DIR=str(pong_paths.developer_dir()))
  sdk=subprocess.check_output(['xcrun','--sdk','iphoneos','--show-sdk-path'],env=env,text=True).strip()
```

The `index` line names the blob at `feat/wifi-bringup` and the mode is the
mode git records for that path, `100644` — the script is executable on disk
but not in the tree, and a header that claims `100755` makes `git apply`
print a mode warning on every run.

Both `git apply --check` and `git apply --check -R` were run on a throwaway
copy of the file on 2026-11-15, so it applies and reverts cleanly as long as
`scripts/build-k60-wifi-native.py` has not moved.

If it no longer applies, the change is one substitution and can always be
done directly:

```sh
cd /mnt/e/hackios/k60-wifi
python3 - <<'PY'
p='scripts/build-k60-wifi-native.py'
s=open(p).read(); assert s.count('.section __TEXT,__const')==1
open(p,'w').write(s.replace('.section __TEXT,__const','.section __DATA,__const'))
PY
```

## 3. Apply and revert

Apply (normally only after T0 reports silent, and only with the Lead's go):

```sh
cd /mnt/e/hackios/k60-wifi
git apply --check <<'PATCH' && git apply <<'PATCH'
<paste the diff from §2>
PATCH
```

Revert — one command, restores the tracked file exactly:

```sh
cd /mnt/e/hackios/k60-wifi && git checkout -- scripts/build-k60-wifi-native.py
```

The revert must happen **after** the t2 archive is produced; the archive keeps
the placement, the script does not.

## 4. Build recipe for `wifi-20261116t2`

`build-strict.sh` does not run `build-k60-wifi-native.py`; it consumes the
archive through `XNU_PONG_WIFI_ARCHIVE`. So T2 is two steps: rebuild the
native archive from the patched script, then the usual strict build.

```sh
# 1 — patched script -> new native archive
cd /mnt/e/hackios/k60-wifi
T=/opt/k60/trees/k60build/out-wifi/mondrian/ipados-16.6.1-20G81/mondrian/tree
export PONG_SHENG_ROOT=/mnt/e/k60-work/impl/wifi/work/src/UniXNU-sheng
export UNIXNU_SDKROOT=$T/.cache/fakeroot UNIXNU_SDK_VERSION=17.0
python3 scripts/build-k60-wifi-native.py \
  --tree $T \
  --ath11k /opt/k60/trees/k60build/wifi/ath11k-mhiboot/libPongAth11k.a \
  --firmware /mnt/e/k60-work/firmware/qca6490-wifi-bdf \
  --output-dir /opt/k60/trees/k60build/wifi/native-t2

# 2 — strict image, same template as z0, only the archive path changes
export K60_OUT=/opt/k60/trees/k60build/out-wifi
export K60_DEVICE_INPUT=/opt/k60/trees/k60-wifi-device
export PONG_NATIVE_DRIVER_SOURCE=/opt/k60/trees/k60-wifi-device
export XNU_PONG_WIFI=1
export XNU_PONG_WIFI_ARCHIVE=/opt/k60/trees/k60build/wifi/native-t2/libPongWifiNative.a
export JOBS=4 PYTHONIOENCODING=utf-8 K60_AGENT_ID=wifi-agent
bash scripts/build-strict.sh wifi-20261116t2 \
  --fd /mnt/e/k60-work/artifacts/fd/wifi-20261114e-cf4485712c29.fd \
  --kernel-arg pong_wifi=0
```

`pong_wifi=0` is deliberate: T2 asks whether the **blob's placement** kills
the boot, so the driver must stay out of the comparison exactly as in z0.
A `pong_wifi=1` t2 image is a later step, after placement is cleared.

Prerequisite: the kernel must be relinked, not reused. `kernel.py` only
compares `kernel.macho` against a marker, not against the archive
(that is how mhi3/mhi4 flew a stale kernel), so either
`mv $M/kernel/kernel.macho $M/kernel/stale/` or confirm from the log that
the linker actually ran.

### 4.1 One-command runner (guarded, refuses to run on the wrong day)

The whole of §4 is wrapped in `/mnt/e/k60-work/scratch/run-t2.sh`
(`bash -n` clean). It refuses to start unless three things hold, which is
exactly the condition the Lead attached to the authorisation:

1. `/mnt/e/k60-work/artifacts/wifi-20261115z0/build-manifest.json` still
   says `series.count = 224` and `series.sha256 = 34cf51e4…`;
2. the diff in §2 still passes `git apply --check` against the current HEAD;
3. the patch is applied only for the duration of the native archive build —
   a shell `trap` reverts `scripts/build-k60-wifi-native.py` on exit, so the
   worktree cannot be left dirty even if the build fails.

It also moves `kernel.macho` into `kernel/stale/` before the strict build, so
the linker cannot be skipped (the mhi3/mhi4 confound), and prints the archive's
`PWF2` count so a wrong placement is visible before the image is built.

The verdict word from `scripts/judge-wifi-boot.py` is a precondition the
script cannot check — it is read from the printed line, not from the exit code.

## 5. Verify the image before anyone flies it

### 5.0 The one table to hold against the built image

z0 (`wifi-20261115z0`) is measured; t2 is arithmetic from z0's own section
sizes — the container is 11,189,974 bytes (`_pong_wifi_firmware_end` −
`_pong_wifi_firmware`), and it is the only thing that moves. Every t2 number
below is therefore exact modulo section alignment; the tolerance column says
how much alignment may add.

| what | z0 measured | t2 expected | tolerance |
| --- | --- | --- | --- |
| `__TEXT` vmsize/filesize | 12,992,512 (0xc64000) | 1,802,538 (0x1b812a) | ±0x2000 (section padding) |
| `__TEXT,__const` size | 11,767,510 (0xb38ed6), fileoff 8,192 | 577,536 (0x8d000) | ±0x1000 |
| `__DATA` filesize | 51,576,832 (0x3130000) | 62,766,806 (0x3bdcd6) | ±0x2000 |
| `PWF2` first hit | file offset 585,728 (0x8f000), inside `__TEXT,__const` | inside the `__DATA` file range [22,773,760, +62,766,806) | must not hit `__TEXT` at all |
| payload kernel bytes | 117,305,344 | 117,305,344 | ±0x10000; bytes must differ |
| `components.payload_kernel` | `ec094bc952930d30f5b18ee43a1e19e0d06898309ec46e80e43121595498ce22` | a different sha256 | must differ from z0 |
| `series` | 224 / `34cf51e4…` | 224 / `34cf51e4…` | must be identical |

Self-check, from the same manifest, before the image is flown:
`kernel_args_requested` must read `["pong_wifi=0"]`, not `[""]` and not an
empty list. `cellular-l3-20261114d` recorded `[""]` and flew without its
`pong_modem=2`, which is why this line is checked rather than assumed (P-159).
`run-t2.sh` and `run-mhi5.sh` assert it on the manifest they just wrote.
Do not trust "it built". Three checks, all offline, all cheap:

1. **Segment table** — extract the payload kernel from the boot image and dump
   its segments (the `@@557056` offset is the ramdisk slot in the Android v4
   header; it is constant for every image on this line):

   ```sh
   mcopy -o -i <boot.img>@@557056 ::/EFI/UniXNU/Payloads/kernel.macho /tmp/k.macho
   python3 - /tmp/k.macho <<'PY'
   import struct,sys
   b=open(sys.argv[1],'rb').read(); n=struct.unpack_from('<I',b,16)[0]; off=32
   for _ in range(n):
       cmd,size=struct.unpack_from('<II',b,off)
       if cmd==0x19:
           name=b[off+8:off+24].rstrip(b'\\x00').decode()
           vm,vs,fo,fs=struct.unpack_from('<QQQQ',b,off+24)
           if name in ('__TEXT','__DATA'):
               ns=struct.unpack_from('<I',b,off+64)[0]; p=off+72; secs=[]
               for _ in range(ns):
                   sn=b[p:p+16].rstrip(b'\\x00').decode()
                   if sn in ('__const','__cstring','__data'): secs.append((sn,hex(struct.unpack_from('<Q',b,p+40)[0])))
                   p+=80
               print(name,hex(vm),hex(fs),secs)
       off+=size
   print('filesize',len(b))
   PY
   ```

   Expected: the `__TEXT` / `__const` / `__DATA` rows of the table in
   §5.0, within their tolerance columns. The earlier draft of this section
   quoted "≈ 0x1a4000–0x1b0000" for `__TEXT`; that figure came from the
   kernels that carry no WiFi archive at all, and it is 82,218 bytes short of
   what z0's own sections imply. Use the table.
2. **Blob location** — `strings -a` / byte search for `PWF2` must now hit
   inside the `__DATA` file range only; the `__TEXT` range must contain no
   `PWF2`.
3. **Identity** — `build-manifest.json` must show `series.count = 224`,
   the same series sha256 (`34cf51e4…`), the usual gates
   (`kernel archives 4/4`, `image-arg-audit OK`, `verify-boot-image OK`),
   and a `components.payload_kernel` that differs from z0's
   `ec094bc952930d30f5b18ee43a1e19e0d06898309ec46e80e43121595498ce22`.
   Kernel identity is the manifest's `payload_kernel`, never
   `boot.json`'s `kernel_sha256` (P-200).

## 6. Risks and fallbacks

- **Linker rejects the section name.** `__DATA,__const` is legal Mach-O but
  unusual; the proven pairing on this board is `__DATA,__data` (the 51 MB
  Metal blob, `scripts/gen-k60-metal-blob.py:109-119`, boots in
  `gpu-20261114t`). If `ld` complains, change the substitution to
  `.section __DATA,__data` — same effect, proven layout, only loses
  read-only-ness of those pages (harmless: `fwGet()` never writes).
- **Kernel file grows past 128 MiB.** It should not: bytes move, they are not
  added. If it does, `DarwinBoot.c:699` (`ReadFile (Root, ...,
  SIZE_128MB, ...)`) rejects the image outright — check the kernel byte count
  in the build log before flying.
- **Nothing changes on the device.** If t2 is silent too, S1 is falsified and
  the next suspect is the loader's pool/window interaction
  (`DarwinBoot.c:558` AllocatePool of the whole image, `:607` the
  contiguous window, `:656` FreePool), which is `uefi-mondrian` work, not
  this line's.

## 7. Explicitly out of scope

- The PWF2 header defect recorded in `BLOB-RESIDENCY.md` (header says 6
  entries, only `entry[0]` is usable, `m3.bin`/`regdb.bin` cannot be found
  at runtime) is a separate bug; T2 does not touch it. Fix the header or the
  lookup table after placement is settled.
- Compressing the container (`gzip -9` takes 11,189,974 B to 5,213,677 B)
  would shrink `__TEXT` too, but it adds a decompressor on the boot path.
  Not part of T2; only relevant if the 11 MB residency itself, rather than the
  segment, turns out to be what matters.