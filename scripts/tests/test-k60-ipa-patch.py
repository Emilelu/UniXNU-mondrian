#!/usr/bin/env python3
"""Offline guard for patch 0623: it must carry the exact PongCellular IPA M0 files.

The build consumes the patch, not drivers/PongCellular, so a stale patch would
silently compile a different skeleton. This gate mirrors the modem image gate.
"""

import pathlib

REPO = pathlib.Path(__file__).resolve().parents[2]
PATCH = REPO / "patches/xnu/0623-k60-ipa.patch"
SERIES = REPO / "patches/xnu/series"
CONFFILES = REPO / "scripts/append-conffiles.py"


def added_lines(patch: str, target: str) -> str:
    collecting = False
    out = []
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            collecting = line.endswith(" b/" + target)
            continue
        if not collecting:
            continue
        if line.startswith(("+++ ", "--- ", "@@ ", "index ", "new file mode ")):
            continue
        if line.startswith("+"):
            out.append(line[1:])
    return "\n".join(out) + ("\n" if out else "")


def fail(message: str) -> int:
    print("FAIL " + message)
    return 1


def kernel_copy(name: str) -> str:
    text = (REPO / "drivers/PongCellular" / name).read_text()
    for source, target in (("K60Ipa.h", "pong_ipa.h"),
                           ("K60Mdt.h", "pong_mdt.h"),
                           ("K60ModemPas.h", "pong_modem_pas.h"),
                           ("K60PmicRail.h", "pong_pmic_rail.h"),
                           ("K60Smem.h", "pong_smem.h"),
                           ("K60Fat.h", "pong_fat.h"),
                           ("K60IpaGsi.h", "pong_ipa_gsi.h"),
                           ("K60IpaSmmu.h", "pong_ipa_smmu.h"),
                           ("K60IpaQmap.h", "pong_ipa_qmap.h")):
        text = text.replace('#include "%s"' % source, '#include "%s"' % target)
    return text


def main() -> int:
    if not PATCH.is_file():
        return fail("patch 0623 is missing")
    patch = PATCH.read_text()

    expected = (
        ("bsd/dev/pong_ipa.h", kernel_copy("K60Ipa.h")),
        ("bsd/dev/pong_ipa.c", kernel_copy("K60Ipa.c")),
        ("bsd/dev/pong_mdt.h", kernel_copy("K60Mdt.h")),
        ("bsd/dev/pong_mdt.c", kernel_copy("K60Mdt.c")),
        ("bsd/dev/pong_ipa_gsi.h", kernel_copy("K60IpaGsi.h")),
        ("bsd/dev/pong_ipa_gsi.c", kernel_copy("K60IpaGsi.c")),
        ("bsd/dev/pong_ipa_smmu.h", kernel_copy("K60IpaSmmu.h")),
        ("bsd/dev/pong_ipa_smmu.c", kernel_copy("K60IpaSmmu.c")),
        ("bsd/dev/pong_ipa_qmap.h", kernel_copy("K60IpaQmap.h")),
        ("bsd/dev/pong_ipa_qmap.c", kernel_copy("K60IpaQmap.c")),
    )
    for target, text in expected:
        if added_lines(patch, target) != text:
            return fail("%s differs from its PongCellular source" % target)
    if "0623-k60-ipa.patch" not in SERIES.read_text().splitlines():
        return fail("0623 is not in patches/xnu/series")
    if "0624-k60-ipa-call-site.patch" not in SERIES.read_text().splitlines():
        return fail("0624 is not in patches/xnu/series")
    call_site = (REPO / "patches/xnu/0624-k60-ipa-call-site.patch").read_text()
    if "k60_ipa_probe_from_handoff" not in call_site:
        return fail("0624 does not call k60_ipa_probe_from_handoff")
    if "bsd/dev/pong_ipa.c" not in CONFFILES.read_text():
        return fail("append-conffiles.py has no pong_ipa.c entry")
    if "bsd/dev/pong_mdt.c" not in CONFFILES.read_text():
        return fail("append-conffiles.py has no pong_mdt.c entry")
    if "bsd/dev/pong_ipa_gsi.c" not in CONFFILES.read_text():
        return fail("append-conffiles.py has no pong_ipa_gsi.c entry")
    if "bsd/dev/pong_ipa_smmu.c" not in CONFFILES.read_text():
        return fail("append-conffiles.py has no pong_ipa_smmu.c entry")
    if "bsd/dev/pong_ipa_qmap.c" not in CONFFILES.read_text():
        return fail("append-conffiles.py has no pong_ipa_qmap.c entry")
    print("K60 IPA PATCH PASS 0623 carries pong_ipa.h/.c, pong_mdt.h/.c, pong_ipa_gsi, pong_ipa_smmu and pong_ipa_qmap")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())