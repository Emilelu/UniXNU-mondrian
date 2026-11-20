#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause-Patent
"""Host cases for check-sheng-inject.py: a fixture checkout that satisfies the
eight required invariants and the one versioned fact, one that only carries the
iOS sandbox grant (green plus a note), one where a needle moved away, one where
the plug-in stopped keeping its image resident, one where the mount stopped
stacking on the earlier add-on slots, and a named tree that has no add-on patch
at all."""
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]
CHECK = REPO / "scripts/check-sheng-inject.py"
cases = 0

PATCH = """Subject: [PATCH] mount the audio add-on
+
+\tstatic const char audio_source[] = "/private/var/ngpu/audio", audio_point[] = "/System/Library/Audio/Plug-Ins/HAL";
 volatile int native_gpu_addon3_stage = 0;
+volatile int native_gpu_addon4_stage = 0;
+\tnative_gpu_addon_mount(p, scratch, 0xa00, audio_source, sizeof(audio_source), audio_point, sizeof(audio_point),
+\t    "/System/Library/Audio/Plug-Ins/HAL/BuiltinAudioPlugin.driver", "/System/Library/Audio/Plug-Ins/HAL/ShengAudio.driver/Info.plist",
"""
PLUGIN = """#include <dlfcn.h>
static void keepImageResident(void) {
    Dl_info info;
}
void start(void) {
    keepImageResident();
}
"""
SERVICE = """#if defined(XNU_TARGET_OS_OSX)
        setProperty("NativeSandboxGrantProcess", "coreaudiod,com.apple.audio.Core-Audio-Driver-Service.helper");
#else
        setProperty("NativeSandboxGrantProcess", "audiomxd,mediaserverd");
#endif
"""


def run(*command):
    done = subprocess.run(list(command), stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True)
    return done.returncode, done.stdout


def checkout(work, name, service=SERVICE, patch=PATCH, plugin=PLUGIN):
    root = work / name
    (root / "patches/xnu-12377").mkdir(parents=True, exist_ok=True)
    (root / "hal").mkdir(parents=True, exist_ok=True)
    (root / "package").mkdir(parents=True, exist_ok=True)
    (root / "patches/xnu-12377/zzyd-sheng-audio-addon-mount.patch").write_text(patch)
    (root / "hal/ShengAudioPlugIn.c").write_text(plugin)
    (root / "package/ShengAudioService.cpp").write_text(service)
    return root


def main():
    global cases
    work = pathlib.Path(tempfile.mkdtemp(prefix="sheng-inject-"))
    good = checkout(work, "good")
    code, out = run(sys.executable, str(CHECK), "--sheng", str(good))
    assert code == 0, out
    assert "SHENG INJECT OK 9/9 invariants" in out, out
    assert "hal/ShengAudioPlugIn.c:2" in out, out
    cases += 1
    print("  ok   the fixture satisfies the eight required invariants and the versioned one")

    ios_only = checkout(work, "ios-only",
                        service=SERVICE.split("#else")[1].split("#endif")[0])
    code, out = run(sys.executable, str(CHECK), "--sheng", str(ios_only))
    assert code == 0, out
    assert "SHENG INJECT NOTE" in out, out
    assert "1 versioned fact(s) absent" in out, out
    assert "SHENG INJECT OK 8/9 invariants" in out, out
    cases += 1
    print("  ok   a tree with only the iOS grant is green, and says which fact is absent")

    noresidency = checkout(work, "noresidency",
                           plugin=PLUGIN.replace("keepImageResident", "keepsTheImage"))
    code, out = run(sys.executable, str(CHECK), "--sheng", str(noresidency))
    assert code == 1, out
    assert "keepImageResident" in out, out
    assert "the plug-in keeps its image resident" in out, out
    cases += 1
    print("  ok   a plug-in that stopped keeping its image resident is a failure, not a note")

    drifted = checkout(work, "drifted", service=SERVICE.replace("audiomxd,mediaserverd", "audiomxd"))
    code, out = run(sys.executable, str(CHECK), "--sheng", str(drifted))
    assert code == 1, out
    assert "INJECT FAILED" in out and "audiomxd,mediaserverd" in out, out
    assert "the iOS sandbox grant names the media servers" in out, out
    cases += 1
    print("  ok   a grant that stopped naming the media servers is named")

    unpatch = checkout(work, "unpatch")
    (unpatch / "patches/xnu-12377/zzyd-sheng-audio-addon-mount.patch").unlink()
    code, out = run(sys.executable, str(CHECK), "--sheng", str(unpatch))
    assert code == 1, out
    assert "refusing to read another tree" in out, out
    cases += 1
    print("  ok   a tree without the add-on patch is refused, not skipped")

    standalone = checkout(work, "standalone",
                          patch=PATCH.replace("volatile int native_gpu_addon3_stage = 0;", ""))
    code, out = run(sys.executable, str(CHECK), "--sheng", str(standalone))
    assert code == 1, out
    assert "native_gpu_addon3_stage = 0" in out, out
    assert "not a standalone patch" in out, out
    cases += 1
    print("  ok   a mount that stopped stacking on the earlier slots is named")

    noplugin = checkout(work, "noplugin")
    (noplugin / "hal/ShengAudioPlugIn.c").unlink()
    code, out = run(sys.executable, str(CHECK), "--sheng", str(noplugin))
    assert code == 1, out
    assert "no hal/ShengAudioPlugIn.c" in out, out
    cases += 1
    print("  ok   a missing plug-in source is named")

    print("TESTS OK %d cases" % cases)


if __name__ == "__main__":
    main()
