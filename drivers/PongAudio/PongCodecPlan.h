/* SPDX-License-Identifier: BSD-2-Clause-Patent
 *
 * K60 codec-side decisions, as pure functions.
 *
 * The SoundWire / WCD938x half of the port cannot touch hardware yet: every LPASS
 * macro and the VA SoundWire master need two PRM block votes plus the 0x30c clock
 * acknowledgement from the ADSP first (W:4, S:PongWcd938.h:59-120), and the ADSP
 * does not boot yet. What can be settled before that is everything the driver has
 * to decide: which SoundWire controller version it is talking to, which register
 * group carries a read transaction, how a read command word is composed, when the
 * command FIFO refuses one, whether a response belongs to the transaction that
 * asked for it, how the enumerator bitmap names slaves, and what the LPI pads have
 * to look like.
 *
 * Keeping those here - no MMIO, no kernel headers - means the host test pins them
 * now, so the eventual on-device read is a thin loop over proven numbers. Same
 * split as PongAudioPlan.h for the amplifier path.
 *
 *   S  /mnt/e/k60-work/references/pong-power/PongWcd938.h
 *   W  docs/research/audio/SOUNDWIRE.md  (live FDT offsets, mainline cross-check)
 */
#ifndef PONG_CODEC_PLAN_H
#define PONG_CODEC_PLAN_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* ---- SoundWire controller version ---------------------------------------
 * S:PongWcd938.h:88-91  v17 = (r(0) == 0x01070000); otherwise the controller
 * must report major version 2 in the top byte of COMP_HW_VERSION.
 * W:2.1  the K60 DT interrupt pair <0 0x1f0 4>, <0 0x208 4> matches mainline's
 * v1.7 layout, so 0x01070000 is the expected answer rather than a guess. The
 * probe still has to read it: an unknown version must stop, not guess.
 */
typedef enum {
	PongSwrUnknown = 0,
	PongSwrV17 = 1,
	PongSwrV2 = 2
} PongSwrVersion;

static inline PongSwrVersion
pong_swr_version(uint32_t hw_version)
{
	if (hw_version == 0x01070000u)
		return PongSwrV17;
	if ((hw_version >> 24) == 2u)
		return PongSwrV2;
	return PongSwrUnknown;
}

/* ---- Read-transaction register group ------------------------------------
 * S:PongWcd938.h:43-58  v1.7 overrides the group to 0x320 / 0x328 / 0x334.
 * W:3  v2 keeps the mainline defaults 0x5024 / 0x5050 / 0x5040; the
 * 0x5060 / 0x5008 / 0x5004 / 0x5064 registers are v2 initialisation writes,
 * not the read path.
 */
typedef struct {
	uint32_t read_command;
	uint32_t fifo_status;
	uint32_t read_fifo;
} PongSwrReadRegs;

static inline bool
pong_swr_read_regs(PongSwrVersion version, PongSwrReadRegs *regs)
{
	if (regs == NULL)
		return false;
	switch (version) {
	case PongSwrV17:
		regs->read_command = 0x320u;
		regs->fifo_status = 0x328u;
		regs->read_fifo = 0x334u;
		return true;
	case PongSwrV2:
		regs->read_command = 0x5024u;
		regs->fifo_status = 0x5050u;
		regs->read_fifo = 0x5040u;
		return true;
	default:
		return false;
	}
}

/* S:PongWcd938.h:43-58  id = (++transaction % 14) + 1. The pre-increment is
 * load-bearing: 'issued' below counts transactions started *before* this one,
 * so the first id is 2, not 1, and the cycle is 2,3,...,14,1. Only the
 * uniqueness within 14 matters for correctness, but matching the proven
 * sequence exactly means a captured trace can be compared line by line.
 */
static inline unsigned
pong_swr_txn_id(unsigned issued)
{
	return ((issued + 1u) % 14u) + 1u;
}

/* (1u<<24) | (device<<20) | (id<<16) | reg  - S:PongWcd938.h:47-48. */
static inline uint32_t
pong_swr_read_command(unsigned device, unsigned txn, unsigned reg)
{
	return (1u << 24) | ((device & 0xfu) << 20) | ((txn & 0xfu) << 16) |
	    (reg & 0xffffu);
}

/* ((fifo >> 8) & 31) >= 8 means the command FIFO would drop this write. */
static inline bool
pong_swr_fifo_full(uint32_t fifo)
{
	return ((fifo >> 8) & 31u) >= 8u;
}

/* A response is only ours when the transaction id packed in bits 11:8 matches
 * (S:PongWcd938.h:52-54). A mismatch is an abort (0x308 <- 1), never a retry
 * with the same id.
 */
static inline bool
pong_swr_response_ok(uint32_t value, unsigned txn)
{
	return ((value >> 8) & 15u) == (txn & 15u);
}

static inline uint32_t
pong_swr_response_data(uint32_t value)
{
	return value & 0xffu;
}

/* v1.7 masks both interrupt lines before enumerating (S:PongWcd938.h:88-96). */
static inline void
pong_swr_v17_intr_masks(uint32_t *status, uint32_t *mask)
{
	if (status != NULL)
		*status = 0xffffffffu;
	if (mask != NULL)
		*mask = 0x1dfdfdu;
}

/* ---- Enumerator --------------------------------------------------------
 * W:3  status = r(0x1090); slave n (1..11) is present when bits 2n+1:2n are
 * non-zero, and its 64-bit SoundWire id is r(0x530+8n) | (r(0x534+8n) << 32).
 * n starts at 1: entry 0 of the bitmap is the master itself.
 */
