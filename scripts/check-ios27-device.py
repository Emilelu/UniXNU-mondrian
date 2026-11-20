#!/usr/bin/env python3
"""Check that the iOS 27 device repository carries what the 27 kernel build reads.

The build resolves its patch series from the device repository (board.toml:
patch_series = [..., "device:patches/xnu-12377/series"]), not from this
repository.  Everything the cellular line generates therefore has to exist in
both places, byte for byte, in the order patches/xnu-12377/series-port.txt
records.  This tool compares the two and names what is missing.

The native UFS result describes the board's default build, without remembered
or command-line overrides. Read the selected TOML override and defconfig, the
builder picker, and the producer and link inputs in that builder. Unsupported
wiring is not proof. No picker, builder or producer is executed, and even a
verified wiring path does not prove that an archive was built.

usage: check-ios27-device.py --device <device repo> [--patches <dir>] [--self-test]
"""

import argparse
import ast
import copy
import hashlib
import os
import re
import shlex
import shutil
import sys
import tempfile
import tomllib
from typing import NamedTuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PATCHES = os.path.join(REPO, "patches", "xnu-12377")
DEVICE_SERIES = os.path.join("patches", "xnu-12377", "series")
BOARD = "board.toml"
NEEDLE = "device:patches/xnu-12377/series"
BUILDER_PICKER = "scripts/pick-xnu-builder.sh"
UFS_SWITCH = "XNU_NATIVE_UFS"
DRIVER_SOURCE = "PONG_NATIVE_DRIVER_SOURCE"
CONFIG_LINE = re.compile(r"^CONFIG_(\w+)=(.*)$")
CONFIG_UNSET = re.compile(r"^#\s*CONFIG_(\w+) is not set$")
ROOT_SETUP = 'ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)'
REL_PATH = re.compile(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*")


class BoardError(Exception):
    """Missing or invalid board/configuration inputs."""


class ShellLine(NamedTuple):
    number: int
    text: str
    guards: tuple
    opaque: bool


def read(path):
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read()


def series_names(path):
    """Bare patch names from a series file, comments and blanks dropped."""
    names = []
    for line in read(path).splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        names.append(entry.split()[0])
    return names


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 16), b""):
            digest.update(block)
    return digest.hexdigest()


def merge(base, overlay):
    """The framework merge: nested tables merge, every other value is replaced."""
    result = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def resolve_profile(device):
    """Apply the selected board-local override exactly as profiles.load does."""
    path = os.path.join(device, BOARD)
    if not os.path.isfile(path):
        raise BoardError("no %s under %s" % (BOARD, device))
    try:
        with open(path, "rb") as handle:
            board = tomllib.load(handle)
    except (OSError, ValueError) as error:
        raise BoardError(str(error)) from error
    name = profile_get(board, "board.os_profile")
    if not isinstance(name, str) or not name:
        raise BoardError("board.toml needs [board].os_profile")
    overrides = board.pop("os_overrides", {})
    if not isinstance(overrides, dict) or not isinstance(overrides.get(name, {}), dict):
        raise BoardError("invalid os_overrides for " + name)
    notes = []
    chosen = overrides.get(name, {}).copy()
    if overrides and name not in overrides:
        notes.append("%s selects %r and no os_overrides table has that name; using base values"
                     % (BOARD, name))
    removed = chosen.pop("remove", [])
    if not isinstance(removed, list) or not all(isinstance(key, str) for key in removed):
        raise BoardError("os_overrides.remove must be a list of dotted keys")
    # The framework looks up package.defconfig on the raw board, not the override.
    config_name = profile_get(board, "package.defconfig", {}).get(name) if isinstance(
        profile_get(board, "package.defconfig", {}), dict) else None
    profile = merge(board, chosen)
    for dotted in removed:
        parents, _, leaf = dotted.rpartition(".")
        node = profile_get(profile, parents) if parents else profile
        if isinstance(node, dict):
            node.pop(leaf, None)
    return name, profile, config_name or profile_get(profile, "kernel.defconfig"), notes


def profile_get(profile, dotted, default=None):
    node = profile
    for key in dotted.split("."):
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return node


def parse_defconfig(path):
    """Mirror unixnu's config-to-shell values; last assignment wins."""
    values = {}
    for number, line in enumerate(read(path).splitlines(), 1):
        entry = line.strip()
        unset = CONFIG_UNSET.fullmatch(entry)
        if unset:
            values[unset[1]] = ("0", "# CONFIG_%s is not set" % unset[1])
            continue
        if not entry or entry.startswith("#"):
            continue
        match = CONFIG_LINE.fullmatch(entry)
        if match:
            key, raw = match.groups()
            if raw in ("y", "n"):
                value = "1" if raw == "y" else "0"
            elif len(raw) >= 2 and raw.startswith('"') and raw.endswith('"'):
                value = raw[1:-1]
            elif re.fullmatch(r"-?(?:0x[0-9a-fA-F]+|[0-9]+)", raw):
                value = str(int(raw, 16 if raw.lstrip("-").startswith("0x") else 10))
            else:
                raise BoardError("%s:%d: invalid defconfig value: %s" % (path, number, entry))
            values[key] = (value, entry)
        else:
            raise BoardError("%s:%d: expected CONFIG_NAME=value" % (path, number))
    return values


