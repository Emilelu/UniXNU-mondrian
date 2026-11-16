/* SPDX-License-Identifier: BSD-2-Clause-Patent
 *
 * The PCM ring the audio service hands to the AFE path: how many frames a
 * period is, how far ahead of the play position the writer must stay, and
 * when the transport may start.
 *
 * The numbers are the vendor's, not ours. AGM opens the PCM device with
 * MAX_PERIOD_BUFFER 8192 bytes (M: agm/service/src/device.c:102) divided by
 * channels times bytes per sample (:273), DEFAULT_PERIOD_COUNT 2 (:103) and
 * start_threshold = period_size / 4 (:405). The speaker backend runs
 * S24_LE at 48 kHz stereo (resourcemanager_waipio_mtp.xml:459-470), and
 * get_pcm_bits_per_sample() counts S24_LE as 32 bits (device.c:140-141),
 * so one frame is 2 * 4 = 8 bytes and one period is 1024 frames.
 *
 * The ring itself is the ShengAudioAbi ring: 65536 frames, room for a 300 ms
 * lead and late HAL cycles (M: ShengAudioAbi.h:21), and lead_frames is that
 * 300 ms expressed in frames. Pure: no MMIO, no kernel headers.
 */
#ifndef PONG_AUDIO_RING_H
#define PONG_AUDIO_RING_H

#include <stdbool.h>
#include <stdint.h>

#define PONG_RING_RATE                 48000u
#define PONG_RING_CHANNELS             2u
#define PONG_RING_SAMPLE_BYTES         4u  /* S24_LE in a 32-bit word */
#define PONG_RING_FRAME_BYTES          (PONG_RING_CHANNELS * PONG_RING_SAMPLE_BYTES)
#define PONG_RING_PERIOD_FRAMES        1024u /* 8192 / (2 * 4) */
#define PONG_RING_PERIOD_COUNT         2u
#define PONG_RING_START_THRESHOLD_FRAMES (PONG_RING_PERIOD_FRAMES / 4u)
#define PONG_RING_LEAD_FRAMES          14400u /* 300 ms at 48 kHz */
#define PONG_RING_FRAMES               65536u
#define PONG_RING_INVALID              0xffffffffu

static inline uint32_t
pong_ring_frame_bytes(void)
{
	return PONG_RING_FRAME_BYTES;
}

static inline uint32_t
pong_ring_period_bytes(void)
{
	return PONG_RING_PERIOD_FRAMES * PONG_RING_FRAME_BYTES;
}

static inline uint32_t
pong_ring_ring_bytes(void)
{
	return PONG_RING_FRAMES * PONG_RING_FRAME_BYTES;
}

static inline uint32_t
pong_ring_period_ns(void)
{
	return (uint32_t)((1000000000ull * PONG_RING_PERIOD_FRAMES) / PONG_RING_RATE);
}

/* Advance a ring position by frames. Positions are frame indices in
 * [0, PONG_RING_FRAMES); anything else is rejected. */
static inline uint32_t
pong_ring_advance(uint32_t position, uint32_t frames)
{
	if (position >= PONG_RING_FRAMES) {
		return PONG_RING_INVALID;
	}
	return (position + frames % PONG_RING_FRAMES) % PONG_RING_FRAMES;
}

/* Frames written but not yet consumed, walking forward from from to to. */
static inline uint32_t
pong_ring_distance(uint32_t from, uint32_t to)
{
	if (from >= PONG_RING_FRAMES || to >= PONG_RING_FRAMES) {
		return PONG_RING_INVALID;
	}
	return (to + PONG_RING_FRAMES - from) % PONG_RING_FRAMES;
}

static inline bool
pong_ring_can_start(uint32_t frames_available)
{
	return frames_available >= PONG_RING_START_THRESHOLD_FRAMES;
}

/* One period of audio fits in the ring with room for the lead? */
static inline bool
pong_ring_geometry_ok(void)
{
	return PONG_RING_LEAD_FRAMES + PONG_RING_PERIOD_COUNT * PONG_RING_PERIOD_FRAMES
	    <= PONG_RING_FRAMES;
}

#endif /* PONG_AUDIO_RING_H */
