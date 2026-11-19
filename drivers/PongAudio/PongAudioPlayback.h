/* SPDX-License-Identifier: BSD-2-Clause-Patent
 *
 * The AudioReach playback graph order the AFE pump follows after the six-step
 * setup. This is the order PongAudio.cpp openGraphs()/start() use: the two
 * endpoints are opened and configured first, their shared-memory buffer is
 * mapped, the tertiary MI2S bit clock is voted, and only then are the speaker
 * and playback graphs prepared and started. Pure: no kernel headers.
 */
#ifndef PONG_AUDIO_PLAYBACK_H
#define PONG_AUDIO_PLAYBACK_H

#include <stdbool.h>
#include <stdint.h>

#define PONG_PLAY_OP_GRAPH_OPEN     0x01001000u
#define PONG_PLAY_OP_GRAPH_PREPARE  0x01001001u
#define PONG_PLAY_OP_GRAPH_START    0x01001002u
#define PONG_PLAY_OP_SET_CFG        0x01001006u
#define PONG_PLAY_OP_MEM_MAP        0x0100100Cu
#define PONG_PLAY_OP_PRM_REQUEST    0x0100100Fu

#define PONG_PLAY_SG_PLAY           0x4001u
#define PONG_PLAY_SG_SPEAKER        0x4005u

#define PONG_PLAY_SLOT_COUNT        8u
#define PONG_PLAY_PERIOD_BYTES      8192u
#define PONG_PLAY_PRIME_SLOTS       4u
#define PONG_PLAY_SLOT_TIMEOUT_PUMPS 8u

typedef enum {
	PongPlayOpenSpeaker = 0,
	PongPlayConfigSpeaker,
	PongPlayOpenPlayback,
	PongPlayConfigPlayback,
	PongPlayConfigShmem,
	PongPlayMap,
	PongPlayClock,
	PongPlayPrepareSpeaker,
	PongPlayPreparePlayback,
	PongPlayStartPair,
	PongPlayStartSpeaker,
	PongPlayStartPlayback,
	PongPlayStepCount
} PongPlayStep;

static inline uint32_t
pong_play_token(unsigned step)
{
	return 0x00030000u + step;
}

static inline uint32_t
pong_play_opcode(unsigned step)
{
	switch (step) {
	case PongPlayOpenSpeaker:
	case PongPlayOpenPlayback:
		return PONG_PLAY_OP_GRAPH_OPEN;
	case PongPlayConfigSpeaker:
	case PongPlayConfigPlayback:
	case PongPlayConfigShmem:
		return PONG_PLAY_OP_SET_CFG;
	case PongPlayMap:
		return PONG_PLAY_OP_MEM_MAP;
	case PongPlayClock:
		return PONG_PLAY_OP_PRM_REQUEST;
	case PongPlayPrepareSpeaker:
	case PongPlayPreparePlayback:
		return PONG_PLAY_OP_GRAPH_PREPARE;
	case PongPlayStartPair:
	case PongPlayStartSpeaker:
	case PongPlayStartPlayback:
		return PONG_PLAY_OP_GRAPH_START;
	default:
		return 0;
	}
}

static inline uint32_t
pong_play_sg(unsigned step)
{
	switch (step) {
	case PongPlayOpenSpeaker:
	case PongPlayConfigSpeaker:
	case PongPlayPrepareSpeaker:
	case PongPlayStartSpeaker:
		return PONG_PLAY_SG_SPEAKER;
	case PongPlayOpenPlayback:
	case PongPlayConfigPlayback:
	case PongPlayConfigShmem:
	case PongPlayPreparePlayback:
	case PongPlayStartPlayback:
		return PONG_PLAY_SG_PLAY;
	default:
		return 0;
	}
}

static inline bool
pong_play_slot_expired(uint32_t age)
{
	return age >= PONG_PLAY_SLOT_TIMEOUT_PUMPS;
}

/* The DSP decodes the upper word of a buffer address as the audio stream
 * index: the reference audio client sends its 0x1001 stream as index 1, and a
 * 36-bit address whose upper word it cannot decode is refused. The shared
 * memory map and the writes both carry this tagged address, so the two sides
 * name one buffer. */
static inline uint64_t
pong_play_dsp_address(uint64_t dma_pa)
{
	return dma_pa | (1ull << 32);
}

static inline uint64_t
pong_play_slot_address(uint64_t dma_pa, unsigned slot)
{
	return pong_play_dsp_address(dma_pa) +
	    (uint64_t)slot * PONG_PLAY_PERIOD_BYTES;
}

static inline bool
pong_play_is_graph_step(unsigned step)
{
	return pong_play_opcode(step) == PONG_PLAY_OP_GRAPH_PREPARE ||
	    pong_play_opcode(step) == PONG_PLAY_OP_GRAPH_START;
}

#endif /* PONG_AUDIO_PLAYBACK_H */
