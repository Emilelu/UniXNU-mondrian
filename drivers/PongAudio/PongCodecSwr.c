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
