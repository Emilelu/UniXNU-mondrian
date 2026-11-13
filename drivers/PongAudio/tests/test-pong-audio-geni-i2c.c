/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Host test: the GENI I2C state machine the amplifier probe drives, and the
 * register-map constants it uses. Both are pure computation over a fake
 * register window, so they can be proven on this machine without a device -
 * the same reasoning as scripts/tests/test-k60-fat.c (PITFALLS.md:4178).
 *
 * What is covered:
 *   - PongAudioRegs.h address arithmetic (TLMM window, GCC windows, GPIO 88).
 *   - pong_geni_prepare: the four reject conditions and every register it writes.
 *   - write path: command composition, TX watermark -> FIFO, completion.
 *   - read path: 1-byte register write holding stop, then the 2-byte read; the
 *     command word of each phase, RX_LEN, and the FIFO word landing in g->rx.
 *   - failure paths: bus error bits, empty RX FIFO, CMD_DONE in TxWait, and the
 *     cancel -> abort -> timeout ladder.
 *   - the byte order the AW882xx chip id arrives in.
 *   - stuck-bus recovery: a refused start while the machine is stuck, and the
 *     three-step ladder that returns it to Idle (what PongAudioAmp.c does
 *     before every transfer so one dead amplifier cannot fail the other).
 *   - every decision helper in PongAudioPlan.h: pad addressing and the pad
 *     config word, the CBCR "running" test, GCC window routing, DFS level
 *     acceptance, and the chip-id table. Those are the parts of the probe that
 *     decide what to write, so they are pinned here rather than at boot.
 *
 * Run: drivers/PongAudio/tests/run-tests.sh
 */
#include <stdio.h>
#include <string.h>

#include "PongAudioGeniI2c.h"
#include "PongAudioPlan.h"
#include "PongAudioRegs.h"

static int fails;
static int cases;

static void
expect(int cond, const char *what)
{
	cases++;
	if (!cond) {
		printf("FAIL %s\n", what);
		fails++;
	}
}

static void
expect_eq(unsigned long got, unsigned long want, const char *what)
{
	cases++;
	if (got != want) {
		printf("FAIL %s: got 0x%lx want 0x%lx\n", what, got, want);
		fails++;
	}
}

/* ---- fake serial engine -------------------------------------------------- */

#define FAKE_WORDS 0x1000u          /* the engine window is 16 KiB */

typedef struct {
	uint32_t reg[FAKE_WORDS];
	uint32_t fifo[8];               /* TX FIFO words, in the order written */
	unsigned fifo_words;
	unsigned writes;                /* every write, for "was it touched" */
	uint32_t last_write_reg;
} FakeSe;

static FakeSe se;

static uint32_t
fake_read(void *ctx, uint32_t reg)
{
	FakeSe *s = ctx;

	return s->reg[(reg >> 2) & (FAKE_WORDS - 1)];
}

static void
fake_write(void *ctx, uint32_t reg, uint32_t value)
{
	FakeSe *s = ctx;
	const unsigned index = (reg >> 2) & (FAKE_WORDS - 1);

	if (reg == PONG_GENI_TX_FIFO && s->fifo_words < 8u) {
		s->fifo[s->fifo_words++] = value;
	}
	s->reg[index] = value;
	s->writes++;
	s->last_write_reg = reg;
}

static void
fake_reset(void)
{
	memset(&se, 0, sizeof se);
	/* A usable engine: I2C firmware, clock on, timing programmed. */
	se.reg[PONG_GENI_FW_REVISION >> 2] = PONG_GENI_PROTO_I2C << 8;
	se.reg[PONG_GENI_CLK_CFG >> 2] = 0x21u;
	se.reg[PONG_GENI_SCL_COUNTERS >> 2] = (5u << 20) | (11u << 10) | 22u;
}

static PongGeniI2c bus;

