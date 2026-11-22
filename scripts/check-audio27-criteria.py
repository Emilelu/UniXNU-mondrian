#!/usr/bin/env python3
"""Run the seven audio 27 criteria and print one fixed line per step.

Each step in docs/research/eight-step/audio-27.toml names a command and the
line that command is expected to print. This script is that command: it reads
the same record and the same sources, recomputes every line, and fails when a
computed line drifts from the record. A line in a document is not a criterion;
a recomputed line is.

Usage: python3 scripts/check-audio27-criteria.py [--root DIR] [--unixnu DIR]
       [--record FILE] [--step NAME]
"""

import argparse
import os
import re
import sys

try:
    import tomllib
except ImportError:  # Python 3.10 on the host
    import tomli as tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.dirname(HERE)
STEPS = ("same_model", "official", "decompile", "wide", "plan", "deep", "verify")

EXPECTED = {
    "same_model": "CRITERIA same_model OK: Pong stack recorded; K60 AW88261 0x34/0x35 differs from CS35L43; probe entry and boot arg present",
    "official": "CRITERIA official OK: power.md audio section has 6 stream steps, 5 hard facts and 6 mic steps",
    "decompile": "CRITERIA decompile OK: DT adsp 0x9fd00000+0x03100000 with 9 unmeasured zeros; amp 0x34/0x35 reset 1/3; TX core 0x30c at 19.2 MHz",
    "wide": "CRITERIA wide OK: 29 catalog components, none named AudioProbe/AdspProbe/PongAudio; sheng AudioReach reference recorded",
    "plan": "CRITERIA plan OK: three seams named; define gate is PongAudioAmp.o.json; 0531 dormant gate cited",
    "deep": "CRITERIA deep OK: probe order pads->mute->GCC->I2C->SE15->reset->probe; APM query 0x01001021 expects 0x02001007 status 1",
    "verify": "CRITERIA verify OK: preflight 58/4 rows; residue 21, hold 17, builder 13 cases recorded",
}


class Failure(Exception):
    pass


def read(root, rel, what=None):
    path = os.path.join(root, rel)
    if not os.path.isfile(path):
        raise Failure("missing %s" % (what or rel))
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError as error:
        raise Failure("cannot read %s: %s" % (rel, error))


def need(text, token, what):
    if token not in text:
        raise Failure("%s does not contain %r" % (what, token))


def resolve_unixnu(root, explicit):
    if explicit:
        candidates = [explicit]
    else:
        candidates = []
        if os.environ.get("UNIXNU_REPO"):
            candidates.append(os.environ["UNIXNU_REPO"])
        candidates.extend([
            "/mnt/e/hackios/UniXNU",
            os.path.join(os.path.dirname(os.path.abspath(root)), "UniXNU"),
            "E:/hackios/UniXNU",
        ])
    for path in candidates:
        if path and os.path.isdir(os.path.join(path, "docs", "zh")):
            return path
    raise Failure("no UniXNU checkout with docs/zh (tried %s)" % ", ".join(candidates))


def load_record(root, explicit):
    path = explicit or os.path.join(root, "docs/research/eight-step/audio-27.toml")
    if not os.path.isfile(path):
        raise Failure("missing record %s" % path)
    try:
        with open(path, "rb") as handle:
            return tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise Failure("cannot read record %s: %s" % (path, error))


def step_table(record, name):
    try:
        return record["hardware"]["audio"]["step"][name]
    except (KeyError, TypeError):
        return None


def same_model(root, unixnu, record):
    del unixnu, record
    research = read(root, "docs/research/audio/RESEARCH.md")
    for token in ("PongAdsp.cpp", "PongAudio.cpp", "PongWcd938.h", "aw882xx", "CS35L43"):
        need(research, token, "RESEARCH.md")
    amp = read(root, "drivers/PongAudio/PongAudioAmp.c")
    need(amp, "pong_audio_amp_probe", "PongAudioAmp.c")
    need(amp, 'PE_parse_boot_argn("pong_audio_probe"', "PongAudioAmp.c")
    regs = read(root, "drivers/PongAudio/PongAudioRegs.h")
    for token in ("0x34u", "0x35u"):
        need(regs, token, "PongAudioRegs.h")
    return EXPECTED["same_model"]


