#!/usr/bin/env python3
"""Executable criteria for the iOS 27 cellular eight-step fragment.

Every step prints one command, the exact reading expected from it, the
precedent that lets us use the mechanism, a conclusion grade, and a negative
dry-run that must fail.  The script never builds, boots, flashes, or writes the
shared trees; the only writes are temporary test copies under the scratch
directory.

Exit codes: 0 PASS, 1 FAIL, 2 PENDING (a required artifact is absent).
--mutate is a meta-check: it feeds the deliberately broken input and returns
1 when the criterion catches it.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


REPO = Path(__file__).resolve().parent.parent
SCRATCH = Path(os.environ.get("K60_SCRATCH", r"E:/k60-work/scratch"))
XNU27_TREE = os.environ.get(
    "K60_XNU27_TREE", "/opt/k60/trees/ios27-out/feeds/xnu-3199e8bc"
)
PATCH_DIR = Path(
    os.environ.get("K60_XNU27_PATCHES", r"E:/k60-work/wt-pitfall/patches/xnu-12377")
)
FIRMWARE = Path(os.environ.get("K60_MODEM_FIRMWARE", r"E:/k60-work/firmware/modem"))
COMPONENTS = Path(os.environ.get("K60_COMPONENTS", r"E:/hackios/UniXNU/components.toml"))
BOARD = Path(os.environ.get("K60_BOARD", r"E:/hackios/k60-gates/board.toml"))
UNIXNU = Path(os.environ.get("K60_UNIXNU", r"E:/hackios/UniXNU"))
REFERENCE_MPSS = Path(
    os.environ.get(
        "K60_REFERENCE_MPSS",
        r"E:/k60-work/references/phk110-port/drivers/modem/hakios.mpss.c",
    )
)
PRECEDENT = Path(
    os.environ.get(
        "K60_PRECEDENT",
        r"E:/hackios/k60-gates/docs/research/ios27/PRECEDENT-REQUIRED.md",
    )
)

STEPS = [
    "same_model",
    "official",
    "decompile",
    "wide",
    "plan",
    "deep",
    "verify",
]

PATCHES_MUST_APPLY = [
    "0626-k60-modem-image.patch",
    "0627-k60-modem-qrtr.patch",
    "0628-k60-ipa.patch",
    "0630-k60-smem.patch",
]
PATCH_MUST_WAIT = "0629-kern-exec-call-sites.patch"


@dataclass
class Result:
    step: str
    ok: bool | None
    reading: str
    cmd: str
    expect: str
    negative: str
    neg_expect: str
    precedent: str
    conclusion: str
    unknown: str
    detail: str


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError:
        return b""


def run(argv: list[str], timeout: int = 240, cwd: Path | None = None):
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except FileNotFoundError as exc:
        return 127, "", str(exc)
    except subprocess.TimeoutExpired:
        return 124, "", "timeout after %d s" % timeout


def run_py(script: Path, args: list[str] | None = None, timeout: int = 300):
    return run([sys.executable, str(script), *(args or [])], timeout=timeout, cwd=REPO)


def as_wsl(path: Path) -> str:
    text = str(path).replace("\\", "/")
    match = re.match(r"^([A-Za-z]):/(.*)$", text)
    if match:
        return "/mnt/%s/%s" % (match.group(1).lower(), match.group(2))
    return text


def wsl_run(args: list[str], timeout: int = 240):
    if os.name == "nt":
        return run(["wsl.exe", "--", *args], timeout=timeout)
    return run(args, timeout=timeout)


def tail(text: str, limit: int = 900) -> str:
    text = " ".join(text.split())
    return text[-limit:] if len(text) > limit else text


def missing_needles(path: Path, needles: list[str]) -> list[str]:
    text = read_text(path)
    if not text:
        return ["missing file %s" % path]
    return [needle for needle in needles if needle not in text]


def make_result(
    step: str,
    ok: bool | None,
    reading: str,
    detail: str,
    precedent: str,
    conclusion: str,
    unknown: str,
    mutate: bool,
) -> Result:
    cmd = "python3 scripts/check-cellular-27-criteria.py --step %s" % step
    negative = cmd + " --mutate"
    expect = "RESULT: PASS; READING: %s" % reading
    neg_expect = "RESULT: FAIL (mutation caught); %s" % detail
    return Result(
        step=step,
        ok=ok,
        reading=reading,
        cmd=cmd,
        expect=expect,
        negative=negative,
        neg_expect=neg_expect,
        precedent=precedent,
        conclusion=conclusion,
        unknown=unknown,
        detail=detail,
    )


def check_same_model(mutate: bool) -> Result:
    table = REPO / "drivers/PongCellular/pong_modem_table.h"
    image_h = REPO / "drivers/PongCellular/K60ModemImage.h"
    adsp_c = REPO / "drivers/PongPower/K60AdspImage.c"
    adsp_doc = REPO / "docs/research/audio/ADSP-PAS1.md"
    flight = REPO / "docs/research/cellular/19-MODEM-BRINGUP-FLIGHT.md"
    anchors = [
        (table, [
            "#define K60_MODEM_BASE 0x8bc00000UL",
            "#define K60_MODEM_WINDOW 0x13200000UL",
            "#define K60_MODEM_SEGMENTS 30",
        ]),
        (image_h, ["K60ModemSegment", "k60_modem_plan", "k60_modem_copy"]),
        (adsp_c, ["k60_adsp_plan", "k60_adsp_copy", "K60AdspOutsideWindow"]),
        (adsp_doc, [
            "PAS_AUTH_AND_RESET",
            "PAS_INIT_IMAGE",
            "PAS_MEM_SETUP",
            "0x86300000",
        ]),
        (flight, ["pong", "0x8bc00000", "0x13200000", "5,884"]),
        (REFERENCE_MPSS, ["PAS_MPSS_DEFAULT", "0x8b800000"]),
    ]
    broken = []
    for path, needles in anchors:
        broken.extend(missing_needles(path, needles))
    if mutate:
        # Change the one constant the loader table is built around.
        text = read_text(table)
        mutated = text.replace(
            "#define K60_MODEM_BASE 0x8bc00000UL",
            "#define K60_MODEM_BASE 0x00000000UL",
        )
        caught = mutated != text and "#define K60_MODEM_BASE 0x8bc00000UL" not in mutated
        ok = not caught
        return make_result(
            "same_model",
            ok,
            "K60_MODEM_BASE=0x00000000UL (mutated)",
            "missing K60_MODEM_BASE 0x8bc00000UL",
            "pong（Nothing Phone 2，SM8475/X65，Darwin24）PAS4 顺序见 docs/research/cellular/19-MODEM-BRINGUP-FLIGHT.md:15-19；同 SoC 参考实现见 E:/k60-work/references/phk110-port/drivers/modem/hakios.mpss.c:1047-1051",
            "有证据",
            "无",
            mutate,
        )
    ok = not broken
    reading = (
        "K60_MODEM_SEGMENTS=30 K60_MODEM_BASE=0x8bc00000UL "
        "K60_MODEM_WINDOW=0x13200000UL anchors=%d/%d"
        % (sum(len(n) for _, n in anchors) - len(broken), sum(len(n) for _, n in anchors))
    )
    return make_result(
        "same_model",
        ok,
        reading,
        "missing " + "; ".join(broken[:4]) if broken else "all anchors present",
        "pong（Nothing Phone 2，SM8475/X65，Darwin24）PAS4 顺序见 docs/research/cellular/19-MODEM-BRINGUP-FLIGHT.md:15-19；同 SoC 参考实现见 E:/k60-work/references/phk110-port/drivers/modem/hakios.mpss.c:1047-1051",
        "有证据",
        "无",
        mutate,
    )


def check_official(mutate: bool) -> Result:
    baseband = UNIXNU / "docs/zh/porting/baseband.md"
    userdata = UNIXNU / "docs/zh/guide/userdata.md"
    concepts = UNIXNU / "docs/zh/concepts/userdata.md"
    qcom = UNIXNU / "docs/zh/drivers/qcom-baseband.md"
    anchors = [
        (baseband, [
            "原厂 FSG/EFS/NV",
            "核对设备保存的摘要",
            "记录固件来源、哈希和打包路径",
            "EFS 写入仍保存在内存中，重启后重新加载原厂数据",
        ]),
        (userdata, [
            "Data 卷来自负载中的 Data ramdisk 种子",
            "卷 UUID 保留，seed 大小变化会改变持久化身份并初始化新的 Data store",
        ]),
        (concepts, ["sheng-log-reserve", "sheng-data-persist=2"]),
        (qcom, ["板级提供", "GLINK/QRTR", "rmtfs", "IPA/GSI/QMAP"]),
    ]
    broken = []
    for path, needles in anchors:
        broken.extend(missing_needles(path, needles))
    if mutate:
        text = read_text(baseband)
        mutated = text.replace(
            "EFS 写入仍保存在内存中，重启后重新加载原厂数据。",
            "EFS 写入会持久化。",
        )
        caught = mutated != text and "EFS 写入仍保存在内存中" not in mutated
        ok = not caught
        return make_result(
            "official",
            ok,
            "baseband EFS memory sentence removed (mutated)",
            "missing EFS 写入仍保存在内存中，重启后重新加载原厂数据",
            "官方页 E:/hackios/UniXNU/docs/zh/porting/baseband.md:22-31 与 :56；guide/userdata.md:60-85；concepts/userdata.md:68-70；drivers/qcom-baseband.md:7-9",
            "有证据",
            "27 proprietary-files.txt 仍缺 modem/fsg/fsc/modemst 条目；F3 前必须补",
            mutate,
        )
    ok = not broken
    reading = "anchors=%d/%d baseband=22-31,25,29,56 userdata=60-85,82 concepts=68-70 qcom=7-9" % (
        sum(len(n) for _, n in anchors) - len(broken),
        sum(len(n) for _, n in anchors),
    )
    return make_result(
        "official",
        ok,
        reading,
        "missing " + "; ".join(broken[:4]) if broken else "all official sentences present",
        "官方页 E:/hackios/UniXNU/docs/zh/porting/baseband.md:22-31 与 :56；guide/userdata.md:60-85；concepts/userdata.md:68-70；drivers/qcom-baseband.md:7-9",
        "有证据",
        "27 proprietary-files.txt 仍缺 modem/fsg/fsc/modemst 条目；F3 前必须补",
        mutate,
    )


def image_test(firmware: Path):
    script = REPO / "scripts/tests/test-k60-modem-image.py"
    return run_py(script, [str(firmware)], timeout=400)


def check_decompile(mutate: bool) -> Result:
    if not FIRMWARE.is_dir():
        return make_result(
            "decompile", None, "firmware dir absent: %s" % FIRMWARE,
            "firmware dir absent", "离线镜像表检查，不涉及启动机制", "不知道", "无固件目录", mutate,
        )
    if mutate:
        tmp = Path(tempfile.mkdtemp(prefix="k60-decompile-", dir=str(SCRATCH)))
        try:
            for source in FIRMWARE.iterdir():
                if not source.is_file():
                    continue
                target = tmp / source.name
                if source.name in ("modem.mdt", "modem.mdt.bin"):
                    shutil.copy2(source, target)
                else:
                    try:
                        os.link(source, target)
                    except OSError:
                        shutil.copy2(source, target)
            changed = []
            for name in ("modem.mdt", "modem.mdt.bin"):
                path = tmp / name
                if not path.is_file():
                    continue
                data = bytearray(read_bytes(path))
                if len(data) >= 46:
                    data[44:46] = (31).to_bytes(2, "little")
                    path.write_bytes(data)
                    changed.append(name)
            rc, out, err = image_test(tmp)
            combined = out + "\n" + err
            ok = rc == 0 and "TESTS OK" in out
            detail = "e_phnum is 31, expected 32" if "e_phnum" in combined else tail(combined)
            return make_result(
                "decompile", ok, "mutated %s e_phnum=31 rc=%d" % (",".join(changed) or "none", rc),
                detail, "离线镜像表检查，不涉及启动机制", "有证据", "无", mutate,
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    rc, out, err = image_test(FIRMWARE)
    combined = out + "\n" + err
    ok = rc == 0 and "TESTS OK 30 segments" in out
    line = next((x for x in combined.splitlines() if "TESTS OK" in x or "e_phnum" in x), tail(combined, 300))
    return make_result(
        "decompile", ok, line.strip() or "rc=%d" % rc,
        "expected TESTS OK 30 segments" if not ok else "30 PT_LOAD, 27 file segments, table and patch agree",
        "离线镜像表检查，不涉及启动机制", "有证据", "GLINK/QRTR 服务表仍未反汇编", mutate,
    )


def component_block(text: str):
    blocks = re.findall(r"(?ms)^\[\[component\]\]\n(.*?)(?=^\[\[component\]\]|\Z)", text)
    for block in blocks:
        if re.search(r'^id = "QcomBaseband"$', block, re.M):
            return block
    return ""


def board_include(text: str) -> list[str]:
    match = re.search(
        r'(?ms)^\[os_overrides\."ios-27\.0\.1-24A446"\.components\]\n(.*?)(?=^\[|\Z)',
        text,
    )
    if not match:
        return []
    include = re.search(r"^include\s*=\s*\[(.*?)\]", match.group(1), re.M | re.S)
    if not include:
        return []
    return re.findall(r'"([^"]+)"', include.group(1))


def check_wide(mutate: bool) -> Result:
    components = read_text(COMPONENTS)
    board = read_text(BOARD)
    block = component_block(components)
    if not block:
        return make_result(
            "wide", None, "QcomBaseband block absent",
            "components.toml has no QcomBaseband block", "官方组件目录；本项只判断能否复用",
            "不知道", "无组件目录", mutate,
        )
    verified = re.search(r"^verified_devices\s*=\s*\[(.*?)\]", block, re.M | re.S)
    verified_names = re.findall(r'"([^"]+)"', verified.group(1)) if verified else []
    includes = board_include(board)
    qcom_in_board = "QcomBaseband" in includes
    if mutate:
        mutated = block.replace(
            "verified_devices = []",
            'verified_devices = ["pong"]',
            1,
        )
        caught = verified_names == [] and "pong" in mutated
        ok = not caught
        return make_result(
            "wide", ok, "verified_devices=[\"pong\"] (mutated)",
            "verified_devices is not empty",
            "官方组件目录是选型先例，不是本板可用性先例；QcomBaseband 的 verified_devices 为空",
            "有证据", "QcomBaseband 在 K60/同 SoC 上无已验证设备", mutate,
        )
    ok = verified_names == [] and not qcom_in_board
    reading = (
        "QcomBaseband=present verified_devices=%d board_include=%s QcomBaseband=absent"
        % (len(verified_names), ",".join(includes) or "none")
    )
    return make_result(
        "wide", ok, reading,
        "verified_devices empty and QcomBaseband absent from the 27 include" if ok else "catalog or board predicate failed",
        "官方组件目录是选型先例，不是本板可用性先例；QcomBaseband 的 verified_devices 为空",
        "有证据", "QcomBaseband 在 K60/同 SoC 上无已验证设备", mutate,
    )


def check_plan(mutate: bool) -> Result:
    if PATCH_DIR.is_dir() is False:
        return make_result(
            "plan", None, "patch dir absent: %s" % PATCH_DIR,
            "patch dir absent", "27 树 apply 实测；无设备机制", "不知道", "无补丁目录", mutate,
        )
    tree_rc, _, tree_err = wsl_run(["test", "-d", XNU27_TREE])
    if tree_rc != 0:
        return make_result(
            "plan", None, "27 tree absent or WSL unavailable: %s" % XNU27_TREE,
            "tree check rc=%d %s" % (tree_rc, tail(tree_err)),
            "27 树 apply 实测；无设备机制", "不知道", "27 树不可达", mutate,
        )
    if mutate:
        source = PATCH_DIR / PATCHES_MUST_APPLY[0]
        text = read_text(source)
        mutated = re.sub(r"@@ -0,0 \+1,\d+ @@", "@@ -0,0 +1,999 @@", text, count=1)
        if mutated == text:
            mutated = text.replace("diff --git", "diff --git-corrupt", 1)
        tmp = Path(tempfile.mkdtemp(prefix="k60-plan-", dir=str(SCRATCH)))
        try:
            patch = tmp / source.name
            patch.write_text(mutated, encoding="utf-8")
            rc, out, err = wsl_run(
                ["git", "-C", XNU27_TREE, "apply", "--check", as_wsl(patch)], timeout=120
            )
            ok = rc == 0
            return make_result(
                "plan", ok, "mutated 0626 apply rc=%d" % rc,
                "corrupted patch applies rc=%d" % rc if ok else "corrupted patch rejected rc=%d" % rc,
                "27 树 apply 实测；无设备机制", "有证据", "27 data-mount 无已到 bsd_init 的同族实现", mutate,
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    results = {}
    detail = []
    for name in PATCHES_MUST_APPLY + [PATCH_MUST_WAIT]:
        path = PATCH_DIR / name
        if not path.is_file():
            return make_result(
                "plan", None, "missing patch %s" % name,
                "missing patch %s" % name, "27 树 apply 实测；无设备机制", "不知道", "缺补丁", mutate,
            )
        rc, out, err = wsl_run(
            ["git", "-C", XNU27_TREE, "apply", "--check", as_wsl(path)], timeout=120
        )
        results[name] = rc
        detail.append("%s=%d" % (name.split("-")[0], rc))
    anchor_rc, _, _ = wsl_run(
        ["git", "-C", XNU27_TREE, "grep", "-c", "native_owner_data_stage", "--", "."],
        timeout=120,
    )
    ok = all(results[name] == 0 for name in PATCHES_MUST_APPLY)
    ok = ok and results[PATCH_MUST_WAIT] == 1 and anchor_rc == 1
    reading = "apply " + " ".join(detail) + " anchor_grep=%d" % anchor_rc
    return make_result(
        "plan", ok, reading,
        "four patches apply, 0629 waits for the data-mount anchor" if ok else "unexpected apply result",
        "27 树 apply 实测；无设备机制", "有证据", "27 data-mount 无已到 bsd_init 的同族实现", mutate,
    )


def wsl_repo() -> str:
    return as_wsl(REPO)


def check_deep(mutate: bool) -> Result:
    gcc_rc, _, gcc_err = wsl_run(["gcc", "--version"])
    if gcc_rc != 0:
        return make_result(
            "deep", None, "gcc unavailable in WSL",
            "gcc check rc=%d %s" % (gcc_rc, tail(gcc_err)),
            "pong PAS4 顺序见 docs/research/cellular/19-MODEM-BRINGUP-FLIGHT.md:15-19；同 SoC 参考见 hakios.mpss.c:1047-1051",
            "不知道", "无 WSL gcc", mutate,
        )
    repo = wsl_repo()
    tmp = Path(tempfile.mkdtemp(prefix="k60-deep-", dir=str(SCRATCH)))
    try:
        loader_exe = "/tmp/k60-criteria-loader-%d" % os.getpid()
        loader_src = repo + "/scripts/tests/test-k60-modem-loader.c"
        loader_impl = repo + "/drivers/PongCellular/K60ModemImage.c"
        include = repo + "/drivers/PongCellular"
        rc, out, err = wsl_run(
            ["gcc", "-O1", "-Wall", "-Wextra", "-Werror", "-I", include, "-o", loader_exe, loader_src, loader_impl],
            timeout=240,
        )
        if rc != 0:
            return make_result(
                "deep", False, "loader compile rc=%d" % rc,
                "loader compile failed: " + tail(out + err),
                "pong PAS4 顺序见 docs/research/cellular/19-MODEM-BRINGUP-FLIGHT.md:15-19；同 SoC 参考见 hakios.mpss.c:1047-1051",
                "有证据", "真实固件服务表未反汇编", mutate,
            )
        run_rc, run_out, run_err = wsl_run([loader_exe])
        loader_ok = run_rc == 0 and "TESTS OK 7" in run_out
        if mutate:
            src = REPO / "drivers/PongCellular/K60ModemQrtr.c"
            header = REPO / "drivers/PongCellular/K60ModemQrtr.h"
            test = REPO / "scripts/tests/test-k60-modem-qrtr.c"
            shutil.copy2(src, tmp / src.name)
            shutil.copy2(header, tmp / header.name)
            shutil.copy2(test, tmp / test.name)
            htext = read_text(tmp / header.name).replace(
                "#define K60_QRTR_VERSION        1u",
                "#define K60_QRTR_VERSION        2u",
                1,
            )
            (tmp / header.name).write_text(htext, encoding="utf-8")
            exe = "/tmp/k60-criteria-qrtr-mut-%d" % os.getpid()
            rc2, out2, err2 = wsl_run(
                ["gcc", "-O1", "-Wall", "-Wextra", "-Werror", "-I", as_wsl(tmp), "-o", exe,
                 as_wsl(tmp / test.name), as_wsl(tmp / src.name)],
                timeout=240,
            )
            run2_rc, run2_out, run2_err = wsl_run([exe]) if rc2 == 0 else (rc2, "", "")
            ok = run2_rc == 0 and "TESTS OK" in run2_out
            return make_result(
                "deep", ok, "loader=TESTS OK 7 qrtr_mutated rc=%d" % run2_rc,
                "QRTR version mismatch" if not ok else "QRTR test still passes after mutation",
                "pong PAS4 顺序见 docs/research/cellular/19-MODEM-BRINGUP-FLIGHT.md:15-19；同 SoC 参考见 hakios.mpss.c:1047-1051",
                "有证据", "真实固件服务表未反汇编", mutate,
            )
        qrtr_exe = "/tmp/k60-criteria-qrtr-%d" % os.getpid()
        qsrc = repo + "/drivers/PongCellular/K60ModemQrtr.c"
        qtest = repo + "/scripts/tests/test-k60-modem-qrtr.c"
        rc3, out3, err3 = wsl_run(
            ["gcc", "-O1", "-Wall", "-Wextra", "-Werror", "-I", include, "-o", qrtr_exe, qtest, qsrc],
            timeout=240,
        )
        qrtr_ok = False
        qrtr_line = "qrtr compile rc=%d" % rc3
        if rc3 == 0:
            qrun_rc, qrun_out, qrun_err = wsl_run([qrtr_exe])
            qrtr_ok = qrun_rc == 0 and "TESTS OK 13 groups" in qrun_out
            qrtr_line = next((x for x in qrun_out.splitlines() if "TESTS OK" in x), "qrtr rc=%d" % qrun_rc)
        ok = loader_ok and qrtr_ok
        return make_result(
            "deep", ok, "loader=TESTS OK 7 " + qrtr_line,
            "loader and QRTR host tests pass" if ok else "host test failed: " + tail(out3 + err3),
            "pong PAS4 顺序见 docs/research/cellular/19-MODEM-BRINGUP-FLIGHT.md:15-19；同 SoC 参考见 hakios.mpss.c:1047-1051",
            "有证据", "真实固件服务表未反汇编", mutate,
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_verify(mutate: bool) -> Result:
    tests = [
        ("w1", "scripts/tests/test-w1-lun-evidence.py", [], "K60 W1 LUN PASS 20 host-only cases"),
        ("efs", "scripts/tests/test-efs-full.py", [], "K60 EFS FULL PASS 12 host-only cases"),
        ("bundle", "scripts/tests/test-capture-bundle.py", [], "K60 CAPTURE BUNDLE PASS 9 host-only cases"),
        ("fixtures", "scripts/tests/test-k60-flight-fixtures.py", [], "K60 FIXTURES PASS nine runs over six synthetic console fixtures"),
    ]
    counts = {}
    failures = []
    for name, rel, args, needle in tests:
        path = REPO / rel
        if not path.is_file():
            failures.append("%s missing" % rel)
            continue
        rc, out, err = run_py(path, args, timeout=300)
        if rc == 0 and needle in out:
            counts[name] = "PASS"
        else:
            counts[name] = "rc=%d" % rc
            failures.append("%s rc=%d" % (name, rc))
    judge = REPO / "scripts/judge-cellular-flight.py"
    if judge.is_file():
        rc, out, err = run_py(judge, ["--self-test"], timeout=300)
        if rc == 0 and "K60 FLIGHT JUDGE PASS" in out:
            counts["judge"] = "PASS"
        else:
            counts["judge"] = "rc=%d" % rc
            failures.append("judge rc=%d" % rc)
    else:
        failures.append("judge missing")
    strict = REPO / "scripts/judge-cellular-flight.py"
    pass_log = REPO / "scripts/tests/fixtures/k60-flight-pass.log"
    nohead_log = REPO / "scripts/tests/fixtures/k60-flight-nohead.log"
    if strict.is_file() and pass_log.is_file():
        rc, out, err = run_py(strict, ["--require-efs-bytes", str(pass_log)], timeout=180)
        if rc == 0 and "VERDICT: PASS" in out:
            counts["strict"] = "PASS"
        else:
            counts["strict"] = "rc=%d" % rc
            failures.append("strict rc=%d" % rc)
    else:
        failures.append("strict fixture missing")
    if mutate:
        if not nohead_log.is_file():
            return make_result(
                "verify", None, "negative fixture missing", "missing %s" % nohead_log,
                "日志通路先例见 E:/hackios/k60-gates/docs/research/ios27/PRECEDENT-REQUIRED.md:16-17",
                "有证据", "设备 W1/W2/F3 仍 PENDING", mutate,
            )
        rc, out, err = run_py(strict, ["--require-efs-bytes", str(nohead_log)], timeout=180)
        ok = rc == 0 and "VERDICT: PASS" in out
        return make_result(
            "verify", ok, "nohead strict rc=%d verdict=%s" % (rc, "PASS" if "VERDICT: PASS" in out else "FAILED"),
            "VERDICT: FAILED" if not ok else "negative fixture unexpectedly passed",
            "日志通路先例见 E:/hackios/k60-gates/docs/research/ios27/PRECEDENT-REQUIRED.md:16-17",
            "有证据", "设备 W1/W2/F3 仍 PENDING", mutate,
        )
    ok = not failures
    reading = "W1=20 EFS=12 BUNDLE=9 FIXTURES=9 JUDGE=self-test STRICT=PASS"
    if not ok:
        reading = " ".join("%s=%s" % (k, v) for k, v in counts.items())
    return make_result(
        "verify", ok, reading,
        "all host judges pass" if ok else "failed: " + "; ".join(failures),
        "日志通路先例见 E:/hackios/k60-gates/docs/research/ios27/PRECEDENT-REQUIRED.md:16-17",
        "有证据", "设备 W1/W2/F3 仍 PENDING", mutate,
    )


CHECKS = {
    "same_model": check_same_model,
    "official": check_official,
    "decompile": check_decompile,
    "wide": check_wide,
    "plan": check_plan,
    "deep": check_deep,
    "verify": check_verify,
}


def print_result(result: Result, mutate: bool) -> None:
    print("STEP: %s" % result.step)
    print("CMD: %s" % result.cmd)
    if mutate:
        print("EXPECT: (negative mode; run the same step without --mutate for the positive expectation)")
    else:
        print("EXPECT: %s" % result.expect)
    print("READING: %s" % result.reading)
    print("PRECEDENT: %s" % result.precedent)
    print("CONCLUSION: %s" % result.conclusion)
    print("UNKNOWN: %s" % result.unknown)
    print("NEGATIVE: %s" % result.negative)
    if mutate:
        print("NEG_EXPECT: RESULT: FAIL (mutation caught); %s" % result.detail)
    else:
        print("NEG_EXPECT: RESULT: FAIL (mutation caught)")
    if mutate:
        print("MUTATION: %s" % ("caught" if result.ok is False else "NOT caught"))
        print("RESULT: %s" % ("FAIL" if result.ok is False else "PASS" if result.ok is True else "PENDING"))
    else:
        print("RESULT: %s" % ("PASS" if result.ok is True else "FAIL" if result.ok is False else "PENDING"))
    print("DETAIL: %s" % result.detail)


def self_test() -> int:
    failures = 0
    for step in STEPS:
        normal = CHECKS[step](False)
        print("== %s ==" % step)
        print("normal: %s" % ("PASS" if normal.ok is True else "FAIL" if normal.ok is False else "PENDING"))
        print("  reading: %s" % normal.reading)
        if normal.ok is not True:
            failures += 1
            print("  ERROR: positive case did not pass")
        mutated = CHECKS[step](True)
        print("mutated: %s" % ("FAIL" if mutated.ok is False else "PASS" if mutated.ok is True else "PENDING"))
        print("  reading: %s" % mutated.reading)
        if mutated.ok is not False:
            failures += 1
            print("  ERROR: negative case did not go red")
    if failures:
        print("CELLULAR 27 CRITERIA SELF-TEST FAILED %d problem(s)" % failures)
        return 1
    print("CELLULAR 27 CRITERIA SELF-TEST PASS 7/7")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--step", choices=STEPS + [str(i) for i in range(1, 8)])
    parser.add_argument("--mutate", action="store_true", help="run the deliberately broken input; red is the expected result")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        if args.step or args.mutate:
            parser.error("--self-test cannot be combined with --step or --mutate")
        return self_test()

    if args.step:
        step = STEPS[int(args.step) - 1] if args.step.isdigit() else args.step
        result = CHECKS[step](args.mutate)
        print_result(result, args.mutate)
        if args.mutate:
            return 0 if result.ok is False else 1 if result.ok is True else 2
        return 0 if result.ok is True else 1 if result.ok is False else 2

    failed = 0
    pending = 0
    for step in STEPS:
        result = CHECKS[step](False)
        print_result(result, False)
        print()
        if result.ok is False:
            failed += 1
        elif result.ok is None:
            pending += 1
    print("SUMMARY: %d PASS, %d FAIL, %d PENDING" % (len(STEPS) - failed - pending, failed, pending))
    if failed:
        return 1
    if pending:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