static void
bus_reset(void)
{
	PongGeniIo io;
	uint32_t config = 0;

	fake_reset();
	io.read = fake_read;
	io.write = fake_write;
	io.ctx = &se;
	(void)pong_geni_prepare(&bus, &io, PONG_AUDIO_AMP_ADDR0, &config);
	se.fifo_words = 0;
	se.writes = 0;
}

/* ---- register map -------------------------------------------------------- */

static void
register_map_cases(void)
{
	/* L:1347 pinctrl@f000000 reg 0xf000000 + 0x1000000; the GPIO block is
	 * TLMM base + 0x100000 (S:PongAudio.cpp:120). */
	expect_eq(PONG_AUDIO_TLMM_PHYS + PONG_AUDIO_TLMM_GPIO_OFF, 0x0f100000u,
	    "TLMM GPIO block base");
	/* GPIO 88 (AMP0 irq) must stay inside the pinctrl node's window. */
	expect_eq(PONG_AUDIO_TLMM_PHYS + PONG_AUDIO_TLMM_GPIO_OFF +
	    PONG_AUDIO_GPIO_STRIDE * PONG_AUDIO_AMP0_IRQ_GPIO, 0x0f158000u,
	    "GPIO 88 register address");
	expect(PONG_AUDIO_TLMM_GPIO_OFF + PONG_AUDIO_GPIO_STRIDE * 88u < 0x1000000u,
	    "GPIO 88 inside pinctrl@f000000");
	/* GCC: the three one-page windows must contain every offset used. */
	expect_eq(PONG_AUDIO_GCC_PHYS + PONG_AUDIO_GCC_RCG_WIN + 0x14u,
	    PONG_AUDIO_GCC_PHYS + PONG_AUDIO_GCC_RCG_SE15, "RCG window covers SE15 cmd_rcgr");
	expect_eq(PONG_AUDIO_GCC_PHYS + PONG_AUDIO_GCC_CBC_WIN + 0x280u,
	    PONG_AUDIO_GCC_PHYS + PONG_AUDIO_GCC_CBC_CORE, "CBC window covers wrap2 core");
	expect_eq(PONG_AUDIO_GCC_PHYS + PONG_AUDIO_GCC_CBC_WIN + 0x28cu,
	    PONG_AUDIO_GCC_PHYS + PONG_AUDIO_GCC_CBC_CORE_2X, "CBC window covers core 2x");
	expect_eq(PONG_AUDIO_GCC_PHYS + PONG_AUDIO_GCC_VOTE_WIN + 0x10u,
	    PONG_AUDIO_GCC_PHYS + PONG_AUDIO_GCC_VOTE_WRAP2, "vote window covers 0x62010");
	/* Five branches: core, core_2x, m_ahb, s_ahb, s0 -> mask 0x1f. */
	expect(PONG_AUDIO_GCC_WRAP2_MASK == 0x1fu, "wrapper 2 branch mask");
	/* Amplifier register addresses from the live FDT. */
	expect_eq(PONG_AUDIO_AMP_ADDR0, 0x34u, "left amplifier address");
	expect_eq(PONG_AUDIO_AMP_ADDR1, 0x35u, "right amplifier address");
	/* AW882xx status bits used to judge a probe. */
	expect_eq(AW_SYSST_FAULTS, 0xc86au, "AW882xx fault mask");
	expect_eq(AW_SYSST_PLLS | AW_SYSST_CLKS, 0x11u, "PLL/clock lock pair");
	expect_eq(AW_SYSCTRL_PWDN | AW_SYSCTRL_AMPPD | AW_SYSCTRL_HMUTE, 0x103u,
	    "AW882xx power-down/mute bits");
	/* The codec side: reset pad and TX core clock id. */
	expect_eq(PONG_AUDIO_CODEC_RESET_GPIO, 43u, "codec reset GPIO");
	expect_eq(PONG_AUDIO_TX_CORE_CLK_ID, 0x30cu, "TX core clock id");
}

/* ---- pong_geni_prepare --------------------------------------------------- */

