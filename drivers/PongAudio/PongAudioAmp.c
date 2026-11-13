/* SPDX-License-Identifier: BSD-2-Clause-Patent
 *
 * K60 (Redmi K60 / mondrian / SM8475 / "cape") speaker amplifier probe.
 *
 * WHAT THIS IS: step 3 of the audio-codec task, the register-level check that
 * can be done before the ADSP exists. Every LPASS block (TX/VA macro, the
 * SoundWire master, LPI pads) needs two PRM block votes and the 0x30c clock
 * acknowledgement from the DSP first (S:PongWcd938.h:59-120), so the codec side
 * cannot be touched yet. The amplifiers, by contrast, hang off an AP-owned
 * QUPV3 serial engine: their chip id answers without the DSP. Reading it
 * decides which amplifier driver the port needs, which is the open question in
 * docs/research/audio/AMPS.md.
 *
 * WHAT IT WRITES (every other access is a read):
 *   - TLMM: GPIO56/57 -> QUP15 function, pull-up, 2 mA, only when they are not
 *     already there;
 *   - TLMM: GPIO1/GPIO3 (the two amplifier reset lines) -> released (high),
 *     only when they are not already released;
 *   - GCC:  the wrapper-2 branch votes and the SE15 DFS level;
 *   - GENI: the engine's own configuration registers.
 * No amplifier register is written. Leaving the amplifiers out of reset while
 * no bit clock runs is the state the Android boot loader leaves them in too; a
 * chip without a clock stays muted, and the fault bits are read and printed,
 * never acted on.
 *
 * WHAT IT DOES NOT DO: no LPASS access, no ADSP/PAS1/GPR call, no amplifier
 * init, no software reset, no ACF profile. Those are blocked (AMPS.md section 7).
 *
 * GATING: the probe runs only when the image is booted with pong_audio_probe=1.
 * Without the argument this file is inert: one boot-arg lookup and a return. The
 * kernel argument lives in board.toml [kernel] kernel_args, which this task may
 * not edit, so it is delivered as a merge request to the Lead.
 *
 * Eight-step status (docs/research/EIGHT-STEPS.toml, hardware.audio):
 *   (1) same model  yes  - AW882xx register file from the phk110 port driver,
 *                          GENI I2C from Pong (same SoC, SM8475)
 *   (2) official    part - mainline geni-se.h / i2c-qcom-geni.c / gcc-sm8450.c
 *   (3) decompile   yes  - live FDT pads, addresses, interrupts (CODEC/AMPS.md)
 *   (4) wide        yes  - three independent sources per constant
 *   (5) plan        yes  - AMPS.md section 5, A1-A7
 *   (6) deep        yes  - AMPS.md sections 3-4
 *   (7) verify      compile + rule gate only; needs one boot to become real
 *   (8) on device   not attempted
 */
#include <pexpert/arm64/board_config.h>
#if defined(PONG)

#include <kern/clock.h>
#include <pexpert/pexpert.h>
#include <sys/systm.h>
#include <sys/types.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#include "PongAudioRegs.h"
#include "PongAudioGeniI2c.h"
#include "PongAudioPlan.h"

extern vm_offset_t ml_io_map(vm_offset_t phys_addr, vm_size_t size);

/* Called from bsd/kern/bsd_init.c right after the audio skeleton hook
 * (patches/audio/0001-k60-audio-amp-probe.patch). Declared here so the file
 * compiles under -Wmissing-prototypes without a second header. */
int pong_audio_amp_probe(void);

#define PONG_AUDIO_IO_PAGE      ((vm_offset_t)PONG_AUDIO_WINDOW_SIZE)
#define PONG_AUDIO_PIN_COUNT    8u

/* ---- accessors ---------------------------------------------------------- */

static inline uint32_t
rd(vm_offset_t address)
{
	return *(volatile uint32_t *)address;
}

static inline void
wr(vm_offset_t address, uint32_t value)
{
	*(volatile uint32_t *)address = value;
	__asm__ volatile("dsb sy" ::: "memory");
}

static void
wait_us(uint32_t us)
{
	delay_for_interval(us, NSEC_PER_USEC);
}

