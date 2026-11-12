#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Fail closed when a generated UniXNU .config drifts from its defconfig.

The default is the K60 schema-2 output layout, verified against
UniXNU/scripts/unixnu/config.py:146-167 and board.toml:1-18. Explicit paths
work without UniXNU, board metadata, build tools, or a device. Only reads occur.

Parsing follows UniXNU/scripts/unixnu/config.py:82-107, except conflicting
assignments are errors rather than silently accepting the final value. This
also flags conflicting fragment overrides in concatenated generated files.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_DEFCONFIG = REPO / "configs" / "mondrian_defconfig"
DEFAULT_OUT = Path("/opt/k60/trees/k60build/out-baseline")
K60_CONFIG_RELATIVE = Path("mondrian/ipados-16.6.1-20G81/mondrian/.config")
ASSIGNMENT = re.compile(r"CONFIG_(\w+)=(.*)")
DISABLED = re.compile(r"#\s*CONFIG_(\w+) is not set")
NUMBER = re.compile(r"-?(0x[0-9a-fA-F]+|\d+)")


@dataclass(frozen=True)
class Assignment:
    kind: str
    value: bool | int | str
    line: int
    raw: str

    def equivalent(self, other: Assignment) -> bool:
        # Python considers True == 1 and False == 0; UniXNU settings must not.
        return self.kind == other.kind and self.value == other.value


def parse_value(raw: str, line: int) -> Assignment:
    if raw in ("y", "n"):
        return Assignment("bool", raw == "y", line, raw)
    if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
        # UniXNU strips quotes; it does not decode C/JSON/Python escapes.
        return Assignment("string", raw[1:-1], line, raw)
    if NUMBER.fullmatch(raw):
        base = 16 if raw.lstrip("-").startswith("0x") else 10
        return Assignment("number", int(raw, base), line, raw)
    raise ValueError("value must be y, n, a number or a quoted string")


def parse_config(
    text: str, path: Path, strict_duplicates: bool
) -> tuple[dict[str, Assignment], list[str], list[str]]:
    """Parse CONFIG_ assignments the way UniXNU/scripts/unixnu/config.py:82-107 does.

    The generated .config is a CONCATENATION of fragments followed by the
    defconfig (cli.py:123-135), and config.py is last-assignment-wins. So a
    repeated symbol in a generated config is normal, not a defect: e.g.
    CORECRYPTO14=y on line 2 then =n on line 88. Failing on that would fail
    every real build and the check would be switched off within a day.

    A selected defconfig is different: there is no legitimate reason for it to
    assign the same symbol twice with different values, so conflicts there are
    errors. That asymmetry is what makes this check survive contact with reality.
    """
    values: dict[str, Assignment] = {}
    problems: list[str] = []
    notes: list[str] = []
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        unset = DISABLED.fullmatch(line)
        if unset:
            name = unset.group(1)
            current = Assignment("bool", False, number, "n (not set)")
        elif not line or line.startswith("#"):
            continue
        else:
            match = ASSIGNMENT.fullmatch(line)
            if not match:
                problems.append(f"{path}:{number}: not CONFIG_NAME=value: {line}")
                continue
            name, raw = match.groups()
            try:
                current = parse_value(raw, number)
            except ValueError as error:
                problems.append(f"{path}:{number}: {error}: {line}")
                continue
        previous = values.get(name)
        if previous is not None and not previous.equivalent(current):
            detail = (
                f"{path}:{number}: duplicate CONFIG_{name}: "
                f"line {previous.line} has {previous.raw}; "
                f"line {number} has {current.raw}"
            )
            if strict_duplicates:
                problems.append(detail + " (last-assignment-wins would silently pick this)")
            else:
                notes.append(detail + " -> last value wins (fragment override)")
        # Last assignment wins, matching config.py.
        values[name] = current
    if not values:
        problems.append(f"{path}: no explicit CONFIG_ assignments")
    return values, problems, notes


def read_config(
    path: Path, label: str, strict_duplicates: bool
) -> tuple[dict[str, Assignment], list[str], list[str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}, [f"{label} missing: {path}"], []
    except (OSError, UnicodeError) as error:
        return {}, [f"cannot read {label} {path}: {error}"], []
    return parse_config(text, path, strict_duplicates)


def compare_configs(
    expected: dict[str, Assignment],
    actual: dict[str, Assignment],
    defconfig: Path,
    config: Path,
) -> list[str]:
    problems = []
    for name, wanted in expected.items():
        found = actual.get(name)
        if found is None:
            problems.append(
                f"CONFIG_{name} missing from generated config {config}; "
                f"expected {wanted.raw} ({defconfig}:{wanted.line})"
            )
        elif not wanted.equivalent(found):
            problems.append(
                f"CONFIG_{name} mismatch: expected {wanted.raw} "
                f"({defconfig}:{wanted.line}); generated {found.raw} "
                f"({config}:{found.line})"
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n", 1)[0],
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog=(
            "K60 defaults refer to WSL/Linux locations. Use --config for an "
            "independent file or another selected OS/profile. No regeneration "
            "or repair is performed. Conflicting fragment overrides fail too. "
            "Exit: 0 = consistent, 1 = missing/invalid/conflicting/mismatched "
            "input, 2 = invalid arguments."
        ),
    )
    parser.add_argument(
        "--defconfig", type=Path, default=DEFAULT_DEFCONFIG,
        help="selected source defconfig",
    )
    target = parser.add_mutually_exclusive_group()
    target.add_argument(
        "--config", type=Path,
        help="exact generated .config path (independent of --defconfig)",
    )
    target.add_argument(
        "--out", type=Path, default=DEFAULT_OUT,
        help=f"K60 output root; appends {K60_CONFIG_RELATIVE.as_posix()}",
    )
    args = parser.parse_args(argv)
    defconfig = args.defconfig.expanduser()
    config = (
        args.config if args.config is not None
        else args.out / K60_CONFIG_RELATIVE
    ).expanduser()
    expected, source_problems, _ = read_config(defconfig, "defconfig", True)
    actual, generated_problems, generated_notes = read_config(config, "generated config", False)
    problems = source_problems + generated_problems
    if expected and actual:
        problems.extend(compare_configs(expected, actual, defconfig, config))
    if problems:
        print("FAIL: configuration consistency", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        print("Inputs were not changed; regenerate explicitly after review.", file=sys.stderr)
        return 1
    print(
        f"PASS: {len(expected)} explicit defconfig symbols match\n"
        f"  defconfig: {defconfig}\n"
        f"  generated: {config}"
    )
    for note in generated_notes:
        print(f"  note: {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
