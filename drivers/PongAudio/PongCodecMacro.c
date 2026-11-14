/* SPDX-License-Identifier: BSD-2-Clause-Patent
 *
 * The VA and TX macro clock gates as a table walk. See PongCodecMacro.h.
 */
#include "PongCodecMacro.h"

/* S:PongWcd938.h:84-86, in order. The second VA 0x04 step reads the register
 * again after the first one wrote it, so each step must re-read: the sequence
 * is not "compose one value and write it three times". */
static const PongCodecMacroStep pong_codec_macro_table[PONG_CODEC_MACRO_STEPS] = {
	{ 0u, 0x000u, 0x0u, 0x1u },   /* VA MCLK_CONTROL: enable */
	{ 0u, 0x004u, 0x0u, 0x3u },   /* VA FS_CNT_CONTROL: both bits */
	{ 0u, 0x004u, 0x2u, 0x1u },   /* VA FS_CNT_CONTROL: clear the high bit */
	{ 0u, 0x080u, 0x0u, 0x2u },   /* VA TOP_CFG0 */
	{ 0u, 0x008u, 0x0u, 0x2u },   /* VA SWR_CONTROL: set */
	{ 0u, 0x008u, 0x0u, 0x1u },   /* VA SWR_CONTROL: enable */
	{ 0u, 0x008u, 0x2u, 0x0u },   /* VA SWR_CONTROL: release the high bit */
	{ 1u, 0x000u, 0x0u, 0x1u },   /* TX MCLK_CONTROL */
	{ 1u, 0x004u, 0x0u, 0x1u },   /* TX FS_CNT_CONTROL */
};

bool
pong_codec_macro_plan(unsigned index, PongCodecMacroStep *out)
{
	if (index >= PONG_CODEC_MACRO_STEPS || out == 0) {
		return false;
	}
	*out = pong_codec_macro_table[index];
	return true;
}

void
pong_codec_macro_start(PongCodecMacro *m, const PongCodecMacroIo *io)
{
	unsigned i;

	if (m == 0) {
		return;
	}
	m->io.va.read = io != 0 ? io->va.read : 0;
	m->io.va.write = io != 0 ? io->va.write : 0;
	m->io.va.ctx = io != 0 ? io->va.ctx : 0;
	m->io.tx.read = io != 0 ? io->tx.read : 0;
	m->io.tx.write = io != 0 ? io->tx.write : 0;
	m->io.tx.ctx = io != 0 ? io->tx.ctx : 0;
	m->step = 0;
	m->writes = 0;
	for (i = 0; i < PONG_CODEC_MACRO_STEPS; ++i) {
		m->old[i] = 0;
		m->now[i] = 0;
	}
}

static bool
pong_codec_macro_ready(const PongCodecMacro *m)
{
	return m != 0 && m->io.va.read != 0 && m->io.va.write != 0 &&
	    m->io.tx.read != 0 && m->io.tx.write != 0;
}

bool
pong_codec_macro_step(PongCodecMacro *m)
{
	const PongCodecMacroStep *entry;
	const PongCodecMacroWindow *window;
	uint32_t old, value;

	if (!pong_codec_macro_ready(m) || m->step >= PONG_CODEC_MACRO_STEPS) {
		return false;
	}

	entry = &pong_codec_macro_table[m->step];
	window = entry->tx != 0u ? &m->io.tx : &m->io.va;
	old = window->read(window->ctx, entry->reg);
	value = pong_codec_macro_value(old, entry->clear, entry->set);
	window->write(window->ctx, entry->reg, value);
	m->old[m->step] = old;
	m->now[m->step] = value;
	++m->writes;
	++m->step;
	return m->step < PONG_CODEC_MACRO_STEPS;
}

bool
pong_codec_macro_done(const PongCodecMacro *m)
{
	return m != 0 && m->step >= PONG_CODEC_MACRO_STEPS;
}