static void
prepare_cases(void)
{
	PongGeniIo io;
	PongGeniI2c local;
	uint32_t config = 0;

	fake_reset();
	se.reg[PONG_GENI_SE_IRQ_EN >> 2] = 0x10u;
	io.read = fake_read;
	io.write = fake_write;
	io.ctx = &se;

	expect_eq((unsigned long)pong_geni_prepare(&local, &io, 0x35, &config), 0u,
	    "prepare accepts a usable engine");
	expect_eq(config, (3u << 24) | 0x21u, "prepare reports proto and clock");
	expect_eq(local.address, 0x35u, "prepare keeps the slave address");
	expect_eq(se.reg[PONG_GENI_DMA_MODE >> 2], 0u, "FIFO mode, not DMA");
	expect_eq(se.reg[PONG_GENI_TX_PACK0 >> 2], 0x7f8feu, "TX pack 0");
	expect_eq(se.reg[PONG_GENI_TX_PACK1 >> 2], 0xffefeu, "TX pack 1");
	expect_eq(se.reg[PONG_GENI_RX_PACK0 >> 2], 0x7f8feu, "RX pack 0");
	expect_eq(se.reg[PONG_GENI_RX_PACK1 >> 2], 0xffefeu, "RX pack 1");
	expect_eq(se.reg[PONG_GENI_BYTE_GRAN >> 2], 0u, "byte granularity");
	expect_eq(se.reg[PONG_GENI_M_IRQ_CLEAR >> 2], 0xffffffffu, "clears stale IRQs");
	expect_eq(se.reg[PONG_GENI_M_IRQ_EN >> 2], PONG_GENI_M_IRQ_WANTED, "enables exactly its own IRQs");
	expect_eq(se.reg[PONG_GENI_SE_IRQ_EN >> 2], 0x10u | PONG_GENI_SE_M_IRQ_EN,
	    "adds the master interrupt to the SE mask");

	/* Each reject condition on its own. */
	fake_reset();
	se.reg[PONG_GENI_FW_REVISION >> 2] = 1u << 8;   /* SPI firmware */
	expect_eq((unsigned long)pong_geni_prepare(&local, &io, 0x34, NULL), (unsigned long)-1,
	    "rejects an engine that is not running I2C");

	fake_reset();
	se.reg[PONG_GENI_IF_DISABLE >> 2] = 1u;
	expect_eq((unsigned long)pong_geni_prepare(&local, &io, 0x34, NULL), (unsigned long)-1,
	    "rejects a disabled interface");

	fake_reset();
	se.reg[PONG_GENI_CLK_CFG >> 2] = 0x20u;         /* clock off */
	expect_eq((unsigned long)pong_geni_prepare(&local, &io, 0x34, NULL), (unsigned long)-1,
	    "rejects an engine whose clock is off");

	fake_reset();
	se.reg[PONG_GENI_SCL_COUNTERS >> 2] = 0u;
	expect_eq((unsigned long)pong_geni_prepare(&local, &io, 0x34, NULL), (unsigned long)-1,
	    "rejects an engine with no timing programmed");
}

/* ---- write path ---------------------------------------------------------- */

