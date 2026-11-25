#!/usr/bin/env python3
"""Tests for scripts/ios27-inputs.py.

The build script skips the payload and the boot image when the key of their
inputs equals the key recorded next to the artifact, so the expensive failure is
a key that stays the same while an input moved: the build prints "reused", exits
0, and ships an image that disagrees with the tree.  These tests pin both
directions:

  * every input the stage reads moves the key -- the packed kernel, the series
    fingerprint, the platform seed, board.toml, the device tree the ADT is
    compiled from, the transform tools the step runs, the framework modules that
    pack the volume, and the firmware volume and Mu-Silicium pieces of the boot
    image;
  * for the kernel stage, one line per patch the series lists, so one edited
    patch is one different key and --explain names the file that moved;
  * the things that are not inputs do not move it -- a second firmware volume
    under another target, a config for another board, a script nothing names.
    A key that moves on everything is a rebuild with extra steps.

The device tree case is deliberate: the payload step compiles hardware.dtb, so a
dts edit leaves kernel.macho untouched, and a key over the kernel alone would
reuse a payload whose ADT is the previous tree.  The kernel level is the mirror
image of it: its key is the series, the list the hook appends to bsd/conf/files,
the defconfig, board.toml and the scripts that turn those into a macho, and it
must *not* move when the tree moves -- a dts edit has to rebuild the payload, not
the 271 s kernel.
"""
import contextlib
import importlib.util
import io
import os
import pathlib
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
HELPER = HERE.parent / 'ios27-inputs.py'

BOARD_TOML = """schema_version = 2

[board]
name = "mondrian"
soc = "SM8475"
soc_source = "sm8475"
os_profile = "ios-27.0.1-24A446"

[device_tree]
source = "device:dts/mondrian.dts"
include_dirs = ["soc:dts"]

[firmware]
config = "mondrian"
fd = "Build/mondrianPkg/{target}_CLANGPDB/FV/SILICIUM_UEFI.fd"

[payload]
volume = "UNIXNU"
size_mib = 192

[payload.adt]
chip_id = "8140"
unique_chip_id = "required"
"""

# The kernel.macho the payload records is written for the DEBUG target, so the
# firmware volume is the one under DEBUG_CLANGPDB and never a second copy that
# happens to sit in another target directory.
FD = 'Build/mondrianPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd'


def load_helper():
    spec = importlib.util.spec_from_file_location('k60_ios27_inputs', HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path, data):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(data)
    return path


