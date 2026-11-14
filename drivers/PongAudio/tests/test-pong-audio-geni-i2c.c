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
#include "PongCodecPlan.h"
#include "PongCodecSwr.h"
#include "PongCodecLpi.h"
#include "PongCodecMacro.h"
#include "PongCodecProbe.h"

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

	/* GCC window routing: four one-page windows, and nothing else. */
	expect_eq((unsigned)pong_audio_gcc_window(PONG_AUDIO_GCC_RCG_SE15, &delta), 0u,
	    "the SE15 RCG lives in the rcg window");
	expect_eq(delta, PONG_AUDIO_GCC_RCG_SE15 - PONG_AUDIO_GCC_RCG_WIN, "rcg delta");
	expect_eq((unsigned)pong_audio_gcc_window(PONG_AUDIO_GCC_CBC_CORE, &delta), 1u,
	    "wrap2_core CBCR lives in the cbc window");
	expect_eq((unsigned)pong_audio_gcc_window(PONG_AUDIO_GCC_VOTE_WRAP2, &delta), 2u,
	    "the wrapper-2 vote register lives in the vote window");
	expect_eq(delta, PONG_AUDIO_GCC_VOTE_WRAP2 - PONG_AUDIO_GCC_VOTE_WIN, "vote delta");
	expect_eq((unsigned)pong_audio_gcc_window(PONG_AUDIO_GCC_PLL0_ENABLE, &delta), 2u,
	    "the GPLL0 enable vote sits in the vote window, not the PLL window");
	expect_eq(delta, PONG_AUDIO_GCC_PLL0_ENABLE - PONG_AUDIO_GCC_VOTE_WIN,
	    "GPLL0 enable delta inside the vote window");
	expect_eq((unsigned)pong_audio_gcc_window(PONG_AUDIO_GCC_PLL0_MODE, &delta), 3u,
	    "PLL_MODE lives in the PLL window");
	expect_eq(delta, 0u, "PLL_MODE is offset 0 of the PLL block");
	expect_eq((unsigned)pong_audio_gcc_window(PONG_AUDIO_GCC_PLL_WIN + 0xffcu, &delta), 3u,
	    "the last word of the PLL window is inside");
	expect_eq((unsigned)pong_audio_gcc_window(PONG_AUDIO_GCC_PLL_WIN + 0x1000u, &delta),
	    (unsigned)-1, "one page past the PLL window is outside");
	expect_eq((unsigned)pong_audio_gcc_window(PONG_AUDIO_GCC_VOTE_WRAP2 + 0x1000u, &delta),
	    (unsigned)-1, "one page past the vote window is outside");
	expect_eq((unsigned)pong_audio_gcc_window(PONG_AUDIO_GCC_VOTE_WIN + 0xffcu, &delta), 2u,
	    "the last word of the vote window is inside");
	expect_eq((unsigned)pong_audio_gcc_window(PONG_AUDIO_GCC_RCG_WIN - 4u, &delta),
	    (unsigned)-1, "one word before the rcg window is outside");
	expect_eq((unsigned)pong_audio_gcc_window(0x00001000u, &delta), (unsigned)-1,
	    "one page past the PLL window is outside even though it is below the RCG");
	expect_eq(PONG_AUDIO_GCC_PLL0_ENABLE, 0x00062018u, "GPLL0 enable is GCC+0x62018");
	expect_eq(PONG_AUDIO_GCC_PLL0_MODE, 0x00000000u, "PLL_MODE is GCC+0x0");
	expect_eq(PONG_AUDIO_GCC_PLL0_VOTE, 1u, "GPLL0 vote is BIT(0) of the enable reg");
	expect_eq(PONG_AUDIO_GCC_PLL_LOCK_DET, 0x80000000u, "PLL lock is BIT(31)");

	/* DFS level: reference source, no divider (touch patch:313-324). */
	expect(pong_audio_dfs_level_ok(0u), "an all-zero level is the reference");
	expect(pong_audio_dfs_level_ok(1u), "m/n of one is still no divider");
	expect(!pong_audio_dfs_level_ok(2u), "m/n of two divides");
	expect(!pong_audio_dfs_level_ok(1u << 8), "a non-reference source is refused");
	expect(!pong_audio_dfs_level_ok(1u << 12), "a pre-divider is refused");
}

/* ---- codec-side decisions ------------------------------------------------
 *
 * The SoundWire half cannot run on this machine - every LPASS access waits on
 * two PRM votes from the ADSP (SOUNDWIRE.md section 4) - but every *choice* it
 * will make is a pure function over numbers, so the choices are pinned here.
 * That is what makes the eventual on-device read a thin loop instead of a
 * place where a wrong constant is first discovered on hardware.
 */
