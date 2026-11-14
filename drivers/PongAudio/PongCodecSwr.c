/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* The read-transaction half of the LPASS VA SoundWire master. See
 * PongCodecSwr.h for the contract and PongCodecPlan.h for the register
 * numbers, which the host test already pins separately.
 *
 * Every function here is a handful of register accesses and a return: the
 * caller owns the deadline. That is deliberate - the boot path that will use
 * this has a budget it cannot blow, and a spinning helper would hide it.
 */
#include "PongCodecSwr.h"

static uint32_t
swr_read(PongSwr *s, uint32_t reg)
{
	return s->io.read(s->io.ctx, reg);
}

static void
swr_write(PongSwr *s, uint32_t reg, uint32_t value)
{
	s->io.write(s->io.ctx, reg, value);
}

static void
swr_abort(PongSwr *s)
{
	swr_write(s, PONG_SWR_ABORT, 1u);
	s->aborts++;
	s->state = PongSwrIdle;
}

int
pong_swr_probe(PongSwr *s, const PongSwrIo *io)
{
	if (s == NULL || io == NULL || io->read == NULL || io->write == NULL)
		return -1;
	s->io = *io;
	s->state = PongSwrIdle;
	s->error = PongSwrOk;
	s->issued = 0u;
	s->txn = 0u;
	s->device = 0u;
	s->reg = 0u;
	s->raw = 0u;
	s->data = 0u;
	s->slave_status = 0u;
	s->reads = 0u;
	s->aborts = 0u;
	s->timeouts = 0u;

	s->hw_version = swr_read(s, PONG_SWR_COMP_HW_VERSION);
	s->version = pong_swr_version(s->hw_version);
	if (!pong_swr_read_regs(s->version, &s->regs)) {
		/* An unknown controller is a stop, not a guess: the read group
		 * differs between v1.7 and v2, so picking one blindly would
		 * write commands into the wrong registers. */
		s->error = PongSwrErrVersion;
		return -1;
	}
	return 0;
}

int
pong_swr_read_start(PongSwr *s, unsigned device, unsigned reg)
{
	uint32_t fifo;

	if (s->state != PongSwrIdle) {
		s->error = PongSwrErrBusy;
		return -1;
	}
	fifo = swr_read(s, s->regs.fifo_status);
	if (pong_swr_fifo_full(fifo)) {
		/* Nothing is written when the FIFO is full: the command would be
		 * dropped, and a dropped command with a fresh transaction id is
		 * indistinguishable from a slave that never answered. */
		s->error = PongSwrErrFifo;
		return -1;
	}

	s->txn = pong_swr_txn_id(s->issued);
	s->issued++;
	s->device = device;
	s->reg = reg;
	s->error = PongSwrOk;
	s->state = PongSwrAwaiting;
	s->reads++;
	swr_write(s, s->regs.read_command,
	    pong_swr_read_command(device, s->txn, reg));
	return 0;
}

int
pong_swr_read_poll(PongSwr *s)
{
	uint32_t fifo;

	if (s->state != PongSwrAwaiting) {
		s->error = PongSwrErrState;
		return PongSwrFailed;
	}
	/* Bits 20:16 of the FIFO status count the responses waiting to be
	 * collected; zero means the master has not answered yet. */
	fifo = swr_read(s, s->regs.fifo_status);
	if (((fifo >> 16) & 31u) == 0u)
		return PongSwrPending;

	s->raw = swr_read(s, s->regs.read_fifo);
	if (!pong_swr_response_ok(s->raw, s->txn)) {
		/* Someone else's answer. Abort rather than retry under the same
		 * id: the outstanding command may still be in flight. */
		s->error = PongSwrErrTxn;
		swr_abort(s);
		return PongSwrFailed;
	}
	s->data = (uint8_t)pong_swr_response_data(s->raw);
	s->error = PongSwrOk;
	s->state = PongSwrIdle;
	return PongSwrDone;
}

int
pong_swr_read_timeout(PongSwr *s)
{
	if (s->state != PongSwrAwaiting) {
		s->error = PongSwrErrState;
		return -1;
	}
	s->timeouts++;
	s->error = PongSwrErrTimeout;
	swr_abort(s);
	return -1;
}

int
pong_swr_init(PongSwr *s)
{
	uint32_t cfg;

	if (s->version == PongSwrUnknown) {
		s->error = PongSwrErrVersion;
		return -1;
	}
	/* Both versions: enable the block, set the frame shape, turn the
	 * enumerator on, and clear then set the 5-bit MCP configuration field.
	 * The read-modify-write is the reference's, verbatim. */
	swr_write(s, PONG_SWR_COMP_CFG2, 1u);
	swr_write(s, PONG_SWR_FRAME_CTRL, (1u << 3) | 7u);
	swr_write(s, PONG_SWR_ENUMERATOR_CFG, 1u);
	cfg = swr_read(s, PONG_SWR_CFG);
	cfg &= ~(0x1fu << 17);
	cfg |= 0x1fu << 17;
	swr_write(s, PONG_SWR_CFG, cfg);
	swr_write(s, PONG_SWR_ENABLE, 1u);

	if (s->version == PongSwrV17) {
		/* SM8475 1.7: CPU1 command FIFO and interrupt offsets differ from
		 * the SM8550 v2 layout. Execution environment 1, then the masks,
		 * then move to environment 3. */
		uint32_t status, mask;

		swr_write(s, 0x314u, 7u);
		swr_write(s, PONG_SWR_BUS_CTRL, 4u);
		swr_write(s, PONG_SWR_COMP_CFG, 2u);
		pong_swr_v17_intr_masks(&status, &mask);
		swr_write(s, 0x208u, status);
		swr_write(s, 0x210u, mask);
		swr_write(s, PONG_SWR_COMP_CFG, 3u);
	} else {
		swr_write(s, PONG_SWR_V2_ENV_CTRL, 1u);
		swr_write(s, 0x314u, 7u | (1u << 31));
		swr_write(s, PONG_SWR_COMP_CFG, 1u);
		swr_write(s, PONG_SWR_COMP_CFG, 2u);
		swr_write(s, PONG_SWR_V2_IRQ_CLEAR, 0xffffffffu);
		swr_write(s, PONG_SWR_V2_IRQ_MASK, 0x1ffffu);
		swr_write(s, PONG_SWR_COMP_CFG, 3u);
	}
	return 0;
}

bool
pong_swr_init_done(PongSwr *s)
{
	if (s->version == PongSwrV17)
		return true;
	if (s->version != PongSwrV2)
		return false;
	return (swr_read(s, PONG_SWR_V2_ENV_STATUS) & PONG_SWR_V2_ENV_READY) != 0u;
}

int
pong_swr_enumerate_start(PongSwr *s)
{
	if (s->state != PongSwrIdle) {
		s->error = PongSwrErrBusy;
		return -1;
	}
	swr_write(s, PONG_SWR_ENUMERATOR_CFG, 1u);
	s->slave_status = swr_read(s, PONG_SWR_SLAVE_STATUS);
	return 0;
}
