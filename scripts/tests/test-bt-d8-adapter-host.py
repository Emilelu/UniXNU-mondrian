#!/usr/bin/env python3
"""Host-only adapter and firmware-fallback harness for the d8 Bluetooth image.

The test reconstructs the bsd/dev/qbt sources from the *frozen* d8 series
(manifest 3dad0a..., 235 patches), compiles the real qbt_core.c,
qbt_linux.c and btqca.c with a fake platform, and drives synthetic TLV and
event inputs.  It is not a controller, UART, DMA, IBS or hardware test.

Run it inside WSL/Linux (needs git and gcc) with the retained artifact:

    python3 scripts/tests/test-bt-d8-adapter-host.py \
        --artifact /mnt/e/k60-work/artifacts/bt-d8-tlv

Every input is fail-closed: a missing or changed manifest, frozen list,
series, patch byte, boot.img or source hash refuses to run.  There is no
fallback to "latest" and the current worktree source is never read.
"""
from __future__ import annotations

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
SERIES_PREFIX_SHA256 = "9a2cfd416b5250854f8fda38d03ca095a631be296e0679bf9522ba445e73cbb8"
SERIES_NAMES_SIZES = "f7aa7d63470b891d"
SERIES_COUNT = 235
HEAD = "91dcd0761aeb035c15de743478851fb8ce0c0417"
BOOT_IMG_SHA256 = "0297012d47eb727bd52c164076bd60bdf90ee47d56eacdf19a89142f794fef2b"
BOOT_IMG_SIZE = 201887744
KERNEL_SHA256 = "6c96f7ccd641d0f751cd76669312c7279055e3232415d5b2d505b28c38065331"
QBT_SOURCE = {
    "qbt_core.c": "e3405ca4514795d0b8b2e7221c5c9e6d7108dcdc204f5aa76f16c269aed835da",
    "qbt_linux.c": "a0ec555a27513a7099e9260e725652d9e1d49949830f377c1f5b6c8b7435656e",
    "btqca.c": "ecc7346f297bbedfb7536624afa50d6486fb6f8131d8ed8c9d11fe96504ee8e3",
}
PATCH_NAMES = (
    "0500-k60-bt-qbt-new-files.patch",
    "0514-k60-bt-boot-observability.patch",
    "0515-k60-bt-tlv-counters.patch",
)
HARNESS = ROOT / "scripts/tests/fixtures/bt-d8-adapter-harness.c"
SUPPORT = ROOT / "scripts/tests/fixtures/bt-d8-adapter-support.c"

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


def validate_inputs(artifact: Path, patches: Path) -> tuple[list[str], dict[str, str]]:
    print("input binding (fail-closed)")
    manifest_path = artifact / "build-manifest.json"
    require_file(manifest_path, "d8 manifest")
    check(sha256(manifest_path) == MANIFEST_SHA256, "manifest sha256", sha256(manifest_path))
    if sha256(manifest_path) != MANIFEST_SHA256:
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
    prefix = lines[:SERIES_COUNT]
    prefix_sha = hashlib.sha256(("\n".join(prefix) + "\n").encode()).hexdigest()
    check(len(lines) >= SERIES_COUNT, "series entry count at least the d8 prefix", str(len(lines)))
    check(prefix_sha == SERIES_PREFIX_SHA256, "series d8 prefix sha256", prefix_sha)
    if len(lines) < SERIES_COUNT or prefix_sha != SERIES_PREFIX_SHA256:
        refuse("series d8 prefix bytes differ from the d8 build")
    lines = prefix
    check(series_fingerprint(lines, patches) == SERIES_NAMES_SIZES,
          "series names+sizes fingerprint", series_fingerprint(lines, patches))
    if len(lines) != SERIES_COUNT or series_fingerprint(lines, patches) != SERIES_NAMES_SIZES:
        refuse("series identity mismatch")

    patch_hashes: dict[str, str] = {}
    for name in lines:
        p = patches / name
        if not p.is_file():
            refuse(f"series patch is missing: {name}")
        actual = sha256(p)
        patch_hashes[name] = actual
        expected = frozen_map.get(f"patches/xnu/{name}")
        if expected is None:
            refuse(f"series patch is absent from frozen-before: {name}")
        if actual != expected:
            refuse(f"series patch bytes differ from frozen-before: {name}")
    check(all(n in patch_hashes for n in PATCH_NAMES), "bound patches present")

    log = artifact / "logs/kernel.log"
    require_file(log, "kernel.log")
    log_text = log.read_text(encoding="utf-8", errors="strict")
    positions = []
    for name in PATCH_NAMES:
        needle = f"== kernel: patch {name}"
        check(needle in log_text, f"kernel.log applied {name}")
        positions.append(log_text.find(needle))
    check(positions == sorted(positions), "bound patches appear in series order")
    if any(p < 0 for p in positions):
        refuse("kernel.log does not show all bound patches")
    return lines, patch_hashes