static void
codec_cases(void)
{
	PongSwrReadRegs regs;
	uint32_t phys = 0;
	uint32_t size = 0;
	uint32_t used = 0;
	uint32_t cfg;
	unsigned i;

	/* Controller version: exact v1.7, else major 2, else stop. 0x02010000 is
	 * a v2 controller and must not be mistaken for v1.7. */
	expect_eq(pong_swr_version(0x01070000u), PongSwrV17, "0x01070000 is v1.7");
	expect_eq(pong_swr_version(0x02010000u), PongSwrV2, "major 2 is v2");
	expect_eq(pong_swr_version(0x02000000u), PongSwrV2, "bare major 2 is v2");
	expect_eq(pong_swr_version(0x00000000u), PongSwrUnknown, "zero is unknown");
	expect_eq(pong_swr_version(0x01070001u), PongSwrUnknown,
	    "a v1.7 variant with another minor is still unknown, not v1.7");
	expect_eq(pong_swr_version(0x03010000u), PongSwrUnknown, "major 3 is unknown");

	/* Read-transaction register group per version. */
	regs.read_command = regs.fifo_status = regs.read_fifo = 0u;
	expect(pong_swr_read_regs(PongSwrV17, &regs), "v1.7 has a read group");
	expect_eq(regs.read_command, 0x320u, "v1.7 read command register");
	expect_eq(regs.fifo_status, 0x328u, "v1.7 fifo status register");
	expect_eq(regs.read_fifo, 0x334u, "v1.7 read fifo register");
	expect(pong_swr_read_regs(PongSwrV2, &regs), "v2 has a read group");
	expect_eq(regs.read_command, 0x5024u, "v2 read command register");
	expect_eq(regs.fifo_status, 0x5050u, "v2 fifo status register");
	expect_eq(regs.read_fifo, 0x5040u, "v2 read fifo register");
	expect(!pong_swr_read_regs(PongSwrUnknown, &regs), "an unknown version has no group");
	expect(!pong_swr_read_regs(PongSwrV17, NULL), "a null out-pointer is refused");

	/* (++transaction % 14) + 1: the pre-increment makes the first id 2, and the
	 * cycle is 2..14 then 1. Never 0. */
	expect_eq(pong_swr_txn_id(0u), 2u, "the first transaction is 2");
	expect_eq(pong_swr_txn_id(12u), 14u, "the thirteenth transaction is 14");
	expect_eq(pong_swr_txn_id(13u), 1u, "the fourteenth wraps to 1");
	expect_eq(pong_swr_txn_id(26u), 14u, "two full laps land on 14 again");

	/* Command word: read flag in bit 24, device, id, register. */
	expect_eq(pong_swr_read_command(0u, 1u, 0u), (1u << 24) | (1u << 16),
	    "device 0 id 1 reg 0 keeps the transaction id");
	expect_eq(pong_swr_read_command(1u, 2u, 0x3456u),
	    (1u << 24) | (1u << 20) | (2u << 16) | 0x3456u, "device 1 id 2 reg 0x3456");
	expect_eq(pong_swr_read_command(0xfu, 0xfu, 0xffffu),
	    0x01ffffffu, "every field at its maximum fills the low 24 bits");
	expect_eq(pong_swr_read_command(0x10u, 0x10u, 0x10000u),
	    1u << 24, "out-of-range fields are masked, not shifted in");

	/* FIFO fullness: bits 12:8, full at 8. */
	expect(!pong_swr_fifo_full(0u), "an empty fifo is not full");
	expect(!pong_swr_fifo_full(7u << 8), "seven entries still fit");
	expect(pong_swr_fifo_full(8u << 8), "eight entries are full");
	expect(pong_swr_fifo_full(0x1fu << 8), "the top of the field is full");
	expect(!pong_swr_fifo_full(0xffu), "the low byte is not the fill level");

	/* Response matching: id in bits 11:8, payload in bits 7:0. */
	expect(pong_swr_response_ok(0x00000300u, 3u), "id 3 matches its response");
	expect(!pong_swr_response_ok(0x00000400u, 3u), "id 4 is somebody else's response");
	expect(pong_swr_response_ok(0x000003ffu, 3u), "the payload does not affect matching");
	expect_eq(pong_swr_response_data(0x000003abu), 0xabu, "payload is the low byte");
	expect_eq(pong_swr_response_data(0xffffffffu), 0xffu, "payload ignores the upper bits");

	/* v1.7 interrupt masks before enumeration. */
	{
		uint32_t status = 0u, mask = 0u;

		pong_swr_v17_intr_masks(&status, &mask);
		expect_eq(status, 0xffffffffu, "v1.7 masks the first line completely");
		expect_eq(mask, 0x1dfdfdu, "v1.7 mask for the second line");
		pong_swr_v17_intr_masks(NULL, NULL);
		expect(1, "null masks are tolerated");
	}

	/* Enumerator bitmap: slave n occupies bits 2n+1:2n, n from 1 to 11. */
	expect(!pong_swr_slave_present(0u, 1u), "an empty bitmap has no slaves");
	expect(pong_swr_slave_present(1u << 2, 1u), "slave 1 in bits 3:2");
	expect(pong_swr_slave_present(2u << 2, 1u), "a half-set pair still counts");
	expect(!pong_swr_slave_present(1u << 0, 1u), "bit 0 is the master, not slave 1");
	expect(pong_swr_slave_present(3u << 22, 11u), "slave 11 in bits 23:22");
	expect(!pong_swr_slave_present(3u << 22, 0u), "slave 0 does not exist");
	expect(!pong_swr_slave_present(3u << 22, 12u), "slave 12 does not exist");
	expect_eq(pong_swr_slave_id_reg(1u), 0x538u, "slave 1 id low word");
	expect_eq(pong_swr_slave_id_reg(11u), 0x588u, "slave 11 id low word");
	expect_eq(pong_swr_slave_id(0x01170223u, 0x000du), PONG_SWR_WCD938X_ID,
	    "the WCD938x id assembles from its two words");
	expect(pong_swr_is_wcd938x(PONG_SWR_WCD938X_ID), "the WCD938x id is recognised");
	expect(!pong_swr_is_wcd938x(0x000d01170222ull), "a neighbouring id is not WCD938x");
	expect_eq(PONG_SWR_WCD938X_ID, 0x000d01170223ull, "WCD938x SoundWire id");

	/* LPI pads: pins 0/1/2/14, function 1, bus-hold on the data lines. */
	expect_eq(pong_codec_lpi_pin(0u), 0u, "pin 0 carries the clock");
	expect_eq(pong_codec_lpi_pin(1u), 1u, "pin 1 is data0");
	expect_eq(pong_codec_lpi_pin(3u), 14u, "pin 3 is data2 on gpio 14");
	expect_eq(pong_codec_lpi_pin(4u), 0xffffffffu, "there is no fifth LPI pin");
	expect_eq(pong_codec_lpi_pad_phys(0u), 0x03440000u, "LPI gpio 0 address");
	expect_eq(pong_codec_lpi_pad_phys(3u), 0x0344e000u, "LPI gpio 14 address");
	expect_eq(pong_codec_lpi_pad_phys(4u), 0u, "an out-of-range pin maps nothing");
	cfg = pong_codec_lpi_pad_config(0u, 0u);
	expect_eq(cfg, 1u << 2, "the clock pad: function 1, no bus hold");
	cfg = pong_codec_lpi_pad_config(0u, 1u);
	expect_eq(cfg, (1u << 2) | 2u, "a data pad: function 1 plus bus hold");
	cfg = pong_codec_lpi_pad_config(0xffffff00u, 1u);
	expect_eq(cfg, 0xffffff00u | (1u << 2) | 2u, "bits above 5 survive the write");
	expect_eq(pong_codec_lpi_pad_config(0x3fu, 0u), 1u << 2,
	    "the function and hold fields are replaced, not or-ed in");

	/* LPASS windows and their io_submap cost. */
	expect_eq(pong_codec_window_count(), 5u, "the codec half needs five windows");
	expect(pong_codec_window(0u, &phys, &size), "window 0 exists");
	expect_eq(phys, 0x033f0000u, "window 0 is the VA macro");
	expect_eq(size, 0x1000u, "the VA macro is one page");
	expect(pong_codec_window(1u, &phys, &size), "window 1 exists");
	expect_eq(phys, 0x03220000u, "window 1 is the TX macro");
	expect(pong_codec_window(2u, &phys, &size), "window 2 exists");
	expect_eq(phys, 0x033b0000u, "window 2 is the VA SoundWire master");
	expect_eq(size, 0x2000u, "the SWR master is mapped as 0x2000, not Pong's 0x10000");
	expect(pong_codec_window(3u, &phys, &size), "window 3 exists");
	expect_eq(phys, 0x03440000u, "window 3 is the LPI pinctrl");
	expect(pong_codec_window(4u, &phys, &size), "window 4 exists");
	expect_eq(phys, 0x034da000u, "window 4 is the LPI slew block");
	expect(!pong_codec_window(5u, &phys, &size), "there is no sixth window");
	expect(pong_codec_window(0u, NULL, NULL), "null out-pointers are tolerated");

	expect_eq(pong_codec_pages(0u), 0u, "zero bytes cost nothing");
	expect_eq(pong_codec_pages(1u), 1u, "one byte still costs a page");
	expect_eq(pong_codec_pages(0x4000u), 1u, "exactly one page");
	expect_eq(pong_codec_pages(0x4001u), 2u, "one byte over rounds up");
	expect_eq(pong_codec_pages(0x17000u), 6u, "the LPI pinctrl window is six pages");

	/* 0x1000+0x1000+0x2000+0x17000+0x1000 = 0x1b000 bytes, but io_map() charges
	 * whole pages: 1+1+1+6+1 = 10 pages = 160 KiB. The pinctrl window is the
	 * expensive one and cannot be shrunk - it spans six pages of live FDT. */
	expect_eq(pong_codec_window_bytes(), 10u * 0x4000u, "the codec half costs 160 KiB");
	expect_eq(pong_codec_window_bytes() / 0x4000u, 10u, "ten arm64 pages");
	expect(pong_codec_budget_ok(192u * 1024u, pong_codec_window_bytes()),
	    "192 KiB of amplifier mappings leave room for the codec half");
	expect(!pong_codec_budget_ok(8u * 1024u * 1024u, 1u), "a full submap takes nothing more");
	expect(!pong_codec_budget_ok(9u * 1024u * 1024u, 0u), "an over-full submap is refused");
	expect(pong_codec_budget_ok(0u, 8u * 1024u * 1024u), "an empty submap takes the whole budget");

	/* The LPASS gate: all three votes, or nothing. */
	expect(!pong_codec_may_touch_lpass(false, false, false), "no votes, no access");
	expect(!pong_codec_may_touch_lpass(true, false, true), "a missing DCODEC vote blocks");
	expect(!pong_codec_may_touch_lpass(true, true, false), "a missing clock ack blocks");
	expect(!pong_codec_may_touch_lpass(false, true, true), "a missing MACRO vote blocks");
	expect(pong_codec_may_touch_lpass(true, true, true), "all three votes allow access");

	/* Every window is inside the LPASS register region and page aligned. */
	for (i = 0u; i < pong_codec_window_count(); i++) {
		expect(pong_codec_window(i, &phys, &size), "window enumerates");
		/* Bases are 4 KiB register aligned, not 16 KiB: the LPI slew block sits
		 * at 0x034da000, which io_map() rounds up into pages for us. */
		expect((phys & 0xfffu) == 0u, "window is 4 KiB aligned");
		expect(phys >= 0x03100000u && phys + size <= 0x03600000u,
		    "window stays inside the LPASS register region");
		used += size;
	}
	expect(used > 0u, "the windows add up to something");
}