def official(root, unixnu, record):
    del record
    tree = resolve_unixnu(root, unixnu)
    page = read(tree, "docs/zh/porting/power.md", "UniXNU power.md")
    need(page, "## 3. 实现音频流", "power.md")
    for token in (
        "1. **打开并识别服务。**",
        "2. **描述一条完整路由。**",
        "3. **实现图命令。**",
        "4. **实现缓冲路径。**",
        "5. **接入 OS 服务。**",
        "6. **验证路由。**",
    ):
        need(page, token, "power.md stream steps")
    for token in ("0x1001 & 0xf", "4 GiB", "0x30c", "VA macro 和 TX macro", "25%", "19.2 MHz"):
        need(page, token, "power.md hard facts")
    need(page, "### 麦克风采集", "power.md")
    for token in (
        "1. **给 codec 上电。**",
        "2. **建立 SoundWire 链路。**",
        "3. **配置模拟通路。**",
        "4. **配置数字通路。**",
        "5. **读取缓冲区。**",
        "6. **发布输入。**",
    ):
        need(page, token, "power.md microphone steps")
    return EXPECTED["official"]


def decompile(root, unixnu, record):
    del unixnu, record
    dts = read(root, "dts/mondrian.dts")
    start = dts.find("pong-audio {")
    if start < 0:
        raise Failure("dts/mondrian.dts has no pong-audio node")
    end = dts.find("\n\t};", start)
    if end < 0:
        raise Failure("pong-audio node is not closed")
    block = dts[start:end]
    need(block, "adsp-base = <0x0 0x9fd00000>", "pong-audio")
    need(block, "adsp-size = <0x0 0x03100000>", "pong-audio")
    zeros = len(re.findall(r"=\s*<0x0 0x0>|=\s*<0>", block))
    if zeros != 9:
        raise Failure("pong-audio has %d unmeasured zeros, expected 9" % zeros)
    regs = read(root, "drivers/PongAudio/PongAudioRegs.h")
    patterns = (
        (r"#define\s+PONG_AUDIO_AMP0_RESET_GPIO\s+1u", "AMP0 reset 1"),
        (r"#define\s+PONG_AUDIO_AMP1_RESET_GPIO\s+3u", "AMP1 reset 3"),
        (r"#define\s+PONG_AUDIO_AMP_ADDR0\s+0x34u", "AMP0 address 0x34"),
        (r"#define\s+PONG_AUDIO_AMP_ADDR1\s+0x35u", "AMP1 address 0x35"),
        (r"#define\s+PONG_AUDIO_TX_CORE_CLK_ID\s+0x30cu", "TX core clock 0x30c"),
        (r"#define\s+PONG_AUDIO_TX_CORE_HZ\s+19200000u", "TX core 19.2 MHz"),
    )
    for pattern, what in patterns:
        if not re.search(pattern, regs):
            raise Failure("PongAudioRegs.h has no %s" % what)
    return EXPECTED["decompile"]


def wide(root, unixnu, record):
    del record
    tree = resolve_unixnu(root, unixnu)
    catalog = read(tree, "components.toml", "UniXNU components.toml")
    count = len(re.findall(r"^\[\[component\]\]", catalog, re.M))
    if count != 29:
        raise Failure("components.toml declares %d components, expected 29" % count)
    for token in ("AudioProbe", "AdspProbe", "PongAudio"):
        if token in catalog:
            raise Failure("components.toml names %s, so the catalog is no longer empty for audio" % token)
    refs = read(root, "docs/research/audio/IOS27-SHENG-REFS.md")
    for token in ("AudioReach", "GENI I2C"):
        need(refs, token, "IOS27-SHENG-REFS.md")
    return EXPECTED["wide"]


def plan(root, unixnu, record):
    del unixnu, record
    wiring = read(root, "docs/research/audio/IOS27-WIRING.md")
    for token in (
        "conf/files",
        "apply-audio27-wiring.py",
        "PongAudioAmp.o.json",
        "EXTRA_MAKE_ARGS",
        "check-audio27-builder.py",
    ):
        need(wiring, token, "IOS27-WIRING.md")
    proposal = read(root, "docs/research/audio/PAS1-CONSUMER-API-PROPOSED.md")
    for token in ("check-audio27-hold.py", "0531"):
        need(proposal, token, "PAS1-CONSUMER-API-PROPOSED.md")
    return EXPECTED["plan"]