def relative_path(value):
    return (isinstance(value, str) and REL_PATH.fullmatch(value)
            and not {".", ".."}.intersection(value.split("/")))


def _display(path, device):
    relative = os.path.relpath(path, device)
    return relative.replace(os.sep, "/") if not relative.startswith("..") else path


def kernel_config(device, profile, name):
    """Read local fragments in order, then the selected defconfig (cli.cmd_defconfig)."""
    if not relative_path(name) or "/" in name:
        raise BoardError("the profile has no usable defconfig name")
    fragments = profile_get(profile, "kernel.config_fragments", [])
    if not isinstance(fragments, list) or not all(isinstance(item, str) for item in fragments):
        raise BoardError("kernel.config_fragments must be a list of paths")
    values, origins, notes = {}, {}, []
    config = "configs/" + name
    for item in [*fragments, config]:
        if item.startswith("device:"):
            item = item.removeprefix("device:")
        if not relative_path(item):
            # A later, uninspected fragment could overwrite an earlier value.
            # A local assignment read after it is still conclusive.
            values.clear()
            origins.clear()
            notes.append("fragment %s was not inspected" % item)
            continue
        path = os.path.join(device, item)
        if not os.path.isfile(path):
            raise BoardError("missing %s" % item)
        for key, (value, entry) in parse_defconfig(path).items():
            values[key] = value
            origins[key] = "%s in %s" % (entry, item)
    return values, origins, notes


# The picker is a tiny, known dispatch format, not a shell program to evaluate.
PICKER_PREFIX = '''set -eu
board=${1:-board.toml}
profile=$(python3 - "$board" <<'PY'
import sys, tomllib
try:
    data = tomllib.load(open(sys.argv[1], 'rb'))
except (FileNotFoundError, OSError):
    print('')
else:
    print(data.get('board', {}).get('os_profile', ''))
PY
)
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
case "$profile" in'''
BUILDER_ENTRY = 'scripts/build-xnu-4k-baseline.sh'
DISPATCH = '''CHOSEN_BUILDER=$(sh "$ROOT/scripts/pick-xnu-builder.sh" "$ROOT/board.toml" 2>/dev/null || true)
if [ -n "${CHOSEN_BUILDER:-}" ] && [ "$CHOSEN_BUILDER" != "$ROOT/scripts/build-xnu-4k-baseline.sh" ] && [ -f "$CHOSEN_BUILDER" ]; then
  echo "build-xnu: [board] os_profile is not the 16.6.1 line; using $CHOSEN_BUILDER" >&2
  exec bash "$CHOSEN_BUILDER" "$@"
fi'''
ROOT_TOKEN = r'\$(?:ROOT|\{ROOT\})'
SOURCE_TOKEN = r'\$(?:PONG_NATIVE_DRIVER_SOURCE|\{PONG_NATIVE_DRIVER_SOURCE\})'
VAR = r'\$(?:(\w+)|\{(\w+)(?::-(\w*))?\})'
GUARD_TEST = re.compile(r'\[\s+(?:(-[nz])\s+)?"' + VAR + r'"(?:\s+(=|!=)\s+"?([\w.-]+)"?)?\s+\]')
PRODUCER_CALL = re.compile(r'python3\s+(?P<script>"[^"\s]+"|[^"\s]+)\s+--tree\s+(?:"'
                           + ROOT_TOKEN + r'"|' + ROOT_TOKEN + r')(?P<flags>(?:\s+--[a-z-]+)*)')
ARCHIVE = re.compile(r'UFS_ARCHIVE=(?:"' + ROOT_TOKEN + r'/([^"\s]+)"|' + ROOT_TOKEN + r'/(\S+))')
FORCE_LOAD = re.compile(r'(KERNEL_EXTRA_ARCHIVES|PLATFORM_ARCHIVES)="\$\1 -Wl,-force_load,\$UFS_ARCHIVE"')
HEREDOC = re.compile(r'(?<!<)<<(-?)\s*([\'\"]?)([A-Za-z_]\w*)\2(?=\s|[;)]|$)')


def noncomments(text):
    return [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]


