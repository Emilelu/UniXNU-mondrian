# Why native_original_branches is empty on this branch

Status: offline investigation, 2026-11-21. Branch feat/xnu27-data-gate.
Inputs: the kit at /opt/k60/trees/ios27-fw/kits/XnuPrelink (HEAD
440589b0c31625f17edf363e24b3c82c51c70bb9), the stage-0 build configuration in
this repository, and the readable build-20 report fields quoted by the Lead.

## Short answer

The field is not a required input and it is not computed from the policy. It is
a record of the .original adapter branches the prelink actually rebound in the
native kernel. A branch is recorded only when the native kernel contains both
an absolute symbol named <target>.original and a matching BTI c; B stub. Our
stage-0 kernel contains no such symbols, so the emitter records an empty list.
The policy can still name two required branches because it describes the
upstream Sheng build, which links the legacy display and HID adapters. That is
a different native input set, not a kit defect and not a contradiction.

## 1. Where the field is written

The write point is unconditional. Every fileset emit calls the segmented
emitter, which calls the layout helper:

    /opt/k60/trees/ios27-fw/kits/XnuPrelink/fileset_emit.py:707
        from fileset_segmented import SegmentedEmit

    /opt/k60/trees/ios27-fw/kits/XnuPrelink/fileset_segmented.py:63-64
        self.original_branches = relocate_original_stubs(self.data, self.layout)
        self.report['native_original_branches_rebound'] = len(self.original_branches)

    /opt/k60/trees/ios27-fw/kits/XnuPrelink/fileset_emit.py:731-732
        'native_original_branches': emit.original_branches,

The helper itself is:

    /opt/k60/trees/ios27-fw/kits/XnuPrelink/fileset_layout.py:250-288
        def relocate_original_stubs(data, layout):
            names = native.symbols()
            for name, source in sorted(native.absolute_symbols().items()):
                if not name.endswith('.original'):
                    continue
                stubs = names.get(name[:-len('.original')], ())
                if len(stubs) != 1:
                    raise ValueError(...)
                ...
                if bti != 0xd503245f or branch & 0xfc000000 != 0x14000000:
                    raise ValueError(...)
                if stub + 4 + sign_extend(branch & 0x3ffffff, 26) * 4 != target:
                    raise ValueError(...)
                owners = layout.retained_code(...)
                if len(owners) != 1:
                    raise ValueError(...)
                ...
                result.append(dict(symbol=name[:-len('.original')],
                                   source=hex(source), target=hex(target),
                                   owner=owners[0]))
            return result

The important negative is before the first loop iteration: it scans only
native.absolute_symbols(), and only names ending in .original. If none exist,
the function returns [] without error. That is why the report has an empty
list rather than a failure.

The kit README states the contract at README.md:27: an adapter that calls
retained kext code uses a native BTI c; B stub and an N_ABS symbol named
<stub>.original at the fixed collection target; the emitter recomputes the
displacement and records the binding.

## 2. What creates a row

A row needs all of the following in the native kernel:

1. An absolute symbol whose name ends in .original, whose value is the fixed
   collection target.
2. A unique native code symbol with the same name minus .original, pointing at
   an 8-byte sequence BTI c; B <target>.
3. One retained owner for that stub in the output layout.

The source side is assembly, not a table. A minimal adapter is:

    .globl  <name>.original
    .set    <name>.original, <fixed-target>
    <name>:
        bti c
        b   <name>.original

Our repository contains no producer of such .original symbols. The only
in-tree binder that writes .globl/.set is scripts/bind-ios16-storage.py:65-68,
used by scripts/build-pong-ufs-probe-macos.py:93-98 for the iOS 16
IOBlockStorageDevice path. It emits plain symbols without the .original
suffix, so it cannot trigger relocate_original_stubs.

## 3. Why the upstream policy has values

The policy names exactly the two adapter families produced by Sheng's
build-gop-legacy-display-27.py:

    __ZN25IOMobileFramebufferLegacyC2EPK11OSMetaClass
    __ZN11IOHIDDevice10handleOpenEP9IOServicejPv

That builder emits the display adapters at
E:/hackios/UniXNU-sheng/scripts/build-gop-legacy-display-27.py:241-257:
for every display binding outside the DATA set it writes

    .globl <name>.original
    .set   <name>.original, <target>
    <name>:
        bti c
        b   <name>.original

It emits the HID adapters the same way at :472-483. HID_DATA contains only
__ZN11IOHIDDevice10gMetaClassE and __ZTV11IOHIDDevice; every other
IOHIDDevice binding, including handleOpen, gets the .original form.