/* ---- fake SoundWire master ---------------------------------------------- */

/* The reference maps 0x10000 for the controller and the v2 registers live at
 * 0x5000 and up, so the fake window has to be the full 64 KiB of words, not the
 * 0x2000 the read path alone would need. */
typedef struct {
	uint32_t regs[0x8000];
	uint32_t writes, last_write_reg, last_write_value;
} FakeSwr;

static uint32_t
fake_swr_read(void *ctx, uint32_t reg)
{
	FakeSwr *f = (FakeSwr *)ctx;

	return f->regs[reg & 0x7fffu];
}

static void
fake_swr_write(void *ctx, uint32_t reg, uint32_t value)
{
	FakeSwr *f = (FakeSwr *)ctx;

	f->regs[reg & 0x7fffu] = value;
	f->writes++;
	f->last_write_reg = reg;
	f->last_write_value = value;
}

static void
swr_cases(void)
{
	/* 64 KiB of register window: static, not on the stack, which the default
	 * 8 MiB thread stack would not miss but a smaller one would. */
	static FakeSwr f;
	PongSwrIo io;
	PongSwr s;
	unsigned i;

	io.read = fake_swr_read;
	io.write = fake_swr_write;
	io.ctx = &f;

	/* v1.7: the expected K60 controller (W:2.1's interrupt pair matches it). */
	memset(&f, 0, sizeof(f));
	f.regs[PONG_SWR_COMP_HW_VERSION] = 0x01070000u;
	expect_eq((unsigned long)pong_swr_probe(&s, &io), 0ul, "probe accepts v1.7");
	expect_eq((unsigned long)s.version, (unsigned long)PongSwrV17, "version is v1.7");
	expect_eq(s.regs.read_command, 0x320u, "v1.7 read command register");
	expect_eq(s.regs.fifo_status, 0x328u, "v1.7 fifo status register");
	expect_eq(s.regs.read_fifo, 0x334u, "v1.7 read fifo register");
	expect_eq(s.state, (unsigned long)PongSwrIdle, "probe leaves the machine idle");
	expect(!pong_swr_busy(&s), "nothing outstanding after probe");

	/* v2 keeps the mainline defaults. */
	memset(&f, 0, sizeof(f));
	f.regs[PONG_SWR_COMP_HW_VERSION] = 0x02010000u;
	expect_eq((unsigned long)pong_swr_probe(&s, &io), 0ul, "probe accepts v2");
	expect_eq(s.regs.read_command, 0x5024u, "v2 read command register");
	expect_eq(s.regs.fifo_status, 0x5050u, "v2 fifo status register");
	expect_eq(s.regs.read_fifo, 0x5040u, "v2 read fifo register");

	/* An unknown controller stops the codec half; it must not guess a group. */
	memset(&f, 0, sizeof(f));
	f.regs[PONG_SWR_COMP_HW_VERSION] = 0x03000000u;
	expect_eq((unsigned long)pong_swr_probe(&s, &io), (unsigned long)-1,
	    "probe refuses an unknown controller");
	expect_eq(s.error, (unsigned long)PongSwrErrVersion, "unknown version is named");
	expect_eq(f.writes, 0ul, "an unknown controller is not written to");

	/* FIFO full: nothing is written, so no orphan command can be left behind. */
	memset(&f, 0, sizeof(f));
	f.regs[PONG_SWR_COMP_HW_VERSION] = 0x01070000u;
	(void)pong_swr_probe(&s, &io);
	f.regs[s.regs.fifo_status] = 8u << 8;
	f.writes = 0;
	expect_eq((unsigned long)pong_swr_read_start(&s, 1u, 0x3000u), (unsigned long)-1,
	    "a full command FIFO refuses the read");
	expect_eq(s.error, (unsigned long)PongSwrErrFifo, "the refusal is named");
	expect_eq(f.writes, 0ul, "a refused read writes no command");
	expect_eq(s.state, (unsigned long)PongSwrIdle, "a refused read leaves it idle");

	/* The happy path: command word, transaction id, response collection. */
	memset(&f, 0, sizeof(f));
	f.regs[PONG_SWR_COMP_HW_VERSION] = 0x01070000u;
	(void)pong_swr_probe(&s, &io);
	f.writes = 0;
	expect_eq((unsigned long)pong_swr_read_start(&s, 1u, 0x3000u), 0ul,
	    "a read starts");
	/* (++transaction % 14) + 1 with transaction starting at 0: the first id
	 * is 2, not 1. Only uniqueness matters for correctness, but matching the
	 * proven sequence lets a captured trace be compared line by line. */
	expect_eq(s.txn, 2ul, "the first transaction id is 2");
	expect_eq(f.last_write_reg, 0x320u, "the command goes to the read command register");
	expect_eq(f.last_write_value, (1ul << 24) | (1ul << 20) | (2ul << 16) | 0x3000ul,
	    "the command word carries opcode, device, id and register");
	expect(pong_swr_busy(&s), "the machine is busy while awaiting a response");

	expect_eq((unsigned long)pong_swr_read_start(&s, 1u, 0x3000u), (unsigned long)-1,
	    "a second read is refused while one is outstanding");
	expect_eq(s.error, (unsigned long)PongSwrErrBusy, "the refusal is named busy");

	/* No response yet: bits 20:16 of the fifo status are zero. */
	expect_eq((unsigned long)pong_swr_read_poll(&s), (unsigned long)PongSwrPending,
	    "an empty response queue is pending, not failed");

	/* The response carries our transaction id in bits 11:8. */
	f.regs[s.regs.fifo_status] = 1u << 16;
	f.regs[s.regs.read_fifo] = (2u << 8) | 0x5au;
	expect_eq((unsigned long)pong_swr_read_poll(&s), (unsigned long)PongSwrDone,
	    "a matching response completes the read");
	expect_eq(s.data, 0x5aul, "the data byte is taken from bits 7:0");
	expect_eq(s.state, (unsigned long)PongSwrIdle, "a completed read leaves it idle");
	expect_eq(s.aborts, 0ul, "a clean read aborts nothing");

	/* Someone else's answer: abort, never retry under the same id. */
	memset(&f, 0, sizeof(f));
	f.regs[PONG_SWR_COMP_HW_VERSION] = 0x01070000u;
	(void)pong_swr_probe(&s, &io);
	(void)pong_swr_read_start(&s, 2u, 0x3000u);
	f.regs[s.regs.fifo_status] = 1u << 16;
	f.regs[s.regs.read_fifo] = (9u << 8) | 0x11u;
	expect_eq((unsigned long)pong_swr_read_poll(&s), (unsigned long)PongSwrFailed,
	    "a foreign transaction id fails the read");
	expect_eq(s.error, (unsigned long)PongSwrErrTxn, "the failure is named");
	expect_eq(f.last_write_reg, PONG_SWR_ABORT, "a foreign response aborts the transaction");
	expect_eq(f.last_write_value, 1ul, "the abort is a one written to 0x308");
	expect_eq(s.aborts, 1ul, "the abort is counted");
	expect_eq(s.state, (unsigned long)PongSwrIdle, "an aborted read leaves it idle");

	/* Deadline: abort and count it. */
	memset(&f, 0, sizeof(f));
	f.regs[PONG_SWR_COMP_HW_VERSION] = 0x01070000u;
	(void)pong_swr_probe(&s, &io);
	(void)pong_swr_read_start(&s, 1u, 0x3000u);
	expect_eq((unsigned long)pong_swr_read_timeout(&s), (unsigned long)-1,
	    "a timed-out read reports failure");
	expect_eq(s.error, (unsigned long)PongSwrErrTimeout, "the timeout is named");
	expect_eq(s.timeouts, 1ul, "the timeout is counted");
	expect_eq(f.last_write_reg, PONG_SWR_ABORT, "a timeout aborts the transaction");
	expect_eq(s.state, (unsigned long)PongSwrIdle, "an aborted read leaves it idle");
	expect_eq((unsigned long)pong_swr_read_timeout(&s), (unsigned long)-1,
	    "a timeout with nothing outstanding is refused");
	expect_eq(s.error, (unsigned long)PongSwrErrState, "that refusal is named");

	/* Initialisation before enumeration (S:PongWcd938.h:88-104). The exact
	 * register writes matter: the reference was proven on this SoC, so the
	 * sequence is copied rather than reasoned about. */
	memset(&f, 0, sizeof(f));
	f.regs[PONG_SWR_COMP_HW_VERSION] = 0x01070000u;
	(void)pong_swr_probe(&s, &io);
	f.regs[PONG_SWR_CFG] = 0xdeadbeefu;
	expect_eq((unsigned long)pong_swr_init(&s), 0ul, "v1.7 initialises");
	expect_eq(f.regs[PONG_SWR_COMP_CFG2], 1ul, "the block is enabled first");
	expect_eq(f.regs[PONG_SWR_FRAME_CTRL], (1ul << 3) | 7ul, "the frame shape is set");
	expect_eq(f.regs[PONG_SWR_ENUMERATOR_CFG], 1ul, "the enumerator is enabled");
	expect_eq(f.regs[PONG_SWR_CFG] & (0x1ful << 17), 0x1ful << 17,
	    "the five MCP configuration bits are set");
	expect_eq(f.regs[PONG_SWR_CFG] & ~(0x1ful << 17), 0xdeadbeeful & ~(0x1ful << 17),
	    "the rest of the MCP configuration register is preserved");
	expect_eq(f.regs[PONG_SWR_ENABLE], 1ul, "the controller is enabled last");
	/* v1.7 moves the execution environment 1 -> 3 around the interrupt masks. */
	expect_eq(f.regs[0x314u], 7ul, "the CPU1 offset is set");
	expect_eq(f.regs[PONG_SWR_BUS_CTRL], 4ul, "the bus control is set");
	expect_eq(f.regs[0x208u], 0xfffffffful, "the v1.7 interrupt status mask is written");
	expect_eq(f.regs[0x210u], 0x1dfdfdul, "the v1.7 interrupt mask is written");
	expect_eq(f.regs[PONG_SWR_COMP_CFG], 3ul, "v1.7 ends in execution environment 3");
	expect(pong_swr_init_done(&s), "v1.7 has nothing to wait for");
	expect_eq(f.regs[PONG_SWR_V2_ENV_CTRL], 0ul, "v1.7 does not touch the v2 registers");

	/* v2 brings the execution environment up instead, and must be waited for. */
	memset(&f, 0, sizeof(f));
	f.regs[PONG_SWR_COMP_HW_VERSION] = 0x02010000u;
	(void)pong_swr_probe(&s, &io);
	expect_eq((unsigned long)pong_swr_init(&s), 0ul, "v2 initialises");
	expect_eq(f.regs[PONG_SWR_V2_ENV_CTRL], 1ul, "v2 starts the execution environment");
	expect_eq(f.regs[0x314u], 7ul | (1ul << 31), "v2 uses the other CPU1 encoding");
	expect_eq(f.regs[PONG_SWR_V2_IRQ_CLEAR], 0xfffffffful, "v2 clears the interrupts");
	expect_eq(f.regs[PONG_SWR_V2_IRQ_MASK], 0x1fffful, "v2 masks the interrupts");
	expect_eq(f.regs[PONG_SWR_COMP_CFG], 3ul, "v2 also ends in environment 3");
	expect(!pong_swr_init_done(&s), "v2 is not ready until 0x5064 bit 0 comes up");
	f.regs[PONG_SWR_V2_ENV_STATUS] = PONG_SWR_V2_ENV_READY;
	expect(pong_swr_init_done(&s), "v2 is ready once the bit is set");
	f.regs[PONG_SWR_V2_ENV_STATUS] = PONG_SWR_V2_ENV_READY | 2u;
	expect(pong_swr_init_done(&s), "other bits in the status register do not matter");

	/* Without a probe there is no version to initialise against. */
	memset(&s, 0, sizeof(s));
	expect_eq((unsigned long)pong_swr_init(&s), (unsigned long)-1,
	    "initialising without a probe is refused");
	expect_eq(s.error, (unsigned long)PongSwrErrVersion, "the refusal is named");

	/* The enumerator: enable, latch the bitmap, then the per-slave reads. */
	memset(&f, 0, sizeof(f));
	f.regs[PONG_SWR_COMP_HW_VERSION] = 0x01070000u;
	(void)pong_swr_probe(&s, &io);
	f.regs[PONG_SWR_SLAVE_STATUS] = (3u << 2) | (1u << 4);
	expect_eq((unsigned long)pong_swr_enumerate_start(&s), 0ul, "enumeration starts");
	expect_eq(f.regs[PONG_SWR_ENUMERATOR_CFG], 1ul, "enumeration is enabled first");
	expect_eq(s.slave_status, (3ul << 2) | (1ul << 4), "the slave bitmap is latched");
	expect(pong_swr_slave_at(&s, 1u), "slave 1 is present");
	expect(pong_swr_slave_at(&s, 2u), "slave 2 is present");
	expect(!pong_swr_slave_at(&s, 3u), "slave 3 is absent");

	/* Transaction ids walk 1..14 and never repeat while one is outstanding. */
	memset(&f, 0, sizeof(f));
	f.regs[PONG_SWR_COMP_HW_VERSION] = 0x01070000u;
	(void)pong_swr_probe(&s, &io);
	for (i = 0u; i < 14u; i++) {
		const unsigned want = ((i + 1u) % 14u) + 1u;

		(void)pong_swr_read_start(&s, 1u, 0x3000u);
		expect_eq(s.txn, (unsigned long)want, "the transaction id cycles 2..14 then 1");
		f.regs[s.regs.fifo_status] = 1u << 16;
		f.regs[s.regs.read_fifo] = ((uint32_t)want << 8);
		expect_eq((unsigned long)pong_swr_read_poll(&s), (unsigned long)PongSwrDone,
		    "every id in the cycle is accepted");
	}
	(void)pong_swr_read_start(&s, 1u, 0x3000u);
	expect_eq(s.txn, 2ul, "the transaction id wraps back to 2 after 14");
	expect_eq(s.reads, 15ul, "every started read is counted");

	/* The codec identity is two 8-bit reads, low byte first (S:113-114). */
	expect_eq(pong_swr_codec_identity(0x23u, 0x01u), 0x0123ul, "identity low byte first");
	expect_eq(pong_swr_codec_identity(0x00u, 0x00u), 0ul, "identity of two zeroes is zero");
}