class StageKeyTest(unittest.TestCase):
    """One board build directory, the way the build script lays it out."""

    def setUp(self):
        self.helper = load_helper()
        self._tmp = tempfile.TemporaryDirectory(prefix='ios27-inputs-')
        self.root = pathlib.Path(self._tmp.name)
        self.device = self.root / 'device'
        self.unixnu = self.root / 'UniXNU'
        self.out = self.root / 'out' / 'mondrian' / 'ios-27.0.1-24A446' / 'mondrian_ios27'
        self.feeds = self.root / 'out' / 'feeds'
        self.uefi = self.root / 'uefi'
        write(self.device / 'board.toml', BOARD_TOML)
        write(self.device / 'dts' / 'mondrian.dts',
              '/dts-v1/;\n/include/ "sm8475.dtsi"\n/ { model = "Redmi K60"; };\n')
        # The kernel stage: a series with a comment and a blank line, the list the
        # hook appends to bsd/conf/files, the defconfig, and the two scripts that
        # turn the series into a macho.  seal-source-crypto-kernel.py is on
        # purpose absent here: test_a_tool_appearing_is_a_new_key creates it, and
        # the payload key must move when it appears.
        write(self.device / 'patches' / 'xnu-12377' / 'series',
              '# xnu-12377, applied in this order\nfirst.patch\n\nsecond.patch\n')
        write(self.device / 'patches' / 'xnu-12377' / 'first.patch',
              'diff --git a/a.c b/a.c\n--- a/a.c\n+++ b/a.c\n@@ -1 +1 @@\n-old\n+new\n')
        write(self.device / 'patches' / 'xnu-12377' / 'second.patch',
              'diff --git a/b.c b/b.c\n--- a/b.c\n+++ b/b.c\n@@ -1 +1 @@\n-one\n+two\n')
        write(self.device / 'patches' / 'xnu-12377' / 'conf-files.txt', 'bsd/dev/arm/k60_bt.c\n')
        write(self.device / 'configs' / 'mondrian_ios27_defconfig',
              'CONFIG_XNU_CPU_ARM64E=y\nCONFIG_XNU_4K_PAGE=y\n')
        write(self.device / 'scripts' / 'build-xnu-generic.sh', '#!/bin/sh\n# generic builder\n')
        write(self.device / 'scripts' / 'k60-conf-files-hook.py', 'print("hook")\n')
        write(self.out / 'tree' / 'scripts' / 'patch-sandbox-label-update.py', 'print("sandbox")\n')
        write(self.unixnu / 'scripts' / 'unixnu' / 'kernel.py', '# kernel\n')
        write(self.unixnu / 'scripts' / 'unixnu' / 'patches.py', '# patches\n')
        write(self.feeds / 'UniXNU-sm8475-common-6ebb3d7f' / 'dts' / 'sm8475.dtsi', '/* soc */\n')
        write(self.out / 'kernel' / 'kernel.macho', b'kernel-one')
        write(self.out / 'payload' / 'payload.img', b'payload-one')
        write(self.out / 'device-tree' / 'hardware.dtb', b'dtb-one')
        write(self.out / 'tree' / 'scripts' / 'patch-armcpu-validate.py', 'print("armcpu")\n')
        write(self.out / 'tree' / 'scripts' / 'patch-xnu-entry-probe.py', 'print("probe")\n')
        write(self.unixnu / 'scripts' / 'unixnu' / 'payload.py', '# payload\n')
        write(self.unixnu / 'scripts' / 'unixnu' / 'devicetree.py', '# devicetree\n')
        write(self.uefi / 'Resources' / 'Scripts' / 'mkbootimg.py', '# mkbootimg\n')
        write(self.uefi / 'Resources' / 'Configs' / 'mondrian.toml', 'config = "mondrian"\n')
        write(self.uefi / 'BootShim' / 'BootShim.S', '// shim\n')
        write(self.uefi / 'BootShim' / 'Makefile', 'all:\n')
        write(self.uefi / FD, b'firmware-volume-one')

    def tearDown(self):
        self._tmp.cleanup()

    # -- the three stages ---------------------------------------------------

    def argv_for(self, stage):
        """The stage's arguments, the way the build script passes them."""
        argv = [stage, '--device', str(self.device), '--out', str(self.out)]
        if stage == 'payload':
            argv += ['--series-fingerprint', 'cc85fd583e77ac7b 240', '--unique-chip-id', '4d4f4e445249414e']
        elif stage == 'bootimg':
            argv += ['--uefi', str(self.uefi)]
        else:
            argv += ['--unixnu', str(self.unixnu)]
        return argv

    def payload_key(self, **overrides):
        argv = ['payload', '--device', str(self.device), '--out', str(self.out),
                '--series-fingerprint', overrides.get('series', 'cc85fd583e77ac7b 240'),
                '--unique-chip-id', overrides.get('seed', '4d4f4e445249414e')]
        if 'feeds' in overrides:
            argv += ['--feeds', str(overrides['feeds'])]
        return self.helper.key(self.helper.payload_lines(self.helper.parser().parse_args(argv)))

    def bootimg_key(self, **overrides):
        argv = ['bootimg', '--device', str(self.device), '--out', str(self.out),
                '--uefi', str(overrides.get('uefi', self.uefi))]
        return self.helper.key(self.helper.bootimg_lines(self.helper.parser().parse_args(argv)))

    def kernel_key(self):
        argv = self.argv_for('kernel')
        return self.helper.key(self.helper.kernel_lines(self.helper.parser().parse_args(argv)))

    def explain(self, stage, *extra):
        argv = self.argv_for(stage) + ['--explain', *extra]
        out = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(out):
            code = self.helper.main(argv)
        return code, out.getvalue().strip().splitlines()

    # -- payload: every input moves the key ---------------------------------

    def test_the_same_inputs_give_the_same_key(self):
        self.assertEqual(self.payload_key(), self.payload_key())

    def test_the_packed_kernel_moves_the_key(self):
        before = self.payload_key()
        write(self.out / 'kernel' / 'kernel.macho', b'kernel-two')
        self.assertNotEqual(before, self.payload_key())

    def test_the_series_fingerprint_moves_the_key(self):
        before = self.payload_key()
        self.assertNotEqual(before, self.payload_key(series='0000000000000000 241'))

    def test_the_platform_seed_moves_the_key(self):
        before = self.payload_key()
        self.assertNotEqual(before, self.payload_key(seed='0000000000000000'))

    def test_the_device_tree_moves_the_key_because_the_adt_is_compiled_here(self):
        before = self.payload_key()
        write(self.device / 'dts' / 'mondrian.dts', '/dts-v1/;\n/ { model = "Redmi K60 Pro"; };\n')
        self.assertNotEqual(before, self.payload_key())

    def test_the_soc_include_moves_the_key(self):
        before = self.payload_key()
        write(self.feeds / 'UniXNU-sm8475-common-6ebb3d7f' / 'dts' / 'sm8475.dtsi', '/* soc, edited */\n')
        self.assertNotEqual(before, self.payload_key())

    def test_a_missing_soc_feed_is_a_different_key_from_a_present_one(self):
        # Not an error -- the payload build would have failed -- but the key must
        # not equal the key computed while the feed was there.
        before = self.payload_key()
        self.assertNotEqual(before, self.payload_key(feeds=self.root / 'no-feeds'))

    def test_a_transform_tool_moves_the_key(self):
        before = self.payload_key()
        write(self.out / 'tree' / 'scripts' / 'patch-armcpu-validate.py', 'print("armcpu, edited")\n')
        self.assertNotEqual(before, self.payload_key())

    def test_a_tool_appearing_is_a_new_key(self):
        before = self.payload_key()
        write(self.out / 'tree' / 'scripts' / 'seal-source-crypto-kernel.py', 'print("seal")\n')
        self.assertNotEqual(before, self.payload_key())

    def test_a_tool_board_toml_names_moves_the_key(self):
        declared = BOARD_TOML.replace('chip_id = "8140"',
                                      'chip_id = "8140"\ntool = "scripts/adt-generate.py"')
        write(self.device / 'board.toml', declared)
        write(self.out / 'tree' / 'scripts' / 'adt-generate.py', 'print("adt")\n')
        before = self.payload_key()
        write(self.out / 'tree' / 'scripts' / 'adt-generate.py', 'print("adt, edited")\n')
        self.assertNotEqual(before, self.payload_key())

    def test_the_framework_modules_that_pack_the_volume_move_the_key(self):
        before = self.payload_key()
        write(self.unixnu / 'scripts' / 'unixnu' / 'payload.py', '# payload, edited\n')
        self.assertNotEqual(before, self.payload_key())

    def test_any_board_toml_byte_moves_the_key(self):
        # board.toml is hashed whole on purpose: projecting it to "the relevant
        # sections" is the optimisation that later forgets a section.  A comment
        # moving the key costs one rebuild and cannot ship a wrong image.
        before = self.payload_key()
        write(self.device / 'board.toml', BOARD_TOML + '\n# a comment\n')
        self.assertNotEqual(before, self.payload_key())

    # -- bootimg: the image is the fd, the ramdisk and the tree -------------

    def test_the_boot_images_inputs_give_a_stable_key(self):
        self.assertEqual(self.bootimg_key(), self.bootimg_key())

    def test_the_firmware_volume_moves_the_boot_key(self):
        before = self.bootimg_key()
        write(self.uefi / FD, b'firmware-volume-two')
        self.assertNotEqual(before, self.bootimg_key())

    def test_the_payload_moves_the_boot_key_because_it_is_the_ramdisk(self):
        before = self.bootimg_key()
        write(self.out / 'payload' / 'payload.img', b'payload-two')
        self.assertNotEqual(before, self.bootimg_key())

    def test_the_compiled_tree_moves_the_boot_key(self):
        before = self.bootimg_key()
        write(self.out / 'device-tree' / 'hardware.dtb', b'dtb-two')
        self.assertNotEqual(before, self.bootimg_key())

    def test_the_uefi_config_moves_the_boot_key(self):
        before = self.bootimg_key()
        write(self.uefi / 'Resources' / 'Configs' / 'mondrian.toml', 'config = "mondrian"\n# edited\n')
        self.assertNotEqual(before, self.bootimg_key())

    def test_a_second_target_or_another_boards_config_is_not_an_input(self):
        # The fd is resolved from board.toml [firmware] fd, the way `unixnu
        # bootimg` resolves it -- not by picking one of the files a find returns.
        before = self.bootimg_key()
        write(self.uefi / 'Build' / 'mondrianPkg' / 'RELEASE_CLANGPDB' / 'FV' / 'SILICIUM_UEFI.fd', b'other')
        write(self.uefi / 'Resources' / 'Configs' / 'pong.toml', 'config = "pong"\n')
        self.assertEqual(before, self.bootimg_key())

    # -- kernel: the series, its list and the recipe ------------------------

    def test_the_kernels_inputs_give_a_stable_key(self):
        self.assertEqual(self.kernel_key(), self.kernel_key())

    def test_a_series_patch_byte_moves_the_kernel_key(self):
        before = self.kernel_key()
        write(self.device / 'patches' / 'xnu-12377' / 'second.patch',
              'diff --git a/b.c b/b.c\n--- a/b.c\n+++ b/b.c\n@@ -1 +1 @@\n-one\n+three\n')
        self.assertNotEqual(before, self.kernel_key())

    def test_the_series_order_moves_the_kernel_key(self):
        # The same patches applied in the other order are a different kernel.
        before = self.kernel_key()
        write(self.device / 'patches' / 'xnu-12377' / 'series',
              '# xnu-12377, applied in this order\nsecond.patch\n\nfirst.patch\n')
        self.assertNotEqual(before, self.kernel_key())

    def test_a_series_comment_does_not_move_the_kernel_key(self):
        # The comment is the file's prose, not its input: a note added to the
        # series must not cost 271 s.
        before = self.kernel_key()
        write(self.device / 'patches' / 'xnu-12377' / 'series',
              '# xnu-12377, applied in this order\n# a note added later\nfirst.patch\n\nsecond.patch\n')
        self.assertEqual(before, self.kernel_key())

    def test_the_defconfig_moves_the_kernel_key(self):
        # CONFIG_XNU_* become XNU_* make variables, so the defconfig is source.
        before = self.kernel_key()
        write(self.device / 'configs' / 'mondrian_ios27_defconfig',
              'CONFIG_XNU_CPU_ARM64E=y\nCONFIG_XNU_4K_PAGE=n\n')
        self.assertNotEqual(before, self.kernel_key())

    def test_any_kernel_board_toml_byte_moves_the_key(self):
        # [kernel] archives, config_fragments and the os_overrides that replace
        # them live here; hashed whole because projecting it forgets a table.
        before = self.kernel_key()
        write(self.device / 'board.toml', BOARD_TOML + '\n# a comment\n')
        self.assertNotEqual(before, self.kernel_key())

    def test_every_named_kernel_input_moves_the_key(self):
        inputs = {
            'the conf-files list': self.device / 'patches' / 'xnu-12377' / 'conf-files.txt',
            'the framework kernel module': self.unixnu / 'scripts' / 'unixnu' / 'kernel.py',
            'the framework patch module': self.unixnu / 'scripts' / 'unixnu' / 'patches.py',
            'the vendored builder': self.device / 'scripts' / 'build-xnu-generic.sh',
            'the conf-files hook': self.device / 'scripts' / 'k60-conf-files-hook.py',
            'a transform tool': self.out / 'tree' / 'scripts' / 'patch-sandbox-label-update.py',
        }
        for name, path in inputs.items():
            with self.subTest(input=name):
                original = path.read_bytes()
                before = self.kernel_key()
                write(path, original + b'\n# edited\n')
                moved = self.kernel_key()
                write(path, original)
                self.assertNotEqual(before, moved)

    def test_the_macho_itself_is_not_a_kernel_input(self):
        # The key decides whether to run the step that writes the macho, so the
        # macho cannot be in it: the stamp rewrite would rebuild forever.
        before = self.kernel_key()
        write(self.out / 'kernel' / 'kernel.macho', b'kernel-two')
        self.assertEqual(before, self.kernel_key())

    def test_a_dts_edit_moves_the_payload_key_but_not_the_kernel_key(self):
        # The payload compiles hardware.dtb, the kernel does not: a dts edit has
        # to rebuild the payload and leave the 271 s kernel alone.
        payload_before, kernel_before = self.payload_key(), self.kernel_key()
        write(self.device / 'dts' / 'mondrian.dts', '/dts-v1/;\n/ { model = "Redmi K60 Pro"; };\n')
        self.assertNotEqual(payload_before, self.payload_key())
        self.assertEqual(kernel_before, self.kernel_key())

    def test_a_series_entry_that_is_not_a_plain_name_is_refused(self):
        # `component:...` resolves inside another module; hashing whatever file
        # happened to match would be worse than refusing.
        write(self.device / 'patches' / 'xnu-12377' / 'series', 'arch:patches/xnu/series\n')
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = self.helper.main(self.argv_for('kernel'))
        self.assertEqual(code, 2)
        self.assertEqual(out.getvalue(), '')
        self.assertIn('arch:patches/xnu/series', err.getvalue())

    def test_a_missing_kernel_input_is_an_error_not_a_key(self):
        required = {
            'the series': self.device / 'patches' / 'xnu-12377' / 'series',
            'a listed patch': self.device / 'patches' / 'xnu-12377' / 'second.patch',
            'the conf-files list': self.device / 'patches' / 'xnu-12377' / 'conf-files.txt',
            'the defconfig': self.device / 'configs' / 'mondrian_ios27_defconfig',
            'board.toml': self.device / 'board.toml',
        }
        for name, path in required.items():
            with self.subTest(missing=name):
                original = path.read_bytes()
                path.unlink()
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = self.helper.main(self.argv_for('kernel'))
                write(path, original)
                self.assertEqual(code, 2)
                self.assertEqual(out.getvalue(), '')
                self.assertIn(path.name, err.getvalue())

    def test_the_real_repository_series_is_all_plain_patches(self):
        # The helper hashes every patch the real series lists; a prefixed entry
        # or a listed file that does not exist has to fail here, not in a build.
        argv = ['kernel', '--device', str(HERE.parent.parent), '--out', str(self.out),
                '--unixnu', str(self.unixnu)]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.helper.main(argv), 0)

    # -- refusals and the explain output ------------------------------------

    def test_a_missing_kernel_is_an_error_not_a_key(self):
        os.unlink(self.out / 'kernel' / 'kernel.macho')
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = self.helper.main(['payload', '--device', str(self.device), '--out', str(self.out),
                                     '--series-fingerprint', 'cc85fd583e77ac7b 240',
                                     '--unique-chip-id', '4d4f4e445249414e'])
        self.assertEqual(code, 2)
        self.assertEqual(out.getvalue(), '')
        self.assertIn('kernel.macho', err.getvalue())

    def test_an_empty_series_fingerprint_is_refused(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = self.helper.main(['payload', '--device', str(self.device), '--out', str(self.out),
                                     '--series-fingerprint', '   ', '--unique-chip-id', '4d4f4e445249414e'])
        self.assertEqual(code, 2)
        self.assertEqual(out.getvalue(), '')

    def test_a_missing_payload_or_tree_blocks_the_boot_key(self):
        os.unlink(self.out / 'payload' / 'payload.img')
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.helper.main(['bootimg', '--device', str(self.device),
                                               '--out', str(self.out), '--uefi', str(self.uefi)]), 2)
        write(self.out / 'payload' / 'payload.img', b'payload-one')
        os.unlink(self.out / 'device-tree' / 'hardware.dtb')
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.helper.main(['bootimg', '--device', str(self.device),
                                               '--out', str(self.out), '--uefi', str(self.uefi)]), 2)

    def test_a_boot_key_without_a_uefi_checkout_is_refused(self):
        with mock.patch.dict(os.environ, {'UNIXNU_UEFI': ''}):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(self.helper.main(['bootimg', '--device', str(self.device),
                                                   '--out', str(self.out)]), 2)

    def test_explain_names_every_input_the_key_is_made_of(self):
        for stage in ('payload', 'bootimg', 'kernel'):
            code, entries = self.explain(stage)
            self.assertEqual(code, 0)
            args = self.helper.parser().parse_args(self.argv_for(stage))
            self.assertEqual(len(entries), len(self.helper.lines_for(args)))
            # A digest per line, and the kernel's own list names each patch, so a
            # moved key can be read back to the file that moved it.
            self.assertTrue(all(len(entry.split()) == 2 for entry in entries))

    def test_the_real_repository_still_parses(self):
        # The helper is run by the build script; a broken import or a changed
        # board.toml layout has to fail here, not after a 452 s kernel build.
        repo = HERE.parent.parent
        argv = ['payload', '--device', str(repo), '--out', str(self.out),
                '--series-fingerprint', 'cc85fd583e77ac7b 240', '--unique-chip-id', '4d4f4e445249414e']
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = self.helper.main(argv)
        # Either it computes a key from the artifacts on disk, or it says which
        # one is missing -- never a traceback.
        self.assertIn(code, (0, 2))


if __name__ == '__main__':
    unittest.main(verbosity=2)