def deep(root, unixnu, record):
    del unixnu, record
    amp = read(root, "drivers/PongAudio/PongAudioAmp.c")
    start = amp.find("pong_audio_amp_probe(void)")
    if start < 0:
        raise Failure("PongAudioAmp.c has no pong_audio_amp_probe(void)")
    end = amp.find("PongAudio: amp probe done", start)
    body = amp[start:end if end >= 0 else len(amp)]
    order = [
        "pads_map()",
        "spk_switch_mute()",
        "gcc_map()",
        "gcc_gpll0_on()",
        "gcc_wrapper2_on()",
        "i2c_pads_take()",
        "se15_open(&level)",
        "amp_reset_release(PadAmp0Reset",
        "amp_probe_one(0",
    ]
    position = -1
    for token in order:
        found = body.find(token, position + 1)
        if found < 0:
            raise Failure("probe body is missing %r in order" % token)
        position = found
    afe = read(root, "drivers/PongAudio/PongAudioAfe.h")
    for token in (
        "PONG_AFE_GPR_APM_GET_SPF_STATE",
        "0x01001021u",
        "PONG_AFE_GPR_APM_SPF_STATE",
        "0x02001007u",
        "pong_afe_gpr_spf_state_query",
        "PONG_AFE_GPR_PORT_CLIENT",
        "PONG_AFE_GPR_PORT_APM",
    ):
        need(afe, token, "PongAudioAfe.h")
    return EXPECTED["deep"]


def verify(root, unixnu, record):
    del unixnu
    table = step_table(record, "verify")
    if not table:
        raise Failure("record has no hardware.audio.step.verify table")
    if table.get("local_verified") is not True:
        raise Failure("verify.local_verified is not true")
    unit = "\n".join(table.get("unit_test") or [])
    for token in ("21 cases", "17 cases", "13 cases"):
        need(unit, token, "verify.unit_test")
    artifact = "\n".join(table.get("artifact_check") or [])
    need(artifact, "4 rows", "verify.artifact_check")
    evidence = "\n".join(table.get("evidence") or [])
    need(evidence, "58", "verify.evidence")
    return EXPECTED["verify"]


RUNNERS = {
    "same_model": same_model,
    "official": official,
    "decompile": decompile,
    "wide": wide,
    "plan": plan,
    "deep": deep,
    "verify": verify,
}


def main(argv):
    parser = argparse.ArgumentParser(
        description=(__doc__ or "").strip().split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--root", default=DEFAULT_ROOT,
                        help="repository root (default: the checkout holding this script)")
    parser.add_argument("--unixnu", default=None,
                        help="UniXNU checkout (default: UNIXNU_REPO, /mnt/e/hackios/UniXNU, ../UniXNU)")
    parser.add_argument("--record", default=None,
                        help="eight-step record (default: ROOT/docs/research/eight-step/audio-27.toml)")
    parser.add_argument("--step", choices=STEPS, default=None,
                        help="run one step instead of all seven")
    args = parser.parse_args(argv)

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print("CRITERIA FAILED: root %s is not a directory" % root)
        return 2
    try:
        record = load_record(root, args.record)
    except Failure as error:
        if args.step in (None, "verify"):
            print("CRITERIA verify FAILED: %s" % error)
            return 1
        record = None

    selected = [args.step] if args.step else list(STEPS)
    failures = 0
    for name in selected:
        try:
            actual = RUNNERS[name](root, args.unixnu, record)
            if actual != EXPECTED[name]:
                raise Failure("computed line drifted from the pinned expected line")
            table = step_table(record, name) if record else None
            if table and isinstance(table.get("criterion_expect"), str):
                if table["criterion_expect"] != actual:
                    raise Failure(
                        "record criterion_expect is not the computed line: %r"
                        % table["criterion_expect"])
            print(actual)
        except Failure as error:
            print("CRITERIA %s FAILED: %s" % (name, error))
            failures += 1
    if failures:
        print("CRITERIA FAILED %d of %d step(s)" % (failures, len(selected)))
        return 1
    print("CRITERIA OK %d of %d step(s)" % (len(selected), len(selected)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
