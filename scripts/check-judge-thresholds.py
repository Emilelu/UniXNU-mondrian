#!/usr/bin/env python3
"""Fail when the two judges disagree about the C3 tolerance window, or when the
carry manifest's own totals stop matching the document that quotes them.

Three kinds of copy are checked here.

1. The C3 window. scripts/judge-battery.py is the C3 comparison; the mirror judge
   carries its own copy of the four tolerances; the criteria doc and the mirror's
   docstring quote them. A copy that drifts is silent in the worst direction: the
   mirror judge would keep its old window after the C3 window moved, so a pair of
   samples one threshold apart passes one judge and fails the other.

2. The carry manifest. docs/research/power/CARRY.toml records how many modules,
   files, assertions and judge cases travel to iOS 27. The 27-port page quotes
   those totals as the output of check-power-carry.py. A hand-written total rots
   the moment a judge gains a fixture (P-259), so the sentence is rendered from
   the manifest and required verbatim in the page.

3. The per-judge case counts. The same page lists each judge and its fixture
   count; those are also rendered from the manifest instead of copied.

Exit 0 all agree, 1 a disagreement or a missing piece, 2 a file cannot be read.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]
CANON = "scripts/judge-battery.py"
COPIES = ("scripts/judge-k60-battery-mirror.py",)
DOC = "docs/research/charger/07-DEVICE-CRITERIA.md"
NAMES = ("V_TOL_MV", "I_TOL_MA", "SOC_TOL_HUNDREDTHS", "T_TOL_HUNDREDTHS")
CARRY = "docs/research/power/CARRY.toml"
CARRY_DOC = "docs/research/power/08-IOS27-POWER-PORT.md"

# A judge that states the window in its own words is a fourth copy of the same
# numbers: the constant can move while the docstring keeps the old value
# (P-259 shape). Each phrase is rendered from the constants, so the check reads
# the code and the prose together.
PROSE = {
    "scripts/judge-k60-battery-mirror.py": (
        "<= {V_TOL_MV} mV",
        "within {I_TOL_MA} mA",
        "<= {SOC_PP} percentage points",
        "<= {T_TOL_HUNDREDTHS} hundredths",
    ),
}


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


def short_judge(name: str) -> str:
    """judge-k60-handoff-console -> handoff, as the page writes it."""
    out = name
    if out.startswith("judge-k60-"):
        out = out[len("judge-k60-"):]
    if out.endswith("-console"):
        out = out[:-len("-console")]
    return out


def carry_values(root: pathlib.Path) -> dict:
    """The carry manifest's totals, read once and rendered below."""
    path = root / CARRY
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    modules = data.get("module", [])
    judges = data.get("judge", [])
    values = {
        "modules": len(modules),
        "files": sum(len(module.get("files", [])) for module in modules),
        "checks": sum(int(module.get("checks", 0)) for module in modules),
        "judges": len(judges),
        "cases": sum(int(judge.get("cases", 0)) for judge in judges),
        "judge_cases": [(short_judge(str(judge.get("name", ""))), int(judge.get("cases", 0)))
                        for judge in judges],
    }
    return values


def carry_sentences(values: dict) -> tuple[str, str]:
    """The two sentences the 27-port page must carry, rendered from the manifest."""
    bundle = (f"power-carry: OK ({values['modules']} modules, {values['files']} files, "
              f"{values['checks']} checks; {values['judges']} judge(s), {values['cases']} cases)")
    cases = " / ".join(f"{name} {count}" for name, count in values["judge_cases"]) + " 例"
    return bundle, cases


def carry_problems(root: pathlib.Path) -> list[str]:
    problems: list[str] = []
    if not (root / CARRY).is_file():
        return [f"{CARRY} is missing"]
    try:
        values = carry_values(root)
    except Exception as error:  # noqa: BLE001 - any parse failure is a problem to report
        return [f"{CARRY} does not parse: {error}"]
    for key in ("modules", "files", "checks", "judges", "cases"):
        if values[key] <= 0:
            problems.append(f"{CARRY}: {key} is {values[key]}, expected a positive count")
    if problems:
        return problems
    doc = root / CARRY_DOC
    if not doc.is_file():
        return [f"{CARRY_DOC} is missing"]
    body = doc.read_text(encoding="utf-8")
    bundle, cases = carry_sentences(values)
    if bundle not in body:
        problems.append(f"{CARRY_DOC} no longer quotes the carry manifest: expected {bundle!r} "
                        f"- run check-power-carry.py and copy the line it prints")
    if cases not in body:
        problems.append(f"{CARRY_DOC} no longer states the judge fixture counts: expected {cases!r} "
                        f"- they are rendered from CARRY.toml, not copied")
    return problems


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
    prose_values = dict(values)
    prose_values["SOC_PP"] = f"{values['SOC_TOL_HUNDREDTHS'] / 100:.2f}"
    for rel, phrases in PROSE.items():
        path = root / rel
        if not path.is_file():
            problems.append(f"{rel} is missing")
            continue
        body = path.read_text(encoding="utf-8")
        for phrase in phrases:
            want = phrase.format(**prose_values)
            if want not in body:
                problems.append(
                    f"{rel} no longer states the window it applies: expected {want!r} "
                    f"- change the docstring with the constants, or the reader trusts the old number")
    problems.extend(carry_problems(root))
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
    carry = carry_values(root)
    print(f"✅ judge-thresholds: {len(NAMES)} tolerance(s) agree between "
          f"{1 + len(COPIES)} judge file(s), the criteria doc and "
          f"{sum(len(v) for v in PROSE.values())} sentence(s) that quote them ({window}); "
          f"CARRY {carry['modules']} modules / {carry['files']} files / {carry['checks']} checks / "
          f"{carry['judges']} judge(s) / {carry['cases']} cases")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
