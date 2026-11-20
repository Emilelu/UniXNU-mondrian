
#!/usr/bin/env python3
"""Fixtures for scripts/check-judge-thresholds.py (P-259: two copies of one number)."""
from __future__ import annotations

import importlib.util
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "scripts" / "check-judge-thresholds.py"
BUILD = ROOT / "build" / ("judge-threshold-tests-" + str(__import__("os").getpid()))

JUDGE = '''#!/usr/bin/env python3
"""Mirror judge.

Criteria:
  SOC       |our SOC - mirror capacity| <= 3.00 percentage points
  VOLTAGE   |our mV - mirror uV/1000| <= {v} mV
  CURRENT   |our mA| vs |mirror uA/1000| within 150 mA (magnitude; sign is a note)
  TEMP      |our hundredths - mirror tenths*10| <= 300 hundredths (3 C)
"""
V_TOL_MV = {v}
I_TOL_MA = 150
SOC_TOL_HUNDREDTHS = 300
T_TOL_HUNDREDTHS = 300

def worst(delta):
    return abs(delta) > V_TOL_MV or abs(delta) > I_TOL_MA or delta > SOC_TOL_HUNDREDTHS or delta > T_TOL_HUNDREDTHS
'''
DOC = """# criteria

C3 阈值：±60 mV / ±150 mA / ±3 pp / ±3 °C（判读器常量）。
"""

CARRY = """version = 1

[[module]]
name = "K60Demo"
checks = 3
files = [
  { path = "drivers/PongPower/K60Demo.c", sha256 = "00" },
]

[[judge]]
name = "judge-k60-demo-console"
cases = 7
"""

CARRY_DOC = """# ios 27 port

power-carry: OK (1 modules, 1 files, 3 checks; 1 judge(s), 7 cases)

判读器夹具：demo 7 例
"""

failures = 0
checks = 0


def check(label, condition, detail=""):
    global failures, checks
    checks += 1
    if condition:
        print("ok   " + label)
    else:
        failures += 1
        print("FAIL " + label + (": " + detail if detail else ""))


