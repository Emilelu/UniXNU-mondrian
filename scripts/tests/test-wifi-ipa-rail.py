#!/usr/bin/env python3
"""Static check: the K60 WLAN profile must carry Pong's vdd-wlan-ipa rail.

Pong's QCA6490 board profile has a seventh WLAN rail, vdd-wlan-ipa on smpe3
(PMR735A S3, 2.2 V). The K60 live DT has the same regulator node and declares
qcom,vreg_ipa="s3e" on the cnss node, but no vdd-wlan-ipa-supply. Pong's
services93/94 record that Wi-Fi failed while the first smpe3 read returned
zero and worked after the rail was ready. This test pins the profile entry and
the two code capacities that must admit it; it does not claim the rail is the
only MHI blocker.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "configs/mondrian-wifi-sm8475.json"
BUILDER = ROOT / "scripts/build-k60-wifi-native.py"
PLATFORM = ROOT / "drivers/PongWifi/PongWifiPlatform.cpp"
PATCH_PROFILE = ROOT / "patches/wifi/0008-configs-mondrian-wifi-sm8475.patch"
PATCH_BUILDER = ROOT / "patches/wifi/0009-scripts-k60-wifi-build.patch"
PATCH_PLATFORM = ROOT / "patches/wifi/0011-drivers-PongWifi-k60-bringup-stages.patch"
PATCH_PLATFORM_BASE = ROOT / "patches/wifi/0001-drivers-PongWifi-vendor-zizhan-087416a.patch"


def check(profile, builder, platform):
    failures = []

    def need(cond, msg):
        if not cond:
            failures.append(msg)

    need(len(profile.get("rails", [])) == 6,
         "the six proven K60 WLAN rails are not intact")
    extra = profile.get("extra_rails", [])
    need(len(extra) == 1, "extra_rails must contain exactly the Pong IPA rail")
    if len(extra) == 1:
        rail = extra[0]
        need(rail.get("supply") == "vdd-wlan-ipa", "extra rail supply is not vdd-wlan-ipa")
        need(rail.get("resource") == "smpe3", "extra rail resource is not smpe3")
        need(rail.get("regulator") == "pmr735a_s3", "extra rail regulator is not pmr735a_s3")
        need(rail.get("request", [])[:2] == [2200000, 2200000],
             "extra rail request is not 2.2 V")
        physical = rail.get("physical", {})
        need(physical.get("spmi_slave") == 4, "extra rail SPMI slave is not 4")
        need(physical.get("peripheral") == 161, "extra rail peripheral is not 161")
        need(physical.get("type") == 3 and physical.get("subtype") == 10,
             "extra rail type/subtype is not 3/10")
        need("vreg_ipa=s3e" in rail.get("origin", ""),
             "extra rail does not record the K60 qcom,vreg_ipa evidence")

    need("profile.get('extra_rails', [])" in builder,
         "native builder does not iterate extra_rails")
    if "profile.get('extra_rails', [])" in builder:
        need(builder.index("profile.get('extra_rails', [])") < builder.index("profile['pcie']['analogue_rails']"),
             "extra rails are emitted after the analogue LDOs")
    need("railCount>9" in platform,
         "platform still rejects the ninth rail")
    need("QcomRpmhResource res[9]" in platform,
         "platform resource array is still sized for eight rails")
    need("readFailures" in platform,
         "platform railReady does not retry the complete sample")
    need("pmicRead(unsigned(channel),4,id,2)||id[0]!=r.type" in platform,
         "platform railReady does not retry PMIC identification")
    return failures


def check_patch_mirrors(profile_patch, builder_patch, platform_patch, platform_base_patch):
    failures = []

    def need(cond, msg):
        if not cond:
            failures.append(msg)

    need('"extra_rails"' in profile_patch,
         "profile patch does not carry extra_rails")
    need('"vdd-wlan-ipa"' in profile_patch,
         "profile patch does not carry vdd-wlan-ipa")
    need("profile.get('extra_rails', [])" in builder_patch,
         "builder patch does not emit extra_rails")
    need("railCount>9" in platform_patch,
         "platform patch still rejects the ninth rail")
    need("QcomRpmhResource res[9]" in platform_patch,
         "platform patch resource array is still eight entries")
    need("readFailures" in platform_base_patch,
         "base platform patch lacks the complete-sample retry")
    need("pmicRead(unsigned(channel),4,id,2)||id[0]!=r.type" in platform_base_patch,
         "base platform patch does not retry PMIC identification")
    return failures


def mutant_profile(profile, **changes):
    other = json.loads(json.dumps(profile))
    for key, value in changes.items():
        if key == "request":
            other["extra_rails"][0]["request"] = value
        elif key == "peripheral":
            other["extra_rails"][0]["physical"]["peripheral"] = value
        elif key == "extra_rails":
            other["extra_rails"] = value
        else:
            other["extra_rails"][0][key] = value
    return other


def main():
    profile = json.loads(PROFILE.read_text())
    builder = BUILDER.read_text()
    platform = PLATFORM.read_text()
    profile_patch = PATCH_PROFILE.read_text()
    builder_patch = PATCH_BUILDER.read_text()
    platform_patch = PATCH_PLATFORM.read_text()
    platform_base_patch = PATCH_PLATFORM_BASE.read_text()
    failures = check(profile, builder, platform)
    failures += check_patch_mirrors(profile_patch, builder_patch, platform_patch, platform_base_patch)
    if failures:
        for failure in failures:
            print("FAIL:", failure)
        return 1

    # The test must reject the regressions it exists to catch.
    cases = [
        ("missing extra rail", mutant_profile(profile, extra_rails=[]), builder, platform),
        ("wrong voltage", mutant_profile(profile, request=[2000000, 2200000, 0, 0, 0]), builder, platform),
        ("wrong PPID", mutant_profile(profile, peripheral=160), builder, platform),
        ("builder loop removed", profile, builder.replace(" for e in profile.get('extra_rails', []):\n", ""), platform),
        ("old eight-rail guard", profile, builder, platform.replace("railCount>9", "railCount>8")),
        ("eight-entry resource array", profile, builder, platform.replace("QcomRpmhResource res[9]", "QcomRpmhResource res[8]")),
        ("rail identification not retried", profile, builder, platform.replace("pmicRead(unsigned(channel),4,id,2)||id[0]!=r.type||id[1]!=r.subtype||", "pmicRead(unsigned(channel),4,id,2)||")),
    ]
    for name, p, b, s in cases:
        if not check(p, b, s):
            print("FAIL: test did not reject", name)
            return 1

    patch_cases = [
        ("profile patch missing extra rail", "", builder_patch, platform_patch, platform_base_patch),
        ("builder patch missing extra loop", profile_patch, "", platform_patch, platform_base_patch),
        ("platform patch old eight-rail guard", profile_patch, builder_patch, platform_patch.replace("railCount>9", "railCount>8"), platform_base_patch),
        ("base platform patch old rail identification", profile_patch, builder_patch, platform_patch, platform_base_patch.replace("pmicRead(unsigned(channel),4,id,2)||id[0]!=r.type||id[1]!=r.subtype||", "pmicRead(unsigned(channel),4,id,2)||")),
    ]
    for name, pp, bp, sp, sb in patch_cases:
        if not check_patch_mirrors(pp, bp, sp, sb):
            print("FAIL: test did not reject", name)
            return 1

    print("PASS: K60 profile carries Pong vdd-wlan-ipa as the ninth rail (%d negative cases)" % (len(cases) + len(patch_cases)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
