#!/usr/bin/env python3
"""Static/unit check: K60 MHI programs its contexts before offering the SBL image.

The proven WCN7850 loader rejected an image offered immediately after reset with
no MHI contexts programmed.  Its working sequence waits 200 ms, writes the MHI
context registers and only then offers the image.  K60 must copy that sequence
instead of relying on mhi_ready_state_transition(), which runs only after the
image has already been handed to the boot loader.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "scripts/build-k60-ath11k.py"
DEFAULT_BOOT = Path("/opt/k60/trees/k60build/wifi/ath11k-mhi-preload/mhi/boot.c")


def check_generator(text):
    failures = []

    def need(condition, message):
        if not condition:
            failures.append(message)

    need("static int nw_mhi_pre_load(struct mhi_controller *mhi_cntrl)" in text,
         "generator does not define nw_mhi_pre_load")
    need("static bool done;" in text, "pre-load is not once-only")
    need("msleep(200);" in text, "pre-load does not settle for 200 ms")
    need("ret = mhi_init_mmio(mhi_cntrl);" in text,
         "pre-load does not program MHI contexts")
    need("Pong MHI: contexts programmed before image" in text,
         "pre-load has no info log")
    need("ret = nw_mhi_pre_load(mhi_cntrl);" in text,
         "boot.c patch does not call the pre-load")
    call = text.find("ret = nw_mhi_pre_load(mhi_cntrl);")
    if call >= 0:
        block = text[call:call + 500]
        need("goto error_fw_load;" in block, "pre-load failure does not fail closed")
    # The call must be in the skip_req_fw path before fw_load_type is read,
    # because that is the point immediately before mhi_load_image_bhie().
    if call >= 0:
        skip = text.find("skip_req_fw:")
        need(skip >= 0 and call > skip, "pre-load is not on the skip_req_fw path")
    return failures


def check_generated(text):
    failures = []

    def need(condition, message):
        if not condition:
            failures.append(message)

    marker = "static int nw_mhi_pre_load(struct mhi_controller *mhi_cntrl)"
    end = "/* Setup RDDM vector table for RDDM transfer and program RXVEC */"
    if marker not in text or end not in text or text.index(marker) > text.index(end):
        failures.append("generated boot.c does not define nw_mhi_pre_load before RDDM setup")
    else:
        function = text[text.index(marker):text.index(end)]
        need("msleep(200);" in function, "generated pre-load does not settle")
        need("mhi_init_mmio(mhi_cntrl)" in function, "generated pre-load does not program contexts")
        need("static bool done;" in function, "generated pre-load is not once-only")

    call = "ret = nw_mhi_pre_load(mhi_cntrl);"
    if call not in text:
        failures.append("generated boot.c has no pre-load call")
        return failures
    call_at = text.index(call)
    fw_type = text.find("fw_load_type = mhi_fw_load_type_get(mhi_cntrl);", call_at)
    load = text.find("mhi_load_image_bhie(mhi_cntrl", call_at)
    need(fw_type > call_at, "pre-load call is after fw_load_type selection")
    need(load > call_at, "pre-load call is after the image is offered")
    block = text[call_at:call_at + 500]
    need("goto error_fw_load;" in block, "generated pre-load failure does not fail closed")
    return failures


def mutant(text, old, new):
    assert old in text, old
    return text.replace(old, new, 1)


def main(generated=None):
    generator = GENERATOR.read_text()
    failures = check_generator(generator)
    if failures:
        for failure in failures:
            print("FAIL:", failure)
        return 1

    if generated:
        boot = Path(generated).read_text()
        failures = check_generated(boot)
        if failures:
            for failure in failures:
                print("FAIL:", failure)
            return 1
        cases = [
            ("missing settle", mutant(boot, "\tmsleep(200);", "")),
            ("missing context write", mutant(boot, "ret = mhi_init_mmio(mhi_cntrl);", "ret = 0;")),
            ("missing call", mutant(boot, "ret = nw_mhi_pre_load(mhi_cntrl);", "")),
            ("not fail closed", mutant(boot, "goto error_fw_load;", "goto skip_req_fw;")),
            ("wrong init helper", mutant(boot, "ret = mhi_init_mmio(mhi_cntrl);", "ret = mhi_init_dev_ctxt(mhi_cntrl);")),
        ]
        for name, bad in cases:
            if not check_generated(bad):
                print("FAIL: test did not reject", name)
                return 1
        print("PASS: MHI contexts are programmed before the SBL image is offered (%d negative cases)" % len(cases))
    else:
        print("PASS: generator carries the MHI pre-load sequence (generated boot.c not supplied)")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--generated", type=Path, default=DEFAULT_BOOT)
    args = parser.parse_args()
    sys.exit(main(args.generated if args.generated.is_file() else None))
