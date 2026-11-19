/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* The codec half's boot order, in one place. See PongCodecProbe.h.
 *
 * The four sequencers next door each own one block and none of them waits.
 * This file is the one that owns the order, the poll budget, and the decision
 * to stop: a read that does not answer is a timeout, not a reason to move on to
 * the next register block. That is the lesson of 2026-11-09 (HR-02): the GENI
 * hang came from touching a block whose predecessor had not acknowledged.
 */
#include <string.h>

#include "PongCodecProbe.h"

static bool
probe_io_complete(const PongCodecProbeIo *io)
{
	return io != NULL &&
	    io->lpi.read != NULL && io->lpi.write != NULL &&
	    io->lpi.slew_read != NULL && io->lpi.slew_write != NULL &&
	    io->macro.va.read != NULL && io->macro.va.write != NULL &&
	    io->macro.tx.read != NULL && io->macro.tx.write != NULL &&
	    io->swr.read != NULL && io->swr.write != NULL;
}

int
pong_codec_probe_start(PongCodecProbe *p, const PongCodecProbeIo *io,
    bool lpass_ready, unsigned max_polls)
{
	if (p == NULL || !probe_io_complete(io))
		return -1;

	memset(p, 0, sizeof(*p));
	p->io = *io;
	p->max_polls = max_polls;
	p->stage = PongCodecStageLpi;

	if (!lpass_ready) {
		/* The three votes are the Lead's, not ours. Refusing here means
		 * the caller gets a named reason instead of a bus hang. */
		p->error = PongCodecProbeErrLpass;
		return -1;
	}

	pong_codec_lpi_start(&p->lpi, &p->io.lpi);
	pong_codec_macro_start(&p->macro, &p->io.macro);
	return 0;
}

/* One poll of the outstanding read, or a failure that names its cause. */
static int
probe_poll(PongCodecProbe *p)
{
	int r = pong_swr_read_poll(&p->swr);

	if (r == PongSwrPending) {
		p->polls++;
		if (p->polls >= p->max_polls) {
			/* Out of budget. Abort the transaction rather than leave a
			 * command in flight whose answer would arrive later and be
			 * attributed to the next read. */
			(void)pong_swr_read_timeout(&p->swr);
			p->timeouts++;
			p->error = PongCodecProbeErrTimeout;
			return PongCodecProbeFailed;
		}
		return PongCodecProbeWaiting;
	}
	if (r == PongSwrFailed) {
		p->error = PongCodecProbeErrSwr;
		return PongCodecProbeFailed;
	}

	p->read_pending = 0u;
	p->polls = 0u;
	p->reads++;
	p->last = p->swr.data;
	return PongCodecProbeRunning;
}

/* Issues one read and remembers that its answer is owed to us. */
static int
probe_read(PongCodecProbe *p, unsigned device, unsigned reg, unsigned next)
{
	if (pong_swr_read_start(&p->swr, device, reg) != 0) {
		p->error = PongCodecProbeErrSwr;
		return PongCodecProbeFailed;
	}
	p->read_pending = 1u;
	p->polls = 0u;
	p->substep = next;
	return PongCodecProbeRunning;
}