static void
write_cases(void)
{
	bus_reset();
	expect_eq((unsigned long)pong_geni_start_write(&bus, AW_REG_VBAT, 0x34), 0u,
	    "start a register write");
	expect_eq(bus.phase, PongGeniTxWait, "write waits for the FIFO");
	expect_eq(se.reg[PONG_GENI_TX_LEN >> 2], 2u, "TX length is two bytes");
	expect_eq(se.reg[PONG_GENI_M_CMD0 >> 2],
	    (PONG_GENI_OP_WRITE << 27) | (0x34u << 9), "write command word");
	expect_eq(se.reg[PONG_GENI_TX_WATERMARK >> 2], 1u, "asks for one FIFO word");

	/* A second start while busy is refused, not queued. */
	expect_eq((unsigned long)pong_geni_start_write(&bus, AW_REG_VBAT, 1), (unsigned long)-1,
	    "refuses a second transfer");

	expect_eq(pong_geni_event(&bus, PONG_GENI_M_TX_WATERMARK), PongGeniPending,
	    "watermark alone does not complete");
	expect_eq(se.fifo_words, 1u, "one FIFO word written");
	expect_eq(se.fifo[0], 0x3421u, "byte 0 in bits 7:0, byte 1 in bits 15:8");
	expect_eq(bus.phase, PongGeniWriteDone, "write leaves the FIFO phase");

	expect_eq(pong_geni_event(&bus, PONG_GENI_M_CMD_DONE), PongGeniDone,
	    "command done completes a write");
	expect_eq(bus.done, 1u, "counts one success");
	expect_eq(bus.failed, 0u, "counts no failure");
	expect_eq(bus.phase, PongGeniIdle, "back to idle");
}

/* ---- read path ----------------------------------------------------------- */

static void
read_cases(void)
{
	bus_reset();
	expect_eq((unsigned long)pong_geni_start_read_bytes(&bus, (const uint8_t *)"\x00", 1, 2), 0u,
	    "start a two-byte register read");
	expect_eq(bus.phase, PongGeniTxWait, "read starts with the pointer write");
	expect_eq(se.reg[PONG_GENI_M_CMD0 >> 2],
	    (PONG_GENI_OP_WRITE << 27) | (0x34u << 9) | PONG_GENI_STOP_STRETCH,
	    "pointer write holds the stop condition");
	expect_eq(se.reg[PONG_GENI_TX_LEN >> 2], 1u, "one pointer byte");

	(void)pong_geni_event(&bus, PONG_GENI_M_TX_WATERMARK);
	expect_eq(se.fifo_words, 1u, "pointer byte in one FIFO word");
	expect_eq(se.fifo[0], 0x00u, "register 0x00 in bits 7:0");

	/* Done of the write phase turns into the read command, not a completion. */
	expect_eq(pong_geni_event(&bus, PONG_GENI_M_CMD_DONE), PongGeniPending,
	    "the pointer write is not the end of a read");
	expect_eq(bus.phase, PongGeniReadDone, "now reading");
	expect_eq(se.reg[PONG_GENI_RX_LEN >> 2], 2u, "asks for two bytes");
	expect_eq(se.reg[PONG_GENI_M_CMD0 >> 2],
	    (PONG_GENI_OP_READ << 27) | (0x34u << 9), "read command releases the stop");

	/* The chip id as the part sends it: high byte first. */
	se.reg[PONG_GENI_RX_FIFO_STATUS >> 2] = 2u;
	se.reg[PONG_GENI_RX_FIFO >> 2] = 0x1321u;
	expect_eq(pong_geni_event(&bus, PONG_GENI_M_CMD_DONE), PongGeniDone,
	    "read completes");
	expect_eq(bus.rx, 0x1321u, "FIFO word kept");
	expect_eq(bus.data, 0x21u, "first byte in bits 7:0");

	/* Empty RX FIFO is a failure, not a zero value. */
	bus_reset();
	(void)pong_geni_start_read_bytes(&bus, (const uint8_t *)"\x01", 1, 1);
	(void)pong_geni_event(&bus, PONG_GENI_M_TX_WATERMARK);
	(void)pong_geni_event(&bus, PONG_GENI_M_CMD_DONE);
	se.reg[PONG_GENI_RX_FIFO_STATUS >> 2] = 0u;
	expect_eq(pong_geni_event(&bus, PONG_GENI_M_CMD_DONE), PongGeniFailed,
	    "empty RX FIFO fails");
	expect_eq(bus.error, PongGeniErrNoData, "empty RX FIFO error code");
}

/* ---- failure paths ------------------------------------------------------- */

