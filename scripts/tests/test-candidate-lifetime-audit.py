#!/usr/bin/env python3
"""Source-shape checks for docs/research/wifi/CANDIDATE-LIFETIME-AUDIT.md.

This is an offline anchor test, not a lifetime proof. It reads the exact Linux,
shim and board sources named by the audit and exits nonzero when an anchor
disappears. It does not compile, run the generator, or touch a device.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

CHECKS = 0


def check(condition: bool, what: str) -> None:
    global CHECKS
    CHECKS += 1
    if not condition:
        raise AssertionError(what)


def body(text: str, start: str, end: str = "\n}\n") -> str:
    at = text.index(start)
    stop = text.index(end, at)
    return text[at:stop]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--linux", default="E:/k60-work/impl/wifi/work/src/linux-7.0.14")
    ap.add_argument("--shim", default="E:/k60-work/impl/wifi/work/src/UniXNU-sheng/drivers/Ath12kWifi")
    ap.add_argument("--repo", default=str(pathlib.Path(__file__).resolve().parents[2]))
    a = ap.parse_args()
    linux = pathlib.Path(a.linux)
    shim = pathlib.Path(a.shim)
    repo = pathlib.Path(a.repo)
    init = (linux / "drivers/bus/mhi/host/init.c").read_text(encoding="utf-8")
    boot = (linux / "drivers/bus/mhi/host/boot.c").read_text(encoding="utf-8")
    pm = (linux / "drivers/bus/mhi/host/pm.c").read_text(encoding="utf-8")
    amhi = (linux / "drivers/net/wireless/ath/ath11k/mhi.c").read_text(encoding="utf-8")
    apci = (linux / "drivers/net/wireless/ath/ath11k/pci.c").read_text(encoding="utf-8")
    nwmhi = (shim / "src/nw_mhi.c").read_text(encoding="utf-8")
    nwpci = (shim / "src/nw_pci.c").read_text(encoding="utf-8")
    pong = (repo / "drivers/PongWifi/ath11k/PongAth11k.c").read_text(encoding="utf-8")
    plat = (repo / "drivers/PongWifi/PongWifiPlatform.cpp").read_text(encoding="utf-8")

    check("ring->alloc_size = len + (len - 1);" in init, "aligned ring alloc_size")
    check("dma_alloc_coherent(mhi_cntrl->cntrl_dev, ring->alloc_size" in init, "ring coherent alloc")
    check("ring->iommu_base = (ring->dma_handle + (len - 1)) & ~(len - 1);" in init, "ring iommu align")
    deinit = body(init, "static void mhi_deinit_dev_ctxt")
    for needle in (
        "ring->alloc_size,",
        "mhi_ctxt->cmd_ctxt",
        "mhi_ctxt->er_ctxt",
        "mhi_ctxt->chan_ctxt",
        "kfree(mhi_ctxt);",
        "mhi_cntrl->mhi_ctxt = NULL;",
    ):
        check(needle in deinit, "context free: " + needle)
    check("ring->ctxt_wp = NULL" not in deinit, "deinit leaves ctxt_wp stale")
    check("ring->rp = NULL" not in deinit, "deinit leaves rp stale")
    unprepare = body(init, "void mhi_unprepare_after_power_down")
    check("mhi_free_bhie_table(mhi_cntrl, mhi_cntrl->fbc_image);" in unprepare, "unprepare frees fbc")
    check("mhi_deinit_dev_ctxt(mhi_cntrl);" in unprepare, "unprepare deinit contexts")
    check("ret = mhi_init_mmio(mhi_cntrl);" in pm and "if (ret) {" in pm, "READY checks init_mmio")
    check("mhi_alloc_bhie_table(mhi_cntrl, &mhi_cntrl->rddm_image," in init, "RDDM ignored alloc anchor")

    unreg = body(nwmhi, "void nw_mhi_unregister")
    check("mhi_unregister_controller(" in unreg, "shim unregisters controller")
    check("mhi_unprepare_after_power_down(" not in unreg, "shim unreg lacks unprepare")
    start = body(amhi, "int ath11k_mhi_start")
    check("mhi_prepare_for_power_up(" in start and "mhi_sync_power_up(" in start, "ath11k start calls")
    check("mhi_unprepare_after_power_down(" not in start, "ath11k start failure lacks unprepare")
    stop = body(amhi, "void ath11k_mhi_stop")
    check("mhi_power_down(" in stop and "mhi_unprepare_after_power_down(" in stop, "ath11k stop unprepares")
    check("ath11k_mhi_unregister(ab_pci);" in apci, "probe error unregisters")
    pdown = body(apci, "static void ath11k_pci_power_down")
    check("ath11k_mhi_stop(ab_pci, is_suspend);" in pdown, "power_down stops MHI")
    free_region = body(apci, "static void ath11k_pci_free_region")
    check("pci_iounmap(pci_dev, ab->mem);" in free_region and "ab->mem = NULL;" in free_region, "free_region no-op unmap")

    check("void *pci_iomap(struct pci_dev *d, int bar, unsigned long max) { (void)d; (void)bar; (void)max; return nw_board->bar; }" in nwpci, "pci_iomap returns board bar")
    check("void pci_iounmap(struct pci_dev *d, void *p) { (void)d; (void)p; }" in nwpci, "pci_iounmap no-op")

    nwstart = body(pong, "int nw_wifi_start")
    check("pong_ath11k_pci_init();" in nwstart, "start calls board init")
    check("pong_ath11k_pci_exit();" not in nwstart, "start failure does not exit board")
    nwstop = body(pong, "void nw_wifi_stop")
    check("if (!running) return;" in nwstop and "pong_ath11k_pci_exit();" in nwstop, "stop gated by running")

    check("void dmaFree(size_t,void *p,uint64_t)" in plat and "blocks[i].at==off" in plat and "blocks[i].used=false" in plat, "dmaFree offset-only")
    dmaalloc = body(plat, "void *dmaAlloc(size_t n,uint64_t *bus)")
    check("for(unsigned i=0;i<blockCount;i++)" in dmaalloc, "dmaAlloc first-fit")
    window = plat[plat.index("struct Window {"):plat.index("Window gcc")]
    check("map(kIOMapAnywhere|kIOMapInhibitCache)" in window, "Window map flags")
    check("close" not in window, "Window has no close")
    check("if(!parf.open(0x1c00000,0x3000))return false;" in plat, "parf map")
    check(plat.index("hostMmioReady=true;") < plat.index("if(!dbi.open(0x60000000,0x1000)"), "hostMmioReady before DBI")
    done = body(plat, " done: stopped=1;", "thread_block(THREAD_CONTINUE_NULL);")
    check("dbi.w(MsiEnable,0)" in done and "parf.w(0x22c,0)" in done, "done masks MSI/PARF")
    for forbidden in ("dmaFree(", "IOFreeData(", "pci_iounmap(", "mhi_unprepare_after_power_down(", "nw_mhi_unregister("):
        check(forbidden not in done, "done retains: " + forbidden)
    check("void halt() {stopped=1;" in plat and "DMA retained until reset" in plat, "halt retains DMA")

    check("segments = DIV_ROUND_UP(alloc_size, seg_size) + 1;" in boot, "fbc segment count")
    alloc = body(boot, "int mhi_alloc_bhie_table")
    check("mhi_buf->buf = dma_alloc_coherent(" in alloc, "fbc per-entry DMA")
    check("error_alloc_segment:" in alloc and "dma_free_coherent(" in alloc, "fbc failure cleanup")
    freebhie = body(boot, "void mhi_free_bhie_table")
    check("image_info->entries" in freebhie and "dma_free_coherent(" in freebhie, "bhie free entries")

    print(f"OK {CHECKS} source-shape checks")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print("FAIL " + str(exc), file=sys.stderr)
        raise SystemExit(1)
