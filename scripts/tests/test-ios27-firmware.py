#!/usr/bin/env python3
"""Fixtures for scripts/check-ios27-firmware.py.

The gate answers "which DarwinBoot does the build compile, and can it read a
fileset?". The fixtures are two real directory shapes, because the answer that
matters is which one the search order picks, not whether some file somewhere
mentions the constant:

  * a vendored platform tree whose driver rejects anything but subtype 0 /
    filetype 2 (what `{uefi}/Platforms/Xiaomi` holds today), and
  * a catalog driver that branches on filetype 12 (what components.toml pins).

The cases below put both on one search path in both orders, add a comment-only
mention that must not count, and check the two "cannot tell" shapes.
"""
import contextlib
import importlib.util
import io
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / 'scripts' / 'check-ios27-firmware.py'
PLATFORM = 'Platforms/Xiaomi/mondrianPkg'

VENDORED = """
EFI_STATUS ParseKernelHeader (CONST UINT8 *Data, UINTN Size, KERNEL *Kernel)
{
  if ((Size < 32) || (U32 (Data) != 0xfeedfacf) || (U32 (Data + 4) != 0x100000c) ||
      (U32 (Data + 8) != 0) || (U32 (Data + 12) != 2)) {
    return EFI_UNSUPPORTED;
  }
  return EFI_SUCCESS;
}
"""

# A comment is not a code path: this must read as execute-only.
COMMENT_ONLY = """
EFI_STATUS ParseKernelHeader (CONST UINT8 *Data, UINTN Size, KERNEL *Kernel)
{
  /* We do not handle LC_FILESET_ENTRY yet; filetype 12 is rejected below. */
  if ((U32 (Data + 8) != 0) || (U32 (Data + 12) != 2)) {
    return EFI_UNSUPPORTED;
  }
  return EFI_SUCCESS;
}
"""

CATALOG = """
EFI_STATUS ParseKernelHeader (CONST UINT8 *Data, UINTN Size, UINTN Header, KERNEL *Kernel)
{
  if ((U32 (Data + Header + 12) != 2) && ((Header != 0) || (U32 (Data + Header + 12) != 12))) {
    return EFI_UNSUPPORTED;
  }
  return EFI_SUCCESS;
}

EFI_STATUS ParseFileset (CONST UINT8 *Data, UINTN Size, KERNEL *Kernel)
{
  if (Command->Command == LC_FILESET_ENTRY) {
    return ParseKernelHeader (Data, Size, Command->FileOffset, &Member);
  }
  return EFI_SUCCESS;
}
"""


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


def tree(root, driver):
    """A search-path root holding the platform DSC and one DarwinBoot source."""
    platform = Path(root) / PLATFORM
    platform.mkdir(parents=True, exist_ok=True)
    (platform / 'mondrian.dsc').write_text(
        '[Components]\n  DarwinBootPkg/Driver/DarwinBoot.inf\n', encoding='utf-8')
    source = Path(root) / 'DarwinBootPkg' / 'Driver' / 'DarwinBoot.c'
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(driver, encoding='utf-8')
    return Path(root)


def dsc_only(root):
    """A root that names the driver but does not provide its source."""
    platform = Path(root) / PLATFORM
    platform.mkdir(parents=True, exist_ok=True)
    (platform / 'mondrian.dsc').write_text(
        '[Components]\n  DarwinBootPkg/Driver/DarwinBoot.inf\n', encoding='utf-8')
    return Path(root)