static void
failure_cases(void)
{
	bus_reset();
	(void)pong_geni_start_write(&bus, AW_REG_ID, 0x55);
	expect_eq(pong_geni_event(&bus, PONG_GENI_M_TX_WATERMARK | PONG_GENI_M_CMD_FAILURE),
	    PongGeniFailed, "a bus error bit fails the transfer");
	expect_eq(bus.error, PongGeniErrBus, "bus error code");
	expect_eq(bus.error_status, PONG_GENI_M_TX_WATERMARK | PONG_GENI_M_CMD_FAILURE,
	    "bus error status is kept for the log");
	expect_eq(bus.failed, 1u, "counts one failure");

	/* Done in the FIFO phase means the watermark never came: the data was not
	 * sent, so this is an error rather than a success. */
	bus_reset();
	(void)pong_geni_start_write(&bus, AW_REG_ID, 0x55);
	expect_eq(pong_geni_event(&bus, PONG_GENI_M_CMD_DONE), PongGeniFailed,
	    "completion without the watermark is an error");
	expect_eq(bus.error, PongGeniErrState, "state error code");

	/* An interrupt nobody asked for, while idle, is counted and ignored. */
	bus_reset();
	expect_eq(pong_geni_event(&bus, PONG_GENI_M_CMD_DONE), PongGeniPending,
	    "idle ignores stray interrupts");
	expect_eq(bus.stray, 1u, "counts the stray interrupt");

	/* Cancel, then abort, then give up. */
	bus_reset();
	(void)pong_geni_start_write(&bus, AW_REG_ID, 0x55);
	expect_eq(pong_geni_timeout(&bus), PongGeniPending, "timeout cancels first");
	expect_eq(bus.phase, PongGeniCancelling, "waiting for the cancel");
	expect_eq(se.reg[PONG_GENI_M_CMD_CTRL >> 2], PONG_GENI_CMD_CTRL_CANCEL, "cancel written");
	expect_eq(bus.timeouts, 1u, "counts one timeout");
	expect_eq(pong_geni_timeout(&bus), PongGeniPending, "then aborts");
	expect_eq(bus.phase, PongGeniAborting, "waiting for the abort");
	expect_eq(se.reg[PONG_GENI_M_CMD_CTRL >> 2], PONG_GENI_CMD_CTRL_ABORT, "abort written");
	expect_eq(pong_geni_timeout(&bus), PongGeniFailed, "then fails the transfer");
	expect_eq(bus.error, PongGeniErrTimeout, "timeout error code");
	expect_eq(bus.phase, PongGeniIdle, "idle after the timeout ladder");

	/* An acknowledged cancel also ends the transfer. */
	bus_reset();
	(void)pong_geni_start_write(&bus, AW_REG_ID, 0x55);
	(void)pong_geni_timeout(&bus);
	expect_eq(pong_geni_event(&bus, PONG_GENI_M_CMD_CANCEL), PongGeniFailed,
	    "an acknowledged cancel fails the transfer");
	expect_eq(bus.error, PongGeniErrTimeout, "cancel keeps the timeout code");

	/* A timeout while idle does nothing. */
	bus_reset();
	expect_eq(pong_geni_timeout(&bus), PongGeniPending, "timeout while idle is a no-op");
	expect_eq(bus.timeouts, 0u, "no timeout counted while idle");

	/* A write of more than 8 bytes, or a zero-length one, is refused. */
	bus_reset();
	expect_eq((unsigned long)pong_geni_start_write_bytes(&bus, (const uint8_t *)"012345678", 9),
	    (unsigned long)-1, "refuses more than 8 bytes");
	expect_eq((unsigned long)pong_geni_start_write_bytes(&bus, (const uint8_t *)"0", 0),
	    (unsigned long)-1, "refuses an empty write");
	expect_eq((unsigned long)pong_geni_start_read_bytes(&bus, (const uint8_t *)"01234", 5, 1),
	    (unsigned long)-1, "refuses a 5-byte pointer");
	expect_eq((unsigned long)pong_geni_start_read_bytes(&bus, (const uint8_t *)"0", 1, 5),
	    (unsigned long)-1, "refuses a 5-byte read");
}