/* The LPI block and the slew block are separate mappings: pads at 0x03440000
 * with one page per pin, slew at 0x034da000. The fake keeps them apart too, so
 * a slew write landing on pad 0 would show up as a wrong pad value. */
typedef struct {
	uint32_t pads[16];
	uint32_t slew;
	unsigned writes, pad_writes, slew_writes;
	uint32_t order[8];          /* pin index of each pad write, in order */
} FakeLpi;

static uint32_t
fake_lpi_read(void *ctx, uint32_t reg)
{
	FakeLpi *f = (FakeLpi *)ctx;

	return f->pads[(reg / PONG_CODEC_LPI_STRIDE) & 15u];
}

static void
fake_lpi_write(void *ctx, uint32_t reg, uint32_t value)
{
	FakeLpi *f = (FakeLpi *)ctx;
	unsigned pin = (reg / PONG_CODEC_LPI_STRIDE) & 15u;

	f->pads[pin] = value;
	if (f->pad_writes < 8u) {
		f->order[f->pad_writes] = pin;
	}
	f->pad_writes++;
	f->writes++;
}

static uint32_t
fake_slew_read(void *ctx, uint32_t reg)
{
	FakeLpi *f = (FakeLpi *)ctx;

	(void)reg;
	return f->slew;
}

