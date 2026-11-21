#!/usr/bin/env python3
"""Check the F1 artifacts after a build, with no board attached.

`unixnu build kernel`, `build payload` and `bootimg` each verify what they
produce, but nothing checks the set afterwards: that the payload still carries
the kernel the kernel step linked (after the transforms the repository declares
and no others), that the ADT still pins /chosen/random-seed (a random seed turns
one boot in three into a pmap_map_bd death), that the identity the profile
promises is the one in the tree, and that boot.img holds the firmware volume and
the payload byte for byte. Each of those fails silently in a rebuild, so they
are asserted here.

    python3 scripts/check-ios27-artifacts.py ~/ios27-out/mondrian/ios-27.0.1-24A446/mondrian_ios27

The board directory defaults to $UNIXNU_OUT/mondrian/<profile>/<config> when the
variable is set. Exits nonzero and prints `error: ...` on the first broken
invariant.
"""
import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import tomllib
import zlib
from pathlib import Path

MH_MAGIC_64 = 0xFEEDFACF
CPU_TYPE_ARM64 = 0x0100000C
CPU_SUBTYPE_ARM64E = 2
MH_EXECUTE, MH_FILESET = 2, 12
MH_NOUNDEFS, MH_PIE = 0x1, 0x200000
MH_DYLIB_IN_CACHE = 0x80000000
LC_BUILD_VERSION = 0x32
LC_FILESET_ENTRY = 0x80000035
PLATFORM_IOS = 2
FD_BYTES = 0x300000
FIRMWARE_BLOCKER = 'firmware-fileset-provider'
REQUIRED_BLOCKERS = frozenset({FIRMWARE_BLOCKER, 'loader-rejects-fileset', 'prelink-map-unresolved'})
FAT_KERNEL = '::/EFI/UniXNU/Payloads/kernel.macho'
FAT_ADT = '::/EFI/UniXNU/Payloads/kernel.macho.adt'
# The one tool the payload step runs on the kernel copy (scripts/unixnu/payload.py:188-191).
TOOL = Path(__file__).resolve().parent / 'patch-armcpu-validate.py'


class Failure(Exception):
    pass


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(data):
    """The same hash for bytes that are already in memory.

    Two call sites want this: the replayed transform and each FAT member. Passing
    bytes to sha256() were an AttributeError waiting for the first image that got
    far enough to print it.
    """
    return hashlib.sha256(data).hexdigest()


def macho(path):
    """Header and, for an executable, LC_BUILD_VERSION of the thin arm64e kernel.

    The kernel step writes MH_EXECUTE before the prelink and MH_FILESET after
    it; the fileset container carries platform 0 / minos 0 and holds the
    version in its members, so only the executable form is checked for those.
    """
    data = path.read_bytes()
    magic, cputype, cpusubtype, filetype, ncmds, sizeofcmds, flags, _ = struct.unpack_from('<8I', data, 0)
    if magic != MH_MAGIC_64:
        raise Failure(f'{path.name}: magic {magic:#x}, not MH_MAGIC_64')
    if cputype != CPU_TYPE_ARM64:
        raise Failure(f'{path.name}: cputype {cputype:#x}, not arm64')
    if cpusubtype & 0x00FFFFFF != CPU_SUBTYPE_ARM64E:
        raise Failure(f'{path.name}: cpusubtype {cpusubtype & 0xFFFFFF}, not arm64e')
    if filetype not in (MH_EXECUTE, MH_FILESET):
        raise Failure(f'{path.name}: filetype {filetype}, neither MH_EXECUTE nor MH_FILESET')
    entries = 0
    pos, build = 32, None
    for _ in range(ncmds):
        cmd, size = struct.unpack_from('<II', data, pos)
        if cmd == LC_BUILD_VERSION:
            platform, minos, sdk = struct.unpack_from('<3I', data, pos + 8)
            build = (platform, minos, sdk)
        elif cmd == LC_FILESET_ENTRY:
            entries += 1
        pos += size
    if filetype == MH_FILESET:
        if not entries:
            raise Failure(f'{path.name}: MH_FILESET with no LC_FILESET_ENTRY')
        return len(data), flags, f'MH_FILESET, {entries} entries'
    for name, bit in (('NOUNDEFS', MH_NOUNDEFS), ('PIE', MH_PIE)):
        if not flags & bit:
            raise Failure(f'{path.name}: MH_{name} is not set')
    if build is None:
        raise Failure(f'{path.name}: no LC_BUILD_VERSION')
    platform, minos, sdk = build
    if platform != PLATFORM_IOS:
        raise Failure(f'{path.name}: platform {platform}, not iOS')
    for label, value in (('minos', minos), ('sdk', sdk)):
        if value >> 16 != 27:
            raise Failure(f'{path.name}: {label} {value >> 16}.{value & 0xFFFF}, not 27.x')
    return len(data), flags, 'MH_EXECUTE'


