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


PARENT_VA = 0x100000000
CHILD_BODY = 32 + 72 + 288     # header, one LC_SEGMENT_64, one LC_UNIXTHREAD
ENTRY_PC = PARENT_VA + 0x100


def segment_command(address, size, fileoff, filesize, protection=7):
    name = b'__PRELINK_TEXT'.ljust(16, b'\0')
    return struct.pack('<II16sQQQQIIII', 0x19, 72, name, address, size, fileoff, filesize,
                       protection, protection, 0, 0)


def unixthread_command(pc):
    # arm_thread_state64 is 34 registers; the PC is the 33rd, at offset 272.
    body = struct.pack('<II', 6, 68) + struct.pack('<34Q', *([0] * 32), pc, 0)
    assert len(body) + 8 == 288
    return struct.pack('<II', 5, 288) + body


def fileset_collection(outer_subtype=0xc0000002, child_subtype=0xc0000002,
                       child_flags=0x80200001, child_type=MH_EXECUTE, entries=2):
    """A collection shaped like Apple's, loader rule included.

    The loader does not only compare three fields of `com.apple.kernel`: it also
    requires every indexed header to sit at the VA its entry advertises (covered
    by a parent segment), the member's entry PC to equal the collection's, and
    every member segment to be covered by a parent segment with the same
    file-offset relation. A fixture without a real parent segment would test
    only the three fields while the gate checks six things, so this builds the
    whole shape: one parent segment, N entries, N child headers (each with its
    own segment and thread), and a shared entry PC.
    """
    names = [b'com.apple.kernel'] + [f'entry{i}'.encode() for i in range(1, entries)]
    name_blob = b''.join(name + b'\0' for name in names)
    commands = 72 + 32 * len(names) + 288
    names_at = 32 + commands
    children_at = [names_at + len(name_blob) + CHILD_BODY * i for i in range(len(names))]
    total = children_at[-1] + CHILD_BODY

    body = segment_command(PARENT_VA, total + 0x1000, 0, total)
    prefix = 0
    for index, name in enumerate(names):
        entry_id = names_at + prefix - (32 + 72 + 32 * index)
        body += struct.pack('<IIQQII', LC_FILESET_ENTRY, 32, PARENT_VA + children_at[index],
                            children_at[index], entry_id, 0)
        prefix += len(name) + 1
    body += unixthread_command(ENTRY_PC)

    header = struct.pack('<8I', MH_MAGIC_64, CPU_TYPE_ARM64, outer_subtype, MH_FILESET,
                         len(names) + 2, commands, 0, 0)
    children = b''
    for index in range(len(names)):
        same_child = index == 0
        child_header = struct.pack('<8I', MH_MAGIC_64, CPU_TYPE_ARM64,
                                   child_subtype if same_child else outer_subtype,
                                   child_type if same_child else 11,
                                   2, CHILD_BODY, child_flags if same_child else 0x80200001, 0)
        children += (child_header
                     + segment_command(PARENT_VA + children_at[index], 0x1000,
                                       children_at[index], 0x100, protection=5)
                     + unixthread_command(ENTRY_PC))
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
    # The ledger is data the gate trusts to refuse a flight, so the fixture has
    # to be a ledger the gate would accept: all three ids it expects, one of
    # them closed by evidence. Each negative case below removes exactly one
    # property of that shape, because "no open entries" is what a green flight
    # gate means and there must be no way to reach it by editing the file.
    def ledger_text(firmware='open', loader='open', prelink='open', closed_evidence=True):
        def entry(name, state):
            text = f'[[blocker]]\nid = "{name}"\nwhat = "{name} stops a flight"\n'
            if state is None:
                return text
            if state != 'closed':
                return text + (f'state = "{state}"\n'
                               'observe_via = "fixture: the totals the checker prints"\n')
            text += 'state = "closed"\n'
            return text + ('closed = "rebuilt, measured zero"\n' if closed_evidence else '')
        return '\n'.join(entry(name, state) for name, state in (
            ('firmware-fileset-provider', firmware),
            ('loader-rejects-fileset', loader),
            ('prelink-map-unresolved', prelink))) + '\n'

    ledger = tmp / 'blockers.toml'
    ledger.write_text(ledger_text(), encoding='utf-8')
    open_ones = module.open_blockers(ledger)
    tests.equal('blockers.open_ids', [e['id'] for e in open_ones],
                ['firmware-fileset-provider', 'loader-rejects-fileset', 'prelink-map-unresolved'])
    tests.equal('blockers.what_parsed', open_ones[0]['what'],
                'firmware-fileset-provider stops a flight')

    ledger.write_text(ledger_text(firmware='closed'), encoding='utf-8')
    tests.equal('blockers.closed_with_evidence_drops_out',
                [e['id'] for e in module.open_blockers(ledger)],
                ['loader-rejects-fileset', 'prelink-map-unresolved'])

    ledger.write_text(ledger_text(firmware='closed', closed_evidence=False), encoding='utf-8')
    tests.raises('blockers.closed_without_evidence_refused', 'without the evidence',
                 module.open_blockers, ledger)

    ledger.write_text(ledger_text(loader=None), encoding='utf-8')
    tests.raises('blockers.missing_state_refused', 'has no state', module.open_blockers, ledger)

    ledger.write_text(ledger_text(loader='deferred'), encoding='utf-8')
    tests.raises('blockers.unknown_state_refused', 'not open or closed',
                 module.open_blockers, ledger)

    ledger.write_text('\n'.join(part for part in ledger_text().split('\n\n')
                                if 'firmware-fileset-provider' not in part), encoding='utf-8')
    tests.raises('blockers.deleted_entry_refused', 'no longer names', module.open_blockers, ledger)

    ledger.write_text('', encoding='utf-8')
    tests.raises('blockers.empty_ledger_refused', 'an empty ledger is not',
                 module.open_blockers, ledger)

    ledger.write_text(ledger_text(), encoding='utf-8')
    tests.raises('blockers.missing_ledger', 'cannot pass on silence',
                 module.open_blockers, tmp / 'absent.toml')

    clean = {'kind': 'MH_FILESET, 32 entries',
             'prelink': {'missing_refs': 0, 'stubbed_refs': 0, 'missing_bundles': 0,
                         'stubbed_bundles': 0}}
    tests.raises('flight.open_blocker_refused', 'firmware-fileset-provider',
                 module.flight_ready, clean, open_ones)
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

    # The loader contract must be computed before the optional kernel.json is
    # read: an absent report once left it unbound and check() died with
    # UnboundLocalError instead of a clean verdict (P-280). Helper-level tests
    # cannot see statement order, so assert it on the source.
    source = (ROOT / 'scripts/check-ios27-artifacts.py').read_text(encoding='utf-8').splitlines()
    contract_at = next((i for i, line in enumerate(source)
                        if line.strip() == 'contract = loader_contract(kernel)'), None)
    report_at = next((i for i, line in enumerate(source)
                      if line.strip() == "report = board / 'kernel/kernel.json'"), None)
    tests.check('checker.contract_is_computed', contract_at is not None, 'no contract assignment')
    tests.check('checker.contract_before_report', contract_at is not None and report_at is not None
                and contract_at < report_at,
                f'contract at {contract_at}, report at {report_at}')
    tests.check('checker.contract_is_not_nested',
                contract_at is not None and not source[contract_at].startswith('        '),
                'the contract is computed inside the report branch')

    print(f'{tests.checks - len(tests.failures)}/{tests.checks} checks passed')
    for failure in tests.failures:
        print(f'FAIL {failure}')
    if tests.failures:
        return 1
    print('OK the artifact checker replays the declared transform and refuses to call a stubbed map flyable')
    return 0


if __name__ == '__main__':
    sys.exit(main())