/* SPDX-License-Identifier: BSD-2-Clause-Patent
 * Ported from /mnt/e/k60-work/references/pong-power/GeniI2c.c (SM8475). The
 * logic is unchanged except for the symbol prefix; the comment on each command
 * field ties it to the mainline decoder so the values are checkable:
 *   M_CMD0 = opcode << 27 | params        (geni-se.h:154-156, qcom-geni-se.c:348)
 *   params: slave address in bits 15:9, STOP_STRETCH bit 2
 *                                        (i2c-qcom-geni.c:39-46, :876-884)
 */
#include "PongAudioGeniI2c.h"

static uint32_t rdp(PongGeniI2c *g, uint32_t reg) { return g->io.read(g->io.ctx, reg); }
static void wrp(PongGeniI2c *g, uint32_t reg, uint32_t value) { g->io.write(g->io.ctx, reg, value); }

int
pong_geni_prepare(PongGeniI2c *g, const PongGeniIo *io, uint8_t address, uint32_t *config)
{
	for (unsigned i = 0; i < sizeof *g; ++i) ((uint8_t *)g)[i] = 0;
	g->io = *io;
	g->address = address;
	const uint32_t proto = (rdp(g, PONG_GENI_FW_REVISION) >> 8) & 0xffu, clock = rdp(g, PONG_GENI_CLK_CFG);
	if (config) *config = (proto << 24) | (clock & 0xffffffu);
	if (proto != PONG_GENI_PROTO_I2C || (rdp(g, PONG_GENI_IF_DISABLE) & 1u) ||
	    !(clock & 1u) || !rdp(g, PONG_GENI_SCL_COUNTERS))
		return -1;
	wrp(g, PONG_GENI_DMA_MODE, 0);
	/* 8-bit words, 4 per FIFO word, least significant byte first on the wire. */
	wrp(g, PONG_GENI_TX_PACK0, 0x7f8fe); wrp(g, PONG_GENI_TX_PACK1, 0xffefe);
	wrp(g, PONG_GENI_RX_PACK0, 0x7f8fe); wrp(g, PONG_GENI_RX_PACK1, 0xffefe);
	wrp(g, PONG_GENI_BYTE_GRAN, 0);
	wrp(g, PONG_GENI_TX_WATERMARK, 0);
	wrp(g, PONG_GENI_M_IRQ_CLEAR, 0xffffffffu);
	/* Exactly the bits this core handles: one the boot loader left enabled (RX
	 * watermark, RX last) would hold the level line up. */
	wrp(g, PONG_GENI_M_IRQ_EN, PONG_GENI_M_IRQ_WANTED);
	wrp(g, PONG_GENI_SE_IRQ_EN, rdp(g, PONG_GENI_SE_IRQ_EN) | PONG_GENI_SE_M_IRQ_EN);
	return 0;
}

/* Starts one write command of `length` bytes (at most 8); the data goes in when
 * the engine asks for it (TX watermark). */
static void
write_command(PongGeniI2c *g, const uint8_t *bytes, uint32_t length, int hold)
{
	g->tx[0] = g->tx[1] = 0;
	for (uint32_t i = 0; i < length; ++i) g->tx[i / 4] |= (uint32_t)bytes[i] << (8 * (i % 4));
	g->tx_words = (uint8_t)((length + 3) / 4);
	g->length = length;
	g->hold = (uint8_t)hold;
	wrp(g, PONG_GENI_TX_LEN, length);
	wrp(g, PONG_GENI_M_CMD0, (PONG_GENI_OP_WRITE << 27) | ((uint32_t)g->address << 9) |
	    (hold ? PONG_GENI_STOP_STRETCH : 0));
	wrp(g, PONG_GENI_TX_WATERMARK, 1);
	g->phase = PongGeniTxWait;
}

int
pong_geni_start_write(PongGeniI2c *g, uint8_t reg, uint8_t value)
{
	if (g->phase != PongGeniIdle) return -1;
	g->reading = 0; g->reg = reg; g->value = value; g->error = PongGeniOk;
	const uint8_t bytes[2] = { reg, value };
	write_command(g, bytes, 2, 0);
	return 0;
}

int
pong_geni_start_read(PongGeniI2c *g, uint8_t reg)
{
	if (g->phase != PongGeniIdle) return -1;
	g->reading = 1; g->rx_length = 1; g->reg = reg; g->error = PongGeniOk;
	write_command(g, &reg, 1, 1);
	return 0;
}