int
pong_codec_probe_step(PongCodecProbe *p)
{
	if (p == NULL)
		return PongCodecProbeFailed;
	if (p->stage == PongCodecStageFinished)
		return PongCodecProbeDone;
	if (p->error != PongCodecProbeOk)
		return PongCodecProbeFailed;

	/* An outstanding read is always served first: the stage handlers below
	 * assume that when they run, any read they asked for has landed in
	 * p->last. */
	if (p->read_pending != 0u) {
		int r = probe_poll(p);

		if (r != PongCodecProbeRunning)
			return r;
	}

	switch (p->stage) {
	case PongCodecStageLpi:
		/* Four pads then the slew value. Nothing here waits, so one step
		 * per call keeps the caller's budget visible. */
		if (pong_codec_lpi_step(&p->lpi))
			return PongCodecProbeRunning;
		if (!pong_codec_lpi_done(&p->lpi)) {
			p->error = PongCodecProbeErrLpi;
			return PongCodecProbeFailed;
		}
		p->stage = PongCodecStageMacro;
		return PongCodecProbeRunning;

	case PongCodecStageMacro:
		/* Nine VA/TX clock-gate steps. VA must be gated before TX, which
		 * the table in PongCodecMacro.c already encodes. */
		if (pong_codec_macro_step(&p->macro))
			return PongCodecProbeRunning;
		if (!pong_codec_macro_done(&p->macro)) {
			p->error = PongCodecProbeErrMacro;
			return PongCodecProbeFailed;
		}
		p->stage = PongCodecStageSwrProbe;
		return PongCodecProbeRunning;

	case PongCodecStageSwrProbe:
		/* Reading COMP_HW_VERSION is the first access that can hang the
		 * bus, which is why the pads and the macro gates went first. An
		 * unknown version stops the machine here. */
		if (pong_swr_probe(&p->swr, &p->io.swr) != 0) {
			p->error = PongCodecProbeErrSwr;
			return PongCodecProbeFailed;
		}
		p->stage = PongCodecStageSwrInit;
		return PongCodecProbeRunning;

	case PongCodecStageSwrInit:
		if (pong_swr_init(&p->swr) != 0) {
			p->error = PongCodecProbeErrSwr;
			return PongCodecProbeFailed;
		}
		p->polls = 0u;
		p->stage = PongCodecStageSwrEnv;
		return PongCodecProbeRunning;

	case PongCodecStageSwrEnv:
		/* v2 brings the CPU execution environment up and has to be waited
		 * for; v1.7 has nothing to wait for and reports ready at once. */
		if (pong_swr_init_done(&p->swr)) {
			p->polls = 0u;
			p->stage = PongCodecStageEnumerate;
			return PongCodecProbeRunning;
		}
		p->polls++;
		if (p->polls >= p->max_polls) {
			p->timeouts++;
			p->error = PongCodecProbeErrTimeout;
			return PongCodecProbeFailed;
		}
		return PongCodecProbeWaiting;

	case PongCodecStageEnumerate:
		if (pong_swr_enumerate_start(&p->swr) != 0) {
			p->error = PongCodecProbeErrSwr;
			return PongCodecProbeFailed;
		}
		p->slave = PONG_SWR_SLAVE_FIRST;
		p->substep = 0u;
		p->stage = PongCodecStageSlaveId;
		return PongCodecProbeRunning;

	case PongCodecStageSlaveId:
		/* The slave id is two ordinary 32-bit register reads, not two read
		 * transactions: S:PongWcd938.h:108-109 reads 0x530+8n and
		 * 0x534+8n directly. The byte-wide transaction path below is only
		 * for the codec's own registers. Slaves that are not in the bitmap
		 * are skipped without a read - reading a silent slave costs a full
		 * poll budget per register and tells us nothing. */
		while (p->slave <= PONG_SWR_SLAVE_LAST &&
		    !pong_swr_slave_at(&p->swr, p->slave))
			p->slave++;
		if (p->slave > PONG_SWR_SLAVE_LAST) {
			p->error = PongCodecProbeErrNotFound;
			return PongCodecProbeFailed;
		}
		{
			uint32_t lo = p->io.swr.read(p->io.swr.ctx,
			    pong_swr_slave_id_reg(p->slave));
			uint32_t hi = p->io.swr.read(p->io.swr.ctx,
			    pong_swr_slave_id_reg(p->slave) + 4u);
			uint64_t id = pong_swr_slave_id(lo, hi);

			if (pong_swr_is_wcd938x(id)) {
				/* The DTS names exactly one slave. Configuring
				 * another one would drive a codec we know nothing
				 * about. */
				p->found_slave = p->slave;
				p->found_id = id;
				p->stage = PongCodecStageIdentity;
				p->substep = 0u;
				return PongCodecProbeRunning;
			}
			p->slave++;
			return PongCodecProbeRunning;
		}

	case PongCodecStageIdentity:
		/* Two consecutive 8-bit reads, low byte first
		 * (S:PongWcd938.h:117-118). */
		if (p->substep == 0u)
			return probe_read(p, p->found_slave, 0x50u, 1u);
		if (p->substep == 1u) {
			p->identity_lo = p->last;
			return probe_read(p, p->found_slave, 0x51u, 2u);
		}
		p->identity = pong_swr_codec_identity(p->identity_lo, p->last);
		p->stage = PongCodecStageFinished;
		return PongCodecProbeDone;

	default:
		p->error = PongCodecProbeErrSwr;
		return PongCodecProbeFailed;
	}
}
