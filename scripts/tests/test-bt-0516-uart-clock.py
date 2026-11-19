#!/usr/bin/env python3
"""Host-only evidence for patch 0516 (QcaBluetooth 986d631 transport fix).

The retained d8 image and its frozen 235-patch series are the base identity.
The candidate is the same series plus exactly one patch, 0516.  Inputs are
fail-closed: any mismatch refuses to run before compilation.  The harness
drives qbt_core.c with synthetic platform callbacks; it does not touch a
controller, UART, DMA, IBS or hardware, and it is not a d8 timeline replay.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT = Path("/mnt/e/k60-work/artifacts/bt-d8-tlv")

MANIFEST_SHA256 = "3dad0a5284896e7fe1cd649db67c604339ef7ec2c3baf17805a5804fe2f91db0"
FROZEN_SHA256 = "ec0bce53352203a5e430ce1ac7f80ae407ed1ba3ba208286dc665ddfe741f4e9"
HEAD = "91dcd0761aeb035c15de743478851fb8ce0c0417"
BOOT_IMG_SHA256 = "0297012d47eb727bd52c164076bd60bdf90ee47d56eacdf19a89142f794fef2b"
BOOT_IMG_SIZE = 201887744
KERNEL_SHA256 = "6c96f7ccd641d0f751cd76669312c7279055e3232415d5b2d505b28c38065331"

# The first 235 lines are the frozen d8 series; 0516 is line 236 and 0517 may follow.
D8_PREFIX_SHA256 = "9a2cfd416b5250854f8fda38d03ca095a631be296e0679bf9522ba445e73cbb8"
D8_NAMES_SIZES = "f7aa7d63470b891d"
D8_COUNT = 235
SERIES_SHA256 = "e7de39278e0eb0da1c5a5036e0645466885678eefdf57835e279f0bef2717db2"
SERIES_COUNT = 236
PATCH_0516 = "0516-k60-bt-qbt-uart-clock.patch"
PATCH_0516_SHA256 = "0134a31bedb65fe6669a7ce7745bc5b9fcb6a7cd44ac66f96f3f604bb01ac6c8"
PATCH_0517 = "0517-k60-bt-power-order.patch"
PATCH_0518 = "0518-k60-bt-gic-intid.patch"

QBT_SOURCE = {
    "qbt_core.c": "653723e92606893f9b91d2273193e5dabd440bbdba3dff5229160c113992e545",
    "qbt.h": "23848f8d892420f79cb7ed3aa4d91079cc9f0b9378c888965b5abc332afe24e0",
    "qbt_internal.h": "400f285f5f4e3277ff4c1d9e5a214409672a78ba76d3789213d3c619db729104",
    "qbt_linux.c": "1281330305072c85bd6e7cf8fc67e56f0ba689f58b8eae7373303ed1d20b14c7",
}

HARNESS = ROOT / "scripts/tests/fixtures/bt-0516-clock-harness.c"
D8_HARNESS = ROOT / "scripts/tests/fixtures/bt-d8-adapter-harness.c"
D8_SUPPORT = ROOT / "scripts/tests/fixtures/bt-d8-adapter-support.c"

SCENARIOS = ("clock_wake_in_stop", "clock_refused_write")

# Each source mutation must turn its named scenario red.  These are twins of
# the four 986d631 behaviors, derived from the reconstructed candidate only.
SOURCE_MUTATIONS = (
    ("old_step_gate", "clock_wake_in_stop",
     "if (pending || q->control_length) {", "if (pending) {", 1),
    ("old_clock_revert", "clock_wake_in_stop",
     "if (q->info.state != 3 && (q->control_length || q->rx_awake)) {",
     "if (0) {", 1),
    ("old_deadline", "clock_refused_write",
     "return q->write_retry_at;", "return 0;", 2),
    ("old_retry_helper", "clock_refused_write",
     "else if (idle) { q->write_retry_at = t + QBT_TX_POLL; q->stats.tx_refused++; }",
     "else if (idle) { }", 1),
)

failures = 0
cases = 0


def check(cond: bool, label: str, detail: str = "") -> None:
    global failures, cases
    cases += 1
    if cond:
        print(f"  ok: {label}")
    else:
        failures += 1
        print(f"  FAIL: {label}" + (f" - {detail}" if detail else ""))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def refuse(message: str) -> "NoReturn":
    print(f"REFUSED: {message}")
    raise SystemExit(2)


def require_file(path: Path, label: str) -> None:
    if not path.is_file():
        refuse(f"{label} is missing: {path}")


def parse_frozen(path: Path) -> dict[str, str]:
    require_file(path, "frozen list")
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="strict").splitlines():
        if not line.strip():
            continue
        m = re.match(r"^([0-9a-f]{64})  (.+)$", line)
        if not m:
            refuse(f"frozen line is not '<sha256>  <path>': {line[:80]!r}")
        out[m.group(2)] = m.group(1)
    return out


def series_fingerprint(lines: list[str], patches: Path) -> str:
    h = hashlib.sha256()
    for name in lines:
        h.update(name.encode())
        p = patches / name
        if p.is_file():
            h.update(str(p.stat().st_size).encode())
    return h.hexdigest()[:16]


def validate_inputs(artifact: Path, patches: Path) -> list[str]:
    print("input binding (fail-closed)")
    manifest_path = artifact / "build-manifest.json"
    require_file(manifest_path, "d8 manifest")
    actual_manifest = sha256(manifest_path)
    check(actual_manifest == MANIFEST_SHA256, "manifest sha256", actual_manifest)
    if actual_manifest != MANIFEST_SHA256:
        refuse("manifest bytes differ from the retained d8 manifest")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    check(manifest.get("tag") == "bt-d8-tlv", "manifest tag")
    repo = manifest.get("repo", {})
    check(repo.get("head") == HEAD, "manifest head", str(repo.get("head")))
    check(repo.get("dirty_files") == 0, "manifest dirty_files", str(repo.get("dirty_files")))
    if repo.get("head") != HEAD or repo.get("dirty_files") != 0:
        refuse("manifest head/dirty identity mismatch")

    components = manifest.get("components", {})
    check(components.get("boot_img") == BOOT_IMG_SHA256, "manifest boot_img")
    check(components.get("kernel_built") == KERNEL_SHA256, "manifest kernel_built")
    if components.get("boot_img") != BOOT_IMG_SHA256:
        refuse("manifest boot_img hash mismatch")
    boot_img = artifact / "boot.img"
    require_file(boot_img, "d8 boot.img")
    check(sha256(boot_img) == BOOT_IMG_SHA256, "boot.img sha256", sha256(boot_img))
    check(boot_img.stat().st_size == BOOT_IMG_SIZE, "boot.img size", str(boot_img.stat().st_size))
    if sha256(boot_img) != BOOT_IMG_SHA256 or boot_img.stat().st_size != BOOT_IMG_SIZE:
        refuse("boot.img bytes differ from the retained d8 image")

    frozen = manifest.get("frozen", {})
    check(frozen.get("list_sha256") == FROZEN_SHA256, "manifest frozen list hash")
    before = artifact / "frozen-before.txt"
    after = artifact / "frozen-after.txt"
    require_file(before, "frozen-before")
    require_file(after, "frozen-after")
    check(sha256(before) == FROZEN_SHA256, "frozen-before sha256", sha256(before))
    check(sha256(after) == FROZEN_SHA256, "frozen-after sha256", sha256(after))
    if sha256(before) != FROZEN_SHA256 or sha256(after) != FROZEN_SHA256:
        refuse("frozen lists differ from the d8 build")
    frozen_map = parse_frozen(before)
    if frozen_map != parse_frozen(after):
        refuse("frozen-before and frozen-after disagree")

    series_path = patches / "series"
    require_file(series_path, "xnu series")
    lines = [line.strip() for line in series_path.read_text(encoding="utf-8").splitlines()
             if line.strip()]
    check(len(lines) >= SERIES_COUNT, "series at least 236 entries", str(len(lines)))
    check(len(lines) >= D8_COUNT and lines[D8_COUNT - 1] != PATCH_0516,
          "d8 prefix ends before 0516")
    check(len(lines) >= SERIES_COUNT and lines[SERIES_COUNT - 1] == PATCH_0516,
          "0516 at the candidate tail")
    tail_ok = len(lines) == SERIES_COUNT or (
        len(lines) > SERIES_COUNT
        and all(line.startswith(("0517-", "0518-", "0519-", "0520-", "0523-", "0525-"))
                for line in lines[SERIES_COUNT:]))
    check(tail_ok, "candidate tail is 0516 optionally followed by later patches")
    if not tail_ok:
        refuse("candidate series tail is not 0516 or 0516+0517+0518")
    candidate = lines[:SERIES_COUNT]
    candidate_sha = hashlib.sha256(("\n".join(candidate) + "\n").encode()).hexdigest()
    check(candidate_sha == SERIES_SHA256, "candidate 236-entry prefix sha256", candidate_sha)
    if candidate_sha != SERIES_SHA256:
        refuse("series bytes differ from the 235-patch d8 series plus 0516")

    prefix = lines[:D8_COUNT]
    prefix_sha = hashlib.sha256(("\n".join(prefix) + "\n").encode()).hexdigest()
    check(prefix_sha == D8_PREFIX_SHA256, "d8 prefix sha256", prefix_sha)
    check(series_fingerprint(prefix, patches) == D8_NAMES_SIZES,
          "d8 prefix names+sizes fingerprint", series_fingerprint(prefix, patches))
    if prefix_sha != D8_PREFIX_SHA256 or series_fingerprint(prefix, patches) != D8_NAMES_SIZES:
        refuse("d8 prefix identity mismatch")

    for name in prefix:
        p = patches / name
        if not p.is_file():
            refuse(f"series patch is missing: {name}")
        expected = frozen_map.get(f"patches/xnu/{name}")
        if expected is None:
            refuse(f"series patch is absent from frozen-before: {name}")
        actual = sha256(p)
        if actual != expected:
            refuse(f"series patch bytes differ from frozen-before: {name}")
    check(all((patches / name).is_file() for name in prefix), "all 235 d8 patches present")

    patch_0516 = patches / PATCH_0516
    require_file(patch_0516, "0516 patch")
    actual_0516 = sha256(patch_0516)
    check(actual_0516 == PATCH_0516_SHA256, "0516 patch sha256", actual_0516)
    check(f"patches/xnu/{PATCH_0516}" not in frozen_map, "0516 is not part of the d8 freeze")
    if actual_0516 != PATCH_0516_SHA256:
        refuse("0516 patch bytes differ from the reviewed candidate")
    return lines


def run(cmd: list[str], cwd: Path, timeout: int = 300) -> subprocess.CompletedProcess:
    e = os.environ.copy()
    e.update({"LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1",
              "GIT_CONFIG_GLOBAL": os.devnull, "HOME": str(cwd)})
    return subprocess.run(cmd, cwd=cwd, env=e, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=timeout)


def reconstruct(work: Path, patches: Path, lines: list[str]) -> Path:
    source = work / "source"
    if source.exists():
        shutil.rmtree(source)
    source.mkdir(parents=True)
    r = run(["git", "init", "-q"], source)
    if r.returncode != 0:
        refuse(f"git init failed: {r.stderr.strip()}")
    for i, name in enumerate(lines, 1):
        r = run(["git", "-c", "core.autocrlf=false", "apply",
                 "--whitespace=nowarn", "--include=bsd/dev/qbt/*",
                 str(patches / name)], source)
        if r.returncode != 0:
            refuse(f"patch {i} did not apply exactly: {name}: {r.stderr.strip()}")
    qbt = source / "bsd/dev/qbt"
    for name, expected in QBT_SOURCE.items():
        p = qbt / name
        require_file(p, f"reconstructed {name}")
        actual = sha256(p)
        check(actual == expected, f"reconstructed {name} sha256", actual)
        if actual != expected:
            refuse(f"reconstructed source differs: {name}")
    return qbt


def compile_clock(work: Path, qbt: Path, source: Path, tag: str) -> Path:
    out = work / f"clock-{tag}"
    cmd = [
        "gcc", "-std=gnu11", "-O0", "-g", "-Wall", "-Wextra",
        "-Wno-unused-parameter", "-I", str(qbt),
        str(HARNESS), str(source), "-o", str(out),
    ]
    r = run(cmd, work)
    if r.returncode != 0:
        refuse(f"gcc failed for {tag}:\n{r.stderr}")
    return out


def execute(binary: Path, scenario: str, work: Path) -> tuple[int, str]:
    r = run([str(binary), scenario], work, timeout=120)
    return r.returncode, r.stdout + r.stderr


def compile_adapter(work: Path, qbt: Path) -> Path:
    out = work / "adapter-0516"
    cmd = [
        "gcc", "-std=gnu11", "-O0", "-g", "-fno-strict-aliasing",
        "-Wno-unused-parameter", "-Wno-unused-function", "-Wno-sign-compare",
        "-Wno-missing-field-initializers",
        "-I", str(qbt / "shim"), "-I", str(qbt),
        "-include", "qbt_linux.h",
        str(D8_HARNESS), str(D8_SUPPORT), str(qbt / "qbt_core.c"),
        str(qbt / "btqca.c"), "-o", str(out),
    ]
    r = run(cmd, work)
    if r.returncode != 0:
        refuse(f"gcc failed for the adapter regression:\n{r.stderr}")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="0516 qbt UART-clock host evidence")
    parser.add_argument("--artifact", default=str(DEFAULT_ARTIFACT))
    parser.add_argument("--patch-dir", default=str(ROOT / "patches/xnu"))
    parser.add_argument("--work-dir", default="")
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--no-mutations", action="store_true")
    parser.add_argument("--no-adapter", action="store_true")
    args = parser.parse_args(argv)

    print("HOST-ONLY: 0516 qbt UART-clock software path on synthetic platform inputs")
    print("NOT RUN: controller, UART, DMA, IBS, hardware, d8 timeline replay")
    print("test-bt-0516-uart-clock")

    artifact = Path(args.artifact)
    patches = Path(args.patch_dir)
    if not artifact.is_dir():
        refuse(f"artifact directory is missing: {artifact}")
    lines = validate_inputs(artifact, patches)

    clock_src = HARNESS.read_text(encoding="utf-8")
    if "HOST-ONLY" not in clock_src or "synthetic" not in clock_src:
        refuse("0516 fixture lost its host-only/synthetic boundary")

    work = Path(args.work_dir) if args.work_dir else Path(tempfile.mkdtemp(prefix="bt-0516-"))
    work.mkdir(parents=True, exist_ok=True)
    print(f"work: {work}")
    try:
        qbt = reconstruct(work, patches, lines)

        print("clock scenarios")
        binary = compile_clock(work, qbt, qbt / "qbt_core.c", "base")
        for name in SCENARIOS:
            rc, out = execute(binary, name, work)
            check(rc == 0, f"scenario {name} rc", out[-2000:])
            if rc == 0:
                check(f"RESULT {name} PASS failures=0" in out,
                      f"scenario {name} self-check", out[-1000:])
            else:
                print(out[-3000:])

        if not args.no_mutations:
            print("negative controls (each must really go red)")
            source_text = (qbt / "qbt_core.c").read_text(encoding="utf-8")
            for label, scenario, old, new, expected in SOURCE_MUTATIONS:
                count = source_text.count(old)
                check(count == expected, f"mutation {label} anchor count", str(count))
                if count != expected:
                    continue
                mutated = source_text.replace(old, new)
                mf = work / f"mutant-{label}.c"
                mf.write_text(mutated, encoding="utf-8")
                mb = compile_clock(work, qbt, mf, f"mut-{label}")
                rc, out = execute(mb, scenario, work)
                red = rc != 0 and "FAIL" in out
                if red:
                    red_line = next((ln.strip() for ln in out.splitlines()
                                     if ln.strip().startswith("FAIL")), "rc != 0")
                    print(f"  red: mutation {label}: {red_line}")
                check(red, f"mutation {label} turns {scenario} red", out[-800:])

        if not args.no_adapter:
            print("adapter regression on the 236-patch candidate")
            adapter = compile_adapter(work, qbt)
            names = list(dict.fromkeys(re.findall(
                r'\{"([a-z_]+)", scenario_',
                D8_HARNESS.read_text(encoding="utf-8"))))
            check(len(names) == 22, "adapter scenario count", str(len(names)))
            for name in names:
                rc, out = execute(adapter, name, work)
                check(rc == 0, f"adapter scenario {name} rc", out[-2000:])
                if rc == 0:
                    check(f"RESULT {name} PASS failures=0" in out,
                          f"adapter scenario {name} self-check", out[-1000:])
                else:
                    print(out[-3000:])

        print(f"\nTESTS {'OK' if failures == 0 else 'FAILED'}: {cases} case(s), {failures} failure(s)")
        return 0 if failures == 0 else 1
    finally:
        if args.keep:
            print(f"kept work dir: {work}")
        else:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
