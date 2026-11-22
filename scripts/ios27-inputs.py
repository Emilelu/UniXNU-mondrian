#!/usr/bin/env python3
"""The input key of an iOS 27 image stage.

`scripts/build-ios27-linux.sh` skips the payload and the boot image when the key
of their inputs equals the key recorded next to the artifact.  Measured
2026-11-21: the payload step shares 452 s with the kernel build and packing the
same 192 MB payload into boot.img costs another 171 s of a 975 s build, and
neither result changes while the inputs below stay byte-identical.

A key is the SHA-256 of one line per input, and a line carries the input's role
and the digest of its content -- no timestamp and no absolute path, so the
answer is "same" rather than "recent" and moving a checkout does not rebuild
anything.

What each stage depends on:

  payload   kernel/kernel.macho (after k60-fileset-stamp, which the build runs
            first), the patch series fingerprint, the unique chip id, board.toml
            (the [payload] and [adt] tables live there), the device tree its
            hardware.dtb is compiled from, the transform tools it runs out of
            <board>/tree/scripts, and the two framework modules that pack the
            volume.
  bootimg   the firmware volume, payload/payload.img (it is the ramdisk), the
            compiled device tree, board.toml ([bootimg] settings), and the
            Mu-Silicium pieces that decide the image layout.

The device tree sources are in the payload key on purpose.  The payload step
compiles hardware.dtb, so a dts edit leaves kernel.macho untouched; a key over
the kernel alone would reuse a payload that still carries the previous ADT.

  python3 scripts/ios27-inputs.py payload --device . --series-fingerprint "$(python3 scripts/series-fingerprint.py)" --unique-chip-id HEX
  python3 scripts/ios27-inputs.py bootimg --device . --uefi ../uefi-mondrian
  python3 scripts/ios27-inputs.py payload ... --explain    # one line per input on stderr

Exit 0 and the key on stdout, or exit 2 and nothing on stdout when an input the
build cannot do without is missing -- a key computed over a hole is not a key.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import sys
import tomllib

# The tools the payload step applies to the packed kernel, in the order
# unixnu/payload.py looks for them.  Absent is a value, not an omission: a tool
# that appears later has to move the key.
PAYLOAD_TOOLS = (
	'patch-armcpu-validate.py',
	'patch-sandbox-label-update.py',
	'patch-xnu-entry-probe.py',
	'seal-source-crypto-kernel.py',
)

# unixnu/payload.py and unixnu/devicetree.py build and write the volume.
FRAMEWORK_MODULES = ('payload.py', 'devicetree.py')

# Mu-Silicium decides the image layout; mkbootimg.py is self-contained, so this
# is the whole set -- BootShim/Makefile is here because the shim is assembled
# from it.
UEFI_LAYOUT_INPUTS = (
	'Resources/Scripts/mkbootimg.py',
	'BootShim/BootShim.S',
	'BootShim/Makefile',
)

TREE_SUFFIXES = ('.dts', '.dtsi', '.h')


class Missing(Exception):
	"""An input the build cannot do without is not on disk."""


def digest(path: pathlib.Path) -> str:
	"""SHA-256 of one file, streamed."""
	value = hashlib.sha256()
	with open(path, 'rb') as handle:
		for chunk in iter(lambda: handle.read(1 << 20), b''):
			value.update(chunk)
	return value.hexdigest()


def need(path: pathlib.Path, what: str) -> pathlib.Path:
	path = pathlib.Path(path)
	if not path.is_file():
		raise Missing(f'{what} is not on disk: {path}')
	return path


def line(role: str, value: str) -> str:
	return f'{role} {value}'


def text_line(role: str, text: str) -> str:
	return line(role, hashlib.sha256(text.strip().encode()).hexdigest())


def file_line(role: str, path: pathlib.Path) -> str:
	path = pathlib.Path(path)
	return line(role, digest(path) if path.is_file() else 'absent')


def tree_digest(root: pathlib.Path, suffixes=TREE_SUFFIXES) -> str:
	"""(relative path, content) over one directory, folded into one digest.

	The relative path is part of what is hashed, so renaming a file counts as a
	change; the absolute prefix is not, so moving the tree does not.
	"""
	root = pathlib.Path(root)
	if not root.is_dir():
		return 'absent'
	entries = []
	for path in sorted(root.rglob('*')):
		if path.is_file() and path.suffix in suffixes:
			entries.append(f'{path.relative_to(root).as_posix()} {digest(path)}')
	if not entries:
		return 'empty'
	return hashlib.sha256(('\n'.join(entries) + '\n').encode()).hexdigest()


def read_board(device: pathlib.Path) -> dict:
	path = need(pathlib.Path(device) / 'board.toml', 'board.toml')
	with open(path, 'rb') as handle:
		return tomllib.load(handle)


def resolve(device: pathlib.Path, reference: str) -> pathlib.Path:
	"""`device:dts/x.dts` and `dts/x.dts` both name a file inside the device."""
	_, _, relative = str(reference).partition(':')
	return pathlib.Path(device) / relative


def device_tree_lines(device: pathlib.Path, feeds: pathlib.Path | None) -> list[str]:
	"""The device tree the payload step compiles into hardware.dtb."""
	spec = read_board(device).get('device_tree', {})
	source = spec.get('source')
	if not source:
		return [line('dt-source', 'absent')]
	lines = [file_line('dt-source', resolve(device, source))]
	for entry in spec.get('include_dirs', []):
		prefix, _, relative = str(entry).partition(':')
		if prefix != 'soc':
			lines.append(line(f'dt-dir:{relative}', tree_digest(pathlib.Path(device) / relative)))
			continue
		# The SoC dtsi comes from a fetched feed, and the feed directory is named
		# after the commit it was fetched at, so a new feed is a new key on its
		# own.  Every matching feed is hashed: picking one would silently ignore
		# the other, and the feed the framework picks is the one that compiles.
		candidates = sorted(path for path in (feeds or pathlib.Path('/nonexistent')).glob(f'*/{relative}') if path.is_dir())
		if not candidates:
			lines.append(line(f'soc-dir:{relative}', 'unresolved'))
		for path in candidates:
			lines.append(line(f'soc-dir:{path.parent.name}/{relative}', tree_digest(path, ('.dts', '.dtsi', '.h'))))
	return lines


def board_tools(device: pathlib.Path) -> list[str]:
	"""Paths board.toml names for the payload step ([payload.adt].tool and so on).

	The step runs these out of <board>/tree, so their content is an input even
	though it is the framework that picks them.
	"""
	names: set[str] = set()

	def walk(node) -> None:
		if isinstance(node, dict):
			for key, value in node.items():
				if isinstance(value, str) and key.endswith('tool'):
					names.add(value)
				walk(value)
		elif isinstance(node, list):
			for item in node:
				walk(item)

	walk(read_board(device))
	return sorted(names)


def payload_lines(args) -> list[str]:
	device = pathlib.Path(args.device)
	out = pathlib.Path(args.out)
	unixnu = pathlib.Path(args.unixnu) if args.unixnu else device.parent / 'UniXNU'
	feeds = pathlib.Path(args.feeds) if args.feeds else out.parents[2] / 'feeds'
	if not args.series_fingerprint.strip():
		raise Missing('--series-fingerprint is empty; the series fingerprint is part of the key')
	lines = [
		line('kernel.macho', digest(need(out / 'kernel/kernel.macho', 'the packed kernel'))),
		text_line('series', args.series_fingerprint),
		text_line('unique-chip-id', args.unique_chip_id),
		line('board.toml', digest(need(device / 'board.toml', 'board.toml'))),
		*device_tree_lines(device, feeds),
	]
	tools = out / 'tree' / 'scripts'
	for name in PAYLOAD_TOOLS:
		lines.append(file_line(f'payload-tool:{name}', tools / name))
	for name in board_tools(device):
		lines.append(file_line(f'board-tool:{name}', out / 'tree' / name))
	for name in FRAMEWORK_MODULES:
		lines.append(file_line(f'framework:{name}', unixnu / 'scripts' / 'unixnu' / name))
	return lines


def bootimg_lines(args) -> list[str]:
	device = pathlib.Path(args.device)
	out = pathlib.Path(args.out)
	uefi = str(args.uefi or os.environ.get('UNIXNU_UEFI', ''))
	if not uefi:
		raise Missing('no --uefi and no UNIXNU_UEFI: the Mu-Silicium checkout is part of the key')
	uefi = pathlib.Path(uefi)
	if not args.fd:
		template = str(read_board(device).get('firmware', {}).get('fd', ''))
		if not template:
			raise Missing('board.toml [firmware] has no fd template and no --fd was given')
		fd = uefi / template.format(target=args.target)
	else:
		fd = pathlib.Path(args.fd)
	config = str(read_board(device).get('firmware', {}).get('config', ''))
	lines = [
		line('fd', digest(need(fd, 'the firmware volume'))),
		line('payload.img', digest(need(out / 'payload/payload.img', 'the payload image (it is the ramdisk)'))),
		line('hardware.dtb', digest(need(out / 'device-tree/hardware.dtb', 'the compiled device tree'))),
		line('board.toml', digest(need(device / 'board.toml', 'board.toml'))),
	]
	# The device config supplies [uefi_fd] base and size and the boot_image
	# settings; without [firmware] config the framework would not find it either.
	config = uefi / 'Resources' / 'Configs' / f'{config}.toml' if config else uefi / 'no-[firmware]-config'
	lines.append(file_line('uefi:config', config))
	for name in UEFI_LAYOUT_INPUTS:
		lines.append(file_line(f'uefi:{name}', uefi / name))
	return lines


def key(lines: list[str]) -> str:
	return hashlib.sha256(('\n'.join(lines) + '\n').encode()).hexdigest()


def parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(
		description='Print the input key of an iOS 27 image stage; the module docstring says what each key covers.',
	)
	stages = parser.add_subparsers(dest='stage', required=True)
	payload = stages.add_parser('payload', help='key of the payload step inputs')
	payload.add_argument('--device', required=True, help='device repository (board.toml, dts/)')
	payload.add_argument('--out', required=True, help='board build directory (<out>/<device>/<profile>/<board>)')
	payload.add_argument('--series-fingerprint', required=True, help='output of scripts/series-fingerprint.py')
	payload.add_argument('--unique-chip-id', required=True, help='--unique-chip-id the payload is built with')
	payload.add_argument('--feeds', help='fetched sources (default: three levels above --out, then feeds/)')
	payload.add_argument('--unixnu', help='framework checkout (default: ../UniXNU next to --device)')
	bootimg = stages.add_parser('bootimg', help='key of the boot image step inputs')
	bootimg.add_argument('--device', required=True, help='device repository (board.toml)')
	bootimg.add_argument('--out', required=True, help='board build directory')
	bootimg.add_argument('--uefi', help='Mu-Silicium checkout (default: $UNIXNU_UEFI)')
	bootimg.add_argument('--fd', help='firmware volume (default: board.toml [firmware] fd under --uefi)')
	bootimg.add_argument('--target', default='DEBUG', help='firmware build target in the fd template (default DEBUG)')
	for stage in (payload, bootimg):
		stage.add_argument('--explain', action='store_true', help='print the inputs the key is made of on stderr')
	return parser


def lines_for(args) -> list[str]:
	return payload_lines(args) if args.stage == 'payload' else bootimg_lines(args)


def main(argv=None) -> int:
	args = parser().parse_args(argv)
	try:
		lines = lines_for(args)
	except Missing as problem:
		print(f'ios27-inputs: {problem}', file=sys.stderr)
		return 2
	if args.explain:
		for entry in lines:
			print(f'  {entry}', file=sys.stderr)
	print(key(lines))
	return 0


if __name__ == '__main__':
	sys.exit(main())
