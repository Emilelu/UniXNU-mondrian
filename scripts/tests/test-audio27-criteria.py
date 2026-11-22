#!/usr/bin/env python3
"""Negative dry-runs for scripts/check-audio27-criteria.py.

Every criterion has to fail on a tree where its source fact is absent. The
fixtures are temporary repositories; nothing here reads or writes the real
eight-step record.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
GATE = os.path.abspath(os.path.join(HERE, "..", "check-audio27-criteria.py"))

RESEARCH = """PongAdsp.cpp
PongAudio.cpp
PongWcd938.h
aw882xx
CS35L43
"""
AMP = """int
pong_audio_amp_probe(void)
{
    if (!PE_parse_boot_argn("pong_audio_probe", &mode, sizeof mode) || mode != 1u) {
        return 0;
    }
    pads_map();
    spk_switch_mute();
    gcc_map();
    gcc_gpll0_on();
    gcc_wrapper2_on();
    i2c_pads_take();
    se15_open(&level);
    amp_reset_release(PadAmp0Reset, "amp0");
    amp_probe_one(0, 0x34u, 1);
    printf("PongAudio: amp probe done");
    return 0;
}
"""
REGS = """#define PONG_AUDIO_AMP0_RESET_GPIO  1u
#define PONG_AUDIO_AMP1_RESET_GPIO  3u
#define PONG_AUDIO_AMP_ADDR0        0x34u
#define PONG_AUDIO_AMP_ADDR1        0x35u
#define PONG_AUDIO_TX_CORE_CLK_ID   0x30cu
#define PONG_AUDIO_TX_CORE_HZ       19200000u
"""
AFE = """#define PONG_AFE_GPR_APM_GET_SPF_STATE 0x01001021u
#define PONG_AFE_GPR_APM_SPF_STATE     0x02001007u
#define PONG_AFE_GPR_PORT_APM          1u
#define PONG_AFE_GPR_PORT_CLIENT       0x2001u
static inline size_t
pong_afe_gpr_spf_state_query(uint8_t *buf, size_t bytes, uint32_t token)
{
    return pong_afe_gpr_hdr(buf, bytes, PONG_AFE_GPR_APM_GET_SPF_STATE,
        token, PONG_AFE_GPR_PORT_CLIENT, PONG_AFE_GPR_PORT_APM,
        PONG_AFE_GPR_HEADER_BYTES);
}
"""
DTS = """\tpong-audio {
\t\tadsp-base = <0x0 0x9fd00000>;
\t\tadsp-size = <0x0 0x03100000>;
\t\ttx-master-base = <0x0 0x0>;
\t\tcodec-reset-gpio = <0>;
\t\tcodec-i2c-address = <0>;
\t\tamp-i2c-address = <0>;
\t\ttx-core-clock-id = <0>;
\t\tcodec-supply-rail = <0>;
\t\tmic-bias = <0>;
\t\tmic-adc = <0>;
\t\tswr-device-index = <0>;
\t};
"""
WIRING = """conf/files
apply-audio27-wiring.py
PongAudioAmp.o.json
EXTRA_MAKE_ARGS
check-audio27-builder.py
"""
PROPOSAL = "check-audio27-hold.py\n0531\n"
SHENG = "AudioReach\nGENI I2C\n"
POWER = """## 3. 实现音频流
1. **打开并识别服务。**
2. **描述一条完整路由。**
3. **实现图命令。**
4. **实现缓冲路径。**
5. **接入 OS 服务。**
6. **验证路由。**
0x1001 & 0xf
4 GiB
0x30c
VA macro 和 TX macro
25%
19.2 MHz
### 麦克风采集
1. **给 codec 上电。**
2. **建立 SoundWire 链路。**
3. **配置模拟通路。**
4. **配置数字通路。**
5. **读取缓冲区。**
6. **发布输入。**
"""
RECORD = """[hardware.audio]