/* ---- pads --------------------------------------------------------------- */

static const uint32_t probe_pads[PONG_AUDIO_PIN_COUNT] = {
	PONG_AUDIO_AMP0_RESET_GPIO, PONG_AUDIO_AMP1_RESET_GPIO,
	PONG_AUDIO_CODEC_RESET_GPIO, PONG_AUDIO_SPKSW_GPIO,
	PONG_AUDIO_I2C_SCL_GPIO, PONG_AUDIO_I2C_SDA_GPIO,
	PONG_AUDIO_AMP1_IRQ_GPIO, PONG_AUDIO_AMP0_IRQ_GPIO,
};
/* Index names, so a log line reads without a lookup. */
enum { PadAmp0Reset, PadAmp1Reset, PadCodecReset, PadSpkSwitch,
       PadI2cScl, PadI2cSda, PadAmp1Irq, PadAmp0Irq };

static vm_offset_t pad_window[PONG_AUDIO_PIN_COUNT];

static bool
pads_map(void)
{
	unsigned i;
	vm_offset_t phys;

	for (i = 0; i < PONG_AUDIO_PIN_COUNT; ++i) {
		phys = (vm_offset_t)pong_audio_pad_phys(probe_pads[i]);
		pad_window[i] = ml_io_map(phys, PONG_AUDIO_IO_PAGE);
		if (!pad_window[i]) {
			printf("PongAudio: amp probe pad map failed gpio=%u phys=0x%x\n",
			    probe_pads[i], (unsigned)phys);
			return false;
		}
	}
	return true;
}

/* Prints the state the firmware inherited. This is evidence in its own right:
 * it tells whether Android already configured the bus pads and released the
 * amplifier resets, and no write below may contradict it silently. */
static void
pads_report(void)
{
	unsigned i;

	for (i = 0; i < PONG_AUDIO_PIN_COUNT; ++i) {
		printf("PongAudio: amp pin gpio=%u cfg=0x%08x io=0x%08x\n",
		    probe_pads[i], rd(pad_window[i]), rd(pad_window[i] + PONG_AUDIO_GPIO_IO));
	}
}

/* I2C pads belong to the QUP15 function with a pull-up; the bus is idle-high.
 * If the firmware already left them there, do not rewrite them. */
static bool
i2c_pads_take(void)
{
	const unsigned pads[2] = { PadI2cScl, PadI2cSda };
	uint32_t current, next, readback;
	bool ready = true;
	unsigned i;

	for (i = 0; i < 2; ++i) {
		current = rd(pad_window[pads[i]]);
		if (pong_audio_pad_function(current) == PONG_AUDIO_GPIO_FN_QUP15) {
			printf("PongAudio: amp i2c pad gpio=%u already qup15 cfg=0x%08x\n",
			    probe_pads[pads[i]], current);
			continue;
		}
		next = pong_audio_pad_config(current, PONG_AUDIO_GPIO_PULL_UP,
		    PONG_AUDIO_GPIO_FN_QUP15, 2u, false);
		wr(pad_window[pads[i]], next);
		readback = rd(pad_window[pads[i]]);
		printf("PongAudio: amp i2c pad gpio=%u cfg=0x%08x -> 0x%08x readback=0x%08x\n",
		    probe_pads[pads[i]], current, next, readback);
		ready = ready && pong_audio_pad_function(readback) == PONG_AUDIO_GPIO_FN_QUP15;
	}
	return ready;
}

/* Releases an amplifier reset line: level first, then direction, so the pad
 * never drives a glitch into the chip (touch patch:169-174). Returns true when
 * this probe is the one that released the line. */
static bool
amp_reset_release(unsigned index, const char *name)
{
	const uint32_t current = rd(pad_window[index]);
	const uint32_t io = rd(pad_window[index] + PONG_AUDIO_GPIO_IO);
	uint32_t next;

	if (pong_audio_pad_output(current) && pong_audio_pad_out_high(io)) {
		printf("PongAudio: amp reset %s gpio=%u already released cfg=0x%08x io=0x%08x\n",
		    name, probe_pads[index], current, io);
		return false;
	}
	wr(pad_window[index] + PONG_AUDIO_GPIO_IO, 2u);
	next = pong_audio_pad_config(current, PONG_AUDIO_GPIO_PULL_NONE,
	    PONG_AUDIO_GPIO_FN_GPIO, 16u, true);
	wr(pad_window[index], next);
	printf("PongAudio: amp reset %s gpio=%u released by this probe cfg=0x%08x -> 0x%08x\n",
	    name, probe_pads[index], current, rd(pad_window[index]));
	return true;
}