def load():
    spec = importlib.util.spec_from_file_location('check_ios27_firmware', CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    tests = Tests()
    module = load()

    with tempfile.TemporaryDirectory() as scratch:
        tmp = Path(scratch)

        # A comment that mentions the constant is not a code path.
        tests.check('fileset.comment_does_not_count',
                    not module.has_fileset_path(COMMENT_ONLY))

        # The two real shapes.
        tests.check('fileset.vendored_rejected', not module.has_fileset_path(VENDORED))
        tests.check('fileset.catalog_accepted', module.has_fileset_path(CATALOG))
        tests.check('fileset.filetype_test_accepted',
                    module.has_fileset_path('if (U32 (Data + 12) != 12) { return 1; }'))

        # Order decides: the first provider on the search path is the compiled one.
        uefi = tree(tmp / 'uefi', VENDORED)
        catalog = tree(tmp / 'catalog', CATALOG)

        vendored_first = module.check([str(uefi), str(catalog)])
        tests.equal('order.vendored_first_kind', vendored_first['kind'], 'execute-only')
        tests.equal('order.vendored_first_source',
                    Path(vendored_first['source']).parent.parent.parent, uefi)
        tests.equal('order.vendored_first_root', vendored_first['dsc_root'], uefi)

        catalog_first = module.check([str(catalog), str(uefi)])
        tests.equal('order.catalog_first_kind', catalog_first['kind'], 'fileset')
        tests.equal('order.catalog_first_source',
                    Path(catalog_first['source']).parent.parent.parent, catalog)

        # A root with no platform DSC is not a candidate for the DSC, but it is
        # still a candidate for the driver: EDK II resolves each package
        # separately, so the two can come from different roots and the gate has
        # to report that pairing rather than assume they travel together.
        bare = Path(tmp / 'bare')
        (bare / 'DarwinBootPkg' / 'Driver').mkdir(parents=True)
        (bare / 'DarwinBootPkg' / 'Driver' / 'DarwinBoot.c').write_text(CATALOG, encoding='utf-8')
        skipped = module.check([str(bare), str(uefi)])
        tests.equal('order.dsc_skips_root_without_platform', skipped['dsc_root'], uefi)
        tests.equal('order.provider_resolved_independently', skipped['kind'], 'fileset')
        tests.equal('order.provider_root', skipped['source_root'], bare)
        tests.check('order.split_roots_flagged', skipped['split_roots'] is True)
        tests.check('order.same_root_not_flagged',
                    module.check([str(uefi), str(catalog)])['split_roots'] is False)

        # "Cannot tell" is its own verdict, and never a pass.
        nowhere = module.check([str(tmp / 'nothing-here')])
        tests.equal('unknown.no_dsc', nowhere['kind'], 'no-dsc')
        tests.check('unknown.no_dsc_note', 'is unknown' in nowhere['note'], nowhere['note'])

        named = dsc_only(tmp / 'named-only')
        orphan = module.check([str(named)])
        tests.equal('unknown.no_provider', orphan['kind'], 'no-provider')
        tests.check('unknown.no_provider_note', 'is unknown' in orphan['note'], orphan['note'])

    # The order has to come from board.toml, not from the caller's memory: the
    # reason the vendored driver wins is its position in that list.
    with tempfile.TemporaryDirectory() as scratch:
        tmp = Path(scratch)
        uefi = tree(tmp / 'uefi', VENDORED)
        catalog = tree(tmp / 'catalog', CATALOG)
        board = tmp / 'board'
        board.mkdir()
        (board / 'board.toml').write_text(
            '[firmware]\npackages = ["{catalog}/", "{uefi}"]\n', encoding='utf-8')
        order = module.search_from_board(board, {'catalog': str(catalog), 'uefi': str(uefi)})
        tests.equal('board.order_read', order, [str(catalog) + '/', str(uefi)])
        tests.equal('board.order_decides', module.check(order)['kind'], 'fileset')

        (board / 'board.toml').write_text(
            '[firmware]\npackages = ["{unset}/"]\n', encoding='utf-8')
        try:
            module.search_from_board(board, {'uefi': str(uefi)})
            tests.check('board.unknown_placeholder_refused', False, 'no exception')
        except SystemExit as error:
            tests.check('board.unknown_placeholder_refused', 'no value was given' in str(error),
                        str(error))

    # Exit codes: the defect is a note by default and fatal under --strict.
    # The gate's own output is captured rather than printed, so the suite ends
    # with its summary and so the messages can be asserted instead of eyeballed.
    def quiet(*arguments):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            code = module.main(list(arguments))
        return code, buffer.getvalue()

    with tempfile.TemporaryDirectory() as scratch:
        uefi = tree(Path(scratch) / 'uefi', VENDORED)
        quiet_code, quiet_text = quiet('--search', str(uefi))
        tests.equal('exit.vendored_reports_zero', quiet_code, 0)
        tests.check('exit.vendored_says_where_it_came_from',
                    str(uefi) in quiet_text, quiet_text[-200:])
        loud_code, _ = quiet('--search', str(uefi), '--strict')
        tests.equal('exit.vendored_strict_one', loud_code, 1)
        unknown_code, unknown_text = quiet('--search', str(Path(scratch) / 'nowhere'))
        tests.equal('exit.no_dsc_two', unknown_code, 2)
        tests.check('exit.no_dsc_explains', 'is unknown' in unknown_text, unknown_text[-200:])

    with tempfile.TemporaryDirectory() as scratch:
        catalog = tree(Path(scratch) / 'catalog', CATALOG)
        clean_code, clean_text = quiet('--search', str(catalog), '--strict')
        tests.equal('exit.catalog_strict_zero', clean_code, 0)
        tests.check('exit.catalog_names_source', 'branches on filetype 12' in clean_text,
                    clean_text[-200:])

    empty_code, empty_text = quiet()
    tests.equal('exit.no_search', empty_code, 2)
    tests.check('exit.no_search_explains', 'packages order' in empty_text, empty_text[-200:])

    print(f'{tests.checks - len(tests.failures)}/{tests.checks} checks passed')
    for failure in tests.failures:
        print(f'FAIL {failure}')
    if tests.failures:
        return 1
    print('OK the firmware gate reads the driver the DSC selects and refuses to guess')
    return 0


if __name__ == '__main__':
    sys.exit(main())