SEGMENT_CMD = 0x19
UNIXTHREAD_CMD = 5


def segments(data, at):
    """The LC_SEGMENT_64 list of one header, read the way the loader reads it."""
    ncmds, sizeofcmds = struct.unpack_from('<II', data, at + 16)
    pos, end, found = at + 32, at + 32 + sizeofcmds, []
    for _ in range(ncmds):
        if pos + 8 > end:
            break
        cmd, size = struct.unpack_from('<II', data, pos)
        if cmd == SEGMENT_CMD and size >= 72:
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from('<QQQQ', data, pos + 24)
            initprot, = struct.unpack_from('<I', data, pos + 60)
            if vmsize:
                found.append({'address': vmaddr, 'size': vmsize, 'fileoff': fileoff,
                              'filesize': filesize, 'protection': initprot})
        pos += size
    return found


def entry_pc(data, at):
    """The LC_UNIXTHREAD program counter of one header, or None."""
    ncmds, = struct.unpack_from('<I', data, at + 16)
    pos = at + 32
    for _ in range(ncmds):
        cmd, size = struct.unpack_from('<II', data, pos)
        if cmd == UNIXTHREAD_CMD and size >= 288:
            return struct.unpack_from('<Q', data, pos + 272)[0]
        pos += size
    return None