/* ---- GCC ---------------------------------------------------------------- */

static vm_offset_t gcc_rcg, gcc_cbc, gcc_vote;
static unsigned gcc_misses;

static bool
gcc_map(void)
{
	gcc_rcg = ml_io_map(PONG_AUDIO_GCC_PHYS + PONG_AUDIO_GCC_RCG_WIN, PONG_AUDIO_IO_PAGE);
	gcc_cbc = ml_io_map(PONG_AUDIO_GCC_PHYS + PONG_AUDIO_GCC_CBC_WIN, PONG_AUDIO_IO_PAGE);
	gcc_vote = ml_io_map(PONG_AUDIO_GCC_PHYS + PONG_AUDIO_GCC_VOTE_WIN, PONG_AUDIO_IO_PAGE);
	if (!gcc_rcg || !gcc_cbc || !gcc_vote) {
		printf("PongAudio: amp probe gcc map failed rcg=%lx cbc=%lx vote=%lx\n",
		    (unsigned long)gcc_rcg, (unsigned long)gcc_cbc, (unsigned long)gcc_vote);
		return false;
	}
	return true;
}

/* Three one-page windows instead of Pong's 640 KiB block: io_submap is 8 MiB
 * kernel-wide (osfmk/arm/io_map.c:66) and must stay shared with everything
 * else. */
static vm_offset_t
gcc_window(uint32_t offset)
{
	uint32_t delta = 0;
	const int index = pong_audio_gcc_window(offset, &delta);

	if (index == 0) {
		return gcc_rcg + delta;
	}
	if (index == 1) {
		return gcc_cbc + delta;
	}
	if (index == 2) {
		return gcc_vote + delta;
	}
	return 0;
}

/* A miss is counted once, in the accessor: a failed read and a failed write are
 * both evidence, and counting twice would inflate the probe's own report. */
static uint32_t
gcc_read(uint32_t offset)
{
	const vm_offset_t address = gcc_window(offset);

	if (!address) {
		++gcc_misses;
		return 0u;
	}
	return rd(address);
}

static void
gcc_write(uint32_t offset, uint32_t value)
{
	const vm_offset_t address = gcc_window(offset);

	if (!address) {
		++gcc_misses;
		return;
	}
	wr(address, value);
}

/* wrapper 2: core, core_2x, m_ahb, s_ahb, s0. The same five clocks Pong votes
 * for on wrapper 1 (S:PongAudio.cpp:130-133), with the wrapper-2 enable
 * register. */
static bool
gcc_wrapper2_on(void)
{
	static const struct {
		uint32_t halt;
		const char *name;
	} clocks[] = {
		{ PONG_AUDIO_GCC_CBC_CORE,    "wrap2_core" },
		{ PONG_AUDIO_GCC_CBC_CORE_2X, "wrap2_core_2x" },
		{ PONG_AUDIO_GCC_CBC_M_AHB,   "wrap2_m_ahb" },
		{ PONG_AUDIO_GCC_CBC_S_AHB,   "wrap2_s_ahb" },
		{ PONG_AUDIO_GCC_CBC_S0,      "wrap2_s0" },
	};
	const uint32_t vote = gcc_read(PONG_AUDIO_GCC_VOTE_WRAP2);
	const uint32_t wanted = vote | PONG_AUDIO_GCC_WRAP2_MASK;
	uint32_t value;
	unsigned i, n;

	gcc_write(PONG_AUDIO_GCC_VOTE_WRAP2, wanted);
	printf("PongAudio: amp gcc vote 0x%x -> 0x%x readback 0x%x\n",
	    vote, wanted, gcc_read(PONG_AUDIO_GCC_VOTE_WRAP2));

	for (i = 0; i < sizeof clocks / sizeof clocks[0]; ++i) {
		value = gcc_read(clocks[i].halt);
		for (n = 0; n < 100u && !pong_audio_cbcr_running(value); ++n) {
			wait_us(100);
			value = gcc_read(clocks[i].halt);
		}
		printf("PongAudio: amp gcc clk %s halt=0x%08x running=%u\n",
		    clocks[i].name, value, pong_audio_cbcr_running(value) ? 1u : 0u);
		if (!pong_audio_cbcr_running(value)) {
			return false;
		}
	}
	return true;
}

