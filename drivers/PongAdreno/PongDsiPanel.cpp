/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/*
 * K60 (mondrian / SM8475) DSI panel bring-up + brightness.
 *
 * Background (research, not guesswork):
 *  - K60 has no discrete backlight IC. The FDT only exposes
 *    pm8350c GPIO "lcd_backlight_ctrl" plus panel DCS dimming
 *    (docs/reference/FEATURES-DRIVERS-RESEARCH-2026-10-31.md:106).
 *  - The verified bring-up order recorded from the user's own notes is
 *    "disp_bring_up -> 0x11 (Sleep Out) -> 0x29 (Display On) -> 0x51 (brightness)"
 *    (same file, quoting PORT-STATUS-K60.md:1069/1131/1195/1292).
 *  - The command transport is the same one zizhan uses on the same SM8475
 *    DSI 2.x controller at 0x0ae94000
 *    (docs/plans/120HZ-PORT-PLAN.md section 3.2, derived from
 *     zizhan:drivers/PongAdreno/PongAdrenoScanout.cpp:670-733).
 *
 * Without this, the software framebuffer does submit frames
 * ("K60 DISPLAY: first frame presented") but the panel never receives
 * 0x11/0x29/0x51, so SpringBoard reports screen=0 dim=1 and the display
 * stays black.
 */

#include "PongDsiPanel.h"

#include <IOKit/IOLib.h>
#include <IOKit/IOMemoryDescriptor.h>
#include <pexpert/pexpert.h>
#include <kern/clock.h>

