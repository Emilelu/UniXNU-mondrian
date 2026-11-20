#!/usr/bin/env python3
"""Self-test for scripts/check-ios27-artifacts.py.

Two things are being protected here, and both of them shipped wrong at least
once:

* the payload transform. `payload/payload.img` holds a kernel that is *not* the
  linker's output: the payload step copies it and runs the repository's own
  patcher on the copy (P-277). The checker must replay that transform and then
  compare the whole FAT member, so a second undeclared edit is caught and a
  declared edit is not reported as corruption.
* the difference between "well formed" and "flyable". A fileset whose prelink
  map still redirects 2688 reference sites to a panic stub is structurally
  perfect; calling that a pass is how a build that cannot boot gets signed off.
  `--flight-ready` therefore refuses on the map and on the open blocker ledger.

The fixtures are synthetic but not stubbed: real 32-byte Mach-O headers, a real
segment command, a real ADT property node, and the tool is invoked through a
stand-in script so the replay path runs exactly as it does in a build.
"""
import importlib.util
import json
import struct
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / 'scripts' / 'check-ios27-artifacts.py'

MH_MAGIC_64 = 0xFEEDFACF
CPU_TYPE_ARM64 = 0x0100000C
CPU_SUBTYPE_ARM64E = 0x80000002
MH_EXECUTE, MH_FILESET = 2, 12
LC_BUILD_VERSION = 0x32
LC_FILESET_ENTRY = 0x80000035
PLATFORM_IOS = 2


def macho_header(filetype, subtype=CPU_SUBTYPE_ARM64E, flags=0x200001,
                 version=(PLATFORM_IOS, (27 << 16), (27 << 16)), fileset_entries=1):
    commands = []
    count = fileset_entries if filetype == MH_FILESET else 0
    names = b''
    base_names_at = 32 + 24 * bool(version is not None) + 32 * count
    if version is not None:
        platform, minos, sdk = version
        commands.append(struct.pack('<6I', LC_BUILD_VERSION, 24, platform, minos, sdk, 0))
    for index in range(count):
        # struct fileset_entry_command: 32 bytes, entry_id is a file offset to the name.
        commands.append(struct.pack('<IIQQII', LC_FILESET_ENTRY, 32, 0, 0,
                                    base_names_at + len(names), 0))
        name = b'com.apple.kernel' if index == 0 else f'entry{index}'.encode()
        names += name + b'\0'
    blob = b''.join(commands)
    return struct.pack('<8I', MH_MAGIC_64, CPU_TYPE_ARM64, subtype, filetype,
                       len(commands), len(blob), flags, 0) + blob + names


def fileset_collection(outer_subtype=0xc0000002, child_subtype=0xc0000002,
                       child_flags=0x80200001, child_type=MH_EXECUTE, entries=2):
    """A collection shaped like Apple's: header, N entries, then N child headers.

    The loader compares three fields of the `com.apple.kernel` child against the
    outer header, so the fixture has to carry real child headers at real file
    offsets -- a self-referencing entry would silently test nothing.
    """
    names = [b'com.apple.kernel'] + [f'entry{i}'.encode() for i in range(1, entries)]
    name_blob = b''.join(name + b'\0' for name in names)
    commands = 32 * len(names)
    names_at = 32 + commands
    children_at = [names_at + len(name_blob) + 32 * i for i in range(len(names))]
    body = b''
    prefix = 0
    for index, name in enumerate(names):
        entry_id = names_at + prefix - (32 + 32 * index)
        body += struct.pack('<IIQQII', LC_FILESET_ENTRY, 32, 0, children_at[index], entry_id, 0)
        prefix += len(name) + 1
    header = struct.pack('<8I', MH_MAGIC_64, CPU_TYPE_ARM64, outer_subtype, MH_FILESET,
                         len(names), commands, 0, 0)
    children = b''
    for index in range(len(names)):
        same_child = index == 0
        children += struct.pack('<8I', MH_MAGIC_64, CPU_TYPE_ARM64,
                                child_subtype if same_child else outer_subtype,
                                child_type if same_child else 11,
                                0, 0, child_flags if same_child else 0x80200001, 0)
    return header + body + name_blob + children