def builder_for(device, name):
    """Resolve the board-reading picker invoked by the framework entry script."""
    picker, entry = (os.path.join(device, rel) for rel in (BUILDER_PICKER, BUILDER_ENTRY))
    if not os.path.isfile(picker):
        raise BoardError("missing " + BUILDER_PICKER)
    lines = noncomments(read(picker))
    prefix = PICKER_PREFIX.splitlines()
    if lines[:len(prefix)] != prefix or lines[-1:] != ["esac"]:
        raise BoardError("unrecognized " + BUILDER_PICKER + " dispatch")
    selected = None
    for line in lines[len(prefix):-1]:
        arm = re.fullmatch(r'\s*(\*|[\w.-]+)\)\s+echo "\$here/([\w.-]+\.sh)"\s+;;', line)
        if not arm:
            raise BoardError("unsupported builder picker arm: " + line.strip())
        if selected is None and arm[1] in (name, "*"):
            selected = "scripts/" + arm[2]
    if selected is None:
        raise BoardError("no builder picker arm for " + name)
    path = os.path.join(device, selected)
    if not os.path.isfile(path):
        raise BoardError("selected builder is missing: " + selected)
    if selected != BUILDER_ENTRY:
        if not os.path.isfile(entry):
            raise BoardError("missing framework entry script " + BUILDER_ENTRY)
        launch = noncomments(read(entry))
        while launch and (launch[0] == "set -euo pipefail" or launch[0].startswith("trap ")):
            launch = launch[1:]
        if launch[:7] != [ROOT_SETUP, 'cd "$ROOT"', *DISPATCH.splitlines()]:
            raise BoardError("cannot verify that %s dispatches to %s" % (BUILDER_ENTRY, selected))
    return path


def shell_lines(text):
    """Yield plain commands with branch guards, never heredoc/function bodies as evidence.

    This recognizes the builder's line-oriented if/elif/else and continuations.
    Loops, case arms, command groups and array literals are opaque, not executed.
    """
    blocks, pending = [], ""
    delimiter = None
    for number, raw in enumerate(text.splitlines(), 1):
        if delimiter:
            word, strip_tabs = delimiter
            if (raw.lstrip("\t") if strip_tabs else raw) == word:
                delimiter = None
            continue
        if not pending:
            start = number
        if not pending and (not raw.strip() or raw.lstrip().startswith("#")):
            continue
        pending += raw.lstrip()
        if pending.endswith("\\"):
            pending = pending[:-1]
            continue
        if pending.rstrip().endswith(("||", "&&")):
            pending = pending.rstrip() + " "
            continue
        line, pending = pending.strip(), ""
        # Quotes can span lines. Ignore the entire command until they close.
        # Do not treat a shell-looking line inside quoted data as a command.
        try:
            shlex.split(line, comments=True)
        except ValueError as error:
            if str(error) != "No closing quotation":
                raise BoardError("unsupported shell quoting at line %d" % start) from error
            pending = line + "\n"
            continue
        here = HEREDOC.search(line)
        if here:
            delimiter = (here[3], bool(here[1]))
            continue
        branch = re.fullmatch(r'(if|elif) (.+);\s*then', line)
        if branch:
            kind, condition = branch.groups()
            if kind == "if":
                blocks.append(("fi", [(condition, True)]))
            elif blocks and blocks[-1][0] == "fi" and blocks[-1][1][-1][1]:
                previous = [(test, False) for test, _ in blocks[-1][1]]
                blocks[-1] = ("fi", [*previous, (condition, True)])
            else:
                raise BoardError("unsupported elif at line %d" % start)
            continue
        if line == "else" and blocks and blocks[-1][0] == "fi" and blocks[-1][1][-1][1]:
            blocks[-1] = ("fi", [(test, False) for test, _ in blocks[-1][1]])
            continue
        if blocks and line == blocks[-1][0]:
            blocks.pop()
            continue
        opaque = None
        if re.match(r'^(for|while|until)\b.*;\s*do$', line):
            opaque = "done"
        elif re.match(r'^case\b.*\bin$', line):
            opaque = "esac"
        elif line.endswith(" {") or line == "{":
            opaque = "}"
        elif line.endswith("=(") or line == "(":
            opaque = ")"
        if opaque:
            blocks.append((opaque, None))
            continue
        if re.match(r'^(if|elif|else|fi|for|while|until|case|done|esac|function)\b', line):
            raise BoardError("unsupported shell control syntax at line %d" % start)
        guards = tuple(pair for _, tests in blocks if tests is not None for pair in tests)
        yield ShellLine(start, line, guards, any(tests is None for _, tests in blocks))
    if pending or blocks or delimiter:
        raise BoardError("unterminated shell construct")