namespace {

enum : uint32_t {
	DsiPa = 0x0ae94000u,
	DsiLen = 0x400,
	DsiHwVersion = 0x000,
	DsiCtrl = 0x004,
	DsiStatus = 0x008,
	DsiCmdDmaCtrl = 0x03c,
	DsiDmaCmdLength = 0x04c,
	DsiTrigCtrl = 0x084,
	DsiCmdDmaSwTrigger = 0x090,
	DsiIntCtrl = 0x110,
	DsiTpgCtrl = 0x15c,
	DsiTpgCmdDmaInitVal = 0x17c,
	DsiTpgDmaFifoReset = 0x1ec,
};

constexpr uint32_t DsiDmaBusy = 1u << 1;
constexpr uint32_t DsiMdpBusy = 1u << 2;
constexpr uint32_t DsiIntDmaDone = 1u << 0;
constexpr uint32_t DsiIntEnableBits = 0xaaaaaaaau;
constexpr uint32_t DsiTpgFifoOn = 3u << 16 | 1u << 2 | 1u << 1;
constexpr uint32_t DsiTrigSw = 4u;
constexpr uint32_t DsiMaxPayload = 60;

vm_offset_t dsi_map;
IOMemoryDescriptor *dsi_desc;
IOMemoryMap *dsi_map_obj;
unsigned dsi_failures;
unsigned dsi_mdp_waits;
unsigned panel_on_done;
unsigned panel_brightness = 0;
int panel_on_result = -100;

/* K60 FDT: MDSS0xae00000, INTF pages0x35000..0x38000. Same SM8475
 * zizhan dpuBus/intfRate require GCC_DISP_AHB and DISP_CC_MDSS_AHB before
 * any MDSS access: scanning alone does not imply the register clock is on.
 * Never enable clocks; only INTF1's known inherited autorefresh may change. */
IOMemoryDescriptor *probe_desc[7];
IOMemoryMap *probe_maps[7];
vm_offset_t probe_va[7];
bool probe_enabled;
uint64_t probe_started,probe_previous;
uint32_t probe_frames[4];
uint16_t probe_te[2];
uint64_t probe_sampled[4];
bool cadence_pending,cadence_verify;
constexpr uint32_t IntfFrameCount=0xac,IntfTearAutorefresh=0x2b4;
constexpr uint32_t CadenceInherited=0x8000003cu,CadenceEveryFrame=0x80000001u;

void panel_log(const char *fmt, ...)
{
	char text[220];
	va_list ap;
	va_start(ap, fmt);
	vsnprintf(text, sizeof(text), fmt, ap);
	va_end(ap);
	IOLog("%s", text);
}

inline uint32_t dsi_rd(uint32_t off) { return *(volatile uint32_t *)(dsi_map + off); }
inline void dsi_wr(uint32_t off, uint32_t v) { *(volatile uint32_t *)(dsi_map + off) = v; }

vm_offset_t probe_page(unsigned slot,uint32_t physical)
{
    if(!probe_va[slot]) {
        probe_desc[slot]=IOMemoryDescriptor::withPhysicalAddress(physical,4096,
            slot==4?kIODirectionInOut:kIODirectionIn);
        if(probe_desc[slot])probe_maps[slot]=probe_desc[slot]->map();
        if(probe_maps[slot])probe_va[slot]=probe_maps[slot]->getVirtualAddress();
    }
    return probe_va[slot];
}
uint32_t probe_read(vm_offset_t base,unsigned offset)
{
    return *reinterpret_cast<volatile uint32_t *>(base+offset);
}

/* Qualcomm-authored SM8475 register facts, mirrored (not a matched K60
 * vendor release): crdroidandroid/android_kernel_xiaomi_sm8475-modules
 * commit 98f72d675c093d88eab7bbe1162da725c580a428,
 * qcom/opensource/display-drivers/msm/sde/sde_hw_intf.c:79-110,675-711:
 * INTF-relative 0x2b4, bit31 enable, low16 frame_count; hardware setter
 * writes enabled count directly. sde_connector.c:36-37 says refresh occurs
 * after FRAME_CNT frames. Count1 removes the inherited 60-frame divider;
 * it does not change panel TE frequency or establish a 120Hz display mode.
 * https://github.com/crdroidandroid/android_kernel_xiaomi_sm8475-modules/blob/98f72d675c093d88eab7bbe1162da725c580a428/qcom/opensource/display-drivers/msm/sde/sde_hw_intf.c#L675-L711
 * Only adopt the live command-mode ABL state after a real INTF1 counter
 * advance. Unknown states belong to their owner and are never rewritten. */
void cadence_update(vm_offset_t base,uint32_t frames,uint32_t delta,uint64_t milliseconds,
    vm_offset_t gcc,vm_offset_t dc,vm_offset_t power)
{
    const uint32_t refresh=probe_read(base,IntfTearAutorefresh);
    if(cadence_verify) {
        panel_log("K60 CADENCE: INTF1 post-write ms=%llu frames=%u delta=%u auto=%#x readback=%s\n",
            milliseconds,frames,delta,refresh,refresh==CadenceEveryFrame?"match":"changed");
        if(refresh!=CadenceEveryFrame || (delta && delta<0x80000000u))cadence_verify=false;
        return;
    }
    if(!cadence_pending || !delta || delta>=0x80000000u)return;
    cadence_pending=false; /* exactly one qualified attempt, never a per-frame writer */
    if(!dsi_map || (dsi_rd(DsiHwVersion)>>28)!=2 || (dsi_rd(DsiCtrl)&5u)!=5u ||
        probe_read(base,0x288)!=0x00180064u || refresh!=CadenceInherited) {
        panel_log("K60 CADENCE: INTF1 active delta=%u auto=%#x; inherited command state changed, no write\n",
            delta,refresh);
        return;
    }
    /* Recheck the existing clock/power guards immediately before the sole
     * write, and re-read the exact state to avoid overwriting another owner. */
    if((probe_read(gcc,4)&0x80000000u) || (probe_read(dc,0xa4)&0x80000000u) ||
        !(probe_read(power,0)&0x80000000u)) {
        panel_log("K60 CADENCE: INTF1 clock/power state changed; no write\n");
        return;
    }
    const uint32_t before=probe_read(base,IntfTearAutorefresh);
    if(before!=CadenceInherited) {
        panel_log("K60 CADENCE: INTF1 auto changed to %#x; no write\n",before);
        return;
    }
    *reinterpret_cast<volatile uint32_t *>(base+IntfTearAutorefresh)=(before&~0xffffu)|1u;
    __asm__ volatile("dsb sy" ::: "memory");
    const uint32_t after=probe_read(base,IntfTearAutorefresh);
    panel_log("K60 CADENCE: INTF1 autorefresh count60->1 before=%#x after=%#x readback=%s prior_ms=%llu frames=%u delta=%u\n",
        before,after,after==CadenceEveryFrame?"match":"mismatch",milliseconds,frames,delta);
    if(after==CadenceEveryFrame) {
        probe_frames[1]=probe_read(base,IntfFrameCount);
        probe_sampled[1]=mach_absolute_time();
        cadence_verify=true; /* report actual subsequent transfers, never software FPS */
    }
}

bool dsi_init(void)
{
	if (!dsi_map) {
		dsi_desc = IOMemoryDescriptor::withPhysicalAddress(DsiPa, DsiLen, kIODirectionInOut);
		if (dsi_desc) {
			dsi_map_obj = dsi_desc->map();
		}
		if (dsi_map_obj) {
			dsi_map = (vm_offset_t)dsi_map_obj->getVirtualAddress();
		}
	}
	if (!dsi_map) {
		panel_log("K60 PANEL: no mapping of DSI0 at %#x\n", DsiPa);
		return false;
	}
	const uint32_t ver = dsi_rd(DsiHwVersion);
	const uint32_t ctl = dsi_rd(DsiCtrl);
	panel_log("K60 PANEL: DSI0 version=0x%08x ctrl=0x%08x status=0x%08x dma_ctrl=0x%08x tpg=0x%08x\n",
	    ver, ctl, dsi_rd(DsiStatus), dsi_rd(DsiCmdDmaCtrl), dsi_rd(DsiTpgCtrl));
	/* Same self-check as zizhan: a probe for "is this a running command-mode
	 * DSI 2.x controller", which also tells us whether ABL still owns it. */
	if ((ver >> 28) != 2 || (ctl & 5u) != 5u) {
		panel_log("K60 PANEL: DSI0 is not a running command-mode DSI 2.x controller; no DCS\n");
		return false;
	}
	return true;
}

/* One DCS write: short 0x05/0x15 or long 0x39, virtual channel 0.
 * FIFO flow copied from zizhan's dsiDcs (the same controller). */
int dsi_dcs(const uint8_t *buf, uint32_t len, bool lp)
{
	uint32_t words[2 + (DsiMaxPayload + 3) / 4];
	uint32_t n = 0, i;

	if (!dsi_map || !len || len > DsiMaxPayload || dsi_failures >= 3) {
		return -1;
	}
	if (len <= 2) {
		words[n++] = 1u << 31 | (len == 1 ? 0x05u : 0x15u) << 16 |
		    (len == 2 ? uint32_t(buf[1]) << 8 : 0u) | buf[0];
	} else {
		words[n++] = 1u << 31 | 1u << 30 | 0x39u << 16 | len;
		for (i = 0; i < len; i += 4) {
			uint32_t w = 0;
			for (uint32_t b = 0; b < 4 && i + b < len; ++b) {
				w |= uint32_t(buf[i + b]) << (8 * b);
			}
			words[n++] = w;
		}
	}
	const uint32_t bytes = n * 4;
	if (n & 1u) {
		words[n++] = 0; /* the FIFO takes an even number of words */
	}

	int rc = 0;
	for (i = 0; i < 250 && (dsi_rd(DsiStatus) & DsiDmaBusy); ++i) {
		IODelay(20);
	}
	if (dsi_rd(DsiStatus) & DsiDmaBusy) {
		rc = -2;
	} else {
		for (i = 0; i < 1000 && (dsi_rd(DsiStatus) & DsiMdpBusy); ++i) {
			IODelay(20);
		}
		if (i == 1000) {
			++dsi_mdp_waits;
		}
		const uint32_t tpg = dsi_rd(DsiTpgCtrl);
		const uint32_t dma = dsi_rd(DsiCmdDmaCtrl);
		const uint32_t trig = dsi_rd(DsiTrigCtrl);
		if ((trig & 0xfu) != DsiTrigSw) {
			dsi_wr(DsiTrigCtrl, (trig & ~0xfu) | DsiTrigSw);
		}
		dsi_wr(DsiIntCtrl, (dsi_rd(DsiIntCtrl) & DsiIntEnableBits) | DsiIntDmaDone);
		dsi_wr(DsiTpgCtrl, DsiTpgFifoOn);
		for (uint32_t w = 0; w < n; ++w) {
			dsi_wr(DsiTpgCmdDmaInitVal, words[w]);
		}
		dsi_wr(DsiCmdDmaCtrl, (dma & ~(1u << 31 | 1u << 30 | 1u << 26)) | 1u << 28 |
		    (lp ? 1u << 26 : 0u));
		dsi_wr(DsiDmaCmdLength, bytes);
		dsi_wr(DsiCmdDmaSwTrigger, 1);
		bool done = false;
		for (i = 0; i < 1250 && !done; ++i) { /* 25 ms */
			done = (dsi_rd(DsiIntCtrl) & DsiIntDmaDone) != 0;
			if (!done) {
				IODelay(20);
			}
		}
		if (!(dsi_rd(DsiStatus) & DsiDmaBusy)) {
			dsi_wr(DsiIntCtrl, (dsi_rd(DsiIntCtrl) & DsiIntEnableBits) | DsiIntDmaDone);
			dsi_wr(DsiTpgCtrl, 0);
			dsi_wr(DsiTpgDmaFifoReset, 1);
			IODelay(1);
			dsi_wr(DsiTpgDmaFifoReset, 0);
			dsi_wr(DsiTpgCtrl, tpg);
			dsi_wr(DsiCmdDmaCtrl, dma);
			if ((trig & 0xfu) != DsiTrigSw) {
				dsi_wr(DsiTrigCtrl, trig);
			}
		}
		if (!done) {
			rc = -3;
		}
	}
	if (rc) {
		++dsi_failures;
		panel_log("K60 PANEL: DCS 0x%02x (%u bytes) failed %d status=0x%x int=0x%x\n",
		    buf[0], len, rc, dsi_rd(DsiStatus), dsi_rd(DsiIntCtrl));
	}
	return rc;
}

int dsi_write1(uint8_t cmd, uint8_t value)
{
	uint8_t buf[2] = { cmd, value };
	if (value == 0xff && cmd == 0x51) {
		return dsi_dcs(buf, 2, false);
	}
	return dsi_dcs(buf, 2, false);
}

int dsi_write0(uint8_t cmd)
{
	return dsi_dcs(&cmd, 1, false);
}

} // namespace

