#!/usr/bin/env python3
# Static, host-side check for patches/xnu/0509-k60-bt-s3-identity-publish.patch
# (twin: patches/bt/0003-k60-bt-s3-identity-publish.patch).
#
# The three identity properties published under /arm-io/bluetooth
# (device_type / compatible / unixnu,adt-name) and the radio's device_type
# must be OSData bytes, not C-string OSStrings: Apple-side readers call
# getBytes: and an OSString made backboardd crash
# (-[NSTaggedPointerString getBytes:range:], bt-s4c-20261115c
# console.log:1303).  This test asserts the patch text, so it runs on the
# host without building a kernel.
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
XNU_PATCH = ROOT / "patches" / "xnu" / "0509-k60-bt-s3-identity-publish.patch"
BT_PATCH = ROOT / "patches" / "bt" / "0003-k60-bt-s3-identity-publish.patch"

failures = 0
cases = 0


def check(condition, label, detail=""):
    global failures, cases
    cases += 1
    if condition:
        print(f"  ok: {label}")
    else:
        failures += 1
        print(f"  FAIL: {label}" + (f" - {detail}" if detail else ""))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


print("test-k60-bt-0509-properties")
xnu_text = XNU_PATCH.read_text(encoding="utf-8")
check(xnu_text.startswith("diff --git a/bsd/dev/qbt_k60.c b/bsd/dev/qbt_k60.c"),
      "0509 patch starts with the qbt_k60.c section")

# 1. Structure: exactly the five known files, MiniBluetooth as a new file.
sections = xnu_text.split("diff --git ")[1:]
paths = [s.split("\n", 1)[0] for s in sections]
check(len(sections) == 5, "patch has five sections",
      f"found {len(sections)}: {paths}")
check(paths[0] == "a/bsd/dev/qbt_k60.c b/bsd/dev/qbt_k60.c", "section 1 is qbt_k60.c")
check(paths[1] == "a/iokit/Kernel/MiniBluetooth.cpp b/iokit/Kernel/MiniBluetooth.cpp",
      "section 2 is MiniBluetooth.cpp")
check("new file mode 100644" in sections[1], "MiniBluetooth.cpp is a new file")
check(paths[2] == "a/iokit/Kernel/MiniDrivers.h b/iokit/Kernel/MiniDrivers.h",
      "section 3 is MiniDrivers.h")
check(paths[3] == "a/iokit/Kernel/MiniIOSurface.cpp b/iokit/Kernel/MiniIOSurface.cpp",
      "section 4 is MiniIOSurface.cpp")
check(paths[4] == "a/iokit/conf/files b/iokit/conf/files", "section 5 is iokit/conf/files")

# 2. Twin parity (patches/bt/series maps 0003 <-> 0509).
bt_text = BT_PATCH.read_text(encoding="utf-8")
check(sha256(XNU_PATCH) == sha256(BT_PATCH),
      "patches/bt/0003 is byte-identical to patches/xnu/0509")

# 3. The OSData helper exists inside the MiniBluetooth section.
mb = sections[1]
helper_in = mb.index("k60_bt_string_property")
check(helper_in >= 0, "k60_bt_string_property helper is present")
check("OSData::withBytes(value, strlen(value) + 1)" in mb,
      "helper wraps the value in OSData::withBytes with NUL-inclusive length")
check("entry->setProperty(key, data);" in mb, "helper publishes the OSData")
check("data->release();" in mb, "helper releases the OSData after publish")
check("if (data == NULL)" in mb, "helper guards against allocation failure")
check("#include <string.h>" in mb, "MiniBluetooth.cpp includes string.h for strlen")

# 4. The three identity properties and the radio device_type go through the
#    helper; no bare C-string setProperty for those keys remains anywhere.
for key, value in [
    ("device_type", "bluetooth"),
    ("compatible", "qcom,wcn7850-bt"),
    ("unixnu,adt-name", "bluetooth"),
]:
    bare = f'setProperty("{key}", "{value}")'
    check(bare not in xnu_text,
          f"no bare OSString publish of {key}={value}",
          f"found {bare!r}")
check('k60_bt_string_property(node, "device_type", "bluetooth");' in mb,
      "node device_type published through the helper")
check('k60_bt_string_property(node, "compatible", "qcom,wcn7850-bt");' in mb,
      "node compatible published through the helper")
check('k60_bt_string_property(node, "unixnu,adt-name", "bluetooth");' in mb,
      "node unixnu,adt-name published through the helper")
check('k60_bt_string_property(radio, "device_type", "bluetooth");' in mb,
      "radio device_type published through the helper")

# 5. Helper usage count: one definition plus four call sites, and nothing
#    outside the MiniBluetooth section.
check(mb.count("k60_bt_string_property(") == 5,
      "helper used exactly five times in MiniBluetooth.cpp",
      f"found {mb.count('k60_bt_string_property(')}")
check("k60_bt_string_property" not in xnu_text.replace(mb, ""),
      "no helper usage outside the MiniBluetooth section")

# 6. The numeric property path is untouched.
check("k60_bt_number_property(" in mb, "numeric property helper still present")

print(f"TESTS OK {cases} case(s) ({failures} failure(s))")
sys.exit(1 if failures else 0)