def loader_contract(path):
    """Check the collection against what the loader compares, not against taste.

    `DarwinBoot.c` (the catalog pin `3c75734`, and the vendored copy after the
    same rule) accepts a fileset collection and then, for the entry named
    `com.apple.kernel`, requires three things besides the entry being covered by
    a parent segment:

        member filetype == MH_EXECUTE
        member cpusubtype == the collection's cpusubtype, bit for bit
        member flags & MH_DYLIB_IN_CACHE

    Apple's own 24A446 collection satisfies all three: 305 entries, every child
    header at 0xc0000002, `com.apple.kernel` at 0x80200001. On 2026-11-20 ours
    satisfied two of the three -- 31 of 32 children at 0xc0000002 but
    `com.apple.kernel` at 0x80000002 -- so the loader refused the image before
    the ADT or XNU ran. That is a defect in our collection, not in the loader,
    which is why this is a conformance check and not a relax-the-guard patch.

    Three more clauses come from the same function: the indexed header must sit
    at the VA its entry advertises, the member's entry PC must equal the
    collection's, and every member segment must be covered by a parent segment
    with matching protection and the file-offset relation
    `child.fileoff == parent.fileoff + child.address - parent.address`. Those
    are checked here too, because a loader that accepts the header and then maps
    the wrong segments fails later and looks like a kernel bug.

    Note what the fourth clause does *not* establish: Apple's own 24A446
    kernelcache fails it (`com.apple.kernel` entry 0xffffffe00eb1c000 against the
    collection's 0xfffffff00b42c000), while our stamped collection passes it.
    So entry equality is this loader's own stricter rule, not an Apple
    invariant, and the gate checks the rule our loader implements -- which is
    the rule that decides whether *our* image boots.
    """
    data = path.read_bytes()
    _, _, outer_subtype, filetype, ncmds, _, _, _ = struct.unpack_from('<8I', data, 0)
    if filetype != MH_FILESET:
        return {'conformant': True, 'violations': [], 'note': 'MH_EXECUTE, no children to compare'}
    pos, violations, entries = 32, [], 0
    outer_segments = segments(data, 0)
    outer_entry = entry_pc(data, 0)
    for _ in range(ncmds):
        cmd, size = struct.unpack_from('<II', data, pos)
        if cmd == LC_FILESET_ENTRY:
            entry_vmaddr, fileoff = struct.unpack_from('<QQ', data, pos + 8)
            entry_id, = struct.unpack_from('<I', data, pos + 24)
            name_at = pos + entry_id
            name = data[name_at:data.index(b'\0', name_at)].decode('utf-8', 'replace')
            entries += 1
            child_subtype, = struct.unpack_from('<I', data, fileoff + 8)
            child_type, = struct.unpack_from('<I', data, fileoff + 12)
            child_flags, = struct.unpack_from('<I', data, fileoff + 24)
            # Every indexed header must be loaded at the VA the entry claims, or
            # XNU would map a header that is not where the entry says it is.
            covered = any(
                fileoff >= parent['fileoff']
                and fileoff - parent['fileoff'] <= parent['filesize']
                and 32 <= parent['filesize'] - (fileoff - parent['fileoff'])
                and entry_vmaddr == parent['address'] + fileoff - parent['fileoff']
                for parent in outer_segments)
            if not covered:
                violations.append(f'{name}: header 0x{fileoff:x} is not covered by any '
                                  f'parent segment at 0x{entry_vmaddr:x}')
            if name == 'com.apple.kernel':
                if child_type != MH_EXECUTE:
                    violations.append(f'{name}: filetype {child_type}, not MH_EXECUTE')
                if child_subtype != outer_subtype:
                    violations.append(
                        f'{name}: cpusubtype {child_subtype:#010x} does not equal the '
                        f'collection {outer_subtype:#010x}')
                if not child_flags & MH_DYLIB_IN_CACHE:
                    violations.append(f'{name}: MH_DYLIB_IN_CACHE is not set')
                member_entry = entry_pc(data, fileoff)
                if member_entry != outer_entry:
                    violations.append(
                        f'{name}: entry {member_entry if member_entry is None else hex(member_entry)}'
                        f' does not equal the collection entry '
                        f'{outer_entry if outer_entry is None else hex(outer_entry)}')
                for child in segments(data, fileoff):
                    if not any(
                            child['address'] >= parent['address']
                            and child['address'] - parent['address'] <= parent['size']
                            and child['size'] <= parent['size'] - (child['address'] - parent['address'])
                            and (child['protection'] & ~parent['protection']) == 0
                            and (child['filesize'] == 0
                                 or (child['address'] - parent['address'] <= parent['filesize']
                                     and child['filesize'] <= parent['filesize'] - (
                                         child['address'] - parent['address'])
                                     and child['fileoff'] == parent['fileoff'] + child['address']
                                     - parent['address']))
                            for parent in outer_segments):
                        violations.append(f'{name}: segment 0x{child["address"]:x}'
                                          f'+0x{child["size"]:x} is not covered by a parent')
        pos += size
    note = (f'{entries} entries, collection cpusubtype {outer_subtype:#010x}, '
            f'{len(violations)} loader violation(s)')
    return {'conformant': not violations, 'violations': violations, 'note': note}


def packed_kernel_expected(kernel, report, directory):
    """What the payload step must have written into EFI/UniXNU/Payloads/kernel.macho.

    The kernel step's own output is the linker's, and the payload step copies it
    and then runs the tools the repository declares against the copy: today
    `patch-armcpu-validate.py` (AppleARMPlatform's _validateConfiguration()
    only accepts an Apple device tree). That is a real byte difference, so
    "payload kernel == kernel/kernel.macho" is the wrong invariant -- round 17
    failed on it while producing exactly the declared image (P-277).

    The right invariant keeps the transform honest: apply the same tool to a
    temporary copy of the linker's output and require the FAT member to match
    *that* byte for byte. Nothing is exempted by offset or by count, so a
    second edit, a stale copy or a half-applied patch still fails.
    """
    expected = directory / 'kernel.expected.macho'
    shutil.copyfile(kernel, expected)
    record = json.loads(report.read_text())
    linker = record.get('kernel_sha256')
    if linker != sha256(kernel):
        raise Failure(f'payload.json records kernel_sha256 {linker}, but kernel/kernel.macho '
                      f'is {sha256(kernel)}: the payload was built from a different kernel')
    tool = TOOL
    if not tool.is_file():
        raise Failure(f'no {tool.name} in this checkout, so the payload transform cannot be reproduced')
    done = subprocess.run([sys.executable, str(tool), str(expected), '--apply'],
                          capture_output=True, text=True, cwd=str(TOOL.parent))
    if done.returncode != 0:
        raise Failure(f'{tool.name} --apply failed on the kernel output: '
                      f'{(done.stdout + done.stderr).strip()}')
    packed = record.get('payload_kernel_sha256')
    return expected.read_bytes(), done.stdout.strip(), packed