static void
fake_slew_write(void *ctx, uint32_t reg, uint32_t value)
{
	FakeLpi *f = (FakeLpi *)ctx;

	(void)reg;
	f->slew = value;
	f->slew_writes++;
	f->writes++;
}

static void
lpi_cases(void)
{
	static FakeLpi f;
	PongCodecLpiIo io;
	PongCodecLpi l;
	unsigned i, steps;

	/* The slew block holds two bits per pin starting at bit 0 (S:80-82). */
	expect_eq((unsigned long)pong_codec_lpi_slew_shift(0u), 0ul, "pin 0 slews at bit 0");
	expect_eq((unsigned long)pong_codec_lpi_slew_shift(1u), 2ul, "pin 1 slews at bit 2");
	expect_eq((unsigned long)pong_codec_lpi_slew_shift(3u), 6ul, "pin 14 slews at bit 6");
	/* Level 1 means the low bit of the pair, with the pair's other bit cleared. */
	expect_eq((unsigned long)pong_codec_lpi_slew_config(0xaaaaaaaau, 0u), 0xaaaaaaa9ul,
	    "slew level 1 replaces the 2-bit field");
	/* Pin 2 sits at bit 4: the pair 11 becomes 01, so 0xffffffff -> 0xffffffdf. */
	expect_eq((unsigned long)pong_codec_lpi_slew_config(0xffffffffu, 2u), 0xffffffdful,
	    "slew on pin 2 clears its high bit");
	expect_eq((unsigned long)pong_codec_lpi_slew_config(0u, 3u), 0x40ul,
	    "slew on pin 14 sets bit 6 only");

	/* The pins are 0, 1, 2 and 14, not 0..3. */
	expect_eq((unsigned long)pong_codec_lpi_pin(0u), 0ul, "first pad is pin 0");
	expect_eq((unsigned long)pong_codec_lpi_pin(1u), 1ul, "second pad is pin 1");
	expect_eq((unsigned long)pong_codec_lpi_pin(2u), 2ul, "third pad is pin 2");
	expect_eq((unsigned long)pong_codec_lpi_pin(3u), 14ul, "fourth pad is pin 14");
	expect_eq((unsigned long)pong_codec_lpi_pin(4u), 0xfffffffful, "a fifth pad does not exist");

	memset(&f, 0, sizeof(f));
	io.read = fake_lpi_read;
	io.write = fake_lpi_write;
	io.ctx = &f;
	io.slew_read = fake_slew_read;
	io.slew_write = fake_slew_write;
	io.slew_ctx = &f;

	/* Pin 1 already carries the function-1 field; the rest is zero. */
	f.pads[1] = 0xffffffc0u;
	f.slew = 0xaaaaaaaau;
	pong_codec_lpi_start(&l, &io);
	expect(!pong_codec_lpi_done(&l), "a fresh sequencer is not done");
	expect_eq((unsigned long)l.step, 0ul, "a fresh sequencer starts at step 0");

	/* Five steps: four pads then the slew register, and nothing more. */
	steps = 0;
	while (pong_codec_lpi_step(&l)) {
		if (++steps > 8u) {
			break;
		}
	}
	expect_eq((unsigned long)steps, 4ul, "four steps report more work, the fifth finishes");
	expect(pong_codec_lpi_done(&l), "the sequencer reports done");
	expect_eq((unsigned long)f.writes, 5ul, "four pads and one slew write");
	expect_eq((unsigned long)f.pad_writes, 4ul, "exactly four pad writes");
	expect_eq((unsigned long)f.slew_writes, 1ul, "exactly one slew write");

	/* Order matters: all four pads before the slew register. */
	expect_eq((unsigned long)f.order[0], 0ul, "pin 0 is programmed first");
	expect_eq((unsigned long)f.order[1], 1ul, "pin 1 second");
	expect_eq((unsigned long)f.order[2], 2ul, "pin 2 third");
	expect_eq((unsigned long)f.order[3], 14ul, "pin 14 fourth");

	/* Pad value: function 1 in bits 2-3, bus-hold on the data pins only. */
	expect_eq((unsigned long)f.pads[0], 0x04ul, "pin 0 keeps function 1 and no bus-hold");
	expect_eq((unsigned long)f.pads[1], 0xffffffc6ul, "pin 1 keeps its upper bits and gains bus-hold");
	expect_eq((unsigned long)f.pads[2], 0x06ul, "pin 2 gains bus-hold");
	expect_eq((unsigned long)f.pads[14], 0x06ul, "pin 14 gains bus-hold");
	expect_eq((unsigned long)l.pad_old[1], 0xffffffc0ul, "the old pin value is kept for the log");

	/* Slew: every 2-bit field becomes level 1, upper bits untouched. */
	/* Only the low eight bits are the four fields; 0xaaaaaaaa's pairs 10 become
	 * 01, which is 0x55, and everything above bit 7 is left as it was. */
	expect_eq((unsigned long)f.slew, 0xaaaaaa55ul, "all four slew fields become level 1");
	expect_eq((unsigned long)l.slew_old, 0xaaaaaaaau, "the old slew value is kept for the log");

	/* Stepping a finished sequencer must not write again. */
	expect(!pong_codec_lpi_step(&l), "a finished sequencer reports no more work");
	expect(!pong_codec_lpi_step(&l), "and keeps reporting that");
	expect_eq((unsigned long)f.writes, 5ul, "a finished sequencer writes nothing more");

	/* A slew value that is already level 1 stays as it is. */
	memset(&f, 0, sizeof(f));
	f.slew = 0x00000055u;
	pong_codec_lpi_start(&l, &io);
	for (i = 0u; i < 8u; i++) {
		if (!pong_codec_lpi_step(&l)) {
			break;
		}
	}
	expect_eq((unsigned long)f.slew, 0x00000055ul, "an already programmed slew is left alone");

	/* Without callbacks the sequencer refuses to run instead of faulting. */
	pong_codec_lpi_start(&l, 0);
	expect(!pong_codec_lpi_step(&l), "a sequencer without callbacks does nothing");
	expect(!pong_codec_lpi_done(&l), "and is not done");
	pong_codec_lpi_start(0, &io);
	expect(!pong_codec_lpi_done(0), "a null sequencer is not done");
}

