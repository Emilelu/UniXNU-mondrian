
#!/usr/bin/env python3
"""Fail when the two judges disagree about the C3 tolerance window.

`scripts/judge-battery.py` is the C3 comparison (console sample vs Android dumpsys or
sysfs). `scripts/judge-k60-battery-mirror.py` compares the same console sample against
sheng's Linux report, and it carries its **own copy** of the four tolerances. Two copies
of one number drift (P-259), and the drift is silent in the worst direction: the mirror
judge would keep its old window after the C3 window moved, so a pair of samples one
threshold apart passes one judge and fails the other, on the same device.

So this gate reads both modules, requires the four numbers to be equal, requires each
number to be *used* (a constant that nothing reads is dead), and requires the criteria
doc to carry the rendered window - the doc quotes the numbers too, which is the third
copy.

Exit 0 all agree, 1 a disagreement or a missing piece, 2 a file cannot be read.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CANON = "scripts/judge-battery.py"
COPIES = ("scripts/judge-k60-battery-mirror.py",)
DOC = "docs/research/charger/07-DEVICE-CRITERIA.md"
NAMES = ("V_TOL_MV", "I_TOL_MA", "SOC_TOL_HUNDREDTHS", "T_TOL_HUNDREDTHS")


def load(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location("jt_" + path.stem.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rendered(values: dict) -> str:
    """The window as a reader writes it, so the doc and the code can be compared."""
    return (f"±{values['V_TOL_MV']} mV / ±{values['I_TOL_MA']} mA / "
            f"±{values['SOC_TOL_HUNDREDTHS'] / 100:g} pp / "
            f"±{values['T_TOL_HUNDREDTHS'] / 100:g} °C")


def used(root: pathlib.Path, rel: str, name: str) -> int:
    """How many times the file mentions the name; the definition itself counts once."""
    text = (root / rel).read_text(encoding="utf-8")
    return text.count(name)


def verify(root: pathlib.Path = ROOT) -> list[str]:
    problems: list[str] = []
    canon_path = root / CANON
    if not canon_path.is_file():
        return [f"{CANON} is missing"]
    try:
        canon = load(canon_path)
    except Exception as error:  # noqa: BLE001 - any import failure is a problem to report
        return [f"{CANON} does not import: {error}"]
    values: dict[str, int] = {}
    for name in NAMES:
        value = getattr(canon, name, None)
        if not isinstance(value, int) or value <= 0:
            problems.append(f"{CANON}: {name} is {value!r}, expected a positive int")
            continue
        values[name] = value
        if used(root, CANON, name) < 2:
            problems.append(f"{CANON}: {name} is defined but never read")
    if problems:
        return problems
    for rel in COPIES:
        path = root / rel
        if not path.is_file():
            problems.append(f"{rel} is missing")
            continue
        try:
            module = load(path)
        except Exception as error:  # noqa: BLE001
            problems.append(f"{rel} does not import: {error}")
            continue
        for name in NAMES:
            value = getattr(module, name, None)
            if value is None:
                problems.append(f"{rel}: no {name}; it compares against the C3 window "
                                f"and has to keep the same {name} ({values[name]})")
                continue
            if value != values[name]:
                problems.append(f"{rel}: {name} = {value!r}, {CANON} says {values[name]!r} "
                                f"- the two judges would disagree about the same pair")
            if used(root, rel, name) < 2:
                problems.append(f"{rel}: {name} is defined but never read")
    doc = root / DOC
    if not doc.is_file():
        problems.append(f"{DOC} is missing")
    else:
        body = doc.read_text(encoding="utf-8")
        window = rendered(values)
        if window not in body:
            problems.append(f"{DOC} does not quote the window the judges use: expected {window!r}")
    return problems


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args(argv)
    root = pathlib.Path(args.root).resolve()
    if not root.is_dir():
        print(f"judge-thresholds: {args.root} is not a directory", file=sys.stderr)
        return 2
    problems = verify(root)
    if problems:
        for problem in problems:
            print(f"❌ {problem}")
        print(f"judge-thresholds: {len(problems)} problem(s)")
        return 1
    canon = load(root / CANON)
    window = rendered({name: getattr(canon, name) for name in NAMES})
    print(f"✅ judge-thresholds: {len(NAMES)} tolerance(s) agree between "
          f"{1 + len(COPIES)} judge file(s) and the criteria doc ({window})")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
