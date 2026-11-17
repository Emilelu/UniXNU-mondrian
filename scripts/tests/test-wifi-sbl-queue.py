#!/usr/bin/env python3
"""Pin the official BHI_EXECENV/SBL path in the K60 MHI builder.

Why this test exists: c7 reaches MHI READY with ee=0 and exec_env=1 (SBL) but
never receives an EE event. The official MhiBoot.c polls BHI_EXECENV and pushes
the BHIe image when it reads SBL. The K60 builder mirrors that with a bounded
poll and a one-shot latch; this test keeps the queue bounded, keeps the latch,
and keeps the direct AMSS call out of the boot path.

Run: python3 scripts/tests/test-wifi-sbl-queue.py
"""
from __future__ import annotations

import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
BUILDER = ROOT / "scripts" / "build-k60-ath11k.py"
FAILS = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + name + (("  " + detail) if detail else ""))
    if not ok:
        FAILS.append(name)


def main() -> int:
    text = BUILDER.read_text(encoding="utf-8")

    check("MHI header grows one pong_sbl_pushed field",
          text.count("bool pong_sbl_pushed;") == 1,
          "count=%d" % text.count("bool pong_sbl_pushed;"))
    check("boot path queues only when fbc and not latched",
          text.count("if (mhi_cntrl->fbc_download && !mhi_cntrl->pong_sbl_pushed) {") == 1)
    check("poll is bounded to 200 samples",
          "for (i = 0; i < 200; i++) {" in text)
    check("poll checks register validity before reading",
          "if (!MHI_REG_ACCESS_VALID(mhi_cntrl->pm_state))" in text)
    check("poll reads BHI_EXECENV",
          "ee = mhi_get_exec_env(mhi_cntrl);" in text)
    check("SBL queues the stock transition once",
          text.count("mhi_queue_state_transition(mhi_cntrl, DEV_ST_TRANSITION_SBL);") == 1)
    check("SBL logs BHI_STATUS before queueing",
          "BHI_STATUS=%#x; queueing the SBL transition" in text)
    check("SBL gates the queue on BHI_STATUS success",
          "status = bhi >> 30;" in text and
          "if (status != BHI_STATUS_SUCCESS) {" in text)
    check("SBL stops on BHI_STATUS error",
          "if (status == BHI_STATUS_ERROR) {" in text)
    check("pm SBL handler has a one-shot latch",
          text.count("if (mhi_cntrl->pong_sbl_pushed) {") == 1 and
          text.count("mhi_cntrl->pong_sbl_pushed = true;") == 1)
    check("boot path does not call the download directly",
          "mhi_download_amss_image(mhi_cntrl);" not in text)

    # A built tree may be supplied for an end-to-end source-shape check.  The
    # repository test still runs when no build is present: the builder anchors
    # above are the source of truth, and the generated files are a projection.
    build = pathlib.Path(os.environ.get("K60_SBL_BUILD_DIR",
                                        "E:/k60-work/build/wifi-sbl-queue-v2"))
    boot = build / "mhi" / "boot.c"
    pm = build / "mhi" / "pm.c"
    header = build / "pinned" / "linux" / "mhi.h"
    if boot.is_file() and pm.is_file() and header.is_file():
        btext = boot.read_text(encoding="utf-8")
        ptext = pm.read_text(encoding="utf-8")
        htext = header.read_text(encoding="utf-8")
        check("generated boot.c has the bounded SBL queue",
              "device is in SBL without an EE event" in btext and
              "status = bhi >> 30;" in btext and
              "if (status != BHI_STATUS_SUCCESS) {" in btext and
              "mhi_queue_state_transition(mhi_cntrl, DEV_ST_TRANSITION_SBL);" in btext)
        check("generated pm.c keeps the latch",
              "mhi_cntrl->pong_sbl_pushed = true;" in ptext)
        check("generated mhi.h has the latch field",
              "bool pong_sbl_pushed;" in htext)
    else:
        print("  SKIP  generated tree not present at %s" % build)

    print("summary: %d failure(s)" % len(FAILS))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
