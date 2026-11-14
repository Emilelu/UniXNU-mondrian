/* SPDX-License-Identifier: BSD-2-Clause-Patent
 *
 * One read transaction on the LPASS VA SoundWire master, as an event-driven
 * state machine, plus the enumerator step that names the slaves.
 *
 * Same shape as PongAudioGeniI2c.h and for the same reason: the owner starts a
 * transaction, feeds it until it answers or its deadline passes, and nothing
 * here waits or spins. That keeps the timing decisions in the caller (which
 * knows how long it may block at boot) and keeps this file host-testable.
 *
 * The register numbers and the command layout live in PongCodecPlan.h, where
 * the host test already pins them; this file only turns them into a sequence.
 *
 *   S  /mnt/e/k60-work/references/pong-power/PongWcd938.h:43-58, :88-96
 *   W  docs/research/audio/SOUNDWIRE.md §3, §3.1
 */
#ifndef PONG_CODEC_SWR_H
#define PONG_CODEC_SWR_H

#include <stdbool.h>
#include <stdint.h>

#include "PongCodecPlan.h"

/* Register offsets this half touches. The read-transaction group is not here:
 * it depends on the controller version and comes from pong_swr_read_regs(). */
#define PONG_SWR_COMP_HW_VERSION 0x000u
#define PONG_SWR_ABORT           0x308u
#define PONG_SWR_ENUMERATOR_CFG  0x500u
#define PONG_SWR_SLAVE_STATUS    0x1090u

typedef struct {
	uint32_t (*read)(void *ctx, uint32_t reg);
	void (*write)(void *ctx, uint32_t reg, uint32_t value);
	void *ctx;
} PongSwrIo;

/* PongSwrIdle: no transaction outstanding. PongSwrAwaiting: a read command was
 * written and its response has not been collected yet. */
enum { PongSwrIdle = 0, PongSwrAwaiting = 1 };

/* PongSwrPending / Done / Failed are the poll outcomes, matching the GENI
 * state machine's vocabulary so the two probes read the same way. */
enum { PongSwrPending = 0, PongSwrDone = 1, PongSwrFailed = 2 };

enum {
	PongSwrOk = 0,
	PongSwrErrBusy = 1,     /* a transaction is already outstanding */
	PongSwrErrVersion = 2,  /* COMP_HW_VERSION is neither v1.7 nor v2 */
	PongSwrErrFifo = 3,     /* the command FIFO is full: nothing was written */
	PongSwrErrTimeout = 4,  /* the deadline passed; the transaction was aborted */
	PongSwrErrTxn = 5,      /* the response carried someone else's transaction id */
	PongSwrErrState = 6     /* a step arrived in a state that cannot take it */
};

typedef struct {
	PongSwrIo io;
	PongSwrVersion version;
	PongSwrReadRegs regs;
	uint8_t state, error;
	unsigned issued;         /* transactions started so far (drives the id) */
	unsigned txn;            /* id of the outstanding transaction */
	unsigned device, reg;    /* what the outstanding transaction asks for */
	uint32_t hw_version;     /* COMP_HW_VERSION as read at probe time */
	uint32_t raw;            /* the last response word, before unpacking */
	uint32_t slave_status;   /* MCP_SLV_STATUS as read at enumerate time */
	uint8_t data;            /* the byte the last read returned */
	uint32_t reads, aborts, timeouts;
} PongSwr;

/* Reads COMP_HW_VERSION, picks the register group, and leaves the machine Idle.
 * Returns 0, or -1 with error = PongSwrErrVersion: an unknown controller must
 * stop the codec half rather than fall back to a guess (W:8 item 1). */
int pong_swr_probe(PongSwr *s, const PongSwrIo *io);

/* Starts a read of one 8-bit register on one slave. Refuses with -1 and
 * PongSwrErrFifo when the command FIFO is full (nothing is written then), or
 * -1 with PongSwrErrBusy when a transaction is still outstanding. */
int pong_swr_read_start(PongSwr *s, unsigned device, unsigned reg);

/* Collects the response if there is one. PongSwrPending means the master has
 * not answered yet and the caller should come back; PongSwrDone leaves the byte
 * in s->data; PongSwrFailed means the response belonged to another transaction,
 * which aborts it (0x308 <- 1) rather than retrying under the same id. */
int pong_swr_read_poll(PongSwr *s);

/* The caller's deadline passed: abort the transaction (0x308 <- 1). */
int pong_swr_read_timeout(PongSwr *s);

/* Enables the enumerator and latches MCP_SLV_STATUS into s->slave_status.
 * The slave ids themselves are two ordinary reads per slave, so the caller
 * loops over pong_swr_slave_present() using the same start/poll pair. */
int pong_swr_enumerate_start(PongSwr *s);

static inline bool
pong_swr_busy(const PongSwr *s)
{
	return s->state != PongSwrIdle;
}

static inline bool
pong_swr_slave_at(const PongSwr *s, unsigned n)
{
	return pong_swr_slave_present(s->slave_status, n);
}

#endif /* PONG_CODEC_SWR_H */
