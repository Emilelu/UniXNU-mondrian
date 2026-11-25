"""Make the fileset reference an LTO one without a Mac in the loop.

The 27 kernel prelinks against a symbol-bearing RELEASE build of the same XNU
source. Upstream's profile asks for it with `--lto`, but on Linux the reference
builder cannot produce it: cctools-port's ld64 will not read LLVM bitcode and the
local toolchain has no llvm-link, so `build-fileset-release-reference.py` writes a
non-LTO "snapshot" reference whose report has almost no names. The prelink then
binds 384 owner-target items to nothing and redirects 2262 sites to the panic
stub, which is exactly the state sheng hit on 2026-11-02.

The LTO reference is therefore built once on macOS (Xcode 26.5, Apple ld) and
carried in `blobs/xnu-fileset-reference/`. This step keeps the framework contract
intact:

  1. run the framework builder, so a real build still happens and its inputs
     (source, sdk, archives, compiler, versions) are recorded;
  2. replace the produced file with the carried LTO reference;
  3. rewrite the record's sha256 and note the provenance, so a later `reusable()`
     check inside this same build sees a consistent record instead of a stale one.

That last point is not cosmetic: the framework overwrites both the file and the
record when inputs change, which silently threw away the LTO reference and the
sheng-shaped failure came back (see P-283 recorder note in docs/engineering).
"""
import argparse
import hashlib
import json
import runpy
import shutil
import sys
from pathlib import Path

REFERENCE_RELATIVE = Path('build/xnu/fileset-reference/mach.release.bcm2837.unstripped.noctf')
CARRIED_RELATIVE = Path('scripts/xnu-fileset-reference/mach.release.bcm2837.unstripped.noctf')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tree', default='.', help='the assembled tree (contains scripts/, build/, blobs/)')
    parser.add_argument('--skip-build', action='store_true',
                        help='only install the carried reference, do not run the framework builder')
    options = parser.parse_args()

    root = Path(options.tree).resolve()
    carried = root / CARRIED_RELATIVE
    if not carried.is_file():
        print(f'error: no carried LTO reference at {carried}', file=sys.stderr)
        return 2

    if not options.skip_build:
        builder = root / 'scripts/build-fileset-release-reference.py'
        if not builder.is_file():
            print(f'error: no framework builder at {builder}', file=sys.stderr)
            return 2
        saved = sys.argv
        sys.argv = ['build-fileset-release-reference.py', '--tree', str(root)]
        try:
            runpy.run_path(str(builder), run_name='__main__')
        except SystemExit as error:
            if error.code:
                print(f'error: the framework reference build failed ({error.code})', file=sys.stderr)
                return error.code or 1
        finally:
            sys.argv = saved

    final = root / REFERENCE_RELATIVE
    record = final.with_suffix('.json')
    if not final.is_file():
        print(f'error: the framework builder left no reference at {final}', file=sys.stderr)
        return 2
    produced = digest(final)
    wanted = digest(carried)
    detail = json.loads(record.read_text()) if record.is_file() else {}
    shutil.copyfile(carried, final)
    detail['sha256'] = wanted
    detail['provenance'] = {
        'how': 'scripts/build-fileset-release-reference.py --lto on macOS (Xcode 26.5, Apple ld)',
        'why': 'the Linux builder has no linker that reads LLVM bitcode, so the symbol-bearing '
               'reference cannot be produced here',
        'carried': str(CARRIED_RELATIVE),
    }
    record.write_text(json.dumps(detail, indent=2) + '\n')
    print(f'fileset reference: produced {produced[:12]} (non-LTO), installed {wanted[:12]} (LTO) '
          f'{final.stat().st_size} bytes')
    return 0


if __name__ == '__main__':
    sys.exit(main())
