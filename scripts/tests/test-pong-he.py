#!/usr/bin/env python3
"""Compile and run the HE (802.11ax) capability codec on the host.

Why this test exists: the station's HE Capabilities element is bytes on the wire, so the encoding, the parsing and the
MCS/NSS narrowing can be checked without a phone. The self-test exercises the element size rules (802.11ax-2021
9.4.2.248), the PPE threshold length, the walker over a vendor element and a truncated list, the crossed MCS maps (the
peer receives with our transmit map and the reverse), width clearing and the HE Operation decode. The same source is
compiled into the ath11k archive by scripts/build-k60-ath11k.py, so the anchors of that injection are pinned here too.

Run: python3 scripts/tests/test-pong-he.py
"""
from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
DIR = ROOT / "drivers" / "PongWifi" / "ath11k"
SOURCE = DIR / "pong_he.c"
HEADER = DIR / "pong_he.h"
SELFTEST = ROOT / "scripts" / "tests" / "pong-he-selftest.c"
BUILDER = ROOT / "scripts" / "build-k60-ath11k.py"
FAILS: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + name + (("  " + detail) if detail else ""))
    if not ok:
        FAILS.append(name)


def main() -> int:
    cc = os.environ.get("CC", "cc")
    if not shutil.which(cc):
        check("a host C compiler is available", False, cc)
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        exe = pathlib.Path(tmp) / "pong-he-selftest"
        cmd = [cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O1",
               "-I", str(DIR), str(SOURCE), str(SELFTEST), "-o", str(exe)]
        build = subprocess.run(cmd, capture_output=True, text=True)
        check("the codec and its self-test compile with -Werror", build.returncode == 0,
              (build.stderr.strip().splitlines() or [""])[-1][:160])
        if build.returncode != 0:
            print("summary: %d failure(s)" % len(FAILS))
            return 1
        run = subprocess.run([str(exe)], capture_output=True, text=True)
        for line in run.stdout.strip().splitlines():
            print("  " + line)
        found = re.search(r"(\d+) checks passed, (\d+) failed", run.stdout)
        check("every self-test check passes",
              run.returncode == 0 and found is not None and int(found.group(2)) == 0 and int(found.group(1)) >= 33,
              (run.stdout.strip().splitlines() or [""])[-1])

    header = HEADER.read_text(encoding="utf-8")
    for token, label in [
        ("#define PONG_HE_ELEM_ID 255", "the extension element id (255)"),
        ("#define PONG_HE_EXT_CAP 35", "the HE Capabilities extension id (35)"),
        ("#define PONG_HE_EXT_OPER 36", "the HE Operation extension id (36)"),
        ("#define PONG_HE_CAP_FIXED 17", "the 6 + 11 byte fixed capability"),
        ("#define PONG_HE_MCS_MAX 12", "three widths of MCS/NSS maps"),
        ("#define PONG_HE_PPE_PRESENT 0x80", "the PPE threshold presence bit"),
    ]:
        check("the header states " + label, token in header)

    source = SOURCE.read_text(encoding="utf-8")
    check("the MCS/NSS field is sized by the width bits",
          "if (phy[0] & PONG_HE_WIDTH_160) n += 4;" in source and
          "if (phy[0] & PONG_HE_WIDTH_80P80) n += 4;" in source)
    check("the peer receive map is bounded by our transmit map and the reverse",
          "peer->mcs[0] = intersect16(own->mcs[1], peer->mcs[0]);" in source and
          "peer->mcs[1] = intersect16(own->mcs[0], peer->mcs[1]);" in source and
          "peer->mcs[3] = intersect16(own->mcs[2], peer->mcs[3]);" in source)

    builder = BUILDER.read_text(encoding="utf-8")
    check("the ath11k build compiles the codec into the archive",
          "jobs += [(ROOT / 'drivers/PongWifi/ath11k/pong_he.c', out / 'pong_he.o', [])]" in builder)
    check("the generated station source can include the codec header",
          "'-I', str(ROOT / 'drivers/PongWifi/ath11k')," in builder)
    check("the association request carries the HE element",
          "if (g_he_ie_len) skb_put_data(skb, g_he_ie, g_he_ie_len);" in builder and
          "pong_he_write_cap_ie(&own, g_he_ie, sizeof g_he_ie);" in builder)
    check("the peer entry carries the narrowed capability and the HE Operation",
          "struct ieee80211_sta_he_cap *h = &sta->deflink.he_cap;" in builder and
          "pong_he_narrow(&own, &he_ap);" in builder and
          "g_vif->bss_conf.he_oper.params = g_he_oper.params;" in builder)

    print("summary: %d failure(s)" % len(FAILS))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