def run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None,
        timeout: int = 300) -> subprocess.CompletedProcess:
    e = os.environ.copy()
    e.update({"LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1",
              "GIT_CONFIG_GLOBAL": os.devnull, "HOME": str(cwd)})
    if env:
        e.update(env)
    return subprocess.run(cmd, cwd=cwd, env=e, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=timeout)


def reconstruct(work: Path, patches: Path, lines: list[str]) -> Path:
    source = work / "source"
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


def compile_harness(work: Path, qbt: Path, fixture: Path, tag: str) -> Path:
    out = work / f"harness-{tag}"
    cmd = [
        "gcc", "-std=gnu11", "-O0", "-g", "-fno-strict-aliasing",
        "-Wno-unused-parameter", "-Wno-unused-function", "-Wno-sign-compare",
        "-Wno-missing-field-initializers",
        "-I", str(qbt / "shim"), "-I", str(qbt),
        "-include", "qbt_linux.h",
        str(fixture), str(SUPPORT), str(qbt / "qbt_core.c"),
        str(qbt / "btqca.c"), "-o", str(out),
    ]
    r = run(cmd, work)
    if r.returncode != 0:
        refuse(f"gcc failed for {tag}:\n{r.stderr}")
    return out


def execute(binary: Path, scenario: str, work: Path) -> tuple[int, str]:
    r = run([str(binary), scenario], work, timeout=120)
    return r.returncode, r.stdout + r.stderr


# (label, scenario, old text, new text) -- each mutation must turn the named
# scenario red.  These are deliberately small synthetic-input or assertion
# twins, not changes to the reconstructed product sources.
MUTATIONS = [
    ("adapter_status_status_zero", "adapter_status",
     "F.force_status = 0xff;", "F.force_status = 0x00;"),
    ("adapter_short_not_short", "adapter_short",
     "F.force_short = 1;", "F.force_short = 0;"),
    ("adapter_timeout_answers", "adapter_timeout",
     "F.no_response = 1;", "F.no_response = 0;"),
    ("adapter_tlv_status_zero", "adapter_tlv_status",
     "F.force_tlv_status = 1;", "F.force_tlv_status = 0;"),
    ("adapter_late_early", "adapter_late",
     "F.late_at = (int)QBT_COMMAND_TIMEOUT;", "F.late_at = 0;"),
    ("adapter_early_disabled", "adapter_early",
     "F.early_response = 1;", "F.early_response = 0;"),
    ("download_one_segment", "download_success",
     "make_patch(0, 500);", "make_patch(0, 100);"),
    ("download_no_fallback", "download_fallback_success",
     "F.fail_tlv_at = 5;", "F.fail_tlv_at = 0;"),
    ("fallback_failure_succeeds", "download_fallback_failure",
     "F.drop_tlv_at = 6;", "F.drop_tlv_at = 0;"),
    ("nvm_primary_present", "download_nvm_missing",
     "F.fw_nvm_primary_missing = 1;", "F.fw_nvm_primary_missing = 0;"),
    ("patch_primary_present", "download_patch_fallback",
     "F.fw_patch_primary_missing = 1;", "F.fw_patch_primary_missing = 0;"),
    ("skip_mode_sync", "download_skip_mode",
     "make_patch(1, 500);", "make_patch(0, 500);"),
    ("boot_success_speed", "boot_success",
     "qbt_boot(F.q, 115200, addr)", "qbt_boot(F.q, 9600, addr)"),
    ("boot_failure_succeeds", "boot_failure_cleanup",
     "F.drop_tlv_at = 6;", "F.drop_tlv_at = 0;"),
    ("boot_no_fallback", "boot_fallback_success",
     "F.fail_tlv_at = 5;", "F.fail_tlv_at = 0;"),
    ("sent_acks_reset", "download_fallback_success",
     "        send_tlv(status);\n        return;",
     "        send_tlv(status);\n        if (status) { F.q->stats.tlv_sent = 0; F.q->stats.tlv_acks = 0; }\n        return;"),
]