#define PONG_SWR_SLAVE_FIRST 1u
#define PONG_SWR_SLAVE_LAST  11u
#define PONG_SWR_WCD938X_ID  0x000d01170223ull

static inline bool
pong_swr_slave_present(uint32_t status, unsigned n)
{
	if (n < PONG_SWR_SLAVE_FIRST || n > PONG_SWR_SLAVE_LAST)
		return false;
	return ((status >> (2u * n)) & 3u) != 0u;
}

static inline unsigned
pong_swr_slave_id_reg(unsigned n)
{
	return 0x530u + 8u * n;
}

static inline uint64_t
pong_swr_slave_id(uint32_t lo, uint32_t hi)
{
	return ((uint64_t)hi << 32) | (uint64_t)lo;
}

static inline bool
pong_swr_is_wcd938x(uint64_t id)
{
	return id == PONG_SWR_WCD938X_ID;
}

/* S:PongWcd938.h:113-114  the codec identity is two consecutive 8-bit reads of
 * 0x50 and 0x51, low byte first. Kept here so the byte order is pinned once
 * rather than at the call site.
 */
static inline unsigned
pong_swr_codec_identity(uint8_t first, uint8_t second)
{
	return (unsigned)first | ((unsigned)second << 8);
}

/* ---- LPI pads ----------------------------------------------------------
 * W:5, S:PongWcd938.h:79-81  pins {0,1,2,14} carry the SWR clock and data0..2.
 * The write is (old & ~0x3f) | (1 << 2) | (index ? 2 : 0): function 1 for all
 * four, plus the data-bus-hold bit on the three data lines.
 */
#define PONG_CODEC_LPI_PHYS   0x03440000u
#define PONG_CODEC_LPI_STRIDE 0x00001000u

static inline unsigned
pong_codec_lpi_pin(unsigned index)
{
	static const unsigned pins[4] = {0u, 1u, 2u, 14u};

	if (index > 3u)
		return 0xffffffffu;
	return pins[index];
}

static inline uint32_t
pong_codec_lpi_pad_phys(unsigned index)
{
	unsigned pin = pong_codec_lpi_pin(index);

	if (pin == 0xffffffffu)
		return 0u;
	return PONG_CODEC_LPI_PHYS + PONG_CODEC_LPI_STRIDE * pin;
}

static inline uint32_t
pong_codec_lpi_pad_config(uint32_t old, unsigned index)
{
	return (old & ~0x3fu) | (1u << 2) | (index != 0u ? 2u : 0u);
}

/* ---- LPASS windows this half needs -------------------------------------
 * W:2 and W:7  five windows, each no larger than its live FDT node range.
 * The SWR master is mapped as 0x2000, not Pong's 0x10000: io_map() charges
 * whole 16 KiB pages out of a kernel-wide 8 MiB io_submap, so 0x10000 would
 * cost 64 KiB where 0x2000 costs 16 KiB.
 */
static inline unsigned
pong_codec_window_count(void)
{
	return 5u;
}

static inline bool
pong_codec_window(unsigned index, uint32_t *phys, uint32_t *size)
{
	switch (index) {
	case 0u:
		if (phys != NULL) *phys = 0x033f0000u;   /* va-macro@33F0000 */
		if (size != NULL) *size = 0x1000u;
		return true;
	case 1u:
		if (phys != NULL) *phys = 0x03220000u;   /* tx-macro@3220000 */
		if (size != NULL) *size = 0x1000u;
		return true;
	case 2u:
		if (phys != NULL) *phys = 0x033b0000u;   /* va_swr_master */
		if (size != NULL) *size = 0x2000u;
		return true;
	case 3u:
		if (phys != NULL) *phys = 0x03440000u;   /* lpi_pinctrl@3440000 */
		if (size != NULL) *size = 0x17000u;
		return true;
	case 4u:
		if (phys != NULL) *phys = 0x034da000u;   /* LPI slew */
		if (size != NULL) *size = 0x1000u;
		return true;
	default:
		return false;
	}
}

/* io_map() rounds every window up to the arm64 page (W:1 item 4). */
#define PONG_CODEC_PAGE_BYTES 0x00004000u
#define PONG_CODEC_IO_SUBMAP  (8u * 1024u * 1024u)

static inline uint32_t
pong_codec_pages(uint32_t bytes)
{
	if (bytes == 0u)
		return 0u;
	return (bytes + PONG_CODEC_PAGE_BYTES - 1u) / PONG_CODEC_PAGE_BYTES;
}

static inline uint32_t
pong_codec_window_bytes(void)
{
	uint32_t total = 0u;
	uint32_t size;
	unsigned i;

	for (i = 0u; i < pong_codec_window_count(); i++) {
		if (pong_codec_window(i, NULL, &size))
			total += pong_codec_pages(size) * PONG_CODEC_PAGE_BYTES;
	}
	return total;
}

static inline bool
pong_codec_budget_ok(uint32_t used_bytes, uint32_t want_bytes)
{
	if (used_bytes > PONG_CODEC_IO_SUBMAP)
		return false;
	return want_bytes <= PONG_CODEC_IO_SUBMAP - used_bytes;
}

/* ---- The gate that actually matters ------------------------------------
 * W:4  two PRM block votes and the 0x30c clock acknowledgement, in that
 * order, all before the first LPASS register access. One predicate instead of
 * three ifs at each call site, so no future edit can skip a vote.
 */
static inline bool
pong_codec_may_touch_lpass(bool macro_voted, bool dcodec_voted, bool clock_acked)
{
	return macro_voted && dcodec_voted && clock_acked;
}

#endif /* PONG_CODEC_PLAN_H */
