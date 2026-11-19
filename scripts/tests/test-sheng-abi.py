#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Host cases for check-sheng-abi.py: a fixture header, reformatted and changed."""
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]
CHECK = REPO / "scripts/check-sheng-abi.py"
cases = 0

GOOD = """#define SHENG_AUDIO_CLASS "ShengAudio"
#define SHENG_AUDIO_MAGIC 0x53484155u
#define SHENG_AUDIO_VERSION 1u
#define SHENG_AUDIO_RATE 48000u
#define SHENG_AUDIO_OUT_CHANNELS 2u
#define SHENG_AUDIO_IN_CHANNELS 1u
#define SHENG_AUDIO_PERIOD_FRAMES 480u
#define SHENG_AUDIO_RING_FRAMES 65536u
enum {ShengAudioMemoryControl = 0, ShengAudioMemoryOutput = 1, ShengAudioMemoryInput = 2};
enum {ShengAudioStartOutput = 0, ShengAudioStopOutput = 1, ShengAudioStartInput = 2, ShengAudioStopInput = 3};
enum {ShengAudioSetHostClock = 4};
enum {ShengAudioOutputRunning = 1u << 0, ShengAudioInputRunning = 1u << 1, ShengAudioOutputReady = 1u << 2, ShengAudioInputReady = 1u << 3};
#define SHENG_AUDIO_DIAG_OFFSET 2048u
#define SHENG_AUDIO_DIAG_SLOTS 32u
#define SHENG_AUDIO_TRACE_OFFSET 2560u
#define SHENG_AUDIO_TRACE_SLOTS 128u
"""


def run(*command):
    done = subprocess.run(list(command), stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True)
    return done.returncode, done.stdout


def checkout(work, text):
    root = work / "sheng"
    (root / "package").mkdir(parents=True, exist_ok=True)
    (root / "package/ShengAudioAbi.h").write_text(text)
    return root


def main():
    global cases
    work = pathlib.Path(tempfile.mkdtemp(prefix="sheng-abi-"))
    try:
        root = checkout(work, GOOD)
        code, out = run(sys.executable, str(CHECK), "--sheng", str(root))
        assert code == 0, out
        assert "SHENG ABI OK 16/16 constants" in out, out
        print("  ok   the fixture header passes")

        reformatted = GOOD.replace(
            "enum {ShengAudioStartOutput = 0, ShengAudioStopOutput = 1, ShengAudioStartInput = 2, ShengAudioStopInput = 3};",
            "enum {\n    ShengAudioStartOutput = 0,\n    ShengAudioStopOutput = 1,\n    ShengAudioStartInput = 2,\n    ShengAudioStopInput = 3,\n};")
        root2 = checkout(work, reformatted)
        (root2 / "package/ShengAudioAbi.h").write_text(reformatted)
        code, out = run(sys.executable, str(CHECK), "--sheng", str(root2))
        assert code == 0, "reformatting must not count as drift: " + out
        print("  ok   reformatting is not drift")

        moved = GOOD.replace("ShengAudioSetHostClock = 4", "ShengAudioSetHostClock = 5")
        root3 = checkout(work, moved)
        (root3 / "package/ShengAudioAbi.h").write_text(moved)
        code, out = run(sys.executable, str(CHECK), "--sheng", str(root3))
        assert code == 1, out
        assert "host clock selector" in out and "SHENG ABI FAILED" in out, out
        print("  ok   a changed selector is named")

        code, out = run(sys.executable, str(CHECK), "--sheng", str(work / "absent"))
        assert code == 1 and "refusing to read another tree" in out, out
        print("  ok   a named checkout without the header is refused, not replaced")
        cases = 4
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print("TESTS OK %d cases" % cases)
    return 0


if __name__ == "__main__":
    sys.exit(main())