/* Picks the DFS level whose source is the always-on reference with no divider,
 * exactly as the touch bring-up does (touch patch:313-324), then hands the
 * choice to the engine: the vendor DFS table is never rewritten. */
static unsigned
gcc_se15_dfs_level(void)
{
	uint32_t cfg;
	unsigned i;

	for (i = 0; i < PONG_AUDIO_GCC_DFS_LEVELS; ++i) {
		cfg = gcc_read(PONG_AUDIO_GCC_RCG_SE15 + 0x1cu + 4u * i);
		printf("PongAudio: amp gcc dfs level=%u cfg=0x%08x\n", i, cfg);
		if (pong_audio_dfs_level_ok(cfg)) {
			return i;
		}
	}
	return 0xffu;
}

/* ---- GENI serial engine ------------------------------------------------- */

static vm_offset_t se_window;

static uint32_t
se_rd(void *ctx, uint32_t reg)
{
	(void)ctx;
	return rd(se_window + reg);
}

static void
se_wr(void *ctx, uint32_t reg, uint32_t value)
{
	(void)ctx;
	wr(se_window + reg, value);
}

static PongGeniI2c bus;
static unsigned bus_recoveries;

/* A transfer whose cancel is never acknowledged leaves the state machine in
 * Cancelling or Aborting, where every later start is refused as busy - and the
 * second amplifier would then be blamed for the first one's timeout. Walk the
 * documented ladder (header: "cancel, then abort an unacknowledged cancel")
 * back to Idle before starting anything. Three steps is the longest path:
 * TxWait/WriteDone/ReadDone -> Cancelling -> Aborting -> Idle. */
static void
bus_recover(void)
{

	unsigned steps = 0;



	while (steps < 3u && pong_geni_busy(&bus)) {

		(void)pong_geni_timeout(&bus);

		++steps;

	}

	if (steps) {

		++bus_recoveries;

		printf("PongAudio: amp bus recovered a stuck transfer in %u step(s) err=%u\n",

		    steps, bus.error);

	}

}

/* Engine bring-up: mainline geni_se_init() (qcom-geni-se.c:316-352 - keep the
 * clocks on, keep GSI events off, default IO output control, force default),
 * then Pong's I2C timing writes (S:PongAudio.cpp:142), then pong_geni_prepare(),
 * which owns the FIFO packing and the interrupt mask. */