extern "C" bool pong_panel_bringup(void)
{
	if (panel_on_done) {
		return panel_on_result == 0;
	}
	panel_on_done = 1;
	panel_on_result = -1;

	if (!dsi_init()) {
		return false;
	}
	panel_log("K60 PANEL: sending DCS 0x11 (Sleep Out)\n");
	int rc = dsi_write0(0x11);
	if (rc) {
		panel_on_result = rc;
		return false;
	}
	IODelay(120 * 1000); /* panel needs >=120 ms after Sleep Out */

	panel_log("K60 PANEL: sending DCS 0x29 (Display On)\n");
	rc = dsi_write0(0x29);
	if (rc) {
		panel_on_result = rc;
		return false;
	}
	IODelay(20 * 1000);

	panel_log("K60 PANEL: sending DCS 0x51 0xff (brightness max)\n");
	rc = dsi_write1(0x51, 0xff);
	if (rc) {
		panel_on_result = rc;
		return false;
	}
	panel_brightness = 0xff;
	panel_on_result = 0;
	panel_log("K60 PANEL: bring-up complete (0x11/0x29/0x51), MDP-busy waits=%u\n", dsi_mdp_waits);
    unsigned probe=0;
    probe_enabled=PE_parse_boot_argn("gprobe",&probe,sizeof(probe)) && probe==1;
    cadence_pending=true;
	return true;
}