/* The VA and TX macros are separate mappings; the fake keeps them separate so a
 * step written to the wrong macro cannot pass by accident. */
typedef struct {
	uint32_t va[0x100];
	uint32_t tx[0x100];
	unsigned va_writes, tx_writes;
	uint32_t va_last_reg, tx_last_reg;
} FakeMacro;

static uint32_t
fake_macro_read(void *ctx, uint32_t reg)
{
	uint32_t *bank = (uint32_t *)ctx;

	return bank[reg & 0xffu];
}

static void
fake_macro_write(void *ctx, uint32_t reg, uint32_t value)
{
	uint32_t *bank = (uint32_t *)ctx;

	bank[reg & 0xffu] = value;
}

static void
macro_cases(void)
{
	static FakeMacro f;
	PongCodecMacroIo io;
	PongCodecMacro m;
	PongCodecMacroStep e;
	unsigned steps;

	/* Nine steps, and the table is readable without running it. */
	expect_eq((unsigned long)PONG_CODEC_MACRO_STEPS, 9ul, "the sequence is nine steps");
	expect(!pong_codec_macro_plan(9u, &e), "step 9 does not exist");
	expect(!pong_codec_macro_plan(0u, 0), "a null step is refused");
	expect(pong_codec_macro_plan(0u, &e), "step 0 exists");
	expect_eq((unsigned long)e.tx, 0ul, "step 0 is a VA macro write");
	expect_eq((unsigned long)e.reg, 0x0ul, "step 0 writes MCLK_CONTROL");
	expect_eq((unsigned long)e.set, 1ul, "step 0 enables the VA MCLK");
	expect(pong_codec_macro_plan(7u, &e), "step 7 exists");
	expect_eq((unsigned long)e.tx, 1ul, "step 7 is the first TX macro write");
	expect_eq((unsigned long)e.reg, 0x0ul, "step 7 writes TX MCLK_CONTROL");

	/* Bit surgery is clear-then-set, and both halves are independent. */
	expect_eq((unsigned long)pong_codec_macro_value(0xfu, 0x2u, 0x1u), 0xdul,
	    "clearing bit 1 and setting bit 0 keeps the rest");
	expect_eq((unsigned long)pong_codec_macro_value(0u, 0u, 0x3u), 0x3ul, "nothing cleared");
	expect_eq((unsigned long)pong_codec_macro_value(0xfu, 0xfu, 0u), 0ul, "everything cleared");
	expect_eq((unsigned long)pong_codec_macro_value(0x2u, 0x2u, 0x2u), 0x2ul,
	    "a bit that is cleared and set ends up set");

	memset(&f, 0, sizeof(f));
	io.va.read = fake_macro_read;
	io.va.write = fake_macro_write;
	io.va.ctx = f.va;
	io.tx.read = fake_macro_read;
	io.tx.write = fake_macro_write;
	io.tx.ctx = f.tx;

	/* Reset values this project has never seen: start from something non-zero so
	 * the read-modify-write is actually exercised. */
	f.va[0x00] = 0xfffffff0u;
	f.va[0x04] = 0xfffffffcu;
	f.va[0x80] = 0xfffffffdu;
	f.va[0x08] = 0xfffffffcu;
	f.tx[0x00] = 0xfffffff0u;
	f.tx[0x04] = 0xfffffff0u;

	pong_codec_macro_start(&m, &io);
	expect(!pong_codec_macro_done(&m), "a fresh sequencer is not done");
	expect_eq((unsigned long)m.step, 0ul, "a fresh sequencer starts at step 0");

	steps = 0;
	while (pong_codec_macro_step(&m)) {
		if (++steps > 12u) {
			break;
		}
	}
	expect_eq((unsigned long)steps, 8ul, "eight steps report more work, the ninth finishes");
	expect(pong_codec_macro_done(&m), "the sequencer reports done");
	expect_eq((unsigned long)m.writes, 9ul, "nine writes, one per step");

	/* The VA macro takes seven of the nine, TX the last two. */
	expect_eq((unsigned long)f.va[0x00], 0xfffffff1ul, "VA MCLK enabled, upper bits kept");
	expect_eq((unsigned long)f.va[0x04], 0xfffffffdu, "VA FS_CNT ends with bit 1 clear, bit 0 set");
	expect_eq((unsigned long)f.va[0x80], 0xfffffffful, "VA TOP_CFG0 gains bit 1");
	expect_eq((unsigned long)f.va[0x08], 0xfffffffdu, "VA SWR_CONTROL ends with bit 1 clear, bit 0 set");
	expect_eq((unsigned long)f.tx[0x00], 0xfffffff1ul, "TX MCLK enabled");
	expect_eq((unsigned long)f.tx[0x04], 0xfffffff1ul, "TX FS_CNT enabled");

	/* Each step records what it read and what it wrote, so the boot log can show
	 * the reset values instead of assuming them. */
	expect_eq((unsigned long)m.old[0], 0xfffffff0ul, "step 0 remembers the reset value");
	expect_eq((unsigned long)m.now[0], 0xfffffff1ul, "step 0 remembers what it wrote");
	expect_eq((unsigned long)m.old[1], 0xfffffffcul, "step 1 read after step 0 wrote");
	expect_eq((unsigned long)m.now[2], 0xfffffffdu, "step 2 cleared bit 1 of the value step 1 wrote");

	/* Stepping a finished sequencer writes nothing more. */
	expect(!pong_codec_macro_step(&m), "a finished sequencer reports no more work");
	expect_eq((unsigned long)m.writes, 9ul, "and writes nothing more");

	/* Without callbacks it does nothing instead of faulting. */
	pong_codec_macro_start(&m, 0);
	expect(!pong_codec_macro_step(&m), "a sequencer without callbacks does nothing");
	expect(!pong_codec_macro_done(&m), "and is not done");
	pong_codec_macro_start(0, &io);
	expect(!pong_codec_macro_done(0), "a null sequencer is not done");
	expect(!pong_codec_macro_plan(0u, 0), "a null plan output is refused");
}

/* ---- the whole codec half, in order ------------------------------------- */

/* One fake covering all four blocks the codec probe touches, because the point
 * of the probe is the order: a fake per block could not show that the pads were
 * written before the controller was read. */
typedef struct {
	uint32_t pads[16];
	uint32_t slew;
	uint32_t va[0x100];        /* indexed by register: 0x00, 0x04, 0x08, 0x80 */
	uint32_t tx[0x100];
	uint32_t swr[0x8000];
	/* What the one slave answers when asked for its id halves and identity
	 * bytes. A table rather than an address trick: the register numbers of
	 * two different slaves overlap in their low bits, so decoding the
	 * command is the only honest way to answer it. */
	uint32_t slave_id_lo[16];
	uint32_t slave_id_hi[16];
	uint32_t slave_id_lo_byte[16];
	uint32_t slave_id_hi_byte[16];
	uint32_t swr_command;      /* the last command word written */
	uint32_t swr_pending;      /* a response is waiting to be collected */
	uint32_t swr_response;
	unsigned swr_silent;       /* never answers: drives the timeout path */
	unsigned writes;
} FakeCodec;

