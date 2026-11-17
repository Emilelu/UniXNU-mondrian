#!/usr/bin/env python3
"""Pin the official BHI_EXECENV/SBL direct-push and mission-poll path.

Why this test exists: c7 reaches MHI READY with ee=0 and exec_env=1 (SBL) but
never receives an EE event. The official MhiBoot.c polls BHI_EXECENV and sends
the BHIe image when it reads SBL. The first K60 attempt queued
DEV_ST_TRANSITION_SBL and failed during teardown. The direct successor proves
the BHIe transfer works, but the host keeps cached ee=1 while the device is
already AMSS/M0. This test pins the next single-variable step: poll
BHI_EXECENV after the direct AMSS download and cache AMSS/WFW before
mhi_sync_power_up resumes.

Run: python3 scripts/tests/test-wifi-sbl-mission.py
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
    check("boot path pushes only when fbc and not latched",
          text.count("if (mhi_cntrl->fbc_download && !mhi_cntrl->pong_sbl_pushed) {") == 1)
    check("poll is bounded to 200 samples",
          "for (i = 0; i < 200; i++) {" in text)
    check("poll checks register validity before reading",
          "if (!MHI_REG_ACCESS_VALID(mhi_cntrl->pm_state))" in text)
    check("poll reads BHI_EXECENV",
          "ee = mhi_get_exec_env(mhi_cntrl);" in text)
    check("SBL sets the cached execution environment before the push",
          "mhi_cntrl->ee = MHI_EE_SBL;" in text)
    check("SBL logs BHI_STATUS before pushing",
          "BHI_STATUS=%#x; pushing the AMSS image" in text)
    check("SBL gates the push on BHI_STATUS success",
          "status = bhi >> 30;" in text and
          "if (status != BHI_STATUS_SUCCESS) {" in text)
    check("SBL stops on BHI_STATUS error",
          "if (status == BHI_STATUS_ERROR) {" in text)
    check("SBL calls the AMSS download exactly once in the boot path",
          text.count("amss_ret = mhi_download_amss_image(mhi_cntrl);") == 1,
          "count=%d" % text.count("amss_ret = mhi_download_amss_image(mhi_cntrl);"))
    check("SBL no longer queues the stock transition",
          "mhi_queue_state_transition(mhi_cntrl, DEV_ST_TRANSITION_SBL);" not in text)
    check("pm SBL handler has a one-shot latch",
          text.count("if (mhi_cntrl->pong_sbl_pushed) {") == 1 and
          text.count("mhi_cntrl->pong_sbl_pushed = true;") == 2)
    check("BHIE wait keeps the transfer status and sequence for the log",
          "u32 tx_status = 0, sequence_id;" in text and
          "Pong MHI: bhie tx_status=%#x seq=%#x expected=%#x ret=%d" in text)
    check("mission poll declares its own counters",
          "int i, j, amss_ret;" in text)
    check("mission poll runs only after a successful AMSS load",
          "amss_ret = mhi_download_amss_image(mhi_cntrl);" in text and
          "if (!amss_ret) {" in text)
    check("mission poll is bounded to 500 samples",
          "for (j = 0; j < 500; j++) {" in text)
    check("mission poll reads BHI_EXECENV",
          "enum mhi_ee_type mission = mhi_get_exec_env(mhi_cntrl);" in text)
    check("mission poll accepts AMSS or WFW",
          "if (mission == MHI_EE_AMSS || mission == MHI_EE_WFW) {" in text)
    check("mission poll caches the new execution environment",
          "mhi_cntrl->ee = mission;" in text)
    check("mission poll wakes the power-up waiter",
          "wake_up_all(&mhi_cntrl->state_event);" in text)
    check("mission poll logs the cached EE",
          "exec_env=%d after AMSS download; cached ee updated" in text)

    # A built tree may be supplied for an end-to-end source-shape check. The
    # repository test still runs when no build is present: the builder anchors
    # above are the source of truth, and the generated files are a projection.
    build = pathlib.Path(os.environ.get("K60_SBL_BUILD_DIR",
                                        "E:/k60-work/build/wifi-sbl-mission"))
    boot = build / "mhi" / "boot.c"
    pm = build / "mhi" / "pm.c"
    header = build / "pinned" / "linux" / "mhi.h"
    if boot.is_file() and pm.is_file() and header.is_file():
        btext = boot.read_text(encoding="utf-8")
        ptext = pm.read_text(encoding="utf-8")
        htext = header.read_text(encoding="utf-8")
        check("generated boot.c has the direct SBL push",
              "BHI_STATUS=%#x; pushing the AMSS image" in btext and
              "status = bhi >> 30;" in btext and
              "if (status != BHI_STATUS_SUCCESS) {" in btext and
              "amss_ret = mhi_download_amss_image(mhi_cntrl);" in btext and
              "mhi_queue_state_transition(mhi_cntrl, DEV_ST_TRANSITION_SBL);" not in btext)
        check("generated boot.c has the mission poll",
              "for (j = 0; j < 500; j++) {" in btext and
              "if (mission == MHI_EE_AMSS || mission == MHI_EE_WFW) {" in btext and
              "mhi_cntrl->ee = mission;" in btext)
        check("generated boot.c logs the BHIE transfer status",
              "bhie tx_status=%#x seq=%#x expected=%#x ret=%d" in btext)
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
