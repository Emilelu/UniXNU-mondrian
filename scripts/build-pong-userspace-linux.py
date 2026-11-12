#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build native 20G81 Turnip, the Rust/Metal bridge and its discovery bundle on Linux.

Uses real iPhoneOS SDK headers/imports and Clang + Mach-O LLD, not xcrun,
XNU's kernel SDK or its no-op codesign shim. Source archives and patches are
reconstructed from the recorded revisions without modifying the reference
checkouts. Only product libraries are compiled; no tests, shader fixtures,
benchmarks, image verification, device operations or automatic publication.

Run --prepare-only first, then the printed cargo generate-lockfile/fetch
commands. The product build is --locked --offline and keeps Cargo.lock,
source/patch records, frontend objects and the Rust archive for relinking.
The generated publication marker is always 0: activation belongs to the
hardware-qualified integration step, not to this builder.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ROOT / 'drivers/PongMetal/userspace-inputs.json'


def write_changed(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = data.encode() if isinstance(data, str) else data
    if not path.is_file() or path.read_bytes() != data:
        path.write_bytes(data)


def dump(path, value):
    write_changed(path, json.dumps(value, indent=2, sort_keys=True) + '\n')


def git(repository, *args):
    return subprocess.check_output(
        ['git', '-C', str(repository), *args], stderr=subprocess.PIPE)


def git_file(repository, revision, path):
    return git(repository, 'show', revision + ':' + path)


def executable(value):
    found = shutil.which(str(value))
    if not found:
        raise RuntimeError('Required host executable is missing: ' + str(value))
    return str(Path(found).absolute())


class Builder:
    def __init__(self, args, pins):
        self.args, self.pins = args, pins
        self.out = args.output_dir.resolve()
        self.out.mkdir(parents=True, exist_ok=True)
        self.commands = []
        self.source_records = {}
        self.cc = executable(args.cc)
        self.cpp = executable(args.cxx)
        self.ld = executable(args.linker)
        self.ar = executable(args.ar)
        self.strip = executable(args.strip)
        self.pkg_config = executable(args.pkg_config)
        self.sdk = args.sdk_root.resolve()
        settings = json.loads((self.sdk / 'SDKSettings.json').read_text())
        if 'iphoneos' not in settings.get('SupportedTargets', {}):
            raise RuntimeError('--sdk-root must be a real device iPhoneOS SDK, not a kernel fakeroot or simulator SDK')
        self.sdk_version = settings['Version']
        self.frameworks = self.sdk / 'System/Library/Frameworks'
        self.cxx_headers = self.sdk / 'usr/include/c++/v1'
        if not (self.cxx_headers / '__config_site').is_file():
            raise RuntimeError('The iPhoneOS SDK libc++ headers are required; do not substitute host or Android libc++')
        for name in ('Foundation', 'CoreFoundation', 'Metal', 'IOSurface', 'QuartzCore', 'CoreGraphics', 'IOKit'):
            directory = self.frameworks / (name + '.framework')
            if not (directory / (name + '.tbd')).is_file():
                raise RuntimeError('Real iPhoneOS framework import is missing: ' + str(directory))
        if not (self.sdk / 'usr/lib/libc++.tbd').is_file():
            raise RuntimeError('The SDK import for the guest /usr/lib/libc++.1.dylib is missing')
        self.guest = pins['guest']
        self.flags = ['-target', self.guest['clang_target'], '-isysroot', str(self.sdk),
                      '-F' + str(self.frameworks), '-fstack-protector-strong']
        # Explicit SDK libc++ avoids Linux Clang's host header-search defaults.
        self.cpp_flags = self.flags + ['-stdlib=libc++', '-nostdinc++',
                                      '-isystem', str(self.cxx_headers)]
        self.link_flags = ['--ld-path=' + self.ld,
                           '-Wl,-platform_version,ios,' + self.guest['version'] + ',' + self.sdk_version,
                           '-Wl,-adhoc_codesign', '-Wl,-no_fixup_chains']
        self.env = dict(os.environ)
        for key in list(self.env):
            if key.startswith(('IR3_', 'FD_MESA_', 'NIR_', 'MESA_SHADER_', 'TU_', 'NMB_', 'NATIVE_METAL_',
                               'METAL2VULKAN_', 'CARGO_TARGET_', 'RUSTFLAGS', 'CARGO_ENCODED_RUSTFLAGS')):
                del self.env[key]
        for key in ('DEVELOPER_DIR', 'MACOSX_DEPLOYMENT_TARGET', 'UNIXNU_SDKROOT',
                    'UNIXNU_SDK_VERSION', 'XNU_TOOLCHAIN_BIN', 'CROSS_CLANG',
                    'CROSS_EXTRA_FLAGS', 'CCC_OVERRIDE_OPTIONS', 'CPATH', 'C_INCLUDE_PATH',
                    'CPLUS_INCLUDE_PATH', 'OBJC_INCLUDE_PATH', 'LIBRARY_PATH',
                    'DYLD_LIBRARY_PATH', 'DYLD_FRAMEWORK_PATH', 'DYLD_INSERT_LIBRARIES'):
            self.env.pop(key, None)
        self.env.update(CC=self.cc, CXX=self.cpp, CFLAGS='', CXXFLAGS='', CPPFLAGS='', LDFLAGS='',
                        SDKROOT=str(self.sdk), IPHONEOS_DEPLOYMENT_TARGET=self.guest['version'],
                        PKG_CONFIG_PATH='', PKG_CONFIG_LIBDIR=str(self.out / 'pkgconfig'),
                        PKG_CONFIG_SYSROOT_DIR='', LC_ALL='C', PYTHONHASHSEED='0',
                        TMPDIR=str(self.out / 'tmp'))
        (self.out / 'tmp').mkdir(exist_ok=True)
        self.env['PATH'] = os.pathsep.join([
            str(args.venv.resolve() / 'bin'), str(args.cargo_directory.resolve()),
            *([str(args.tools_directory.resolve())] if args.tools_directory else []),
            '/usr/bin', '/bin'])

    def run(self, command, log, cwd=None, **kwargs):
        command = [str(item) for item in command]
        self.commands.append(dict(argv=command, cwd=str(cwd or self.out), log=str(log)))
        with log.open('w') as stream:
            result = subprocess.run(command, cwd=cwd or self.out, env=self.env,
                                    stdout=stream, stderr=subprocess.STDOUT, **kwargs)
        if result.returncode:
            raise RuntimeError('Build command failed; see ' + str(log))

    def source(self, name, repository, revision, patches):
        # Each patch carries its immutable Git blob ID (or this device source hash).
        record = dict(repository=str(repository.resolve()), revision=revision,
                      tree=git(repository, 'rev-parse', revision + '^{tree}').decode().strip(),
                      patches=[entry for entry, _ in patches])
        identity = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()[:16]
        destination = self.out / 'sources' / (name + '-' + identity)
        complete = destination / '.pong-source.json'
        if not complete.is_file():
            destination.mkdir(parents=True, exist_ok=False)
            archive = self.out / 'sources' / (name + '-' + identity + '.tar')
            with archive.open('wb') as stream:
                subprocess.run(['git', '-C', str(repository), 'archive', '--format=tar', revision],
                               env=self.env, stdout=stream, check=True)
            with tarfile.open(archive) as stream:
                stream.extractall(destination, filter='data')
            for index, (entry, data) in enumerate(patches):
                patch = self.out / 'patches' / name / ('%02d-' % index + Path(entry['path']).name)
                write_changed(patch, data)
                self.run(['git', 'apply', '--whitespace=nowarn', str(patch)],
                         self.out / ('%s-patch-%02d.log' % (name, index)), cwd=destination)
            dump(complete, record)
        self.source_records[name] = dict(record, directory=str(destination))
        return destination

    def record(self):
        return dict(guest=self.guest, sdk=dict(directory=str(self.sdk), version=self.sdk_version,
                    cpp_headers=str(self.cxx_headers), cpp_runtime='/usr/lib/libc++.1.dylib'),
                    source_inputs=str(INPUTS), sources=self.source_records,
                    compiler=self.cc, cpp_compiler=self.cpp, linker=self.ld,
                    compile_flags=self.flags, cpp_flags=self.cpp_flags, link_flags=self.link_flags,
                    commands=self.commands, hardware_executed=False,
                    image_verification='not performed', publication_enabled=False)


def recorded_patches(repository, revision, paths):
    result = []
    for path in paths:
        blob = git(repository, 'rev-parse', revision + ':' + path).decode().strip()
        result.append((dict(repository=str(repository.resolve()), revision=revision,
                            path=path, blob=blob), git_file(repository, revision, path)))
    return result


def device_patches(paths):
    return [(dict(repository=str(ROOT), path=path,
                  sha256=hashlib.sha256((ROOT / path).read_bytes()).hexdigest()),
             (ROOT / path).read_bytes()) for path in paths]


def prepare_sources(builder):
    a, pins = builder.args, builder.pins
    core = pins['core_inputs']
    mesa_record = json.loads(git_file(a.core, core['revision'], core['mesa_record']))
    translator_record = json.loads(git_file(a.core, core['revision'], core['translator_record']))
    if mesa_record['mesa']['commit'] != core['mesa_commit'] or mesa_record['patches'] != core['mesa_patches']:
        raise RuntimeError('The recorded nine-patch Mesa source identity differs')
    if translator_record['translator']['commit'] != core['translator_commit']:
        raise RuntimeError('The recorded Pong translator source identity differs')
    module = a.metal_source or a.core / 'drivers/AdrenoMetal'
    metal = pins['metal_module']
    mesa_patches = recorded_patches(a.core, core['revision'], core['mesa_patches'])
    mesa_patches += device_patches(pins['device_patches']['mesa'])
    translator_patches = recorded_patches(module, metal['revision'], metal['patches'])
    translator_patches += device_patches(pins['device_patches']['translator'])
    mesa = builder.source('mesa', a.mesa, core['mesa_commit'], mesa_patches)
    translator = builder.source('metal2vulkan', a.translator, core['translator_commit'], translator_patches)
    dump(builder.out / 'upstream-mesa-inputs.json', mesa_record)
    dump(builder.out / 'upstream-translator-inputs.json', translator_record)
    builder.env['MESA_GIT_SHA1_OVERRIDE'] = core['mesa_commit']
    builder.env['SOURCE_DATE_EPOCH'] = git(a.mesa, 'show', '-s', '--format=%ct', core['mesa_commit']).decode().strip()
    return mesa, translator, module


def prepare_meson(builder):
    out = builder.out
    zlib_header = (builder.sdk / 'usr/include/zlib.h').read_text()
    version = re.search(r'^#define\s+ZLIB_VERSION\s+"([^"]+)"', zlib_header, re.M)
    if not version or not (builder.sdk / 'usr/lib/libz.tbd').is_file():
        raise RuntimeError('Real SDK zlib header/import is required')
    # Isolate pkg-config from Linux libraries. This metadata describes the real
    # SDK zlib, whose headers, import and guest implementation are not replaced.
    write_changed(out / 'pkgconfig/zlib.pc', '\n'.join([
        'prefix=' + str(builder.sdk), 'libdir=${prefix}/usr/lib', 'includedir=${prefix}/usr/include',
        'Name: zlib', 'Description: iPhoneOS SDK zlib import', 'Version: ' + version[1],
        'Libs: -L${libdir} -lz', 'Cflags: -I${includedir}', '']))
    cross = out / 'pong-ios16.cross'
    text = '[binaries]\n'
    for key, value in (('c', builder.cc), ('cpp', builder.cpp), ('objc', builder.cc),
                       ('ar', builder.ar), ('strip', builder.strip), ('pkg-config', builder.pkg_config)):
        text += key + ' = ' + repr(value) + '\n'
    text += ("[host_machine]\nsystem = 'darwin'\ncpu_family = 'aarch64'\n"
             "cpu = 'arm64'\nendian = 'little'\n[properties]\nneeds_exe_wrapper = true\n"
             '[built-in options]\n')
    for key, flags in (('c_args', builder.flags), ('cpp_args', builder.cpp_flags), ('objc_args', builder.flags),
                       ('c_link_args', builder.flags + builder.link_flags),
                       ('cpp_link_args', builder.cpp_flags + builder.link_flags),
                       ('objc_link_args', builder.flags + builder.link_flags)):
        text += key + ' = ' + repr(flags) + '\n'
    write_changed(cross, text)
    native = out / 'pong-host.native'
    write_changed(native, '[binaries]\nc = ' + repr(builder.cc) + '\ncpp = ' + repr(builder.cpp) +
                  '\n[ built-in options ]\nc_args = []\ncpp_args = []\nc_link_args = []\ncpp_link_args = []\n')
    return cross, native


def prepare_cargo(builder, translator, module):
    bridge = builder.out / 'metal'
    bridge.mkdir(exist_ok=True)
    seed = git_file(module, builder.pins['metal_module']['revision'],
                    builder.pins['metal_module']['dependency_lock'])
    external = [p for p in tomllib.loads(seed.decode())['package'] if 'source' in p]
    versions = {p['name']: p['version'] for p in external}
    manifest = bridge / 'Cargo.toml'
    dependencies = [
        'metal2vulkan = { path = ' + json.dumps(str(translator / 'crates/metal2vulkan')) + ', features = ["ash"] }',
        'metal2vulkan-runtime = { path = ' + json.dumps(str(translator / 'crates/metal2vulkan-runtime')) + ' }',
        'libc = "=' + versions['libc'] + '"',
        'serde_json = "=' + versions['serde_json'] + '"',
        'sha2 = "=' + versions['sha2'] + '"',
    ]
    write_changed(manifest, '\n'.join([
        '[package]', 'name = "pong-metal-bridge"', 'version = "0.1.0"', 'edition = "2024"',
        'rust-version = "1.98"', '[workspace]', '[lib]', 'crate-type = ["staticlib"]',
        'path = ' + json.dumps(str(ROOT / 'drivers/PongMetal/bridge/lib.rs')),
        '[dependencies]', *dependencies,
        '[profile.release]', 'panic = "unwind"', 'debug = 0', '']))
    write_changed(bridge / 'dependency-seed.lock', seed)
    if not (bridge / 'Cargo.lock').exists():
        write_changed(bridge / 'Cargo.lock', seed)
    cargo_directory = builder.args.cargo_directory.resolve()
    cargo = str(cargo_directory / 'cargo')
    # Cargo reads configuration from its cwd, not --manifest-path's directory.
    # Product targets never pass through the macOS SDK-discovery linker path.
    rustflags = ['-C', 'linker=' + builder.cc]
    for flag in builder.flags + builder.link_flags:
        rustflags += ['-C', 'link-arg=' + flag]
    write_changed(bridge / '.cargo/config.toml', '\n'.join([
        '[target.' + builder.guest['rust_target'] + ']',
        'linker = ' + json.dumps(builder.cc), 'rustflags = ' + json.dumps(rustflags), '']))
    builder.env['CARGO_HOME'] = str(builder.out / 'cargo-home')
    builder.env['CC_' + builder.guest['rust_target'].replace('-', '_')] = builder.cc
    builder.env['CXX_' + builder.guest['rust_target'].replace('-', '_')] = builder.cpp
    builder.env['CFLAGS_' + builder.guest['rust_target'].replace('-', '_')] = shlex.join(builder.flags)
    builder.env['CXXFLAGS_' + builder.guest['rust_target'].replace('-', '_')] = shlex.join(builder.cpp_flags)
    builder.env['AR_' + builder.guest['rust_target'].replace('-', '_')] = builder.ar
    commands = [
        [cargo, '+' + builder.pins['host']['rust_toolchain'], 'generate-lockfile', '--manifest-path', str(manifest)],
        [cargo, '+' + builder.pins['host']['rust_toolchain'], 'fetch', '--locked', '--manifest-path', str(manifest),
         '--target', builder.guest['rust_target']],
    ]
    dump(bridge / 'dependency-preparation.json', dict(cwd=str(bridge), commands=commands,
         environment=dict(CARGO_HOME=builder.env['CARGO_HOME'], SDKROOT=str(builder.sdk),
                          IPHONEOS_DEPLOYMENT_TARGET=builder.guest['version']),
         seed_record=builder.pins['metal_module'],
         note='Run these fetch-only commands before building; the seed lacks runtime Vulkan-loader packages.'))
    return manifest, commands


def build_turnip(builder, mesa, cross, native):
    a = builder.args
    meson = executable(a.venv.resolve() / 'bin/meson')
    ninja = executable(a.ninja)
    for tool in ('bison', 'flex', 'glslangValidator'):
        if not shutil.which(tool, path=builder.env['PATH']):
            raise RuntimeError('Missing host generator ' + tool + '; install the recorded host prerequisites first')
    abi = (a.abi_directory or ROOT / 'drivers/PongAdreno/submit').resolve()
    if not (abi / 'NativeAdrenoABI.h').is_file():
        raise RuntimeError('--abi-directory must hold the real NativeAdrenoABI.h')
    turnip = builder.out / 'turnip'
    options = [
        '-Dgallium-drivers=', '-Dvulkan-drivers=freedreno', '-Dfreedreno-kmds=darwin',
        '-Dtu-darwin-abi-dir=' + str(abi), '-Dplatforms=macos', '-Dglx=disabled',
        '-Degl=disabled', '-Dgbm=disabled', '-Dopengl=false', '-Dgles1=disabled', '-Dgles2=disabled',
        '-Dllvm=disabled', '-Dshared-glapi=disabled', '-Dxmlconfig=disabled', '-Dshader-cache=disabled',
        '-Dtools=', '-Dbuild-tests=false', '-Dvideo-codecs=', '-Dvulkan-layers=',
        '-Dlibunwind=disabled', '-Dlmsensors=disabled', '-Dvalgrind=disabled', '-Dexpat=disabled',
        '-Dzstd=disabled', '-Ddisplay-info=disabled', '-Dallow-fallback-for=',
        '-Dbuildtype=release', '-Db_ndebug=true', '-Ddefault_library=static',
        '-Dtu-builtin-source-id=', '-Dtu-builtin-pack-header=',
    ]
    # Reconfigure also rereads the explicit cross/native files on rebuilds.
    command = [meson, 'setup', str(turnip), str(mesa), '--wrap-mode=nodownload',
               '--cross-file', str(cross), '--native-file', str(native), '--prefix=/usr']
    if (turnip / 'build.ninja').is_file():
        command += ['--reconfigure']
    builder.run(command + options, builder.out / 'turnip-configure.log')
    # Building this target alone excludes every host probe/fixture/tool target.
    library = turnip / 'src/freedreno/vulkan/libvulkan_freedreno.dylib'
    builder.run([ninja, '-C', str(turnip), '-j' + str(a.jobs),
                 'src/freedreno/vulkan/libvulkan_freedreno.dylib'], builder.out / 'turnip-build.log')
    return library


def build_bridge(builder, manifest):
    cargo = executable(builder.args.cargo_directory.resolve() / 'cargo')
    bridge = manifest.parent
    lock = tomllib.loads((bridge / 'Cargo.lock').read_text())
    if not any(p['name'] == 'pong-metal-bridge' for p in lock['package']):
        raise RuntimeError('Cargo.lock is only the source seed: run the printed dependency-preparation commands first')
    target = builder.guest['rust_target']
    rustlib = subprocess.check_output(
        [str(builder.args.cargo_directory.resolve() / 'rustc'),
         '+' + builder.pins['host']['rust_toolchain'], '--print', 'target-libdir', '--target', target],
        env=builder.env, text=True).strip()
    if not any(Path(rustlib).glob('libstd-*.rlib')):
        raise RuntimeError('Install the real Rust iOS standard library: rustup target add --toolchain ' +
                           builder.pins['host']['rust_toolchain'] + ' ' + target)
    frontend = bridge / 'PongMetalFrontend.o'
    builder.run([builder.cpp, *builder.cpp_flags, '-std=c++17', '-fobjc-arc', '-fblocks', '-Os',
                 '-Wall', '-Wextra', '-Werror', '-Wno-deprecated-declarations',
                 '-I' + str(ROOT / 'drivers/PongMetal'), '-c',
                 ROOT / 'drivers/PongMetal/NativeBridgeMetalFrontend.mm', '-o', frontend],
                builder.out / 'metal-frontend.log')
    builder.run([cargo, '+' + builder.pins['host']['rust_toolchain'], 'build', '--release', '--lib',
                 '--locked', '--offline', '--manifest-path', manifest, '--target', target,
                 '--target-dir', builder.out / 'cargo-target', '--jobs', str(builder.args.jobs)],
                builder.out / 'metal-cargo.log', cwd=bridge)
    archive = builder.out / 'cargo-target' / target / 'release/libpong_metal_bridge.a'
    library = bridge / 'PongMetalBridge.dylib'
    builder.run([builder.cpp, *builder.cpp_flags, *builder.link_flags, '-dynamiclib',
                 '-Wl,-install_name,@rpath/PongMetalBridge.dylib',
                 frontend, '-Wl,-force_load,' + str(archive),
                 '-framework', 'Foundation', '-framework', 'CoreFoundation', '-framework', 'Metal',
                 '-framework', 'IOSurface', '-framework', 'QuartzCore', '-framework', 'CoreGraphics',
                 '-lobjc', '-liconv', '-lresolv', '-o', library], builder.out / 'metal-link.log')
    report = builder.record()
    report.update(frontend=str(frontend), archive=str(archive), library=str(library),
                  cargo_lock=str(bridge / 'Cargo.lock'), dependencies=lock['package'])
    dump(bridge / 'build-report.json', report)
    return library


def build_plugin(builder, bridge, turnip):
    plugin = builder.out / 'plugin'
    bundle = plugin / 'PongAdrenoMetal.bundle'
    bundle.mkdir(parents=True, exist_ok=True)
    builder.run([builder.cpp, *builder.cpp_flags, *builder.link_flags,
                 '-std=c++17', '-fobjc-arc', '-fblocks', '-Os', '-Wall', '-Wextra', '-Werror',
                 '-Wno-deprecated-declarations', '-I' + str(ROOT / 'drivers/PongMetal'),
                 '-I' + str(ROOT / 'drivers/PongAdreno/submit'), '-dynamiclib',
                 ROOT / 'drivers/PongMetal/PongMetalPlugin.mm', bridge,
                 '-framework', 'Foundation', '-framework', 'CoreFoundation', '-framework', 'Metal', '-lobjc',
                 '-Wl,-rpath,@loader_path',
                 '-Wl,-install_name,@rpath/PongAdrenoMetal.bundle/PongAdrenoMetal',
                 '-o', bundle / 'PongAdrenoMetal'], builder.out / 'plugin-link.log')
    shutil.copy2(bridge, bundle / 'PongMetalBridge.dylib')
    shutil.copy2(turnip, bundle / 'libvulkan_freedreno.dylib')
    for name in ('PongAdrenoMetal', 'PongMetalBridge.dylib', 'libvulkan_freedreno.dylib'):
        (bundle / name).chmod(0o755)
    write_changed(bundle / 'Info.plist', plistlib.dumps(dict(
        CFBundleIdentifier='dev.unixnu.pong.Metal', CFBundleName='PongAdrenoMetal',
        CFBundleExecutable='PongAdrenoMetal', CFBundlePackageType='BNDL', CFBundleVersion='1',
        NSPrincipalClass='PongAdrenoMetalDevice', MinimumOSVersion=builder.guest['version'],
        CFBundleSupportedPlatforms=['iPhoneOS'])))
    clients = ['backboardd', 'SpringBoard', 'CollectionsPoster', 'WidgetRenderer_Default',
               'PosterBoard', 'Weather', 'WeatherPoster', 'GradientPosterExtension']
    write_changed(plugin / 'PongAdrenoMetal.clients', '\n'.join(clients) + '\n')
    write_changed(plugin / 'PongAdrenoMetal.publish', '0\n')
    report = builder.record()
    report.update(bundle=str(bundle), clients=clients,
                  discovery='IOAcceleratorES -> MetalPluginName -> NSBundle principal class',
                  required_properties=['PongAdrenoCPReady', 'PongMetal20G81Enabled'],
                  activation='Separate parent-owned step after real CP fences, 20G81 ABI and Vulkan device creation',
                  hardware_acceleration_confirmed=False,
                  remaining=['Actual SM8475 power/monitor authorization and CP fence completion',
                             'Actual 20G81 client rendering and accelerated IOSurface presentation'])
    dump(plugin / 'build-report.json', report)
    return bundle


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--core', type=Path, required=True)
    p.add_argument('--mesa', type=Path, required=True)
    p.add_argument('--translator', type=Path, required=True)
    p.add_argument('--metal-source', type=Path, help='AdrenoMetal Git checkout; default: <core>/drivers/AdrenoMetal')
    p.add_argument('--sdk-root', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--venv', type=Path, required=True, help='Environment with the recorded requirements-adreno-compiler.txt')
    p.add_argument('--tools-directory', type=Path, help='Optional native bison/flex/glslang directory')
    p.add_argument('--abi-directory', type=Path, help='Default: this device drivers/PongAdreno/submit')
    p.add_argument('--cargo-directory', type=Path, default=Path.home() / '.cargo/bin')
    p.add_argument('--cc', default='clang-18')
    p.add_argument('--cxx', default='clang++-18')
    p.add_argument('--linker', default='ld64.lld-18')
    p.add_argument('--ar', default='llvm-ar-18')
    p.add_argument('--strip', default='llvm-strip-18')
    p.add_argument('--pkg-config', default='pkg-config')
    p.add_argument('--ninja', default='ninja')
    p.add_argument('--jobs', type=int, default=6)
    p.add_argument('--prepare-only', action='store_true', help='Extract pinned sources and write build/dependency inputs; compile nothing')
    a = p.parse_args()
    if not sys.platform.startswith('linux') or sys.version_info < (3, 12):
        p.error('This builder requires Linux and Python 3.12 or later')
    if a.jobs < 1:
        p.error('--jobs must be positive')
    pins = json.loads(INPUTS.read_text())
    try:
        builder = Builder(a, pins)
        mesa, translator, module = prepare_sources(builder)
        cross, native = prepare_meson(builder)
        manifest, commands = prepare_cargo(builder, translator, module)
        dump(builder.out / 'source-build-inputs.json', builder.record())
        if a.prepare_only:
            print('Prepared native iOS product inputs; nothing compiled or published.')
            print('Run in ' + str(manifest.parent) + ':')
            print('export CARGO_HOME=' + shlex.quote(builder.env['CARGO_HOME']))
            for command in commands:
                print(shlex.join(command))
            print('Then repeat this builder command without --prepare-only.')
            return
        turnip = build_turnip(builder, mesa, cross, native)
        bridge = build_bridge(builder, manifest)
        bundle = build_plugin(builder, bridge, turnip)
        dump(builder.out / 'build-report.json', dict(builder.record(), bundle=str(bundle),
             turnip=str(turnip), bridge=str(bridge),
             publication_marker=str(bundle.parent / 'PongAdrenoMetal.publish')))
        print(bundle)
    except (OSError, RuntimeError, subprocess.CalledProcessError, tarfile.TarError) as error:
        raise SystemExit(str(error)) from error


if __name__ == '__main__':
    main()
