#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Run frozen d8 QBT C source with fake platform callbacks, never a device.

Requires explicit external inputs and an external output directory. This compiles
only a host test executable. It does not build XNU or claim full firmware, UART,
controller, boot, or flash-gate coverage. See the printed NOT RUN list.
"""
import argparse
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import sys

PATCHES = {
    "0500-k60-bt-qbt-new-files.patch": "4e6f58d96f1ba06cd8d440feaa7546e3df05519631a8550b96a6441ba69bc0b0",
    "0514-k60-bt-boot-observability.patch": "e6d5296b0b9e7e137c0f12271670aa485ebfa4e649b090101e258faef418a73c",
    "0515-k60-bt-tlv-counters.patch": "120c4d57d1bf72bdee18770a520367bd68d46c1c96ffb185c5bbf51ec46c4cd6",
}
FROZEN_SHA256 = "ec0bce53352203a5e430ce1ac7f80ae407ed1ba3ba208286dc665ddfe741f4e9"
ROOT = Path(__file__).resolve().parents[2]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def new_file(patch, name):
    """Extract an entire new-file hunk, rejecting context/deletion/duplicates."""
    marker = "+++ b/" + name + "\n"
    require(patch.count(marker) == 1, "missing/duplicate new file: " + name)
    section = patch.split(marker, 1)[1]
    section = re.split(r"(?m)^(?:--- |diff --git )", section, maxsplit=1)[0]
    lines = section.splitlines(keepends=True)
    require(lines and re.fullmatch(r"@@ -0,0 \+1,\d+ @@\n", lines[0]),
            "not a new-file hunk: " + name)
    require(all(line.startswith("+") for line in lines[1:]), "non-addition in " + name)
    return "".join(line[1:] for line in lines[1:])


def hunks(patch, name):
    """Read exact before/after text. Hunk line offsets are not trusted."""
    marker = "+++ b/" + name + "\n"
    require(patch.count(marker) == 1, "missing/duplicate patch file: " + name)
    section = patch.split(marker, 1)[1].split("diff --git ", 1)[0]
    result = []
    before, after = None, None
    for line in section.splitlines(keepends=True):
        if line.startswith("@@ "):
            if before is not None:
                result.append(("".join(before), "".join(after)))
            before, after = [], []
        elif before is not None:
            require(line[:1] in (" ", "+", "-"), "unsupported patch line")
            if line[0] in " -":
                before.append(line[1:])
            if line[0] in " +":
                after.append(line[1:])
    if before is not None:
        result.append(("".join(before), "".join(after)))
    require(result, "no hunks in " + name)
    return result


def apply_exact(source, changes):
    for before, after in changes:
        require(source.count(before) == 1, "hunk context is not unique/exact")
        source = source.replace(before, after, 1)
    return source


def verify_patch(name, raw, recorded):
    expected = PATCHES[name]
    require(recorded.get("patches/xnu/" + name) == expected, "d8 frozen record differs: " + name)
    require(digest(raw) == expected, "unknown patch SHA256: " + name)


def guard_checks(patch_dir, frozen, recorded, script):
    """Exercise rejection paths with memory mutations, without editing inputs."""
    checks = 0

    def rejected(action, message):
        nonlocal checks
        try:
            action()
        except ValueError as error:
            require(message in str(error), "wrong guard failure: " + str(error))
            checks += 1
            return
        raise ValueError("guard accepted invalid input: " + message)

    require(digest(frozen) == FROZEN_SHA256, "unknown d8 frozen-before SHA256")
    rejected(lambda: require(digest(frozen + b"x") == FROZEN_SHA256,
                             "unknown d8 frozen-before SHA256"), "unknown d8 frozen")
    for name in PATCHES:
        raw = (patch_dir / name).read_bytes()
        verify_patch(name, raw, recorded)
        rejected(lambda: verify_patch(name, raw + b"x", recorded), "unknown patch SHA256")
        rejected(lambda: verify_patch(name, raw, {}), "d8 frozen record differs")
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
    require(result.returncode == 2 and "required" in result.stderr,
            "missing explicit CLI inputs were not rejected")
    checks += 1
    print(f"PASS: {checks} source/input rejection guards", flush=True)


def prepare(patches, output):
    core_name = "bsd/dev/qbt/qbt_core.c"
    internal_name = "bsd/dev/qbt/qbt_internal.h"
    initial = patches["0500-k60-bt-qbt-new-files.patch"]
    observe = patches["0514-k60-bt-boot-observability.patch"]
    counters = patches["0515-k60-bt-tlv-counters.patch"]
    core = apply_exact(new_file(initial, core_name), hunks(observe, core_name))
    internal = apply_exact(new_file(initial, internal_name), hunks(observe, internal_name))
    # Only this file's actual 0515 segment block and summary block are wrapped.
    # qca_tlv_send_segment is a fake boundary, so this is observation coverage,
    # not execution of qca_download_firmware or its fallback/reset path.
    changes = hunks(counters, "bsd/dev/qbt/btqca.c")
    segment = changes[1][1]
    segment = segment[segment.index("\t\t{\n"):segment.index("\t\tif (ret)")]
    summary = changes[2][1].split("out:\n", 1)[1].split("\tvfree(data);", 1)[0]
    wrapper = (
        "struct hci_dev { struct qbt *q; };\n"
        "struct timing_config { int dnld_mode, type; };\n"
        "static int qca_tlv_send_segment(struct hci_dev *, int, const unsigned char *, int, int);\n"
        "static int measured_segment(struct hci_dev *hdev, struct timing_config *config, "
        "unsigned *count) {\n"
        "    int ret, segsize = 243, soc_type = 0;\n"
        "    const unsigned char *segment = NULL; unsigned segs = *count;\n"
        + segment + "    *count = segs; return ret;\n}\n"
        "static void measured_summary(struct hci_dev *hdev, struct timing_config *config, "
        "unsigned segs, int ret) {\n" + summary + "}\n"
    )
    for name, content in (("qbt.h", new_file(initial, "bsd/dev/qbt/qbt.h")),
                          ("qbt_internal.h", internal), ("qbt_core.c", core),
                          ("qbt_observation.inc", wrapper)):
        (output / name).write_text(content, encoding="utf-8")
    print("SOURCE_C: complete qbt_core.c + exact 0514 core/internal hunks", flush=True)
    print("SOURCE_C: exact 0515 segment/summary blocks; fake send boundary", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--patch-dir", type=Path, required=True)
    parser.add_argument("--frozen-before", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--cc", default="cc")
    args = parser.parse_args()
    patch_dir, output = args.patch_dir.resolve(), args.work_dir.resolve()
    require(not output.is_relative_to(ROOT), "--work-dir must be outside this repository")
    source_repo = patch_dir.parent.parent
    require(not output.is_relative_to(source_repo), "--work-dir must be outside the source repository")
    require(shutil.which(args.cc) is not None, "C compiler unavailable: " + args.cc)
    frozen = args.frozen_before.read_bytes()
    require(digest(frozen) == FROZEN_SHA256, "unknown d8 frozen-before SHA256")
    recorded = {}
    for line in frozen.decode("utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        require(match is not None, "invalid frozen input line")
        sha, name = match.groups()
        require(name not in recorded, "duplicate frozen input: " + name)
        recorded[name] = sha
    patches = {}
    for name, expected in PATCHES.items():
        raw = (patch_dir / name).read_bytes()
        verify_patch(name, raw, recorded)
        patches[name] = raw.decode("utf-8")
        print("SOURCE_MATCH " + name + " " + expected, flush=True)
    guard_checks(patch_dir, frozen, recorded, Path(__file__).resolve())
    output.mkdir(parents=True, exist_ok=True)
    prepare(patches, output)
    executable = output / "bt-d8-timing-harness"
    fixture = ROOT / "scripts/tests/fixtures/bt-d8-timing-harness.c"
    subprocess.run([args.cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O0", "-g",
                    "-I", str(output), str(fixture), "-o", str(executable)], check=True)
    subprocess.run([str(executable)], check=True, timeout=30)
    print("NOT RUN: full QCA firmware download/fallback, qbt_boot/reset lifecycle, Linux adapter")
    print("NOT RUN: controller/UART/DMA/IBS hardware timing, XNU build, boot, flash gates")
    print("HOST_ONLY: callbacks and event arrival times are deterministic test inputs, not d8 replay")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print("FAIL: " + str(error), file=sys.stderr)
        sys.exit(1)