MUTATIONS += [
    ("version_mismatch_full", "adapter_version_mismatch",
     "F.short_version = 1;", "F.short_version = 0;"),
    ("version_overlong_exact", "adapter_version_overlong",
     "F.long_version = 1;", "F.long_version = 0;"),
    ("alt_already_bin_name", "download_alt_already_bin",
     "\"synthetic.bin\"", "\"synthetic.tlv\""),
    ("alt_name_bin", "download_alt_name",
     "\"synthetic.tlv\"", "\"synthetic.bin\""),
    ("boot_patch_fail_fallback", "boot_patch_fail",
     "F.fw_patch_fallback_missing = 1;", "F.fw_patch_fallback_missing = 0;"),
    ("boot_bdaddr_fail_ok", "boot_bdaddr_fail",
     "F.fail_bdaddr = 1;", "F.fail_bdaddr = 0;"),
    ("boot_reset_fail_ok", "boot_reset_fail",
     "F.fail_reset = 1;", "F.fail_reset = 0;"),
    ("firmware_release_count", "download_success",
     "F.fw_puts++;", "F.fw_puts += 0;"),
]

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="d8 adapter/fallback host harness")
    parser.add_argument("--artifact", default=str(DEFAULT_ARTIFACT))
    parser.add_argument("--patch-dir", default=str(ROOT / "patches/xnu"))
    parser.add_argument("--work-dir", default="")
    parser.add_argument("--scenario", default="")
    parser.add_argument("--no-mutations", action="store_true")
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args(argv)

    print("HOST-ONLY: adapter/download/fallback software path on frozen d8 sources")
    print("NOT RUN: controller, UART, DMA, IBS, hardware, d8 timeline replay")
    print("test-bt-d8-adapter-host")

    artifact = Path(args.artifact)
    patches = Path(args.patch_dir)
    if not artifact.is_dir():
        refuse(f"artifact directory is missing: {artifact}")
    lines, _ = validate_inputs(artifact, patches)

    work = Path(args.work_dir) if args.work_dir else Path(tempfile.mkdtemp(prefix="bt-d8-adapter-"))
    work.mkdir(parents=True, exist_ok=True)
    print(f"work: {work}")
    try:
        qbt = reconstruct(work, patches, lines)
        fixture_src = HARNESS.read_text(encoding="utf-8")
        if "HOST-ONLY" not in fixture_src or "synthetic" not in fixture_src:
            refuse("fixture lost its host-only/synthetic boundary")
        fixture = work / "harness.c"
        fixture.write_text(fixture_src, encoding="utf-8")
        binary = compile_harness(work, qbt, fixture, "base")

        # both the "all" table and the argv dispatch table list every
        # scenario; keep one execution and the table's declaration order.
        names = list(dict.fromkeys(re.findall(r'\{"([a-z_]+)", scenario_', fixture_src)))
        if args.scenario:
            names = [args.scenario] if args.scenario in names else refuse(
                f"unknown scenario {args.scenario}")
        for name in names:
            rc, out = execute(binary, name, work)
            check(rc == 0, f"scenario {name} rc", out[-3000:])
            if rc == 0:
                check(f"RESULT {name} PASS failures=0" in out,
                      f"scenario {name} self-check", out[-1000:])
            else:
                print(out[-4000:])

        if not args.no_mutations:
            print("negative controls (each must really go red)")
            for label, scenario, old, new in MUTATIONS:
                if scenario not in names:
                    continue
                if fixture_src.count(old) < 1:
                    check(False, f"mutation {label} anchor", old[:60])
                    continue
                mutated = fixture_src.replace(old, new)
                mf = work / f"mutant-{label}.c"
                mf.write_text(mutated, encoding="utf-8")
                mb = compile_harness(work, qbt, mf, f"mut-{label}")
                rc, out = execute(mb, scenario, work)
                red = rc != 0 and ("FAIL" in out or "failures=" in out)
                if red:
                    red_line = next((ln.strip() for ln in out.splitlines()
                                     if ln.strip().startswith("FAIL")), "rc != 0")
                    print(f"  red: mutation {label}: {red_line}")
                check(red, f"mutation {label} turns {scenario} red", out[-800:])

        print(f"\nTESTS {'OK' if failures == 0 else 'FAILED'}: {cases} case(s), {failures} failure(s)")
        return 0 if failures == 0 else 1
    finally:
        if args.keep:
            print(f"kept work dir: {work}")
        else:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())