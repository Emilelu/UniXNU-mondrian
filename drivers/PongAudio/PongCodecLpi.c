/* SPDX-License-Identifier: BSD-2-Clause-Patent
 *
 * Step-at-a-time programming of the four SoundWire pads and the slew block.
 * See PongCodecLpi.h for why the order is pads first, slew last.
 */
#include "PongCodecLpi.h"

void
pong_codec_lpi_start(PongCodecLpi *l, const PongCodecLpiIo *io)
{
	unsigned i;

	if (l == 0) {
		return;
	}
	l->io.read = io != 0 ? io->read : 0;
	l->io.write = io != 0 ? io->write : 0;
	l->io.ctx = io != 0 ? io->ctx : 0;
	l->io.slew_read = io != 0 ? io->slew_read : 0;
	l->io.slew_write = io != 0 ? io->slew_write : 0;
	l->io.slew_ctx = io != 0 ? io->slew_ctx : 0;
	l->step = 0;
	l->slew_old = 0;
	l->slew_new = 0;
	l->writes = 0;
	for (i = 0; i < 4u; ++i) {
		l->pad_old[i] = 0;
		l->pad_new[i] = 0;
	}
}

static bool
pong_codec_lpi_ready(const PongCodecLpi *l)
{
	return l != 0 && l->io.read != 0 && l->io.write != 0 &&
	    l->io.slew_read != 0 && l->io.slew_write != 0;
}

bool
pong_codec_lpi_step(PongCodecLpi *l)
{
	if (!pong_codec_lpi_ready(l) || l->step >= PONG_CODEC_LPI_STEPS) {
		return false;
	}

	if (l->step < 4u) {
		uint32_t old = l->io.read(l->io.ctx, pong_codec_lpi_pin(l->step) * PONG_CODEC_LPI_STRIDE);
		uint32_t value = pong_codec_lpi_pad_config(old, l->step);

		l->io.write(l->io.ctx, pong_codec_lpi_pin(l->step) * PONG_CODEC_LPI_STRIDE, value);
		l->pad_old[l->step] = old;
		l->pad_new[l->step] = value;
		++l->writes;
		++l->step;
		return l->step < PONG_CODEC_LPI_STEPS;
	}

	/* Last step: the slew register is written once, after all four pads. */
	l->slew_old = l->io.slew_read(l->io.slew_ctx, 0u);
	l->slew_new = l->slew_old;
	{
		unsigned i;

		for (i = 0; i < 4u; ++i) {
			l->slew_new = pong_codec_lpi_slew_config(l->slew_new, i);
		}
	}
	l->io.slew_write(l->io.slew_ctx, 0u, l->slew_new);
	++l->writes;
	l->step = PONG_CODEC_LPI_STEPS;
	return false;
}

bool
pong_codec_lpi_done(const PongCodecLpi *l)
{
	return l != 0 && l->step >= PONG_CODEC_LPI_STEPS;
}