extern "C" void pong_panel_sample(void)
{
    if(panel_on_result!=0 || (!probe_enabled && !cadence_pending && !cadence_verify))return;
    const uint64_t now=mach_absolute_time();
    uint64_t elapsed=0;
    if(probe_started) {
        absolutetime_to_nanoseconds(now-probe_started,&elapsed);
        if(elapsed>=120*NSEC_PER_SEC) {
            if(cadence_pending || cadence_verify)
                panel_log("K60 CADENCE: bounded correction window expired pending=%u verify=%u\n",
                    unsigned(cadence_pending),unsigned(cadence_verify));
            probe_enabled=false;cadence_pending=false;cadence_verify=false;return;
        }
        absolutetime_to_nanoseconds(now-probe_previous,&elapsed);
        if(elapsed<5*NSEC_PER_SEC)return;
    } else probe_started=now;
    for(unsigned i=0;i<4;++i)if(probe_sampled[i] && now-probe_sampled[i]>now-probe_previous)probe_sampled[i]=0;
    probe_previous=now;
    const vm_offset_t gcc=probe_page(0,0x00137000);
    if(!gcc){if(probe_enabled)panel_log("K60 CADENCE: no GCC mapping; no display register reads\n");return;}
    const uint32_t gate=probe_read(gcc,4);
    if(gate&0x80000000u) {
        if(probe_enabled)panel_log("K60 CADENCE: GCC_DISP_AHB off=%#x; skip DISPCC/MDSS\n",gate);return;
    }
    const vm_offset_t dc=probe_page(1,0x0af08000),power=probe_page(2,0x0af09000);
    if(!dc || !power){if(probe_enabled)panel_log("K60 CADENCE: no DISPCC mapping; skip MDSS\n");return;}
    const uint32_t ahb=probe_read(dc,0xa4),gdsc=probe_read(power,0);
    if((ahb&0x80000000u) || !(gdsc&0x80000000u)) {
        if(probe_enabled)panel_log("K60 CADENCE: MDSS gate=%#x power=%#x; skip MDSS\n",ahb,gdsc);return;
    }
    for(unsigned i=0;i<4;++i) {
        if(!probe_enabled && i!=1)continue;
        const vm_offset_t base=probe_page(3+i,0x0ae35000+i*4096);
        if(!base){probe_sampled[i]=0;if(probe_enabled)panel_log("K60 CADENCE: INTF%u mapping unavailable\n",i);continue;}
        const bool previous=probe_sampled[i]!=0;
        uint64_t span=0;
        if(previous)absolutetime_to_nanoseconds(now-probe_sampled[i],&span);
        const uint64_t milliseconds=span/NSEC_PER_MSEC;
        const uint32_t frames=probe_read(base,IntfFrameCount);
        const uint32_t delta=previous?frames-probe_frames[i]:0;
        probe_frames[i]=frames;
        probe_sampled[i]=now;
        if(probe_enabled && (i==1 || i==2)) {
            const uint16_t te=uint16_t(probe_read(base,0x298)>>16);
            const uint16_t count=previous?uint16_t(te-probe_te[i-1]):0;
            probe_te[i-1]=te;
            panel_log("K60 CADENCE: INTF%u ms=%llu frames=%u delta=%u te=%u delta=%u auto=%#x sync=%#x\n",
                i,milliseconds,frames,delta,unsigned(te),unsigned(count),probe_read(base,IntfTearAutorefresh),probe_read(base,0x288));
        } else if(probe_enabled)panel_log("K60 CADENCE: INTF%u ms=%llu frames=%u delta=%u\n",i,milliseconds,frames,delta);
        if(i==1 && (cadence_pending || cadence_verify))cadence_update(base,frames,delta,milliseconds,gcc,dc,power);
    }
}

extern "C" int pong_panel_set_brightness(uint32_t level)
{
	if (!panel_on_done || panel_on_result != 0) {
		return -1;
	}
	if (level > 0xff) {
		level = 0xff;
	}
	const int rc = dsi_write1(0x51, (uint8_t)level);
	if (!rc) {
		panel_brightness = level;
	}
	return rc;
}

extern "C" uint32_t pong_panel_brightness(void)
{
	return panel_brightness;
}

extern "C" int pong_panel_status(void)
{
	return panel_on_result;
}