def adt_node(name, props, children=b''):
    out = struct.pack('<II', len(props) + 1, 1 if children else 0)
    for key, value in [('name', name.encode() + b'\0')] + list(props):
        pad = -len(value) % 4
        out += key.encode().ljust(32, b'\0') + struct.pack('<I', len(value)) + value + b'\0' * pad
    return out + children


def adt(chosen_props):
    chosen = adt_node('chosen', chosen_props)
    return adt_node('device-tree', [], chosen)


class Tests:
    def __init__(self):
        self.checks = 0
        self.failures = []

    def check(self, name, condition, detail=''):
        self.checks += 1
        if not condition:
            self.failures.append(f'{name}{": " + detail if detail else ""}')

    def equal(self, name, actual, expected):
        self.check(name, actual == expected, f'{actual!r} != {expected!r}')

    def raises(self, name, needle, function, *arguments):
        try:
            function(*arguments)
        except Exception as error:  # noqa: BLE001 - the message is the assertion
            self.check(name, needle in str(error), f'{needle!r} not in {error!r}')
            return
        self.check(name, False, 'no exception')


def load():
    spec = importlib.util.spec_from_file_location('check_ios27_artifacts', CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    tests = Tests()
    module = load()
    tmp = Path(tempfile.mkdtemp(prefix='ios27-artifacts-'))

    # --- header parsing ---------------------------------------------------
    execute = tmp / 'execute.macho'
    execute.write_bytes(macho_header(MH_EXECUTE))
    size, flags, kind = module.macho(execute)
    tests.equal('macho.execute_kind', kind, 'MH_EXECUTE')
    tests.equal('macho.execute_size', size, execute.stat().st_size)

    fileset = tmp / 'fileset.macho'
    fileset.write_bytes(macho_header(MH_FILESET, subtype=0xc0000002, flags=0x200000,
                                     version=None, fileset_entries=2))
    size, _, kind = module.macho(fileset)
    tests.equal('macho.fileset_kind', kind, 'MH_FILESET, 2 entries')

    bad = tmp / 'plain-arm64.macho'
    bad.write_bytes(macho_header(MH_EXECUTE, subtype=0))
    tests.raises('macho.subtype_refused', 'not arm64e', module.macho, bad)

    bad = tmp / 'fileset-no-entries.macho'
    bad.write_bytes(macho_header(MH_FILESET, version=None, fileset_entries=0))
    tests.raises('macho.fileset_without_entries', 'no LC_FILESET_ENTRY', module.macho, bad)

    bad = tmp / 'no-noundefs.macho'
    bad.write_bytes(macho_header(MH_EXECUTE, flags=0x200000))
    tests.raises('macho.noundefs_required', 'MH_NOUNDEFS', module.macho, bad)

    bad = tmp / 'old-minos.macho'
    bad.write_bytes(macho_header(MH_EXECUTE, version=(PLATFORM_IOS, (26 << 16), (26 << 16))))
    tests.raises('macho.minos_must_be_27', 'not 27.x', module.macho, bad)

    bad = tmp / 'macos.macho'
    bad.write_bytes(macho_header(MH_EXECUTE, version=(1, (27 << 16), (27 << 16))))
    tests.raises('macho.platform_must_be_ios', 'not iOS', module.macho, bad)

    # --- hashing ----------------------------------------------------------
    tests.equal('digest.matches_file', module.digest(execute.read_bytes()), module.sha256(execute))

    # --- the payload transform -------------------------------------------
    board = tmp / 'board'
    (board / 'kernel').mkdir(parents=True)
    (board / 'payload').mkdir()
    kernel = board / 'kernel/kernel.macho'
    kernel.write_bytes(macho_header(MH_FILESET, subtype=0xc0000002, version=None) + b'\x00' * 64)
    report = board / 'payload/payload.json'

    appender = tmp / 'append-eight.py'
    appender.write_text(
        'import sys\n'
        'path = sys.argv[1]\n'
        'data = open(path, "rb").read()\n'
        'open(path, "wb").write(data + b"\\x20\\x00\\x80\\x52\\xff\\x0f\\x5f\\xd6")\n'
        'print("patched: mov w0, #1 ; retab")\n',
        encoding='utf-8')
    module.TOOL = appender

    expected_bytes = kernel.read_bytes() + b'\x20\x00\x80\x52\xff\x0f\x5f\xd6'
    report.write_text(json.dumps({
        'kernel_sha256': module.sha256(kernel),
        'payload_kernel_sha256': module.digest(expected_bytes),
    }), encoding='utf-8')
    with tempfile.TemporaryDirectory() as name:
        got, note, _ = module.packed_kernel_expected(kernel, report, Path(name))
    tests.equal('transform.replays_declared_edit', got, expected_bytes)
    tests.check('transform.reports_the_tool', 'retab' in note, note)

    # A recorded hash that the declared transform does not produce is returned,
    # not swallowed: check() compares it after diffing the real FAT member, so the
    # operator sees both the byte offset and the stale bookkeeping.
    report.write_text(json.dumps({
        'kernel_sha256': module.sha256(kernel),
        'payload_kernel_sha256': 'f' * 64,
    }), encoding='utf-8')
    with tempfile.TemporaryDirectory() as name:
        got, _, recorded = module.packed_kernel_expected(kernel, report, Path(name))
    tests.equal('transform.stale_hash_is_reported', recorded, 'f' * 64)
    tests.equal('transform.stale_hash_does_not_change_bytes', got, expected_bytes)

    report.write_text(json.dumps({
        'kernel_sha256': 'e' * 64,
        'payload_kernel_sha256': module.digest(expected_bytes),
    }), encoding='utf-8')
    with tempfile.TemporaryDirectory() as name:
        tests.raises('transform.wrong_source_refused', 'different kernel',
                     module.packed_kernel_expected, kernel, report, Path(name))

    noop = tmp / 'noop.py'
    noop.write_text('import sys\nprint("already patched")\n', encoding='utf-8')
    module.TOOL = noop
    report.write_text(json.dumps({
        'kernel_sha256': module.sha256(kernel),
        'payload_kernel_sha256': module.sha256(kernel),
    }), encoding='utf-8')
    with tempfile.TemporaryDirectory() as name:
        got, _, _ = module.packed_kernel_expected(kernel, report, Path(name))
    tests.equal('transform.noop_tool_is_honest', got, kernel.read_bytes())

    module.TOOL = tmp / 'not-here.py'
    with tempfile.TemporaryDirectory() as name:
        tests.raises('transform.missing_tool_refused', 'cannot be reproduced',
                     module.packed_kernel_expected, kernel, report, Path(name))

    # --- ADT --------------------------------------------------------------
    seed = bytes([0x5A]) * 256
    tree = adt([('random-seed', seed),
                ('chip-id', struct.pack('<I', 0x8140)),
                ('unique-chip-id', struct.pack('<Q', 0x4D4F4E445249414E))])
    chosen = module.chosen_properties(tree)
    tests.equal('adt.random_seed', chosen['random-seed'], seed)
    tests.equal('adt.chip_id', int.from_bytes(chosen['chip-id'], 'little'), 0x8140)
    tests.raises('adt.truncated_refused', 'parsed', module.chosen_properties, tree[:-4])
    tests.raises('adt.no_chosen_refused', 'no /chosen', module.chosen_properties,
                 adt_node('device-tree', []))

    # --- prelink arithmetic ----------------------------------------------
    state = module.prelink_state({
        'mapping_complete': False, 'loadable': False, 'runtime_qualified': False,
        'missing': {'a': [1, 2, 3], 'b': [1]},
        'stubbed': {'c': list(range(10))},
    })
    tests.equal('prelink.missing_refs', state['missing_refs'], 4)
    tests.equal('prelink.missing_bundles', state['missing_bundles'], 2)
    tests.equal('prelink.stubbed_refs', state['stubbed_refs'], 10)
    tests.equal('prelink.loadable_passed_through', state['loadable'], False)
    empty = module.prelink_state({'mapping_complete': True, 'loadable': False})
    tests.equal('prelink.empty_maps', (empty['missing_refs'], empty['stubbed_refs']), (0, 0))

    # --- the flight gate --------------------------------------------------
    ledger = tmp / 'blockers.toml'
    ledger.write_text(
        '[[blocker]]\nid = "still-open"\nwhat = "the loader refuses filetype 12"\nstate = "open"\n\n'
        '[[blocker]]\nid = "closed-one"\nwhat = "already fixed"\nstate = "closed"\n',
        encoding='utf-8')
    open_ones = module.open_blockers(ledger)
    tests.equal('blockers.open_count', [e['id'] for e in open_ones], ['still-open'])
    tests.equal('blockers.id_parsed', open_ones[0]['what'], 'the loader refuses filetype 12')

    tests.raises('blockers.missing_ledger', 'cannot pass on silence',
                 module.open_blockers, tmp / 'absent.toml')

    clean = {'kind': 'MH_FILESET, 32 entries',
             'prelink': {'missing_refs': 0, 'stubbed_refs': 0, 'missing_bundles': 0,
                         'stubbed_bundles': 0}}
    tests.raises('flight.open_blocker_refused', 'still-open', module.flight_ready, clean, open_ones)
    module.flight_ready(clean, [])

    dirty = {'kind': 'MH_FILESET, 32 entries',
             'prelink': {'missing_refs': 384, 'stubbed_refs': 2688,
                         'missing_bundles': 28, 'stubbed_bundles': 29}}
    tests.raises('flight.unmapped_refused', 'no address', module.flight_ready, dirty, [])
    tests.raises('flight.stub_sites_refused', 'panic stub', module.flight_ready,
                 {'kind': dirty['kind'], 'prelink': {'missing_refs': 0, 'stubbed_refs': 5,
                                                     'missing_bundles': 0, 'stubbed_bundles': 1}}, [])
    # A plain MH_EXECUTE is not subject to the fileset map's numbers.
    module.flight_ready({'kind': 'MH_EXECUTE', 'prelink': None}, [])

    # The loader compares the com.apple.kernel child against the collection.
    good = tmp / 'collection-good'
    good.write_bytes(fileset_collection())
    tests.equal('loader.apple_shape_conforms', module.loader_contract(good)['violations'], [])

    mismatch = tmp / 'collection-mismatch'
    mismatch.write_bytes(fileset_collection(child_subtype=0x80000002))
    violations = module.loader_contract(mismatch)['violations']
    tests.equal('loader.one_violation', len(violations), 1)
    tests.check('loader.names_the_field', 'cpusubtype 0x80000002' in violations[0],
                violations[0] if violations else 'no violation')
    tests.check('loader.names_the_child', 'com.apple.kernel' in violations[0], violations[0])

    no_cache = tmp / 'collection-no-cache'
    no_cache.write_bytes(fileset_collection(child_flags=0x200001))
    tests.check('loader.dylib_in_cache_required',
                any('MH_DYLIB_IN_CACHE' in v for v in module.loader_contract(no_cache)['violations']),
                str(module.loader_contract(no_cache)['violations']))

    wrong_type = tmp / 'collection-wrong-type'
    wrong_type.write_bytes(fileset_collection(child_type=11))
    tests.check('loader.member_must_be_execute',
                any('not MH_EXECUTE' in v for v in module.loader_contract(wrong_type)['violations']),
                str(module.loader_contract(wrong_type)['violations']))

    execute = tmp / 'kernel-execute'
    execute.write_bytes(macho_header(MH_EXECUTE))
    tests.equal('loader.execute_has_no_children', module.loader_contract(execute)['violations'], [])

    # And the flight gate refuses an image whose collection the loader would reject.
    tests.raises('flight.loader_mismatch_refused', 'the shipped loader refuses the collection',
                 module.flight_ready,
                 {'kind': 'MH_FILESET, 2 entries', 'prelink': {'missing_refs': 0, 'stubbed_refs': 0},
                  'contract': module.loader_contract(mismatch)}, [])

    print(f'{tests.checks - len(tests.failures)}/{tests.checks} checks passed')
    for failure in tests.failures:
        print(f'FAIL {failure}')
    if tests.failures:
        return 1
    print('OK the artifact checker replays the declared transform and refuses to call a stubbed map flyable')
    return 0


if __name__ == '__main__':
    sys.exit(main())