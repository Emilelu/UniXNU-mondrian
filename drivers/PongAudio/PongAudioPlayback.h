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
pong_play_is_graph_step(unsigned step)
{
	return pong_play_opcode(step) == PONG_PLAY_OP_GRAPH_PREPARE ||
	    pong_play_opcode(step) == PONG_PLAY_OP_GRAPH_START;
}

#endif /* PONG_AUDIO_PLAYBACK_H */