def guard_truth(condition, env, external):
    """Known conjunctions of literal [ ] tests; None is not a true branch."""
    if condition in ("true", ":", "false"):
        return condition != "false"
    unknown = False
    for part in condition.split("&&"):
        match = GUARD_TEST.fullmatch(part.strip())
        if not match:
            unknown = True
            continue
        unary, bare, braced, default, op, wanted = match.groups()
        name = bare or braced
        value = env.get(name, None if external and name.startswith("XNU_") else "")
        if value is None or (not unary and not op) or (unary and op):
            unknown = True
            continue
        value = value or default or ""
        truth = {"-n": bool(value), "-z": not value, "=": value == wanted,
                 "!=": value != wanted}[unary or op]
        if not truth:
            return False
    return None if unknown else True


def reach(line, env, external):
    if line.opaque:
        return None
    unknown = False
    for condition, positive in line.guards:
        truth = guard_truth(condition, env, external)
        if truth is None:
            unknown = True
        elif truth != positive:
            return False
    return None if unknown else True


def directory_token(value, device):
    """Map a build-tree path to its device source, without an unrelated fallback."""
    if value in ("$ROOT", "${ROOT}", "{tree}"):
        return device
    for root in ("$ROOT/", "${ROOT}/", "{tree}/"):
        if value.startswith(root) and relative_path(value[len(root):]):
            return os.path.join(device, value[len(root):])
    if os.path.isabs(value) and relative_path(value.lstrip("/")):
        return value
    return None


def producer_path(token, device, profile, driver, cwd_is_root):
    if token.endswith('"') and token.startswith('"'):
        token = token[1:-1]
    match = re.fullmatch(SOURCE_TOKEN + r'/(.+)', token)
    if match:
        source = profile_get(profile, "kernel.pong_native_driver_source")
        if not isinstance(source, str) or not source:
            raise BoardError("PONG_NATIVE_DRIVER_SOURCE has no kernel.pong_native_driver_source in this profile (unset or removed)")
        pinned = directory_token(source, device)
        if pinned is None or driver is None or os.path.realpath(driver) != os.path.realpath(pinned):
            raise BoardError("cannot verify PONG_NATIVE_DRIVER_SOURCE is set to kernel.pong_native_driver_source")
        root, relative = pinned, match[1]
    else:
        match = re.fullmatch(ROOT_TOKEN + r'/(.+)', token)
        if not match and not cwd_is_root:
            raise BoardError("relative producer path without a known build-tree working directory")
        root, relative = device, match[1] if match else token.removeprefix("./")
    if not relative_path(relative) or not relative.startswith("scripts/") or not relative.endswith(".py"):
        raise BoardError("unsupported producer path: " + token)
    path = os.path.join(root, relative)
    if not os.path.isfile(path):
        raise BoardError("producer is missing at the invoked path: " + _display(path, device))
    return path


def attr(node, owner, name):
    return (isinstance(node, ast.Attribute) and node.attr == name
            and isinstance(node.value, ast.Name) and node.value.id == owner)


def call_statement(node):
    if isinstance(node, (ast.Expr, ast.Assign, ast.AnnAssign)) and isinstance(node.value, ast.Call):
        return node.value
    return None