The archive is assembled at :698-701 as
libNativeLegacyDisplay.late.a. It includes original-bindings.o,
original-addresses.o, the late display objects, LegacyDisplayProbe/Support,
KeyStore, and the input objects (hid-bindings.o, hid-addresses.o,
NativeHidInput.late.o, KeyboardCover, probes, board drivers). Linking that one
archive supplies both symbols the policy requires.

The policy is therefore a statement about a native build that links this
archive. It is not a statement that the prelink can invent a branch.

## 4. Why our kernel has none

The switch is off in the stage-0 configuration:

    configs/mondrian_ios27_defconfig:23
        CONFIG_XNU_NATIVE_LEGACY_DISPLAY=n

The surrounding comment at :16-22 says stage 0 stops at bsd_init and the
display belongs to F4. The two other board configs are also n:
configs/mondrian_defconfig:19 and configs/mondrian_wifi_defconfig:19.

The builder reads the switch at scripts/build-xnu-generic.sh:376:

    NATIVE_LEGACY_DISPLAY=${XNU_NATIVE_LEGACY_DISPLAY:-0}

and uses it at :676-690:

    if [ "$NATIVE_LEGACY_DISPLAY" = 1 ]; then
      LEGACY_DISPLAY_ARCHIVE=$ROOT/build/native-legacy-display/libNativeLegacyDisplay.late.a
      test -f "$LEGACY_DISPLAY_ARCHIVE"
      python3 - "$LEGACY_DISPLAY_ARCHIVE" "$ROOT" <<'PY_LEGACY_DISPLAY'
      ... archive_sha256 and source_sha256 checks ...
      PY_LEGACY_DISPLAY
      KERNEL_EXTRA_ARCHIVES="$KERNEL_EXTRA_ARCHIVES -Wl,-force_load,$LEGACY_DISPLAY_ARCHIVE"
      KERNEL_ARCHIVE_DEPENDENCIES="$KERNEL_ARCHIVE_DEPENDENCIES $LEGACY_DISPLAY_ARCHIVE"
    fi

With the switch n, the force_load branch is skipped. Even if it were on, the
archive is absent today:

    $ ls build/native-legacy-display
    ls: cannot access 'build/native-legacy-display': No such file or directory

and git ls-files in this repository contains no build-gop-legacy-display,
NativeLegacyDisplay, GopFramebuffer or HID source. It has only
patches/unixnu-core/legacy/k60-unixnu-core.patch, patches/xnu/0616-k60-init-legacy-helper.patch,
patches/xnu/offline-legacy-start.patch and scripts/legacy/README.md. The
repository cannot produce the archive on its own today.

The stage-0 kernel therefore has no .original names, relocate_original_stubs
returns [], and the report field is empty. This is the expected consequence of
the configuration, not evidence that the kit dropped a branch.

## 5. The LTO reference is not the missing input

The shared reference helper
k60-gates/scripts/build-k60-fileset-reference.py runs the framework reference
builder and then copies the carried LTO reference:

    :33-34  REFERENCE_RELATIVE and CARRIED_RELATIVE
    :78-86  shutil.copyfile(carried, final), rewrite detail['sha256'],
            record the provenance

It changes the symbol names available for matching in kernel.map.json. It does
not add anything to the native kernel. The relocator reads native.symbols() and
native.absolute_symbols(), so a richer reference cannot create a .original
symbol. Adding or improving the LTO reference will not make this field
nonempty.

## 6. What would make it nonempty

The one configuration line is:

    configs/mondrian_ios27_defconfig:23
    -CONFIG_XNU_NATIVE_LEGACY_DISPLAY=n
    +CONFIG_XNU_NATIVE_LEGACY_DISPLAY=y

That is sufficient only if a qualified archive already exists at
build/native-legacy-display/libNativeLegacyDisplay.late.a with the matching
build-report.json. The archive is the actual missing input. Without it the
same change stops at test -f at scripts/build-xnu-generic.sh:678.

A qualified archive must contain both the display and HID .original symbols,
not only the display constructor. Sheng's archive does; a display-only archive
would make the field nonempty but would still fail the policy's second
required branch.

The archive producer is not in this repository. The only concrete generator
found in the reference trees is Sheng's
scripts/build-gop-legacy-display-27.py; producing an equivalent archive is a
separate task.

## 7. Consequences for the 24A446 policy

The policy's two required_original_branches are useful as an upstream parity
check, but they cannot be satisfied by this stage-0 build:

- They are not unresolved references that the prelink stubs by default. They
  are adapter branches that exist only when the adapter archive is linked.
- An empty native_original_branches is not a regression against a previous
  state of this branch; it is the same zero that the current configuration
  produces.
- A checker must distinguish missing required branches (our native build does
  not carry the adapters) from a prelink that failed to rebind a branch that
  was present. The first is a configuration gap; the second is a kit or input
  error.

Until the adapter archive is part of the build, the policy should report the
two names as absent from the native input, not as a prelink rebinding failure.
That keeps the failure attributable to the missing input instead of the
emitter.

## 8. Kernel-to-kext paths: absolute branches versus hooks

This is a baseline table, not a new probe. It separates the one mechanism the
kit records from the hook that exists today and from the reverse direction, so
a future patch can be classified before the policy is edited.

The current record has **zero absolute branches** and one explicit hook. The
generic `OSKext::start` -> `startfunc` dispatch that starts every prelinked
kext is deliberately out of scope: it is the loader's normal entry and carries
no per-kext policy decision. Counting it would make every kext look like an
exception. The reverse direction is also not a kernel-to-kext path: the 205
stubbed slots are held by kexts and point at kernel functions.

| # | Path | Direction | Mechanism | Today | Policy effect |
| --- | --- | --- | --- | --- | --- |
| 1 | `OSKext::start` -> AMFI early security initializer | kernel -> kext | **hook**: reads the `_NativePrelinkEarlySecurityInit` property and calls the address indirectly | present; one initializer at `profiles/os/ios-27.0.1-24A446/profile.toml:39`, call site `patches/xnu/zzzzzzzzzzzzzzzzzzzzzzzzzzzzzz-pong-prelink-security-init.patch:47` and `:72-74` | not recorded in `native_original_branches`; no `required_original_branches` entry |
| 2 | kernel -> `__ZN25IOMobileFramebufferLegacyC2EPK11OSMetaClass` | kernel -> kext | **absolute branch**: native `.original` symbol plus a `bti c; b` stub to a retained target | absent; `configs/mondrian_ios27_defconfig:23` is `n` and the archive is not linked | if a patch adds it, `native_original_branches` must become non-empty; this is the first upstream required name |
| 3 | kernel -> `__ZN11IOHIDDevice10handleOpenEP9IOServicejPv` | kernel -> kext | **absolute branch**: same `.original` and `bti c; b` shape | absent; the HID adapter is in the same missing archive (`E:/hackios/UniXNU-sheng/scripts/build-gop-legacy-display-27.py:472-483`) | same; this is the second upstream required name |
| 4 | kext -> kernel function pointer slots | kext -> kernel | `__auth_got` and `__const` slots | 205 references over 131 targets; see `E:/hackios/k60-gates/docs/research/ios27/PRELINK-RESIDUE.md:7-17` | reverse direction; belongs to the missing/stubbed policy, never to `native_original_branches` |

The two absent rows are the only absolute branches the upstream policy names. Their
source is Sheng's `libNativeLegacyDisplay.late.a`: display adapters at
`E:/hackios/UniXNU-sheng/scripts/build-gop-legacy-display-27.py:241-257`, HID
adapters at `:472-483`, archive at `:698-701`. Our switch and archive facts are
in sections 4 and 6 above. The hook row is the path the Lead's residue note
calls "the only kernel-to-kext path today" (`E:/hackios/k60-gates/docs/research/ios27/PRELINK-RESIDUE.md:63-66`).

Classification rule for a future patch:

- A patch that adds a `.original` absolute symbol and a `bti c; b` stub is an
  absolute branch. Update `required_original_branches`, expect
  `native_original_branches` to become non-empty, and add its row here first.
- A patch that looks up a property or function pointer and calls it indirectly
  is a hook. It does not populate `native_original_branches`; record it in the
  hook row instead of adding a required branch.
- A patch that adds a `__auth_got` or `__const` slot from a kext to a kernel
  function is the reverse direction. It belongs to the missing/stubbed table,
  not to this one.
- If a patch introduces an absolute branch but the list stays empty, that is a
  rebinding failure, not a configuration gap. The two cases must stay separate.

## 9. Limits

This note does not claim that the display or HID adapter is required for
stage 0, that the Sheng archive is licensed for reuse, or that enabling the
switch is safe before F4. It also does not change the kit, the policy, the
shared tree or the board configuration. It only locates the write point, the
trigger and the missing input, so the next change can be one line plus one
qualified archive.