static uint32_t
fake_codec_lpi_read(void *ctx, uint32_t reg)
{
	FakeCodec *f = (FakeCodec *)ctx;

	return f->pads[(reg / 0x1000u) % 16u];
}

static void
fake_codec_lpi_write(void *ctx, uint32_t reg, uint32_t value)
{
	FakeCodec *f = (FakeCodec *)ctx;

	f->pads[(reg / 0x1000u) % 16u] = value;
	f->writes++;
}

static uint32_t
fake_codec_slew_read(void *ctx, uint32_t reg)
{
	FakeCodec *f = (FakeCodec *)ctx;

	(void)reg;
	return f->slew;
}

static void
fake_codec_slew_write(void *ctx, uint32_t reg, uint32_t value)
{
	FakeCodec *f = (FakeCodec *)ctx;

	(void)reg;
	f->slew = value;
	f->writes++;
}

static uint32_t
fake_codec_va_read(void *ctx, uint32_t reg)
{
	FakeCodec *f = (FakeCodec *)ctx;

	return f->va[reg & 0xffu];
}

static void
fake_codec_va_write(void *ctx, uint32_t reg, uint32_t value)
{
	FakeCodec *f = (FakeCodec *)ctx;

	f->va[reg & 0xffu] = value;
	f->writes++;
}

static uint32_t
fake_codec_tx_read(void *ctx, uint32_t reg)
{
	FakeCodec *f = (FakeCodec *)ctx;

	return f->tx[reg & 0xffu];
}

static void
fake_codec_tx_write(void *ctx, uint32_t reg, uint32_t value)
{
	FakeCodec *f = (FakeCodec *)ctx;

	f->tx[reg & 0xffu] = value;
	f->writes++;
}

/* The master answers as soon as it is asked: the command word is decoded when
 * it is written and the answer is staged, so one poll is enough. Real hardware
 * needs polls in between, which is what swr_silent exercises. */
/* What one slave answers for one register. Only the four registers the probe
 * asks for are modelled; anything else reads back as zero, which is what a
 * slave that has nothing to say would return. */
static uint32_t
fake_codec_answer(FakeCodec *f, unsigned device, unsigned reg)
{
	if (device > 15u)
		return 0u;
	if (reg == 0x530u + 8u * device)
		return f->slave_id_lo[device];
	if (reg == 0x534u + 8u * device)
		return f->slave_id_hi[device];
	if (reg == 0x50u)
		return f->slave_id_lo_byte[device];
	if (reg == 0x51u)
		return f->slave_id_hi_byte[device];
	return 0u;
}

static uint32_t
fake_codec_swr_read(void *ctx, uint32_t reg)
{
	FakeCodec *f = (FakeCodec *)ctx;
	uint32_t off = reg & 0x7fffu;

	if (off == 0x328u || off == 0x5050u)
		return f->swr_pending ? (1u << 16) : 0u;
	if (off == 0x334u || off == 0x5040u) {
		f->swr_pending = 0u;
		return f->swr_response;
	}
	return f->swr[off];
}

static void
fake_codec_swr_write(void *ctx, uint32_t reg, uint32_t value)
{
	FakeCodec *f = (FakeCodec *)ctx;
	uint32_t off = reg & 0x7fffu;

	f->swr[off] = value;
	f->writes++;
	if (off == 0x320u || off == 0x5024u) {
		/* Decode the command the way the master would: device in 23:20,
		 * transaction id in 19:16, register in 15:0. The answer table is
		 * the "slave answers" half of the fake, addressed by device. */
		unsigned device = (value >> 20) & 0xfu;
		unsigned txn = (value >> 16) & 0xfu;
		unsigned reg_no = value & 0xffffu;

		f->swr_command = value;
		if (f->swr_silent)
			return;
		f->swr_response = (txn << 8) | (fake_codec_answer(f, device, reg_no) & 0xffu);
		f->swr_pending = 1u;
	}
}

/* A slave's 64-bit id is two registers and its identity two more, so the fake
 * is handed all four at once. */
static void
fake_codec_set_slave(FakeCodec *f, unsigned n, uint64_t id, unsigned identity)
{
	/* The id halves are ordinary registers: the reference reads them
	 * directly (S:PongWcd938.h:108-109), not through a read transaction. */
	f->swr[0x530u + 8u * n] = (uint32_t)(id & 0xffffffffu);
	f->swr[0x534u + 8u * n] = (uint32_t)(id >> 32);
	f->slave_id_lo[n] = (uint32_t)(id & 0xffffffffu);
	f->slave_id_hi[n] = (uint32_t)(id >> 32);
	f->slave_id_lo_byte[n] = identity & 0xffu;
	f->slave_id_hi_byte[n] = (identity >> 8) & 0xffu;
}

static void
probe_io_fill(PongCodecProbeIo *io, FakeCodec *f)
{
	io->lpi.read = fake_codec_lpi_read;
	io->lpi.write = fake_codec_lpi_write;
	io->lpi.ctx = f;
	io->lpi.slew_read = fake_codec_slew_read;
	io->lpi.slew_write = fake_codec_slew_write;
	io->lpi.slew_ctx = f;
	io->macro.va.read = fake_codec_va_read;
	io->macro.va.write = fake_codec_va_write;
	io->macro.va.ctx = f;
	io->macro.tx.read = fake_codec_tx_read;
	io->macro.tx.write = fake_codec_tx_write;
	io->macro.tx.ctx = f;
	io->swr.read = fake_codec_swr_read;
	io->swr.write = fake_codec_swr_write;
	io->swr.ctx = f;
}

/* Steps until the machine stops and reports how it stopped. */
static int
probe_run(PongCodecProbe *p, unsigned limit)
{
	unsigned i;

	for (i = 0u; i < limit; i++) {
		int r = pong_codec_probe_step(p);

		if (r == PongCodecProbeDone || r == PongCodecProbeFailed)
			return r;
	}
	return PongCodecProbeRunning;
}