def load():
    spec = importlib.util.spec_from_file_location("jth", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tree(name, *, v=60, copy_v=60, doc=DOC, drop_copy=None, unused=False, judge=JUDGE):
    base = BUILD / name
    if base.exists():
        shutil.rmtree(base, ignore_errors=True)
    (base / "scripts").mkdir(parents=True)
    (base / "docs" / "research" / "charger").mkdir(parents=True)
    (base / "docs" / "research" / "power").mkdir(parents=True)
    (base / "scripts" / "judge-battery.py").write_text(judge.format(v=v), encoding="utf-8", newline="\n")
    text = JUDGE.format(v=copy_v)
    if drop_copy:
        text = "\n".join(line for line in text.split("\n") if not line.startswith(drop_copy))
    if unused:
        text = text.replace("abs(delta) > V_TOL_MV or ", "")
    (base / "scripts" / "judge-k60-battery-mirror.py").write_text(text, encoding="utf-8", newline="\n")
    (base / "docs" / "research" / "charger" / "07-DEVICE-CRITERIA.md").write_text(
        doc, encoding="utf-8", newline="\n")
    (base / "docs" / "research" / "power" / "CARRY.toml").write_text(
        CARRY, encoding="utf-8", newline="\n")
    (base / "docs" / "research" / "power" / "08-IOS27-POWER-PORT.md").write_text(
        CARRY_DOC, encoding="utf-8", newline="\n")
    return base


def run(root):
    env = {**__import__("os").environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run([sys.executable, str(TOOL), "--root", str(root)],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env)


def main():
    module = load()
    BUILD.mkdir(parents=True, exist_ok=True)

    ok = tree("agree")
    check("two judges that agree pass", module.verify(ok) == [], str(module.verify(ok)))

    bad = tree("copy-moved", copy_v=80)
    problems = module.verify(bad)
    check("a copy whose window moved is refused",
          any("the two judges would disagree" in p for p in problems), str(problems))

    missing = tree("copy-missing", drop_copy="SOC_TOL_HUNDREDTHS")
    problems = module.verify(missing)
    check("a copy that dropped a tolerance is refused",
          any("has to keep the same SOC_TOL_HUNDREDTHS" in p for p in problems), str(problems))

    dead = tree("unused", unused=True)
    problems = module.verify(dead)
    check("a tolerance nothing reads is refused",
          any("defined but never read" in p for p in problems), str(problems))

    prose = tree("prose-drift")
    mirror = prose / "scripts" / "judge-k60-battery-mirror.py"
    mirror.write_text(mirror.read_text(encoding="utf-8").replace("<= 60 mV", "<= 80 mV"),
                      encoding="utf-8", newline="\n")
    problems = module.verify(prose)
    check("a docstring that quotes the old window is refused",
          any("no longer states the window it applies" in p for p in problems), str(problems))

    gone = tree("prose-gone")
    mirror = gone / "scripts" / "judge-k60-battery-mirror.py"
    text2 = "\n".join(line for line in mirror.read_text(encoding="utf-8").split("\n")
                      if "VOLTAGE" not in line)
    mirror.write_text(text2, encoding="utf-8", newline="\n")
    problems = module.verify(gone)
    check("a docstring that stops stating the window is refused",
          any("expected '<= 60 mV'" in p for p in problems), str(problems))

    stale = tree("stale-doc")
    (stale / "docs" / "research" / "charger" / "07-DEVICE-CRITERIA.md").write_text(
        DOC.replace("±60 mV", "±70 mV"), encoding="utf-8", newline="\n")
    problems = module.verify(stale)
    check("a doc that quotes the old window is refused",
          any("does not quote the window" in p for p in problems), str(problems))

    nodoc = tree("no-doc")
    (nodoc / "docs" / "research" / "charger" / "07-DEVICE-CRITERIA.md").unlink()
    check("a missing criteria doc is refused",
          any("07-DEVICE-CRITERIA.md is missing" in p for p in module.verify(nodoc)))

    stale_carry = tree("carry-stale")
    page = stale_carry / "docs" / "research" / "power" / "08-IOS27-POWER-PORT.md"
    page.write_text(CARRY_DOC.replace("7 cases", "6 cases"), encoding="utf-8", newline="\n")
    problems = module.verify(stale_carry)
    check("a page whose carry totals moved is refused",
          any("no longer quotes the carry manifest" in p for p in problems), str(problems))

    stale_cases = tree("carry-cases")
    page = stale_cases / "docs" / "research" / "power" / "08-IOS27-POWER-PORT.md"
    page.write_text(CARRY_DOC.replace("demo 7 例", "demo 6 例"), encoding="utf-8", newline="\n")
    problems = module.verify(stale_cases)
    check("a page whose judge fixture counts moved is refused",
          any("no longer states the judge fixture counts" in p for p in problems), str(problems))

    no_carry = tree("carry-missing")
    (no_carry / "docs" / "research" / "power" / "CARRY.toml").unlink()
    problems = module.verify(no_carry)
    check("a missing carry manifest is refused",
          any("CARRY.toml is missing" in p for p in problems), str(problems))

    nojudge = tree("no-mirror")
    (nojudge / "scripts" / "judge-k60-battery-mirror.py").unlink()
    check("a missing mirror judge is refused",
          any("judge-k60-battery-mirror.py is missing" in p for p in module.verify(nojudge)))

    broken = tree("broken")
    (broken / "scripts" / "judge-battery.py").write_text("def (", encoding="utf-8", newline="\n")
    check("a judge that does not import is refused",
          any("does not import" in p for p in module.verify(broken)))

    result = run(ok)
    check("the cli exits 0 on agreement", result.returncode == 0, result.stderr)
    check("the cli prints the window it checked", "±60 mV / ±150 mA / ±3 pp / ±3 °C" in result.stdout,
          result.stdout)
    check("the cli prints the carry totals it rendered",
          "CARRY 1 modules / 1 files / 3 checks / 1 judge(s) / 7 cases" in result.stdout, result.stdout)

    result = run(bad)
    check("the cli exits 1 on a moved copy", result.returncode == 1, result.stdout)
    check("the cli names the constant", "V_TOL_MV = 80" in result.stdout, result.stdout)

    result = run(BUILD / "does-not-exist")
    check("an unreadable root exits 2", result.returncode == 2, result.stdout)

    real = subprocess.run([sys.executable, str(TOOL)], capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
    check("this checkout agrees", real.returncode == 0, real.stdout + real.stderr)
    check("this checkout renders the same window it prints",
          "±60 mV / ±150 mA / ±3 pp / ±3 °C" in real.stdout, real.stdout)

    print("")
    if failures:
        print(f"TESTS FAILED {failures} check(s)")
        return 1
    print("TESTS OK %d checks (0 failures)" % checks)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