static bool
se15_open(unsigned *dfs_level)
{
	PongGeniIo io;
	uint32_t revision, proto, config = 0;
	unsigned level;

	se_window = ml_io_map(PONG_AUDIO_SE15_PHYS, PONG_AUDIO_SE15_SIZE);
	if (!se_window) {
		printf("PongAudio: amp probe se map failed phys=0x%x\n", PONG_AUDIO_SE15_PHYS);
		return false;
	}

	revision = se_rd(NULL, PONG_GENI_FW_REVISION);
	proto = (revision >> 8) & 0xffu;
	printf("PongAudio: amp se15 fw=0x%08x proto=%u disabled=0x%08x clock=0x%08x scl=0x%08x\n",
	    revision, proto, se_rd(NULL, PONG_GENI_IF_DISABLE), se_rd(NULL, PONG_GENI_CLK_CFG),
	    se_rd(NULL, PONG_GENI_SCL_COUNTERS));
	if (proto != PONG_GENI_PROTO_I2C) {
		return false;
	}

	level = gcc_se15_dfs_level();
	if (dfs_level) {
		*dfs_level = level;
	}
	if (level == 0xffu) {
		printf("PongAudio: amp se15 no DFS level with the reference source; not driving one\n");
		return false;
	}

	se_wr(NULL, 0x28u, se_rd(NULL, 0x28u) | 0x7fu);   /* SE_GENI_CGC_CTRL */
	se_wr(NULL, 0xe18u, 0u);                          /* SE_GSI_EVENT_EN: GSI unused */
	se_wr(NULL, 0x24u, 0x7fu);                        /* GENI_OUTPUT_CTRL default mask */
	se_wr(NULL, 0x20u, 1u);                           /* GENI_FORCE_DEFAULT_REG */
	se_wr(NULL, 0x7cu, level);                        /* SE_GENI_CLK_SEL: DFS level */
	se_wr(NULL, PONG_GENI_CLK_CFG, 0x21u);            /* M clock divider + enable */
	se_wr(NULL, PONG_GENI_SCL_COUNTERS, (5u << 20) | (11u << 10) | 22u);

	io.read = se_rd;
	io.write = se_wr;
	io.ctx = NULL;
	if (pong_geni_prepare(&bus, &io, PONG_AUDIO_AMP_ADDR0, &config) != 0) {
		printf("PongAudio: amp se15 prepare refused config=0x%08x\n", config);
		return false;
	}
	printf("PongAudio: amp se15 ready config=0x%08x status=0x%08x level=%u\n",
	    config, se_rd(NULL, 0x40u), level);
	return true;
}

/* Bounded transfer: 20 ms of polling, then the engine's cancel/abort ladder.
 * Boot-time context, so a plain delay keeps the code honest about both the
 * deadline and the fact that nothing else can run here. */
static int
transfer_run(void)
{
	int result;
	unsigned n;

	for (n = 0; n < 4000u; ++n) {
		result = pong_geni_poll(&bus);
		if (result != PongGeniPending) {
			return result;
		}
		wait_us(5);
	}
	(void)pong_geni_timeout(&bus);
	for (n = 0; n < 200u; ++n) {
		result = pong_geni_poll(&bus);
		if (result != PongGeniPending) {
			return result;
		}
		wait_us(5);
	}
	return PongGeniFailed;
}

/* One amplifier register read: a 1-byte write of the register number that holds
 * the stop condition, then a 2-byte read; the first byte arrives in rx[7:0], so
 * the value is big-endian (S:PongAudio.cpp:108-110). */
static int
amp_read(uint8_t address, uint8_t reg, uint16_t *value)
{
	const uint8_t pointer = reg;
	int result;

	bus_recover();
	bus.address = address;
	bus.error = PongGeniOk;
	if (pong_geni_start_read_bytes(&bus, &pointer, 1, 2) != 0) {
		return -1;
	}
	result = transfer_run();
	if (result != PongGeniDone) {
		return result == PongGeniFailed ? -(int)bus.error - 10 : -1;
	}
	*value = pong_audio_amp_value(bus.rx);
	return 0;
}

static uint16_t
amp_read_or(uint8_t address, uint8_t reg, uint16_t fallback)
{
	uint16_t value = fallback;
	const int result = amp_read(address, reg, &value);

	if (result != 0) {
		printf("PongAudio: amp read failed addr=0x%x reg=0x%02x result=%d err=%u irq=0x%08x\n",
		    address, reg, result, bus.error, bus.error_status);
	}
	return value;
}