def literal(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def producer_outputs(path):
    """Follow straight-line writes in Python's entry point, not every AST call.

    Recognize argparse's --tree, simple pathlib joins and subprocess.run of
    libtool/ar. Unrelated compilation work remains an untested prerequisite.
    """
    module = ast.parse(read(path), filename=path)
    main = [st for st in module.body if isinstance(st, ast.FunctionDef) and st.name == "main"]
    if len(main) == 1 and not main[0].decorator_list and module.body:
        last = module.body[-1]
        if (isinstance(last, ast.If) and ast.unparse(last.test) == "__name__ == '__main__'"
                and len(last.body) == 1 and ast.unparse(last.body[0]) == "main()"):
            # Only the entry-point body is evidence. Do not use path assignments
            # from unrelated functions or from after the archive command.
            statements = main[0].body
        else:
            statements = module.body
    else:
        statements = module.body
    bindings, archives = {}, set()
    parser = args = None
    tree_option = False

    def tree_path(node):
        if isinstance(node, ast.Name):
            return bindings.get(node.id)
        if isinstance(node, ast.Attribute) and attr(node, args, "tree") and tree_option:
            return ()
        if isinstance(node, ast.Call) and not node.keywords:
            if isinstance(node.func, ast.Name) and node.func.id in ("Path", "str") and len(node.args) == 1:
                return tree_path(node.args[0])
            if isinstance(node.func, ast.Attribute) and node.func.attr == "resolve" and not node.args:
                return tree_path(node.func.value)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            parent, part = tree_path(node.left), literal(node.right)
            if parent is not None and relative_path(part):
                return (*parent, part)
        return None

    for stmt in statements:
        if isinstance(stmt, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
            break
        if isinstance(stmt, ast.If) and isinstance(stmt.test, ast.Constant) and not stmt.test.value and not stmt.orelse:
            continue
        call = call_statement(stmt)
        if call and attr(call.func, parser, "add_argument") and call.args and literal(call.args[0]) == "--tree":
            tree_option = any(kw.arg == "type" and isinstance(kw.value, ast.Name) and kw.value.id == "Path"
                              for kw in call.keywords)
        if call and attr(call.func, "subprocess", "run") and call.args:
            argv = call.args[0]
            if isinstance(argv, ast.Name):
                argv = bindings.get(("argv", argv.id))
            if isinstance(argv, (ast.List, ast.Tuple)) and not any(kw.arg in ("shell", None) for kw in call.keywords):
                words = [literal(word) for word in argv.elts]
                index = None
                if words[:4] == ["xcrun", "libtool", "-static", "-o"]:
                    index = 4
                elif words[:3] == ["libtool", "-static", "-o"]:
                    index = 3
                elif len(words) > 1 and words[0] in ("ar", "llvm-ar") and words[1] == "rcs":
                    index = 2
                if index is not None and len(words) > index + 1:
                    out = tree_path(argv.elts[index])
                    if not out or not out[-1].endswith(".a"):
                        raise BoardError("archive output is not under the build tree at line %d" % stmt.lineno)
                    archives.add("/".join(out))
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
            target = stmt.targets[0].id
            bindings[target] = tree_path(stmt.value)
            # Only literal argv values: evaluating their names after a later
            # reassignment would not model Python's assignment-time values.
            if isinstance(stmt.value, (ast.List, ast.Tuple)):
                bindings[("argv", target)] = stmt.value
            else:
                bindings.pop(("argv", target), None)
            if call and attr(call.func, "argparse", "ArgumentParser"):
                parser, args, tree_option = target, None, False
            elif call and attr(call.func, parser, "parse_args") and not call.args and not call.keywords:
                args = target
            elif target == args or target == parser:
                args, tree_option = None, False
        elif not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for node in ast.walk(stmt):
                if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
                    bindings.pop(node.id, None)
                    if node.id in (parser, args):
                        args, tree_option = None, False
    return archives


def ufs_wiring(device, name, profile, values, external):
    builder = builder_for(device, name)
    where = _display(builder, device)
    commands = list(shell_lines(read(builder)))
    # A normal link, not the framework's earlier compile-record pass. When the
    # switch is off, inspect this counterfactual only to explain what is missing.
    env = {**values, UFS_SWITCH: "1", "XNU_BOOTSTRAP": ""}
    archive = driver = None
    rooted = cwd_is_root = False
    carried, handoff, producers, problems = {}, None, {}, []
    archive_test_at = 0
    for line in commands:
        command = line.text
        active = reach(line, env, external)
        if active is False or line.opaque:
            continue
        if re.match(r'^(?:exit|return|exec)(?:\s|$)', command) and active is True:
            break
        if re.match(r'^(?:export\s+)?(?:ROOT|XNU_NATIVE_UFS|XNU_BOOTSTRAP)=|^unset\s+(?:ROOT|XNU_NATIVE_UFS)\b', command):
            if command == ROOT_SETUP and active is True and not rooted:
                rooted = True
            else:
                raise BoardError("%s:%d: cannot verify builder root or switch reassignment" % (where, line.number))
        elif command == 'BOOTSTRAP=${XNU_BOOTSTRAP:-0}' and active is True:
            env["BOOTSTRAP"] = "0"
        elif command.startswith("cd "):
            cwd_is_root = rooted and active is True and command == 'cd "$ROOT"'
        elif command.startswith(DRIVER_SOURCE + "=") or command.startswith("export " + DRIVER_SOURCE + "="):
            value = command.split("=", 1)[1].removeprefix('"').removesuffix('"')
            driver = directory_token(value, device) if active is True and rooted else None
            env[DRIVER_SOURCE] = driver
        elif command.startswith("UFS_ARCHIVE="):
            match = ARCHIVE.fullmatch(command)
            relative = (match[1] or match[2]) if match else None
            off = reach(line, {**env, UFS_SWITCH: "0"}, external)
            archive = (relative, active, line.number) if rooted and relative_path(relative) and off is False else None
            archive_test_at = 0
        elif command == 'test -f "$UFS_ARCHIVE"' and archive is not None:
            archive_test_at = line.number
        elif match := FORCE_LOAD.fullmatch(command):
            carried[match[1]] = (archive, active, archive_test_at or line.number) if archive else None
        elif match := re.match(r'^(KERNEL_EXTRA_ARCHIVES|PLATFORM_ARCHIVES)=(.*)', command):
            if not match[2].startswith('"$' + match[1] + ' '):
                carried.pop(match[1], None)
        elif match := re.fullmatch(r'EXTRA_MAKE_ARGS\+=\("LD_KERNEL_ARCHIVES=\$(\w+)"\)', command):
            handoff = (carried.get(match[1]), active)
        elif command.startswith("EXTRA_MAKE_ARGS=") or "LD_KERNEL_ARCHIVES=" in command:
            handoff = None
        elif match := PRODUCER_CALL.fullmatch(command):
            token, flags = match.groups()
            if active is not True:
                if "ufs" in token.lower():
                    problems.append("producer guard at %s:%d is unverified" % (where, line.number))
                continue
            if not rooted or not set(flags.split()).issubset({"--skip-image-verification", "--verified-root"}):
                continue
            try:
                path = producer_path(token, device, profile, driver, cwd_is_root)
                for output in producer_outputs(path):
                    producers.setdefault(output, (line.number, _display(path, device)))
            except (BoardError, OSError, SyntaxError) as error:
                if "ufs" in token.lower():
                    problems.append(str(error))
        if command.startswith("make ") and '"${EXTRA_MAKE_ARGS[@]}"' in command and handoff and handoff[0]:
            (relative, assigned, assignment_at), linked, first_use = handoff[0]
            expectation = "%s targets %s" % (where, relative)
            producer = producers.get(relative)
            if producer is None or producer[0] >= min(first_use, line.number):
                if producers:
                    written = ", ".join("%s writes %s" % (source, output) for output, (_, source) in sorted(producers.items()))
                    return False, "%s; no matching producer before the consumer (%s)" % (expectation, written)
                detail = "; ".join(problems) or "it runs no verifiable UFS producer before the consumer"
                return False, "%s, and nothing writes the archive: %s" % (expectation, detail)
            if not all(state is True for state in (active, assigned, linked, handoff[1])):
                return False, "%s, but its link guards are unverified" % expectation
            return True, "%s:%d runs %s, which writes %s consumed by make at line %d" % (
                where, producer[0], producer[1], relative, line.number)
    return False, "%s has no verified UFS archive force-load handed to make" % where


def ufs_archive(device, resolved=None):
    """Return ('ok' | 'pending', reason); ok describes wiring, not an artifact."""
    try:
        name, profile, config, notes = resolved or resolve_profile(device)
        values, origins, config_notes = kernel_config(device, profile, config)
    except (BoardError, OSError) as error:
        return "pending", "native UFS configuration is unverified: " + str(error)
    state = values.get(UFS_SWITCH)
    origin = origins.get(UFS_SWITCH, "CONFIG_XNU_NATIVE_UFS not resolved in configs/" + config)
    notes = notes + config_notes
    suffix = " (" + "; ".join(notes) + ")" if notes else ""
    try:
        wired, why = ufs_wiring(device, name, profile, values, bool(config_notes))
    except (BoardError, OSError) as error:
        wired, why = False, str(error)
    if state == "1" and wired:
        return "ok", "%s native UFS wiring verified (%s): %s; artifact not checked%s" % (name, origin, why, suffix)
    if state == "1":
        lead = "the %s profile enables native UFS (%s), but wiring is unverified" % (name, origin)
    elif state in ("", "0"):
        lead = "the %s profile keeps native UFS off (%s)" % (name, origin)
        if not wired:
            lead += ", and enabling it would not be enough"
    else:
        lead = "native UFS is not proven enabled for %s (%s)" % (name, origin)
    return "pending", lead + ": " + why + suffix


def check(device, patches):
    """Return (drift, UFS status) after comparing the device repository with ours."""
    drift = 0
    try:
        resolved = resolve_profile(device)
    except BoardError as error:
        print("K60 DEVICE INVALID " + str(error))
        return None, None
    _, profile, _, _ = resolved
    series = profile_get(profile, "kernel.patch_series", [])
    if not isinstance(series, list) or NEEDLE not in series:
        drift += 1
        print("K60 DEVICE DRIFT %s does not list %s in patch_series" % (BOARD, NEEDLE))
    else:
        print("K60 DEVICE ok   %s lists %s" % (BOARD, NEEDLE))

    ours = os.path.join(patches, "series-port.txt")
    if not os.path.exists(ours):
        print("K60 DEVICE INVALID no series-port.txt under " + patches)
        return None, None
    wanted = series_names(ours)

    theirs_path = os.path.join(device, DEVICE_SERIES)
    if not os.path.exists(theirs_path):
        drift += 1
        print("K60 DEVICE DRIFT the device repository has no " + DEVICE_SERIES)
    theirs = series_names(theirs_path) if os.path.isfile(theirs_path) else []
    missing = [name for name in wanted if name not in theirs]
    if missing and theirs:
        drift += 1
        print("K60 DEVICE DRIFT %d of %d ported patches are not in the device series: %s"
              % (len(missing), len(wanted), " ".join(missing)))
    elif not missing:
        order = [theirs.index(name) for name in wanted]
        if order != sorted(order):
            drift += 1
            print("K60 DEVICE DRIFT the ported patches are out of order in the device series")
        else:
            print("K60 DEVICE ok   %d ported patches are in the device series, in order"
                  % len(wanted))

    differing, absent = [], []
    for name in wanted:
        mine = os.path.join(patches, name)
        other = os.path.join(device, os.path.dirname(DEVICE_SERIES), name)
        if not os.path.exists(other):
            absent.append(name)
        elif sha256(mine) != sha256(other):
            differing.append(name)
    if absent:
        drift += 1
        print("K60 DEVICE DRIFT the device repository has no copy of: " + " ".join(absent))
    elif differing:
        drift += 1
        print("K60 DEVICE DRIFT copies differ from ours: " + " ".join(differing))
    else:
        print("K60 DEVICE ok   every ported patch is byte-identical in both repositories")

    included = profile_get(profile, "components.include")
    if not isinstance(included, list):
        print("K60 DEVICE note the 27 package block lists no components")
    elif "QcomBaseband" in included:
        print("K60 DEVICE ok   the 27 package includes QcomBaseband")
    else:
        print("K60 DEVICE note QcomBaseband is not in the 27 package include list")
    # Two components, two different jobs: QcomBaseband answers for the seven
    # coachz symbols at link time, PongUfs is what can read a named volume at
    # all. Both are notes, not drift: the freeze keeps them off main until F3.
    if isinstance(included, list) and "PongUfs" not in included:
        print("K60 DEVICE note PongUfs is not in the 27 package include list either")
    elif isinstance(included, list):
        print("K60 DEVICE ok   the 27 package includes PongUfs")

    status, why = ufs_archive(device, resolved)
    print("K60 DEVICE " + ("ok   " if status == "ok" else "pending ") + why)
    return drift, status

FIXTURE_BOARD = """schema_version = 2

[board]
os_profile = "ipados-27.0.1-24A446"

[components]
include = ["ArmDTPlatform", "PongUfs", "QcomBaseband"]

[kernel]
defconfig = "mondrian_defconfig"
pong_native_driver_source = "{tree}"

[os_overrides."ipados-27.0.1-24A446"]
remove = []

[os_overrides."ipados-27.0.1-24A446".components]
include = ["ArmDTPlatform", "QcomBaseband"]

[os_overrides."ipados-27.0.1-24A446".kernel]
defconfig = "mondrian_ios27_defconfig"
patch_series = ["device:patches/xnu-12377/series"]
"""

FIXTURE_PICKER = '#!/bin/sh\n' + PICKER_PREFIX + '''
  ipados-16.6.1-20G81) echo "$here/build-xnu-4k-baseline.sh" ;;
  *) echo "$here/build-xnu-generic.sh" ;;
esac
'''
FIXTURE_SETUP = '#!/usr/bin/env bash\nset -euo pipefail\n' + ROOT_SETUP + '\ncd "$ROOT"\n'
FIXTURE_ENTRY = FIXTURE_SETUP + DISPATCH + '\n'
FIXTURE_CONSUMER = '''if [ "$XNU_NATIVE_UFS" = 1 ]; then
  UFS_ARCHIVE=$ROOT/build/native-ufs/libNativeUfs.a
  test -f "$UFS_ARCHIVE"
  KERNEL_EXTRA_ARCHIVES="$KERNEL_EXTRA_ARCHIVES -Wl,-force_load,$UFS_ARCHIVE"
  EXTRA_MAKE_ARGS+=("LD_KERNEL_ARCHIVES=$KERNEL_EXTRA_ARCHIVES")
fi
make -C .cache/xnu-work build "${EXTRA_MAKE_ARGS[@]}"
'''
FIXTURE_LINK = FIXTURE_SETUP + FIXTURE_CONSUMER
FIXTURE_PRODUCER = '''import argparse
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--tree", type=Path)
args = parser.parse_args()
tree = args.tree.resolve()
archive = tree / "build/native-ufs" / "libNativeUfs.a"
subprocess.run(["xcrun", "libtool", "-static", "-o", str(archive), "NativeUfs.o"], check=True)
'''
FIXTURE_CALL = FIXTURE_SETUP + '''PONG_NATIVE_DRIVER_SOURCE="$ROOT"
if [ "$XNU_NATIVE_UFS" = 1 ] && [ -n "$PONG_NATIVE_DRIVER_SOURCE" ]; then
  python3 "$PONG_NATIVE_DRIVER_SOURCE/scripts/build-pong-ufs-probe-macos.py" --tree "$ROOT"
fi
''' + FIXTURE_CONSUMER


def _write(path, text):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def self_test():
    work = tempfile.mkdtemp(prefix="k60-device-")
    try:
        patches = os.path.join(work, "patches", "xnu-12377")
        os.makedirs(patches)
        names = ["0626-a.patch", "0627-b.patch"]
        _write(os.path.join(patches, "series-port.txt"), "# comment\n" + "\n".join(names) + "\n")
        for name in names:
            _write(os.path.join(patches, name), name + "\n")
        device = os.path.join(work, "device")
        target = os.path.join(device, "patches", "xnu-12377")
        os.makedirs(target)
        _write(os.path.join(device, BOARD), FIXTURE_BOARD)
        # The wiring exists from the first run on, so the pending line a reader
        # sees is the real one and not "the builder is unknown".
        scripts = os.path.join(device, "scripts")
        configs = os.path.join(device, "configs")
        os.makedirs(scripts)
        os.makedirs(configs)
        _write(os.path.join(scripts, "pick-xnu-builder.sh"), FIXTURE_PICKER)
        _write(os.path.join(scripts, "build-xnu-4k-baseline.sh"), FIXTURE_ENTRY)
        _write(os.path.join(scripts, "build-xnu-generic.sh"), FIXTURE_LINK)
        _write(os.path.join(scripts, "build-pong-ufs-probe-macos.py"), FIXTURE_PRODUCER)
        config = os.path.join(configs, "mondrian_ios27_defconfig")
        _write(config, "CONFIG_XNU_NATIVE_UFS=n\n")
        _write(os.path.join(target, "series"), "0500-bt.patch\n" + "\n".join(names) + "\n")
        for name in names:
            shutil.copy(os.path.join(patches, name), os.path.join(target, name))
        if check(device, patches)[0] != 0:
            print("K60 DEVICE FAIL a complete device repository was reported as drift")
            return 1
        _write(os.path.join(target, "series"), "0500-bt.patch\n0626-a.patch\n")
        if check(device, patches)[0] == 0:
            print("K60 DEVICE FAIL a missing series entry was not reported")
            return 1
        _write(os.path.join(target, "series"), "0500-bt.patch\n" + "\n".join(names) + "\n")
        _write(os.path.join(target, "0627-b.patch"), "changed\n")
        if check(device, patches)[0] == 0:
            print("K60 DEVICE FAIL a differing copy was not reported")
            return 1
        # Undo the perturbation: the fixtures below expect a clean comparison.
        _write(os.path.join(target, "0627-b.patch"), "0627-b.patch\n")
        # The native UFS wiring.  Off and unwired are pending,
        # and a producer the builder actually runs clears it - only for the path
        # the link step force-loads.
        status, why = ufs_archive(device)
        if status != "pending":
            print("K60 DEVICE FAIL a disabled switch was not reported as pending")
            return 1
        print("K60 DEVICE pending " + why)
        _write(config, "CONFIG_XNU_NATIVE_UFS=y\n")
        status, why = ufs_archive(device)
        if status != "pending" or "nothing writes the archive" not in why:
            print("K60 DEVICE FAIL an enabled switch with no producer was not reported")
            return 1
        print("K60 DEVICE pending " + why)
        _write(os.path.join(scripts, "build-xnu-generic.sh"), FIXTURE_CALL)
        status, why = ufs_archive(device)
        if status != "ok":
            print("K60 DEVICE FAIL a producer the builder runs was not reported")
            return 1
        print("K60 DEVICE ok   " + why)
        _write(os.path.join(scripts, "build-pong-ufs-probe-macos.py"),
               FIXTURE_PRODUCER.replace("libNativeUfs.a", "libShengUfs.a"))
        if ufs_archive(device)[0] != "pending":
            print("K60 DEVICE FAIL a producer writing another archive was not reported")
            return 1
        print("K60 DEVICE PASS agreement, missing entry, differing copy, archive wiring")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv):
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--device")
    parser.add_argument("--patches", default=DEFAULT_PATCHES)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.device:
        parser.error("--device is required")
    try:
        drift, status = check(args.device, args.patches)
    except OSError as error:
        print("K60 DEVICE INVALID " + str(error))
        return 2
    if drift is None:
        return 2
    if drift:
        print("K60 DEVICE CHANGED %d expectation(s) drifted" % drift)
        return 1
    if status == "pending":
        print("K60 DEVICE PENDING patch checks agree; native UFS is unverified")
    else:
        print("K60 DEVICE OK patch checks agree; native UFS static wiring verified")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