static void
probe_cases(void)
{
	static FakeCodec f;
	PongCodecProbeIo io;
	PongCodecProbe p;
	unsigned writes;

	probe_io_fill(&io, &f);

	/* The gate: without the three LPASS votes nothing is touched at all. */
	memset(&f, 0, sizeof(f));
	expect_eq((unsigned long)pong_codec_probe_start(&p, &io, false, 8u),
	    (unsigned long)-1, "a shut LPASS gate refuses the start");
	expect_eq(p.error, (unsigned long)PongCodecProbeErrLpass, "the refusal is named");
	expect_eq((unsigned long)f.writes, 0ul, "a shut gate writes nothing");
	expect(pong_codec_probe_failed(&p), "the machine reports the failure");
	expect_eq(pong_codec_probe_step(&p), PongCodecProbeFailed,
	    "stepping a refused machine keeps failing");

	/* Incomplete callbacks are refused before anything is read. */
	{
		PongCodecProbeIo partial;

		memset(&partial, 0, sizeof(partial));
		partial.lpi = io.lpi;
		expect_eq((unsigned long)pong_codec_probe_start(&p, &partial, true, 8u),
		    (unsigned long)-1, "missing callbacks refuse the start");
	}

	/* The happy path: v1.7, slave 1 carries the WCD938x id. */
	memset(&f, 0, sizeof(f));
	f.swr[PONG_SWR_COMP_HW_VERSION] = 0x01070000u;
	f.swr[PONG_SWR_SLAVE_STATUS] = 1u << 2;      /* slave 1 present */
	fake_codec_set_slave(&f, 1u, PONG_SWR_WCD938X_ID, 0x1234u);
	f.pads[0] = 0xffffffffu;
	expect_eq((unsigned long)pong_codec_probe_start(&p, &io, true, 8u), 0ul,
	    "the probe starts with the gate open");
	expect_eq((unsigned long)pong_codec_probe_step(&p), (unsigned long)PongCodecProbeRunning,
	    "the first step is the first LPI pad");
	/* (0xffffffff & ~0x3f) | (1 << 2) | 0: function 1, no bus-hold on clock. */
	expect_eq((unsigned long)f.pads[0], 0xffffffc4ul,
	    "pad 0 is written first, before any macro or controller access");
	expect_eq((unsigned long)pong_codec_probe_step(&p), (unsigned long)PongCodecProbeRunning,
	    "the second step is the second pad");
	expect_eq((unsigned long)f.va[0x00], 0ul,
	    "no macro register is written while the pads are still being programmed");

	expect_eq((unsigned long)probe_run(&p, 200u), (unsigned long)PongCodecProbeDone,
	    "the machine finishes");
	expect(pong_codec_probe_done(&p), "it reports done");
	expect(!pong_codec_probe_failed(&p), "and no error");
	expect_eq(p.stage, (unsigned long)PongCodecStageFinished, "the stage is finished");
	expect_eq(p.found_slave, 1ul, "the codec was found on slave 1");
	expect(p.found_id == PONG_SWR_WCD938X_ID, "the full 64-bit id was reassembled");
	expect_eq(p.identity, 0x1234ul, "the identity is low byte first");
	/* Only the identity bytes are read transactions; the two id halves are
	 * plain register reads, as the reference does them. */
	expect_eq(p.reads, 2ul, "two read transactions: the two identity bytes");
	expect_eq(p.timeouts, 0ul, "no timeout on the happy path");

	/* The order the log will show: every pad, then the slew value, then the
	 * macro gates, and only then the controller. */
	expect_eq((unsigned long)f.pads[1], 0x6ul, "pad 1: function 1 plus the data bus-hold bit");
	expect_eq((unsigned long)f.pads[2], 0x6ul, "pad 2: same");
	expect_eq((unsigned long)f.pads[14], 0x6ul, "pad 14: same");
	expect_eq((unsigned long)f.slew, 0x55ul, "the slew register is written last, two bits per pin");
	expect_eq((unsigned long)f.va[0x00], 1ul, "VA MCLK is gated");
	expect_eq((unsigned long)f.tx[0x00], 1ul, "TX MCLK is gated after VA");
	expect(f.swr[PONG_SWR_ENABLE] != 0ul, "the controller was enabled before enumerating");

	/* Stepping a finished machine touches nothing. */
	writes = f.writes;
	expect_eq(pong_codec_probe_step(&p), PongCodecProbeDone,
	    "a finished machine reports done");
	expect_eq((unsigned long)f.writes, (unsigned long)writes,
	    "and writes nothing more");

	/* A bitmap with no slave stops the machine instead of guessing. */
	memset(&f, 0, sizeof(f));
	f.swr[PONG_SWR_COMP_HW_VERSION] = 0x01070000u;
	f.swr[PONG_SWR_SLAVE_STATUS] = 0u;
	(void)pong_codec_probe_start(&p, &io, true, 8u);
	expect_eq((unsigned long)probe_run(&p, 200u), (unsigned long)PongCodecProbeFailed,
	    "an empty bitmap fails the probe");
	expect_eq(p.error, (unsigned long)PongCodecProbeErrNotFound, "the cause is named");

	/* A slave that is present but is not the codec is not configured. */
	memset(&f, 0, sizeof(f));
	f.swr[PONG_SWR_COMP_HW_VERSION] = 0x01070000u;
	f.swr[PONG_SWR_SLAVE_STATUS] = 1u << 2;
	fake_codec_set_slave(&f, 1u, 0x000d01179999ull, 0x1234u);
	(void)pong_codec_probe_start(&p, &io, true, 8u);
	expect_eq((unsigned long)probe_run(&p, 200u), (unsigned long)PongCodecProbeFailed,
	    "another slave id is not the codec");
	expect_eq(p.error, (unsigned long)PongCodecProbeErrNotFound, "and is reported as absent");

	/* A silent master: the poll budget runs out and the transaction is aborted
	 * rather than left in flight. */
	memset(&f, 0, sizeof(f));
	f.swr[PONG_SWR_COMP_HW_VERSION] = 0x01070000u;
	f.swr[PONG_SWR_SLAVE_STATUS] = 1u << 2;
	fake_codec_set_slave(&f, 1u, PONG_SWR_WCD938X_ID, 0x1234u);
	f.swr_silent = 1u;
	(void)pong_codec_probe_start(&p, &io, true, 4u);
	expect_eq((unsigned long)probe_run(&p, 200u), (unsigned long)PongCodecProbeFailed,
	    "a silent master fails the probe");
	expect_eq(p.error, (unsigned long)PongCodecProbeErrTimeout, "the cause is a timeout");
	expect(p.timeouts > 0ul, "the timeout is counted");
	expect_eq((unsigned long)f.swr[PONG_SWR_ABORT], 1ul,
	    "the outstanding transaction is aborted, not left in flight");

	/* An unknown controller stops the machine at the version read. */
	memset(&f, 0, sizeof(f));
	f.swr[PONG_SWR_COMP_HW_VERSION] = 0x03000000u;
	(void)pong_codec_probe_start(&p, &io, true, 8u);
	expect_eq((unsigned long)probe_run(&p, 200u), (unsigned long)PongCodecProbeFailed,
	    "an unknown controller fails the probe");
	expect_eq(p.error, (unsigned long)PongCodecProbeErrSwr, "the cause is the controller");

	/* v2 has to wait for its execution environment before enumerating. */
	memset(&f, 0, sizeof(f));
	f.swr[PONG_SWR_COMP_HW_VERSION] = 0x02010000u;
	f.swr[PONG_SWR_V2_ENV_STATUS] = PONG_SWR_V2_ENV_READY;
	f.swr[PONG_SWR_SLAVE_STATUS] = 1u << 2;
	fake_codec_set_slave(&f, 1u, PONG_SWR_WCD938X_ID, 0x5678u);
	(void)pong_codec_probe_start(&p, &io, true, 8u);
	expect_eq((unsigned long)probe_run(&p, 300u), (unsigned long)PongCodecProbeDone,
	    "a v2 controller finishes once its environment is up");
	expect_eq(p.identity, 0x5678ul, "v2 reads the identity the same way");
	expect_eq((unsigned long)f.swr[PONG_SWR_V2_ENV_CTRL], 1ul,
	    "v2 brings its environment up");

	/* v2 that never comes up is a timeout, not a silent success. */
	memset(&f, 0, sizeof(f));
	f.swr[PONG_SWR_COMP_HW_VERSION] = 0x02010000u;
	(void)pong_codec_probe_start(&p, &io, true, 4u);
	expect_eq((unsigned long)probe_run(&p, 200u), (unsigned long)PongCodecProbeFailed,
	    "a v2 environment that never comes up fails");
	expect_eq(p.error, (unsigned long)PongCodecProbeErrTimeout, "and is a timeout");
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
	codec_cases();
	swr_cases();
	lpi_cases();
	macro_cases();
	probe_cases();

	if (fails) {
		printf("TESTS FAILED %d of %d\n", fails, cases);
		return 1;
	}
	printf("TESTS OK %d cases\n", cases);
	return 0;
}