static unsigned
amp_probe_one(unsigned index, uint8_t address, bool reset_by_us)
{
	uint16_t chip = 0, status, mask, control, i2s, debug, vbat, pvdd, temp, vcal;
	uint16_t f4, f3, l4, l3;
	int result = -1;
	unsigned attempt;

	for (attempt = 0; attempt < 3u; ++attempt) {
		result = amp_read(address, AW_REG_ID, &chip);
		if (result == 0) {
			break;
		}
		wait_us(5000);
	}
	if (result != 0) {
		printf("PongAudio: amp%u addr=0x%x no answer after 3 reads result=%d err=%u irq=0x%08x reset=%s\n",
		    index, address, result, bus.error, bus.error_status,
		    reset_by_us ? "released-by-probe" : "already-released-or-untouched");
		return 0;
	}

	/* Everything below is a read. AW_SYSINT (0x02) is deliberately skipped:
	 * reading it clears the interrupt status, and this probe leaves state
	 * alone. */
	status = amp_read_or(address, AW_REG_SYSST, 0xffffu);
	mask = amp_read_or(address, AW_REG_SYSINTM, 0xffffu);
	control = amp_read_or(address, AW_REG_SYSCTRL, 0xffffu);
	i2s = amp_read_or(address, AW_REG_I2SCTRL, 0xffffu);
	debug = amp_read_or(address, AW_REG_DBGCTRL, 0xffffu);
	vbat = amp_read_or(address, AW_REG_VBAT, 0xffffu);
	pvdd = amp_read_or(address, AW_REG_PVDD, 0xffffu);
	temp = amp_read_or(address, AW_REG_TEMP, 0xffffu);
	vcal = amp_read_or(address, AW_REG_VSNTM1, 0xffffu);
	f4 = amp_read_or(address, AW_REG_EFRH4, 0xffffu);
	f3 = amp_read_or(address, AW_REG_EFRH3, 0xffffu);
	l4 = amp_read_or(address, AW_REG_EFRL4, 0xffffu);
	l3 = amp_read_or(address, AW_REG_EFRL3, 0xffffu);

	printf("PongAudio: amp%u addr=0x%x id=0x%04x chip=%s status=0x%04x faults=0x%04x pll=%u\n",
	    index, address, chip, pong_audio_amp_name(chip), status,
	    (unsigned)(status & AW_SYSST_FAULTS),
	    (unsigned)((status & (AW_SYSST_CLKS | AW_SYSST_PLLS)) == (AW_SYSST_CLKS | AW_SYSST_PLLS)));
	printf("PongAudio: amp%u mask=0x%04x ctrl=0x%04x i2s=0x%04x dbg=0x%04x vbat=0x%04x pvdd=0x%04x temp=0x%04x\n",
	    index, mask, control, i2s, debug, vbat, pvdd, temp);
	printf("PongAudio: amp%u vcal=0x%04x fuse=0x%04x/0x%04x/0x%04x/0x%04x\n",
	    index, vcal, f4, f3, l4, l3);
	return 1;
}

/* ---- entry point -------------------------------------------------------- */

int
pong_audio_amp_probe(void)
{
	uint32_t mode = 0;
	unsigned level = 0xffu;
	unsigned found0, found1;
	bool released0, released1;

	if (!PE_parse_boot_argn("pong_audio_probe", &mode, sizeof mode) || mode != 1u) {
		return 0;
	}

	printf("PongAudio: amp probe start (amplifiers are read-only; AMPS.md A1-A7)\n");

	if (!pads_map()) {
		return -1;
	}
	pads_report();

	if (!gcc_map()) {
		return -1;
	}
	if (!gcc_wrapper2_on()) {
		printf("PongAudio: amp probe stop: QUPV3 wrapper 2 clocks not running\n");
		return -1;
	}
	if (!i2c_pads_take()) {
		printf("PongAudio: amp probe stop: I2C pads did not take the QUP15 function\n");
		return -1;
	}
	if (!se15_open(&level)) {
		printf("PongAudio: amp probe stop: serial engine 15 not usable\n");
		return -1;
	}

	/* Only now that the bus answers is it worth releasing a reset line: doing it
	 * earlier and failing would leave an amplifier awake with no clock. */
	released0 = amp_reset_release(PadAmp0Reset, "amp0");
	released1 = amp_reset_release(PadAmp1Reset, "amp1");
	wait_us(5000);

	found0 = amp_probe_one(0, PONG_AUDIO_AMP_ADDR0, released0);
	found1 = amp_probe_one(1, PONG_AUDIO_AMP_ADDR1, released1);

	printf("PongAudio: amp probe done found=%u/2 transfers=%u failed=%u timeouts=%u stray=%u recovered=%u gcc_misses=%u\n",
	    found0 + found1, bus.done, bus.failed, bus.timeouts, bus.stray, bus_recoveries,
	    gcc_misses);
	return (int)(found0 + found1);
}

#endif /* PONG */