/* ---- poll ---------------------------------------------------------------- */

static void
poll_cases(void)
{
	bus_reset();
	se.reg[PONG_GENI_M_IRQ_STATUS >> 2] = PONG_GENI_M_TX_WATERMARK;
	(void)pong_geni_start_write(&bus, AW_REG_VBAT, 0x34);
	/* poll reads the status, clears it, then feeds it to the state machine. */
	expect_eq(pong_geni_poll(&bus), PongGeniPending, "poll feeds the watermark");
	expect_eq(se.reg[PONG_GENI_M_IRQ_CLEAR >> 2], PONG_GENI_M_TX_WATERMARK,
	    "poll clears what it read");
	expect_eq(bus.phase, PongGeniWriteDone, "poll advanced the transfer");
}

/* ---- the AW882xx chip id byte order -------------------------------------- */

/* The part sends the high byte first; GENI packs the first byte of a FIFO word
 * into bits 7:0 (PongAudioGeniI2c.h). PongAudioPlan.h decodes it; the encoder
 * here is the inverse, so a change on either side shows up as a failure rather
 * than a wrong chip name. */
static uint32_t
encode_amp_value(uint16_t value)
{
	/* high byte first -> the high byte is the low byte of the FIFO word */
	return (uint32_t)(((value & 0xffu) << 8) | ((value >> 8) & 0xffu));
}

static void
chip_id_cases(void)
{
	static const uint16_t ids[] = { 0x2113, 0x2013, 0x2032, 0x2049, 0x2055,
	                                0x2066, 0x2071, 0x2183, 0x2308 };
	unsigned i;

	for (i = 0; i < sizeof ids / sizeof ids[0]; ++i) {
		expect(pong_audio_amp_value(encode_amp_value(ids[i])) == ids[i],
		    "chip id survives the byte order");
	}
	expect_eq(pong_audio_amp_value(0x1321u), 0x2113u,
	    "AW88261 from FIFO word 0x1321");
	expect(strcmp(pong_audio_amp_name(0x2113u), "AW88261") == 0,
	    "the known part is named");
	expect(strcmp(pong_audio_amp_name(0x1234u), "unknown") == 0,
	    "an unknown id is not guessed into a part");
}

/* ---- stuck-bus recovery --------------------------------------------------- */

/* PongAudioAmp.c walks the timeout ladder back to Idle before every transfer.
 * Without that step an unanswered cancel leaves the engine in Cancelling, and
 * the next start is refused as busy - the second amplifier would then be
 * blamed for the first one's timeout. These cases pin both halves: that a
 * stuck machine really refuses work, and that the ladder clears it within the
 * three steps the driver allows. */
static void
recovery_cases(void)
{

	const uint8_t pointer = 0x00;
	unsigned steps;

	bus_reset();
	(void)pong_geni_start_read_bytes(&bus, &pointer, 1, 2);
	(void)pong_geni_timeout(&bus);
	expect_eq(bus.phase, PongGeniCancelling, "stuck after an unanswered cancel");
	expect_eq((unsigned long)pong_geni_start_read_bytes(&bus, &pointer, 1, 2),
	    (unsigned long)-1, "a stuck bus refuses the next start");
	expect(pong_geni_busy(&bus) != 0, "the bus reports busy while stuck");

	for (steps = 0; steps < 3u && pong_geni_busy(&bus); ++steps) {
		(void)pong_geni_timeout(&bus);
	}
	expect_eq(steps, 2u, "two more steps clear a stuck cancel");
	expect_eq(bus.phase, PongGeniIdle, "idle again after recovery");
	expect_eq(bus.timeouts, 1u, "recovery steps do not invent timeouts");
	expect_eq((unsigned long)pong_geni_start_read_bytes(&bus, &pointer, 1, 2), 0ul,
	    "the bus takes a transfer again after recovery");

	/* The longest path: a live transfer needs cancel, abort, then the give-up
	 * that returns to Idle. Three steps is exactly what bus_recover() allows. */
	bus_reset();
	(void)pong_geni_start_write(&bus, AW_REG_ID, 0x55);
	for (steps = 0; steps < 5u && pong_geni_busy(&bus); ++steps) {
		(void)pong_geni_timeout(&bus);
	}
	expect_eq(steps, 3u, "three steps is the longest ladder");
	expect_eq(bus.phase, PongGeniIdle, "idle after the longest ladder");
	expect_eq(bus.timeouts, 1u, "only the live transfer was counted");
}