def fat_extract(image, member, directory):
    target = directory / Path(member).name
    result = subprocess.run(['mcopy', '-o', '-n', '-i', str(image), member, str(target)],
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise Failure(f'{image.name}: cannot read {member}: {result.stderr.strip()}')
    return target.read_bytes()


def parse_node(data, pos):
    nprops, nchildren = struct.unpack_from('<II', data, pos)
    pos += 8
    props = {}
    for _ in range(nprops):
        key = data[pos:pos + 32].split(b'\0')[0].decode()
        size, = struct.unpack_from('<I', data, pos + 32)
        props[key] = data[pos + 36:pos + 36 + size]
        pos += 36 + size + (-size % 4)
    children = []
    for _ in range(nchildren):
        child, pos = parse_node(data, pos)
        children.append(child)
    return (props['name'].rstrip(b'\0').decode(), props, children), pos


def chosen_properties(adt):
    def walk(node):
        name, props, children = node
        if name == 'chosen':
            return props
        for child in children:
            found = walk(child)
            if found is not None:
                return found
        return None
    node, end = parse_node(adt, 0)
    if end != len(adt):
        raise Failure(f'ADT: parsed {end} of {len(adt)} bytes')
    chosen = walk(node)
    if chosen is None:
        raise Failure('ADT: no /chosen node')
    return chosen


def prelink_state(record):
    """What the prelink emitter says about the collection, as numbers.

    These fields are written by fileset_emit.py's static mapping analysis, and
    two of them are literals: runtime_qualified and loadable are hardcoded False
    (fileset_emit.py:741). So a False here is not a verdict about this build, and
    a True would not be evidence either. What *is* countable is the mapping:
    unresolved owner-target items and the items redirected to
    `_unixnu_fileset_unmapped`, which is a real panic stub
    (osfmk/kern/debug.c:2585). Neither number may be assumed unreachable, so
    structural checks report them and the flight gate refuses while they exist.
    """
    missing = record.get('missing') or {}
    stubbed = record.get('stubbed') or {}
    return {
        'mapping_complete': record.get('mapping_complete'),
        'loadable': record.get('loadable'),
        'runtime_qualified': record.get('runtime_qualified'),
        'missing_bundles': len(missing),
        'missing_refs': sum(len(value) if hasattr(value, '__len__') else int(value)
                            for value in missing.values()),
        'stubbed_bundles': len(stubbed),
        'stubbed_refs': sum(len(value) if hasattr(value, '__len__') else int(value)
                            for value in stubbed.values()),
    }


def prelink_policy(report):
    """Run the regression gate against this record, the way the framework build does.

    The framework refuses a prelink record that grows past `regression_policy`
    (scripts/unixnu/kernel.py:300). Our tree keeps the same rule in
    scripts/check-prelink-regressions.py so it can run against an artifact without a
    rebuild. An absent gate or an unreadable record is "could not judge" and stays
    silent here; the flight gate is where a grown gap becomes fatal.
    """
    script = Path(__file__).resolve().with_name('check-prelink-regressions.py')
    if not script.is_file():
        return []
    completed = subprocess.run([sys.executable, str(script), '--record', str(report)],
                               capture_output=True, text=True)
    if completed.returncode == 0:
        return []
    return [line[len('FAIL: '):] for line in completed.stdout.splitlines()
            if line.startswith('FAIL: ')]


def check(board, chip_id, unique_chip_id):
    kernel = board / 'kernel/kernel.macho'
    payload = board / 'payload/payload.img'
    boot = board / 'boot/boot.img'
    for path in (kernel, payload, boot):
        if not path.is_file():
            raise Failure(f'missing {path}: build kernel, payload and bootimg first')

    size, flags, kind = macho(kernel)
    print(f'ok kernel.macho: arm64e {kind}, flags {flags:#x}, {size} bytes, sha256 {sha256(kernel)[:12]}')
    # The loader contract is a property of kernel.macho alone, so it is checked
    # whether or not kernel.json exists; an absent report must not be able to
    # turn this into an UnboundLocalError (or, worse, silence).
    contract = loader_contract(kernel)
    if contract['violations']:
        print(f'note loader: {contract["note"]}; the shipped loader refuses this collection: '
              + '; '.join(contract['violations']))
    else:
        print(f'ok loader: {contract["note"]}')
    report = board / 'kernel/kernel.json'
    prelink = None
    if report.is_file():
        record = json.loads(report.read_text())
        prelink = prelink_state(record)
        if kind.startswith('MH_FILESET'):
            # "note", not "ok": an image whose prelink map still points at the
            # panic stub is a structurally valid fileset, and calling that ok is
            # how a build that cannot boot gets reported as passing (P-277).
            # "items", not "symbols" or "sites": this counts owner-target
            # pairs, one per bundle/symbol entry in the report. The distinct
            # addresses and the reference-site counts are larger and are named
            # in the ledger rather than guessed at here (P-281).
            print(f'note prelink: mapping_complete={prelink["mapping_complete"]}, '
                  f'{prelink["missing_refs"]} unresolved owner-target items in '
                  f'{prelink["missing_bundles"]} bundles, '
                  f'{prelink["stubbed_refs"]} items redirected to the panic stub in '
                  f'{prelink["stubbed_bundles"]} bundles, loadable={prelink["loadable"]}')
            # Growth is a property of the record against the recorded baseline, so it
            # is reported here and made fatal by the flight gate. A shrinking record
            # prints nothing: fewer gaps than the baseline is the direction we want.
            prelink['policy'] = prelink_policy(report)
            for problem in prelink['policy']:
                print(f'note prelink policy: {problem}')

    with tempfile.TemporaryDirectory(prefix='ios27-artifacts-') as name:
        directory = Path(name)
        payload_report = board / 'payload/payload.json'
        if not payload_report.is_file():
            raise Failure(f'missing {payload_report}: build payload first')
        expected, transform, recorded_packed = packed_kernel_expected(kernel, payload_report, directory)
        packed_kernel = fat_extract(payload, FAT_KERNEL, directory)
        if packed_kernel != expected:
            first = next((i for i in range(min(len(packed_kernel), len(expected)))
                          if packed_kernel[i] != expected[i]), None)
            if first is None:
                where = f'lengths differ: {len(packed_kernel)} vs {len(expected)} bytes'
            else:
                where = (f'first difference at {first:#x}: payload has '
                         f'{packed_kernel[first:first + 8].hex()}, the declared transform writes '
                         f'{expected[first:first + 8].hex()}')
            raise Failure(f'payload kernel.macho is not the declared transform of the kernel '
                          f'output ({where}); recorded payload_kernel_sha256 {recorded_packed}, '
                          f'the transform produces {digest(expected)}')
        if recorded_packed and recorded_packed != digest(expected):
            # Same bytes, stale bookkeeping: the image was produced by an older
            # tool than the one this checkout declares. Say so instead of blaming
            # the image, because the fix is a rebuild, not an edit.
            raise Failure(f'payload.json records payload_kernel_sha256 {recorded_packed} but this '
                          f'checkout\'s declared transform produces {digest(expected)}: the image '
                          f'predates the current tool, rebuild the payload')
        adt = fat_extract(payload, FAT_ADT, directory)
        print(f'ok payload.img: {payload.stat().st_size} bytes, kernel.macho = '
              f'{sha256(kernel)[:12]} + declared transform {digest(expected)[:12]}, ADT {len(adt)} bytes')
        if not transform:
            raise Failure('the declared transform produced no output; check the tool, not the image')

    chosen = chosen_properties(adt)
    seed = chosen.get('random-seed')
    if seed is None:
        raise Failure('ADT: /chosen has no random-seed, the kernel will use a fresh physmap slide')
    if len(seed) != 256:
        raise Failure(f'ADT: random-seed is {len(seed)} bytes, xnu-12377 reads four 64-byte seeds')
    if len(set(seed)) != 1:
        raise Failure('ADT: random-seed is not a pinned value, the slide moves between builds')
    print(f'ok ADT random-seed: {len(seed)} bytes of {seed[0]:#04x}')

    identity = chosen.get('chip-id')
    if identity is None or int.from_bytes(identity, 'little') != chip_id:
        actual = 'absent' if identity is None else f'{int.from_bytes(identity, "little"):04x}'
        raise Failure(f'ADT: chip-id {actual}, expected {chip_id:04x}')
    seed_id = chosen.get('unique-chip-id')
    if seed_id is None or int.from_bytes(seed_id, 'little') != unique_chip_id:
        actual = 'absent' if seed_id is None else f'{int.from_bytes(seed_id, "little"):016x}'
        raise Failure(f'ADT: unique-chip-id {actual}, expected {unique_chip_id:016x}')
    print(f'ok ADT identity: chip-id {chip_id:04x}, unique-chip-id {unique_chip_id:016x}')

    image = boot.read_bytes()
    magic, kernel_size, ramdisk_size, _, header_size = struct.unpack_from('<8s4I', image, 0)
    if magic != b'ANDROID!':
        raise Failure(f'boot.img: magic {magic!r}, not ANDROID!')
    if struct.unpack_from('<I', image, 40)[0] != 4:
        raise Failure('boot.img: header is not v4')
    page = 4096
    start = page * ((header_size + page - 1) // page)
    stream = zlib.decompressobj(31)
    blob = stream.decompress(image[start:start + kernel_size])
    tree = stream.unused_data
    if len(blob) < FD_BYTES:
        raise Failure(f'boot.img: kernel payload is {len(blob)} bytes, shorter than the firmware volume')
    firmware = blob[-FD_BYTES:]
    if firmware[40:44] != b'_FVH':
        raise Failure('boot.img: the firmware volume has no _FVH signature at offset 40')
    if tree[:4] != b'\xd0\x0d\xfe\xed' or struct.unpack_from('>I', tree, 4)[0] != len(tree):
        raise Failure('boot.img: the appended device tree is missing or truncated')
    ramdisk_at = start + ((kernel_size + page - 1) // page) * page
    ramdisk = image[ramdisk_at:ramdisk_at + ramdisk_size]
    if ramdisk != payload.read_bytes():
        raise Failure('boot.img: the ramdisk is not the current payload.img')
    print(f'ok boot.img: {len(image)} bytes, hdr v4 {header_size}, shim {len(blob) - FD_BYTES} B, '
          f'FD {FD_BYTES} B sha256 {hashlib.sha256(firmware).hexdigest()[:12]}, DTB {len(tree)} B, '
          f'ramdisk = payload')
    print(f'artifacts: {boot.stat().st_size} byte boot.img sha256 {sha256(boot)}')
    return {'kind': kind, 'prelink': prelink, 'contract': contract, 'firmware': digest(firmware),
            'payload': sha256(payload), 'boot': sha256(boot)}


def open_blockers(path):
    """Every `state = "open"` entry in the flight-blocker ledger, in file order.

    The ledger exists because a structural pass and a bootable image are two
    different claims, and the gap between them is a list of specific, named
    defects. Keeping them in a file the gate reads means the gate cannot go green
    by forgetting one, and two rules make that real rather than nominal:

    * an entry is closed only by carrying `closed = "<evidence>"` -- deleting the
      entry, or setting a state nobody checks, is not a close;
    * the ids this gate expects must all be present, so removing a defect from
      the file is a failure instead of a silent pass.

    The file is parsed as TOML now (it was a hand-rolled key scan): a scan cannot
    tell `state = "open"` from a typo, and the first draft of this ledger was one
    indentation away from silently containing nothing (P-251 family).
    """
    if not path.is_file():
        raise Failure(f'no flight-blocker ledger at {path}: the flight gate cannot pass on silence')
    entries = tomllib.loads(path.read_text(encoding='utf-8')).get('blocker')
    if not entries:
        raise Failure(f'{path.name} declares no [[blocker]] entries: an empty ledger is not '
                      f'evidence that nothing blocks a flight')
    open_ones, seen = [], set()
    for entry in entries:
        name = entry.get('id')
        if not name:
            raise Failure(f'{path.name}: a blocker has no id')
        if name in seen:
            raise Failure(f'{path.name}: blocker {name} appears twice')
        seen.add(name)
        state = entry.get('state')
        if state is None:
            raise Failure(f'{path.name}: blocker {name} has no state; write "open" or '
                          f'closed = "<evidence>"')
        if state == 'closed':
            if not entry.get('closed'):
                raise Failure(f'{path.name}: blocker {name} says closed without the evidence '
                              f'that closed it')
            continue
        if state != 'open':
            raise Failure(f'{path.name}: blocker {name} has state {state!r}, not open or closed')
        open_ones.append(entry)
    missing = REQUIRED_BLOCKERS - seen
    if missing:
        raise Failure(f'{path.name}: the ledger no longer names {sorted(missing)}; removing a '
                      f'known defect from the file does not fix it')
    return open_ones


def flight_ready(result, blockers):
    """Refuse to call a structurally valid image flyable.

    Every check here is a claim the artifacts cannot make for themselves: the
    prelink map has no unresolved owner-target references, and every named
    blocker in the ledger is closed with evidence.
    """
    prelink = result.get('prelink') or {}
    contract = result.get('contract') or {}
    problems = []
    for violation in contract.get('violations') or ():
        problems.append(f'the shipped loader refuses the collection ({violation})')
    if result['kind'].startswith('MH_FILESET'):
        if prelink.get('missing_refs'):
            problems.append(f'{prelink["missing_refs"]} owner-target items have no address '
                            f'in the prelink map ({prelink["missing_bundles"]} bundles)')
        if prelink.get('stubbed_refs'):
            problems.append(f'{prelink["stubbed_refs"]} items are redirected to the '
                            f'_unixnu_fileset_unmapped panic stub ({prelink["stubbed_bundles"]} bundles)')
    problems += [f'blocker {e.get("id", "?")}: {e.get("what", "(no description)")}'
                 for e in blockers]
    # A record that grew past its own baseline is a regression even if the absolute
    # numbers would look acceptable: something started resolving worse than last time.
    problems += [f'prelink regressed: {problem}' for problem in prelink.get('policy') or ()]
    if problems:
        raise Failure('structurally valid, but not flyable: ' + '; '.join(problems))
    print('ok flight: prelink map has no unresolved references and no blocker is open')


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('board', nargs='?', help='board output directory (default: $UNIXNU_OUT/mondrian/...)')
    parser.add_argument('--chip-id', default='8140', help='expected /chosen/chip-id (T8140)')
    parser.add_argument('--unique-chip-id', default='4d4f4e445249414e', help='expected /chosen/unique-chip-id')
    parser.add_argument('--flight-ready', action='store_true',
                        help='also refuse unless the image is actually flyable, not just well-formed')
    parser.add_argument('--blockers', type=Path,
                        default=Path(__file__).resolve().parents[1]
                        / 'docs/engineering/IOS27-FLIGHT-BLOCKERS.toml',
                        help='ledger of open defects that make a valid image unflyable')
    args = parser.parse_args()
    board = Path(args.board) if args.board else Path(
        os.environ.get('UNIXNU_OUT', '')) / 'mondrian/ios-27.0.1-24A446/mondrian_ios27'
    if not board.is_dir():
        parser.error(f'no board directory at {board}; pass it or set UNIXNU_OUT')
    try:
        result = check(board, int(args.chip_id, 16), int(args.unique_chip_id, 16))
        if args.flight_ready:
            flight_ready(result, open_blockers(args.blockers))
    except Failure as error:
        print(f'error: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