[hardware.audio.step.verify]
local_verified = true
unit_test = ["residue 21 cases", "hold 17 cases", "builder 13 cases"]
artifact_check = ["PAC PREFLIGHT OK 4 rows"]
evidence = ["preflight 58 rows"]
"""


class CriteriaTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="audio27-criteria-")
        self.unixnu = tempfile.mkdtemp(prefix="audio27-unixnu-")
        self.put("docs/research/audio/RESEARCH.md", RESEARCH)
        self.put("docs/research/audio/IOS27-SHENG-REFS.md", SHENG)
        self.put("docs/research/audio/IOS27-WIRING.md", WIRING)
        self.put("docs/research/audio/PAS1-CONSUMER-API-PROPOSED.md", PROPOSAL)
        self.put("docs/research/eight-step/audio-27.toml", RECORD)
        self.put("drivers/PongAudio/PongAudioAmp.c", AMP)
        self.put("drivers/PongAudio/PongAudioRegs.h", REGS)
        self.put("drivers/PongAudio/PongAudioAfe.h", AFE)
        self.put("dts/mondrian.dts", DTS)
        self.put("__unixnu__/docs/zh/porting/power.md", POWER)
        self.put("__unixnu__/components.toml", "[[component]]\n" * 29)
        self.unixnu = os.path.join(self.root, "__unixnu__")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def put(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def run_gate(self, *args):
        return subprocess.run(
            [sys.executable, GATE, "--root", self.root, "--unixnu", self.unixnu] + list(args),
            capture_output=True, text=True, encoding="utf-8", errors="replace")

    def test_all_seven_pass(self):
        result = self.run_gate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.count("CRITERIA ") - 1, 7, result.stdout)
        for name in ("same_model", "official", "decompile", "wide", "plan", "deep", "verify"):
            self.assertIn("CRITERIA %s OK:" % name, result.stdout)

    def test_same_model_fails_without_amp_token(self):
        self.put("docs/research/audio/RESEARCH.md", RESEARCH.replace("aw882xx", "unknown"))
        result = self.run_gate("--step", "same_model")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("RESEARCH.md", result.stdout)

    def test_official_fails_without_hard_fact(self):
        self.put("__unixnu__/docs/zh/porting/power.md", POWER.replace("0x1001 & 0xf", "missing"))
        result = self.run_gate("--step", "official")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("hard facts", result.stdout)

    def test_decompile_fails_with_wrong_adsp_size(self):
        self.put("dts/mondrian.dts", DTS.replace("0x03100000", "0x01000000"))
        result = self.run_gate("--step", "decompile")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("adsp-size", result.stdout)

    def test_wide_fails_when_catalog_names_audio(self):
        self.put("__unixnu__/components.toml", ("[[component]]\n" * 29) + "PongAudio\n")
        result = self.run_gate("--step", "wide")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("no longer empty", result.stdout)

    def test_plan_fails_without_define_seam(self):
        self.put("docs/research/audio/IOS27-WIRING.md", WIRING.replace("EXTRA_MAKE_ARGS", "missing"))
        result = self.run_gate("--step", "plan")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("EXTRA_MAKE_ARGS", result.stdout)

    def test_deep_fails_when_probe_order_breaks(self):
        self.put("drivers/PongAudio/PongAudioAmp.c", AMP.replace("    gcc_map();\n", ""))
        result = self.run_gate("--step", "deep")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("in order", result.stdout)

    def test_verify_fails_without_hold_case_count(self):
        broken = RECORD.replace('"hold 17 cases", ', "")
        self.put("docs/research/eight-step/audio-27.toml", broken)
        result = self.run_gate("--step", "verify")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("17 cases", result.stdout)

    def test_record_expect_must_match_computed_line(self):
        self.put("docs/research/eight-step/audio-27.toml",
                 '[hardware.audio.step.same_model]\ncriterion_expect = "WRONG"\n')
        result = self.run_gate("--step", "same_model")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("criterion_expect", result.stdout)

    def test_missing_source_fails(self):
        os.unlink(os.path.join(self.root, "drivers/PongAudio/PongAudioAmp.c"))
        result = self.run_gate("--step", "same_model")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("missing", result.stdout)

    def test_missing_root_is_usage(self):
        result = subprocess.run(
            [sys.executable, GATE, "--root", os.path.join(self.root, "nope")],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(result.returncode, 2, result.stdout)

    def test_help(self):
        result = subprocess.run(
            [sys.executable, GATE, "--help"],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(result.returncode, 0)
        self.assertIn("usage:", result.stdout.lower())


if __name__ == "__main__":
    suite = unittest.main(verbosity=0, exit=False)
    if suite.result.wasSuccessful():
        print("TESTS OK %d cases" % suite.result.testsRun)
    sys.exit(0 if suite.result.wasSuccessful() else 1)
