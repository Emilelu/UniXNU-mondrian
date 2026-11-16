#!/usr/bin/env python3
"""Apply the WiFi flash proposal only in temporary trees and test its CLI.

The active gate and EIGHT-STEPS.toml are hashed before/after. Only the unrelated
README renderer is stubbed; selection and all evidence checks run in the actual
patched gate subprocess. Requires Python 3.11+ (or tomli) and git.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts" / "eight-step-gate.py"
DATA = ROOT / "docs" / "research" / "EIGHT-STEPS.toml"
PATCH = ROOT / "scripts" / "proposals" / "wifi-eight-step-gate.patch"
STEPS = ("same_model", "official", "decompile", "wide", "plan", "deep", "verify")
OBSERVATION = "wifi-observation-a"
EVIDENCE = "Fixture evidence: source.c:123 records the exact expected state and result."


def record(status):
    steps = {name: {"done": True, "evidence": EVIDENCE} for name in STEPS}
    steps["wide"].update(catalog_checked=True, catalog_result=EVIDENCE)
    steps["verify"].update(local_verified=True, static_check=EVIDENCE,
                           unit_test=EVIDENCE, artifact_check=EVIDENCE,
                           observation=OBSERVATION, reference="verification.md:12")
    steps["device"] = {"done": False, "prediction": {
        "success": "Expected log line from source.c:123",
        "failure": "Refusal or timeout described by source.c:124",
        "observation": OBSERVATION, "reference": "observation.md:25"}}
    return {"status": status, "step": steps}


def fixture():
    return {"touch": record("active"), "wifi": record("parked")}


def toml(data):
    lines = []
    def emit(path, table):
        lines.append("[" + ".".join(path) + "]")
        for key, value in table.items():
            if not isinstance(value, dict):
                encoded = str(value).lower() if isinstance(value, bool) else json.dumps(value)
                lines.append(key + " = " + encoded)
        lines.append("")
        for key, value in table.items():
            if isinstance(value, dict):
                emit(path + [key], value)
    emit(["hardware"], data)
    return chr(10).join(lines)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    before = (digest(GATE), digest(DATA))
    failures = 0
    cases = 0
    with tempfile.TemporaryDirectory(prefix="wifi-flash-proposal-") as temp:
        tree = Path(temp)
        (tree / "scripts").mkdir()
        (tree / "docs" / "research").mkdir(parents=True)
        shutil.copy2(GATE, tree / "scripts" / GATE.name)
        for options in (("--check",), ()):
            applied = subprocess.run(["git", "apply", *options, str(PATCH)],
                                     cwd=tree, capture_output=True, text=True)
            if applied.returncode:
                print(applied.stdout + applied.stderr)
                return 1
        (tree / "scripts" / "render-eight-step-table.py").write_text(
            "raise SystemExit(0)" + chr(10), encoding="utf-8")

        def check(label, want_ok, needle, data=None, items="wifi",
                  observation=OBSERVATION, mode="--flash", build_items=None):
            nonlocal failures, cases
            cases += 1
            path = tree / "docs" / "research" / DATA.name
            path.write_text(toml(fixture() if data is None else data), encoding="utf-8")
            env = {key: value for key, value in os.environ.items()
                   if not key.startswith("K60_")}
            env["PYTHONIOENCODING"] = "utf-8"
            for key, value in (("K60_FLASH_ITEMS", items),
                               ("K60_FLASH_OBSERVATION", observation),
                               ("K60_EIGHT_STEP_ITEMS", build_items)):
                if value is not None:
                    env[key] = value
            proc = subprocess.run([sys.executable, str(tree / "scripts" / GATE.name), mode],
                                  cwd=tree, env=env, capture_output=True, text=True,
                                  encoding="utf-8", timeout=20)
            output = proc.stdout + proc.stderr
            passed = (proc.returncode == 0) == want_ok and needle in output
            print(("PASS " if passed else "FAIL ") + label)
            if not passed:
                failures += 1
                print("exit=%s expected success=%s" % (proc.returncode, want_ok)); print(output)

        check("explicit parked WiFi is included with the active floor", True,
              "touch[active], wifi[parked]")
        check("missing flash scope fails", False, "explicit K60_FLASH_ITEMS", items=None)
        check("unknown scope fails", False, "unknown hardware", items="nosuch")
        check("empty comma scope fails", False, "explicit K60_FLASH_ITEMS", items=",")
        check("partial empty scope fails", False, "explicit K60_FLASH_ITEMS", items="wifi,")
        check("duplicate scope fails", False, "duplicate hardware", items="wifi,wifi")
        check("observation cannot silently omit parked WiFi", False,
              "explicit WiFi scope", items="touch")
        check("missing observation identifier fails", False, "K60_FLASH_OBSERVATION",
              observation=None)
        check("invalid observation identifier fails", False, "K60_FLASH_OBSERVATION",
              observation="../old")

        for step in ("verify", "device"):
            data = fixture()
            entry = data["wifi"]["step"][step]
            if step == "device":
                entry = entry["prediction"]
            entry["observation"] = "wifi-observation-old"
            check("stale %s observation fails" % step, False,
                  "%s observation mismatch" % step, data)
            entry["observation"] = OBSERVATION
            del entry["reference"]
            check("missing %s reference fails" % step, False,
                  "%s missing observation reference" % step, data)

        for name in STEPS:
            data = fixture()
            del data["wifi"]["step"][name]
            check("missing step %s fails" % name, False, "wifi ::", data)
        for field in ("local_verified", "static_check", "unit_test", "artifact_check"):
            data = fixture()
            del data["wifi"]["step"]["verify"][field]
            check("missing verify %s fails" % field, False, field, data)
        for field in ("success", "failure"):
            data = fixture()
            del data["wifi"]["step"]["device"]["prediction"][field]
            check("missing prediction %s fails" % field, False, "prediction." + field, data)
        data = fixture()
        data["touch"]["step"]["official"]["done"] = False
        check("active floor remains checked", False, "touch ::", data)
        data = {"wifi": record("parked")}
        check("explicit WiFi works with no active records", True, "wifi[parked]", data)
        check("unbound non-WiFi scope can omit WiFi: integration blocker", True,
              "touch[active]", items="touch", observation=None)
        for field, value in (("done", False), ("evidence", "too short")):
            data = fixture()
            data["wifi"]["step"]["official"][field] = value
            check("invalid official %s fails" % field, False, "wifi ::", data)
        for step in ("verify", "device"):
            data = fixture()
            entry = data["wifi"]["step"][step]
            if step == "device":
                entry = entry["prediction"]
            del entry["observation"]
            check("missing %s observation fails" % step, False,
                  "%s observation mismatch" % step, data)
            entry["observation"] = OBSERVATION
            entry["reference"] = "unsupported assertion"
            check("uncited %s reference fails" % step, False,
                  "%s missing observation reference" % step, data)
        check("all-parked default build retains prior refusal", False, "禁止构建",
              data={"wifi": record("parked")}, items=None, observation=None, mode="--build")
        check("build mode retains existing scope behavior", True, "wifi[parked]",
              mode="--build", items=None, observation=None, build_items="wifi")

    if before != (digest(GATE), digest(DATA)):
        print("FAIL active gate or evidence file changed")
        failures += 1
    print("TESTS OK %d cases (%d failure(s)); active inputs unchanged" % (cases, failures))
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