/* ---- decision helpers ---------------------------------------------------- */

/* These are the probe's choices, not the engine's: which pad address to map,
 * what config word to write, whether a branch clock is running, which GCC
 * window holds an offset, whether a DFS level is usable, and what to call a
 * chip. Every one of them is a pure function over numbers, so the whole set is
 * provable here (eight-step step 4 "verify"). */
static void
plan_cases(void)
{
	uint32_t delta = 0;
	uint32_t cfg;

	/* Pad addressing: the GPIO block is TLMM base + 0x100000, one 0x1000
	 * block per pad (S:PongAudio.cpp:120-129). */
	expect_eq(pong_audio_pad_phys(1u), 0x0f101000u, "amp0 reset pad address");
	expect_eq(pong_audio_pad_phys(3u), 0x0f103000u, "amp1 reset pad address");
	expect_eq(pong_audio_pad_phys(43u), 0x0f12b000u, "codec reset pad address");
	expect_eq(pong_audio_pad_phys(88u), 0x0f158000u, "amp0 irq pad address");
	expect_eq(pong_audio_pad_phys(88u) - pong_audio_pad_phys(1u), 87u * 0x1000u,
	    "pads are one 0x1000 block apart");
	expect(pong_audio_pad_phys(118u) + 0x1000u <= 0x0f000000u + 0x1000000u,
	    "every pad stays inside the pinctrl node window");

	/* Pad config: pull [1:0], function [5:2], drive [8:6], output [9]. The
	 * upper bits survive, and APPS ownership is only claimed when the pad
	 * says an eGPIO exists (touch patch:148-166). */
	cfg = pong_audio_pad_config(0u, PONG_AUDIO_GPIO_PULL_UP,
	    PONG_AUDIO_GPIO_FN_QUP15, 2u, false);
	expect_eq(cfg, 3u | (1u << 2), "i2c pad: pull-up, qup15, no drive");
	cfg = pong_audio_pad_config(0u, PONG_AUDIO_GPIO_PULL_NONE,
	    PONG_AUDIO_GPIO_FN_GPIO, 16u, true);
	expect_eq(cfg, (7u << 6) | (1u << 9), "reset pad: 16 mA, output, no pull");
	expect_eq(pong_audio_pad_config(0xfffff800u, 0u, 0u, 2u, false) & 0xfffff800u,
	    0xfffff800u, "bits above the documented field survive");
	expect_eq(pong_audio_pad_config(PONG_AUDIO_GPIO_EGPIO_EXISTS, 0u, 0u, 2u, false),
	    PONG_AUDIO_GPIO_EGPIO_EXISTS | PONG_AUDIO_GPIO_APPS_CTRL,
	    "APPS ownership only when the pad has an eGPIO");
	expect_eq(pong_audio_pad_config(0u, 0u, 0u, 0u, false), 0u,
	    "a zero drive does not go negative");
	expect_eq(pong_audio_pad_config(0u, 0u, 0u, 3u, false), 0u,
	    "3 mA rounds down to the 2 mA field value");
	expect_eq(pong_audio_pad_config(0u, 0u, 0u, 4u, false), 1u << 6,
	    "4 mA is the next field step");
	expect_eq(pong_audio_pad_config(0u, 0u, 0u, 16u, false), 7u << 6,
	    "16 mA is the top of the field");

	expect_eq(pong_audio_pad_function(0x3u | (1u << 2)), 1u, "reads the function");
	expect_eq(pong_audio_pad_output(1u << 9), 1u, "reads the output bit");
	expect_eq(pong_audio_pad_output(1u << 8), 0u, "drive bit is not the output bit");
	expect_eq(pong_audio_pad_out_high(2u), 1u, "reads the out-high bit");

	/* CBCR: a hardware-gated branch reports CLK_OFF while it is running, so
	 * the halt test has to accept HWCG (clk-branch.c:50-59). */
	expect(pong_audio_cbcr_running(0u), "a branch with no halt bit is running");
	expect(pong_audio_cbcr_running(PONG_AUDIO_CBCR_HWCG), "hw-gated branch is running");
	expect(pong_audio_cbcr_running(PONG_AUDIO_CBCR_CLK_OFF | PONG_AUDIO_CBCR_HWCG),
	    "hw-gated branch with CLK_OFF still runs");
	expect(!pong_audio_cbcr_running(PONG_AUDIO_CBCR_CLK_OFF),
	    "a halted branch with no hwcg is not running");

	/* GCC window routing: three one-page windows, and nothing else. */
	expect_eq((unsigned)pong_audio_gcc_window(PONG_AUDIO_GCC_RCG_SE15, &delta), 0u,
	    "the SE15 RCG lives in the rcg window");
	expect_eq(delta, PONG_AUDIO_GCC_RCG_SE15 - PONG_AUDIO_GCC_RCG_WIN, "rcg delta");
	expect_eq((unsigned)pong_audio_gcc_window(PONG_AUDIO_GCC_CBC_CORE, &delta), 1u,
	    "wrap2_core CBCR lives in the cbc window");
	expect_eq((unsigned)pong_audio_gcc_window(PONG_AUDIO_GCC_VOTE_WRAP2, &delta), 2u,
	    "the wrapper-2 vote register lives in the vote window");
	expect_eq(delta, PONG_AUDIO_GCC_VOTE_WRAP2 - PONG_AUDIO_GCC_VOTE_WIN, "vote delta");
	expect_eq((unsigned)pong_audio_gcc_window(0x00000000u, &delta), (unsigned)-1,
	    "offset 0 is outside every window");
	expect_eq((unsigned)pong_audio_gcc_window(PONG_AUDIO_GCC_VOTE_WRAP2 + 0x1000u, &delta),
	    (unsigned)-1, "one page past the vote window is outside");
	expect_eq((unsigned)pong_audio_gcc_window(PONG_AUDIO_GCC_VOTE_WIN + 0xffcu, &delta), 2u,
	    "the last word of the vote window is inside");
	expect_eq((unsigned)pong_audio_gcc_window(PONG_AUDIO_GCC_RCG_WIN - 4u, &delta),
	    (unsigned)-1, "one word before the rcg window is outside");

	/* DFS level: reference source, no divider (touch patch:313-324). */
	expect(pong_audio_dfs_level_ok(0u), "an all-zero level is the reference");
	expect(pong_audio_dfs_level_ok(1u), "m/n of one is still no divider");
	expect(!pong_audio_dfs_level_ok(2u), "m/n of two divides");
	expect(!pong_audio_dfs_level_ok(1u << 8), "a non-reference source is refused");
	expect(!pong_audio_dfs_level_ok(1u << 12), "a pre-divider is refused");
}

int
main(void)
{
	register_map_cases();
	prepare_cases();
	write_cases();
	read_cases();
	failure_cases();
	poll_cases();
	recovery_cases();
	plan_cases();
	chip_id_cases();

	if (fails) {
		printf("TESTS FAILED %d of %d\n", fails, cases);
		return 1;
	}
	printf("TESTS OK %d cases\n", cases);
	return 0;
}