int
pong_geni_start_write_bytes(PongGeniI2c *g, const uint8_t *bytes, uint32_t length)
{
	if (g->phase != PongGeniIdle || !length || length > 8) return -1;
	g->reading = 0; g->error = PongGeniOk;
	write_command(g, bytes, length, 0);
	return 0;
}

int
pong_geni_start_read_bytes(PongGeniI2c *g, const uint8_t *bytes, uint32_t length, uint32_t read_length)
{
	if (g->phase != PongGeniIdle || !length || length > 4 || !read_length || read_length > 4) return -1;
	g->reading = 1; g->rx_length = (uint8_t)read_length; g->error = PongGeniOk;
	write_command(g, bytes, length, 1);
	return 0;
}

static int
finish(PongGeniI2c *g, int error, uint32_t status)
{
	g->phase = PongGeniIdle;
	wrp(g, PONG_GENI_TX_WATERMARK, 0);
	if (!error) { g->done++; return PongGeniDone; }
	g->error = (uint8_t)error;
	g->error_status = status;
	g->failed++;
	return PongGeniFailed;
}

int
pong_geni_event(PongGeniI2c *g, uint32_t status)
{
	if (!status) return PongGeniPending;
	switch (g->phase) {
	case PongGeniIdle:
		g->stray++;
		return PongGeniPending;
	case PongGeniCancelling:
		if (status & PONG_GENI_M_CMD_CANCEL) return finish(g, PongGeniErrTimeout, g->error_status);
		return PongGeniPending;
	case PongGeniAborting:
		if (status & PONG_GENI_M_CMD_ABORT) return finish(g, PongGeniErrTimeout, g->error_status);
		return PongGeniPending;
	default:
		break;
	}
	/* A failed command also ends with CMD_DONE; the error bits decide. */
	if (status & PONG_GENI_M_ERRORS) return finish(g, PongGeniErrBus, status);
	if (g->phase == PongGeniTxWait) {
		if (status & PONG_GENI_M_TX_WATERMARK) {
			for (unsigned i = 0; i < g->tx_words; ++i) wrp(g, PONG_GENI_TX_FIFO, g->tx[i]);
			wrp(g, PONG_GENI_TX_WATERMARK, 0);
			g->phase = PongGeniWriteDone;
		}
		if (!(status & PONG_GENI_M_CMD_DONE)) return PongGeniPending;
		if (g->phase == PongGeniTxWait) return finish(g, PongGeniErrState, status);
	}
	if (!(status & PONG_GENI_M_CMD_DONE)) return PongGeniPending;
	if (g->phase == PongGeniWriteDone) {
		if (!g->reading) return finish(g, PongGeniOk, 0);
		wrp(g, PONG_GENI_RX_LEN, g->rx_length);
		wrp(g, PONG_GENI_M_CMD0, (PONG_GENI_OP_READ << 27) | ((uint32_t)g->address << 9));
		g->phase = PongGeniReadDone;
		return PongGeniPending;
	}
	/* PongGeniReadDone */
	if (!(rdp(g, PONG_GENI_RX_FIFO_STATUS) & 0x1ffffffu)) return finish(g, PongGeniErrNoData, status);
	g->rx = rdp(g, PONG_GENI_RX_FIFO);
	g->data = (uint8_t)g->rx;
	return finish(g, PongGeniOk, 0);
}

int
pong_geni_poll(PongGeniI2c *g)
{
	const uint32_t status = rdp(g, PONG_GENI_M_IRQ_STATUS);
	if (status) wrp(g, PONG_GENI_M_IRQ_CLEAR, status);
	return g->phase == PongGeniIdle ? PongGeniPending : pong_geni_event(g, status);
}

int
pong_geni_timeout(PongGeniI2c *g)
{
	switch (g->phase) {
	case PongGeniIdle:
		return PongGeniPending;
	case PongGeniCancelling:
		wrp(g, PONG_GENI_M_CMD_CTRL, PONG_GENI_CMD_CTRL_ABORT);
		g->phase = PongGeniAborting;
		return PongGeniPending;
	case PongGeniAborting:
		return finish(g, PongGeniErrTimeout, g->error_status);
	default:
		g->timeouts++;
		g->error_status = rdp(g, PONG_GENI_M_IRQ_STATUS);
		wrp(g, PONG_GENI_TX_WATERMARK, 0);
		wrp(g, PONG_GENI_M_CMD_CTRL, PONG_GENI_CMD_CTRL_CANCEL);
		g->phase = PongGeniCancelling;
		return PongGeniPending;
	}
}
