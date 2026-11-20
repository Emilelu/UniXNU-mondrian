#!/usr/bin/env python3
"""Fixture tests for scripts/check-pac-probe-capture.py.

The checker exists so a one-shot flight cannot turn a missing probe row into
"hardware does not support PAC". These cases prove the three verdicts and the
line-level attribution, plus the command-line exit codes.
"""
import hashlib
import importlib.util
import os
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
WORK = REPO / "build" / ("pac-capture-tests-%d" % os.getpid())
CHECKS = 0
FAILURES = 0


def check(name, condition, detail=""):
    global CHECKS, FAILURES
    CHECKS += 1
    if condition:
        print("ok   %s" % name)
    else:
        FAILURES += 1
        print("FAIL %s%s" % (name, ": " + detail if detail else ""))


def load():
    spec = importlib.util.spec_from_file_location(
        "check_pac_probe_capture", REPO / "scripts" / "check-pac-probe-capture.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def healthy(sha):
    lines = ["K60PAC: probe v3 start image_sha256=%s cpus=8" % sha, "K60PAC: P0 begin"]
    for cpu in range(8):
        lines.append("K60PAC: P0 core=%d mpidr=0x%03x midr=0x%08x isar1=0x0010011101211052 "
                     "isar2=0x0 apa=0b0101 api=0 gpa=1 gpi=0 verdict=PASS"
                     % (cpu, cpu * 0x100, 0x410fd460 + cpu))
    lines.append("K60PAC: P0 end")
    lines.append("K60PAC: P1 begin")
    for cpu in range(8):
        for key in ("APIA", "APIB", "APDA", "APDB", "APGA"):
            lines.append("K60PAC: P1 core=%d key=%s write=0x%016x read=0x%016x verdict=PASS"
                         % (cpu, key, cpu + 1, cpu + 1))
        lines.append("K60PAC: P1 core=%d sctlr EnIA=1 EnIB=1 EnDA=1 EnDB=1" % cpu)
    lines.append("K60PAC: P1 end")
    lines.append("K60PAC: P2 begin")
    for cpu in range(8):
        for el in ("1", "0"):
            lines.append("K60PAC: P2 core=%d el=%s p=0x%016x s=0x%016x autia=0x%016x ec=0x00 verdict=PASS"
                         % (cpu, el, cpu + 2, cpu + 3, cpu + 2))
    lines.append("K60PAC: P2 cross-key core=0 ec=0x1c verdict=PASS")
    lines.append("K60PAC: P2 end")
    lines.append("K60PAC: P3 begin")
    lines.append("K60PAC: P3 page=/soc-support repo=UniXNU commit=0123456789abcdef")
    lines.append("K60PAC: P3 end")
    lines.append("K60PAC: P4 begin")
    lines.append("K60PAC: P4 stage=pmap tcr=0x00000022a5192519 tg0=0b00 tg1=0b10")
    lines.append("K60PAC: P4 stage=user tcr=0x00000022a5192519 tg0=0b00 tg1=0b10")
    lines.append("K60PAC: P4 end")
    lines.append("K60PAC: done P0=PASS P1=PASS P2=PASS P3=PASS P4=PASS")
    return lines


def without(lines, needle):
    return [line for line in lines if needle not in line]


def main():
    module = load()
    if WORK.exists():
        shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True)
    image = WORK / "kernel.macho"
    image.write_bytes(b"fixture image\n")
    sha = hashlib.sha256(image.read_bytes()).hexdigest()
    base = healthy(sha)

    formatted = WORK / "probe.macho"
    formatted.write_bytes(b"binary\nprintf(\"K60PAC: probe v3 start image_sha256=%s cpus=8\\n\")\n")
    verdict, missing, details = module.preflight(formatted, 3)
    check("an image with the start format string passes image-only preflight",
          verdict == "PASS" and missing == [] and details.get("bytes", 0) > 0,
          "%s %s" % (verdict, missing))

    verdict, missing, details = module.preflight(image, 3)
    check("an image without the start format string is INVALID and names the build",
          verdict == "INVALID" and any("compiled in" in item and "build problem" in item for item in missing),
          "%s %s" % (verdict, missing))

    verdict, missing, _ = module.evaluate(base, sha)
    check("a complete capture is PASS", verdict == "PASS" and missing == [], "%s %s" % (verdict, missing))

    verdict, missing, details = module.evaluate(["boot only"], sha, image_has_probe=True)
    check("a capture with no probe, from an image that carries it, is INVALID cause=run",
          verdict == "INVALID" and details.get("cause") == "run" and any("did not run" in item for item in missing),
          "%s %s %s" % (verdict, details, missing))

    verdict, missing, details = module.evaluate(["boot only"], sha, image_has_probe=False)
    check("a capture with no probe, from an image without it, is INVALID cause=build",
          verdict == "INVALID" and details.get("cause") == "build" and any("rebuild the image" in item for item in missing),
          "%s %s %s" % (verdict, details, missing))
    check("build and run causes do not produce the same sentence",
          module.evaluate(["boot only"], sha, image_has_probe=True)[2].get("cause")
          != module.evaluate(["boot only"], sha, image_has_probe=False)[2].get("cause"))

    verdict, missing, details = module.evaluate(base, "0" * 64)
    check("a hash mismatch is INVALID cause=version and says it is another image",
          verdict == "INVALID" and details.get("cause") == "version"
          and any("another image" in item for item in missing), "%s %s" % (details, missing))

    lines = [line.replace("cpus=8", "cpus=7") for line in base]
    verdict, missing, _ = module.evaluate(lines, sha)
    check("a capture that did not sample all eight CPUs is INVALID",
          verdict == "INVALID" and any("cpus=7" in item for item in missing), str(missing))

    lines = [line.replace("probe v3", "probe v2") for line in base]
    verdict, missing, _ = module.evaluate(lines, sha)
    check("a capture from another probe version is INVALID and says re-image",
          verdict == "INVALID" and any("re-image" in item for item in missing), str(missing))
    check("the other-version message does not claim the probe is missing",
          all("image carries no probe" not in item for item in missing), str(missing))

    verdict, missing, details = module.evaluate(["K60PAC: boot noise"] + base, sha)
    check("a K60PAC line before start is INVALID cause=version",
          verdict == "INVALID" and details.get("cause") == "version"
          and any("not the start" in item for item in missing), "%s %s" % (details, missing))

    verdict, missing, _ = module.evaluate(without(base, "P0 core=3 "), sha)
    check("a missing P0 core is INCOMPLETE and names the core",
          verdict == "INCOMPLETE" and "P0 core=3 line" in missing, str(missing))

    verdict, missing, _ = module.evaluate(without(base, "P1 core=5 key=APDA "), sha)
    check("a missing P1 key row is INCOMPLETE and names the key",
          verdict == "INCOMPLETE" and "P1 APDA core=5 line" in missing, str(missing))

    verdict, missing, _ = module.evaluate(without(base, "P2 core=7 el=0 "), sha)
    check("a missing P2 EL0 row is INCOMPLETE and names the row",
          verdict == "INCOMPLETE" and "P2 core=7 el=0 line" in missing, str(missing))

    verdict, missing, _ = module.evaluate(without(base, "P4 stage=user "), sha)
    check("a missing P4 runtime row is INCOMPLETE and names the stage",
          verdict == "INCOMPLETE" and "P4 stage=user" in " ".join(missing), str(missing))

    verdict, missing, _ = module.evaluate(without(base, "K60PAC: done "), sha)
    check("a capture without done is INCOMPLETE",
          verdict == "INCOMPLETE" and any("done line" in item for item in missing), str(missing))

    verdict, missing, _ = module.evaluate(base + ["K60PAC: P2 exception trap"], sha)
    check("an exception without EC is INCOMPLETE",
          verdict == "INCOMPLETE" and any("without EC" in item for item in missing), str(missing))

    log = WORK / "console.log"
    log.write_text("\n".join(base) + "\n", encoding="utf-8")
    result = subprocess.run([sys.executable, str(REPO / "scripts" / "check-pac-probe-capture.py"),
                             "--image", str(image), "--log", str(log)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    check("the command prints PASS and exits 0",
          result.returncode == 0 and "PAC-CAPTURE: PASS" in result.stdout,
          "rc=%d out=%r err=%r" % (result.returncode, result.stdout, result.stderr))

    bad_image = WORK / "other.macho"
    bad_image.write_bytes(b"other image\n")
    result = subprocess.run([sys.executable, str(REPO / "scripts" / "check-pac-probe-capture.py"),
                             "--image", str(bad_image), "--log", str(log)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    check("a mismatch on the command line is INVALID, says cause=version and exits 2",
          result.returncode == 2 and "PAC-CAPTURE: INVALID" in result.stdout
          and "cause: version" in result.stdout,
          "rc=%d out=%r err=%r" % (result.returncode, result.stdout, result.stderr))

    result = subprocess.run([sys.executable, str(REPO / "scripts" / "check-pac-probe-capture.py"),
                             "--image", str(formatted)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    check("image-only preflight prints PASS and exits 0",
          result.returncode == 0 and "PAC-CAPTURE: PASS" in result.stdout,
          "rc=%d out=%r err=%r" % (result.returncode, result.stdout, result.stderr))

    result = subprocess.run([sys.executable, str(REPO / "scripts" / "check-pac-probe-capture.py"),
                             "--image", str(image)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    check("image-only preflight without the format string is INVALID and exits 2",
          result.returncode == 2 and "PAC-CAPTURE: INVALID" in result.stdout
          and "compiled in" in result.stdout and "present" not in result.stdout,
          "rc=%d out=%r err=%r" % (result.returncode, result.stdout, result.stderr))

    incomplete = WORK / "incomplete.log"
    incomplete.write_text("\n".join(without(base, "P0 core=3 ")) + "\n", encoding="utf-8")
    result = subprocess.run([sys.executable, str(REPO / "scripts" / "check-pac-probe-capture.py"),
                             "--image", str(image), "--log", str(incomplete)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    check("a missing row on the command line is INCOMPLETE and exits 1",
          result.returncode == 1 and "PAC-CAPTURE: INCOMPLETE" in result.stdout
          and "P0 core=3" in result.stdout,
          "rc=%d out=%r err=%r" % (result.returncode, result.stdout, result.stderr))

    print()
    if FAILURES:
        print("TESTS FAILED %d of %d checks" % (FAILURES, CHECKS))
        return 1
    print("TESTS OK %d checks (0 failure(s))" % CHECKS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
